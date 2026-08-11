"""Enforce the implemented package dependency boundaries."""

from __future__ import annotations

import ast
import re
import sys
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = ROOT / "src" / "ea_research_lab"


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            yield module, node.lineno


class DependencyBoundaryTests(unittest.TestCase):
    def test_domain_imports_only_stdlib_or_domain_modules(self) -> None:
        self._assert_imports(
            PACKAGE_ROOT / "domain",
            internal_prefixes=("ea_research_lab.domain",),
        )

    def test_application_imports_only_stdlib_or_domain_application_modules(self) -> None:
        self._assert_imports(
            PACKAGE_ROOT / "application",
            internal_prefixes=(
                "ea_research_lab.application",
                "ea_research_lab.contracts",
                "ea_research_lab.domain",
            ),
        )

    def test_contracts_import_only_approved_contract_dependencies(self) -> None:
        self._assert_imports(
            PACKAGE_ROOT / "contracts",
            internal_prefixes=(
                "ea_research_lab.contracts",
                "ea_research_lab.domain",
            ),
            external_modules=("jsonschema", "referencing"),
        )

    def test_only_approved_orchestration_uses_contracts_from_application(self) -> None:
        violations = []
        for path in sorted((PACKAGE_ROOT / "application").glob("*.py")):
            if path.name in {"build.py", "execution.py"}:
                continue
            for module, line in _imports(path):
                if module == "ea_research_lab.contracts" or module.startswith(
                    "ea_research_lab.contracts."
                ):
                    violations.append(f"{path.relative_to(ROOT)}:{line}: {module}")
        self.assertEqual(violations, [])

    def test_infrastructure_imports_only_approved_inward_modules(self) -> None:
        self._assert_imports(
            PACKAGE_ROOT / "infrastructure",
            internal_prefixes=(
                "ea_research_lab.application",
                "ea_research_lab.contracts",
                "ea_research_lab.domain",
                "ea_research_lab.infrastructure",
            ),
        )

    def test_only_approved_core_packages_exist(self) -> None:
        packages = {
            path.name
            for path in PACKAGE_ROOT.iterdir()
            if path.is_dir() and path.name != "__pycache__"
        }
        self.assertEqual(
            packages,
            {"application", "contracts", "domain", "infrastructure"},
        )

    def test_build_boundary_excludes_external_and_trading_semantics(self) -> None:
        forbidden = (
            "metaeditor",
            "subprocess",
            "pathlib",
            "windows",
            "filesystem",
            ".ex5",
            "exit_code",
            "log_path",
            "strategy",
            "signal",
            "symbol",
            "timeframe",
            "indicator",
        )
        for relative_path in ("domain/build.py", "application/build.py"):
            source = (PACKAGE_ROOT / relative_path).read_text(encoding="utf-8").lower()
            with self.subTest(path=relative_path):
                self.assertEqual(
                    [term for term in forbidden if term in source],
                    [],
                )

    def test_execution_boundary_excludes_provider_and_trading_semantics(self) -> None:
        forbidden = (
            "metatrader",
            "strategy tester",
            "subprocess",
            "pathlib",
            "windows",
            "filesystem",
            "terminal configuration",
            "exit_code",
            "report_path",
            "log_path",
            "account",
            "symbol",
            "timeframe",
            "signal",
            "indicator",
            "live trading",
        )
        for relative_path in ("domain/execution.py", "application/execution.py"):
            source = (PACKAGE_ROOT / relative_path).read_text(encoding="utf-8").lower()
            with self.subTest(path=relative_path):
                self.assertEqual([term for term in forbidden if term in source], [])

    def test_execution_provider_port_remains_narrow(self) -> None:
        path = PACKAGE_ROOT / "application/execution.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        provider = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "ExecutionProvider"
        )
        methods = {
            node.name for node in provider.body if isinstance(node, ast.FunctionDef)
        }
        self.assertEqual(methods, {"execute"})

    def test_no_generic_or_future_phase_modules_exist(self) -> None:
        forbidden_stems = {
            "analysis",
            "api",
            "mcp",
            "persistence",
            "process_runner",
            "provider_registry",
            "repository",
            "semantic_layer",
            "ui",
            "workflow_engine",
        }
        modules = {
            path.stem
            for path in PACKAGE_ROOT.rglob("*.py")
            if path.name != "__init__.py"
        }
        self.assertEqual(modules & forbidden_stems, set())

    def test_build_workspace_excludes_provider_execution_semantics(self) -> None:
        source = (PACKAGE_ROOT / "infrastructure/build_workspace.py").read_text(
            encoding="utf-8"
        ).lower()
        forbidden = (
            "metaeditor",
            "subprocess",
            ".ex5",
            "exit_code",
            "compiler_log",
            "strategy",
            "signal",
            "symbol",
            "timeframe",
            "indicator",
        )
        self.assertEqual([term for term in forbidden if term in source], [])

    def test_only_approved_adapters_use_contracts_from_infrastructure(self) -> None:
        violations = []
        for path in sorted((PACKAGE_ROOT / "infrastructure").glob("*.py")):
            if path.name in {
                "artifact.py",
                "build_workspace.py",
                "metaeditor.py",
                "mt5_strategy_tester.py",
            }:
                continue
            for module, line in _imports(path):
                if module == "ea_research_lab.contracts" or module.startswith(
                    "ea_research_lab.contracts."
                ):
                    violations.append(f"{path.relative_to(ROOT)}:{line}: {module}")
        self.assertEqual(violations, [])

    def test_metaeditor_semantics_remain_inside_its_adapter(self) -> None:
        adapter = (PACKAGE_ROOT / "infrastructure/metaeditor.py").read_text(
            encoding="utf-8"
        ).lower()
        self.assertNotIn("artifactid", adapter)
        self.assertNotIn("buildoutcome", adapter)
        for boundary in ("domain", "application"):
            for path in (PACKAGE_ROOT / boundary).glob("*.py"):
                source = path.read_text(encoding="utf-8").lower()
                with self.subTest(path=path.relative_to(ROOT)):
                    self.assertNotIn("metaeditor", source)
                    self.assertNotIn("utf-16", source)
                    self.assertNotIn("exit_code", source)

    def test_external_process_and_filesystem_ownership_stays_at_adapters(self) -> None:
        forbidden_core_imports = {"os", "pathlib", "shutil", "subprocess", "tempfile"}
        violations = []
        for boundary in ("domain", "application"):
            for path in sorted((PACKAGE_ROOT / boundary).glob("*.py")):
                for module, line in _imports(path):
                    if module.split(".", 1)[0] in forbidden_core_imports:
                        violations.append(f"{path.relative_to(ROOT)}:{line}: {module}")
        for path in sorted((PACKAGE_ROOT / "infrastructure").glob("*.py")):
            if path.name in {"metaeditor.py", "mt5_strategy_tester.py"}:
                continue
            for module, line in _imports(path):
                if module.split(".", 1)[0] == "subprocess":
                    violations.append(f"{path.relative_to(ROOT)}:{line}: {module}")
        self.assertEqual(violations, [])

    def test_mt5_semantics_remain_inside_its_adapter_and_contracts(self) -> None:
        adapter = (PACKAGE_ROOT / "infrastructure/mt5_strategy_tester.py").read_text(
            encoding="utf-8"
        ).lower()
        self.assertNotIn("raw_evidence", adapter)
        self.assertNotIn("run_manifest", adapter)
        for boundary in ("domain", "application"):
            for path in (PACKAGE_ROOT / boundary).glob("*.py"):
                source = path.read_text(encoding="utf-8").lower()
                with self.subTest(path=path.relative_to(ROOT)):
                    self.assertNotIn("metatrader5-strategy-tester", source)
                    self.assertNotIn("terminal64", source)
                    self.assertNotIn("strategy tester", source)

    def test_artifact_adapter_does_not_finalize_build_or_persist(self) -> None:
        source = (PACKAGE_ROOT / "infrastructure/artifact.py").read_text(
            encoding="utf-8"
        ).lower()
        forbidden = (
            "buildoutcome",
            "build-record:0.2.0",
            "artifact repository",
            "database",
            "persistence",
        )
        self.assertEqual([term for term in forbidden if term in source], [])

    def test_build_workflow_does_not_introduce_future_capabilities(self) -> None:
        source = (PACKAGE_ROOT / "application/build.py").read_text(
            encoding="utf-8"
        ).lower()
        forbidden = (
            "executionprovider",
            "strategy tester",
            "artifact registry",
            "database",
            "platform api",
            "mcp",
            "workflow engine",
            "provider registry",
        )
        self.assertEqual([term for term in forbidden if term in source], [])

    def test_execution_workflow_does_not_introduce_future_capabilities(self) -> None:
        source = (PACKAGE_ROOT / "application/execution.py").read_text(
            encoding="utf-8"
        ).lower()
        forbidden = (
            "database",
            "repository",
            "persistence",
            "analysis plane",
            "platform api",
            "semantic layer",
            "mcp",
            "workflow engine",
        )
        self.assertEqual([term for term in forbidden if term in source], [])

    def test_dependencies_are_approved_and_locked(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(
            project["project"]["dependencies"],
            ["jsonschema[format]>=4.26,<5"],
        )

        direct = self._requirement_lines(ROOT / "requirements.in")
        self.assertEqual(
            set(direct),
            {"setuptools==84.0.0", "jsonschema[format]==4.26.0"},
        )

        locked = self._requirement_lines(ROOT / "requirements.lock")
        exact_requirement = re.compile(
            r"[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?==\S+"
        )
        for requirement in locked:
            with self.subTest(requirement=requirement):
                self.assertRegex(requirement, rf"^{exact_requirement.pattern}$")
        self.assertIn("setuptools==84.0.0", locked)
        self.assertIn("jsonschema[format]==4.26.0", locked)

    def _assert_imports(
        self,
        package: Path,
        *,
        internal_prefixes: tuple[str, ...],
        external_modules: tuple[str, ...] = (),
    ) -> None:
        violations = []
        for path in sorted(package.glob("*.py")):
            for module, line in _imports(path):
                top_level = module.split(".", 1)[0]
                is_internal = any(
                    module == prefix or module.startswith(f"{prefix}.")
                    for prefix in internal_prefixes
                )
                if (
                    not is_internal
                    and top_level not in sys.stdlib_module_names
                    and top_level not in external_modules
                ):
                    violations.append(f"{path.relative_to(ROOT)}:{line}: {module}")
        self.assertEqual(violations, [], "Forbidden imports:\n" + "\n".join(violations))

    @staticmethod
    def _requirement_lines(path: Path) -> list[str]:
        return [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]


if __name__ == "__main__":
    unittest.main()
