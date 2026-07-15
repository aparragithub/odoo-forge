# Design: Docker Database Adapter Security Authority

## Technical Approach

Add a backend-local `LocalOwnershipAuthority` persisting signed records and an Ed25519 keyring under `${XDG_STATE_HOME:-~/.local/state}/odoo-forge/postgres-docker/`; labels only locate candidates. Provision through PostgreSQL's `_FILE` contract and a protected bind-mounted secret directory, never password environment variables. This closes `review-e272dab2cf939ee5` findings while preserving `DatabaseProvider`, opaque handoffs, redaction, `DPROV-DB`, local routing, and exclusions.

## Architecture Decisions

| Option | Tradeoff | Decision and rationale |
|---|---|---|
| Signed records / labels / service | Custody needs recovery; labels are forgeable; a service expands scope | Use local signed records: restart-durable without control-plane authority. |
| Ed25519 / HMAC | Adds `cryptography`; HMAC verifiers can mint | Ed25519 separates signing from verification and removes `_mint_runtime_ownership_evidence`. |
| Bind file + `_FILE` / env file / Swarm | Cleanup is explicit; env persists credentials; Swarm changes resources | Require Linux Docker Engine >=24 and official `postgres:16` `_FILE`; no fallback. |
| Recreate / migrate labels | Recreation disrupts; migration elevates metadata | Legacy/authority-less resources require recreation. |

## Components, State, and Trust Boundaries

- `authority.py` owns locking, records, rotation, and evidence. Its directory is `0700`; current-UID regular files are `0600`. Reject symlinks, wrong custody, unreadable data, unknown keys, bad signatures/schema, and generation regression.
- Canonical JSON records contain schema, authority/key IDs, generation, opaque operation, kind/name, immutable Docker ID, `reserved|active|retired`, and timestamps—never credentials. Under an exclusive lock, writes use same-directory `O_EXCL|O_NOFOLLOW` temporaries, file `fsync`, atomic `replace`, then directory `fsync`.
- Rotation creates a key, re-signs records, then activates it; old public keys remain through evidence expiry. Recovery requires a permission-valid matching state/key backup. Loss or coherent rollback requires recreation.
- `secret_injection.py` creates a `0700` directory/`0600` file, bind-mounts it, sets only `POSTGRES_PASSWORD_FILE`, deletes the file after readiness, verifies absence, and cleans every path.
- Trust boundaries: OS account/state directory, Docker socket, credential capability, container. Same-UID/root compromise is excluded.

## Data Flow

```mermaid
sequenceDiagram
    participant P as Provider
    participant A as Local Authority
    participant C as Credential Capability
    participant D as Docker
    P->>A: reserve operation (fsync)
    P->>C: resolve opaque handle to protected file
    P->>D: create/start with discovery label, bind, and _FILE path
    D-->>P: immutable container ID
    P->>A: bind ID and activate (fsync)
    P->>D: readiness check; delete mounted secret
    P-->>P: verify secret absence before returning
```

```mermaid
sequenceDiagram
    participant P as Provider
    participant A as Local Authority
    participant D as Docker
    P->>D: list label-matched candidates
    P->>A: verify signed active record
    A-->>P: expected immutable Docker ID
    P->>D: inspect ID and runtime state
    alt exact authority and runtime match
        P->>D: mutate, reconcile, rollback, or cleanup
        P->>A: retire/update record atomically
    else missing, legacy, tampered, or stale
        P-->>P: typed redacted refusal; recreate required
    end
```

## Interfaces and File Changes

| File | Action | Responsibility |
|---|---|---|
| `src/odoo_forge_postgres_docker/authority.py` | Create | Custody, records, evidence, rotation/recovery. |
| `src/odoo_forge_postgres_docker/secret_injection.py` | Create | `_FILE` injection/erasure. |
| `src/odoo_forge_postgres_docker/provider.py` | Modify | Authority-backed lifecycle; discovery labels. |
| `src/odoo_forge/database/readiness.py` | Modify | Verify signed claims with configured trust; remain pure. |
| `pyproject.toml`, `uv.lock` | Modify | Add `cryptography`. |
| `tests/adapters/test_postgres_docker_{authority,provider,integration}.py`, `tests/database/test_readiness.py` | Create/Modify | Security/real-Docker proof. |

Evidence binds authority/key, operation, immutable Docker ID, generation, observation/expiry, and nonce. The composition root supplies the trust set; callers cannot add keys. Verification rechecks current state and live identity, rejecting replayed, expired, imported, forged, or inspect-built claims.

## Failure Modes, Observability, and Rollback

Failures remain typed/redacted; logs contain operation ID, kind, phase, and reason code—never keys, signatures, credentials, Docker stderr, or records. Store failure prevents mutation. Create followed by failed activation reports incomplete rollback and strands the container; labels never authorize deletion. Chain rollback never restores `--env-file` or label authority and retains cleanup state.

## Testing Strategy and Delivery

RED-first tests cover custody, atomic crashes, tamper/loss, restart, rotation/recovery, replay/forgery, ID mismatch, legacy rejection, redaction, rollback, and erasure. Opt-in real-Docker tests prove authentication, daemon-restart reconcile/cleanup, foreign survival, final signed evidence, and password absence from `Config.Env`, labels, inspect JSON, argv/output, authority state, and host/container paths. Verification/archive evidence is regenerated only from final chain lineage; predecessor evidence is rejected. `review-093c1c067f361178` is never read, modified, validated, recovered, or passed to tooling.

Force a feature-branch chain, each green, rollbackable, and **<=400 changed lines**: (1) custody/store, (2) signing/rotation/evidence, (3) authority lifecycle, (4) file injection, (5) real-Docker/final-lineage proof. Split any oversized forecast.

## Threat Matrix

| Boundary | Applicability | Design response / RED tests |
|---|---|---|
| Documentation-like paths | N/A—no executable classification | None. |
| Git repository selection | N/A—no Git execution | None. |
| Commit state | N/A—no commit automation | None. |
| Push state | N/A—no push automation | None. |
| PR commands | N/A—no PR command composition | None. |

Docker subprocesses remain argv-only, identifier-validated, bounded, and redacted; tests reject shell strings, injected identifiers, unsupported runtimes, and failures before authority advances.

## Open Questions

None.
