"""Concrete `ImageRegistryProvider` adapter backed by `docker buildx imagetools inspect`."""

import json
import os
import re
import subprocess
from collections.abc import Mapping

from odoo_forge.image_registry.errors import (
    RegistryAuthenticationError,
    RegistryError,
    RegistryImageNotFoundError,
    RegistryPublishError,
    RegistryPullError,
    RegistryUnavailableError,
)
from odoo_forge.image_registry.reference import (
    normalize_digest_image_reference,
    normalize_publishable_image_reference,
)
from odoo_forge.image_registry.types import ImageDigestRef, ImageRef, LocalImageRef

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
    "manifest unknown",
)
_PUSH_DIGEST_RE = re.compile(r"digest:\s*(sha256:[0-9a-f]{64})", re.IGNORECASE | re.MULTILINE)


def _registry_env() -> dict[str, str]:
    env = os.environ.copy()
    env["LANG"] = "C"
    env["LC_ALL"] = "C"
    return env


class GhcrImageRegistryProvider:
    def __init__(self, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout

    def publish(self, ref: ImageRef) -> ImageDigestRef:
        normalized = normalize_publishable_image_reference(ref)
        try:
            push_result = self._push_image(normalized)
            digest = _extract_push_digest(push_result)
            if digest is None:
                digest = self._inspect_digest(normalized)
            return normalize_digest_image_reference(_canonical_digest_ref(normalized, digest))
        except RegistryError as exc:
            raise RegistryPublishError(normalized, str(exc)) from exc

    def pull(self, digest: ImageDigestRef) -> LocalImageRef:
        normalized = normalize_digest_image_reference(digest)
        try:
            self._pull_image(normalized)
        except RegistryError as exc:
            raise RegistryPullError(normalized, str(exc)) from exc
        return LocalImageRef(normalized)

    def resolve_digest(self, ref: ImageRef) -> ImageDigestRef:
        normalized = normalize_publishable_image_reference(ref)
        digest = self._inspect_digest(normalized)
        return normalize_digest_image_reference(_canonical_digest_ref(normalized, digest))

    def exists(self, digest: ImageDigestRef) -> bool:
        normalized = normalize_digest_image_reference(digest)
        try:
            current_digest = self._inspect_digest(normalized)
        except RegistryImageNotFoundError:
            return False
        return _canonical_digest_ref(normalized, current_digest) == normalized

    def _inspect_digest(self, ref: str) -> str:
        result = self._run_registry_command(
            [
                "docker",
                "buildx",
                "imagetools",
                "inspect",
                ref,
                "--format",
                "{{json .}}",
            ],
            ref,
            unavailable_detail="docker buildx inspect failed",
        )

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RegistryUnavailableError(ref, "registry inspect returned malformed JSON") from exc

        digest = _extract_digest(payload)
        if digest is None:
            raise RegistryUnavailableError(ref, "registry inspect did not return a manifest digest")
        return digest

    def _push_image(self, ref: str) -> subprocess.CompletedProcess[str]:
        return self._run_registry_command(
            ["docker", "push", ref], ref, unavailable_detail="docker push failed"
        )

    def _pull_image(self, ref: str) -> None:
        self._run_registry_command(
            ["docker", "pull", ref], ref, unavailable_detail="docker pull failed"
        )

    def _run_registry_command(
        self,
        argv: list[str],
        ref: str,
        *,
        unavailable_detail: str,
    ) -> subprocess.CompletedProcess[str]:
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
                ref, f"docker command timed out after {self._timeout}s"
            ) from exc

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            lowered = stderr.lower()
            if any(marker in lowered for marker in _AUTH_MARKERS):
                raise RegistryAuthenticationError(ref)
            if any(marker in lowered for marker in _NOT_FOUND_MARKERS):
                raise RegistryImageNotFoundError(ref)
            raise RegistryUnavailableError(ref, stderr or unavailable_detail)

        return result


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


def _extract_push_digest(result: subprocess.CompletedProcess[str]) -> str | None:
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    match = _PUSH_DIGEST_RE.search(output)
    if match is None:
        return None
    return match.group(1).lower()


def _canonical_digest_ref(ref: str, digest: str) -> str:
    repo = ref.split("@", 1)[0] if "@" in ref else ref.rsplit(":", 1)[0]
    return f"{repo}@{digest}"


__all__ = ["GhcrImageRegistryProvider"]
