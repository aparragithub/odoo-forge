"""Filesystem-backed content-addressed staging store (design D7/D8, bridge slice B1).

Disk custody mirrors `LocalOwnershipAuthority`
(`odoo_forge_postgres_docker/authority.py`): root under
`$XDG_STATE_HOME/odoo-forge/artifact-store` (see
`default_staged_artifact_store_root`), directories `0o700`, files `0o600`,
every custody or IO failure fails closed. Layout: `blobs/<algorithm>-<hex
digest>.bin` (content-addressed, dedup) + `manifests/<restore_set_id>.json`
(the manifest persisted under that ref).

Path derivation is constrained to values the domain types already validate
(`ArtifactDigest`'s hex-and-length shape, `require_safe_opaque_identifier`'s
`[A-Za-z0-9_-]` ref shape) — but this store independently RE-validates both
before building any path, so a manifest tampered on disk (bypassing the
in-memory Pydantic construction that originally produced it) can never
smuggle a traversal segment into a blob or manifest path (design threat
matrix: "Store path derivation").

This slice (B1) is a standalone store: it is NOT wired into capture,
restore, or the coordinator yet (that is bridge slices B2-B5).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import stat
from contextlib import suppress
from pathlib import Path

from odoo_forge.data_artifacts.contracts import (
    ArtifactDigest,
    DiscardOutcome,
    DiscardOutcomeCode,
    RestoreSetComponent,
    RestoreSetManifest,
)
from odoo_forge.data_artifacts.types import DataArtifactRef, require_safe_opaque_identifier
from odoo_forge.database.errors import DatabaseOperationError

_DIRECTORY_MODE = 0o700
_FILE_MODE = 0o600
_CHUNK_SIZE = 1 << 20  # 1 MiB: bounds in-memory buffering while re-hashing a staged blob.
_DIGEST_HEX_LENGTHS = {"sha256": 64, "sha512": 128}
_HEX_TEXT = re.compile(r"^[0-9a-fA-F]+$")


class StagedArtifactError(DatabaseOperationError):
    """Base error for staged artifact store failures, without filesystem detail."""


class StagedArtifactCustodyError(StagedArtifactError):
    """Staged artifact paths do not meet the required private local custody."""

    public_detail = "staged artifact store custody is invalid"


class StagedArtifactUnavailableError(StagedArtifactError):
    """The requested staged artifact reference or blob is not present."""

    public_detail = "staged artifact is unavailable"


class StagedArtifactIntegrityError(StagedArtifactError):
    """A staged blob's recomputed digest does not match its recorded digest."""

    public_detail = "staged artifact integrity verification failed"


class StagedArtifactStateError(StagedArtifactError):
    """Staged artifact manifest state is missing, corrupt, or could not be committed."""

    public_detail = "staged artifact state is invalid"


def default_staged_artifact_store_root() -> Path:
    """Resolve the default store root: `$XDG_STATE_HOME/odoo-forge/artifact-store`.

    Mirrors `DockerBackendProvider._default_authority`'s `XDG_STATE_HOME`
    resolution (`odoo_forge_postgres_docker/provider.py`). Not wired into any
    composition root in this slice (B1); a future slice (B5) is expected to
    call this when building a production `FilesystemStagedArtifactStore`.
    """
    state_home = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state")))
    return state_home / "odoo-forge" / "artifact-store"


