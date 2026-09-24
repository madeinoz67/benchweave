"""The dev-corpus resolution seam (issue #176 increment 2, design §1b).

The seam is the gateway runtime twin of the checker lane's
``_declared_dev_head`` (``scripts/architecture/_validation_report.py``):
manifest-derived, accept-exactly-the-declared-head, loud on every refusal,
and a view (never a mutation). The controls S-R1..S-R4 of the design
record's pre-committed set pin the four properties the governor reviews:
default-is-today (S-R1), exactly-the-declared-head with self-retirement
(S-R2), packaged impossibility (S-R3), and the no-path-valued-surface
shape (S-R4).
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, get_type_hints

import pytest

import benchweave.vendoring as vendoring
from benchweave.content.store import ContentStore
from benchweave.control import coordinator as coordinator_module
from benchweave.control import documents as documents_module
from benchweave.interfaces.app import create_app
from benchweave.state.store import Store
from benchweave.vendoring import CorpusResolution, declared_dev_family

#: The repository root behind this checkout's ``benchweave`` package (the
#: resolver's own derivation, re-derived here so the test never hardcodes a
#: path).
REPO = Path(vendoring.__file__).resolve().parents[2]


def _standards_tree(tmp_path: Path, entry: dict[str, Any]) -> Path:
    """A minimal standards tree whose manifest declares exactly ``entry``."""
    root = tmp_path / "repo"
    (root / "standards").mkdir(parents=True)
    manifest = {
        "manifest_version": 1,
        "standards": [entry],
    }
    (root / "standards/standards-manifest.json").write_text(json.dumps(manifest))
    return root


def _execution_entry(dev: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "id": "execution",
        "version": "0.1.0",
        "status": "stable",
        "released": "2026-09-16",
        "normative": [
            "standards/execution/0.1.0/procedure.schema.json",
        ],
        **({"dev": dev} if dev is not None else {}),
    }


@pytest.fixture()
def _packaged_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """An empty packaged contracts root (the packaged-first miss)."""
    packaged = tmp_path / "packaged"
    (packaged / "contracts").mkdir(parents=True)
    monkeypatch.setattr(vendoring, "_PACKAGED_ROOT", packaged)
    return packaged


def test_s_r1_default_composition_is_today() -> None:
    """S-R1: the default composition resolves the active family — the
    frozen literals stay the sites' defaults, byte-identical posture, and
    the opt-in channel is keyword-only enum injection. The literal moved
    to 0.2.0 with the promotion sweep."""
    assert vendoring.contract_family("execution/0.2.0") == documents_module._CONTRACTS
    assert vendoring.contract_family("execution/0.2.0") == coordinator_module._CONTRACTS
    parameter = inspect.signature(create_app).parameters["execution_corpus"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is CorpusResolution.ACTIVE
    assert get_type_hints(create_app)["execution_corpus"] is CorpusResolution


def test_s_r1_active_composition_never_invokes_the_dev_resolver(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """S-R1: an ACTIVE composition resolves nothing dev — the resolver is
    not called on the default construction path at all."""

    def _refuse(standard_id: str) -> Path:
        raise AssertionError(
            f"ACTIVE composition must not resolve a dev head ({standard_id})"
        )

    import benchweave.interfaces.app as app_module

    monkeypatch.setattr(vendoring, "declared_dev_family", _refuse)
    # The composition root binds the resolver at import time; both names
    # must refuse so the control cannot pass vacuously.
    monkeypatch.setattr(app_module, "declared_dev_family", _refuse)
    limits: dict[str, int] = {
        "max_json_bytes": 1048576,
        "max_page_size": 1000,
        "max_chunk_bytes": 65536,
        "max_lease_ms": 600000,
        "min_poll_ms": 100,
        "max_admission_ms": 5000,
    }
    store = Store.open(tmp_path / "seam-active.db")
    try:
        app = create_app(
            store=store,
            content=ContentStore(store),
            secret=b"seam-secret",
            limits=limits,
            gateway_id="gw-seam-active",
            fixtures_dir=tmp_path,
            now_iso=lambda: "2026-09-24T00:00:00Z",
            now_epoch=lambda: 1_800_000_000,
        )
        assert app.title == "BenchWeave gateway"
    finally:
        store.close()


def test_s_r2_self_retirement_is_live_truth_on_the_real_tree() -> None:
    """S-R2, post-promotion: the real manifest declares no dev head, so
    a stray DEV_HEAD resolution refuses by name — the seam cannot
    outlive the head, and it never falls back to the active corpus."""
    with pytest.raises(ValueError, match="execution_dev_head_absent:"):
        declared_dev_family("execution")


def test_s_r2_self_retires_when_no_head_declared(
    tmp_path: Path, _packaged_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S-R2: with the dev block removed (the post-promotion shape), any
    stray DEV_HEAD composition refuses — the seam cannot outlive the head."""
    root = _standards_tree(tmp_path, _execution_entry(dev=None))
    monkeypatch.setattr(vendoring, "_REPO_ROOT", root)
    with pytest.raises(ValueError, match="execution_dev_head_absent:"):
        declared_dev_family("execution")


