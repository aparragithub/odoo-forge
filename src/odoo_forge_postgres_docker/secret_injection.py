from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path

from odoo_forge.credentials.types import CredentialInjectionDescriptor

_CONTAINER_SECRET_PATH = "/run/secrets/postgres-password"


class SecretInjectionError(Exception):
    pass
SecretResolver = Callable[[CredentialInjectionDescriptor], AbstractContextManager[str]]


@dataclass(frozen=True)
class PostgreSQLSecretInjection:
    host_path: Path

    def docker_args(self) -> tuple[str, ...]:
        return (
            "--mount",
            f"type=bind,src={self.host_path},dst={_CONTAINER_SECRET_PATH},readonly",
            "--env",
            f"POSTGRES_PASSWORD_FILE={_CONTAINER_SECRET_PATH}",
        )


class PostgreSQLSecretInjector:
    def __init__(self, resolve: SecretResolver, *, temporary_root: Path | None = None) -> None:
        self._resolve = resolve
        self._temporary_root = temporary_root

    @contextmanager
    def inject(
        self, descriptor: CredentialInjectionDescriptor
    ) -> Iterator[PostgreSQLSecretInjection]:
        self._validate_descriptor(descriptor)
        directory: Path | None = None
        secret_path: Path | None = None
        try:
            try:
                directory = Path(
                    tempfile.mkdtemp(prefix="odoo-forge-postgres-", dir=self._temporary_root)
                )
                directory.chmod(0o700)
                secret_path = directory / "postgres-password"
                with self._resolve(descriptor) as plaintext:
                    self._write_secret(secret_path, plaintext)
            except SecretInjectionError:
                raise
            except Exception as exc:
                raise SecretInjectionError() from exc
            yield PostgreSQLSecretInjection(host_path=secret_path)
        finally:
            self._erase(secret_path, directory)

    @staticmethod
    def _validate_descriptor(descriptor: CredentialInjectionDescriptor) -> None:
        if descriptor.target_kind != "database" or not descriptor.store_ref.startswith("sops://"):
            raise SecretInjectionError()

    @staticmethod
    def _write_secret(path: Path, plaintext: str) -> None:
        if not plaintext or "\x00" in plaintext:
            raise SecretInjectionError()
        try:
            descriptor = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as secret_file:
                secret_file.write(plaintext)
                secret_file.flush()
                os.fsync(secret_file.fileno())
        except OSError as exc:
            raise SecretInjectionError() from exc

    @staticmethod
    def _erase(secret_path: Path | None, directory: Path | None) -> None:
        # Zeroing the plaintext is security-critical and must succeed (or prove
        # the file is already gone); unlinking the emptied file and removing the
        # directory is best-effort hygiene whose failure leaves no plaintext
        # behind and must not fail the caller.
        if secret_path is not None:
            PostgreSQLSecretInjector._zero_secret(secret_path)
            with suppress(OSError):
                secret_path.unlink(missing_ok=True)
        if directory is not None:
            with suppress(OSError):
                directory.rmdir()

    @staticmethod
    def _zero_secret(secret_path: Path) -> None:
        try:
            descriptor = os.open(secret_path, os.O_RDWR | os.O_NOFOLLOW)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise SecretInjectionError() from exc
        try:
            os.ftruncate(descriptor, 0)
            os.fsync(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.read(descriptor, 1):
                raise SecretInjectionError()
        except OSError as exc:
            raise SecretInjectionError() from exc
        finally:
            os.close(descriptor)
