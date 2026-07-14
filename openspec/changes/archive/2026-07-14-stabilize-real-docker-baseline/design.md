# Design: Stabilize the Real-Docker Baseline

## Technical Approach

Replace the skipped skeleton with one opt-in, direct `DockerBackendProvider` test. A test fixture creates a unique plan, injects generated credentials through `SopsEnvFileInjector`, selects a project-factory Odoo image, and exercises `run -> status -> stop`. It proves volume preservation, performs ownership-scoped cleanup, and independently checks residuals. Production behavior remains unchanged.

## Architecture Decisions

| Option | Tradeoff | Decision and rationale |
|---|---|---|
| Direct provider vs. CLI | Omits CLI parsing; avoids unrelated orchestration. | Use the smallest boundary proving Docker lifecycle behavior. |
| Build vs. select image | Building adds Buildx/yq/network failures. | Require `ODOO_FORGE_TEST_ODOO_IMAGE`; validate factory source/version labels. `factory/build.sh <version>` prepares it. |
| Production seam vs. fixture | A new seam expands production. | No production seam: private test helpers can use the existing constructor, image override, credential resolver, labels, and timeouts. |
| Prune vs. exact cleanup | Prune risks unrelated resources. | Delete only exact names with unique ownership labels. |
| Automatic vs. opt-in CI | A merge gate burdens daemon-free jobs. | Preserve default exclusion; permit a separate explicit Docker job. |

## Data Flow

```text
factory image ref + unique identity + generated secret
                 -> test-only BackendPlan
                 -> DockerBackendProvider.run (PG ready -> Odoo healthy)
                 -> status -> stop
                 -> preservation assertions -> final cleanup -> residual queries
```

## File Changes

| File | Action | Description |
|---|---|---|
| `tests/adapters/test_docker_provider_integration.py` | Modify | Replace the skip with the fixture, lifecycle assertions, cleanup, and evidence-friendly diagnostics. |

## Interfaces / Contracts

- `ODOO_FORGE_TEST_ODOO_IMAGE=<factory image ref>` is test-only and never persisted.
- Generate a random password in memory. The resolver returns it for opaque handles; arguments, output, failures, and evidence MUST exclude its value.
- Use a UUID-derived manifest/instance identity. Planner labels (`com.odoo-forge.project`, `instance`, `managed`, `role`) are the ownership proof.
- PostgreSQL remains the provider's official pinned `postgres:16`. Odoo ports remain `None` in the plan so Docker allocates host ports; assertions use inspected mappings.
- Provider readiness uses its bounded PostgreSQL and >=180-second Odoo deadlines; the runner may impose a larger outer timeout.

## Failure Modes and Cleanup

Only a missing Docker executable or unreachable daemon causes `pytest.skip`. Missing/invalid image selection, pull/auth failure, timeout, assertion, or cleanup failure fails. A `finally` block attempts exact owned container/network removal, then both volumes; errors accumulate. Independent name/label queries always follow, with redacted diagnostics.

After `stop`, containers/network MUST be absent and both volumes present. Final cleanup removes the volumes; residual reporting distinguishes preservation from leaks.

## Testing and Verification Strategy

| Layer | What | Approach |
|---|---|---|
| Focused integration | Factory image, pinned PostgreSQL, ephemeral mappings, readiness, live status, stop preservation, cleanup | `uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q` with the image selector. |
| Regression | Default daemon independence | `uv run pytest -q`; integration remains deselected. |
| Static boundaries | Test-only scope and architecture | `uv run ruff check`, `uv run mypy`, `uv run lint-imports`. |
| Verification receipt | Reproducibility and leaks | Record Docker client/server versions, commands/results, image labels, readiness/status, ports, preservation, cleanup, and residuals—never secrets. |

## Threat Matrix

| Boundary | Applicability | Design response / RED tests |
|---|---|---|
| Documentation-like paths | N/A — no executable classification. | None. |
| Git repository selection | N/A — no Git command or cwd selection. | None. |
| Commit state | N/A — no commit/index operation. | None. |
| Push state | N/A — no push/ref resolution. | None. |
| PR commands | N/A — no PR automation. | None. |

The Docker process boundary is outside these five rows. RED coverage replaces the skip: unavailable Docker skips; every later failure fails and still cleans up.

## Migration, Rollback, and Delivery

No migration or production rollout is required. Roll back only `tests/adapters/test_docker_provider_integration.py`; uniquely labelled leftovers can be removed by exact name after verification.

Forced Feature Branch Chain: one child under 400 authored lines contains harness and verification. A draft/no-merge tracker is the feature boundary; child #1 targets it. Start: skipped skeleton. End: passing runtime receipt and unchanged default suite. If over budget, split only at an independently verifiable fixture/evidence boundary; keep tests with behavior.

## Defect-Extraction Stop Rule

If the harness reveals a production provider defect, stop this unit, preserve the failing receipt and cleanup evidence, and open a separate SDD change. Do not alter production code or weaken assertions here.

## Open Questions

None.
