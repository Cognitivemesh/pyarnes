"""Atomic + private JSON writes for disk-backed hook state.

Every pyarnes hook that persists state between CC invocations
(``rate_limit.json``, ``budget.json``, ``checkpoint.json``,
``violations.jsonl``) funnels through :func:`write_private` so we get
two properties for free:

1. **Atomic** — we write to a sibling ``.tmp`` path, ``fsync``, then
   ``os.replace``; a crash mid-write leaves the prior file intact rather
   than truncating it to zero bytes.
2. **Private** — the file is created with mode ``0o600`` so secrets that
   land in ``violations.jsonl`` (or a malformed tool response the post-
   hook archived) are not world-readable on a shared host.

Append mode is handled by :func:`append_private` which opens the target
with ``os.open`` + explicit ``0o600`` so the first append creates the
file private even if the process umask is lax.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

__all__ = ["append_private", "write_private"]


def write_private(path: Path, content: str) -> None:
    """Write *content* to *path* atomically with ``0o600`` permissions.

    Parent directories are created with mode ``0o700``. The write goes
    to a ``NamedTemporaryFile`` on the same filesystem, is ``fsync``ed,
    then renamed over *path* via :func:`os.replace`.
    """
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Same-dir temp so os.replace is atomic (rename across filesystems
    # is not atomic on Linux).
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    tmp_path.chmod(0o600)
    tmp_path.replace(path)


def append_private(path: Path, line: str) -> None:
    r"""Append *line* (which should already end in ``\n``) with ``0o600``.

    Uses ``os.open`` with ``O_CREAT | O_APPEND | O_WRONLY`` + explicit
    ``0o600`` so that even first-write creates a private file regardless
    of the caller's umask. ``O_NOFOLLOW`` refuses to open a file whose
    final component is a symlink — a symlink there is suspicious enough
    to surface rather than silently write through.
    """
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)
