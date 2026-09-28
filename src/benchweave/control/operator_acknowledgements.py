"""The operator acknowledgement carrier (issue #219, design deferral D11).

The authored half of the per-device operator acknowledgement (VR-18): an
operator-owned, optional ``operator-acknowledgements.json`` in the fixtures
directory (the administrator-configuration locus the transport-settings
precedent established), carrying exactly the ``operator_acknowledgements``
argument admission takes — a mapping of device id to the exact OTDP pin the
acknowledgement covers. It binds the pin it names and only that pin
(admission's ``_authorise_pin`` enforces the equality); one file cannot
blanket a bench, and nothing here can express an endpoint, credential or
path — by schema, not by policy (``additionalProperties: false`` at the top
level; every value is a canonical-semver pin).

Nothing in the execution lattice pins this file. Its authority is the
operator's file act; the PERSISTED record is the admission record's
(``admit_startup_bench`` stamps each loaded acknowledgement onto the
device's store row). Refusals carry the typed ``acknowledgements_schema:``
prefix and the file decodes through the exact-byte decoder (duplicate keys,
non-finite numbers, size, strict UTF-8) like every other admission-adjacent
document.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from benchweave.content.json_document import DocumentRejected, load_document

#: The one filename the bootstrap seam looks for (optional).
ACKNOWLEDGEMENTS_FILENAME = "operator-acknowledgements.json"

#: The admission byte cap shared with every other admission document.
_MAX_ACK_BYTES = 1_048_576

#: The carrier's shape (gateway source, not corpus — operator state, the
#: transport-settings posture). Device ids carry the interface's id
#: grammar; pins are canonical semver (an acknowledgement names a released
#: version — a dev-label pin classifies conforming and never needs one).
ACKNOWLEDGEMENTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "acknowledgements": {
            "type": "object",
            "propertyNames": {"pattern": "^[a-z][a-z0-9_.-]*$"},
            "additionalProperties": {
                "type": "string",
                "pattern": r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$",
            },
        },
    },
    "required": ["acknowledgements"],
    "additionalProperties": False,
}


class AcknowledgementsRejected(ValueError):
    """The acknowledgement file failed validation or decode."""


def load_operator_acknowledgements(path: Path) -> dict[str, str]:
    """Exact-byte decode, validate, and flatten the file to its mapping.

    Returns ``{device_id: acked_pin}`` — the exact shape admission's
    ``operator_acknowledgements`` parameter takes, so the bootstrap seam
    threads the file verbatim with no translation layer to drift.
    """
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        document = load_document(raw, digest, max_bytes=_MAX_ACK_BYTES)
    except DocumentRejected as exc:
        raise AcknowledgementsRejected(
            f"acknowledgements_schema: {path.name} ({exc})"
        ) from exc
    error = next(
        iter(
            Draft202012Validator(
                ACKNOWLEDGEMENTS_SCHEMA, format_checker=FormatChecker()
            ).iter_errors(document.content)
        ),
        None,
    )
    if error is not None:
        raise AcknowledgementsRejected(
            f"acknowledgements_schema: {path.name} {error.json_path}: {error.message}"
        )
    return {
        str(key): str(value)
        for key, value in document.content["acknowledgements"].items()
    }
