"""The G4 approval workspace + apply flow (issue #305, design record
§2.3, acceptance arm B + the apply half of D) over a REAL composed
gateway with a frozen clock — the G3b rig shape. The approval pair is
constructed out of band (``put_approval``, the seam suite's helper
lifted to the shared support module): no gateway surface mints the
applier's approval, and neither does the UI.

Each behavior was proven RED before its implementation (the verbatim
failure text rides the commit message); the fire-time guard carries its
own mutation proof after GREEN (trust the stored view instead of the
fresh document read → the no-call spy arm fails — the design's named
RED control).
"""

from __future__ import annotations

import re
import sqlite3
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.testclient import TestClient
from ui_gateway_support import FIXTURES, LIMITS, NOW_EPOCH, SECRET, put_approval

from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.sessions import ApprovalView, SessionStore
from benchweave.state.store import Store

_BENCH = "sim-bench"
_CLIENT_BASE = "http://testserver:8125"
ADMIN = frozenset({"stg:observe", "stg:control", "stg:admin"})
OBSERVE = frozenset({"stg:observe"})


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


def _compose(data_dir: Any, name: str, clock: _Clock) -> Any:
    store = Store.open(str(data_dir / f"state-{name}.sqlite"), check_same_thread=False)
    content = ContentStore(store)
    app = create_app(
        store=store,
        content=content,
        secret=SECRET,
        limits=dict(LIMITS),
        gateway_id="ui-test",
        fixtures_dir=FIXTURES,
        now_iso=clock.iso,
        now_epoch=clock.epoch_s,
    )
    app.state.g4_store = store
    app.state.g4_content = content
    app.state.g4_db_path = str(data_dir / f"state-{name}.sqlite")
    return app


@pytest.fixture()
def apply_rig(tmp_path: Any) -> Any:
    clock = _Clock()
    app = _compose(tmp_path, "g4-apply", clock)
    with TestClient(app, base_url=_CLIENT_BASE) as client:
        record = _session(app, scopes=ADMIN)
        observe = _session(app, principal="watcher", scopes=OBSERVE)
        yield SimpleNamespace(
            app=app, client=client, clock=clock, record=record, observe=observe
        )


def _session(
    app: Any, *, principal: str = "admin-op", scopes: frozenset[str]
) -> Any:
    sessions: SessionStore = app.state.ui_sessions
    code = sessions.mint_login_code(
        Identity(
            principal=principal,
            audience="stg",
            scopes=scopes,
            expires_at=NOW_EPOCH + 12 * 3600,
        )
    )
    return sessions.exchange(code)


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


def _form(**overrides: str) -> dict[str, str]:
    data = {
        "request_id": "ui-g4submit0001",
        "kind": "trip_reset",
        "target_id": "sim-bench",
        "target_version": "1",
        "target_sha256": "0" * 64,
        "expected_generation": "1",
        "reason": "reset after a clean bench",
    }
    data.update(overrides)
    return data


def _change_rows(rig: Any) -> list[tuple[str, str]]:
    """The store's change rows — the TEST's own enumeration (the seam has
    none; G4-D2). Read-only SQL over the rig's database file."""
    connection = sqlite3.connect(f"file:{rig.app.state.g4_db_path}?mode=ro", uri=True)
    try:
        return list(
            connection.execute("SELECT change_id, state FROM changes ORDER BY change_id")
        )
    finally:
        connection.close()


def _submit(rig: Any) -> str:
    """File one trip_reset as the admin session and return its change id
    (every apply arm's seed)."""
    response = _post(rig, f"/ui/benches/{_BENCH}/changes", rig.record, _form())
    assert response.status_code == 200, response.text[:500]
    match = re.search(r"/ui/changes/(chg-[0-9a-f]+)", response.text)
    assert match is not None, response.text[:500]
    return match.group(1)


def _load(rig: Any, change_id: str, ref: dict[str, str]) -> Any:
    """POST the approval pair's digest + ref fields to the workspace."""
    return _post(
        rig,
        f"/ui/changes/{change_id}/approval",
        rig.record,
        {
            "approval_sha256": ref["sha256"],
            "approval_id": ref["id"],
            "approval_version": ref["version"],
        },
    )


def _apply(rig: Any, change_id: str, token: str, **overrides: str) -> Any:
    data = {"request_id": "ui-g4apply0001", "approver_token": token}
    data.update(overrides)
    return _post(rig, f"/ui/changes/{change_id}/apply", rig.record, data)


