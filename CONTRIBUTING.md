# Contributing to odoo-forge

Thanks for considering it. This page tells you everything the automation
will enforce anyway — reading it first saves you a rejected PR.

## Where to start

Issues labeled [`good-first-issue`](https://github.com/aparragithub/odoo-forge/issues?q=is%3Aissue+is%3Aopen+label%3Agood-first-issue)
are small, well-scoped, and need no deep architecture knowledge. If you want
to work on something bigger, open an issue first and let's talk before you
write code.

## Setup

Python 3.11+ and [uv](https://docs.astral.sh/uv/); Docker only if you run
backend or integration tests.

```bash
git clone https://github.com/aparragithub/odoo-forge.git
cd odoo-forge
uv sync
```

## The quality gate

Run locally what CI will run — a PR cannot merge with a red gate:

```bash
uv run lint-imports          # architecture contracts (9, all must hold)
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest                # integration tests deselected by default
```

## The rules the bots enforce

1. **Every PR must close an open issue.** Put `Closes #N` in the PR body.
   The `require-linked-issue` check blocks the merge otherwise. Maintainers
   can apply the `no-issue` label for trivial chores — contributors should
   assume they need an issue.
2. **Conventional commits** (`feat:`, `fix:`, `docs:`, `chore:`, …).
3. **CodeRabbit reviews every PR** with an assertive profile and may request
   changes; its "changes requested" state blocks the merge until resolved.
   Argue with it if it is wrong — the maintainer can dismiss false positives.
4. **`main` is protected**: no direct pushes, no force pushes, required
   checks (`lint-and-test`, `require-linked-issue`) must pass — this applies
   to the maintainer too.

## Architecture boundaries (the short version)

The domain core (`src/odoo_forge/`) never imports adapters, the CLI,
`subprocess`, or network I/O — nine import-linter contracts fail the build
if it does. Adapters (`src/odoo_forge_*`) depend on the core's ports, never
on each other. If your change fights this shape, stop and open an issue:
either the design conversation is worth having, or the change belongs in an
adapter.

Two hard security contracts, enforced in review:

- secrets must never reach process argv, logs, or exception messages;
- workflow scripts read event payloads via `env`, never inline `${{ }}`.

## Tests

Behavior over implementation: assert what the code does, not how. Fast unit
tests run by default; anything touching a real daemon goes behind the
`integration` or `real_docker` markers.

## Security issues

Never open a public issue for a vulnerability — see [SECURITY.md](SECURITY.md).
