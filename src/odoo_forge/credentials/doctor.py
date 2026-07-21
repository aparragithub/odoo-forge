"""Enterprise credential doctor check (Slice 5).

The doctor check is pure/testable-via-fakes logic that lives here,
independent of the CLI — `odoo_forge_cli.main` only wires a thin Typer
command (`doctor`) that calls into this module. Never logs, returns, or
embeds resolved secret material in a `DoctorCheckResult` message.

The rotation helper (`rotate_enterprise_credential`) used to live here too,
but it shells out via `subprocess`, which core (`odoo_forge`) is forbidden
from importing — see the "Core never imports infrastructure or framework"
import-linter contract. It now lives in
`odoo_forge_docker.credential_injection`, alongside the other `sops`-shelling
adapter (`SopsCommandResolver`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from odoo_forge.credentials.conventions import ENTERPRISE_SOURCE_CREDENTIAL_HANDLE
from odoo_forge.credentials.errors import CredentialError
from odoo_forge.credentials.types import CredentialResolver

_AGE_KEY_MARKER = "AGE-SECRET-KEY-"
_DEFAULT_AGE_KEY_FILE = Path.home() / ".config" / "sops" / "age" / "keys.txt"


@dataclass(frozen=True)
class DoctorCheckResult:
    """One independent doctor check's outcome. Never carries secret material."""

    name: str
    ok: bool
    message: str


@dataclass(frozen=True)
class DoctorReport:
    """Both doctor checks' outcomes, always reported independently of each other."""

    age_key: DoctorCheckResult
    enterprise_credential: DoctorCheckResult

    @property
    def ok(self) -> bool:
        return self.age_key.ok and self.enterprise_credential.ok


def check_age_key_present(*, age_key_file: Path | None = None) -> DoctorCheckResult:
    """Verify the age private key is present and minimally well-formed.

    Checks that `age_key_file` (or the default `~/.config/sops/age/keys.txt`
    location) exists, is readable, and contains at least one
    `AGE-SECRET-KEY-` line. Never reads the key material into the returned
    message — only the keyfile path, which is not secret.
    """
    path = age_key_file if age_key_file is not None else _DEFAULT_AGE_KEY_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, OSError):
        return DoctorCheckResult(
            name="age-key",
            ok=False,
            message=(
                f"age private key not found or unreadable at '{path}' — "
                "populate the keyfile or set SOPS_AGE_KEY_FILE"
            ),
        )
    if not any(line.strip().startswith(_AGE_KEY_MARKER) for line in text.splitlines()):
        return DoctorCheckResult(
            name="age-key",
            ok=False,
            message=f"'{path}' does not contain a usable age private key",
        )
    return DoctorCheckResult(name="age-key", ok=True, message=f"age private key usable at '{path}'")


def check_enterprise_credential_resolves(resolver: CredentialResolver) -> DoctorCheckResult:
    """Verify the conventional Enterprise source credential resolves.

    Calls `resolver` directly with the conventional handle — the exact same
    resolver used by the real fetch path (`_make_enterprise_credential_resolver`)
    — and reports pass/fail without ever placing the resolved value in the
    returned message.
    """
    try:
        resolver(ENTERPRISE_SOURCE_CREDENTIAL_HANDLE)
    except CredentialError as exc:
        return DoctorCheckResult(
            name="enterprise-credential",
            ok=False,
            message=f"Enterprise source credential unavailable: {exc}",
        )
    return DoctorCheckResult(
        name="enterprise-credential",
        ok=True,
        message="Enterprise source credential resolves",
    )


def run_doctor(*, resolver: CredentialResolver, age_key_file: Path | None = None) -> DoctorReport:
    """Run both doctor checks independently; neither failure short-circuits the other."""
    return DoctorReport(
        age_key=check_age_key_present(age_key_file=age_key_file),
        enterprise_credential=check_enterprise_credential_resolves(resolver),
    )


__all__ = [
    "CredentialResolver",
    "DoctorCheckResult",
    "DoctorReport",
    "check_age_key_present",
    "check_enterprise_credential_resolves",
    "run_doctor",
]
