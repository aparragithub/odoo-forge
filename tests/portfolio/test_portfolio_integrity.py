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
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
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
        "CHG-PORTFOLIO-AUTHORITY-PATH",
        "CHG-SP4B-VALIDATOR-GROUNDWORK",
    }
)
EXPECTED_ROUTE_DECISIONS = frozenset({"DEC-CP-STACK", "DEC-UI-PARTIAL", "DEC-UI-STACK"})

EXPECTED_DECISION_IDS = (
    "DEC-6375",
    "DP",
    "DT",
    "DD",
    "DO",
    "DR",
    "DG",
    "DPROV-DB",
    "DPROV-REMOTE",
    "DPROV-IDP",
    "DPROV-CI",
    "DPROV-SECRETS",
    "DEC-CP-STACK",
    "DEC-UI-PARTIAL",
    "DEC-UI-STACK",
)
EXPECTED_DECOMPOSITION_IDS = (
    "CHG-FIRST-DATABASE-ADAPTER",
    "CHG-FIRST-REMOTE-ADAPTER",
    "CHG-FIRST-IDENTITY-ADAPTER",
    "CHG-PORTFOLIO-VALIDATOR",
    "CHG-ADOPT-UI-ROUTE",
    "CHG-PROVIDER-CATALOG",
    "CHG-SP4A-INSTANCE-REGISTRY",
    "CHG-SP4B-REGISTRY-POSTGRES",
    "CHG-SP4C-CONTROL-PLANE-EDGE",
    "CHG-OPS-UI-READONLY",
    "CHG-PORTFOLIO-AUTHORITY-PATH",
    "CHG-SP4B-VALIDATOR-GROUNDWORK",
)

EXPECTED_UNRELATED_DECISION_DIGESTS = {
    "DEC-6375": "1ee353af1f63b33ed822ed81736f1edadbecf92dd08cfdee924b07bb3c855744",
    "DP": "fe1589cac9b6914e498a71faecd10aa94ed68791891eb7b8f2d3a307e3539b04",
    "DT": "0724dd358bfeb948c1855e6e9435bb59992750376209a9ae22e3f89ce9611261",
    "DD": "086e3c4b0fa8ed02d4d57dc186b893f2684592e57cc811e1f9ab84c593549747",
    "DO": "69c61fb1305b6eb4a46b41d974f55698b473836bd62cc33149bc2cb4f604f249",
    "DR": "4458b3eabd04077453943e1fb25f6bc412970578cde9c6cd1f8e6c6a76b5f674",
    "DG": "b753ec94fb680561761c7c1da4a0e1855b37fdfb81c71f88c36fb0858e641ea6",
    "DPROV-DB": "cfa0657b9aec400f48f5afa8eb7aacdb8f65c7cbe55108008cf7d3e6b29fb305",
    "DPROV-REMOTE": "60d6dc85d001eb8af22925fc264bf5fd6141b7b21d1313d91127f5f0097fe7eb",
    "DPROV-IDP": "cbcec2a9b59fb4aa41a79eb6122be20b12757aa3cf85701fe7a9b86a9d5d1ea4",
    "DPROV-CI": "2e1772210a60f0fdd203622455e72d2a55034e815db8210fe90f31cb3a4c1bb4",
    "DPROV-SECRETS": "51c04a52b07a0d765f90dc61d36ab0fac3f512b9d36715f2575c647d1040924c",
    "DEC-UI-PARTIAL": "22aa0c1dcb66050d79eac7b3a4c4d7ec2ab91ee8e1f924a7837948a50c72c4c2",
    "DEC-UI-STACK": "1e9c10d56d7db8ae7b302cbccaa570ca649e5c9f9abd2eff687376386ee7d6ed",
}
EXPECTED_UNRELATED_DECOMPOSITION_DIGESTS = {
    "CHG-FIRST-DATABASE-ADAPTER": (
        "05644f731e5a9c5f704a81164e258103e1848843da646f4b15c6e7474c16600c"
    ),
    "CHG-FIRST-REMOTE-ADAPTER": "49922f13209d39eedf107d1ae83b90b96c374e1afbf3e9809b84130dc94615b4",
    "CHG-FIRST-IDENTITY-ADAPTER": (
        "618e19319b384d1265ff03962b9d6789e9ce17b954bde6efdb4250822f4dde8b"
    ),
    "CHG-PORTFOLIO-VALIDATOR": "6805da24908487ba9e1e06dd73e9157a19b530ef1459c139ebb91199480cbe4d",
    "CHG-ADOPT-UI-ROUTE": "f1a4b74c77c8d8b0bb0e826f021558ee155f6d52f06c954af40de0274e8e2ade",
    "CHG-PROVIDER-CATALOG": "7f24c7988304c63d4e296afc25352591f14ed9186854f8901bbec69469737cfe",
    "CHG-SP4A-INSTANCE-REGISTRY": (
        "2718487ba90aa4a2dd8f201a97abeb035c9d115b72f5530446eb5d56d4c8b038"
    ),
    "CHG-OPS-UI-READONLY": "517e074c836c24bf1c4ec00ab9f8e7bc1765827688b662ac5bfd5b43b05847a9",
}

