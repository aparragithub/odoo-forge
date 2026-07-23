"""Pipeline (CI) port — interface only, no adapter in this slice.

`odoo_forge` depends only on this structural interface. No concrete CI
engine is chosen here (selecting one is out of scope for this slice); the
future adapter that maps these neutral operations onto a specific engine
MUST NOT be imported by this module.

`from __future__ import annotations` keeps every annotation a lazy string,
so this module never needs a runtime import of `pipeline.types`
(`PipelineRunSpec`/`PipelineRunRef`/`PipelineRunStatus`). `runtime_checkable`
only inspects method NAMES at runtime, so lazy annotations do not weaken the
`isinstance` conformance check.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from odoo_forge.pipeline.types import PipelineRunRef, PipelineRunSpec, PipelineRunStatus


@runtime_checkable
class PipelineProvider(Protocol):
    def trigger(self, spec: PipelineRunSpec) -> PipelineRunRef:
        """Start a run from a provider-neutral definition; return an opaque run handle."""
        ...

    def status(self, ref: PipelineRunRef) -> PipelineRunStatus:
        """Report `ref`'s current neutral run state."""
        ...

    def logs(self, ref: PipelineRunRef) -> str:
        """Return `ref`'s accumulated output text."""
        ...


__all__ = ["PipelineProvider"]
