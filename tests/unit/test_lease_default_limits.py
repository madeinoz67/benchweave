"""The #307-ruled 6-hour manual lease default (G3a carries it, design
record §2.6): every in-tree artifact declaring the gateway's default
``max_lease_ms`` moves in one commit, and a booted gateway whose limits
come from the app-entry defaults PUBLISHES the ruled value.

The floors-vs-limit sanity the exit gate names (#307's closing reading):
at 21 600 000 ms the GW-44 percentages dominate (72 min / 18 min) and
both floors are inert by design — the pure predicate matrix in
``tests/interfaces_ui/test_ui_control_leases.py`` pins the pair at that
duration.
"""

from __future__ import annotations

import sys
from pathlib import Path

from starlette.testclient import TestClient

from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.state.store import Store

# The integration conftest's sys.path-insertion precedent: the G2 UI
# suite's shared gateway constants (a tracked, denylisted secret
# literal — never a new one here; the app-entry production posture test
# greps the tracked tree for secret-shaped literals).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interfaces_ui"))
from ui_gateway_support import FIXTURES, NOW_EPOCH, NOW_ISO, SECRET

#: #307's closing ruling: the 6-hour manual lease default.
RULED_DEFAULT_MS = 21_600_000


def test_app_entry_default_is_the_ruled_six_hours() -> None:
    from benchweave.interfaces import app_entry

    assert app_entry._LIMITS["max_lease_ms"] == RULED_DEFAULT_MS


def test_cli_demo_default_is_the_ruled_six_hours() -> None:
    from benchweave.cli import demo

    assert demo.DEFAULT_LIMITS["max_lease_ms"] == RULED_DEFAULT_MS


def test_booted_gateway_publishes_the_ruled_default() -> None:
    """A gateway composed from the app-entry default limits publishes
    the ruled value on the wire (``gateway_info.limits``) — the arm the
    exit gate reads as the floors' sanity check."""
    import pathlib
    import tempfile

    from benchweave.interfaces import app_entry

    tmp = pathlib.Path(tempfile.mkdtemp())
    store = Store.open(str(tmp / "state.sqlite"), check_same_thread=False)
    app = create_app(
        store=store,
        content=ContentStore(store),
        secret=SECRET,
        limits=app_entry._limits_from_env(),
        gateway_id="lease-default",
        fixtures_dir=FIXTURES,
        now_iso=lambda: NOW_ISO,
        now_epoch=lambda: NOW_EPOCH,
    )
    with TestClient(app) as client:
        response = client.get(
            "/v1",
            headers={"Authorization": "Bearer " + _token()},
        )
        assert response.status_code == 200
        published = response.json()["data"]["limits"]["max_lease_ms"]
    assert published == RULED_DEFAULT_MS
    store.close()


def _token() -> str:
    from benchweave.interfaces.identity import issue

    return issue(
        SECRET,
        principal="default-check",
        audience="stg",
        scopes={"stg:observe"},
        expires_at=NOW_EPOCH + 3600,
    )
