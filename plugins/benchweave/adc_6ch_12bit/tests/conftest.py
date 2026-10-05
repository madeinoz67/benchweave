# author: Stephen Eaton
"""Path bootstrap for the standalone device project's tests.

The project is standalone (no pyproject; the CI job copies the directory
and runs pytest from the copy): the tests import the in-project
``adc_wire`` package and the emulator from their source locations.
"""

import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for _path in (_PLUGIN_ROOT / "src", _PLUGIN_ROOT / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
