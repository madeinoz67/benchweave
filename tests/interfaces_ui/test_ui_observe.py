"""The G2b acceptance arms: observe-no-control (design §7-E), the I02
/ui extension (design §7-C's read-route half), and the induced-code
matrix's data-bearing arms (design §7-F).

Observe-no-control: an observe session renders every observe-tier read
view with its seam data present, and NO page carries an enabled mutating
control — no form, no button, and a direct POST to every read path is
refused by the route table itself (405: the routes are GET-only). The
belt around the belt: nothing in the adapter constructs an ``Identity``
except the session-record mapping.

I02's /ui half: no principal spoofing (no route reads a principal
parameter; a posted principal is ignored) and no cross-bench reads (the
seam's bench-scoped device lookup renders not_found as
unavailable-to-caller — pinned in the presentation suite; the
cross-principal reconcile arm lives here).

The induced arms carry their discriminating controls inline: every
monkeypatched seam arm runs the same request UNINDUCED and asserts 200
first, so an arm that cannot discriminate cannot pass.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.testclient import TestClient
from ui_gateway_support import (
    FIXTURES,
    LIMITS,
    NOW_EPOCH,
    build_ui_gateway,
    live_session,
)

from benchweave.content.store import ContentStore
from benchweave.interfaces import errors
from benchweave.interfaces.identity import Identity
from benchweave.state.store import Store

BENCH_ID = "sim-bench"
SOURCES = (
    Path(__file__).resolve().parent.parent.parent
    / "src" / "benchweave" / "interfaces" / "ui_read.py",
    Path(__file__).resolve().parent.parent.parent
    / "src" / "benchweave" / "interfaces" / "ui.py",
)

#: The nine §C.3 codes the read wire cannot produce naturally in this
#: fixture — INDUCED (monkeypatched seam refusals), labelled per the
#: honesty rule. cursor_expired additionally has NO emitter in the seam
#: at all (the G2c design's §1 finding); its arm here proves the PAGE
#: renders the row when the bridge's G2c lane raises it.
INDUCED_CODES = (
    "conflict",
    "policy_denied",
    "not_ready",
    "gone",
    "rate_limited",
    "unavailable",
    "internal_error",
    "cursor_expired",
    "event_gap",
)


@pytest.fixture(scope="module")
def gateway(tmp_path_factory: pytest.TempPathFactory) -> Any:
    data_dir = tmp_path_factory.mktemp("ui-observe")
    app = build_ui_gateway(data_dir, name="observe")
    store = Store.open(
        str(data_dir / "state-observe.sqlite"), check_same_thread=False
    )
    content = ContentStore(store)
    session = live_session(app)
    control = app.state.ui_sessions.exchange(
        app.state.ui_sessions.mint_login_code(
            Identity(
                principal="observe-control",
                audience="stg",
                scopes=frozenset({"stg:control"}),
                expires_at=2**31,
            )
        )
    )
    with TestClient(app, base_url="http://testserver:8125") as client:
        devices, _ = app.state.ui_operations.device_list(
            Identity(
                principal="ui-shell",
                audience="stg",
                scopes=frozenset({"stg:observe"}),
                expires_at=2**31,
            ),
            BENCH_ID,
            limit=10,
            cursor=None,
        )
        # A run driven to terminal so the run page has real data.
        operations = app.state.ui_operations
        control_identity = Identity(
            principal="observe-control",
            audience="stg",
            scopes=frozenset({"stg:control"}),
            expires_at=2**31,
        )
        raw = (FIXTURES / "run-binding.json").read_bytes()
        binding = json.loads(raw)
        ref = {
            "id": str(binding["request_id"]),
            "version": str(binding["contract_version"]),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        operations.run_start(
            control_identity, BENCH_ID, str(ref["id"]), ref, 1, None
        )
        yield SimpleNamespace(
            app=app,
            client=client,
            session=session,
            control=control,
            content=content,
            device=devices[0],
        )
    store.close()


def _terminal_run(gateway: SimpleNamespace) -> dict[str, Any]:
    """The driven run polled to terminal (the parity discipline)."""
    operations = gateway.app.state.ui_operations
    identity = Identity(
        principal="observe-control",
        audience="stg",
        scopes=frozenset({"stg:control"}),
        expires_at=2**31,
    )
    raw = (FIXTURES / "run-binding.json").read_bytes()
    binding = json.loads(raw)
    ref = {
        "id": str(binding["request_id"]),
        "version": str(binding["contract_version"]),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    run = operations.run_start(identity, BENCH_ID, str(ref["id"]), ref, 1, None)
    import time

    deadline = time.monotonic() + 60.0
    while True:
        current: dict[str, Any] = operations.run_get(identity, str(run["run_id"]))
        if current["state"] == "terminal":
            return current
        assert time.monotonic() < deadline, f"run never reached terminal: {current}"
        time.sleep(0.2)


# --- §7-E: observe sees every read view, no mutating control --------------------


def test_observe_session_sees_every_observe_tier_view(gateway: SimpleNamespace) -> None:
    """Every observe-tier read page renders 200 with its seam data — the
    PRD's exit phrasing "every read view" resolves against the frozen
    catalog: run_find (control) and change_get (admin, D6/G4) render
    their tier refusals, pinned separately."""
    cookie = {"bw_session": gateway.session.session_id}
    run = _terminal_run(gateway)
    evidence_id = gateway.content.put_evidence(
        "dataset", {"sha256": "0" * 64}, None, None, "2026-10-03T00:00:00Z"
    )
    pages = {
        "/ui/": "data-bw-gateway-strip",
        f"/ui/benches/{BENCH_ID}": "data-bw-bench-id",
        f"/ui/benches/{BENCH_ID}/devices/{gateway.device['device_id']}": (
            "data-bw-device-page"
        ),
        f"/ui/runs/{run['run_id']}": "data-bw-run-id",
        f"/ui/evidence/{evidence_id}": "data-bw-evidence-id",
    }
    for path, marker in pages.items():
        response = gateway.client.get(path, cookies=cookie)
        assert response.status_code == 200, path
        assert marker in response.text, path


def test_no_read_page_renders_a_form_or_button(gateway: SimpleNamespace) -> None:
    """§7-E's belt, evolved with the surface it polices (G3a): for an
    observe session no mutating control renders ENABLED anywhere — no
    form at all, and every button that does render (the lease controls'
    observe shape) is disabled. G2's no-button pin was this invariant
    when no control existed; the disabled-with-no-authority shape
    (design §2.2) is its G3 form."""
    import re

    cookie = {"bw_session": gateway.session.session_id}
    run = _terminal_run(gateway)
    paths = (
        "/ui/",
        f"/ui/benches/{BENCH_ID}",
        f"/ui/benches/{BENCH_ID}/devices/{gateway.device['device_id']}",
        f"/ui/runs/{run['run_id']}",
    )
    for path in paths:
        page = gateway.client.get(path, cookies=cookie).text
        assert "<form" not in page, path
        buttons = re.findall(r"<button\b[^>]*>", page)
        assert all("disabled" in attrs for attrs in buttons), (
            path,
            [a for a in buttons if "disabled" not in a],
        )


def test_direct_post_to_read_paths_is_refused(
    gateway: SimpleNamespace,
) -> None:
    """§7-E's belt around the belt, in the executed truth (the #368 F2
    fold): a session-bearing POST to a read path is refused by the CSRF
    guard — 403, before any handler, whatever the path matches. The
    earlier prose named a 405 route-table refusal that never executes on
    this path shape: the CSRF guard intercepts every session-bearing
    state change first (a sessionless POST to a GET-only route is the
    only 405 shape, and an unknown path falls to the namespace 404)."""
    cookie = {"bw_session": gateway.control.session_id}
    for path in (
        f"/ui/benches/{BENCH_ID}",
        f"/ui/benches/{BENCH_ID}/devices/{gateway.device['device_id']}",
        "/ui/runs/run-x",
        "/ui/requests/req-x",
        "/ui/evidence/ev-x",
        "/ui/documents/" + "0" * 64,
    ):
        response = gateway.client.post(path, cookies=cookie)
        assert response.status_code == 403, (path, response.status_code)
        assert "csrf" in response.text.lower()  # a refusal shape, never a mutation ack


def test_only_the_session_record_constructs_an_identity() -> None:
    """I02's structural pin: the adapter modules construct ``Identity``
    in exactly ONE place — the session-record mapping — never from
    request data."""
    for source in SOURCES:
        text = source.read_text(encoding="utf-8")
        constructions = [
            line
            for line in text.splitlines()
            if re.search(r"=\s*Identity\(", line) and "def " not in line
        ]
        assert all("_session_identity" in text for _ in constructions)
        assert len(constructions) <= 1, f"{source.name}: {constructions}"


def test_posted_principal_is_ignored(gateway: SimpleNamespace) -> None:
    """I02's no-spoofing arm: a principal parameter on a /ui read is
    ignored — the page renders the SESSION's principal, never the posted
    one."""
    clean = gateway.client.get(
        f"/ui/benches/{BENCH_ID}", cookies={"bw_session": gateway.session.session_id}
    )
    spoofed = gateway.client.get(
        f"/ui/benches/{BENCH_ID}?principal=someone-else",
        cookies={"bw_session": gateway.session.session_id},
    )
    assert clean.status_code == spoofed.status_code == 200
    assert 'data-bw-principal="ui-shell"' in spoofed.text
    assert "someone-else" not in spoofed.text


def test_cross_principal_reconcile_lookup_is_not_found(
    gateway: SimpleNamespace,
) -> None:
    """run_find is principal-scoped at the seam (§9): another principal's
    request id can never discover their runs — the page renders
    not_found as unavailable-to-caller."""
    response = gateway.client.get(
        "/ui/requests/req-from-another-principal",
        cookies={"bw_session": gateway.control.session_id},
    )
    assert response.status_code == 404
    assert 'data-bw-refusal-code="not_found"' in response.text


# --- §7-F's data-bearing arms ---------------------------------------------------


def test_artifact_over_the_reassembly_bound_is_payload_too_large(
    gateway: SimpleNamespace,
) -> None:
    """GW-60: beyond the adapter's one payload ceiling the artifact
    download renders the payload_too_large row — never an unbounded
    reassembly. Control: an under-bound artifact downloads 200."""
    cookie = {"bw_session": gateway.session.session_id}
    over_id = gateway.content.put_artifact(
        b"x" * (LIMITS["max_json_bytes"] + 1), "2026-10-03T00:00:00Z"
    )
    under_id = gateway.content.put_artifact(b"y" * 128, "2026-10-03T00:00:00Z")
    refused = gateway.client.get(f"/ui/artifacts/{over_id}", cookies=cookie)
    assert refused.status_code == 413
    assert 'data-bw-refusal-code="payload_too_large"' in refused.text
    assert gateway.client.get(f"/ui/artifacts/{under_id}", cookies=cookie).status_code == 200


def test_malformed_document_digest_is_invalid_request(gateway: SimpleNamespace) -> None:
    """The seam's own validator induces invalid_request on a read route:
    a malformed sha256 path parameter fails document_get's payload
    validation. Control: a well-formed (unknown) digest is not_found,
    not invalid_request — the two rows stay distinct."""
    cookie = {"bw_session": gateway.session.session_id}
    malformed = gateway.client.get("/ui/documents/not-a-digest", cookies=cookie)
    assert malformed.status_code == 400
    assert 'data-bw-refusal-code="invalid_request"' in malformed.text
    unknown = gateway.client.get(
        "/ui/documents/" + "0" * 64, cookies=cookie
    )
    assert unknown.status_code == 404
    assert 'data-bw-refusal-code="not_found"' in unknown.text


def test_expired_session_renders_unauthenticated(
    tmp_path: Any,
) -> None:
    """The expired-session arm, induced deterministically through the
    session store's INJECTED clock (the composition seam the whole suite
    freezes): advance the clock past the session's expiry — resolve
    returns None and the page renders the §C.3 unauthenticated row (the
    G2a login suite pins the store-level sweep; this pins the PAGE)."""
    from benchweave.interfaces.sessions import SessionStore

    data_dir = tmp_path / "expired"
    data_dir.mkdir()
    app = build_ui_gateway(data_dir, name="expired-arm")
    sessions: SessionStore = app.state.ui_sessions
    code = sessions.mint_login_code(
        Identity(
            principal="expires",
            audience="stg",
            scopes=frozenset({"stg:observe"}),
            expires_at=NOW_EPOCH + 3600,
        ),
        ttl_seconds=60,
    )
    record = sessions.exchange(code)
    original_now = sessions._now
    with TestClient(app, base_url="http://testserver:8125") as client:
        fresh = client.get(
            "/ui/benches/sim-bench", cookies={"bw_session": record.session_id}
        )
        assert fresh.status_code == 200
        sessions._now = lambda: NOW_EPOCH + 7200
        expired = client.get(
            "/ui/benches/sim-bench", cookies={"bw_session": record.session_id}
        )
    sessions._now = original_now
    assert expired.status_code == 401
    assert 'data-bw-refusal-code="unauthenticated"' in expired.text
    # The honest state (the #368 F3 fold): this path has NO Failure
    # object — the session layer refused before any seam call — so no
    # correlation id renders. The correlation id is the seam failure's
    # diagnostic join (errors.py mints it), not a property of the §C.3
    # row; the operator guide's wording names that boundary.
    assert "Correlation id" not in expired.text
    assert not re.search(r"data-bw-correlation-id", expired.text)


@pytest.mark.parametrize("code", INDUCED_CODES)
def test_induced_seam_refusal_renders_its_row(
    gateway: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, code: str
) -> None:
    """The nine read-wire-impossible classes, each INDUCED by
    monkeypatching ``run_get`` on the adapter's own seam object, with the
    discriminating control first: the SAME request uninduced renders 200
    with the run's data (an arm that cannot discriminate cannot pass).
    cursor_expired is additionally emitter-less in the seam (the G2c
    design's §1 disclosure): the arm proves the PAGE renders the row
    when G2c's bridge raises it — it does not claim an emission."""
    cookie = {"bw_session": gateway.session.session_id}
    run = _terminal_run(gateway)
    path = f"/ui/runs/{run['run_id']}"
    assert gateway.client.get(path, cookies=cookie).status_code == 200  # control

    operations = gateway.app.state.ui_operations
    original = operations.run_get

    def induced(identity: Identity, run_id: str) -> dict[str, Any]:
        raise errors.OperationFailure(
            errors.failure(code, f"induced {code} for the row-render matrix")
        )

    monkeypatch.setattr(operations, "run_get", induced)
    response = gateway.client.get(path, cookies=cookie)
    expected_status = errors.FAILURE_HTTP[code]
    assert response.status_code == expected_status, code
    assert f'data-bw-refusal-code="{code}"' in response.text, code
    assert f"induced {code}" in response.text, code
    assert re.search(r"[0-9a-f]{16}", response.text), code
    monkeypatch.setattr(operations, "run_get", original)
