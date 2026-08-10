"""GitHub identity adapter."""

from odoo_forge_identity_github.provider import GitHubIdentityProvider
from odoo_forge_identity_github.transport import (
    BoundedHttpOpener,
    BoundedHttpResponse,
    GitHubOidcHttpsTransport,
    GitHubOidcTransport,
    create_github_oidc_https_transport,
)

__all__ = [
    "BoundedHttpOpener",
    "BoundedHttpResponse",
    "GitHubIdentityProvider",
    "GitHubOidcHttpsTransport",
    "GitHubOidcTransport",
    "create_github_oidc_https_transport",
]
