import io
import json
import urllib.request
import zipfile

import pytest

from odoo_forge_pipeline_github.transport import GitHubActionsRestTransport


def _transport() -> GitHubActionsRestTransport:
    return GitHubActionsRestTransport(token="token", owner="acme", repo="widgets")


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return output.getvalue()


def _corrupted_compressed_entry() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("job.txt", b"workflow output\n" * 100)

    corrupted = bytearray(output.getvalue())
    with zipfile.ZipFile(io.BytesIO(corrupted)) as archive:
        entry = archive.getinfo("job.txt")
        data_offset = entry.header_offset + 30 + len(entry.filename.encode()) + len(entry.extra)
        corrupted[data_offset] = (corrupted[data_offset] & ~0x06) | 0x06
    return bytes(corrupted)


def _mock_urlopen(monkeypatch: pytest.MonkeyPatch, response: bytes) -> list[urllib.request.Request]:
    requests: list[urllib.request.Request] = []

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return response

    def urlopen(request: urllib.request.Request, *, timeout: float) -> Response:
        requests.append(request)
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return requests


def test_requests_pin_the_github_api_version(monkeypatch: pytest.MonkeyPatch) -> None:
    requests = _mock_urlopen(monkeypatch, b'{"workflow_run_id": 314}')

    _transport().dispatch_workflow("ci.yml", "main", {})

    assert requests[0].get_header("X-github-api-version") == "2026-03-10"


def test_dispatch_returns_the_exact_workflow_run_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _transport()
    requests = _mock_urlopen(monkeypatch, json.dumps({"workflow_run_id": 314}).encode())

    assert transport.dispatch_workflow("ci.yml", "main", {"env": "qa"}) == "314"
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].data == json.dumps({"ref": "main", "inputs": {"env": "qa"}}).encode()


@pytest.mark.parametrize("response", [b"{}", b"not-json", b"\xff"])
def test_dispatch_fails_when_the_run_id_is_missing_or_malformed(
    response: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = _transport()
    _mock_urlopen(monkeypatch, response)

    with pytest.raises(RuntimeError, match="workflow run id"):
        transport.dispatch_workflow("ci.yml", "main", {})


def test_logs_render_real_zip_entries_in_deterministic_name_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _transport()
    archive = _zip_bytes({"job/z.txt": b"last\n", "job/a.txt": b"first\n"})
    _mock_urlopen(monkeypatch, archive)

    assert transport.get_run_logs("42") == "first\nlast\n"


@pytest.mark.parametrize(
    "archive",
    [b"not-a-zip", _zip_bytes({"../secret.txt": b"secret"}), _zip_bytes({"/abs.txt": b"x"})],
)
def test_logs_reject_malformed_or_unsafe_archives(
    archive: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = _transport()
    _mock_urlopen(monkeypatch, archive)

    with pytest.raises(RuntimeError, match="log archive"):
        transport.get_run_logs("42")


def test_logs_reject_archives_over_the_uncompressed_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _transport()
    archive = _zip_bytes({"large.txt": b"x" * 101})
    _mock_urlopen(monkeypatch, archive)
    monkeypatch.setattr("odoo_forge_pipeline_github.transport.MAX_LOG_BYTES", 100)

    with pytest.raises(RuntimeError, match="log archive"):
        transport.get_run_logs("42")


def test_logs_reject_corrupted_compressed_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _transport()
    _mock_urlopen(monkeypatch, _corrupted_compressed_entry())

    with pytest.raises(RuntimeError, match="invalid log archive"):
        transport.get_run_logs("42")


def test_logs_reject_malformed_utf8_entry_names(monkeypatch: pytest.MonkeyPatch) -> None:
    archive = bytearray(_zip_bytes({"job.txt": b"output"}))
    central_header = archive.index(b"PK\x01\x02")
    archive[central_header + 8 : central_header + 10] = (0x800).to_bytes(2, "little")
    archive[central_header + 46] = 0xFF
    _mock_urlopen(monkeypatch, bytes(archive))

    with pytest.raises(RuntimeError, match="invalid log archive"):
        _transport().get_run_logs("42")
