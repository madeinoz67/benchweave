"""The G4 failed/unknown inhibited state (issue #305, design record
§2.4, acceptance arm C) over a REAL composed gateway with a frozen
clock — the explicit record, the §B.1 critical persistent alert, the
apply disable until per-session acknowledgement, submit staying enabled
(the contract's own reconciliation route), and state sourcing from the
record.

The alert/disable renderers landed with commit 3 and are policed here
for the first time; their RED controls are the design's named
mutations (remove the alert computation; remove the disable), run
after GREEN. The acknowledgement route itself REDs naturally (404
before it exists).
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.testclient import TestClient
from ui_gateway_support import FIXTURES, LIMITS, NOW_EPOCH, SECRET, put_approval

from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.sessions import SessionStore
from benchweave.state.store import Store

_BENCH = "sim-bench"
_CLIENT_BASE = "http://testserver:8125"
ADMIN = frozenset({"stg:observe", "stg:control", "stg:admin"})


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
def inhibited_rig(tmp_path: Any) -> Any:
    clock = _Clock()
    app = _compose(tmp_path, "g4-inhibited", clock)
    with TestClient(app, base_url=_CLIENT_BASE) as client:
        record = _session(app, scopes=ADMIN)
        yield SimpleNamespace(
            app=app, client=client, clock=clock, record=record
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


def _get(rig: Any, path: str) -> Any:
    return rig.client.get(
        path, cookies={"bw_session": rig.record.session_id}, follow_redirects=False
    )


def _post(rig: Any, path: str, data: dict[str, str]) -> Any:
    return rig.client.post(
        path,
        cookies={"bw_session": rig.record.session_id},
        data=data,
        headers={"X-CSRF-Token": rig.record.csrf_token},
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


def _submit(rig: Any, **overrides: str) -> str:
    """File one change as the admin session and return ITS change id —
    the new row, derived by diffing the store (the region lists every
    indexed change sorted, so a first-match regex returns the WRONG id
    on a second submit; caught by the two-change C1 arms)."""
    before = {row[0] for row in _change_rows(rig)}
    response = _post(rig, f"/ui/benches/{_BENCH}/changes", _form(**overrides))
    assert response.status_code == 200, response.text[:500]
    new = {row[0] for row in _change_rows(rig)} - before
    assert len(new) == 1, f"expected exactly one new change row: {sorted(new)}"
    return new.pop()


def _failed_apply(rig: Any, change_id: str, *, valid: bool = False) -> Any:
    """Load a binding independent approval and apply — the
    decided-refusal seed: by default the garbage token fails closed at
    the token check (unauthenticated, recorded failed); ``valid=True``
    sends the REAL token so the refusal the test names happens further
    in (C1's not_ready via a live lease, C2's crash inside the
    dispatch)."""
    ref, token = put_approval(rig.app.state.g4_content, change_id=change_id)
    loaded = _post(
        rig,
        f"/ui/changes/{change_id}/approval",
        {
            "approval_sha256": ref["sha256"],
            "approval_id": ref["id"],
            "approval_version": ref["version"],
        },
    )
    assert loaded.status_code == 200, loaded.text[:500]
    return _post(
        rig,
        f"/ui/changes/{change_id}/apply",
        {
            "request_id": "ui-g4apply0001",
            "approver_token": token if valid else "not-a-token",
        },
    )


def _set_state(rig: Any, change_id: str, state: str) -> None:
    """C3's mutator: move the STORE row's state directly, between
    renders — the rendered state must follow the record."""
    connection = sqlite3.connect(rig.app.state.g4_db_path)
    try:
        connection.execute(
            "UPDATE changes SET state = ? WHERE change_id = ?", (state, change_id)
        )
        connection.commit()
    finally:
        connection.close()


# --- C1: a decided failure renders the inhibited state -------------------------------


def test_decided_failure_renders_the_persistent_alert(inhibited_rig: Any) -> None:
    """A live lease + a configuration_activation apply: the seam refuses
    not_ready, the change records failed, and the bench region renders
    the §B.1 critical persistent alert naming the change, its state and
    ``reasons[0]`` verbatim, the reconciliation route, and the
    acknowledge affordance (the REGION is the acknowledgement surface)."""
    rig = inhibited_rig
    operations: Any = rig.app.state.ui_operations
    operations.lease_create(
        Identity("lease-op", "stg", frozenset({"stg:control"}), NOW_EPOCH + 3600),
        _BENCH,
        "lease-req-1",
        1,
        60000,
    )
    change_id = _submit(rig, kind="configuration_activation")
    response = _failed_apply(rig, change_id, valid=True)
    assert response.status_code == 409, response.text[:500]
    assert 'data-bw-failure="not_ready"' in response.text
    assert _change_rows(rig) == [(change_id, "failed")]
    region = _get(rig, f"/ui/benches/{_BENCH}")
    assert region.status_code == 200, region.text[:500]
    assert 'data-severity="critical"' in region.text
    assert f"Change {change_id} failed" in region.text
    assert "never re-apply" in region.text
    assert f'hx-post="/ui/changes/{change_id}/acknowledgements"' in region.text
    assert "data-bw-change-acknowledge" in region.text


def test_the_change_page_alert_is_informational_only(inhibited_rig: Any) -> None:
    """The ruled deviation: the change page renders the same alert (the
    explicit record with reasons[0] verbatim) but carries NO acknowledge
    affordance — acknowledgement is a region action."""
    rig = inhibited_rig
    change_id = _submit(rig)
    response = _failed_apply(rig, change_id)
    assert "unauthenticated" in response.text
    page = _get(rig, f"/ui/changes/{change_id}")
    assert page.status_code == 200, page.text[:500]
    assert 'data-severity="critical"' in page.text
    assert "data-bw-change-reasons" in page.text
    assert "acknowledgements" not in page.text


def test_inhibition_disables_apply_and_keeps_submit_enabled(
    inhibited_rig: Any,
) -> None:
    """While an unacknowledged failed change holds the bench: a proposed
    change's region row and workspace render the disabled apply control
    under ``no-authority`` naming the blocking change — and submit stays
    enabled (filing a new change is the contract's own reconciliation
    route; disabling it would block the correction)."""
    rig = inhibited_rig
    failed = _submit(rig, reason="the failing one")
    _failed_apply(rig, failed)
    proposed = _submit(rig, reason="the correction", request_id="ui-g4submit0002")
    region = _get(rig, f"/ui/benches/{_BENCH}")
    assert region.status_code == 200
    assert "data-bw-change-inhibited" in region.text
    assert 'data-bw-disabled-reason="no-authority"' in region.text
    assert failed in region.text
    # submit stays armed
    assert 'hx-post="/ui/benches/sim-bench/changes"' in region.text
    workspace = _get(rig, f"/ui/changes/{proposed}")
    assert workspace.status_code == 200
    assert "data-bw-change-inhibited" in workspace.text


def test_acknowledge_clears_the_alert_and_lifts_the_disables(
    inhibited_rig: Any,
) -> None:
    """POST the acknowledgement (session-layer, no seam call): the
    response re-renders the region with the alert gone and the disable
    lifted — and a fresh GET agrees (server-side session state)."""
    rig = inhibited_rig
    failed = _submit(rig)
    _failed_apply(rig, failed)
    proposed = _submit(rig, reason="the correction", request_id="ui-g4submit0002")
    acknowledged = _post(rig, f"/ui/changes/{failed}/acknowledgements", {})
    assert acknowledged.status_code == 200, acknowledged.text[:500]
    assert 'data-severity="critical"' not in acknowledged.text
    assert "data-bw-change-inhibited" not in acknowledged.text
    assert 'data-bw-disabled-reason="no-authority"' not in acknowledged.text
    assert proposed in acknowledged.text  # the healthy region still lists it
    after = _get(rig, f"/ui/benches/{_BENCH}")
    assert 'data-severity="critical"' not in after.text
    # the gateway record never changed
    assert _change_rows(rig) == sorted(
        [(failed, "failed"), (proposed, "proposed")]
    )


def test_the_alert_persists_across_reloads(inhibited_rig: Any) -> None:
    """The alert is persistent-until-resolved (§B.1): page reloads
    before the acknowledgement re-render it — server-side session
    state, no client-side clearing."""
    rig = inhibited_rig
    failed = _submit(rig)
    _failed_apply(rig, failed)
    first = _get(rig, f"/ui/benches/{_BENCH}")
    second = _get(rig, f"/ui/benches/{_BENCH}")
    assert 'data-severity="critical"' in first.text
    assert 'data-severity="critical"' in second.text
    assert f'hx-post="/ui/changes/{failed}/acknowledgements"' in second.text


def test_acknowledging_a_change_this_session_never_indexed_is_not_found(
    inhibited_rig: Any,
) -> None:
    """A change outside this session's index has nothing to acknowledge:
    the honest ``not_found`` row (the session-layer answer)."""
    rig = inhibited_rig
    response = _post(rig, "/ui/changes/chg-never-indexed/acknowledgements", {})
    assert response.status_code == 404, response.text[:500]
    assert 'data-bw-failure="not_found"' in response.text


def test_acknowledging_a_proposed_change_refuses_and_cannot_silence_a_future_alert(
    inhibited_rig: Any,
) -> None:
    """The acknowledgement is the reconciliation of a TERMINAL record
    (the refute fold, F5): acknowledging a change that is still
    ``proposed`` refuses ``invalid_request`` — there is nothing to
    acknowledge yet. Pre-fold, the route marked the view silently, so a
    forged early ack permanently silenced the alert the change's LATER
    failure should raise."""
    rig = inhibited_rig
    change_id = _submit(rig)
    too_early = _post(rig, f"/ui/changes/{change_id}/acknowledgements", {})
    assert too_early.status_code == 400, too_early.text[:500]
    assert 'data-bw-failure="invalid_request"' in too_early.text
    # The refusal marked nothing: the later failure's alert renders.
    _failed_apply(rig, change_id)
    region = _get(rig, f"/ui/benches/{_BENCH}")
    assert 'data-severity="critical"' in region.text, region.text[:500]
    assert f"Change {change_id} failed" in region.text


def test_submit_replay_preserves_the_acknowledgement(inhibited_rig: Any) -> None:
    """The P1 sequence (the refute fold, F3): the §9 replay of the
    original submit form returns the ORIGINAL change — the handler
    re-indexes only what is new. A fresh view wiped the operator's
    acknowledgement and resurrected the GW-72 alert over a change this
    session had already reconciled (the browser-back shape)."""
    rig = inhibited_rig
    failed = _submit(rig)
    _failed_apply(rig, failed)
    acknowledged = _post(rig, f"/ui/changes/{failed}/acknowledgements", {})
    assert acknowledged.status_code == 200, acknowledged.text[:500]
    assert 'data-severity="critical"' not in acknowledged.text
    # Browser-back: the original form replays; §9 returns the same change.
    replay = _post(rig, f"/ui/benches/{_BENCH}/changes", _form())
    assert replay.status_code == 200, replay.text[:500]
    assert 'data-bw-change-state="failed"' in replay.text
    # The acknowledgement survived: no resurrected alert, here or on a
    # fresh render.
    assert 'data-severity="critical"' not in replay.text
    after = _get(rig, f"/ui/benches/{_BENCH}")
    assert 'data-severity="critical"' not in after.text


# --- C2: an unknown change from an undecided crash ------------------------------------


def test_an_unknown_change_from_a_crash_inhibits_the_same_way(
    inhibited_rig: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash raised inside the seam's dispatch (the induced-crash
    posture): the ``unavailable`` row renders, the change records
    ``unknown``, and the same alert/disable/acknowledge arms hold — the
    guidance naming the contract's route (a NEW change if warranted;
    never re-apply)."""
    rig = inhibited_rig
    change_id = _submit(rig)

    def power_loss(bench_id: str, now: str) -> int:
        raise RuntimeError("power lost mid-apply")

    monkeypatch.setattr(rig.app.state.g4_store, "bump_generation", power_loss)
    response = _failed_apply(rig, change_id, valid=True)
    assert response.status_code == 503, response.text[:500]
    assert 'data-bw-failure="unavailable"' in response.text
    assert _change_rows(rig) == [(change_id, "unknown")]
    region = _get(rig, f"/ui/benches/{_BENCH}")
    assert 'data-severity="critical"' in region.text
    assert f"Change {change_id} unknown" in region.text
    assert "never re-apply" in region.text
    acknowledged = _post(rig, f"/ui/changes/{change_id}/acknowledgements", {})
    assert acknowledged.status_code == 200
    assert 'data-severity="critical"' not in acknowledged.text


# --- C3: the rendered state follows the record, never the index -----------------------


def test_the_state_follows_the_record_not_the_index(inhibited_rig: Any) -> None:
    """Move the STORE row's state between renders: the alert's presence
    and its named state follow ``change_get`` — the index caches
    nothing."""
    rig = inhibited_rig
    change_id = _submit(rig)
    _failed_apply(rig, change_id)
    assert 'data-severity="critical"' in _get(rig, f"/ui/benches/{_BENCH}").text
    _set_state(rig, change_id, "applied")
    recovered = _get(rig, f"/ui/benches/{_BENCH}")
    assert 'data-severity="critical"' not in recovered.text
    assert f'href="/ui/changes/{change_id}"' in recovered.text
    _set_state(rig, change_id, "unknown")
    flipped = _get(rig, f"/ui/benches/{_BENCH}")
    assert 'data-severity="critical"' in flipped.text
    assert f"Change {change_id} unknown" in flipped.text
