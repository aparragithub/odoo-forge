import json
from pathlib import Path

import yaml

from odoo_forge.anonymization.policy import AnonymizationPolicy
from odoo_forge.anonymization.policy_input import (
    AnonymizationPolicyInputError,
    PolicyInputIssue,
    parse_anonymization_policy_document,
)

_FORMATS = {".yaml", ".yml", ".json"}


def _unique_mapping(pairs: list[tuple[object, object]]) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key, value in pairs:
        if key in mapping:
            raise ValueError("duplicate mapping key")
        mapping[key] = value
    return mapping


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    lambda loader, node: _unique_mapping(loader.construct_pairs(node, deep=True)),
)


def load_anonymization_policy(path: Path) -> AnonymizationPolicy:
    suffix = path.suffix.casefold()
    if suffix not in _FORMATS:
        raise AnonymizationPolicyInputError(
            (PolicyInputIssue("file", "extension must be .yaml, .yml, or .json"),)
        )
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise AnonymizationPolicyInputError(
            (PolicyInputIssue("file", "could not be read"),)
        ) from exc
    try:
        decoded = (
            json.loads(text, object_pairs_hook=_unique_mapping)
            if suffix == ".json"
            else yaml.load(text, Loader=_UniqueKeyLoader)
        )
    except (json.JSONDecodeError, yaml.YAMLError, ValueError) as exc:
        correction = (
            "duplicate mapping key"
            if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError)
            else f"malformed {'JSON' if suffix == '.json' else 'YAML'}"
        )
        raise AnonymizationPolicyInputError((PolicyInputIssue("file", correction),)) from exc
    return parse_anonymization_policy_document(decoded)
