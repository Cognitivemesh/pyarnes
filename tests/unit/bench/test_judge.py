"""Tests for :mod:`pyarnes_bench._judge` — JSON-validated judge helper."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import BaseModel

from pyarnes_bench._judge import judge_json
from pyarnes_core.errors import LLMRecoverableError


class _Toy(BaseModel):
    value: int


class ScriptedModel:
    """Return successive canned payloads from a queue."""

    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self._payloads = list(payloads)
        self.calls = 0

    async def next_action(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        self.calls += 1
        return self._payloads.pop(0)


class TestJudgeJson:
    @pytest.mark.asyncio
    async def test_plain_json_parses(self) -> None:
        client = ScriptedModel([{"content": json.dumps({"value": 7})}])
        result = await judge_json(client, "prompt", _Toy)
        assert result.value == 7
        assert client.calls == 1

    @pytest.mark.asyncio
    async def test_fenced_json_parses(self) -> None:
        payload = "```json\n" + json.dumps({"value": 3}) + "\n```"
        client = ScriptedModel([{"content": payload}])
        result = await judge_json(client, "prompt", _Toy)
        assert result.value == 3

    @pytest.mark.asyncio
    async def test_content_dict_text(self) -> None:
        client = ScriptedModel([{"content": {"text": json.dumps({"value": 11})}}])
        result = await judge_json(client, "prompt", _Toy)
        assert result.value == 11

    @pytest.mark.asyncio
    async def test_retries_once_on_bad_json(self) -> None:
        client = ScriptedModel(
            [
                {"content": "nope, not json at all"},
                {"content": json.dumps({"value": 42})},
            ]
        )
        result = await judge_json(client, "prompt", _Toy)
        assert result.value == 42
        assert client.calls == 2

    @pytest.mark.asyncio
    async def test_raises_after_max_attempts(self) -> None:
        client = ScriptedModel(
            [
                {"content": "still not json"},
                {"content": json.dumps({"wrong": "shape"})},
            ]
        )
        with pytest.raises(LLMRecoverableError):
            await judge_json(client, "prompt", _Toy)
        assert client.calls == 2

    @pytest.mark.asyncio
    async def test_missing_content_key(self) -> None:
        client = ScriptedModel([{"stop_reason": "end_turn"}, {"stop_reason": "end_turn"}])
        with pytest.raises(LLMRecoverableError):
            await judge_json(client, "prompt", _Toy)
