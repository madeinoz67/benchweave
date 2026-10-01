"""Package-boundary unit tests (UR-11): the runtime import graph never
reaches the harness, and the runtime dependency set stays Jinja2/MarkupSafe."""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

PACKAGE_SRC = Path(__file__).resolve().parents[2] / "packages" / "ui-html" / "src"
PACKAGE_NAME = "benchweave_ui_html"
HARNESS_SUBPACKAGE = "contract_harness"


def _imports_harness(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Import):
            for alias in child.names:
                if alias.name.startswith(f"{PACKAGE_NAME}.{HARNESS_SUBPACKAGE}"):
                    return True
        elif isinstance(child, ast.ImportFrom):
            if child.module is None:
                continue
            if child.module == PACKAGE_NAME and any(
                alias.name == HARNESS_SUBPACKAGE for alias in child.names
            ):
                return True
            if child.module.startswith(f"{PACKAGE_NAME}.{HARNESS_SUBPACKAGE}"):
                return True
    return False


def test_nothing_outside_contract_harness_imports_it() -> None:
    """Walk the package source: only files under contract_harness/ may import
    the harness (design record §4)."""
    offenders: list[str] = []
    for path in sorted((PACKAGE_SRC / PACKAGE_NAME).rglob("*.py")):
        relative = path.relative_to(PACKAGE_SRC / PACKAGE_NAME)
        if len(relative.parts) > 1 and relative.parts[0] == HARNESS_SUBPACKAGE:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if _imports_harness(tree):
            offenders.append(str(relative))
    assert offenders == []


def test_runtime_dependency_set_is_jinja2_and_markupsafe_only() -> None:
    pyproject = tomllib.loads(
        (PACKAGE_SRC.parent / "pyproject.toml").read_text(encoding="utf-8")
    )
    dependencies = set(pyproject["project"]["dependencies"])
    assert dependencies == {"jinja2>=3.1", "markupsafe>=3.0"}
    # pytest must not be a runtime dependency (test-only, the test group).
    assert not any(dep.startswith("pytest") for dep in dependencies)
