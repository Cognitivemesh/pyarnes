"""Tests for the AST-hash duplicate detector."""

from __future__ import annotations

import networkx as nx

from pyarnes_bench.audit.duplicates import detect_duplicates


def _add_function(graph: nx.DiGraph, node_id: str, body: str) -> None:
    graph.add_node(node_id, kind="function", name=node_id, extra={"body": body})


_LONG_BODY_A = (
    "def f(x):\n"
    "    total = 0\n"
    "    for i in range(x):\n"
    "        total += i * 2\n"
    "        total -= i // 3\n"
    "    return total\n"
)
_LONG_BODY_B_SAME_LOGIC = (
    "def g(x):\n"
    '    """Different docstring."""\n'
    "    total = 0\n"
    "    for i in range(x):\n"
    "        total += i * 2\n"
    "        total -= i // 3\n"
    "    return total\n"
)
_SHORT_BODY = "def t():\n    return 1\n"


def test_duplicates_match_after_docstring_strip() -> None:
    g: nx.DiGraph = nx.DiGraph()
    _add_function(g, "f", _LONG_BODY_A)
    _add_function(g, "g", _LONG_BODY_B_SAME_LOGIC)

    findings = detect_duplicates(g, min_tokens=10)
    assert findings
    assert findings[0].category == "duplicate_block"
    assert findings[0].detail["group_size"] == 2


def test_short_function_below_threshold_is_not_flagged() -> None:
    g: nx.DiGraph = nx.DiGraph()
    _add_function(g, "t1", _SHORT_BODY)
    _add_function(g, "t2", _SHORT_BODY)
    findings = detect_duplicates(g, min_tokens=80)
    assert findings == []


def test_distinct_functions_are_not_flagged() -> None:
    g: nx.DiGraph = nx.DiGraph()
    _add_function(g, "f", _LONG_BODY_A)
    _add_function(g, "h", "def h(x):\n    return x * 2\n")
    findings = detect_duplicates(g, min_tokens=10)
    assert findings == []
