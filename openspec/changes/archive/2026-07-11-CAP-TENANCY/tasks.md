# Tasks: CAP-TENANCY

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~140–240 lines across 5 docs |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | single-pr |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

## Tasks

- [x] **Normalize the CAP-TENANCY source contract**
  - Update `openspec/changes/CAP-TENANCY/proposal.md`, `openspec/changes/CAP-TENANCY/specs/tenancy-contract/spec.md`, and `openspec/changes/CAP-TENANCY/design.md` so all three artifacts use the approved decisions verbatim: tenant = customer/client, canonical `tenant_id`, project as the only normative subordinate scope in v1, `PROD`/`QA`/`DEV` as operational classifications, `environment_family` not normative, quota authority exactly once, ownership composition with `created` / `adopted` / `external`, and `AC-CAP-TENANCY-READY`.
  - Keep this contract-first and prerequisite-only; do not add auth, persistence, provider, or control-plane implementation details.
  - **Verify:** focused diff review plus searches for disallowed tenancy redefinitions (`environment_family`, project as peer tenant, local quota authority, SP-4-defined tenancy).
  - **Rollback:** revert only the three CAP-TENANCY source artifacts.

- [x] **Align portfolio dependency and readiness metadata**
  - Update `docs/specs/platform/portfolio.json` to record `CAP-TENANCY` as the prerequisite tenancy capability and to position `SP-3`, `SP-4`, and `SP-8` as consumers of its contract rather than authors of tenancy/quota semantics.
  - Keep the change documentary; no runtime or schema work.
  - **Verify:** the portfolio entry still reflects the approved dependency order and readiness-gate language.
  - **Rollback:** revert `docs/specs/platform/portfolio.json` only.

- [x] **Normalize downstream consumer briefs to consume CAP-TENANCY**
  - Update `docs/specs/platform/SP-3-remote-backend-providers.md`, `docs/specs/platform/SP-4-control-plane-core.md`, and `docs/specs/platform/SP-8-instance-lifecycle-requests.md` so each doc states it consumes tenant scope, isolation expectations, ownership composition, and quota authority from `CAP-TENANCY`.
  - Remove or rewrite any language that treats tenancy/quota as local authority (for example SP-4 defining the tenancy model, or SP-8 keeping quota ownership).
  - Preserve each doc's own scope, non-goals, and actor-facing purpose; do not expand into implementation requirements.
  - **Verify:** targeted searches confirm `CAP-TENANCY` is the only tenancy authority and the downstream docs are consumer-only.
  - **Rollback:** revert each downstream doc independently.

- [x] **Final consistency sweep for readiness evidence**
  - Re-read all CAP-TENANCY artifacts plus the three downstream briefs and confirm `AC-CAP-TENANCY-READY` is sufficient to unblock later work without introducing auth, provider-specific enforcement, or control-plane implementation.
  - Confirm no task introduces runtime work by accident.
  - **Verify:** final search pass over the modified files plus a brief narrative check of the dependency chain.
  - **Rollback:** revert the last doc-edit batch only if the readiness story drifts.
