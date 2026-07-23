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
    0  no CRITICAL or BLOCKER violations
    1  at least one CRITICAL or BLOCKER violation
    2  usage / load error
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path

DEFAULT_PLAN = "docs/specs/platform/portfolio.json"
PARENT_VERIFY_SHA256 = "0fbb60e3b0aba12a46cc26a69c57b40ffb26fa1c60adde5946c0ee9018d084c4"
RENDERER_SHA256 = "526e20a35ace9f4d198a157ddc7e4e0315fe7b208c021099b7a3898c8ee662ed"
CANDIDATE_PATHS = {
    "docs/specs/platform/platform-architecture.html",
    "docs/tools/platform_portfolio/test_validate.py",
    "docs/tools/platform_portfolio/validate.py",
    "openspec/changes/fix-roadmap-refresh-verification-closure/apply-progress.md",
    "openspec/changes/fix-roadmap-refresh-verification-closure/tasks.md",
}
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


class RendererResult:
    def __init__(self, returncode: int, detail: str) -> None:
        self.returncode = returncode
        self.detail = detail


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
        blockers = x.get("blocking_decision_ids", [])
        for bd in blockers:
            if bd not in decisions:
                add("CRITICAL", "decomp-decision-ref", f"{x['id']}:{bd}")
        # a placeholder that still claims blockers, yet every blocker is already
        # decided, is a stale contradiction the plan must not carry silently
        resolved = [bd for bd in blockers if decisions.get(bd, {}).get("status") == "decided"]
        if blockers and len(resolved) == len(blockers):
            add("CRITICAL", "decomp-stale-block", f"{x['id']}:{','.join(blockers)} all decided")

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


