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
from collections import Counter
from pathlib import Path
from typing import Any, NamedTuple

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
        "CHG-SP4B-ITEM-SCAFFOLD",
        "CHG-SP4B-DECOMPOSITION-ADOPTION",
        "CHG-SP4B-ERRORS-PACKAGE",
        "CHG-SP4B-ADAPTER",
        "CHG-SP4B-CONFORMANCE-FAKES",
        "CHG-SP4B-POSTGRES-HARNESS",
        "CHG-SP4B-REAL-ACCEPTANCE",
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
    "CHG-SP4B-ITEM-SCAFFOLD",
    "CHG-SP4B-DECOMPOSITION-ADOPTION",
    "CHG-SP4B-ERRORS-PACKAGE",
    "CHG-SP4B-ADAPTER",
    "CHG-SP4B-CONFORMANCE-FAKES",
    "CHG-SP4B-POSTGRES-HARNESS",
    "CHG-SP4B-REAL-ACCEPTANCE",
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
}

EXPECTED_SP4_CONTRACTS = {
    "CHG-SP4B-REGISTRY-POSTGRES": {
        "inputs": ["CHG-SP4A-INSTANCE-REGISTRY"],
        "dependencies": ["CHG-SP4A-INSTANCE-REGISTRY"],
        "immediate_parent": "CHG-SP4A-INSTANCE-REGISTRY",
        "outputs": [
            "src/odoo_forge_instances_postgres/migrate.py",
            "src/odoo_forge_instances_postgres/migrations/__init__.py",
            "src/odoo_forge_instances_postgres/migrations/0001_instance_registry.sql",
            "tests/odoo_forge_instances_postgres/test_migrate.py",
            "tests/odoo_forge_instances_postgres/test_migration_process.py",
        ],
        "changed_line_forecast": {
            "files": [
                {
                    "additions": 82,
                    "deletions": 0,
                    "path": "src/odoo_forge_instances_postgres/migrate.py",
                    "total": 82,
                },
                {
                    "additions": 2,
                    "deletions": 0,
                    "path": "src/odoo_forge_instances_postgres/migrations/__init__.py",
                    "total": 2,
                },
                {
                    "additions": 24,
                    "deletions": 0,
                    "path": (
                        "src/odoo_forge_instances_postgres/migrations/0001_instance_registry.sql"
                    ),
                    "total": 24,
                },
                {
                    "additions": 142,
                    "deletions": 0,
                    "path": "tests/odoo_forge_instances_postgres/test_migrate.py",
                    "total": 142,
                },
                {
                    "additions": 50,
                    "deletions": 0,
                    "path": "tests/odoo_forge_instances_postgres/test_migration_process.py",
                    "total": 50,
                },
            ],
            "hard_gate": 400,
            "total": 300,
        },
    },
    "CHG-SP4C-CONTROL-PLANE-EDGE": {
        "inputs": [
            "CHG-PROVIDER-CATALOG",
            "CHG-SP4B-REAL-ACCEPTANCE",
        ],
        "dependencies": [
            "CHG-PROVIDER-CATALOG",
            "CHG-SP4B-REAL-ACCEPTANCE",
        ],
        "immediate_parent": "CHG-SP4B-REAL-ACCEPTANCE",
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
        for field in (
            "inputs",
            "dependencies",
            "immediate_parent",
            "outputs",
            "changed_line_forecast",
        ):
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
        # Narrow legacy index guard; this is not a general topological invariant.
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


EXPECTED_DEC_UI_DECISIONS = {
    "DEC-UI-PARTIAL": {
        "status": "decided",
        "chosen": "Allow a localhost-only single-operator read-only slice with a permanent gap",
        "rationale": (
            "The localhost-only, single-operator, read-only slice preserves useful visibility "
            "while identity/RBAC remains deferred rather than cancelled."
        ),
        "consequence": (
            "Accepted costs: identity/RBAC remains a permanent acceptance gap for this slice, "
            "deferred rather than cancelled; loopback enforcement must be executable. "
            "Downstream acceptance shows Docker-observed truth with a visible drift label and "
            "keeps drifted rows visible. Data availability distinguishes exactly six states: "
            "fresh, drifted, stale/unverified, empty, persistence error, and per-row partial "
            "failure; anything not confirmed live is labelled."
        ),
    },
    "DEC-UI-STACK": {
        "status": "decided",
        "chosen": "Server-rendered views with polling",
        "rationale": (
            "Server-rendered views with polling fit the decided FastAPI process without a SPA, "
            "push transport, Node toolchain, or second artifact."
        ),
        "consequence": (
            "Accepted cost: polling latency. The future slice uses server-rendered views with "
            "polling inside FastAPI, with no SPA, push transport, Node toolchain, or second "
            "artifact."
        ),
    },
}
EXPECTED_UI_NON_READINESS_NOTE = (
    "Decision adoption does not deliver UI or runtime readiness; implementation remains gated "
    "by the five post-registry SP4B leaves through CHG-SP4B-REAL-ACCEPTANCE, then "
    "CHG-SP4C-CONTROL-PLANE-EDGE and control-plane authority acceptance."
)
EXPECTED_REGISTRY_DELIVERY_NOTE = "Delivered by PR #106 at main commit f94b5ed."
EXPECTED_POST_REGISTRY_LEAVES = (
    "CHG-SP4B-ERRORS-PACKAGE",
    "CHG-SP4B-ADAPTER",
    "CHG-SP4B-CONFORMANCE-FAKES",
    "CHG-SP4B-POSTGRES-HARNESS",
    "CHG-SP4B-REAL-ACCEPTANCE",
)


def _assert_dec_ui_authority(plan: dict[str, Any]) -> None:
    decisions = {entry["id"]: entry for entry in plan["decisions"]}
    for decision_id, expected_fields in EXPECTED_DEC_UI_DECISIONS.items():
        decision = decisions[decision_id]
        for field, expected in expected_fields.items():
            assert decision[field] == expected

    ui_item = next(entry for entry in plan["items"] if entry["id"] == "CHG-OPS-UI-READONLY")
    assert ui_item["status"] == "proposed"
    assert ui_item["status_note"] == EXPECTED_UI_NON_READINESS_NOTE
    assert ui_item["acceptance"] == [
        {
            "evidence": [],
            "gaps": ["G0"],
            "id": "AC-CHG-OPS-UI-READONLY-READY",
            "status": "proposed",
        }
    ]

    operations_ui = next(entry for entry in plan["items"] if entry["id"] == "SP-OPERATIONS-UI")
    assert operations_ui["status"] == "proposed"
    assert operations_ui["acceptance"][0]["gaps"] == ["G0"]

    registry = next(
        entry for entry in plan["items"] if entry["id"] == "CHG-SP4B-REGISTRY-POSTGRES"
    )
    assert registry["status"] == "achieved"
    assert registry["evidence_date"] == "2026-08-01"
    assert registry["status_note"] == EXPECTED_REGISTRY_DELIVERY_NOTE
    assert registry["acceptance"] == [
        {
            "evidence": [],
            "gaps": [],
            "id": "AC-SP4B-REGISTRY-POSTGRES-READY",
            "status": "achieved",
        }
    ]

    decompositions = {entry["id"]: entry for entry in plan["decompositions"]}
    assert _sp4b_leaf_chain_ids(plan)[1:] == EXPECTED_POST_REGISTRY_LEAVES
    for entry_id in EXPECTED_POST_REGISTRY_LEAVES:
        assert decompositions[entry_id]["status"] == "ready_for_proposal"


def _assert_serialized_portfolio_authority(plan: dict[str, Any]) -> None:
    _assert_dec_ui_authority(plan)
    assert _dec_cp_stack_governance_errors(plan) == []


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


def test_dec_ui_semantic_contract_accepts_authority_and_non_readiness(
    live_plan: dict[str, Any],
) -> None:
    _assert_dec_ui_authority(live_plan)


def test_dec_ui_semantic_contract_red_catches_restored_decision(
    live_plan: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(live_plan)
    decision = next(entry for entry in mutated["decisions"] if entry["id"] == "DEC-UI-STACK")
    decision["chosen"] = "Single-page application with push transport"

    with pytest.raises(AssertionError):
        _assert_dec_ui_authority(mutated)


def test_dec_ui_semantic_contract_red_catches_lost_drift_state_evidence(
    live_plan: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(live_plan)
    decision = next(entry for entry in mutated["decisions"] if entry["id"] == "DEC-UI-PARTIAL")
    decision["consequence"] = decision["consequence"].replace("drifted", "hidden")

    with pytest.raises(AssertionError):
        _assert_dec_ui_authority(mutated)


def test_dec_ui_semantic_contract_red_catches_cleared_readiness_gate(
    live_plan: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(live_plan)
    item = next(entry for entry in mutated["items"] if entry["id"] == "CHG-OPS-UI-READONLY")
    item["status"] = "achieved"

    with pytest.raises(AssertionError):
        _assert_dec_ui_authority(mutated)


def test_serialized_portfolio_red_catches_registry_lost_update(
    live_plan: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(live_plan)
    registry = next(
        entry for entry in mutated["items"] if entry["id"] == "CHG-SP4B-REGISTRY-POSTGRES"
    )
    registry["status"] = "proposed"
    registry["evidence_date"] = None
    registry["status_note"] = ""
    registry["acceptance"][0]["status"] = "proposed"
    registry["acceptance"][0]["gaps"] = ["G0"]

    with pytest.raises(AssertionError):
        _assert_serialized_portfolio_authority(mutated)


def test_serialized_portfolio_authority_preserves_both_changes(
    live_plan: dict[str, Any],
) -> None:
    _assert_serialized_portfolio_authority(live_plan)


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


class ScaffoldRecord(NamedTuple):
    """One expected SP4B scaffold item record.

    Named fields rather than a positional tuple: the earlier seven-field
    positional form was unpacked with throwaway names, and two of those
    columns (`title`, `decision_ids`) silently went unasserted while still
    looking covered. Named access makes an unused expectation visible.
    """

    item_id: str
    title: str
    owner_role: str
    acceptance_id: str
    decision_ids: tuple[str, ...]
    predecessors: tuple[str, ...]
    successors: tuple[str, ...]


EXPECTED_SP4B_SCAFFOLD_CHAIN: tuple[ScaffoldRecord, ...] = (
    ScaffoldRecord(
        "CHG-SP4B-REDECOMPOSE",
        "SP4B PostgreSQL Registry Recomposition",
        "Architecture",
        "AC-CHG-SP4B-REDECOMPOSE-READY",
        (),
        (),
        ("CHG-SP4B-REGISTRY-POSTGRES",),
    ),
    ScaffoldRecord(
        "CHG-SP4B-REGISTRY-POSTGRES",
        "SP4B Registry PostgreSQL Schema and Migration",
        "Data Platform",
        "AC-SP4B-REGISTRY-POSTGRES-READY",
        ("DEC-CP-STACK",),
        ("CHG-SP4B-REDECOMPOSE",),
        ("CHG-SP4B-ERRORS-PACKAGE",),
    ),
    ScaffoldRecord(
        "CHG-SP4B-ERRORS-PACKAGE",
        "SP4B Registry Errors and Package",
        "Data Platform",
        "AC-SP4B-ERRORS-PACKAGE-READY",
        ("DEC-CP-STACK",),
        ("CHG-SP4B-REGISTRY-POSTGRES",),
        ("CHG-SP4B-ADAPTER",),
    ),
    ScaffoldRecord(
        "CHG-SP4B-ADAPTER",
        "SP4B PostgreSQL Registry Adapter",
        "Data Platform",
        "AC-SP4B-ADAPTER-READY",
        ("DEC-CP-STACK",),
        ("CHG-SP4B-ERRORS-PACKAGE",),
        ("CHG-SP4B-CONFORMANCE-FAKES",),
    ),
    ScaffoldRecord(
        "CHG-SP4B-CONFORMANCE-FAKES",
        "SP4B Registry Conformance and Fakes",
        "Data Platform",
        "AC-SP4B-CONFORMANCE-FAKES-READY",
        ("DEC-CP-STACK",),
        ("CHG-SP4B-ADAPTER",),
        ("CHG-SP4B-POSTGRES-HARNESS",),
    ),
    ScaffoldRecord(
        "CHG-SP4B-POSTGRES-HARNESS",
        "SP4B PostgreSQL Test Harness",
        "Data Platform",
        "AC-SP4B-POSTGRES-HARNESS-READY",
        ("DEC-CP-STACK",),
        ("CHG-SP4B-CONFORMANCE-FAKES",),
        ("CHG-SP4B-REAL-ACCEPTANCE",),
    ),
    ScaffoldRecord(
        "CHG-SP4B-REAL-ACCEPTANCE",
        "SP4B Real PostgreSQL Acceptance",
        "Data Platform",
        "AC-SP4B-REAL-ACCEPTANCE-READY",
        ("DEC-CP-STACK",),
        ("CHG-SP4B-POSTGRES-HARNESS",),
        (),
    ),
    ScaffoldRecord(
        "CHG-SP4B-DECOMPOSITION-ADOPTION",
        "SP4B Decomposition Adoption and SP4C Rewire",
        "Architecture",
        "AC-CHG-SP4B-DECOMPOSITION-ADOPTION-READY",
        (),
        ("CHG-SP4B-ITEM-SCAFFOLD",),
        (),
    ),
)


def test_sp4b_scaffold_items_exist_with_exact_kind_owner_role_and_status(
    live_plan: dict[str, Any],
) -> None:
    """Pin kind/owner_role/status/evidence_date/title/decision_ids for all eight
    scaffold records (spec R1; corrects W4).

    `title` and `decision_ids` were previously unpacked from
    `EXPECTED_SP4B_SCAFFOLD_CHAIN` and asserted nowhere: mutating either
    survived both this suite and the validator.
    """
    items = {item["id"]: item for item in live_plan["items"]}
    for expected in EXPECTED_SP4B_SCAFFOLD_CHAIN:
        item = items[expected.item_id]
        assert item["kind"] == "sdd_change"
        assert item["owner_role"] == expected.owner_role
        if expected.item_id == "CHG-SP4B-REGISTRY-POSTGRES":
            assert item["status"] == "achieved"
            assert item["evidence_date"] == "2026-08-01"
        else:
            assert item["status"] == "proposed"
            assert item["evidence_date"] is None
        assert item["title"] == expected.title
        assert tuple(item["decision_ids"]) == expected.decision_ids


SP4B_GOVERNANCE_ITEM_IDS: frozenset[str] = frozenset(
    {"CHG-SP4B-REDECOMPOSE", "CHG-SP4B-DECOMPOSITION-ADOPTION"}
)
SP4B_LEAF_ITEM_IDS: frozenset[str] = frozenset(
    {
        "CHG-SP4B-REGISTRY-POSTGRES",
        "CHG-SP4B-ERRORS-PACKAGE",
        "CHG-SP4B-ADAPTER",
        "CHG-SP4B-CONFORMANCE-FAKES",
        "CHG-SP4B-POSTGRES-HARNESS",
        "CHG-SP4B-REAL-ACCEPTANCE",
    }
)


def test_sp4b_scaffold_acceptance_ids_are_exact(live_plan: dict[str, Any]) -> None:
    """Pin the acceptance-id `CHG-` infix classification against the live plan
    (spec R2, corrected by design X2).

    A governance-change record's acceptance id carries the `CHG-` infix; a
    leaf/scaffold record's does not. This used to be enforced positionally
    (index 0 only) and broke the moment an 8th `ScaffoldRecord` (this
    change's own item, `CHG-SP4B-DECOMPOSITION-ADOPTION`) was appended at
    index 7 while also carrying `CHG-`. The rule is now id-classified: it
    checks membership in `SP4B_GOVERNANCE_ITEM_IDS` /
    `SP4B_LEAF_ITEM_IDS`, never array position, so appending further
    records never breaks it. `acceptance_ids` is built from `live_plan`,
    not from the expectation constant, so the checks below actually
    exercise the live data instead of comparing hand-written literals to
    themselves.
    """
    items = {item["id"]: item for item in live_plan["items"]}
    acceptance_ids: list[str] = []
    for expected in EXPECTED_SP4B_SCAFFOLD_CHAIN:
        item = items[expected.item_id]
        live_acceptance_ids = [a["id"] for a in item["acceptance"]]
        assert live_acceptance_ids == [expected.acceptance_id]
        acceptance_ids.extend(live_acceptance_ids)
    assert {
        record.item_id for record in EXPECTED_SP4B_SCAFFOLD_CHAIN
    } == SP4B_GOVERNANCE_ITEM_IDS | SP4B_LEAF_ITEM_IDS
    assert SP4B_GOVERNANCE_ITEM_IDS.isdisjoint(SP4B_LEAF_ITEM_IDS)
    for item_id in SP4B_GOVERNANCE_ITEM_IDS:
        assert "CHG-" in items[item_id]["acceptance"][0]["id"]
    for item_id in SP4B_LEAF_ITEM_IDS:
        assert "CHG-" not in items[item_id]["acceptance"][0]["id"]
    assert len(set(acceptance_ids)) == len(acceptance_ids)


def _assert_sp4b_scaffold_chain_lineage(plan: dict[str, Any]) -> None:
    """Pin every scaffold record's lineage by value, independent of scans."""
    items = {item["id"]: item for item in plan["items"]}
    for expected in EXPECTED_SP4B_SCAFFOLD_CHAIN:
        item = items[expected.item_id]
        assert tuple(item["predecessors"]) == expected.predecessors
        assert tuple(item["successors"]) == expected.successors


def test_sp4b_scaffold_chain_lineage_is_exact_and_record7_terminal(
    live_plan: dict[str, Any],
) -> None:
    """Pin the linear predecessor/successor chain across records 1-6 (spec R5)
    and record 7's terminal successors list (spec R3), plus record 8's own
    change lineage.

    Record 7's `successors` is empty in this change; whether a forward link
    to an SP4C item is ever populated is an open question owned by
    CHG-SP4B-DECOMPOSITION-ADOPTION (design D5) -- this is asserted by the
    exact eight-record table rather than by a blanket foreign-id scan.
    """
    _assert_sp4b_scaffold_chain_lineage(live_plan)


def test_sp4b_scaffold_chain_red_catches_sp4c_foreign_successor(
    live_plan: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(live_plan)
    own_item = next(
        item for item in mutated["items"] if item["id"] == "CHG-SP4B-DECOMPOSITION-ADOPTION"
    )
    own_item["successors"] = ["CHG-SP4C-CONTROL-PLANE-EDGE"]

    with pytest.raises(AssertionError):
        _assert_sp4b_scaffold_chain_lineage(mutated)


def test_sp4b_scaffold_chain_red_catches_non_sp4c_foreign_successor(
    live_plan: dict[str, Any],
) -> None:
    mutated = copy.deepcopy(live_plan)
    own_item = next(
        item for item in mutated["items"] if item["id"] == "CHG-SP4B-DECOMPOSITION-ADOPTION"
    )
    own_item["successors"] = ["CHG-UNRELATED-FOREIGN-ITEM"]

    with pytest.raises(AssertionError):
        _assert_sp4b_scaffold_chain_lineage(mutated)


def test_sp4b_leaf_chain_rejects_cycles(live_plan: dict[str, Any]) -> None:
    mutated = copy.deepcopy(live_plan)
    leaves = {
        entry["id"]: entry
        for entry in mutated["decompositions"]
        if entry["id"].startswith("CHG-SP4B-")
    }
    leaves["CHG-SP4B-REGISTRY-POSTGRES"]["immediate_parent"] = "CHG-SP4B-ERRORS-PACKAGE"
    leaves["CHG-SP4B-ADAPTER"]["immediate_parent"] = "CHG-SP4A-INSTANCE-REGISTRY"

    with pytest.raises(AssertionError, match="cycle"):
        _sp4b_leaf_chain_ids(mutated)


EXPECTED_PREEXISTING_COMMAND_CATALOG: dict[str, str] = {
    "C37": "uv run pytest",
    "C38": "uv run lint-imports",
    "C39": "uv run mypy",
    "C40": "uv run ruff check",
    "C41": "uv build",
}

EXPECTED_SP4B_COMMAND_CATALOG: dict[str, str] = {
    "C42": "uv run pytest tests/portfolio/test_portfolio_integrity.py",
    "C43": "uv run pytest docs/tools/platform_portfolio/test_validate.py",
    "C44": "python docs/tools/platform_portfolio/validate.py --root .",
    "C45": "uv run pytest tests/odoo_forge_instances_postgres -m 'not integration and not real_docker'",  # noqa: E501
    "C46": (
        "uv run pytest -m 'integration and real_docker' "
        "tests/odoo_forge_instances_postgres/test_real_postgres_integration.py"
    ),
}


def test_sp4b_command_catalog_mints_c42_to_c46_with_exact_strings(
    live_plan: dict[str, Any],
) -> None:
    """Pin C42-C46's exact command strings and confirm C37-C41 remain
    byte-unchanged (spec R6).

    A set-difference-over-keys check only pins the added key set: a
    pre-existing value could be mutated, or a pre-existing key deleted (if
    still referenced by some decomposition, masking the loss), without
    failing anything. Full dict equality against the merged pre-existing +
    new mapping pins values, not just keys.
    """
    catalog = live_plan["meta"]["command_catalog"]
    assert catalog == EXPECTED_PREEXISTING_COMMAND_CATALOG | EXPECTED_SP4B_COMMAND_CATALOG


def test_sp4b_item_scaffold_decomposition_is_exact(live_plan: dict[str, Any]) -> None:
    """Pin this change's own decomposition record (spec R7), including
    start_boundary/finish_boundary/rollback and changed_line_forecast.

    The forecast is pinned by value, not left to the validator. The
    validator's `forecast-sum` only checks internal arithmetic, and
    `forecast-gate` compares the record's total against a `hard_gate`
    stored in that same record -- so raising `hard_gate` to 10000 or
    deleting it outright defeats the gate while both checks stay silent.
    Redistributing `additions`/`deletions`, rescaling every total
    consistently, or replacing a file `path` are equally silent. An
    arithmetic check passes for any internally consistent rewrite, so it
    never substitutes for pinning the individual field values.
    """
    decomposition = next(
        entry for entry in live_plan["decompositions"] if entry["id"] == "CHG-SP4B-ITEM-SCAFFOLD"
    )
    assert decomposition["owner"] == "Architecture"
    assert decomposition["type"] == "implementation_change"
    assert decomposition["inputs"] == []
    assert decomposition["outputs"] == [
        "docs/specs/platform/portfolio.json",
        "tests/portfolio/test_portfolio_integrity.py",
    ]
    assert decomposition["acceptance_ids"] == ["AC-CHG-SP4B-ITEM-SCAFFOLD-READY"]
    assert decomposition["start_boundary"] == "start:CHG-SP4B-ITEM-SCAFFOLD"
    assert decomposition["finish_boundary"] == "finish:CHG-SP4B-ITEM-SCAFFOLD"
    assert decomposition["dependencies"] == ["CHG-SP4B-VALIDATOR-GROUNDWORK"]
    assert decomposition["verification_commands"] == ["C42", "C43", "C44"]
    assert decomposition["rollback"] == (
        "revert the single commit; restore portfolio.json to prior committed bytes"
    )
    assert decomposition["immediate_parent"] is None
    assert decomposition["status"] == "ready_for_proposal"
    assert decomposition["blocking_decision_ids"] == []
    assert decomposition["changed_line_forecast"] == {
        "files": [
            {
                "path": "docs/specs/platform/portfolio.json",
                "additions": 134,
                "deletions": 0,
                "total": 134,
            },
            {
                "path": "tests/portfolio/test_portfolio_integrity.py",
                "additions": 107,
                "deletions": 0,
                "total": 107,
            },
        ],
        "total": 241,
        "hard_gate": 400,
    }


class ForecastFile(NamedTuple):
    path: str
    additions: int
    deletions: int
    total: int


class LeafContract(NamedTuple):
    """One expected SP4B leaf decomposition record, by value.

    Accessed by field name only -- no positional unpacking anywhere, the
    same discipline as `ScaffoldRecord` above (a positional form silently
    dropped columns on the previous link).
    """

    decomposition_id: str
    owner: str
    record_type: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    acceptance_ids: tuple[str, ...]
    start_boundary: str
    finish_boundary: str
    dependencies: tuple[str, ...]
    verification_commands: tuple[str, ...]
    rollback: str
    immediate_parent: str
    forecast_files: tuple[ForecastFile, ...]
    forecast_total: int
    hard_gate: int
    status: str
    blocking_decision_ids: tuple[str, ...]


EXPECTED_SP4B_LEAF_CONTRACTS: tuple[LeafContract, ...] = (
    LeafContract(
        decomposition_id="CHG-SP4B-REGISTRY-POSTGRES",
        owner="Data Platform",
        record_type="implementation_change",
        inputs=("CHG-SP4A-INSTANCE-REGISTRY",),
        outputs=(
            "src/odoo_forge_instances_postgres/migrate.py",
            "src/odoo_forge_instances_postgres/migrations/__init__.py",
            "src/odoo_forge_instances_postgres/migrations/0001_instance_registry.sql",
            "tests/odoo_forge_instances_postgres/test_migrate.py",
            "tests/odoo_forge_instances_postgres/test_migration_process.py",
        ),
        acceptance_ids=("AC-SP4B-REGISTRY-POSTGRES-READY",),
        start_boundary="start:CHG-SP4B-REGISTRY-POSTGRES",
        finish_boundary="finish:CHG-SP4B-REGISTRY-POSTGRES",
        dependencies=("CHG-SP4A-INSTANCE-REGISTRY",),
        verification_commands=("C37", "C38", "C39", "C40", "C41", "C45"),
        rollback=(
            "revert the migration module, SQL migration, and their tests; "
            "source rollback drops no migrated database"
        ),
        immediate_parent="CHG-SP4A-INSTANCE-REGISTRY",
        forecast_files=(
            ForecastFile("src/odoo_forge_instances_postgres/migrate.py", 82, 0, 82),
            ForecastFile("src/odoo_forge_instances_postgres/migrations/__init__.py", 2, 0, 2),
            ForecastFile(
                "src/odoo_forge_instances_postgres/migrations/0001_instance_registry.sql",
                24,
                0,
                24,
            ),
            ForecastFile("tests/odoo_forge_instances_postgres/test_migrate.py", 142, 0, 142),
            ForecastFile(
                "tests/odoo_forge_instances_postgres/test_migration_process.py", 50, 0, 50
            ),
        ),
        forecast_total=300,
        hard_gate=400,
        status="ready_for_proposal",
        blocking_decision_ids=(),
    ),
    LeafContract(
        decomposition_id="CHG-SP4B-ERRORS-PACKAGE",
        owner="Data Platform",
        record_type="implementation_change",
        inputs=("CHG-SP4B-REGISTRY-POSTGRES",),
        outputs=(
            "src/odoo_forge_instances_postgres/__init__.py",
            "src/odoo_forge_instances_postgres/errors.py",
            "pyproject.toml",
            "uv.lock",
            ".github/workflows/release.yml",
            "tests/odoo_forge_instances_postgres/test_errors.py",
            "tests/odoo_forge_instances_postgres/test_package.py",
        ),
        acceptance_ids=("AC-SP4B-ERRORS-PACKAGE-READY",),
        start_boundary="start:CHG-SP4B-ERRORS-PACKAGE",
        finish_boundary="finish:CHG-SP4B-ERRORS-PACKAGE",
        dependencies=("CHG-SP4B-REGISTRY-POSTGRES",),
        verification_commands=("C37", "C38", "C39", "C40", "C41", "C45"),
        rollback=(
            "revert the errors package, packaging metadata, and their tests; "
            "no migrated database state is affected"
        ),
        immediate_parent="CHG-SP4B-REGISTRY-POSTGRES",
        forecast_files=(
            ForecastFile("src/odoo_forge_instances_postgres/__init__.py", 12, 0, 12),
            ForecastFile("src/odoo_forge_instances_postgres/errors.py", 58, 0, 58),
            ForecastFile("pyproject.toml", 22, 0, 22),
            ForecastFile("uv.lock", 115, 0, 115),
            ForecastFile(".github/workflows/release.yml", 8, 0, 8),
            ForecastFile("tests/odoo_forge_instances_postgres/test_errors.py", 95, 0, 95),
            ForecastFile("tests/odoo_forge_instances_postgres/test_package.py", 30, 0, 30),
        ),
        forecast_total=340,
        hard_gate=400,
        status="ready_for_proposal",
        blocking_decision_ids=(),
    ),
    LeafContract(
        decomposition_id="CHG-SP4B-ADAPTER",
        owner="Data Platform",
        record_type="implementation_change",
        inputs=("CHG-SP4B-ERRORS-PACKAGE",),
        outputs=(
            "src/odoo_forge_instances_postgres/adapter.py",
            "tests/odoo_forge_instances_postgres/test_adapter.py",
        ),
        acceptance_ids=("AC-SP4B-ADAPTER-READY",),
        start_boundary="start:CHG-SP4B-ADAPTER",
        finish_boundary="finish:CHG-SP4B-ADAPTER",
        dependencies=("CHG-SP4B-ERRORS-PACKAGE",),
        verification_commands=("C37", "C38", "C39", "C40", "C41", "C45"),
        rollback="revert the adapter module and its tests; no migrated database state is affected",
        immediate_parent="CHG-SP4B-ERRORS-PACKAGE",
        forecast_files=(
            ForecastFile("src/odoo_forge_instances_postgres/adapter.py", 160, 0, 160),
            ForecastFile("tests/odoo_forge_instances_postgres/test_adapter.py", 160, 0, 160),
        ),
        forecast_total=320,
        hard_gate=400,
        status="ready_for_proposal",
        blocking_decision_ids=(),
    ),
    LeafContract(
        decomposition_id="CHG-SP4B-CONFORMANCE-FAKES",
        owner="Data Platform",
        record_type="implementation_change",
        inputs=("CHG-SP4B-ADAPTER",),
        outputs=(
            "src/odoo_forge_instances_postgres/fakes.py",
            "tests/odoo_forge_instances_postgres/test_conformance.py",
            "tests/odoo_forge_instances_postgres/test_fake_boundary.py",
        ),
        acceptance_ids=("AC-SP4B-CONFORMANCE-FAKES-READY",),
        start_boundary="start:CHG-SP4B-CONFORMANCE-FAKES",
        finish_boundary="finish:CHG-SP4B-CONFORMANCE-FAKES",
        dependencies=("CHG-SP4B-ADAPTER",),
        verification_commands=("C37", "C38", "C39", "C40", "C41", "C45"),
        rollback=(
            "revert the conformance fakes module and its tests; "
            "no migrated database state is affected"
        ),
        immediate_parent="CHG-SP4B-ADAPTER",
        forecast_files=(
            ForecastFile("src/odoo_forge_instances_postgres/fakes.py", 90, 0, 90),
            ForecastFile("tests/odoo_forge_instances_postgres/test_conformance.py", 70, 0, 70),
            ForecastFile("tests/odoo_forge_instances_postgres/test_fake_boundary.py", 80, 0, 80),
        ),
        forecast_total=240,
        hard_gate=400,
        status="ready_for_proposal",
        blocking_decision_ids=(),
    ),
    LeafContract(
        decomposition_id="CHG-SP4B-POSTGRES-HARNESS",
        owner="Data Platform",
        record_type="implementation_change",
        inputs=("CHG-SP4B-CONFORMANCE-FAKES",),
        outputs=(
            "src/odoo_forge_instances_postgres/real_postgres.py",
            "tests/odoo_forge_instances_postgres/test_real_postgres_harness.py",
            "tests/odoo_forge_instances_postgres/test_real_postgres_process.py",
        ),
        acceptance_ids=("AC-SP4B-POSTGRES-HARNESS-READY",),
        start_boundary="start:CHG-SP4B-POSTGRES-HARNESS",
        finish_boundary="finish:CHG-SP4B-POSTGRES-HARNESS",
        dependencies=("CHG-SP4B-CONFORMANCE-FAKES",),
        verification_commands=("C37", "C38", "C39", "C40", "C41", "C45"),
        rollback=(
            "revert harness module and process tests; persisted database state is removed only by "
            "an explicit retention-approved operation"
        ),
        immediate_parent="CHG-SP4B-CONFORMANCE-FAKES",
        forecast_files=(
            ForecastFile("src/odoo_forge_instances_postgres/real_postgres.py", 150, 0, 150),
            ForecastFile(
                "tests/odoo_forge_instances_postgres/test_real_postgres_harness.py", 150, 0, 150
            ),
            ForecastFile(
                "tests/odoo_forge_instances_postgres/test_real_postgres_process.py", 80, 0, 80
            ),
        ),
        forecast_total=380,
        hard_gate=400,
        status="ready_for_proposal",
        blocking_decision_ids=(),
    ),
    LeafContract(
        decomposition_id="CHG-SP4B-REAL-ACCEPTANCE",
        owner="Data Platform",
        record_type="implementation_change",
        inputs=("CHG-SP4B-POSTGRES-HARNESS",),
        outputs=(
            "tests/odoo_forge_instances_postgres/test_real_postgres_integration.py",
            "tests/odoo_forge_instances_postgres/postgres_test_database.py",
            "tests/odoo_forge_instances_postgres/test_real_postgres_acceptance.py",
        ),
        acceptance_ids=(
            "AC-SP4B-REAL-ACCEPTANCE-READY",
            "AC-SP-CONTROL-PLANE-AUTHORITY-READY",
        ),
        start_boundary="start:CHG-SP4B-REAL-ACCEPTANCE",
        finish_boundary="finish:CHG-SP4B-REAL-ACCEPTANCE",
        dependencies=("CHG-SP4B-POSTGRES-HARNESS",),
        verification_commands=("C37", "C38", "C39", "C40", "C41", "C45", "C46"),
        rollback=(
            "revert acceptance-only tests and helpers; database cleanup stays explicit and "
            "retention-governed"
        ),
        immediate_parent="CHG-SP4B-POSTGRES-HARNESS",
        forecast_files=(
            ForecastFile(
                "tests/odoo_forge_instances_postgres/test_real_postgres_integration.py", 220, 0, 220
            ),
            ForecastFile(
                "tests/odoo_forge_instances_postgres/postgres_test_database.py", 80, 0, 80
            ),
            ForecastFile(
                "tests/odoo_forge_instances_postgres/test_real_postgres_acceptance.py", 50, 0, 50
            ),
        ),
        forecast_total=350,
        hard_gate=400,
        status="ready_for_proposal",
        blocking_decision_ids=(),
    ),
)

DECOMPOSITION_KEY_ORDER: tuple[str, ...] = (
    "id",
    "owner",
    "type",
    "inputs",
    "outputs",
    "acceptance_ids",
    "start_boundary",
    "finish_boundary",
    "dependencies",
    "verification_commands",
    "rollback",
    "immediate_parent",
    "changed_line_forecast",
    "status",
    "blocking_decision_ids",
)
FORECAST_KEY_ORDER: tuple[str, ...] = ("files", "total", "hard_gate")


def _sp4b_leaf_chain_ids(plan: dict[str, Any]) -> tuple[str, ...]:
    """Walk the SP4B leaf chain from leaf 1 via `immediate_parent`, live.

    Deliberately NOT derived from `EXPECTED_SP4B_LEAF_CONTRACTS`: if it were,
    the both-ways equality in `test_sp4b_leaf_contract_table_ids_match_live_leaf_ids`
    would be a tautology (an unpinned 4th leaf would never be noticed). The
    `CHG-SP4B-` prefix filter excludes the legitimate SP4C child
    `CHG-SP4C-CONTROL-PLANE-EDGE` of `CHG-SP4B-REAL-ACCEPTANCE`, which would
    otherwise extend the SP4B leaf chain.
    """
    decompositions = {entry["id"]: entry for entry in plan["decompositions"]}
    chain = ["CHG-SP4B-REGISTRY-POSTGRES"]
    current = chain[0]
    visited = set(chain)
    while True:
        candidates = [
            entry_id
            for entry_id, entry in decompositions.items()
            if entry.get("immediate_parent") == current
            and entry_id.startswith("CHG-SP4B-")
            and entry_id != current
        ]
        assert len(candidates) <= 1, f"ambiguous SP4B chain successor(s) of {current}: {candidates}"
        if not candidates:
            break
        current = candidates[0]
        assert current not in visited, f"cycle in SP4B leaf chain at {current}"
        visited.add(current)
        chain.append(current)
    return tuple(chain)


def _sp4b_leaf_contract_from_live(plan: dict[str, Any], decomposition_id: str) -> LeafContract:
    entry = next(e for e in plan["decompositions"] if e["id"] == decomposition_id)
    forecast = entry["changed_line_forecast"]
    return LeafContract(
        decomposition_id=entry["id"],
        owner=entry["owner"],
        record_type=entry["type"],
        inputs=tuple(entry["inputs"]),
        outputs=tuple(entry["outputs"]),
        acceptance_ids=tuple(entry["acceptance_ids"]),
        start_boundary=entry["start_boundary"],
        finish_boundary=entry["finish_boundary"],
        dependencies=tuple(entry["dependencies"]),
        verification_commands=tuple(entry["verification_commands"]),
        rollback=entry["rollback"],
        immediate_parent=entry["immediate_parent"],
        forecast_files=tuple(
            ForecastFile(f["path"], f["additions"], f["deletions"], f["total"])
            for f in forecast["files"]
        ),
        forecast_total=forecast["total"],
        hard_gate=forecast["hard_gate"],
        status=entry["status"],
        blocking_decision_ids=tuple(entry["blocking_decision_ids"]),
    )


def test_sp4b_leaf_contract_table_ids_match_live_leaf_ids(live_plan: dict[str, Any]) -> None:
    """T3 (both-ways id-set equality, spec: EXPECTED_SP4_CONTRACTS stays at two
    entries / leaf contracts live in a separate table).

    `SP4B_LEAF_IDS` is derived from the live chain (`_sp4b_leaf_chain_ids`),
    not from `EXPECTED_SP4B_LEAF_CONTRACTS`, so a 4th leaf appended without a
    table row fails this, and a table row for a leaf no longer reachable
    from the chain also fails this.
    """
    table_ids = {row.decomposition_id for row in EXPECTED_SP4B_LEAF_CONTRACTS}
    live_ids = set(_sp4b_leaf_chain_ids(live_plan))
    assert table_ids == live_ids
    assert len(EXPECTED_SP4B_LEAF_CONTRACTS) == 6


def test_sp4b_leaf_contracts_match_live_plan_by_value(live_plan: dict[str, Any]) -> None:
    """T3 by-value half: every SP4B leaf field, pinned exactly.

    A single `NamedTuple == NamedTuple` equality per leaf pins every field
    at once, including per-file `additions`/`deletions`/`path` and the
    `hard_gate`/`total` pair -- so redistributed additions/deletions, an
    inflated or deleted `hard_gate`, a swapped forecast path, or a
    consistent rescale of every total are all caught (spec W6 a-e), none of
    which the validator's `forecast-sum`/`file-total`/`forecast-gate`
    catches (those only check internal arithmetic, not the pinned values).
    """
    for expected in EXPECTED_SP4B_LEAF_CONTRACTS:
        actual = _sp4b_leaf_contract_from_live(live_plan, expected.decomposition_id)
        assert actual == expected


def test_sp4b_leaf_contract_red_catches_hard_gate_deleted(live_plan: dict[str, Any]) -> None:
    mutated = copy.deepcopy(live_plan)
    entry = next(e for e in mutated["decompositions"] if e["id"] == "CHG-SP4B-ADAPTER")
    del entry["changed_line_forecast"]["hard_gate"]

    with pytest.raises(KeyError):
        _sp4b_leaf_contract_from_live(mutated, "CHG-SP4B-ADAPTER")


def test_sp4b_leaf_chain_is_linear_and_rooted(live_plan: dict[str, Any]) -> None:
    """T4 (spec: Six-Leaf Chain Shape)."""
    chain = _sp4b_leaf_chain_ids(live_plan)
    assert chain == (
        "CHG-SP4B-REGISTRY-POSTGRES",
        "CHG-SP4B-ERRORS-PACKAGE",
        "CHG-SP4B-ADAPTER",
        "CHG-SP4B-CONFORMANCE-FAKES",
        "CHG-SP4B-POSTGRES-HARNESS",
        "CHG-SP4B-REAL-ACCEPTANCE",
    )
    decompositions = {e["id"]: e for e in live_plan["decompositions"]}
    assert (
        decompositions["CHG-SP4B-REGISTRY-POSTGRES"]["immediate_parent"]
        == "CHG-SP4A-INSTANCE-REGISTRY"
    )


def test_sp4b_leaf_chain_red_catches_shared_parent(live_plan: dict[str, Any]) -> None:
    """A leaf re-parented onto an already-claimed parent is ambiguous fan-out;
    catches both 'predecessor skipped' and 'two leaves share a parent'.
    """
    mutated = copy.deepcopy(live_plan)
    leaf3 = next(e for e in mutated["decompositions"] if e["id"] == "CHG-SP4B-ADAPTER")
    leaf3["immediate_parent"] = "CHG-SP4B-REGISTRY-POSTGRES"  # leaf 2's parent too

    with pytest.raises(AssertionError):
        _sp4b_leaf_chain_ids(mutated)


def test_sp4b_leaf_output_paths_are_exclusive(live_plan: dict[str, Any]) -> None:
    """T5 (spec: Output Path Exclusivity); the validator's `decomp-output-path`
    only checks shape, never cross-leaf duplication.
    """
    leaf_ids = set(_sp4b_leaf_chain_ids(live_plan))
    paths = [p for e in live_plan["decompositions"] if e["id"] in leaf_ids for p in e["outputs"]]
    duplicates = [p for p, n in Counter(paths).items() if n > 1]
    assert duplicates == []


def test_sp4b_leaf_forecast_arithmetic_holds(live_plan: dict[str, Any]) -> None:
    """T6 (spec: Forecast arithmetic holds per leaf)."""
    for leaf_id in _sp4b_leaf_chain_ids(live_plan):
        entry = next(e for e in live_plan["decompositions"] if e["id"] == leaf_id)
        forecast = entry["changed_line_forecast"]
        for f in forecast["files"]:
            assert f["total"] == f["additions"] + f["deletions"]
        assert forecast["total"] == sum(f["total"] for f in forecast["files"])
        assert forecast["hard_gate"] == 400
        assert forecast["total"] <= forecast["hard_gate"]


def test_sp4b_leaf_key_order_is_exact(live_plan: dict[str, Any]) -> None:
    """T11 (spec: Decomposition Key Order Is Enforced).

    Neither the byte-stability test (round-trips whatever order was
    authored) nor `_canonical_record_digest` (`sort_keys=True`, order-blind)
    pins key order. This is the only test that does.
    """
    for leaf_id in _sp4b_leaf_chain_ids(live_plan):
        entry = next(e for e in live_plan["decompositions"] if e["id"] == leaf_id)
        assert list(entry.keys()) == list(DECOMPOSITION_KEY_ORDER)
        assert list(entry["changed_line_forecast"].keys()) == list(FORECAST_KEY_ORDER)


def test_sp4b_capability_acceptance_belongs_only_to_leaf_six(
    live_plan: dict[str, Any],
) -> None:
    capability_acceptance = "AC-SP-CONTROL-PLANE-AUTHORITY-READY"
    owners = [
        leaf_id
        for leaf_id in _sp4b_leaf_chain_ids(live_plan)
        if capability_acceptance
        in next(entry for entry in live_plan["decompositions"] if entry["id"] == leaf_id)[
            "acceptance_ids"
        ]
    ]
    assert owners == ["CHG-SP4B-REAL-ACCEPTANCE"]


def test_sp4c_rewire_is_complete(live_plan: dict[str, Any]) -> None:
    sp4c = next(
        entry
        for entry in live_plan["decompositions"]
        if entry["id"] == "CHG-SP4C-CONTROL-PLANE-EDGE"
    )
    assert sp4c["inputs"] == ["CHG-PROVIDER-CATALOG", "CHG-SP4B-REAL-ACCEPTANCE"]
    assert sp4c["dependencies"] == ["CHG-PROVIDER-CATALOG", "CHG-SP4B-REAL-ACCEPTANCE"]
    assert sp4c["immediate_parent"] == "CHG-SP4B-REAL-ACCEPTANCE"


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


def test_live_plan_decomposition_ids_are_exact(live_plan: dict[str, Any]) -> None:
    """T1 (spec: SP4B Six-Leaf Decomposition / slice A id extension).

    Built from `live_plan`, not from the constant it is compared against
    being re-derived: a dropped, renamed, reordered, or undeclared extra
    decomposition id fails this before any other slice-A assertion runs.
    """
    assert tuple(entry["id"] for entry in live_plan["decompositions"]) == EXPECTED_DECOMPOSITION_IDS


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
