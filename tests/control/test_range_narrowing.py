"""VR-19: a range change never alters a run in progress (issue #219, E1).

The pre-committed acceptance rule E1 has TWO halves and either half failing
kills:

1. **Immutability of the stored record.** A fixture range narrowing happens
   MID-RUN (inside the body's first dispatch); the run's stored
   ``devices_pinned`` event keeps the classification it was recorded with,
   byte-unchanged, across every later policy motion — stored run records are
   recorded facts, never re-derived from a policy that moved afterwards.
2. **The NEXT admission classifies under the NEW range.** After the
   narrowing, a fresh ``admit_documents`` of the same pin refuses (or
   classifies non-conforming behind an acknowledgement) under the narrowed
   range — no stale classification survives a policy edit.

The mechanism under test in half 2 is the classification cache's freshness:
it must key on the corpus state the classification reads, not on the
(corpus path, pin) pair alone, or the second admission serves the
pre-narrowing verdict.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from test_documents_perpin import (
    CORPUS,
    _admit,
    _controller_document,
    _psu_document,
)
from test_run_pins import _plugins

import benchweave.control.documents as documents_module
from benchweave.control.clocking import TestClock
from benchweave.control.coordinator import RunCoordinator
from benchweave.control.documents import AdmissionRejected
from benchweave.host.plugin import DevicePlugin
from benchweave.host.types import OperationRequest, OperationResult
from benchweave.state.store import Store


def _set_otdp_range(corpus: Path, value: str) -> None:
    """Rewrite the fixture policy block's otdp range (a working-tree edit)."""
    manifest = json.loads((corpus / "standards-manifest.json").read_text())
    manifest["dependency_policy"]["standards"]["otdp"]["range"] = value
    (corpus / "standards-manifest.json").write_text(json.dumps(manifest, indent=1))


class _NarrowingPlugin:
    """A ``DevicePlugin`` wrapper firing a hook before its first dispatch.

    The hook is where the fixture range narrows: inside the run's monitored
    body, so the narrowing is literally mid-run (VR-19) rather than between
    two calls the run never observes.
    """

    def __init__(self, inner: DevicePlugin, hook: Callable[[], None]) -> None:
        self._inner = inner
        self._hook = hook
        self._fired = False

    @property
    def simulation(self) -> Any:
        return self._inner.simulation

    def plugin_open(self, services: Any) -> None:
        self._inner.plugin_open(services)

    def plugin_close(self) -> None:
        self._inner.plugin_close()

    def dispatch(self, request: OperationRequest, *, deadline_ns: int) -> OperationResult:
        if not self._fired:
            self._fired = True
            self._hook()
        return self._inner.dispatch(request, deadline_ns=deadline_ns)


