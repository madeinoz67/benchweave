# author: Stephen Eaton
"""A6: the evidence gate, made mechanical rather than promised.

The rule (A02, and the owner's ruling on issue #92): a claim about the
physical unit enters the descriptor only with evidence from the unit. This
guard reads the committed evidence sheet and refuses a descriptor that makes
a gated claim no ``EVIDENCED`` row with a ``hardware`` origin unlocks.

Gated claims and the row each one needs:

- a ``supported_firmware`` entry ``v`` needs ``firmware:v``
- a profile in ``profiles`` needs ``profile:<id>``
- a bounds-bearing parameter, ``capture_limits``, ``stream_limits``, or a
  non-empty ``input_constraints`` needs ``bounds:<name>``
- a declared channel needs ``channels:<id>``
- any transport type other than ``custom``, and any transport provider, needs
  ``transport:<type>``

What this guard does not catch: whether a cited capture is real; whether code
that claims to implement an evidenced fact does; a verb added to
``capabilities`` whose parameters carry no bounds; a change to the evidence
sheet that turns a row ``EVIDENCED`` without a capture behind it. Those stay
with the reviewer.
"""

import copy
import datetime as dt
import json
import re
from typing import Any

import pytest
from support import EVIDENCE_SHEET, PACKAGE

DESCRIPTOR = PACKAGE / "descriptor.json"
BASE_KEYS = ("transport", "firmware", "dialect", "bounds", "channels")
BOUNDS_FIELDS = ("range", "enum_values", "string_constraints")
CUSTOM = "custom"
TRANSPORT_ROW_PREFIX = "STATUS[transport]:"
USBTMC = {"type": "usbtmc", "connection_key": "dho924s", "settings": {}}

STATUS_LINE = re.compile(r"^STATUS\[([a-z0-9_.:-]+)\]: (.*)$")
EVIDENCED_ROW = re.compile(
    r"^EVIDENCED \| source=(\S.*?) \| date=(\d{4}-\d{2}-\d{2}) \| origin=(hardware|simulator)$"
)
UNKNOWN_ROW = re.compile(r"^UNKNOWN — evidence needed: (\S.*)$")


def hardware_row(key: str) -> str:
    """A well-formed EVIDENCED row whose origin is hardware (invented)."""
    return f"STATUS[{key}]: EVIDENCED | source=a capture | date=2026-11-28 | origin=hardware"


def simulator_row(key: str) -> str:
    """A well-formed EVIDENCED row whose origin is a simulator (invented)."""
    return f"STATUS[{key}]: EVIDENCED | source=a mock | date=2026-11-28 | origin=simulator"


def read_descriptor() -> dict[str, Any]:
    descriptor: dict[str, Any] = json.loads(DESCRIPTOR.read_text(encoding="utf-8"))
    return descriptor


def read_sheet() -> str:
    return EVIDENCE_SHEET.read_text(encoding="utf-8")


def over_claiming(**changes: Any) -> dict[str, Any]:
    """The committed descriptor with one over-claim applied."""
    descriptor = copy.deepcopy(read_descriptor())
    for key, value in changes.items():
        descriptor[key] = value
    return descriptor


def with_identity(**changes: Any) -> dict[str, Any]:
    descriptor = over_claiming()
    descriptor["identity"].update(changes)
    return descriptor


def parse_rows(sheet: str) -> dict[str, str]:
    """Every status line as key -> origin ('hardware', 'simulator' or 'UNKNOWN').

    A malformed line refuses.
    """
    rows: dict[str, str] = {}
    for number, line in enumerate(sheet.splitlines(), start=1):
        match = STATUS_LINE.match(line)
        if match is None:
            if line.startswith("STATUS"):
                raise ValueError(f"evidence sheet line {number}: malformed status line")
            continue
        key, body = match.groups()
        if key in rows:
            raise ValueError(f"evidence sheet line {number}: duplicate row {key}")
        if body.startswith("EVIDENCED"):
            row = EVIDENCED_ROW.match(body)
            if row is None:
                raise ValueError(f"evidence sheet line {number}: malformed EVIDENCED row {key}")
            dt.date.fromisoformat(row.group(2))
            rows[key] = row.group(3)
        elif body.startswith("UNKNOWN"):
            if UNKNOWN_ROW.match(body) is None:
                raise ValueError(f"evidence sheet line {number}: malformed UNKNOWN row {key}")
            rows[key] = "UNKNOWN"
        else:
            raise ValueError(f"evidence sheet line {number}: unknown state for {key}")
    return rows


