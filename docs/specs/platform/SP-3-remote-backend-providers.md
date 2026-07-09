# SP-3 — Remote BackendProvider adapters

**Layer:** Ports & adapters · **Status:** planned · **SDD change name (proposed):** `platform-remote-backends`

## Purpose
This sub-project extends the existing `BackendProvider` port — already implemented for **local
docker** in Slice 4b — with **remote deploy-target adapters**: EC2/VPS, Fargate, and Kubernetes.
No new port is introduced; the proven Slice 4b interface (`run` / `status` / `stop` / `logs` /
`exec`) is reused verbatim, and each new target becomes another interchangeable adapter behind it.

This realizes the "across multiple deployment targets" clause of the vision (§1) and the CD
destination for DevOps (§4 actor 2: "deploy to the corresponding target (EC2/VPS/Fargate/K8s)").

## Actor(s) served
**DevOps (operations)** primarily (§4 actor 2) — the target an approved update deploys to. Also
serves **control-plane users** whose PROD/QA instance requests must land on a real target (§4 actor 3).
Unblocks: "on pass, deploys to the corresponding target".

## Port & adapters
**Existing** `BackendProvider` port (no new port). New adapter packages, one per target, each chosen
at init and each a dumb shell over the target's native API/CLI:

- **EC2/VPS adapter** — provision/run containers on a VM (docker over SSH / cloud-init).
- **Fargate adapter** — run task definitions on ECS Fargate.
- **Kubernetes adapter** — apply/manage workloads via the cluster API.

Each must satisfy the same `run(plan) -> InstanceRef`, `status`, `stop`, `logs`, `exec` contract and
pass the port conformance test. **Recommendation: one target per slice** (§8) — deliver EC2/VPS
first, then Fargate, then K8s — so each adapter is independently proven.

## What it reuses (does NOT build)
Per §3 "what else is reused", each remote adapter defers to **target-native** infrastructure:
- **DNS / ingress / TLS** — ALB, ingress-nginx, Traefik (not built here).
- **Observability** — CloudWatch and target-native logging/metrics.
- **Secrets** — cloud secret managers.
- The `BackendPlan` / `ContainerRole` / `InstanceRef` domain from Slice 4b — reused, not redefined.

## Pointers, not copies
Stores **`InstanceRef` handles** and target coordinates (region, cluster, service ARN, host) — which
instance runs where — never runtime data or logs at rest. Logs are fetched on demand via `logs`
(target-native), consistent with §Principle 4.

## Scope
- New adapter package(s) implementing `BackendProvider` for the chosen target(s).
- Import-linter forbidden contract + `root_packages` entry per new adapter package.
- Mapping `BackendPlan` (from Slice 4b) onto each target's provisioning primitives.
- **Per-tenant data-plane isolation** — each backend adapter enforces network / namespace /
  DB-credential scoping so instances of different tenants cannot reach one another. The tenancy
  model is defined by SP-4; each adapter enforces it in its target-native way.
- **Secret injection** — wire secret-manager **refs** into the instance plan/env at deploy time
  (resolved from the target-native secret manager), never hardcoded plaintext env as in Slice 4b.
- CLI surface parity: `forge run/status/stop/logs/exec` work against the remote target.

## Non-goals
- No new port or change to the `BackendProvider` interface.
- No DNS/ingress/TLS/observability implementation (target-native, reused).
- No control-plane orchestration (SP-4) or CI/CD gating (SP-6).
- No multi-target fan-out at runtime (one adapter per init, §Principle 3).

## Dependencies
Foundation only — **Slice 4b (`BackendProvider` port + docker adapter + `BackendPlan`)**.
Independent of SP-1/SP-2. Upstream of SP-4, SP-6, SP-8 (§6, §7).

## Success criteria
- Each new adapter passes the `BackendProvider` conformance test (`isinstance` + `inspect.signature`).
- A full `run → status → exec → logs → stop` lifecycle succeeds against the target (integration-tested).
- Core stays pure: each adapter covered by its own import-linter forbidden contract; purity gate green
  (note: `boto3`/`kubernetes` are already in the core "forbidden" list).
- Strict TDD; adapters are dumb shells over target-native APIs, no domain logic leaks into them.

## Open decisions
- Which target is **default-at-init** for the first Mirgor deployment (§8).
- **One target at a time (recommended) vs. a batch** (§8).
- Per-target `BackendPlan` translation gaps (e.g. K8s needs manifests/Helm the plan does not yet model).
