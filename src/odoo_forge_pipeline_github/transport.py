"""GitHub Actions transport seam.

`GitHubActionsTransport` is the sole I/O boundary for the adapter: all network
calls to the GitHub REST API live behind it. The provider never imports
`urllib`/`http` directly, which keeps unit tests hermetic (a fake transport is
injected) and contains GitHub-specific vocabulary (status/conclusion strings,
JSON payload shapes) inside this module.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Protocol, runtime_checkable

GITHUB_API_BASE_URL = "https://api.github.com"
DEFAULT_TIMEOUT_SECONDS = 30.0


@runtime_checkable
class GitHubActionsTransport(Protocol):
    def dispatch_workflow(self, workflow: str, ref: str, inputs: dict[str, str]) -> None:
        """Trigger a `workflow_dispatch` event for `workflow` on `ref`."""
        ...

    def latest_run_id(self, workflow: str, ref: str) -> str:
        """Return the id of the newest run for `workflow` on `ref`."""
        ...

    def get_run_state(self, run_id: str) -> tuple[str, str | None]:
        """Return the run's raw `(status, conclusion)` pair."""
        ...

    def get_run_logs(self, run_id: str) -> str:
        """Return the run's accumulated log text."""
        ...


class GitHubActionsRestTransport:
    """Real `GitHubActionsTransport` implementation backed by the GitHub REST API."""

    def __init__(
        self,
        *,
        token: str,
        owner: str,
        repo: str,
        base_url: str = GITHUB_API_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._token = token
        self._owner = owner
        self._repo = repo
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def dispatch_workflow(self, workflow: str, ref: str, inputs: dict[str, str]) -> None:
        url = (
            f"{self._base_url}/repos/{self._owner}/{self._repo}/actions/"
            f"workflows/{workflow}/dispatches"
        )
        body = json.dumps({"ref": ref, "inputs": inputs}).encode("utf-8")
        self._request(url, method="POST", body=body)

    def latest_run_id(self, workflow: str, ref: str) -> str:
        url = (
            f"{self._base_url}/repos/{self._owner}/{self._repo}/actions/workflows/"
            f"{workflow}/runs?branch={ref}&per_page=1"
        )
        payload = json.loads(self._request(url, method="GET"))
        runs = payload.get("workflow_runs", [])
        if not runs:
            raise RuntimeError(f"no runs found for workflow {workflow!r} on ref {ref!r}")
        return str(runs[0]["id"])

    def get_run_state(self, run_id: str) -> tuple[str, str | None]:
        url = f"{self._base_url}/repos/{self._owner}/{self._repo}/actions/runs/{run_id}"
        payload = json.loads(self._request(url, method="GET"))
        return (payload["status"], payload.get("conclusion"))

    def get_run_logs(self, run_id: str) -> str:
        url = f"{self._base_url}/repos/{self._owner}/{self._repo}/actions/runs/{run_id}/logs"
        return self._request(url, method="GET").decode("utf-8", errors="replace")

    def _request(self, url: str, *, method: str, body: bytes | None = None) -> bytes:
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
            body_bytes: bytes = response.read()
            return body_bytes


__all__ = ["GitHubActionsTransport", "GitHubActionsRestTransport"]
