"""Ship the vendored contracts tree in wheels, minus dev-stage directories.

The devstage design record's F1 call (ratified 2026-09-23, §13.3): wheels
never carry dev bytes. hatchling's exclude patterns provably do not filter
force-included trees — that is what "force" means — and a build hook cannot
delete a config-declared force-include row (hooks contribute through
``build_data``, which ``get_force_include`` merges OVER the config map, key
by key; a pop from build_data touches nothing the config declared). So the
``standards`` mapping lives here, not in pyproject: this hook contributes
one force-include row per unit under ``standards/`` onto exactly the target
path the old whole-tree mapping produced, skipping every directory whose
name ends with ``-dev`` — no row, nothing shipped.

The dev rule is lexical on purpose. Packaging must not depend on manifest
state (a stray ``-dev`` directory governance has not admitted yet ships in
no wheel either); the manifest's dev-head rules (load_manifest) stay the
stricter authority on the governance side. Gated on the wheel target only —
the sdist declares no contracts mapping and carries the repository source
tree by its own rules. A missing hook module fails the build loudly, and
``tests/integration/test_wheel_dev_exclusion.py`` pins both halves: no
``-dev`` entries, and the active contracts carriage preserved.
"""

from __future__ import annotations

import os

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

STANDARDS_SOURCE = "standards"
CONTRACTS_TARGET = "benchweave/_vendored/contracts"
DEV_SUFFIX = "-dev"


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        if self.target_name != "wheel":
            return
        build_data.setdefault("force_include", {}).update(
            _contracts_rows(os.fspath(self.root))
        )


def _contracts_rows(root: str) -> dict[str, str]:
    """Map every unit under standards/ to its contracts target, dev skipped.

    Top-level files (the manifests, GOVERNANCE.md) map one-for-one; each
    standard id directory maps per child, so a ``<target>-dev`` child
    simply has no row. A missing standards/ directory fails the build
    loudly — this repository always carries one.
    """
    standards = os.path.join(root, STANDARDS_SOURCE)
    rows: dict[str, str] = {}
    for name in sorted(os.listdir(standards)):
        source = f"{STANDARDS_SOURCE}/{name}"
        target = f"{CONTRACTS_TARGET}/{name}"
        identifier_dir = os.path.join(standards, name)
        if not os.path.isdir(identifier_dir):
            rows[source] = target
            continue
        for child in sorted(os.listdir(identifier_dir)):
            if child.endswith(DEV_SUFFIX):
                continue
            rows[f"{source}/{child}"] = f"{target}/{child}"
    return rows
