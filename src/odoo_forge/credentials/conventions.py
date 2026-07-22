"""Single source of truth for the conventional Enterprise source credential.

The Enterprise source is a fixed, system-provided repository: the user never
declares its URL or a credential in the manifest. The credential is resolved
by convention via this fixed `CredentialHandle`/`TargetContext` pair, looked
up through the existing SOPS+age materialization pipeline. No other module
may hardcode this string — always import from here.

The canonical/trusted Enterprise source URL itself (`ENTERPRISE_SOURCE_URL`)
also lives here: it is the single anchor for BOTH the manifest
`EnterpriseLayer.url` default AND the credential host allow-list. No other
module may hardcode it either — always import from here.
"""

from odoo_forge.credentials.types import CredentialHandle, TargetContext

ENTERPRISE_SOURCE_CREDENTIAL_HANDLE: CredentialHandle = CredentialHandle("enterprise/source-git")
ENTERPRISE_SOURCE_TARGET: TargetContext = TargetContext(kind="source", target_id="enterprise")
# Canonical/trusted Enterprise source URL — the anchor for both the manifest
# `EnterpriseLayer.url` default and the credential host allow-list seed.
ENTERPRISE_SOURCE_URL: str = "https://github.com/odoo/enterprise.git"

__all__ = [
    "ENTERPRISE_SOURCE_CREDENTIAL_HANDLE",
    "ENTERPRISE_SOURCE_TARGET",
    "ENTERPRISE_SOURCE_URL",
]
