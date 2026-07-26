"""`copy` command: end-to-end capture -> anonymize -> deliver (bridge slice B5).

Composes the durable `DataArtifactCopyCoordinator` (real `FilesystemStagedArtifactStore` +
`StagedArtifactCapability` + store-backed byte source + real `RestoreTarget` + Postgres
`DatabaseProvider`, see `odoo_forge_cli._composition._make_data_artifact_copy_coordinator`)
to clone a live source Postgres database into a target, moving real bytes through the
staged artifact store. Anonymize-by-default (design D4): the coordinator always routes
the captured manifest through the real `mask_transform` wired at the composition root,
which masks bytes per rule via a scratch-database round trip. Operators may supply a
versioned YAML or JSON policy; omitting it preserves the empty-policy behavior.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import typer

from odoo_forge.anonymization.policy import AnonymizationPolicy
from odoo_forge.anonymization.policy_input import AnonymizationPolicyInputError
from odoo_forge.credentials.types import CredentialHandle, TargetContext
from odoo_forge.data_artifacts.capture import CaptureSource
from odoo_forge.database.errors import DatabaseProviderError
from odoo_forge.database.types import DatabaseSpec
from odoo_forge.durable_operations.types import DurableOperationIdentity
from odoo_forge_cli import _composition
from odoo_forge_cli.anonymization_policy import load_anonymization_policy


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
    anonymization_policy_file: Path | None = typer.Option(
        None, "--anonymization-policy-file", help="Versioned YAML or JSON anonymization policy"
    ),
) -> None:
    """Capture SOURCE, anonymize it, and deliver it into TARGET as one durable operation."""
    try:
        policy = (
            load_anonymization_policy(anonymization_policy_file)
            if anonymization_policy_file is not None
            else AnonymizationPolicy()
        )
    except AnonymizationPolicyInputError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    coordinator = _composition._make_data_artifact_copy_coordinator(
        credentials_file=credentials_file
    )
    capture_source = CaptureSource(
        credentials=CredentialHandle(f"database-copy/{source}"),
        target=TargetContext(kind="source", target_id=source),
    )
    spec = DatabaseSpec(name=target)
    canonical_policy = json.dumps(
        policy.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    policy_digest = hashlib.sha256(canonical_policy).hexdigest()
    operation = DurableOperationIdentity(
        operation_id=f"copy-{source}-{target}",
        request_digest=f"{source}:{target}:{policy_digest}",
    )

    # Resilient boundary, mirroring `backend.run`/`backend.status`: every
    # `DatabaseProviderError` (capture failure, integrity mismatch, raw-delivery
    # refusal, restore/provisioning failure) surfaces as a single clean
    # `error: ...` line, never a raw traceback.
    try:
        result = coordinator.run(
            source=capture_source,
            spec=spec,
            policy=policy,
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
    typer.echo(
        f"anonymization: {len(policy.rules)} rule(s) applied"
        if policy.rules
        else (
            "anonymization: policy is empty; no effective anonymization rules were applied"
            if anonymization_policy_file is not None
            else "anonymization: no effective anonymization rules were applied"
        )
    )


def register(app: typer.Typer) -> None:
    """Bind the `copy` command onto `app`."""
    app.command(name="copy")(copy)


__all__ = ["copy", "register"]
