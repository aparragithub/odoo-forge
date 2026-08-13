"""Provider-neutral port for exposure reconciliation."""

from typing import Protocol, runtime_checkable

from odoo_forge.exposure.types import ExposureRequest, ExposureResult


@runtime_checkable
class ExposureReconciler(Protocol):
    """Reconcile one scoped exposure request without exposing provider mechanics."""

    def reconcile(self, request: ExposureRequest) -> ExposureResult:
        """Converge implemented HTTP routing and DNS while preserving deferred TLS intent."""
        ...


__all__ = ["ExposureReconciler"]
