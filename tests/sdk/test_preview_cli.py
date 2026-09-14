"""The preview-ui CLI validates first and reports a deterministic local endpoint."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

SDK = Path(__file__).resolve().parents[2] / "packages/sdk/src"
sys.path.insert(0, str(SDK))


class FakeAddress:
    url = "http://127.0.0.1:49152"


class FakeServer:
    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.args = args
        self.kwargs = kwargs
        self.address = FakeAddress()
        self.started = False
        self.waited = False

    def start(self) -> FakeAddress:
        self.started = True
        return self.address

    def wait(self) -> None:
        self.waited = True

    def shutdown(self) -> None:
        return


def test_preview_ui_no_open_reports_ready_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = importlib.import_module("benchweave_sdk.cli")
    presentation = importlib.import_module("benchweave_sdk.presentation")
    fixtures = importlib.import_module("benchweave_sdk.fixtures")
    preview_server = importlib.import_module("benchweave_sdk.preview_server")
    server = FakeServer()
    monkeypatch.setattr(presentation, "load_validated_preview_inputs", lambda *a, **k: object())
    monkeypatch.setattr(fixtures, "build_preview_model", lambda candidate: object())
    monkeypatch.setattr(preview_server, "PreviewServer", lambda *a, **k: server)
    monkeypatch.setattr(preview_server, "bundled_assets", lambda: tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "benchweave-sdk",
            "preview-ui",
            "presentation.json",
            "--descriptor",
            "descriptor.json",
            "--resources",
            ".",
            "--catalogue",
            "binding-catalogue.json",
            "--no-open",
        ],
    )

    cli.main()

    output = capsys.readouterr().out
    assert "SIMULATED PRESENTATION DATA" in output
    assert server.address.url in output
    assert server.started and server.waited


def test_preview_ui_rejects_non_loopback_without_acknowledgement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = importlib.import_module("benchweave_sdk.cli")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "benchweave-sdk",
            "preview-ui",
            "presentation.json",
            "--descriptor",
            "descriptor.json",
            "--resources",
            ".",
            "--catalogue",
            "binding-catalogue.json",
            "--host",
            "192.0.2.10",
            "--no-open",
        ],
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 1
