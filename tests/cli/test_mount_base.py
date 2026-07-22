"""`_resolve_mount_base` is the ONE place `odoo_forge_cli` reads env for the
HOST mount base — `odoo_forge` core stays env-free. Pure function: reads the
environment at call time (not import time), so it is fully testable via
`monkeypatch` regardless of when `odoo_forge_cli.main` was first imported.
"""

from pathlib import Path

import pytest

from odoo_forge.manifest.errors import ManifestInputError
from odoo_forge.manifest.projection import MOUNT_ROOTS, build_mount_roots
from odoo_forge_cli import _support


class TestResolveMountBase:
    def test_default_resolution_with_no_env_vars_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FORGE_MOUNT_BASE", raising=False)
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)

        assert _support._resolve_mount_base() == Path.home() / ".local" / "state" / "odoo-forge"

    def test_forge_mount_base_overrides_everything(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FORGE_MOUNT_BASE", "/custom/path")
        monkeypatch.setenv("XDG_STATE_HOME", "/xdg/state")

        assert _support._resolve_mount_base() == Path("/custom/path")

    def test_xdg_state_home_influences_the_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FORGE_MOUNT_BASE", raising=False)
        monkeypatch.setenv("XDG_STATE_HOME", "/xdg/state")

        assert _support._resolve_mount_base() == Path("/xdg/state/odoo-forge")

    def test_empty_string_forge_mount_base_is_treated_as_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FORGE_MOUNT_BASE", "")
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)

        assert _support._resolve_mount_base() == Path.home() / ".local" / "state" / "odoo-forge"

    def test_forge_mount_base_mnt_reproduces_the_pre_change_host_paths(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FORGE_MOUNT_BASE", "/mnt")

        roots = build_mount_roots(_support._resolve_mount_base())

        assert roots == MOUNT_ROOTS

    def test_relative_forge_mount_base_is_rejected_with_a_clear_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A relative host base would flow unvalidated into the Docker `-v`
        # source token, where Docker silently treats it as a named-volume
        # reference instead of a bind mount. Fail fast with a clear message
        # instead of that silent, surprising behavior.
        monkeypatch.setenv("FORGE_MOUNT_BASE", "relative/mount/base")

        with pytest.raises(ManifestInputError, match="absolute path"):
            _support._resolve_mount_base()

    def test_relative_xdg_state_home_is_ignored_per_the_xdg_spec(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The XDG Base Directory spec mandates that a non-absolute
        # XDG_STATE_HOME be ignored, falling back to the default.
        monkeypatch.delenv("FORGE_MOUNT_BASE", raising=False)
        monkeypatch.setenv("XDG_STATE_HOME", "relative/state")

        assert _support._resolve_mount_base() == Path.home() / ".local" / "state" / "odoo-forge"
