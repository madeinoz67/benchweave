"""The G3 control routes (issue #304 G3a): lease take/renew/release as
one-operation translations over the seam, the polled control-region
fragment, GW-95's session bound, GW-44's warnings and the ``no-lease``
mode entry.

Every handler is the rest.py three-step translation with the Identity
source swapped (session → seam → render), the exact G2 shapes. The
module's rules: GW-10's one-operation-per-mutating-route discipline;
the seam is the authority (the adapter's ONE pre-send refusal is
GW-95's — a lease that would outlive its session — every other refusal
is the seam's, rendered through its own §C.3 row); no background
renewal (GW-41/57); the poll is a read (NFR-O1, pinned by test).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from benchweave_ui_html.data import (
    AlertBubbleData,
    DisabledLabelData,
    ModeBannerData,
    ModeEntry,
)
from benchweave_ui_html.partials import (
    render_alert_bubble,
    render_disabled_label,
    render_mode_banner,
)
from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse
from markupsafe import Markup, escape

from benchweave.interfaces.errors import OperationFailure, failure
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.operations import TIER_SATISFIES, Operations
from benchweave.interfaces.sessions import (
    HeldLease,
    SessionRecord,
    SessionStore,
)

#: GW-44's floors (the record §2.2, the Q2 ruling); the percentages ride
#: the predicate body. The floors guarantee a minimum reaction window
#: for short-lease configurations; at the commissioned 6-hour default
#: the percentages dominate and the floors are inert.
WARN_FLOOR_MS = 120_000
CRITICAL_FLOOR_MS = 30_000

#: The take/renew forms' offered minimum duration — GW-95's disabled
#: shape's denominator: when the session's remaining time is below this,
#: every offered duration would outlive the session.
FORM_MIN_DURATION_MS = 60_000

#: The polled fragment's base cadence (fork F3): a service knob
#: (``ui_panel_poll_ms`` in the limits table, env
#: ``BENCHWEAVE_UI_PANEL_POLL_MS``), tightened ÷6 inside warning and
#: ÷30 inside critical. A service parameter in the ui_* class — NOT a
#: bench safety envelope (A02 governs bench hazards).
DEFAULT_PANEL_POLL_MS = 30_000

#: The staging panel's selector reads the bench's own first events page
#: for candidate binding refs (admission's ``authority_changed`` rows
#: are the oldest in the stream); the trip predicate separately walks
#: the retained tail to its newest row (ui_staging.read_bench_events).
_CONTROLS_EVENTS_PAGE = 20

#: The release control's fixed reason. The release control is one click;
#: the reason names the action's class (the seam's minimum is one
#: character and this is the honest description).
_RELEASE_REASON = "released via the gateway UI"

#: The control tier the lease operations require — the SAME lattice the
#: seam's ``require_permission("control")`` judges (observe ⊆ control ⊆
#: admin), so the rendered controls never claim less authority than the
#: seam would grant (FOLD-7; the literal-scope check mislabelled an
#: admin-only session observe-only).
_CONTROL_TIER = "control"


def expiry_warning(remaining_ms: int, duration_ms: int) -> str | None:
    """GW-44's pure threshold predicate (the record §2.2, Q2's max()
    semantics): ``None`` | ``"warning" | "critical"``.

    ``warn_at = max(duration//5, 120 000)``; ``critical_at =
    max(duration//20, 30 000)``. Inside both, critical wins (the tier
    ordering the matrix test pins). Pure: the caller injects the clock
    by passing the remaining time; nothing here reads a wall.
    """
    warn_at = max(duration_ms // 5, WARN_FLOOR_MS)
    critical_at = max(duration_ms // 20, CRITICAL_FLOOR_MS)
    if remaining_ms <= critical_at:
        return "critical"
    if remaining_ms <= warn_at:
        return "warning"
    return None


def _parse_iso_to_epoch(stamp: str) -> int | None:
    """The stored stamp is the read-time oracle: parse it to epoch
    seconds, or ``None`` when it is not parseable — a corrupt stamp
    never fabricates a deadline (the seam's own fail-closed idiom)."""
    try:
        moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int(moment.timestamp())


def _format_epoch(epoch_s: int) -> str:
    """Wall-time display for a stated expiry (GW-95's "session expiry
    stated (wall time)")."""
    return datetime.fromtimestamp(epoch_s, tz=UTC).strftime("%Y-%m-%d %H:%M UTC")


def bench_mode(held: HeldLease | None, *, now_epoch: Callable[[], int]) -> str | None:
    """GW-42's bench-scoped mode key: the ``no-lease`` entry fires when
    the session holds NO LIVE view for the bench — no view at all, or
    the view's stored expiry has passed (the same read-time arithmetic
    the seam's own ``_live_lease`` oracle applies). ``None`` renders no
    banner; per §D absence asserts full-authority presentation."""
    if held is None:
        return "no-lease"
    expiry_s = _parse_iso_to_epoch(stamp=held.expires_at)
    if expiry_s is None or now_epoch() >= expiry_s:
        return "no-lease"
    return None


#: The trip-lifecycle kinds on the bench event wire: a ``trip`` raises
#: protection-active; a ``bench_changed`` — the ONLY wire shadow an
#: applied trip_reset has (the closed event def has no channel for the
#: change kind) — clears it.
_TRIP_LIFECYCLE = frozenset({"trip", "bench_changed"})


def trip_active(events: list[dict[str, Any]]) -> bool:
    """§2.5's wire-honest trip predicate over the bench's event rows:
    protection-active iff the NEWEST trip-lifecycle event (by sequence)
    is a ``trip``.

    Disclosed boundaries (the record §2.5, each pinned by test): (a) the
    gateway's own bench projection hardcodes ``tripped=False`` — this
    predicate consumes the gateway's own ``trip`` events, the only live
    trip signal the wire carries, and §C.1's row is presentation-level;
    (b) an admin configuration activation after a trip ALSO emits
    ``bench_changed`` and therefore also clears the marker (the err-clear
    boundary the owner accepted as disclosed); (c) retention may have
    dropped an old trip past the window — no trip-lifecycle row is no
    verdict, never protection-active. The gateway's own start checks stay
    authoritative and carry no trip gate (G3-D3 files that seam gap).
    """
    newest: tuple[int, str] | None = None
    for row in events:
        kind = str(row.get("kind", ""))
        if kind not in _TRIP_LIFECYCLE:
            continue
        try:
            sequence = int(row.get("sequence", 0))
        except (TypeError, ValueError):
            sequence = 0
        if newest is None or sequence >= newest[0]:
            newest = (sequence, kind)
    return newest is not None and newest[1] == "trip"


def _iter_steps(steps: list[Any]) -> Any:
    """Yield every step in a procedure's step tree, recursing through the
    structured kinds' nested bodies (``if.then`` / ``if.else`` /
    ``repeat.steps``) — an author cannot hide an enable by nesting it."""
    for step in steps:
        if not isinstance(step, dict):
            continue
        yield step
        for key in ("then", "else", "steps"):
            nested = step.get(key)
            if isinstance(nested, list):
                yield from _iter_steps(nested)


def energy_sourcing(procedure: dict[str, Any]) -> bool:
    """GW-52's energy classification — a pure function of the admitted
    procedure document: energy-sourcing IFF any ``invoke`` step's input
    carries ``"enabled": true`` (R-ENERGISE-1's enabling clause,
    mechanically derivable from admitted documents).

    Disclosed boundary (the record §2.4/G3-D2): "changing a setpoint of
    a currently-energised output" is NOT derivable from documents — it
    needs live device state — and is uncovered at run-start granularity.
    A procedure whose every enable-shaped input is false or absent is the
    de-energising class. The classifier errs toward MORE confirmation
    only by rule change, never silently.
    """
    for step in _iter_steps(procedure.get("steps", [])):
        if step.get("kind") != "invoke":
            continue
        action_input = step.get("input")
        if isinstance(action_input, dict) and action_input.get("enabled") is True:
            return True
    return False


def session_warning_bubble(
    record: SessionRecord, *, now_epoch: Callable[[], int]
) -> Markup | None:
    """D1 (GW-44's session half): the shell warning over the session's
    remaining time and GRANTED duration. Names what is lost — the
    session ends and leases held by it cannot be renewed afterwards
    (GW-95's rationale) — and the clearing action (``ui-login``).
    Severity classes per §B.1. ``duration_s <= 0`` (not recorded)
    composes no verdict."""
    if record.duration_s <= 0:
        return None
    remaining_ms = max(record.expires_at - now_epoch(), 0) * 1000
    level = expiry_warning(remaining_ms, record.duration_s * 1000)
    if level is None:
        return None
    expires_display = _format_epoch(record.expires_at)
    message = (
        f"This session ends at {expires_display}. Leases it holds cannot be"
        " renewed afterwards. Run benchweave ui-login for a longer session."
    )
    if level == "critical":
        bubble = AlertBubbleData(
            severity="critical",
            title="Browser session ending",
            message=message,
            live_region="alert",
            dismissible=False,
        )
    else:
        bubble = AlertBubbleData(
            severity="warning",
            title="Browser session ending soon",
            message=message,
            live_region="status",
            dismissible=True,
        )
    # Trusted package-rendered markup for the shell slot (S704's escape
    # hatch not in play — every interpolable byte is escaped data).
    return Markup(render_alert_bubble(bubble))  # noqa: S704  # trusted partial


def mode_banner_markup(mode: str) -> Markup:
    """The single-entry §D.1 banner for one active mode (``no-lease`` in
    G3a). Trusted markup: the package renders it from the contract's own
    fixed wording, never request data."""
    wording = {"no-lease": "NO CONTROLLER LEASE · ACTIONS CANNOT BE AUTHORISED"}.get(
        mode
    )
    if wording is None:
        raise ValueError(f"unknown mode key: {mode!r}")
    banner = ModeBannerData(modes=(ModeEntry(key="no-lease", wording=wording),))
    # Package-rendered contract text — S704's escape hatch is not in
    # play (the ui.py slot rule).
    return Markup(render_mode_banner(banner))  # noqa: S704


@dataclass(frozen=True)
class ControlViews:
    """The composed control-region callables ``build_ui_router`` hands
    to the page handlers (fragment embed, mode computation, the session
    warning)."""

    render: Callable[[SessionRecord, dict[str, Any], list[dict[str, Any]]], str]
    bench_mode: Callable[[SessionRecord, str], str | None]
    session_warning: Callable[[SessionRecord], str | None]


def _esc(value: Any) -> str:
    return str(escape(value))


def _hidden(name: str, value: Any) -> str:
    return f'<input type="hidden" name="{name}" value="{_esc(value)}">'


def _number_field(
    name: str, input_id: str, *, label: str, value: Any, minimum: int, maximum: int
) -> str:
    """The host duration picker (a service form, not the §E.1 staging
    numeric-input — that pattern's required "staged" help text belongs
    to G3b's staging panel, so a plain labelled number field composes
    here)."""
    return (
        '<div class="bw-field">'
        f'<label for="{input_id}">{_esc(label)}</label>'
        # hx-preserve (FOLD-8): the section-level poll swap replaces the
        # forms wholesale; the attribute keeps a live, half-typed input
        # across the swap (htmx matches preserved elements by id). The
        # server-rendered value/min/max still refresh in the new content
        # for a FRESH element; a preserved one keeps the operator's
        # in-progress text — the server-side bounds re-judge every POST.
        f'<input id="{input_id}" name="{name}" type="number" hx-preserve '
        f'value="{_esc(value)}" min="{minimum}" max="{maximum}">'
        "</div>"
    )


def _submit(label: str, *, variant: str = "primary") -> str:
    """The host's form-submit button: the §E.1 button contract's
    attribute set (``bw-button``, ``data-variant``, ``aria-busy``) with
    ``type=submit`` — the package partial pins ``type=button`` (its own
    non-form uses), so the host composes the form shape."""
    return (
        '<button type="submit" class="bw-button"'
        f' data-variant="{variant}" aria-busy="false">{_esc(label)}</button>'
    )


def _disabled_control(label: str) -> str:
    """A mutating control in the observe-session shape: disabled with
    the §C.2 ``no-authority`` reason and its visible label."""
    return (
        '<button type="button" class="bw-button" data-variant="primary"'
        ' aria-busy="false" disabled'
        ' data-bw-disabled-reason="no-authority">'
        f"{_esc(label)}</button>"
        + render_disabled_label(
            DisabledLabelData(
                reason="no-authority", label="No lease or policy authority"
            )
        )
    )


def _bounded_control(label: str, note: str) -> str:
    """GW-95's disabled shape: the control disabled with the session
    expiry stated and the clearing action beside it (its own rule, not a
    §C.2 key)."""
    return (
        '<button type="button" class="bw-button" data-variant="primary"'
        ' aria-busy="false" disabled data-bw-session-bound="true">'
        f"{_esc(label)}</button>"
        f'<p class="bw-field__note" data-bw-session-bound-note>{_esc(note)}</p>'
    )


def _lease_facts_row(state: str, facts: str) -> str:
    return (
        f'<dl class="bw-kv" data-bw-lease-facts data-bw-lease-state="{state}">'
        f"{facts}</dl>"
    )


def _render_fragment(
    *,
    record: SessionRecord,
    bench: dict[str, Any],
    held: HeldLease | None,
    now_epoch: Callable[[], int],
    max_lease_ms: int,
    poll_base_ms: int,
    staging_html: str = "",
) -> str:
    """The control region's fragment: lease facts, GW-44 warning, and
    the take/renew/release controls — every byte derived at the current
    injected clock. All interpolations are escaped (the CSRF token too);
    package-rendered partials enter as pre-rendered trusted strings."""
    raw_id = bench.get("bench_id")
    # FOLD-4: the projection may be unreadable (a failed refetch after a
    # successful mutation) — no unconditional indexing. Without a bench
    # identity the two surfaces that address the bench by id (the take
    # control and the poll) cannot render; facts, the warning, and the
    # lease_id-addressed renew/release controls compose from the view.
    bench_id = str(raw_id) if raw_id is not None else ""
    busy = bool(bench.get("busy")) if bench_id else False
    has_control_scope = bool(record.scopes & TIER_SATISFIES[_CONTROL_TIER])

    expiry_s = _parse_iso_to_epoch(held.expires_at) if held is not None else None
    view_live = held is not None and expiry_s is not None and now_epoch() < expiry_s
    if view_live:
        lease_state = "held"
    elif held is not None:
        lease_state = "expired"
    elif busy:
        lease_state = "other"
    else:
        lease_state = "none"

    session_remaining_ms = max(record.expires_at - now_epoch(), 0) * 1000
    remaining_ms = max(expiry_s - now_epoch(), 0) * 1000 if expiry_s is not None else None

    level: str | None = None
    if view_live and held is not None and remaining_ms is not None:
        level = expiry_warning(remaining_ms, held.requested_duration_ms)
    if level == "critical":
        poll_ms = poll_base_ms // 30
    elif level == "warning":
        poll_ms = poll_base_ms // 6
    else:
        poll_ms = poll_base_ms

    warning_html = ""
    if level is not None:
        expires_display = _format_epoch(expiry_s) if expiry_s is not None else "unknown"
        message = (
            "Manual work on this bench will be ended by the safe transition when the"
            f" lease expires at {expires_display}. Renew the lease to extend the"
            " window."
        )
        bubble = AlertBubbleData(
            severity="critical",
            title="Lease ending",
            message=message,
            live_region="alert",
            dismissible=False,
        )
        if level == "warning":
            bubble = AlertBubbleData(
                severity="warning",
                title="Lease ending soon",
                message=message,
                live_region="status",
                dismissible=True,
            )
        warning_html = render_alert_bubble(bubble)

    if not has_control_scope:
        take_html = (
            f'<div class="bw-control" data-bw-lease-take>'
            f"{_disabled_control('Take lease')}</div>"
        )
        renew_html = (
            f'<div class="bw-control" data-bw-lease-renew>'
            f"{_disabled_control('Renew')}</div>"
        )
        release_html = (
            f'<div class="bw-control" data-bw-lease-release>'
            f"{_disabled_control('Release')}</div>"
        )
    else:
        gw95_note = (
            "This session ends at"
            f" {_format_epoch(record.expires_at)}; run benchweave ui-login for a"
            " longer session."
        )
        if session_remaining_ms < FORM_MIN_DURATION_MS:
            take_html = (
                f'<div class="bw-control" data-bw-lease-take>'
                f"{_bounded_control('Take lease', gw95_note)}</div>"
            )
        else:
            maximum = min(max_lease_ms, session_remaining_ms)
            if not bench_id:
                # FOLD-4: the bench identity is unavailable (a failed
                # refetch), so the take control — which addresses the
                # bench by id — cannot render; the view's facts and the
                # lease_id-addressed controls still do.
                take_html = ""
            else:
                generation = int(bench.get("generation", 0))
                take_html = (
                    '<form class="bw-control" data-bw-lease-take'
                    f' hx-post="/ui/benches/{_esc(bench_id)}/leases"'
                    ' hx-target="closest section" hx-swap="outerHTML">'
                    + _hidden("expected_generation", generation)
                    + _number_field(
                        "duration_ms",
                        f"bw-lease-duration-{_esc(bench_id)}",
                        label="Duration (ms)",
                        value=maximum,
                        minimum=FORM_MIN_DURATION_MS,
                        maximum=maximum,
                    )
                    + _submit("Take lease")
                    + "</form>"
                )
        if held is None or lease_state != "held":
            renew_html = ""
            release_html = ""  # absence is the no-lease shape (G3a)
        elif session_remaining_ms < FORM_MIN_DURATION_MS:
            renew_html = (
                f'<div class="bw-control" data-bw-lease-renew>'
                f"{_bounded_control('Renew', gw95_note)}</div>"
            )
            release_html = (
                '<form class="bw-control" data-bw-lease-release'
                f' hx-post="/ui/leases/{_esc(held.lease_id)}/release"'
                ' hx-target="closest section" hx-swap="outerHTML">'
                + _submit("Release", variant="secondary")
                + "</form>"
            )
        else:
            maximum = min(max_lease_ms, session_remaining_ms)
            renew_html = (
                '<form class="bw-control" data-bw-lease-renew'
                f' hx-post="/ui/leases/{_esc(held.lease_id)}/renewals"'
                ' hx-target="closest section" hx-swap="outerHTML">'
                + _hidden("sequence", held.sequence)
                + _number_field(
                    "duration_ms",
                    f"bw-lease-renew-duration-{_esc(bench_id)}",
                    label="Renew for (ms)",
                    value=max(held.requested_duration_ms, FORM_MIN_DURATION_MS),
                    minimum=FORM_MIN_DURATION_MS,
                    maximum=maximum,
                )
                + _submit("Renew")
                + "</form>"
            )
            release_html = (
                '<form class="bw-control" data-bw-lease-release'
                f' hx-post="/ui/leases/{_esc(held.lease_id)}/release"'
                ' hx-target="closest section" hx-swap="outerHTML">'
                + _submit("Release", variant="secondary")
                + "</form>"
            )

    if lease_state == "held":
        # view_live holds here, so the view and its remaining figure are
        # present — the local names restate the invariant for the type
        # checker, never a runtime assert.
        held_live = held
        remaining_live = remaining_ms
        if held_live is None or remaining_live is None:
            return ""
        facts = (
            f'<div><dt>Holder</dt><dd data-bw-lease-holder="{_esc(record.principal)}">'
            f"{_esc(record.principal)}</dd></div>"
            f'<div><dt>Expires</dt><dd data-bw-lease-expires-at="{_esc(held_live.expires_at)}">'
            f"{_esc(held_live.expires_at)}</dd></div>"
            f'<div><dt>Remaining</dt><dd data-bw-lease-remaining-ms="{remaining_live}">'
            f"{max(remaining_live // 1000, 0)} s</dd></div>"
        )
    elif lease_state == "expired":
        facts = (
            '<div><dt>Lease</dt><dd data-bw-lease-expired>expired</dd></div>'
        )
    elif lease_state == "other":
        facts = (
            '<div><dt>Lease</dt><dd data-bw-lease-other>held by another caller</dd></div>'
        )
    else:
        facts = '<div><dt>Lease</dt><dd data-bw-lease-none>none</dd></div>'

    bench_attr = f' data-bw-bench="{_esc(bench_id)}"' if bench_id else ""
    poll_ms_attr = f' data-bw-panel-poll-ms="{poll_ms}"' if bench_id else ""
    poll_attrs = (
        f' hx-get="/ui/benches/{_esc(bench_id)}/controls"'
        f' hx-trigger="every {poll_ms}ms" hx-swap="outerHTML"'
        if bench_id
        else ""
    )
    return (
        f'<section class="bw-panel bw-controls" data-bw-controls'
        f'{bench_attr} aria-label="Bench control"'
        f'{poll_ms_attr}'
        f"{poll_attrs}>"
        f"{warning_html}"
        f"{_lease_facts_row(lease_state, facts)}"
        "<div class=\"bw-controls__actions\">"
        f"{take_html}{renew_html}{release_html}"
        "</div>"
        # G3b: the staging panel rides INSIDE the fragment section —
        # one swap target, one poll cadence, both panels.
        f"{staging_html}"
        "</section>"
    )


def register_control_routes(
    router: APIRouter,
    *,
    operations: Operations,
    sessions: SessionStore,
    limits: Mapping[str, int],
    now_epoch: Callable[[], int],
    resolve_session: Callable[[Request], SessionRecord | None],
    session_identity: Callable[[SessionRecord], Identity],
    failure_page: Callable[[OperationFailure, Request], HTMLResponse],
    unauthenticated_page: Callable[[Request], HTMLResponse],
    render: Callable[..., str],
) -> ControlViews:
    """Register the G3a control routes on the UI router (before its
    catch-all) and return the composed views the page handlers use.

    Same closures as the read pages: one session resolution, one
    failure translation, one unauthenticated shape."""
    max_lease_ms = int(limits.get("max_lease_ms", 21600000))  # #307's published default
    poll_base_ms = int(limits.get("ui_panel_poll_ms", DEFAULT_PANEL_POLL_MS))

    def _authed(request: Request) -> tuple[SessionRecord, Identity] | None:
        record = resolve_session(request)
        if record is None:
            return None
        return record, session_identity(record)

    def _gw95_failure(record: SessionRecord, duration_ms: int) -> OperationFailure:
        """GW-95's pre-send refusal body: the bound, the session expiry
        (wall time) and the clearing action."""
        remaining_ms = max(record.expires_at - now_epoch(), 0) * 1000
        return OperationFailure(
            failure(
                "policy_denied",
                f"the requested {duration_ms} ms lease would outlive this session"
                f" ({remaining_ms} ms remaining; session expires"
                f" {_format_epoch(record.expires_at)}). Run benchweave ui-login for a"
                " longer session.",
            )
        )

    def _form_int(form: dict[str, Any], name: str) -> int:
        raw = form.get(name)
        if not isinstance(raw, str):
            raise OperationFailure(
                failure("invalid_request", f"{name} is required")
            )
        try:
            return int(raw)
        except ValueError:
            raise OperationFailure(
                failure("invalid_request", f"{name} must be an integer")
            ) from None

    def _first_events_page(identity: Identity, bench_id: str) -> list[dict[str, Any]]:
        """The selector's candidate refs read: the bench's first events
        page. A refusal composes no refs (the digest field still works)
        — never a failed render over presentation data."""
        try:
            return list(
                operations.events_get(
                    identity, bench_id, after=None, limit=_CONTROLS_EVENTS_PAGE
                )["events"]
            )
        except OperationFailure:
            return []

    def _fragment_response(
        record: SessionRecord,
        bench: dict[str, Any],
        bench_id: str | None = None,
        identity: Identity | None = None,
        page_events: list[dict[str, Any]] | None = None,
        started: tuple[str, bool] | None = None,
    ) -> HTMLResponse:
        resolved = (
            bench_id if bench_id is not None else str(bench.get("bench_id", ""))
        )
        staging_html = ""
        if staging is not None and identity is not None and resolved:
            rows = (
                page_events
                if page_events is not None
                else _first_events_page(identity, resolved)
            )
            staging_html = staging.panel_html(
                record, identity, bench, resolved, rows, started
            )
        return HTMLResponse(
            _render_fragment(
                record=record,
                bench=bench,
                held=sessions.held_lease(record.session_id, resolved),
                now_epoch=now_epoch,
                max_lease_ms=max_lease_ms,
                poll_base_ms=poll_base_ms,
                staging_html=staging_html,
            )
        )

    @router.get("/benches/{bench_id}/controls", include_in_schema=False)
    async def controls_fragment(bench_id: str, request: Request) -> Response:
        authed = _authed(request)
        if authed is None:
            return unauthenticated_page(request)
        record, identity = authed
        try:
            bench = operations.bench_get(identity, bench_id)
        except OperationFailure as fail:
            return failure_page(fail, request)
        return _fragment_response(record, bench, identity=identity)

    def _mint_request_id() -> str:
        return "ui-" + uuid.uuid4().hex[:12]

    @router.post("/benches/{bench_id}/leases", include_in_schema=False)
    async def take_lease(bench_id: str, request: Request) -> Response:
        """Take a lease (GW-40): ``lease_create`` on the session's
        identity; the GW-95 bound refuses pre-send; success re-renders
        the control region from the recorded view."""
        authed = _authed(request)
        if authed is None:
            return unauthenticated_page(request)
        record, identity = authed
        form = dict(await request.form())
        try:
            duration_ms = _form_int(form, "duration_ms")
            expected_generation = _form_int(form, "expected_generation")
        except OperationFailure as fail:
            return failure_page(fail, request)
        if now_epoch() * 1000 + duration_ms > record.expires_at * 1000:
            return failure_page(_gw95_failure(record, duration_ms), request)
        if duration_ms > max_lease_ms:
            # FOLD-6: mirror the form's own bound on the wire path. UI-side
            # presentation enforcement — the seam stays the authority (the
            # seam-side envelope is the deferred G3-D6 gap), so a non-UI
            # client is judged at the seam exactly as before.
            return failure_page(
                OperationFailure(
                    failure(
                        "policy_denied",
                        f"the requested {duration_ms} ms exceeds this gateway's"
                        f" published maximum lease of {max_lease_ms} ms",
                    )
                ),
                request,
            )
        try:
            lease = operations.lease_create(
                identity,
                bench_id,
                _mint_request_id(),
                expected_generation,
                duration_ms,
            )
        except OperationFailure as fail:
            return failure_page(fail, request)
        sessions.record_held_lease(
            record.session_id,
            HeldLease(
                lease_id=str(lease["lease_id"]),
                bench_id=str(lease["bench_id"]),
                sequence=int(lease["sequence"]),
                expires_at=str(lease["expires_at"]),
                state=str(lease["state"]),
                requested_duration_ms=duration_ms,
            ),
        )
        try:
            bench = operations.bench_get(identity, bench_id)
        except OperationFailure:
            bench = {}  # the fragment tolerates a failed refetch (facts from the view)
        return _fragment_response(record, bench, bench_id=bench_id, identity=identity)

    @router.post("/leases/{lease_id}/renewals", include_in_schema=False)
    async def renew_lease(lease_id: str, request: Request) -> Response:
        """Renew (GW-41/57): ``lease_renew`` with the HELD VIEW's current
        sequence — never a client-supplied one. Same GW-95 bound; a
        not_found/forbidden refusal clears the phantom view (R2's
        mitigation, scoped by kind); a CONFLICT keeps the view — the
        sequence moved elsewhere (a REST-class renewal), the lease may
        still be this session's, and release stays the recovery path
        (the seam's lease_release judges the bench's own stored
        sequence, never the view's — FOLD-3); success replaces the view
        with the successor."""
        authed = _authed(request)
        if authed is None:
            return unauthenticated_page(request)
        record, identity = authed
        form = dict(await request.form())
        try:
            duration_ms = _form_int(form, "duration_ms")
        except OperationFailure as fail:
            return failure_page(fail, request)
        # FOLD-4 (renew): the view resolves from the route's own lease id
        # (server truth) — the form's bench field never keys the view.
        held = sessions.held_lease_for_lease(record.session_id, lease_id)
        if held is None:
            return failure_page(
                OperationFailure(
                    failure(
                        "invalid_request",
                        "no held lease view for this lease in this session",
                    )
                ),
                request,
            )
        bench_id = held.bench_id
        if now_epoch() * 1000 + duration_ms > record.expires_at * 1000:
            return failure_page(_gw95_failure(record, duration_ms), request)
        if duration_ms > max_lease_ms:
            # FOLD-6, the renew path: same published-max mirror, same
            # disclosure (the seam stays the authority; G3-D6 unchanged).
            return failure_page(
                OperationFailure(
                    failure(
                        "policy_denied",
                        f"the requested {duration_ms} ms exceeds this gateway's"
                        f" published maximum lease of {max_lease_ms} ms",
                    )
                ),
                request,
            )
        try:
            successor = operations.lease_renew(
                identity,
                lease_id,
                _mint_request_id(),
                held.sequence,
                duration_ms,
            )
        except OperationFailure as fail:
            if fail.failure.code in ("not_found", "forbidden"):
                # The lease is gone or not this session's — the view is
                # phantom; clear it (R2's mitigation, scoped to these).
                sessions.clear_held_lease(record.session_id, bench_id)
            # A conflict — and every other refusal — keeps the view: the
            # sequence moved elsewhere, the lease may still be live and
            # THIS session's, and release (the seam judges its own stored
            # sequence) stays available (FOLD-3).
            return failure_page(fail, request)
        sessions.record_held_lease(
            record.session_id,
            HeldLease(
                lease_id=str(successor["lease_id"]),
                bench_id=str(successor["bench_id"]),
                sequence=int(successor["sequence"]),
                expires_at=str(successor["expires_at"]),
                state=str(successor["state"]),
                requested_duration_ms=duration_ms,
            ),
        )
        try:
            bench = operations.bench_get(identity, bench_id)
        except OperationFailure:
            bench = {}
        return _fragment_response(record, bench, bench_id=bench_id, identity=identity)

    @router.post("/leases/{lease_id}/release", include_in_schema=False)
    async def release_lease(lease_id: str, request: Request) -> Response:
        """Release (one click, GW-40): ``lease_release`` with the fixed
        reason; the seam re-validates holder-only authority (a forged
        release renders its own refusal); success clears the view."""
        authed = _authed(request)
        if authed is None:
            return unauthenticated_page(request)
        record, identity = authed
        # FOLD-4: the view key resolves from the route's own lease id
        # through the session's held views (server truth) — never a form
        # field; an absent/wrong bench_id used to skip the clear and 500
        # the render after the seam had already released.
        view = sessions.held_lease_for_lease(record.session_id, lease_id)
        bench_id = view.bench_id if view is not None else ""
        try:
            operations.lease_release(
                identity, lease_id, _mint_request_id(), _RELEASE_REASON
            )
        except OperationFailure as fail:
            if bench_id:
                sessions.clear_held_lease(record.session_id, bench_id)
            return failure_page(fail, request)
        if bench_id:
            sessions.clear_held_lease(record.session_id, bench_id)
        try:
            bench = operations.bench_get(identity, bench_id)
        except OperationFailure:
            bench = {}
        return _fragment_response(record, bench, bench_id=bench_id, identity=identity)

    # The G3b staging routes (issue #304, §2.4): the five handlers plus
    # the staging-panel composition, wired with this module's closures.
    # Deferred import — ui_staging reads this module's helpers, so a
    # top-level import would be circular.
    from benchweave.interfaces.ui_staging import StagingRoutes

    staging = StagingRoutes(
        operations=operations,
        sessions=sessions,
        now_epoch=now_epoch,
        page_size=int(limits.get("max_page_size", 1000)),
        resolve_session=resolve_session,
        session_identity=session_identity,
        failure_page=failure_page,
        unauthenticated_page=unauthenticated_page,
        render=render,
        fragment=lambda record, bench, bench_id, identity, started=None: _fragment_response(
            record, bench, bench_id=bench_id, identity=identity,
            started=started,
        ),
    )
    staging.register(router)

    def _cancel_region(
        run_id: str, terminal: bool, requested: bool, has_control: bool
    ) -> str:
        """The run page's cancel region as its own swap target (the
        POST re-renders exactly this block — GW-55's marker appears
        without a page reload and gives way to the run's own state)."""
        return render(
            "cancel-region.j2",
            run_id=run_id,
            run_terminal=terminal,
            cancel_requested=requested,
            has_control=has_control,
        )

    @router.post("/runs/{run_id}/cancellations", include_in_schema=False)
    async def cancel_run(run_id: str, request: Request) -> Response:
        """GW-53/55 (§2.4): one action, never confirmed, UNGATED by
        lease or trip (§6's owner-or-admin judgement is the seam's,
        which "does not require an unexpired controlling lease" — its
        own clause). run_cancel carries the form's reason; the
        pending-cancel marker then renders until run_get reports
        terminal."""
        authed = _authed(request)
        if authed is None:
            return unauthenticated_page(request)
        record, identity = authed
        form = dict(await request.form())
        reason = str(form.get("reason", ""))
        if not reason.strip():
            return failure_page(
                OperationFailure(
                    failure(
                        "invalid_request",
                        "a reason is required (one character minimum)",
                    )
                ),
                request,
            )
        try:
            operations.run_cancel(identity, run_id, _mint_request_id(), reason)
        except OperationFailure as fail:
            return failure_page(fail, request)
        sessions.record_cancel_request(record.session_id, run_id)
        try:
            run = operations.run_get(identity, run_id)
        except OperationFailure:
            run = {}
        return HTMLResponse(
            _cancel_region(
                run_id,
                str(run.get("state", "")) == "terminal",
                sessions.cancel_requested(record.session_id, run_id),
                bool(record.scopes & TIER_SATISFIES[_CONTROL_TIER]),
            )
        )

    return ControlViews(
        render=lambda record, bench, events: _render_fragment(
            record=record,
            bench=bench,
            held=sessions.held_lease(
                record.session_id, str(bench.get("bench_id", ""))
            ),
            now_epoch=now_epoch,
            max_lease_ms=max_lease_ms,
            poll_base_ms=poll_base_ms,
            staging_html=(
                staging.panel_html(
                    record,
                    session_identity(record),
                    bench,
                    str(bench.get("bench_id", "")),
                    events,
                )
                if str(bench.get("bench_id", ""))
                else ""
            ),
        ),
        bench_mode=lambda record, bench_id: bench_mode(
            sessions.held_lease(record.session_id, bench_id), now_epoch=now_epoch
        ),
        session_warning=lambda record: session_warning_bubble(
            record, now_epoch=now_epoch
        ),
    )


# --- G3b: runs, staging, energy confirmation (issue #304, design §2.4/§2.5) --------


_HEX64 = set("0123456789abcdef")


def _is_digest(candidate: str) -> bool:
    return len(candidate) == 64 and set(candidate) <= _HEX64


def _binding_chain(
    operations: Operations, identity: Identity, binding_ref: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The DEP7 chain over the seam (never the store): the staged
    binding by digest, then its pinned procedure — the same
    digest-addressed resolution ``run_check`` performs.

    FOLD-1: a STORED document lacking the binding shape (no procedure
    pin — the stage handler tolerates every stored document) is the
    unreadable-chain class, never a raw KeyError: it refuses
    ``not_found`` ("no binding document exists at this digest"), the
    same seam answer an unstored digest gets, so every caller composes
    its own honest shape (the panel's disabled branch, the arm's §C.3
    row). What it does NOT catch: a stored binding whose PINNED
    procedure digest is shapeless — the second ``document_get`` returns
    whatever the store holds and downstream readers (``armed_composition``)
    treat missing keys honestly (FOLD-5)."""
    binding_sha = str(binding_ref.get("sha256", ""))
    binding_doc = operations.document_get(identity, binding_sha)["content"]
    procedure_pin = (
        binding_doc.get("procedure") if isinstance(binding_doc, dict) else None
    )
    procedure_sha = (
        str(procedure_pin.get("sha256", ""))
        if isinstance(procedure_pin, dict)
        else ""
    )
    if not procedure_sha:
        raise OperationFailure(
            failure(
                "not_found",
                "the stored document does not name a pinned procedure —"
                " no binding document exists at this digest",
            )
        )
    procedure_doc = operations.document_get(identity, procedure_sha)["content"]
    return binding_doc, procedure_doc


def _attention_bound_ms(procedure: dict[str, Any]) -> int | None:
    """GW-56's attention bound (DEP7, the #306-verified chain): the
    procedure document's ``max_body_ms + max_protection_ms``. Both are
    required by the procedure schema for every admitted manual
    document; absent (a non-schema shape) composes no refusal — never a
    fabricated zero."""
    body = procedure.get("max_body_ms")
    protection = procedure.get("max_protection_ms")
    if (
        isinstance(body, int)
        and not isinstance(body, bool)
        and isinstance(protection, int)
        and not isinstance(protection, bool)
    ):
        return int(body) + int(protection)
    return None


def _format_number(value: Any) -> str:
    """Exact values, not floats: 5.0 renders ``5`` and 0.5 renders
    ``0.5`` (the confirm's non-optional exact value+unit)."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


_UNIT_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("_ms", "ms"),
    ("_a", "A"),
    ("_v", "V"),
)


def _unit_for(field: str, sample_units: dict[str, str]) -> str:
    """Unit derivation precedence (the record §2.4): (1) a same-named
    ``sample`` step's declared unit; (2) the field-name SI suffix
    (``_v``/``_a``/``_ms``) as the documented last resort."""
    if field in sample_units:
        return sample_units[field]
    for suffix, unit in _UNIT_SUFFIXES:
        if field.endswith(suffix):
            return unit
    return ""


_EFFECT = "the output will be energised"


def armed_composition(
    binding_doc: dict[str, Any], procedure_doc: dict[str, Any]
) -> tuple[bool, bool, str | None]:
    """(energy, manual, armed_text) from the document chain (GW-52,
    §E.1): energy-sourcing iff ``energy_sourcing(procedure)``; the armed
    text states the effect, the exact values with units (the enable
    step's sibling configure inputs), and the target (the enable step's
    role mapped through the binding's ``bindings[]``) — joined per the
    contract's shape. ``None`` text when the class is de-energising."""
    energy = energy_sourcing(procedure_doc)
    manual = str(procedure_doc.get("mode", "")) == "manual"
    if not energy:
        return energy, manual, None
    sample_units = {
        str(step.get("variable_id", "")): str(step.get("unit", ""))
        for step in _iter_steps(procedure_doc.get("steps", []))
        if isinstance(step, dict) and step.get("kind") == "sample"
    }
    enable = next(
        (
            step
            for step in _iter_steps(procedure_doc.get("steps", []))
            if step.get("kind") == "invoke"
            and isinstance(step.get("input"), dict)
            and step["input"].get("enabled") is True
            and step.get("role")
        ),
        None,
    )
    values: list[str] = []
    if enable is not None:
        for step in _iter_steps(procedure_doc.get("steps", [])):
            if step.get("kind") != "invoke" or not isinstance(step.get("input"), dict):
                continue
            if step is enable:
                break
            action_input = step["input"]
            for field, value in action_input.items():
                if field.startswith("$stg_"):
                    continue
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                unit = _unit_for(str(field), sample_units)
                values.append(f"{_format_number(value)} {unit}".rstrip())
            break  # the configure inputs are the enable step's nearest preceding sibling
    target = ""
    if enable is not None:
        role = str(enable.get("role", ""))
        for entry in binding_doc.get("bindings", []):
            if str(entry.get("role", "")) == role:
                device_id = str(entry.get("device_id", ""))
                channels = entry.get("channels", {}) or {}
                channel = next(iter(channels.values()), "") if isinstance(channels, dict) else ""
                target = f"{device_id} {channel}".strip()
                break
    text = f"{_EFFECT}: {', '.join(values)} to {target}. Confirm to proceed."
    return energy, manual, text


