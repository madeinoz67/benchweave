"""Wheel-install path defaults fail fast with the knob named, never silently."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchweave.interfaces import app_entry


def test_build_names_the_fixtures_knob_when_lattice_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # In a wheel install _DEFAULT_FIXTURES resolves into the environment's
    # site-packages parent — a path that exists nowhere. build() must refuse
    # with BENCHWEAVE_FIXTURES in the message instead of booting toward a
    # cryptic downstream error.
    monkeypatch.setenv("BENCHWEAVE_DB", str(tmp_path / "state.db"))
    monkeypatch.delenv("BENCHWEAVE_FIXTURES", raising=False)
    monkeypatch.setattr(app_entry, "_DEFAULT_FIXTURES", tmp_path / "absent" / "execution")
    with pytest.raises(RuntimeError, match="BENCHWEAVE_FIXTURES"):
        app_entry.build()


def test_explicit_missing_fixtures_is_also_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BENCHWEAVE_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("BENCHWEAVE_FIXTURES", str(tmp_path / "nowhere"))
    with pytest.raises(RuntimeError, match="nowhere"):
        app_entry.build()
