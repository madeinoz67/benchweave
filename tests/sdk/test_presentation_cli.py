"""SDK UI scaffolding remains optional and operates without device access."""

import errno
import importlib
import json
import os
import subprocess
import sys
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


def test_scaffold_rejects_shadowing_package_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("benchweave_sdk", "benchweave", "os"):
        assert run(monkeypatch, "new", tmp_path / f"p-{name}", "--package", name) == 1


def test_create_ui_resources_is_atomic_on_unusable_descriptors(tmp_path: Path) -> None:
    presentation = importlib.import_module("benchweave_sdk.presentation")
    scaffold = importlib.import_module("benchweave_sdk.scaffold")

    empty = tmp_path / "empty"
    scaffold.create_project(empty, "example_plugin")
    descriptor_path = empty / "src/example_plugin/descriptor.json"
    document = json.loads(descriptor_path.read_bytes())
    document["parameters"] = []
    descriptor_path.write_text(json.dumps(document), encoding="utf-8")
    package = empty / "src/example_plugin"
    with pytest.raises(ValueError, match="at least one readable"):
        presentation.create_ui_resources(empty, "example_plugin")
    assert not (package / "presentation.json").exists()
    assert not (package / "ui").exists()

    unknown = tmp_path / "unknown"
    scaffold.create_project(unknown, "example_plugin")
    descriptor_path = unknown / "src/example_plugin/descriptor.json"
    document = json.loads(descriptor_path.read_bytes())
    document["parameters"][0]["type"] = "float8"
    descriptor_path.write_text(json.dumps(document), encoding="utf-8")
    package = unknown / "src/example_plugin"
    with pytest.raises(ValueError, match="preview_unsupported_parameter_type"):
        presentation.create_ui_resources(unknown, "example_plugin")
    assert not (package / "presentation.json").exists()


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
    assert "BASELINE_IDS" in conformance.read_text()

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


