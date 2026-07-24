"""`copy` command: end-to-end capture -> anonymize -> deliver (bridge slice B5).

Composes the durable `DataArtifactCopyCoordinator` (real `FilesystemStagedArtifactStore` +
`StagedArtifactCapability` + store-backed byte source + real `RestoreTarget` + Postgres
`DatabaseProvider`, see `odoo_forge_cli._composition._make_data_artifact_copy_coordinator`)
to clone a live source Postgres database into a target, moving real bytes through the
staged artifact store. Anonymize-by-default (design D4): this v1 command always runs an
empty `AnonymizationPolicy`, matching the pass-through `mask_transform` wired at the
composition root (real per-rule byte masking is explicitly deferred).
"""

from __future__ import annotations

from pathlib import Path

import typer

from odoo_forge.anonymization.policy import AnonymizationPolicy
from odoo_forge.credentials.types import CredentialHandle, TargetContext
from odoo_forge.data_artifacts.capture import CaptureSource
from odoo_forge.database.errors import DatabaseProviderError
from odoo_forge.database.types import DatabaseSpec
from odoo_forge.durable_operations.types import DurableOperationIdentity
from odoo_forge_cli import _composition


def copy(
    source: str = typer.Argument(
        ..., help="Docker container name of the live source PostgreSQL database"
    ),
    target: str = typer.Argument(
        ..., help="Docker container/database name to restore the copy into"
    ),
    credentials_file: Path = typer.Option(
        Path("credentials.sops.yaml"),
        "--credentials-file",
        help="Path to the SOPS-encrypted credentials file",
    ),
    retain_staged: bool = typer.Option(
        False,
        "--retain-staged",
        help="Keep the staged artifact bytes after a successful copy (default: discard)",
    ),
) -> None:
    """Capture SOURCE, anonymize it, and deliver it into TARGET as one durable operation."""
    coordinator = _composition._make_data_artifact_copy_coordinator(
        credentials_file=credentials_file
    )
    capture_source = CaptureSource(
        credentials=CredentialHandle(f"database-copy/{source}"),
        target=TargetContext(kind="source", target_id=source),
    )
    spec = DatabaseSpec(name=target)
    operation = DurableOperationIdentity(
        operation_id=f"copy-{source}-{target}",
        request_digest=f"{source}:{target}",
    )

    # Resilient boundary, mirroring `backend.run`/`backend.status`: every
    # `DatabaseProviderError` (capture failure, integrity mismatch, raw-delivery
    # refusal, restore/provisioning failure) surfaces as a single clean
    # `error: ...` line, never a raw traceback.
    try:
        result = coordinator.run(
            source=capture_source,
            spec=spec,
            policy=AnonymizationPolicy(),
            credentials=CredentialHandle(f"database-copy/{target}"),
            operation=operation,
            retain_staged=retain_staged,
        )
    except DatabaseProviderError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"copied: source '{source}' -> target '{result.creation.ref.identifier}' "
        f"(state={result.state})"
    )


def register(app: typer.Typer) -> None:
    """Bind the `copy` command onto `app`."""
    app.command(name="copy")(copy)


__all__ = ["copy", "register"]
