# Design: CAP-CREDENTIALS

## Technical Approach

Keep the change contract-first. The proposal/spec define handle-only consumers, bounded plaintext lifetime, redaction, and approval evidence; they do **not** expand runtime scope. The PR 1 bridge is the existing `forge run` path, where the mixed baseline already transports opaque handles through `plan_backend()`. PR 2 remains responsible for replacing the final Docker launch boundary with SOPS-backed injection; this design does not claim that injector/provider work is complete.

## Architecture Decisions

| Decision | Options / Tradeoff | Decision / Rationale |
|---|---|---|
| Contract proof seam | Leave task 3.1 abstract vs wire one real in-repo path | Use `src/odoo_forge_cli/main.py -> src/odoo_forge/backend/plan.py -> src/odoo_forge_docker/provider.py` as the **minimal bridge**. It proves the contract on a real composition-root path without expanding Docker-specific product scope. |
| `CredentialHandle` ownership | Let planners/adapters mint handles vs bind once at composition root | Keep binding at CLI composition root. `src/odoo_forge/credentials/types.py` owns opaque types; planners/adapters only carry handles or descriptors. |
| Safe launch transport | Keep `docker run -e`, `--env-file`, or mount protected secret files | Use injector-owned `0600` secret files, bind-mounted read-only at `/run/secrets/<key>`, with only `<key>_FILE` pointers in Docker configuration. This keeps plaintext out of Docker argv, parent env, and container inspect/config output. |
| Readiness evidence anchor | Keep evidence implicit vs define approval ledger now | The mixed baseline already contains `DPROV-SECRETS`, `CAP-CREDENTIALS`, and `AC-CAP-CREDENTIALS-READY` pointers in `docs/specs/platform/portfolio.json`, with validator assertions that confirm SOPS and the proposed, gap-blocked acceptance state. Those pointers are not completion evidence; downstream handoffs remain blocked until the required runtime verification is complete. |

## Data Flow

```text
forge run
  -> bind backend slots to CredentialHandle values
  -> plan_backend(..., credentials=bindings)
  -> DockerBackendProvider.run(plan with opaque secret slots)
  -> SOPS injector resolves handles for this operation only
  -> write 0600 secret files
  -> docker run --mount .../run/secrets/<key> -e <key>_FILE=...
  -> unlink secret files in finally
```

## File Changes

| File | Action | Description |
|---|---|---|
| `src/odoo_forge/backend/plan.py` | Modify | Separate non-secret env from handle-backed secret slots in the local backend plan. |
| `src/odoo_forge/credentials/types.py` | Modify | Keep `CredentialHandle` capability-owned and add binding/injection shapes. |
| `src/odoo_forge/credentials/materialization.py` | Modify | Add the backend target shape used by the bridge while keeping opaque outputs. |
| `src/odoo_forge_docker/credential_injection.py` | Create | Resolve SOPS-backed handles into protected secret files and clean up. |
| `src/odoo_forge_docker/provider.py` | Modify | Replace secret-bearing Docker environment values with injector-owned read-only secret-file mounts. |
| `src/odoo_forge_cli/main.py` | Modify | Bind backend credential handles and inject the SOPS bridge at the composition root. |
| `tests/credentials/test_materialization.py` | Modify | Lock opaque descriptor, rejection, redaction, and lifetime rules. |
| `tests/adapters/test_docker_provider.py` | Modify | Prove argv/env/log redaction and env-file cleanup on success/failure. |
| `tests/cli/test_backend.py` | Modify | Prove task 3.1 composition-root wiring through `forge run`. |
| `docs/specs/platform/portfolio.json` | Existing mixed-baseline evidence | Retain the existing decision/readiness pointers and validator assertions; they document a proposed, gap-blocked gate and do not advance readiness. |

## Interfaces / Contracts

```python
class BackendCredentialBindings(BaseModel):
    postgres_password: CredentialHandle
    odoo_db_password: CredentialHandle

class ContainerSpec(BaseModel):
    env: dict[str, str]
    secret_env: dict[str, CredentialHandle] = {}

def plan_backend(..., credentials: BackendCredentialBindings) -> BackendPlan: ...
```

`BackendPlan`, refs, receipts, diagnostics, and subprocess argv/env must never carry plaintext; plaintext may exist only inside the injector during one launch attempt.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Planner keeps secret slots opaque; materialization returns only opaque descriptors | Pytest over `plan_backend()` and `materialize_for_target()`. |
| Integration | Launch path uses read-only secret-file mounts, cleans up on both paths, captures redacted readiness diagnostics, and reports rollback residuals | Docker provider tests with argv capture, temp-file assertions, and redacted errors. |
| E2E | Composition-root wiring for task 3.1 and readiness evidence inputs | CLI test proves `run()` binds handles. Existing portfolio validator assertions prove the decision/readiness pointer shape while preserving the proposed, gap-blocked acceptance state. |

## Threat Matrix

| Boundary | Status | Expected safe/failure behavior | Planned RED test |
|---|---|---|---|
| Routing | N/A — no routing surface | — | — |
| Shell commands | Applicable — local backend launch builds a Docker CLI argv | argv may contain only secret-file mount paths and `*_FILE` pointers, never plaintext `KEY=VALUE` or decrypted values | Assert recorded argv has mounts/pointers and no secret-bearing token |
| Subprocesses | Applicable — provider starts the `docker` subprocess | subprocess env remains non-secret; stderr/errors/logs stay redacted | Assert subprocess kwargs/env and raised messages contain no plaintext |
| VCS/PR automation | N/A — none | — | — |
| Executable-file classification | N/A — none | — | — |
| Process integration | Applicable — the bridge hands secrets to the final local target-native injection step | secret files are `0600`, mounted read-only, deleted on success/failure, and unsupported/plaintext-requiring targets fail closed before launch | Assert unlink on both paths and typed rejection before any docker call |

## Migration / Rollout

No migration required. The mixed baseline already contains the matching portfolio decision, capability, acceptance pointers, and validator assertions. SOPS is the approved first-store decision, but `AC-CAP-CREDENTIALS-READY` remains proposed and blocked by `G0` until the deferred injector/provider behavior and required runtime verification are complete. Downstream handoffs on `G15/G18/G24/G27/G30` remain blocked.

## Open Questions

- [ ] None.
