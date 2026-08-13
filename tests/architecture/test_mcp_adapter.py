"""Enforce the Phase 09 MCP adapter boundary."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "src" / "ea_research_lab"
ADAPTER = ROOT / "apps" / "mcp_adapter"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
    return imports


class McpAdapterArchitectureTests(unittest.TestCase):
    def test_adapter_is_outside_core_and_core_has_no_mcp_imports(self) -> None:
        self.assertTrue(ADAPTER.is_dir())
        self.assertFalse((CORE / "mcp").exists())
        violations = []
        for path in CORE.rglob("*.py"):
            if any(module == "mcp" or module.startswith("mcp.") for module in _imports(path)):
                violations.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(violations, [])

    def test_runtime_adapter_depends_on_platform_api_not_lower_boundaries(self) -> None:
        server_imports = _imports(ADAPTER / "server.py")
        self.assertIn("ea_research_lab.application.platform_api", server_imports)
        forbidden_fragments = (
            "data_plane",
            "research_query_port",
            "platform_queries",
            "sqlite",
            "metaeditor",
            "mt5",
            "infrastructure",
        )
        self.assertEqual(
            [
                module
                for module in server_imports
                if any(fragment in module.lower() for fragment in forbidden_fragments)
            ],
            [],
        )
        entrypoint_infrastructure = {
            module
            for module in _imports(ADAPTER / "__main__.py")
            if module.startswith("ea_research_lab.infrastructure")
        }
        self.assertEqual(
            entrypoint_infrastructure,
            {
                "ea_research_lab.infrastructure.composition",
                "ea_research_lab.infrastructure.config",
                "ea_research_lab.infrastructure.logging",
            },
        )

    def test_adapter_has_exact_tools_and_no_forbidden_capabilities(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8").lower()
            for path in ADAPTER.glob("*.py")
        )
        server_tree = ast.parse((ADAPTER / "server.py").read_text(encoding="utf-8"))
        tool_decorators = [
            node
            for node in ast.walk(server_tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "tool"
                for decorator in node.decorator_list
            )
        ]
        self.assertEqual(
            [node.name for node in tool_decorators],
            [
                "list_research_runs",
                "get_research_run",
                "list_run_evidence_objects",
                "list_run_datasets",
                "get_dataset",
                "list_dataset_analyses",
                "get_analysis",
                "get_canonical_chain",
                "build_artifact",
                "execute_run",
                "transform_evidence",
                "analyze_datasets",
            ],
        )
        for forbidden in (
            ".resource(",
            ".prompt(",
            "sampling",
            "read_file",
            "write_file",
            "list_directory",
            "execute_command",
            "subprocess",
            "sqlite3",
            "dataclasses.asdict",
            "vars(",
            "__dict__",
            "default=str",
            "print(",
            "sys.stdout",
        ):
            with self.subTest(term=forbidden):
                self.assertNotIn(forbidden, source)
        serialization = (ADAPTER / "serialization.py").read_text(encoding="utf-8")
        self.assertNotIn("SerializerRegistry", serialization)
        self.assertNotIn('"payload"', serialization)
        self.assertNotIn('"content"', serialization)


if __name__ == "__main__":
    unittest.main()