def sheet_faults(rows: dict[str, str]) -> list[str]:
    """The sheet must carry each gated fact, and a detail cannot outrun its base.

    A detail evidenced from hardware needs its base evidenced from hardware.
    A detail evidenced from a simulator needs its base evidenced at all.
    """
    faults = [
        f"evidence sheet lacks a status row for {key}" for key in BASE_KEYS if key not in rows
    ]
    for key, origin in rows.items():
        base, _, detail = key.partition(":")
        if not detail or origin == "UNKNOWN" or base not in BASE_KEYS:
            continue
        base_origin = rows.get(base, "UNKNOWN")
        if base_origin == "UNKNOWN" or (origin == "hardware" and base_origin != "hardware"):
            faults.append(f"evidence sheet: {key} is EVIDENCED but {base} is not")
    return faults


def ungated_claims(descriptor: dict[str, Any], sheet: str) -> list[str]:
    """Every gated claim in the descriptor that no hardware row unlocks."""
    rows = parse_rows(sheet)
    faults = sheet_faults(rows)

    def needs(key: str, claim: str) -> None:
        if rows.get(key) != "hardware":
            faults.append(f"{claim} needs a hardware EVIDENCED row: STATUS[{key}]")

    for version in descriptor.get("identity", {}).get("supported_firmware", []):
        needs(f"firmware:{version}", f"supported_firmware entry {version!r}")
    for profile in descriptor.get("profiles", []):
        needs(f"profile:{profile}", f"profile claim {profile!r}")
    for parameter in descriptor.get("parameters", []):
        if any(field in parameter for field in BOUNDS_FIELDS):
            needs(f"bounds:{parameter['name']}", f"bounds on parameter {parameter['name']!r}")
    for section in ("capture_limits", "stream_limits"):
        if section in descriptor:
            needs(f"bounds:{section}", section)
    for action_id, action in descriptor.get("actions", {}).items():
        if action.get("input_constraints"):
            needs(f"bounds:{action_id}", f"input_constraints on {action_id!r}")
    for channel in descriptor.get("channels", []):
        needs(f"channels:{channel['id']}", f"channel {channel['id']!r}")
    transport = descriptor.get("transport", {})
    if transport.get("type") != CUSTOM:
        needs(f"transport:{transport.get('type')}", f"transport type {transport.get('type')!r}")
    if "provider" in transport:
        needs("transport:provider", "transport provider")
    return faults


def sheet_with(*rows: str) -> str:
    """The committed sheet with its transport row replaced by the given rows."""
    lines = read_sheet().splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith(TRANSPORT_ROW_PREFIX))
    lines[index : index + 1] = list(rows)
    return "\n".join(lines) + "\n"


def test_the_committed_descriptor_makes_no_claim_the_evidence_sheet_does_not_unlock() -> None:
    assert ungated_claims(read_descriptor(), read_sheet()) == []


def test_each_listed_firmware_version_needs_its_own_row() -> None:
    listed = with_identity(firmware_policy="listed", supported_firmware=["0.0.0", "9.9.9"])
    assert ungated_claims(listed, read_sheet()) == [
        "supported_firmware entry '0.0.0' needs a hardware EVIDENCED row: STATUS[firmware:0.0.0]",
        "supported_firmware entry '9.9.9' needs a hardware EVIDENCED row: STATUS[firmware:9.9.9]",
    ]


