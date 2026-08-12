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
            if path.name in {
                "analysis.py",
                "build.py",
                "data_plane.py",
                "dataset.py",
                "execution.py",
            }:
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

    def test_dataset_boundary_is_provider_neutral_and_narrow(self) -> None:
        paths = ("domain/dataset.py", "application/dataset.py")
        forbidden = (
            "metatrader",
            "mt5",
            "html",
            "filesystem",
            "subprocess",
            "pathlib",
            "analysis",
            "database",
            "repository",
            "persistence",
        )
        for relative_path in paths:
            source = (PACKAGE_ROOT / relative_path).read_text(encoding="utf-8").lower()
            with self.subTest(path=relative_path):
                self.assertEqual([term for term in forbidden if term in source], [])

        path = PACKAGE_ROOT / "application/dataset.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        transformer = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "DatasetTransformer"
        )
        methods = {
            node.name for node in transformer.body if isinstance(node, ast.FunctionDef)
        }
        self.assertEqual(methods, {"transform"})

    def test_analysis_boundary_is_provider_neutral_and_not_a_framework(self) -> None:
        forbidden = (
            "metatrader",
            "mt5",
            "html",
            "filesystem",
            "subprocess",
            "pathlib",
            "database",
            "repository",
            "persistence",
            "ranking",
            "optimizer",
            "recommendation",
            "chart",
            "equity",
            "exposure",
            "holding duration",
            "periodic return",
            "rolling metric",
            "sharpe",
            "slippage",
            "sortino",
            "volatility",
            "analysisengine",
            "analysisregistry",
        )
        for relative_path in ("domain/analysis.py", "application/analysis.py"):
            source = (PACKAGE_ROOT / relative_path).read_text(encoding="utf-8").lower()
            with self.subTest(path=relative_path):
                self.assertEqual([term for term in forbidden if term in source], [])

    def test_mt5_report_vocabulary_and_filesystem_stay_in_infrastructure(self) -> None:
        adapter = PACKAGE_ROOT / "infrastructure/mt5_report.py"
        imports = {module.split(".", 1)[0] for module, _ in _imports(adapter)}
        self.assertEqual(imports & {"os", "pathlib", "subprocess"}, set())
        labels = (
            "initial deposit:",
            "total net profit:",
            "profit trades (% of total):",
            "loss trades (% of total):",
            "utf-16le",
        )
        for boundary in ("domain", "application"):
            for path in (PACKAGE_ROOT / boundary).glob("*.py"):
                source = path.read_text(encoding="utf-8").lower()
                with self.subTest(path=path.relative_to(ROOT)):
                    self.assertEqual([label for label in labels if label in source], [])

    def test_no_generic_or_future_phase_modules_exist(self) -> None:
        forbidden_stems = {
            "api",
            "analytics_engine",
            "dataset_registry",
            "etl",
            "mcp",
            "metric_registry",
            "optimizer",
            "persistence",
            "process_runner",
            "provider_registry",
            "repository",
            "ranking",
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
                "mt5_report.py",
                "mt5_strategy_tester.py",
                "sqlite_data_plane.py",
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

    def test_data_plane_boundary_is_storage_neutral_and_narrow(self) -> None:
        path = PACKAGE_ROOT / "application/data_plane.py"
        text = path.read_text(encoding="utf-8")
        source = text.lower()
        forbidden = (
            "sqlite",
            "pathlib",
            "select ",
            "insert ",
            "update ",
            "delete ",
            "cursor",
            "connection",
            "database path",
            "content_objects",
            "published_records",
            "document_digest",
            "record_kind",
        )
        self.assertEqual([term for term in forbidden if term in source], [])

        tree = ast.parse(text, filename=str(path))
        port = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "DataPlane"
        )
        methods = {
            node.name for node in port.body if isinstance(node, ast.FunctionDef)
        }
        self.assertEqual(
            methods,
            {
                "publish_build",
                "load_build",
                "publish_run",
                "load_run",
                "publish_dataset",
                "load_dataset",
                "publish_analysis",
                "load_analysis",
            },
        )

        reconstruction = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "reconstruct_canonical_chain"
        )
        data_plane_calls = {
            node.func.attr
            for node in ast.walk(reconstruction)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "data_plane"
        }
        self.assertEqual(
            data_plane_calls,
            {"load_build", "load_run", "load_dataset", "load_analysis"},
        )
        classes = {
            node.name for node in tree.body if isinstance(node, ast.ClassDef)
        }
        self.assertTrue(
            classes.isdisjoint({"ProvenanceService", "LineageEngine"})
        )

    def test_sqlite_is_confined_to_the_data_plane_adapter(self) -> None:
        users = set()
        for path in PACKAGE_ROOT.rglob("*.py"):
            for module, _ in _imports(path):
                if module.split(".", 1)[0] == "sqlite3":
                    users.add(path.relative_to(PACKAGE_ROOT).as_posix())
        self.assertEqual(users, {"infrastructure/sqlite_data_plane.py"})

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
