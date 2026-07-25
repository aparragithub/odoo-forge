"""RED-first tests for the real byte-level `MaskTransform` (scratch-DB round trip).

A `pg_dump --format=custom` archive is opaque: its rows cannot be rewritten in
place. So masking restores the captured dump into a THROWAWAY container,
applies one `UPDATE` per `AnonymizationRule` there, re-dumps, and stages the
masked bytes under a new digest. The raw bytes therefore never reach the
delivery target — the anonymize-before-delivery contract holds.
"""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import IO, NoReturn, cast

import pytest

from odoo_forge.anonymization.policy import AnonymizationRule, MaskStrategy
from odoo_forge.data_artifacts.contracts import (
    ArtifactComponentKind,
    ArtifactDigest,
    RestoreSetComponent,
)
from odoo_forge.data_artifacts.staging import StagedArtifactStore
from odoo_forge_postgres_docker.mask_transform import (
    DockerMaskRunner,
    MaskBinaryUnavailableError,
    MaskCommandFailedError,
    MaskPersistenceError,
    MaskScratchUnavailableError,
    MaskTimeoutError,
    ScratchDatabase,
    ScratchDatabaseFactory,
    docker_scratch_database,
    make_docker_mask_transform,
)
from odoo_forge_postgres_docker.staged_store import FilesystemStagedArtifactStore

_RAW = b"raw-pii-dump-bytes"
_MASKED = b"masked-dump-bytes"


def _digest_of(payload: bytes) -> ArtifactDigest:
    return ArtifactDigest(algorithm="sha256", value=hashlib.sha256(payload).hexdigest())


def _store_with_raw(tmp_path: Path, payload: bytes = _RAW) -> FilesystemStagedArtifactStore:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    source = tmp_path / "raw-dump"
    source.write_bytes(payload)
    store.stage(_digest_of(payload), source)
    return store


def _database_component(payload: bytes = _RAW) -> RestoreSetComponent:
    return RestoreSetComponent(
        kind=ArtifactComponentKind.DATABASE,
        opaque_component_ref="database-odoo-source",
        format_version="pg_dump-custom-v1",
        digest=_digest_of(payload),
    )


def _rule(
    table: str = "res_partner",
    column: str = "email",
    strategy: MaskStrategy = MaskStrategy.HASH,
    static_value: str | None = None,
) -> AnonymizationRule:
    return AnonymizationRule(
        table=table, column=column, mask_strategy=strategy, static_value=static_value
    )


class _RecordingRunner:
    """Records every scratch-container invocation and fakes the re-dump output."""

    def __init__(self, *, masked: bytes = _MASKED, returncode: int = 0) -> None:
        self.calls: list[list[str]] = []
        self.stdin_bytes: list[bytes] = []
        self._masked = masked
        self._returncode = returncode

    def __call__(
        self,
        argv: Sequence[str],
        *,
        stdin: IO[bytes] | None = None,
        stdout: IO[bytes] | None = None,
        timeout: float,
    ) -> subprocess.CompletedProcess[bytes]:
        self.calls.append(list(argv))
        if stdin is not None:
            self.stdin_bytes.append(stdin.read())
        if stdout is not None:
            stdout.write(self._masked)
            stdout.flush()
        return subprocess.CompletedProcess(list(argv), self._returncode)

    def statements(self) -> list[str]:
        """Every `-c <sql>` payload, in invocation order."""
        return [argv[argv.index("-c") + 1] for argv in self.calls if "-c" in argv]


def _scratch_factory(
    opened: list[str] | None = None, closed: list[str] | None = None
) -> ScratchDatabaseFactory:
    @contextmanager
    def _factory() -> Iterator[ScratchDatabase]:
        scratch = ScratchDatabase(container="odoo-forge-mask-test", database="maskdb")
        if opened is not None:
            opened.append(scratch.container)
        try:
            yield scratch
        finally:
            if closed is not None:
                closed.append(scratch.container)

    return _factory


