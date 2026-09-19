"""sim_scope preset lanes — the issue #6 row A acceptance proof.

Design §7.2: the shipped preset set is a census (N = 2). The metric is the
real CLI lanes' exit codes read from ``cli.main`` return values, plus finding
codes where a RED control targets a specific refusal. Every control mutates a
tmp copy — the shipped bytes are never touched. Modeled on
tests/sdk/test_presentation_cli.py (syspath prepend, in-process CLI).
"""

from __future__ import annotations

import hashlib
import importlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "plugins" / "benchweave" / "sim_scope" / "src" / "benchweave_sim_scope"
DESCRIPTOR = PACKAGE / "descriptor.json"
SETTINGS_SCHEMA = PACKAGE / "ui" / "settings" / "oscilloscope-configure.schema.json"
PRESET_FAST = PACKAGE / "ui" / "presets" / "fast-survey.json"
PRESET_PAIR = PACKAGE / "ui" / "presets" / "low-noise-pair.json"
SHIPPED_PRESETS = (PRESET_FAST, PRESET_PAIR)
FIRMWARE = "sim-1.0.0"


@pytest.fixture(autouse=True)
def sdk_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "packages/sdk/src"))


def run(monkeypatch: pytest.MonkeyPatch, *arguments: str | Path) -> int:
    cli = importlib.import_module("benchweave_sdk.cli")
    exit_code: int = cli.main([*map(str, arguments)])
    return exit_code


def lane1(monkeypatch: pytest.MonkeyPatch, preset: Path, *, firmware: str = FIRMWARE) -> int:
    return run(
        monkeypatch,
        "check-preset",
        preset,
        "--descriptor",
        DESCRIPTOR,
        "--settings-schema",
        SETTINGS_SCHEMA,
        "--firmware",
        firmware,
    )


def lane2(monkeypatch: pytest.MonkeyPatch, package: Path = PACKAGE) -> int:
    return run(
        monkeypatch,
        "check-ui",
        package / "presentation.json",
        "--descriptor",
        package / "descriptor.json",
        "--resources",
        package,
        "--catalogue",
        package / "binding-catalogue.json",
        "--firmware",
        FIRMWARE,
    )


def encode(document: object) -> bytes:
    return json.dumps(document).encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def preset_report(raw: bytes) -> Any:
    presentation = importlib.import_module("benchweave_sdk.presentation")
    return presentation.validate_preset(
        raw,
        descriptor_raw=DESCRIPTOR.read_bytes(),
        settings_schema_raw=SETTINGS_SCHEMA.read_bytes(),
        firmware=FIRMWARE,
    )


def ui_report(package: Path) -> Any:
    presentation = importlib.import_module("benchweave_sdk.presentation")
    return presentation.check_ui(
        package / "presentation.json",
        package / "descriptor.json",
        package,
        package / "binding-catalogue.json",
        firmware=FIRMWARE,
        features=frozenset(),
        panels=frozenset(),
    )


def findings(report: Any) -> set[str]:
    return {row.code for row in report.findings}


def copy_package(tmp_path: Path) -> Path:
    package = tmp_path / "benchweave_sim_scope"
    shutil.copytree(PACKAGE, package)
    return package


def write_document(path: Path, document: object) -> Path:
    path.write_bytes(encode(document))
    return path


def repin_manifest_and_envelope(package: Path) -> None:
    """Recompute asset digests in the manifest, then the manifest pin upstream."""
    manifest_path = package / "ui" / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    for asset in manifest["assets"]:
        raw = (package / "ui" / asset["path"]).read_bytes()
        asset["sha256"] = digest(raw)
    write_document(manifest_path, manifest)
    envelope_path = package / "presentation.json"
    envelope = json.loads(envelope_path.read_bytes())
    envelope["manifest"]["sha256"] = digest(manifest_path.read_bytes())
    write_document(envelope_path, envelope)


def _repin_descriptor_sha256(package: Path) -> None:
    """Re-pin descriptor_sha256 in every document that carries it.

    check-ui verifies the descriptor digest in the manifest, the envelope and
    the binding catalogue, so a tmp-package descriptor edit must move all
    three or the package reports digest_mismatch instead of the finding the
    control targets."""
    pin = digest((package / "descriptor.json").read_bytes())
    for name in ("ui/manifest.json", "presentation.json", "binding-catalogue.json"):
        path = package / name
        document = json.loads(path.read_bytes())
        document["descriptor_sha256"] = pin
        write_document(path, document)


