import pytest

from odoo_forge.anonymization.policy import AnonymizationPolicy
from odoo_forge.anonymization.policy_input import (
    AnonymizationPolicyInputError,
    parse_anonymization_policy_document,
)

RULE = {"table": "res_partner", "column": "email", "mask_strategy": "hash"}


def test_v1_conversion_preserves_order_and_empty_policy() -> None:
    policy = parse_anonymization_policy_document(
        {"version": 1, "rules": [RULE, {**RULE, "column": "phone"}]}
    )
    assert [rule.column for rule in policy.rules] == ["email", "phone"]
    assert parse_anonymization_policy_document({"version": 1, "rules": []}) == AnonymizationPolicy()


def test_invalid_documents_fail_at_safe_paths() -> None:
    cases = [
        ({}, "version"),
        ({"version": 1, "rules": {}}, "rules"),
        ({"version": 1, "rules": [{**RULE, "mask_strategy": "wat"}]}, "rules"),
        ({"version": 1, "rules": [RULE, RULE]}, "rules"),
    ]
    for document, path in cases:
        with pytest.raises(AnonymizationPolicyInputError) as raised:
            parse_anonymization_policy_document(document)
        assert path in str(raised.value)


def test_invalid_static_value_does_not_leak_contents() -> None:
    secret = "credential-token-123"
    with pytest.raises(AnonymizationPolicyInputError) as raised:
        parse_anonymization_policy_document(
            {"version": 1, "rules": [{**RULE, "static_value": secret}]}
        )
    assert "static_value" in str(raised.value) and secret not in str(raised.value)
