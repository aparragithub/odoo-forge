"""GitHub Actions transport seam.

`GitHubActionsTransport` is the sole I/O boundary for the adapter: all network
calls to the GitHub REST API live behind it. The provider never imports
`urllib`/`http` directly, which keeps unit tests hermetic (a fake transport is
injected) and contains GitHub-specific vocabulary (status/conclusion strings,
JSON payload shapes) inside this module.
"""

from __future__ import annotations

import io
import json
import urllib.request
import zipfile
from pathlib import PurePosixPath
from typing import Protocol, runtime_checkable

GITHUB_API_BASE_URL = "https://api.github.com"
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_LOG_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_LOG_BYTES = 100 * 1024 * 1024
MAX_LOG_ENTRIES = 1000


@runtime_checkable
class GitHubActionsTransport(Protocol):
    def dispatch_workflow(self, workflow: str, ref: str, inputs: dict[str, str]) -> str:
        """Trigger `workflow` on `ref` and return the dispatched run id."""
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

    def dispatch_workflow(self, workflow: str, ref: str, inputs: dict[str, str]) -> str:
        url = (
            f"{self._base_url}/repos/{self._owner}/{self._repo}/actions/"
            f"workflows/{workflow}/dispatches"
        )
        body = json.dumps({"ref": ref, "inputs": inputs}).encode("utf-8")
        try:
            payload = json.loads(self._request(url, method="POST", body=body))
            run_id = payload["workflow_run_id"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise RuntimeError("workflow dispatch response has no workflow run id") from exc
        if isinstance(run_id, bool) or not isinstance(run_id, (int, str)) or not str(run_id):
            raise RuntimeError("workflow dispatch response has no workflow run id")
        return str(run_id)

    def get_run_state(self, run_id: str) -> tuple[str, str | None]:
        url = f"{self._base_url}/repos/{self._owner}/{self._repo}/actions/runs/{run_id}"
        payload = json.loads(self._request(url, method="GET"))
        return (payload["status"], payload.get("conclusion"))

    def get_run_logs(self, run_id: str) -> str:
        url = f"{self._base_url}/repos/{self._owner}/{self._repo}/actions/runs/{run_id}/logs"
        archive_bytes = self._request(url, method="GET")
        if len(archive_bytes) > MAX_LOG_ARCHIVE_BYTES:
            raise RuntimeError("log archive exceeds the compressed size limit")
        try:
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
                entries = [entry for entry in archive.infolist() if not entry.is_dir()]
                if len(entries) > MAX_LOG_ENTRIES:
                    raise RuntimeError("log archive contains too many entries")
                if sum(entry.file_size for entry in entries) > MAX_LOG_BYTES:
                    raise RuntimeError("log archive exceeds the uncompressed size limit")

                output: list[str] = []
                for entry in sorted(entries, key=lambda item: item.filename):
                    normalized = entry.filename.replace("\\", "/")
                    path = PurePosixPath(normalized)
                    if path.is_absolute() or ".." in path.parts or entry.flag_bits & 0x1:
                        raise RuntimeError("log archive contains an unsafe entry")
                    output.append(archive.read(entry).decode("utf-8", errors="replace"))
                return "".join(output)
        except zipfile.BadZipFile as exc:
            raise RuntimeError("invalid log archive") from exc

    def _request(self, url: str, *, method: str, body: bytes | None = None) -> bytes:
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2026-03-10",
            },
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
            body_bytes: bytes = response.read()
            return body_bytes


__all__ = ["GitHubActionsTransport", "GitHubActionsRestTransport"]
