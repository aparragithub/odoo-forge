"""Doctor check logic, independent of the CLI.

Fake resolvers only — never real `sops`/`age`. The rotation helper's tests
live in `tests/adapters/test_credential_injection.py`.
"""

from pathlib import Path

from odoo_forge.credentials.conventions import ENTERPRISE_SOURCE_CREDENTIAL_HANDLE
from odoo_forge.credentials.doctor import (
    CredentialResolver,
    check_age_key_present,
    check_enterprise_credential_resolves,
    run_doctor,
)
from odoo_forge.credentials.errors import CredentialUnavailableError
from odoo_forge.credentials.types import CredentialHandle

_SECRET_MARKER = "s3cr3t-age-doctor-marker"


def _succeeding_resolver() -> tuple[list[CredentialHandle], CredentialResolver]:
    calls: list[CredentialHandle] = []

    def resolver(handle: CredentialHandle) -> str:
        calls.append(handle)
        return _SECRET_MARKER

    return calls, resolver


def _raising_resolver() -> CredentialResolver:
    def resolver(handle: CredentialHandle) -> str:
        raise CredentialUnavailableError()

    return resolver


# ---------------------------------------------------------------------------
# check_age_key_present
# ---------------------------------------------------------------------------


def test_age_key_present_ok_when_file_contains_a_usable_key(tmp_path: Path) -> None:
    key_file = tmp_path / "keys.txt"
    key_file.write_text(
        "AGE-SECRET-KEY-1QYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQ\n"
    )

    result = check_age_key_present(age_key_file=key_file)

    assert result.ok is True
    assert _SECRET_MARKER not in result.message
    assert "AGE-SECRET-KEY-" not in result.message


def test_age_key_present_fails_when_file_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.txt"

    result = check_age_key_present(age_key_file=missing)

    assert result.ok is False
    assert "not found" in result.message or "unreadable" in result.message


def test_age_key_present_fails_when_file_has_no_usable_key(tmp_path: Path) -> None:
    key_file = tmp_path / "keys.txt"
    key_file.write_text("not-a-key\n")

    result = check_age_key_present(age_key_file=key_file)

    assert result.ok is False


# ---------------------------------------------------------------------------
# check_enterprise_credential_resolves
# ---------------------------------------------------------------------------


def test_enterprise_credential_resolves_ok_when_resolver_succeeds() -> None:
    calls, resolver = _succeeding_resolver()

    result = check_enterprise_credential_resolves(resolver)

    assert result.ok is True
    assert calls == [ENTERPRISE_SOURCE_CREDENTIAL_HANDLE]
    assert _SECRET_MARKER not in result.message


def test_enterprise_credential_resolves_fails_when_resolver_raises() -> None:
    result = check_enterprise_credential_resolves(_raising_resolver())

    assert result.ok is False
    assert "unavailable" in result.message


# ---------------------------------------------------------------------------
# run_doctor: both checks reported independently
# ---------------------------------------------------------------------------


def test_run_doctor_reports_both_checks_independently_age_key_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.txt"
    _calls, resolver = _succeeding_resolver()

    report = run_doctor(resolver=resolver, age_key_file=missing)

    assert report.age_key.ok is False
    assert report.enterprise_credential.ok is True
    assert report.ok is False


def test_run_doctor_reports_both_checks_independently_credential_missing(tmp_path: Path) -> None:
    key_file = tmp_path / "keys.txt"
    key_file.write_text(
        "AGE-SECRET-KEY-1QYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQ\n"
    )

    report = run_doctor(resolver=_raising_resolver(), age_key_file=key_file)

    assert report.age_key.ok is True
    assert report.enterprise_credential.ok is False
    assert report.ok is False


def test_run_doctor_reports_success_on_both_checks(tmp_path: Path) -> None:
    key_file = tmp_path / "keys.txt"
    key_file.write_text(
        "AGE-SECRET-KEY-1QYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQ\n"
    )
    _calls, resolver = _succeeding_resolver()

    report = run_doctor(resolver=resolver, age_key_file=key_file)

    assert report.age_key.ok is True
    assert report.enterprise_credential.ok is True
    assert report.ok is True


# `rotate_enterprise_credential`'s tests now live in
# `tests/adapters/test_credential_injection.py`, alongside its new home in
# `odoo_forge_docker.credential_injection` — core (`odoo_forge`) may not
# import `subprocess`, so the `sops updatekeys` wrapper cannot live here.
