"""Issue #85, integration leg: a poisoned lattice refuses gateway BOOT.

The composed-gateway level pin (design §6 item 4): the lifespan's admission
refusal propagates — uvicorn reports application startup failed, the server
never binds — and the store the gateway would have served stays empty. The
stand-up is the poc_app pattern (own temp Store + own fixtures copy, never
repo state); the boot-failure observation is the second-gateway pattern
from test_backup_restore.
"""

from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path
from typing import Any

import uvicorn

from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.state.store import Store

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"
SECRET = b"issue85-startup-admission-secret"
NOW_ISO = "2026-09-20T00:00:00Z"
NOW_EPOCH = 1_800_000_000
GATEWAY_ID = "gw-issue85-refusal"
LIMITS: dict[str, int] = {
    "max_json_bytes": 1048576,
    "max_page_size": 1000,
    "max_chunk_bytes": 65536,
    "max_lease_ms": 600000,
    "min_poll_ms": 100,
    "max_admission_ms": 5000,
}


def test_startup_refuses_poisoned_lattice_and_leaves_store_empty(
    tmp_path: Path,
) -> None:
    lattice = tmp_path / "lattice"
    shutil.copytree(FIXTURES, lattice)
    # V1-style poison: an S01 capabilities/operations mismatch the gate
    # refuses (the unit file runs all five variants; one suffices here —
    # this test pins the composed-app propagation, not the refusal set).
    document: dict[str, Any] = json.loads(
        (lattice / "descriptor-sim-psu.json").read_bytes()
    )
    document["capabilities"].remove("invoke")
    (lattice / "descriptor-sim-psu.json").write_text(json.dumps(document, indent=2) + "\n")

    db_path = tmp_path / "state.sqlite"
    store = Store.open(db_path, check_same_thread=False)
    content = ContentStore(store)
    app = create_app(
        store=store,
        content=content,
        secret=SECRET,
        limits=LIMITS,
        gateway_id=GATEWAY_ID,
        fixtures_dir=lattice,
        now_iso=lambda: NOW_ISO,
        now_epoch=lambda: NOW_EPOCH,
    )
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5.0
    while not server.started and thread.is_alive():
        if time.monotonic() > deadline:
            break
        time.sleep(0.05)
    try:
        assert not server.started, (
            "a gateway must not boot on a lattice the admission gate refuses"
        )
        assert not thread.is_alive(), "the boot attempt must terminate, not linger"
        benches, _ = store.list_benches(limit=10, offset=0)
        devices, _ = store.list_devices("sim-bench", limit=10, offset=0)
        assert benches == [] and devices == []
        assert store.current_generation("sim-bench") == 0
    finally:
        server.should_exit = True
        thread.join(timeout=5.0)
        store.close()
