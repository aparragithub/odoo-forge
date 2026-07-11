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
LIVE_PLAN = REPO_ROOT / "docs" / "specs" / "platform" / "portfolio.json"


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

    def test_credential_capability_records_sops_decision_and_readiness_pointers(self):
        plan = json.loads(LIVE_PLAN.read_text(encoding="utf-8"))
        decisions = {decision["id"]: decision for decision in plan["decisions"]}
        capability = next(item for item in plan["items"] if item["id"] == "CAP-CREDENTIALS")
        acceptance = next(
            item for item in capability["acceptance"] if item["id"] == "AC-CAP-CREDENTIALS-READY"
        )

        self.assertEqual(decisions["DPROV-SECRETS"]["status"], "decided")
        self.assertEqual(decisions["DPROV-SECRETS"]["chosen"], "SOPS")
        self.assertIn("S43", decisions["DPROV-SECRETS"]["evidence"])
        self.assertEqual(acceptance["status"], "proposed")
        self.assertEqual(acceptance["gaps"], ["G0"])
        self.assertEqual(acceptance["evidence"], ["S43", "S44", "S45", "S46"])

    def test_credential_readiness_pointers_are_catalogued_and_keep_the_gate_blocked(self):
        plan = json.loads(LIVE_PLAN.read_text(encoding="utf-8"))
        capability = next(item for item in plan["items"] if item["id"] == "CAP-CREDENTIALS")
        acceptance = next(
            item for item in capability["acceptance"] if item["id"] == "AC-CAP-CREDENTIALS-READY"
        )

        self.assertEqual(
            [plan["meta"]["evidence_catalog"][pointer] for pointer in acceptance["evidence"]],
            [
                "Engram #6647",
                "openspec/changes/CAP-CREDENTIALS/specs/credential-materialization/spec.md",
                "openspec/changes/CAP-CREDENTIALS/design.md",
                "tests/credentials/test_materialization.py",
            ],
        )
        self.assertIn("G0", acceptance["gaps"])

    def test_credential_readiness_blocks_a_missing_first_store_decision(self):
        plan = json.loads(LIVE_PLAN.read_text(encoding="utf-8"))
        plan["decisions"] = [
            decision for decision in plan["decisions"] if decision["id"] != "DPROV-SECRETS"
        ]

        readiness = validate.evaluate_credential_readiness(plan)

        self.assertFalse(readiness.is_ready)
        self.assertIn("DPROV-SECRETS approval", readiness.missing_requirements)

    def test_credential_readiness_requires_explicit_approval_after_complete_evidence(self):
        plan = json.loads(LIVE_PLAN.read_text(encoding="utf-8"))

        blocked = validate.evaluate_credential_readiness(plan)

        self.assertFalse(blocked.is_ready)
        self.assertIn("AC-CAP-CREDENTIALS-READY approval", blocked.missing_requirements)

        complete = copy.deepcopy(plan)
        capability = next(item for item in complete["items"] if item["id"] == "CAP-CREDENTIALS")
        acceptance = next(
            item for item in capability["acceptance"] if item["id"] == "AC-CAP-CREDENTIALS-READY"
        )
        acceptance["status"] = "approved"
        acceptance["gaps"] = []

        readiness = validate.evaluate_credential_readiness(complete)

        self.assertTrue(readiness.is_ready)
        self.assertEqual(readiness.missing_requirements, ())

    def test_detects_dangling_edge(self):
        broken = copy.deepcopy(self.valid)
        broken["edges"].append(
            {
                "id": "G1",
                "from": "SP-EXAMPLE",
                "to": "SP-DOES-NOT-EXIST",
                "type": "hard",
                "reason": "x",
                "handoff_ids": ["AC-EXAMPLE"],
                "evidence": ["S0"],
                "ownership_destination": "SP-DOES-NOT-EXIST",
            }
        )
        self.assertIn("edge-to", _codes(validate.validate_plan(broken)))

    def test_detects_unresolved_transfer_destination(self):
        broken = copy.deepcopy(self.valid)
        broken["transfers"].append(
            {
                "id": "X1",
                "origin": "SP-EXAMPLE",
                "dotted_scope": "example.scope",
                "destination": "NOPE",
                "evidence": ["S0"],
            }
        )
        self.assertIn("transfer-dest", _codes(validate.validate_plan(broken)))

    def test_detects_dependency_cycle(self):
        broken = copy.deepcopy(self.valid)
        broken["edges"].append(
            {
                "id": "G1",
                "from": "SP-EXAMPLE",
                "to": "SP-EXAMPLE",
                "type": "hard",
                "reason": "x",
                "handoff_ids": ["AC-EXAMPLE"],
                "evidence": ["S0"],
                "ownership_destination": "SP-EXAMPLE",
            }
        )
        self.assertIn("edge-cycle", _codes(validate.validate_plan(broken)))


if __name__ == "__main__":
    unittest.main()
