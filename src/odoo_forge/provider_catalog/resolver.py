"""Deterministic resolution for the approved provider adapter catalog."""

from collections.abc import Iterable

from odoo_forge.provider_catalog.models import (
    ApprovedProviderAdapter,
    GlobalProviderBinding,
    ProviderCatalog,
    ProviderCatalogFailureCode,
    ProviderCatalogResolution,
    ProviderCatalogResolutionFailure,
    ProviderKind,
    ResolvedProviderAdapter,
)


def _invalid_value_detail(value: object) -> str:
    return value if isinstance(value, str) else type(value).__name__


def _invalid_details(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def _catalog_errors(catalog: ProviderCatalog) -> tuple[str, ...]:
    errors: list[str] = []
    approved_keys: set[tuple[ProviderKind, str]] = set()
    approved_by_kind: set[tuple[ProviderKind, str]] = set()

    for adapter in catalog.approved_adapters:
        if not isinstance(adapter, ApprovedProviderAdapter):
            errors.append(_invalid_value_detail(adapter))
            continue
        key = (adapter.kind, adapter.adapter_id)
        if key in approved_keys:
            errors.append(adapter.adapter_id)
        approved_keys.add(key)
        approved_by_kind.add(key)

    binding_keys: set[tuple[ProviderKind, str]] = set()
    for binding in catalog.global_bindings:
        if not isinstance(binding, GlobalProviderBinding):
            errors.append(_invalid_value_detail(binding))
            continue
        key = (binding.kind, binding.adapter_id)
        if key in binding_keys:
            errors.append(binding.adapter_id)
        binding_keys.add(key)
        if key not in approved_by_kind:
            errors.append(binding.adapter_id)

    return _invalid_details(errors)


class ProviderCatalogResolver:
    def __init__(self, catalog: ProviderCatalog) -> None:
        self._catalog = catalog

    def resolve(self, kind: ProviderKind) -> ProviderCatalogResolution:
        if not isinstance(kind, ProviderKind):
            return ProviderCatalogResolutionFailure(
                code=ProviderCatalogFailureCode.INVALID_CATALOG,
                details=(_invalid_value_detail(kind),),
            )

        invalid_details = _catalog_errors(self._catalog)
        if invalid_details:
            return ProviderCatalogResolutionFailure(
                code=ProviderCatalogFailureCode.INVALID_CATALOG,
                details=invalid_details,
            )

        bindings = tuple(
            binding for binding in self._catalog.global_bindings if binding.kind is kind
        )
        adapter_ids = tuple(sorted(binding.adapter_id for binding in bindings))
        if len(adapter_ids) > 1:
            return ProviderCatalogResolutionFailure(
                code=ProviderCatalogFailureCode.AMBIGUOUS_SELECTION,
                details=adapter_ids,
            )
        if not adapter_ids:
            return ProviderCatalogResolutionFailure(
                code=ProviderCatalogFailureCode.MISSING_SELECTION,
            )
        return ResolvedProviderAdapter(kind=kind, adapter_id=adapter_ids[0])


__all__ = ["ProviderCatalogResolver"]
