"""Bounded, injectable transport for GitHub OIDC metadata and JWKS."""

from __future__ import annotations

import json
import urllib.request
from typing import Protocol, cast, runtime_checkable
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
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if max_response_bytes <= 0:
            raise ValueError("response size limit must be greater than zero")
        self._timeout = timeout
        self._max_response_bytes = max_response_bytes

    def get_metadata(self, issuer: str) -> dict[str, object]:
        """Retrieve the standard OpenID configuration for an HTTPS issuer."""
        issuer = self._validate_https_url(issuer)
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
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                body = response.read(self._max_response_bytes + 1)
        except Exception as exc:
            raise RuntimeError("GitHub OIDC transport request failed") from exc
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
    def _validate_https_url(url: str) -> str:
        try:
            parsed = urlsplit(url)
        except ValueError as exc:
            raise ValueError("GitHub OIDC transport requires an HTTPS URL") from exc
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError("GitHub OIDC transport requires an HTTPS URL")
        return url


__all__ = ["GitHubOidcHttpsTransport", "GitHubOidcTransport"]
