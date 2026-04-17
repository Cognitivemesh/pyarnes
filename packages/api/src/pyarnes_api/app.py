"""FastAPI application factory for the pyarnes API."""

from __future__ import annotations

from fastapi import FastAPI

from pyarnes_api.routes import eval as eval_router
from pyarnes_api.routes import guardrails as guardrails_router
from pyarnes_api.routes import health as health_router
from pyarnes_api.routes import lifecycle as lifecycle_router
from pyarnes_api.routes import tools as tools_router


def create_app() -> FastAPI:
    """Build and return the FastAPI application.

    Returns:
        Fully configured FastAPI instance with all routes mounted.
    """
    app = FastAPI(
        title="pyarnes API",
        description=(
            "OpenAPI interface for the pyarnes agentic harness. "
            "Manage lifecycle, check guardrails, inspect tools, and run evaluations."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.include_router(health_router.router)
    app.include_router(lifecycle_router.router, prefix="/api/v1")
    app.include_router(guardrails_router.router, prefix="/api/v1")
    app.include_router(tools_router.router, prefix="/api/v1")
    app.include_router(eval_router.router, prefix="/api/v1")

    return app


app = create_app()
