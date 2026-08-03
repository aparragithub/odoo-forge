"""FastAPI application factory for the read-only control-plane edge."""

from dataclasses import dataclass
from ipaddress import ip_address
from typing import Any

from fastapi import FastAPI

from odoo_forge_server.routes.instances import create_instances_router


@dataclass(frozen=True)
class UiRuntime:
    """Fail-closed runtime configuration for the optional local UI."""

    bind_host: str
    production: bool = False

    def __post_init__(self) -> None:
        if self.production:
            raise ValueError("read-only UI is forbidden in production")
        try:
            address = ip_address(self.bind_host)
        except ValueError as exc:
            raise ValueError("read-only UI requires a literal loopback bind host") from exc
        if not address.is_loopback:
            raise ValueError("read-only UI requires a loopback bind host")


def create_app(*, reconciler: Any, ui_runtime: UiRuntime | None = None) -> FastAPI:
    """Create the framework boundary around one request-scoped reconciler."""
    app = FastAPI(title="Odoo Forge Control Plane")
    app.include_router(create_instances_router(reconciler))
    if ui_runtime is not None:
        from odoo_forge_server.views import create_ui_router

        app.include_router(create_ui_router(reconciler, ui_runtime))
    return app


__all__ = ["UiRuntime", "create_app"]
