"""Rendering helpers: turn already-computed domain values into human text.

No domain logic lives here — parsing, composition, and drift detection are
all delegated to `odoo_forge`. These functions only translate already-computed
results into what `forge` prints.
"""

import typer
from pydantic import ValidationError

from odoo_forge.manifest.drift import DriftEntry


def _format_drift(entry: DriftEntry) -> str:
    """Render a structured drift entry as a single human-readable line."""
    if entry.kind == "missing_lock":
        return "no lockfile present — manifest has never been locked"
    if entry.kind == "manifest_lock_hash":
        return f"manifest hash '{entry.expected}' does not match lock's '{entry.actual}'"
    if entry.kind == "not_materialized":
        target = f"layer '{entry.layer}'"
        if entry.repo:
            target += f" repo '{entry.repo}'"
        return f"{target} is not materialized"
    if entry.kind == "commit_mismatch":
        return (
            f"layer '{entry.layer}' repo '{entry.repo}' lock declares "
            f"'{entry.expected}' but materialized at '{entry.actual}'"
        )
    return f"unrecognized drift entry: {entry.kind}"


def _format_missing_dependencies(missing: dict[str, frozenset[str]]) -> str:
    """Render every module's missing dependencies as one sorted, multi-line message."""
    lines = [f"  {name} -> {', '.join(sorted(deps))}" for name, deps in sorted(missing.items())]
    return "missing module dependencies:\n" + "\n".join(lines)


def _render_validation_errors(exc: ValidationError) -> None:
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        typer.echo(f"error: {location}: {error['msg']}", err=True)
