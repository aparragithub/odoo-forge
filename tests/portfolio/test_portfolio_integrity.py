"""Assertions the existing validator (validate.py) genuinely lacks.

These five checks close the gap between what
`docs/tools/platform_portfolio/validate.py` verifies today and what the live
plan (`docs/specs/platform/portfolio.json`) must guarantee:

1. All-severity live cleanliness — the existing suite
   (`docs/tools/platform_portfolio/test_validate.py`) only asserts BLOCKER-free
   on the live plan, leaving ~9 CRITICAL checks dormant.
2. Hard-edge graph preservation, by explicit named set — a bare count would
   not name the offending edge on a silent deletion or hard->soft downgrade.
3. Status invariants — `proposed` items must carry an open gap and not claim
   delivery; `achieved` items must have no open gaps and a real
   `evidence_date` (the field is `null`, not absent, on proposed items).
4. Decision evidence integrity — every decision evidence ID must resolve in
   `meta.evidence_catalog`.
5. Decomposition input integrity — every decomposition input ID must resolve
   in the complete item/decomposition ID namespace.

Update workflow: a legitimate hard-edge change to `portfolio.json` MUST edit
`EXPECTED_HARD_EDGES` in the same PR. The failure message of
`test_hard_dependency_edges_are_preserved` names the exact tuple(s) to add or
remove.

Every new assertion here was proven RED first against an in-memory
`copy.deepcopy` mutation (never the live file) before being asserted GREEN
against `live_plan`. Expected literals are hand-written, never derived from
the file under test.
"""

from __future__ import annotations

import copy
from typing import Any

import validate

