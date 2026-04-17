"""Lifecycle management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from pyarnes_api.schemas import ErrorResponse, LifecycleState, TransitionRequest
from pyarnes_core.lifecycle import Lifecycle

router = APIRouter(tags=["lifecycle"])

# In-memory session lifecycle (single-session for now).
_lifecycle = Lifecycle()


def _reset_lifecycle() -> None:
    """Reset the global lifecycle (used by tests)."""
    global _lifecycle  # noqa: PLW0603
    _lifecycle = Lifecycle()


@router.get(
    "/lifecycle",
    response_model=LifecycleState,
    summary="Get current lifecycle state",
)
async def get_lifecycle() -> LifecycleState:
    """Return the current session lifecycle phase, metadata, and history."""
    return LifecycleState(
        phase=_lifecycle.phase.value,
        is_terminal=_lifecycle.is_terminal,
        metadata=_lifecycle.metadata,
        history=_lifecycle.history,
    )


@router.post(
    "/lifecycle/transition",
    response_model=LifecycleState,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    summary="Transition lifecycle phase",
)
async def transition_lifecycle(body: TransitionRequest) -> LifecycleState:
    """Transition the session lifecycle to a new phase.

    Allowed actions: ``start``, ``pause``, ``resume``, ``complete``, ``fail``.
    """
    action_map = {
        "start": _lifecycle.start,
        "pause": _lifecycle.pause,
        "resume": _lifecycle.resume,
        "complete": _lifecycle.complete,
        "fail": _lifecycle.fail,
    }

    fn = action_map.get(body.action)
    if fn is None:
        raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")

    try:
        fn()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return LifecycleState(
        phase=_lifecycle.phase.value,
        is_terminal=_lifecycle.is_terminal,
        metadata=_lifecycle.metadata,
        history=_lifecycle.history,
    )


@router.post(
    "/lifecycle/reset",
    response_model=LifecycleState,
    summary="Reset lifecycle to INIT",
)
async def reset_lifecycle() -> LifecycleState:
    """Reset the session lifecycle back to INIT phase."""
    _reset_lifecycle()
    return LifecycleState(
        phase=_lifecycle.phase.value,
        is_terminal=_lifecycle.is_terminal,
        metadata=_lifecycle.metadata,
        history=_lifecycle.history,
    )
