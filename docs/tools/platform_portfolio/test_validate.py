"""Tests for the platform portfolio structural validator.

Self-contained doc-tooling test (not part of the product test suite). Run with:
    python -m unittest discover -s docs/tools/platform_portfolio -p 'test_*.py'

Runs against a minimal valid fixture and the live plan, and proves the
validator catches the defect classes that matter for portfolio integrity:
dangling references, unresolved transfer destinations, and dependency cycles.
"""

import contextlib
import copy
import io
import json
import os
import pathlib
import re
import subprocess
import tempfile
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
        self.assertEqual(acceptance["status"], "approved")
        self.assertEqual(acceptance["gaps"], [])
        self.assertEqual(acceptance["evidence"], ["S43", "S44", "S45", "S46"])

    def test_credential_readiness_pointers_are_catalogued_and_the_gate_is_approved(self):
        plan = json.loads(LIVE_PLAN.read_text(encoding="utf-8"))
        capability = next(item for item in plan["items"] if item["id"] == "CAP-CREDENTIALS")
        acceptance = next(
            item for item in capability["acceptance"] if item["id"] == "AC-CAP-CREDENTIALS-READY"
        )

        self.assertEqual(
            [plan["meta"]["evidence_catalog"][pointer] for pointer in acceptance["evidence"]],
            [
                "Engram #6647",
                "openspec/changes/archive/2026-07-11-CAP-CREDENTIALS/specs/credential-materialization/spec.md",
                "openspec/changes/archive/2026-07-11-CAP-CREDENTIALS/design.md",
                "tests/credentials/test_materialization.py",
            ],
        )
        self.assertEqual(acceptance["gaps"], [])

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

        approved = validate.evaluate_credential_readiness(plan)

        self.assertTrue(approved.is_ready)
        self.assertEqual(approved.missing_requirements, ())

        # Rolling the gate back to proposed/gapped must re-block readiness,
        # proving the explicit approval — not the documentary evidence, which is
        # unchanged here — is what advances AC-CAP-CREDENTIALS-READY.
        reverted = copy.deepcopy(plan)
        capability = next(item for item in reverted["items"] if item["id"] == "CAP-CREDENTIALS")
        acceptance = next(
            item for item in capability["acceptance"] if item["id"] == "AC-CAP-CREDENTIALS-READY"
        )
        acceptance["status"] = "proposed"
        acceptance["gaps"] = ["G0"]

        readiness = validate.evaluate_credential_readiness(reverted)

        self.assertFalse(readiness.is_ready)
        self.assertIn("AC-CAP-CREDENTIALS-READY approval", readiness.missing_requirements)

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