def file_sha256(path: Path) -> str:
    """Return the stable byte digest used for protected-history checks."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _ArchitectureHtml(HTMLParser):
    """Collect only the ownership markers needed by the documentation gate."""

    def __init__(self) -> None:
        super().__init__()
        self.language = ""
        self.states: list[str] = []
        self.links: list[str] = []
        self.ownership = ""
        self.ownership_verified = ""
        self.ownership_markers = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "html":
            self.ownership_markers += 1
            self.language = values.get("lang") or ""
            self.ownership = values.get("data-ownership") or ""
            self.ownership_verified = values.get("data-ownership-verified") or ""
        if tag == "section" and values.get("data-state"):
            self.states.append(values["data-state"] or "")
        if tag == "a" and values.get("href"):
            self.links.append(values["href"] or "")


def _is_archived_evidence_path(root: Path, value: str) -> bool:
    relative = value.split("#", 1)[0]
    path = Path(relative)
    if (
        not relative.startswith("openspec/changes/archive/")
        or path.is_absolute()
        or ".." in path.parts
    ):
        return False
    return (root / path).resolve().is_relative_to(root.resolve())


def run_fixed_renderer(root: Path, run_process=subprocess.run) -> RendererResult:
    renderer = root / "docs/diagrams/render-current-implementation.sh"
    if not renderer.is_file():
        return RendererResult(1, "renderer missing")
    try:
        result = run_process(
            [renderer, "--check"], cwd=root, shell=False, capture_output=True, text=True, timeout=30
        )
    except subprocess.TimeoutExpired:
        return RendererResult(1, "renderer timeout")
    except OSError as exc:
        return RendererResult(1, f"renderer execution: {exc}")
    return RendererResult(result.returncode, (result.stdout + result.stderr).strip())


def _violation(code: str, detail: str) -> Violation:
    return Violation("CRITICAL", code, detail)


def validate_parent_apply_status(text: str) -> list[Violation]:
    canonical = "## Status: Apply Complete — Ready for sdd-verify"
    headings = re.findall(r"^## .*", text, re.MULTILINE)
    statuses = re.findall(r"^## Status:.*", text, re.MULTILINE)
    if headings and headings[0] == canonical and statuses == [canonical]:
        return []
    return [_violation("apply-progress-status", "parent apply progress")]


def resolve_repo_path(root: Path, raw: str) -> Path | None:
    path = Path(raw)
    if not raw or "\\" in raw or path.is_absolute() or "." in path.parts or ".." in path.parts:
        return None
    resolved = (root / path).resolve()
    return resolved if resolved.is_relative_to(root) else None


def parse_candidate_paths(text: str) -> tuple[tuple[str, ...], list[Violation]]:
    blocks = re.findall(r"^## Candidate Paths$([\s\S]*?)(?=^## |\Z)", text, re.MULTILINE)
    if len(blocks) != 1:
        return (), [_violation("candidate-paths", "one block required")]
    lines = [line for line in blocks[0].splitlines() if line]
    paths = tuple(line.removeprefix("- path: ") for line in lines[1:])
    invalid = not lines or lines[0] != "schema: odoo-forge.changed-paths/v1" or not paths
    invalid |= any(not line.startswith("- path: ") for line in lines[1:])
    for path in paths:
        parsed = Path(path)
        invalid |= path not in CANDIDATE_PATHS or path != parsed.as_posix() or parsed.is_absolute()
        invalid |= "\\" in path or "." in parsed.parts or ".." in parsed.parts
    if invalid or len(set(paths)) != len(paths):
        return paths, [_violation("candidate-paths", "invalid candidate path block")]
    return paths, []


def validate_evidence_claims(plan: dict, root: Path) -> list[Violation]:
    root = root.resolve()
    catalog = plan["meta"].get("evidence_catalog", {})
    gaps = plan["meta"].get("gap_catalog", {})

    def collect(value: object) -> set[str]:
        if isinstance(value, dict):
            nested = set().union(*(collect(v) for v in value.values()))
            return set(value.get("evidence", [])) | nested
        if isinstance(value, list):
            return set().union(*(collect(v) for v in value)) if value else set()
        return set()

    active = collect(
        {key: plan.get(key, []) for key in ("items", "transfers", "edges", "decisions")}
    )
    violations: list[Violation] = []
    for evidence_id, location in catalog.items():
        relative = Path(str(location).split("#", 1)[0])
        path = root / relative
        valid = _is_archived_evidence_path(root, str(location)) and path.is_file()
        repo_path = relative.parts and relative.parts[0] in {"docs", "openspec", "tests"}
        supported = (
            repo_path
            and not relative.is_absolute()
            and ".." not in relative.parts
            and path.resolve().is_relative_to(root.resolve())
            and path.is_file()
        )
        if evidence_id in active and repo_path and not supported:
            violations.append(_violation("fabricated-evidence", evidence_id))
            continue
        unverifiable = evidence_id == "S62" or (str(location).endswith(".md") and not supported)
        if valid or supported or not unverifiable:
            continue
        if evidence_id == "S62" or evidence_id in active:
            violations.append(_violation("fabricated-evidence", evidence_id))
            continue
        matches = [
            gap
            for gap in gaps.values()
            if isinstance(gap, dict) and gap.get("evidence_id") == evidence_id and gap.get("reason")
        ]
        if not matches:
            violations.append(_violation("evidence-gap-missing", evidence_id))
    return violations


def validate_slice_policy(
    tasks_text: str, progress_text: str, changed_paths: list[str]
) -> list[Violation]:
    guards = (
        "Decision needed before apply: No",
        "Chained PRs recommended: Yes",
        "Chain strategy: feature-branch-chain",
        "400-line budget risk: High",
    )
    if not all(guard in tasks_text for guard in guards) or any(
        opposite in tasks_text
        for opposite in (
            "Decision needed before apply: Yes",
            "Chained PRs recommended: No",
            "budget risk: Low",
        )
    ):
        return [_violation("slice-policy-source", "parent tasks guards")]
    counts = [
        int(n) for n in re.findall(r"(\d+) (?:authored|changed)(?: changed)? lines", progress_text)
    ]
    counts += [
        int(a) + int(d) for a, d in re.findall(r"(\d+) additions \+ (\d+) deletions", progress_text)
    ]
    if not {387, 375, 109}.issubset(counts):
        return [_violation("slice-policy-source", "parent progress records")]
    violations = []
    if any(count > 400 for count in counts):
        violations.append(_violation("slice-budget", "parent measured slice"))
    if any("unit4" in path.lower() for path in changed_paths):
        violations.append(_violation("slice-unit4", "Unit4 path"))
    return violations


def validate_parent_verify_snapshot(
    root: Path, expected_hash: str = PARENT_VERIFY_SHA256
) -> list[Violation]:
    active = root / "openspec/changes/fix-roadmap-refresh-verification-closure/evidence"
    date = "[0-9]" * 4 + "-" + "[0-9]" * 2 + "-" + "[0-9]" * 2
    pattern = f"{date}-fix-roadmap-refresh-verification-closure/evidence"
    archived = list((root / "openspec/changes/archive").glob(pattern))
    locations = [active] if active.parent.is_dir() else archived
    if len(locations) != 1:
        return [_violation("parent-verify-snapshot", "missing or ambiguous evidence")]
    evidence = locations[0]
    snapshot = evidence / "parent-verify-fail.md"
    receipt = evidence / "parent-verify-fail.sha256"
    expected = f"{expected_hash}  parent-verify-fail.md\n"
    if not snapshot.is_file() or not receipt.is_file():
        return [_violation("parent-verify-snapshot", "missing evidence")]
    if file_sha256(snapshot) != expected_hash or receipt.read_text(encoding="utf-8") != expected:
        return [_violation("parent-verify-snapshot", "bytes or receipt")]
    return []


def validate_documentation(root: Path, run_renderer=run_fixed_renderer) -> list[Violation]:
    """Check bounded documentation ownership, links, and generated-output inputs."""
    violations: list[Violation] = []

    def add(code: str, detail: str) -> None:
        violations.append(Violation("CRITICAL", code, detail))

    diagrams = root / "docs/diagrams"
    source = diagrams / "odoo-forge-current-implementation.mmd"
    output = diagrams / "odoo-forge-current-implementation.mmd.svg"
    renderer = diagrams / "render-current-implementation.sh"
    renderer_valid = renderer.is_file() and file_sha256(renderer) == RENDERER_SHA256
    if not renderer_valid:
        add("fixed-renderer", str(renderer.relative_to(root)))
    else:
        result = run_renderer(root)
        if result.returncode:
            add(
                (
                    "renderer-execution"
                    if result.detail.startswith("renderer")
                    else "renderer-coherence"
                ),
                result.detail,
            )
    if not source.is_file() or not output.is_file():
        add("missing-derived-output", "Mermaid source or SVG output")

    html_path = root / "docs/specs/platform/platform-architecture.html"
    html_text = html_path.read_text(encoding="utf-8") if html_path.is_file() else ""
    parser = _ArchitectureHtml()
    parser.feed(html_text)
    if parser.language != "es":
        add("html-language", str(html_path.relative_to(root)))
    if (
        parser.ownership_markers != 1
        or parser.ownership != "hand-authored"
        or parser.ownership_verified != "true"
    ):
        add("html-ownership", str(html_path.relative_to(root)))
    for state, code in (("current", "html-current-label"), ("target", "html-target-label")):
        if parser.states.count(state) != 1:
            add(code, str(html_path.relative_to(root)))
    target = "../../diagrams/odoo-forge-current-implementation-guide.md"
    resolved = (html_path.parent / target).resolve()
    if (
        parser.links != [target]
        or not resolved.is_relative_to(root.resolve())
        or not resolved.is_file()
    ):
        add("html-guide-link", str(html_path.relative_to(root)))
    stale = (
        "no operational adapter",
        "pg dockerizado ya hecho",
        "solo docker local (4b) existe hoy",
    )
    if any(
        marker
        in f"{html_text}\n{source.read_text(encoding='utf-8') if source.is_file() else ''}".lower()
        for marker in stale
    ):
        add("stale-claim", "current implementation documentation")
    return violations


def validate_repository(root: Path, plan: dict) -> list[Violation]:
    """Validate repository-bound roadmap evidence without mutating any artifact."""
    root = root.resolve()
    violations: list[Violation] = []
    meta = plan["meta"]

    def add(code: str, detail: str) -> None:
        violations.append(Violation("CRITICAL", code, detail))

    s62 = meta.get("evidence_catalog", {}).get("S62", "")
    evidence_path = root / s62.split("#", 1)[0]
    if not _is_archived_evidence_path(root, s62):
        add("invalid-evidence-path", f"S62:{s62}")
    if not evidence_path.is_file():
        add("missing-evidence", f"S62:{s62}")

    changes = root / "openspec/changes"
    archive = changes / "archive"
    active = (
        {path.name for path in changes.iterdir() if path.is_dir() and path.name != "archive"}
        if changes.is_dir()
        else set()
    )
    corrective = "fix-roadmap-refresh-verification-closure"

    # Archived reality: the two stabilization changes must no longer linger as
    # active directories, and each must be closed under archive/ with the
    # documented-closure report proving its intended terminal state.
    forbidden_active = {"refresh-platform-roadmap-after-stabilization", "sp-data-environments"}
    still_active = active & forbidden_active
    if still_active:
        add("active-inventory", f"stabilization changes still active: {sorted(still_active)}")

    def _require_archived_closure(suffix: str, report: str) -> None:
        matches = (
            sorted(path for path in archive.glob(f"*-{suffix}") if path.is_dir())
            if archive.is_dir()
            else []
        )
        if len(matches) != 1:
            add(
                "active-inventory",
                f"expected exactly one archive/*-{suffix}, found {[p.name for p in matches]}",
            )
            return
        if not (matches[0] / report).is_file():
            add("active-inventory", f"{matches[0].name} missing {report}")

    _require_archived_closure("refresh-platform-roadmap-after-stabilization", "verify-report.md")
    _require_archived_closure("sp-data-environments", "archive-report.md")

    roadmap = root / "docs/specs/2026-07-14-stabilization-roadmap.md"
    roadmap_text = roadmap.read_text(encoding="utf-8") if roadmap.is_file() else ""
    required = (
        "CHG-FIRST-DATABASE-ADAPTER",
        "archived as superseded",
        "archive/2026-07-17-refresh-platform-roadmap-after-stabilization",
        "archive/2026-07-17-sp-data-environments",
    )
    if (
        any(marker not in roadmap_text for marker in required)
        or "PR #64" in roadmap_text
        or "Unit 3 is next" in roadmap_text
    ):
        add("stale-roadmap", str(roadmap.relative_to(root)))

    for relative, expected_hash in meta.get("protected_history_sha256", {}).items():
        path = root / relative
        if not path.is_file() or file_sha256(path) != expected_hash:
            add("protected-history", relative)

    violations.extend(validate_documentation(root))
    violations.extend(validate_evidence_claims(plan, root))
    child = changes / "fix-roadmap-refresh-verification-closure"
    if child.is_dir():
        (child / "apply-progress.md").read_text(encoding="utf-8")
    if child.is_dir() or any((changes / "archive").glob(f"*-{corrective}")):
        violations.extend(validate_parent_verify_snapshot(root))

    return violations


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

    violations = validate_plan(plan) + validate_repository(Path(args.root), plan)
    order = {"BLOCKER": 0, "CRITICAL": 1, "WARNING": 2}
    violations.sort(key=lambda z: order.get(z.severity, 9))
    if not violations:
        print("VALIDATOR: CLEAN — 0 violations")
        return 0
    print(f"VALIDATOR: {len(violations)} violations")
    for viol in violations:
        print(f"  {viol}")
    return 1 if any(x.severity in {"BLOCKER", "CRITICAL"} for x in violations) else 0


if __name__ == "__main__":
    raise SystemExit(main())
