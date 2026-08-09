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
        run_id: str = "1",
        run_state: tuple[str, str | None] = ("queued", None),
        run_logs: str = "",
    ) -> None:
        self.dispatch_calls: list[tuple[str, str, dict[str, str]]] = []
        self.get_run_state_calls: list[str] = []
        self.get_run_logs_calls: list[str] = []
        self._run_id = run_id
        self._run_state = run_state
        self._run_logs = run_logs

    def dispatch_workflow(self, workflow: str, ref: str, inputs: dict[str, str]) -> str:
        self.dispatch_calls.append((workflow, ref, inputs))
        return self._run_id

    def get_run_state(self, run_id: str) -> tuple[str, str | None]:
        self.get_run_state_calls.append(run_id)
        return self._run_state

    def get_run_logs(self, run_id: str) -> str:
        self.get_run_logs_calls.append(run_id)
        return self._run_logs


__all__ = ["FakeGitHubActionsTransport"]
