# author: Stephen Eaton
"""A7: the package is independent of the BenchWeave core.

Mirrors the DPS-150 independence tests and adds a walk of the shipped
modules: no module may import a BenchWeave core implementation module.
"""

import ast
import importlib
import importlib.util
import json
from importlib.metadata import requires, version
from importlib.resources import files
from pathlib import Path

from benchweave_rigol_dho924s.descriptor import build_descriptor

PACKAGE_DIR = Path(__file__).resolve().parents[1] / "src" / "benchweave_rigol_dho924s"
CORE = "benchweave"


def test_core_is_not_a_development_or_runtime_dependency() -> None:
    assert importlib.util.find_spec(CORE) is None
    assert not requires("benchweave-rigol-dho924s")
    assert version("benchweave-rigol-dho924s") == "0.1.0"


def imported_roots(source: str) -> list[str]:
    """The top-level package name of every import statement in one module."""
    tree = ast.parse(source)
    roots: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.append(node.module.split(".")[0])
    return roots


def test_no_shipped_module_imports_a_core_implementation_module() -> None:
    modules = sorted(PACKAGE_DIR.glob("*.py"))
    assert len(modules) >= 6
    seen: list[str] = []
    for path in modules:
        for root in imported_roots(path.read_text(encoding="utf-8")):
            seen.append(root)
            assert root != CORE, f"{path.name} imports the BenchWeave core: {root}"
    assert "benchweave_rigol_dho924s" in seen


def test_descriptor_factory_and_packaged_vectors() -> None:
    package = files("benchweave_rigol_dho924s")
    descriptor = json.loads(package.joinpath("descriptor.json").read_text(encoding="utf-8"))
    assert descriptor == build_descriptor()
    module, factory_name = descriptor["integration"]["adapter"]["entry_point"].split(":")
    assert module.startswith("benchweave_rigol_dho924s.")
    factory = getattr(importlib.import_module(module), factory_name)
    assert factory() is not factory()
    for vector in descriptor["provenance"]["test_vectors"]:
        assert package.joinpath(vector["path"]).is_file()
