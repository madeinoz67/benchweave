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


def test_l1a_smuggled_averaging_key_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pinned refusal of Reading 1: model averaging is structurally
    unrepresentable in preset settings under the closed action schemas."""
    preset = json.loads(PRESET_PAIR.read_bytes())
    preset["settings"]["averaging_count"] = 8
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


def test_l2a_key_outside_action_schema_refused_by_canonical_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shipped-artifact twin of test_preset_cannot_bypass_canonical_action_schema:
    even a permissive settings file cannot smuggle averaging past the corpus."""
    package = copy_package(tmp_path)
    schema_path = package / "ui" / "settings" / "oscilloscope-configure.schema.json"
    schema = json.loads(schema_path.read_bytes())
    schema.pop("required", None)
    schema["additionalProperties"] = True
    write_document(schema_path, schema)
    preset_path = package / "ui" / "presets" / "low-noise-pair.json"
    preset = json.loads(preset_path.read_bytes())
    preset["settings"]["averaging_count"] = 8
    preset["settings_schema"]["sha256"] = digest(schema_path.read_bytes())
    write_document(preset_path, preset)
    repin_manifest_and_envelope(package)
    assert lane2(monkeypatch, package) != 0
    assert "invalid_settings" in findings(ui_report(package))


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
    validation = importlib.import_module("benchweave_sdk.validation")
    catalog = validation.contract_documents()["otdp/0.1.1/device-profile-catalog.json"]
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
