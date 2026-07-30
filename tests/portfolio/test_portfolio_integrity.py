"""Assertions the existing validator (validate.py) genuinely lacks.

These three checks close the gap between what
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
    }
)


def _status_invariant_offenders(plan: dict[str, Any]) -> list[str]:
    """Return one readable string per item whose status contradicts its
    acceptance gaps or evidence_date, or an empty list if none.
    """
    offenders: list[str] = []
    for item in plan["items"]:
        status = item.get("status")
        acceptance = item.get("acceptance", []) or []
        gap_lists = [a.get("gaps", []) for a in acceptance if isinstance(a, dict)]
        all_gaps_empty = all(not gaps for gaps in gap_lists) if gap_lists else True
        if status == "proposed":
            if all_gaps_empty:
                offenders.append(f"{item['id']}: proposed with no open acceptance gap")
            if item.get("evidence_date"):
                offenders.append(f"{item['id']}: proposed but claims an evidence_date")
        if status == "achieved":
            if not all_gaps_empty:
                offenders.append(f"{item['id']}: achieved but has open acceptance gaps")
            if not item.get("evidence_date"):
                offenders.append(f"{item['id']}: achieved but evidence_date is null")
    return offenders


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
    acceptance_entry = next(
        a for a in item["acceptance"] if isinstance(a, dict) and a.get("gaps")
    )
    acceptance_entry["gaps"] = ["G-NOPE"]
    violations = [str(v) for v in validate.validate_plan(mutated)]
    assert violations != []
    assert any("bad-ac-gap" in v and item["id"] in v and "G-NOPE" in v for v in violations)


def test_one_directional_alias_mapping_red_catches_alias_backref(
    live_plan: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(live_plan)
    alias_key, targets = next(
        iter(mutated["meta"]["historical_alias_map"].items())
    )
    target_id = targets[0]
    target_item = next(it for it in mutated["items"] if it["id"] == target_id)
    target_item["historical_aliases"] = [
        a for a in target_item.get("historical_aliases", []) if a != alias_key
    ]
    violations = [str(v) for v in validate.validate_plan(mutated)]
    assert violations != []
    assert any(
        "alias-backref" in v and target_id in v and alias_key in v for v in violations
    )


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


def test_status_invariants_red_catches_blanked_evidence_date(
    live_plan: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(live_plan)
    achieved_item = next(it for it in mutated["items"] if it.get("status") == "achieved")
    achieved_item["evidence_date"] = None
    offenders = _status_invariant_offenders(mutated)
    assert any(achieved_item["id"] in offender for offender in offenders)


def test_status_invariants_red_catches_proposed_claiming_evidence_date(
    live_plan: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(live_plan)
    proposed_item = next(it for it in mutated["items"] if it.get("status") == "proposed")
    proposed_item["evidence_date"] = "2026-07-30"
    offenders = _status_invariant_offenders(mutated)
    assert any(proposed_item["id"] in offender for offender in offenders)


def test_status_invariants_red_catches_emptied_proposed_gaps(
    live_plan: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(live_plan)
    proposed_item = next(it for it in mutated["items"] if it.get("status") == "proposed")
    for entry in proposed_item.get("acceptance", []) or []:
        if isinstance(entry, dict):
            entry["gaps"] = []
    offenders = _status_invariant_offenders(mutated)
    assert any(proposed_item["id"] in offender for offender in offenders)


def test_status_invariants_hold(live_plan: dict[str, Any]) -> None:
    assert _status_invariant_offenders(live_plan) == []
