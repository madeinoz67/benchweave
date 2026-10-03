"""The device-page reading tiles populated from retained observations
(issue #369, design record 2026-10-03 — Fork A, the evidence join).

Every arm runs against a seeded in-process app (the parity suite's
``boot`` pattern) with frozen clocks: a real composed gateway, a real
second store/content connection for seeding (the read-views suite's
discipline), real telemetry landed through the REAL landing lane
(``StreamController.land_events`` — the same bytes, references and
artifacts a run's stream produces), and runs seeded at store level
(``create_run`` + ``put_run_state``, the projection the join reads).

The join under test (``interfaces/ui_readings.py``) is the design's §4:
bench→runs→binding filter→evidence rows by context→digest-verified
artifacts→the landing lane's OWN reading validator→attribution census
→recency by the observation's own timestamp→``populate_tiles``. The
acceptance arms A1–A12 are the design record's §8, including the two
controls the record requires: A6's MECHANISM-TOGGLE (digest
verification neutralized must RED the tamper arm) and A7's
DISCRIMINATOR (the ambiguity refusal must flip to a populated tile when
the sibling's declaration is removed).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.testclient import TestClient
from ui_gateway_support import (
    FIXTURES,
    LIMITS,
    NOW_EPOCH,
    NOW_ISO,
    SECRET,
    build_ui_gateway,
    live_session,
)

from benchweave.content.store import ContentStore
from benchweave.content.stream_services import LandedEvent, StreamController
from benchweave.host.services import QuotaLimits
from benchweave.interfaces.app import create_app
from benchweave.state.store import Store

_NOW_MS = NOW_EPOCH * 1000
_QUOTA = QuotaLimits(
    max_dataset_bytes=8192, max_evidence_entries=100_000, max_event_batch=1000
)
#: Where the join's verdicts are asserted exactly (A3/A4): the tile mark
#: only distinguishes stale from not-stale, so fresh vs no-verdict is
#: pinned at the composition level in those arms.
_TILE_PAGE_MARK = "data-bw-presentation-page-readings"


def _iso(epoch_ms: int) -> str:
    return datetime.fromtimestamp(epoch_ms / 1000, UTC).isoformat()


def _param(name: str, *, max_age_ms: int | None = 500) -> dict[str, Any]:
    read_policy: dict[str, Any] = {"destructive": False}
    if max_age_ms is not None:
        read_policy["max_age_ms"] = max_age_ms
    return {
        "name": name,
        "description": f"Seeded parameter {name} for the reading-tile arms.",
        "type": "float",
        "access": "ro",
        "semantic": "measurement",
        "unit": "V",
        "binding": {"kind": "adapter", "key": name},
        "read_policy": read_policy,
    }


def _descriptor_raw(params: list[dict[str, Any]]) -> bytes:
    return json.dumps(
        {
            "descriptor_version": "1.0.0",
            "otdp_version": "0.2.2",
            "id": "dev.benchweave.seed-psu",
            "identity": {
                "strategy": "adapter",
                "manufacturer": "benchweave-seed",
                "model": "seed-1",
                "firmware_policy": "listed",
                "supported_firmware": ["seed-0.1.0"],
            },
            "capabilities": ["read"],
            "profiles": [],
            "parameters": params,
            "channels": [
                {
                    "id": "ch1",
                    "label": "Seeded channel",
                    "role": "source",
                    "quantities": ["voltage"],
                    "parameter_names": [str(param["name"]) for param in params],
                }
            ],
        }
    ).encode()


def _seed_bench(
    store: Store, content: ContentStore, bench_id: str, devices: list[tuple[str, bytes]]
) -> None:
    """A bench whose rows the store admits directly (put_bench/put_device,
    the inventory the seam reads) plus each descriptor admitted as a
    document at its own digest — the bytes ``document_get`` serves."""
    store.put_bench(bench_id, 1, "{}", "{}", "seed", NOW_ISO)
    for device_id, descriptor in devices:
        store.put_device(
            device_id,
            bench_id,
            1,
            "[]",
            descriptor.decode(),
            "commissioned",
            "seed",
            NOW_ISO,
        )
        content.put_document(
            descriptor,
            hashlib.sha256(descriptor).hexdigest(),
            json.loads(descriptor),
            "urn:stg:seed-descriptor",
            NOW_ISO,
        )


def _admit_attachment(
    content: ContentStore, descriptor_raw: bytes, parameter_ids: list[str]
) -> None:
    """Envelope + manifest + binding catalogue for one descriptor, one
    readings page, one observation target per parameter (the G2b suite's
    seeding shape, parameterised)."""
    plugin_ui = next(
        entry["version"]
        for entry in json.loads(
            (FIXTURES.parent.parent / "standards" / "standards-manifest.json").read_text(
                encoding="utf-8"
            )
        )["standards"]
        if entry["id"] == "plugin-ui"
    )
    digest = hashlib.sha256(descriptor_raw).hexdigest()
    manifest = {
        "contract_version": plugin_ui,
        "plugin_id": json.loads(descriptor_raw)["id"],
        "descriptor_sha256": digest,
        "bindings": [
            {"id": f"reading-{name}", "kind": "observation", "target_id": name}
            for name in parameter_ids
        ],
        "pages": [
            {
                "id": "readings",
                "title": "Readings",
                "kind": "readings",
                "bindings": [f"reading-{name}" for name in parameter_ids],
                "required": True,
            }
        ],
    }
    manifest_raw = json.dumps(manifest).encode()
    catalogue = {
        "contract_version": plugin_ui,
        "descriptor_sha256": digest,
        "targets": [
            {
                "id": name,
                "kind": "observation",
                "parameter_id": name,
                "variables": [
                    {
                        "id": "time",
                        "type": "number",
                        "unit": "s",
                        "shape": "scalar",
                        "axis_role": "receipt_time",
                    },
                    {
                        "id": "value",
                        "type": "number",
                        "unit": "V",
                        "shape": "scalar",
                        "axis_role": "value",
                    },
                ],
            }
            for name in parameter_ids
        ],
    }
    envelope = {
        "contract_version": plugin_ui,
        "descriptor_sha256": digest,
        "resource_root": "ui",
        "manifest": {"path": "manifest.json", "sha256": hashlib.sha256(manifest_raw).hexdigest()},
    }
    for raw, parsed, schema in (
        (
            manifest_raw,
            manifest,
            f"https://benchweave.dev/contracts/plugin-ui/{plugin_ui}/ui-manifest.schema.json",
        ),
        (
            json.dumps(catalogue).encode(),
            catalogue,
            f"https://benchweave.dev/contracts/plugin-ui/{plugin_ui}/binding-catalogue.schema.json",
        ),
        (
            json.dumps(envelope).encode(),
            envelope,
            f"https://benchweave.dev/contracts/plugin-ui/{plugin_ui}/presentation-envelope.schema.json",
        ),
    ):
        content.put_document(
            raw, hashlib.sha256(raw).hexdigest(), parsed, schema, NOW_ISO
        )


def _seed_run(
    store: Store,
    run_id: str,
    bench_id: str,
    device_ids: list[str],
    *,
    updated_at: str,
) -> None:
    """One run row plus its queue-state projection — the two rows the
    join reads (newest-first by ``updated_at``; the binding carries every
    device the run bound)."""
    store.create_run(
        run_id,
        {
            "request_id": run_id,
            "bindings": [
                {"role": f"role-{device_id}", "device_id": device_id, "channels": {}}
                for device_id in device_ids
            ],
        },
        "ui-shell",
        NOW_ISO,
    )
    store.put_run_state(run_id, bench_id, "running", updated_at)


def _land(
    store: Store,
    run_id: str,
    rows: list[dict[str, Any]],
) -> None:
    """Land telemetry through the REAL landing lane under the run's
    context key (``run:<run_id>`` — the key the join queries). Each row:
    ``parameter``, ``observed_ms``, ``value`` (plus optional
    ``quality``/``unit``/``sequence``/``host_received_at``)."""
    controller = StreamController(
        store=store,
        context_key=f"run:{run_id}",
        wall=lambda: NOW_ISO,
        quota=_QUOTA,
    )
    entries = [
        LandedEvent(
            event={
                "subscription_id": f"sub-{run_id}",
                "sequence": int(row.get("sequence", index)),
                "kind": "telemetry",
                "reading": {
                    "parameter": row["parameter"],
                    "value": row["value"],
                    "unit": row.get("unit", "V"),
                    "observed_at": _iso(int(row["observed_ms"])),
                    "age_ms": 0,
                    "quality": row.get("quality", "valid"),
                    "source": "device",
                },
            },
            host_received_at=str(row.get("host_received_at", NOW_ISO)),
        )
        for index, row in enumerate(rows)
    ]
    assert controller.land_events(entries) != []


def _page(gateway: SimpleNamespace, bench_id: str, device_id: str) -> str:
    response: Any = gateway.client.get(
        f"/ui/benches/{bench_id}/devices/{device_id}",
        cookies={"bw_session": gateway.session.session_id},
    )
    assert response.status_code == 200, response.text
    return str(response.text)


def _tile_zone(page: str) -> str:
    mark = page.find(_TILE_PAGE_MARK)
    assert mark != -1, "the readings page did not render"
    return page[mark:]


@pytest.fixture(scope="module")
def gateway(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SimpleNamespace]:
    """The default-budget gateway: one composed app, one second
    store/content connection for seeding (the read-views pattern)."""
    data_dir = tmp_path_factory.mktemp("ui-readings")
    app = build_ui_gateway(data_dir, name="readings")
    store = Store.open(
        str(data_dir / "state-readings.sqlite"), check_same_thread=False
    )
    content = ContentStore(store)
    session = live_session(app)
    with TestClient(app, base_url="http://testserver:8125") as client:
        yield SimpleNamespace(
            app=app, client=client, session=session, store=store, content=content
        )
    store.close()


@pytest.fixture(scope="module")
def budget(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[SimpleNamespace]:
    """The A10 gateway: identical composition with
    ``ui_reading_scan_rows`` pinned to 2 — the budget arm must bound the
    join without an exception."""
    data_dir = tmp_path_factory.mktemp("ui-readings-budget")
    store = Store.open(
        str(data_dir / "state-readings-budget.sqlite"), check_same_thread=False
    )
    app = create_app(
        store=store,
        content=ContentStore(store),
        secret=SECRET,
        limits={**LIMITS, "ui_reading_scan_rows": 2},
        gateway_id="ui-readings-budget",
        fixtures_dir=FIXTURES,
        now_iso=lambda: NOW_ISO,
        now_epoch=lambda: NOW_EPOCH,
    )
    seed_store = Store.open(
        str(data_dir / "state-readings-budget.sqlite"), check_same_thread=False
    )
    session = live_session(app)
    with TestClient(app, base_url="http://testserver:8125") as client:
        yield SimpleNamespace(
            app=app,
            client=client,
            session=session,
            store=seed_store,
            content=ContentStore(seed_store),
        )
    seed_store.close()


# --- A1/A2: the fresh and stale arms --------------------------------------------


def test_a1_fresh_observation_populates_tile(gateway: SimpleNamespace) -> None:
    bench, device = "bench-a1", "dev-a1"
    descriptor = _descriptor_raw([_param("voltage", max_age_ms=500)])
    _seed_bench(gateway.store, gateway.content, bench, [(device, descriptor)])
    _admit_attachment(gateway.content, descriptor, ["voltage"])
    _seed_run(gateway.store, "run-a1", bench, [device], updated_at=NOW_ISO)
    _land(
        gateway.store,
        "run-a1",
        [{"parameter": "voltage", "observed_ms": _NOW_MS - 250, "value": 12.5}],
    )
    zone = _tile_zone(_page(gateway, bench, device))
    assert "12.5" in zone, "the landed value did not reach the tile"
    assert "valid" in zone, "the reading's own quality did not render"
    observed = _iso(_NOW_MS - 250)
    assert observed in zone, "freshness must carry the observation's own stamp"
    assert "retained observation from run run-a1" in zone, (
        "the tile must name its source class so a retained value never reads live"
    )
    assert 'data-bw-stale="true"' not in zone, "250 ms inside a 500 ms window is fresh"


def test_a2_stale_observation_renders_value_with_stale_marker(
    gateway: SimpleNamespace,
) -> None:
    bench, device = "bench-a2", "dev-a2"
    descriptor = _descriptor_raw([_param("voltage", max_age_ms=500)])
    _seed_bench(gateway.store, gateway.content, bench, [(device, descriptor)])
    _admit_attachment(gateway.content, descriptor, ["voltage"])
    _seed_run(gateway.store, "run-a2", bench, [device], updated_at=NOW_ISO)
    _land(
        gateway.store,
        "run-a2",
        [{"parameter": "voltage", "observed_ms": _NOW_MS - 600, "value": 4.25}],
    )
    zone = _tile_zone(_page(gateway, bench, device))
    assert "4.25" in zone, "a stale observation still renders its value (ST-2)"
    assert 'data-bw-stale="true"' in zone, "600 ms outside a 500 ms window is stale"


# --- A3: the boundary and the zero window ---------------------------------------


def test_a3_boundary_is_fresh_and_zero_window_is_stale(
    gateway: SimpleNamespace,
) -> None:
    bench, device = "bench-a3", "dev-a3"
    descriptor = _descriptor_raw(
        [_param("voltage", max_age_ms=500), _param("zero_window", max_age_ms=0)]
    )
    _seed_bench(gateway.store, gateway.content, bench, [(device, descriptor)])
    _admit_attachment(gateway.content, descriptor, ["voltage", "zero_window"])
    _seed_run(gateway.store, "run-a3", bench, [device], updated_at=NOW_ISO)
    _land(
        gateway.store,
        "run-a3",
        [
            {"parameter": "voltage", "observed_ms": _NOW_MS - 500, "value": 11.0},
            {"parameter": "zero_window", "observed_ms": _NOW_MS - 1, "value": 2.0},
        ],
    )
    zone = _tile_zone(_page(gateway, bench, device))
    assert "11.0" in zone and "2.0" in zone
    # ST-2 strict inequality: equality is the descriptor's own disavowal
    # line, not past it. The tile mark cannot distinguish fresh from
    # no-verdict, so the exact verdicts are pinned at the composition
    # level over the same seeded store.
    from benchweave.interfaces.ui_presentation import compose_device_presentation
    from benchweave.interfaces.ui_readings import latest_retained_readings, populate_tiles

    readings = latest_retained_readings(
        gateway.store,
        gateway.content,
        bench_id=bench,
        device_id=device,
        sibling_parameter_owners={"voltage": 1, "zero_window": 1},
        now_epoch_ms=_NOW_MS,
        scan_rows=200,
    )
    populated = populate_tiles(
        compose_device_presentation(gateway.content, descriptor),
        readings,
        json.loads(descriptor),
        now_epoch_ms=_NOW_MS,
    )
    verdicts = {tile.parameter_id: tile.stale_verdict for tile in populated.pages[0].tiles}
    assert verdicts["voltage"] == "fresh", "freshness_ms == max_age_ms is fresh (ST-2)"
    assert verdicts["zero_window"] == "stale", "max_age_ms 0: any age >= 1 is stale"
    # Page-level: the zero-window tile carries the stale marker, the
    # boundary tile does not.
    assert zone.count('data-bw-stale="true"') == 1


# --- A4: no commissioned window is no verdict -----------------------------------


def test_a4_absent_window_renders_no_verdict(gateway: SimpleNamespace) -> None:
    bench, device = "bench-a4", "dev-a4"
    descriptor = _descriptor_raw([_param("no_window", max_age_ms=None)])
    _seed_bench(gateway.store, gateway.content, bench, [(device, descriptor)])
    _admit_attachment(gateway.content, descriptor, ["no_window"])
    _seed_run(gateway.store, "run-a4", bench, [device], updated_at=NOW_ISO)
    _land(
        gateway.store,
        "run-a4",
        [{"parameter": "no_window", "observed_ms": _NOW_MS - 250, "value": 9.5}],
    )
    zone = _tile_zone(_page(gateway, bench, device))
    assert "9.5" in zone, "the value renders without a window"
    assert 'data-bw-stale="true"' not in zone, "no window means no stale verdict"
    from benchweave.interfaces.ui_presentation import compose_device_presentation
    from benchweave.interfaces.ui_readings import latest_retained_readings, populate_tiles

    readings = latest_retained_readings(
        gateway.store,
        gateway.content,
        bench_id=bench,
        device_id=device,
        sibling_parameter_owners={"no_window": 1},
        now_epoch_ms=_NOW_MS,
        scan_rows=200,
    )
    populated = populate_tiles(
        compose_device_presentation(gateway.content, descriptor),
        readings,
        json.loads(descriptor),
        now_epoch_ms=_NOW_MS,
    )
    assert populated.pages[0].tiles[0].stale_verdict == "no-verdict", (
        "a parameter without max_age_ms never gets an invented window (ST-3)"
    )


# --- A5: honest absence ----------------------------------------------------------


def test_a5_no_retained_telemetry_keeps_honest_absence(
    gateway: SimpleNamespace,
) -> None:
    bench, device = "bench-a5", "dev-a5"
    descriptor = _descriptor_raw([_param("voltage", max_age_ms=500)])
    _seed_bench(gateway.store, gateway.content, bench, [(device, descriptor)])
    _admit_attachment(gateway.content, descriptor, ["voltage"])
    # A run with NO telemetry: the tile keeps the G2 honest floor.
    _seed_run(gateway.store, "run-a5", bench, [device], updated_at=NOW_ISO)
    zone = _tile_zone(_page(gateway, bench, device))
    assert "Unavailable" in zone, "no observation, no value — never fabricated"
    assert 'data-bw-stale="true"' not in zone, "no observation, no verdict (ST-3)"


# --- A6: the tamper arm and its MECHANISM-TOGGLE control -------------------------


def _seed_tampered_bench(gateway: SimpleNamespace, *, suffix: str) -> tuple[str, str]:
    """One bench with a landed voltage reading whose artifact row is then
    corrupted in place (the read-views H2 discipline): the id still names
    the admission, the bytes no longer hash to it. ``suffix`` keeps every
    invocation's bench/run ids unique (run ids are never reusable)."""
    bench, device = f"bench-a6-{suffix}", f"dev-a6-{suffix}"
    run_id = f"run-a6-{suffix}"
    descriptor = _descriptor_raw([_param("voltage", max_age_ms=500)])
    _seed_bench(gateway.store, gateway.content, bench, [(device, descriptor)])
    _admit_attachment(gateway.content, descriptor, ["voltage"])
    _seed_run(gateway.store, run_id, bench, [device], updated_at=NOW_ISO)
    _land(
        gateway.store,
        run_id,
        [{"parameter": "voltage", "observed_ms": _NOW_MS - 250, "value": 12.5}],
    )
    payload = json.dumps(
        {
            "subscription_id": f"sub-{run_id}",
            "sequence": 0,
            "kind": "telemetry",
            "reading": {
                "parameter": "voltage",
                "value": 99.9,
                "unit": "V",
                "observed_at": _iso(_NOW_MS - 250),
                "age_ms": 0,
                "quality": "valid",
                "source": "device",
            },
        },
        sort_keys=True,
    ).encode()
    row = gateway.store.connection.execute(
        "SELECT artifact_id FROM evidence WHERE context_key = ?", (f"run:{run_id}",)
    ).fetchone()
    assert row is not None
    # Corrupt the landed artifact in place: same row, wrong bytes. The
    # tampered payload is a VALID telemetry event with a different value,
    # so only the digest verification stands between it and the tile.
    gateway.store.connection.execute(
        "UPDATE artifacts SET data = ? WHERE artifact_id = ?",
        (payload, str(row[0])),
    )
    gateway.store.connection.commit()
    return bench, device


