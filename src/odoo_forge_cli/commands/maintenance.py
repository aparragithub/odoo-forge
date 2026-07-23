"""Maintenance commands: `doctor` and `rotate-enterprise-credential`.

Both are thin CLI wiring only — the real logic lives in
`odoo_forge.credentials.doctor.run_doctor` and
`odoo_forge_docker.credential_injection.rotate_enterprise_credential`
respectively. Helper modules are imported and called module-qualified
(`_composition.*`, `enterprise_credential.*`) so each moved symbol keeps
exactly one canonical patch target, per the design's module-qualified
access decision. This module never imports `odoo_forge_cli.main`.
"""

from pathlib import Path

import typer

from odoo_forge.credentials.doctor import run_doctor
from odoo_forge_cli import _composition, enterprise_credential
from odoo_forge_docker.credential_injection import (
    rotate_enterprise_credential as _rotate_enterprise_credential,
)


def doctor(
    manifest: Path = typer.Option(
        Path("project.yaml"), "--manifest", help="Path to the project.yaml manifest file"
    ),
) -> None:
    """Check local Enterprise credential prerequisites: age key + conventional SOPS entry.

    Thin CLI wiring only — both checks' logic lives in
    `odoo_forge.credentials.doctor.run_doctor`. Reports both checks
    independently and never prints secret material.
    """
    resolver = enterprise_credential._make_enterprise_credential_resolver(
        credentials_file=manifest.resolve().parent / "credentials.sops.yaml"
    )
    report = run_doctor(resolver=resolver, age_key_file=_composition._doctor_age_key_file())
    for check in (report.age_key, report.enterprise_credential):
        status = "ok" if check.ok else "FAIL"
        typer.echo(f"{status}: {check.name}: {check.message}")
    if not report.ok:
        raise typer.Exit(code=1)


def rotate_enterprise_credential(
    manifest: Path = typer.Option(
        Path("project.yaml"), "--manifest", help="Path to the project.yaml manifest file"
    ),
) -> None:
    """Rotate the conventional Enterprise source credential's SOPS keys.

    Thin CLI wiring only — the `sops updatekeys` wrapper itself lives in
    `odoo_forge_docker.credential_injection.rotate_enterprise_credential`
    (the docker adapter, since core is forbidden from importing
    `subprocess`). Touches no schema/state file; only
    `credentials.sops.yaml` is rewritten by `sops`.
    """
    credentials_file = manifest.resolve().parent / "credentials.sops.yaml"
    result = _rotate_enterprise_credential(credentials_file=credentials_file)
    if not result.ok:
        typer.echo(f"error: {result.message}", err=True)
        raise typer.Exit(code=1)
    typer.echo(result.message)


def register(app: typer.Typer) -> None:
    """Bind the two maintenance commands onto `app`, byte-identical names."""
    app.command(name="doctor")(doctor)
    app.command(name="rotate-enterprise-credential")(rotate_enterprise_credential)
