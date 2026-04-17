"""pyarnes-api — OpenAPI REST interface for the agentic harness.

Exposes harness operations as HTTP endpoints via FastAPI:

* ``/health``            — readiness / liveness probe
* ``/api/v1/lifecycle``  — manage session lifecycle (start, pause, complete, fail)
* ``/api/v1/guardrails`` — validate tool calls against guardrails
* ``/api/v1/tools``      — list and inspect registered tools
* ``/api/v1/eval``       — run evaluation suites
"""

from __future__ import annotations

__all__: list[str] = []

__version__ = "0.1.0"
