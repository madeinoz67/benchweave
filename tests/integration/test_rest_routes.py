"""WP07 Task 9: the 20 REST routes — status shapes, auth tiers, body ceiling.

The parametrized matrix drives every catalog operation once against the real
gateway (store + content + bootstrap + run worker over ``create_app``).
Placeholder ids (``{sha}``/``{run_id}``/``{lease_id}``/…) are filled from
real seeded state during module-fixture setup — the fixture fires the
creating requests itself and stashes what the matrix reads. Resolutions,
disclosed per the brief's "fill placeholders from seeded fixture reality":

- ``sim-bench`` with devices ``sim-psu``/``sim-controller`` is the bootstrap
  bench (admitted by the app lifespan); a second bench ``bench-two`` is
  seeded pre-boot so the negative-limit clamp case proves the floor against
  a real second page (Task 8's prep pattern).
- Evidence/artifact rows are seeded through the content store pre-boot
  (Task 8's ``put_artifact`` pattern plus one ``put_evidence`` row).
- The setup sequence respects the generation fence: run + lease + change1
  submit/apply all at generation 1 (apply bumps to 2), then change2 is
  submitted with its approval document for the matrix's own apply case.
- ``change_apply``'s independent approval follows Task 7's pattern: a
  stored sha-verified approval document plus a detached ``gateway-admin``
  approver token forwarded as the seam's optional ``approver_token`` — the
  catalog REST body schema does not declare that field; without it the
  REST-only apply can never succeed (the seam fail-closes ``missing_token``).
  Disclosed in the task report for the Task 10 parity review.

Matrix order is load-bearing: cases execute in declaration order, so the
lease created in setup is renewed then released by later cases, and the
admin apply (generation 2 -> 3) fires after every generation-fenced case.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.interfaces.identity import issue
from benchweave.state.store import Store

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"
SECRET = b"wp07-task-nine-secret"
NOW_ISO = "2026-09-12T00:00:00Z"
NOW_EPOCH = 1_800_000_000
LIMITS: dict[str, int] = {
    "max_json_bytes": 1048576,
    "max_page_size": 1000,
    "max_chunk_bytes": 65536,
    "max_lease_ms": 600000,
    "min_poll_ms": 100,
    "max_admission_ms": 5000,
}
BENCH = "sim-bench"
BINDING_SHA = hashlib.sha256((FIXTURES / "run-binding.json").read_bytes()).hexdigest()
BINDING_REF = {"id": "req-voltage-check-1", "version": "1.0.0", "sha256": BINDING_SHA}
TARGET_REF = {"id": "t9", "version": "1", "sha256": "0" * 64}

ROUTE_CASES: list[tuple[str, str, int, Any]] = [
    ("get", "/v1", 200, None),  # gateway_info
    ("get", "/v1/benches?limit=10&cursor=", 200, None),  # bench_list
    ("get", f"/v1/benches/{BENCH}", 200, None),  # bench_get
    ("get", f"/v1/benches/{BENCH}/devices?limit=10&cursor=", 200, None),  # device_list
    # Bootstrap keys device rows by the descriptor document's own ``id``
    # (``descriptor-sim-controller``), not the bench doc's short device id.
    ("get", f"/v1/benches/{BENCH}/devices/descriptor-sim-controller", 200, None),
    ("get", "/v1/documents/{sha}", 200, None),  # document_get
    ("post", f"/v1/benches/{BENCH}/run-checks", 200, {"binding_ref": BINDING_REF}),
    # A §9 replay of the setup run (same request id, same binding pin, fence
    # satisfied at the post-apply generation): the seam's idempotency key
    # returns the original run without a second enqueue — starting a second
    # run on the same binding would trip the coordinator's binding-level
    # duplicate rejection in the worker thread.
    ("post", f"/v1/benches/{BENCH}/runs", 202, {
        "request_id": "req-voltage-check-1",
        "binding_ref": BINDING_REF,
        "expected_generation": 2,
        "lease_id": None,
    }),
    ("get", "/v1/runs/{run_id}", 200, None),  # run_get
    ("get", "/v1/requests/{request_id}", 200, None),  # run_find
    ("post", "/v1/runs/{run_id}/cancellations", 200, {
        "request_id": "req-matrix-cancel",
        "reason": "operator",
    }),
    ("post", f"/v1/benches/{BENCH}/leases", 201, {
        "request_id": "req-matrix-lease",
        "expected_generation": 2,
        "duration_ms": 60000,
    }),
    ("post", "/v1/leases/{lease_id}/renewals", 200, {
        "request_id": "req-matrix-renew",
        "sequence": "{lease_sequence}",
        "duration_ms": 60000,
    }),
    ("post", "/v1/leases/{lease_id}/releases", 200, {
        "request_id": "req-matrix-release",
        "reason": "done",
    }),
    ("get", f"/v1/benches/{BENCH}/events?after=&limit=10", 200, None),  # events_get
    ("get", "/v1/evidence/{evidence_id}", 200, None),  # evidence_get
    ("get", "/v1/artifacts/{artifact_id}/chunks?offset=0&length=64", 200, None),
    ("post", "/v1/admin/changes", 201, {
        "request_id": "req-matrix-change",
        "bench_id": BENCH,
        "kind": "trip_reset",
        "target_ref": TARGET_REF,
        "expected_generation": 2,
        "reason": "matrix submit",
    }),
    ("post", "/v1/admin/changes/{change_id}/apply", 200, {
        "request_id": "req-matrix-apply",
        "expected_generation": 2,
        "approval_ref": "{approval_ref}",
        "approver_token": "{approver_token}",
    }),
    ("get", "/v1/admin/changes/{change_id}", 200, None),  # change_get
]


def _token(principal: str, scopes: set[str], *, audience: str = "stg") -> str:
    return issue(
        SECRET,
        principal=principal,
        audience=audience,
        scopes=scopes,
        expires_at=NOW_EPOCH + 3600,
    )


def _store_approval(
    content: ContentStore, change_id: str, expected_generation: int
) -> dict[str, str]:
    """Store one approval document binding ``change_id`` at one generation."""
    body = {
        "change_id": change_id,
        "expected_generation": expected_generation,
        "approver_principal": "approver-9",
        "policy_version": "1",
    }
    raw = json.dumps(body, sort_keys=True).encode()
    sha = hashlib.sha256(raw).hexdigest()
    content.put_document(raw, sha, body, "urn:stg:approval", NOW_ISO)
    return {"id": f"approval-{change_id}", "version": "1", "sha256": sha}


@pytest.fixture(scope="module")
def gateway(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SimpleNamespace]:
    """One real gateway: store, content, bootstrap bench, worker, REST + MCP.

    All placeholder state is created here in generation-fence order (run and
    lease and change1-apply at generation 1; change2 submitted at generation
    2 with its approval document so the matrix's apply case can succeed).
    """
    tmp_path = tmp_path_factory.mktemp("task9-rest")
    store = Store.open(tmp_path / "state.db", check_same_thread=False)
    content = ContentStore(store)

    # Clamp-case inventory: a second bench beyond the bootstrap bench.
    generation = store.bump_generation("bench-two", NOW_ISO)
    store.put_bench("bench-two", generation, "observation", "{}", "proprietary", NOW_ISO)

    artifact_id = content.put_artifact(b"0123456789abcdefghij", NOW_ISO)
    evidence_id = content.put_evidence(
        "document",
        {"id": "ev-doc", "version": "1", "sha256": "0" * 64},
        artifact_id,
        None,
        NOW_ISO,
    )

    app: FastAPI = create_app(
        store=store,
        content=content,
        secret=SECRET,
        limits=LIMITS,
        gateway_id="gw-task9",
        fixtures_dir=FIXTURES,
        now_iso=lambda: NOW_ISO,
        now_epoch=lambda: NOW_EPOCH,
    )
    admin = {"Authorization": f"Bearer {_token('admin-9', {'stg:admin'})}"}
    filled: dict[str, Any] = {
        "sha": BINDING_SHA,
        "artifact_id": artifact_id,
        "evidence_id": evidence_id,
    }

    with TestClient(app) as client:
        started = client.post(
            f"/v1/benches/{BENCH}/runs",
            headers=admin,
            json={
                "request_id": "req-voltage-check-1",  # §5: the binding doc's own id
                "binding_ref": BINDING_REF,
                "expected_generation": 1,
                "lease_id": None,
            },
        )
        assert started.status_code == 202, started.text
        filled["run_id"] = started.json()["data"]["run_id"]
        filled["request_id"] = "req-voltage-check-1"

        created = client.post(
            f"/v1/benches/{BENCH}/leases",
            headers=admin,
            json={
                "request_id": "req-task9-lease",
                "expected_generation": 1,
                "duration_ms": 60000,
            },
        )
        assert created.status_code == 201, created.text
        lease = created.json()["data"]
        filled["lease_id"] = lease["lease_id"]
        filled["lease_sequence"] = lease["sequence"]

        submitted = client.post(
            "/v1/admin/changes",
            headers=admin,
            json={
                "request_id": "req-task9-change",
                "bench_id": BENCH,
                "kind": "trip_reset",
                "target_ref": TARGET_REF,
                "expected_generation": 1,
                "reason": "setup apply",
            },
        )
        assert submitted.status_code == 201, submitted.text
        setup_change = submitted.json()["data"]["change_id"]

        applied = client.post(
            f"/v1/admin/changes/{setup_change}/apply",
            headers=admin,
            json={
                "request_id": "req-task9-apply",
                "expected_generation": 1,
                "approval_ref": _store_approval(content, setup_change, 1),
                "approver_token": _token(
                    "approver-9", {"stg:admin"}, audience="gateway-admin"
                ),
            },
        )
        assert applied.status_code == 200, applied.text

        # The matrix's own apply case: a second proposed change at the new
        # generation, with its approval document stored beside it.
        second = client.post(
            "/v1/admin/changes",
            headers=admin,
            json={
                "request_id": "req-task9-change-2",
                "bench_id": BENCH,
                "kind": "trip_reset",
                "target_ref": TARGET_REF,
                "expected_generation": 2,
                "reason": "matrix apply",
            },
        )
        assert second.status_code == 201, second.text
        filled["change_id"] = second.json()["data"]["change_id"]
        filled["approval_ref"] = _store_approval(content, filled["change_id"], 2)
        filled["approver_token"] = _token(
            "approver-9", {"stg:admin"}, audience="gateway-admin"
        )

        yield SimpleNamespace(
            client=client,
            admin_headers=admin,
            observe_headers={
                "Authorization": f"Bearer {_token('watcher-9', {'stg:observe'})}"
            },
            filled=filled,
        )
    store.close()


def _fill(value: Any, ids: dict[str, Any]) -> Any:
    """Resolve ``"{name}"`` sentinel strings in a matrix body from ``ids``."""
    if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
        return ids[value[1:-1]]
    if isinstance(value, dict):
        return {key: _fill(item, ids) for key, item in value.items()}
    return value


@pytest.mark.parametrize("method,path,expected_status,body", ROUTE_CASES)
def test_route_status_shapes(
    gateway: SimpleNamespace, method: str, path: str, expected_status: int, body: Any
) -> None:
    ids = gateway.filled
    resolved = path.format(**ids)
    payload = _fill(body, ids)
    resp = gateway.client.request(
        method, resolved, headers=gateway.admin_headers, json=payload
    )
    assert resp.status_code == expected_status, resp.text
    if resp.status_code < 400:
        assert resp.json()["ok"] is True


def test_missing_token_is_401_unauthenticated(gateway: SimpleNamespace) -> None:
    resp = gateway.client.get("/v1")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthenticated"


def test_expired_token_is_401_unauthenticated(gateway: SimpleNamespace) -> None:
    """WP02 map: token-shaped rejections (malformed/bad_signature/expired)
    are 401 at the REST layer."""
    expired = issue(
        SECRET,
        principal="late-9",
        audience="stg",
        scopes={"stg:admin"},
        expires_at=NOW_EPOCH - 1,
    )
    resp = gateway.client.get("/v1", headers={"Authorization": f"Bearer {expired}"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthenticated"


def test_wrong_audience_token_is_403_forbidden(gateway: SimpleNamespace) -> None:
    """WP02 map: audience/scope rejections are 403 — the semantics the MCP
    transport cannot express and collapses to a 401-class transport reject."""
    foreign = _token("elsewhere-9", {"stg:admin"}, audience="gateway-admin")
    resp = gateway.client.get("/v1", headers={"Authorization": f"Bearer {foreign}"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


def test_observe_token_on_admin_is_403_forbidden(gateway: SimpleNamespace) -> None:
    resp = gateway.client.get(
        "/v1/admin/changes/x", headers=gateway.observe_headers
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


def test_body_over_max_json_bytes_is_413_payload_too_large(
    gateway: SimpleNamespace,
) -> None:
    """The REST layer enforces the limits dict's ``max_json_bytes`` bound."""
    padding = "x" * (LIMITS["max_json_bytes"] + 1)
    resp = gateway.client.post(
        f"/v1/benches/{BENCH}/run-checks",
        headers=gateway.admin_headers,
        json={"binding_ref": {"id": padding, "version": "1", "sha256": BINDING_SHA}},
    )
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "payload_too_large"


def test_negative_query_params_are_clamped_not_rejected(
    gateway: SimpleNamespace,
) -> None:
    """REST-layer clamps mirror Task 8's MCP clamps: floor limit at 1 (SQLite
    reads ``LIMIT < 0`` as UNLIMITED), floor artifact length at 1, and a
    non-integer limit is ``invalid_request`` — never a store-facing 500."""
    floored = gateway.client.get(
        "/v1/benches?limit=-5&cursor=", headers=gateway.admin_headers
    )
    assert floored.status_code == 200, floored.text
    page = floored.json()["data"]
    assert len(page["items"]) == 1  # two benches exist; the floor holds at 1
    assert page["next_cursor"] is not None

    chunk = gateway.client.get(
        f"/v1/artifacts/{gateway.filled['artifact_id']}/chunks?offset=0&length=-3",
        headers=gateway.admin_headers,
    )
    assert chunk.status_code == 200, chunk.text
    assert chunk.json()["data"]["bytes"] == 1

    garbage = gateway.client.get(
        "/v1/benches?limit=abc&cursor=", headers=gateway.admin_headers
    )
    assert garbage.status_code == 400
    assert garbage.json()["error"]["code"] == "invalid_request"
