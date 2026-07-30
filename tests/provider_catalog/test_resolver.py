from itertools import permutations

import pytest

from odoo_forge.provider_catalog.models import (
    ApprovedProviderAdapter,
    GlobalProviderBinding,
    ProviderCatalog,
    ProviderCatalogResolutionFailure,
    ProviderKind,
    ResolvedProviderAdapter,
)
from odoo_forge.provider_catalog.resolver import ProviderCatalogResolver


def _catalog(
    approved: tuple[ApprovedProviderAdapter, ...],
    bindings: tuple[GlobalProviderBinding, ...],
) -> ProviderCatalog:
    return ProviderCatalog(approved, bindings)


def test_resolve_returns_one_opaque_global_selection() -> None:
    result = ProviderCatalogResolver(
        _catalog(
            (ApprovedProviderAdapter(ProviderKind.SOURCE, "git"),),
            (GlobalProviderBinding(ProviderKind.SOURCE, "git"),),
        )
    ).resolve(ProviderKind.SOURCE)

    assert result == ResolvedProviderAdapter(ProviderKind.SOURCE, "git")


def test_resolve_reports_missing_kind_without_fallback() -> None:
    result = ProviderCatalogResolver(
        _catalog(
            (ApprovedProviderAdapter(ProviderKind.SOURCE, "git"),),
            (GlobalProviderBinding(ProviderKind.SOURCE, "git"),),
        )
    ).resolve(ProviderKind.DATABASE)

    assert isinstance(result, ProviderCatalogResolutionFailure)
    assert result.code == "missing_selection"
    assert result.details == ()


def test_resolve_reports_sorted_ambiguous_adapter_ids() -> None:
    result = ProviderCatalogResolver(
        _catalog(
            (
                ApprovedProviderAdapter(ProviderKind.SOURCE, "gitlab"),
                ApprovedProviderAdapter(ProviderKind.SOURCE, "github"),
            ),
            (
                GlobalProviderBinding(ProviderKind.SOURCE, "gitlab"),
                GlobalProviderBinding(ProviderKind.SOURCE, "github"),
            ),
        )
    ).resolve(ProviderKind.SOURCE)

    assert isinstance(result, ProviderCatalogResolutionFailure)
    assert result.code == "ambiguous_selection"
    assert result.details == ("github", "gitlab")


def test_invalid_catalog_state_wins_before_ambiguous_cardinality() -> None:
    invalid_adapter = type("InvalidAdapter", (), {"__str__": None})()
    result = ProviderCatalogResolver(
        _catalog(
            (
                ApprovedProviderAdapter(ProviderKind.SOURCE, "git"),
                ApprovedProviderAdapter(ProviderKind.SOURCE, "git"),
                invalid_adapter,
            ),
            (
                GlobalProviderBinding(ProviderKind.SOURCE, "git"),
                GlobalProviderBinding(ProviderKind.SOURCE, "other"),
            ),
        )
    ).resolve(ProviderKind.SOURCE)

    assert isinstance(result, ProviderCatalogResolutionFailure)
    assert result.code == "invalid_catalog"
    assert result.details == ("InvalidAdapter", "git", "other")


@pytest.mark.parametrize(
    "bindings",
    [
        (GlobalProviderBinding(ProviderKind.SOURCE, "git"),) * 2,
        (GlobalProviderBinding(ProviderKind.DATABASE, "git"),),
    ],
)
def test_duplicate_or_unapproved_global_bindings_are_invalid(
    bindings: tuple[GlobalProviderBinding, ...],
) -> None:
    result = ProviderCatalogResolver(
        _catalog(
            (ApprovedProviderAdapter(ProviderKind.SOURCE, "git"),),
            bindings,
        )
    ).resolve(bindings[0].kind)

    assert isinstance(result, ProviderCatalogResolutionFailure)
    assert result.code == "invalid_catalog"
    assert result.details == ("git",)


def test_resolution_is_independent_of_input_order_and_instance_data() -> None:
    adapters = (
        ApprovedProviderAdapter(ProviderKind.SOURCE, "git"),
        ApprovedProviderAdapter(ProviderKind.DATABASE, "postgres"),
    )
    bindings = (
        GlobalProviderBinding(ProviderKind.SOURCE, "git"),
        GlobalProviderBinding(ProviderKind.DATABASE, "postgres"),
    )
    results = {
        ProviderCatalogResolver(_catalog(adapter_order, binding_order)).resolve(ProviderKind.SOURCE)
        for adapter_order in permutations(adapters)
        for binding_order in permutations(bindings)
    }

    assert results == {ResolvedProviderAdapter(ProviderKind.SOURCE, "git")}
    resolver = ProviderCatalogResolver(_catalog((), ()))
    with pytest.raises(TypeError):
        resolver.resolve(ProviderKind.SOURCE, instance="production")  # type: ignore[call-arg]