@pytest.mark.parametrize(
    ("descriptor", "needed"),
    [
        pytest.param(
            with_identity(firmware_policy="listed", supported_firmware=["0.0.0"]),
            "STATUS[firmware:0.0.0]",
            id="supported-firmware-entry",
        ),
        pytest.param(
            over_claiming(profiles=["otdp.oscilloscope/1.0.0"]),
            "STATUS[profile:otdp.oscilloscope/1.0.0]",
            id="profile-claim",
        ),
        pytest.param(
            over_claiming(
                parameters=[
                    {
                        "name": "ch1_scale",
                        "description": "synthetic over-claim",
                        "type": "float",
                        "access": "ro",
                        "semantic": "configuration",
                        "range": [0.001, 10.0],
                        "binding": {"kind": "adapter", "key": "ch1_scale"},
                    }
                ]
            ),
            "STATUS[bounds:ch1_scale]",
            id="bounds-bearing-parameter",
        ),
        pytest.param(
            over_claiming(
                parameters=[
                    {
                        "name": "ch1_coupling",
                        "description": "synthetic over-claim",
                        "type": "enum",
                        "access": "ro",
                        "semantic": "configuration",
                        "enum_values": ["ac", "dc"],
                        "binding": {"kind": "adapter", "key": "ch1_coupling"},
                    }
                ]
            ),
            "STATUS[bounds:ch1_coupling]",
            id="enum-values-are-bounds",
        ),
        pytest.param(
            over_claiming(capture_limits={"max_samples": 1000000, "max_bytes": 8000000}),
            "STATUS[bounds:capture_limits]",
            id="class-maximum-copied-as-capture-limits",
        ),
        pytest.param(
            over_claiming(stream_limits={"min_interval_ms": 20, "max_subscriptions": 1}),
            "STATUS[bounds:stream_limits]",
            id="stream-limits",
        ),
        pytest.param(
            over_claiming(
                actions={
                    "otdp.oscilloscope.configure/1.0.0": {
                        "binding": {"kind": "adapter", "key": "configure"},
                        "input_constraints": {"properties": {"sample_count": {"maximum": 1000}}},
                        "timeout_ms": 1000,
                        "side_effect": "state_change",
                        "cancellable": True,
                        "retry": "never",
                    }
                }
            ),
            "STATUS[bounds:otdp.oscilloscope.configure/1.0.0]",
            id="action-input-constraints",
        ),
        pytest.param(
            over_claiming(
                channels=[
                    {
                        "id": "ch1",
                        "label": "synthetic over-claim",
                        "role": "analogue_input",
                        "quantities": ["voltage"],
                        "parameter_names": [],
                    }
                ]
            ),
            "STATUS[channels:ch1]",
            id="declared-channel",
        ),
        pytest.param(
            over_claiming(
                transport={
                    "type": "usbtmc",
                    "connection_key": "dho924s",
                    "settings": {
                        "vid": 1,
                        "pid": 1,
                        "write_termination": "lf",
                        "read_termination": "lf",
                        "max_response_bytes": 256,
                    },
                }
            ),
            "STATUS[transport:usbtmc]",
            id="usbtmc-transport",
        ),
        pytest.param(
            over_claiming(
                transport={
                    "type": "lan_scpi",
                    "connection_key": "dho924s",
                    "settings": {
                        "protocol": "raw",
                        "port": 5555,
                        "write_termination": "lf",
                        "read_termination": "lf",
                        "max_response_bytes": 256,
                    },
                }
            ),
            "STATUS[transport:lan_scpi]",
            id="lan-scpi-transport",
        ),
        pytest.param(
            over_claiming(
                transport={
                    "type": "custom",
                    "connection_key": "dho924s",
                    "settings": {"protocol_reference": "synthetic over-claim"},
                    "provider": {
                        "feature_id": "otdp.transport.synthetic/1.0.0",
                        "id": "urn:otdp:transport-provider:synthetic:1.0.0",
                        "path": "synthetic.json",
                        "sha256": "0" * 64,
                    },
                }
            ),
            "STATUS[transport:provider]",
            id="transport-provider",
        ),
    ],
)
def test_an_over_claiming_descriptor_is_refused_without_a_hardware_row(
    descriptor: dict[str, Any], needed: str
) -> None:
    faults = ungated_claims(descriptor, read_sheet())
    assert len(faults) == 1, faults
    assert needed in faults[0]


