# Installation

## Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) package manager

## Install from source

```bash
git clone https://github.com/Cognitivemesh/pyarnes.git
cd pyarnes
uv sync
```

This installs all three workspace packages (`pyarnes`, `pyarnes-core`, `pyarnes-harness`) and their dev dependencies.

## Verify installation

```bash
uv run tasks check
```