def test_a6_tampered_artifact_is_skipped_never_rendered(
    gateway: SimpleNamespace,
) -> None:
    bench, device = _seed_tampered_bench(gateway, suffix="main")
    page = _page(gateway, bench, device)
    zone = _tile_zone(page)
    assert "99.9" not in zone, "tampered bytes reached the tile"
    assert "12.5" not in zone, (
        "the row was consumed by the mismatch, so no value renders for it"
    )
    assert "Unavailable" in zone, "the digest mismatch degrades to honest absence"
    assert page.count("<form") == 0


def test_a6_mechanism_toggle_lets_tampered_value_through(
    gateway: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MECHANISM-TOGGLE CONTROL (design §8 A6): with the digest
    verification neutralized, the tampered value MUST reach the tile —
    proving the arm discriminates the mechanism and is not vacuously
    green (A6's assertion REDs under exactly this neutralization)."""
    bench, device = _seed_tampered_bench(gateway, suffix="toggle")
    from benchweave.interfaces import ui_readings

    def _unverified(
        content: ContentStore, artifact_id: str, expected_sha256: str
    ) -> bytes | None:
        chunk = content.artifact_chunk(artifact_id, 0, 65536)
        return bytes(chunk["data"])  # neutralized on purpose: no digest check

    monkeypatch.setattr(ui_readings, "_verified_payload", _unverified)
    zone = _tile_zone(_page(gateway, bench, device))
    assert "99.9" in zone, (
        "the toggle control is dead: A6 passes with the mechanism removed"
    )


# --- A7: attribution ambiguity and its DISCRIMINATOR control ---------------------


def test_a7_shared_parameter_declaration_refuses_attribution_for_both_devices(
    gateway: SimpleNamespace,
) -> None:
    bench, device, sibling = "bench-a7", "dev-a7", "dev-a7-sib"
    psu = _descriptor_raw([_param("voltage", max_age_ms=500)])
    sibling_v1 = _descriptor_raw([_param("voltage", max_age_ms=500)])
    _seed_bench(
        gateway.store, gateway.content, bench, [(device, psu), (sibling, sibling_v1)]
    )
    _admit_attachment(gateway.content, psu, ["voltage"])
    _admit_attachment(gateway.content, sibling_v1, ["voltage"])
    _seed_run(
        gateway.store, "run-a7", bench, [device, sibling], updated_at=NOW_ISO
    )
    _land(
        gateway.store,
        "run-a7",
        [{"parameter": "voltage", "observed_ms": _NOW_MS - 250, "value": 12.5}],
    )
    for dev in (device, sibling):
        zone = _tile_zone(_page(gateway, bench, dev))
        assert "Unavailable" in zone, f"ambiguous parameter rendered for {dev}"
        assert "12.5" not in zone, "no attribution guess (A7)"


def test_a7_discriminator_unique_declaration_populates(
    gateway: SimpleNamespace,
) -> None:
    """DISCRIMINATOR CONTROL (design §8 A7), reframed by the fold's F1:
    removing the sibling's declaration flips the refusal to a populated
    tile — which pins TODAY's behavior, parameter-name-only attribution,
    not a proof of correctness. The reading this arm seeds carries no
    device identity at all (exactly what a real landing carries), so the
    populated value is attributed by NAME: a sibling bound by the same
    run whose plugin streams an undeclared "voltage" is
    indistinguishable from this reading and is NOT caught — the census
    clause in ``ui_read.device_page`` names the case; the carrier (a
    persisted subscription->device resolution at landing) is an
    interface/host slice recorded in the #369 fold addendum."""
    bench, device, sibling = "bench-a7b", "dev-a7b", "dev-a7b-sib"
    psu = _descriptor_raw([_param("voltage", max_age_ms=500)])
    sibling_v1 = _descriptor_raw([_param("voltage", max_age_ms=500)])
    _seed_bench(
        gateway.store, gateway.content, bench, [(device, psu), (sibling, sibling_v1)]
    )
    _admit_attachment(gateway.content, psu, ["voltage"])
    _seed_run(
        gateway.store, "run-a7b", bench, [device, sibling], updated_at=NOW_ISO
    )
    _land(
        gateway.store,
        "run-a7b",
        [{"parameter": "voltage", "observed_ms": _NOW_MS - 250, "value": 12.5}],
    )
    assert "Unavailable" in _tile_zone(_page(gateway, bench, device))
    # Re-put the sibling WITHOUT the voltage declaration (whole-row
    # replace, the store's own semantics) and admit the new descriptor.
    sibling_v2 = _descriptor_raw([_param("current", max_age_ms=500)])
    gateway.store.put_device(
        sibling,
        bench,
        1,
        "[]",
        sibling_v2.decode(),
        "commissioned",
        "seed",
        NOW_ISO,
    )
    gateway.content.put_document(
        sibling_v2,
        hashlib.sha256(sibling_v2).hexdigest(),
        json.loads(sibling_v2),
        "urn:stg:seed-descriptor",
        NOW_ISO,
    )
    zone = _tile_zone(_page(gateway, bench, device))
    assert "12.5" in zone, "unique declaration must attribute the reading"


# --- A8: recency is the observation's own timestamp ------------------------------


def test_a8_recency_is_the_observation_timestamp_not_run_order(
    gateway: SimpleNamespace,
) -> None:
    bench, device = "bench-a8", "dev-a8"
    descriptor = _descriptor_raw([_param("voltage", max_age_ms=500)])
    _seed_bench(gateway.store, gateway.content, bench, [(device, descriptor)])
    _admit_attachment(gateway.content, descriptor, ["voltage"])
    # The NEWER run carries the OLDER observation (GW-23's spirit: run
    # order is not recency).
    _seed_run(
        gateway.store, "run-a8-old", bench, [device], updated_at="2026-10-03T00:00:01Z"
    )
    _land(
        gateway.store,
        "run-a8-old",
        [{"parameter": "voltage", "observed_ms": _NOW_MS - 250, "value": 12.5}],
    )
    _seed_run(
        gateway.store, "run-a8-new", bench, [device], updated_at="2026-10-03T00:00:02Z"
    )
    _land(
        gateway.store,
        "run-a8-new",
        [{"parameter": "voltage", "observed_ms": _NOW_MS - 1000, "value": 3.3}],
    )
    zone = _tile_zone(_page(gateway, bench, device))
    assert ">12.5 <small>" in zone, "the newest observed_at must win"
    assert ">3.3 <small>" not in zone, "run order must not decide recency"
    assert "run-a8-old" in zone, "the winner's run is the provenance"


# --- A9: bench scoping ----------------------------------------------------------


def test_a9_other_bench_rows_are_never_consulted(gateway: SimpleNamespace) -> None:
    local_bench, local_device = "bench-a9a", "dev-a9a"
    other_bench, other_device = "bench-a9b", "dev-a9b"
    descriptor = _descriptor_raw([_param("voltage", max_age_ms=500)])
    _seed_bench(gateway.store, gateway.content, local_bench, [(local_device, descriptor)])
    _admit_attachment(gateway.content, descriptor, ["voltage"])
    _seed_bench(gateway.store, gateway.content, other_bench, [(other_device, descriptor)])
    _admit_attachment(gateway.content, descriptor, ["voltage"])
    _seed_run(gateway.store, "run-a9", other_bench, [other_device], updated_at=NOW_ISO)
    _land(
        gateway.store,
        "run-a9",
        [{"parameter": "voltage", "observed_ms": _NOW_MS - 250, "value": 7.7}],
    )
    page = _page(gateway, local_bench, local_device)
    zone = _tile_zone(page)
    assert "Unavailable" in zone, "a value from another bench must not render"
    assert "7.7" not in page, "the join must never consult another bench's runs"


# --- A10: the scan budget --------------------------------------------------------


def test_a10_scan_budget_populates_newest_and_discloses_absence(
    budget: SimpleNamespace,
) -> None:
    bench, device = "bench-a10", "dev-a10"
    descriptor = _descriptor_raw(
        [
            _param("voltage", max_age_ms=500),
            _param("zero_window", max_age_ms=0),
            _param("no_window", max_age_ms=None),
        ]
    )
    _seed_bench(budget.store, budget.content, bench, [(device, descriptor)])
    _admit_attachment(budget.content, descriptor, ["voltage", "zero_window", "no_window"])
    _seed_run(budget.store, "run-a10", bench, [device], updated_at=NOW_ISO)
    # Rows ordered by stored_at descending: the two newest are voltage
    # and zero_window — inside the budget of 2; no_window's rows are
    # older and never decoded — absence disclosed, no exception.
    _land(
        budget.store,
        "run-a10",
        [
            {
                "parameter": "no_window",
                "observed_ms": _NOW_MS - 900,
                "value": 8.8,
                "host_received_at": "2026-10-03T00:00:00.010Z",
            },
            {
                "parameter": "no_window",
                "observed_ms": _NOW_MS - 950,
                "value": 9.9,
                "host_received_at": "2026-10-03T00:00:00.020Z",
            },
            {
                "parameter": "zero_window",
                "observed_ms": _NOW_MS - 1,
                "value": 2.0,
                "host_received_at": "2026-10-03T00:00:00.030Z",
            },
            {
                "parameter": "voltage",
                "observed_ms": _NOW_MS - 250,
                "value": 12.5,
                "host_received_at": "2026-10-03T00:00:00.040Z",
            },
        ],
    )
    zone = _tile_zone(_page(budget, bench, device))
    # Value assertions anchor on the tile's value element — a bare
    # substring like "9.9" also matches rendered timestamps such as
    # "…59.999000…" (observed while pinning this arm).
    assert ">12.5 <small>" in zone and ">2.0 <small>" in zone, (
        "the newest rows within budget populate"
    )
    assert ">8.8 <small>" not in zone and ">9.9 <small>" not in zone, (
        "rows beyond the budget leaked"
    )
    assert "Unavailable" in zone, "absence must be disclosed, not fabricated"


# --- A11: the landing lane's own validator ---------------------------------------


def test_a11_invalid_readings_are_skipped_by_the_landing_validator(
    gateway: SimpleNamespace,
) -> None:
    bench, device = "bench-a11", "dev-a11"
    descriptor = _descriptor_raw([_param("voltage", max_age_ms=500)])
    _seed_bench(gateway.store, gateway.content, bench, [(device, descriptor)])
    _admit_attachment(gateway.content, descriptor, ["voltage"])
    _seed_run(gateway.store, "run-a11-old", bench, [device], updated_at=NOW_ISO)
    _land(
        gateway.store,
        "run-a11-old",
        [{"parameter": "voltage", "observed_ms": _NOW_MS - 250, "value": 12.5}],
    )
    # A newer run whose rows are shape-invalid: a non-finite value and a
    # reading missing a required field. json.dumps serialises inf as
    # Infinity and json.loads parses it back — the landing lane stores
    # it (validation is the bridge's job); consumption must not trust it.
    bad_nonfinite = json.loads(
        json.dumps(
            {
                "subscription_id": "sub-run-a11-new",
                "sequence": 0,
                "kind": "telemetry",
                "reading": {
                    "parameter": "voltage",
                    "value": float("inf"),
                    "unit": "V",
                    "observed_at": _iso(_NOW_MS - 100),
                    "age_ms": 0,
                    "quality": "valid",
                    "source": "device",
                },
            }
        )
    )
    controller = StreamController(
        store=gateway.store,
        context_key="run:run-a11-new",
        wall=lambda: NOW_ISO,
        quota=_QUOTA,
    )
    missing_field = dict(bad_nonfinite)
    missing_field["reading"] = {
        key: value
        for key, value in bad_nonfinite["reading"].items()
        if key != "quality"
    }
    missing_field["sequence"] = 1
    _seed_run(
        gateway.store,
        "run-a11-new",
        bench,
        [device],
        updated_at="2026-10-03T00:00:05Z",
    )
    assert controller.land_events(
        [
            LandedEvent(event=bad_nonfinite, host_received_at=NOW_ISO),
            LandedEvent(event=missing_field, host_received_at=NOW_ISO),
        ]
    )
    zone = _tile_zone(_page(gateway, bench, device))
    assert "12.5" in zone, "the valid older reading still wins"
    assert "inf" not in zone.replace("Unavailable", ""), "an invalid value rendered"


# --- A12: route shape ------------------------------------------------------------


def test_a12_route_shape_read_only_and_no_mutating_control(
    gateway: SimpleNamespace,
) -> None:
    """The join adds no route and no mutating control: the populated
    device page carries no form or button (the G2b route-mapping
    enumeration — run in this battery — pins the route set itself)."""
    bench, device = "bench-a12", "dev-a12"
    descriptor = _descriptor_raw([_param("voltage", max_age_ms=500)])
    _seed_bench(gateway.store, gateway.content, bench, [(device, descriptor)])
    _admit_attachment(gateway.content, descriptor, ["voltage"])
    _seed_run(gateway.store, "run-a12", bench, [device], updated_at=NOW_ISO)
    _land(
        gateway.store,
        "run-a12",
        [{"parameter": "voltage", "observed_ms": _NOW_MS - 250, "value": 12.5}],
    )
    page = _page(gateway, bench, device)
    assert "12.5" in _tile_zone(page)
    assert "<form" not in page and "<button" not in page


# --- the refute lane's fold rows (F2/F3; F1's disclosure is comment-only) --------


#: The instrumentation taps for the F2 budget arms: counting wrappers
#: around the three store surfaces the join touches, patched onto the
#: CLASSES for the duration of one page GET (the join closes over the
#: app's own store/content instances; nothing else on the device page
#: calls these three methods during a GET).
_original_chunk = ContentStore.artifact_chunk
_original_rows_by_context = ContentStore.evidence_rows_by_context
_original_get_run = Store.get_run


def _corrupt_run_artifacts(store: Store, run_id: str) -> None:
    """Corrupt every landed artifact under one run context in place (the
    read-views H2 discipline, bulk form): evidence rows stay valid, the
    bytes no longer hash to their references — every open fails digest
    verification."""
    store.connection.execute(
        "UPDATE artifacts SET data = ? WHERE artifact_id IN"
        " (SELECT artifact_id FROM evidence WHERE context_key = ?)",
        (b"corrupted", f"run:{run_id}"),
    )
    store.connection.commit()


def _instrument_join(calls: dict[str, int], monkeypatch: pytest.MonkeyPatch) -> None:
    """Count the join's artifact opens, evidence queries and run reads."""

    def counting_chunk(
        self: ContentStore, artifact_id: str, offset: int, length: int
    ) -> dict[str, Any]:
        calls["opens"] += 1
        return _original_chunk(self, artifact_id, offset, length)

    def counting_rows(
        self: ContentStore, context_key: str, *, limit: int
    ) -> list[dict[str, Any]]:
        calls["queries"] += 1
        return _original_rows_by_context(self, context_key, limit=limit)

    def counting_get_run(self: Store, run_id: str) -> dict[str, Any] | None:
        calls["runs"] += 1
        return _original_get_run(self, run_id)

    monkeypatch.setattr(ContentStore, "artifact_chunk", counting_chunk)
    monkeypatch.setattr(ContentStore, "evidence_rows_by_context", counting_rows)
    monkeypatch.setattr(Store, "get_run", counting_get_run)


def test_f2_artifact_opens_are_bounded_across_runs(
    budget: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F2(i) (refute lane 1, MEDIUM): the scan budget must bound TOTAL
    artifact opens, not only successful decodes — rows failing digest
    verification are the cheap-to-forget case (measured pre-fold:
    scan_rows=2, five runs x four tampered rows -> 10 opens: the
    per-run SQL LIMIT clamps rows to scan_rows but nothing bounds the
    walk across runs). Five runs each carrying four tampered rows: two
    opens exhaust the budget of 2 and the walk stops inside the first
    queried run."""
    bench, device = "bench-f2a", "dev-f2a"
    descriptor = _descriptor_raw([_param("voltage", max_age_ms=500)])
    _seed_bench(budget.store, budget.content, bench, [(device, descriptor)])
    _admit_attachment(budget.content, descriptor, ["voltage"])
    for index in range(5):
        run_id = f"run-f2a-{index}"
        _seed_run(
            budget.store,
            run_id,
            bench,
            [device],
            updated_at=f"2026-10-03T00:00:0{index}Z",
        )
        _land(
            budget.store,
            run_id,
            [
                {
                    "parameter": "voltage",
                    "observed_ms": _NOW_MS - 250 - index,
                    "value": 1.0 + index,
                    "host_received_at": f"2026-10-03T00:00:0{index}.1{row}Z",
                }
                for row in range(4)
            ],
        )
        _corrupt_run_artifacts(budget.store, run_id)
    calls = {"opens": 0, "queries": 0, "runs": 0}
    _instrument_join(calls, monkeypatch)
    zone = _tile_zone(_page(budget, bench, device))
    assert "Unavailable" in zone, "tampered rows must never render"
    assert calls["opens"] <= 2, (
        f"artifact opens {calls['opens']} exceed the scan budget of 2"
    )
    assert calls["queries"] <= 1, (
        f"evidence queries {calls['queries']} continued past the exhausted budget"
    )


def test_f2_walk_stops_when_budget_fills(
    budget: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F2(ii) (refute lane 1, MEDIUM): once the budget fills, the walk
    must stop issuing store reads for the remaining runs (measured
    pre-fold: scan_rows=2, four runs -> 4 evidence queries + 4 get_run,
    get_run preceding the binding check). The newest run's two valid
    rows fill the budget; three older runs exist and must never be
    queried."""
    bench, device = "bench-f2b", "dev-f2b"
    descriptor = _descriptor_raw([_param("voltage", max_age_ms=500)])
    _seed_bench(budget.store, budget.content, bench, [(device, descriptor)])
    _admit_attachment(budget.content, descriptor, ["voltage"])
    _seed_run(
        budget.store, "run-f2b-new", bench, [device], updated_at="2026-10-03T00:00:09Z"
    )
    _land(
        budget.store,
        "run-f2b-new",
        [
            {
                "parameter": "voltage",
                "observed_ms": _NOW_MS - 250,
                "value": 12.5,
                "host_received_at": "2026-10-03T00:00:09.1Z",
            },
            {
                "parameter": "voltage",
                "observed_ms": _NOW_MS - 400,
                "value": 13.5,
                "host_received_at": "2026-10-03T00:00:09.2Z",
            },
        ],
    )
    for index in range(3):
        run_id = f"run-f2b-old-{index}"
        _seed_run(
            budget.store,
            run_id,
            bench,
            [device],
            updated_at=f"2026-10-03T00:00:0{index}Z",
        )
        _land(
            budget.store,
            run_id,
            [
                {
                    "parameter": "voltage",
                    "observed_ms": _NOW_MS - 600,
                    "value": 7.7,
                    "host_received_at": f"2026-10-03T00:00:0{index}.1Z",
                }
            ],
        )
    calls = {"opens": 0, "queries": 0, "runs": 0}
    _instrument_join(calls, monkeypatch)
    zone = _tile_zone(_page(budget, bench, device))
    assert ">12.5 <small>" in zone, "the budgeted rows did not populate"
    assert calls["queries"] <= 1, (
        f"evidence queries {calls['queries']} continued past the filled budget"
    )
    assert calls["runs"] <= 1, (
        f"get_run calls {calls['runs']} continued past the filled budget"
    )


def test_f3_corrupt_reference_row_is_skipped_per_row(
    gateway: SimpleNamespace,
) -> None:
    """F3 (refute lane 1, LOW): a corrupt ``content_ref_json`` column
    kills exactly its own row, never the join — the newest row's
    reference corrupted in place (direct SQL, the store-level corruption
    class), the older valid row still populates."""
    bench, device = "bench-f3", "dev-f3"
    descriptor = _descriptor_raw([_param("voltage", max_age_ms=500)])
    _seed_bench(gateway.store, gateway.content, bench, [(device, descriptor)])
    _admit_attachment(gateway.content, descriptor, ["voltage"])
    _seed_run(gateway.store, "run-f3", bench, [device], updated_at=NOW_ISO)
    _land(
        gateway.store,
        "run-f3",
        [
            {
                "parameter": "voltage",
                "observed_ms": _NOW_MS - 250,
                "value": 12.5,
                "host_received_at": "2026-10-03T00:00:00.010Z",
            },
            {
                "parameter": "voltage",
                "observed_ms": _NOW_MS - 400,
                "value": 44.4,
                "host_received_at": "2026-10-03T00:00:00.020Z",
            },
        ],
    )
    gateway.store.connection.execute(
        "UPDATE evidence SET content_ref_json = ? WHERE context_key = ?"
        " AND stored_at = ?",
        ("{oops", "run:run-f3", "2026-10-03T00:00:00.020Z"),
    )
    gateway.store.connection.commit()
    zone = _tile_zone(_page(gateway, bench, device))
    assert ">12.5 <small>" in zone, (
        "one corrupt reference row aborted the whole join"
    )


# --- the limits row (service parameter plumbing) ---------------------------------


def test_scan_rows_limit_row_and_env_knob_exist() -> None:
    """The budget is a service parameter in ``app_entry._LIMITS`` with a
    fail-loud env override (the G2a knobs' class) — never a bench
    envelope (A02 governs bench hazards, not page budgets)."""
    from benchweave.interfaces import app_entry

    assert app_entry._LIMITS["ui_reading_scan_rows"] >= 1
    assert (
        "ui_reading_scan_rows",
        "BENCHWEAVE_UI_READING_SCAN_ROWS",
    ) in app_entry._QUOTA_ENV_KEYS
