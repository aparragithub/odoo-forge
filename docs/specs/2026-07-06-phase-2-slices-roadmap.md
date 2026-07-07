# Phase 2 — Vertical Slices Roadmap

**Status:** living document · **Last updated:** 2026-07-06

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

## Slice 2 — Resolution / Materialization ⏭️ NEXT

Turns declared *intent* into resolved, materialized sources. This is where I/O enters.

**Owns (deferred out of Slice 1):**
- **`core.ref: None → odoo_version` branch resolution at compose time.** Slice 1 accepts
  `core.ref = None` as valid unresolved intent and preserves it untouched; resolving it to
  a concrete branch name belongs here. (Slice 1 spec amendment + verify C1.)
- **Pin resolution — ref → commit SHA** into the lockfile (`resolve_ref()` on the port).
- **Concrete git `SourceProvider` adapter** (the network/git implementation behind the
  Slice 1 port interface).
- **`forge lock` CLI** — produces `project.lock`.
- **`project.lock` on-disk serialization format** — Slice 1's CLI chose plain JSON of
  `Lockfile.model_dump(mode="json")` ad hoc (verify W3); formalize it here, where the
  lockfile is actually written.

**Must design (not just execute):** *how* resolution behaves — read remote branch? assume
naming convention? fail when a ref does not exist? These are real design questions for the
Slice 2 explore/proposal, not carried-over tasks.

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
- `sdd/phase-2-manifest-core/verify-report` (#2289) — residual warnings (W2 fork-url test, W3 lock format).

## Non-blocking test debt (not a slice)

- **W2** — explicit fork-url override test; add when that area is next touched.
