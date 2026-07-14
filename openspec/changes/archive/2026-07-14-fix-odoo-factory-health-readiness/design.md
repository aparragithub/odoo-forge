# Design: Bootstrap Fresh Odoo Databases Before Readiness

## Technical Approach

Keep completed Child #1/2 behavior: a 300-second monotonic Docker-health deadline, recoverable non-healthy states, selected diagnostics, bounded logs, redaction, and created-only rollback. These remain useful defense-in-depth after bootstrap but are not the root-cause fix. Add one provider-owned bootstrap between PostgreSQL readiness and normal Odoo startup, only when this invocation created the Postgres-data volume.

## Architecture Decisions

| Decision | Choice and rationale |
|---|---|
| Newness authority | The provider's `_ensure_volume` creation result for `plan.postgres.volumes[0]`; it is already the ownership fact used by rollback. A reattached volume means an existing lifecycle, so no repair/adoption probe is allowed. |
| Bootstrap scope | Install only `base`; broader modules belong to application setup, not backend viability. |
| Container identity | Derive `<plan.odoo.name>-bootstrap`; preflight it with the normal Postgres/Odoo names and refuse any collision before creating resources. Never adopt or replace it. |
| Retained defenses | Keep 300 seconds and diagnostics: bootstrap removes schema absence, while cold normal startup can still be slow or fail and needs bounded, secret-safe evidence. |

## Bootstrap Contract

Construct a temporary `ContainerSpec`-equivalent from `plan.odoo`: same image, network, labels, environment, `secret_env`, addon mounts, and named filestore volume; distinct name; no published ports. Docker argv is explicit, foreground, and shell-free:

```text
docker run --name <odoo-name>-bootstrap --network <network>
  <labels> <secret mounts/env-file> <env> <filestore/addon mounts>
  <image> -i base --stop-after-init --no-http
```

The existing factory entrypoint supplies config and database arguments before these Odoo arguments. Exit code 0 is success. Any non-zero/Docker failure is bootstrap failure; bounded combined output is redacted with the existing resolved-secret and longest-first planned-value policy.

## Sequence and Cleanup

```text
preflight normal + bootstrap names
  -> pull image -> ensure network/volumes -> start Postgres -> PG ready
  -> if PG data volume created: run bootstrap foreground
       success -> docker rm bootstrap -> start normal Odoo -> Docker health
       failure -> capture/redact -> docker rm -f bootstrap -> rollback(created reverse) -> raise
  -> if PG data volume reused: start normal Odoo -> Docker health
```

Successful bootstrap removal MUST complete before normal creation. Removal failure is failure and triggers created-only rollback. The bootstrap container is tracked separately until removed so rollback orders it first, followed by normal/Postgres containers, newly created volumes, then network according to existing reverse ownership bookkeeping. Cleanup failures append residual details but do not replace the bootstrap cause. No failure preserves bootstrap for debugging.

Repeated `run` remains refuse-if-instance-exists. A stale bootstrap-name collision also refuses before provisioning. A failed invocation that cleans all created resources may be retried as a new lifecycle; an existing Postgres volume always suppresses bootstrap, even if incomplete.

## Files and Tests

| File | Change |
|---|---|
| `src/odoo_forge_docker/provider.py` | Newness result, bootstrap argv/execution, collision, diagnostics, ordered cleanup |
| `tests/adapters/test_docker_provider.py` | Strict-TDD command/order/newness/failure/redaction/rollback cases |

RED tests use the existing fake Docker router and credential injector. Assert exact bootstrap argv and ordering; base-only command; same image/network/env/secrets/mounts/filestore and no ports; new-volume-only execution; existing-volume skip; zero/non-zero exit; remove-before-normal; collision refusal; redacted logs; removal failure; created-only rollback. Then run focused, full, static, build, unchanged real-Docker, and factory smoke commands.

## Threat Matrix

| Boundary | Applicability | Response |
|---|---|---|
| Docker process argv | Applicable | Explicit argv, no shell; RED tests assert exact command, secret transport, exit handling, and redacted failure. |
| Documentation-like paths | N/A | No executable classification. |
| Git repository selection | N/A | No Git selection. |
| Commit state | N/A | No commit operation. |
| Push state | N/A | No push operation. |
| PR commands | N/A | No PR automation. |

## Delivery and Rollback

Feature Branch Chain: completed Child #1 targets tracker; completed Child #2 targets Child #1; autonomous Child #3 bootstrap targets Child #2; Phase 3 acceptance follows Child #3. Roll back Child #3 provider/tests without reverting the useful completed defenses. Factory, baseline harness, and baseline mutable-image-tag follow-up remain unchanged. Open questions: none.
