"""Unit tests for ErrorHandlerRegistry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from pyarnes_core.error_registry import ErrorHandlerRegistry
from pyarnes_core.errors import HarnessError


@dataclass(frozen=True, slots=True)
class CustomError(HarnessError):
    """Custom HarnessError subtype for testing."""


@dataclass(frozen=True, slots=True)
class OtherError(HarnessError):
    """Another HarnessError subtype that will not be registered."""


class TestErrorHandlerRegistry:
    """ErrorHandlerRegistry dispatch logic."""

    @pytest.mark.asyncio()
    async def test_registered_handler_is_called(self) -> None:
        """Handler registered for an error type is invoked and its result returned."""
        called_with: list[HarnessError] = []
        sentinel = object()

        async def handler(exc: HarnessError) -> Any:
            called_with.append(exc)
            return sentinel

        registry = ErrorHandlerRegistry()
        registry.register(CustomError, handler)

        exc = CustomError(message="boom")
        result = await registry.dispatch(exc)

        assert called_with == [exc]
        assert result is sentinel

    @pytest.mark.asyncio()
    async def test_handler_returning_none_falls_through(self) -> None:
        """A handler that returns None causes dispatch to return None."""

        async def none_handler(exc: HarnessError) -> None:
            return None

        registry = ErrorHandlerRegistry()
        registry.register(CustomError, none_handler)

        result = await registry.dispatch(CustomError(message="x"))
        assert result is None

    @pytest.mark.asyncio()
    async def test_unregistered_type_returns_none(self) -> None:
        """No handler registered → dispatch returns None without raising."""
        registry = ErrorHandlerRegistry()
        result = await registry.dispatch(OtherError(message="y"))
        assert result is None

    @pytest.mark.asyncio()
    async def test_exact_type_match_not_base(self) -> None:
        """Handler registered for base type does not fire for a different subtype."""
        sentinel = object()

        async def base_handler(exc: HarnessError) -> Any:
            return sentinel

        registry = ErrorHandlerRegistry()
        registry.register(HarnessError, base_handler)

        # CustomError is a subtype of HarnessError but exact lookup skips base.
        result = await registry.dispatch(CustomError(message="z"))
        assert result is None

    @pytest.mark.asyncio()
    async def test_latest_register_wins(self) -> None:
        """Registering a second handler for the same type overwrites the first."""
        first_called: list[bool] = []

        async def first(_: HarnessError) -> Any:
            first_called.append(True)
            return "first"

        async def second(_: HarnessError) -> Any:
            return "second"

        registry = ErrorHandlerRegistry()
        registry.register(CustomError, first)
        registry.register(CustomError, second)

        result = await registry.dispatch(CustomError(message="a"))
        assert result == "second"
        assert first_called == []
