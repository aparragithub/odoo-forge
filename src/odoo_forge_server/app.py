"""FastAPI application factory for the read-only control-plane edge."""

from typing import Any

from fastapi import FastAPI

from odoo_forge_server.routes.instances import create_instances_router


def create_app(*, reconciler: Any) -> FastAPI:
    """Create the framework boundary around one request-scoped reconciler."""
    app = FastAPI(title="Odoo Forge Control Plane")
    app.include_router(create_instances_router(reconciler))
    return app


__all__ = ["create_app"]
