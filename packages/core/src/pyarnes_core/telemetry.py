"""Optional OpenTelemetry tracing integration.

When ``opentelemetry-sdk`` and ``opentelemetry-exporter-otlp`` are installed
(``pip install pyarnes-core[otel]``) this module sets up a :class:`TracerProvider`
that exports spans to an OTLP endpoint.  When the SDK is absent every public
symbol degrades gracefully — ``configure_tracing`` is a no-op, ``get_tracer``
returns a zero-overhead no-op tracer, and context managers yield immediately
without allocating any span objects.

Usage with ``AgentRuntime``
---------------------------
Set ``OTEL_EXPORTER_OTLP_ENDPOINT`` (and optionally ``OTEL_SERVICE_NAME``) in
the environment before running the agent.  ``AgentRuntime.run()`` calls
``configure_tracing()`` automatically when the endpoint variable is present.

Span shape
----------
Spans created here mirror the fields emitted by ``log_lifecycle_transition``
and ``log_tool_call`` from ``pyarnes_core.observability`` so a single trace
backend can correlate log events with distributed traces.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Generator
from typing import Any

__all__ = [
    "configure_tracing",
    "get_tracer",
    "session_span",
]


# ── Internal state ────────────────────────────────────────────────────────────

_configured = False


# ── No-op fallbacks (always importable, zero overhead) ────────────────────────


class _NoOpSpan:
    """Minimal span interface that accepts set_attribute calls silently."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, *_: object) -> None:
        pass


class _NoOpTracer:
    """Tracer that produces no-op spans — used when OTEL SDK is absent."""

    def start_as_current_span(self, _name: str, **_kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()


_noop_tracer = _NoOpTracer()


# ── Public API ────────────────────────────────────────────────────────────────


def configure_tracing(endpoint: str, service_name: str) -> None:
    """Set up a global OTLP TracerProvider.

    No-op when ``opentelemetry-sdk`` is not installed.

    Args:
        endpoint: OTLP collector endpoint (e.g. ``"http://localhost:4317"``).
        service_name: Logical name for this agent service in the trace backend.
    """
    global _configured  # noqa: PLW0603

    try:
        from opentelemetry import trace  # noqa: PLC0415  # type: ignore[import-untyped]
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # noqa: PLC0415
            OTLPSpanExporter,  # type: ignore[import-untyped]
        )
        from opentelemetry.sdk.resources import Resource  # noqa: PLC0415  # type: ignore[import-untyped]
        from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415  # type: ignore[import-untyped]
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # noqa: PLC0415  # type: ignore[import-untyped]
    except ImportError:
        return

    resource = Resource(attributes={"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    _configured = True


def get_tracer(name: str) -> Any:
    """Return an OpenTelemetry tracer, or a no-op tracer when OTEL is absent.

    Args:
        name: Instrumentation scope name (typically ``__name__``).

    Returns:
        A real :class:`opentelemetry.trace.Tracer` when the SDK is installed
        and :func:`configure_tracing` has been called; otherwise a
        :class:`_NoOpTracer` instance.
    """
    if not _configured:
        return _noop_tracer
    try:
        from opentelemetry import trace  # noqa: PLC0415  # type: ignore[import-untyped]

        return trace.get_tracer(name)
    except ImportError:
        return _noop_tracer


@contextlib.contextmanager
def session_span(
    service_name: str,
    *,
    session_id: str,
    trace_id: str,
) -> Generator[Any]:
    """Context manager that wraps a session in an OTEL span.

    Attributes added to the span match the fields emitted by
    ``log_lifecycle_transition`` so a trace backend can correlate both.

    When OTEL is not configured this is a zero-cost no-op.

    Args:
        service_name: Human-readable label for the span (e.g. ``"agent-session"``).
        session_id: The agent session identifier.
        trace_id: The distributed trace identifier.

    Yields:
        The current span (real or no-op).
    """
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span(service_name) as span:
        span.set_attribute("session_id", session_id)
        span.set_attribute("trace_id", trace_id)
        yield span


def tracing_endpoint_from_env() -> str | None:
    """Return the OTLP endpoint from ``OTEL_EXPORTER_OTLP_ENDPOINT``, or ``None``."""
    return os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
