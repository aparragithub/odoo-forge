import pytest

from odoo_forge.identity.types import (
    AuthenticatedPrincipal,
    AuthenticationRequest,
    IdentityAssertion,
    SessionRef,
)
from odoo_forge.ports.identity_provider import IdentityProvider
from odoo_forge_identity_github import GitHubIdentityProvider

ISSUER = "https://token.actions.githubusercontent.com"
JWKS_URI = f"{ISSUER}/.well-known/jwks"


class _RecordingTransport:
    def __init__(self) -> None:
        self.metadata_requests: list[str] = []
        self.jwks_requests: list[str] = []
        self.metadata: dict[str, object] = {"issuer": ISSUER, "jwks_uri": JWKS_URI}
        self.jwks: dict[str, object] = {"keys": []}
        self.metadata_error: Exception | None = None
        self.jwks_error: Exception | None = None

    def get_metadata(self, issuer: str) -> dict[str, object]:
        self.metadata_requests.append(issuer)
        if self.metadata_error is not None:
            raise self.metadata_error
        return self.metadata

    def get_jwks(self, jwks_uri: str) -> dict[str, object]:
        self.jwks_requests.append(jwks_uri)
        if self.jwks_error is not None:
            raise self.jwks_error
        return self.jwks


def _provider(transport: _RecordingTransport | None = None) -> GitHubIdentityProvider:
    return GitHubIdentityProvider(
        transport=transport or _RecordingTransport(),
        issuer=ISSUER,
        required_claims=("repository", "ref"),
    )


def test_provider_satisfies_runtime_identity_port() -> None:
    assert isinstance(_provider(), IdentityProvider)


def test_begin_returns_a_non_empty_opaque_stateless_challenge_and_recovers_audience() -> None:
    provider = _provider()
    request = AuthenticationRequest(audience="platform-console")

    first = provider.begin(request)
    second = provider.begin(request)

    assert first.challenge_id
    assert first.payload
    assert first.challenge_id == first.payload
    assert first.challenge_id != request.audience
    assert request.audience not in first.payload
    assert first == second
    assert provider._recover_audience(first.challenge_id) == request.audience


def test_challenge_contains_only_audience_and_does_not_infer_mappings() -> None:
    provider = _provider()
    request = AuthenticationRequest(
        audience="platform-console",
        context={
            "tenant": "tenant-1",
            "project": "project-1",
            "role": "administrator",
            "session": "session-1",
            "provision": "true",
            "link": "account-1",
        },
    )

    challenge = provider.begin(request)

    assert provider._recover_audience(challenge.challenge_id) == request.audience
    assert provider.begin(AuthenticationRequest(audience=request.audience)).challenge_id == (
        challenge.challenge_id
    )


def test_verify_recovers_audience_uses_injected_transport_and_stops_before_jose() -> None:
    transport = _RecordingTransport()
    provider = _provider(transport)
    challenge = provider.begin(AuthenticationRequest(audience="platform-console"))

    result = provider.verify(
        IdentityAssertion(challenge_id=challenge.challenge_id, value="opaque-jose-artifact")
    )

    assert result is None
    assert transport.metadata_requests == [ISSUER]
    assert transport.jwks_requests == [JWKS_URI]


@pytest.mark.parametrize("failure", ["metadata", "jwks"])
def test_verify_fails_closed_on_transport_failure(failure: str) -> None:
    transport = _RecordingTransport()
    if failure == "metadata":
        transport.metadata_error = RuntimeError("network failure")
    else:
        transport.jwks_error = RuntimeError("network failure")
    provider = _provider(transport)
    challenge = provider.begin(AuthenticationRequest(audience="platform-console"))

    result = provider.verify(IdentityAssertion(challenge_id=challenge.challenge_id, value="token"))

    assert result is None


def test_verify_rejects_unusable_key_response_before_constructing_principal() -> None:
    transport = _RecordingTransport()
    transport.jwks = {"keys": "not-a-list"}
    provider = _provider(transport)
    challenge = provider.begin(AuthenticationRequest(audience="platform-console"))

    result = provider.verify(IdentityAssertion(challenge_id=challenge.challenge_id, value="token"))

    assert result is None
    assert transport.jwks_requests == [JWKS_URI]


def test_principal_translation_keeps_mandatory_session_ref_empty_and_neutral() -> None:
    principal = GitHubIdentityProvider._translate_principal(
        subject="github-subject",
        claims={"repository": "org/repo", "role": "member"},
    )

    assert isinstance(principal, AuthenticatedPrincipal)
    assert principal.subject == "github-subject"
    assert principal.claims == {"repository": "org/repo", "role": "member"}
    assert principal.session == SessionRef(reference="")
    assert set(principal.model_dump()) == {"subject", "claims", "session"}


def test_resolve_fails_closed_without_transport_or_session_mapping() -> None:
    transport = _RecordingTransport()
    provider = _provider(transport)

    with pytest.raises(NotImplementedError, match="session resolution"):
        provider.resolve(SessionRef(reference=""))

    assert transport.metadata_requests == []
    assert transport.jwks_requests == []


def test_malformed_challenge_is_rejected_before_transport_access() -> None:
    transport = _RecordingTransport()
    provider = _provider(transport)

    result = provider.verify(IdentityAssertion(challenge_id="not-a-challenge", value="token"))

    assert result is None
    assert transport.metadata_requests == []
    assert transport.jwks_requests == []
