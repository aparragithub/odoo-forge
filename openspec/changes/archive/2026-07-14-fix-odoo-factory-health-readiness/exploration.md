## Exploration: fix-odoo-factory-health-readiness

### Current State

The blocked `stabilize-real-docker-baseline` child exercises `DockerBackendProvider.run()`. The provider pulls the selected Odoo image, creates PostgreSQL and Odoo, waits for PostgreSQL with a 30-second deadline, then waits for Docker health to become `healthy` with a 180-second deadline. Docker health is read from the container's `State.Health.Status`; the provider does not probe HTTP itself.

The factory image has a valid entrypoint and healthcheck:

- `factory/entrypoint.sh` copies and injects configuration, waits for PostgreSQL, then executes `odoo` with the generated database arguments.
- `factory/Dockerfile` exposes 8069/8072 and declares `curl -f http://localhost:8069/web/health` as its healthcheck (`start-period=60s`, `interval=30s`, `retries=3`).
- `factory/smoke-test.sh` independently booted the same local image against disposable PostgreSQL and passed its normal-server `/web/health` probe. This materially excludes a broken image healthcheck path, invalid startup command, image architecture, and a generally unusable factory image.

The blocked receipt reports Docker 29.6.1 on amd64, PostgreSQL reaching readiness, and Odoo logging `Waiting for PostgreSQL` followed by `PostgreSQL is ready!`, but Odoo never reached Docker `healthy` within 180 seconds. The provider run took 219.53 seconds including failure handling; cleanup and independent residual checks passed. The plan uses a fresh project database and the provider invokes the image's default `odoo` command, whereas the factory smoke test's normal-server phase uses an already initialized `smoke_test` database. This is the important behavioral difference: the provider cold-boots a newly initialized project database.

### Affected Areas

- `src/odoo_forge_docker/provider.py` — owns the 180-second Odoo health-readiness deadline and currently reports only that Docker health did not become healthy.
- `src/odoo_forge/backend/plan.py` — creates the fresh project database and supplies `DB_HOST`, `DB_PORT`, `DB_USER`, and `POSTGRES_DB` to the factory entrypoint; no evidence indicates the generated network or port plan is wrong.
- `factory/Dockerfile` — owns the healthcheck command and timing. The command/path is validated by the passing factory smoke test; changing it is not currently justified.
- `factory/entrypoint.sh` — owns PostgreSQL wait and Odoo startup/config injection. Its observed logs show the DB wait completed; no startup-command defect is proven.
- `tests/adapters/test_docker_provider_integration.py` — blocked evidence harness; it must remain unchanged by this exploration and must be rerun after the product fix.
- `openspec/changes/stabilize-real-docker-baseline/{proposal.md,specs/local-backend/spec.md,design.md,tasks.md,apply-progress.md}` — dependency and failing receipt that this change must unblock.

### Approaches

1. **Increase and make provider Odoo readiness cold-boot tolerant** — retain Docker HEALTHCHECK as the readiness contract, but give fresh database initialization a bounded deadline materially above the current 180 seconds and improve timeout diagnostics (health status and redacted logs).
   - Pros: smallest product-owned boundary; preserves image contract and test intent; addresses the observed provider-specific cold-start path.
   - Cons: increases worst-case wait; a true Odoo startup failure still needs useful diagnostics to distinguish it from slowness.
   - Effort: Medium

2. **Change the factory image healthcheck or entrypoint to expose a different readiness signal** — alter the image command/path or startup behavior.
   - Pros: could shorten or simplify health detection if a real image defect is found.
   - Cons: contradicted by the passing factory smoke test; changes a shared product image contract without evidence; risks masking fresh-database initialization latency.
   - Effort: Medium

3. **Modify the integration harness to pre-initialize or bypass the fresh database** — make the test resemble the smoke test rather than exercising the canonical provider plan.
   - Pros: likely makes the test pass faster.
   - Cons: harness misuse against the stated `run` contract; would hide the provider defect and violate the baseline's defect-extraction stop rule.
   - Effort: Low

### Recommendation

Treat this as a Docker-provider readiness defect candidate, not a factory-image or harness defect. The smallest fix boundary is `src/odoo_forge_docker/provider.py`: preserve Docker health as the signal, extend the bounded Odoo readiness budget for cold fresh-database startup, and retain redacted diagnostics. Do not change the factory healthcheck, startup command, image labels, architecture assumptions, or the blocked harness without new contradictory evidence.

Before proposal/apply, reproduce the provider scenario with a uniquely named disposable plan and capture `docker inspect` health status plus redacted Odoo logs at timeout. Exact unblock evidence is: the unchanged command
`ODOO_FORGE_TEST_ODOO_IMAGE=ghcr.io/aparragithub/odoo-ce:19 uv run pytest -m integration tests/adapters/test_docker_provider_integration.py -q`
must complete `run -> status -> stop`, report Odoo healthy, preserve both volumes until final cleanup, and leave no owned containers, network, or disposable volumes. The factory smoke test must remain passing, and no unrelated Docker resources may be removed.

### Risks

