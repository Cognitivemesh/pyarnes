"""Tests for :mod:`pyarnes_bench._judge` — JSON-validated judge helper."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from pyarnes_bench._judge import judge_json
from pyarnes_core.errors import LLMRecoverableError


class _Toy(BaseModel):
    value: int


class ScriptedModel:
    """Return successive canned text responses from a queue."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls = 0

    async def judge(self, prompt: str) -> str:
        self.calls += 1
        return self._responses.pop(0)


class TestJudgeJson:
    @pytest.mark.asyncio
    async def test_plain_json_parses(self) -> None:
        client = ScriptedModel([json.dumps({"value": 7})])
        result = await judge_json(client, "prompt", _Toy)
        assert result.value == 7
        assert client.calls == 1

    @pytest.mark.asyncio
    async def test_fenced_json_parses(self) -> None:
        payload = "```json\n" + json.dumps({"value": 3}) + "\n```"
        client = ScriptedModel([payload])
        result = await judge_json(client, "prompt", _Toy)
        assert result.value == 3

    @pytest.mark.asyncio
    async def test_retries_once_on_bad_json(self) -> None:
        client = ScriptedModel(
            [
                "nope, not json at all",
                json.dumps({"value": 42}),
            ]
        )
        result = await judge_json(client, "prompt", _Toy)
        assert result.value == 42
        assert client.calls == 2

    @pytest.mark.asyncio
    async def test_raises_after_max_attempts(self) -> None:
        client = ScriptedModel(
            [
                "still not json",
                json.dumps({"wrong": "shape"}),
            ]
        )
        with pytest.raises(LLMRecoverableError):
            await judge_json(client, "prompt", _Toy)
        assert client.calls == 2
