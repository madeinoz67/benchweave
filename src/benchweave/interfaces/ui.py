"""The gateway's browser UI: a third adapter over the one seam (G2a).

Every handler is the ``rest.py`` three-step translation with the Identity
source swapped: session cookie → ``SessionStore.resolve`` → seam call →
render. The browser never holds a bearer token (CON-15): the cookie is an
opaque id, and the adapter derives the seam's ``Identity`` from the
server-side record — never from request data.

Composition (``create_app``): the UI mounts at ``/ui`` BETWEEN the REST
include and the catch-all ``/`` mount, so it owns its namespace — an
unknown ``/ui`` path is this adapter's own 404 shape, never an MCP
envelope, and the pattern library is never served (obligation 25). At
construction with the UI enabled the composition verifies the renderer
package's vendored-asset inventory and REFUSES to compose on drift
(obligation 12's wiring; a host serves the assets only once the inventory
verifies).

The guard set (design §2.3, NFR-S4–S7) is the I1 ``security.py`` precedent
adapted: each guard is an individually omittable middleware object
installed on the UI sub-application — never on the whole gateway app — so
``/v1`` and ``/mcp`` behaviour is untouched by construction, and a
minus-one acceptance arm can prove which guard stops which attack. CORS
is not a guard because there is nothing to arm: no ``/ui`` response ever
carries a CORS header.
"""

from __future__ import annotations

import ipaddress
import json
import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from benchweave_ui_html import assets as ui_assets
from benchweave_ui_html.data import RefusalData
from benchweave_ui_html.partials import render_refusal
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from jinja2 import Environment, PackageLoader, StrictUndefined
from markupsafe import Markup
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from benchweave.interfaces.errors import FAILURE_HTTP, Failure, OperationFailure, failure
from benchweave.interfaces.identity import Identity, IdentityRejected, validate
from benchweave.interfaces.operations import Operations
from benchweave.interfaces.sessions import (
    LoginCodeRejected,
    MintRejected,
    SessionRecord,
    SessionStore,
)

_LOG = logging.getLogger(__name__)

#: ``frame-ancestors 'none'`` from day one (the I1 accepted-risk LOW is
#: not carried); htmx is configured via the page's meta element
#: (``allowEval=false``, ``selfRequestsOnly=true``) and a template test
#: refuses any ``<script>`` without ``src``.
CSP_POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'self'; "
    "connect-src 'self'; frame-ancestors 'none'"
)

_STATE_CHANGING = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: The cookie carries the opaque session id — never a token, never a
#: scope, never an expiry (CON-15).
SESSION_COOKIE = "bw_session"

#: The individually omittable guards (``minus one`` = the set minus one
#: name, the design's RED-arm construction). There is deliberately no
#: CORS entry: absence is the posture, pinned by test.
GUARD_NAMES: tuple[str, ...] = ("trusted_host", "body_cap", "csrf", "csp")
DEFAULT_GUARDS: frozenset[str] = frozenset(GUARD_NAMES)

#: The §C.3 row the session-less page renders. Carried data, pinned to
#: ``docs/internal/ui-contract.md``'s table by test (drift reds in the
#: suite, not in a browser). G2b generalises this to the full row table.
UNAUTHENTICATED_REFUSAL = RefusalData(
    code="unauthenticated",
    severity="warning",
    what_happened="The request was not accepted: the caller is not authenticated.",
    sent_status="NO",
    operator_action="Authenticate and submit again.",
)

_HOST_STATIC = Path(__file__).resolve().parent / "ui_static"

#: The host chrome alias the assets route serves beside the package's
#: inventory names (the gateway's own stylesheet — host content, not
#: package content).
_HOST_ASSETS: dict[str, Path] = {"host.css": _HOST_STATIC / "ui.css"}

_CONTENT_TYPES: dict[str, str] = {
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}

#: The rest.py token-shape map (the WP02 posture): token-shaped
#: rejections are 401 unauthenticated; audience/scope failures 403.
_AUTH_401_REASONS = frozenset({"malformed_token", "bad_signature", "expired"})


def _default_now_epoch() -> int:
    import time

    return int(time.time())


