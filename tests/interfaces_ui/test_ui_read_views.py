"""The G2b read views: every observe-tier page renders, with the seam's
own data present (design §7-E's read half, GW-20/55/60/61).

An observe session is the PRD's read-only actor. Every observe-tier
operation's page returns 200 with its seam data; ``run_find`` is
control-tier in the frozen catalog, so its page renders the ``forbidden``
§C.3 row for observe and the resolved run for a control session (the
catalog is the authority — A13; the PRD's "every read view" phrasing
assumed observe-tier for all twelve reads, and the catalog rules
otherwise for this one).

The run/request arms drive a REAL run through the composed gateway's own
worker (the parity suite's discipline): start through the seam, poll
``run_get`` to a terminal projection, then read the pages.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.testclient import TestClient
from ui_gateway_support import FIXTURES, NOW_ISO, build_ui_gateway, live_session

from benchweave.content.store import ContentStore
from benchweave.interfaces.identity import Identity
from benchweave.state.store import Store

BENCH_ID = "sim-bench"  # the fixture bench.json's id (startup admission)


@pytest.fixture(scope="module")
def gateway(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SimpleNamespace]:
    """One composed gateway whose store/content handles the suite keeps
    (the seeding arms write evidence/artifacts/documents through the
    content store — the same surface a real run writes through)."""
    data_dir = tmp_path_factory.mktemp("ui-read")
    app = build_ui_gateway(data_dir, name="read-views")
    store = Store.open(
        str(data_dir / "state-read-views.sqlite"), check_same_thread=False
    )
    content = ContentStore(store)
    session = live_session(app)
    control_record = app.state.ui_sessions.exchange(
        app.state.ui_sessions.mint_login_code(
            Identity(
                principal="ui-control",
                audience="stg",
                scopes=frozenset({"stg:control"}),
                expires_at=2**31,
            )
        )
    )
    with TestClient(app, base_url="http://testserver:8125") as client:
        yield SimpleNamespace(
            app=app,
            client=client,
            session=session,
            control=control_record,
            store=store,
            content=content,
        )
    store.close()


def _binding_ref() -> dict[str, Any]:
    raw = (FIXTURES / "run-binding.json").read_bytes()
    binding = json.loads(raw)
    return {
        "id": str(binding["request_id"]),
        "version": str(binding["contract_version"]),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _driven_run(gateway: SimpleNamespace) -> dict[str, Any]:
    """Start one run through the seam on the control identity and poll to
    a terminal projection (the parity suite's discipline)."""
    operations = gateway.app.state.ui_operations
    identity = Identity(
        principal="ui-control",
        audience="stg",
        scopes=frozenset({"stg:control"}),
        expires_at=2**31,
    )
    ref = _binding_ref()
    request_id = str(ref["id"])
    run = operations.run_start(identity, BENCH_ID, request_id, ref, 1, None)
    run_id = str(run["run_id"])
    deadline = time.monotonic() + 60.0
    while True:
        current: dict[str, Any] = operations.run_get(identity, run_id)
        if current["state"] == "terminal":
            return current
        assert time.monotonic() < deadline, f"run never reached terminal: {current}"
        time.sleep(0.2)


# --- the observe-tier pages ------------------------------------------------------


def test_bench_page_renders_projection_devices_and_events(
    gateway: SimpleNamespace,
) -> None:
    response = gateway.client.get(
        f"/ui/benches/{BENCH_ID}", cookies={"bw_session": gateway.session.session_id}
    )
    assert response.status_code == 200
    page = response.text
    assert 'data-bw-bench-id="sim-bench"' in page
    assert "data-bw-device-list" in page  # the admitted fixture device renders
    assert "data-bw-events-first-page" in page  # GW-20: first events page
    assert "data-bw-gateway-id>ui-test<" in page  # GW-81 strip


def test_unknown_bench_renders_not_found_as_unavailable(
    gateway: SimpleNamespace,
) -> None:
    """GW-14: the §C.3 not_found row — unavailable to this caller."""
    response = gateway.client.get(
        "/ui/benches/no-such-bench", cookies={"bw_session": gateway.session.session_id}
    )
    assert response.status_code == 404
    assert 'data-bw-refusal-code="not_found"' in response.text
    assert "unavailable to this caller" in response.text


def test_run_page_renders_state_exactly_as_reported(
    gateway: SimpleNamespace,
) -> None:
    run = _driven_run(gateway)
    response = gateway.client.get(
        f"/ui/runs/{run['run_id']}", cookies={"bw_session": gateway.session.session_id}
    )
    assert response.status_code == 200
    page = response.text
    assert f'data-bw-run-id="{run["run_id"]}"' in page
    assert "data-bw-run-state>terminal<" in page
    # GW-55: outcome and safe state render exactly as reported — no
    # inferred terminal wording, no cancel control.
    assert "data-bw-run-outcome" in page
    assert "cancel" not in page.lower()
    assert "<form" not in page and "<button" not in page


def test_run_find_view_refuses_observe_and_resolves_for_control(
    gateway: SimpleNamespace,
) -> None:
    """``run_find`` is control-tier (the frozen catalog) — the observe
    session renders the forbidden §C.3 row; the control session that
    started the run resolves it (GW-12's reconcile view)."""
    operations = gateway.app.state.ui_operations
    control = Identity(
        principal="ui-control",
        audience="stg",
        scopes=frozenset({"stg:control"}),
        expires_at=2**31,
    )
    ref = _binding_ref()
    request_id = str(ref["id"])
    started = operations.run_start(control, BENCH_ID, request_id, ref, 1, None)
    refused = gateway.client.get(
        f"/ui/requests/{request_id}", cookies={"bw_session": gateway.session.session_id}
    )
    assert refused.status_code == 403
    assert 'data-bw-refusal-code="forbidden"' in refused.text
    resolved = gateway.client.get(
        f"/ui/requests/{request_id}",
        cookies={"bw_session": gateway.control.session_id},
    )
    assert resolved.status_code == 200
    assert 'data-bw-request-run' in resolved.text
    assert started["run_id"] in resolved.text


def test_evidence_page_renders_kind_digest_and_artifact_link(
    gateway: SimpleNamespace,
) -> None:
    artifact_id = gateway.content.put_artifact(b"evidence-payload", NOW_ISO)
    evidence_id = gateway.content.put_evidence(
        "dataset",
        {"sha256": hashlib.sha256(b"evidence-payload").hexdigest()},
        artifact_id,
        None,
        NOW_ISO,
    )
    response = gateway.client.get(
        f"/ui/evidence/{evidence_id}", cookies={"bw_session": gateway.session.session_id}
    )
    assert response.status_code == 200
    page = response.text
    assert "data-bw-evidence-kind>dataset<" in page
    assert f'href="/ui/artifacts/{artifact_id}"' in page


def test_artifact_download_verifies_the_complete_digest(
    gateway: SimpleNamespace,
) -> None:
    """GW-60/61: the download reassembles chunked ``artifact_read`` and
    serves the EXACT bytes with the digest — 3 chunks over the 64 KiB
    chunk ceiling proves the loop, not a single-chunk read."""
    payload = bytes(range(256)) * 1024  # 256 KiB = 4 chunks at 64 KiB
    artifact_id = gateway.content.put_artifact(payload, NOW_ISO)
    response = gateway.client.get(
        f"/ui/artifacts/{artifact_id}",
        cookies={"bw_session": gateway.session.session_id},
    )
    assert response.status_code == 200
    assert response.content == payload
    assert response.headers["x-benchweave-sha256"] == hashlib.sha256(payload).hexdigest()
    assert response.headers["content-disposition"].startswith("attachment")


def test_document_page_shows_digest_and_content(
    gateway: SimpleNamespace,
) -> None:
    raw = json.dumps({"hello": "document"}).encode()
    digest = hashlib.sha256(raw).hexdigest()
    gateway.content.put_document(
        raw, digest, json.loads(raw), "urn:stg:admitted", NOW_ISO
    )
    response = gateway.client.get(
        f"/ui/documents/{digest}", cookies={"bw_session": gateway.session.session_id}
    )
    assert response.status_code == 200
    page = response.text
    assert f"data-bw-document-sha>{digest}<" in page
    assert "data-bw-document-content" in page
    assert "hello" in page


def test_unknown_run_evidence_artifact_document_render_not_found(
    gateway: SimpleNamespace,
) -> None:
    cookie = {"bw_session": gateway.session.session_id}
    for path in (
        "/ui/runs/run-nope",
        "/ui/evidence/ev-nope",
        "/ui/artifacts/art-" + "0" * 24,
        "/ui/documents/" + "0" * 64,
    ):
        response = gateway.client.get(path, cookies=cookie)
        assert response.status_code == 404, path
        assert 'data-bw-refusal-code="not_found"' in response.text, path


def test_sessionless_read_page_renders_unauthenticated(
    gateway: SimpleNamespace,
) -> None:
    response = gateway.client.get(f"/ui/benches/{BENCH_ID}")
    assert response.status_code == 401
    assert 'data-bw-refusal-code="unauthenticated"' in response.text
