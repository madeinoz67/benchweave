"""The public docs site never stages or ships dev-stage bytes (review row 1)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_assembler() -> Any:
    path = ROOT / "scripts" / "assemble_docs_site.py"
    spec = importlib.util.spec_from_file_location("assemble_docs_site", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _headed_repo(tmp_path: Path) -> Path:
    """A minimal REPO-shaped tree: active otdp prose+schema, plus an open
    dev head carrying copies of both (the dev-open shape — schemas ship
    beside the prose, which is exactly why the skip must cover the resource
    copy and not just the page staging)."""
    repo = tmp_path / "repo"
    standards = repo / "standards"
    active = standards / "otdp" / "0.2.0"
    active.mkdir(parents=True)
    (active / "otdp-specification.md").write_text("# spec\n", encoding="utf-8")
    (active / "otdp-measurement.schema.json").write_text("{}\n", encoding="utf-8")
    head = standards / "otdp" / "0.2.1-dev"
    head.mkdir(parents=True)
    (head / "otdp-specification.md").write_text("# spec staged copy\n", encoding="utf-8")
    (head / "otdp-measurement.schema.json").write_text("{}\n", encoding="utf-8")
    return repo


def test_dev_head_bytes_never_reach_the_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assembler = _load_assembler()
    monkeypatch.setattr(assembler, "REPO", _headed_repo(tmp_path))

    manifest = assembler.standards_manifest()
    for source, staged in manifest.items():
        assert "-dev/" not in f"{source}->{staged}", "a dev page staged into the site"
    assert any("otdp/0.2.0" in source for source in manifest), "active prose must still stage"

    docs_root = tmp_path / "site"
    (docs_root / "standards").mkdir(parents=True)
    assembler.copy_standards_resources(docs_root)
    staged_files = [
        path.relative_to(docs_root / "standards").as_posix()
        for path in (docs_root / "standards").rglob("*")
        if path.is_file()
    ]
    assert not any("-dev/" in name for name in staged_files), staged_files
    assert "otdp/0.2.0/otdp-measurement.schema.json" in staged_files
