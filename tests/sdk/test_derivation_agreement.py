"""Two-implementation agreement over the vendored derivation census (S19).

The SDK's authoring lane re-implements the derived-variable grammar/static
subset offline (``benchweave_sdk.validation.validate_descriptor``, check
S19) because the SDK is self-contained and cannot import the gateway
module. This suite pins both implementations to the same vendored census
(``standards/otdp/0.1.2/examples/derivation-vectors.json``, byte-identical
in the SDK's vendored tree by the CON-4 lock): every grammar and static row
must produce the same accept/reject decision — and the same
``derivation_*:`` reason prefix — from
``benchweave.measurement.derivation.check_derived_variables`` and from the
SDK's ``validate_descriptor``. Evaluation rows are gateway-only (the SDK
does not evaluate); they are pinned in ``tests/unit/test_derivation.py``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from benchweave.measurement.derivation import (
    DerivationRejected,
    check_derived_variables,
)

ROOT = Path(__file__).resolve().parents[2]
VECTORS = ROOT / "standards" / "otdp" / "0.1.2" / "examples" / "derivation-vectors.json"
CLASS_EXAMPLE = ROOT / "standards" / "otdp" / "0.1.2" / "examples" / "class-dc_psu.json"
SDK_SRC = ROOT / "packages" / "sdk" / "src"

if not SDK_SRC.is_dir():
    # CI checks out submodules recursively; an absent submodule there is an
    # environment defect, not a skip (same posture as test_adapter_agreement).
    if os.environ.get("CI"):
        pytest.fail(
            "packages/sdk/src is absent under CI; submodules must be checked out recursively",
            pytrace=False,
        )
    pytest.skip(
        "packages/sdk not initialized; run: git submodule update --init packages/sdk",
        allow_module_level=True,
    )

sys.path.insert(0, str(SDK_SRC))

from benchweave_sdk.validation import validate_descriptor  # noqa: E402


def _census() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(VECTORS.read_bytes())
    return document


def _base_descriptor() -> dict[str, Any]:
    """A schema-valid OTDP 0.1.2 descriptor to carry census declarations.

    The corpus class example is the honest base: it is the descriptor the
    architecture validator already admits, and ``derived_variables`` is a
    new optional top-level property beside its existing content.
    """

    descriptor: dict[str, Any] = json.loads(CLASS_EXAMPLE.read_bytes())
    assert descriptor["otdp_version"] == "0.1.2"
    return descriptor


def _sdk_check(derived: list[dict[str, Any]]) -> None:
    descriptor = _base_descriptor()
    if derived:
        descriptor["derived_variables"] = derived
    validate_descriptor(descriptor)


def _gateway_check(derived: list[dict[str, Any]]) -> None:
    check_derived_variables(derived)


@pytest.mark.parametrize(
    "row",
    [*_census()["grammar"], *_census()["static"]],
    ids=lambda row: row["id"],
)
def test_both_lanes_agree_on_every_census_row(row: dict[str, Any]) -> None:
    derived = (
        row["derived"]
        if "derived" in row
        else [
            {
                "id": "probe0",
                "quantity": "probe",
                "unit": "1",
                "expression": row["expression"],
            }
        ]
    )
    if row["expect"] == "accept":
        _gateway_check(derived)
        _sdk_check(derived)
        return
    prefix = str(row["reason_prefix"])
    with pytest.raises(DerivationRejected) as gateway_raised:
        _gateway_check(derived)
    assert str(gateway_raised.value).startswith(prefix), str(gateway_raised.value)
    with pytest.raises(ValueError) as sdk_raised:
        _sdk_check(derived)
    assert prefix in str(sdk_raised.value), str(sdk_raised.value)
    assert "S19" in str(sdk_raised.value), str(sdk_raised.value)


def test_sdk_accepts_a_well_formed_declaration() -> None:
    descriptor = _base_descriptor()
    descriptor["derived_variables"] = [
        {
            "id": "rail_offset",
            "quantity": "voltage",
            "unit": "V",
            "expression": "voltage - 4.5",
        }
    ]
    validate_descriptor(descriptor)


def test_sdk_rejects_derived_variables_of_the_wrong_shape() -> None:
    descriptor = _base_descriptor()
    descriptor["derived_variables"] = "voltage - 4.5"
    with pytest.raises(ValueError, match="S19"):
        validate_descriptor(descriptor)


def test_census_bytes_are_identical_in_the_vendored_tree() -> None:
    """The agreement pin holds only if both lanes read the same bytes."""

    vendored = (
        SDK_SRC
        / "benchweave_sdk"
        / "standards"
        / "otdp"
        / "0.1.2"
        / "examples"
        / "derivation-vectors.json"
    )
    assert vendored.is_file(), f"vendored census absent: {vendored}"
    assert vendored.read_bytes() == VECTORS.read_bytes()
