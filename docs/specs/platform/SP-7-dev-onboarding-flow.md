# SP-7 — Dev onboarding flow

**Layer:** Experience · **Status:** planned · **SDD change name (proposed):** `platform-dev-onboarding-flow`

## Purpose
This sub-project delivers the **Dev Jr onboarding journey** (§4 actor 1) end to end: a developer
**requests an environment by client**, receives **editable source + a randomized DB** of that client,
**develops locally**, and **pushes** to a repo (which then enters the CI/CD flow owned by SP-6). It is
the first Layer 3 experience and the canonical "dev instance" (Model A: *editable source + a database*,
as opposed to the pre-built-image server instance of SP-1).

It builds no new external-concern port. It **composes** existing capabilities into a single guided flow.

## Actor(s) served
**Dev Jr (onboarding)** (§4 actor 1). Unblocks the full step: "Requests an environment by client →
receives code + a randomized DB → develops locally → pushes to a repo → CI".

## Port & adapters
Orchestration only — no new port. It composes:
- **`SourceProvider`** (git, Slice 2b) — deliver editable client source into the workspace.
- **`WorkspaceProvider`** + `plan_projection` / `materialize_state` (Slice 3) — project the workspace.
- **`DatabaseProvider`** (SP-2) — provision a **randomized/anonymized** DB of the requested client.
- **SP-4** control-plane API — register the resulting dev instance and its pointers.

## What it reuses (does NOT build)
- SP-2's randomization/anonymization (dev never gets real PII).
- The git `SourceProvider` + workspace projection foundation (Slices 2b/3) for source delivery.
- SP-4's registry for tracking the dev instance.
- Local docker backend (Slice 4b) for running the instance during development.

## Pointers, not copies
Registers the dev instance with its **repo URL + resolved SHA** and **DB connection ref** (a
randomized copy's ref) — no source or DB contents stored centrally (§Principle 4). The editable
source lives in the developer's local workspace; the DB lives in the DB provider.

## Scope
- "Request environment by **client**" intake mapped to a concrete manifest/source + randomized DB.
- Compose source delivery (SourceProvider + workspace projection) with DB randomization (SP-2).
- Register the dev instance in the SP-4 registry.
- Hand off to `push → CI` (SP-6) at the end — the flow ends at push; CI/CD is SP-6's domain.

## Non-goals
- No new port or adapter.
- No PROD/QA instance provisioning (SP-8).
- No CI/CD execution (SP-6) beyond initiating the push handoff.
- No web UI (SP-9) — this is the flow/orchestration; UI is layered separately.

## Dependencies
Upstream: **SP-2** (randomized DB), **`SourceProvider`** + workspace foundation, **SP-4** (registry/API)
(§6, §7). Benefits from SP-5 for role-scoped requests but is primarily gated by SP-2/SP-4.

## Success criteria
- A single request-by-client produces: delivered editable source + a registered dev instance with a
  **randomized** DB ref (no real PII), verified end to end.
- The developer can run the instance locally and push; the push is observable by the CI flow (SP-6).
- Orchestration logic is pure and import-linter-clean; all external work goes through existing
  adapters. Strict TDD.

## Open decisions
- How "request by client" resolves to a manifest/source + which client DB to randomize (config vs. lookup).
- Whether randomized DB provisioning is synchronous or async (long clones).
- Interaction with SP-5: is onboarding self-service or role-gated?
