"""Guardrails specific to the S3 download-verify-delete pipeline."""

from __future__ import annotations

import json
from pathlib import Path

from pyarnes_core.errors import UserFixableError
from pyarnes_guardrails import Guardrail


class VerificationCompleteGuardrail(Guardrail):
    """Block ``delete_bucket`` unless the manifest reports every object verified."""

    def __init__(self, manifest_path: str) -> None:
        self.manifest_path = manifest_path

    def check(self, tool_name: str, arguments: dict) -> None:
        if tool_name != "delete_bucket":
            return
        manifest_file = Path(self.manifest_path)
        if not manifest_file.exists():
            raise UserFixableError(
                message=f"verification manifest missing at {self.manifest_path}",
                prompt_hint="Run the verify step before sweeping the bucket.",
            )
        manifest = json.loads(manifest_file.read_text())
        unverified = [o for o in manifest.get("objects", []) if not o.get("verified")]
        if unverified:
            raise UserFixableError(
                message=f"{len(unverified)} objects unverified; refusing delete_bucket",
                prompt_hint=(
                    "Failing keys: "
                    + ", ".join(sorted(o["key"] for o in unverified))
                ),
            )


class BucketAllowlistGuardrail(Guardrail):
    """Refuse any tool call targeting a bucket outside the allowlist."""

    def __init__(self, allowed_buckets: frozenset[str]) -> None:
        self.allowed_buckets = allowed_buckets

    def check(self, tool_name: str, arguments: dict) -> None:
        bucket = arguments.get("bucket")
        if bucket is not None and bucket not in self.allowed_buckets:
            raise UserFixableError(
                message=f"bucket {bucket!r} is not in the allowlist",
                prompt_hint=f"Allowed buckets: {sorted(self.allowed_buckets)}",
            )
