# example-pii-pipeline

Reference implementation of **Adopter A** for pyarnes (see
[`specs/03-examples-adopter-a-and-b.md`](../../specs/03-examples-adopter-a-and-b.md)).

Shape: **PII redaction pipeline**. Ingest a document → extract text → detect
PII → redact → render markdown → rank TF-IDF keywords.

Every symbol imported from pyarnes is part of the stable public surface
declared in [`CHANGELOG.md`](../../CHANGELOG.md). The tools and guardrails
here use regex-based stubs in place of Kreuzberg and Presidio so the test
suite stays fast and self-contained. Swap in the real integrations when
adopting this shape for production.

## Commands

```bash
uv run pii-pipeline ingest path/to/doc.pdf --output-dir ./out
uv run pii-pipeline redact path/to/doc.pdf --output-dir ./out
```
