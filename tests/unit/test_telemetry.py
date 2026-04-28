"""Tests for the optional OpenTelemetry telemetry module."""

from __future__ import annotations

import pytest

import pyarnes_core.telemetry as telemetry_module
from pyarnes_core.telemetry import (
    _NoOpSpan,
    _NoOpTracer,
    configure_tracing,
    get_tracer,
    session_span,
    tracing_endpoint_from_env,
)


class TestNoOpSpan:
    """No-op span satisfies the minimal span interface."""

    def test_set_attribute_is_silent(self) -> None:
        span = _NoOpSpan()
        span.set_attribute("key", "value")  # must not raise

    def test_context_manager_yields_self(self) -> None:
        span = _NoOpSpan()
        with span as s:
            assert s is span


class TestNoOpTracer:
    """No-op tracer returns no-op spans."""

    def test_start_as_current_span_returns_noop_span(self) -> None:
        tracer = _NoOpTracer()
        span = tracer.start_as_current_span("test-span")
        assert isinstance(span, _NoOpSpan)


class TestConfigureTracingNoSDK:
    """configure_tracing is a no-op when opentelemetry is absent."""

    def test_configure_tracing_no_op_when_sdk_missing(self, monkeypatch) -> None:
        def _block_otel(name: str, *args: object, **kwargs: object) -> object:
            if name.startswith("opentelemetry"):
                raise ImportError(f"blocked: {name}")
            return __import__(name, *args, **kwargs)  # type: ignore[no-untyped-call]

        monkeypatch.setattr(telemetry_module, "_configured", False)
        monkeypatch.setattr("builtins.__import__", _block_otel)

        configure_tracing(endpoint="http://localhost:4317", service_name="test")
        assert telemetry_module._configured is False


class TestGetTracer:
    """get_tracer returns the no-op tracer when OTEL is not configured."""

    def test_returns_noop_when_not_configured(self, monkeypatch) -> None:
        monkeypatch.setattr(telemetry_module, "_configured", False)
        tracer = get_tracer("test.module")
        assert isinstance(tracer, _NoOpTracer)


class TestSessionSpan:
    """session_span context manager works without OTEL."""

    @pytest.mark.asyncio()
    async def test_session_span_yields_without_error(self, monkeypatch) -> None:
        monkeypatch.setattr(telemetry_module, "_configured", False)
        entered = False
        with session_span("agent-session", session_id="abc", trace_id="xyz") as span:
            entered = True
            span.set_attribute("test", "ok")  # must not raise
        assert entered

    @pytest.mark.asyncio()
    async def test_session_span_re_raises_exceptions(self, monkeypatch) -> None:
        monkeypatch.setattr(telemetry_module, "_configured", False)
        with pytest.raises(ValueError, match="boom"), session_span("agent-session", session_id="s", trace_id="t"):
            raise ValueError("boom")


class TestTracingEndpointFromEnv:
    """tracing_endpoint_from_env reads the OTEL env var."""

    def test_returns_none_when_unset(self, monkeypatch) -> None:
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        assert tracing_endpoint_from_env() is None

    def test_returns_value_when_set(self, monkeypatch) -> None:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4317")
        assert tracing_endpoint_from_env() == "http://collector:4317"
