import base64
import json
import time
from collections.abc import Mapping

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from odoo_forge.identity.types import AuthenticationRequest, IdentityAssertion, SessionRef
from odoo_forge_identity_github import GitHubIdentityProvider

ISSUER = "https://token.actions.githubusercontent.com"
AUDIENCE = "platform-console"
JWKS_URI = f"{ISSUER}/.well-known/jwks"
REQUIRED_CLAIMS = ("repository", "ref")


class _Transport:
    def __init__(self, *, jwks: dict[str, object] | None = None) -> None:
        self.metadata: dict[str, object] = {"issuer": ISSUER, "jwks_uri": JWKS_URI}
        self.jwks = jwks or {"keys": []}
        self.failure: Exception | None = None

    def get_metadata(self, issuer: str) -> dict[str, object]:
        if self.failure is not None:
            raise self.failure
        return self.metadata

    def get_jwks(self, jwks_uri: str) -> dict[str, object]:
        if self.failure is not None:
            raise self.failure
        return self.jwks


@pytest.fixture()
def key_pair() -> tuple[rsa.RSAPrivateKey, dict[str, object]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_numbers = private_key.public_key().public_numbers()
    return private_key, {
        "kty": "RSA",
        "kid": "github-key",
        "use": "sig",
        "alg": "RS256",
        "n": _b64(public_numbers.n.to_bytes((public_numbers.n.bit_length() + 7) // 8, "big")),
        "e": _b64(public_numbers.e.to_bytes((public_numbers.e.bit_length() + 7) // 8, "big")),
    }


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _token(
    private_key: rsa.RSAPrivateKey,
    *,
    header: Mapping[str, object] | None = None,
    claims: Mapping[str, object] | None = None,
    signature_key: rsa.RSAPrivateKey | None = None,
    include_kid: bool = True,
    omit_claims: tuple[str, ...] = (),
) -> str:
    token_header = {"alg": "RS256", "typ": "JWT", **(header or {})}
    if include_kid and "kid" not in token_header:
        token_header["kid"] = "github-key"
    token_claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "repo:acme/widget:ref:refs/heads/main",
        "exp": int(time.time()) + 60,
        "repository": "acme/widget",
        "ref": "refs/heads/main",
        **(claims or {}),
    }
    for claim in omit_claims:
        token_claims.pop(claim, None)
    encoded_header = _b64(json.dumps(token_header, separators=(",", ":")).encode())
    encoded_claims = _b64(json.dumps(token_claims, separators=(",", ":")).encode())
    signing_input = f"{encoded_header}.{encoded_claims}".encode()
    signature = (signature_key or private_key).sign(
        signing_input, padding.PKCS1v15(), hashes.SHA256()
    )
    return f"{encoded_header}.{encoded_claims}.{_b64(signature)}"


def _provider(jwks: dict[str, object]) -> GitHubIdentityProvider:
    return GitHubIdentityProvider(
        transport=_Transport(jwks=jwks),
        issuer=ISSUER,
        required_claims=REQUIRED_CLAIMS,
    )


def _assertion(token: str) -> IdentityAssertion:
    provider = GitHubIdentityProvider(
        transport=_Transport(), issuer=ISSUER, required_claims=REQUIRED_CLAIMS
    )
    challenge = provider.begin(AuthenticationRequest(audience=AUDIENCE))
    return IdentityAssertion(challenge_id=challenge.challenge_id, value=token)


def test_valid_rs256_assertion_returns_neutral_principal(
    key_pair: tuple[rsa.RSAPrivateKey, dict[str, object]],
) -> None:
    private_key, jwk = key_pair
    provider = _provider({"keys": [jwk]})

    principal = provider.verify(_assertion(_token(private_key)))

    assert principal is not None
    assert principal.subject == "repo:acme/widget:ref:refs/heads/main"
    assert principal.claims == {"repository": "acme/widget", "ref": "refs/heads/main"}


def test_valid_assertion_excludes_unsupported_identity_mappings(
    key_pair: tuple[rsa.RSAPrivateKey, dict[str, object]],
) -> None:
    private_key, jwk = key_pair
    provider = _provider({"keys": [jwk]})
    unsupported_claims = {
        "tenant": "tenant-1",
        "role": "administrator",
        "account": "account-1",
        "project": "project-1",
    }

    principal = provider.verify(_assertion(_token(private_key, claims=unsupported_claims)))

    assert principal is not None
    assert principal.claims == {"repository": "acme/widget", "ref": "refs/heads/main"}
    assert set(unsupported_claims).isdisjoint(principal.claims)
    assert principal.session == SessionRef(reference="")
    assert principal.session.reference == ""
    assert set(principal.model_dump()) == {"subject", "claims", "session"}
    assert set(unsupported_claims).isdisjoint(principal.model_dump())


@pytest.mark.parametrize(
    ("claims", "omit_claims", "expected"),
    [
        ({"iss": "https://evil.example"}, (), "wrong issuer"),
        ({"aud": "another-audience"}, (), "wrong audience"),
        ({"sub": ""}, (), "empty subject"),
        ({"exp": int(time.time()) - 1}, (), "expired"),
        ({"exp": "not-a-number"}, (), "invalid expiry"),
        ({}, ("exp",), "missing expiry"),
        ({}, ("repository",), "missing required claim"),
        ({"repository": None}, (), "invalid required claim"),
        ({"ref": 42}, (), "non-string required claim"),
    ],
)
def test_invalid_claims_fail_closed_without_a_partial_principal(
    key_pair: tuple[rsa.RSAPrivateKey, dict[str, object]],
    claims: dict[str, object],
    omit_claims: tuple[str, ...],
    expected: str,
) -> None:
    private_key, jwk = key_pair
    provider = _provider({"keys": [jwk]})

    result = provider.verify(
        _assertion(_token(private_key, claims=claims, omit_claims=omit_claims))
    )

    assert result is None, expected


@pytest.mark.parametrize(
    "token",
    [
        "only-one-segment",
        "a.b.c.d",
        "%%% .eyJzdWIiOiJ4In0.signature".replace(" ", ""),
        "eyJhbGciOiJSUzI1NiJ9.not-json.signature",
    ],
)
def test_malformed_jose_is_rejected(
    key_pair: tuple[rsa.RSAPrivateKey, dict[str, object]], token: str
) -> None:
    _, jwk = key_pair

    assert _provider({"keys": [jwk]}).verify(_assertion(token)) is None


@pytest.mark.parametrize(
    "header",
    [
        {"alg": "HS256"},
        {"crit": ["b64"]},
        {"crit": "b64"},
        {"kid": ""},
    ],
)
def test_unsupported_algorithm_and_critical_headers_fail_closed(
    key_pair: tuple[rsa.RSAPrivateKey, dict[str, object]], header: dict[str, object]
) -> None:
    private_key, jwk = key_pair

    assert _provider({"keys": [jwk]}).verify(_assertion(_token(private_key, header=header))) is None


def test_unknown_kid_is_rejected(key_pair: tuple[rsa.RSAPrivateKey, dict[str, object]]) -> None:
    private_key, jwk = key_pair

    assert (
        _provider({"keys": [jwk]}).verify(
            _assertion(_token(private_key, header={"kid": "unknown-key"}))
        )
        is None
    )


def test_missing_kid_is_rejected(key_pair: tuple[rsa.RSAPrivateKey, dict[str, object]]) -> None:
    private_key, jwk = key_pair

    assert (
        _provider({"keys": [jwk]}).verify(_assertion(_token(private_key, include_kid=False)))
        is None
    )


@pytest.mark.parametrize(
    "jwk_patch",
    [
        {"kty": "EC"},
        {"use": "enc"},
        {"n": "not-base64"},
        {"e": "AA"},
        {"n": "", "e": "AQAB"},
    ],
)
def test_invalid_rsa_key_type_material_or_use_is_rejected(
    key_pair: tuple[rsa.RSAPrivateKey, dict[str, object]], jwk_patch: dict[str, object]
) -> None:
    private_key, jwk = key_pair
    invalid_jwk = {**jwk, **jwk_patch}

    assert _provider({"keys": [invalid_jwk]}).verify(_assertion(_token(private_key))) is None


def test_mismatched_signature_is_rejected(
    key_pair: tuple[rsa.RSAPrivateKey, dict[str, object]],
) -> None:
    private_key, jwk = key_pair
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    assert (
        _provider({"keys": [jwk]}).verify(_assertion(_token(private_key, signature_key=other_key)))
        is None
    )


def test_transport_failure_fails_closed_without_constructing_principal(
    key_pair: tuple[rsa.RSAPrivateKey, dict[str, object]],
) -> None:
    private_key, jwk = key_pair
    transport = _Transport(jwks={"keys": [jwk]})
    transport.failure = RuntimeError("network failure")
    provider = GitHubIdentityProvider(
        transport=transport, issuer=ISSUER, required_claims=REQUIRED_CLAIMS
    )

    assert provider.verify(_assertion(_token(private_key))) is None
