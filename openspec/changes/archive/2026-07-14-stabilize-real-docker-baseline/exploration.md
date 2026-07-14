## Exploration: stabilize-real-docker-baseline

### Current State
The local Docker backend is implemented in `odoo_forge_docker.provider.DockerBackendProvider` and is invoked by the `forge run`, `status`, and `stop` CLI commands. `run()` explicitly pulls the Odoo image, creates only missing networks and named volumes, starts Postgres, waits for TCP readiness, starts Odoo, waits for its Docker health status, and performs created-only reverse-order rollback. Credentials are materialized through `SopsEnvFileInjector`; they are not placed in the public environment plan, and the injector is cleared in `finally`. `stop()` removes containers and the network but intentionally preserves named Postgres and filestore volumes.

The existing real-daemon test is an unconditional `pytest.mark.integration` skip skeleton. The default pytest configuration excludes integration tests (`-m 'not integration'`), while the explicit integration command currently reports one skipped test. Unit tests cover argv construction, readiness seams, error classification, rollback bookkeeping, secret handling, ephemeral host ports, and status parsing, but cannot prove daemon behavior, image health timing, or actual residual cleanup. The canonical `openspec/specs/local-backend/spec.md` already defines the relevant lifecycle contract; this change should add runtime evidence rather than revise production behavior.

### Affected Areas
- `tests/adapters/test_docker_provider_integration.py` — replace the unconditional skip with the smallest disposable real-daemon `run -> status -> stop` scenario.
- `src/odoo_forge_docker/provider.py` — inspect-only target; current lifecycle, cleanup, secret, timeout, and ephemeral-port behavior appears sufficient, so production changes are not presently required.
- `src/odoo_forge_cli/main.py` — harness entry-point boundary for manifest-derived identity; no CLI change is indicated.
- `openspec/specs/local-backend/spec.md` — normative lifecycle, secret, volume, readiness, and status contract to validate; no delta is justified by exploration alone.
- `pyproject.toml` — existing integration marker and default opt-out are appropriate; CI/local gating should be documented or adjusted only if the implementation needs a repository-level command change.
- `docs/specs/2026-07-14-stabilization-roadmap.md` — authoritative execution guidance: Unit 1 requires no production behavior and a runtime receipt including Docker version, exact commands/results, and leak checks.

### Approaches
1. **Direct provider smoke test with a disposable fixture** — construct the smallest valid `BackendPlan` using the existing provider test helpers or an isolated temporary manifest/workspace, use a unique instance name, run the provider, assert both roles are running/ready and host ports are assigned, then always call `stop()` and inspect Docker for absent containers/network while confirming named volumes are handled according to the contract.
   - Pros: directly proves the adapter boundary and keeps the test narrowly scoped; no CLI subprocess nesting; cleanup can be enforced with `try/finally`.
   - Cons: requires stable construction of credential inputs and a usable Odoo image; real first boot can be slow.
   - Effort: Medium

2. **CLI round-trip harness** — create an isolated manifest and invoke `forge run`, `forge status`, and `forge stop` through Typer's test runner or subprocess, then inspect resources by labels/names.
   - Pros: validates command wiring and operator-visible output in addition to the daemon lifecycle.
   - Cons: broader than Unit 1, couples the smoke test to workspace scanning, manifest fixtures, credential-file discovery, and CLI output; it does not reduce Docker readiness risk.
   - Effort: Medium/High

### Recommendation
Use Approach 1 for this stabilization unit. Keep the integration test opt-in and marked `integration`; skip only when the Docker executable/daemon prerequisite is unavailable, with a clear reason, while failures after prerequisite detection MUST fail. Use a unique sanitized instance/project identity to avoid collisions, avoid fixed host ports (the provider already requests ephemeral mappings), and never place credentials in test argv, assertions, logs, or committed fixtures. Put cleanup in `finally`, attempt provider `stop()` after a successful or partially successful run, and add an independent label/name-based residual check for containers and network. Do not remove named volumes as part of the smoke test unless the test creates uniquely owned disposable volumes and explicitly needs to prove volume cleanup; the current `stop` contract preserves them, so the harness should record and remove only its own disposable leftovers in a final safety cleanup if required.

The default suite MUST remain unchanged and continue to exclude integration tests. The explicit local gate is `uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q`; CI SHOULD expose a Docker-enabled integration job separately rather than making ordinary unit jobs daemon-dependent. Set a bounded test-level timeout consistent with the provider's 180-second Odoo health floor, and avoid aggressive polling overrides that would invalidate the cold-boot contract. Record Docker client/server versions and exact commands/results in the later verification receipt. The change is expected to be test-only; any production defect discovered by the harness should be extracted into a separate SDD change rather than hidden in this baseline.

For delivery, forecast low authored change volume (well below the 400-line review budget), so the forced feature-branch-chain strategy has one implementation work unit: integration harness plus its test-only fixture/documentation changes, with rollback limited to those files. No production code, manifest contract, image policy, credential contract, or volume semantics should be changed here.

### Risks
- Odoo image availability, registry authorization, Docker daemon permissions, architecture compatibility, or cold first-boot duration can make local runs unavailable or slow; prerequisite skips must not mask post-start failures.
- A failed test before cleanup can leak containers, networks, or volumes; `finally` cleanup and an independent residual assertion are mandatory, with unique labels/names preventing interference with user workloads.
- Reusing a developer's real manifest or credentials could expose secrets or mutate meaningful workspace state; use an isolated disposable fixture and the existing credential-injection boundary.
- Preserved named volumes are intentional `stop` behavior, so “zero volumes after stop” would contradict the canonical spec; cleanup assertions must distinguish invocation-owned disposable resources from preserved lifecycle state.
- Real-daemon behavior may expose a genuine production defect in readiness, status parsing, or cleanup. Such a defect is out of scope for a test-only baseline and requires a separate proposal/design decision.

### Ready for Proposal
Yes. Proceed to proposal with a test-only scope, direct provider harness, explicit prerequisite/skip policy, unconditional cleanup, secret-safe isolated fixtures, and separate Docker-enabled CI/local gating. The proposal should state that production changes are not currently required and that any discovered adapter defect is extracted rather than folded into this baseline.
