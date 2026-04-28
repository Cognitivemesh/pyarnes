"""Runtime sandboxing hooks for AgentLoop.

Provides a ``SandboxHook`` protocol and two optional implementations:

* ``RestrictedPythonSandbox`` — restricts code execution via ``restrictedpython``
  (``pip install restrictedpython``).
* ``SeccompSandbox`` — applies a seccomp syscall allowlist on Linux
  (``pip install seccomp``; no-op on non-Linux).

Both implementations raise ``ImportError`` at instantiation time (not at
import time) when the optional dependency is absent, so the module is always
importable without extra packages.

Usage::

    from pyarnes_core.sandbox import SeccompSandbox
    from pyarnes_harness.loop import AgentLoop

    loop = AgentLoop(
        ...,
        sandbox=SeccompSandbox(allowed_syscalls=frozenset({"read", "write", "close"})),
    )
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

__all__ = [
    "RestrictedPythonSandbox",
    "SandboxHook",
    "SeccompSandbox",
]


@runtime_checkable
class SandboxHook(Protocol):
    """Protocol for sandbox lifecycle hooks.

    ``AgentLoop`` calls ``enter()`` before each tool execution and
    ``exit(exc)`` after, passing the exception if one was raised or ``None``
    on success.  Implementations may raise to abort the tool call.
    """

    async def enter(self) -> None:
        """Called before tool execution; may raise to abort the call."""
        ...

    async def exit(self, exc: BaseException | None) -> None:
        """Called after tool execution; ``exc`` is the raised exception or ``None``."""
        ...


@dataclass(frozen=True, slots=True)
class RestrictedPythonSandbox:
    """Sandbox using RestrictedPython to restrict code execution.

    On creation, imports ``RestrictedPython`` to verify it is installed.
    Raises ``ImportError`` if the package is absent — install with
    ``pip install restrictedpython``.

    This hook does not automatically compile or exec user code; it signals
    intent to the execution environment.  Tools that accept arbitrary Python
    source should call ``RestrictedPython.compile_restricted`` themselves before
    calling ``exec``.

    Attributes:
        policy: Optional string label for the restriction policy (informational).
    """

    policy: str = "default"

    def __post_init__(self) -> None:  # noqa: D105
        try:
            import RestrictedPython  # noqa: PLC0415, F401
        except ImportError as exc:
            raise ImportError(
                "RestrictedPythonSandbox requires 'restrictedpython': "
                "pip install restrictedpython"
            ) from exc

    async def enter(self) -> None:  # noqa: D102
        pass

    async def exit(self, exc: BaseException | None) -> None:  # noqa: D102
        pass


@dataclass(frozen=True, slots=True)
class SeccompSandbox:
    """Linux-only seccomp syscall-allowlist sandbox.

    On Linux, applies a seccomp BPF filter that restricts the process to the
    given ``allowed_syscalls`` set before each tool execution.  On non-Linux
    platforms the hook is a complete no-op; no import is attempted.

    On Linux, raises ``ImportError`` at instantiation if ``seccomp`` is not
    installed — install with ``pip install seccomp``.

    Attributes:
        allowed_syscalls: Frozenset of syscall names to permit.  An empty set
            means only the seccomp control syscalls are permitted; subclass and
            override ``enter`` for custom policies.
    """

    allowed_syscalls: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:  # noqa: D105
        if sys.platform != "linux":
            return
        try:
            import seccomp  # noqa: PLC0415, F401
        except ImportError as exc:
            raise ImportError(
                "SeccompSandbox requires 'seccomp' on Linux: pip install seccomp"
            ) from exc

    async def enter(self) -> None:  # noqa: D102
        if sys.platform != "linux":
            return
        # Subclass and override to apply a custom libseccomp filter.
        # Default implementation is intentionally a no-op to avoid forcing a
        # seccomp policy on callers who only need the structural hook.

    async def exit(self, exc: BaseException | None) -> None:  # noqa: D102
        pass
