"""Tests for packaging.version — E19 prep."""

from __future__ import annotations

from pyarnes_core.packaging import version_of


class TestVersionOf:
    """version_of reads from installed metadata with a safe fallback."""

    def test_returns_installed_pyarnes_core_version(self) -> None:
        result = version_of("pyarnes-core")
        # In this repo the package is installed editable, so some version
        # string is present — verify it's non-empty and looks PEP-440-ish.
        assert isinstance(result, str)
        assert result
        assert result != "0+unknown"

    def test_unknown_distribution_returns_fallback(self) -> None:
        assert version_of("nonexistent-package-xyz-123") == "0+unknown"
