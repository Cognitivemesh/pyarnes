# example-s3-sweep

Reference implementation of **Adopter B** for pyarnes (see
[`specs/03-examples-adopter-a-and-b.md`](../../specs/03-examples-adopter-a-and-b.md)).

Shape: **download-verify-delete**. List an S3 bucket → download all objects
→ verify each (size + etag + checksum) → delete the bucket **only after**
every object has been verified.

The destructive ``delete_bucket`` tool is gated by
``VerificationCompleteGuardrail``: the guardrail reads the verification
manifest and raises ``UserFixableError`` if any entry is unverified or has
a checksum mismatch. The S3 integration uses a fake client so tests are
self-contained; swap in ``boto3``/``aioboto3`` for production.

## Commands

```bash
uv run s3-sweeper download --bucket my-bucket --dest ./out
uv run s3-sweeper verify --manifest ./out/manifest.json
uv run s3-sweeper sweep   --bucket my-bucket --manifest ./out/manifest.json
```
