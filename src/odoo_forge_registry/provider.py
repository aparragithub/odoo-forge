"""Concrete `ImageRegistryProvider` adapter backed by `docker buildx imagetools inspect`."""

import json
import os
import re
import subprocess
from collections.abc import Mapping

from odoo_forge.image_registry.errors import (
    MalformedImageReferenceError,
    RegistryAuthenticationError,
    RegistryDigestMismatchError,
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
        normalized = _normalize_publishable_ref(ref)
        try:
            push_result = self._push_image(normalized)
            digest = _extract_push_digest(push_result)
            if digest is None:
                digest = self._inspect_digest(normalized)
            return normalize_digest_image_reference(_canonical_digest_ref(normalized, digest))
        except RegistryError as exc:
            raise RegistryPublishError(_safe_repository(normalized), str(exc)) from exc

    def pull(self, digest: ImageDigestRef) -> LocalImageRef:
        normalized = _normalize_digest_ref(digest)
        try:
            self._pull_image(normalized)
        except RegistryError as exc:
            raise RegistryPullError(_safe_repository(normalized), str(exc)) from exc
        return LocalImageRef(normalized)

    def resolve_digest(self, ref: ImageRef) -> ImageDigestRef:
        normalized = _normalize_publishable_ref(ref)
        digest = self._inspect_digest(normalized)
        return normalize_digest_image_reference(_canonical_digest_ref(normalized, digest))

    def exists(self, digest: ImageDigestRef) -> bool:
        normalized = _normalize_digest_ref(digest)
        try:
            current_digest = self._inspect_digest(normalized)
        except RegistryImageNotFoundError:
            return False
        if _canonical_digest_ref(normalized, current_digest) != normalized:
            raise RegistryDigestMismatchError(_safe_repository(normalized))
        return True

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
            exc.doc = ""
            exc.args = ("registry inspect returned malformed JSON",)
            raise RegistryUnavailableError(
                _safe_repository(ref), "registry inspect returned malformed JSON"
            ) from exc

        digest = _extract_digest(payload)
        if digest is None:
            raise RegistryUnavailableError(
                _safe_repository(ref), "registry inspect did not return a manifest digest"
            )
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
            exc.filename = None
            exc.strerror = "docker executable not found"
            exc.args = ("docker executable not found",)
            raise RegistryUnavailableError(
                _safe_repository(ref), "docker executable not found"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            exc.cmd = ["docker"]
            exc.output = None
            exc.stderr = None
            raise RegistryUnavailableError(
                _safe_repository(ref), f"docker command timed out after {self._timeout}s"
            ) from exc

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            lowered = stderr.lower()
            if any(marker in lowered for marker in _AUTH_MARKERS):
                raise RegistryAuthenticationError(_safe_repository(ref))
            if any(marker in lowered for marker in _NOT_FOUND_MARKERS):
                raise RegistryImageNotFoundError(_safe_repository(ref))
            raise RegistryUnavailableError(_safe_repository(ref), unavailable_detail)

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


def _safe_repository(ref: str) -> str:
    ghcr_index = ref.lower().find("ghcr.io/")
    if ghcr_index < 0:
        return "ghcr.io"
    repository = ref[ghcr_index:].split("@", 1)[0].rsplit(":", 1)[0]
    parts = repository.split("/")
    return "/".join(parts[:3]) if len(parts) >= 3 else "ghcr.io"


def _reject_userinfo(ref: str) -> None:
    registry_part = ref.split("/", 1)[0]
    if "@" in registry_part:
        raise MalformedImageReferenceError(
            _safe_repository(ref), "credentials in image references are not supported"
        )


def _normalize_publishable_ref(ref: str) -> ImageRef:
    _reject_userinfo(ref)
    return normalize_publishable_image_reference(ref)


def _normalize_digest_ref(ref: str) -> ImageDigestRef:
    _reject_userinfo(ref)
    return normalize_digest_image_reference(ref)


__all__ = ["GhcrImageRegistryProvider"]
