# SP-6 — CI/CD integration

**Layer:** Orchestration · **Status:** planned · **SDD change name (proposed):** `platform-cicd-integration`

## Purpose
This sub-project connects the control plane to an existing **CI/CD engine** so it can **trigger** and
**read** pipelines — implementing the `push → CI → build → CD` flow that is central to the vision
(§1, §4). Crucially, it enforces the **repo-only provenance** rule (§Principle 1): nothing deploys
outside the `git → CI` path, and a deploy is **gated by a pre-production DB test copy** (SP-2) that
must pass before CD proceeds to the target (SP-3).

The platform does **not** build a CI engine; it reuses GitHub Actions / GitLab CI and acts as the
conductor that starts pipelines and reacts to their results.

## Actor(s) served
**DevOps (operations)** primarily (§4 actor 2): "decides to apply an update → CI/CD runs against a
pre-production DB copy → on pass, deploys to the corresponding target". Also serves **Dev Jr**
indirectly — the push at the end of onboarding (§4 actor 1) enters this same flow.

## Port & adapters
Orchestration over SP-1/3/4 with a new **CI provider** port (chosen-at-init adapter, §Principle 3):
a `PipelineProvider` with **GitHub Actions** and **GitLab CI** adapters.

- `trigger(repo_ref, pipeline_ref, params) -> RunRef` — start a pipeline.
- `status(run_ref) -> PipelineStatus` — read live/terminal state.
- `artifacts(run_ref) -> ArtifactRefs` — read outputs (e.g. the built image digest).

The **flow orchestration** (build image via SP-1 → clone pre-prod DB via SP-2 → run tests → gate →
CD via SP-3) is pure domain logic in the control-plane core; the adapter only talks to the CI engine.

## What it reuses (does NOT build)
- **GitHub Actions / GitLab CI** — the runners, queueing, caching, and pipeline execution are the
  engine's job (§3 "what else is reused"). The platform triggers and reads; it does not execute jobs.
- **SP-1** image publish/pull, **SP-2** pre-prod DB copy + randomization, **SP-3** deploy targets.
- Existing repo webhooks/events where possible to observe `push`.

## Pointers, not copies
Stores **run references**, resulting **image digests**, and pass/fail gate outcomes — not pipeline
logs or artifacts at rest (§Principle 4). Logs/artifacts are read on demand from the CI engine.

## Scope
- `PipelineProvider` port + one adapter chosen at init; import-linter forbidden contract +
  `root_packages` entry for the adapter package.
- The `push → CI → build (SP-1) → pre-prod DB copy (SP-2) → test → gate → CD (SP-3)` orchestration
  as pure domain logic.
- Deploy gating: CD is blocked unless the pre-production DB test copy passes.
- Enforcement of §Principle 1: deploys only originate from a `git → CI` run.

## Non-goals
- No CI engine, runner, or job executor of its own.
- No new deploy targets (SP-3) or DB lifecycle ops (SP-2) — it composes them.
- No approval UI (SP-9) or request intake (SP-8).

## Dependencies
Upstream: **SP-1** (build/publish), **SP-3** (deploy target), **SP-4** (control plane + registry),
and **SP-2** (pre-prod DB gate). Ordered after SP-4/SP-5 in the build order (§7). Downstream: SP-8.

## Success criteria
- Trigger→status→artifacts round-trips against the chosen CI adapter (integration-tested).
- A failing pre-production DB test **blocks** CD; a passing one allows it (gate verified by test).
- No deploy path exists that bypasses `git → CI` (repo-only provenance regression guard).
- Flow orchestration is pure and import-linter-clean; the CI adapter is a dumb shell. Strict TDD.

## Open decisions
- Which CI engine is **default-at-init** for the first Mirgor deployment (GH Actions vs. GitLab CI).
- Trigger mechanism: webhook-observed `push` vs. control-plane-initiated dispatch.
- Where the pipeline definition lives (in-repo template owned by the platform vs. per-project).
- How the pre-prod DB test suite is defined and who owns it (overlaps SP-2 anonymization rules).
