import json
import traceback
import urllib.error
import urllib.request
from collections.abc import Callable

import pytest

from odoo_forge.identity_github.transport import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_RESPONSE_BYTES,
    GitHubOidcHttpsTransport,
    GitHubOidcTransport,
)


class _FakeTransport:
    def get_metadata(self, issuer: str) -> dict[str, object]:
        return {"issuer": issuer}

    def get_jwks(self, jwks_uri: str) -> dict[str, object]:
        return {"jwks_uri": jwks_uri}


class _Response:
    def __init__(self, body: bytes, reads: list[int], url: str) -> None:
        self._body = body
        self._reads = reads
        self._url = url

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, amount: int = -1) -> bytes:
        self._reads.append(amount)
        return self._body

    def geturl(self) -> str:
        return self._url


def _urlopen_returning(
    body: bytes,
    calls: list[tuple[str, float]],
    reads: list[int],
    *,
    final_url: str | None = None,
) -> Callable[..., _Response]:
    def urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        calls.append((request.full_url, timeout))
        return _Response(body, reads, final_url or request.full_url)

    return urlopen


def test_transport_protocol_is_runtime_checkable_and_satisfied_structurally() -> None:
    assert isinstance(_FakeTransport(), GitHubOidcTransport)


def test_non_https_urls_are_rejected_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("network must not be called")

    monkeypatch.setattr(urllib.request, "urlopen", fail_if_called)
    transport = GitHubOidcHttpsTransport()

    with pytest.raises(ValueError, match="HTTPS"):
        transport.get_metadata("http://issuer.example")
    with pytest.raises(ValueError, match="HTTPS"):
        transport.get_jwks("file:///tmp/keys.json")


def test_metadata_issuer_with_query_is_rejected_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("network must not be called")

    monkeypatch.setattr(urllib.request, "urlopen", fail_if_called)

    with pytest.raises(ValueError, match="HTTPS"):
        GitHubOidcHttpsTransport().get_metadata("https://issuer.example?token=secret")


def test_https_requests_use_timeout_and_read_one_byte_beyond_response_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, float]] = []
    reads: list[int] = []
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        _urlopen_returning(b'{"issuer":"https://issuer.example"}', calls, reads),
    )
    transport = GitHubOidcHttpsTransport(timeout=2.5)

    result = transport.get_metadata("https://issuer.example")

    assert result == {"issuer": "https://issuer.example"}
    assert calls == [
        (
            "https://issuer.example/.well-known/openid-configuration",
            2.5,
        )
    ]
    assert reads == [MAX_RESPONSE_BYTES + 1]


def test_oversized_response_is_rejected_before_json_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, float]] = []
    reads: list[int] = []
    body = b"{" + b"x" * MAX_RESPONSE_BYTES + b"}"
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        _urlopen_returning(body, calls, reads),
    )

    with pytest.raises(RuntimeError, match="response exceeds size limit"):
        GitHubOidcHttpsTransport().get_jwks("https://issuer.example/keys")


def test_https_request_rejects_non_https_redirect_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, float]] = []
    reads: list[int] = []
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        _urlopen_returning(b'{"keys":[]}', calls, reads, final_url="http://issuer.example/keys"),
    )

    with pytest.raises(RuntimeError, match="request failed"):
        GitHubOidcHttpsTransport().get_jwks("https://issuer.example/keys")

    assert reads == []


def test_malformed_or_non_object_json_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, float]] = []
    reads: list[int] = []
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        _urlopen_returning(b"not-json", calls, reads),
    )

    with pytest.raises(RuntimeError, match="malformed JSON"):
        GitHubOidcHttpsTransport().get_jwks("https://issuer.example/keys")

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        _urlopen_returning(json.dumps(["not", "an", "object"]).encode(), calls, reads),
    )
    with pytest.raises(RuntimeError, match="malformed JSON"):
        GitHubOidcHttpsTransport().get_jwks("https://issuer.example/keys")


def test_network_failures_are_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise urllib.error.URLError("token=do-not-leak at https://private.example")

    monkeypatch.setattr(urllib.request, "urlopen", fail)

    with pytest.raises(RuntimeError, match="request failed") as error:
        GitHubOidcHttpsTransport().get_jwks("https://issuer.example/keys")

    message = str(error.value)
    assert "do-not-leak" not in message
    assert "private.example" not in message
    formatted = "".join(traceback.format_exception(error.type, error.value, error.tb))
    assert "do-not-leak" not in formatted
    assert "private.example" not in formatted


def test_constructor_rejects_unbounded_timeout_configuration() -> None:
    for timeout in (0, float("nan"), float("inf"), float("-inf"), True):
        with pytest.raises(ValueError, match="timeout"):
            GitHubOidcHttpsTransport(timeout=timeout)

    for max_response_bytes in (0, 1.5, True):
        with pytest.raises(ValueError, match="response size"):
            GitHubOidcHttpsTransport(max_response_bytes=max_response_bytes)  # type: ignore[arg-type]

    assert DEFAULT_TIMEOUT_SECONDS > 0
