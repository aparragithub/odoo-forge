from typing import Sequence

from odoo_forge.ports.backend_provider import BackendProvider


class _FakeBackendProvider:
    """Structural stand-in — not a real adapter, just satisfies the shape.

    Uses plain `object`/`str` parameter types rather than the real
    `BackendPlan`/`InstanceRef`/`InstanceStatus`/`ExecResult` types, proving
    the port contract is satisfiable by `isinstance` without needing PR-1b's
    status types (`runtime_checkable` verifies method NAMES only).
    """

    def run(self, plan: object) -> object:
        return "instance-ref"

    def status(self, ref: object) -> object:
        return "instance-status"

    def stop(self, ref: object) -> None:
        pass

    def logs(self, ref: object, role: object) -> str:
        return "log text"

    def exec(self, ref: object, argv: Sequence[str]) -> object:
        return "exec-result"


def test_conforming_class_satisfies_backend_provider_protocol() -> None:
    provider = _FakeBackendProvider()

    assert isinstance(provider, BackendProvider)
    assert provider.run(plan=object()) == "instance-ref"


def test_non_conforming_class_does_not_satisfy_protocol() -> None:
    class _MissingExec:
        """Conforms to every method except `exec` — must fail `isinstance`."""

        def run(self, plan: object) -> object:
            return "instance-ref"

        def status(self, ref: object) -> object:
            return "instance-status"

        def stop(self, ref: object) -> None:
            pass

        def logs(self, ref: object, role: object) -> str:
            return "log text"

    assert not isinstance(_MissingExec(), BackendProvider)