class _StageFailingStore:
    """A store that resolves raw bytes fine but cannot take custody of masked ones."""

    def __init__(self, inner: FilesystemStagedArtifactStore) -> None:
        self._inner = inner

    def open_component(self, component: RestoreSetComponent) -> Path:
        return self._inner.open_component(component)

    def stage(self, digest: ArtifactDigest, source_path: Path) -> None:
        raise RuntimeError("simulated stage failure")

    def put(self, ref: object, manifest: object) -> None:
        raise NotImplementedError

    def resolve(self, ref: object) -> object:
        raise NotImplementedError

    def discard(self, ref: object) -> object:
        raise NotImplementedError


class TestEmptyPolicyIsAPureNoOp:
    """An empty policy must not round-trip through a scratch container: `pg_dump` is
    not byte-stable, so a pointless round trip would churn the digest and spin up a
    container holding raw PII for nothing."""

    def test_no_rules_returns_the_component_unchanged(self, tmp_path: Path) -> None:
        runner = _RecordingRunner()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path),
            runner=runner,
            scratch_factory=_scratch_factory(),
        )
        component = _database_component()

        assert transform(component, ()) == component

    def test_no_rules_never_starts_a_scratch_container(self, tmp_path: Path) -> None:
        opened: list[str] = []
        runner = _RecordingRunner()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path),
            runner=runner,
            scratch_factory=_scratch_factory(opened),
        )

        transform(_database_component(), ())

        assert opened == []
        assert runner.calls == []


class TestFilestoreComponentIsPassedThrough:
    def test_a_filestore_component_is_never_masked(self, tmp_path: Path) -> None:
        """D6: the filestore component is a metadata-only placeholder with no staged
        blob, so there is nothing to mask and `open_component` must never be called."""
        opened: list[str] = []
        component = RestoreSetComponent(
            kind=ArtifactComponentKind.FILESTORE,
            opaque_component_ref="filestore-empty-v1",
            format_version="empty-v1",
            digest=_digest_of(b""),
        )
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path),
            runner=_RecordingRunner(),
            scratch_factory=_scratch_factory(opened),
        )

        assert transform(component, (_rule(),)) == component
        assert opened == []


class TestScratchRoundTrip:
    def test_the_raw_dump_is_restored_into_the_scratch_database(self, tmp_path: Path) -> None:
        runner = _RecordingRunner()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path), runner=runner, scratch_factory=_scratch_factory()
        )

        transform(_database_component(), (_rule(),))

        restore_argv = next(argv for argv in runner.calls if "pg_restore" in argv)
        assert restore_argv[:4] == ["docker", "exec", "-i", "odoo-forge-mask-test"]
        assert "-d" in restore_argv and "maskdb" in restore_argv
        assert runner.stdin_bytes == [_RAW], "the staged raw bytes stream into pg_restore"

    def test_the_masked_dump_is_staged_and_returned_under_its_new_digest(
        self, tmp_path: Path
    ) -> None:
        store = _store_with_raw(tmp_path)
        transform = make_docker_mask_transform(
            store=store, runner=_RecordingRunner(), scratch_factory=_scratch_factory()
        )

        masked = transform(_database_component(), (_rule(),))

        assert masked.digest == _digest_of(_MASKED)
        assert masked.digest != _database_component().digest
        assert store.open_component(masked).read_bytes() == _MASKED

    def test_the_component_identity_and_format_survive_masking(self, tmp_path: Path) -> None:
        """Only the digest changes: the coordinator (D11) re-persists the manifest, and
        the component must stay the same component, in the same archive format."""
        original = _database_component()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path),
            runner=_RecordingRunner(),
            scratch_factory=_scratch_factory(),
        )

        masked = transform(original, (_rule(),))

        assert masked.kind is original.kind
        assert masked.opaque_component_ref == original.opaque_component_ref
        assert masked.format_version == original.format_version

    def test_the_re_dump_uses_the_same_custom_archive_format(self, tmp_path: Path) -> None:
        runner = _RecordingRunner()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path), runner=runner, scratch_factory=_scratch_factory()
        )

        transform(_database_component(), (_rule(),))

        dump_argv = next(argv for argv in runner.calls if "pg_dump" in argv)
        assert "--format=custom" in dump_argv

    def test_restore_masking_and_re_dump_run_in_that_order(self, tmp_path: Path) -> None:
        """Re-dumping before the UPDATEs would ship unmasked bytes under a digest that
        claims to be anonymized — the exact failure this whole path exists to prevent."""
        runner = _RecordingRunner()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path), runner=runner, scratch_factory=_scratch_factory()
        )

        transform(_database_component(), (_rule(),))

        stages = [
            next(tool for tool in ("pg_restore", "psql", "pg_dump") if tool in argv)
            for argv in runner.calls
            if any(tool in argv for tool in ("pg_restore", "psql", "pg_dump"))
        ]
        assert stages == ["pg_restore", "psql", "pg_dump"]

    def test_the_scratch_container_is_torn_down_on_success(self, tmp_path: Path) -> None:
        closed: list[str] = []
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path),
            runner=_RecordingRunner(),
            scratch_factory=_scratch_factory(closed=closed),
        )

        transform(_database_component(), (_rule(),))

        assert closed == ["odoo-forge-mask-test"]

    def test_the_scratch_container_is_torn_down_when_masking_fails(self, tmp_path: Path) -> None:
        """The scratch database holds the RAW, un-anonymized data. A failure that left
        it running would leave unmasked PII in a container nobody is tracking."""
        closed: list[str] = []
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path),
            runner=_RecordingRunner(returncode=1),
            scratch_factory=_scratch_factory(closed=closed),
        )

        with pytest.raises(MaskCommandFailedError):
            transform(_database_component(), (_rule(),))

        assert closed == ["odoo-forge-mask-test"]


