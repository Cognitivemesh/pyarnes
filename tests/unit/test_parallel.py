"""Tests for parallel tool batch detection and execution."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from pyarnes_harness.parallel import SERIAL_TOOLS, can_parallelize, execute_batch

# ── can_parallelize ────────────────────────────────────────────────────────


def _call(name: str, **args: Any) -> dict[str, Any]:
    return {"tool": name, "id": name, "arguments": args}


def test_single_call_is_parallelizable() -> None:
    assert can_parallelize([_call("search", q="foo")]) is True


def test_two_independent_calls_are_parallelizable() -> None:
    calls = [_call("search", q="foo"), _call("calc", expr="1+1")]
    assert can_parallelize(calls) is True


def test_calls_with_same_path_are_serial() -> None:
    calls = [
        _call("write_file", path="/tmp/out.txt", content="a"),  # noqa: S108
        _call("write_file", path="/tmp/out.txt", content="b"),  # noqa: S108
    ]
    assert can_parallelize(calls) is False


def test_calls_with_different_paths_are_parallelizable() -> None:
    calls = [
        _call("write_file", path="/tmp/a.txt", content="a"),  # noqa: S108
        _call("write_file", path="/tmp/b.txt", content="b"),  # noqa: S108
    ]
    assert can_parallelize(calls) is True


def test_serial_tool_forces_serial() -> None:
    serial_name = next(iter(SERIAL_TOOLS))
    calls = [_call("search", q="foo"), _call(serial_name)]
    assert can_parallelize(calls) is False


def test_empty_calls_is_parallelizable() -> None:
    assert can_parallelize([]) is True


# ── execute_batch ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_batch_parallel_calls_concurrently() -> None:
    """Independent calls are run via gather (concurrently)."""
    order: list[str] = []

    async def handler(name: str, call_id: str, args: dict) -> Any:
        order.append(f"start:{name}")
        await asyncio.sleep(0)  # yield — lets other tasks run
        order.append(f"end:{name}")
        return f"result:{name}"

    calls = [_call("a"), _call("b")]
    results = await execute_batch(calls, handler)

    assert len(results) == 2
    # Both started before either ended (interleaved — proves gather)
    assert order.index("start:b") < order.index("end:a")


@pytest.mark.asyncio
async def test_execute_batch_serial_tool_runs_sequentially() -> None:
    """When SERIAL_TOOLS detected, calls run one-at-a-time."""
    order: list[str] = []
    serial_name = next(iter(SERIAL_TOOLS))

    async def handler(name: str, call_id: str, args: dict) -> Any:
        order.append(f"start:{name}")
        await asyncio.sleep(0)
        order.append(f"end:{name}")
        return f"result:{name}"

    calls = [_call("search"), _call(serial_name)]
    await execute_batch(calls, handler)

    # Serial: search fully completes before serial_tool starts
    assert order.index("end:search") < order.index(f"start:{serial_name}")


@pytest.mark.asyncio
async def test_execute_batch_returns_in_call_order() -> None:
    """Results are returned in the same order as input calls."""
    handler = AsyncMock(side_effect=lambda name, _cid, _args: f"r:{name}")
    calls = [_call("x"), _call("y"), _call("z")]
    results = await execute_batch(calls, handler)
    assert list(results) == ["r:x", "r:y", "r:z"]