def _spy_on_apply(rig: Any, monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Wrap ``change_apply`` with a call recorder (the pre-send arms'
    observable: the UI must not send what it can see the gateway would
    refuse)."""
    calls: list[Any] = []
    operations: Any = rig.app.state.ui_operations
    original = operations.change_apply

    def _spy(*args: Any, **kwargs: Any) -> Any:
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(operations, "change_apply", _spy)
    return calls


# --- step 1: the approval load (design §2.3) ----------------------------------------


def test_change_page_renders_the_approval_load_form(apply_rig: Any) -> None:
    """§F wire pins on the load form (no route without an affordance):
    the digest field's 64-hex pattern, the ref fields, its own POST
    target."""
    rig = apply_rig
    change_id = _submit(rig)
    page = _get(rig, f"/ui/changes/{change_id}", rig.record)
    assert page.status_code == 200, page.text[:500]
    assert "data-bw-approval-load" in page.text
    assert 'pattern="[0-9a-f]{64}"' in page.text
    assert 'name="approval_sha256"' in page.text
    assert 'name="approval_id"' in page.text
    assert 'name="approval_version"' in page.text
    assert f'hx-post="/ui/changes/{change_id}/approval"' in page.text


def test_approval_load_displays_the_approver_and_offers_apply(apply_rig: Any) -> None:
    """GW-71's presentation check made visible: a binding approval naming
    a DIFFERENT principal displays what the document says and offers the
    apply control (its form attributes wire-pinned)."""
    rig = apply_rig
    change_id = _submit(rig)
    ref, token = put_approval(rig.app.state.g4_content, change_id=change_id)
    assert token  # the detached token exists out of band; the UI never sees it
    response = _load(rig, change_id, ref)
    assert response.status_code == 200, response.text[:600]
    assert "data-bw-approval-facts" in response.text
    assert 'data-bw-approval-approver="approver-x"' in response.text
    assert 'data-bw-approval-binds="true"' in response.text
    assert f'href="/ui/documents/{ref["sha256"]}"' in response.text
    assert f'hx-post="/ui/changes/{change_id}/apply"' in response.text
    assert 'name="request_id"' in response.text
    assert 'name="approver_token" type="password"' in response.text
    assert 'autocomplete="off"' in response.text


def test_unstored_digest_renders_the_seam_not_found_row(apply_rig: Any) -> None:
    """An unstored digest is the gateway's own answer to render: the
    ``not_found`` row, no invented wording."""
    rig = apply_rig
    change_id = _submit(rig)
    response = _load(
        rig,
        change_id,
        {"sha256": "f" * 64, "id": "approval-x", "version": "1"},
    )
    assert response.status_code == 404, response.text[:500]
    assert 'data-bw-failure="not_found"' in response.text


def test_submit_replay_preserves_the_loaded_approval(apply_rig: Any) -> None:
    """The approval half of the replay rule (the refute fold, F3): the
    §9 replay re-indexes only what is new — the loaded approval
    survives the replay (a fresh view wiped it, sending the operator
    back to the paste step for nothing)."""
    rig = apply_rig
    change_id = _submit(rig)
    ref, token = put_approval(rig.app.state.g4_content, change_id=change_id)
    assert token
    loaded = _load(rig, change_id, ref)
    assert loaded.status_code == 200, loaded.text[:500]
    assert "data-bw-approval-facts" in loaded.text
    replay = _post(rig, f"/ui/benches/{_BENCH}/changes", rig.record, _form())
    assert replay.status_code == 200, replay.text[:500]
    page = _get(rig, f"/ui/changes/{change_id}", rig.record)
    assert page.status_code == 200, page.text[:500]
    assert "data-bw-approval-facts" in page.text
    assert 'data-bw-approval-approver="approver-x"' in page.text


# --- GW-71: self-approval is not offered ---------------------------------------------


def test_self_approval_is_not_offered(apply_rig: Any) -> None:
    """A binding approval naming the SESSION's own principal: the facts
    display, the apply control renders disabled under §C.2's
    ``no-authority`` with the independence text — never a live
    affordance."""
    rig = apply_rig
    change_id = _submit(rig)
    ref, _token = put_approval(
        rig.app.state.g4_content, change_id=change_id, approver="admin-op"
    )
    response = _load(rig, change_id, ref)
    assert response.status_code == 200, response.text[:600]
    assert 'data-bw-approval-approver="admin-op"' in response.text
    assert "data-bw-apply-control" in response.text
    assert 'data-bw-disabled-reason="no-authority"' in response.text
    assert "Independent approval" in response.text
    assert f'hx-post="/ui/changes/{change_id}/apply"' not in response.text


def test_self_approval_forged_post_is_refused_pre_send(
    apply_rig: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The disabled shape does not gate: a direct forged POST (the
    operator posts despite the control) is refused PRE-SEND — the spy
    asserts no ``change_apply`` call — rendering the same disabled shape;
    the seam never judged, so the record stays proposed."""
    rig = apply_rig
    change_id = _submit(rig)
    ref, token = put_approval(
        rig.app.state.g4_content, change_id=change_id, approver="admin-op"
    )
    loaded = _load(rig, change_id, ref)
    assert loaded.status_code == 200
    calls = _spy_on_apply(rig, monkeypatch)
    response = _apply(rig, change_id, token)
    assert response.status_code == 200, response.text[:600]
    assert 'data-bw-disabled-reason="no-authority"' in response.text
    assert "Independent approval" in response.text
    assert calls == [], "the UI sent a self-approval the gateway would refuse"
    assert _change_rows(rig) == [(change_id, "proposed")]


def test_non_binding_approval_is_not_offered_and_not_sendable(
    apply_rig: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An approval binding a DIFFERENT change (or generation) does not
    offer the control — the non-binding reason shows — and a forged POST
    is refused pre-send the same way."""
    rig = apply_rig
    change_id = _submit(rig)
    ref, token = put_approval(
        rig.app.state.g4_content, change_id="chg-not-this-one"
    )
    response = _load(rig, change_id, ref)
    assert response.status_code == 200, response.text[:600]
    assert 'data-bw-approval-binds="false"' in response.text
    assert 'data-bw-disabled-reason="invalid-staged-input"' in response.text
    assert f'hx-post="/ui/changes/{change_id}/apply"' not in response.text
    calls = _spy_on_apply(rig, monkeypatch)
    forged = _apply(rig, change_id, token)
    assert forged.status_code == 200, forged.text[:600]
    assert 'data-bw-disabled-reason="invalid-staged-input"' in forged.text
    assert calls == []
    assert _change_rows(rig) == [(change_id, "proposed")]


def test_the_fire_time_read_ignores_a_stale_session_view(
    apply_rig: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fire-time guard re-reads the approval document FRESH and
    re-derives the view — never trusting session memory: a forged view
    claiming an independent approval does not buy a send when the stored
    document names the session's own principal."""
    rig = apply_rig
    change_id = _submit(rig)
    ref, token = put_approval(
        rig.app.state.g4_content, change_id=change_id, approver="admin-op"
    )
    sessions: SessionStore = rig.app.state.ui_sessions
    sessions.record_change_approval(
        rig.record.session_id,
        change_id,
        ApprovalView(
            sha256=ref["sha256"],
            ref_id=ref["id"],
            ref_version=ref["version"],
            approver_principal="approver-x",
            policy_version="1",
            binds=True,
            bound_change_id=change_id,
            bound_generation=1,
        ),
    )
    calls = _spy_on_apply(rig, monkeypatch)
    response = _apply(rig, change_id, token)
    assert response.status_code == 200, response.text[:600]
    # the fresh read re-derived the view: the facts now name the session
    assert 'data-bw-approval-approver="admin-op"' in response.text
    assert 'data-bw-disabled-reason="no-authority"' in response.text
    assert calls == [], "the guard trusted session memory over the document"
    assert _change_rows(rig) == [(change_id, "proposed")]


# --- step 3: apply (GW-70's apply half, US9) ------------------------------------------


def test_apply_with_an_independent_approval_succeeds(apply_rig: Any) -> None:
    """US9: a binding approval naming a different principal applies — the
    workspace renders the applied record with the generation increment
    read fresh from the bench — and the approver token appears in no
    response byte."""
    rig = apply_rig
    change_id = _submit(rig)
    ref, token = put_approval(rig.app.state.g4_content, change_id=change_id)
    loaded = _load(rig, change_id, ref)
    assert loaded.status_code == 200
    response = _apply(rig, change_id, token)
    assert response.status_code == 200, response.text[:600]
    assert 'data-bw-change-applied="true"' in response.text
    assert "Generation 1 → 2" in response.text
    assert _change_rows(rig) == [(change_id, "applied")]
    assert token not in response.text
    assert token not in _get(rig, f"/ui/changes/{change_id}", rig.record).text
    assert token not in _get(rig, f"/ui/benches/{_BENCH}", rig.record).text


def test_a_second_apply_renders_the_two_phase_conflict(apply_rig: Any) -> None:
    """Apply has no §9 replay (R6): a re-apply of an applied change is
    the two-phase ``conflict`` row, unsoftened — and the record stays
    applied (a decided outcome is never overwritten)."""
    rig = apply_rig
    change_id = _submit(rig)
    ref, token = put_approval(rig.app.state.g4_content, change_id=change_id)
    _load(rig, change_id, ref)
    first = _apply(rig, change_id, token)
    assert first.status_code == 200, first.text[:600]
    second = _apply(rig, change_id, token)
    assert second.status_code == 409, second.text[:500]
    assert 'data-bw-failure="conflict"' in second.text
    assert _change_rows(rig) == [(change_id, "applied")]


def test_the_applied_change_page_claims_no_generation_increment(apply_rig: Any) -> None:
    """The GET change page never renders a generation increment for an
    applied change (the refute fold, F7): the change record stores no
    at-apply generation (the bump lands on the bench row), and the
    bench's CURRENT generation is not this change's outcome once later
    changes land — an increment paragraph on the page would be a false
    claim on a terminal record. The increment is the apply RESPONSE's
    claim alone (US9, ``data-bw-change-applied``); the page renders the
    terminal workspace with no increment."""
    rig = apply_rig
    change_id = _submit(rig)
    ref, token = put_approval(rig.app.state.g4_content, change_id=change_id)
    _load(rig, change_id, ref)
    applied = _apply(rig, change_id, token)
    assert applied.status_code == 200, applied.text[:600]
    assert "Generation 1 → 2" in applied.text  # US9 lives on the response
    page = _get(rig, f"/ui/changes/{change_id}", rig.record)
    assert page.status_code == 200, page.text[:500]
    assert 'data-bw-change-state="applied"' in page.text
    assert 'data-bw-change-applied-generation' not in page.text
    assert "Generation 1 → 2" not in page.text


def test_a_decided_refusal_records_failed_and_renders_its_row(
    apply_rig: Any,
) -> None:
    """A decided refusal (a garbage approver token: the UI's guards pass
    — binding, independent — and the seam judges) renders its §C.3 row
    and the change records ``failed``: the seam-answered refusal path."""
    rig = apply_rig
    change_id = _submit(rig)
    ref, _token = put_approval(rig.app.state.g4_content, change_id=change_id)
    _load(rig, change_id, ref)
    response = _apply(rig, change_id, "not-a-token")
    assert response.status_code == 401, response.text[:500]
    assert 'data-bw-failure="unauthenticated"' in response.text
    assert _change_rows(rig) == [(change_id, "failed")]


def test_apply_without_a_loaded_approval_is_refused_pre_send(
    apply_rig: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Form validation (no loaded approval in this session's view): the
    ``invalid_request`` row pre-send — the seam never judged, nothing
    records."""
    rig = apply_rig
    change_id = _submit(rig)
    ref, token = put_approval(rig.app.state.g4_content, change_id=change_id)
    assert ref
    calls = _spy_on_apply(rig, monkeypatch)
    response = _apply(rig, change_id, token)
    assert response.status_code == 400, response.text[:500]
    assert 'data-bw-failure="invalid_request"' in response.text
    assert calls == []
    assert _change_rows(rig) == [(change_id, "proposed")]


# --- the apply half of arm D: the no-response variant ---------------------------------


def test_apply_no_response_renders_the_change_reconcile(
    apply_rig: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An induced non-``OperationFailure`` on the apply call: §C.3's
    no-response row, sent status UNKNOWN, the reconcile action = the
    change page link, no retry action — and no run_find-shaped link (the
    run reconcile would be a lie here)."""
    rig = apply_rig
    change_id = _submit(rig)
    ref, token = put_approval(rig.app.state.g4_content, change_id=change_id)
    _load(rig, change_id, ref)

    def _crash(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("induced: no interface answer")

    operations: Any = rig.app.state.ui_operations
    monkeypatch.setattr(operations, "change_apply", _crash)
    response = _apply(rig, change_id, token)
    assert response.status_code == 504, response.text[:500]
    assert "No interface answer arrived" in response.text
    assert "UNKNOWN" in response.text
    assert f'href="/ui/changes/{change_id}"' in response.text
    assert "do not re-apply" in response.text
    assert "/ui/requests/" not in response.text
    # the seam never judged: nothing records, the state stays proposed
    assert _change_rows(rig) == [(change_id, "proposed")]


# --- the honest authority answers ------------------------------------------------------


def test_non_admin_change_page_renders_the_seam_forbidden(apply_rig: Any) -> None:
    """``change_get`` is admin-tier: a non-admin session's review page is
    the seam's own ``forbidden`` row — no UI gate pretends otherwise."""
    rig = apply_rig
    change_id = _submit(rig)
    page = _get(rig, f"/ui/changes/{change_id}", rig.observe)
    assert page.status_code == 403, page.text[:500]
    assert 'data-bw-failure="forbidden"' in page.text
