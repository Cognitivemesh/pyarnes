"""Tests for the SteeringQueue mid-execution note injection."""

from __future__ import annotations

import asyncio

import pytest

from pyarnes_harness.steering import SteeringQueue


@pytest.mark.asyncio
async def test_drain_empty_queue_returns_empty_list() -> None:
    q = SteeringQueue()
    result = await q.drain()
    assert result == []


@pytest.mark.asyncio
async def test_push_then_drain_returns_user_message() -> None:
    q = SteeringQueue()
    await q.push("please focus on security")
    messages = await q.drain()
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "please focus on security"


@pytest.mark.asyncio
async def test_drain_clears_queue() -> None:
    q = SteeringQueue()
    await q.push("note one")
    await q.drain()
    result = await q.drain()
    assert result == []


@pytest.mark.asyncio
async def test_multiple_notes_preserved_in_order() -> None:
    q = SteeringQueue()
    await q.push("first")
    await q.push("second")
    await q.push("third")
    messages = await q.drain()
    assert [m["content"] for m in messages] == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_drain_after_partial_drain() -> None:
    q = SteeringQueue()
    await q.push("a")
    await q.drain()
    await q.push("b")
    messages = await q.drain()
    assert len(messages) == 1
    assert messages[0]["content"] == "b"


@pytest.mark.asyncio
async def test_concurrent_push_and_drain_are_safe() -> None:
    q = SteeringQueue()

    async def pusher() -> None:
        for i in range(10):
            await q.push(f"note {i}")
            await asyncio.sleep(0)

    async def drainer() -> list:
        collected = []
        for _ in range(5):
            collected.extend(await q.drain())
            await asyncio.sleep(0)
        return collected

    _, collected = await asyncio.gather(pusher(), drainer())
    # All 10 notes must eventually be drained (run a final drain after both tasks)
    collected.extend(await q.drain())
    assert len(collected) == 10
