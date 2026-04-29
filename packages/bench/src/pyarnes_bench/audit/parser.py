"""Python-only tree-sitter parser.

Single language, single grammar, single recursive walker. Pattern lifted from
``tirth8205/code-review-graph/parser.py`` but trimmed of its 35+ language
branches — we extract only the four constructs the audit cares about
(``class_definition``, ``function_definition``, the two ``import`` forms, and
``call``) and emit a fixed set of edge kinds.

Why tree-sitter rather than ``ast``? The plan reserves room for adding more
languages in the future (Phase 2). Keeping the parser shape generic lets us
swap in another grammar without rewriting the audits.
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter_python as tsp
from tree_sitter import Language, Parser
from tree_sitter import Node as TSNode

from pyarnes_bench.audit.schema import Edge, EdgeKind, Node, NodeKind, make_node_id

__all__ = ["PythonParser"]


_PY_LANGUAGE = Language(tsp.language())


class PythonParser:
    """Parse a Python file and emit nodes + edges for the audit graph."""

    def __init__(self) -> None:
        """Build a fresh parser bound to the embedded Python grammar."""
        self._parser = Parser(_PY_LANGUAGE)

    # ── Public API ────────────────────────────────────────────────────────

    def parse_file(self, path: Path, *, project_root: Path) -> tuple[list[Node], list[Edge]]:
        """Parse *path* and return its nodes and edges.

        ``project_root`` is used to compute the relative file path baked into
        every node id, so two builds of the same project produce identical ids.
        """
        source = path.read_bytes()
        return self.parse_bytes(path, source, project_root=project_root)

    def parse_bytes(
        self,
        path: Path,
        source: bytes,
        *,
        project_root: Path,
    ) -> tuple[list[Node], list[Edge]]:
        """Parse pre-loaded *source* bytes for *path*."""
        rel = self._relative_path(path, project_root)
        tree = self._parser.parse(source)
        root = tree.root_node

        nodes: list[Node] = []
        edges: list[Edge] = []

        # Module + file nodes — every file contributes both so unused-file
        # detection can compare imports against MODULE nodes specifically.
        module_qualname = self._module_qualname(rel)
        module_id = make_node_id(rel, module_qualname)
        nodes.append(
            Node(
                id=module_id,
                kind=NodeKind.MODULE,
                name=module_qualname,
                file_path=rel,
                line_start=1,
                line_end=root.end_point[0] + 1,
                qualname=module_qualname,
            )
        )

        self._walk(root, source, rel, module_id, [], nodes, edges)
        return nodes, edges

    # ── Internals ─────────────────────────────────────────────────────────

    def _relative_path(self, path: Path, project_root: Path) -> str:
        try:
            return str(path.resolve().relative_to(project_root.resolve()))
        except ValueError:
            return str(path)

    def _module_qualname(self, rel_path: str) -> str:
        # `pkg/sub/mod.py` → `pkg.sub.mod`. Treat `__init__.py` as the package
        # itself, matching how Python resolves imports. For src-layout
        # workspaces (`packages/<name>/src/<module>.py`), strip the
        # `<name>/src/` prefix so the qualname matches what callers actually
        # `import` from.
        without_ext = rel_path.removesuffix(".py")
        without_ext = without_ext.removesuffix("/__init__")
        parts = without_ext.split("/")
        if "src" in parts:
            # Keep only the parts after the last `src` segment.
            parts = parts[parts.index("src") + 1 :]
        return ".".join(parts)

    def _walk(  # noqa: PLR0913
        self,
        ts_node: TSNode,
        source: bytes,
        file_path: str,
        parent_id: str,
        parent_qual: list[str],
        nodes: list[Node],
        edges: list[Edge],
    ) -> None:
        for child in ts_node.children:
            kind = child.type
            if kind == "class_definition":
                self._handle_class(child, source, file_path, parent_id, parent_qual, nodes, edges)
            elif kind == "function_definition":
                self._handle_function(child, source, file_path, parent_id, parent_qual, nodes, edges)
            elif kind == "import_statement":
                self._handle_import(child, source, file_path, parent_id, edges)
            elif kind == "import_from_statement":
                self._handle_import_from(child, source, file_path, parent_id, edges)
            else:
                # Drill into anything else — calls etc. live deeper in the AST.
                self._walk(child, source, file_path, parent_id, parent_qual, nodes, edges)

    def _handle_class(  # noqa: PLR0913
        self,
        ts_node: TSNode,
        source: bytes,
        file_path: str,
        parent_id: str,
        parent_qual: list[str],
        nodes: list[Node],
        edges: list[Edge],
    ) -> None:
        name = self._field_text(ts_node, "name", source) or "<anonymous>"
        qual = ".".join([*parent_qual, name])
        node_id = make_node_id(file_path, qual)
        nodes.append(
            Node(
                id=node_id,
                kind=NodeKind.CLASS,
                name=name,
                file_path=file_path,
                line_start=ts_node.start_point[0] + 1,
                line_end=ts_node.end_point[0] + 1,
                qualname=qual,
            )
        )
        edges.append(
            Edge(
                src=parent_id,
                dst=node_id,
                kind=EdgeKind.CONTAINS,
                file_path=file_path,
                line=ts_node.start_point[0] + 1,
            )
        )
        # Inheritance — class C(Base): the superclass list lives in the
        # `superclasses` field as an `argument_list` node.
        for base in self._iter_argument_identifiers(ts_node.child_by_field_name("superclasses"), source):
            edges.append(  # noqa: PERF401  # building Edges with positional fields; comprehension would obscure shape
                Edge(
                    src=node_id,
                    dst=base,  # unresolved until link pass; left as a name
                    kind=EdgeKind.INHERITS,
                    file_path=file_path,
                    line=ts_node.start_point[0] + 1,
                    extra={"unresolved": True},
                )
            )
        body = ts_node.child_by_field_name("body")
        if body is not None:
            self._walk(body, source, file_path, node_id, [*parent_qual, name], nodes, edges)

    def _handle_function(  # noqa: PLR0913
        self,
        ts_node: TSNode,
        source: bytes,
        file_path: str,
        parent_id: str,
        parent_qual: list[str],
        nodes: list[Node],
        edges: list[Edge],
    ) -> None:
        name = self._field_text(ts_node, "name", source) or "<anonymous>"
        qual = ".".join([*parent_qual, name])
        node_id = make_node_id(file_path, qual)
        kind = NodeKind.METHOD if parent_qual else NodeKind.FUNCTION
        body_text = source[ts_node.start_byte : ts_node.end_byte].decode("utf-8", errors="replace")
        nodes.append(
            Node(
                id=node_id,
                kind=kind,
                name=name,
                file_path=file_path,
                line_start=ts_node.start_point[0] + 1,
                line_end=ts_node.end_point[0] + 1,
                qualname=qual,
                extra={"body": body_text},
            )
        )
        edges.append(
            Edge(
                src=parent_id,
                dst=node_id,
                kind=EdgeKind.CONTAINS,
                file_path=file_path,
                line=ts_node.start_point[0] + 1,
            )
        )
        body = ts_node.child_by_field_name("body")
        if body is not None:
            # Collect calls in the body (descend further so nested defs and
            # calls inside conditionals are picked up).
            self._collect_calls(body, source, file_path, node_id, edges)
            # Recurse so nested functions / classes get their own nodes too.
            self._walk(body, source, file_path, node_id, [*parent_qual, name], nodes, edges)

    def _collect_calls(
        self,
        ts_node: TSNode,
        source: bytes,
        file_path: str,
        caller_id: str,
        edges: list[Edge],
    ) -> None:
        if ts_node.type == "call":
            target = self._call_target(ts_node, source)
            if target:
                edges.append(
                    Edge(
                        src=caller_id,
                        dst=target,
                        kind=EdgeKind.CALLS,
                        file_path=file_path,
                        line=ts_node.start_point[0] + 1,
                        extra={"unresolved": True},
                    )
                )
        for child in ts_node.children:
            self._collect_calls(child, source, file_path, caller_id, edges)

    def _handle_import(
        self,
        ts_node: TSNode,
        source: bytes,
        file_path: str,
        parent_id: str,
        edges: list[Edge],
    ) -> None:
        for name_node in ts_node.children:
            if name_node.type in {"dotted_name", "aliased_import"}:
                module = self._dotted_name_text(name_node, source)
                if module:
                    edges.append(
                        Edge(
                            src=parent_id,
                            dst=module,
                            kind=EdgeKind.IMPORTS,
                            file_path=file_path,
                            line=ts_node.start_point[0] + 1,
                            extra={"unresolved": True},
                        )
                    )

    def _handle_import_from(
        self,
        ts_node: TSNode,
        source: bytes,
        file_path: str,
        parent_id: str,
        edges: list[Edge],
    ) -> None:
        module_node = ts_node.child_by_field_name("module_name")
        module = self._dotted_name_text(module_node, source) if module_node else None
        if not module:
            return
        # `child_by_field_name` returns a fresh wrapper each call, so compare
        # by byte range instead of identity to filter the module-name node out
        # of the imported-symbols loop.
        module_range = (module_node.start_byte, module_node.end_byte) if module_node else None
        for child in ts_node.children:
            if child.type not in {"dotted_name", "aliased_import"}:
                continue
            if module_range is not None and (child.start_byte, child.end_byte) == module_range:
                continue
            name = self._dotted_name_text(child, source)
            if name:
                edges.append(
                    Edge(
                        src=parent_id,
                        dst=f"{module}.{name}",
                        kind=EdgeKind.IMPORTS_FROM,
                        file_path=file_path,
                        line=ts_node.start_point[0] + 1,
                        extra={"unresolved": True, "module": module, "name": name},
                    )
                )

    # ── Tiny tree-sitter helpers ──────────────────────────────────────────

    def _field_text(self, ts_node: TSNode, field: str, source: bytes) -> str | None:
        node = ts_node.child_by_field_name(field)
        if node is None:
            return None
        return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    def _dotted_name_text(self, ts_node: TSNode | None, source: bytes) -> str | None:
        if ts_node is None:
            return None
        text = source[ts_node.start_byte : ts_node.end_byte].decode("utf-8", errors="replace")
        return text.strip().split(" as ", 1)[0].strip()

    def _iter_argument_identifiers(self, ts_node: TSNode | None, source: bytes) -> list[str]:
        if ts_node is None:
            return []
        out: list[str] = []
        for child in ts_node.children:
            if child.type in {"identifier", "attribute"}:
                out.append(  # noqa: PERF401  # decode-and-collect; a comprehension would obscure the slice
                    source[child.start_byte : child.end_byte].decode("utf-8", errors="replace")
                )
        return out

    def _call_target(self, ts_node: TSNode, source: bytes) -> str | None:
        function = ts_node.child_by_field_name("function")
        if function is None:
            return None
        text = source[function.start_byte : function.end_byte].decode("utf-8", errors="replace")
        return text.strip() or None
