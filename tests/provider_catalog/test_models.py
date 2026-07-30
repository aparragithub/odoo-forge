import sys
from dataclasses import FrozenInstanceError

import pytest

from odoo_forge.provider_catalog import (
    ApprovedProviderAdapter,
    GlobalProviderBinding,
    ProviderCatalog,
    ProviderCatalogFailureCode,
    ProviderCatalogResolutionFailure,
    ProviderCatalogResolver,
    ProviderKind,
    ResolvedProviderAdapter,
)

sys.modules.pop("test_resolver", None)  # Avoid duplicate module during scoped collection.


def test_provider_kind_is_a_closed_vocabulary() -> None:
    assert "|".join(ProviderKind) == "source|image_registry|database|backend"


def test_provider_values_are_frozen_and_catalog_collections_are_tuples() -> None:
    adapter = ApprovedProviderAdapter(ProviderKind.SOURCE, "git")
    binding = GlobalProviderBinding(ProviderKind.SOURCE, "git")
    catalog = ProviderCatalog((adapter,), (binding,))

    assert catalog.approved_adapters == (adapter,)
    assert catalog.global_bindings == (binding,)
    with pytest.raises(FrozenInstanceError):
        adapter.adapter_id = "other"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        catalog.approved_adapters = ()  # type: ignore[misc]


@pytest.mark.parametrize(
    ("factory", "arguments"),
    [
        (ApprovedProviderAdapter, (ProviderKind.SOURCE, "  ")),
        (GlobalProviderBinding, (ProviderKind.SOURCE, "")),
        (ResolvedProviderAdapter, (ProviderKind.SOURCE, "\t")),
    ],
)
def test_provider_values_reject_blank_adapter_ids(
    factory: object, arguments: tuple[object, ...]
) -> None:
    with pytest.raises(ValueError, match="adapter_id"):
        factory(*arguments)  # type: ignore[operator]


def test_provider_values_reject_unsupported_provider_kinds() -> None:
    with pytest.raises(ValueError, match="provider kind"):
        ApprovedProviderAdapter("unsupported", "adapter")  # type: ignore[arg-type]


def test_catalog_values_expose_no_instance_selection_dimension() -> None:
    for value_type in (ApprovedProviderAdapter, GlobalProviderBinding, ResolvedProviderAdapter):
        with pytest.raises(TypeError):
            value_type(ProviderKind.SOURCE, "git", instance="production")  # type: ignore[call-arg]


def test_public_contract_exports_models_and_resolver() -> None:
    assert ProviderCatalogFailureCode.MISSING_SELECTION.value == "missing_selection"
    assert ProviderCatalogResolutionFailure.__name__ == "ProviderCatalogResolutionFailure"
    assert ProviderCatalogResolver.__name__ == "ProviderCatalogResolver"