EXPECTED_SP4_CONTRACTS = {
    "CHG-SP4B-REGISTRY-POSTGRES": {
        "dependencies": ["CHG-SP4A-INSTANCE-REGISTRY"],
        "immediate_parent": "CHG-SP4A-INSTANCE-REGISTRY",
        "outputs": [
            "src/odoo_forge_instances_postgres/",
            "tests/odoo_forge_instances_postgres/",
        ],
        "changed_line_forecast": {
            "files": [
                {
                    "additions": 200,
                    "deletions": 0,
                    "path": "src/odoo_forge_instances_postgres/",
                    "total": 200,
                },
                {
                    "additions": 150,
                    "deletions": 0,
                    "path": "tests/odoo_forge_instances_postgres/",
                    "total": 150,
                },
            ],
            "hard_gate": 400,
            "total": 350,
        },
    },
    "CHG-SP4C-CONTROL-PLANE-EDGE": {
        "dependencies": [
            "CHG-PROVIDER-CATALOG",
            "CHG-SP4B-REGISTRY-POSTGRES",
        ],
        "immediate_parent": "CHG-SP4B-REGISTRY-POSTGRES",
        "outputs": ["src/odoo_forge_server/", "tests/odoo_forge_server/"],
        "changed_line_forecast": {
            "files": [
                {
                    "additions": 220,
                    "deletions": 0,
                    "path": "src/odoo_forge_server/",
                    "total": 220,
                },
                {
                    "additions": 160,
                    "deletions": 0,
                    "path": "tests/odoo_forge_server/",
                    "total": 160,
                },
            ],
            "hard_gate": 400,
            "total": 380,
        },
    },
}


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


