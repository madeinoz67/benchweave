"""GW-04: the composed app's routing, both postures (G2a, design §7-A/I).

With the UI enabled, ``/ui`` is the UI sub-application's own namespace:
its HTML, its 404 shape, its assets — never an MCP envelope, never REST.
With the UI disabled the router is ABSENT, not stubbed: every ``/ui`` path
falls to the catch-all mount. The mount-order mechanism is pinned by a
scratch-app toggle (the design's mechanism-toggle control): with the UI
mounted AFTER the catch-all, the ownership assertions go false.

Obligation 25's half of the pin: the pattern library (the static export)
is never served by production — no ``/ui/patterns`` path resolves.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from benchweave_ui_html import assets as ui_assets
from fastapi import FastAPI
from starlette.responses import JSONResponse
from starlette.testclient import TestClient
from starlette.types import Receive, Scope, Send
from ui_gateway_support import (
    boot,
    build_ui_gateway,
    live_session,
    module_gateway,
    stop,
    ui_token,
)

from benchweave.interfaces.operations import Operations
from benchweave.interfaces.sessions import SessionRecord

CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "internal" / "ui-contract.md"

#: The template-posture patterns, hoisted so the hardening is pinnable:
#: both compiled case-INSENSITIVE (CodeQL py/bad-tag-filter — a
#: case-sensitive match on <script>/on* misses <SCRIPT>/ONLOAD=, and the
#: two self-asserting arms at the top of the template test pin that).
_SCRIPT_TAG = re.compile(r"<script[^>]*>", re.IGNORECASE)
_INLINE_HANDLER = re.compile(r"\son\w+=", re.IGNORECASE)


@pytest.fixture(scope="module")
def ui_gateway(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SimpleNamespace]:
    """One live composed gateway (UI enabled) on a real loopback port."""
    app = module_gateway("ui-routing", tmp_path_factory.mktemp("ui-gateway"))
    server, thread, port = boot(app)
    yield SimpleNamespace(app=app, base=f"http://127.0.0.1:{port}", port=port)
    stop(server, thread)


@pytest.fixture()
def ui_session(ui_gateway: SimpleNamespace) -> SessionRecord:
    """A live browser session; ``session_id`` is the cookie value."""
    return live_session(ui_gateway.app)


def _owns_ui_namespace(response: Any) -> bool:
    """The GW-04 ownership property for an unknown /ui path: the UI's own
    404 shape (HTML + marker), never another surface's envelope.
    (Tolerant typing: starlette's TestClient returns its own Response
    type, a structural httpx twin.)"""
    return (
        response.status_code == 404
        and response.headers["content-type"].startswith("text/html")
        and "data-bw-ui-404" in response.text
        and "jsonrpc" not in response.text
    )


# --- GW-04: the six assertions, UI enabled ------------------------------------


def test_v1_is_still_rest_json(ui_gateway: SimpleNamespace) -> None:
    response = httpx.get(
        f"{ui_gateway.base}/v1/benches?limit=10&cursor=",
        headers={"Authorization": f"Bearer {ui_token()}"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["ok"] is True


def test_ui_with_session_is_html(
    ui_gateway: SimpleNamespace, ui_session: object
) -> None:
    response = httpx.get(
        f"{ui_gateway.base}/ui",
        cookies={"bw_session": ui_session.session_id},  # type: ignore[attr-defined]
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "data-bw-gateway-strip" in response.text
    # The redirect target stays inside /ui and carries no query (GW-92's
    # clean-URL shape: no code, no session material on the wire path).
    assert response.url.path.startswith("/ui")
    assert response.url.query == b""


def test_mcp_post_is_still_mcp(ui_gateway: SimpleNamespace) -> None:
    """Routing proof, not protocol proof: with the UI mounted, POST /mcp
    is still answered by the MCP application (its own error envelope for
    a non-JSON-RPC body), never by the UI's HTML."""
    response = httpx.post(f"{ui_gateway.base}/mcp", json={"jsonrpc": "2.0"})
    assert "text/html" not in response.headers.get("content-type", "")
    assert "data-bw-" not in response.text


def test_unknown_ui_path_is_the_ui_404(
    ui_gateway: SimpleNamespace, ui_session: object
) -> None:
    response = httpx.get(
        f"{ui_gateway.base}/ui/nope",
        cookies={"bw_session": ui_session.session_id},  # type: ignore[attr-defined]
    )
    assert _owns_ui_namespace(response), response.text[:200]