EXPECTED_HARD_EDGES: frozenset[tuple[str, str, str]] = frozenset(
    {
        ("G1", "CAP-MANIFEST", "CAP-PROJECT-CATALOG"),
        ("G2", "CAP-MANIFEST", "CAP-DEPLOYMENT-SPEC"),
        ("G3", "CAP-SOURCE", "CAP-PROJECT-CATALOG"),
        ("G4", "CAP-WORKSPACE", "SP-DEVELOPER-ONBOARDING"),
        ("G5", "CAP-LOCAL-BACKEND", "SP-DEVELOPER-ONBOARDING"),
        ("G6", "PORT-SOURCE-PROVIDER", "CAP-PROJECT-CATALOG"),
        ("G7", "ADAPTER-SOURCE-GIT", "CAP-SOURCE"),
        ("G8", "PORT-WORKSPACE-PROVIDER", "CAP-WORKSPACE"),
        ("G9", "ADAPTER-WORKSPACE-GIT", "CAP-WORKSPACE"),
        ("G10", "PORT-BACKEND-PROVIDER", "CAP-DEPLOYMENT-SPEC"),
        ("G11", "ADAPTER-BACKEND-DOCKER", "CAP-LOCAL-BACKEND"),
        ("G12", "PORT-IMAGE-REGISTRY", "CAP-IMAGE-REGISTRY"),
        ("G13", "ADAPTER-IMAGE-REGISTRY-GHCR", "CAP-IMAGE-REGISTRY"),
        ("G14", "CAP-IMAGE-REGISTRY", "INT-LOCAL-DIGEST-CONSUMPTION"),
        ("G15", "CAP-CREDENTIALS", "CHG-FIRST-DATABASE-ADAPTER"),
        ("G16", "CAP-DATA-ARTIFACTS", "CHG-FIRST-DATABASE-ADAPTER"),
        ("G17", "PORT-DATABASE-PROVIDER", "CHG-FIRST-DATABASE-ADAPTER"),
        ("G18", "CAP-CREDENTIALS", "CHG-FIRST-REMOTE-ADAPTER"),
        ("G19", "CAP-TENANCY", "CHG-FIRST-REMOTE-ADAPTER"),
        ("G20", "CAP-DEPLOYMENT-SPEC", "CHG-FIRST-REMOTE-ADAPTER"),
        ("G21", "PORT-BACKEND-PROVIDER", "CHG-FIRST-REMOTE-ADAPTER"),
        ("G22", "CAP-TENANCY", "CHG-FIRST-IDENTITY-ADAPTER"),
        ("G23", "PORT-IDENTITY", "CHG-FIRST-IDENTITY-ADAPTER"),
        ("G24", "CAP-CREDENTIALS", "CHG-FIRST-IDENTITY-ADAPTER"),
        ("G25", "PORT-PIPELINE", "CHG-FIRST-PIPELINE-ADAPTER"),
        ("G26", "CAP-DURABLE-OPERATIONS", "CHG-FIRST-PIPELINE-ADAPTER"),
        ("G27", "CAP-CREDENTIALS", "CHG-FIRST-PIPELINE-ADAPTER"),
        ("G28", "CAP-PROVIDER-CATALOG", "SP-CONTROL-PLANE-AUTHORITY"),
        ("G29", "CAP-TENANCY", "SP-CONTROL-PLANE-AUTHORITY"),
        ("G30", "CAP-CREDENTIALS", "SP-CONTROL-PLANE-AUTHORITY"),
        ("G31", "CAP-DURABLE-OPERATIONS", "SP-CONTROL-PLANE-AUTHORITY"),
        ("G32", "CAP-RESOURCE-OWNERSHIP", "SP-CONTROL-PLANE-AUTHORITY"),
        ("G33", "CHG-FIRST-DATABASE-ADAPTER", "INT-DATABASE-RUNTIME-CUTOVER"),
        ("G34", "INT-DATABASE-RUNTIME-CUTOVER", "WF-DATA-COPY"),
        ("G35", "CHG-FIRST-DATABASE-ADAPTER", "WF-DATA-COPY"),
        ("G36", "WF-DATA-COPY", "SP-DATA-ENVIRONMENTS"),
        ("G37", "CHG-FIRST-DATABASE-ADAPTER", "SP-DATA-ENVIRONMENTS"),
        ("G38", "CHG-FIRST-REMOTE-ADAPTER", "SP-REMOTE-DEPLOYMENT"),
        ("G39", "CHG-FIRST-IDENTITY-ADAPTER", "SP-PLATFORM-ACCESS"),
        ("G40", "CHG-FIRST-PIPELINE-ADAPTER", "SP-DELIVERY-AUTOMATION"),
        ("G41", "SP-CONTROL-PLANE-AUTHORITY", "SP-DATA-ENVIRONMENTS"),
        ("G42", "SP-CONTROL-PLANE-AUTHORITY", "SP-REMOTE-DEPLOYMENT"),
        ("G43", "SP-CONTROL-PLANE-AUTHORITY", "SP-PLATFORM-ACCESS"),
        ("G45", "SP-CONTROL-PLANE-AUTHORITY", "SP-ENVIRONMENT-REQUESTS"),
        ("G46", "SP-CONTROL-PLANE-AUTHORITY", "SP-OPERATIONS-UI"),
        ("G47", "SP-CONTROL-PLANE-AUTHORITY", "SP-RESOURCE-LIFECYCLE"),
        ("G48", "SP-DATA-ENVIRONMENTS", "SP-PRODUCTION-GOVERNANCE"),
        ("G49", "SP-REMOTE-DEPLOYMENT", "SP-PRODUCTION-GOVERNANCE"),
        ("G50", "SP-PLATFORM-ACCESS", "SP-PRODUCTION-GOVERNANCE"),
        ("G51", "WF-PRODUCTION-PROMOTION", "SP-PRODUCTION-GOVERNANCE"),
        ("G52", "SP-DATA-ENVIRONMENTS", "SP-DELIVERY-AUTOMATION"),
        ("G53", "SP-REMOTE-DEPLOYMENT", "SP-DELIVERY-AUTOMATION"),
        ("G54", "SP-PRODUCTION-GOVERNANCE", "SP-DELIVERY-AUTOMATION"),
        ("G55", "CAP-IMAGE-REGISTRY", "SP-DELIVERY-AUTOMATION"),
        ("G57", "CAP-PROJECT-CATALOG", "SP-DEVELOPER-ONBOARDING"),
        ("G58", "SP-DATA-ENVIRONMENTS", "WF-ENVIRONMENT-REQUEST"),
        ("G59", "SP-REMOTE-DEPLOYMENT", "WF-ENVIRONMENT-REQUEST"),
        ("G60", "SP-PLATFORM-ACCESS", "WF-ENVIRONMENT-REQUEST"),
        ("G61", "SP-PRODUCTION-GOVERNANCE", "WF-ENVIRONMENT-REQUEST"),
        ("G62", "WF-ENVIRONMENT-REQUEST", "SP-ENVIRONMENT-REQUESTS"),
        ("G63", "SP-DATA-ENVIRONMENTS", "SP-DATA-RECOVERY"),
        ("G64", "SP-PRODUCTION-GOVERNANCE", "SP-DATA-RECOVERY"),
        ("G65", "SP-PLATFORM-ACCESS", "SP-OPERATIONS-UI"),
        ("G68", "CAP-DURABLE-OPERATIONS", "WF-DATA-COPY"),
        ("G69", "CAP-DURABLE-OPERATIONS", "WF-PRODUCTION-PROMOTION"),
        ("G70", "CAP-DURABLE-OPERATIONS", "WF-ENVIRONMENT-REQUEST"),
        ("G71", "CAP-RESOURCE-OWNERSHIP", "SP-RESOURCE-LIFECYCLE"),
        ("G72", "CAP-RESOURCE-OWNERSHIP", "WF-ENVIRONMENT-REQUEST"),
        ("G73", "CAP-RESOURCE-OWNERSHIP", "WF-DATA-COPY"),
        ("G74", "CAP-TENANCY", "SP-REMOTE-DEPLOYMENT"),
        ("G75", "CAP-TENANCY", "SP-ENVIRONMENT-REQUESTS"),
        ("G76", "SP-CONTROL-PLANE-AUTHORITY", "CHG-OPS-UI-READONLY"),
    }
)

