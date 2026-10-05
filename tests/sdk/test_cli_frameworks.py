"""SDK CLI framework boundaries remain stable and automation-safe."""

from io import StringIO
from pathlib import Path

import pytest
from click.testing import CliRunner


@pytest.fixture(autouse=True)
def sdk_source(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "packages/sdk/src"))


def test_sdk_exposes_click_command_group() -> None:
    from benchweave_sdk.cli import cli

    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    for command in ("new", "check", "inventory", "check-ui", "check-preset", "preview-ui"):
        assert command in result.output


def test_click_usage_and_domain_exit_codes(tmp_path: Path) -> None:
    from benchweave_sdk.cli import cli

    runner = CliRunner()
    assert runner.invoke(cli, ["check-ui"]).exit_code == 2
    result = runner.invoke(cli, ["check", str(tmp_path / "missing.json")])
    assert result.exit_code == 1


def test_findings_render_author_strings_literally() -> None:
    from benchweave_sdk.console import ConsoleOutput

    stream = StringIO()
    output = ConsoleOutput(file=stream, terminal=True)
    output.findings([("[red]evil[/red]", "presentation.json", "[bold]spoofed[/bold]")])
    rendered = stream.getvalue()
    assert "[red]evil[/red]" in rendered
    assert "[bold]spoofed[/bold]" in rendered


# v0.7.0 reconciliation: the SDK deleted the in-package preview surfaces these
# two arms pinned (ConsoleOutput.preview_ready and the textual
# preview_tui.PreviewStatusApp — the banner text and textual are gone from the
# SDK tree entirely). The preview moved to the [server]-extra host
# (benchweave_sdk_server), whose extras-missing refusal and serve behavior the
# SDK's own suite and wheel-install smoke pin; the gateway-provable remainder
# of the preview surface (preview-ui listed in --help) stays pinned by the
# command-group test above.
