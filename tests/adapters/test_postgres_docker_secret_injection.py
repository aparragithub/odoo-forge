from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from odoo_forge.credentials.types import CredentialHandle, CredentialInjectionDescriptor
from odoo_forge_postgres_docker.secret_injection import (
    PostgreSQLSecretInjector,
    SecretInjectionError,
)


def _descriptor() -> CredentialInjectionDescriptor:
    return CredentialInjectionDescriptor(
        handle=CredentialHandle("opaque-postgres-password"),
        target_kind="database",
        store_ref="sops://opaque-postgres-password",
        redaction_label="SOPS credential",
    )


def test_injection_uses_a_private_file_mount_and_postgres_file_environment(tmp_path: Path) -> None:
    secret = "postgres-password-not-in-docker-config"

    @contextmanager
    def resolve(_descriptor: CredentialInjectionDescriptor) -> Iterator[str]:
        yield secret

    injector = PostgreSQLSecretInjector(resolve, temporary_root=tmp_path)

    with injector.inject(_descriptor()) as injection:
        assert injection.host_path.read_text() == secret
        assert injection.host_path.stat().st_mode & 0o777 == 0o600
        assert injection.host_path.parent.stat().st_mode & 0o777 == 0o700
        assert injection.docker_args() == (
            "--mount",
            f"type=bind,src={injection.host_path},dst=/run/secrets/postgres-password,readonly",
            "--env",
            "POSTGRES_PASSWORD_FILE=/run/secrets/postgres-password",
        )

    assert not injection.host_path.exists()
    assert not injection.host_path.parent.exists()
    assert secret not in repr(injection)


def test_injection_erases_temporary_material_when_the_consumer_fails(tmp_path: Path) -> None:
    @contextmanager
    def resolve(_descriptor: CredentialInjectionDescriptor) -> Iterator[str]:
        yield "failure-path-password"

    injector = PostgreSQLSecretInjector(resolve, temporary_root=tmp_path)

    with (
        pytest.raises(RuntimeError, match="readiness failed"),
        injector.inject(_descriptor()) as injection,
    ):
        path = injection.host_path
        raise RuntimeError("readiness failed")

    assert not path.exists()
    assert not path.parent.exists()


def test_cleanup_erases_the_mounted_inode_before_unlinking(tmp_path: Path) -> None:
    secret = "mounted-inode-password"

    @contextmanager
    def resolve(_descriptor: CredentialInjectionDescriptor) -> Iterator[str]:
        yield secret

    injector = PostgreSQLSecretInjector(resolve, temporary_root=tmp_path)
    mounted_path = tmp_path / "mounted-secret"

    with pytest.raises(RuntimeError), injector.inject(_descriptor()) as injection:
        mounted_path.hardlink_to(injection.host_path)
        raise RuntimeError("consumer failed")

    assert mounted_path.read_bytes() == b""
    assert not injection.host_path.exists()


def test_injection_erases_material_when_the_resolver_exit_fails_after_write(
    tmp_path: Path,
) -> None:
    @contextmanager
    def resolve(_descriptor: CredentialInjectionDescriptor) -> Iterator[str]:
        yield "resolver-exit-failure-password"
        raise RuntimeError("resolver exit failed after write")

    injector = PostgreSQLSecretInjector(resolve, temporary_root=tmp_path)

    with pytest.raises(SecretInjectionError), injector.inject(_descriptor()):
        pytest.fail("a resolver-exit failure must abort before yielding a target")

    assert list(tmp_path.iterdir()) == []


def test_cleanup_tolerates_removal_failure_after_the_plaintext_is_zeroed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "removal-failure-password"

    @contextmanager
    def resolve(_descriptor: CredentialInjectionDescriptor) -> Iterator[str]:
        yield secret

    injector = PostgreSQLSecretInjector(resolve, temporary_root=tmp_path)
    host_path: dict[str, Path] = {}

    def failing_unlink(self: Path, *args: object, **kwargs: object) -> None:
        raise OSError("unlink blocked")

    monkeypatch.setattr(Path, "unlink", failing_unlink)

    with injector.inject(_descriptor()) as injection:
        host_path["path"] = injection.host_path

    assert host_path["path"].read_bytes() == b""


def test_injection_reports_failure_when_the_plaintext_cannot_be_zeroed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    @contextmanager
    def resolve(_descriptor: CredentialInjectionDescriptor) -> Iterator[str]:
        yield "unzeroable-password"

    injector = PostgreSQLSecretInjector(resolve, temporary_root=tmp_path)
    real_open = os.open

    def failing_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        if flags & os.O_RDWR:
            raise OSError("cannot open for zeroing")
        return real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "open", failing_open)

    with pytest.raises(SecretInjectionError), injector.inject(_descriptor()):
        pass


@pytest.mark.parametrize(
    ("target_kind", "store_ref"),
    [("backend", "sops://opaque"), ("database", "legacy://opaque")],
)
def test_injection_rejects_non_ref_capable_or_unsupported_targets_without_resolution(
    target_kind: str, store_ref: str, tmp_path: Path
) -> None:
    resolved = False

    @contextmanager
    def resolve(_descriptor: CredentialInjectionDescriptor) -> Iterator[str]:
        nonlocal resolved
        resolved = True
        yield "must-not-be-exposed"

    with (
        pytest.raises(SecretInjectionError),
        PostgreSQLSecretInjector(resolve, temporary_root=tmp_path).inject(
            CredentialInjectionDescriptor(
                handle=CredentialHandle("opaque"),
                target_kind=target_kind,
                store_ref=store_ref,
                redaction_label="SOPS",
            )
        ),
    ):
        pytest.fail("unsupported injection must not yield a target")

    assert resolved is False
    assert list(tmp_path.iterdir()) == []