@pytest.mark.parametrize(
    "path",
    ["/ui/patterns", "/ui/patterns/", "/ui/patterns/components.html"],
)
def test_pattern_library_is_never_served(
    ui_gateway: SimpleNamespace, ui_session: object, path: str
) -> None:
    """Obligation 25's routing pin: production serves no pattern-library
    path (the dev posture is loopback file:// browsing)."""
    response = httpx.get(
        f"{ui_gateway.base}{path}",
        cookies={"bw_session": ui_session.session_id},  # type: ignore[attr-defined]
    )
    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]


def test_vendored_assets_are_served_from_the_inventory(
    ui_gateway: SimpleNamespace,
) -> None:
    for name, media in (
        ("tokens.css", "text/css"),
        ("htmx.min.js", "javascript"),
        ("sse.js", "javascript"),
        ("bw-host.js", "javascript"),
        ("host.css", "text/css"),
    ):
        response = httpx.get(f"{ui_gateway.base}/ui/assets/{name}")
        assert response.status_code == 200, name
        assert media in response.headers["content-type"], name
    # A name outside the inventory + alias set is a 404, never a traversal.
    assert (
        httpx.get(f"{ui_gateway.base}/ui/assets/..%2F..%2Fpyproject.toml").status_code
        == 404
    )


@pytest.mark.parametrize("path", ["/ui/openapi.json", "/ui/docs", "/ui/redoc"])
def test_the_docs_surfaces_are_absent(
    ui_gateway: SimpleNamespace, path: str
) -> None:
    """FOLD-1 (refute lane-2 MEDIUM): FastAPI's default docs surfaces on
    the UI sub-app were a live UNAUTHENTICATED surface on the auth slice
    (route names + handler docstrings, pre-session). The composition
    turns all three off; the pin stays here so they stay off."""
    response = httpx.get(f"{ui_gateway.base}{path}", follow_redirects=False)
    assert response.status_code == 404, path
    assert "data-bw-ui-404" in response.text  # the UI's own 404 owns them


def test_the_ui_app_generates_no_schema_and_no_route_is_in_schema() -> None:
    """The companion pins: openapi_url is None on the sub-app, and every
    UI route is include_in_schema=False — G2b's route-mapping gate
    enumerates the mounted routes and must meet exactly the declared
    set, so nothing may register a schema surface."""
    from benchweave.interfaces.sessions import SessionStore
    from benchweave.interfaces.ui import build_ui_app, build_ui_router

    store = SessionStore(now_epoch=lambda: 1)
    app = build_ui_app(
        cast(Operations, _NullOperations()),
        store,
        secret=b"schema-pin",
        limits={"max_json_bytes": 64},
    )
    assert app.openapi_url is None
    assert app.docs_url is None
    assert app.redoc_url is None
    router = build_ui_router(
        cast(Operations, _NullOperations()),
        store,
        secret=b"schema-pin",
        limits={"max_json_bytes": 64},
    )
    from fastapi.routing import APIRoute

    assert router.routes, "the UI router has no routes to pin"
    api_routes = cast(list[APIRoute], router.routes)
    assert all(route.include_in_schema is False for route in api_routes), [
        route.path for route in api_routes if route.include_in_schema
    ]


# --- GW-04: UI disabled means absent, not stubbed ------------------------------