#: The gateway host's page templates (UR-01: hosts own pages, the
#: package owns components). Package-loaded so source checkouts and
#: wheel installs serve the same bytes.
_ENV = Environment(
    loader=PackageLoader("benchweave", "interfaces/ui_templates"),
    autoescape=True,
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


def _page(template: str, status: int = 200, **context: Any) -> HTMLResponse:
    return HTMLResponse(_ENV.get_template(template).render(**context), status_code=status)


def _resolve_session(request: Request, sessions: SessionStore) -> SessionRecord | None:
    """The live session behind the request's cookie, or ``None``."""
    value = request.cookies.get(SESSION_COOKIE)
    if not value:
        return None
    return sessions.resolve(value)


def _session_identity(record: SessionRecord) -> Identity:
    """The seam's Identity for a browser session — derived from the
    server-side record only (the rest.py rule holds: adapters never
    construct an Identity from request data; the session store is the
    server's own state)."""
    return Identity(
        principal=record.principal,
        audience=record.audience,
        scopes=record.scopes,
        expires_at=record.expires_at,
    )


# --- the guard set (I1 security.py adapted; scoped to the UI sub-app) ----------


def _host_is_trusted(header: str, bound_host: str, bound_port: int) -> bool:
    """Does ``header`` name THIS listener? (the I1 truth table, tightened)

    Bracketed IPv6 and an exact port match as in I1; then the name must
    either BE the bind's own name (IP literal or otherwise — a non-
    loopback LAN bind is exactly namable) or be ``localhost`` on a
    loopback bind. I1 additionally accepted any loopback literal when the
    bind was loopback (``[::1]`` on a ``127.0.0.1`` bind); that branch is
    deliberately NOT ported — a header naming another address family
    names another listener, and this guard never guesses.
    """
    if header.startswith("["):
        closing = header.find("]")
        if closing < 0:
            return False
        name = header[1:closing]
        port = header[closing + 1 :].lstrip(":")
    else:
        name, separator, port = header.partition(":")
        if not separator:
            return False
    if not port.isdigit() or int(port) != int(bound_port):
        return False
    if name == bound_host:
        return True
    if name.lower() == "localhost":
        try:
            return ipaddress.ip_address(bound_host).is_loopback
        except ValueError:
            return False
    return False


class TrustedHostGuard(BaseHTTPMiddleware):
    """Refuse DNS rebinding: the Host header must name this listener.

    The bound truth is the ASGI scope's own ``server`` entry — what the
    server ACTUALLY bound — falling back to the constructor pair when a
    transport does not provide one. The judgement itself is the pure
    ``_host_is_trusted`` function, so the truth table is directly
    testable (the I1 test shape).
    """

    def __init__(self, app: object, *, bound_host: str, bound_port: int) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._bound_host = bound_host
        self._bound_port = bound_port

    def trusted(self, header: str) -> bool:
        """Does ``header`` name this guard's configured listener?"""
        return _host_is_trusted(header, self._bound_host, self._bound_port)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        bound = request.scope.get("server")
        bound_host, bound_port = (
            (str(bound[0]), int(bound[1])) if bound is not None
            # The synthetic-transport fallback (real servers always set it).
            else (self._bound_host, self._bound_port)
        )
        header = request.headers.get("host", "")
        if not _host_is_trusted(header, bound_host, bound_port):
            return Response("refused: untrusted host header", status_code=403)
        return await call_next(request)


class BodyCapGuard(BaseHTTPMiddleware):
    """Refuse oversized request bodies before they are read (413).

    Pre-checks the ``Content-Length`` header on state-changing requests
    against ``max_json_bytes`` (the rest.py ceiling, as an omittable
    guard). Does NOT catch a chunked body sent without that header — the
    handler's own ceiling check reads that one; this guard is the outer
    refusal, not the only one.
    """

    def __init__(self, app: object, *, limit: int) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._limit = limit

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        length = request.headers.get("content-length")
        if (
            request.method in _STATE_CHANGING
            and length is not None
            and (not length.isdigit() or int(length) > self._limit)
        ):
            return Response(
                f"refused: body exceeds {self._limit} bytes", status_code=413
            )
        return await call_next(request)


class CsrfGuard(BaseHTTPMiddleware):
    """Session-bearing state changes must carry the page-delivered CSRF
    token (NFR-S4), beside a same-origin ``Origin`` check.

    Applies when a request BOTH carries a live session cookie AND changes
    state — the mint is deliberately exempt: it authenticates by Bearer
    (no ambient browser credential exists to ride). The token rides htmx
    ``hx-headers`` and is rendered into every page the session can act
    from; the comparison happens against the SERVER-side record, so a
    guessed token is a miss, not a leak.
    """

    def __init__(self, app: object, *, sessions: SessionStore) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._sessions = sessions

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        state_changing = request.method in _STATE_CHANGING
        # Every path inside the UI sub-app is a session path except the
        # mint (Bearer-authenticated; no ambient credential to ride).
        mint = request.url.path.startswith("/login-codes")
        if not (state_changing and not mint):
            return await call_next(request)
        cookie = request.cookies.get(SESSION_COOKIE)
        record = self._sessions.resolve(cookie) if cookie else None
        if record is None:
            return await call_next(request)  # the route renders unauthenticated
        origin = request.headers.get("origin")
        if origin is not None:
            own = f"{request.url.scheme}://{request.url.netloc}"
            if origin != own:
                return Response("refused: cross-origin state change", status_code=403)
        if request.headers.get("x-csrf-token") != record.csrf_token:
            return Response("refused: csrf token required", status_code=403)
        return await call_next(request)


class SecurityHeadersGuard(BaseHTTPMiddleware):
    """CSP on HTML responses; ``Referrer-Policy: no-referrer`` and
    ``X-Content-Type-Options: nosniff`` on every UI response (GW-92);
    no CORS header is ever set (there is no arming code to omit)."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Content-Security-Policy"] = CSP_POLICY
        return response


def install_ui_guards(
    app: FastAPI,
    *,
    guards: frozenset[str],
    sessions: SessionStore,
    max_json_bytes: int,
) -> None:
    """Add the armed guards in the fail-closed order (Starlette applies
    middleware last-added-first: trusted-host outermost, headers
    innermost — a rebinding refusal precedes everything else)."""
    if "csp" in guards:
        app.add_middleware(SecurityHeadersGuard)
    if "csrf" in guards:
        app.add_middleware(CsrfGuard, sessions=sessions)
    if "body_cap" in guards:
        app.add_middleware(BodyCapGuard, limit=max_json_bytes)
    if "trusted_host" in guards:
        app.add_middleware(TrustedHostGuard, bound_host="127.0.0.1", bound_port=0)


def _inventory_asset_names() -> frozenset[str]:
    """The names the package's committed inventory pins (read once at
    build; the composition-time verification is the integrity check)."""
    import json

    inventory = json.loads(
        (ui_assets.ASSETS_DIR / ui_assets.INVENTORY_NAME).read_text(encoding="utf-8")
    )
    return frozenset(row["path"] for row in inventory["assets"])


# --- the login-link flow (GW-90–92; the Q1 ruling verbatim) --------------------


def _redacting_access_formatter(
    fmt: str | None = None,
    datefmt: str | None = None,
    style: str = "%",
    use_colors: bool | None = None,
) -> logging.Formatter:
    """A uvicorn AccessFormatter that redacts the login code (R2).

    The access log line carries the request line with its query string,
    and the code RIDES that query; this formatter replaces any query on
    a ``/ui/login`` path with ``code=[redacted]`` before rendering —
    every other line renders unchanged. Built lazily (uvicorn imports at
    call time) so composing an app never pays the uvicorn import.
    """
    # ``style`` stays str-typed at the boundary; uvicorn's formatter
    # wants the Literal form, narrowed here (a runtime check, not an
    # assert — production code).
    if style not in ("%", "{", "$"):
        raise ValueError(f"unknown log format style: {style}")
    from uvicorn.logging import AccessFormatter

    class _Formatter(AccessFormatter):
        def formatMessage(self, record: logging.LogRecord) -> str:
            args = record.args
            if (
                isinstance(args, tuple)
                and len(args) >= 3
                and isinstance(args[2], str)
                and args[2].startswith("/ui/login")
            ):
                fields = record.__dict__.copy()
                fields["args"] = (
                    args[:2] + (args[2].split("?", 1)[0] + "?code=[redacted]",)
                    + args[3:]
                )
                return AccessFormatter.formatMessage(self, logging.makeLogRecord(fields))
            return AccessFormatter.formatMessage(self, record)

    # style is narrowed above; the Literal is uvicorn's own typing.
    return _Formatter(fmt, datefmt, style, use_colors)  # type: ignore[arg-type]


def build_serving_log_config() -> dict[str, Any]:
    """uvicorn's default logging config with the access formatter swapped
    for the redacting one — what ``benchweave serve`` installs; the
    login-code URL transit is once, and no log line keeps it."""
    import copy

    from uvicorn.config import LOGGING_CONFIG

    config = copy.deepcopy(LOGGING_CONFIG)
    config["formatters"]["access"]["()"] = _redacting_access_formatter
    return config


# --- the router ---------------------------------------------------------------


def ui_root_redirect() -> RedirectResponse:
    """``GET /ui`` → ``/ui/``: a mounted sub-app never sees the empty
    path, and Starlette's automatic slash-redirect computes its target
    from the SUB-app's root — landing on the catch-all mount (a routing
    defect the GW-04 suite caught). This explicit hop keeps the exact
    ``/ui`` URL inside the UI's own namespace."""
    return RedirectResponse("/ui/", status_code=307)


