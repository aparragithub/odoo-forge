"""Local backend port — interface only, no adapter in this slice.

`odoo_forge` depends only on this structural interface. The concrete
adapter (`docker` CLI via `subprocess`) lives outside the core package in a
sibling package (`odoo_forge_docker`, later PR of this slice) and MUST NOT
be imported here.

`from __future__ import annotations` keeps every annotation a lazy string,
so this module never needs a runtime import of `backend.status`
(`InstanceRef`/`InstanceStatus`/`ExecResult`, added in a later PR of this
slice) or `backend.plan` (`BackendPlan`/`ContainerRole`). `runtime_checkable`
only inspects method NAMES at runtime, so lazy annotations do not weaken the
`isinstance` conformance check; a later PR adds an explicit
`inspect.signature` conformance test once the referenced types exist.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from odoo_forge.backend.plan import BackendPlan, ContainerRole
    from odoo_forge.backend.status import ExecResult, InstanceRef, InstanceStatus


@runtime_checkable
class BackendProvider(Protocol):
    def run(self, plan: BackendPlan) -> InstanceRef:
        """Provision `plan` and return a handle to a ready, reachable instance."""
        ...

    def status(self, ref: InstanceRef) -> InstanceStatus:
        """Report `ref`'s live state, derived from Docker introspection only."""
        ...

    def stop(self, ref: InstanceRef) -> None:
        """Stop and remove `ref`'s containers/network, preserving named volumes."""
        ...

    def logs(self, ref: InstanceRef, role: ContainerRole) -> str:
        """Return `role`'s container log text for `ref`."""
        ...

    def exec(self, ref: InstanceRef, argv: Sequence[str]) -> ExecResult:
        """Run `argv` inside `ref`'s Odoo container and return its result."""
        ...


__all__ = ["BackendProvider"]
