"""Vendored-asset resolution is packaged-first with a repository fallback."""

from pathlib import Path

import pytest

from benchweave import vendoring

ROOT = Path(__file__).resolve().parents[2]


def _fake_roots(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    """Point both resolution roots into tmp; neither tree exists yet."""
    packaged = tmp_path / "_vendored"
    repo = tmp_path / "checkout"
    monkeypatch.setattr(vendoring, "_PACKAGED_ROOT", packaged)
    monkeypatch.setattr(vendoring, "_REPO_ROOT", repo)
    return packaged, repo


def test_contract_family_prefers_packaged_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    packaged, _repo = _fake_roots(monkeypatch, tmp_path)
    family = packaged / "contracts" / "interface" / "0.1.0"
    family.mkdir(parents=True)
    assert vendoring.contract_family("interface/0.1.0") == family


def test_contract_family_falls_back_to_repo_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _packaged, repo = _fake_roots(monkeypatch, tmp_path)
    expected = repo / "standards" / "interface" / "0.1.0"
    expected.mkdir(parents=True)
    assert vendoring.contract_family("interface/0.1.0") == expected


def test_contract_family_ignores_a_packaged_non_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only a real packaged directory wins; a stray file never masks the repo."""
    packaged, repo = _fake_roots(monkeypatch, tmp_path)
    (packaged / "contracts").mkdir(parents=True)
    (packaged / "contracts" / "interface").write_text("not a tree", encoding="utf-8")
    assert vendoring.contract_family("interface") == repo / "standards" / "interface"


def test_contract_family_missing_everywhere_still_names_the_repo_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The module defines no error contract: with neither tree present it
    still returns the deterministic repository-layout path, and the caller
    that opens it raises its own missing-asset diagnostic."""
    _packaged, repo = _fake_roots(monkeypatch, tmp_path)
    resolved = vendoring.contract_family("ghost/9.9.9")
    assert resolved == repo / "standards" / "ghost" / "9.9.9"
    assert not resolved.exists()


def test_sim_plugins_root_prefers_packaged_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    packaged, _repo = _fake_roots(monkeypatch, tmp_path)
    plugins = packaged / "plugins" / "benchweave"
    plugins.mkdir(parents=True)
    assert vendoring.sim_plugins_root() == plugins


def test_sim_plugins_root_falls_back_to_repo_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _packaged, repo = _fake_roots(monkeypatch, tmp_path)
    assert vendoring.sim_plugins_root() == repo / "plugins" / "benchweave"


def test_dev_checkout_resolves_into_the_real_repo_trees() -> None:
    """In this checkout (no ``_vendored`` ships in ``src/``) both helpers
    resolve to existing repo-root trees the suites also pin."""
    if (Path(vendoring.__file__).resolve().parent / "_vendored").is_dir():
        pytest.skip("a local _vendored tree shadows the repo layout")
    family = vendoring.contract_family("interface/0.1.0")
    assert family == ROOT / "standards" / "interface" / "0.1.0"
    assert family.is_dir()
    plugins = vendoring.sim_plugins_root()
    assert plugins == ROOT / "plugins" / "benchweave"
    assert plugins.is_dir()
