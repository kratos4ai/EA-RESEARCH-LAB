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

    def test_only_build_workspace_uses_contracts_from_infrastructure(self) -> None:
        violations = []
        for path in sorted((PACKAGE_ROOT / "infrastructure").glob("*.py")):
            if path.name == "build_workspace.py":
                continue
            for module, line in _imports(path):
                if module == "ea_research_lab.contracts" or module.startswith(
                    "ea_research_lab.contracts."
                ):
                    violations.append(f"{path.relative_to(ROOT)}:{line}: {module}")
        self.assertEqual(violations, [])

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
