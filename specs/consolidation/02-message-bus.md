# pyarnes_swarm — MessageBus

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — Message Bus |
> | **Status** | active |
> | **Type** | core-runtime |
> | **Owns** | MessageBus Protocol, Turso/InMemory/NATS implementations, message serialization, offset/resume semantics |
> | **Depends on** | 01-package-structure.md |
> | **Extends** | — |
> | **Supersedes** | — |
> | **Read after** | 01-package-structure.md |
> | **Read before** | 03-model-router.md |
> | **Not owned here** | model selection (see `03-model-router.md`); provider config (see `10-provider-config.md`); transport adapters (see `22-transport.md`) — the bus is inter-agent messaging only, not model-call plumbing |
> | **Last reviewed** | 2026-04-29 |

## Why a MessageBus?

`pyarnes_swarm` runs agents as **separate OS processes** to avoid Python GIL contention and context loss from sub-agent spawning in the same process. Separate processes cannot share in-process queues. A `MessageBus` gives them a durable, typed channel to coordinate.

Use cases:
- Parent agent dispatches tasks to a pool of sub-agents and collects results
- Sub-agent reports intermediate progress back to an orchestrator
- Agent crash recovery: replay from a durable offset after restart

## Design Rationale

**Why separate OS processes instead of async tasks?** Python's GIL prevents true CPU parallelism in threads. Two agents sharing a process also share memory — a crash, a rogue `sys.exit()`, or an OOM in one agent can corrupt the other's state. Separate processes isolate failures.

**Why MVCC in TursoMessageBus instead of WAL SQLite?** Standard SQLite WAL mode allows concurrent readers but still serialises writers — one writer at a time. In a swarm where 4 agents publish results simultaneously, that serialisation creates a bottleneck. Turso/Limbo uses Multi-Version Concurrency Control (MVCC), the same technique PostgreSQL uses: writers create new row versions instead of locking rows, so multiple agents write without blocking each other.

**Why `resume_from(topic, offset)` in the Protocol?** Agents crash. Without replay, a crash means lost work. `offset` is a monotonic message ID — the agent records the last offset it processed, and on restart, replays from there. This is the event sourcing pattern applied to agent coordination.

**Why three implementations instead of one configurable one?** Each implementation answers a different question: InMemoryBus answers "how do I test?", TursoMessageBus answers "how do I run locally without infra?", NatsJetStreamBus answers "how do I scale?". Trying to make one implementation answer all three questions produces a complex class that does none of them well.

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
    # run_parallel takes (agent_name, messages) tuples — same format as run_agent
    results = await swarm.run_parallel([
        ("worker-1", [{"role": "user", "content": "Summarise file a.py"}]),
        ("worker-2", [{"role": "user", "content": "Summarise file b.py"}]),
    ])
    for res in results:
        if isinstance(res, Exception):
            print("task failed:", res)
        else:
            print(res[-1]["content"])

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

## Key concepts

### MVCC (Multi-Version Concurrency Control)

**What**: A database concurrency mechanism where writers create new versions of rows instead of locking them. Readers always see a consistent snapshot; writers don't block each other.

**Why Used Here**: `TursoMessageBus` needs multiple agent OS processes to write messages simultaneously. Standard SQLite WAL mode still serialises writers — one writer at a time. Turso/Limbo uses MVCC so agent-1 publishing `"task.start"` doesn't block agent-2 publishing `"task.progress"`.

**When to Use**: Any scenario with concurrent writes and need for consistent reads. PostgreSQL, CockroachDB, and FoundationDB all use MVCC.

**Learning**: [MVCC in PostgreSQL](https://www.postgresql.org/docs/current/mvcc-intro.html) — the same technique Turso/Limbo uses, explained in depth

---

### Event Sourcing (resume_from pattern)

`MessageBus.resume_from(topic, offset)` is event sourcing applied to agent coordination. `offset` is a monotonic message ID — each agent records the last offset it processed, and on restart replays from there. This recovers from crashes without losing work. Understanding event sourcing explains why `offset` exists as a first-class parameter rather than being hidden inside the bus.

## Event Sourcing via `resume_from` Offset

To provide resilient crash-recovery across sessions, the Message Bus implements monotonic offset checkpointing via a `resume_from(topic, offset)` semantic. 
Each message in a topic receives a strictly monotonic integer ID over the session stream. If the sub-agent or `AgentLoop` terminates abruptly, it seamlessly checkpoints the last successfully processed offset into the local database. Upon restart, it re-connects using `resume_from` to replay any unacknowledged events rather than losing state. This provides event-sourcing with effectively exactly-once execution semantics.
