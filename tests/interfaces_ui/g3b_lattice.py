"""Shared helpers for the G3b runs suites (issue #304, design record §6's
in-test lattice rule): temp fixture dirs through the bootstrap admission
path — no ``fixtures/`` motion, no digest-lattice obligation.

The variant lattice copies the committed sim execution lattice and
re-pins ONE mutated procedure document (mode / the enable step's
``enabled`` value), then re-derives the three digests the mutation
moves — the procedure pin in the binding and the commissioning, and the
commissioning pin in the binding — exactly the digest-lattice walk the
activation harness (tests/integration/test_run_activation.py::_lattice)
performs. Everything else stays the committed bytes.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from ui_gateway_support import FIXTURES


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def author_g3b_lattice(
    root: Path,
    *,
    mode: str = "manual",
    enabled: Any = True,
    request_id: str = "req-g3b-energise",
    name: str = "lattice",
) -> tuple[Path, str]:
    """Author one G3b variant lattice; return ``(dir, binding_sha256)``.

    ``mode`` is the procedure's execution mode (manual keeps the
    seam's lease rule live; gateway_owned rides the commissioned
    unattended grant the sim commissioning already carries). ``enabled``
    is the enable step's ``input.enabled`` value: ``True`` is the
    energy-sourcing class, ``False`` the explicit de-energising class,
    ``"absent"`` strips the field (the no-enable-step shape). The
    binding's own ``request_id`` is the staging cycle's §9 id — the seam
    requires ``run_start``'s request id to equal it.
    """
    dest = root / name
    dest.mkdir(parents=True, exist_ok=True)
    for item in sorted(FIXTURES.iterdir()):
        if item.is_file():
            shutil.copy2(item, dest / item.name)

    procedure_path = dest / "procedure-voltage-check.json"
    procedure = json.loads(procedure_path.read_text())
    procedure["mode"] = mode
    for step in procedure.get("steps", []):
        if step.get("id") == "enable":
            if enabled == "absent":
                step["input"].pop("enabled", None)
            else:
                step["input"]["enabled"] = enabled
    procedure_path.write_text(json.dumps(procedure, indent=2) + "\n")
    procedure_sha = _sha(procedure_path)

    commissioning_path = dest / "commissioning.json"
    commissioning = json.loads(commissioning_path.read_text())
    for reference in commissioning.get("procedure_refs", []):
        reference["sha256"] = procedure_sha
    commissioning_path.write_text(json.dumps(commissioning, indent=2) + "\n")
    commissioning_sha = _sha(commissioning_path)

    binding_path = dest / "run-binding.json"
    binding = json.loads(binding_path.read_text())
    binding["request_id"] = request_id
    binding["procedure"]["sha256"] = procedure_sha
    binding["commissioning"]["sha256"] = commissioning_sha
    binding_path.write_text(json.dumps(binding, indent=2) + "\n")
    return dest, _sha(binding_path)
