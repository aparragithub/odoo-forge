from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from odoo_forge.anonymization.policy import AnonymizationPolicy, AnonymizationRule


@dataclass(frozen=True)
class PolicyInputIssue:
    path: str
    correction: str


class AnonymizationPolicyInputError(ValueError):
    def __init__(self, issues: Sequence[PolicyInputIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__("; ".join(f"{i.path}: {i.correction}" for i in self.issues))


def parse_anonymization_policy_document(data: object) -> AnonymizationPolicy:
    if (
        not isinstance(data, Mapping)
        or type(data.get("version")) is not int
        or data.get("version") != 1
    ):
        raise AnonymizationPolicyInputError((PolicyInputIssue("version", "must be the integer 1"),))
    raw_rules = data.get("rules")
    if not isinstance(raw_rules, Sequence) or isinstance(raw_rules, (str, bytes)):
        raise AnonymizationPolicyInputError((PolicyInputIssue("rules", "must be a sequence"),))
    try:
        rules = tuple(AnonymizationRule.model_validate(raw) for raw in raw_rules)
        return AnonymizationPolicy(rules=rules)
    except ValidationError as exc:
        raise AnonymizationPolicyInputError(
            (PolicyInputIssue("rules", "check table, column, mask_strategy, and static_value"),)
        ) from exc