def test_e1_narrowing_mid_run_keeps_the_record_and_reclassifies_the_next_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E1, both halves (the pre-committed kill directions)."""
    corpus = tmp_path / "e1-corpus"
    shutil.copytree(CORPUS, corpus)
    monkeypatch.setattr(documents_module, "_otdp_corpus", lambda: corpus)

    # The wide range's seed: a 0.2.0-pinned psu (retained, in range) and the
    # 0.2.2-pinned controller both classify conforming on admission.
    psu = _psu_document()
    psu["otdp_version"] = "0.2.0"
    controller = _controller_document()
    assert controller["otdp_version"] == "0.2.2"
    docs = _admit(tmp_path, {"psu": psu, "controller": controller})
    assert docs.pins["psu"].conformance == "conforming"
    assert docs.pins["controller"].conformance == "conforming"

    # Run with the range narrowing MID-RUN: the psu's first dispatch inside
    # the monitored body flips the fixture range to >=0.2.2,<0.3.0, so the
    # stored record was written before the policy moved and must not move
    # with it.
    clock = TestClock()
    store = Store.open(tmp_path / "state.db")
    plugins = _plugins(clock)
    plugins["psu"] = _NarrowingPlugin(
        plugins["psu"], lambda: _set_otdp_range(corpus, ">=0.2.2,<0.3.0")
    )
    coordinator = RunCoordinator(store, plugins, clock, clock, docs)
    record = coordinator.start_run("run-e1", "principal-a")
    assert record["outcome"] == "passed", record

    # Half 1, first read: the stored event carries the classification it was
    # recorded with, even though the policy no longer says it.
    events_after = store.read_events("run:run-e1")
    assert events_after, "run stream must be non-empty"
    first = events_after[0]
    assert first.get("kind") == "devices_pinned", first
    assert first["devices"]["psu"] == {
        "otdp_version": "0.2.0",
        "conformance": "conforming",
    }, first["devices"]["psu"]

    # Half 1, the byte-unchanged arm: a FURTHER policy motion must not move
    # one byte of the stored record. (The edit changes the file's bytes —
    # the first narrowing already happened mid-run — so a re-deriving read
    # would produce different bytes here.)
    snapshot = json.dumps(events_after, sort_keys=True, separators=(",", ":"))
    _set_otdp_range(corpus, ">=0.2.1,<0.3.0")
    events_again = store.read_events("run:run-e1")
    assert json.dumps(events_again, sort_keys=True, separators=(",", ":")) == snapshot, (
        "the stored run record changed under a policy edit — stored "
        "classifications are recorded facts (VR-19 half 1)"
    )

    # Half 2: the NEXT admission classifies under the NEW (narrowed) range.
    # 0.2.0 is retained but below the new floor: non-conforming, which loads
    # only behind a recorded per-device acknowledgement — without one,
    # admission refuses. RED before the cache keys on corpus state: the
    # first admission's conforming verdict is served stale and this raises
    # nothing.
    psu_again = _psu_document()
    psu_again["otdp_version"] = "0.2.0"
    with pytest.raises(AdmissionRejected, match=r"^operator_ack_required:"):
        _admit(tmp_path, {"psu": psu_again, "controller": controller})

    # Half 2, the positive arm: with the acknowledgement recorded, the same
    # pin ADMITS under the new range and the admission record shows the new
    # class — proof the second classification ran against the narrowed
    # policy rather than the cached wide one.
    admitted = _admit(
        tmp_path,
        {"psu": psu_again, "controller": controller},
        operator_acknowledgements={"psu": "0.2.0"},
    )
    assert admitted.pins["psu"].conformance == "non-conforming"
    assert admitted.pins["psu"].acknowledgement == {
        "otdp_version": "0.2.0",
        "recorded_at": None,
    }
    # The in-range device is untouched by the narrowing: per-pin, per-range.
    assert admitted.pins["controller"].conformance == "conforming"
    assert admitted.pins["controller"].acknowledgement is None


# --- fold LOW-1: the corpus-state token follows the loader's absence semantics ----


def _boundary_corpus(tmp_path: Path, name: str, *, drop: tuple[str, ...]) -> Path:
    corpus = tmp_path / name
    shutil.copytree(CORPUS, corpus)
    for relative in drop:
        (corpus / relative).unlink()
    return corpus


@pytest.mark.parametrize(
    ("drop", "pin", "expected"),
    [
        # Both manifests present: the seed classification (served /
        # non-conforming / unknown-dev — no head is declared on this tree).
        ((), "0.2.0", "conforming"),
        ((), "0.1.2", "non-conforming"),
        ((), "0.3.0-dev", "non-conforming-unknown"),
        # corpus-manifest ABSENT: the loader's own semantics are retained=()
        # (every semver pin reads version_unknown, never carried); the dev
        # label still consults the manifest's (absent) head. The token must
        # not turn this state into a crash the loader never raises.
        (("corpus-manifest.json",), "0.2.0", "non-conforming-unknown"),
        (("corpus-manifest.json",), "0.1.2", "non-conforming-unknown"),
        (("corpus-manifest.json",), "0.3.0-dev", "non-conforming-unknown"),
    ],
    ids=[
        "both-served",
        "both-out-of-range",
        "both-dev",
        "no-corpus-manifest-in-range",
        "no-corpus-manifest-out-of-range",
        "no-corpus-manifest-dev",
    ],
)
def test_the_token_follows_the_loaders_absence_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drop: tuple[str, ...],
    pin: str,
    expected: str,
) -> None:
    """Fold LOW-1 (#219 refute wave): with only the corpus manifest
    missing, ``_corpus_state_token`` raised a raw FileNotFoundError while
    the loader it feeds treats that absence as ``retained == ()`` — a
    typed never-carried refusal, not a crash. The token follows the
    loader now; a missing STANDARDS manifest keeps raising exactly like
    the loader's own file read (the both-absent arms live below)."""
    from benchweave.control.documents import classify_descriptor_pin

    corpus = _boundary_corpus(tmp_path, "boundary", drop=drop)
    monkeypatch.setattr(documents_module, "_otdp_corpus", lambda: corpus)
    record = classify_descriptor_pin(pin)
    if expected == "conforming":
        assert record.conformance == "conforming"
        assert record.status == "served"
    elif expected == "non-conforming":
        assert record.conformance == "non-conforming"
        assert str(record.note).startswith("standard_nonconforming:")
    else:
        assert record.conformance == "non-conforming"
        assert str(record.note).startswith("version_unknown:"), str(record.note)


@pytest.mark.parametrize(
    "pin",
    ["0.2.0", "0.1.2"],
    ids=["in-range", "out-of-range"],
)
def test_a_missing_standards_manifest_raises_like_the_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pin: str,
) -> None:
    """The other boundary half: without the standards manifest the policy
    loader itself dies on its own file read — the token must raise the
    SAME exception (it does, at its own read), never something broader."""
    from benchweave.control.documents import classify_descriptor_pin

    corpus = _boundary_corpus(
        tmp_path, "no-standards", drop=("standards-manifest.json",)
    )
    monkeypatch.setattr(documents_module, "_otdp_corpus", lambda: corpus)
    with pytest.raises(FileNotFoundError):
        classify_descriptor_pin(pin)
