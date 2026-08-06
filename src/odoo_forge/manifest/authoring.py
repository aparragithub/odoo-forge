"""Presentation-neutral draft validation and canonical manifest serialization."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import yaml
from pydantic import ValidationError

from odoo_forge.manifest.schema import Manifest


@dataclass(frozen=True)
class DraftIssue:
    """One actionable validation issue associated with a draft field."""

    path: str
    message: str


@dataclass(frozen=True)
class DraftResult:
    """A validated manifest or ordered issues, never both."""

    manifest: Manifest | None
    issues: tuple[DraftIssue, ...] = ()


def _format_error_path(location: tuple[Any, ...]) -> str:
    path = ""
    for component in location:
        if isinstance(component, int):
            path += f"[{component}]"
        elif path:
            path += f".{component}"
        else:
            path = str(component)
    return path or "manifest"


def validate_draft(draft: Mapping[str, object]) -> DraftResult:
    """Validate a presentation-neutral draft using ``Manifest`` semantics."""
    try:
        return DraftResult(manifest=Manifest.model_validate(draft))
    except ValidationError as exc:
        issues = tuple(
            DraftIssue(path=_format_error_path(error["loc"]), message=str(error["msg"]))
            for error in exc.errors()
        )
        return DraftResult(manifest=None, issues=issues)


def serialize_manifest(manifest: Manifest) -> str:
    """Serialize a manifest in schema order with unset/default values omitted."""
    document = manifest.model_dump(mode="json", exclude_unset=True, exclude_defaults=True)
    return (
        yaml.safe_dump(
            document,
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
        ).rstrip("\n")
        + "\n"
    )


__all__ = ["DraftIssue", "DraftResult", "serialize_manifest", "validate_draft"]