class FilesystemStagedArtifactStore:
    """Content-addressed, custody-hardened filesystem implementation of `StagedArtifactStore`.

    Structurally satisfies `odoo_forge.data_artifacts.staging.StagedArtifactStore`.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self._blobs_dir = root / "blobs"
        self._manifests_dir = root / "manifests"

    def stage(self, digest: ArtifactDigest, source_path: Path) -> None:
        """Move `source_path`'s bytes into custody, keyed by `digest` (content-addressed dedup)."""
        blob_path = self._blob_path(digest)
        self._ensure_dir(self._blobs_dir)
        if blob_path.exists():
            self._validate_private_path(blob_path, _FILE_MODE, directory=False)
            with suppress(OSError):
                source_path.unlink()
            return
        self._move_into_custody(source_path, blob_path)

    def put(self, ref: DataArtifactRef, manifest: RestoreSetManifest) -> None:
        """Persist `manifest` under `ref`, superseding any prior record for `ref`."""
        self._ensure_dir(self._manifests_dir)
        manifest_path = self._manifest_path(ref)
        payload = manifest.model_dump_json().encode("utf-8")
        self._write_atomic(manifest_path, payload)

    def resolve(self, ref: DataArtifactRef) -> RestoreSetManifest:
        """Return the manifest persisted under `ref`, failing closed if absent or corrupt."""
        manifest_path = self._manifest_path(ref)
        try:
            descriptor = self._open_private_file(manifest_path)
        except FileNotFoundError as exc:
            raise StagedArtifactUnavailableError() from exc
        try:
            with os.fdopen(descriptor, "r", encoding="utf-8") as manifest_file:
                payload = json.load(manifest_file)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise StagedArtifactStateError() from exc
        try:
            return RestoreSetManifest.model_validate(payload)
        except ValueError as exc:
            raise StagedArtifactStateError() from exc

    def open_component(self, component: RestoreSetComponent) -> Path:
        """Return a readable path to `component`'s staged bytes, verifying its digest."""
        blob_path = self._blob_path(component.digest)
        if not blob_path.exists():
            raise StagedArtifactUnavailableError()
        self._validate_private_path(blob_path, _FILE_MODE, directory=False)
        recomputed = self._hash_file(blob_path, component.digest.algorithm)
        if recomputed != component.digest.value.lower():
            raise StagedArtifactIntegrityError()
        return blob_path

    def discard(self, ref: DataArtifactRef) -> DiscardOutcome:
        """Remove `ref`'s manifest and its staged blobs; idempotent when already absent.

        A blob is content-addressed and may be shared by other staged
        manifests (`stage` dedups by digest); this only unlinks a blob when no
        other manifest still references its digest, so discarding one
        manifest can never silently destroy bytes another manifest depends
        on. A blob deliberately preserved because it is still shared is a
        success, not a residual failure.
        """
        try:
            manifest = self.resolve(ref)
        except StagedArtifactUnavailableError:
            return DiscardOutcome(code=DiscardOutcomeCode.COMPLETED)
        except StagedArtifactStateError:
            return self._discard_manifest_file(ref)
        referenced_elsewhere = self._referenced_digests_excluding(ref)
        residual_ids: list[str] = []
        for component in manifest.components:
            digest_key = (component.digest.algorithm, component.digest.value.lower())
            if digest_key in referenced_elsewhere:
                continue
            try:
                self._blob_path(component.digest).unlink(missing_ok=True)
            except OSError:
                residual_ids.append(component.opaque_component_ref)
        return self._discard_manifest_file(ref, residual_ids=residual_ids)

    def _referenced_digests_excluding(self, excluded_ref: DataArtifactRef) -> set[tuple[str, str]]:
        """Collect `(algorithm, lowercase digest)` pairs referenced by every OTHER
        staged manifest, so `discard` can tell a shared blob from an orphan."""
        referenced: set[tuple[str, str]] = set()
        if not self._manifests_dir.exists():
            return referenced
        for manifest_file in self._manifests_dir.glob("*.json"):
            if manifest_file.stem == str(excluded_ref):
                continue
            try:
                other = self.resolve(DataArtifactRef(manifest_file.stem))
            except StagedArtifactError:
                continue
            for component in other.components:
                referenced.add((component.digest.algorithm, component.digest.value.lower()))
        return referenced

    def _discard_manifest_file(
        self, ref: DataArtifactRef, *, residual_ids: list[str] | None = None
    ) -> DiscardOutcome:
        residual_ids = list(residual_ids) if residual_ids else []
        try:
            self._manifest_path(ref).unlink(missing_ok=True)
        except OSError:
            residual_ids.append(str(ref))
        if residual_ids:
            return DiscardOutcome(
                code=DiscardOutcomeCode.RESIDUAL_FAILURE, residual_ids=tuple(residual_ids)
            )
        return DiscardOutcome(code=DiscardOutcomeCode.COMPLETED)

    def _blob_path(self, digest: ArtifactDigest) -> Path:
        expected_length = _DIGEST_HEX_LENGTHS.get(digest.algorithm)
        if (
            expected_length is None
            or len(digest.value) != expected_length
            or _HEX_TEXT.fullmatch(digest.value) is None
        ):
            raise StagedArtifactCustodyError()
        return self._blobs_dir / f"{digest.algorithm}-{digest.value.lower()}.bin"

    def _manifest_path(self, ref: DataArtifactRef | str) -> Path:
        try:
            safe_ref = require_safe_opaque_identifier(str(ref), "staged artifact reference")
        except ValueError as exc:
            raise StagedArtifactCustodyError() from exc
        return self._manifests_dir / f"{safe_ref}.json"

    def _ensure_root(self) -> None:
        try:
            self.root.mkdir(mode=_DIRECTORY_MODE)
        except FileExistsError:
            pass
        except OSError as exc:
            raise StagedArtifactCustodyError() from exc
        self._validate_private_path(self.root, _DIRECTORY_MODE, directory=True)

    def _ensure_dir(self, path: Path) -> None:
        self._ensure_root()
        try:
            path.mkdir(mode=_DIRECTORY_MODE)
        except FileExistsError:
            pass
        except OSError as exc:
            raise StagedArtifactCustodyError() from exc
        self._validate_private_path(path, _DIRECTORY_MODE, directory=True)

    def _move_into_custody(self, source_path: Path, blob_path: Path) -> None:
        try:
            source_is_symlink = stat.S_ISLNK(os.lstat(source_path).st_mode)
        except OSError as exc:
            raise StagedArtifactCustodyError() from exc
        if source_is_symlink:
            raise StagedArtifactCustodyError()
        temporary = blob_path.parent / f".{blob_path.name}.{secrets.token_hex(8)}.tmp"
        try:
            shutil.move(os.fspath(source_path), os.fspath(temporary))
            os.chmod(temporary, _FILE_MODE)
            os.replace(temporary, blob_path)
        except OSError as exc:
            with suppress(OSError):
                temporary.unlink()
            raise StagedArtifactCustodyError() from exc
        self._validate_private_path(blob_path, _FILE_MODE, directory=False)

    def _write_atomic(self, path: Path, payload: bytes) -> None:
        temporary = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
        descriptor: int | None = None
        try:
            descriptor = os.open(
                temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, _FILE_MODE
            )
            os.fchmod(descriptor, _FILE_MODE)
            remaining = payload
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise OSError("staged artifact manifest write made no progress")
                remaining = remaining[written:]
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = None
            os.replace(temporary, path)
        except OSError as exc:
            raise StagedArtifactStateError() from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise StagedArtifactStateError() from exc

    def _open_private_file(self, path: Path) -> int:
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW, _FILE_MODE)
        except OSError as exc:
            if isinstance(exc, FileNotFoundError):
                raise
            raise StagedArtifactCustodyError() from exc
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
            raise StagedArtifactCustodyError() from exc
        expected_type = stat.S_ISDIR if directory else stat.S_ISREG
        if (
            not expected_type(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != mode
        ):
            raise StagedArtifactCustodyError()

    @staticmethod
    def _hash_file(path: Path, algorithm: str) -> str:
        """Re-hash a staged blob under the same O_NOFOLLOW + fstat custody idiom
        as `_open_private_file`, so a symlink swapped in after an earlier lstat
        check cannot be followed here (TOCTOU)."""
        hasher = hashlib.new(algorithm)
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError as exc:
            if isinstance(exc, FileNotFoundError):
                raise StagedArtifactUnavailableError() from exc
            raise StagedArtifactCustodyError() from exc
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != _FILE_MODE
            ):
                raise StagedArtifactCustodyError()
            while chunk := os.read(descriptor, _CHUNK_SIZE):
                hasher.update(chunk)
        except OSError as exc:
            raise StagedArtifactUnavailableError() from exc
        finally:
            os.close(descriptor)
        return hasher.hexdigest()


__all__ = [
    "FilesystemStagedArtifactStore",
    "StagedArtifactCustodyError",
    "StagedArtifactError",
    "StagedArtifactIntegrityError",
    "StagedArtifactStateError",
    "StagedArtifactUnavailableError",
    "default_staged_artifact_store_root",
]