def test_an_empty_constraints_object_is_not_a_bounds_claim() -> None:
    # `{}` in a structural fixture is no evidence; the class rule says so. It
    # is also no bound, so it is not this guard's to refuse.
    assert ungated_claims(over_claiming(actions={}), read_sheet()) == []


def test_a_simulator_row_unlocks_nothing() -> None:
    sheet = sheet_with(
        simulator_row("transport"),
        simulator_row("transport:usbtmc"),
    )
    faults = ungated_claims(over_claiming(transport=USBTMC), sheet)
    assert len(faults) == 1 and "STATUS[transport:usbtmc]" in faults[0]


@pytest.mark.parametrize(
    "row",
    [
        pytest.param(
            "STATUS[transport]: EVIDENCED | source=a capture | date=2026-11-28",
            id="no-origin",
        ),
        pytest.param(
            "STATUS[transport]: EVIDENCED | date=2026-11-28 | origin=hardware",
            id="no-source",
        ),
        pytest.param(
            "STATUS[transport]: EVIDENCED | source=a capture | origin=hardware",
            id="no-date",
        ),
        pytest.param(
            "STATUS[transport]: EVIDENCED | source=a capture | date=2026-13-40 | origin=hardware",
            id="impossible-date",
        ),
        pytest.param(
            "STATUS[transport]: EVIDENCED | source=a capture | date=yesterday | origin=hardware",
            id="date-not-a-date",
        ),
        pytest.param(
            "STATUS[transport]: EVIDENCED | source=a capture | date=2026-11-28 | origin=both",
            id="unknown-origin",
        ),
        pytest.param(
            "STATUS[transport]: PROBABLY | source=a capture | date=2026-11-28 | origin=hardware",
            id="unknown-state",
        ),
        pytest.param("STATUS[transport]: UNKNOWN — see the manual", id="unknown-without-evidence"),
        pytest.param("STATUS transport]: UNKNOWN — evidence needed: x", id="malformed-line"),
        pytest.param("STATUS[transport]: EVIDENCED", id="bare-evidenced"),
    ],
)
def test_a_malformed_row_is_refused(row: str) -> None:
    with pytest.raises(ValueError):
        ungated_claims(read_descriptor(), sheet_with(row))


def test_a_deleted_row_unlocks_nothing() -> None:
    sheet = "".join(
        line
        for line in read_sheet().splitlines(keepends=True)
        if not line.startswith(TRANSPORT_ROW_PREFIX)
    )
    faults = ungated_claims(over_claiming(transport=USBTMC), sheet)
    assert any("lacks a status row for transport" in fault for fault in faults)
    assert any("STATUS[transport:usbtmc]" in fault for fault in faults)


def test_a_detailed_row_cannot_outrun_its_base_fact() -> None:
    faults = ungated_claims(read_descriptor(), sheet_with(hardware_row("transport:usbtmc")))
    assert faults == [
        "evidence sheet lacks a status row for transport",
        "evidence sheet: transport:usbtmc is EVIDENCED but transport is not",
    ]


def test_a_hardware_row_unlocks_exactly_its_claim() -> None:
    sheet = sheet_with(hardware_row("transport"), hardware_row("transport:usbtmc"))
    assert ungated_claims(over_claiming(transport=USBTMC), sheet) == []
    lan = over_claiming(transport={"type": "lan_scpi", "connection_key": "dho924s", "settings": {}})
    faults = ungated_claims(lan, sheet)
    assert len(faults) == 1 and "STATUS[transport:lan_scpi]" in faults[0]
    listed = with_identity(firmware_policy="listed", supported_firmware=["0.0.0"])
    faults = ungated_claims(listed, sheet)
    assert len(faults) == 1 and "STATUS[firmware:0.0.0]" in faults[0]