class TestRepositoryValidation(unittest.TestCase):
    def _repository(self):
        temporary = tempfile.TemporaryDirectory()
        root = pathlib.Path(temporary.name)
        evidence = (
            root
            / "openspec/changes/archive/2026-07-16-CHG-FIRST-DATABASE-ADAPTER/apply-progress.md"
        )
        evidence.parent.mkdir(parents=True)
        evidence.write_text("real Docker receipt\n", encoding="utf-8")
        for change in (
            "refresh-platform-roadmap-after-stabilization",
            "sp-data-environments",
        ):
            (root / "openspec/changes" / change).mkdir(parents=True)
        (root / "docs/specs/platform").mkdir(parents=True)
        (root / "docs/specs/2026-07-14-stabilization-roadmap.md").write_text(
            "# Current Stabilization Roadmap\n"
            "CHG-FIRST-DATABASE-ADAPTER is archived as superseded.\n"
            "Active: refresh-platform-roadmap-after-stabilization and "
            "sp-data-environments (blocked).\n",
            encoding="utf-8",
        )
        protected = root / "docs/specs/protected.md"
        protected.write_text("immutable\n", encoding="utf-8")
        (root / "docs/diagrams").mkdir()
        (root / "docs/diagrams/odoo-forge-current-implementation.mmd").write_text(
            "flowchart LR\n    database[Database lifecycle]\n", encoding="utf-8"
        )
        (root / "docs/diagrams/odoo-forge-current-implementation.mmd.svg").write_text(
            "<svg/>\n", encoding="utf-8"
        )
        (root / "docs/diagrams/render-current-implementation.sh").write_bytes(
            (REPO_ROOT / "docs/diagrams/render-current-implementation.sh").read_bytes()
        )
        (root / "docs/diagrams/render-current-implementation.sh").chmod(0o755)
        (root / "docs/diagrams/odoo-forge-current-implementation-guide.md").write_text(
            "# Guía actual\n", encoding="utf-8"
        )
        (root / "docs/specs/platform/platform-architecture.html").write_text(
            '<html lang="es" data-ownership="hand-authored" '
            'data-ownership-verified="true"><body><section data-state="current">'
            "Implementado hoy: adaptador PostgreSQL Docker.</section>"
            '<section data-state="target">Objetivo futuro.</section>'
            '<a href="../../diagrams/odoo-forge-current-implementation-guide.md">Guía actual</a>'
            "</body></html>",
            encoding="utf-8",
        )
        (
            root / "openspec/changes/refresh-platform-roadmap-after-stabilization/apply-progress.md"
        ).write_text(
            "# Apply Progress\n\n## Status: Apply Complete — Ready for sdd-verify\n",
            encoding="utf-8",
        )
        plan = json.loads(FIXTURE.read_text(encoding="utf-8"))
        plan["meta"].update(
            {
                "evidence_catalog": {
                    "S62": "openspec/changes/archive/2026-07-16-CHG-FIRST-DATABASE-ADAPTER/"
                    "apply-progress.md"
                },
                "protected_history_paths": ["docs/specs/protected.md"],
                "protected_history_sha256": {
                    "docs/specs/protected.md": validate.file_sha256(protected)
                },
            }
        )
        return temporary, root, plan

    def test_s62_requires_an_archived_existing_evidence_pointer(self):
        temporary, root, plan = self._repository()
        with temporary:
            self.assertEqual(validate.validate_evidence_claims(plan, root), [])
            plan["meta"]["evidence_catalog"]["S62"] = "missing.md"
            self.assertIn("missing-evidence", _codes(validate.validate_repository(root, plan)))

    def test_repository_validation_is_root_path_invariant(self):
        temporary, root, plan = self._repository()
        with temporary:
            relative = pathlib.Path(os.path.relpath(root, pathlib.Path.cwd()))
            self.assertEqual(
                _codes(validate.validate_repository(root, plan)),
                _codes(validate.validate_repository(relative, plan)),
            )

    def test_s62_rejects_parent_traversal_even_when_it_reaches_a_file(self):
        temporary, root, plan = self._repository()
        with temporary:
            (root / "outside.md").write_text("not archived evidence\n", encoding="utf-8")
            plan["meta"]["evidence_catalog"]["S62"] = "openspec/changes/archive/../../outside.md"
            self.assertIn("invalid-evidence-path", _codes(validate.validate_repository(root, plan)))

    def test_missing_changes_root_reports_inventory_instead_of_crashing(self):
        temporary, root, plan = self._repository()
        with temporary:
            import shutil

            shutil.rmtree(root / "openspec/changes")
            self.assertIn("active-inventory", _codes(validate.validate_repository(root, plan)))

    def test_parent_status_contract_is_pure_and_not_a_child_gate(self):
        canonical = "## Status: Apply Complete — Ready for sdd-verify\n"
        self.assertEqual(validate.validate_parent_apply_status(canonical), [])
        for text in (
            "## Status: Blocked\n",
            "## Status: Phase 3 Complete\n",
            "## Status: Apply Complete — Ready for sdd-verify\n## Status: Blocked\n",
            "## Evidence\n" + canonical,
        ):
            self.assertIn(
                "apply-progress-status", _codes(validate.validate_parent_apply_status(text))
            )
        temporary, root, plan = self._repository()
        with temporary:
            progress = (
                root
                / "openspec/changes"
                / "refresh-platform-roadmap-after-stabilization/apply-progress.md"
            )
            baseline = _codes(validate.validate_repository(root, plan))
            progress.write_text("## Status: Blocked\n", encoding="utf-8")
            self.assertEqual(_codes(validate.validate_repository(root, plan)), baseline)

    def test_slice_five_target_lists_thirteen_child_paths(self):
        active_progress = (
            REPO_ROOT
            / "openspec/changes"
            / "fix-roadmap-refresh-verification-closure/apply-progress.md"
        )
        if active_progress.exists():
            progress_path = active_progress
        else:
            archive_root = REPO_ROOT / "openspec/changes/archive"
            archived_progress = [
                path
                for path in archive_root.glob(
                    "*-fix-roadmap-refresh-verification-closure/apply-progress.md"
                )
                if re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}-fix-roadmap-refresh-verification-closure",
                    path.parent.name,
                )
            ]
            self.assertEqual(len(archived_progress), 1, archived_progress)
            progress_path = archived_progress[0]

        progress = progress_path.read_text()
        block = progress.split("### Intended Native Staged Target (13 paths)", 1)[1].split(
            "This is planning", 1
        )[0]
        paths = re.findall(r"`([^`]+)`", block)
        expected = {
            "docs/specs/platform/platform-architecture.html",
            "docs/tools/platform_portfolio/test_validate.py",
            "docs/tools/platform_portfolio/validate.py",
            "docs/diagrams/odoo-forge-current-implementation.mmd",
            "docs/diagrams/odoo-forge-current-implementation.mmd.svg",
            "openspec/changes/fix-roadmap-refresh-verification-closure/apply-progress.md",
            "openspec/changes/fix-roadmap-refresh-verification-closure/design.md",
            "openspec/changes/fix-roadmap-refresh-verification-closure/evidence/parent-verify-fail.md",
            "openspec/changes/fix-roadmap-refresh-verification-closure/evidence/parent-verify-fail.sha256",
            "openspec/changes/fix-roadmap-refresh-verification-closure/exploration.md",
            "openspec/changes/fix-roadmap-refresh-verification-closure/proposal.md",
            "openspec/changes/fix-roadmap-refresh-verification-closure/specs/platform-portfolio-documentation-integrity/spec.md",
            "openspec/changes/fix-roadmap-refresh-verification-closure/tasks.md",
        }
        self.assertEqual(set(paths), expected)
        self.assertNotEqual(
            set(re.findall(r"`([^`]+)`", block.replace("proposal.md", "exploration.md"))), expected
        )

    def test_isolated_staged_mermaid_cannot_be_masked_by_clean_bytes(self):
        clean_temporary, clean_root, _ = self._repository()
        staged_temporary, staged_root, _ = self._repository()
        with clean_temporary, staged_temporary:

            def renderer(_):
                return validate.RendererResult(0, "")

            self.assertNotIn(
                "stale-claim", _codes(validate.validate_documentation(clean_root, renderer))
            )
            (staged_root / "docs/diagrams/odoo-forge-current-implementation.mmd").write_text(
                "No Operational Adapter\n", encoding="utf-8"
            )
            self.assertIn(
                "stale-claim", _codes(validate.validate_documentation(staged_root, renderer))
            )

    def test_documentation_checks_require_current_target_labels_links_and_fresh_claims(self):
        temporary, root, plan = self._repository()
        with temporary:
            html = root / "docs/specs/platform/platform-architecture.html"
            html.write_text(
                '<html lang="en"><body>No Operational Adapter</body></html>', encoding="utf-8"
            )
            codes = _codes(validate.validate_repository(root, plan))
            self.assertTrue(
                {
                    "html-language",
                    "html-current-label",
                    "html-target-label",
                    "html-guide-link",
                    "stale-claim",
                }.issubset(codes)
            )

    def test_renderer_check_requires_a_pinned_fixed_argv_script_and_derived_svg(self):
        temporary, root, plan = self._repository()
        with temporary:
            renderer = root / "docs/diagrams/render-current-implementation.sh"
            renderer.write_text(
                "# @sha256:\nif false; then\n"
                '"$runtime" run --rm --input "$SOURCE" --output "$container_output"\n'
                "fi\nexit 0\n",
                encoding="utf-8",
            )
            (root / "docs/diagrams/odoo-forge-current-implementation.mmd.svg").unlink()
            self.assertIn("fixed-renderer", _codes(validate.validate_repository(root, plan)))
            self.assertIn(
                "missing-derived-output", _codes(validate.validate_repository(root, plan))
            )

    def test_invalid_renderer_is_rejected_before_execution(self):
        temporary, root, _ = self._repository()
        with temporary:
            renderer = root / "docs/diagrams/render-current-implementation.sh"
            renderer.write_text('"$runtime" run --rm "$@"\n', encoding="utf-8")
            called = False

            def run_renderer(_):
                nonlocal called
                called = True
                return validate.RendererResult(0, "")

            codes = _codes(validate.validate_documentation(root, run_renderer=run_renderer))
            self.assertIn("fixed-renderer", codes)
            self.assertFalse(called)

    def test_active_inventory_is_exact(self):
        temporary, root, plan = self._repository()
        with temporary:
            (root / "openspec/changes/unplanned-work").mkdir()
            self.assertIn("active-inventory", _codes(validate.validate_repository(root, plan)))

    def test_current_roadmap_rejects_stale_claims(self):
        temporary, root, plan = self._repository()
        with temporary:
            roadmap = root / "docs/specs/2026-07-14-stabilization-roadmap.md"
            roadmap.write_text("PR #64 is current; Unit 3 is next.\n", encoding="utf-8")
            self.assertIn("stale-roadmap", _codes(validate.validate_repository(root, plan)))

    def test_protected_history_hash_mismatch_is_critical(self):
        temporary, root, plan = self._repository()
        with temporary:
            (root / "docs/specs/protected.md").write_text("rewritten\n", encoding="utf-8")
            self.assertIn("protected-history", _codes(validate.validate_repository(root, plan)))

    def test_cli_exits_nonzero_for_critical_repository_violations(self):
        temporary, root, plan = self._repository()
        with temporary:
            plan_path = root / "docs/specs/platform/portfolio.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            plan["meta"]["evidence_catalog"]["S62"] = "missing.md"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(validate.main(["--root", str(root)]), 1)


if __name__ == "__main__":
    unittest.main()
