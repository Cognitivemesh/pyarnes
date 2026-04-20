"""Tests for observability.atoms.jsonable."""

from __future__ import annotations

import json
from pathlib import Path

from pyarnes_core.observability import dumps, to_jsonable


class TestToJsonable:
    """to_jsonable preserves native JSON types, strings everything else."""

    def test_dict_preserved(self) -> None:
        value = {"foo": 1, "bar": "baz"}
        assert to_jsonable(value) == value
        assert to_jsonable(value) is value

    def test_list_preserved(self) -> None:
        value = [1, 2, 3]
        assert to_jsonable(value) is value

    def test_none_preserved(self) -> None:
        assert to_jsonable(None) is None

    def test_bool_preserved(self) -> None:
        assert to_jsonable(True) is True
        assert to_jsonable(False) is False

    def test_path_becomes_string(self, tmp_path: Path) -> None:
        result = to_jsonable(tmp_path)
        assert isinstance(result, str)
        assert str(tmp_path) == result


class TestDumps:
    """dumps uses default=str and preserves unicode."""

    def test_structured_value_round_trips(self) -> None:
        value = {"rows": [1, 2], "name": "alice"}
        assert json.loads(dumps(value)) == value

    def test_non_serializable_falls_back_to_str(self, tmp_path: Path) -> None:
        value = {"path": tmp_path}
        encoded = dumps(value)
        decoded = json.loads(encoded)
        assert isinstance(decoded["path"], str)
        assert decoded["path"] == str(tmp_path)

    def test_unicode_preserved(self) -> None:
        """ensure_ascii=False keeps non-ASCII characters literal in the output."""
        encoded = dumps({"name": "café"})
        assert "café" in encoded
