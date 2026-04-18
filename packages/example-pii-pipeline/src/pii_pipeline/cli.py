"""Typer CLI for the PII-redaction reference adopter."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from pii_pipeline.pipeline import redact

app = typer.Typer(help="Reference PII-redaction pipeline.")


@app.command()
def ingest(input_path: str, output_dir: str = "./out") -> None:
    """Extract raw text from ``input_path`` into ``output_dir``."""
    dest = Path(output_dir)
    dest.mkdir(parents=True, exist_ok=True)
    text = Path(input_path).read_text(encoding="utf-8")
    (dest / (Path(input_path).stem + ".txt")).write_text(text)
    typer.echo(f"wrote {dest / (Path(input_path).stem + '.txt')}")


@app.command()
def redact_cmd(input_path: str, output_dir: str = "./out") -> None:
    """Run the full PII-redaction pipeline on ``input_path``."""
    dest = Path(output_dir)
    dest.mkdir(parents=True, exist_ok=True)
    markdown = asyncio.run(redact(input_path))
    target = dest / (Path(input_path).stem + ".md")
    target.write_text(markdown)
    typer.echo(f"wrote {target}")


# Register under the plain `redact` name for the CLI surface.
app.command(name="redact")(redact_cmd)


if __name__ == "__main__":  # pragma: no cover
    app()
