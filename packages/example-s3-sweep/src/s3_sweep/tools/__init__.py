"""Tool handlers for the S3 sweep pipeline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pyarnes_core.types import ToolHandler
from pyarnes_harness import ToolRegistry
from s3_sweep.fakes import FakeS3


class ListObjects(ToolHandler):
    """Return every key in ``arguments['bucket']``."""

    def __init__(self, s3: FakeS3) -> None:
        self.s3 = s3

    async def execute(self, arguments: dict) -> list[str]:
        return self.s3.list_keys(arguments["bucket"])


class DownloadObject(ToolHandler):
    """Download ``arguments['key']`` from ``arguments['bucket']`` into ``dest``."""

    def __init__(self, s3: FakeS3) -> None:
        self.s3 = s3

    async def execute(self, arguments: dict) -> dict:
        bucket, key, dest_dir = arguments["bucket"], arguments["key"], arguments["dest"]
        body = self.s3.get(bucket, key)
        target = Path(dest_dir) / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        return {"key": key, "path": str(target), "size": len(body)}


class VerifyObject(ToolHandler):
    """Compare local file metadata against S3 metadata.

    Returns an entry suitable for the verification manifest.
    """

    def __init__(self, s3: FakeS3) -> None:
        self.s3 = s3

    async def execute(self, arguments: dict) -> dict:
        bucket, key, path = arguments["bucket"], arguments["key"], arguments["path"]
        remote = self.s3.head(bucket, key)
        body = Path(path).read_bytes()
        local_size = len(body)
        local_etag = hashlib.md5(body, usedforsecurity=False).hexdigest()
        verified = local_size == remote["size"] and local_etag == remote["etag"]
        return {
            "key": key,
            "path": path,
            "size": local_size,
            "etag": local_etag,
            "verified": verified,
        }


class DeleteBucket(ToolHandler):
    """Delete ``arguments['bucket']``. Gated upstream by the guardrail chain."""

    def __init__(self, s3: FakeS3) -> None:
        self.s3 = s3

    async def execute(self, arguments: dict) -> str:
        self.s3.delete_bucket(arguments["bucket"])
        return f"deleted s3://{arguments['bucket']}"


class WriteManifest(ToolHandler):
    """Persist the accumulated verification entries to ``arguments['path']``."""

    async def execute(self, arguments: dict) -> str:
        path = Path(arguments["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"objects": arguments["objects"]}, indent=2))
        return str(path)


def register_tools(registry: ToolRegistry, *, s3: FakeS3) -> None:
    """Register every S3-sweep tool on ``registry`` bound to ``s3``."""
    registry.register("list_objects", ListObjects(s3))
    registry.register("download_object", DownloadObject(s3))
    registry.register("verify_object", VerifyObject(s3))
    registry.register("delete_bucket", DeleteBucket(s3))
    registry.register("write_manifest", WriteManifest())
