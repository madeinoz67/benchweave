"""Cross-suite fixture reuse for the integration layer.

The seam-level integration suites (e.g. ``test_seam_prechecks``) drive the
in-process Operations seam on the unit layer's established bootstrap
(``seam_control`` from tests/unit/test_seam_control.py) rather than
duplicating it. That file is not a package sibling, so its directory joins
sys.path here — conftest modules import before test modules, and the shared
sys.modules entry keeps one module instance with pytest's own collection.
"""

from __future__ import annotations

import sys
from pathlib import Path

_UNIT_DIR = Path(__file__).resolve().parents[1] / "unit"
if str(_UNIT_DIR) not in sys.path:
    sys.path.insert(0, str(_UNIT_DIR))

from test_seam_control import seam_control  # noqa: E402, F401  (fixture re-export)
