# s3-sweep examples

Standalone PEP 723 scripts demonstrating S3 operations. No pyarnes
dependency; no project-wide install.

## list-bucket.py

List the first page of objects in an S3 bucket using
[boto3](https://pypi.org/project/boto3/).

```bash
uv run scripts/examples/s3-sweep/list-bucket.py my-bucket
```

Credentials come from the standard AWS chain (env vars, profile, instance
metadata). First run downloads `boto3` into an isolated cached env.

## Lifting this into your project

When you're ready to integrate S3 into your app:

1. Add `boto3>=1.35` (and `aioboto3>=13.0` for async) to
   `[project.dependencies]` in `pyproject.toml`.
2. Call the clients from `src/{{ project_module }}/` or from a
   `ToolHandler` under `.claude/agent_kit/tools/`.
