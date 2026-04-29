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

from pyarnes_bench.audit import AuditConfig
from pyarnes_core.observability.ports import LoggerPort
from pyarnes_core.observe.logger import LogFormat, configure_logging, get_logger

__all__ = ["AuditTaskContext", "bootstrap"]


@dataclass(frozen=True, slots=True)
class AuditTaskContext:
    """Everything the audit task body needs after argument parsing."""

    config: AuditConfig
    logger: LoggerPort
    session_id: str
    trace_id: str


def bootstrap(prog: str, *, default_step: int = 0) -> AuditTaskContext:
    """Parse ``--root`` / ``--graph``, build :class:`AuditConfig`, return context.

    Args:
        prog: ``argparse`` program name (e.g. ``"tasks audit:build"``).
        default_step: Reserved for callers that want to start their step
            counter somewhere other than zero; kept here so the dataclass
            stays immutable while still giving each task control.
    """
    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument(
        "--root",
        default=".",
        help="Project root containing pyproject.toml (defaults to cwd).",
    )
    parser.add_argument(
        "--graph",
        default=None,
        help="Override the graph path (defaults to [tool.pyarnes-audit].graph_path).",
    )
    args = parser.parse_args()
    _ = default_step  # accepted for API stability; unused today

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
