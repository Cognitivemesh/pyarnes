# pyarnes-api

OpenAPI REST interface for the pyarnes agentic harness, built with [FastAPI](https://fastapi.tiangolo.com/).

## What it provides

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Readiness / liveness probe |
| `/api/v1/lifecycle` | GET | Get current session phase |
| `/api/v1/lifecycle/transition` | POST | Start, pause, resume, complete, or fail |
| `/api/v1/lifecycle/reset` | POST | Reset session back to INIT |
| `/api/v1/guardrails/check` | POST | Validate a tool call against guardrails |
| `/api/v1/tools` | GET | List registered tools |
| `/api/v1/tools/{name}` | GET | Get a specific tool |
| `/api/v1/eval` | POST | Run an evaluation suite and get scores |
| `/docs` | GET | Interactive Swagger UI |
| `/redoc` | GET | ReDoc documentation |
| `/openapi.json` | GET | OpenAPI 3.1 specification |

## Running the server

```bash
uv run uvicorn pyarnes_api.app:app --reload
```

Then open <http://localhost:8000/docs> for the interactive API docs.

## Example requests

### Check guardrails

```bash
curl -X POST http://localhost:8000/api/v1/guardrails/check \
  -H "Content-Type: application/json" \
  -d '{"tool_name": "shell", "arguments": {"command": "ls -la"}}'
```

Response:

```json
{"allowed": true, "violation": null}
```

### Manage lifecycle

```bash
curl -X POST http://localhost:8000/api/v1/lifecycle/transition \
  -H "Content-Type: application/json" \
  -d '{"action": "start"}'
```

### Run evaluations

```bash
curl -X POST http://localhost:8000/api/v1/eval \
  -H "Content-Type: application/json" \
  -d '{
    "suite_name": "my-eval",
    "scenarios": [
      {"scenario": "test1", "expected": "hello", "actual": "hello"},
      {"scenario": "test2", "expected": "world", "actual": "earth"}
    ]
  }'
```

## Dependencies

- `pyarnes-core`, `pyarnes-harness`, `pyarnes-guardrails`, `pyarnes-bench`
- `fastapi` — web framework
- `uvicorn` — ASGI server
