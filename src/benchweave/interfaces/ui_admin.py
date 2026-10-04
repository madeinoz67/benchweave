"""The G4 administration routes (issue #305, design record §2): change
submit, the review page, the approval workspace, and the failed/unknown
inhibited state — GW-10's last two mutating rows mounted.

Every handler is the G2/G3 translation shape: session resolution, the
seam call, the honest render. The seam is the authority; the session's
change index (design §2.1) is presentation of this session's own seam
answers — never a state cache, never authority. The bench page's
administration region is server-rendered at page render (never inside
the polled controls fragment: change state is not live data and does
not deserve the poll budget); the region and the workspace re-render as
the response of their own POSTs, htmx-swapped into place — the
responseHandling override already covers the fragment-vs-page refusal
shapes.

Ruled-deviation note (the commit message carries it): the region's
proposed-change rows render their disabled apply affordance ONLY under
inhibition (the G3a absence-is-the-no-lease shape); §2.4's "the
region's apply controls render disabled" reads true for the inhibited
render, and a healthy render composes no apply control — the workspace
(the change page) is the apply surface when the bench is healthy.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from benchweave_ui_html.data import AlertBubbleData, DisabledLabelData
from benchweave_ui_html.partials import render_alert_bubble, render_disabled_label
from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse
from markupsafe import Markup, escape

from benchweave.interfaces.errors import OperationFailure, failure
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.operations import TIER_SATISFIES, Operations
from benchweave.interfaces.sessions import (
    ApprovalView,
    ChangeView,
    SessionRecord,
    SessionStore,
)
from benchweave.interfaces.ui_control import _esc
from benchweave.interfaces.ui_refusals import (
    render_no_response_change_apply,
    render_no_response_change_submit,
)

_LOG = logging.getLogger(__name__)

#: The submit form's display order over the seam's ``CHANGE_KINDS``: the
#: trip reset first (its target prefills from the bench's own
#: configuration ref — the R5 convention), the registry kinds after.
#: Guarded against the seam's set at import (a construction bug, not a
#: runtime refusal) — a kind the seam does not know must never render.
_CHANGE_KIND_ORDER: tuple[str, ...] = (
    "trip_reset",
    "configuration_activation",
    "package_admission",
)
if set(_CHANGE_KIND_ORDER) != set(Operations.CHANGE_KINDS):
    raise RuntimeError(
        f"the submit form's kinds must be exactly the seam's CHANGE_KINDS;"
        f" the form orders {sorted(_CHANGE_KIND_ORDER)}, the seam defines"
        f" {sorted(Operations.CHANGE_KINDS)}"
    )

#: The workspace's two-phase statement (US8): who can approve.
_TWO_PHASE_NOTE = (
    "Needs independent approval: a principal other than any applier must"
    " authenticate the approval before this change can be applied."
)

#: §2.4's reconciliation route, in the contract's own terms.
_RECONCILIATION_NOTE = (
    "Read the record, then file a NEW change if warranted; never re-apply"
    " this one."
)


class AdminRoutes:
    """The five G4 routes plus the region/workspace compositions, wired
    by ``register_admin_routes`` with the shared closures."""

    def __init__(
        self,
        *,
        operations: Operations,
        sessions: SessionStore,
        resolve_session: Callable[[Request], SessionRecord | None],
        session_identity: Callable[[SessionRecord], Identity],
        failure_page: Callable[[OperationFailure, Request], HTMLResponse],
        unauthenticated_page: Callable[[Request], HTMLResponse],
        page: Callable[..., HTMLResponse],
        render: Callable[..., str],
        session_warning: Callable[[SessionRecord], str | None],
    ) -> None:
        self._operations = operations
        self._sessions = sessions
        self._resolve_session = resolve_session
        self._session_identity = session_identity
        self._failure_page = failure_page
        self._unauthenticated_page = unauthenticated_page
        self._page = page
        self._render = render
        self._session_warning = session_warning

    # --- shared shapes ------------------------------------------------------

    def _authed(self, request: Request) -> tuple[SessionRecord, Identity] | None:
        record = self._resolve_session(request)
        if record is None:
            return None
        return record, self._session_identity(record)

    def _has_admin(self, record: SessionRecord) -> bool:
        return bool(record.scopes & TIER_SATISFIES["admin"])

    def _mint_request_id(self) -> str:
        return "ui-" + uuid.uuid4().hex[:12]

    def _derive_approval(
        self,
        *,
        ref_id: str,
        ref_version: str,
        sha256: str,
        body: dict[str, Any],
        change: dict[str, Any],
    ) -> ApprovalView:
        """The view over what one stored approval document SAYS, read
        fresh through ``document_get`` and re-derived at every use (the
        offer-time load and the fire-time guard share this derivation):
        the approver the document names, its policy version, and whether
        it binds the change record being viewed (its ``change_id`` and
        ``expected_generation`` both match). Presentation of the
        document's own bytes — never authority: the seam re-verifies the
        pair at apply time."""
        bound_change = str(body.get("change_id", ""))
        try:
            bound_generation = int(body.get("expected_generation", -1))
        except (TypeError, ValueError):
            bound_generation = -1
        binds = (
            bound_change == str(change.get("change_id", ""))
            and bound_generation == int(change.get("expected_generation", -1))
        )
        return ApprovalView(
            sha256=sha256,
            ref_id=ref_id,
            ref_version=ref_version,
            approver_principal=str(body.get("approver_principal", "")),
            policy_version=str(body.get("policy_version", "")),
            binds=binds,
            bound_change_id=bound_change,
            bound_generation=bound_generation,
        )

    def _strip(self, record: SessionRecord) -> dict[str, Any]:
        """The base-template context (the read pages' shape): gateway
        identity, the session's principal/scopes, the shell warning, the
        CSRF token."""
        info = self._operations.gateway_info(self._session_identity(record))
        return {
            "gateway_id": str(info["gateway_id"]),
            "principal": record.principal,
            "scopes": sorted(record.scopes),
            "mode_banner": None,
            "session_warning": self._session_warning(record),
            "csrf_token": record.csrf_token,
        }

    def _blocked_changes(
        self, record: SessionRecord, identity: Identity, bench_id: str
    ) -> list[dict[str, str]]:
        """GW-72's predicate over THIS session's index, state freshly
        read: the unacknowledged failed/unknown indexed changes for the
        bench. The index carries no state — every verdict here is a
        fresh ``change_get`` (the C3 arm's seam). A change the session
        can no longer read is skipped and logged server-side (D4's
        posture: the free-form reason is the log's, never a rendered
        guess)."""
        views = self._sessions.change_views_for_bench(record.session_id, bench_id)
        blocked: list[dict[str, str]] = []
        for change_id in sorted(views):
            view = views[change_id]
            if view.acknowledged:
                continue
            try:
                change = self._operations.change_get(identity, change_id)
            except OperationFailure:
                _LOG.warning(
                    "change %s left this session's reach; skipped in the"
                    " administration render",
                    change_id,
                )
                continue
            state = str(change.get("state", ""))
            if state not in ("failed", "unknown"):
                continue
            reasons = list(change.get("reasons") or [])
            blocked.append(
                {
                    "change_id": change_id,
                    "state": state,
                    "reason": str(reasons[0]) if reasons else "",
                }
            )
        return blocked

    def _alert_markup(
        self, blocked: list[dict[str, str]], *, acknowledge: bool = False
    ) -> Markup | None:
        """The §B.1 critical persistent alert over the blocked changes
        (one bubble per change; each names its id, the state,
        ``reasons[0]`` verbatim, links the record and states the
        reconciliation route). The REGION render carries the acknowledge
        affordance under each bubble — the region is the
        acknowledgement surface (the ruled deviation: the change page's
        identical alert is informational only)."""
        if not blocked:
            return None
        parts: list[str] = []
        for entry in blocked:
            bubble = AlertBubbleData(
                severity="critical",
                title=f"Change {entry['change_id']} {entry['state']}",
                message=(
                    f"{entry['reason']} {_RECONCILIATION_NOTE}"
                    " Acknowledge from this region once read."
                ),
                live_region="alert",
                dismissible=False,
            )
            parts.append(render_alert_bubble(bubble))
            if acknowledge:
                parts.append(
                    '<form class="bw-control" data-bw-change-acknowledge'
                    ' hx-post="/ui/changes/'
                    f'{_esc(entry["change_id"])}/acknowledgements"'
                    ' hx-target="closest section" hx-swap="outerHTML">'
                    '<button type="submit" class="bw-button"'
                    ' data-variant="secondary" aria-busy="false">'
                    "Acknowledge change</button>"
                    "</form>"
                )
        # Trusted package-rendered HTML (the §E.1/§B.1 partial), not
        # request data — S704's escape hatch is not in play.
        return Markup("".join(parts))  # noqa: S704

    # --- the bench administration region (GW-70's submit half) --------------

    def region_html(
        self,
        record: SessionRecord,
        identity: Identity,
        bench: dict[str, Any],
        bench_id: str,
    ) -> str:
        """The region at the render clock: this session's indexed changes
        with state freshly read, the inhibited-state alert, the disabled
        apply affordances, and the submit form (or its disabled shape)."""
        has_admin = self._has_admin(record)
        views = self._sessions.change_views_for_bench(record.session_id, bench_id)
        blocked = (
            self._blocked_changes(record, identity, bench_id) if has_admin else []
        )
        rows: list[dict[str, Any]] = []
        for change_id in sorted(views):
            try:
                change = self._operations.change_get(identity, change_id)
            except OperationFailure:
                _LOG.warning(
                    "change %s left this session's reach; skipped in the region",
                    change_id,
                )
                continue
            state = str(change.get("state", ""))
            row: dict[str, Any] = {
                "change_id": change_id,
                "kind": str(change.get("kind", "")),
                "state": state,
                "proposed": state == "proposed",
                # The disabled apply affordance renders ONLY under
                # inhibition (the ruled deviation named in the module
                # docstring); absence is the healthy shape (G3a).
                "inhibited_html": None,
            }
            if state == "proposed" and blocked:
                blocking = blocked[0]["change_id"]
                # Trusted host-rendered markup (the module's own escaped
                # composition) wrapped in Markup so the template RENDERS
                # it — the raw str double-escaped into visible text
                # until the commit-5 suite caught it (no affordance on
                # the wire, only escaped glyphs).
                row["inhibited_html"] = Markup(  # noqa: S704
                    self._inhibited_apply_html(blocking)
                )
            rows.append(row)
        configuration = bench.get("configuration") or {}
        return self._render(
            "admin-region.j2",
            observe=not has_admin,
            bench_id=bench_id,
            generation=int(bench.get("generation", 0)),
            config_id=str(configuration.get("id", "")),
            config_version=str(configuration.get("version", "")),
            config_sha256=str(configuration.get("sha256", "")),
            request_id=self._mint_request_id(),
            kinds=list(_CHANGE_KIND_ORDER),
            rows=rows,
            two_phase_html=_TWO_PHASE_NOTE,
            # Trusted package-rendered HTML — S704 not in play. The region
            # is the acknowledgement surface: its alert carries the
            # acknowledge affordance (the ruled deviation — the change
            # page's identical alert is informational only).
            alert_html=self._alert_markup(blocked, acknowledge=True),
            no_authority_html=Markup(  # noqa: S704
                render_disabled_label(
                    DisabledLabelData(
                        reason="no-authority",
                        label="No lease or policy authority",
                    )
                )
            ),
        )

    def _inhibited_apply_html(self, blocking_change_id: str) -> str:
        """The disabled apply affordance for a proposed change while the
        bench is inhibited (§2.4): the control disabled with §C.2's
        ``no-authority`` beside a note naming the blocking change."""
        return (
            '<div class="bw-control" data-bw-change-inhibited>'
            '<button type="button" class="bw-button" data-variant="primary"'
            ' aria-busy="false" disabled'
            ' data-bw-disabled-reason="no-authority">Apply change</button>'
            f'<p class="bw-field__note" data-bw-inhibit-note>Apply is unavailable'
            f" while change {escape(blocking_change_id)} is unacknowledged."
            f" {_RECONCILIATION_NOTE}</p>"
            "</div>"
        )

    # --- the change page + the apply workspace (GW-70/71) --------------------

    def workspace_html(
        self,
        record: SessionRecord,
        identity: Identity,
        change: dict[str, Any],
        *,
        bench_generation: int | None = None,
    ) -> str:
        """The apply workspace as its own swap target (the region's own
        POSTs re-render it — the full page never swaps into itself)."""
        change_id = str(change.get("change_id", ""))
        state = str(change.get("state", ""))
        if not self._has_admin(record):
            return ""
        if state == "applied":
            increment = (
                f'Generation {escape(str(change.get("expected_generation", "")))}'
                f" → {escape(str(bench_generation))}"
                if bench_generation is not None
                else ""
            )
            return (
                '<section class="bw-panel bw-admin-workspace"'
                ' data-bw-change-workspace aria-label="Apply workspace">'
                f'<p data-bw-change-applied="true">Change applied.'
                f" {increment}</p>"
                "</section>"
            )
        if state in ("failed", "unknown"):
            return (
                '<section class="bw-panel bw-admin-workspace"'
                ' data-bw-change-workspace aria-label="Apply workspace">'
                f'<p class="bw-field__note" data-bw-change-outcome-note>'
                f"This change is {escape(state)} and terminal."
                f" {_RECONCILIATION_NOTE}</p>"
                "</section>"
            )
        # state == proposed and an admin session: the three-step flow.
        view = self._sessions.change_view(record.session_id, change_id)
        approval = view.approval if view is not None else None
        bench_id = str(change.get("bench_id", ""))
        blocked = self._blocked_changes(record, identity, bench_id)
        inhibiting = blocked[0]["change_id"] if blocked else None
        parts: list[str] = [
            '<section class="bw-panel bw-admin-workspace"'
            ' data-bw-change-workspace aria-label="Apply workspace">'
        ]
        if inhibiting is not None:
            parts.append(self._inhibited_apply_html(inhibiting))
        if approval is None:
            parts.append(
                '<form class="bw-control" data-bw-approval-load'
                f' hx-post="/ui/changes/{_esc(change_id)}/approval"'
                ' hx-target="closest section" hx-swap="outerHTML">'
                '<label for="bw-approval-sha">Approval digest (sha256)</label>'
                '<input id="bw-approval-sha" name="approval_sha256" type="text"'
                ' required minlength="64" maxlength="64"'
                ' pattern="[0-9a-f]{64}">'
                '<label for="bw-approval-id">Approval id</label>'
                '<input id="bw-approval-id" name="approval_id" type="text" required>'
                '<label for="bw-approval-version">Approval version</label>'
                '<input id="bw-approval-version" name="approval_version"'
                ' type="text" required>'
                '<p class="bw-field__note" data-bw-approval-note>The approval is'
                " two things: a stored document (pasted by digest) and the"
                " approver's detached token (pasted at the apply step). Both"
                " come from the approver, out of band.</p>"
                '<button type="submit" class="bw-button" data-variant="primary"'
                ' aria-busy="false">Load approval</button>'
                "</form>"
            )
        else:
            parts.append(self._approval_facts_html(change_id, approval))
            parts.append(
                self._apply_control_html(
                    record, identity, change_id, approval, inhibiting
                )
            )
        parts.append("</section>")
        return "".join(parts)

    def _approval_facts_html(self, change_id: str, approval: ApprovalView) -> str:
        """What the loaded approval actually says (§2.3 step 1): bound
        change, generation, approver principal, policy version — with the
        document page link for the full view."""
        binds_text = "binds this change" if approval.binds else "does not bind this change"
        return (
            '<dl class="bw-kv" data-bw-approval-facts'
            f' data-bw-approval-binds="{"true" if approval.binds else "false"}">'
            f"<div><dt>Approver</dt><dd"
            f' data-bw-approval-approver="{_esc(approval.approver_principal)}">'
            f"{_esc(approval.approver_principal)}</dd></div>"
            f"<div><dt>Bound change</dt><dd"
            f' data-bw-approval-change="{_esc(approval.bound_change_id)}">'
            f"{_esc(approval.bound_change_id)} @ generation"
            f" {_esc(approval.bound_generation)}</dd></div>"
            f"<div><dt>Policy</dt><dd data-bw-approval-policy>"
            f"{_esc(approval.policy_version)}</dd></div>"
            f'<div><dt>Document</dt><dd><a class="bw-link"'
            f' href="/ui/documents/{_esc(approval.sha256)}">the stored'
            " document</a></dd></div>"
            f'<p class="bw-field__note" data-bw-approval-binds-note>The approval'
            f" {binds_text}.</p>"
            "</dl>"
        )

    def _apply_control_html(
        self,
        record: SessionRecord,
        identity: Identity,
        change_id: str,
        approval: ApprovalView,
        inhibiting: str | None,
    ) -> str:
        """GW-71's offer-time machine + GW-72's disable: the apply control
        offered ONLY to a binding approval naming a different principal on
        an uninhibited bench; every other state renders its disabled
        shape with the honest reason."""
        if inhibiting is not None:
            return self._inhibited_apply_html(inhibiting)
        if not approval.binds:
            return (
                '<div class="bw-control" data-bw-apply-control>'
                '<button type="button" class="bw-button" data-variant="primary"'
                ' aria-busy="false" disabled'
                ' data-bw-disabled-reason="invalid-staged-input">Apply change</button>'
                '<p class="bw-field__note" data-bw-apply-note>The loaded approval'
                " does not bind this change (its change id or expected"
                " generation differs) — load the approval written for this"
                " change.</p></div>"
            )
        if approval.approver_principal == record.principal:
            return (
                '<div class="bw-control" data-bw-apply-control>'
                '<button type="button" class="bw-button" data-variant="primary"'
                ' aria-busy="false" disabled'
                ' data-bw-disabled-reason="no-authority">Apply change</button>'
                '<p class="bw-field__note" data-bw-apply-note>Independent'
                " approval: a principal other than the applier must have"
                " authenticated the approval. The gateway refuses"
                " self-approval, and the UI does not offer what the gateway"
                " would refuse.</p></div>"
            )
        return (
            '<form class="bw-control" data-bw-apply-control'
            f' hx-post="/ui/changes/{_esc(change_id)}/apply"'
            ' hx-target="closest section" hx-swap="outerHTML">'
            '<input type="hidden" name="request_id"'
            f' value="{_esc(self._mint_request_id())}">'
            '<label for="bw-approver-token">Approver token (detached)</label>'
            '<input id="bw-approver-token" name="approver_token" type="password"'
            ' autocomplete="off" required>'
            '<p class="bw-field__note" data-bw-token-note>The approver token is'
            " never rendered back: no response byte carries it.</p>"
            '<button type="submit" class="bw-button" data-variant="primary"'
            ' aria-busy="false">Apply change</button>'
            "</form>"
        )

    # --- the routes -----------------------------------------------------------

    def register(self, router: APIRouter) -> None:
        """The declared G4 rows (ui_routes.py's table is the authority;
        registration order is irrelevant — exact paths, before the
        catch-all)."""
        router.add_api_route(
            "/benches/{bench_id}/changes",
            self.submit_change,
            methods=["POST"],
            include_in_schema=False,
        )
        router.add_api_route(
            "/changes/{change_id}",
            self.change_page,
            methods=["GET"],
            include_in_schema=False,
        )
        router.add_api_route(
            "/changes/{change_id}/approval",
            self.load_approval,
            methods=["POST"],
            include_in_schema=False,
        )
        router.add_api_route(
            "/changes/{change_id}/apply",
            self.apply_change,
            methods=["POST"],
            include_in_schema=False,
        )
        router.add_api_route(
            "/changes/{change_id}/acknowledgements",
            self.acknowledge_change,
            methods=["POST"],
            include_in_schema=False,
        )

    async def submit_change(self, bench_id: str, request: Request) -> Response:
        """GW-70's submit half: ``change_submit`` with the FORM's §9 id —
        never one minted per POST (the design's RED control: a per-POST
        mint turns the double-click replay into two rows). The §9 key is
        scoped to the session's principal, so a replay of the identical
        form returns the original change; a different candidate on the
        same id is the seam's ``conflict``. Success re-renders the region
        with the new change's row (fresh state, review link, the
        two-phase statement); the change indexes into the session's
        change view — a §9 replay PRESERVES the existing view's
        acknowledgement and loaded approval, re-indexing only what is
        new. A non-``OperationFailure`` composes the §C.3
        no-response row with the resubmit reconcile (§2.5)."""
        authed = self._authed(request)
        if authed is None:
            return self._unauthenticated_page(request)
        record, identity = authed
        form = dict(await request.form())
        request_id = str(form.get("request_id", ""))
        if not request_id:
            return self._failure_page(
                OperationFailure(
                    failure("invalid_request", "the submit form carries no request id")
                ),
                request,
            )
        target_ref = {
            "id": str(form.get("target_id", "")),
            "version": str(form.get("target_version", "")),
            "sha256": str(form.get("target_sha256", "")),
        }
        try:
            expected_generation = int(str(form.get("expected_generation", "")))
        except ValueError:
            return self._failure_page(
                OperationFailure(
                    failure(
                        "invalid_request", "expected_generation must be an integer"
                    )
                ),
                request,
            )
        try:
            change = self._operations.change_submit(
                identity,
                request_id,
                bench_id,
                str(form.get("kind", "")),
                target_ref,
                expected_generation,
                str(form.get("reason", "")),
            )
        except OperationFailure as fail:
            return self._failure_page(fail, request)
        except Exception:
            # Transport-shaped (no interface answer): §C.3's no-response
            # row with the change-honest reconcile. An in-process adapter
            # cannot honestly produce this; the suite induces it (the G2
            # §7-F posture).
            return HTMLResponse(
                render_no_response_change_submit(request_id), status_code=504
            )
        change_id = str(change["change_id"])
        prior = self._sessions.change_view(record.session_id, change_id)
        # The §9 replay returns the ORIGINAL change: re-index only what
        # is new. A view this session already holds for this bench KEEPS
        # its acknowledged flag (a browser-back replay must not resurrect
        # the GW-72 alert over a change this session reconciled) and its
        # loaded approval; a first sighting — or a bench rebinding —
        # records a fresh view (the refute fold, F3).
        self._sessions.record_change_view(
            record.session_id,
            change_id,
            replace(prior, bench_id=bench_id)
            if prior is not None and prior.bench_id == bench_id
            else ChangeView(bench_id=bench_id),
        )
        try:
            bench = self._operations.bench_get(identity, bench_id)
        except OperationFailure:
            bench = {}
        return HTMLResponse(self.region_html(record, identity, bench, bench_id))

    async def change_page(self, change_id: str, request: Request) -> Response:
        """GW-70's read half: the ten-field record exactly as
        ``change_get`` serves it, the persistent alert when this
        session's index holds unacknowledged failed/unknown changes for
        the record's bench, and the workspace (admin + proposed)."""
        authed = self._authed(request)
        if authed is None:
            return self._unauthenticated_page(request)
        record, identity = authed
        try:
            change = self._operations.change_get(identity, change_id)
        except OperationFailure as fail:
            return self._failure_page(fail, request)
        bench_id = str(change.get("bench_id", ""))
        blocked = (
            self._blocked_changes(record, identity, bench_id)
            if self._has_admin(record)
            else []
        )
        return self._page(
            "change.j2",
            title=f"Change {change_id}",
            change=change,
            alert_html=self._alert_markup(blocked),
            # Trusted host-rendered markup (the module's own escaped
            # composition) — S704's escape hatch is not in play.
            workspace_html=Markup(  # noqa: S704
                self.workspace_html(record, identity, change)
            )
            if self._has_admin(record)
            else None,
            bench_generation=None,
            **self._strip(record),
        )

    async def load_approval(self, change_id: str, request: Request) -> Response:
        """§2.3 step 1 (the session layer, the staging trio's shape): read
        the stored approval document through ``document_get`` — no seam
        write — and record what it SAYS in this session's change view. An
        unstored digest renders the seam's own ``not_found`` row; the
        binding verdict derives from the document's bytes against the
        change record being viewed. The response re-renders the
        workspace with the approval facts and the apply control's
        offer-time state (GW-71 at offer time)."""
        authed = self._authed(request)
        if authed is None:
            return self._unauthenticated_page(request)
        record, identity = authed
        form = dict(await request.form())
        sha256 = str(form.get("approval_sha256", ""))
        try:
            change = self._operations.change_get(identity, change_id)
            doc = self._operations.document_get(identity, sha256)
        except OperationFailure as fail:
            return self._failure_page(fail, request)
        approval = self._derive_approval(
            ref_id=str(form.get("approval_id", "")),
            ref_version=str(form.get("approval_version", "")),
            sha256=sha256,
            body=doc["content"],
            change=change,
        )
        self._sessions.record_change_approval(record.session_id, change_id, approval)
        return HTMLResponse(self.workspace_html(record, identity, change))

    async def apply_change(self, change_id: str, request: Request) -> Response:
        """§2.3 step 3: ``change_apply`` with server-side truth — the form
        carries only the §9 request id and the approver's detached
        token; the generation comes from the record, the approval ref
        from the loaded view. GW-71's fire-time re-evaluation runs
        BEFORE the send (the armed-confirm rule): the approval document
        is re-read fresh and the view re-derived, and a self-approval or
        a non-binding approval refuses PRE-SEND — no ``change_apply``
        call; the UI does not send what it can see the gateway would
        refuse, and a pre-send refusal records nothing (the seam never
        judged). A seam-answered refusal re-reads the record and indexes
        the change — the state rendered anywhere is the record's, never
        the refusal's (§2.4). A non-``OperationFailure`` composes §C.3's
        no-response row with the change-page reconcile (§2.5)."""
        authed = self._authed(request)
        if authed is None:
            return self._unauthenticated_page(request)
        record, identity = authed
        form = dict(await request.form())
        request_id = str(form.get("request_id", ""))
        token = str(form.get("approver_token", ""))
        if not request_id or not token:
            return self._failure_page(
                OperationFailure(
                    failure(
                        "invalid_request",
                        "the apply form carries its request id and the approver"
                        " token",
                    )
                ),
                request,
            )
        view = self._sessions.change_view(record.session_id, change_id)
        if view is None or view.approval is None:
            return self._failure_page(
                OperationFailure(
                    failure(
                        "invalid_request",
                        "load the approval for this change before applying it",
                    )
                ),
                request,
            )
        try:
            change = self._operations.change_get(identity, change_id)
        except OperationFailure as fail:
            return self._failure_page(fail, request)
        # Index the change with the record's own bench binding (a
        # manually-entered change id gains its true bench here; the
        # index carries no state — this is not an outcome).
        bench_id = str(change.get("bench_id", ""))
        self._sessions.record_change_view(
            record.session_id, change_id, replace(view, bench_id=bench_id)
        )
        # GW-71's fire-time re-evaluation: the approval document re-read
        # FRESH (content-addressed and immutable — no TOCTOU by
        # construction) and the view re-derived from its bytes, never
        # from session memory; the corrected view is what renders.
        prior = view.approval
        try:
            doc = self._operations.document_get(identity, prior.sha256)
        except OperationFailure as fail:
            return self._failure_page(fail, request)
        approval = self._derive_approval(
            ref_id=prior.ref_id,
            ref_version=prior.ref_version,
            sha256=prior.sha256,
            body=doc["content"],
            change=change,
        )
        self._sessions.record_change_approval(record.session_id, change_id, approval)
        if not approval.binds or approval.approver_principal == record.principal:
            # Pre-send refusal: the workspace re-renders the same
            # disabled shape (non-binding or self-approval) — the seam
            # never judged, so no outcome exists to present.
            return HTMLResponse(self.workspace_html(record, identity, change))
        try:
            applied = self._operations.change_apply(
                identity,
                request_id,
                change_id,
                int(change["expected_generation"]),
                {
                    "id": approval.ref_id,
                    "version": approval.ref_version,
                    "sha256": approval.sha256,
                },
                approver_token=token,
            )
        except OperationFailure as fail:
            # Seam-answered: re-read the record and index the change —
            # the rendered state is the record's, never inferred from
            # the refusal (§2.4). The row itself renders unsoftened.
            try:
                settled = self._operations.change_get(identity, change_id)
                self._sessions.record_change_view(
                    record.session_id,
                    change_id,
                    replace(view, bench_id=str(settled.get("bench_id", bench_id))),
                )
            except OperationFailure:
                pass
            return self._failure_page(fail, request)
        except Exception:
            # Transport-shaped (no interface answer): §C.3's no-response
            # row with the change-honest reconcile. An in-process adapter
            # cannot honestly produce this; the suite induces it (the G2
            # §7-F posture).
            return HTMLResponse(
                render_no_response_change_apply(change_id), status_code=504
            )
        try:
            bench = self._operations.bench_get(identity, bench_id)
            generation = int(bench.get("generation", 0))
        except (OperationFailure, ValueError):
            generation = None
        # US9: the applied record beside the generation increment, read
        # fresh from the bench after the seam bumped it.
        return HTMLResponse(
            self.workspace_html(record, identity, applied, bench_generation=generation)
        )

    async def acknowledge_change(self, change_id: str, request: Request) -> Response:
        """§2.4's reconciliation (session-layer, NO seam call): the
        operator, having read the record, marks it acknowledged in this
        session's index — the alert clears and the region's apply
        disables lift, the response re-rendering the region (the alert's
        own surface). The gateway record never changes (no operation
        marks a change reconciled); the acknowledgement is per-session
        presentation. A change this session never indexed is an honest
        ``not_found`` — there is nothing to acknowledge."""
        authed = self._authed(request)
        if authed is None:
            return self._unauthenticated_page(request)
        record, identity = authed
        view = self._sessions.change_view(record.session_id, change_id)
        if view is None or not view.bench_id:
            return self._failure_page(
                OperationFailure(
                    failure(
                        "not_found",
                        f"change {change_id} is not in this session's index",
                    )
                ),
                request,
            )
        self._sessions.acknowledge_change(record.session_id, change_id)
        try:
            bench = self._operations.bench_get(identity, view.bench_id)
        except OperationFailure as fail:
            return self._failure_page(fail, request)
        return HTMLResponse(
            self.region_html(record, identity, bench, view.bench_id)
        )


def register_admin_routes(
    router: APIRouter,
    *,
    operations: Operations,
    sessions: SessionStore,
    resolve_session: Callable[[Request], SessionRecord | None],
    session_identity: Callable[[SessionRecord], Identity],
    failure_page: Callable[[OperationFailure, Request], HTMLResponse],
    unauthenticated_page: Callable[[Request], HTMLResponse],
    page: Callable[..., HTMLResponse],
    render: Callable[..., str],
    session_warning: Callable[[SessionRecord], str | None],
) -> AdminRoutes:
    """Register the G4 administration routes on the UI router (before its
    catch-all) and return the composed views the bench page embeds —
    the same closure pattern as the control routes."""
    admin = AdminRoutes(
        operations=operations,
        sessions=sessions,
        resolve_session=resolve_session,
        session_identity=session_identity,
        failure_page=failure_page,
        unauthenticated_page=unauthenticated_page,
        page=page,
        render=render,
        session_warning=session_warning,
    )
    admin.register(router)
    return admin
