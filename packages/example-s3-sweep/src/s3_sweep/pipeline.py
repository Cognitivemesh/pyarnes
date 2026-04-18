"""Orchestrate the S3 download-verify-delete pipeline."""

from __future__ import annotations

from pyarnes_core.observe.logger import get_logger
from pyarnes_guardrails import GuardrailChain, PathGuardrail, ToolAllowlistGuardrail
from pyarnes_harness import ToolCallLogger, ToolRegistry
from s3_sweep.fakes import FakeS3
from s3_sweep.guardrails import BucketAllowlistGuardrail, VerificationCompleteGuardrail
from s3_sweep.tools import register_tools

log = get_logger(__name__)


def build_registry(*, s3: FakeS3) -> ToolRegistry:
    """Return a ``ToolRegistry`` populated with every S3-sweep tool."""
    registry = ToolRegistry()
    register_tools(registry, s3=s3)
    return registry


def build_chain(
    *,
    allowed_roots: tuple[str, ...],
    allowed_buckets: frozenset[str],
    manifest_path: str,
    tool_names: frozenset[str],
) -> GuardrailChain:
    """Compose the guardrail chain with the project-specific constraints."""
    return GuardrailChain(guardrails=[
        PathGuardrail(allowed_roots=allowed_roots),
        ToolAllowlistGuardrail(allowed_tools=tool_names),
        BucketAllowlistGuardrail(allowed_buckets=allowed_buckets),
        VerificationCompleteGuardrail(manifest_path=manifest_path),
    ])


async def download(
    s3: FakeS3,
    bucket: str,
    dest_dir: str,
    logger: ToolCallLogger | None = None,
    registry: ToolRegistry | None = None,
) -> list[dict]:
    """Download every object in ``bucket`` to ``dest_dir``. Returns the download log."""
    tools = (registry or build_registry(s3=s3)).as_dict()
    keys = await tools["list_objects"].execute({"bucket": bucket})
    entries = []
    for key in keys:
        entry = await tools["download_object"].execute({"bucket": bucket, "key": key, "dest": dest_dir})
        entries.append(entry)
        if logger is not None:
            logger.log_call("download_object", {"bucket": bucket, "key": key}, result=str(entry))
    log.info("sweep.download bucket={bucket} count={count}", bucket=bucket, count=len(entries))
    return entries


async def verify(
    s3: FakeS3,
    bucket: str,
    entries: list[dict],
    manifest_path: str,
    logger: ToolCallLogger | None = None,
    registry: ToolRegistry | None = None,
) -> list[dict]:
    """Verify every downloaded object; write the manifest; return verification records."""
    tools = (registry or build_registry(s3=s3)).as_dict()
    records = []
    for entry in entries:
        record = await tools["verify_object"].execute(
            {"bucket": bucket, "key": entry["key"], "path": entry["path"]},
        )
        records.append(record)
        if logger is not None:
            logger.log_call("verify_object", {"key": entry["key"]}, result=str(record))
    await tools["write_manifest"].execute({"path": manifest_path, "objects": records})
    return records


async def sweep(
    s3: FakeS3,
    bucket: str,
    manifest_path: str,
    allowed_buckets: frozenset[str],
    logger: ToolCallLogger | None = None,
    registry: ToolRegistry | None = None,
) -> str:
    """Delete ``bucket`` after the guardrail chain confirms every object is verified."""
    registry = registry or build_registry(s3=s3)
    tools = registry.as_dict()
    chain = build_chain(
        allowed_roots=(".",),
        allowed_buckets=allowed_buckets,
        manifest_path=manifest_path,
        tool_names=frozenset(registry.names),
    )
    args = {"bucket": bucket}
    chain.check("delete_bucket", args)
    result = await tools["delete_bucket"].execute(args)
    if logger is not None:
        logger.log_call("delete_bucket", args, result=result)
    return result
