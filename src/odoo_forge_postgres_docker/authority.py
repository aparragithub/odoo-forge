"""Durable, backend-local custody for Docker ownership records.

Every filesystem or signature failure fails closed.
"""

import base64
import fcntl
import json
import os
import secrets
import stat
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from odoo_forge.database.errors import DatabaseOperationError

_DIRECTORY_MODE = 0o700
_FILE_MODE = 0o600
_REQUIRED_RECORD_FIELDS = frozenset({"operation", "kind", "name", "docker_id", "state"})
_STORED_RECORD_FIELDS = _REQUIRED_RECORD_FIELDS | frozenset({"generation", "key_id", "signature"})
_EVIDENCE_FIELDS = frozenset(
    {
        "schema",
        "key_id",
        "operation",
        "docker_id",
        "nonce",
        "observed_at",
        "expires_at",
        "signature",
    }
)


class AuthorityError(DatabaseOperationError):
    """Base error for authority failures, deliberately without filesystem detail."""


class AuthorityCustodyError(AuthorityError):
    """Authority paths do not meet the required private local custody."""


class AuthorityStateError(AuthorityError):
    """Authority state is missing, corrupt, or could not be committed safely."""


class LocalOwnershipAuthority:
    """Persist credential-free ownership records with fail-closed local custody."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.state_path = root / "authority.json"
        self._lock_path = root / "authority.lock"

    @contextmanager
    def locked(self) -> Iterator[None]:
        """Hold the authority's process-safe exclusive lock."""
        self._ensure_root()
        descriptor = self._open_private_file(self._lock_path, create=True)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        except OSError as exc:
            raise AuthorityStateError() from exc
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def read(self) -> dict[str, Any]:
        """Return validated state, refusing missing, altered, or corrupt files."""
        self._ensure_root()
        try:
            descriptor = self._open_private_file(self.state_path, create=False)
        except FileNotFoundError as exc:
            raise AuthorityStateError() from exc
        try:
            with os.fdopen(descriptor, "r", encoding="utf-8") as state_file:
                payload = json.load(state_file)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AuthorityStateError() from exc
        return self._validate_state(payload)

    def write(self, record: Mapping[str, object]) -> None:
        """Append one record through an fsynced no-follow atomic replacement."""
        self._validate_record(record)
        initializing = not self._lock_path.exists()
        with self.locked():
            state = self._read_or_initial_state(initializing=initializing)
            self._append(state, record)

    def reserve(self, operation: str, name: str) -> None:
        """Record intent before Docker creation can make a resource live."""
        initializing = not self._lock_path.exists()
        with self.locked():
            state = self._read_or_initial_state(initializing=initializing)
            self._append(
                state,
                {
                    "operation": operation,
                    "kind": "container",
                    "name": name,
                    "docker_id": "",
                    "state": "reserved",
                },
            )

    def bind(self, operation: str, name: str, docker_id: str) -> None:
        """Bind a reserved record to Docker's immutable resource identity."""
        self._transition(operation, name, docker_id, expected="reserved", target="reserved")

    def activate(self, operation: str, name: str, docker_id: str) -> None:
        """Make a bound resource eligible for authority-backed lifecycle work."""
        self._transition(operation, name, docker_id, expected="reserved", target="active")

    def retire(self, operation: str, name: str, docker_id: str) -> None:
        """Record successful removal so historical active authority cannot be reused."""
        self._transition(operation, name, docker_id, expected="active", target="retired")

    def retire_absent(self, operation: str, name: str, *, docker_id: str | None = None) -> None:
        """Retire an active record only after Docker confirms its name is absent."""
        with self.locked():
            state = self._read_or_initial_state(initializing=False)
            record = self._latest(state, operation, name)
            if (
                record is None
                or record["state"] not in {"active", "retired"}
                or (docker_id is not None and record["docker_id"] != docker_id)
            ):
                raise AuthorityStateError()
            if record["state"] == "retired":
                return
            self._append(
                state,
                {
                    "operation": operation,
                    "kind": "container",
                    "name": name,
                    "docker_id": record["docker_id"],
                    "state": "retired",
                },
            )

    @classmethod
    def recover(cls, root: Path) -> "LocalOwnershipAuthority":
        """Reopen only a custody-valid, coherent authority state."""
        authority = cls(root)
        authority.read()
        return authority

    def rotate_keys(self) -> None:
        """Add and activate a fresh signing key while retaining prior verifiers."""
        with self.locked():
            state = self.read()
            self._add_key(state)
            self._write_atomic(state)

    def issue_evidence(
        self, operation: str, docker_id: str, *, nonce: str, observed_at: int, expires_at: int
    ) -> dict[str, object]:
        """Issue short-lived signed evidence for one active authority record."""
        if not nonce or observed_at < 0 or expires_at <= observed_at:
            raise AuthorityStateError()
        with self.locked():
            state = self.read()
            if not any(
                record["operation"] == operation
                and record["docker_id"] == docker_id
                and record["state"] == "active"
                for record in state["records"]
            ):
                raise AuthorityStateError()
            key_id = state["active_key"]
            evidence: dict[str, object] = {
                "schema": 1,
                "key_id": key_id,
                "operation": operation,
                "docker_id": docker_id,
                "nonce": nonce,
                "observed_at": observed_at,
                "expires_at": expires_at,
            }
            evidence["signature"] = self._sign(state["keys"][key_id], evidence)
            return evidence

    def verify_evidence(self, evidence: Mapping[str, object], docker_id: str, *, now: int) -> bool:
        """Verify authority-bound evidence once; inspection data cannot mint claims."""
        try:
            if set(evidence) != _EVIDENCE_FIELDS or evidence["docker_id"] != docker_id:
                return False
            string_keys = ("key_id", "operation", "docker_id", "nonce", "signature")
            if not all(isinstance(evidence[key], str) and evidence[key] for key in string_keys):
                return False
            integer_keys = ("schema", "observed_at", "expires_at")
            if not all(isinstance(evidence[key], int) for key in integer_keys):
                return False
            schema = evidence["schema"]
            observed_at = evidence["observed_at"]
            expires_at = evidence["expires_at"]
            if (
                not isinstance(schema, int)
                or not isinstance(observed_at, int)
                or not isinstance(expires_at, int)
                or schema != 1
                or not observed_at <= now < expires_at
            ):
                return False
            with self.locked():
                state = self.read()
                key = state["keys"].get(evidence["key_id"])
                if key is None or evidence["nonce"] in state["used_nonces"]:
                    return False
                self._verify(key, evidence)
                if not any(
                    record["operation"] == evidence["operation"]
                    and record["docker_id"] == docker_id
                    and record["state"] == "active"
                    for record in state["records"]
                ):
                    return False
                state["used_nonces"].append(evidence["nonce"])
                self._write_atomic(state)
            return True
        except (AuthorityError, InvalidSignature, ValueError, TypeError, KeyError):
            return False

    def owns(self, operation: str, name: str, docker_id: str) -> bool:
        """Return whether a signed active local record proves this exact resource."""
        state = self.read()
        record = self._latest(state, operation, name)
        return (
            record is not None and record["docker_id"] == docker_id and record["state"] == "active"
        )

    def _transition(
        self, operation: str, name: str, docker_id: str, *, expected: str, target: str
    ) -> None:
        with self.locked():
            state = self._read_or_initial_state(initializing=False)
            record = self._latest(state, operation, name)
            if (
                record is None
                or record["state"] != expected
                or record["docker_id"] not in {"", docker_id}
            ):
                raise AuthorityStateError()
            self._append(
                state,
                {
                    "operation": operation,
                    "kind": "container",
                    "name": name,
                    "docker_id": docker_id,
                    "state": target,
                },
            )

    @staticmethod
    def _latest(state: Mapping[str, Any], operation: str, name: str) -> Mapping[str, object] | None:
        return next(
            (
                record
                for record in reversed(state["records"])
                if record["operation"] == operation and record["name"] == name
            ),
            None,
        )

    def _append(self, state: dict[str, Any], record: Mapping[str, object]) -> None:
        self._validate_record(record)
        generation = state["generation"] + 1
        stored_record = dict(record)
        stored_record["generation"] = generation
        stored_record["key_id"] = state["active_key"]
        stored_record["signature"] = self._sign(state["keys"][state["active_key"]], stored_record)
        state["generation"] = generation
        state["records"].append(stored_record)
        self._write_atomic(state)

    def _ensure_root(self) -> None:
        try:
            self.root.mkdir(mode=_DIRECTORY_MODE)
        except FileExistsError:
            pass
        except OSError as exc:
            raise AuthorityCustodyError() from exc
        self._validate_private_path(self.root, _DIRECTORY_MODE, directory=True)

    def _read_or_initial_state(self, *, initializing: bool) -> dict[str, Any]:
        if not self.state_path.exists():
            if not initializing:
                raise AuthorityStateError()
            state: dict[str, Any] = {"generation": 0, "records": [], "keys": {}, "used_nonces": []}
            self._add_key(state)
            return state
        return self.read()

    def _write_atomic(self, state: Mapping[str, object]) -> None:
        temporary = self.root / f".authority-{secrets.token_hex(16)}.tmp"
        descriptor: int | None = None
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                _FILE_MODE,
            )
            os.fchmod(descriptor, _FILE_MODE)
            encoded = json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8")
            while encoded:
                written = os.write(descriptor, encoded)
                if written <= 0:
                    raise OSError("authority state write made no progress")
                encoded = encoded[written:]
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = None
            os.replace(temporary, self.state_path)
        except OSError as exc:
            raise AuthorityStateError() from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise AuthorityStateError() from exc
        # os.replace above is the durable commit point: the new state is now
        # in place at the inode level. A directory fsync failure past this
        # point is only a best-effort durability concern, not a failed write,
        # so it must not surface as AuthorityStateError and roll back the
        # already-committed transition (and any healthy container it backs).
        with suppress(OSError):
            self._fsync_directory()

    def _fsync_directory(self) -> None:
        descriptor = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _open_private_file(self, path: Path, *, create: bool) -> int:
        flags = os.O_RDWR | os.O_CREAT if create else os.O_RDONLY
        try:
            descriptor = os.open(path, flags | os.O_NOFOLLOW, _FILE_MODE)
        except OSError as exc:
            if isinstance(exc, FileNotFoundError) and not create:
                raise
            raise AuthorityCustodyError() from exc
        try:
            self._validate_private_path(path, _FILE_MODE, directory=False)
        except Exception:
            os.close(descriptor)
            raise
        return descriptor

    @staticmethod
    def _validate_private_path(path: Path, mode: int, *, directory: bool) -> None:
        try:
            metadata = os.lstat(path)
        except OSError as exc:
            raise AuthorityCustodyError() from exc
        expected_type = stat.S_ISDIR if directory else stat.S_ISREG
        if (
            not expected_type(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != mode
        ):
            raise AuthorityCustodyError()

    @staticmethod
    def _validate_record(record: Mapping[str, object]) -> None:
        if (
            set(record) != _REQUIRED_RECORD_FIELDS
            or not all(isinstance(value, str) for value in record.values())
            or not all(record[key] for key in ("operation", "kind", "name", "state"))
            or record["state"] not in {"reserved", "active", "retired"}
            or (record["state"] != "reserved" and not record["docker_id"])
        ):
            raise AuthorityStateError()

    @staticmethod
    def _add_key(state: dict[str, Any]) -> None:
        key_id = secrets.token_hex(16)
        private = Ed25519PrivateKey.generate()
        state["keys"][key_id] = base64.b64encode(
            private.private_bytes(
                serialization.Encoding.Raw,
                serialization.PrivateFormat.Raw,
                serialization.NoEncryption(),
            )
        ).decode()
        state["active_key"] = key_id

    @staticmethod
    def _payload(values: Mapping[str, object]) -> bytes:
        return json.dumps(
            {key: value for key, value in values.items() if key != "signature"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def _sign(self, encoded_key: object, evidence: Mapping[str, object]) -> str:
        if not isinstance(encoded_key, str):
            raise AuthorityStateError()
        private = Ed25519PrivateKey.from_private_bytes(base64.b64decode(encoded_key, validate=True))
        return base64.b64encode(private.sign(self._payload(evidence))).decode()

    def _verify(self, encoded_key: object, evidence: Mapping[str, object]) -> None:
        if not isinstance(encoded_key, str) or not isinstance(evidence["signature"], str):
            raise AuthorityStateError()
        private = Ed25519PrivateKey.from_private_bytes(base64.b64decode(encoded_key, validate=True))
        public = Ed25519PublicKey.from_public_bytes(
            private.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
        )
        public.verify(
            base64.b64decode(evidence["signature"], validate=True), self._payload(evidence)
        )

    def _validate_state(self, payload: object) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise AuthorityStateError()
        generation = payload.get("generation")
        records = payload.get("records")
        keys = payload.get("keys")
        used_nonces = payload.get("used_nonces")
        active_key = payload.get("active_key")
        if (
            not isinstance(generation, int)
            or generation < 0
            or not isinstance(records, list)
            or not isinstance(keys, dict)
            or not isinstance(used_nonces, list)
            or not isinstance(active_key, str)
            or active_key not in keys
            or not all(
                isinstance(key, str) and isinstance(value, str) for key, value in keys.items()
            )
            or not all(isinstance(nonce, str) for nonce in used_nonces)
        ):
            raise AuthorityStateError()
        copied_records: list[dict[str, object]] = []
        highest_generation = 0
        for record in records:
            if not isinstance(record, dict):
                raise AuthorityStateError()
            if set(record) != _STORED_RECORD_FIELDS:
                raise AuthorityStateError()
            stored_generation = record.get("generation")
            key_id = record.get("key_id")
            if not isinstance(key_id, str) or key_id not in keys:
                raise AuthorityStateError()
            self._validate_record({key: record[key] for key in _REQUIRED_RECORD_FIELDS})
            if not isinstance(stored_generation, int) or stored_generation <= highest_generation:
                raise AuthorityStateError()
            try:
                self._verify(keys[key_id], record)
            except (InvalidSignature, ValueError, TypeError, KeyError) as exc:
                raise AuthorityStateError() from exc
            highest_generation = stored_generation
            copied_records.append(dict(record))
        if highest_generation != generation:
            raise AuthorityStateError()
        return {
            "generation": generation,
            "records": copied_records,
            "keys": keys,
            "active_key": active_key,
            "used_nonces": used_nonces,
        }


__all__ = [
    "AuthorityCustodyError",
    "AuthorityError",
    "AuthorityStateError",
    "LocalOwnershipAuthority",
]