def test_scaffold_hint_pair_validates_identically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Metric 1's fourth pair: the scaffold's own hinted plot vs its unhinted
    twin, both feature conditions.

    Since the scaffold emits a receipt-time axis and one time-series plot with
    a muted-channel hint, the author-side step is exactly hint authoring:
    strip or keep the scaffold's channel_hints (re-pinning the manifest
    digest). check-ui must accept both members identically (P1/P2) — and the
    scaffold must declare the ACTIVE contract version or this fails before
    hints are even considered.
    """
    hashlib = importlib.import_module("hashlib")
    presentation = importlib.import_module("benchweave_sdk.presentation")
    scaffold = importlib.import_module("benchweave_sdk.scaffold")

    def authored(hints: list[dict[str, object]] | None) -> Path:
        project = tmp_path / ("ui-hinted" if hints is not None else "ui-plain")
        scaffold.create_project(project, "example_plugin")
        presentation.create_ui_resources(project, "example_plugin")
        package = project / "src/example_plugin"
        if hints is None:
            manifest_path = package / "ui/manifest.json"
            manifest = json.loads(manifest_path.read_bytes())
            manifest["pages"][0]["plots"][0].pop("channel_hints", None)
            manifest_raw = json.dumps(manifest, indent=2) + "\n"
            manifest_path.write_text(manifest_raw, encoding="utf-8")
            envelope_path = package / "presentation.json"
            envelope = json.loads(envelope_path.read_bytes())
            envelope["manifest"]["sha256"] = hashlib.sha256(manifest_raw.encode()).hexdigest()
            envelope_path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
        return package

    plain = authored(None)
    hinted = authored([{"variable_id": "value", "color_role": "muted"}])
    assert check(monkeypatch, plain, firmware="1.0.0") == 0
    # No --feature flag is the empty supported-feature host; one flag is the
    # feature-declaring host. Both must accept the hinted twin identically.
    assert check(monkeypatch, hinted, firmware="1.0.0") == 0
    assert check(monkeypatch, hinted, firmware="1.0.0", feature="legend/1.0.0") == 0


def _numeric_target_ids(catalogue_path: Path) -> list[str]:
    catalogue = json.loads(catalogue_path.read_bytes())
    return [
        str(row["id"])
        for row in catalogue["targets"]
        if next(
            variable
            for variable in row["variables"]
            if variable.get("axis_role") != "receipt_time"
        )["type"]
        in ("number", "integer")
    ]


def _scaffold_with_leading_parameter(
    tmp_path: Path, parameter_type: str, *, only: bool = False
) -> Path:
    """Scaffold UI resources over a descriptor whose FIRST readable parameter
    is non-numeric (bool or string) — the shape the refute lane's HIGH shipped
    on. ``only=True`` rewrites the whole parameter list non-numeric."""
    presentation = importlib.import_module("benchweave_sdk.presentation")
    scaffold = importlib.import_module("benchweave_sdk.scaffold")
    project = tmp_path / f"ui-{parameter_type}-first"
    scaffold.create_project(project, "example_plugin")
    descriptor_path = project / "src/example_plugin/descriptor.json"
    descriptor = json.loads(descriptor_path.read_bytes())
    leading = dict(descriptor["parameters"][0])
    leading.update(
        {
            "name": "ready",
            "type": parameter_type,
            "description": f"Synthetic {parameter_type} leading parameter",
        }
    )
    leading["binding"] = {"kind": "adapter", "key": "ready"}
    if parameter_type == "string":
        # The descriptor schema requires string_constraints on string
        # parameters and no numeric unit rides them.
        leading.pop("unit", None)
        leading["string_constraints"] = {"min_length": 0, "max_length": 40}
    if only:
        descriptor["parameters"] = [leading]
    else:
        descriptor["parameters"].insert(0, leading)
    descriptor_path.write_text(json.dumps(descriptor, indent=2) + "\n", encoding="utf-8")
    presentation.create_ui_resources(project, "example_plugin")
    return project / "src/example_plugin"


@pytest.mark.parametrize("parameter_type", ["bool", "string"])
def test_scaffold_plot_attaches_to_the_first_numeric_observation_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, parameter_type: str
) -> None:
    """Refute HIGH (reproduced): a non-numeric-first descriptor must still get
    a working plot example.

    The plot example binds the first NUMERIC observation target — the same
    number/integer test the presentation validator applies to plot axes — not
    targets[0], because _ui_targets admits bool/string parameters while
    _plot_findings refuses non-numeric axes. Pinning the example to targets[0]
    made the scaffold emit a plot check-ui rejects (invalid_plot) and
    load_validated_preview_inputs refuse the whole preview.
    """
    fixtures = importlib.import_module("benchweave_sdk.fixtures")
    presentation = importlib.import_module("benchweave_sdk.presentation")
    package = _scaffold_with_leading_parameter(tmp_path, parameter_type)

    assert check(monkeypatch, package, firmware="1.0.0") == 0

    candidate = presentation.load_validated_preview_inputs(
        package / "presentation.json",
        package / "descriptor.json",
        package,
        package / "binding-catalogue.json",
        firmware="1.0.0",
        features=frozenset(),
        panels=frozenset(),
    )
    views = fixtures.build_preview_model(candidate).plot_views
    assert views, "the scaffold plot example must project for a numeric-capable descriptor"
    assert views[0].binding_id == _numeric_target_ids(package / "binding-catalogue.json")[0]


def test_scaffold_without_numeric_targets_skips_the_plot_example(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No numeric observation target => no example plot: a disclosed
    degradation, never a plot check-ui rejects."""
    fixtures = importlib.import_module("benchweave_sdk.fixtures")
    presentation = importlib.import_module("benchweave_sdk.presentation")
    package = _scaffold_with_leading_parameter(tmp_path, "bool", only=True)

    assert check(monkeypatch, package, firmware="1.0.0") == 0

    manifest = json.loads((package / "ui/manifest.json").read_bytes())
    assert "plots" not in manifest["pages"][0]
    candidate = presentation.load_validated_preview_inputs(
        package / "presentation.json",
        package / "descriptor.json",
        package,
        package / "binding-catalogue.json",
        firmware="1.0.0",
        features=frozenset(),
        panels=frozenset(),
    )
    assert fixtures.build_preview_model(candidate).plot_views == ()