- A longer deadline can hide a genuine startup regression unless timeout diagnostics identify the last health state and redacted logs.
- First-use database initialization time is host- and image-dependent; the deadline should remain bounded and evidence-based rather than unlimited.
- The exact Odoo log excerpt after `PostgreSQL is ready!` is not present in the saved receipt, so the conclusion is a high-confidence defect classification, not a proof of one internal Odoo code path.
- The blocked baseline has 0/12 tasks complete and must not be marked green until the unchanged harness passes.

### Ready for Proposal

Yes. The proposal should target the Docker provider readiness boundary, explicitly preserve the factory image contract and baseline harness, require timeout diagnostics, and link back to the blocked baseline receipt as the acceptance/unblock evidence.

## Exploration Update: contradictory runtime evidence (2026-07-14)

### New Evidence

The unchanged provider acceptance was rerun with the Child #2 diagnostics and a 300-second deadline. It still failed after 307.01 seconds. The terminal receipt is:

- `final_health=unhealthy`
- `FailingStreak=8`
- Odoo logs contain `KeyError: 'ir.http'`
- Odoo reports the relation `ir_module_module` is missing
- provider-owned cleanup is clean: exact-name checks found no residual containers, network, or volumes
- focused/full/static/build checks mostly pass; `mypy` fails separately at `tests/adapters/test_docker_provider_integration.py:75` because `BaseModel` has no attribute `labels`
- factory smoke was not rerun because the provider acceptance failed

This contradicts the previous “valid cold start may merely exceed 180/300 seconds” conclusion. The failure is not a readiness-budget problem: Odoo is starting against a database whose core schema has not been initialized.

### Compared Execution Paths

The provider path is:

1. `plan_backend()` assigns `POSTGRES_DB` and `--database` to the fresh project database.
2. `DockerBackendProvider.run()` starts Postgres, waits for TCP readiness, then starts one Odoo container using the image default `CMD ["odoo"]`.
3. `factory/entrypoint.sh` converts that default launch into `odoo -c /tmp/odoo.conf --db_host ... --database <project-db>` after waiting for PostgreSQL.
4. No `--init`, `-i base`, or `--stop-after-init` phase exists in this path.

The passing factory smoke path explicitly performs initialization first:

```text
odoo -d smoke_test -i base,sale,purchase,stock --stop-after-init --no-http
```

Only after that one-shot initialization does it launch the normal server with `odoo -d smoke_test` and probe `/web/health`. Therefore the smoke result does not validate a fresh, uninitialized database under the provider’s one-process startup contract.

### Revised Root Cause

The evidence now supports a high-confidence orchestration/initialization defect, not a factory healthcheck timing defect. The provider creates the database through PostgreSQL but does not make Odoo own the required core-module initialization before declaring the long-running server ready. `KeyError: 'ir.http'` and missing `ir_module_module` are schema/module bootstrap failures; extending Docker health polling cannot repair them.

The factory entrypoint and healthcheck remain internally consistent for the smoke contract, but the provider invokes them with a materially different database lifecycle. The prior recommendation to change only the readiness deadline is superseded by this evidence.

### Smallest Evidence-Backed Fix Boundary

The fix should move from readiness polling to an explicit provider-owned bootstrap phase, preferably in `DockerBackendProvider` orchestration with a small plan/command extension:

- create the database/network/volumes as today;
- run a disposable Odoo initialization command against the planned database, equivalent to `-i base --stop-after-init --no-http` (with the provider’s existing credentials and mounts);
- only after successful initialization start the long-running Odoo container and retain Docker health as the readiness authority;
- preserve created-only rollback and the existing secret-safe diagnostics.

This keeps initialization ownership in the backend lifecycle rather than making every factory launch implicitly mutate databases. A factory entrypoint change is an alternative only if implementation constraints make a provider bootstrap impossible; it is now permitted by the contradictory evidence but is not the smallest boundary. A readiness-only change, a larger timeout, or test pre-initialization is no longer evidence-backed.

### Options Rejected or Deferred

1. **Increase the deadline further** — rejected; the terminal error proves schema absence, not slow recovery.
2. **Pre-initialize in the integration test** — rejected; it would hide the provider lifecycle defect.
3. **Always initialize inside `factory/entrypoint.sh`** — deferred; it changes shared image semantics and may impose repeated module initialization on already initialized databases.
4. **Provider bootstrap before normal server startup** — recommended; matches the passing smoke sequence while preserving the canonical provider contract.

### Exact Unblock Evidence

After the bootstrap implementation, rerun the unchanged provider command and require all of the following: successful `run -> status -> stop`; Docker health `healthy`; no `ir.http`/`ir_module_module` bootstrap errors; lifecycle volumes preserved until `stop`; no owned residuals; and the same focused/full/static/build checks. Then rerun `./factory/smoke-test.sh ghcr.io/aparragithub/odoo-ce:19` to confirm the factory contract remains intact. The separate mypy harness annotation issue must be tracked independently and must not be used as evidence for the runtime diagnosis.

### Revised Recommendation

Do not implement a provider timeout increase as the final fix. Update the proposal/design/tasks in a later planning step to replace “readiness-only” scope with “provider-owned fresh-database bootstrap followed by Docker-health readiness.” Keep factory files and the unchanged harness untouched unless the bootstrap reproduction produces new evidence directly implicating entrypoint behavior.
