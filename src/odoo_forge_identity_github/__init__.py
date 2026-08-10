"""GitHub identity adapter."""

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
    "GitHubOidcHttpsTransport",
    "GitHubOidcTransport",
    "create_github_oidc_https_transport",
]
