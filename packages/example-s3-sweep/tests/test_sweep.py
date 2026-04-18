"""End-to-end tests for the S3 sweep reference adopter.

The destructive ``delete_bucket`` path is the key safety surface; these
tests lock down the contract that verification must succeed *before* the
bucket disappears.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from s3_sweep.fakes import FakeS3
from s3_sweep.guardrails import BucketAllowlistGuardrail, VerificationCompleteGuardrail
from s3_sweep.pipeline import download, sweep, verify

from pyarnes_core.errors import UserFixableError


def _seeded(bucket: str = "test-bucket") -> FakeS3:
    s3 = FakeS3()
    s3.put(bucket, "a.txt", b"alpha")
    s3.put(bucket, "b.txt", b"bravo")
    return s3


async def test_full_sweep_flow_succeeds(tmp_path: Path) -> None:
    """A clean bucket downloads → verifies → sweeps without error."""
    s3 = _seeded()
    entries = await download(s3, "test-bucket", str(tmp_path))
    assert len(entries) == 2

    manifest = tmp_path / "manifest.json"
    records = await verify(s3, "test-bucket", entries, str(manifest))
    assert all(r["verified"] for r in records)

    result = await sweep(s3, "test-bucket", str(manifest), frozenset({"test-bucket"}))
    assert "test-bucket" in result
    assert s3.list_keys("test-bucket") == []


async def test_sweep_refuses_when_manifest_missing(tmp_path: Path) -> None:
    """Missing manifest blocks the destructive call."""
    s3 = _seeded()
    with pytest.raises(UserFixableError, match="manifest missing"):
        await sweep(s3, "test-bucket", str(tmp_path / "absent.json"), frozenset({"test-bucket"}))
    assert s3.list_keys("test-bucket") == ["a.txt", "b.txt"]  # bucket untouched


async def test_sweep_refuses_on_corrupted_manifest(tmp_path: Path) -> None:
    """A single unverified entry blocks the destructive call."""
    s3 = _seeded()
    entries = await download(s3, "test-bucket", str(tmp_path))
    manifest_path = tmp_path / "manifest.json"
    await verify(s3, "test-bucket", entries, str(manifest_path))

    # Corrupt one record — simulate a checksum mismatch after verification.
    manifest = json.loads(manifest_path.read_text())
    manifest["objects"][0]["verified"] = False
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(UserFixableError, match="unverified"):
        await sweep(s3, "test-bucket", str(manifest_path), frozenset({"test-bucket"}))
    # Bucket must be untouched.
    assert set(s3.list_keys("test-bucket")) == {"a.txt", "b.txt"}


def test_verification_guardrail_only_fires_on_delete(tmp_path: Path) -> None:
    """The guardrail is scoped to ``delete_bucket``, not other tools."""
    guardrail = VerificationCompleteGuardrail(manifest_path=str(tmp_path / "manifest.json"))
    # No manifest present, but the call is not ``delete_bucket`` — must not raise.
    guardrail.check("download_object", {"bucket": "x", "key": "y"})


def test_bucket_allowlist_blocks_unapproved() -> None:
    """Calls against buckets outside the allowlist are rejected."""
    guardrail = BucketAllowlistGuardrail(allowed_buckets=frozenset({"approved"}))
    with pytest.raises(UserFixableError, match="not in the allowlist"):
        guardrail.check("delete_bucket", {"bucket": "rogue"})
