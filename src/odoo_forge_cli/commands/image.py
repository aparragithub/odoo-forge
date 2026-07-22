"""Image registry commands: resolve/publish/pull/exists."""

import typer

from odoo_forge.image_registry import RegistryError
from odoo_forge.image_registry.reference import (
    normalize_digest_image_reference,
    normalize_publishable_image_reference,
)
from odoo_forge_cli import _composition


def image_resolve(ref: str = typer.Option(..., "--ref", help="Image reference to resolve")) -> None:
    """Resolve a supported GHCR image reference to a canonical digest ref."""
    try:
        normalized_ref = normalize_publishable_image_reference(ref)
        provider = _composition._make_image_registry_provider()
        typer.echo(provider.resolve_digest(normalized_ref))
    except RegistryError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def image_publish(
    ref: str = typer.Option(..., "--ref", help="Image reference to publish"),
) -> None:
    """Publish a built GHCR image and print its immutable digest ref."""
    try:
        normalized_ref = normalize_publishable_image_reference(ref)
        provider = _composition._make_image_registry_provider()
        typer.echo(provider.publish(normalized_ref))
    except RegistryError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def image_pull(
    ref: str = typer.Option(..., "--ref", help="Digest image reference to prefetch"),
) -> None:
    """Prefetch a digest image into the local Docker daemon."""
    try:
        normalized_ref = normalize_digest_image_reference(ref)
        provider = _composition._make_image_registry_provider()
        typer.echo(provider.pull(normalized_ref))
    except RegistryError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def image_exists(
    ref: str = typer.Option(..., "--ref", help="Digest image reference to check"),
) -> None:
    """Check whether a digest image exists in the registry."""
    try:
        normalized_ref = normalize_digest_image_reference(ref)
        provider = _composition._make_image_registry_provider()
        typer.echo(str(provider.exists(normalized_ref)).lower())
    except RegistryError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def register(app: typer.Typer) -> None:
    """Bind the four image-registry commands onto `app`, byte-identical names."""
    app.command(name="image-resolve")(image_resolve)
    app.command(name="image-publish")(image_publish)
    app.command(name="image-pull")(image_pull)
    app.command(name="image-exists")(image_exists)
