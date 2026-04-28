"""Tests for pyarnes_harness.budget.IterationBudget."""

import asyncio

import pytest

from pyarnes_harness.budget import IterationBudget


@pytest.mark.asyncio
async def test_initial_remaining():
    b = IterationBudget(total=5)
    assert b.remaining == 5


@pytest.mark.asyncio
async def test_consume_decrements():
    b = IterationBudget(total=5)
    ok = await b.consume()
    assert ok is True
    assert b.remaining == 4


@pytest.mark.asyncio
async def test_consume_exhausts():
    b = IterationBudget(total=2)
    assert await b.consume() is True
    assert await b.consume() is True
    assert await b.consume() is False
    assert b.remaining == 0


@pytest.mark.asyncio
async def test_refund_restores():
    b = IterationBudget(total=3)
    await b.consume()
    await b.consume()
    await b.refund()
    assert b.remaining == 2


@pytest.mark.asyncio
async def test_refund_capped_at_total():
    b = IterationBudget(total=3)
    await b.refund(10)
    assert b.remaining == 3


@pytest.mark.asyncio
async def test_consume_n():
    b = IterationBudget(total=10)
    ok = await b.consume(5)
    assert ok is True
    assert b.remaining == 5


@pytest.mark.asyncio
async def test_concurrent_consume():
    b = IterationBudget(total=3)

    async def worker() -> bool:
        return await b.consume()

    results = await asyncio.gather(worker(), worker(), worker(), worker())
    assert results.count(True) == 3
    assert results.count(False) == 1
    assert b.remaining == 0


def test_invalid_total():
    with pytest.raises(ValueError):
        IterationBudget(total=0)
