"""FastAPI application factory for the read-only control-plane edge."""

from typing import Any

from fastapi import FastAPI

from odoo_forge_server.routes.instances import create_instances_router
from odoo_forge_server.runtime import UiRuntime


def create_app(*, reconciler: Any, ui_runtime: UiRuntime | None = None) -> FastAPI:
    """Create the framework boundary around one request-scoped reconciler."""
    app = FastAPI(title="Odoo Forge Control Plane")
    app.include_router(create_instances_router(reconciler))
    if ui_runtime is not None:
        from odoo_forge_server.views import create_ui_router

        app.include_router(create_ui_router(reconciler, ui_runtime))
    return app


__all__ = ["UiRuntime", "create_app"]