def _canonical_record_digest(record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(payload).hexdigest()


def _dec_cp_stack_governance_errors(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    decisions = {entry["id"]: entry for entry in plan["decisions"]}
    decompositions = {entry["id"]: entry for entry in plan["decompositions"]}

    decision = decisions.get("DEC-CP-STACK")
    if decision is None:
        errors.append("dec-cp-stack-missing")
    else:
        expected_decision = {
            "status": "decided",
            "chosen": "FastAPI + psycopg",
            "decided_date": "2026-07-30",
            "rationale": (
                "FastAPI best matches the typed Pydantic control-plane API, while psycopg is "
                "the shared PostgreSQL driver and Docker aligns with the repository's existing "
                "adapter/runtime investment."
            ),
            "consequence": (
                "Initial production uses Docker Compose on one server; core domain, ports, and "
                "adapters remain framework-neutral to preserve a no-rewrite scaling path; "
                "psycopg pools are per worker and must be bounded against PostgreSQL capacity; "
                "Jinja2 is an explicit dependency only for a later SSR slice; this decision "
                "records architecture and does not implement or deliver the control plane."
            ),
            "evidence": ["S83", "S84", "S85"],
        }
        for field, expected_value in expected_decision.items():
            if decision.get(field) != expected_value:
                error_name = {
                    "status": "dec-cp-stack-status",
                    "chosen": "dec-cp-stack-chosen",
                    "decided_date": "dec-cp-stack-date",
                    "rationale": "dec-cp-stack-rationale",
                    "consequence": "dec-cp-stack-consequence",
                    "evidence": "dec-cp-stack-evidence",
                }[field]
                errors.append(error_name)

        evidence_catalog = plan["meta"].get("evidence_catalog", {})
        for evidence_id in decision.get("evidence", []):
            if evidence_id not in evidence_catalog:
                errors.append(f"dec-cp-stack-evidence-unresolved:{evidence_id}")

        delivery_markers = ("implemented", "delivered", "deployed", "production-ready")
        decision_text = " ".join(
            str(decision.get(field, "")) for field in ("status", "rationale", "consequence")
        ).lower()
        if decision.get("status") in {"implemented", "delivered", "deployed"} or any(
            marker in decision_text for marker in delivery_markers
        ):
            errors.append("dec-cp-stack-delivery-claim")

    for decomposition_id, contract in EXPECTED_SP4_CONTRACTS.items():
        decomposition = decompositions.get(decomposition_id)
        label = "chg-sp4b" if decomposition_id.endswith("SP4B-REGISTRY-POSTGRES") else "chg-sp4c"
        if decomposition is None:
            errors.append(f"{label}-missing")
            continue
        if decomposition.get("blocking_decision_ids") != []:
            errors.append(f"{label}-blocker")
        if decomposition.get("type") != "implementation_change":
            errors.append(f"{label}-type")
        if decomposition.get("status") != "ready_for_proposal":
            errors.append(f"{label}-status")
        for field in ("dependencies", "immediate_parent", "outputs", "changed_line_forecast"):
            if decomposition.get(field) != contract[field]:
                field_name = field.replace("immediate_parent", "parent").replace(
                    "changed_line_forecast", "forecast"
                )
                errors.append(f"{label}-{field_name}")

    decomposition_order = tuple(entry["id"] for entry in plan["decompositions"])
    if decomposition_order != EXPECTED_DECOMPOSITION_IDS:
        errors.append("decomposition-id-order")
    if (
        "CHG-SP4B-REGISTRY-POSTGRES" in decomposition_order
        and "CHG-SP4C-CONTROL-PLANE-EDGE" in decomposition_order
        and decomposition_order.index("CHG-SP4B-REGISTRY-POSTGRES")
        > decomposition_order.index("CHG-SP4C-CONTROL-PLANE-EDGE")
    ):
        errors.append("chg-sp4b-sp4c-order")

    if tuple(entry["id"] for entry in plan["decisions"]) != EXPECTED_DECISION_IDS:
        errors.append("decision-id-order")

    for record_id, expected_digest in EXPECTED_UNRELATED_DECISION_DIGESTS.items():
        record = decisions.get(record_id)
        if record is None:
            errors.append(f"unrelated-decision-missing:{record_id}")
        elif _canonical_record_digest(record) != expected_digest:
            errors.append(f"unrelated-decision-drift:{record_id}")

    for record_id, expected_digest in EXPECTED_UNRELATED_DECOMPOSITION_DIGESTS.items():
        record = decompositions.get(record_id)
        if record is None:
            errors.append(f"unrelated-decomposition-missing:{record_id}")
        elif _canonical_record_digest(record) != expected_digest:
            errors.append(f"unrelated-decomposition-drift:{record_id}")

    return errors


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


def test_dec_cp_stack_rejects_wrong_chosen_value(live_plan: dict[str, Any]) -> None:
    mutated = copy.deepcopy(live_plan)
    decision = next(entry for entry in mutated["decisions"] if entry["id"] == "DEC-CP-STACK")
    decision["chosen"] = "Flask + psycopg"

    assert "dec-cp-stack-chosen" in _dec_cp_stack_governance_errors(mutated)


def test_dec_cp_stack_rejects_missing_evidence_reference(live_plan: dict[str, Any]) -> None:
    mutated = copy.deepcopy(live_plan)
    decision = next(entry for entry in mutated["decisions"] if entry["id"] == "DEC-CP-STACK")
    decision["evidence"] = ["S83", "S85"]

    assert "dec-cp-stack-evidence" in _dec_cp_stack_governance_errors(mutated)


def test_dec_cp_stack_rejects_dangling_evidence_catalog_entry(live_plan: dict[str, Any]) -> None:
    mutated = copy.deepcopy(live_plan)
    decision = next(entry for entry in mutated["decisions"] if entry["id"] == "DEC-CP-STACK")
    decision["evidence"] = ["S83", "S84", "S85"]
    mutated["meta"]["evidence_catalog"].update({"S84": "Engram #3727", "S85": "Engram #3734"})
    mutated["meta"]["evidence_catalog"].pop("S85")

    assert "dec-cp-stack-evidence-unresolved:S85" in _dec_cp_stack_governance_errors(mutated)


def test_dec_cp_stack_rejects_wrong_date_rationale_and_consequence(
    live_plan: dict[str, Any],
) -> None:
    mutations = (
        ("decided_date", "2026-07-31", "dec-cp-stack-date"),
        ("rationale", "A different rationale", "dec-cp-stack-rationale"),
        ("consequence", "The control plane is already delivered.", "dec-cp-stack-consequence"),
    )

    for field, value, error_name in mutations:
        mutated = copy.deepcopy(live_plan)
        decision = next(entry for entry in mutated["decisions"] if entry["id"] == "DEC-CP-STACK")
        decision[field] = value

        assert error_name in _dec_cp_stack_governance_errors(mutated)


def test_dec_cp_stack_rejects_accidental_delivery_claim(live_plan: dict[str, Any]) -> None:
    mutated = copy.deepcopy(live_plan)
    decision = next(entry for entry in mutated["decisions"] if entry["id"] == "DEC-CP-STACK")
    decision["status"] = "delivered"

    assert "dec-cp-stack-delivery-claim" in _dec_cp_stack_governance_errors(mutated)


def test_dec_cp_stack_rejects_stale_blocker_type_and_status(live_plan: dict[str, Any]) -> None:
    for field, value, error_name in (
        ("blocking_decision_ids", ["DEC-CP-STACK"], "chg-sp4b-blocker"),
        ("type", "blocked_product_placeholder", "chg-sp4b-type"),
        ("status", "blocked_placeholder", "chg-sp4b-status"),
    ):
        mutated = copy.deepcopy(live_plan)
        decomposition = next(
            entry
            for entry in mutated["decompositions"]
            if entry["id"] == "CHG-SP4B-REGISTRY-POSTGRES"
        )
        decomposition[field] = value

        assert error_name in _dec_cp_stack_governance_errors(mutated)


def test_dec_cp_stack_rejects_changed_dependency_parent_output_and_forecast(
    live_plan: dict[str, Any],
) -> None:
    mutations = (
        ("dependencies", ["CHG-PROVIDER-CATALOG"], "chg-sp4b-dependencies"),
        ("immediate_parent", "CHG-PROVIDER-CATALOG", "chg-sp4b-parent"),
        ("outputs", ["src/changed/"], "chg-sp4b-outputs"),
        (
            "changed_line_forecast",
            {"files": [], "hard_gate": 400, "total": 0},
            "chg-sp4b-forecast",
        ),
    )

    for field, value, error_name in mutations:
        mutated = copy.deepcopy(live_plan)
        decomposition = next(
            entry
            for entry in mutated["decompositions"]
            if entry["id"] == "CHG-SP4B-REGISTRY-POSTGRES"
        )
        decomposition[field] = value

        assert error_name in _dec_cp_stack_governance_errors(mutated)


def test_dec_cp_stack_rejects_changed_chg3_chg4_order(live_plan: dict[str, Any]) -> None:
    mutated = copy.deepcopy(live_plan)
    decompositions = mutated["decompositions"]
    chg3 = next(entry for entry in decompositions if entry["id"] == "CHG-SP4B-REGISTRY-POSTGRES")
    chg4 = next(entry for entry in decompositions if entry["id"] == "CHG-SP4C-CONTROL-PLANE-EDGE")
    chg3_index = decompositions.index(chg3)
    chg4_index = decompositions.index(chg4)
    decompositions[chg3_index], decompositions[chg4_index] = (
        decompositions[chg4_index],
        decompositions[chg3_index],
    )

    assert "chg-sp4b-sp4c-order" in _dec_cp_stack_governance_errors(mutated)


def test_dec_cp_stack_names_missing_ordered_decompositions(live_plan: dict[str, Any]) -> None:
    for decomposition_id, error_name in (
        ("CHG-SP4B-REGISTRY-POSTGRES", "chg-sp4b-missing"),
        ("CHG-SP4C-CONTROL-PLANE-EDGE", "chg-sp4c-missing"),
    ):
        mutated = copy.deepcopy(live_plan)
        mutated["decompositions"] = [
            entry for entry in mutated["decompositions"] if entry["id"] != decomposition_id
        ]

        assert error_name in _dec_cp_stack_governance_errors(mutated)


def test_dec_cp_stack_rejects_unrelated_decision_drift(live_plan: dict[str, Any]) -> None:
    mutated = copy.deepcopy(live_plan)
    decision = next(entry for entry in mutated["decisions"] if entry["id"] == "DP")
    decision["rationale"] = "A meaningful unrelated rationale mutation."

    assert "unrelated-decision-drift:DP" in _dec_cp_stack_governance_errors(mutated)


def test_dec_cp_stack_rejects_unrelated_decomposition_drift(live_plan: dict[str, Any]) -> None:
    mutated = copy.deepcopy(live_plan)
    decomposition = next(
        entry for entry in mutated["decompositions"] if entry["id"] == "CHG-SP4A-INSTANCE-REGISTRY"
    )
    decomposition["outputs"] = ["src/changed/instance_registry/"]

    assert (
        "unrelated-decomposition-drift:CHG-SP4A-INSTANCE-REGISTRY"
        in _dec_cp_stack_governance_errors(mutated)
    )


def test_dec_cp_stack_governance_contract_holds(live_plan: dict[str, Any]) -> None:
    assert _dec_cp_stack_governance_errors(live_plan) == []


def test_dec_cp_stack_preserves_existing_decision_identity_and_gate(
    live_plan: dict[str, Any],
) -> None:
    decision = next(entry for entry in live_plan["decisions"] if entry["id"] == "DEC-CP-STACK")

    assert {
        key: decision[key] for key in ("id", "owner", "due_gate", "blocking_effect", "options")
    } == {
        "id": "DEC-CP-STACK",
        "owner": "Architecture",
        "due_gate": "before CHG-SP4B-REGISTRY-POSTGRES",
        "blocking_effect": "Blocks the registry persistence and control-plane edge changes",
        "options": ["FastAPI + psycopg", "Flask + psycopg", "Starlette + psycopg"],
    }


def test_dec_cp_stack_catalogues_signed_engram_evidence(live_plan: dict[str, Any]) -> None:
    assert live_plan["meta"]["evidence_catalog"]["S84"] == "Engram #3727"
    assert live_plan["meta"]["evidence_catalog"]["S85"] == "Engram #3734"


def _stale_authority_offenders(specs_root: Path) -> list[str]:
    """Return authoritative spec files still referencing the stale plan path.

    Boundary is exactly `openspec/specs/**/spec.md` (#3816): the root is a
    parameter and callers keep passing the real repository root, so this
    hardening never widens the scan to tool source.

    `Path.glob` on a missing directory yields an empty iterator without
    raising, which let the guard below pass vacuously if the tree was ever
    renamed or moved. Fail loudly instead.
    """
    if not specs_root.is_dir():
        raise FileNotFoundError(f"authoritative spec root is missing: {specs_root}")
    return sorted(
        str(path.relative_to(specs_root.parents[1]))
        for path in specs_root.glob("**/spec.md")
        if "portfolio-plan.json" in path.read_text(encoding="utf-8")
    )


def test_no_stale_authority_path_in_authoritative_specs(live_plan: dict[str, Any]) -> None:
    specs_root = Path(__file__).resolve().parents[2] / "openspec" / "specs"
    offenders = _stale_authority_offenders(specs_root)
    assert offenders == [], (
        f"stale authority path 'portfolio-plan.json' found in: {offenders}; "
        f"the live authority is {live_plan['meta']['live_location']}"
    )


def test_stale_authority_offenders_raises_on_missing_specs_root(tmp_path: Path) -> None:
    absent = tmp_path / "openspec" / "specs"
    with pytest.raises(FileNotFoundError):
        _stale_authority_offenders(absent)


def test_stale_authority_offenders_flags_a_synthetic_positive_control(tmp_path: Path) -> None:
    specs_root = tmp_path / "openspec" / "specs"
    spec = specs_root / "cap" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("legacy authority: portfolio-plan.json\n", encoding="utf-8")

    offenders = _stale_authority_offenders(specs_root)

    assert offenders == ["openspec/specs/cap/spec.md"]


def test_live_plan_is_byte_stable_under_canonical_reserialization() -> None:
    """Permanent hard-abort gate: any portfolio.json mutation MUST preserve this.

    The live plan's exact on-disk bytes must equal
    json.dumps(d, ensure_ascii=True, separators=(",", ":")).encode("utf-8") —
    no indent, no sort_keys (which would reorder every record), no trailing
    newline. This invariant is asserted before every mutation of the file and
    shipped here permanently so it survives every future edit.
    """
    path = Path(__file__).resolve().parents[2] / "docs" / "specs" / "platform" / "portfolio.json"
    raw = path.read_bytes()
    d = json.loads(raw.decode("utf-8"))

    assert json.dumps(d, ensure_ascii=True, separators=(",", ":")).encode("utf-8") == raw
