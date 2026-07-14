# Tasks: Bootstrap Fresh Odoo Databases Before Readiness

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated authored change | 620-820 lines |
| Completed prerequisite slices | Child #1 readiness/recovery; Child #2 diagnostics/redaction |
| New autonomous slice | Child #3 bootstrap, estimated 220-340 lines |
| Delivery strategy | force-chained |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Boundary | Focused test | Runtime | Rollback |
|---|---|---|---|---|
| 1 (complete) | Child #1, base=tracker: readiness/recovery | `uv run pytest tests/adapters/test_docker_provider.py -q` | N/A: fake clock | Revert 300s/recovery only |
| 2 (complete) | Child #2, base=Child #1: diagnostics/redaction | Same focused command | Failed baseline produced schema evidence | Revert diagnostics only |
| 3 (complete) | Child #3, base=Child #2: bootstrap | Same focused command | Passing baseline consumes bootstrap GREEN | Revert bootstrap only |

## Phase 1: Completed Prerequisite RED Coverage

- [x] 1.1 Characterize the 180-second default and require a 300-second default while retaining the constructor override.
- [x] 1.2 Cover recovery from `unhealthy` and retrying missing, unknown, and `starting` Docker health states.
- [x] 1.3 Add RED tests for selected inspect fields, bounded combined logs before cleanup, and unavailable fallback markers.
- [x] 1.4 Add RED tests for resolved-secret and planned-environment-value redaction, including longest-first replacement.
- [x] 1.5 Prove created-only timeout rollback preserves reattached volumes, including incomplete container cleanup.

## Phase 2: Provider Implementation and Child #3 Bootstrap

- [x] 2.1 Set the provider-owned Docker health deadline default to 300 seconds.
- [x] 2.2 Capture selected inspect state and `docker logs --tail 200` stdout/stderr before created-only rollback.
- [x] 2.3 Redact resolved credentials and all non-empty planned env values before diagnostic composition.
- [x] 2.4 RED in `tests/adapters/test_docker_provider.py`: exact shell-free `<odoo>-bootstrap` argv uses the planned image/network/env/opaque secrets/mounts/filestore, no ports, and only `-i base --stop-after-init --no-http`.
- [x] 2.5 RED: bootstrap runs only when this invocation creates the Postgres-data volume; reused incomplete lifecycles are not repaired; bootstrap-name collision refuses before provisioning.
- [x] 2.6 RED: exit 0 removes bootstrap before normal Odoo; non-zero, Docker error, or removal failure prevents normal startup, redacts bounded output, removes bootstrap, and rolls back only created resources in order.
- [x] 2.7 GREEN in `src/odoo_forge_docker/provider.py`: expose volume-created authority internally, execute/remove the temporary bootstrap, preserve primary/cause diagnostics, then start normal Odoo and existing health readiness.
- [x] 2.8 REFACTOR green code; keep orchestration private, explicit-argv, collision-safe, and independent of public plan/CLI/factory contracts.

## Phase 3: Acceptance and Evidence Gate

- [x] 3.1 Run `uv run pytest tests/adapters/test_docker_provider.py -q`, `uv run pytest -v`, `uv run ruff check`, `uv run mypy`, `uv run lint-imports`, and `uv build`; exact passing results are recorded by the baseline receipt.
- [x] 3.2 Consume the exact passing baseline receipt for `ODOO_FORGE_TEST_ODOO_IMAGE=ghcr.io/aparragithub/odoo-ce:19 uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q`; it proves bootstrap-before-normal, healthy `run -> status -> stop`, preserved volumes, clean owned rollback/residuals, and no schema/secret errors.
- [x] 3.3 Consume the recorded `./factory/smoke-test.sh ghcr.io/aparragithub/odoo-ce:19` receipt. Keep factory unchanged; leave the mutable-image-tag warning in the baseline SDD follow-up.