def build_ui_router(
    operations: Operations,
    sessions: SessionStore,
    *,
    secret: bytes,
    limits: Mapping[str, int],
    audience: str = "stg",
    now_epoch: Callable[[], int] | None = None,
) -> APIRouter:
    """The UI routes over the seam. UNPREFIXED by design: this router is
    included in the UI sub-application which itself mounts at ``/ui``
    (a router prefix here would double the path). The design's §2.1
    sketch (``prefix="/ui"``, ``include_router`` on the gateway app)
    deviates to a mounted sub-app so the guard set scopes to ``/ui``
    alone — see ``build_ui_app``. Plus ``secret`` — the mint's Bearer
    authentication structurally requires it (the sketch omitted it).
    Translation only, like ``rest.py``."""
    router = APIRouter()
    max_page_size = int(limits.get("max_page_size", 1000))
    max_json_bytes = int(limits.get("max_json_bytes", 1_048_576))
    asset_names = _inventory_asset_names()
    epoch = now_epoch if now_epoch is not None else _default_now_epoch

    def _bearer_identity(request: Request) -> Identity:
        """The rest.py ``_identity`` idiom verbatim: manual header parse
        (no HTTPBearer — our own 401 envelope), ``identity.validate``
        fail-closed, token-shaped rejections 401 and audience/scope
        failures 403."""
        header = request.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise OperationFailure(
                failure("unauthenticated", "bearer token required")
            )
        try:
            return validate(secret, token, audience=audience, now=epoch())
        except IdentityRejected as rejected:
            code = (
                "unauthenticated"
                if rejected.reason in _AUTH_401_REASONS
                else "forbidden"
            )
            raise OperationFailure(
                failure(code, f"token rejected: {rejected.reason}")
            ) from None

    def _envelope(fail: Failure) -> JSONResponse:
        return JSONResponse(fail.body(), status_code=FAILURE_HTTP[fail.code])

    async def _mint_body(request: Request) -> dict[str, Any]:
        """Optional JSON body (the rest.py ``_json_body`` idiom with an
        empty body meaning "all defaults"): ceiling before decode, dict
        or ``invalid_request``."""
        raw = await request.body()
        if len(raw) > max_json_bytes:
            raise OperationFailure(
                failure(
                    "payload_too_large",
                    f"body exceeds max_json_bytes ({max_json_bytes})",
                )
            )
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except ValueError:
            raise OperationFailure(
                failure("invalid_request", "body is not valid JSON")
            ) from None
        if not isinstance(parsed, dict):
            raise OperationFailure(
                failure("invalid_request", "body must be an object")
            )
        return parsed

    def _failure_page(fail: OperationFailure) -> HTMLResponse:
        """A seam failure renders through the shell with its own code,
        message and correlation id (GW-11's shape; G2b generalises to the
        full §C.3 row table and its induced-code matrix)."""
        return _page(
            "failure.j2",
            status=FAILURE_HTTP[fail.failure.code],
            title="Request refused",
            gateway_id=None,
            principal=None,
            scopes=None,
            mode_banner=None,
            csrf_token=None,
            failure=fail.failure,
        )

    @router.get("/", include_in_schema=False)
    async def index(request: Request) -> Response:
        """The shell (GW-80/81): gateway identity strip, the session's
        principal and scopes, the bench inventory."""
        record = _resolve_session(request, sessions)
        if record is None:
            return _page(
                "refusal-page.j2",
                status=401,
                title="Authentication required",
                gateway_id=None,
                principal=None,
                scopes=None,
                mode_banner=None,
                csrf_token=None,
                # Trusted package-rendered HTML (the §C.3 partial), not
                # request data — S704's escape hatch is not in play.
                refusal_html=Markup(render_refusal(UNAUTHENTICATED_REFUSAL)),  # noqa: S704
            )
        identity = _session_identity(record)
        try:
            info = operations.gateway_info(identity)
            items, _next = operations.bench_list(
                identity, limit=max_page_size, cursor=None
            )
        except OperationFailure as fail:
            return _failure_page(fail)
        return _page(
            "index.j2",
            title="Benches",
            gateway_id=str(info["gateway_id"]),
            principal=record.principal,
            scopes=sorted(record.scopes),
            # The §D mode banner's slot (GW-80 machinery): bench pages
            # populate it in G2b; the index carries no bench, so no
            # active modes and no banner (§D: absence is meaningful).
            mode_banner=None,
            # NFR-S4 machinery: the page-delivered CSRF token (htmx
            # hx-headers consume it; G2a's only state-changing control is
            # logout, G3 wires the rest).
            csrf_token=record.csrf_token,
            benches=items,
        )

    @router.post("/login-codes", status_code=201)
    async def mint_login_code(request: Request) -> Response:
        """Mint one single-use login code (GW-90, the Q1 ruling).

        Bearer-authenticated (``identity.validate``; adapters never
        construct an Identity from request data). Optional body:
        ``scopes`` (a subset of the caller's) and ``ttl_seconds`` (bounded
        by the caller token's expiry and the configured ceiling) —
        widening is REFUSED ``forbidden``, never clamped (NFR-S2); shape
        violations are ``invalid_request``. The response carries exactly
        the login URL; the code's only raw existence is here.
        """
        try:
            identity = _bearer_identity(request)
            body = await _mint_body(request)
            scopes_raw = body.get("scopes")
            scopes: frozenset[str] | None = None
            if scopes_raw is not None:
                if not isinstance(scopes_raw, list) or not all(
                    isinstance(item, str) and item for item in scopes_raw
                ):
                    raise OperationFailure(
                        failure("invalid_request", "scopes must be a list of strings")
                    )
                scopes = frozenset(scopes_raw)
            ttl_raw = body.get("ttl_seconds")
            if ttl_raw is not None and not isinstance(ttl_raw, int):
                raise OperationFailure(
                    failure("invalid_request", "ttl_seconds must be an integer")
                )
            code = sessions.mint_login_code(
                identity, scopes=scopes, ttl_seconds=ttl_raw
            )
        except OperationFailure as fail:
            return _envelope(fail.failure)
        except MintRejected as refused:
            return _envelope(
                failure(
                    "forbidden" if refused.reason == "forbidden" else "invalid_request",
                    f"mint refused: {refused.reason}",
                )
            )
        return JSONResponse(
            {"ok": True, "data": {"login_url": f"{request.base_url}ui/login?code={code}"}},
            status_code=201,
        )

    @router.get("/login")
    async def login(request: Request) -> Response:
        """Exchange a login code for a session, exactly once (GW-91/92).

        Unknown, expired and used codes render the §C.3 unauthenticated
        refusal identically (the caller learns nothing about which codes
        exist); the refusal class rides the server log — never the code.
        Success is a 303 to a CODE-FREE URL with the session cookie and
        ``Referrer-Policy: no-referrer`` (the header guard carries it on
        every UI response).
        """
        code = request.query_params.get("code", "")
        try:
            record = sessions.exchange(code)
        except LoginCodeRejected as refused:
            _LOG.info("ui login exchange refused: %s", refused.reason)
            return _page(
                "refusal-page.j2",
                status=401,
                title="Authentication required",
                gateway_id=None,
                principal=None,
                scopes=None,
                mode_banner=None,
                csrf_token=None,
                refusal_html=Markup(render_refusal(UNAUTHENTICATED_REFUSAL)),  # noqa: S704
            )
        response = RedirectResponse("/ui/", status_code=303)
        response.set_cookie(
            SESSION_COOKIE,
            record.session_id,
            httponly=True,
            samesite="strict",
            path="/ui",
            secure=request.url.scheme == "https",
            max_age=max(0, record.expires_at - epoch()),
        )
        return response

    @router.post("/logout")
    async def logout(request: Request) -> Response:
        """Delete the session server-side (GW-94): the cookie alone is
        dead from this moment. CSRF-enforced by the guard (the per-session
        token beside a same-origin Origin check, NFR-S4); this handler
        only acts on the already-authenticated session."""
        record = _resolve_session(request, sessions)
        if record is None:
            return _page(
                "refusal-page.j2",
                status=401,
                title="Authentication required",
                gateway_id=None,
                principal=None,
                scopes=None,
                mode_banner=None,
                csrf_token=None,
                refusal_html=Markup(render_refusal(UNAUTHENTICATED_REFUSAL)),  # noqa: S704
            )
        sessions.logout(record.session_id)
        response = RedirectResponse("/ui/", status_code=303)
        response.delete_cookie(SESSION_COOKIE, path="/ui")
        return response

    @router.get("/assets/{name}", include_in_schema=False)
    async def asset(name: str) -> Response:
        """Vendored assets, inventory-named (plus the host-chrome alias).
        A name outside the set is a 404 — there is no filesystem path
        here to traverse."""
        source: Path | None = None
        if name in _HOST_ASSETS:
            source = _HOST_ASSETS[name]
        elif name in asset_names:
            source = ui_assets.ASSETS_DIR / name
        if source is None or not source.is_file():
            return _not_found()
        return FileResponse(
            source,
            media_type=_CONTENT_TYPES.get(source.suffix, "application/octet-stream"),
        )

    def _not_found() -> HTMLResponse:
        return _page(
            "not-found.j2",
            status=404,
            title="Not found",
            gateway_id=None,
            principal=None,
            scopes=None,
            mode_banner=None,
            csrf_token=None,
        )

    @router.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
        include_in_schema=False,
    )
    async def ui_not_found(request: Request, path: str) -> Response:
        """The UI's own 404: the sub-application owns its namespace, so
        an unknown ``/ui`` path is this shape — never an MCP envelope
        (GW-04) and never the pattern library (obligation 25)."""
        return _not_found()

    return router


