# Tasks: First Docker PostgreSQL Database Adapter

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 700–900 total; 150–240 each |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 → PR 4 |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Docker argv runner and creator-label proof | PR 1; base=tracker | `uv run pytest tests/adapters/test_postgres_docker_provider.py -k 'command or proof'` | N/A: mocked subprocess safety | New package foundation and tests |
| 2 | Provision, readiness, reconcile, rollback, cleanup | PR 2; base=PR 1 | `uv run pytest tests/adapters/test_postgres_docker_provider.py -k 'provision or reconcile or cleanup or rollback'` | `docker version`; real lifecycle in PR 4 | Provider lifecycle and tests |
| 3 | Credential/artifact handoffs and restore | PR 3; base=PR 2 | `uv run pytest tests/adapters/test_postgres_docker_provider.py -k 'restore or redaction'` | N/A: target injectors are test doubles | Handoff module and restore behavior |
| 4 | Real-Docker acceptance and evidence receipt | PR 4; base=PR 3 | `uv run pytest tests/adapters/test_postgres_docker_provider_integration.py -m real_docker` | Same real-Docker command | Evidence, registration, portfolio entry |

## Phase 1: Foundation and Safety (PR 1)

- [x] 1.1 RED: in `tests/adapters/test_postgres_docker_provider.py`, prove hostile names never execute, timeout/nonzero failures are typed, secret stderr is absent, and mismatched live labels refuse mutation.
- [x] 1.2 GREEN: create `src/odoo_forge_postgres_docker/__init__.py` and `provider.py` with argv-only runner, typed redacted errors, labels, creator tokens, receipts, and live-label proof.
- [x] 1.3 REFACTOR: add protocol-conformance/typing tests; keep imports isolated from `odoo_forge_docker` and local-backend routing.

## Phase 2: Lifecycle (PR 2)

- [x] 2.1 RED: add tests for created-only provision, bounded `pg_isready`, reverse partial-failure rollback, reconcile, delete, cleanup, foreign-resource survival, and zero owned residuals.
- [x] 2.2 GREEN: implement lifecycle methods in `provider.py`; select only through `DPROV-DB`, without local PostgreSQL extraction or cutover.
- [x] 2.3 REFACTOR: verify receipt membership plus live labels on destructive paths and typed redacted unavailable/ownership outcomes.

## Phase 3: Handoffs and Restore (PR 3)

- [x] 3.1 RED: test `target_handoffs.py` for opaque credential injection, artifact-reference use, secret/byte redaction, and validation failure before any Docker mutation.
- [x] 3.2 GREEN: create `src/odoo_forge_postgres_docker/target_handoffs.py`; wire `CAP-CREDENTIALS` materialization and validated `CAP-DATA-ARTIFACTS` restore injection.
- [x] 3.3 REFACTOR: cover unavailable, incoherent, and integrity-invalid refs with fail-closed typed errors.

## Phase 4: Integration and Acceptance (PR 4)

- [ ] 4.1 RED: create opt-in real-Docker tests for provisioning/readiness, interrupted reconcile, partial rollback, restore, redaction, foreign survival, and complete cleanup.
- [ ] 4.2 GREEN: register package/markers in `pyproject.toml`; implement integration evidence with unique labels and `finally` cleanup.
- [ ] 4.3 REFACTOR: record only DPROV-DB evidence in `docs/specs/platform/portfolio.json`; run `uv run lint-imports`, `uv run mypy`, `uv run ruff check`, and default pytest. Preserve exclusions: WF-DATA-COPY, SP-CONTROL-PLANE-AUTHORITY, sp-data-environments, PublishedLayer/Override, and runtime cutover.