EXPECTED_ROUTE_DECOMPOSITIONS = frozenset(
    {
        "CHG-PORTFOLIO-VALIDATOR",
        "CHG-ADOPT-UI-ROUTE",
        "CHG-PROVIDER-CATALOG",
        "CHG-SP4A-INSTANCE-REGISTRY",
        "CHG-SP4B-REGISTRY-POSTGRES",
        "CHG-SP4C-CONTROL-PLANE-EDGE",
        "CHG-OPS-UI-READONLY",
    }
)
EXPECTED_ROUTE_DECISIONS = frozenset({"DEC-CP-STACK", "DEC-UI-PARTIAL", "DEC-UI-STACK"})


def _unresolved_decision_evidence(plan: dict[str, Any]) -> list[tuple[str, str]]:
    evidence_catalog = set(plan["meta"]["evidence_catalog"])
    return [
        (decision["id"], evidence_id)
        for decision in plan["decisions"]
        for evidence_id in decision.get("evidence", [])
        if evidence_id not in evidence_catalog
    ]


def _unresolved_decomposition_inputs(plan: dict[str, Any]) -> list[tuple[str, str]]:
    item_or_decomposition_ids = {item["id"] for item in plan["items"]} | {
        decomposition["id"] for decomposition in plan.get("decompositions", [])
    }
    return [
        (decomposition["id"], input_id)
        for decomposition in plan.get("decompositions", [])
        for input_id in decomposition.get("inputs", [])
        if input_id not in item_or_decomposition_ids
    ]


