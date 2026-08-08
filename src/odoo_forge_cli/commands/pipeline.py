"""Pipeline commands: trigger a CI run, check its status, and print its logs."""

import typer

from odoo_forge.pipeline.types import PipelineRunRef, PipelineRunSpec
from odoo_forge_cli import _composition


def _parse_params(params: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for entry in params:
        if "=" not in entry:
            raise ValueError(f"malformed --param entry (expected KEY=VALUE): {entry!r}")
        key, value = entry.split("=", 1)
        parsed[key] = value
    return parsed


def trigger(
    workflow: str = typer.Option(..., "--workflow", help="Workflow definition to trigger"),
    param: list[str] = typer.Option([], "--param", help="KEY=VALUE, repeatable"),
) -> None:
    """Trigger a pipeline run and print its run id."""
    try:
        parameters = _parse_params(param)
        spec = PipelineRunSpec(definition=workflow, parameters=parameters)
        provider = _composition._make_pipeline_provider()
        run_ref = provider.trigger(spec)
        typer.echo(run_ref.run_id)
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def status(run_id: str = typer.Option(..., "--run-id", help="Run id to check")) -> None:
    """Print a pipeline run's current state."""
    try:
        ref = PipelineRunRef(run_id=run_id)
        provider = _composition._make_pipeline_provider()
        run_status = provider.status(ref)
        typer.echo(run_status.state)
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def logs(run_id: str = typer.Option(..., "--run-id", help="Run id to inspect")) -> None:
    """Print a pipeline run's logs."""
    try:
        ref = PipelineRunRef(run_id=run_id)
        provider = _composition._make_pipeline_provider()
        log_text = provider.logs(ref)
        typer.echo(log_text)
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def register(app: typer.Typer) -> None:
    """Bind the pipeline commands onto `app`."""
    app.command(name="pipeline-trigger")(trigger)
    app.command(name="pipeline-status")(status)
    app.command(name="pipeline-logs")(logs)
