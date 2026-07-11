#!/usr/bin/env python3
"""Deterministic structural validator for the platform portfolio plan.

Pure Python standard library. No third-party packages, no network, no build.

It replaces LLM sampling as the structural gate for ``portfolio-plan.json``.
The plan describes the *portfolio* — outcomes, capabilities, ports, adapters,
integrations, workflows, future SDD changes, decisions, and the traceability
(transitions, transfers, dependency edges) that ties old numeric subprojects to
the new semantic ones. This validator exhaustively checks every invariant that
traceability must satisfy: unique identity, resolvable references, one dotted
scope grammar, and an acyclic dependency graph.

Usage:
    python docs/tools/platform_portfolio/validate.py --root .
    python docs/tools/platform_portfolio/validate.py --plan path/to/portfolio-plan.json

Exit codes:
    0  no BLOCKER violations (CRITICAL/WARNING may still be reported)
    1  at least one BLOCKER violation
    2  usage / load error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict

DEFAULT_PLAN = "docs/specs/platform/portfolio.json"
ITEM_KINDS = {
    "sp",
    "prerequisite",
    "port",
    "adapter",
    "integration",
    "workflow",
    "sdd_change",
}
SCOPE_RE = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$")


class Violation:
    __slots__ = ("severity", "code", "detail")

    def __init__(self, severity: str, code: str, detail: str) -> None:
        self.severity = severity
        self.code = code
        self.detail = detail

    def __str__(self) -> str:
        return f"[{self.severity:8}] {self.code:24} {self.detail}"


class CredentialReadiness:
    """Result of assessing the credential acceptance gate's recorded evidence."""

    __slots__ = ("is_ready", "missing_requirements")

    def __init__(self, missing_requirements: tuple[str, ...]) -> None:
        self.missing_requirements = missing_requirements
        self.is_ready = not missing_requirements


def evaluate_credential_readiness(plan: dict) -> CredentialReadiness:
    """Assess the SOPS decision and explicit approval required for readiness.

    This evaluator does not transition portfolio state. It makes the approval
    prerequisite executable so callers can prove that documentary pointers do
    not advance `AC-CAP-CREDENTIALS-READY` by themselves.
    """
    required_evidence = {"S43", "S44", "S45", "S46"}
    decisions = {decision["id"]: decision for decision in plan["decisions"]}
    capability = next(item for item in plan["items"] if item["id"] == "CAP-CREDENTIALS")
    acceptance = next(
        item for item in capability["acceptance"] if item["id"] == "AC-CAP-CREDENTIALS-READY"
    )
    missing: list[str] = []

    decision = decisions.get("DPROV-SECRETS")
    if (
        decision is None
        or decision.get("status") != "decided"
        or decision.get("chosen") != "SOPS"
        or not decision.get("evidence")
    ):
        missing.append("DPROV-SECRETS approval")
    if not required_evidence.issubset(acceptance.get("evidence", [])):
        missing.append("credential readiness evidence")
    if acceptance.get("gaps"):
        missing.append("credential readiness gaps")
    if acceptance.get("status") != "approved":
        missing.append("AC-CAP-CREDENTIALS-READY approval")

    return CredentialReadiness(tuple(missing))