@pytest.fixture(scope="module")
def disabled_base(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    app = build_ui_gateway(
        tmp_path_factory.mktemp("ui-disabled"), ui_enabled=False, name="disabled"
    )
    server, thread, port = boot(app)
    yield f"http://127.0.0.1:{port}"
    stop(server, thread)


def test_disabled_ui_is_absent(disabled_base: str) -> None:
    for path in ("/ui", "/ui/login", "/ui/assets/tokens.css", "/ui/nope"):
        response = httpx.get(f"{disabled_base}{path}", follow_redirects=False)
        assert response.status_code == 404, path
        # Absent, not stubbed: the UI's own shapes never appear.
        assert "data-bw-ui-404" not in response.text
        assert "data-bw-gateway-strip" not in response.text


def test_disabled_ui_leaves_v1_intact(disabled_base: str) -> None:
    response = httpx.get(
        f"{disabled_base}/v1/benches?limit=10&cursor=",
        headers={"Authorization": f"Bearer {ui_token()}"},
    )
    assert response.status_code == 200


# --- the mechanism-toggle control: mount order ---------------------------------


async def _catch_all_json(scope: Scope, receive: Receive, send: Send) -> None:
    """The stand-in for the MCP catch-all: JSON for every request."""
    if scope["type"] == "http":
        await JSONResponse({"detail": "catch-all"})(scope, receive, send)


def test_the_mount_order_is_the_mechanism(tmp_path: Path) -> None:
    """§7-A's control, on a scratch app: with the catch-all mounted FIRST
    (the order violation the composition rule forbids), the /ui ownership
    property goes FALSE — the same assertions test_unknown_ui_path asserts
    would RED. If this control ever stops discriminating (the ownership
    property holds under the wrong order), the GW-04 suite has stopped
    testing the mechanism."""
    from benchweave.interfaces.sessions import SessionStore
    from benchweave.interfaces.ui import build_ui_router

    store = SessionStore(now_epoch=lambda: 1)
    router = build_ui_router(
        cast(Operations, _NullOperations()),
        store,
        secret=b"toggle",
        limits={"max_json_bytes": 1024},
    )
    ui_app = FastAPI()
    ui_app.include_router(router)

    scrambled = FastAPI()
    scrambled.mount("/", _catch_all_json)
    scrambled.mount("/ui", ui_app)
    client = TestClient(scrambled)
    response = client.get("/ui/nope")
    assert not _owns_ui_namespace(response), (
        "the ownership property held under the WRONG mount order — the "
        "GW-04 arms no longer discriminate the mechanism"
    )
    assert response.headers["content-type"].startswith("application/json")


class _NullOperations:
    """An operations seam stand-in the router composes against; the
    routing arms must never reach it (every attribute access returns a
    callable that fails the test)."""

    def __getattr__(self, name: str) -> object:
        def _unreachable(*args: object, **kwargs: object) -> object:
            raise AssertionError(f"the routing arm must not reach operations.{name}")

        return _unreachable


# --- §7-I: construction-time asset verification --------------------------------


def _tamper(copy: Path, name: str) -> None:
    shutil.copytree(ui_assets.ASSETS_DIR, copy)
    if name == "__absent__":
        (copy / "sse.js").unlink()
        return
    doctored = bytearray((copy / name).read_bytes())
    doctored[0] = doctored[0] ^ 0x20
    (copy / name).write_bytes(bytes(doctored))


@pytest.mark.parametrize(
    ("tampered", "name"),
    [("byte", "themes.css"), ("absent", "__absent__")],
)
def test_create_app_refuses_on_drifted_assets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tampered: str,
    name: str,
) -> None:
    """§7-I: a tampered or missing vendored byte refuses COMPOSITION,
    naming the asset — before any route exists (there is no app object
    at all to serve the drift)."""
    copy = tmp_path / "assets"
    _tamper(copy, name)
    monkeypatch.setattr(ui_assets, "ASSETS_DIR", copy)
    with pytest.raises(RuntimeError) as refused:
        build_ui_gateway(tmp_path, name=f"tamper-{tampered}")
    assert ("themes.css" if tampered == "byte" else "sse.js") in str(refused.value)


# --- the index shell (GW-81) ----------------------------------------------------


def test_index_shell_shows_identity_strip_and_inventory(
    ui_gateway: SimpleNamespace, ui_session: object
) -> None:
    response = httpx.get(
        f"{ui_gateway.base}/ui",
        cookies={"bw_session": ui_session.session_id},  # type: ignore[attr-defined]
        follow_redirects=True,
    )
    page = response.text
    # GW-81: gateway identity + bench inventory + the session's principal
    # and scopes — nothing else is the session's to show.
    assert "ui-routing" in page  # the gateway id from gateway_info
    assert 'data-bw-principal="ui-shell"' in page
    assert "data-bw-scopes" in page and "stg:observe" in page
    # The seeded bench from startup admission renders as the inventory.
    assert "data-bw-bench-list" in page
    # The bearer token never reaches the browser (NFR-S1).
    assert ui_token() not in page


def test_index_without_session_renders_the_c3_unauthenticated_row(
    ui_gateway: SimpleNamespace,
) -> None:
    response = httpx.get(f"{ui_gateway.base}/ui", follow_redirects=True)
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("text/html")
    assert 'data-bw-refusal-code="unauthenticated"' in response.text


