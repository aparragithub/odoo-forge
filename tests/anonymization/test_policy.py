import pytest
from pydantic import ValidationError

from odoo_forge.anonymization.policy import AnonymizationPolicy, AnonymizationRule, MaskStrategy


def test_mask_strategy_vocabulary_is_the_fixed_v1_set() -> None:
    assert {member.value for member in MaskStrategy} == {
        "redact",
        "hash",
        "nullify",
        "static_replace",
    }


def test_anonymization_rule_accepts_each_v1_strategy_for_a_table_column_selector() -> None:
    redact = AnonymizationRule(
        table="res_partner", column="email", mask_strategy=MaskStrategy.REDACT
    )
    hashed = AnonymizationRule(table="res_partner", column="phone", mask_strategy=MaskStrategy.HASH)
    nullified = AnonymizationRule(
        table="res_partner", column="vat", mask_strategy=MaskStrategy.NULLIFY
    )
    static = AnonymizationRule(
        table="res_partner",
        column="street",
        mask_strategy=MaskStrategy.STATIC_REPLACE,
        static_value="REDACTED",
    )

    assert redact.mask_strategy is MaskStrategy.REDACT
    assert hashed.mask_strategy is MaskStrategy.HASH
    assert nullified.mask_strategy is MaskStrategy.NULLIFY
    assert static.static_value == "REDACTED"


def test_static_replace_requires_a_static_value_other_strategies_forbid_it() -> None:
    with pytest.raises(ValidationError):
        AnonymizationRule(
            table="res_partner", column="street", mask_strategy=MaskStrategy.STATIC_REPLACE
        )
    with pytest.raises(ValidationError):
        AnonymizationRule(
            table="res_partner",
            column="email",
            mask_strategy=MaskStrategy.REDACT,
            static_value="unexpected",
        )


def test_anonymization_rule_rejects_unsafe_table_or_column_selectors() -> None:
    with pytest.raises(ValidationError):
        AnonymizationRule(
            table="res_partner; DROP TABLE x", column="email", mask_strategy=MaskStrategy.REDACT
        )
    with pytest.raises(ValidationError):
        AnonymizationRule(table="res_partner", column="", mask_strategy=MaskStrategy.REDACT)


def test_policy_rejects_duplicate_table_column_selectors() -> None:
    with pytest.raises(ValidationError):
        AnonymizationPolicy(
            rules=(
                AnonymizationRule(
                    table="res_partner", column="email", mask_strategy=MaskStrategy.REDACT
                ),
                AnonymizationRule(
                    table="res_partner", column="email", mask_strategy=MaskStrategy.HASH
                ),
            )
        )


def test_policy_rule_for_looks_up_by_table_and_column() -> None:
    rule = AnonymizationRule(table="res_partner", column="email", mask_strategy=MaskStrategy.HASH)
    policy = AnonymizationPolicy(rules=(rule,))

    assert policy.rule_for("res_partner", "email") is rule
    assert policy.rule_for("res_partner", "missing") is None


def test_policy_defaults_to_an_empty_ordered_collection() -> None:
    policy = AnonymizationPolicy()

    assert policy.rules == ()
