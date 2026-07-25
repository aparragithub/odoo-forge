"""Opt-in real-Docker acceptance harness for the byte-level `MaskTransform`.

Every other mask-transform test asserts the GENERATED SQL string against a mocked
runner. That proves what we emit, never that Postgres accepts it or that the rows
actually change. This harness closes that gap: it builds a real source database,
captures it with a real `pg_dump`, runs the real transform through a real scratch
container, and then restores the masked archive and reads the rows back.

Run with `-m real_docker` (deselected by default, like the sibling adapter harnesses).
"""

from __future__ import annotations

import hashlib
import subprocess
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from odoo_forge.anonymization.policy import AnonymizationRule, MaskStrategy
from odoo_forge.data_artifacts.contracts import (
    ArtifactComponentKind,
    ArtifactDigest,
    RestoreSetComponent,
)
from odoo_forge_postgres_docker.mask_transform import (
    MaskColumnTypeUnsupportedError,
    MaskSelectorNotFoundError,
    MaskUniqueColumnCollisionError,
    make_docker_mask_transform,
)
from odoo_forge_postgres_docker.staged_store import FilesystemStagedArtifactStore

pytestmark = [pytest.mark.integration, pytest.mark.real_docker]

_IMAGE = "postgres:16"
_SOURCE_DB = "sourcedb"