def build_ui_app(
    operations: Operations,
    sessions: SessionStore,
    *,
    secret: bytes,
    limits: Mapping[str, int],
    audience: str = "stg",
    now_epoch: Callable[[], int] | None = None,
    guards: frozenset[str] = DEFAULT_GUARDS,
) -> FastAPI:
    """The UI sub-application: the router plus its guard set.

    Composed as a MOUNTED SUB-APP (not ``include_router`` on the gateway
    app, and the router itself is unprefixed) so the guards scope to
    ``/ui`` alone — wrapping the whole gateway, including the MCP mount's
    streaming transport, in ``BaseHTTPMiddleware`` would put a new
    middleware layer on a frozen surface; the sub-app keeps that
    structurally impossible. The mount-ordering rule (before the
    catch-all ``/``) lives in ``create_app`` and is pinned by the GW-04
    suite's toggle control.
    """
    app = FastAPI(title="BenchWeave UI")
    app.include_router(
        build_ui_router(
            operations,
            sessions,
            secret=secret,
            limits=limits,
            audience=audience,
            now_epoch=now_epoch,
        )
    )
    install_ui_guards(
        app,
        guards=guards,
        sessions=sessions,
        max_json_bytes=int(limits.get("max_json_bytes", 1_048_576)),
    )
    return app


def build_session_store(
    limits: Mapping[str, int], *, now_epoch: Callable[[], int]
) -> SessionStore:
    """The store from the limits table, with the documented defaults when
    a caller's table omits the keys (the operational default path is
    ``app_entry._LIMITS``; the knobs are service parameters, not bench
    safety envelopes — A02 governs bench hazards, not session TTLs)."""
    return SessionStore(
        now_epoch=now_epoch,
        code_ttl_s=int(limits.get("ui_login_code_ttl_ms", 60_000)) // 1000,
        session_ttl_s=int(limits.get("ui_session_ttl_ms", 28_800_000)) // 1000,
    )
