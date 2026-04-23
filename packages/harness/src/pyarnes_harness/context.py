"""Domain-specific contextual guidance for the agent loop."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["AgentContext"]


@dataclass(frozen=True, slots=True)
class AgentContext:
    """Domain-specific guidance injected into the agent's system message.

    Construct directly or load from a ``.agents.yml`` file via
    :meth:`from_yaml`. All sequence fields are stored as tuples so the
    dataclass stays immutable (frozen).

    Attributes:
        project_name: Human-readable project identifier.
        conventions: Coding or style conventions for the agent to follow.
        architecture_rules: Structural rules (e.g. "no circular imports").
        testing_requirements: Test expectations the agent must satisfy.
        approved_libraries: Third-party packages the agent may use.
        forbidden_patterns: Patterns the agent must avoid.
    """

    project_name: str
    conventions: tuple[str, ...] = ()
    architecture_rules: tuple[str, ...] = ()
    testing_requirements: tuple[str, ...] = ()
    approved_libraries: frozenset[str] = frozenset()
    forbidden_patterns: tuple[str, ...] = ()

    @classmethod
    def from_yaml(cls, path: Path) -> AgentContext:
        """Load context from a ``.agents.yml`` file.

        YAML sequences are coerced to tuples/frozenset to match field types.
        Missing keys are silently defaulted to empty collections.

        Args:
            path: Path to a YAML file with optional keys: ``project_name``,
                ``conventions``, ``architecture_rules``,
                ``testing_requirements``, ``approved_libraries``,
                ``forbidden_patterns``.
        """
        import yaml  # noqa: PLC0415 — pyyaml is an optional dep; lazy import keeps it optional

        raw: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
        return cls(
            project_name=raw.get("project_name", path.stem),
            conventions=tuple(raw.get("conventions", [])),
            architecture_rules=tuple(raw.get("architecture_rules", [])),
            testing_requirements=tuple(raw.get("testing_requirements", [])),
            approved_libraries=frozenset(raw.get("approved_libraries", [])),
            forbidden_patterns=tuple(raw.get("forbidden_patterns", [])),
        )

    def to_system_prompt(self) -> str:
        """Render non-empty sections as a markdown fragment.

        Empty collections produce no output — no bare section headers.
        """
        lines: list[str] = [f"# Project: {self.project_name}"]
        sections: list[tuple[str, Any]] = [
            ("## Conventions", self.conventions),
            ("## Architecture Rules", self.architecture_rules),
            ("## Testing Requirements", self.testing_requirements),
            ("## Approved Libraries", sorted(self.approved_libraries)),
            ("## Forbidden Patterns", self.forbidden_patterns),
        ]
        for header, items in sections:
            if items:
                lines.append(header)
                lines.extend(f"- {item}" for item in items)
        return "\n".join(lines)
