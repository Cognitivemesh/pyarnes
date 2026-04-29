"""Shared argument parsing + bootstrap for the four ``audit:*`` task modules.

Each task module is a thin shim: parse ``--root`` and ``--graph``, mint a
fresh ``session_id`` / ``trace_id`` so every event in this run is correlated,
configure JSONL logging on stderr, and return the bits the task body needs.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

import networkx as nx

from pyarnes_bench.audit import AuditConfig, load_graph
from pyarnes_core.observability.ports import LoggerPort
from pyarnes_core.observe.logger import LogFormat, configure_logging, get_logger

__all__ = ["AuditTaskContext", "bootstrap", "require_graph"]


@dataclass(frozen=True, slots=True)
class AuditTaskContext:
    """Everything the audit task body needs after argument parsing."""

    config: AuditConfig
    logger: LoggerPort
    session_id: str
    trace_id: str


def bootstrap(prog: str) -> AuditTaskContext:
    """Parse ``--root`` / ``--graph``, build :class:`AuditConfig`, return context."""
    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--root", default=".", help="Project root (defaults to cwd).")
    parser.add_argument(
        "--graph",
        default=None,
        help="Override the graph path (defaults to [tool.pyarnes-audit].graph_path).",
    )
    args = parser.parse_args()

    config = AuditConfig.load(args.root)
    if args.graph is not None:
        # Replace just the graph_path while leaving the rest of the config
        # untouched. ``dataclasses.replace`` keeps the frozen dataclass invariant.
        config = replace(config, graph_path=Path(args.graph).resolve())

    configure_logging(level="INFO", fmt=LogFormat.JSON, stream=sys.stderr)
    logger = get_logger(prog)
    return AuditTaskContext(
        config=config,
        logger=logger,
        session_id=uuid.uuid4().hex,
        trace_id=uuid.uuid4().hex,
    )


def require_graph(ctx: AuditTaskContext, prog: str) -> nx.DiGraph | int:
    """Load the persisted graph or print a friendly hint and return exit code 1.

    Centralises the "graph file not found, run `tasks audit:build` first" guard
    that every audit task except ``audit:build`` needs.
    """
    graph_path = ctx.config.graph_path
    if not graph_path.is_file():
        print(  # noqa: T201
            f"{prog}  graph file not found at {graph_path}; run `tasks audit:build` first.",
            file=sys.stderr,
        )
        return 1
    return load_graph(graph_path)
