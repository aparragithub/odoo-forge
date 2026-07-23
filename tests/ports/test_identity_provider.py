import ast
import inspect

from odoo_forge import identity
from odoo_forge.identity import types as identity_types
from odoo_forge.ports import identity_provider
from odoo_forge.ports.identity_provider import IdentityProvider

_DENYLIST = (
    "github",
    "gitlab",
    "google",
    "oidc",
    "oauth",
    "openid",
    "saml",
    "sso",
    "jwt",
    "bearer",
    "password",
    "credential",
    "ldap",
    "mfa",
    "okta",
    "auth0",
    "keycloak",
    "cognito",
    "entra",
    "azuread",
)


class _FakeIdentityProvider:
    """Structural stand-in — not a real adapter, just satisfies the shape.

    Uses plain `object`-typed parameters rather than the real
    `AuthenticationRequest`/`IdentityAssertion`/`SessionRef` types, proving the
    port contract is satisfiable by `isinstance` without needing the real
    domain types (`runtime_checkable` verifies method NAMES only).
    """

    def begin(self, request: object) -> object:
        return "challenge"

    def verify(self, assertion: object) -> object:
        return "principal"

    def resolve(self, session: object) -> object:
        return "principal"


def test_conforming_class_satisfies_identity_provider_protocol() -> None:
    provider = _FakeIdentityProvider()

    assert isinstance(provider, IdentityProvider)


def test_non_conforming_class_does_not_satisfy_protocol() -> None:
    class _MissingResolve:
        """Conforms to every method except `resolve` — must fail `isinstance`."""

        def begin(self, request: object) -> object:
            return "challenge"

        def verify(self, assertion: object) -> object:
            return "principal"

    assert not isinstance(_MissingResolve(), IdentityProvider)


def test_begin_verify_happy_path_returns_neutral_shapes() -> None:
    from odoo_forge.identity.types import (
        AuthenticatedPrincipal,
        AuthenticationChallenge,
        AuthenticationRequest,
        IdentityAssertion,
        SessionRef,
    )

    class _NeutralProvider:
        def begin(self, request: AuthenticationRequest) -> AuthenticationChallenge:
            return AuthenticationChallenge(challenge_id="challenge-1", payload="opaque-blob")

        def verify(self, assertion: IdentityAssertion) -> AuthenticatedPrincipal:
            return AuthenticatedPrincipal(
                subject="external-subject-1",
                claims={"role": "member"},
                session=SessionRef(reference="session-ref-1"),
            )

        def resolve(self, session: SessionRef) -> AuthenticatedPrincipal:
            return AuthenticatedPrincipal(
                subject="external-subject-1",
                claims={"role": "member"},
                session=session,
            )

    provider: IdentityProvider = _NeutralProvider()
    request = AuthenticationRequest(audience="platform-console")

    challenge = provider.begin(request)
    assertion = IdentityAssertion(challenge_id=challenge.challenge_id, value="opaque-artifact")
    principal = provider.verify(assertion)

    assert isinstance(challenge, AuthenticationChallenge)
    assert isinstance(principal, AuthenticatedPrincipal)
    assert principal.subject == "external-subject-1"
    assert principal.claims == {"role": "member"}
    assert isinstance(principal.session, SessionRef)

    principal_vars = vars(principal)
    assert "password" not in principal_vars
    assert "secret" not in principal_vars
    assert "private_key" not in principal_vars


def test_resolve_round_trips_a_session_reference() -> None:
    from odoo_forge.identity.types import (
        AuthenticatedPrincipal,
        AuthenticationChallenge,
        AuthenticationRequest,
        IdentityAssertion,
        SessionRef,
    )

    class _NeutralProvider:
        def begin(self, request: AuthenticationRequest) -> AuthenticationChallenge:
            raise NotImplementedError

        def verify(self, assertion: IdentityAssertion) -> AuthenticatedPrincipal:
            raise NotImplementedError

        def resolve(self, session: SessionRef) -> AuthenticatedPrincipal:
            return AuthenticatedPrincipal(
                subject="external-subject-1",
                claims={"role": "member"},
                session=session,
            )

    provider: IdentityProvider = _NeutralProvider()
    session = SessionRef(reference="session-ref-1")

    resolved = provider.resolve(session)

    assert isinstance(resolved, AuthenticatedPrincipal)
    assert resolved.session == session
    assert resolved.subject == "external-subject-1"


def test_rejected_authentication_may_signal_distinctly_without_raising() -> None:
    from odoo_forge.identity.types import (
        AuthenticatedPrincipal,
        AuthenticationChallenge,
        AuthenticationRequest,
        IdentityAssertion,
        SessionRef,
    )

    class _RejectingProvider:
        def begin(self, request: AuthenticationRequest) -> AuthenticationChallenge:
            raise NotImplementedError

        def verify(self, assertion: IdentityAssertion) -> AuthenticatedPrincipal | None:
            if assertion.value == "invalid-artifact":
                return None
            raise NotImplementedError

        def resolve(self, session: SessionRef) -> AuthenticatedPrincipal:
            raise NotImplementedError

    provider = _RejectingProvider()
    assert isinstance(provider, IdentityProvider)
    assertion = IdentityAssertion(challenge_id="challenge-1", value="invalid-artifact")

    result = provider.verify(assertion)

    assert result is None


def test_identity_port_documents_neutral_verbs() -> None:
    begin_doc = IdentityProvider.begin.__doc__
    verify_doc = IdentityProvider.verify.__doc__
    resolve_doc = IdentityProvider.resolve.__doc__

    assert begin_doc is not None
    assert "challenge" in begin_doc.lower() or "attempt" in begin_doc.lower()
    assert verify_doc is not None
    assert "principal" in verify_doc.lower() or "claims" in verify_doc.lower()
    assert resolve_doc is not None
    assert "session" in resolve_doc.lower() or "principal" in resolve_doc.lower()


def test_idp_vendor_denylist_absent_from_public_surface() -> None:
    port_source = inspect.getsource(identity_provider).lower()
    types_source = inspect.getsource(identity_types).lower()

    for token in _DENYLIST:
        assert token not in port_source, f"denylisted token {token!r} found in identity_provider.py"
        assert token not in types_source, f"denylisted token {token!r} found in identity/types.py"


def test_no_adapter_import_in_identity_provider() -> None:
    tree = ast.parse(inspect.getsource(identity_provider))
    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)

    forbidden_fragments = ("adapter", "subprocess", "requests", "httpx")
    for fragment in forbidden_fragments:
        assert not any(fragment in module.lower() for module in imported_modules)

    assert identity.__name__ == "odoo_forge.identity"
