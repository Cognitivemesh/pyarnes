"""Tests for the structured JSONL logger."""

from __future__ import annotations

import asyncio
import io
import json

from pyarnes_core.observe.logger import configure_logging, get_logger


class TestConfigureLogging:
    """Logger configuration produces JSONL output."""

    def test_json_output(self) -> None:
        buf = io.StringIO()
        configure_logging(level="DEBUG", json=True, stream=buf)
        log = get_logger("test.json")
        log.info("hello")

        line = buf.getvalue().strip()
        data = json.loads(line)
        assert data["event"] == "hello"
        assert "timestamp" in data
        assert data["level"] == "info"

    def test_console_output(self) -> None:
        buf = io.StringIO()
        configure_logging(level="DEBUG", json=False, stream=buf)
        log = get_logger("test.console")
        log.info("visible")

        output = buf.getvalue()
        assert "visible" in output

    def test_extra_sinks_receive_events(self) -> None:
        """Side-channel sinks survive reconfigures when registered here."""
        captured: list[str] = []

        def side_sink(message: object) -> None:
            captured.append(str(message).strip())

        buf = io.StringIO()
        configure_logging(level="DEBUG", json=True, stream=buf, extra_sinks=[side_sink])
        log = get_logger("test.extra")
        log.info("side-channel")
        assert any("side-channel" in line for line in captured)

    def test_scrub_redacts_payload_before_write(self) -> None:
        """``scrub`` rewrites the JSON payload before it reaches the sink."""
        buf = io.StringIO()

        def drop_authorization(payload: dict) -> dict:
            return {k: v for k, v in payload.items() if k != "authorization"}

        configure_logging(level="DEBUG", json=True, stream=buf, scrub=drop_authorization)
        log = get_logger("test.scrub")
        log.bind(authorization="Bearer secret", user_id=42).info("auth.check")

        data = json.loads(buf.getvalue().strip())
        assert "authorization" not in data
        assert data["user_id"] == 42
        assert data["event"] == "auth.check"

    def test_scrub_none_is_noop(self) -> None:
        """Omitting ``scrub`` (default) leaves the payload untouched."""
        buf = io.StringIO()
        configure_logging(level="DEBUG", json=True, stream=buf)
        log = get_logger("test.scrub.none")
        log.bind(marker="abc").info("keep")
        data = json.loads(buf.getvalue().strip())
        assert data["marker"] == "abc"

    def test_concurrent_tasks_stream_isolation(self) -> None:
        """ContextVar isolation: two concurrent tasks each see their own stream.

        Each asyncio Task copies the context at creation time, so a
        ``ContextVar.set()`` in one task must not bleed into the other.
        An explicit ``asyncio.sleep(0)`` yield between set and log forces
        genuine interleaving — proving isolation rather than sequential luck.
        """

        async def _run() -> None:
            buf_a = io.StringIO()
            buf_b = io.StringIO()

            async def task_a() -> None:
                configure_logging(level="DEBUG", json=True, stream=buf_a)
                await asyncio.sleep(0)  # yield so task_b can run
                get_logger("iso.a").info("from-a")

            async def task_b() -> None:
                configure_logging(level="DEBUG", json=True, stream=buf_b)
                await asyncio.sleep(0)  # yield so task_a can run
                get_logger("iso.b").info("from-b")

            await asyncio.gather(task_a(), task_b())

            lines_a = [json.loads(l) for l in buf_a.getvalue().splitlines() if l.strip()]
            lines_b = [json.loads(l) for l in buf_b.getvalue().splitlines() if l.strip()]

            events_a = {d["event"] for d in lines_a}
            events_b = {d["event"] for d in lines_b}

            assert "from-a" in events_a, "task_a stream did not capture its own log"
            assert "from-b" not in events_a, "task_b log bled into task_a stream"
            assert "from-b" in events_b, "task_b stream did not capture its own log"
            assert "from-a" not in events_b, "task_a log bled into task_b stream"

        asyncio.run(_run())
