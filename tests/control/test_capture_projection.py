"""F8/F10: the capture projection's presence gate and open-set walk.

The capture step's landed manifest becomes referable through
``_capture_projection`` (execution contract §3, the ``_resolve_ref``
capture arm). Two folds pin its shape:

- **F10** — the presence gate requires all SIX OTDP-required members,
  refusing a thinner dict HERE (at the projection, with the honest
  ``not a captureManifest`` refusal) instead of letting a pointer miss
  at the walk with a key-miss message.
- **F8** — the projection is an OPEN SET: every JSON-typed member of
  the landed manifest projects, x-extension members included (the
  bridge's per-key manifest doctrine — ``x-`` keys are schema-legal),
  so its docstring is true. ``_walk_pointer``'s non-JSON refusal is
  unchanged and still guards a non-JSON leaf inside a projected member.
"""

from __future__ import annotations

from collections import ChainMap
from typing import Any

import pytest

from benchweave.control.executor import ScopeError, _resolve_ref
from benchweave.host.types import OperationResult, OperationVerb

#: The six members the OTDP captureManifest requires (F10's gate).
SIX: dict[str, Any] = {
    "capture_id": "cap:run-1:grab",
    "format": "waveform_f64le",
    "artifact_id": "art-1",
    "byte_length": 512,
    "sha256": "0" * 64,
    "started_at": "2026-09-24T00:00:00Z",
}


def _scope(manifest: dict[str, Any]) -> ChainMap[str, Any]:
    result = OperationResult.ok("cap-op-1", OperationVerb.CAPTURE, manifest)
    return ChainMap({"grab": result})


def test_the_six_required_members_always_resolve() -> None:
    """The guaranteed core: each of the six required members resolves by
    pointer (presence-filtered — all six are present here)."""
    for key, expected in SIX.items():
        value = _resolve_ref({"step": "grab", "pointer": f"/{key}"}, _scope(dict(SIX)))
        assert value == expected, key


def test_f10_a_three_key_manifest_fails_at_the_projection_not_the_walk() -> None:
    """F10: a manifest-shaped dict carrying only the three §3-named
    members refuses at ``_capture_projection``'s six-member gate — the
    ``not a captureManifest`` refusal, never a downstream key miss at
    ``_walk_pointer`` (which would misreport a malformed manifest as a
    pointer typo)."""
    partial = {
        "capture_id": "cap:run-1:grab",
        "artifact_id": "art-1",
        "sha256": "0" * 64,
    }
    with pytest.raises(ScopeError, match="not a captureManifest") as refused:
        _resolve_ref(
            {"step": "grab", "pointer": "/byte_length"}, _scope(partial)
        )
    assert "key 'byte_length' missing" not in str(refused.value)


def test_f8_an_x_extension_member_resolves() -> None:
    """F8: the projection is open-set — a schema-legal ``x-`` extension
    member of the landed manifest resolves by pointer (before the fold
    the whitelist dropped it and the pointer missed)."""
    manifest: dict[str, object] = {
        **SIX,
        "sample_count": 64,
        "sample_interval_s": 0.001,
        "unit": "V",
        "x-acq-site-42": {"bay": 3},
    }
    value = _resolve_ref(
        {"step": "grab", "pointer": "/x-acq-site-42/bay"}, _scope(manifest)
    )
    assert value == 3


def test_f8_a_non_json_leaf_inside_a_projected_member_still_refuses() -> None:
    """F8 keeps ``_walk_pointer``'s non-JSON rejection: the member
    projects (it is a JSON-typed dict) and the walk refuses when a
    selected LEAF inside it is not JSON."""
    manifest: dict[str, object] = {
        **SIX,
        "x-acq-site-42": {"bay": ("not", "json")},
    }
    with pytest.raises(ScopeError, match="non-JSON"):
        _resolve_ref(
            {"step": "grab", "pointer": "/x-acq-site-42/bay"}, _scope(manifest)
        )


def test_optional_members_stay_presence_filtered() -> None:
    """The waveform-conditional members are not fabricated: a raw_binary
    manifest (six members only) refuses a ``/sample_count`` pointer."""
    with pytest.raises(ScopeError, match="sample_count"):
        _resolve_ref(
            {"step": "grab", "pointer": "/sample_count"}, _scope(dict(SIX))
        )
