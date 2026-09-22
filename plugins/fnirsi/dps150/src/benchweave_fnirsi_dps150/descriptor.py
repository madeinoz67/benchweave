"""Pure, exact descriptor contract; admission performs no filesystem I/O."""

from typing import Any

# Field, component (None for a scalar), logical type, unit, semantic, choices.
PARAMETERS = (
    ("voltage", 195, 0, "float", "V", "measurement", ()),
    ("current", 195, 1, "float", "A", "measurement", ()),
    ("power", 195, 2, "float", "W", "measurement", ()),
    ("input_voltage", 192, None, "float", "V", "measurement", ()),
    ("temperature", 196, None, "float", "Cel", "measurement", ()),
    ("output_enabled", 219, None, "bool", None, "state", ()),
    (
        "protection",
        220,
        None,
        "enum",
        None,
        "state",
        ("normal", "OVP", "OCP", "OPP", "OTP", "LVP", "REP"),
    ),
    ("mode", 221, None, "enum", None, "state", ("CC", "CV")),
)


def build_descriptor() -> dict[str, Any]:
    """Return an independent copy of the reviewed, local-only integration contract."""
    parameters = []
    for name, _, _, kind, unit, semantic, choices in PARAMETERS:
        parameter: dict[str, Any] = {
            "name": name,
            "description": f"Device-reported {name.replace('_', ' ')}; receipt timestamp only.",
            "type": kind,
            "access": "ro",
            "semantic": semantic,
            "read_policy": {"max_age_ms": 0, "destructive": False},
            "binding": {"kind": "adapter", "key": name},
        }
        if unit is not None:
            parameter["unit"] = unit
        if choices:
            parameter["enum_values"] = list(choices)
        parameters.append(parameter)
    return {
        "otdp_version": "0.2.1",
        "descriptor_version": "0.2.0",
        "id": "org.benchweave.fnirsi-dps150",
        "display_name": "FNIRSI DPS-150 (read-only, KochC empty-GET dialect)",
        "description": (
            "Mock-qualified core identity and scalar reads; "
            "no DC PSU profile or hardware qualification."
        ),
        "identity": {
            "strategy": "adapter",
            "manufacturer": "FNIRSI",
            "model": "DPS-150",
            "firmware_policy": "commissioned",
        },
        "integration": {
            "mode": "adapter",
            "adapter": {
                "entry_point": "benchweave_fnirsi_dps150.adapter:create_plugin",
                "api_version": "1.1",
                "version": "0.1.0",
                "dependencies": [],
                "permissions": ["scoped_transport"],
            },
        },
        "transport": {
            "type": "serial",
            "connection_key": "dps150",
            "settings": {
                "baud": 115200,
                "data_bits": 8,
                "parity": "none",
                "stop_bits": 1,
                "rtscts": True,
                "max_frame_bytes": 260,
            },
        },
        "capabilities": ["identify", "read"],
        "operations": {
            verb: {
                "timeout_ms": 1000,
                "side_effect": "none",
                "retry": "never",
                "cancellable": True,
                "completion": "acknowledged",
            }
            for verb in ("identify", "read")
        },
        "parameters": parameters,
        "required_features": ["otdp.core/0.1.0", "otdp.adapter/0.1.0"],
        "provenance": {
            "sources": [
                {
                    "title": "KochC protocol mappings and serial settings",
                    "reference": "https://github.com/KochC/DPS-150-python-library/tree/ae1df445d5993bdc0839d863ac1ba25d9d1bbfae",
                    "revision": "ae1df445d5993bdc0839d863ac1ba25d9d1bbfae",
                },
                {
                    "title": "cho45 framing reference (MIT); GET dialect differs",
                    "reference": "https://github.com/cho45/fnirsi-dps-150/tree/6107bd34531aa52692d757e3b82d9573750311ac",
                    "revision": "6107bd34531aa52692d757e3b82d9573750311ac",
                },
            ],
            "test_vectors": [
                {
                    "id": "scalar-reads",
                    "path": "adapter-vectors.json",
                    "purpose": (
                        "Exact mocked queries, responses and runtime readings "
                        "for every advertised parameter"
                    ),
                },
                {
                    "id": "failure-cases",
                    "path": "adapter-failure-vectors.json",
                    "purpose": (
                        "Mocked rejection, malformed response, deadline and uncertain outcomes"
                    ),
                },
            ],
        },
    }
