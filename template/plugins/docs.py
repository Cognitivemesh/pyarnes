"""Docstring generation and mkdocs site builds."""

from __future__ import annotations

from pyarnes_tasks.plugin_base import ShellPlugin


class Docs(ShellPlugin):
    """``uv run tasks docs`` — doq writes docstrings into sources."""

    name = "docs"
    description = "doq writes docstrings into sources"
    cmd = ("uv", "run", "doq", "-w", "-r")
    targets = ("sources",)


class DocsServe(ShellPlugin):
    """``uv run tasks docs:serve`` — mkdocs live-reload server."""

    name = "docs:serve"
    description = "mkdocs live-reload server"
    cmd = ("uv", "run", "mkdocs", "serve")


class DocsBuild(ShellPlugin):
    """``uv run tasks docs:build`` — mkdocs static-site build."""

    name = "docs:build"
    description = "mkdocs static-site build"
    cmd = ("uv", "run", "mkdocs", "build")
