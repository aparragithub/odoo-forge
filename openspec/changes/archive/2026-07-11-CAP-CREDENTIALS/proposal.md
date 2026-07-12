# Proposal: CAP-CREDENTIALS

## Intent

Define the contract for credential materialization and force the unresolved `DPROV-SECRETS` decision so downstream platform changes can consume credential handles without persisting or exposing plaintext.

## Scope

### In Scope
- Select the first credential store via `DPROV-SECRETS`.
- Define the handle → resolution/materialization boundary, allowed plaintext lifetime, cleanup, and redaction rules.
- Define target-side injection / secret-ref handoff rules and acceptance evidence for `AC-CAP-CREDENTIALS-READY`.

### Out of Scope
- Multi-store support or a general `SecretsProvider` unless the chosen store proves the minimal shape insufficient.
- Consumer-specific implementation for database, remote backend, identity, pipeline, or control-plane runtimes.
- Runtime cutovers, tenancy policy, registry ownership, or replacing local-dev hardcoded backend credentials in this change.

## Capabilities

### New Capabilities
- `credential-materialization`: normative contract for opaque credential handles, first-store resolution, temporary materialization, redaction, and target-side injection.

### Modified Capabilities
- None.

## Approach

Use a contract-first proposal anchored in existing portfolio and platform docs. The change must resolve `DPROV-SECRETS` first, then specify one first-store capability that keeps consumers handle-only, keeps plaintext out of refs/state/logs/diagnostics, and leaves broader secrets-provider abstraction for a follow-up only if the store choice requires it.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `openspec/changes/CAP-CREDENTIALS/` | Modified | Proposal, later delta specs/design/tasks for this capability |
| `openspec/specs/` | New | Add canonical capability spec for credential materialization |
| `docs/specs/platform/portfolio.json` | Modified | Acceptance evidence and `DPROV-SECRETS` resolution handoff |
| `src/odoo_forge/credentials/` | Modified | Existing opaque handle surface informs the contract boundary |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Store decision inflates into speculative abstraction | Med | Limit this change to one first store and defer multi-store design |
| Plaintext leaks into refs, logs, env plans, or receipts | High | Make redaction and pointer-only boundaries normative |
| Consumer scope bleeds into this proposal | Med | Keep adapter/runtime behavior explicitly out of scope |

## Rollback Plan

Revert the proposal/spec artifacts and leave downstream changes blocked on `AC-CAP-CREDENTIALS-READY` until a corrected contract and `DPROV-SECRETS` decision are approved.

## Dependencies

- `docs/specs/platform/portfolio.json`
- `docs/specs/2026-07-08-platform-roadmap.md`
- `docs/specs/platform/SP-2-database-provider-and-lifecycle.md`
- `docs/specs/platform/SP-3-remote-backend-providers.md`
- `docs/specs/platform/SP-4-control-plane-core.md`

## Success Criteria

- [x] `DPROV-SECRETS` is resolved with SOPS as the approved first-store choice; approval is recorded in the change design.
- [ ] The accepted contract defines handle-only consumers, materialization boundaries, redaction, and target-side injection.
- [ ] `AC-CAP-CREDENTIALS-READY` evidence is sufficient for downstream changes without adding consumer-specific behavior.
