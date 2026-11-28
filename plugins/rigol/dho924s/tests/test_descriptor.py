# author: Stephen Eaton
"""A1: the descriptor is honest and minimal, and validates against the schema
of its own pin.

The descriptor pins the OTDP version that its contract lock names. That pin is
behind the corpus active version, on purpose. Every in-tree plugin pins the
same served version, and the repository's descriptor-dialect control
(tests/contract/test_plugin_descriptor_dialect.py, which this project cannot
run from its own environment) pins that fact. Move this pin only with that
control.
"""

import json
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from support import PACKAGE, ROOT, SYNTHETIC_PROVENANCE, contracts_dir, vectors

from benchweave_rigol_dho924s.descriptor import (
    CONNECTION_KEY,
    DESCRIPTOR_ID,
    MANUFACTURER,
    MODEL,
    build_descriptor,
)

# The served OTDP version every in-tree plugin pins (see the module docstring).
PINNED_OTDP_VERSION = "0.2.2"


def descriptor() -> dict[str, Any]:
    return build_descriptor()


def test_factory_returns_an_independent_copy_of_the_packaged_declaration() -> None:
    packaged = json.loads(
        files("benchweave_rigol_dho924s").joinpath("descriptor.json").read_text(encoding="utf-8")
    )
    assert build_descriptor() == packaged
    assert packaged == json.loads((PACKAGE / "descriptor.json").read_text())
    changed = build_descriptor()
    changed["capabilities"].clear()
    changed["identity"]["firmware_policy"] = "listed"
    assert build_descriptor() == packaged


def test_descriptor_validates_against_the_schema_of_its_own_pin() -> None:
    document = descriptor()
    lock = json.loads((ROOT / "contracts/lock.json").read_text())
    assert document["otdp_version"] == lock["otdp_version"] == PINNED_OTDP_VERSION
    assert lock["directory"] == f"standards/otdp/{lock['otdp_version']}"
    schema = json.loads((contracts_dir() / "otdp-device-descriptor.schema.json").read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)


def test_capabilities_are_exactly_identify() -> None:
    document = descriptor()
    assert document["capabilities"] == ["identify"]
    assert list(document["operations"]) == ["identify"]
    assert document["operations"]["identify"] == {
        "timeout_ms": 1000,
        "side_effect": "none",
        "retry": "never",
        "cancellable": True,
        "completion": "acknowledged",
    }


def test_transport_is_custom_with_no_provider() -> None:
    document = descriptor()
    assert document["transport"] == {
        "type": "custom",
        "connection_key": CONNECTION_KEY,
        "settings": {
            "protocol_reference": (
                "rigol-dho900-scpi (documentary only, unqualified; see docs/device-evidence.md)"
            )
        },
    }
    assert CONNECTION_KEY == "dho924s"


def test_identity_claims_no_firmware() -> None:
    document = descriptor()
    assert document["identity"] == {
        "strategy": "adapter",
        "manufacturer": MANUFACTURER,
        "model": MODEL,
        "firmware_policy": "commissioned",
    }
    assert (MANUFACTURER, MODEL) == ("RIGOL", "DHO924S")
    assert "supported_firmware" not in document["identity"]


def test_no_bounds_profile_channels_or_capture_surface() -> None:
    document = descriptor()
    assert document["parameters"] == []
    absent = {
        "profiles",
        "channels",
        "actions",
        "contracts",
        "decoders",
        "capture_formats",
        "capture_limits",
        "stream_limits",
        "diagnostics",
        "derived_variables",
    }
    assert not absent & document.keys()


def test_adapter_block_names_the_factory_and_the_scoped_transport_permission() -> None:
    document = descriptor()
    assert document["id"] == DESCRIPTOR_ID == "org.benchweave.rigol-dho924s"
    assert document["integration"] == {
        "mode": "adapter",
        "adapter": {
            "entry_point": "benchweave_rigol_dho924s.adapter:create_plugin",
            "api_version": "1.1",
            "version": "0.1.0",
            "dependencies": [],
            "permissions": ["scoped_transport"],
        },
    }
    assert document["required_features"] == ["otdp.core/0.1.0", "otdp.adapter/0.1.0"]


def test_description_says_that_the_integration_is_unqualified() -> None:
    description = descriptor()["description"]
    assert description.startswith("UNQUALIFIED")
    assert "not claimed" in description
    assert "docs/device-evidence.md" in description


def test_vector_files_are_packaged_and_name_themselves_synthetic() -> None:
    for vector in descriptor()["provenance"]["test_vectors"]:
        path = (PACKAGE / vector["path"]).resolve()
        assert path.is_relative_to(PACKAGE) and path.is_file()
        assert "not hardware-qualified" in vector["purpose"]
    for name in ("adapter-vectors.json", "adapter-failure-vectors.json"):
        assert json.loads((PACKAGE / name).read_text())["provenance"] == (SYNTHETIC_PROVENANCE)
        assert files("benchweave_rigol_dho924s").joinpath(name).is_file()


def test_the_documentary_source_is_cited_as_documentary_only() -> None:
    sources = descriptor()["provenance"]["sources"]
    assert len(sources) == 1
    source = sources[0]
    assert "not evidence from any unit" in source["title"]
    assert source["reference"].endswith("DHO800900_ProgrammingGuide_EN.pdf")
    assert "sha256" in source["revision"]


def test_project_files_the_guide_requires_are_present() -> None:
    assert (ROOT / "README.md").is_file()
    assert (ROOT / "LICENSE").is_file()
    assert (ROOT / "docs" / "device-evidence.md").is_file()
    assert (ROOT / "uv.lock").is_file()
    assert vectors("adapter-vectors.json")