class TestMaskStrategySql:
    """Every `MaskStrategy` in the fixed v1 vocabulary maps to one `UPDATE`."""

    def _statement_for(self, tmp_path: Path, rule: AnonymizationRule) -> str:
        runner = _RecordingRunner()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path), runner=runner, scratch_factory=_scratch_factory()
        )
        transform(_database_component(), (rule,))
        return runner.statements()[0]

    def test_hash_replaces_the_value_with_a_digest_of_itself(self, tmp_path: Path) -> None:
        statement = self._statement_for(tmp_path, _rule(strategy=MaskStrategy.HASH))
        assert statement == 'UPDATE "res_partner" SET "email" = md5("email"::text)'

    def test_nullify_sets_the_column_to_null(self, tmp_path: Path) -> None:
        statement = self._statement_for(tmp_path, _rule(strategy=MaskStrategy.NULLIFY))
        assert statement == 'UPDATE "res_partner" SET "email" = NULL'

    def test_redact_replaces_the_value_with_a_fixed_marker(self, tmp_path: Path) -> None:
        statement = self._statement_for(tmp_path, _rule(strategy=MaskStrategy.REDACT))
        assert statement == 'UPDATE "res_partner" SET "email" = \'[REDACTED]\''

    def test_static_replace_uses_the_configured_value(self, tmp_path: Path) -> None:
        statement = self._statement_for(
            tmp_path,
            _rule(strategy=MaskStrategy.STATIC_REPLACE, static_value="masked@example.test"),
        )
        assert statement == 'UPDATE "res_partner" SET "email" = \'masked@example.test\''

    def test_every_v1_strategy_is_implemented(self, tmp_path: Path) -> None:
        """A new `MaskStrategy` member must not silently fall through to a no-op."""
        for strategy in MaskStrategy:
            static_value = "x" if strategy is MaskStrategy.STATIC_REPLACE else None
            statement = self._statement_for(
                tmp_path, _rule(strategy=strategy, static_value=static_value)
            )
            assert statement.startswith('UPDATE "res_partner" SET "email" = ')

    def test_one_update_is_issued_per_rule(self, tmp_path: Path) -> None:
        runner = _RecordingRunner()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path), runner=runner, scratch_factory=_scratch_factory()
        )

        transform(
            _database_component(),
            (
                _rule(column="email"),
                _rule(column="phone", strategy=MaskStrategy.NULLIFY),
                _rule(table="res_users", column="login", strategy=MaskStrategy.REDACT),
            ),
        )

        assert len(runner.statements()) == 3

    def test_masking_aborts_on_the_first_error_rather_than_continuing(self, tmp_path: Path) -> None:
        """`ON_ERROR_STOP` plus a nonzero exit: a rule that cannot be applied (missing
        table or column) fails the whole transform. Delivering a dump stamped
        'anonymized' with one rule silently skipped is the worst possible outcome."""
        runner = _RecordingRunner()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path), runner=runner, scratch_factory=_scratch_factory()
        )

        transform(_database_component(), (_rule(),))

        psql_argv = next(argv for argv in runner.calls if "psql" in argv)
        assert "ON_ERROR_STOP=1" in psql_argv


