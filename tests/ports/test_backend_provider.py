from collections.abc import Sequence

from pydantic import ValidationError

from odoo_forge.backend.destruction import DestroyResourceResult, DestroyResult
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

    def destroy(self, ref: object) -> DestroyResult:
        return DestroyResult(resources=())


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


def test_backend_port_documents_opaque_credential_injection_boundary() -> None:
    documentation = BackendProvider.run.__doc__

    assert documentation is not None
    assert "opaque injection descriptor" in documentation.lower()
    assert "plaintext" in documentation.lower()


def test_backend_port_exposes_destroy_result() -> None:
    provider = _FakeBackendProvider()

    assert isinstance(provider.destroy(object()), DestroyResult)
    assert "destroy" in dir(BackendProvider)


def test_destroy_result_is_frozen_and_validates_outcome_vocabulary() -> None:
    result = DestroyResult(
        resources=(DestroyResourceResult(kind="volume", identifier="data", outcome="protected"),)
    )

    assert result.resources[0].detail is None
    try:
        result.resources[0].outcome = "removed"  # type: ignore[misc]
    except ValidationError:
        pass
    else:
        raise AssertionError("destroy outcomes must be immutable")


def test_destroy_result_keeps_ordered_resource_outcomes() -> None:
    result = DestroyResult(
        resources=(
            DestroyResourceResult(kind="container", identifier="app", outcome="removed"),
            DestroyResourceResult(kind="network", identifier="net", outcome="absent"),
        )
    )

    assert [resource.outcome for resource in result.resources] == ["removed", "absent"]
