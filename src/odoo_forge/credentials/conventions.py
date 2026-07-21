"""Single source of truth for the conventional Enterprise source credential.

The Enterprise source is a fixed, system-provided repository: the user never
declares its URL or a credential in the manifest. The credential is resolved
by convention via this fixed `CredentialHandle`/`TargetContext` pair, looked
up through the existing SOPS+age materialization pipeline. No other module
may hardcode this string — always import from here.
"""

from odoo_forge.credentials.types import CredentialHandle, TargetContext

ENTERPRISE_SOURCE_CREDENTIAL_HANDLE: CredentialHandle = CredentialHandle("enterprise/source-git")
ENTERPRISE_SOURCE_TARGET: TargetContext = TargetContext(kind="source", target_id="enterprise")

__all__ = [
    "ENTERPRISE_SOURCE_CREDENTIAL_HANDLE",
    "ENTERPRISE_SOURCE_TARGET",
]
