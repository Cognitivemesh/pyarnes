# pii-redaction examples

Standalone PEP 723 scripts demonstrating text extraction and PII-adjacent
operations. No pyarnes dependency; no project-wide install.

## extract-pdf.py

Extract raw text from a PDF using [kreuzberg](https://pypi.org/project/kreuzberg/).

```bash
uv run scripts/examples/pii-redaction/extract-pdf.py path/to.pdf
```

First run downloads `kreuzberg` into an isolated cached env. Later runs
reuse the cache.

## Lifting this into your project

When you're ready to integrate extraction into your app, do **not** import
this script. Instead:

1. Add `kreuzberg>=1.0,<2` to `[project.dependencies]` in `pyproject.toml`.
2. Call `kreuzberg.extract_file(...)` from the relevant module in
   `src/{{ project_module }}/` (or from an agent-loop tool handler under
   `.claude/agent_kit/tools/`).