def _docker(argv: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(  # noqa: S603 - test harness, argv-only
        ["docker", *argv], capture_output=True, check=False
    )


def _require_real_docker() -> None:
    try:
        result = _docker(["info", "--format", "{{.ServerVersion}}"])
    except FileNotFoundError:
        pytest.skip("Docker prerequisite unavailable: executable not found")
    if result.returncode != 0:
        pytest.skip("Docker prerequisite unavailable: daemon is unreachable")


def _wait_for_database(container: str, database: str = _SOURCE_DB) -> None:
    """Poll until `database` itself answers a query.

    Deliberately NOT `pg_isready`: the postgres entrypoint runs a temporary bootstrap
    server during initdb, so `pg_isready` reports ready BEFORE `POSTGRES_DB` has been
    created. Only a real query against the target database proves it exists.
    """
    for _ in range(120):
        probe = _docker(
            ["exec", container, "psql", "-U", "postgres", "-d", database, "-tAc", "SELECT 1"]
        )
        if probe.returncode == 0:
            return
        time.sleep(0.25)
    pytest.fail(f"database {database} never became reachable in {container}")


def _sql(container: str, statement: str, database: str = _SOURCE_DB) -> str:
    result = _docker(
        [
            "exec",
            container,
            "psql",
            "-U",
            "postgres",
            "-d",
            database,
            "-v",
            "ON_ERROR_STOP=1",
            "-tAc",
            statement,
        ]
    )
    assert result.returncode == 0, result.stderr.decode()
    return result.stdout.decode().strip()


@contextmanager
def _source_database(schema: str) -> Iterator[str]:
    """Start a real Postgres, apply `schema`, and always tear it down."""
    container = f"odoo-forge-masktest-{uuid.uuid4().hex[:12]}"
    started = _docker(
        [
            "run",
            "--detach",
            "--name",
            container,
            "--network",
            "none",
            "--env",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            "--env",
            f"POSTGRES_DB={_SOURCE_DB}",
            _IMAGE,
        ]
    )
    assert started.returncode == 0, started.stderr.decode()
    try:
        _wait_for_database(container)
        _sql(container, schema)
        yield container
    finally:
        _docker(["rm", "-f", container])


def _capture(container: str, tmp_path: Path) -> Path:
    """Produce a real `pg_dump --format=custom` archive of the source database."""
    dump_path = tmp_path / "source.dump"
    with dump_path.open("wb") as handle:
        result = subprocess.run(  # noqa: S603 - test harness, argv-only
            [
                "docker",
                "exec",
                container,
                "pg_dump",
                "-U",
                "postgres",
                "--format=custom",
                _SOURCE_DB,
            ],
            stdout=handle,
            stderr=subprocess.PIPE,
            check=False,
        )
    assert result.returncode == 0, result.stderr.decode()
    assert dump_path.stat().st_size > 0
    return dump_path


def _staged(
    tmp_path: Path, dump_path: Path
) -> tuple[FilesystemStagedArtifactStore, RestoreSetComponent]:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    digest = ArtifactDigest(
        algorithm="sha256", value=hashlib.sha256(dump_path.read_bytes()).hexdigest()
    )
    component = RestoreSetComponent(
        kind=ArtifactComponentKind.DATABASE,
        opaque_component_ref="database-sourcedb",
        format_version="pg_dump-custom-v1",
        digest=digest,
    )
    store.stage(digest, dump_path)
    return store, component


@contextmanager
def _restored(masked_path: Path) -> Iterator[str]:
    """Restore a masked archive into a fresh container so its rows can be read back."""
    container = f"odoo-forge-maskverify-{uuid.uuid4().hex[:12]}"
    started = _docker(
        [
            "run",
            "--detach",
            "--name",
            container,
            "--network",
            "none",
            "--env",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            "--env",
            f"POSTGRES_DB={_SOURCE_DB}",
            _IMAGE,
        ]
    )
    assert started.returncode == 0, started.stderr.decode()
    try:
        _wait_for_database(container)
        with masked_path.open("rb") as handle:
            restore = subprocess.run(  # noqa: S603 - test harness, argv-only
                [
                    "docker",
                    "exec",
                    "-i",
                    container,
                    "pg_restore",
                    "-U",
                    "postgres",
                    "-d",
                    _SOURCE_DB,
                    "--no-owner",
                    "--clean",
                    "--if-exists",
                ],
                stdin=handle,
                capture_output=True,
                check=False,
            )
        assert restore.returncode == 0, restore.stderr.decode()
        yield container
    finally:
        _docker(["rm", "-f", container])


_TEXT_SCHEMA = """
CREATE TABLE res_partner (
    id serial PRIMARY KEY,
    email text,
    phone text,
    city text
);
INSERT INTO res_partner (email, phone, city) VALUES
    ('ada@example.test', '+34 600 000 001', 'Madrid'),
    ('alan@example.test', '+34 600 000 002', 'Rosario');
"""


def test_masking_actually_changes_the_rows_end_to_end(tmp_path: Path) -> None:
    """The whole point: a real dump goes in, real masked rows come out.

    Nothing else in the suite proves the emitted SQL is even accepted by Postgres,
    let alone that it rewrites the data. This asserts the restored, masked database
    no longer contains the original values.
    """
    _require_real_docker()
    with _source_database(_TEXT_SCHEMA) as source:
        dump_path = _capture(source, tmp_path)
    store, component = _staged(tmp_path, dump_path)
    transform = make_docker_mask_transform(store=store)

    masked = transform(
        component,
        (
            AnonymizationRule(table="res_partner", column="email", mask_strategy=MaskStrategy.HASH),
            AnonymizationRule(
                table="res_partner", column="phone", mask_strategy=MaskStrategy.NULLIFY
            ),
            AnonymizationRule(
                table="res_partner", column="city", mask_strategy=MaskStrategy.REDACT
            ),
        ),
    )

    assert masked.digest != component.digest
    with _restored(store.open_component(masked)) as verifier:
        emails = _sql(verifier, "SELECT email FROM res_partner ORDER BY id")
        phones = _sql(verifier, "SELECT coalesce(phone, 'NULL') FROM res_partner ORDER BY id")
        cities = _sql(verifier, "SELECT city FROM res_partner ORDER BY id")
        row_count = _sql(verifier, "SELECT count(*) FROM res_partner")

    assert row_count == "2", "masking must not drop or duplicate rows"
    assert "ada@example.test" not in emails and "alan@example.test" not in emails
    assert emails.split("\n") == [
        hashlib.md5(b"ada@example.test").hexdigest(),  # noqa: S324 - asserting md5(), not securing
        hashlib.md5(b"alan@example.test").hexdigest(),  # noqa: S324
    ], "HASH must be deterministic md5 of the original value"
    assert phones.split("\n") == ["NULL", "NULL"]
    assert cities.split("\n") == ["[REDACTED]", "[REDACTED]"]


def test_hash_on_a_non_text_column(tmp_path: Path) -> None:
    """Review #175 item 1: does `md5(col::text)` on an integer column actually fail?

    Asserted against a real backend rather than reasoned about — the mocked-runner
    tests cannot answer this either way.
    """
    _require_real_docker()
    schema = """
    CREATE TABLE account (id serial PRIMARY KEY, balance integer);
    INSERT INTO account (balance) VALUES (100), (250);
    """
    with _source_database(schema) as source:
        dump_path = _capture(source, tmp_path)
    store, component = _staged(tmp_path, dump_path)
    transform = make_docker_mask_transform(store=store)

    with pytest.raises(MaskColumnTypeUnsupportedError):
        transform(
            component,
            (
                AnonymizationRule(
                    table="account", column="balance", mask_strategy=MaskStrategy.HASH
                ),
            ),
        )


def test_redact_on_a_unique_column(tmp_path: Path) -> None:
    """Review #175 item 2: does collapsing a UNIQUE column to one literal fail?"""
    _require_real_docker()
    schema = """
    CREATE TABLE res_users (id serial PRIMARY KEY, login text UNIQUE);
    INSERT INTO res_users (login) VALUES ('ada'), ('alan');
    """
    with _source_database(schema) as source:
        dump_path = _capture(source, tmp_path)
    store, component = _staged(tmp_path, dump_path)
    transform = make_docker_mask_transform(store=store)

    with pytest.raises(MaskUniqueColumnCollisionError):
        transform(
            component,
            (
                AnonymizationRule(
                    table="res_users", column="login", mask_strategy=MaskStrategy.REDACT
                ),
            ),
        )


def test_hash_on_a_unique_column_is_accepted_by_a_real_backend(tmp_path: Path) -> None:
    """The permissive half of #175 item 2: HASH keeps distinct inputs distinct, so a
    UNIQUE column is a legitimate target and the pre-flight must not over-reject it.
    Proven by actually restoring the masked archive and reading the rows back."""
    _require_real_docker()
    schema = """
    CREATE TABLE res_users (id serial PRIMARY KEY, login text UNIQUE);
    INSERT INTO res_users (login) VALUES ('ada'), ('alan');
    """
    with _source_database(schema) as source:
        dump_path = _capture(source, tmp_path)
    store, component = _staged(tmp_path, dump_path)
    transform = make_docker_mask_transform(store=store)

    masked = transform(
        component,
        (AnonymizationRule(table="res_users", column="login", mask_strategy=MaskStrategy.HASH),),
    )

    with _restored(store.open_component(masked)) as verifier:
        logins = _sql(verifier, "SELECT login FROM res_users ORDER BY id")
    assert logins.split("\n") == [
        hashlib.md5(b"ada").hexdigest(),  # noqa: S324 - asserting md5(), not securing
        hashlib.md5(b"alan").hexdigest(),  # noqa: S324
    ]


def test_a_typo_in_a_selector_is_caught_before_any_row_is_touched(tmp_path: Path) -> None:
    """#175: a policy typo used to reach Postgres as a failing UPDATE and surface as a
    generic command failure with the reason discarded to DEVNULL."""
    _require_real_docker()
    with _source_database(_TEXT_SCHEMA) as source:
        dump_path = _capture(source, tmp_path)
    store, component = _staged(tmp_path, dump_path)
    transform = make_docker_mask_transform(store=store)

    with pytest.raises(MaskSelectorNotFoundError):
        transform(
            component,
            (
                AnonymizationRule(
                    table="res_partner", column="no_such_column", mask_strategy=MaskStrategy.REDACT
                ),
            ),
        )
