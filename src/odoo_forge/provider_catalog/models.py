"""Immutable domain values for the approved provider adapter catalog."""

from dataclasses import dataclass
from enum import StrEnum


class ProviderKind(StrEnum):
    SOURCE = "source"
    IMAGE_REGISTRY = "image_registry"
    DATABASE = "database"
    BACKEND = "backend"


class ProviderCatalogFailureCode(StrEnum):
    MISSING_SELECTION = "missing_selection"
    INVALID_CATALOG = "invalid_catalog"
    AMBIGUOUS_SELECTION = "ambiguous_selection"


def _validate_provider_kind(kind: ProviderKind) -> None:
    if not isinstance(kind, ProviderKind):
        raise ValueError("provider kind must be a supported ProviderKind")


def _validate_adapter_id(adapter_id: str) -> None:
    if not isinstance(adapter_id, str) or not adapter_id.strip():
        raise ValueError("adapter_id must be a non-blank string")


@dataclass(frozen=True, slots=True)
class ApprovedProviderAdapter:
    kind: ProviderKind
    adapter_id: str

    def __post_init__(self) -> None:
        _validate_provider_kind(self.kind)
        _validate_adapter_id(self.adapter_id)


@dataclass(frozen=True, slots=True)
class GlobalProviderBinding:
    kind: ProviderKind
    adapter_id: str

    def __post_init__(self) -> None:
        _validate_provider_kind(self.kind)
        _validate_adapter_id(self.adapter_id)


@dataclass(frozen=True, slots=True)
class ProviderCatalog:
    approved_adapters: tuple[ApprovedProviderAdapter, ...]
    global_bindings: tuple[GlobalProviderBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "approved_adapters", tuple(self.approved_adapters))
        object.__setattr__(self, "global_bindings", tuple(self.global_bindings))


@dataclass(frozen=True, slots=True)
class ResolvedProviderAdapter:
    kind: ProviderKind
    adapter_id: str

    def __post_init__(self) -> None:
        _validate_provider_kind(self.kind)
        _validate_adapter_id(self.adapter_id)


@dataclass(frozen=True, slots=True)
class ProviderCatalogResolutionFailure:
    code: ProviderCatalogFailureCode
    details: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.code, ProviderCatalogFailureCode):
            raise ValueError("code must be a ProviderCatalogFailureCode")
        object.__setattr__(self, "details", tuple(sorted(self.details)))


ProviderCatalogResolution = ResolvedProviderAdapter | ProviderCatalogResolutionFailure


__all__ = [
    "ApprovedProviderAdapter",
    "GlobalProviderBinding",
    "ProviderCatalog",
    "ProviderCatalogFailureCode",
    "ProviderCatalogResolution",
    "ProviderCatalogResolutionFailure",
    "ProviderKind",
    "ResolvedProviderAdapter",
]
