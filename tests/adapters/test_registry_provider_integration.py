"""Explicitly gated live evidence for the GHCR registry adapter.

The default suite remains hermetic. Running this module requires a declared
policy, Docker credentials, a reachable Docker daemon/buildx, and a fixture
tag plus its expected immutable digest reference.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from odoo_forge.image_registry import ImageDigestRef, ImageRef
from odoo_forge_registry.provider import GhcrImageRegistryProvider

pytestmark = pytest.mark.integration


def _require_live_registry() -> tuple[str, str]:
    if os.getenv("FORGE_REGISTRY_LIVE_POLICY") != "allow":
        pytest.skip("live registry policy is not explicitly enabled")
    if os.getenv("FORGE_REGISTRY_LIVE_CREDENTIALS") != "available":
        pytest.skip("live registry credentials are not explicitly declared available")

    tag_ref = os.getenv("FORGE_REGISTRY_LIVE_TAG")
    digest_ref = os.getenv("FORGE_REGISTRY_LIVE_DIGEST")
    if not tag_ref or not digest_ref:
        pytest.skip("live registry tag and immutable digest fixture are not configured")

    if shutil.which("docker") is None:
        pytest.skip("live registry prerequisite unavailable: docker executable not found")
    for argv, label in (
        (["docker", "version", "--format", "{{.Server.Version}}"], "Docker daemon"),
        (["docker", "buildx", "version"], "Docker buildx"),
    ):
        try:
            result = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pytest.skip(f"live registry prerequisite unavailable: {label}")
        if result.returncode != 0:
            pytest.skip(f"live registry prerequisite unavailable: {label}")

    return tag_ref, digest_ref


def test_live_registry_resolves_and_confirms_immutable_fixture() -> None:
    tag_ref, digest_ref = _require_live_registry()
    provider = GhcrImageRegistryProvider()

    assert provider.resolve_digest(ImageRef(tag_ref)) == digest_ref
    assert provider.exists(ImageDigestRef(digest_ref)) is True
