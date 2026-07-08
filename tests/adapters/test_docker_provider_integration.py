"""Real-daemon-only smoke test for `DockerBackendProvider`.

Deselected from the default Strict-TDD unit run (`addopts = "-m 'not
integration'"` in `pyproject.toml`); run explicitly with `uv run pytest -m
integration` against a live Docker daemon.

This is a minimal skeleton pinning the scenarios the design (`design.md`,
"Integration" test row) calls out as ONLY observable against a real daemon:
the Postgres first-boot socket-vs-TCP readiness race, ephemeral host-port
assignment, and the Odoo `Health=healthy` wait timing. It is intentionally
not fleshed out here — CI/local unit runs never require a docker daemon.
"""

import pytest

pytestmark = pytest.mark.integration


def test_run_status_stop_round_trip_against_real_daemon() -> None:
    """Full `run` -> `status` -> `stop` cycle against a live Docker daemon.

    Covers: PG bootstrap readiness race (socket vs. TCP), ephemeral host-port
    assignment for the Odoo container, and the `Health=healthy` wait timing —
    none of which are observable through the mocked-subprocess unit tests in
    `tests/adapters/test_docker_provider.py`.
    """
    pytest.skip(
        "integration skeleton: requires a real Docker daemon; "
        "fleshed out in a follow-up hardening pass, not this slice"
    )