class TestSqlInjectionSafety:
    def test_identifiers_are_double_quoted(self, tmp_path: Path) -> None:
        """Selectors permit `-`, which is subtraction in an unquoted identifier. The
        selector charset excludes `"`, so double-quoting cannot be escaped out of."""
        runner = _RecordingRunner()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path), runner=runner, scratch_factory=_scratch_factory()
        )

        transform(
            _database_component(),
            (_rule(table="res-partner", column="e-mail", strategy=MaskStrategy.NULLIFY),),
        )

        assert runner.statements()[0] == 'UPDATE "res-partner" SET "e-mail" = NULL'

    def test_a_static_value_single_quote_is_escaped(self, tmp_path: Path) -> None:
        """`static_value` is the only free-form field in a rule and is NOT covered by
        the selector charset, so it is the one real injection surface."""
        runner = _RecordingRunner()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path), runner=runner, scratch_factory=_scratch_factory()
        )

        transform(
            _database_component(),
            (
                _rule(
                    strategy=MaskStrategy.STATIC_REPLACE,
                    static_value="'; DROP TABLE res_users; --",
                ),
            ),
        )

        assert (
            runner.statements()[0]
            == "UPDATE \"res_partner\" SET \"email\" = '''; DROP TABLE res_users; --'"
        )

    def test_every_invocation_is_argv_only(self, tmp_path: Path) -> None:
        runner = _RecordingRunner()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path), runner=runner, scratch_factory=_scratch_factory()
        )

        transform(_database_component(), (_rule(),))

        for argv in runner.calls:
            assert all(isinstance(item, str) for item in argv)
            assert argv[0] == "docker"


class TestFailureTaxonomy:
    def _transform(
        self, tmp_path: Path, runner: DockerMaskRunner
    ) -> Callable[[RestoreSetComponent, tuple[AnonymizationRule, ...]], RestoreSetComponent]:
        return make_docker_mask_transform(
            store=_store_with_raw(tmp_path), runner=runner, scratch_factory=_scratch_factory()
        )

    def test_a_nonzero_exit_raises_the_command_failed_error(self, tmp_path: Path) -> None:
        transform = self._transform(tmp_path, _RecordingRunner(returncode=1))

        with pytest.raises(MaskCommandFailedError) as exc_info:
            transform(_database_component(), (_rule(),))

        assert str(exc_info.value) == MaskCommandFailedError.public_detail

    def test_a_missing_docker_binary_raises_the_binary_error(self, tmp_path: Path) -> None:
        class _MissingBinaryRunner:
            def __call__(self, argv: Sequence[str], **kwargs: object) -> NoReturn:
                raise FileNotFoundError("docker")

        transform = self._transform(tmp_path, _MissingBinaryRunner())

        with pytest.raises(MaskBinaryUnavailableError) as exc_info:
            transform(_database_component(), (_rule(),))

        assert str(exc_info.value) == MaskBinaryUnavailableError.public_detail

    def test_a_timeout_raises_the_timeout_error(self, tmp_path: Path) -> None:
        class _TimeoutRunner:
            def __call__(self, argv: Sequence[str], **kwargs: object) -> NoReturn:
                raise subprocess.TimeoutExpired(list(argv), 1.0)

        transform = self._transform(tmp_path, _TimeoutRunner())

        with pytest.raises(MaskTimeoutError) as exc_info:
            transform(_database_component(), (_rule(),))

        assert str(exc_info.value) == MaskTimeoutError.public_detail

    def test_a_store_failure_raises_the_persistence_error(self, tmp_path: Path) -> None:
        transform = make_docker_mask_transform(
            store=cast("StagedArtifactStore", _StageFailingStore(_store_with_raw(tmp_path))),
            runner=_RecordingRunner(),
            scratch_factory=_scratch_factory(),
        )

        with pytest.raises(MaskPersistenceError) as exc_info:
            transform(_database_component(), (_rule(),))

        assert str(exc_info.value) == MaskPersistenceError.public_detail

    def test_an_unavailable_scratch_database_raises_its_own_error(self, tmp_path: Path) -> None:
        @contextmanager
        def _failing_factory() -> Iterator[ScratchDatabase]:
            raise MaskScratchUnavailableError()
            yield  # pragma: no cover - unreachable, keeps this a generator

        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path),
            runner=_RecordingRunner(),
            scratch_factory=_failing_factory,
        )

        with pytest.raises(MaskScratchUnavailableError):
            transform(_database_component(), (_rule(),))


