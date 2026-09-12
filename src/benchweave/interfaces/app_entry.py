"""Test-support ASGI entry: the composed gateway from the environment.

``uvicorn benchweave.interfaces.app_entry:app`` (or a programmatic
``uvicorn.run(app_entry.build(), ...)``) boots exactly what ``create_app``
composes for the integration suites — bootstrap, REST ``/v1``, the MCP
mount, the run worker — reading its inputs from the environment so a
child process can run the real app against a chosen database file:

- ``BENCHWEAVE_DB`` (required): state database path.
- ``BENCHWEAVE_PORT``: the intended port (uvicorn owns the actual bind).
- ``BENCHWEAVE_FIXTURES``: fixtures directory (default: the repository
  execution lattice, resolved like the app's plugin root).
- ``BENCHWEAVE_SECRET``: identity issuer secret (default: the suites' test
  secret; production packaging — WP08 — supplies the real one).

This module exists so kill/restart orchestration can drive the same
composition in a separate OS process (Task 11); it adds no behaviour.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI

from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.state.store import Store

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_FIXTURES = _REPO_ROOT / "fixtures" / "execution"
_DEFAULT_SECRET = b"wp07-task-eleven-secret"
_LIMITS: dict[str, int] = {
    "max_json_bytes": 1048576,
    "max_page_size": 1000,
    "max_chunk_bytes": 65536,
    "max_lease_ms": 600000,
    "min_poll_ms": 100,
    "max_admission_ms": 5000,
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _now_epoch() -> int:
    return int(datetime.now(UTC).timestamp())


def build() -> FastAPI:
    """Compose the gateway from ``BENCHWEAVE_*`` environment inputs."""
    db_path = os.environ["BENCHWEAVE_DB"]
    fixtures = Path(os.environ.get("BENCHWEAVE_FIXTURES", str(_DEFAULT_FIXTURES)))
    secret = os.environ.get("BENCHWEAVE_SECRET", _DEFAULT_SECRET.decode()).encode()
    store = Store.open(db_path, check_same_thread=False)
    content = ContentStore(store)
    return create_app(
        store=store,
        content=content,
        secret=secret,
        limits=_LIMITS,
        gateway_id="gw-app-entry",
        fixtures_dir=fixtures,
        now_iso=_now_iso,
        now_epoch=_now_epoch,
    )


app = build()