def test_live_plan_is_clean_at_every_severity_red_catches_bad_kind(
    live_plan: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(live_plan)
    mutated["items"][0]["kind"] = "not-a-real-kind"
    bad_id = mutated["items"][0]["id"]
    violations = [str(v) for v in validate.validate_plan(mutated)]
    assert violations != []
    assert any(bad_id in v and "not-a-real-kind" in v for v in violations)


def test_live_plan_is_clean_at_every_severity(live_plan: dict[str, Any]) -> None:
    assert [str(v) for v in validate.validate_plan(live_plan)] == []


def test_dangling_gap_reference_red_catches_bad_ac_gap(live_plan: dict[str, Any]) -> None:
    mutated = copy.deepcopy(live_plan)
    item = next(
        it
        for it in mutated["items"]
        for a in it.get("acceptance", []) or []
        if isinstance(a, dict) and a.get("gaps")
    )
    acceptance_entry = next(a for a in item["acceptance"] if isinstance(a, dict) and a.get("gaps"))
    acceptance_entry["gaps"] = ["G-NOPE"]
    violations = [str(v) for v in validate.validate_plan(mutated)]
    assert violations != []
    assert any("bad-ac-gap" in v and item["id"] in v and "G-NOPE" in v for v in violations)


def test_one_directional_alias_mapping_red_catches_alias_backref(
    live_plan: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(live_plan)
    alias_key, targets = next(iter(mutated["meta"]["historical_alias_map"].items()))
    target_id = targets[0]
    target_item = next(it for it in mutated["items"] if it["id"] == target_id)
    target_item["historical_aliases"] = [
        a for a in target_item.get("historical_aliases", []) if a != alias_key
    ]
    violations = [str(v) for v in validate.validate_plan(mutated)]
    assert violations != []
    assert any("alias-backref" in v and target_id in v and alias_key in v for v in violations)


def test_hard_dependency_edges_red_catches_deleted_edge(live_plan: dict[str, Any]) -> None:
    mutated = copy.deepcopy(live_plan)
    mutated["edges"] = [e for e in mutated["edges"] if e["id"] != "G46"]
    actual = {(e["id"], e["from"], e["to"]) for e in mutated["edges"] if e["type"] == "hard"}
    missing = sorted(EXPECTED_HARD_EDGES - actual)
    assert missing == [("G46", "SP-CONTROL-PLANE-AUTHORITY", "SP-OPERATIONS-UI")]


def test_hard_dependency_edges_red_catches_downgraded_edge(live_plan: dict[str, Any]) -> None:
    mutated = copy.deepcopy(live_plan)
    for edge in mutated["edges"]:
        if edge["id"] == "G65":
            edge["type"] = "soft"
    actual = {(e["id"], e["from"], e["to"]) for e in mutated["edges"] if e["type"] == "hard"}
    missing = sorted(EXPECTED_HARD_EDGES - actual)
    assert missing == [("G65", "SP-PLATFORM-ACCESS", "SP-OPERATIONS-UI")]


def test_hard_dependency_edges_are_preserved(live_plan: dict[str, Any]) -> None:
    actual = {(e["id"], e["from"], e["to"]) for e in live_plan["edges"] if e["type"] == "hard"}
    assert sorted(EXPECTED_HARD_EDGES - actual) == []  # removed or downgraded to soft
    assert sorted(actual - EXPECTED_HARD_EDGES) == []  # undeclared new hard edge


def test_operations_ui_route_has_exact_decompositions_and_decisions(
    live_plan: dict[str, Any],
) -> None:
    route_decompositions = {
        entry["id"]
        for entry in live_plan["decompositions"]
        if entry["id"].startswith("CHG-")
        and entry["id"] not in {"CHG-FIRST-DATABASE-ADAPTER", "CHG-FIRST-REMOTE-ADAPTER"}
        and entry["id"] != "CHG-FIRST-IDENTITY-ADAPTER"
    }
    route_decisions = {
        entry["id"] for entry in live_plan["decisions"] if "S83" in entry.get("evidence", [])
    }

    assert route_decompositions == EXPECTED_ROUTE_DECOMPOSITIONS
    assert route_decisions == EXPECTED_ROUTE_DECISIONS


def test_decision_evidence_integrity_red_catches_missing_catalog_entry(
    live_plan: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(live_plan)
    decision = next(entry for entry in mutated["decisions"] if entry["id"] == "DEC-CP-STACK")
    decision["evidence"] = ["S-MISSING"]

    assert _unresolved_decision_evidence(mutated) == [("DEC-CP-STACK", "S-MISSING")]


def test_all_decision_evidence_references_resolve(live_plan: dict[str, Any]) -> None:
    assert _unresolved_decision_evidence(live_plan) == []


def test_decomposition_input_integrity_red_catches_missing_namespace_entry(
    live_plan: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(live_plan)
    decomposition = next(
        entry for entry in mutated["decompositions"] if entry["id"] == "CHG-OPS-UI-READONLY"
    )
    decomposition["inputs"] = ["CHG-NOT-REAL"]

    assert _unresolved_decomposition_inputs(mutated) == [("CHG-OPS-UI-READONLY", "CHG-NOT-REAL")]


def test_all_decomposition_inputs_resolve_in_item_or_decomposition_namespace(
    live_plan: dict[str, Any],
) -> None:
    assert _unresolved_decomposition_inputs(live_plan) == []


def test_operations_ui_readonly_slice_has_exact_lineage_and_edge(
    live_plan: dict[str, Any],
) -> None:
    slice_item = next(item for item in live_plan["items"] if item["id"] == "CHG-OPS-UI-READONLY")
    hard_edges = [
        edge
        for edge in live_plan["edges"]
        if edge["from"] == slice_item["id"] or edge["to"] == slice_item["id"]
        if edge["type"] == "hard"
    ]

    assert slice_item["kind"] == "sdd_change"
    assert slice_item["predecessors"] == ["SP-OPERATIONS-UI"]
    assert [acceptance["id"] for acceptance in slice_item["acceptance"]] == [
        "AC-CHG-OPS-UI-READONLY-READY"
    ]
    assert len(hard_edges) == 1
    assert hard_edges[0]["id"] == "G76"
    assert hard_edges[0]["from"] == "SP-CONTROL-PLANE-AUTHORITY"
    assert hard_edges[0]["handoff_ids"] == ["AC-SP-CONTROL-PLANE-AUTHORITY-READY"]


def test_operations_ui_route_preserves_parent_governance(live_plan: dict[str, Any]) -> None:
    parent = next(item for item in live_plan["items"] if item["id"] == "SP-OPERATIONS-UI")
    parent_edges = {
        edge["id"]: (edge["from"], edge["to"], edge["type"], edge["handoff_ids"])
        for edge in live_plan["edges"]
        if edge["to"] == parent["id"] and edge["id"] in {"G46", "G65"}
    }

    assert parent["status"] == "proposed"
    assert parent_edges == {
        "G46": (
            "SP-CONTROL-PLANE-AUTHORITY",
            "SP-OPERATIONS-UI",
            "hard",
            ["AC-SP-CONTROL-PLANE-AUTHORITY-READY"],
        ),
        "G65": (
            "SP-PLATFORM-ACCESS",
            "SP-OPERATIONS-UI",
            "hard",
            ["AC-SP-PLATFORM-ACCESS-READY"],
        ),
    }


def test_status_invariants_red_catches_blanked_evidence_date(
    live_plan: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(live_plan)
    achieved_item = next(it for it in mutated["items"] if it.get("status") == "achieved")
    achieved_item["evidence_date"] = None
    violations = [str(v) for v in validate.validate_plan(mutated)]
    assert any(
        "status-achieved-no-evidence-date" in v and achieved_item["id"] in v for v in violations
    )


def test_status_invariants_red_catches_proposed_claiming_evidence_date(
    live_plan: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(live_plan)
    proposed_item = next(it for it in mutated["items"] if it.get("status") == "proposed")
    proposed_item["evidence_date"] = "2026-07-30"
    violations = [str(v) for v in validate.validate_plan(mutated)]
    assert any(
        "status-proposed-evidence-date" in v and proposed_item["id"] in v for v in violations
    )


def test_status_invariants_red_catches_emptied_proposed_gaps(
    live_plan: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(live_plan)
    proposed_item = next(it for it in mutated["items"] if it.get("status") == "proposed")
    for entry in proposed_item.get("acceptance", []) or []:
        if isinstance(entry, dict):
            entry["gaps"] = []
    violations = [str(v) for v in validate.validate_plan(mutated)]
    assert any("status-proposed-no-gap" in v and proposed_item["id"] in v for v in violations)


def test_status_invariants_red_catches_achieved_with_item_level_gap(
    live_plan: dict[str, Any],
) -> None:
    """An achieved item must not retain an open gap recorded on the item itself.

    The validator reads item-level gaps, so a check that inspected only
    acceptance gaps would let this through.
    """
    mutated = copy.deepcopy(live_plan)
    achieved_item = next(it for it in mutated["items"] if it.get("status") == "achieved")
    achieved_item["gaps"] = ["G0"]
    violations = [str(v) for v in validate.validate_plan(mutated)]
    assert any("status-achieved-open-gap" in v and achieved_item["id"] in v for v in violations)


def test_status_invariants_accept_proposed_with_only_item_level_gap(
    live_plan: dict[str, Any],
) -> None:
    """A proposed item whose only open gap is item-level is valid.

    Guards the opposite failure mode: a gate that rejects valid data is as
    harmful as one that admits invalid data.
    """
    mutated = copy.deepcopy(live_plan)
    proposed_item = next(it for it in mutated["items"] if it.get("status") == "proposed")
    for entry in proposed_item.get("acceptance", []) or []:
        if isinstance(entry, dict):
            entry["gaps"] = []
    proposed_item["gaps"] = ["G0"]
    violations = [str(v) for v in validate.validate_plan(mutated)]
    assert not any("status-" in v and proposed_item["id"] in v for v in violations)


def test_status_invariants_red_catches_unknown_status(live_plan: dict[str, Any]) -> None:
    mutated = copy.deepcopy(live_plan)
    item = mutated["items"][0]
    item["status"] = "not-a-real-status"
    violations = [str(v) for v in validate.validate_plan(mutated)]
    assert any(
        "status-unknown" in v and item["id"] in v and "not-a-real-status" in v for v in violations
    )


def test_status_invariants_accept_legal_governance_statuses(live_plan: dict[str, Any]) -> None:
    """`status-unknown` must not fire for any status the governance spec declares legal.

    openspec/specs/platform-subproject-governance/spec.md:31 declares six legal
    statuses. This change only implements invariants for `proposed` and
    `achieved`; the other four are legal but intentionally unchecked here
    (follow-up work), so they must not trip the catch-all.
    """
    mutated = copy.deepcopy(live_plan)
    item = mutated["items"][0]
    for status in ("validated", "active", "partially delivered", "superseded"):
        item["status"] = status
        violations = [str(v) for v in validate.validate_plan(mutated)]
        assert not any("status-unknown" in v and item["id"] in v for v in violations)


def test_status_invariants_hold(live_plan: dict[str, Any]) -> None:
    violations = [str(v) for v in validate.validate_plan(live_plan)]
    assert not any("status-" in v for v in violations)
