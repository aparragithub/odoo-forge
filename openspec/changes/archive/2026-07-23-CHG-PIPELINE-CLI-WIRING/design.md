# Design: Wire the GitHub Actions Pipeline Adapter into the CLI

## Technical Approach

Mirror `commands/image.py` + `_composition.py`'s `_make_image_registry_provider`
exactly: a new `_make_pipeline_provider()` factory builds
`GitHubActionsPipelineProvider` over `GitHubActionsRestTransport` from four
env vars; a new `commands/pipeline.py` exposes `trigger`/`status` Typer
commands that call the factory, convert args to neutral types, and catch a
broad error surface into one `error: ...` line. Registered in `main.py` like
`backend`/`image`/`maintenance`/`manifest`. Fulfils `pipeline-cli-command`;
`pipeline-provider`/`github-actions-pipeline-adapter` are untouched.

## Architecture Decisions

| Decision | Choice | Alternatives considered | Rationale |
|---|---|---|---|
| Import-linter direction | CLI → adapter import is **allowed** — no code change needed | Add new contract entry | `pyproject.toml`'s only pipeline contract forbids `odoo_forge` (core) → `odoo_forge_pipeline_github`; nothing forbids `odoo_forge_cli` → adapters. `_composition.py` already imports `odoo_forge_docker`, `odoo_forge_git`, `odoo_forge_registry` directly — same edge shape, already precedented |
| Env var names | `FORGE_PIPELINE_GITHUB_{TOKEN,OWNER,REPO,REF}` | Reuse ambient `GITHUB_TOKEN`/`GITHUB_REPOSITORY` (Actions' own vars) | Ambient GH Actions vars would silently leak CI-runner identity into local/other invocations; an explicit `FORGE_`-prefixed name is unambiguous and matches the `SOPS_AGE_KEY_FILE` override precedent |
| Missing-env-var error | New `PipelineConfigurationError(RuntimeError)` raised by the factory, message names only the missing var | Return `None`/sentinel and fail later inside the provider | Fails fast, at the composition boundary, with a message that is safe to print (var name only, never a value) — satisfies "no silent default for token" and "never echo token" |
| Command error surface | Commands catch `(OSError, RuntimeError, ValueError)` around factory + provider call | Define a new typed domain error in the adapter package | Adapter package is explicitly out of scope for this change; `provider.py`/`transport.py` currently raise plain `RuntimeError` ("no runs found") and `urllib.error.URLError`/`HTTPError` (both `OSError` subclasses) — no adapter-level error type exists yet. Catching this exact built-in surface satisfies the spec's "single `error:` line" requirement without touching the adapter. Flagged as an open follow-up (adapter should gain a typed error) |
| Output shape | `trigger` echoes bare `run_ref.run_id`; `status` echoes bare `status.state` | Echo full pydantic `repr()`/JSON | Matches `image.py`'s scalar-string echo convention; scriptable, no schema commitment beyond what the spec requires |
| `--param` parsing | Repeatable `--param KEY=VALUE`, joined into `PipelineRunSpec.parameters: dict[str, str]` | Single `--params` JSON blob | Simple, typo-safe, Typer-idiomatic; malformed entries (no `=`) raise `ValueError`, caught by the same error path |

## Data Flow

    CLI args ──▶ pipeline.py ──▶ _composition._make_pipeline_provider()
                     │                     │
                     │            env vars (token/owner/repo/ref)
                     │                     ▼
                     │        GitHubActionsPipelineProvider(transport=GitHubActionsRestTransport)
                     ▼
          PipelineRunSpec / PipelineRunRef ──▶ provider.trigger()/status() ──▶ typer.echo(...)
                                                        │
                                          OSError | RuntimeError | ValueError
                                                        ▼
                                          "error: ..." (stderr) + exit(1)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/odoo_forge_cli/_composition.py` | Modify | Add `_make_pipeline_provider()`, `_require_pipeline_env()`, `PipelineConfigurationError` |
| `src/odoo_forge_cli/commands/pipeline.py` | Create | `trigger`/`status` Typer commands + `register(app)` |
| `src/odoo_forge_cli/main.py` | Modify | Import + register `pipeline` |
| `tests/cli/test_pipeline.py` | Create | `CliRunner` + `_composition` monkeypatch, mirrors `test_image_registry.py` |
| `pyproject.toml` | None | No import-linter change needed (see decision above) |

## Interfaces / Contracts

```python
# _composition.py
class PipelineConfigurationError(RuntimeError):
    """Raised when a required pipeline env var is unset."""

def _require_pipeline_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise PipelineConfigurationError(f"missing required environment variable: {name}")
    return value

def _make_pipeline_provider() -> PipelineProvider:
    token = _require_pipeline_env("FORGE_PIPELINE_GITHUB_TOKEN")
    owner = _require_pipeline_env("FORGE_PIPELINE_GITHUB_OWNER")
    repo = _require_pipeline_env("FORGE_PIPELINE_GITHUB_REPO")
    ref = _require_pipeline_env("FORGE_PIPELINE_GITHUB_REF")
    transport = GitHubActionsRestTransport(token=token, owner=owner, repo=repo)
    return GitHubActionsPipelineProvider(transport=transport, owner=owner, repo=repo, ref=ref)

# commands/pipeline.py
def trigger(
    workflow: str = typer.Option(..., "--workflow"),
    param: list[str] = typer.Option([], "--param", help="KEY=VALUE, repeatable"),
) -> None: ...  # -> typer.echo(run_ref.run_id)

def status(run_id: str = typer.Option(..., "--run-id")) -> None: ...  # -> typer.echo(status.state)

def register(app: typer.Typer) -> None:
    app.command(name="pipeline-trigger")(trigger)
    app.command(name="pipeline-status")(status)
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit (`_composition`) | Missing env var raises `PipelineConfigurationError` naming the var; all-present builds provider | monkeypatch `os.environ`, no network |
| Unit (CLI) | `pipeline-trigger`/`pipeline-status` success paths, arg→spec/ref mapping, exit 0 | `CliRunner` + fake provider via `monkeypatch.setattr(_composition, "_make_pipeline_provider", ...)` |
| Unit (CLI) | Provider raises `OSError`/`RuntimeError` → single `error:` line, exit 1, no traceback | same fake, parametrized error injection |
| Unit (CLI) | Malformed `--param` (no `=`) fails fast before provider call | assert fake's call log stays empty |
| Unit (CLI) | Token value never appears in stdout/stderr, success or error path | assert token string absent from `result.output` |
| Registration | `pipeline-trigger`/`pipeline-status` reachable from root `app` | `runner.invoke(app, ["--help"])` lists both |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file
classification, or new process-integration boundary. Network I/O is already
contained behind `GitHubActionsTransport` (established in
CHG-FIRST-PIPELINE-ADAPTER); this change only adds a composition-root
factory and a thin CLI presentation layer over that existing seam.

## Migration / Rollout

No migration. Additive: new factory, new command module, new registration
line, new test file. Revert = delete `commands/pipeline.py` and
`tests/cli/test_pipeline.py`, remove the factory/error class from
`_composition.py`, remove the two lines in `main.py`.

## Open Questions

- [ ] Adapter package (`odoo_forge_pipeline_github`) has no typed domain
      error today; this design catches `(OSError, RuntimeError, ValueError)`
      as an interim measure. A follow-up should give the adapter a proper
      error type so the CLI (and any future consumer) can catch precisely.
