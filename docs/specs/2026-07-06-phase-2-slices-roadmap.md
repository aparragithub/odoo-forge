# Phase 2 — Vertical Slices Roadmap

**Status:** living document · **Last updated:** 2026-07-07

Phase 2 (CLI core + manifest + local backend) is delivered as vertical slices, each a
self-contained SDD change. This is the forward map: what each slice owns and what feeds
it. Authoritative scope boundaries were set in the Slice 1 proposal (Out of Scope) and
design; this doc consolidates them so the next slice starts from a known line, not memory.

Source of truth for Slice 1 boundaries:
`openspec/changes/archive/2026-07-06-phase-2-manifest-core/{proposal,design}.md`.

---

## Slice 1 — Manifest Core ✅ DONE (archived 2026-07-06)

Pure manifest/lockfile domain, no I/O.

- Pydantic v2 schema (`Manifest`/`Lockfile`, `core` field, `requires_edition` gating,
  discriminated `Layer` union).
- Onion composition (order + coherence) and pure `detect_drift(manifest, lock, materialized)`.
- `SourceProvider` **port (interface only)**.
- Thin `forge validate` CLI; import-linter purity gate from commit one.

Baseline spec: `openspec/specs/manifest/spec.md`.

---

## Slice 2a — Pure Resolution Prep ✅ DONE (archived 2026-07-07)

Foundation work — pure logic only, zero I/O, no new runtime deps.

- **Default-ref substitution helper** — `resolve_default_ref(core, odoo_version) -> str`, pure function that returns `odoo_version` when `core.ref is None`, else echoes `core.ref` unchanged.
- **Lockfile serialization contract** — formalized JSON schema (add `schema_version: int` field starting at 1), deterministic key ordering, byte-stable round-trip (`to_canonical_json()` / `from_json()`).
- **Drift back-compat regression** — confirm legacy (Slice-1-era) locks without `schema_version` validate and yield identical `DriftReport` results.
- **Spec amendment** — update `openspec/specs/manifest/spec.md` with new Req 1 (default-ref helper) and Req 2 (canonical lockfile format). Resolves verify-report **W1** (naming divergence) with method names `to_canonical_json()`/`from_json()`.
- **W3 debt closed** — lockfile-format debt formalized; no longer a residual warning.

Baseline spec: `openspec/specs/manifest/spec.md` (amended 2026-07-07).

---

## Slice 2b — Git Resolution & Lock Writer ⏭️ NEXT

Turns declared *intent* into resolved, materialized sources. This is where I/O enters.

**Owns (deferred out of Slice 1 + Slice 2a):**
- **Concrete git `SourceProvider` adapter** (new package, e.g. `odoo_forge_git`; the network/git implementation behind the Slice 1 port interface).
- **Pin resolution — ref → commit SHA** into the lockfile (`resolve_ref()` on the port, using `git ls-remote` via subprocess).
- **`forge lock` CLI** — produces `project.lock` by composing a manifest, substituting default refs (from 2a), and calling the concrete adapter to resolve SHAs.
- **Error taxonomy for ref-not-found / auth-failure** — explicit error classes in `errors.py` for resolution failure modes.
- **Import-linter third contract** — add forbidden-import contract for the new adapter package (target: 3 kept / 0 broken, preserving core purity).

**Must design (not just execute):** *how* resolution behaves on network failure, missing credentials, or stale/moved refs. These are real design questions deferred from Slice 2 explore, now ready for Slice 2b.

---

## Slice 3 — Workspace Projection

Projects composed + materialized layers onto the developer's filesystem.

- Workspace projection.
- `Layer.name → /mnt/*` mount-root mapping.
- `unlock`.

---

## Slice 4 — Local Docker Backend

- Local Docker backend.
- HTTP / registry client libraries (not called by any earlier slice).

---

## Cross-session pointers (Engram)

- `sdd/phase-2-manifest-core/scope-boundary` (#2290) — why core.ref resolution was deferred.
- `sdd/phase-2-manifest-core/archive-report` (#2291) — Slice 1 close + deferred list.
- `sdd/phase-2-manifest-core/verify-report` (#2289) — residual warnings (W2 fork-url test, W3 ~~lock format~~ CLOSED).
- `sdd/phase-2-slice-2a-resolution-prep/archive-report` (#TBD) — Slice 2a close + Slice 2b handoff.

## Non-blocking test debt (not a slice)

- **W2** — explicit fork-url override test; add when that area is next touched.
