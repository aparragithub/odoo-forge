from __future__ import annotations

import inspect

import pytest

from odoo_forge.durable_operations.types import DurableOperationIdentity
from odoo_forge.ports.resource_ownership import ResourceOwnershipPort
from odoo_forge.resource_ownership import (
    OwnershipAttestation,
    OwnershipReceipt,
    OwnershipRecord,
    ResourceOwnership,
    ResourceRef,
    TenantAttribution,
)

_TRANSITION_VERBS = ("reserve", "bind", "activate", "retire", "adopt")


def _ref(ownership: ResourceOwnership = ResourceOwnership.CREATED) -> ResourceRef:
    return ResourceRef(identifier="database-42", resource_kind="database", ownership=ownership)


def _receipt(
    owned_ids: tuple[str, ...] = ("database-42",), live_proof_expected: bool = True
) -> OwnershipReceipt:
    return OwnershipReceipt(
        operation=DurableOperationIdentity(operation_id="provision-42", request_digest="digest-42"),
        owned_resource_ids=owned_ids,
        live_proof_expected=live_proof_expected,
    )


class _ConformingResourceOwnershipPort:
    """A read/attest-only fake adapter proving the contract without mutation."""

    def __init__(self) -> None:
        self.describe_calls = 0

    def describe_ownership(self, resource: ResourceRef) -> OwnershipRecord:
        self.describe_calls += 1
        attribution = (
            TenantAttribution(tenant_id="tenant-1")
            if resource.ownership is not ResourceOwnership.EXTERNAL
            else None
        )
        return OwnershipRecord(ref=resource, attribution=attribution)

    def attest_ownership(self, receipt: OwnershipReceipt) -> OwnershipAttestation:
        resource = _ref()
        owned = resource.identifier in receipt.owned_resource_ids
        live_proof_verified = owned and receipt.live_proof_expected
        return OwnershipAttestation(
            resource=resource,
            attested=owned and live_proof_verified,
            live_proof_verified=live_proof_verified,
        )


def test_port_is_a_runtime_checkable_protocol_satisfied_by_a_conforming_adapter() -> None:
    port = _ConformingResourceOwnershipPort()

    assert isinstance(port, ResourceOwnershipPort)


def test_describe_ownership_is_side_effect_free_and_returns_state_and_attribution() -> None:
    port = _ConformingResourceOwnershipPort()

    record = port.describe_ownership(_ref(ResourceOwnership.ADOPTED))

    assert port.describe_calls == 1
    assert record.ref.ownership is ResourceOwnership.ADOPTED
    assert record.attribution == TenantAttribution(tenant_id="tenant-1")


def test_describe_ownership_leaves_external_resources_tenant_unattributed() -> None:
    port = _ConformingResourceOwnershipPort()

    record = port.describe_ownership(_ref(ResourceOwnership.EXTERNAL))

    assert record.attribution is None


def test_attest_ownership_succeeds_for_an_owned_resource_with_live_proof() -> None:
    port = _ConformingResourceOwnershipPort()

    attestation = port.attest_ownership(_receipt())

    assert attestation.attested is True
    assert attestation.live_proof_verified is True


def test_attest_ownership_rejects_a_receipt_that_does_not_own_the_resource() -> None:
    port = _ConformingResourceOwnershipPort()

    attestation = port.attest_ownership(_receipt(owned_ids=("some-other-id",)))

    assert attestation.attested is False


def test_attest_ownership_rejects_a_receipt_missing_its_live_proof_expectation() -> None:
    port = _ConformingResourceOwnershipPort()

    attestation = port.attest_ownership(_receipt(live_proof_expected=False))

    assert attestation.attested is False
    assert attestation.live_proof_verified is False


def test_port_exposes_exactly_read_and_attest_semantics() -> None:
    expected = {
        "describe_ownership": ["self", "resource"],
        "attest_ownership": ["self", "receipt"],
    }

    for name, parameters in expected.items():
        signature = inspect.signature(getattr(ResourceOwnershipPort, name))
        assert list(signature.parameters) == parameters


@pytest.mark.parametrize("verb", _TRANSITION_VERBS)
def test_port_never_defines_a_transition_verb(verb: str) -> None:
    assert not hasattr(ResourceOwnershipPort, verb)


def test_nonconforming_adapter_missing_attest_ownership_is_rejected() -> None:
    class _MissingAttestOwnership:
        def describe_ownership(self, resource: ResourceRef) -> OwnershipRecord:
            return OwnershipRecord(ref=resource)

    assert not isinstance(_MissingAttestOwnership(), ResourceOwnershipPort)
