"""Tests for the platform portfolio structural validator.

Self-contained doc-tooling test (not part of the product test suite). Run with:
    python -m unittest discover -s docs/tools/platform_portfolio -p 'test_*.py'

Runs against a minimal valid fixture and the live plan, and proves the
validator catches the defect classes that matter for portfolio integrity:
dangling references, unresolved transfer destinations, and dependency cycles.
"""
import copy
import json
import pathlib
import unittest

import validate

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
FIXTURE = HERE / "fixtures" / "valid.json"
LIVE_PLAN = (
    REPO_ROOT / "openspec" / "changes" / "platform-subproject-redefinition"
    / "portfolio-plan.json"
)


def _codes(violations):
    return {v.code for v in violations}


class TestValidator(unittest.TestCase):
    def setUp(self):
        self.valid = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_valid_fixture_is_clean(self):
        self.assertEqual(validate.validate_plan(self.valid), [])

    def test_live_plan_has_no_blockers(self):
        plan = json.loads(LIVE_PLAN.read_text(encoding="utf-8"))
        blockers = [v for v in validate.validate_plan(plan) if v.severity == "BLOCKER"]
        self.assertEqual(blockers, [], [str(b) for b in blockers])

    def test_detects_dangling_edge(self):
        broken = copy.deepcopy(self.valid)
        broken["edges"].append({
            "id": "G1", "from": "SP-EXAMPLE", "to": "SP-DOES-NOT-EXIST",
            "type": "hard", "reason": "x", "handoff_ids": ["AC-EXAMPLE"],
            "evidence": ["S0"], "ownership_destination": "SP-DOES-NOT-EXIST",
        })
        self.assertIn("edge-to", _codes(validate.validate_plan(broken)))

    def test_detects_unresolved_transfer_destination(self):
        broken = copy.deepcopy(self.valid)
        broken["transfers"].append({
            "id": "X1", "origin": "SP-EXAMPLE", "dotted_scope": "example.scope",
            "destination": "NOPE", "evidence": ["S0"],
        })
        self.assertIn("transfer-dest", _codes(validate.validate_plan(broken)))

    def test_detects_dependency_cycle(self):
        broken = copy.deepcopy(self.valid)
        broken["edges"].append({
            "id": "G1", "from": "SP-EXAMPLE", "to": "SP-EXAMPLE",
            "type": "hard", "reason": "x", "handoff_ids": ["AC-EXAMPLE"],
            "evidence": ["S0"], "ownership_destination": "SP-EXAMPLE",
        })
        self.assertIn("edge-cycle", _codes(validate.validate_plan(broken)))


if __name__ == "__main__":
    unittest.main()
