"""The G3b runs control surface (issue #304, design record §2.4/§2.5,
acceptance arms E–J) — the run half of GW-10's eight.

Pure-function arms first (this file's opening block — the trip
predicate's matrix and the energy classifier's, with the record's
disclosed boundaries pinned), then the route arms over a REAL composed
gateway with a MUTABLE injected clock, each behavior proven RED before
its implementation (the verbatim failure text rides the commit message
and the run report).
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import Any

import pytest
from g3b_lattice import author_g3b_lattice
from starlette.testclient import TestClient
from ui_gateway_support import LIMITS, NOW_EPOCH, SECRET

from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.operations import Operations
from benchweave.interfaces.sessions import SessionStore
from benchweave.interfaces.ui_control import (
    armed_composition,
    energy_sourcing,
    trip_active,
)
from benchweave.state.store import Store

_FIXTURES_PROCEDURE = (
    __import__("pathlib").Path(__file__).resolve().parents[2]
    / "fixtures"
    / "execution"
    / "procedure-voltage-check.json"
)


def _event(kind: str, sequence: int) -> dict[str, Any]:
    return {"kind": kind, "sequence": sequence, "at": "2026-10-03T00:00:00Z"}


# --- §2.5: the trip predicate (GW-43/54's wire-honest core) -----------------------


def test_no_trip_lifecycle_events_composes_no_protection() -> None:
    """Boundary (c): retention dropped (or never carried) any
    trip-lifecycle row — no verdict, never protection-active."""
    assert trip_active([]) is False
    assert trip_active([_event("run_changed", 1), _event("lease_changed", 2)]) is False


def test_newest_trip_lifecycle_event_decides() -> None:
    """Newest → oldest by sequence: the newest trip-lifecycle row's kind
    decides — a ``trip`` is protection-active; a ``bench_changed`` (the
    only wire shadow an applied trip_reset has) clears it."""
    assert trip_active([_event("trip", 5)]) is True
    assert trip_active([_event("trip", 5), _event("bench_changed", 7)]) is False
    assert trip_active([_event("bench_changed", 3), _event("trip", 5)]) is True
    assert trip_active([_event("trip", 5), _event("bench_changed", 7), _event("trip", 9)]) is True


def test_trip_predicate_is_order_agnostic() -> None:
    """The verdict keys on sequence, never list order — an adapter may
    hand the rows in either direction."""
    rows = [_event("run_changed", 1), _event("trip", 5), _event("bench_changed", 7)]
    assert trip_active(rows) is False
    assert trip_active(list(reversed(rows))) is False
    rows = [_event("bench_changed", 7), _event("run_changed", 1), _event("trip", 9)]
    assert trip_active(rows) is True
    assert trip_active(list(reversed(rows))) is True


def test_boundary_b_admin_change_after_a_trip_clears() -> None:
    """Disclosed boundary (b): an admin configuration activation after a
    trip also emits ``bench_changed`` and therefore ALSO clears the
    marker — the closed event def has no channel for the change kind
    (the record §2.5b err-clear boundary, pinned as disclosed)."""
    rows = [_event("trip", 5), _event("bench_changed", 7)]
    assert trip_active(rows) is False


# --- GW-52: the energy classification ---------------------------------------------


def _variant(tmp_path: Any, name: str, **kwargs: Any) -> dict[str, Any]:
    directory, _binding_sha = author_g3b_lattice(tmp_path, name=name, **kwargs)
    procedure_path = directory / "procedure-voltage-check.json"
    parsed: dict[str, Any] = json.loads(procedure_path.read_text())
    return parsed


def test_enable_true_is_energy_sourcing(tmp_path: Any) -> None:
    """R-ENERGISE-1's enabling clause: any ``invoke`` step whose input
    carries ``enabled: true`` makes the procedure energy-sourcing."""
    assert energy_sourcing(json.loads(_FIXTURES_PROCEDURE.read_text())) is True
    assert energy_sourcing(_variant(tmp_path, "energise", enabled=True)) is True


def test_explicit_false_is_de_energising(tmp_path: Any) -> None:
    """An explicit ``enabled: false`` is the de-energising class (the
    record's own shape: manual + explicit false)."""
    assert energy_sourcing(_variant(tmp_path, "deenergise", enabled=False)) is False


def test_absent_enable_field_is_de_energising(tmp_path: Any) -> None:
    """A procedure with no enable-true step (including the enable step
    with the field absent) is the de-energising class."""
    assert energy_sourcing(_variant(tmp_path, "absent", enabled="absent")) is False


def test_nested_enable_steps_are_classified(tmp_path: Any) -> None:
    """The scan recurses into ``if.then`` / ``repeat.steps`` bodies — an
    author cannot hide an enable from the classifier by nesting it."""
    base = json.loads(_FIXTURES_PROCEDURE.read_text())
    nested = {
        "id": "wrap",
        "kind": "if",
        "predicate": {"sample": "voltage", "minimum": 0.0, "maximum": 1.0},
        "then": [step for step in base["steps"] if step.get("id") == "enable"],
        "else": [],
    }
    procedure = dict(base)
    procedure["steps"] = [nested]
    assert energy_sourcing(procedure) is True
    looped = dict(base)
    looped["steps"] = [
        {
            "id": "loop",
            "kind": "repeat",
            "count": 1,
            "steps": [step for step in base["steps"] if step.get("id") == "enable"],
        }
    ]
    assert energy_sourcing(looped) is True


def test_the_setpoint_clause_is_not_derived() -> None:
    """Disclosed boundary (G3-D2): a WRITE step raising a setpoint of a
    currently-energised output is NOT classified — the clause needs live
    device state the documents are silent on, and the classifier errs
    only by rule change, never silently."""
    write_only = {
        "id": "p",
        "version": "0.1.0",
        "mode": "manual",
        "steps": [
            {
                "id": "raise",
                "kind": "write",
                "role": "supply",
                "parameter": "voltage_setpoint_v",
                "value": 5.5,
                "timeout_ms": 500,
            }
        ],
    }
    assert energy_sourcing(write_only) is False


# --- FOLD-5: the armed text composes EVERY enable, honestly ----------------------


def _f5_binding() -> dict[str, Any]:
    """The committed fixture's own role map, isolated: supply → psu ch1."""
    return {
        "bindings": [
            {"role": "supply", "device_id": "psu", "channels": {"output": "ch1"}}
        ]
    }


def test_armed_text_names_every_energised_output() -> None:
    """FOLD-5 (B-F3): EVERY enable step composes — each with its own
    preceding configure invoke's values and its mapped target — never
    only the first (the first-enable-only text understated the blast
    radius: one device named while a second is energised)."""
    base = json.loads(_FIXTURES_PROCEDURE.read_text())
    two_enables = dict(base)
    two_enables["steps"] = [
        base["steps"][0],  # the fixture's configure invoke (5 V, …)
        {
            "id": "enable-1",
            "kind": "invoke",
            "role": "supply",
            "action_id": "otdp.dc_psu.output/1.0.0",
            "input": {"enabled": True},
            "timeout_ms": 500,
        },
        {
            "id": "configure-2",
            "kind": "invoke",
            "role": "supply",
            "action_id": "otdp.dc_psu.configure/1.0.0",
            "input": {"voltage_v": 9.0},
            "timeout_ms": 500,
        },
        {
            "id": "enable-2",
            "kind": "invoke",
            "role": "supply",
            "action_id": "otdp.dc_psu.output/1.0.0",
            "input": {"enabled": True},
            "timeout_ms": 500,
        },
    ]
    _energy, _manual, text = armed_composition(_f5_binding(), two_enables)
    assert text is not None
    assert "9 V" in text  # the second enable's own configure value
    assert text.count("to psu ch1") == 2  # BOTH targets named


def test_armed_text_says_no_input_values_when_the_enable_precedes_its_configure() -> None:
    """FOLD-5's degenerate value shape: an enable whose preceding
    sibling carries no numeric inputs renders the honest "no input
    values" — never the old empty gap ("…:  to psu ch1")."""
    base = json.loads(_FIXTURES_PROCEDURE.read_text())
    enable_first = dict(base)
    enable_first["steps"] = [
        {
            "id": "enable",
            "kind": "invoke",
            "role": "supply",
            "action_id": "otdp.dc_psu.output/1.0.0",
            "input": {"enabled": True},
            "timeout_ms": 500,
        },
        {
            "id": "configure",
            "kind": "invoke",
            "role": "supply",
            "action_id": "otdp.dc_psu.configure/1.0.0",
            "input": {"voltage_v": 5.0},
            "timeout_ms": 500,
        },
    ]
    _energy, _manual, text = armed_composition(_f5_binding(), enable_first)
    assert text is not None
    assert "no input values" in text
    assert "psu ch1" in text


def test_armed_text_names_an_unmapped_role() -> None:
    """FOLD-5's degenerate target shape: an enable whose role maps to
    no binding entry renders "an unmapped role" — never the old blank
    target ("… to . Confirm…")."""
    base = json.loads(_FIXTURES_PROCEDURE.read_text())
    unmapped = dict(base)
    unmapped["steps"] = [
        base["steps"][0],
        {
            "id": "enable",
            "kind": "invoke",
            "role": "heater",
            "action_id": "otdp.heater.output/1.0.0",
            "input": {"enabled": True},
            "timeout_ms": 500,
        },
    ]
    _energy, _manual, text = armed_composition(_f5_binding(), unmapped)
    assert text is not None
    assert "an unmapped role" in text
    assert "5 V" in text


# --- the composed-gateway rig ------------------------------------------------------


_BENCH = "sim-bench"
_CLIENT_BASE = "http://testserver:8125"
CONTROL = frozenset({"stg:observe", "stg:control"})
OBSERVE = frozenset({"stg:observe"})
_BINDING_REQUEST_ID = "req-g3b-energise"  # the variant binding's own §9 id


class _Clock:
    """One mutable epoch cell; ``iso`` renders the same instant."""

    def __init__(self) -> None:
        self.epoch = NOW_EPOCH

    def epoch_s(self) -> int:
        return self.epoch

    def iso(self) -> str:
        from datetime import UTC, datetime

        return datetime.fromtimestamp(self.epoch, tz=UTC).isoformat().replace(
            "+00:00", "Z"
        )

    def advance(self, seconds: int) -> None:
        self.epoch += seconds


def _compose(data_dir: Any, name: str, clock: _Clock, lattice_dir: Any) -> Any:
    store = Store.open(str(data_dir / f"state-{name}.sqlite"), check_same_thread=False)
    app = create_app(
        store=store,
        content=ContentStore(store),
        secret=SECRET,
        limits=dict(LIMITS),
        gateway_id="ui-test",
        fixtures_dir=lattice_dir,
        now_iso=clock.iso,
        now_epoch=clock.epoch_s,
    )
    app.state.g3b_store = store
    return app


@pytest.fixture()
def gateway_owned_rig(tmp_path: Any) -> Any:
    """The commissioned-grant lattice (the committed fixture's own
    mode): gateway_owned + unattended grant — starts admit with no
    lease, so it is the rig for the ungated legs (arm I) and GW-56's
    gateway-owned non-refusal (arm J's fourth leg)."""
    clock = _Clock()
    lattice_dir, binding_sha = author_g3b_lattice(
        tmp_path, mode="gateway_owned", enabled=True, request_id=_BINDING_REQUEST_ID
    )
    app = _compose(tmp_path, "g3b-gateway-owned", clock, lattice_dir)
    with TestClient(app, base_url=_CLIENT_BASE) as client:
        record = _session(app, scopes=CONTROL)
        yield SimpleNamespace(
            app=app,
            client=client,
            clock=clock,
            binding_sha=binding_sha,
            record=record,
        )


def _session(
    app: Any, *, principal: str = "ui-operator", scopes: frozenset[str], ttl_s: int = 3600
) -> Any:
    sessions: SessionStore = app.state.ui_sessions
    code = sessions.mint_login_code(
        Identity(
            principal=principal,
            audience="stg",
            scopes=scopes,
            expires_at=NOW_EPOCH + 12 * 3600,
        ),
        ttl_seconds=ttl_s,
    )
    return sessions.exchange(code)


@pytest.fixture()
def energise_rig(tmp_path: Any) -> Any:
    """One composed gateway on the manual+enable-true (energy-sourcing)
    lattice, its own clock, one control-scope session."""
    clock = _Clock()
    lattice_dir, binding_sha = author_g3b_lattice(
        tmp_path, mode="manual", enabled=True, request_id=_BINDING_REQUEST_ID
    )
    app = _compose(tmp_path, "g3b-energise", clock, lattice_dir)
    with TestClient(app, base_url=_CLIENT_BASE) as client:
        record = _session(app, scopes=CONTROL)
        yield SimpleNamespace(
            app=app,
            client=client,
            clock=clock,
            binding_sha=binding_sha,
            record=record,
        )


def _get(rig: Any, path: str, record: Any) -> Any:
    return rig.client.get(
        path, cookies={"bw_session": record.session_id}, follow_redirects=False
    )


def _post(rig: Any, path: str, record: Any, data: dict[str, str]) -> Any:
    return rig.client.post(
        path,
        cookies={"bw_session": record.session_id},
        data=data,
        headers={"X-CSRF-Token": record.csrf_token},
    )


def _spy(rig: Any, name: str) -> list[str]:
    calls: list[str] = []
    operations: Operations = rig.app.state.ui_operations
    real = getattr(operations, name)

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        calls.append(name)
        return real(*args, **kwargs)

    setattr(operations, name, wrapper)
    return calls


def _generation(rig: Any, record: Any) -> int:
    response = _get(rig, f"/ui/benches/{_BENCH}", record)
    assert response.status_code == 200
    import re

    match = re.search(r'data-bw-bench-generation>(\d+)<', response.text)
    assert match is not None, response.text[:2000]
    return int(match.group(1))


def _stage(rig: Any, record: Any, *, sha: str | None = None) -> Any:
    return _post(
        rig,
        f"/ui/benches/{_BENCH}/staging",
        record,
        data={"binding_sha256": sha or rig.binding_sha},
    )


# --- GW-50: staging (the binding selection) ----------------------------------------


def test_staging_records_the_cycle_and_the_panel_shows_it(energise_rig: Any) -> None:
    """Staging a binding records the cycle server-side; the panel marks
    it staged (§F) and shows the binding's own request id — the id every
    mutating form of this cycle will carry (GW-13's fixed id)."""
    rig = energise_rig
    response = _stage(rig, rig.record)
    assert response.status_code == 200, response.text[:500]
    assert 'data-bw-staged="true"' in response.text
    assert rig.binding_sha[:16] in response.text
    assert _BINDING_REQUEST_ID in response.text


def test_re_staging_the_same_binding_keeps_the_request_id(energise_rig: Any) -> None:
    """The staging cycle's id is the binding's own — a same-binding
    re-stage (a post-refusal retry's re-render) cannot change it."""
    rig = energise_rig
    first = _stage(rig, rig.record)
    second = _stage(rig, rig.record)
    assert first.text.count(_BINDING_REQUEST_ID) >= 1
    assert second.text.count(_BINDING_REQUEST_ID) >= 1


def test_staging_a_garbage_digest_refuses_pre_send(energise_rig: Any) -> None:
    rig = energise_rig
    response = _stage(rig, rig.record, sha="not-a-digest")
    assert response.status_code == 400, response.text[:500]
    assert 'data-bw-failure="invalid_request"' in response.text
    store: SessionStore = rig.app.state.ui_sessions
    assert store.staged_start(rig.record.session_id, _BENCH) is None


# --- GW-51: check precedes start, a staged change invalidates ----------------------


def test_check_records_the_verdict_and_the_start_gates_on_it(energise_rig: Any) -> None:
    """The check records {valid, generation, findings} for the CURRENT
    staged set; the staged start handler refuses pre-send when no check
    is on record (the §C.3 invalid_request row, no seam write)."""
    rig = energise_rig
    _stage(rig, rig.record)
    calls = _spy(rig, "run_start")
    start_response = _post(
        rig,
        f"/ui/benches/{_BENCH}/run-starts",
        rig.record,
        data={
            "request_id": _BINDING_REQUEST_ID,
            "expected_generation": str(_generation(rig, rig.record)),
        },
    )
    # RED-to-GREEN note: before the route exists this is a 404; after,
    # the no-check guard refuses pre-send — either way the run never
    # starts.
    assert "run_start" not in calls
    assert start_response.status_code == 400, start_response.text[:500]
    assert 'data-bw-failure="invalid_request"' in start_response.text

    check_response = _post(
        rig, f"/ui/benches/{_BENCH}/run-checks", rig.record, data={}
    )
    assert check_response.status_code == 200, check_response.text[:500]
    assert 'data-bw-check-state="valid"' in check_response.text
    # The start control enables only now — the no-check guard no longer
    # fires (the arm leg proceeds to its own guards below).
    store: SessionStore = rig.app.state.ui_sessions
    staged = store.staged_start(rig.record.session_id, _BENCH)
    assert staged is not None and staged.check is not None
    assert staged.check["valid"] is True


def test_staged_change_clears_the_recorded_check(energise_rig: Any) -> None:
    """GW-51's invalidation: any staged change clears the recorded check
    (the record re-stages with ``check=None`` and un-arms)."""
    rig = energise_rig
    _stage(rig, rig.record)
    _post(rig, f"/ui/benches/{_BENCH}/run-checks", rig.record, data={})
    store: SessionStore = rig.app.state.ui_sessions
    staged = store.staged_start(rig.record.session_id, _BENCH)
    assert staged is not None and staged.check is not None
    _stage(rig, rig.record)  # same binding, a deliberate re-stage
    staged = store.staged_start(rig.record.session_id, _BENCH)
    assert staged is not None
    assert staged.check is None
    assert staged.armed is False


def test_stage_only_start_control_gates_on_the_recorded_check(
    energise_rig: Any,
) -> None:
    """FOLD-2 (B-F2): §2.4's invalid-staged-input state. Stage-only (no
    check on record) rendered the start control ENABLED while the
    panel's own note said the preflight gates it — the render now
    matches the handler's no-check refusal: the start control renders
    disabled with the §C.2 invalid-staged-input reason until a check is
    on record for the current staged set. A check on record composes
    the actions again (the energy class's arm control appears; the
    handler legs were already honest and stay as-is)."""
    rig = energise_rig
    _stage(rig, rig.record)
    page = _get(rig, f"/ui/benches/{_BENCH}", rig.record)
    assert page.status_code == 200, page.text[:500]
    assert 'data-bw-disabled-reason="invalid-staged-input"' in page.text
    assert "No check is on record" in page.text
    # no enabled start path composes: the gated control is a disabled
    # div, never a form posting to run-starts
    assert "data-bw-start-control hx-post" not in page.text
    _post(rig, f"/ui/benches/{_BENCH}/run-checks", rig.record, data={})
    page = _get(rig, f"/ui/benches/{_BENCH}", rig.record)
    assert page.status_code == 200, page.text[:500]
    assert 'data-bw-disabled-reason="invalid-staged-input"' not in page.text
    assert "data-bw-arm-control" in page.text


# --- GW-52: the arm step composes the confirm from the documents -------------------


def _check(rig: Any, record: Any) -> Any:
    return _post(rig, f"/ui/benches/{_BENCH}/run-checks", record, data={})


def test_arm_composes_the_armed_confirm_from_the_documents(energise_rig: Any) -> None:
    """Arm (H): the armed fragment states the effect, the exact values
    with units, and the target — composed from the documents per §E.1's
    armed-text shape — and no seam MUTATION ran (reads only)."""
    rig = energise_rig
    _stage(rig, rig.record)
    # FOLD-2: the check pre-step — the gate requires a check on record
    # before any start/confirm action composes (the arm composes reads
    # only; its own intent, the documents → armed text, is unchanged).
    _check(rig, rig.record)
    # Two named live lists, asserted separately: ``_spy`` returns the list
    # it appends to, and concatenating two spy results snapshots dead empty
    # copies — the repaired shape keeps each assertion live (kill rule: an
    # assertion that cannot fail polices nothing).
    calls_start = _spy(rig, "run_start")
    calls_lease = _spy(rig, "lease_create")
    response = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert response.status_code == 200
    assert 'data-bw-confirm="armed"' in response.text
    assert "the output will be energised" in response.text
    assert "5 V" in response.text
    assert "psu ch1" in response.text
    assert "Confirm to proceed." in response.text
    assert "Confirm: Start run" in response.text
    assert ">Cancel</button>" in response.text
    assert not calls_start
    assert not calls_lease


def test_arm_records_the_armed_flag(energise_rig: Any) -> None:
    rig = energise_rig
    _stage(rig, rig.record)
    _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    store: SessionStore = rig.app.state.ui_sessions
    staged = store.staged_start(rig.record.session_id, _BENCH)
    assert staged is not None and staged.armed is True
    # GW-51's invalidation reaches the arm too: a staged change un-arms.
    _stage(rig, rig.record)
    staged = store.staged_start(rig.record.session_id, _BENCH)
    assert staged is not None and staged.armed is False


def test_disarm_keeps_the_staged_set_and_clears_the_arm(energise_rig: Any) -> None:
    """No auto-disarm has an inverse: the operator's Cancel (the disarm
    POST) clears the armed flag and keeps the staged binding and the
    recorded check (the staged intent is never silently discarded)."""
    rig = energise_rig
    _stage(rig, rig.record)
    _check(rig, rig.record)
    _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    response = _post(rig, f"/ui/benches/{_BENCH}/staging/disarm", rig.record, data={})
    assert response.status_code == 200
    store: SessionStore = rig.app.state.ui_sessions
    staged = store.staged_start(rig.record.session_id, _BENCH)
    assert staged is not None
    assert staged.armed is False
    assert staged.check is not None
    assert 'data-bw-staged="true"' in response.text


def test_arm_with_nothing_staged_refuses_pre_send(energise_rig: Any) -> None:
    rig = energise_rig
    calls_start = _spy(rig, "run_start")
    calls_check = _spy(rig, "run_check")
    response = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert response.status_code == 400
    assert 'data-bw-failure="invalid_request"' in response.text
    assert not calls_start
    assert not calls_check


def test_arm_with_an_unstored_binding_refuses(energise_rig: Any) -> None:
    """An unstored digest stages fine (run_check will report the
    finding), but the arm's document chain refuses ``not_found`` — the
    honest §C.3 row, rendered."""
    rig = energise_rig
    _stage(rig, rig.record, sha="e" * 64)
    response = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert response.status_code == 404
    assert 'data-bw-failure="not_found"' in response.text


# --- FOLD-1: a staged stored NON-binding document is the unreadable chain ----------


def _lattice_procedure_sha(tmp_path: Any) -> str:
    """The rig lattice's procedure document digest: the committed
    fixture's bytes with the lattice mutation re-applied, deterministic
    for the rig's (mode, enabled) — the digest the store holds."""
    return hashlib.sha256(
        (tmp_path / "lattice" / "procedure-voltage-check.json").read_bytes()
    ).hexdigest()


def test_stored_non_binding_digest_renders_the_unreadable_branch(
    energise_rig: Any, tmp_path: Any
) -> None:
    """FOLD-1 (A-F2/B-F1, two-lane convergence): a STORED document that
    is not a binding — here the lattice's own procedure document, staged
    by its content digest — used to KeyError the panel's chain read
    (``binding_doc["procedure"]["sha256"]``) and 500 the whole bench
    surface: stage tolerates every stored document (only ``not_found``
    refuses) and the panel caught OperationFailure only. The chain now
    treats the shapeless document as unreadable: the stage answers 200,
    the panel renders the honest-disabled staged-chain-unreadable branch
    (template code that previously had zero coverage), and the bench
    page composes."""
    rig = energise_rig
    procedure_sha = _lattice_procedure_sha(tmp_path)
    staged = _stage(rig, rig.record, sha=procedure_sha)
    assert staged.status_code == 200, staged.text[:500]
    page = _get(rig, f"/ui/benches/{_BENCH}", rig.record)
    assert page.status_code == 200, page.text[:500]
    assert 'data-bw-disabled-reason="staged-chain-unreadable"' in page.text
    assert "document chain is not readable" in page.text


def test_arm_refuses_a_stored_non_binding_document_honestly(
    energise_rig: Any, tmp_path: Any
) -> None:
    """FOLD-1's second leg: the arm step's chain read on the stored
    non-binding document refuses ``not_found`` honestly — the same §C.3
    row an unstored digest gets — never a raw KeyError 500."""
    rig = energise_rig
    procedure_sha = _lattice_procedure_sha(tmp_path)
    staged = _stage(rig, rig.record, sha=procedure_sha)
    assert staged.status_code == 200, staged.text[:500]
    arm = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert arm.status_code == 404, arm.text[:500]
    assert 'data-bw-failure="not_found"' in arm.text
    assert "does not name a pinned procedure" in arm.text


# --- GW-56 at arm (the J-family guard fires on the arm step too) -------------------


def _take_lease(
    rig: Any, record: Any, *, duration_ms: int, generation: int | None = None
) -> Any:
    resolved = generation if generation is not None else _generation(rig, record)
    return _post(
        rig,
        f"/ui/benches/{_BENCH}/leases",
        record,
        data={"duration_ms": str(duration_ms), "expected_generation": str(resolved)},
    )


def test_gw56_refuses_the_arm_when_the_bound_exceeds_attention(
    energise_rig: Any,
) -> None:
    """Manual mode, bound (max_body_ms + max_protection_ms = 10 000 ms)
    vs attention remaining: with a live held lease with 5 000 ms
    remaining (session hours), the bound exceeds the attention remainder
    — the arm refuses PRE-SEND (no mutating seam call), rendering the
    bound, both remaining figures, and the clearing actions."""
    rig = energise_rig
    generation = _generation(rig, rig.record)
    _take_lease(rig, rig.record, duration_ms=5_000, generation=generation)
    _stage(rig, rig.record)
    _check(rig, rig.record)
    calls_start = _spy(rig, "run_start")
    calls_lease = _spy(rig, "lease_create")
    response = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert response.status_code == 403, response.text[:800]
    assert 'data-bw-failure="policy_denied"' in response.text
    assert "10000" in response.text
    assert "5000" in response.text
    assert "benchweave ui-login" in response.text
    assert not calls_start
    assert not calls_lease


def test_gw56_arm_boundary_equal_is_allowed(energise_rig: Any) -> None:
    """The boundary: bound exactly equal to the attention remainder is
    allowed — the arm composes (the seam still decides the start)."""
    rig = energise_rig
    generation = _generation(rig, rig.record)
    _take_lease(rig, rig.record, duration_ms=10_000, generation=generation)
    _stage(rig, rig.record)
    _check(rig, rig.record)
    response = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert response.status_code == 200, response.text[:500]
    assert 'data-bw-confirm="armed"' in response.text


# --- GW-42: observe sessions render the panel disabled with no-authority -----------


def test_observe_session_renders_the_panel_controls_disabled(energise_rig: Any) -> None:
    """§2.2's observe posture: every mutating control of the staging
    panel renders disabled with the §C.2 no-authority reason and its
    visible label."""
    rig = energise_rig
    observer = _session(rig.app, principal="ui-observer", scopes=OBSERVE)
    _stage(rig, rig.record)  # the operator stages; the observer only reads
    response = _get(rig, f"/ui/benches/{_BENCH}", observer)
    assert response.status_code == 200
    assert 'data-bw-disabled-reason="no-authority"' in response.text
    assert "No lease or policy authority" in response.text


# --- GW-12/13: double-submit and fire-time guards (arms E/G) ---------------------


def _run_started_id(response: Any) -> str:
    import re

    match = re.search(r'data-bw-run-started="([^"]+)"', response.text)
    assert match is not None, response.text[:800]
    return match.group(1)


def test_e_two_identical_confirms_start_exactly_one_run(energise_rig: Any) -> None:
    """Arm E (§6.E): Arm then two identical Confirm POSTs (same cookie,
    same request id): exactly one run exists in the store, both
    responses carry the same run id, the second being the §9 replay.
    The binding's own request id IS the staging cycle's §9 id (the
    keep-record-on-start ruled deviation: the staged record stays as
    the replay handle, so the second POST reaches the seam and replays
    instead of being refused by the guards)."""
    rig = energise_rig
    generation = _generation(rig, rig.record)
    _take_lease(rig, rig.record, duration_ms=10_000, generation=generation)
    _stage(rig, rig.record)
    _check(rig, rig.record)
    arm = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert arm.status_code == 200, arm.text[:500]
    payload = {
        "request_id": _BINDING_REQUEST_ID,
        "binding_sha256": rig.binding_sha,
        "expected_generation": str(generation),
    }
    first = _post(rig, f"/ui/benches/{_BENCH}/run-starts", rig.record, data=payload)
    assert first.status_code == 200, first.text[:800]
    second = _post(rig, f"/ui/benches/{_BENCH}/run-starts", rig.record, data=payload)
    assert second.status_code == 200, second.text[:800]
    store: Store = rig.app.state.g3b_store
    runs = store.list_run_states(_BENCH)
    assert len(runs) == 1, runs
    assert _run_started_id(first) == _run_started_id(second)


def test_f3_the_staged_record_discloses_the_started_run(energise_rig: Any) -> None:
    """FOLD-3 (A-F1, adopted fork, disclosed): the staged record survives
    a start (keep-record-on-start) and now carries the last-started run
    id, so the panel discloses it on every render — "This binding
    already started run X — a resubmission replays it." The disclosure
    survives a same-binding restage: the §9 id is the binding's own, so
    the started-run knowledge belongs to the binding, not the check
    cycle. No seam motion, no authority change — the seam still owns
    the replay."""
    rig = energise_rig
    generation = _generation(rig, rig.record)
    _take_lease(rig, rig.record, duration_ms=600_000, generation=generation)
    _stage(rig, rig.record)
    _check(rig, rig.record)
    arm = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert arm.status_code == 200, arm.text[:500]
    payload = {
        "request_id": _BINDING_REQUEST_ID,
        "binding_sha256": rig.binding_sha,
        "expected_generation": str(generation),
    }
    started = _post(rig, f"/ui/benches/{_BENCH}/run-starts", rig.record, data=payload)
    assert started.status_code == 200, started.text[:800]
    run_id = _run_started_id(started)
    page = _get(rig, f"/ui/benches/{_BENCH}", rig.record)
    assert page.status_code == 200, page.text[:500]
    assert f'data-bw-run-started="{run_id}"' in page.text
    assert "This binding already started run" in page.text
    assert "a resubmission replays it" in page.text
    # a same-binding restage keeps the disclosure
    _stage(rig, rig.record)
    restaged = _get(rig, f"/ui/benches/{_BENCH}", rig.record)
    assert restaged.status_code == 200, restaged.text[:500]
    assert f'data-bw-run-started="{run_id}"' in restaged.text


def test_f3_a_resubmission_after_a_full_cycle_replays_and_says_so(
    energise_rig: Any,
) -> None:
    """FOLD-3's repro (lane A): a full cycle whose run settles terminal,
    restage the SAME binding, re-check, re-arm, confirm — the seam's §9
    replay returns the FIRST run; the response renders it AS a replay
    (the data-bw-replay marker and the first run's id), never a
    fresh-looking start; the store holds exactly one run. The second
    cycle runs under the FIRST cycle's lease (600 s, still live under
    the injected clock; the seam admits one controlling lease per
    bench, so no second lease is taken — the repro's "new lease" leg
    reduces to a live lease at fire)."""
    rig = energise_rig
    generation = _generation(rig, rig.record)
    _take_lease(rig, rig.record, duration_ms=600_000, generation=generation)
    _stage(rig, rig.record)
    _check(rig, rig.record)
    arm = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert arm.status_code == 200, arm.text[:500]
    payload = {
        "request_id": _BINDING_REQUEST_ID,
        "binding_sha256": rig.binding_sha,
        "expected_generation": str(generation),
    }
    first = _post(rig, f"/ui/benches/{_BENCH}/run-starts", rig.record, data=payload)
    assert first.status_code == 200, first.text[:800]
    first_run_id = _run_started_id(first)
    operations: Operations = rig.app.state.ui_operations
    identity = Identity(
        principal=rig.record.principal,
        audience="stg",
        scopes=rig.record.scopes,
        expires_at=rig.record.expires_at,
    )
    import time

    start = time.monotonic()
    while True:
        current = operations.run_get(identity, first_run_id)
        if current["state"] == "terminal":
            break
        assert time.monotonic() - start < 60.0, current
        time.sleep(0.2)
    _stage(rig, rig.record)
    _check(rig, rig.record)
    arm2 = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert arm2.status_code == 200, arm2.text[:500]
    replay = _post(rig, f"/ui/benches/{_BENCH}/run-starts", rig.record, data=payload)
    assert replay.status_code == 200, replay.text[:800]
    assert _run_started_id(replay) == first_run_id
    assert 'data-bw-replay="true"' in replay.text
    assert "Replayed run" in replay.text
    store: Store = rig.app.state.g3b_store
    runs = store.list_run_states(_BENCH)
    assert len(runs) == 1, runs


def test_g_a_trip_while_armed_refuses_the_confirm_without_a_seam_call(
    energise_rig: Any,
) -> None:
    """Arm G (§6.G), planted-event induction (labelled: the belt of the
    two inductions the record names — the seam's own events_get reads
    the same stream the row is planted on): Arm, then a planted trip
    row, then the Confirm POST — NO seam run_start call, the armed
    state re-rendered with the §E.1 protection-active disable and its
    guard note, no auto-disarm (Cancel stays enabled), and the armed
    flag survives (a departing guard re-enables on the next render)."""
    rig = energise_rig
    generation = _generation(rig, rig.record)
    _take_lease(rig, rig.record, duration_ms=10_000, generation=generation)
    _stage(rig, rig.record)
    _check(rig, rig.record)
    arm = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert arm.status_code == 200, arm.text[:500]
    store: Store = rig.app.state.g3b_store
    store.append_event(
        f"bench.{_BENCH}",
        {
            "stream_id": f"bench.{_BENCH}",
            "at": rig.clock.iso(),
            "kind": "trip",
            "run_id": None,
            "evidence": {},
        },
    )
    calls_start = _spy(rig, "run_start")
    response = _post(
        rig,
        f"/ui/benches/{_BENCH}/run-starts",
        rig.record,
        data={
            "request_id": _BINDING_REQUEST_ID,
            "binding_sha256": rig.binding_sha,
            "expected_generation": str(generation),
        },
    )
    assert response.status_code == 200, response.text[:800]
    assert not calls_start
    assert 'data-bw-confirm="armed"' in response.text
    assert 'data-bw-disabled-reason="protection-active"' in response.text
    assert ">Cancel</button>" in response.text
    sessions: SessionStore = rig.app.state.ui_sessions
    staged = sessions.staged_start(rig.record.session_id, _BENCH)
    assert staged is not None and staged.armed is True


def test_f_a_transport_shaped_failure_renders_no_response(energise_rig: Any) -> None:
    """Arm F (§6.F), labelled INDUCED-not-emitted (the G2 §7-F honesty
    rule): a seam double raising RuntimeError on run_start — no
    interface answer — renders §C.3's no-response row, sent status
    UNKNOWN, and the reconcile link naming the staged request id,
    resolving to run_find's view."""
    rig = energise_rig
    generation = _generation(rig, rig.record)
    _take_lease(rig, rig.record, duration_ms=10_000, generation=generation)
    _stage(rig, rig.record)
    _check(rig, rig.record)
    arm = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert arm.status_code == 200, arm.text[:500]
    operations: Operations = rig.app.state.ui_operations

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("induced transport-shaped failure")

    operations.run_start = _boom  # type: ignore[method-assign]
    response = _post(
        rig,
        f"/ui/benches/{_BENCH}/run-starts",
        rig.record,
        data={
            "request_id": _BINDING_REQUEST_ID,
            "binding_sha256": rig.binding_sha,
            "expected_generation": str(generation),
        },
    )
    assert response.status_code == 504, response.text[:500]
    assert "No interface answer arrived" in response.text
    assert "UNKNOWN" in response.text
    assert f'href="/ui/requests/{_BINDING_REQUEST_ID}"' in response.text


# --- GW-53/55: ungated cancel, the run-page marker (arm I) ----------------------


@pytest.fixture()
def _started_gateway_run(gateway_owned_rig: Any) -> Any:
    """Arm + confirm on the commissioned-grant rig (no lease anywhere —
    the grant admits it), returning the started run id via the rig."""
    rig = gateway_owned_rig
    generation = _generation(rig, rig.record)
    _stage(rig, rig.record)
    _check(rig, rig.record)
    arm = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert arm.status_code == 200, arm.text[:500]
    started = _post(
        rig,
        f"/ui/benches/{_BENCH}/run-starts",
        rig.record,
        data={
            "request_id": _BINDING_REQUEST_ID,
            "binding_sha256": rig.binding_sha,
            "expected_generation": str(generation),
        },
    )
    # Arm J's fourth leg (GW-56): gateway-owned + commissioned grant +
    # NO lease — the guard does not refuse (it is manual-only); the
    # seam's own grant gate decides, and admits.
    assert started.status_code == 200, started.text[:800]
    rig.run_id = _run_started_id(started)
    return rig


def test_i_cancel_is_ungated_and_marks_the_run_page(
    _started_gateway_run: Any,
) -> None:
    """Arm I (§6.I): with NO lease and a trip planted, the cancel
    control renders enabled; the POST reaches the seam (owner session);
    the run page carries the pending-cancel marker; once run_get
    reports terminal the marker gives way to the state (the driven
    poll discipline)."""
    rig = _started_gateway_run
    store: Store = rig.app.state.g3b_store
    store.append_event(
        f"bench.{_BENCH}",
        {
            "stream_id": f"bench.{_BENCH}",
            "at": rig.clock.iso(),
            "kind": "trip",
            "run_id": None,
            "evidence": {},
        },
    )
    page = _get(rig, f"/ui/runs/{rig.run_id}", rig.record)
    assert page.status_code == 200, page.text[:500]
    assert 'data-bw-cancel-control' in page.text
    assert 'data-bw-disabled-reason="no-authority"' not in page.text
    calls_cancel = _spy(rig, "run_cancel")
    # FOLD-4 (A-F3): the OR-fork let a fast sim's terminal render mask a
    # broken marker (lane A observed the masking; on a slower sim the
    # same OR caught the break — the arm's outcome was the sim's speed,
    # not the render's correctness). The during-live-window render is
    # pinned on an INDUCED live window (a one-shot run_get wrap
    # reporting the run's own accepted state — labelled induction, the
    # G2 §7-F posture; every seam call stays real): the marker renders,
    # the terminal note does not. The terminal settle below runs on the
    # unwrapped seam.
    operations: Operations = rig.app.state.ui_operations
    real_get = operations.run_get

    def _live_once(*args: Any, **kwargs: Any) -> Any:
        projection = real_get(*args, **kwargs)
        return {**projection, "state": "accepted"}  # one poll only

    operations.run_get = _live_once  # type: ignore[method-assign]
    cancel = _post(
        rig,
        f"/ui/runs/{rig.run_id}/cancellations",
        rig.record,
        data={"reason": "operator stopped the run"},
    )
    operations.run_get = real_get  # type: ignore[method-assign]
    assert cancel.status_code == 200, cancel.text[:500]
    assert "run_cancel" in calls_cancel
    sessions: SessionStore = rig.app.state.ui_sessions
    assert sessions.cancel_requested(rig.record.session_id, rig.run_id) is True
    assert "data-bw-cancel-requested" in cancel.text
    assert "data-bw-terminal-note" not in cancel.text
    operations = rig.app.state.ui_operations
    from benchweave.interfaces.identity import Identity as _Identity

    identity = _Identity(
        principal=rig.record.principal,
        audience="stg",
        scopes=rig.record.scopes,
        expires_at=rig.record.expires_at,
    )
    deadline = 60.0
    import time

    start = time.monotonic()
    while True:
        current = operations.run_get(identity, rig.run_id)
        if current["state"] == "terminal":
            break
        assert time.monotonic() - start < deadline, current
        time.sleep(0.2)
    settled = _get(rig, f"/ui/runs/{rig.run_id}", rig.record)
    assert 'data-bw-cancel-requested' not in settled.text
    assert 'data-bw-terminal-note' in settled.text


# --- GW-56 at fire (arm J): the re-judged bound --------------------------------


def _confirm(rig: Any, generation: int) -> Any:
    return _post(
        rig,
        f"/ui/benches/{_BENCH}/run-starts",
        rig.record,
        data={
            "request_id": _BINDING_REQUEST_ID,
            "binding_sha256": rig.binding_sha,
            "expected_generation": str(generation),
        },
    )


def test_j_gw56_at_fire_the_renewed_shorter_lease_refuses(energise_rig: Any) -> None:
    """Arm J, lease leg (§6.J): armed under a long lease, then renewed
    down to 5 000 ms — at fire the bound (10 000 ms) exceeds the
    attention remainder: pre-send refusal (no seam run_start call)
    naming the bound and the figures."""
    rig = energise_rig
    generation = _generation(rig, rig.record)
    _take_lease(rig, rig.record, duration_ms=600_000, generation=generation)
    _stage(rig, rig.record)
    _check(rig, rig.record)
    arm = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert arm.status_code == 200, arm.text[:500]
    sessions: SessionStore = rig.app.state.ui_sessions
    held = sessions.held_lease(rig.record.session_id, _BENCH)
    assert held is not None
    renew = _post(
        rig,
        f"/ui/leases/{held.lease_id}/renewals",
        rig.record,
        data={"duration_ms": "5000"},
    )
    assert renew.status_code == 200, renew.text[:500]
    calls_start = _spy(rig, "run_start")
    response = _confirm(rig, generation)
    assert response.status_code == 403, response.text[:800]
    assert 'data-bw-failure="policy_denied"' in response.text
    assert "10000" in response.text
    assert "5000" in response.text
    assert "benchweave ui-login" in response.text
    assert not calls_start


def test_j_gw56_at_fire_the_clock_advanced_session_refuses(energise_rig: Any) -> None:
    """Arm J, session leg (§6.J), injected clock: armed with hours of
    session, the clock advanced to 5 000 ms of session remaining (the
    lease long expired — no live view, no lease leg) — the session is
    the shorter remainder and the fire refuses pre-send."""
    rig = energise_rig
    generation = _generation(rig, rig.record)
    _take_lease(rig, rig.record, duration_ms=600_000, generation=generation)
    _stage(rig, rig.record)
    _check(rig, rig.record)
    arm = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert arm.status_code == 200, arm.text[:500]
    rig.clock.advance(3_595)  # 3 600 s session minus 5 s
    calls_start = _spy(rig, "run_start")
    response = _confirm(rig, generation)
    assert response.status_code == 403, response.text[:800]
    assert 'data-bw-failure="policy_denied"' in response.text
    assert "10000" in response.text
    assert "5000" in response.text
    assert "benchweave ui-login" in response.text
    assert not calls_start


def test_j_gw56_fire_boundary_equal_is_allowed(energise_rig: Any) -> None:
    """Arm J boundary (§6.J): the bound exactly equal to the attention
    remainder at FIRE is allowed — the post sends and the seam decides
    (here: it accepts, the run starts)."""
    rig = energise_rig
    generation = _generation(rig, rig.record)
    _take_lease(rig, rig.record, duration_ms=10_000, generation=generation)
    _stage(rig, rig.record)
    _check(rig, rig.record)
    arm = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert arm.status_code == 200, arm.text[:500]
    response = _confirm(rig, generation)
    assert response.status_code == 200, response.text[:800]
    assert 'data-bw-run-started=' in response.text


# --- GW-53's de-energising class (arm H's second half) --------------------------


@pytest.fixture()
def deenergise_rig(tmp_path: Any) -> Any:
    """The explicit de-energising lattice: manual + ``enabled: false``.
    One action, never confirmed (§E.1 renders no confirm pattern)."""
    clock = _Clock()
    lattice_dir, binding_sha = author_g3b_lattice(
        tmp_path, mode="manual", enabled=False, request_id=_BINDING_REQUEST_ID
    )
    app = _compose(tmp_path, "g3b-deenergise", clock, lattice_dir)
    with TestClient(app, base_url=_CLIENT_BASE) as client:
        record = _session(app, scopes=CONTROL)
        yield SimpleNamespace(
            app=app,
            client=client,
            clock=clock,
            binding_sha=binding_sha,
            record=record,
        )


def test_h_deenergising_renders_no_confirm_pattern(deenergise_rig: Any) -> None:
    """Arm H's second half (§6.H): the de-energising staged set renders
    the ONE-action start — no armed confirm pattern, no arm control —
    and its start is never gated by protection-active in the
    presentation (GW-53/R-DEENERGISE-1)."""
    rig = deenergise_rig
    _stage(rig, rig.record)
    _check(rig, rig.record)
    response = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert response.status_code == 400, response.text[:500]
    assert 'data-bw-failure="invalid_request"' in response.text
    page = _get(rig, f"/ui/benches/{_BENCH}", rig.record)
    assert 'data-bw-staged="true"' in page.text
    assert 'data-bw-confirm="armed"' not in page.text
    assert "Arm staged set" not in page.text
    assert 'data-bw-disabled-reason="protection-active"' not in page.text
