## Exploration: CAP-CREDENTIALS

### Current State
`docs/specs/platform/portfolio.json` is the current planning authority. It defines `CAP-CREDENTIALS` as a proposed Security-owned prerequisite named **Credential Materialization**, with one acceptance gate, `AC-CAP-CREDENTIALS-READY`, and hard downstream edges to `CHG-FIRST-DATABASE-ADAPTER`, `CHG-FIRST-REMOTE-ADAPTER`, `CHG-FIRST-IDENTITY-ADAPTER`, `CHG-FIRST-PIPELINE-ADAPTER`, and `SP-CONTROL-PLANE-AUTHORITY`. The portfolio transfers `credential.materialization`, `credential.injection`, and `credential.resolution` into this capability from historical SP-2/SP-3/SP-4 planning.

The repository does not yet contain a credential contract or implementation. Current code only provides the opaque `CredentialHandle` type in `src/odoo_forge/credentials/types.py`. The active `DatabaseProvider` contract already depends on `CredentialHandle`, but treats it as an external opaque input and explicitly does not implement materialization. Current local runtime code still hardcodes local PostgreSQL credentials (`odoo`/`odoo`) inside `plan_backend()` for the Docker backend, which is evidence of today's gap rather than a reusable credential capability.

The core unresolved product/architecture decision is `DPROV-SECRETS`: choose the first credential store (`environment`, `SOPS`, `AWS Secrets Manager`, or `Vault`) and decide whether that choice still fits this capability shape or forces a more explicit secrets-provider abstraction. Existing documentation consistently says consumers should carry refs/handles, not plaintext, and that remote/control-plane flows should resolve secret-manager refs and inject them target-side without exposing plaintext through core models or orchestration state.

### Affected Areas
- `docs/specs/platform/portfolio.json` — authoritative scope, ownership, unresolved `DPROV-SECRETS`, acceptance gate, and downstream consumers.
- `docs/specs/2026-07-08-platform-roadmap.md` — current roadmap statement that secrets handling is still an open decision and may or may not remain a non-port concern.
- `docs/specs/platform/SP-2-database-provider-and-lifecycle.md` — historical evidence that database refs should carry credential handles, not secrets.
- `docs/specs/platform/SP-3-remote-backend-providers.md` — target-side secret injection requirement for remote adapters.
- `docs/specs/platform/SP-4-control-plane-core.md` — control plane must keep refs/pointers only and pass secret-manager refs without persisting plaintext.
- `src/odoo_forge/credentials/types.py` and `src/odoo_forge/credentials/__init__.py` — current capability surface is only an opaque handle declaration.
- `src/odoo_forge/ports/database_provider.py` and `openspec/specs/database-provider/spec.md` — accepted consumer boundary already requires `CredentialHandle` as an opaque external contract.
- `src/odoo_forge/backend/plan.py` — current local backend hardcodes credentials, showing why a reusable credential capability is still missing.
- `openspec/changes/CHG-FIRST-DATABASE-ADAPTER/exploration.md` — active downstream consumer explicitly blocked on `AC-CAP-CREDENTIALS-READY`.

### Approaches
1. **Contract-first credential capability with one selected first store** — define the credential handle, resolution/materialization, redaction, and target-side injection contract around the store chosen by `DPROV-SECRETS`, while keeping consumers handle-only.
   - Pros: Matches the current portfolio, resolves a real blocker for five downstream changes, and keeps plaintext out of provider values and control-plane state.
   - Cons: Requires an explicit store decision now; later multi-store support may need a follow-up abstraction.
   - Effort: Medium

2. **Promote immediately to a general `SecretsProvider` abstraction** — treat `CAP-CREDENTIALS` as a first-class multi-store provider contract before any single consumer ships.
   - Pros: Cleaner long-term abstraction if multiple stores are truly near-term.
   - Cons: The current portfolio does not require that larger abstraction yet, and `DP`/`DG` both favor minimal first delivery over speculative machinery.
   - Effort: High

3. **Let each downstream change solve credentials locally** — database, remote backend, identity, pipeline, and control plane each define their own secret resolution path.
   - Pros: Lowest immediate design effort for any one consumer.
   - Cons: Directly contradicts the portfolio prerequisite graph, duplicates security-sensitive behavior, and would make cross-cutting redaction/injection rules inconsistent.
   - Effort: High

### Recommendation
Use **contract-first credential capability with one selected first store**. Frame `CAP-CREDENTIALS` as solving this problem: the platform has opaque credential handles but no approved way to resolve, materialize, redact, and inject credentials for multiple downstream consumers without leaking plaintext or duplicating logic. Scope the next change to: select the first store via `DPROV-SECRETS`; define the normative handle-to-materialization boundary; define where plaintext may temporarily exist and how cleanup/redaction work; define target-side injection/ref handoff rules; and define acceptance evidence for `AC-CAP-CREDENTIALS-READY`. Do **not** include database artifacts, adapter-specific lifecycle logic, tenancy, durable operations, or control-plane registry/state ownership. Also do not assume a general multi-store provider unless the store decision proves the simpler capability is insufficient.

### Risks
- Starting implementation before resolving `DPROV-SECRETS` would invent the credential store and possibly the wrong abstraction level.
- Letting current local-backend hardcoded credentials shape the contract would leak a dev-only shortcut into a cross-platform capability.
- Allowing plaintext secrets into refs, provider values, CLI diagnostics, logs, or receipts would violate the repository's pointer-only and redaction direction.
- Pulling adapter-specific behavior into this capability would blur ownership and recreate the superseded SP-2/SP-3/SP-4 bundle.

### Ready for Proposal
Yes — if the proposal is explicitly framed as a contract-and-decision change, not an adapter implementation. The repository documentation is sufficient to justify the problem, downstream consumers, and scope boundaries. The proposal should force resolution of `DPROV-SECRETS`, define the minimal first-store capability, and keep unsupported multi-store or consumer-specific behavior out of scope.
