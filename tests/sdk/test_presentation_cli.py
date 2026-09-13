"""SDK UI scaffolding remains optional and operates without device access."""

import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def sdk_source(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "packages/sdk/src"))


def run(monkeypatch, *arguments):
    from benchweave_sdk import cli

    monkeypatch.setattr("sys.argv", ["benchweave-sdk", *map(str, arguments)])
    cli.main()


def check(monkeypatch, package, **options):
    arguments = [
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
    run(monkeypatch, *arguments)


def test_optional_ui_preserves_descriptor_and_adapter(tmp_path, monkeypatch, capsys):
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


def test_ui_check_rejects_modified_manifest(tmp_path, monkeypatch):
    run(monkeypatch, "new", tmp_path / "ui", "--with-ui")
    package = tmp_path / "ui/src/example_plugin"
    manifest = package / "ui/manifest.json"
    manifest.write_bytes(manifest.read_bytes() + b"\n")
    with pytest.raises(SystemExit) as error:
        check(monkeypatch, package)
    assert error.value.code == 1


def test_ui_check_rejects_symlinked_resource(tmp_path, monkeypatch):
    run(monkeypatch, "new", tmp_path / "ui", "--with-ui")
    package = tmp_path / "ui/src/example_plugin"
    manifest = package / "ui/manifest.json"
    outside = tmp_path / "outside.json"
    outside.write_bytes(manifest.read_bytes())
    manifest.unlink()
    manifest.symlink_to(outside)
    with pytest.raises(SystemExit) as error:
        check(monkeypatch, package)
    assert error.value.code == 1


def test_ui_check_rejects_resource_root_escape(tmp_path, monkeypatch):
    run(monkeypatch, "new", tmp_path / "ui", "--with-ui")
    package = tmp_path / "ui/src/example_plugin"
    envelope = package / "presentation.json"
    document = json.loads(envelope.read_bytes())
    document["resource_root"] = "../outside"
    envelope.write_text(json.dumps(document))
    with pytest.raises(SystemExit) as error:
        check(monkeypatch, package)
    assert error.value.code == 1
