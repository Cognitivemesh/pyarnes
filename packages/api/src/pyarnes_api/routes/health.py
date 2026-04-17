"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from pyarnes_api import __version__
from pyarnes_api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness / readiness probe.

    Returns the API version and an ``ok`` status.
    """
    return HealthResponse(status="ok", version=__version__)
