"""Bounded, injectable transport for GitHub OIDC metadata and JWKS."""

from __future__ import annotations

import http.client
import json
import math
import urllib.request
from typing import IO, Protocol, cast, runtime_checkable
from urllib.parse import urlsplit

DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_RESPONSE_BYTES = 1_048_576
_OPENID_CONFIGURATION_PATH = "/.well-known/openid-configuration"
_JSON_HEADERS = {"Accept": "application/json"}


@runtime_checkable
class GitHubOidcTransport(Protocol):
    def get_metadata(self, issuer: str) -> dict[str, object]:
        """Retrieve the issuer's OpenID configuration."""
        ...

    def get_jwks(self, jwks_uri: str) -> dict[str, object]:
        """Retrieve the issuer's JSON Web Key Set."""
        ...


class GitHubOidcHttpsTransport:
    """Retrieve GitHub OIDC JSON documents using bounded HTTPS requests."""

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
    ) -> None:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ValueError("timeout must be a finite number greater than zero")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if isinstance(max_response_bytes, bool) or not isinstance(max_response_bytes, int):
            raise ValueError("response size limit must be a positive integer")
        if max_response_bytes <= 0:
            raise ValueError("response size limit must be greater than zero")
        self._timeout = timeout
        self._max_response_bytes = max_response_bytes
        self._opener = urllib.request.build_opener(_HttpsRedirectHandler())

    def get_metadata(self, issuer: str) -> dict[str, object]:
        """Retrieve the standard OpenID configuration for an HTTPS issuer."""
        issuer = self._validate_https_url(issuer, allow_query=False)
        return self._get_json(f"{issuer.rstrip('/')}{_OPENID_CONFIGURATION_PATH}")

    def get_jwks(self, jwks_uri: str) -> dict[str, object]:
        """Retrieve a JSON Web Key Set from an HTTPS URL."""
        return self._get_json(self._validate_https_url(jwks_uri))

    def _get_json(self, url: str) -> dict[str, object]:
        return self._decode_json(self._read_response(url))

    def _read_response(self, url: str) -> bytes:
        request = urllib.request.Request(
            url,
            method="GET",
            headers=_JSON_HEADERS,
        )
        try:
            with self._opener.open(request, timeout=self._timeout) as response:  # noqa: S310
                self._validate_https_url(response.geturl())
                body = response.read(self._max_response_bytes + 1)
        except Exception:
            raise RuntimeError("GitHub OIDC transport request failed") from None
        if not isinstance(body, bytes):
            raise RuntimeError("GitHub OIDC transport returned an invalid response")
        if len(body) > self._max_response_bytes:
            raise RuntimeError("GitHub OIDC transport response exceeds size limit")
        return body

    @staticmethod
    def _decode_json(body: bytes) -> dict[str, object]:
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError("GitHub OIDC transport returned malformed JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("GitHub OIDC transport returned malformed JSON")
        return cast(dict[str, object], payload)

    @staticmethod
    def _validate_https_url(url: str, *, allow_query: bool = True) -> str:
        try:
            parsed = urlsplit(url)
        except ValueError as exc:
            raise ValueError("GitHub OIDC transport requires an HTTPS URL") from exc
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or "#" in url
            or (not allow_query and "?" in url)
        ):
            raise ValueError("GitHub OIDC transport requires an HTTPS URL")
        return url


class _HttpsRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: http.client.HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        GitHubOidcHttpsTransport._validate_https_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


__all__ = ["GitHubOidcHttpsTransport", "GitHubOidcTransport"]
