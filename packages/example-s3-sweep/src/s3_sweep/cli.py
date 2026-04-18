"""Typer CLI for the S3 sweep reference adopter."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from s3_sweep.fakes import FakeS3
from s3_sweep.pipeline import build_registry
from s3_sweep.pipeline import download as pipeline_download
from s3_sweep.pipeline import sweep as pipeline_sweep
from s3_sweep.pipeline import verify as pipeline_verify

app = typer.Typer(help="S3 download-verify-delete reference pipeline.")


@app.command()
def download(bucket: str, dest: str = "./out") -> None:
    """Download every object from ``bucket`` into ``dest``."""
    s3 = _seed_from_env()
    registry = build_registry(s3=s3)
    entries = asyncio.run(pipeline_download(s3, bucket, dest, registry=registry))
    (Path(dest) / "downloads.json").write_text(json.dumps(entries, indent=2))
    typer.echo(f"downloaded {len(entries)} objects")


@app.command()
def verify(bucket: str, dest: str = "./out", manifest: str = "./out/manifest.json") -> None:
    """Verify every downloaded object and write the manifest."""
    s3 = _seed_from_env()
    registry = build_registry(s3=s3)
    entries = json.loads((Path(dest) / "downloads.json").read_text())
    records = asyncio.run(pipeline_verify(s3, bucket, entries, manifest, registry=registry))
    typer.echo(f"verified {sum(1 for r in records if r['verified'])}/{len(records)}")


@app.command()
def sweep(bucket: str, manifest: str = "./out/manifest.json") -> None:
    """Delete ``bucket`` after the guardrail chain confirms every object verified."""
    s3 = _seed_from_env()
    registry = build_registry(s3=s3)
    typer.echo(
        asyncio.run(pipeline_sweep(s3, bucket, manifest, frozenset({bucket}), registry=registry)),
    )


def _seed_from_env() -> FakeS3:
    """Placeholder: real adopters replace this with a boto3/aioboto3 client."""
    return FakeS3()


if __name__ == "__main__":  # pragma: no cover
    app()