def test_the_carried_unauthenticated_row_is_the_contract_row() -> None:
    """The refusal wording the gateway renders is ui-contract.md §C.3's
    row, character for character — carried data, pinned to the authority
    so drift reds here rather than in a browser."""
    from benchweave.interfaces.ui import UNAUTHENTICATED_REFUSAL

    table = CONTRACT.read_text(encoding="utf-8")
    match = re.search(
        r"^\| `unauthenticated` \| `(\w+)` \| (.+?) \| `(\w+)` \| (.+?) \|$",
        table,
        re.MULTILINE,
    )
    assert match is not None, "the §C.3 unauthenticated row is missing from the contract"
    severity, what, sent, action = match.groups()
    assert UNAUTHENTICATED_REFUSAL.severity == severity
    assert UNAUTHENTICATED_REFUSAL.what_happened == what
    assert UNAUTHENTICATED_REFUSAL.sent_status == sent
    assert UNAUTHENTICATED_REFUSAL.operator_action == action


# --- template posture (what the CSP depends on) ---------------------------------


def test_gateway_templates_never_inline_script() -> None:
    templates = (
        Path(__file__).resolve().parents[2] / "src/benchweave/interfaces/ui_templates"
    )
    files = sorted(templates.glob("*.j2"))
    assert files, "the gateway host templates are missing"
    # The hardening is itself pinned first: uppercase variants MUST match.
    assert _SCRIPT_TAG.findall("<SCRIPT src='/x.js'></SCRIPT>"), (
        "the script-tag pattern misses uppercase <SCRIPT>"
    )
    assert _INLINE_HANDLER.search("<div ONLOAD='steal()'></div>"), (
        "the inline-handler pattern misses uppercase ON*"
    )
    for template in files:
        source = template.read_text(encoding="utf-8")
        for script in _SCRIPT_TAG.findall(source):
            assert ' src="' in script, f"{template.name}: a script tag without src"
        assert not _INLINE_HANDLER.search(source), f"{template.name}: an inline handler"
    base = (templates / "base.j2").read_text(encoding="utf-8")
    assert '"allowEval": false' in base
    assert '"selfRequestsOnly": true' in base


def test_every_ui_response_carries_referrer_policy_and_no_cors(
    ui_gateway: SimpleNamespace, ui_session: object
) -> None:
    for path in ("/ui", "/ui/assets/tokens.css", "/ui/nope"):
        response = httpx.get(
            f"{ui_gateway.base}{path}",
            cookies={"bw_session": ui_session.session_id},  # type: ignore[attr-defined]
            follow_redirects=True,
        )
        assert response.headers.get("referrer-policy") == "no-referrer", path
        assert not any(
            key.lower().startswith("access-control-") for key in response.headers
        ), path


def test_html_responses_carry_the_csp_with_frame_ancestors(
    ui_gateway: SimpleNamespace, ui_session: object
) -> None:
    response = httpx.get(
        f"{ui_gateway.base}/ui",
        cookies={"bw_session": ui_session.session_id},  # type: ignore[attr-defined]
        follow_redirects=True,
    )
    csp = response.headers.get("content-security-policy", "")
    assert "default-src 'none'" in csp
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert response.headers.get("x-content-type-options") == "nosniff"



@pytest.mark.parametrize("method", ["post", "head", "put"])
def test_non_get_ui_exact_discriminates_from_the_disabled_posture(
    ui_gateway: SimpleNamespace, disabled_base: str, method: str
) -> None:
    """Fold G1: with the UI ENABLED, a non-GET request to the exact /ui
    path must NOT look like the disabled posture's answer — the enabled
    app owns the path even for methods it refuses. The signature
    compared is (status, content-type, the UI marker family): identical
    answers would mean /ui ownership is GET-only, and the GW-04 arms
    would be blind to a routing change for every other verb."""
    enabled = httpx.request(method, f"{ui_gateway.base}/ui", follow_redirects=False)
    disabled = httpx.request(method, f"{disabled_base}/ui", follow_redirects=False)

    def signature(response: httpx.Response) -> tuple[int, str, bool, bool]:
        return (
            response.status_code,
            response.headers.get("content-type", ""),
            "data-bw-" in response.text,
            "jsonrpc" in response.text,
        )

    assert signature(enabled) != signature(disabled), (
        f"{method.upper()} /ui is indistinguishable between the enabled and "
        "disabled postures — the ownership pin discriminates GET only"
    )
