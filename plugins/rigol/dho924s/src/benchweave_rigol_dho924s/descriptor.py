# author: Stephen Eaton
"""The packaged descriptor is the one declaration of the integration contract.

``build_descriptor`` returns an independent copy of ``descriptor.json``. The
descriptor is not restated in Python: one declaration means the file the host
validates and admits is the same document the adapter compares at open.
"""

import json
from importlib.resources import files
from typing import Any, Final

_PACKAGE: Final = "benchweave_rigol_dho924s"
_DESCRIPTOR: Final = "descriptor.json"

DESCRIPTOR_ID: Final = "org.benchweave.rigol-dho924s"
MANUFACTURER: Final = "RIGOL"
MODEL: Final = "DHO924S"
CONNECTION_KEY: Final = "dho924s"


def build_descriptor() -> dict[str, Any]:
    """Return an independent copy of the packaged descriptor."""
    document = files(_PACKAGE).joinpath(_DESCRIPTOR).read_text(encoding="utf-8")
    loaded = json.loads(document)
    if not isinstance(loaded, dict):
        raise ValueError("The packaged descriptor must be a JSON object")
    return loaded
