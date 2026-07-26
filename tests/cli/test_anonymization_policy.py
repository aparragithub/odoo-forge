import json
from pathlib import Path

import pytest

from odoo_forge.anonymization.policy_input import AnonymizationPolicyInputError
from odoo_forge_cli.anonymization_policy import load_anonymization_policy


@pytest.mark.parametrize("suffix", [".yaml", ".YML", ".JSON"])
def test_loader_accepts_case_normalized_formats(tmp_path: Path, suffix: str) -> None:
    path = tmp_path / f"policy{suffix}"
    path.write_text(
        json.dumps(
            {"version": 1, "rules": [{"table": "x", "column": "y", "mask_strategy": "hash"}]}
        )
    )
    assert load_anonymization_policy(path).rules[0].column == "y"


def test_unsupported_suffix_does_not_read_or_decode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        Path, "read_text", lambda *_args, **_kwargs: pytest.fail("input was touched")
    )
    with pytest.raises(AnonymizationPolicyInputError):
        load_anonymization_policy(Path("policy.json.bak"))


@pytest.mark.parametrize(
    "suffix,text",
    [
        (".json", '{"version": 1, "rules": [], "rules": [{"table": "x"}]}'),
        (".yaml", "version: 1\nrules: []\nrules:\n  - table: x\n"),
    ],
)
def test_loader_rejects_duplicate_mapping_keys(tmp_path: Path, suffix: str, text: str) -> None:
    path = tmp_path / f"policy{suffix}"
    path.write_text(text)

    with pytest.raises(AnonymizationPolicyInputError, match="duplicate mapping key"):
        load_anonymization_policy(path)


@pytest.mark.parametrize(
    "suffix,text",
    [
        (".json", "{"),
        (".yaml", ""),
        (".yaml", None),
    ],
)
def test_loader_failures_are_typed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str, text: str | None
) -> None:
    path = tmp_path / f"policy{suffix}"
    if text is None:
        monkeypatch.setattr(
            Path, "read_text", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError())
        )
    else:
        path.write_text(text)
    with pytest.raises(AnonymizationPolicyInputError):
        load_anonymization_policy(path)
