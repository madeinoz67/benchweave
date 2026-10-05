"""The G4 submit + review surface (issue #305, design record §2.2/§2.5,
acceptance arms A, D-submit, E) over a REAL composed gateway with a
frozen clock — the G3b rig shape.

Each behavior was proven RED before its implementation (the verbatim
failure text rides the commit message and the run report); the §9
mechanism arm carries its own mutation proof after GREEN (the handler
mints per POST → the one-row assertion fails — the design's named RED
control).
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.testclient import TestClient
from ui_gateway_support import FIXTURES, LIMITS, NOW_EPOCH, SECRET

from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.sessions import SessionStore
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
    app.state.g4_db_path = str(data_dir / f"state-{name}.sqlite")
    return app


@pytest.fixture()
def admin_rig(tmp_path: Any) -> Any:
    clock = _Clock()
    app = _compose(tmp_path, "g4-submit", clock)
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


# --- the region renders (bench page embed) -----------------------------------------


def test_admin_region_renders_on_the_bench_page(admin_rig: Any) -> None:
    """§F wire pins: the region section, the submit form with its hidden
    §9 id, the closed kind select, the 64-hex pattern on the digest
    field, the required reason — every form attribute the browser lane
    will re-prove."""
    rig = admin_rig
    response = _get(rig, f"/ui/benches/{_BENCH}", rig.record)
    assert response.status_code == 200, response.text[:500]
    assert 'data-bw-admin aria-label="Bench administration"' in response.text
    assert 'hx-post="/ui/benches/sim-bench/changes"' in response.text
    assert 'name="request_id"' in response.text
    for kind in ("trip_reset", "configuration_activation", "package_admission"):
        assert f'<option value="{kind}">' in response.text
    assert 'pattern="[0-9a-f]{64}"' in response.text
    assert 'name="reason" type="text" required minlength="1"' in response.text
    assert 'name="expected_generation" type="number"' in response.text
    assert 'data-bw-change-none' in response.text  # no rows yet


def test_observe_session_renders_the_disabled_submit(admin_rig: Any) -> None:
    """§2.2's non-admin shape: the admin region renders with its submit
    control disabled under §C.2's ``no-authority`` — and no submit form
    (a disabled control, never a live affordance)."""
    rig = admin_rig
    response = _get(rig, f"/ui/benches/{_BENCH}", rig.observe)
    assert response.status_code == 200
    assert 'data-bw-admin aria-label="Bench administration"' in response.text
    region = response.text.split('data-bw-admin aria-label="Bench administration"', 1)[1]
    region = region.split("</section>", 1)[0]
    assert 'data-bw-disabled-reason="no-authority"' in region
    assert 'hx-post="/ui/benches/sim-bench/changes"' not in region


# --- arm A: submit (GW-70) ----------------------------------------------------------


def test_submit_records_the_change_and_the_region_shows_it(admin_rig: Any) -> None:
    """A successful submit re-renders the region with the change's row
    (state=proposed), its review link, the two-phase statement — and the
    store holds exactly one change row."""
    rig = admin_rig
    response = _post(rig, f"/ui/benches/{_BENCH}/changes", rig.record, _form())
    assert response.status_code == 200, response.text[:800]
    assert 'data-bw-change-state="proposed"' in response.text
    assert 'href="/ui/changes/chg-' in response.text
    assert "data-bw-two-phase-note" in response.text
    assert "independent approval" in response.text
    assert len(_change_rows(rig)) == 1


def test_resubmit_the_same_form_replays_one_change(admin_rig: Any) -> None:
    """The §9 replay (the double-click shape): the same form — the same
    request id — returns the SAME change; still one row. RED control:
    a handler that mints the id per POST fails this arm (two ids, two
    rows) — proven by mutation after GREEN."""
    rig = admin_rig
    first = _post(rig, f"/ui/benches/{_BENCH}/changes", rig.record, _form())
    second = _post(rig, f"/ui/benches/{_BENCH}/changes", rig.record, _form())
    assert first.status_code == 200 and second.status_code == 200
    import re

    ids = re.findall(r'data-bw-change-id="(chg-[0-9a-f]+)"', first.text + second.text)
    assert len(set(ids)) == 1, f"two change ids from one form: {ids}"
    rows = _change_rows(rig)
    assert len(rows) == 1, f"the replay filed a second row: {rows}"


def test_same_request_id_different_body_conflicts(admin_rig: Any) -> None:
    """GW-11, no softening: the §9 key with a different candidate is the
    conflict row."""
    rig = admin_rig
    _post(rig, f"/ui/benches/{_BENCH}/changes", rig.record, _form())
    response = _post(
        rig, f"/ui/benches/{_BENCH}/changes", rig.record, _form(reason="different")
    )
    assert response.status_code == 409, response.text[:500]
    assert 'data-bw-failure="conflict"' in response.text


def test_forged_post_from_observe_renders_the_seam_forbidden(admin_rig: Any) -> None:
    """The disabled shape does not gate: a direct POST reaches the seam
    and its ``forbidden`` row renders — the honest authority answer."""
    rig = admin_rig
    response = _post(rig, f"/ui/benches/{_BENCH}/changes", rig.observe, _form())
    assert response.status_code == 403, response.text[:500]
    assert 'data-bw-failure="forbidden"' in response.text
    assert len(_change_rows(rig)) == 0


# --- the review page (GW-70's read half) ---------------------------------------------


def test_review_page_renders_the_ten_field_record(admin_rig: Any) -> None:
    rig = admin_rig
    submitted = _post(rig, f"/ui/benches/{_BENCH}/changes", rig.record, _form())
    import re

    match = re.search(r"/ui/changes/(chg-[0-9a-f]+)", submitted.text)
    assert match is not None, submitted.text[:500]
    change_id = match.group(1)
    page = _get(rig, f"/ui/changes/{change_id}", rig.record)
    assert page.status_code == 200, page.text[:500]
    assert f'data-bw-change-id="{change_id}"' in page.text
    assert 'data-bw-change-bench-id' in page.text
    assert ">trip_reset<" in page.text
    assert 'data-bw-change-state="proposed"' in page.text
    assert "reset after a clean bench" in page.text
    assert "data-bw-change-generation" in page.text
    assert "data-bw-change-created_at" in page.text
    assert "data-bw-change-updated_at" in page.text
    # The target ref's three parts render (the catalog's closed shape).
    assert ("0" * 64) in page.text


def test_review_page_unknown_change_renders_not_found(admin_rig: Any) -> None:
    rig = admin_rig
    page = _get(rig, "/ui/changes/chg-absent", rig.record)
    assert page.status_code == 404, page.text[:500]
    assert 'data-bw-failure="not_found"' in page.text


def _admin_region_of(text: str) -> str:
    """The admin region's own markup — the assertion scope for the
    literal-``None`` arms (the rest of the bench page is out of scope)."""
    region = text.split('data-bw-admin aria-label="Bench administration"', 1)[1]
    return region.split("</section>", 1)[0]


def test_the_region_renders_no_literal_none(admin_rig: Any) -> None:
    """Jinja prints an explicit ``None`` as the literal text "None"
    (the environment sets no finalize): the healthy region — no alert,
    no inhibited rows — must render neither slot (the refute fold, F6;
    pre-fold, every healthy page carried a bare "None" line)."""
    rig = admin_rig
    healthy = _get(rig, f"/ui/benches/{_BENCH}", rig.record)
    assert healthy.status_code == 200
    assert "None" not in _admin_region_of(healthy.text)
    # A proposed change without inhibition exercises the row slot too.
    _post(rig, f"/ui/benches/{_BENCH}/changes", rig.record, _form())
    with_change = _get(rig, f"/ui/benches/{_BENCH}", rig.record)
    assert with_change.status_code == 200
    assert "None" not in _admin_region_of(with_change.text)
    # The observe shape renders the region with no alert either.
    observe = _get(rig, f"/ui/benches/{_BENCH}", rig.observe)
    assert observe.status_code == 200
    assert "None" not in _admin_region_of(observe.text)


def test_the_change_page_renders_no_literal_none(admin_rig: Any) -> None:
    """The same hunt over the change page (its alert and workspace slots
    carry ``None`` on the healthy render — guarded there already; this
    arm pins the absence so a future unguarded slot reds)."""
    rig = admin_rig
    submitted = _post(rig, f"/ui/benches/{_BENCH}/changes", rig.record, _form())
    import re

    match = re.search(r"/ui/changes/(chg-[0-9a-f]+)", submitted.text)
    assert match is not None, submitted.text[:500]
    page = _get(rig, f"/ui/changes/{match.group(1)}", rig.record)
    assert page.status_code == 200
    assert "None" not in page.text


# --- arm D (submit half): the change-honest no-response variant ----------------------


def test_submit_no_response_renders_the_change_reconcile(
    admin_rig: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An induced non-``OperationFailure`` on the submit call: the §C.3
    no-response row, sent status UNKNOWN, and the CHANGE-honest
    reconcile action — resubmit the identical form, never run_find's
    link (change keys are invisible to it)."""
    rig = admin_rig
    operations: Any = rig.app.state.ui_operations

    def _crash(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("induced: no interface answer")

    monkeypatch.setattr(operations, "change_submit", _crash)
    response = _post(rig, f"/ui/benches/{_BENCH}/changes", rig.record, _form())
    assert response.status_code == 504, response.text[:500]
    assert "No interface answer arrived" in response.text
    assert "UNKNOWN" in response.text
    assert "resubmit" in response.text
    # The run_find reconcile link would be a lie for a change submit.
    assert "/ui/requests/" not in response.text
    assert len(_change_rows(rig)) == 0


def test_submit_no_response_reconcile_is_executable_from_the_refusal_body(
    admin_rig: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reconcile action is SELF-CONTAINED (the refute fold, F4):
    the no-response refusal body carries its own resubmit form — the
    §9 request id and the staged fields hidden, one button. Prose
    advice alone is unexecutable: htmx's outerHTML swap already
    destroyed the original form, and every fresh render mints a NEW
    request id. Posting the carried form's fields back must return the
    ORIGINAL change (the D-arm's substance, now executable from the
    surface it renders on)."""
    import re

    rig = admin_rig
    operations: Any = rig.app.state.ui_operations
    # The original submit LANDS (the §9 key is recorded server-side)...
    landed = _post(rig, f"/ui/benches/{_BENCH}/changes", rig.record, _form())
    assert landed.status_code == 200, landed.text[:500]
    rows_before = _change_rows(rig)
    assert len(rows_before) == 1

    def _crash(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("induced: no interface answer")

    # ...then the transport dies on the replay: no interface answer.
    monkeypatch.setattr(operations, "change_submit", _crash)
    replay = _post(rig, f"/ui/benches/{_BENCH}/changes", rig.record, _form())
    assert replay.status_code == 504, replay.text[:500]
    assert "data-bw-change-resubmit" in replay.text, replay.text[:500]
    assert f'hx-post="/ui/benches/{_BENCH}/changes"' in replay.text
    fields = dict(
        re.findall(
            r'<input type="hidden" name="([^"]+)" value="([^"]*)"', replay.text
        )
    )
    assert fields.get("request_id") == "ui-g4submit0001", fields
    assert fields.get("kind") == "trip_reset", fields
    assert fields.get("target_sha256") == "0" * 64, fields
    assert fields.get("expected_generation") == "1", fields
    assert fields.get("reason") == "reset after a clean bench", fields

    # Posting the carried form back: §9 returns the ORIGINAL change.
    monkeypatch.undo()
    resubmitted = _post(
        rig, f"/ui/benches/{_BENCH}/changes", rig.record, fields
    )
    assert resubmitted.status_code == 200, resubmitted.text[:500]
    assert _change_rows(rig) == rows_before
    ids = re.findall(r'data-bw-change-id="(chg-[0-9a-f]+)"', resubmitted.text)
    assert set(ids) == {rows_before[0][0]}, ids
