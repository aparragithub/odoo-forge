"""Custody regressions for Docker-local ownership authority."""

import json
import os
import stat
import threading
from pathlib import Path

import pytest

from odoo_forge_postgres_docker.authority import (
    AuthorityCustodyError,
    AuthorityStateError,
    LocalOwnershipAuthority,
)


def _record(name: str) -> dict[str, object]:
    return {
        "operation": f"postgres-docker:{name}",
        "kind": "container",
        "name": name,
        "docker_id": f"immutable-{name}",
        "state": "reserved",
    }


def test_initializes_private_directory_and_credential_free_record(tmp_path: Path) -> None:
    authority = LocalOwnershipAuthority(tmp_path / "authority")

    authority.write(_record("alpha"))

    assert stat.S_IMODE(authority.root.stat().st_mode) == 0o700
    assert stat.S_IMODE(authority.state_path.stat().st_mode) == 0o600
    state = json.loads(authority.state_path.read_text(encoding="utf-8"))
    assert state["generation"] == 1
    assert state["records"][0]["docker_id"] == "immutable-alpha"
    assert "password" not in authority.state_path.read_text(encoding="utf-8").lower()


def test_rejects_symlinked_root_or_state(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    root_link = tmp_path / "authority-link"
    root_link.symlink_to(target, target_is_directory=True)

    with pytest.raises(AuthorityCustodyError):
        LocalOwnershipAuthority(root_link).write(_record("alpha"))

    authority = LocalOwnershipAuthority(tmp_path / "authority")
    authority.write(_record("alpha"))
    replacement = tmp_path / "replacement.json"
    replacement.write_text("{}", encoding="utf-8")
    authority.state_path.unlink()
    authority.state_path.symlink_to(replacement)

    with pytest.raises(AuthorityCustodyError):
        authority.read()


def test_rejects_permissive_existing_custody(tmp_path: Path) -> None:
    authority = LocalOwnershipAuthority(tmp_path / "authority")
    authority.write(_record("alpha"))
    authority.state_path.chmod(0o644)

    with pytest.raises(AuthorityCustodyError):
        authority.read()


@pytest.mark.parametrize("contents", ["{", ""])
def test_rejects_corrupt_or_lost_state(tmp_path: Path, contents: str) -> None:
    authority = LocalOwnershipAuthority(tmp_path / "authority")
    authority.write(_record("alpha"))
    authority.state_path.write_text(contents, encoding="utf-8")

    with pytest.raises(AuthorityStateError):
        authority.read()

    authority.state_path.unlink()

    with pytest.raises(AuthorityStateError):
        authority.read()


def test_exclusive_lock_serializes_writers(tmp_path: Path) -> None:
    authority = LocalOwnershipAuthority(tmp_path / "authority")
    authority.write(_record("alpha"))
    entered = threading.Event()
    release = threading.Event()
    wrote = threading.Event()

    def hold_lock() -> None:
        with authority.locked():
            entered.set()
            release.wait(timeout=2)

    def write_record() -> None:
        authority.write(_record("beta"))
        wrote.set()

    holder = threading.Thread(target=hold_lock)
    holder.start()
    assert entered.wait(timeout=2)
    writer = threading.Thread(target=write_record)
    writer.start()
    assert not wrote.wait(timeout=0.1)
    release.set()
    holder.join(timeout=2)
    writer.join(timeout=2)
    assert wrote.is_set()
    assert [record["name"] for record in authority.read()["records"]] == ["alpha", "beta"]


def test_failed_replace_keeps_previous_durable_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    authority = LocalOwnershipAuthority(tmp_path / "authority")
    authority.write(_record("alpha"))
    previous = authority.state_path.read_bytes()

    def crash_before_replace(source: str | Path, destination: str | Path) -> None:
        raise OSError("simulated crash")

    monkeypatch.setattr(os, "replace", crash_before_replace)

    with pytest.raises(AuthorityStateError):
        authority.write(_record("beta"))

    assert authority.state_path.read_bytes() == previous


def test_rejects_generation_regression(tmp_path: Path) -> None:
    authority = LocalOwnershipAuthority(tmp_path / "authority")
    authority.write(_record("alpha"))
    authority.write(_record("beta"))
    state = authority.read()
    state["generation"] = 1
    authority.state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(AuthorityStateError):
        authority.read()


def test_write_fails_closed_when_initialized_state_is_deleted(tmp_path: Path) -> None:
    authority = LocalOwnershipAuthority(tmp_path / "authority")
    authority.write(_record("alpha"))
    authority.state_path.unlink()

    with pytest.raises(AuthorityStateError):
        authority.write(_record("beta"))

    assert not authority.state_path.exists()


def test_write_fails_closed_when_initialized_state_is_dangling_symlink(tmp_path: Path) -> None:
    authority = LocalOwnershipAuthority(tmp_path / "authority")
    authority.write(_record("alpha"))
    authority.state_path.unlink()
    authority.state_path.symlink_to(tmp_path / "missing.json")

    with pytest.raises(AuthorityStateError):
        authority.write(_record("beta"))

    assert authority.state_path.is_symlink()


def test_reserve_fails_closed_when_initialized_state_is_dangling_symlink(tmp_path: Path) -> None:
    authority = LocalOwnershipAuthority(tmp_path / "authority")
    authority.reserve("postgres-docker:alpha", "alpha")
    authority.state_path.unlink()
    authority.state_path.symlink_to(tmp_path / "missing.json")

    with pytest.raises(AuthorityStateError):
        authority.reserve("postgres-docker:beta", "beta")

    assert authority.state_path.is_symlink()


def test_short_writes_are_completed_before_atomic_replace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    authority = LocalOwnershipAuthority(tmp_path / "authority")
    authority.write(_record("alpha"))
    original_write = os.write

    def short_write(descriptor: int, data: bytes) -> int:
        return original_write(descriptor, data[:1])

    monkeypatch.setattr(os, "write", short_write)

    authority.write(_record("beta"))

    assert [record["name"] for record in authority.read()["records"]] == ["alpha", "beta"]


def test_zero_byte_write_keeps_previous_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    authority = LocalOwnershipAuthority(tmp_path / "authority")
    authority.write(_record("alpha"))
    previous = authority.state_path.read_bytes()
    monkeypatch.setattr(os, "write", lambda descriptor, data: 0)

    with pytest.raises(AuthorityStateError):
        authority.write(_record("beta"))

    assert authority.state_path.read_bytes() == previous


def test_signed_evidence_rejects_tampering_unknown_keys_and_invalid_schema(tmp_path: Path) -> None:
    authority = LocalOwnershipAuthority(tmp_path / "authority")
    authority.write({**_record("alpha"), "state": "active"})

    evidence = authority.issue_evidence(
        "postgres-docker:alpha", "immutable-alpha", nonce="one", observed_at=10, expires_at=20
    )
    assert authority.verify_evidence(evidence, "immutable-alpha", now=11)

    for field, value in (("docker_id", "other"), ("key_id", "unknown"), ("schema", 0)):
        forged = {**evidence, field: value}
        assert not authority.verify_evidence(forged, "immutable-alpha", now=11)


@pytest.mark.parametrize(
    ("field", "value"),
    (("operation", "postgres-docker:forged"), ("docker_id", "forged-id"), ("state", "retired")),
)
def test_rejects_schema_valid_tampering_of_signed_ownership_records(
    tmp_path: Path, field: str, value: str
) -> None:
    authority = LocalOwnershipAuthority(tmp_path / "authority")
    authority.write({**_record("alpha"), "state": "active"})
    state = json.loads(authority.state_path.read_text(encoding="utf-8"))
    state["records"][0][field] = value
    authority.state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(AuthorityStateError):
        LocalOwnershipAuthority.recover(authority.root)


def test_rotation_recovery_and_replay_or_expired_nonce_are_rejected(tmp_path: Path) -> None:
    authority = LocalOwnershipAuthority(tmp_path / "authority")
    authority.write({**_record("alpha"), "state": "active"})
    original = authority.issue_evidence(
        "postgres-docker:alpha", "immutable-alpha", nonce="one", observed_at=10, expires_at=20
    )

    authority.rotate_keys()
    rotated = authority.issue_evidence(
        "postgres-docker:alpha", "immutable-alpha", nonce="two", observed_at=10, expires_at=20
    )
    assert LocalOwnershipAuthority.recover(authority.root).verify_evidence(
        original, "immutable-alpha", now=11
    )
    assert authority.verify_evidence(rotated, "immutable-alpha", now=11)
    assert not authority.verify_evidence(rotated, "immutable-alpha", now=11)
    assert not authority.verify_evidence(original, "immutable-alpha", now=21)


def test_imported_or_inspect_minted_evidence_is_rejected_and_errors_are_redacted(
    tmp_path: Path,
) -> None:
    authority = LocalOwnershipAuthority(tmp_path / "authority")
    authority.write({**_record("alpha"), "state": "active"})

    imported = {
        "schema": 1,
        "key_id": "inspect",
        "operation": "postgres-docker:alpha",
        "docker_id": "immutable-alpha",
        "nonce": "one",
        "observed_at": 10,
        "expires_at": 20,
        "signature": "inspect-data",
    }
    assert not authority.verify_evidence(imported, "immutable-alpha", now=11)
    with pytest.raises(AuthorityStateError) as error:
        authority.issue_evidence(
            "postgres-docker:alpha", "wrong", nonce="two", observed_at=10, expires_at=20
        )
    assert "immutable-alpha" not in str(error.value)
