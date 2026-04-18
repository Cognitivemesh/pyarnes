"""In-memory fake S3 backend used by the reference adopter.

Replacing this module with ``aioboto3`` calls is the single integration
seam between the reference adopter and a real S3 bucket.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass
class FakeS3Object:
    """A single fake object held in the ``FakeS3`` backend."""

    key: str
    body: bytes

    @property
    def size(self) -> int:
        return len(self.body)

    @property
    def etag(self) -> str:
        return hashlib.md5(self.body, usedforsecurity=False).hexdigest()


@dataclass
class FakeS3:
    """Dict-backed S3 stand-in. Not thread-safe; fine for tests."""

    buckets: dict[str, dict[str, FakeS3Object]] = field(default_factory=dict)

    def put(self, bucket: str, key: str, body: bytes) -> None:
        self.buckets.setdefault(bucket, {})[key] = FakeS3Object(key=key, body=body)

    def list_keys(self, bucket: str) -> list[str]:
        return sorted(self.buckets.get(bucket, {}))

    def head(self, bucket: str, key: str) -> dict:
        obj = self.buckets[bucket][key]
        return {"size": obj.size, "etag": obj.etag}

    def get(self, bucket: str, key: str) -> bytes:
        return self.buckets[bucket][key].body

    def delete_bucket(self, bucket: str) -> None:
        self.buckets.pop(bucket, None)
