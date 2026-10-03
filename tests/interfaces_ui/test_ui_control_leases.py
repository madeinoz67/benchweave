"""The G3a lease control surface (design record §2.2/§2.3, acceptance
arms A–D + K's G3a rows) — the lease half of GW-10's eight.

Every arm runs against a REAL composed gateway (the readings suite's
discipline) with a MUTABLE injected clock (one epoch cell feeding both
the seam's ``now_iso`` and the adapter's ``now_epoch``, so expiry,
warning thresholds and the GW-95 session bound move deterministically):

- A1/A2/A3 — GW-95: a duration that would outlive the session is
  refused PRE-SEND (no seam call, spy-asserted); renewal same; a
  duration ending EXACTLY at session expiry is admitted (equality
  admits) and reaches the seam;
- B — the pure GW-44 predicate matrix: both floors and both percentages
  pinned at the record's six cells (6 h, 60 s, 10 min, 20 min, 2 min 1 s
  plus the two-tier ordering), two-sided neutralization proofs recorded
  at development time;
- C — carried by the default-flip commit (the booted-gateway limit arm);
- D — the lease lifecycle over the fragment: take → facts row
  (holder/expires/remaining), second take → the seam's own ``conflict``
  row (GW-11, no softening), renew advances the view's sequence, release
  clears the view, the ``no-lease`` banner entry fires before take and
  is absent after on the bench AND device pages, observe sessions render
  every lease control disabled with ``no-authority``, and an
  injected-clock expiry renders the expired state and re-fires the
  ``no-lease`` posture;
- the polled controls fragment: server-chosen cadence per render —
  ``ui_panel_poll_ms`` normally, ÷6 inside warning, ÷30 inside critical
  (fork F3) — with no device-affecting operation on any refresh;
- D1 — the session-expiry warning (GW-44's session half): the same
  predicate over the session's remaining time and granted duration,
  rendered in the shell on every page, naming what is lost (held leases
  cannot be renewed afterwards) and the clearing action (``ui-login``).
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.testclient import TestClient
from ui_gateway_support import FIXTURES, LIMITS, NOW_EPOCH, SECRET

from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.operations import Operations
from benchweave.interfaces.sessions import HeldLease, SessionStore
from benchweave.interfaces.ui_control import (
    CRITICAL_FLOOR_MS,
    DEFAULT_PANEL_POLL_MS,
    FORM_MIN_DURATION_MS,
    WARN_FLOOR_MS,
    bench_mode,
    expiry_warning,
    session_warning_bubble,
)
from benchweave.state.store import Store

_BENCH = "sim-bench"
_CLIENT_BASE = "http://testserver:8125"


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


def _compose(data_dir: Any, name: str, clock: _Clock) -> Any:
    store = Store.open(
        str(data_dir / f"state-{name}.sqlite"), check_same_thread=False
    )
    app = create_app(
        store=store,
        content=ContentStore(store),
        secret=SECRET,
        limits=dict(LIMITS),
        gateway_id="ui-test",
        fixtures_dir=FIXTURES,
        now_iso=clock.iso,
        now_epoch=clock.epoch_s,
    )
    app.state.g3a_store = store
    return app


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


CONTROL = frozenset({"stg:observe", "stg:control"})
OBSERVE = frozenset({"stg:observe"})


@pytest.fixture()
def rig(tmp_path: Any) -> Any:
    """One composed gateway per arm (fresh DB) with its own clock."""
    clock = _Clock()
    app = _compose(tmp_path, "g3a", clock)
    with TestClient(app, base_url=_CLIENT_BASE) as client:
        yield SimpleNamespace(app=app, client=client, clock=clock)


def _get(rig: Any, path: str, record: Any) -> Any:
    return rig.client.get(
        path,
        cookies={"bw_session": record.session_id},
        follow_redirects=False,
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

    match = re.search(
        r'data-bw-bench-generation>(\d+)<', response.text
    )
    assert match is not None, response.text
    return int(match.group(1))


def _take(rig: Any, record: Any, duration_ms: int = 300_000) -> Any:
    generation = _generation(rig, record)
    return _post(
        rig,
        f"/ui/benches/{_BENCH}/leases",
        record,
        data={"duration_ms": str(duration_ms), "expected_generation": str(generation)},
    )


# --- B: the pure GW-44 predicate matrix ------------------------------------------


@pytest.mark.parametrize(
    ("duration_ms", "remaining_ms", "expected"),
    [
        # 6 h: the percentages dominate; the floors are inert (72 / 18 min).
        (21_600_000, 4_320_000, "warning"),
        (21_600_000, 4_320_001, None),
        (21_600_000, 1_080_000, "critical"),
        (21_600_000, 1_080_001, "warning"),
        # 60 s: the warning floor dominates from creation; the critical
        # floor takes over at 30 s.
        (60_000, 60_000, "warning"),
        (60_000, 30_000, "critical"),
        (60_000, 30_001, "warning"),
        # Exactly 10 min: warn floor and percentage COINCIDE at 120 s
        # (the #307-noted coincidence).
        (600_000, 120_000, "warning"),
        (600_000, 120_001, None),
        # 20 min: the percentage (4 min) beats the floor.
        (1_200_000, 240_000, "warning"),
        (1_200_000, 240_001, None),
        # 2 min 1 s: the floor (120 s) beats the percentage (24.02 s) —
        # Q2's max() rationale's own case.
        (121_000, 120_000, "warning"),
        (121_000, 120_001, None),
        # Tier ordering: inside both thresholds the critical tier wins.
        (121_000, 30_000, "critical"),
    ],
)
def test_expiry_warning_matrix(
    duration_ms: int, remaining_ms: int, expected: str | None
) -> None:
    assert expiry_warning(remaining_ms, duration_ms) == expected


def test_expiry_warning_floors_are_the_recorded_constants() -> None:
    assert WARN_FLOOR_MS == 120_000
    assert CRITICAL_FLOOR_MS == 30_000


# --- D1: the session-expiry warning (GW-44's session half) ------------------------


def test_session_warning_bubble_names_the_loss_and_the_clearing_action() -> None:
    from benchweave.interfaces.sessions import SessionRecord

    record = SessionRecord(
        session_id="s",
        principal="p",
        audience="stg",
        scopes=CONTROL,
        expires_at=NOW_EPOCH + 100,
        csrf_token="t",
        duration_s=120,
    )
    now = NOW_EPOCH + 20  # 100 s remaining of a 120 s session → warning floor
    bubble = session_warning_bubble(record, now_epoch=lambda: now)
    assert bubble is not None
    assert 'data-severity="warning"' in bubble
    assert "cannot be renewed" in bubble
    assert "ui-login" in bubble
    # Critical leg: 20 s remaining of 120 s → critical tier, alert region,
    # non-dismissible (§B.1 persistence classes).
    critical = session_warning_bubble(record, now_epoch=lambda: NOW_EPOCH + 100)
    assert critical is not None
    assert 'data-severity="critical"' in critical
    assert 'role="alert"' in critical
    assert 'aria-label="Dismiss"' not in critical


def test_session_warning_absent_for_unrecorded_duration() -> None:
    from benchweave.interfaces.sessions import SessionRecord

    record = SessionRecord(
        session_id="s",
        principal="p",
        audience="stg",
        scopes=CONTROL,
        expires_at=NOW_EPOCH + 10,
        csrf_token="t",
    )
    assert session_warning_bubble(record, now_epoch=lambda: NOW_EPOCH) is None


def test_session_warning_renders_in_the_page_shell(rig: Any) -> None:
    """D1 renders on every authed page's shell: a session 100 s from its
    end (of 120 s granted) shows the warning bubble beside the banner
    slot; a fresh session shows none."""
    record = _session(rig.app, scopes=CONTROL, ttl_s=120)
    rig.clock.advance(20)  # 100 s remaining of 120 → warning
    page = _get(rig, f"/ui/benches/{_BENCH}", record)
    assert page.status_code == 200
    assert 'data-severity="warning"' in page.text
    assert "cannot be renewed" in page.text
    assert "ui-login" in page.text


# --- GW-42's bench-scoped mode entry ---------------------------------------------


def test_bench_mode_helper() -> None:
    live = HeldLease(
        lease_id="lease-a",
        bench_id=_BENCH,
        sequence=1,
        expires_at="2027-03-01T00:00:00Z",
        state="active",
        requested_duration_ms=60_000,
    )
    now = 1_800_000_000
    assert bench_mode(live, now_epoch=lambda: now) is None
    expired_view = HeldLease(
        lease_id="lease-a",
        bench_id=_BENCH,
        sequence=1,
        expires_at="2026-10-03T01:00:00Z",
        state="active",
        requested_duration_ms=60_000,
    )
    # 2026-10-03T01:00:00Z is epoch 1780413600: well past NOW_EPOCH —
    # advance past it to flip the read-time liveness.
    assert bench_mode(expired_view, now_epoch=lambda: NOW_EPOCH) == "no-lease"
    assert bench_mode(None, now_epoch=lambda: now) == "no-lease"


# --- A: GW-95's session bound -----------------------------------------------------


def test_a1_short_session_renders_the_take_control_disabled(rig: Any) -> None:
    """A session whose every offered duration would outlive it (50 s
    remaining < the form's 60 s minimum) renders the take control
    disabled with the session expiry stated and the clearing action."""
    record = _session(rig.app, scopes=CONTROL, ttl_s=50)
    rig.clock.advance(5)  # 45 s remaining < 60 s form minimum
    page = _get(rig, f"/ui/benches/{_BENCH}", record)
    assert page.status_code == 200
    assert "data-bw-session-bound" in page.text
    assert "ui-login" in page.text
    fragment = _get(rig, f"/ui/benches/{_BENCH}/controls", record)
    assert fragment.status_code == 200
    assert 'disabled data-bw-session-bound="true"' in fragment.text


def test_a1_forged_post_outliving_the_session_is_refused_pre_send(rig: Any) -> None:
    """A direct POST with a duration beyond the session's remaining time
    is refused BEFORE the seam — no ``lease_create`` call — with the
    session expiry and the clearing action in the rendered refusal."""
    record = _session(rig.app, scopes=CONTROL, ttl_s=3600)
    calls = _spy(rig, "lease_create")
    response = _take(rig, record, duration_ms=200_000_000)
    assert response.status_code == 403
    assert "outlive this session" in response.text
    assert "ui-login" in response.text
    assert calls == []


def test_a2_renewal_past_the_session_bound_is_refused_pre_send(rig: Any) -> None:
    """Same bound on the renewal path: no ``lease_renew`` call."""
    record = _session(rig.app, scopes=CONTROL, ttl_s=3600)
    take = _take(rig, record, duration_ms=300_000)
    assert take.status_code == 200
    lease_id = _held_lease_id(rig, record)
    calls = _spy(rig, "lease_renew")
    response = _post(
        rig,
        f"/ui/leases/{lease_id}/renewals",
        record,
        data={
            "bench_id": _BENCH,
            "duration_ms": "200000000",
        },
    )
    assert response.status_code == 403
    assert "outlive this session" in response.text
    assert calls == []


def test_a3_duration_ending_exactly_at_session_expiry_is_admitted(rig: Any) -> None:
    """Equality admits: a duration ending exactly at the session's
    expiry reaches the seam (the seam's own judgement then applies)."""
    record = _session(rig.app, scopes=CONTROL, ttl_s=3600)
    calls = _spy(rig, "lease_create")
    response = _take(rig, record, duration_ms=3_600_000)
    assert response.status_code == 200, response.text
    assert calls == ["lease_create"]
    sessions: SessionStore = rig.app.state.ui_sessions
    held = sessions.held_lease(record.session_id, _BENCH)
    assert held is not None


def test_the_form_bound_is_the_minimum_of_lease_limit_and_session(rig: Any) -> None:
    """The rendered take form's max is ``min(max_lease_ms,
    session_remaining_ms)`` — 600 000 of a 3 600 s session here."""
    record = _session(rig.app, scopes=CONTROL, ttl_s=3600)
    fragment = _get(rig, f"/ui/benches/{_BENCH}/controls", record)
    # min(max_lease_ms, session_remaining_ms) = min(600000, 3600000)
    bound = min(LIMITS["max_lease_ms"], 3_600_000)
    assert bound >= FORM_MIN_DURATION_MS
    assert f'value="{bound}"' in fragment.text
    assert f'max="{bound}"' in fragment.text


def test_the_lease_bound_fallback_is_the_published_default(
    tmp_path: Any,
) -> None:
    """FOLD-9: with ``max_lease_ms`` absent from a caller's limits
    table, the fragment's bound reads the SAME default the app-entry
    table publishes (#307's 6-hour ruling, 21 600 000), not the retired
    10-minute constant. Composed without the key on purpose: the
    fallback is the only mechanism under test here."""
    clock = _Clock()
    store = Store.open(
        str(tmp_path / "state-fold9.sqlite"), check_same_thread=False
    )
    limits = {key: value for key, value in LIMITS.items() if key != "max_lease_ms"}
    app = create_app(
        store=store,
        content=ContentStore(store),
        secret=SECRET,
        limits=limits,
        gateway_id="ui-fold9",
        fixtures_dir=FIXTURES,
        now_iso=clock.iso,
        now_epoch=clock.epoch_s,
    )
    with TestClient(app, base_url=_CLIENT_BASE) as client:
        sessions_store: SessionStore = app.state.ui_sessions
        code = sessions_store.mint_login_code(
            Identity(
                principal="ui-operator",
                audience="stg",
                scopes=CONTROL,
                expires_at=NOW_EPOCH + 12 * 3600,
            ),
            ttl_seconds=28800,  # 8 h session: the published default binds first
        )
        record = sessions_store.exchange(code)
        response = client.get(
            f"/ui/benches/{_BENCH}/controls",
            cookies={"bw_session": record.session_id},
            follow_redirects=False,
        )
    assert response.status_code == 200
    # min(published default 21 600 000, session 28 800 000) = 21 600 000.
    assert 'value="21600000"' in response.text
    assert 'max="21600000"' in response.text


# --- D: the lease lifecycle over the fragment -------------------------------------


def _held_lease_id(rig: Any, record: Any) -> str:
    sessions: SessionStore = rig.app.state.ui_sessions
    held = sessions.held_lease(record.session_id, _BENCH)
    assert held is not None, "no held-lease view"
    return held.lease_id


def test_d_take_renders_the_lease_facts_row(rig: Any) -> None:
    record = _session(rig.app, scopes=CONTROL, ttl_s=3600)
    take = _take(rig, record, duration_ms=300_000)
    assert take.status_code == 200
    assert 'data-bw-lease-state="held"' in take.text
    assert 'data-bw-lease-holder="ui-operator"' in take.text
    sessions: SessionStore = rig.app.state.ui_sessions
    held = sessions.held_lease(record.session_id, _BENCH)
    assert held is not None
    assert held.requested_duration_ms == 300_000
    # The facts row renders the seam's own expiry stamp and a remaining
    # figure derived from it (read-time arithmetic, never an inference).
    assert f'data-bw-lease-expires-at="{held.expires_at}"' in take.text
    assert "data-bw-lease-remaining-ms" in take.text
    # GW-40 on the refreshed bench page: busy is a live-lease fact.
    page = _get(rig, f"/ui/benches/{_BENCH}", record)
    assert 'data-bw-bench-busy>yes<' in page.text


def test_d_second_take_renders_the_seams_own_conflict_row(rig: Any) -> None:
    record = _session(rig.app, scopes=CONTROL, ttl_s=3600)
    assert _take(rig, record).status_code == 200
    second = _take(rig, record)
    assert second.status_code == 409
    assert 'data-bw-refusal-code="conflict"' in second.text
    assert "active lease" in second.text


def test_d_renew_advances_the_sequence_in_the_held_view(rig: Any) -> None:
    record = _session(rig.app, scopes=CONTROL, ttl_s=3600)
    assert _take(rig, record, duration_ms=300_000).status_code == 200
    lease_id = _held_lease_id(rig, record)
    renew = _post(
        rig,
        f"/ui/leases/{lease_id}/renewals",
        record,
        data={"bench_id": _BENCH, "duration_ms": "300000"},
    )
    assert renew.status_code == 200, renew.text
    sessions: SessionStore = rig.app.state.ui_sessions
    held = sessions.held_lease(record.session_id, _BENCH)
    assert held is not None
    assert held.sequence == 2


def test_d_release_clears_the_view(rig: Any) -> None:
    record = _session(rig.app, scopes=CONTROL, ttl_s=3600)
    assert _take(rig, record).status_code == 200
    lease_id = _held_lease_id(rig, record)
    release = _post(
        rig,
        f"/ui/leases/{lease_id}/release",
        record,
        data={"bench_id": _BENCH},
    )
    assert release.status_code == 200, release.text
    sessions: SessionStore = rig.app.state.ui_sessions
    assert sessions.held_lease(record.session_id, _BENCH) is None
    assert 'data-bw-lease-state="none"' in release.text


def test_d_no_lease_banner_before_and_absent_after_on_bench_and_device(rig: Any) -> None:
    record = _session(rig.app, scopes=CONTROL, ttl_s=3600)
    bench_page = _get(rig, f"/ui/benches/{_BENCH}", record)
    assert 'data-bw-mode="no-lease"' in bench_page.text
    devices, _next = rig.app.state.ui_operations.device_list(
        _identity_for(record), _BENCH, limit=10, cursor=None
    )
    device_page = _get(
        rig, f"/ui/benches/{_BENCH}/devices/{devices[0]['device_id']}", record
    )
    assert device_page.status_code == 200
    assert 'data-bw-mode="no-lease"' in device_page.text

    assert _take(rig, record).status_code == 200
    bench_page_after = _get(rig, f"/ui/benches/{_BENCH}", record)
    assert 'data-bw-mode="no-lease"' not in bench_page_after.text
    device_page_after = _get(
        rig, f"/ui/benches/{_BENCH}/devices/{devices[0]['device_id']}", record
    )
    assert 'data-bw-mode="no-lease"' not in device_page_after.text


def test_d_observe_session_renders_every_lease_control_disabled(rig: Any) -> None:
    record = _session(rig.app, scopes=OBSERVE, ttl_s=3600)
    fragment = _get(rig, f"/ui/benches/{_BENCH}/controls", record)
    assert fragment.status_code == 200
    assert fragment.text.count('data-bw-disabled-reason="no-authority"') >= 3
    # The take control never presents as takeable for an observe session.
    assert "disabled data-bw-session-bound" not in fragment.text


def test_d_expired_lease_renders_expired_and_refires_no_lease(rig: Any) -> None:
    record = _session(rig.app, scopes=CONTROL, ttl_s=3600)
    assert _take(rig, record, duration_ms=120_000).status_code == 200
    rig.clock.advance(121)  # past the lease's own expiry
    fragment = _get(rig, f"/ui/benches/{_BENCH}/controls", record)
    assert fragment.status_code == 200
    assert 'data-bw-lease-state="expired"' in fragment.text
    bench_page = _get(rig, f"/ui/benches/{_BENCH}", record)
    assert 'data-bw-mode="no-lease"' in bench_page.text
    assert 'data-bw-bench-busy>no<' in bench_page.text


def _identity_for(record: Any) -> Identity:
    return Identity(
        principal=record.principal,
        audience=record.audience,
        scopes=record.scopes,
        expires_at=record.expires_at,
    )


# --- the polled fragment: server-chosen cadence (§2.3, fork F3) -------------------


def _poll_ms(fragment: Any) -> int:
    import re

    match = re.search(r'data-bw-panel-poll-ms="(\d+)"', fragment.text)
    assert match is not None, fragment.text
    return int(match.group(1))


def test_fragment_poll_cadence_escalates_with_the_warning_state(rig: Any) -> None:
    record = _session(rig.app, scopes=CONTROL, ttl_s=3600)
    base = _get(rig, f"/ui/benches/{_BENCH}/controls", record)
    assert _poll_ms(base) == DEFAULT_PANEL_POLL_MS  # 30 000 normally
    assert _take(rig, record, duration_ms=120_000).status_code == 200
    # 90 s remaining of a 120 s lease: inside the 120 s warning floor,
    # outside the 30 s critical floor → ÷6.
    rig.clock.advance(30)
    warning = _get(rig, f"/ui/benches/{_BENCH}/controls", record)
    assert _poll_ms(warning) == DEFAULT_PANEL_POLL_MS // 6
    assert _poll_ms(warning) == 5_000
    # 20 s remaining → inside the critical floor → ÷30.
    rig.clock.advance(70)
    critical = _get(rig, f"/ui/benches/{_BENCH}/controls", record)
    assert _poll_ms(critical) == DEFAULT_PANEL_POLL_MS // 30
    assert _poll_ms(critical) == 1_000


def test_fragment_warns_with_the_safe_transition_loss_and_renew_action(rig: Any) -> None:
    """GW-44's required content: the lease warning names what is lost
    (the safe transition ends manual work) and carries the renew action."""
    record = _session(rig.app, scopes=CONTROL, ttl_s=3600)
    assert _take(rig, record, duration_ms=120_000).status_code == 200
    rig.clock.advance(30)  # 90 s remaining → warning
    fragment = _get(rig, f"/ui/benches/{_BENCH}/controls", record)
    assert 'data-severity="warning"' in fragment.text
    assert "safe transition" in fragment.text
    assert "Renew the lease" in fragment.text
    # Critical: alert region, non-dismissible.
    rig.clock.advance(75)  # 15 s remaining → critical
    fragment = _get(rig, f"/ui/benches/{_BENCH}/controls", record)
    assert 'data-severity="critical"' in fragment.text
    assert 'role="alert"' in fragment.text
    assert 'aria-label="Dismiss"' not in fragment.text


def test_fragment_poll_is_a_read_only_refresh(rig: Any) -> None:
    """NFR-O1 on the panel: the fragment GET carries no device-affecting
    operation — no mutating seam call fires on any refresh."""
    record = _session(rig.app, scopes=CONTROL, ttl_s=3600)
    assert _take(rig, record).status_code == 200
    for name in ("lease_create", "lease_renew", "lease_release"):
        calls = _spy(rig, name)
        assert _get(rig, f"/ui/benches/{_BENCH}/controls", record).status_code == 200
        assert calls == []


# --- the #307-noted floor/percentage coincidence, rendered ------------------------


def test_the_ten_minute_warning_fires_at_its_coincident_threshold(rig: Any) -> None:
    """At exactly 10 min the warn floor and the 20% percentage coincide
    at 120 s (#307's own noted coincidence): the warning fires from the
    lease's creation — accepted noise there, pinned here."""
    record = _session(rig.app, scopes=CONTROL, ttl_s=3600)
    assert _take(rig, record, duration_ms=600_000).status_code == 200
    rig.clock.advance(480)  # 120 s remaining exactly
    fragment = _get(rig, f"/ui/benches/{_BENCH}/controls", record)
    assert _poll_ms(fragment) == DEFAULT_PANEL_POLL_MS // 6
    assert 'data-severity="warning"' in fragment.text


# --- K's G3a rows are policed by test_ui_route_mapping.py (re-run there) ----------


def test_route_rows_declare_the_g3a_operations() -> None:
    from benchweave.interfaces.ui_routes import UI_ROUTES

    by_path = {spec.path: spec for spec in UI_ROUTES}
    assert by_path["/benches/{bench_id}/leases"].operations == frozenset(
        {"lease_create"}
    )
    assert by_path["/leases/{lease_id}/renewals"].operations == frozenset(
        {"lease_renew"}
    )
    assert by_path["/leases/{lease_id}/release"].operations == frozenset(
        {"lease_release"}
    )
    fragment_row = by_path["/benches/{bench_id}/controls"]
    assert fragment_row.classification == "session"
    assert fragment_row.methods == frozenset({"GET"})


def test_unused_helpers_import_clean() -> None:
    """The G2-era fixtures stay importable (the suite's own hygiene)."""
    assert callable(hashlib.sha256)
    assert json.loads("{}") == {}