def test_generated_conformance_test_compiles_and_runs(tmp_path: Path) -> None:
    """The generator's OUTPUT executes, not just gets inspected.

    CI's sdk_smoke installs the starter and RUNS its generated conformance
    test; a template that emits a syntactically invalid assert (the trailing
    comma after the message) is pytest exit 2 at collection there while every
    local gate stayed green — none executed the file. Both template variants
    (numeric descriptor -> plot assertion; all-non-numeric -> empty
    assertion) are compiled here, then executed in a subprocess exactly the
    way CI runs them, so this class stays caught locally.
    """
    presentation = importlib.import_module("benchweave_sdk.presentation")
    scaffold = importlib.import_module("benchweave_sdk.scaffold")
    sdk_source = Path(__file__).resolve().parents[2] / "packages/sdk/src"

    with_plot_project = tmp_path / "with-plot"
    scaffold.create_project(with_plot_project, "example_plugin")
    presentation.create_ui_resources(with_plot_project, "example_plugin")
    no_plot_package = _scaffold_with_leading_parameter(tmp_path / "generated", "bool", only=True)
    no_plot_project = no_plot_package.parents[1]

    for name, project in (("with-plot", with_plot_project), ("no-plot", no_plot_project)):
        conformance = project / "tests" / "test_presentation_preview.py"
        source = conformance.read_text()
        compile(source, str(conformance), "exec")
        environment = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join([str(sdk_source), str(project / "src")]),
        }
        executed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(conformance)],
            capture_output=True,
            text=True,
            env=environment,
            check=False,
        )
        assert executed.returncode == 0, f"{name}: {executed.stdout}{executed.stderr}"


def test_generated_conformance_test_compiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scaffold's generated conformance test must be importable Python.

    The smoke job executes it against the installed SDK; a template syntax
    error leaves every local gate green (they validate scaffold output
    without executing it) while CI goes red. Compiling both template arms —
    plot-present and plot-absent — pins the generator's output as code.
    """
    for case, only in (("with-plot", False), ("no-plot", True)):
        package = _scaffold_with_leading_parameter(tmp_path / case, "bool", only=only)
        generated = package.parent.parent / "tests" / "test_presentation_preview.py"
        compile(generated.read_text(encoding="utf-8"), str(generated), "exec")


def test_new_with_ui_succeeds_under_symlinked_ancestor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    assert run(monkeypatch, "new", link / "proj", "--with-ui") == 0
    package = real / "proj/src/example_plugin"
    for name in (
        "presentation.json",
        "binding-catalogue.json",
        "ui/manifest.json",
        "ui/fixtures/normal.json",
    ):
        assert (package / name).is_file()
    assert (real / "proj/UI-GUIDE.md").is_file()
    assert (real / "proj/tests/test_presentation_preview.py").is_file()

    # SRF-1 control: the same package scaffolded through a canonical path must
    # be byte-identical — the fix changes where writes happen, never what.
    control = tmp_path / "control"
    assert run(monkeypatch, "new", control, "--with-ui") == 0
    generated = sorted(
        path.relative_to(real / "proj") for path in (real / "proj").rglob("*") if path.is_file()
    )
    assert generated == sorted(
        path.relative_to(control) for path in control.rglob("*") if path.is_file()
    )
    for relative in generated:
        assert (real / "proj" / relative).read_bytes() == (control / relative).read_bytes()


def test_check_ui_refuses_symlinked_ancestor_with_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run(monkeypatch, "new", tmp_path / "real", "--with-ui")
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "real")
    assert check(monkeypatch, link / "src/example_plugin") == 1
    assert "path_symlink_component:" in capsys.readouterr().err


def test_read_file_propagates_genuine_not_directory(tmp_path: Path) -> None:
    presentation = importlib.import_module("benchweave_sdk.presentation")
    blocker = tmp_path / "blocker"
    blocker.write_bytes(b"regular file\n")
    with pytest.raises(OSError) as details:
        presentation.read_file(blocker / "descriptor.json")
    assert details.value.errno == errno.ENOTDIR
    assert "path_symlink_component" not in str(details.value)
