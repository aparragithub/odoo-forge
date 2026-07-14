"""SOPS-backed, short-lived Docker environment-file injection."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

from odoo_forge.backend.plan import ContainerSpec
from odoo_forge.credentials.errors import CredentialError, CredentialUnavailableError
from odoo_forge.credentials.types import CredentialHandle

CredentialResolver = Callable[[CredentialHandle], str]


class SopsCommandResolver:
    """Resolve a handle from the configured SOPS document without a shell."""

    def __init__(self, credentials_file: Path = Path("credentials.sops.yaml")) -> None:
        self._credentials_file = credentials_file

    def __call__(self, handle: CredentialHandle) -> str:
        try:
            result = subprocess.run(
                ["sops", "--decrypt", "--extract", f'["{handle}"]', str(self._credentials_file)],
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise CredentialUnavailableError() from exc
        if result.returncode != 0:
            raise CredentialUnavailableError()
        value = result.stdout.rstrip("\r\n")
        if not value:
            raise CredentialUnavailableError()
        return value


class SopsEnvFileInjector:
    """Resolve SOPS handles only while Docker consumes a protected env-file."""

    def __init__(self, resolver: CredentialResolver | None = None) -> None:
        self._resolver = resolver or _unavailable_resolver
        self._resolved_values: set[str] = set()

    @contextmanager
    def env_file(self, spec: ContainerSpec) -> Iterator[Path]:
        """Yield a `0600` env-file and remove it on every exit path."""
        fd, raw_path = tempfile.mkstemp(prefix="odoo-forge-credentials-", suffix=".env")
        path = Path(raw_path)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as env_file:
                for key, handle in spec.secret_env.items():
                    env_file.write(f"{key}={self._resolve(handle)}\n")
            yield path
        finally:
            path.unlink(missing_ok=True)

    def validate(self, spec: ContainerSpec) -> None:
        """Resolve every handle before Docker receives any launch request."""
        for handle in spec.secret_env.values():
            self._resolve(handle)

    @contextmanager
    def secret_files(self, spec: ContainerSpec) -> Iterator[dict[str, Path]]:
        """Yield one protected file per secret, then remove all plaintext files."""
        directory = Path(tempfile.mkdtemp(prefix="odoo-forge-credentials-"))
        files: dict[str, Path] = {}
        try:
            for key, handle in spec.secret_env.items():
                path = directory / key
                value = self._resolve(handle)
                files[key] = path
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as secret_file:
                    secret_file.write(value)
                os.chmod(path, 0o600)
            yield files
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def redact(self, value: str, additional_values: Iterable[str] = ()) -> str:
        secrets = self._resolved_values | {item for item in additional_values if item}
        for secret in sorted(secrets, key=len, reverse=True):
            value = value.replace(secret, "[REDACTED]")
        return value

    def clear(self) -> None:
        self._resolved_values.clear()

    def _resolve(self, handle: CredentialHandle) -> str:
        try:
            value = self._resolver(handle)
        except CredentialError:
            raise
        except Exception as exc:
            raise CredentialUnavailableError() from exc
        if "\n" in value or "\r" in value:
            raise CredentialUnavailableError()
        self._resolved_values.add(value)
        return value


def _unavailable_resolver(_handle: CredentialHandle) -> str:
    """Fail closed until the composition root supplies an approved SOPS resolver."""
    raise CredentialUnavailableError()


__all__ = ["CredentialResolver", "SopsCommandResolver", "SopsEnvFileInjector"]
