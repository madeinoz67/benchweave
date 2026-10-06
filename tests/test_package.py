from __future__ import annotations

import ast
import re
import sys
from importlib.metadata import distribution, entry_points
from pathlib import Path

from pytest import CaptureFixture

from benchweave import __version__
from benchweave.__main__ import main

DIST_NAME = "benchweave-adc"


def test_version_is_available() -> None:
    assert __version__


def test_cli_entrypoint_prints_version(capsys: CaptureFixture[str]) -> None:
    assert main() == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("benchweave-adc ")


def _runtime_requirements(dist_name: str) -> set[str]:
    """Distribution names this package installs unconditionally."""
    names: set[str] = set()
    for requirement in distribution(dist_name).requires or []:
        if "; extra" in requirement:
            continue  # optional extras are not runtime
        base = requirement.split(";")[0]
        name = re.split(r"[<>=!~\[ ]", base, maxsplit=1)[0].strip().lower()
        names.add(name.replace("-", "_"))
    return names


def _module_imports(module_path: Path) -> set[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_console_script_imports_are_runtime_dependencies() -> None:
    """Every console-script target module must import only stdlib, this
    package, or packages listed as RUNTIME dependencies — not something
    the dev group happens to provide (F1's class: a clean-venv wheel
    install must not die ModuleNotFoundError on a shipped entry point)."""
    runtime = _runtime_requirements(DIST_NAME)
    package_file = sys.modules["benchweave"].__file__
    assert package_file is not None
    dist_root = Path(package_file).resolve().parent.parent
    offenders: list[str] = []
    for entry in entry_points(group="console_scripts"):
        if entry.dist is None or entry.dist.name != DIST_NAME:
            continue
        module_name = entry.value.split(":", 1)[0]
        module_path = dist_root.joinpath(*module_name.split(".")).with_suffix(".py")
        for root in sorted(_module_imports(module_path)):
            if root in sys.stdlib_module_names or root == "benchweave":
                continue
            if root.replace("-", "_") not in runtime:
                offenders.append(f"{entry.name} ({module_name}) imports {root!r}")
    assert not offenders, "entry-point imports missing from runtime deps:\n" + "\n".join(offenders)
