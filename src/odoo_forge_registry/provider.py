"""Concrete `ImageRegistryProvider` adapter backed by `docker buildx imagetools inspect`."""

import json
import os
import subprocess
from collections.abc import Mapping

from odoo_forge.image_registry.errors import (
    RegistryAuthenticationError,
    RegistryImageNotFoundError,
    RegistryUnavailableError,
)
from odoo_forge.image_registry.reference import normalize_image_reference

DEFAULT_TIMEOUT_SECONDS = 30.0
_AUTH_MARKERS = (
    "authentication required",
    "unauthorized",
    "insufficient_scope",
    "denied",
)
_NOT_FOUND_MARKERS = (
    "no such manifest",
    "not found",
    "does not exist",
)


def _registry_env() -> dict[str, str]:
    env = os.environ.copy()
    env["LANG"] = "C"
    env["LC_ALL"] = "C"
    return env


class GhcrImageRegistryProvider:
    def __init__(self, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout

    def resolve(self, ref: str) -> str:
        normalized = normalize_image_reference(ref, require_digest=False)
        digest = self._inspect_digest(normalized)
        return _canonical_digest_ref(normalized, digest)

    def validate(self, ref: str) -> str:
        normalized = normalize_image_reference(ref, require_digest=True)
        requested_digest = normalized.split("@", 1)[1]
        digest = self._inspect_digest(normalized)
        if digest != requested_digest:
            raise RegistryImageNotFoundError(normalized)
        return _canonical_digest_ref(normalized, digest)

    def _inspect_digest(self, ref: str) -> str:
        argv = [
            "docker",
            "buildx",
            "imagetools",
            "inspect",
            ref,
            "--format",
            "{{json .}}",
        ]
        try:
            result = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                check=False,
                timeout=self._timeout,
                env=_registry_env(),
            )
        except FileNotFoundError as exc:
            raise RegistryUnavailableError(ref, f"docker executable not found: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RegistryUnavailableError(
                ref, f"docker buildx inspect timed out after {self._timeout}s"
            ) from exc

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            lowered = stderr.lower()
            if any(marker in lowered for marker in _AUTH_MARKERS):
                raise RegistryAuthenticationError(ref)
            if any(marker in lowered for marker in _NOT_FOUND_MARKERS):
                raise RegistryImageNotFoundError(ref)
            raise RegistryUnavailableError(ref, stderr or "docker buildx inspect failed")

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RegistryUnavailableError(ref, "registry inspect returned malformed JSON") from exc

        digest = _extract_digest(payload)
        if digest is None:
            raise RegistryUnavailableError(ref, "registry inspect did not return a manifest digest")
        return digest


def _extract_digest(payload: object) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    manifest = payload.get("manifest")
    if isinstance(manifest, Mapping):
        digest = manifest.get("digest")
        if isinstance(digest, str):
            return digest
    digest = payload.get("digest")
    if isinstance(digest, str):
        return digest
    return None


def _canonical_digest_ref(ref: str, digest: str) -> str:
    repo = ref.split("@", 1)[0] if "@" in ref else ref.rsplit(":", 1)[0]
    return f"{repo}@{digest}"


__all__ = ["GhcrImageRegistryProvider"]