# --- the two acceptance lanes over the shipped package -------------------------


@pytest.mark.parametrize("preset", SHIPPED_PRESETS, ids=lambda path: path.name)
def test_lane1_check_preset_passes_for_shipped_preset(
    monkeypatch: pytest.MonkeyPatch, preset: Path
) -> None:
    assert lane1(monkeypatch, preset) == 0


def test_lane2_check_ui_passes_for_shipped_package(monkeypatch: pytest.MonkeyPatch) -> None:
    assert lane2(monkeypatch) == 0


# --- RED controls: lane 1 (check-preset) ---------------------------------------


def test_l1a_schema_violating_settings_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preset = json.loads(PRESET_PAIR.read_bytes())
    preset["settings"]["channels"][0]["range_v"] = -1.0
    broken = write_document(tmp_path / "broken.json", preset)
    assert lane1(monkeypatch, broken) != 0
    assert "invalid_settings" in findings(preset_report(broken.read_bytes()))


def test_l1a_averaging_within_envelope_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The admission control of the OTDP 0.2.0 catalog revision (issue #64):
    an in-envelope averaging_count rides preset settings and passes lane 1.
    Under 0.1.2 this exact document was refused as an unknown key — the
    pinned refusal this test replaces."""
    preset = json.loads(PRESET_PAIR.read_bytes())
    preset["settings"]["averaging_count"] = 8
    admitted = write_document(tmp_path / "admitted.json", preset)
    assert lane1(monkeypatch, admitted) == 0
    assert "invalid_settings" not in findings(preset_report(admitted.read_bytes()))


def test_l1a_averaging_at_corpus_maximum_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drift pin (refute row R1): lane 1 admits the endpoint 64 itself.
    Paired with the 65-refusal row below, a corpus maximum that drifts below
    64 (say 63) turns THIS row red instead of silently narrowing the
    envelope — the interior-8 row cannot catch that."""
    preset = json.loads(PRESET_PAIR.read_bytes())
    preset["settings"]["averaging_count"] = 64
    admitted = write_document(tmp_path / "at-max.json", preset)
    assert lane1(monkeypatch, admitted) == 0
    assert "invalid_settings" not in findings(preset_report(admitted.read_bytes()))


def test_l1a_averaging_above_corpus_maximum_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression pin, not a RED control: 65 is refused before the revision
    (unknown key) and after it (above the corpus maximum of 64) — the
    observable that distinguishes the worlds is the in-envelope admission
    above, not this refusal."""
    preset = json.loads(PRESET_PAIR.read_bytes())
    preset["settings"]["averaging_count"] = 65
    broken = write_document(tmp_path / "broken.json", preset)
    assert lane1(monkeypatch, broken) != 0
    assert "invalid_settings" in findings(preset_report(broken.read_bytes()))


def test_l1a_averaging_below_corpus_minimum_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression pin, not a RED control: 0 is refused before the revision
    (unknown key) and after it (below the corpus minimum of 1)."""
    preset = json.loads(PRESET_PAIR.read_bytes())
    preset["settings"]["averaging_count"] = 0
    broken = write_document(tmp_path / "broken.json", preset)
    assert lane1(monkeypatch, broken) != 0
    assert "invalid_settings" in findings(preset_report(broken.read_bytes()))


def test_l1b_incompatible_firmware_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    assert lane1(monkeypatch, PRESET_FAST, firmware="other-9.9.9") != 0
    presentation = importlib.import_module("benchweave_sdk.presentation")
    incompatible = presentation.validate_preset(
        PRESET_FAST.read_bytes(),
        descriptor_raw=DESCRIPTOR.read_bytes(),
        settings_schema_raw=SETTINGS_SCHEMA.read_bytes(),
        firmware="other-9.9.9",
    )
    assert "incompatible_firmware" in findings(incompatible)


def test_l1c_drifted_settings_schema_bytes_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    drifted = tmp_path / "drifted.schema.json"
    drifted.write_bytes(SETTINGS_SCHEMA.read_bytes() + b"\n")
    cli = importlib.import_module("benchweave_sdk.cli")
    exit_code = cli.main(
        [
            "check-preset",
            str(PRESET_FAST),
            "--descriptor",
            str(DESCRIPTOR),
            "--settings-schema",
            str(drifted),
            "--firmware",
            FIRMWARE,
        ]
    )
    assert exit_code != 0
    presentation = importlib.import_module("benchweave_sdk.presentation")
    report = presentation.validate_preset(
        PRESET_FAST.read_bytes(),
        descriptor_raw=DESCRIPTOR.read_bytes(),
        settings_schema_raw=drifted.read_bytes(),
        firmware=FIRMWARE,
    )
    assert "digest_mismatch" in findings(report)


def test_l1d_foreign_plugin_identity_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preset = json.loads(PRESET_FAST.read_bytes())
    preset["plugin_id"] = "dev.benchweave.other-plugin"
    broken = write_document(tmp_path / "broken.json", preset)
    assert lane1(monkeypatch, broken) != 0
    assert "identity_mismatch" in findings(preset_report(broken.read_bytes()))


# --- RED controls: lane 2 (check-ui) -------------------------------------------


def test_l2a_canonical_corpus_bounds_averaging_not_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shipped-artifact twin of test_preset_cannot_bypass_canonical_action_schema:
    even a permissive settings file cannot launder averaging past the corpus —
    and since OTDP 0.2.0 the refusing authority is the corpus bound (65 > 64),
    not the unknown-key rule the permissive file defeated."""
    package = copy_package(tmp_path)
    schema_path = package / "ui" / "settings" / "oscilloscope-configure.schema.json"
    schema = json.loads(schema_path.read_bytes())
    schema.pop("required", None)
    schema["additionalProperties"] = True
    write_document(schema_path, schema)
    preset_path = package / "ui" / "presets" / "low-noise-pair.json"
    preset = json.loads(preset_path.read_bytes())
    preset["settings"]["averaging_count"] = 65
    preset["settings_schema"]["sha256"] = digest(schema_path.read_bytes())
    write_document(preset_path, preset)
    repin_manifest_and_envelope(package)
    assert lane2(monkeypatch, package) != 0
    assert "invalid_settings" in findings(ui_report(package))


def test_l2_descriptor_constraints_tighter_than_corpus_still_refuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Descriptor input_constraints AND onto corpus-legal settings: a tmp
    descriptor narrowing averaging to [1, 8] refuses a corpus-legal 16 in
    lane 2, while lane 1 — which never consults descriptor actions — still
    passes. Pins the descriptor-AND vs corpus-OR role split the 0.2.0
    class bound relies on."""
    package = copy_package(tmp_path)
    descriptor_path = package / "descriptor.json"
    descriptor = json.loads(descriptor_path.read_bytes())
    constraints = descriptor["actions"]["otdp.oscilloscope.configure/1.0.0"][
        "input_constraints"
    ]
    constraints["properties"]["averaging_count"] = {"minimum": 1, "maximum": 8}
    write_document(descriptor_path, descriptor)
    _repin_descriptor_sha256(package)
    preset_path = package / "ui" / "presets" / "low-noise-pair.json"
    preset = json.loads(preset_path.read_bytes())
    preset["settings"]["averaging_count"] = 16
    write_document(preset_path, preset)
    repin_manifest_and_envelope(package)
    assert lane2(monkeypatch, package) != 0
    assert "invalid_settings" in findings(ui_report(package))
    assert lane1(monkeypatch, preset_path) == 0


def test_l2b_value_outside_input_constraints_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = copy_package(tmp_path)
    preset_path = package / "ui" / "presets" / "fast-survey.json"
    preset = json.loads(preset_path.read_bytes())
    preset["settings"]["sample_rate_hz"] = 2_000_000.0
    write_document(preset_path, preset)
    repin_manifest_and_envelope(package)
    assert lane2(monkeypatch, package) != 0
    assert "invalid_settings" in findings(ui_report(package))


def test_l2c_mutated_preset_bytes_after_pinning_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = copy_package(tmp_path)
    preset_path = package / "ui" / "presets" / "fast-survey.json"
    preset = json.loads(preset_path.read_bytes())
    preset["title"] = "Fast survey (edited after pinning)"
    write_document(preset_path, preset)
    assert lane2(monkeypatch, package) != 0
    assert "digest_mismatch" in findings(ui_report(package))


def test_l2d_catalogue_naming_missing_preset_asset_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = copy_package(tmp_path)
    catalogue_path = package / "binding-catalogue.json"
    catalogue = json.loads(catalogue_path.read_bytes())
    target = catalogue["targets"][0]
    target["preset_asset_ids"] = [*target["preset_asset_ids"], "preset-missing"]
    manifest_path = package / "ui" / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    binding = manifest["bindings"][0]
    binding["preset_ids"] = [*binding["preset_ids"], "preset-missing"]
    write_document(manifest_path, manifest)
    repin_manifest_and_envelope(package)
    write_document(catalogue_path, catalogue)
    assert lane2(monkeypatch, package) != 0
    assert "unresolved_reference" in findings(ui_report(package))


# --- structure pins (design §7.2 point 4) --------------------------------------


def test_settings_schema_tracks_corpus() -> None:
    """Parsed equality with the vendored corpus action input schema: the
    shipped copy cannot silently drift when the corpus moves."""
    sdk = importlib.import_module("benchweave_sdk")
    validation = importlib.import_module("benchweave_sdk.validation")
    catalog = validation.contract_documents()[
        f"otdp/{sdk.OTDP_VERSION}/device-profile-catalog.json"
    ]
    corpus = catalog["actions"]["otdp.oscilloscope.configure/1.0.0"]["input_schema"]
    shipped = json.loads(SETTINGS_SCHEMA.read_bytes())
    assert shipped == corpus


def test_presets_carry_no_presentation_fields() -> None:
    settings_keys = {
        "configuration_id",
        "channels",
        "sample_rate_hz",
        "sample_count",
        "pretrigger_fraction",
        "trigger",
        "averaging_count",
    }
    channel_keys = {"channel", "coupling", "range_v", "offset_v", "probe_ratio"}
    for path in SHIPPED_PRESETS:
        preset = json.loads(path.read_bytes())
        assert set(preset["settings"]) <= settings_keys, path
        for item in preset["settings"]["channels"]:
            assert set(item) <= channel_keys, path


def test_descriptor_labels_units_present() -> None:
    descriptor = json.loads(DESCRIPTOR.read_bytes())
    for channel in descriptor["channels"]:
        assert isinstance(channel.get("label"), str) and channel["label"], channel["id"]
    for parameter in descriptor["parameters"]:
        if parameter["name"].endswith("_v"):
            assert parameter.get("unit") == "V", parameter["name"]


# --- descriptor-envelope census (fix wave F1) -----------------------------------
# {field, value} x {lane 1 check-preset, lane 2 check-ui, plugin dispatch}.
# The plugin column is the envelope's definition; the lanes are the preset
# verification mechanism. Lane 1 is pinned at its honest structural behavior:
# check-preset validates settings against the settings-schema FILE (the corpus
# byte copy) and never consults the descriptor's action input_constraints, so
# it cannot refuse a corpus-legal value that violates the descriptor envelope.
# Lane 2 is where the declared envelope bites (input_constraints are AND-ed
# onto preset settings in the configuration-binding loop). Since OTDP 0.2.0
# (issue #64) this residual applies to descriptor-only envelopes (range_v,
# offset_v): corpus-bounded fields — sample_count's class maximum, the
# averaging_count range — are refused by lane 1 too, because the bound lives
# in the settings-schema bytes themselves (top-level census below).

ENVELOPE_MATRIX = [
    ("range_v", 25.0, True),
    ("range_v", 0.0005, True),
    ("offset_v", 100.0, True),
    ("range_v", 10.0, False),
    ("range_v", 0.001, False),
    ("offset_v", -10.0, False),
    ("range_v", 10.001, True),
    ("range_v", 0.0009, True),
    ("offset_v", -10.001, True),
]


def _make_sim_scope() -> Any:
    import importlib.util
    import sys

    path = ROOT / "plugins/benchweave/sim_scope/src/benchweave_sim_scope/plugin.py"
    spec = importlib.util.spec_from_file_location("sim_scope_census", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    plugin = module.create_plugin(now_fn=lambda: "2026-09-19T00:00:00Z", monotonic_ns_fn=lambda: 0)
    plugin.plugin_open(_NullServices())
    return plugin


class _NullServices:
    def resolve_content(self, content_id: str) -> bytes:
        return b"{}"

    def retain_evidence(self, key: str, payload: bytes) -> str:
        return f"evidence-{key}"

    def emit_event(self, kind: str, body: dict[str, Any]) -> None:
        pass

    def quota_state(self) -> dict[str, int]:
        return {"dataset_bytes_used": 0, "evidence_entries_used": 0, "events_emitted": 0}

    def register_reading_sink(self, sink: Any) -> None:
        pass


def _plugin_configure(plugin: Any, settings: dict[str, Any]) -> Any:
    from benchweave.host import OperationRequest, OperationStatus, OperationVerb

    request = OperationRequest(
        operation_id="census-op",
        verb=OperationVerb.INVOKE,
        arguments={"action_id": "otdp.oscilloscope.configure/1.0.0", "input": settings},
    )
    return plugin.dispatch(request, deadline_ns=10**12).status is OperationStatus.OK


@pytest.mark.parametrize("field,value,should_refuse", ENVELOPE_MATRIX)
def test_descriptor_envelope_census(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: float, should_refuse: bool
) -> None:
    preset = json.loads(PRESET_FAST.read_bytes())
    preset["settings"]["channels"][0][field] = value
    settings = preset["settings"]
    plugin = _make_sim_scope()
    plugin_ok = _plugin_configure(plugin, settings)
    preset_path = write_document(tmp_path / "census.json", preset)
    lane1_exit = lane1(monkeypatch, preset_path)
    package = copy_package(tmp_path / "pkg")
    mutated = json.loads((package / "ui/presets/fast-survey.json").read_bytes())
    mutated["settings"]["channels"][0][field] = value
    write_document(package / "ui/presets/fast-survey.json", mutated)
    repin_manifest_and_envelope(package)
    lane2_exit = lane2(monkeypatch, package)
    if should_refuse:
        assert not plugin_ok, (field, value)
        assert lane2_exit != 0, (field, value)
        assert lane1_exit == 0, (field, value)
    else:
        assert plugin_ok, (field, value)
        assert lane1_exit == 0 and lane2_exit == 0, (field, value)


# Top-level settings fields carry their own envelope. The plugin-authored
# caps (fix wave R1: 1e6 rate/count ceilings) became class-level corpus
# bounds in OTDP 0.2.0 (issue #64): the catalog input schema — which the
# shipped settings-schema file copies byte-for-byte — now refuses a 1e12
# count in BOTH lanes. Unlike the channel census above there is no lane-1
# residual: the bound lives in the settings-schema bytes, which is exactly
# what lane 1 checks.

TOP_LEVEL_MATRIX = [
    ("sample_count", 10**12, True),
    ("sample_count", 10**6, False),
]


@pytest.mark.parametrize("field,value,should_refuse", TOP_LEVEL_MATRIX)
def test_settings_envelope_census_top_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: int, should_refuse: bool
) -> None:
    preset = json.loads(PRESET_FAST.read_bytes())
    preset["settings"][field] = value
    settings = preset["settings"]
    plugin = _make_sim_scope()
    plugin_ok = _plugin_configure(plugin, settings)
    preset_path = write_document(tmp_path / "census.json", preset)
    lane1_exit = lane1(monkeypatch, preset_path)
    package = copy_package(tmp_path / "pkg")
    mutated = json.loads((package / "ui/presets/fast-survey.json").read_bytes())
    mutated["settings"][field] = value
    write_document(package / "ui/presets/fast-survey.json", mutated)
    repin_manifest_and_envelope(package)
    lane2_exit = lane2(monkeypatch, package)
    if should_refuse:
        assert not plugin_ok, (field, value)
        assert lane2_exit != 0, (field, value)
        # THE FLIP (issue #64): the corpus maximum reached the shipped
        # settings-schema bytes, so lane 1 now refuses too — under 0.1.2 a
        # 1e12-count preset passed lane 1 clean.
        assert lane1_exit != 0, (field, value)
    else:
        assert plugin_ok, (field, value)
        assert lane1_exit == 0 and lane2_exit == 0, (field, value)
