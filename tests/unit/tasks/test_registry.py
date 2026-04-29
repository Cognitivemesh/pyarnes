"""Tests for the PluginRegistry — registration, lookup, isolation."""

from __future__ import annotations

import pytest

from pyarnes_tasks.registry import PluginRegistry, global_registry


class _Stub:
    """Bare stand-in for a Plugin instance — registry doesn't validate types."""

    def __init__(self, name: str) -> None:
        self.name = name


def test_register_and_get() -> None:
    reg = PluginRegistry()
    stub = _Stub("foo")
    reg.register("foo", stub)
    assert reg.get("foo") is stub


def test_register_duplicate_raises() -> None:
    reg = PluginRegistry()
    reg.register("foo", _Stub("foo"))
    with pytest.raises(ValueError, match="already registered"):
        reg.register("foo", _Stub("foo"))


def test_get_missing_returns_none() -> None:
    assert PluginRegistry().get("nope") is None


def test_names_sorted() -> None:
    reg = PluginRegistry()
    for n in ("zeta", "alpha", "mu"):
        reg.register(n, _Stub(n))
    assert reg.names == ["alpha", "mu", "zeta"]


def test_contains_and_len() -> None:
    reg = PluginRegistry()
    assert len(reg) == 0
    assert "foo" not in reg
    reg.register("foo", _Stub("foo"))
    assert "foo" in reg
    assert len(reg) == 1


def test_unregister() -> None:
    reg = PluginRegistry()
    reg.register("foo", _Stub("foo"))
    reg.unregister("foo")
    assert "foo" not in reg
    with pytest.raises(KeyError, match="not registered"):
        reg.unregister("foo")


def test_global_registry_is_singleton() -> None:
    assert global_registry() is global_registry()


def test_clear_resets_state() -> None:
    reg = PluginRegistry()
    reg.register("a", _Stub("a"))
    reg.register("b", _Stub("b"))
    reg.clear()
    assert len(reg) == 0
    assert reg.names == []
