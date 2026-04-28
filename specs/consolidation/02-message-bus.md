# pyarnes_swarm — MessageBus

## Why a MessageBus?

`pyarnes_swarm` runs agents as **separate OS processes** to avoid Python GIL contention and context loss from sub-agent spawning in the same process. Separate processes cannot share in-process queues. A `MessageBus` gives them a durable, typed channel to coordinate.

Use cases:
- Parent agent dispatches tasks to a pool of sub-agents and collects results
- Sub-agent reports intermediate progress back to an orchestrator
- Agent crash recovery: replay from a durable offset after restart

## Protocol (`ports.py`)

```python
class MessageBus(Protocol):
    async def publish(self, topic: str, payload: bytes) -> None: ...
    async def subscribe(self, topic: str) -> AsyncIterator[bytes]: ...
    async def resume_from(self, topic: str, offset: int) -> AsyncIterator[bytes]: ...
```

`topic` is a free-form string (e.g. `"agent.tasks"`, `"agent.results.worker-1"`).
`payload` is raw bytes — callers decide serialization (JSON, msgpack, protobuf).
`resume_from` enables replay from a known offset after restart.

## Implementations

### `TursoMessageBus` — default (BETA)

Backed by **Turso/Limbo**: an in-process Rust rewrite of SQLite with MVCC concurrent writes. Multiple agent OS processes can write simultaneously without the serialization issue of standard SQLite WAL mode.

```python
class TursoMessageBus:
    """
    BETA: Backed by Turso/Limbo embedded database.
    MVCC enables concurrent writes from multiple agent processes.

    Requires: pip install pyturso (included in core deps)

    Use InMemoryBus in tests. Use NatsJetStreamBus for production.
    """
    def __init__(self, db_path: str | Path = ":memory:") -> None: ...
    async def publish(self, topic: str, payload: bytes) -> None: ...
    async def subscribe(self, topic: str) -> AsyncIterator[bytes]: ...
    async def resume_from(self, topic: str, offset: int) -> AsyncIterator[bytes]: ...
```

Schema (managed internally, not exposed):
```sql
CREATE TABLE messages (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    topic   TEXT NOT NULL,
    payload BLOB NOT NULL,
    ts      INTEGER NOT NULL DEFAULT (unixepoch('subsec') * 1000)
);
CREATE INDEX idx_messages_topic ON messages (topic, id);
```

**Beta label:** Turso/Limbo is a stable project but the Python binding (`pyturso`) is newer. Treat `TursoMessageBus` as production-ready for small-to-medium agent swarms; benchmark before using at high throughput.

### `InMemoryBus` — tests

Zero-infra bus. Does not persist across process restarts. Use in unit tests via `pytest` fixture injection.

```python
class InMemoryBus:
    """Async in-memory bus. No persistence. No inter-process visibility."""
    async def publish(self, topic: str, payload: bytes) -> None: ...
    async def subscribe(self, topic: str) -> AsyncIterator[bytes]: ...
    async def resume_from(self, topic: str, offset: int) -> AsyncIterator[bytes]: ...
```

### `NatsJetStreamBus` — production optional extra

Production-grade persistent messaging via NATS JetStream. Requires a running NATS server. `nats-py` is a client library — the server is separate infrastructure.

```python
# Only importable when pip install pyarnes_swarm[nats]
class NatsJetStreamBus:
    """
    Production-grade bus backed by NATS JetStream.
    Requires: pip install pyarnes_swarm[nats] + a running nats-server.

    Best for: large agent swarms, cross-host coordination, high throughput.
    """
    def __init__(self, servers: list[str] | None = None) -> None: ...
    async def connect(self) -> None: ...
    async def close(self) -> None: ...
    async def publish(self, topic: str, payload: bytes) -> None: ...
    async def subscribe(self, topic: str) -> AsyncIterator[bytes]: ...
    async def resume_from(self, topic: str, offset: int) -> AsyncIterator[bytes]: ...
```

## Choosing a bus

| Bus | When to use |
|---|---|
| `InMemoryBus` | Tests, single-process prototyping |
| `TursoMessageBus` | Default — local dev, small cloud deployments, no infra required |
| `NatsJetStreamBus` | Large agent swarms, cross-host, high throughput, production SLAs |

## Usage example

```python
import asyncio
from pyarnes_swarm import TursoMessageBus, Swarm, AgentSpec

bus = TursoMessageBus(db_path=".pyarnes/swarm.db")

swarm = Swarm(
    bus=bus,
    agents=[
        AgentSpec(name="worker-1", model="claude-haiku-4-5"),
        AgentSpec(name="worker-2", model="claude-haiku-4-5"),
    ],
)

async def main():
    # Dispatch tasks; workers pick them up from the bus
    await swarm.run_parallel(["Summarise file a.py", "Summarise file b.py"])

asyncio.run(main())
```

## Message serialization convention

The bus transports raw bytes. The recommended convention is newline-delimited JSON (NDJSON):

```python
import json

payload = json.dumps({"task": "summarise", "path": "a.py"}).encode()
await bus.publish("agent.tasks", payload)

async for raw in bus.subscribe("agent.tasks"):
    task = json.loads(raw)
```

This keeps the bus generic while preserving human-readability.