def test_s_r3_packaged_refusal_never_falls_back_to_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S-R3: an unresolvable head directory (the wheel shape — a packaged
    root that exists but does not carry the head, a repo fallback that
    does not either) refuses naming the missed path; the active family is
    never silently substituted."""
    packaged = tmp_path / "packaged"
    (packaged / "contracts").mkdir(parents=True)
    monkeypatch.setattr(vendoring, "_PACKAGED_ROOT", packaged)
    root = _standards_tree(
        tmp_path,
        _execution_entry(
            dev={
                "version": "0.2.0-dev",
                "opened": "2026-09-24",
                "normative": ["standards/execution/0.2.0-dev/procedure.schema.json"],
            }
        ),
    )
    monkeypatch.setattr(vendoring, "_REPO_ROOT", root)
    with pytest.raises(ValueError, match="dev_head_unresolvable:") as refused:
        declared_dev_family("execution")
    message = str(refused.value)
    assert "standards/execution/0.2.0-dev" in message
    # Never-a-fallback, stated in the refusal itself: the active tree is
    # not in the resolved path, and the message does not offer it.
    assert "execution/0.1.0" not in message


def test_loader_dev_block_refusals_are_inherited_verbatim(
    tmp_path: Path, _packaged_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The loader's own dev-block shape refusals are the seam's refusals —
    same words on both surfaces (the checker-lane ruling)."""
    cases = [
        (
            "dev_version_invalid:",
            _execution_entry(
                dev={
                    "version": "0.2.0",
                    "opened": "2026-09-24",
                    "normative": ["standards/execution/0.2.0-dev/procedure.schema.json"],
                }
            ),
        ),
        (
            "dev_head_stale:",
            _execution_entry(
                dev={
                    "version": "0.0.9-dev",
                    "opened": "2026-09-24",
                    "normative": ["standards/execution/0.0.9-dev/procedure.schema.json"],
                }
            ),
        ),
        (
            "dev_block_invalid:",
            _execution_entry(dev={"version": "0.2.0-dev"}),
        ),
    ]
    for expected, entry in cases:
        root = _standards_tree(tmp_path / expected.split(":")[0], entry)
        monkeypatch.setattr(vendoring, "_REPO_ROOT", root)
        with pytest.raises(ValueError, match=expected):
            declared_dev_family("execution")


def test_manifest_absent_refuses_with_the_lane_word(
    tmp_path: Path, _packaged_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A manifest the loader cannot find (a wheel-installed runtime has no
    repository manifest) refuses — it never degrades to anything."""
    empty = tmp_path / "empty-repo"
    (empty / "standards").mkdir(parents=True)
    monkeypatch.setattr(vendoring, "_REPO_ROOT", empty)
    with pytest.raises(ValueError, match="execution_manifest_absent:"):
        declared_dev_family("execution")


def test_s_r1_dev_head_is_called_and_threaded_by_create_app(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """sF1 (fold wave): the DEV_HEAD branch of ``create_app`` is
    discriminating — the resolver is CALLED at composition and its
    directory is THREADED into the run factory. Deleting the branch body
    (binding ``contracts`` straight to ``_CONTRACTS``) makes this fail:
    the sentinel is never invoked and the factory receives the frozen
    literal instead."""
    import benchweave.interfaces.app as app_module

    sentinel = tmp_path / "sentinel-dev-head"
    sentinel.mkdir()
    resolved: list[str] = []

    def _sentinel_resolver(standard_id: str) -> Path:
        resolved.append(standard_id)
        return sentinel

    threaded: list[Any] = []
    original_factory = app_module._build_run_factory

    def _spy_factory(*args: Any, **kwargs: Any) -> Any:
        threaded.append(kwargs.get("contracts"))
        return original_factory(*args, **kwargs)

    monkeypatch.setattr(app_module, "declared_dev_family", _sentinel_resolver)
    monkeypatch.setattr(app_module, "_build_run_factory", _spy_factory)
    limits: dict[str, int] = {
        "max_json_bytes": 1048576,
        "max_page_size": 1000,
        "max_chunk_bytes": 65536,
        "max_lease_ms": 600000,
        "min_poll_ms": 100,
        "max_admission_ms": 5000,
    }
    store = Store.open(tmp_path / "seam-dev.db")
    try:
        app = create_app(
            store=store,
            content=ContentStore(store),
            secret=b"seam-secret",
            limits=limits,
            gateway_id="gw-seam-dev",
            fixtures_dir=tmp_path,
            now_iso=lambda: "2026-09-24T00:00:00Z",
            now_epoch=lambda: 1_800_000_000,
            execution_corpus=CorpusResolution.DEV_HEAD,
        )
        assert app.title == "BenchWeave gateway"
    finally:
        store.close()
    assert resolved == ["execution"], (
        "the DEV_HEAD branch must resolve the declared head exactly once at composition"
    )
    assert threaded == [sentinel], (
        "the resolved directory must thread into the run build factory unchanged"
    )


def test_s_r4_no_path_valued_surface() -> None:
    """S-R4: the seam's public surface exposes no path-valued corpus
    parameter — the enum is the only opt-in (a shape assertion over the
    factory signature; mypy-visible)."""
    signature = inspect.signature(create_app)
    corpus_shaped = [
        name
        for name, parameter in signature.parameters.items()
        if "corpus" in name or "contracts" in name
    ]
    assert corpus_shaped == ["execution_corpus"]
    hints = get_type_hints(create_app)
    assert hints["execution_corpus"] is CorpusResolution
    resolver = inspect.signature(declared_dev_family)
    assert list(resolver.parameters) == ["standard_id"]
    assert get_type_hints(declared_dev_family)["standard_id"] is str
    assert get_type_hints(declared_dev_family)["return"] is Path
