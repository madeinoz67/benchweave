"""SDK UI scaffolding remains optional and operates without device access."""

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def sdk_source(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "packages/sdk/src"))


def run(monkeypatch: pytest.MonkeyPatch, *arguments: str | Path) -> int:
    cli = importlib.import_module("benchweave_sdk.cli")
    exit_code: int = cli.main([*map(str, arguments)])
    return exit_code


def check(monkeypatch: pytest.MonkeyPatch, package: Path, **options: str) -> int:
    arguments: list[str | Path] = [
        "check-ui",
        package / "presentation.json",
        "--descriptor",
        package / "descriptor.json",
        "--resources",
        package,
        "--catalogue",
        package / "binding-catalogue.json",
    ]
    for key, value in options.items():
        arguments.extend(["--" + key, value])
    return run(monkeypatch, *arguments)


def test_optional_ui_preserves_descriptor_and_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plain = tmp_path / "plain"
    ui = tmp_path / "ui"
    run(monkeypatch, "new", plain)
    run(monkeypatch, "new", ui, "--with-ui")
    base = plain / "src/example_plugin"
    package = ui / "src/example_plugin"
    for name in ("descriptor.json", "adapter.py", "protocol.py"):
        assert (base / name).read_bytes() == (package / name).read_bytes()
    assert not (base / "presentation.json").exists()
    assert (package / "ui/manifest.json").is_file()
    check(monkeypatch, package, firmware="1.0.0")
    assert "not admission or approval" in capsys.readouterr().out


def test_ui_scaffold_includes_valid_preview_fixtures_and_conformance_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run(monkeypatch, "new", tmp_path / "ui", "--with-ui")
    project = tmp_path / "ui"
    package = project / "src/example_plugin"
    assert (package / "ui/fixtures/normal.json").is_file()
    assert (package / "ui/fixtures/warning.json").is_file()
    conformance = project / "tests/test_presentation_preview.py"
    assert conformance.is_file()
    assert "MANDATORY_BASELINE_IDS" in conformance.read_text()

    from benchweave_sdk.fixtures import build_preview_model
    from benchweave_sdk.presentation import load_validated_preview_inputs

    candidate = load_validated_preview_inputs(
        package / "presentation.json",
        package / "descriptor.json",
        package,
        package / "binding-catalogue.json",
        firmware=None,
        features=frozenset(),
        panels=frozenset(),
    )
    ids = {scenario.id for scenario in build_preview_model(candidate).scenarios}
    mandatory = {
        "normal",
        "warning",
        "loading",
        "stale",
        "disconnected",
        "critical",
        "trip",
        "recovery",
        "request-rejected",
    }
    assert mandatory <= ids


def test_ui_check_rejects_modified_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run(monkeypatch, "new", tmp_path / "ui", "--with-ui")
    package = tmp_path / "ui/src/example_plugin"
    manifest = package / "ui/manifest.json"
    manifest.write_bytes(manifest.read_bytes() + b"\n")
    assert check(monkeypatch, package) == 1


def test_ui_check_rejects_symlinked_resource(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run(monkeypatch, "new", tmp_path / "ui", "--with-ui")
    package = tmp_path / "ui/src/example_plugin"
    manifest = package / "ui/manifest.json"
    outside = tmp_path / "outside.json"
    outside.write_bytes(manifest.read_bytes())
    manifest.unlink()
    manifest.symlink_to(outside)
    assert check(monkeypatch, package) == 1


def test_ui_check_rejects_resource_root_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run(monkeypatch, "new", tmp_path / "ui", "--with-ui")
    package = tmp_path / "ui/src/example_plugin"
    envelope = package / "presentation.json"
    document = json.loads(envelope.read_bytes())
    document["resource_root"] = "../outside"
    envelope.write_text(json.dumps(document))
    assert check(monkeypatch, package) == 1
