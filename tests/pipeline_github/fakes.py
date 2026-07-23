"""Hermetic fake `GitHubActionsTransport` for tests — zero network access."""

from __future__ import annotations


class FakeGitHubActionsTransport:
    """Records calls and returns configurable, canned responses.

    No socket, HTTP client, or subprocess is ever touched by this fake, so
    tests using it are hermetic by construction.
    """

    def __init__(
        self,
        *,
        run_ids: list[str] | None = None,
        run_state: tuple[str, str | None] = ("queued", None),
        run_logs: str = "",
    ) -> None:
        self.dispatch_calls: list[tuple[str, str, dict[str, str]]] = []
        self.latest_run_id_calls: list[tuple[str, str]] = []
        self.get_run_state_calls: list[str] = []
        self.get_run_logs_calls: list[str] = []
        self._run_ids = run_ids if run_ids is not None else ["1"]
        self._run_state = run_state
        self._run_logs = run_logs

    def dispatch_workflow(self, workflow: str, ref: str, inputs: dict[str, str]) -> None:
        self.dispatch_calls.append((workflow, ref, inputs))

    def latest_run_id(self, workflow: str, ref: str) -> str:
        self.latest_run_id_calls.append((workflow, ref))
        return self._run_ids[-1]

    def get_run_state(self, run_id: str) -> tuple[str, str | None]:
        self.get_run_state_calls.append(run_id)
        return self._run_state

    def get_run_logs(self, run_id: str) -> str:
        self.get_run_logs_calls.append(run_id)
        return self._run_logs


__all__ = ["FakeGitHubActionsTransport"]
