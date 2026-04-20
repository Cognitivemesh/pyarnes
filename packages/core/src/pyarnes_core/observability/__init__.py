"""Observability domain — structured event recording primitives.

Atoms and molecules that produce JSON-safe values, measure durations,
and bind structured fields to log records. Adapters under
``observability/adapters/`` wire these to loguru and JSONL files at
the system edge.
"""