def validate_plan(d: dict) -> list[Violation]:
    """Return every structural violation in the plan document (empty == clean)."""
    v: list[Violation] = []

    def add(severity: str, code: str, detail: str) -> None:
        v.append(Violation(severity, code, detail))

    meta = d["meta"]
    items = {it["id"]: it for it in d["items"]}
    decisions = {x["id"]: x for x in d["decisions"]}
    decomp = {x["id"]: x for x in d.get("decompositions", [])}
    commands = set(meta.get("command_catalog", {}))
    evidence = set(meta["evidence_catalog"])
    gaps = set(meta["gap_catalog"])
    alias_map = meta.get("historical_alias_map", {})

    acceptance = set()
    for it in d["items"]:
        for a in it.get("acceptance", []) or []:
            acceptance.add(a["id"] if isinstance(a, dict) else a)

    # unique ids per collection
    for coll in ("items", "decisions", "transitions", "transfers", "edges", "decompositions"):
        seen = set()
        for x in d.get(coll, []):
            i = x.get("id")
            if i in seen:
                add("BLOCKER", "dup-id", f"{coll}:{i}")
            seen.add(i)

    # items: kind, gaps, acceptance evidence, decisions, lineage
    for it in d["items"]:
        if it["kind"] not in ITEM_KINDS:
            add("CRITICAL", "bad-kind", f"{it['id']}={it['kind']}")
        for g in it.get("gaps", []) or []:
            if g not in gaps:
                add("CRITICAL", "bad-gap", f"{it['id']}:{g}")
        for a in it.get("acceptance", []) or []:
            if not isinstance(a, dict):
                continue
            for g in a.get("gaps", []):
                if g not in gaps:
                    add("CRITICAL", "bad-ac-gap", f"{it['id']}:{g}")
            for e in a.get("evidence", []):
                if e not in evidence:
                    add("CRITICAL", "bad-ac-ev", f"{it['id']}:{e}")
        for dc in it.get("decision_ids", []) or []:
            if dc not in decisions:
                add("CRITICAL", "bad-decision-ref", f"{it['id']}:{dc}")
        for rel in ("predecessors", "successors"):
            for r in it.get(rel, []) or []:
                if r not in items and r not in alias_map:
                    add("CRITICAL", "bad-lineage", f"{it['id']}.{rel}:{r}")

    # transfers: destination, origin, dotted-scope grammar, evidence
    for t in d["transfers"]:
        if t["destination"] not in items and t["destination"] not in decisions:
            add("BLOCKER", "transfer-dest", f"{t['id']}->{t['destination']}")
        if t["origin"] not in items and t["origin"] not in alias_map:
            add("CRITICAL", "transfer-origin", f"{t['id']} origin {t['origin']}")
        if not SCOPE_RE.match(t["dotted_scope"]):
            add("CRITICAL", "scope-grammar", f"{t['id']}:{t['dotted_scope']}")
        for e in t.get("evidence", []):
            if e not in evidence:
                add("CRITICAL", "transfer-ev", f"{t['id']}:{e}")

    # edges: nodes, handoffs, evidence, acyclicity
    adj = defaultdict(list)
    for e in d["edges"]:
        if e["from"] not in items:
            add("BLOCKER", "edge-from", f"{e['id']}:{e['from']}")
        if e["to"] not in items:
            add("BLOCKER", "edge-to", f"{e['id']}:{e['to']}")
        for h in e.get("handoff_ids", []):
            if h not in acceptance:
                add("CRITICAL", "edge-handoff", f"{e['id']}:{h}")
        for ev in e.get("evidence", []):
            if ev not in evidence:
                add("CRITICAL", "edge-ev", f"{e['id']}:{ev}")
        adj[e["from"]].append(e["to"])
    color: dict[str, int] = {}

    def dfs(u: str) -> None:
        color[u] = 1
        for w in adj[u]:
            if color.get(w) == 1:
                add("BLOCKER", "edge-cycle", f"{u}->{w}")
            elif color.get(w) is None:
                dfs(w)
        color[u] = 2

    for n in list(items):
        if color.get(n) is None:
            dfs(n)

    # decompositions (future SDD changes): references + forecast consistency
    for x in d.get("decompositions", []):
        for a in x.get("acceptance_ids", []):
            if a not in acceptance:
                add("CRITICAL", "decomp-ac", f"{x['id']}:{a}")
        for dp in x.get("dependencies", []):
            if dp not in decomp and dp not in items:
                add("BLOCKER", "decomp-dep", f"{x['id']}:{dp}")
        ip = x.get("immediate_parent")
        if ip is not None and ip not in decomp:
            add("BLOCKER", "decomp-parent", f"{x['id']}:{ip}")
        for c in x.get("verification_commands", []):
            if c not in commands:
                add("CRITICAL", "decomp-cmd", f"{x['id']}:{c}")
        f = x.get("changed_line_forecast", {})
        total = 0
        for fl in f.get("files", []):
            if fl.get("total") != fl.get("additions", 0) + fl.get("deletions", 0):
                add("CRITICAL", "file-total", f"{x['id']}:{fl['path']}")
            total += fl.get("total", 0)
        if f and f.get("total") != total:
            add("CRITICAL", "forecast-sum", f"{x['id']} {f.get('total')}!={total}")

    # historical alias map: bidirectional consistency
    for k, targets in alias_map.items():
        if not re.fullmatch(r"SP-\d+", k):
            add("CRITICAL", "alias-key", k)
        for iid in targets:
            if iid not in items:
                add("CRITICAL", "alias-target", f"{k}->{iid}")
            elif k not in (items[iid].get("historical_aliases") or []):
                add("CRITICAL", "alias-backref", f"{iid} missing alias {k}")
    for it in d["items"]:
        for a in it.get("historical_aliases", []) or []:
            if it["id"] not in alias_map.get(a, []):
                add("CRITICAL", "alias-map-missing", f"{a}->{it['id']} not in alias_map")

    return v


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the platform portfolio plan.")
    parser.add_argument("--root", default=".", help="repository root (default: .)")
    parser.add_argument("--plan", default=None, help="explicit path to portfolio-plan.json")
    args = parser.parse_args(argv)

    plan_path = args.plan or f"{args.root.rstrip('/')}/{DEFAULT_PLAN}"
    try:
        plan = _load(plan_path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"validate.py: cannot load {plan_path}: {exc}", file=sys.stderr)
        return 2

    violations = validate_plan(plan)
    order = {"BLOCKER": 0, "CRITICAL": 1, "WARNING": 2}
    violations.sort(key=lambda z: order.get(z.severity, 9))
    if not violations:
        print("VALIDATOR: CLEAN — 0 violations")
        return 0
    print(f"VALIDATOR: {len(violations)} violations")
    for viol in violations:
        print(f"  {viol}")
    return 1 if any(x.severity == "BLOCKER" for x in violations) else 0


if __name__ == "__main__":
    raise SystemExit(main())
