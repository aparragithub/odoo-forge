"""GitHub Actions `PipelineProvider` adapter.

Depends only on the neutral port (`odoo_forge.ports.pipeline_provider`) and
neutral types (`odoo_forge.pipeline.types`); all GitHub-specific vocabulary
(status/conclusion strings, run ids, REST payload shapes) is translated here
or contained in `transport.py`. Network I/O never happens directly in this
module — it always goes through the injected `GitHubActionsTransport`.
"""

from __future__ import annotations

from odoo_forge.pipeline.types import (
    PipelineRunRef,
    PipelineRunSpec,
    PipelineRunState,
    PipelineRunStatus,
)
from odoo_forge_pipeline_github.transport import GitHubActionsTransport

_PENDING_STATUSES = frozenset({"queued", "requested", "waiting", "pending"})
_FAILURE_CONCLUSIONS = frozenset({"failure", "timed_out", "startup_failure"})


def _map_state(status: str, conclusion: str | None) -> PipelineRunState:
    """Map a GitHub Actions `(status, conclusion)` pair onto a neutral state.

    GitHub's `cancelled` conclusion (double-L, GitHub spelling) maps to the
    neutral `canceled` state (single-L, neutral spelling) — the two words are
    intentionally different across the port boundary.
    """
    if status in _PENDING_STATUSES:
        return "pending"
    if status == "in_progress":
        return "running"
    if status == "completed":
        if conclusion == "success":
            return "succeeded"
        if conclusion in _FAILURE_CONCLUSIONS:
            return "failed"
        if conclusion == "cancelled":
            return "canceled"
        return "unknown"
    return "unknown"


class GitHubActionsPipelineProvider:
    """Structurally satisfies `odoo_forge.ports.pipeline_provider.PipelineProvider`."""

    def __init__(
        self,
        *,
        transport: GitHubActionsTransport,
        owner: str,
        repo: str,
        ref: str,
    ) -> None:
        self._transport = transport
        self._owner = owner
        self._repo = repo
        self._ref = ref

    def trigger(self, spec: PipelineRunSpec) -> PipelineRunRef:
        self._transport.dispatch_workflow(spec.definition, self._ref, spec.parameters)
        run_id = self._transport.latest_run_id(spec.definition, self._ref)
        return PipelineRunRef(run_id=run_id)

    def status(self, ref: PipelineRunRef) -> PipelineRunStatus:
        status, conclusion = self._transport.get_run_state(ref.run_id)
        return PipelineRunStatus(state=_map_state(status, conclusion))

    def logs(self, ref: PipelineRunRef) -> str:
        return self._transport.get_run_logs(ref.run_id)


__all__ = ["GitHubActionsPipelineProvider"]