class TestStagedTempFileCleanup:
    def test_the_re_dump_temp_file_is_removed_on_success(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """On success the store MOVES the file into custody; the transform's `finally`
        must find nothing left to clean, and leave no second copy behind."""
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path),
            runner=_RecordingRunner(),
            scratch_factory=_scratch_factory(),
        )

        transform(_database_component(), (_rule(),))

        assert list(tmp_path.glob("odoo-forge-mask-*")) == []

    def test_the_re_dump_temp_file_is_removed_when_the_dump_fails(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path),
            runner=_RecordingRunner(returncode=1),
            scratch_factory=_scratch_factory(),
        )

        with pytest.raises(MaskCommandFailedError):
            transform(_database_component(), (_rule(),))

        assert list(tmp_path.glob("odoo-forge-mask-*")) == []


class TestDefaultScratchDatabaseFactory:
    """The default factory owns a real throwaway container end to end."""

    def test_it_starts_waits_for_readiness_and_always_removes_the_container(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[list[str]] = []

        def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            calls.append(list(argv))
            return subprocess.CompletedProcess(list(argv), 0)

        monkeypatch.setattr(subprocess, "run", _fake_run)

        with docker_scratch_database() as scratch:
            assert scratch.container.startswith("odoo-forge-mask-")

        tools = [argv[1] for argv in calls]
        assert tools[0] == "run"
        assert "pg_isready" in calls[1]
        assert tools[-1] == "rm"
        assert "-f" in calls[-1]

    def test_the_container_is_removed_even_when_the_body_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[list[str]] = []

        def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            calls.append(list(argv))
            return subprocess.CompletedProcess(list(argv), 0)

        monkeypatch.setattr(subprocess, "run", _fake_run)

        with pytest.raises(RuntimeError), docker_scratch_database():
            raise RuntimeError("simulated masking failure")

        assert calls[-1][1] == "rm"

    def test_a_container_that_never_becomes_ready_is_reported_and_removed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[list[str]] = []

        def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            calls.append(list(argv))
            returncode = 0 if argv[1] in ("run", "rm") else 1
            return subprocess.CompletedProcess(list(argv), returncode)

        monkeypatch.setattr(subprocess, "run", _fake_run)
        monkeypatch.setattr("time.sleep", lambda _seconds: None)

        with (
            pytest.raises(MaskScratchUnavailableError),
            docker_scratch_database(readiness_attempts=3),
        ):
            pytest.fail("the body must never run for an unready scratch database")

        assert calls[-1][1] == "rm", "an unready container is still removed"

    def test_each_scratch_container_gets_a_unique_safe_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        names: list[str] = []

        def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            return subprocess.CompletedProcess(list(argv), 0)

        monkeypatch.setattr(subprocess, "run", _fake_run)

        for _ in range(2):
            with docker_scratch_database() as scratch:
                names.append(scratch.container)

        assert len(set(names)) == 2
        for name in names:
            assert len(name) <= 64
            assert all(character.isalnum() or character == "-" for character in name)
