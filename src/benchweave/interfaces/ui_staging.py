"""The G3b staging routes and panel (issue #304, design record §2.4).

The second panel of the controls fragment — staging, check, arm/disarm,
run-starts — over the same seam and the same session-side staging
records commit 1 landed. Every handler keeps the G2/G3a translation
shape: session resolution, an honest pre-send guard where the session
record dictates one, the seam call, the fragment re-render. Every byte
the panel renders is a seam answer (the ``document_get`` chain, a
``run_check`` verdict, ``events_get`` rows) or a pure function over seam
answers (``armed_composition``, ``trip_active``) — never a store read
(CON-5's line; the one state home is the session-side staging record,
which is presentation of this session's own cycle).

Ruled deviations carried here (each named in its commit message): the
stage route reads the binding document at staging time to pin the §9
request id (the design's §2.4 letter was written for a session-minted
id; the seam requires ``run_start``'s id to equal the binding's own),
and ``run-starts`` lands as a GUARD-ONLY interim replaced by the next
commit.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from benchweave_ui_html.data import DisabledLabelData
from benchweave_ui_html.partials import render_disabled_label
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from markupsafe import Markup

from benchweave.interfaces.errors import OperationFailure, failure
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.operations import TIER_SATISFIES, Operations
from benchweave.interfaces.sessions import SessionRecord, SessionStore, StagedStart
from benchweave.interfaces.ui_control import (
    _attention_bound_ms,
    _binding_chain,
    _is_digest,
    _parse_iso_to_epoch,
    armed_composition,
    trip_active,
)
from benchweave.interfaces.ui_refusals import render_no_response

#: The trip predicate's event read: page size for the tail walk. The
#: seam's own retention bound (``max_page_size * 10`` rows per stream)
#: is the exhaustion point; the page cap below is a runaway guard set
#: above that bound, never a semantic cutoff.
_EVENTS_PAGE = 1000
_EVENTS_PAGE_CAP = 12


def read_bench_events(
    operations: Operations, identity: Identity, bench_id: str, *, page_size: int
) -> list[dict[str, Any]]:
    """The bench's retained event rows, paged to exhaustion through the
    seam (``events_get``), oldest page first.

    Any seam refusal composes ``[]`` — no verdict, never a fabricated
    one (the trip predicate's disclosed boundary: an unreadable stream
    is not protection-active). ``trip_active`` keys on the newest
    trip-lifecycle row, so the walk must reach the tail; retention (the
    seam's own trim) bounds it.
    """
    rows: list[dict[str, Any]] = []
    after: str | None = None
    for _ in range(_EVENTS_PAGE_CAP):
        try:
            page = operations.events_get(
                identity, bench_id, after=after, limit=page_size
            )
        except OperationFailure:
            return []
        batch = list(page.get("events", []))
        rows.extend(batch)
        if len(batch) < page_size:
            return rows
        after = str(page.get("cursor", "")) or None
    return rows


def _binding_refs(events: list[dict[str, Any]]) -> list[str]:
    """The staging selector's candidates (GW-50): binding digests the
    bench's own event history pins — ``authority_changed`` evidence rows
    carry the closed ``{id, version, sha256}`` document ref. The
    interface has no binding enumeration (G3-D1); this is the honest
    read of what the wire already carries, in sequence order."""
    refs: list[str] = []
    seen: set[str] = set()
    for row in events:
        if str(row.get("kind", "")) != "authority_changed":
            continue
        evidence = row.get("evidence")
        if not isinstance(evidence, dict):
            continue
        sha = str(evidence.get("sha256", ""))
        if sha and sha not in seen:
            seen.add(sha)
            refs.append(sha)
    return refs


class StagingRoutes:
    """The five G3b routes plus the staging-panel composition, wired by
    ``register_control_routes`` with its own closures (the ui.py render
    callable included, so the panel template renders through the same
    Jinja environment as every page)."""

    def __init__(
        self,
        *,
        operations: Operations,
        sessions: SessionStore,
        now_epoch: Callable[[], int],
        page_size: int,
        resolve_session: Callable[[Request], SessionRecord | None],
        session_identity: Callable[[SessionRecord], Identity],
        failure_page: Callable[[OperationFailure, Request], HTMLResponse],
        unauthenticated_page: Callable[[Request], HTMLResponse],
        render: Callable[..., str],
        fragment: Callable[..., Response],
    ) -> None:
        self._operations = operations
        self._sessions = sessions
        self._now_epoch = now_epoch
        self._page_size = page_size
        self._resolve_session = resolve_session
        self._session_identity = session_identity
        self._failure_page = failure_page
        self._unauthenticated_page = unauthenticated_page
        self._render = render
        self._fragment = fragment

    # --- shared shapes ------------------------------------------------------

    def _authed(self, request: Request) -> tuple[SessionRecord, Identity] | None:
        record = self._resolve_session(request)
        if record is None:
            return None
        return record, self._session_identity(record)

    def _has_control(self, record: SessionRecord) -> bool:
        return bool(record.scopes & TIER_SATISFIES["control"])

    def _observe_refusal(self, request: Request) -> HTMLResponse:
        """Session-layer refusal for observe-scope sessions: the staging
        trio writes no seam row the seam's own tier check could refuse,
        so the route states the tier honestly itself (§C.3's forbidden
        row — the same answer the seam gives run-checks/run-starts)."""
        return self._failure_page(
            OperationFailure(
                failure(
                    "forbidden",
                    "staging and starting runs is a control-scope action;"
                    " this session has observe authority only",
                )
            ),
            request,
        )

    def _tail_events(self, identity: Identity, bench_id: str) -> list[dict[str, Any]]:
        return read_bench_events(
            self._operations, identity, bench_id, page_size=self._page_size
        )

    def _lease_remaining_ms(
        self, record: SessionRecord, bench_id: str
    ) -> int | None:
        """The held-lease view's live remaining time, or ``None`` (no
        view, unparseable stamp, or already past): an absent view
        declares no attention window at all — never zero, which would
        refuse every start the seam might still allow."""
        held = self._sessions.held_lease(record.session_id, bench_id)
        if held is None:
            return None
        expiry_s = _parse_iso_to_epoch(stamp=held.expires_at)
        now = self._now_epoch()
        if expiry_s is None or now >= expiry_s:
            return None
        return (expiry_s - now) * 1000

    def _attention_failure(
        self, record: SessionRecord, bench_id: str, procedure_doc: dict[str, Any]
    ) -> OperationFailure | None:
        """GW-56 at arm and at fire (DEP7 chain, #306-verified): for a
        manual-mode procedure the attention bound ``max_body_ms +
        max_protection_ms`` must not exceed the remaining attention
        window — the minimum of the KNOWN remainings (the held view's
        lease leg contributes only when a live view exists). Equality
        is allowed; a non-schema shape (no bound) composes no refusal —
        never a fabricated zero."""
        if str(procedure_doc.get("mode", "")) != "manual":
            return None
        bound = _attention_bound_ms(procedure_doc)
        if bound is None:
            return None
        lease_rem = self._lease_remaining_ms(record, bench_id)
        session_rem = max(record.expires_at - self._now_epoch(), 0) * 1000
        legs = [session_rem]
        if lease_rem is not None:
            legs.append(lease_rem)
        if bound <= min(legs):
            return None
        lease_figure = f"{lease_rem} ms" if lease_rem is not None else "no live held-lease view"
        return OperationFailure(
            failure(
                "policy_denied",
                f"the procedure's attention bound ({bound} ms) exceeds the"
                f" remaining attention window (lease: {lease_figure};"
                f" session: {session_rem} ms). Renew the lease or run"
                " benchweave ui-login for a longer session.",
            )
        )

    # --- the panel ----------------------------------------------------------

    def panel_html(
        self,
        record: SessionRecord,
        identity: Identity,
        bench: dict[str, Any],
        bench_id: str,
        page_events: list[dict[str, Any]],
        started: tuple[str, bool] | None = None,
    ) -> str:
        """The staging panel's HTML, composed from seam answers at the
        render clock: the session's staging record, the DEP7 chain read
        (an unreadable chain is the panel's own disabled shape, never a
        guess), the recorded check, and the trip predicate over the
        event tail. ``page_events`` (the bench page's own first page)
        feeds only the selector's candidate refs — admission's
        ``authority_changed`` rows are the oldest in the stream."""
        staged_record = self._sessions.staged_start(record.session_id, bench_id)
        staged_ctx: dict[str, Any] | None = None
        check_ctx: dict[str, Any] | None = None
        readable = False
        energy = False
        armed_text: str | None = None
        if staged_record is not None:
            staged_ctx = {
                "sha256": str(staged_record.binding_ref.get("sha256", "")),
                "request_id": staged_record.request_id,
                "armed": staged_record.armed,
            }
            if staged_record.check is not None:
                valid = bool(staged_record.check.get("valid"))
                findings = staged_record.check.get("findings") or []
                check_ctx = {
                    "state": "valid" if valid else "invalid",
                    "findings_count": len(findings),
                }
            try:
                binding_doc, procedure_doc = _binding_chain(
                    self._operations, identity, staged_record.binding_ref
                )
                energy, _manual, armed_text = armed_composition(
                    binding_doc, procedure_doc
                )
                readable = True
            except OperationFailure:
                pass  # the chain is not readable; the panel says so itself
        # FOLD-3: the row's event precedence — the response's own start
        # event (run id, replayed flag) when this render answers a start
        # POST; otherwise the record's started-run memory renders as the
        # prior-start disclosure ("this binding already started run X").
        started_run_id: str | None = None
        replayed = False
        prior_started = False
        if started is not None:
            started_run_id, replayed = started
        elif staged_record is not None and staged_record.started_run_id is not None:
            started_run_id = staged_record.started_run_id
            prior_started = True
        return self._render(
            "staging-panel.j2",
            observe=not self._has_control(record),
            staged=staged_ctx,
            check=check_ctx,
            arming={
                "readable": readable,
                "energy": energy,
                "armed_text": armed_text,
            },
            bench_id=bench_id,
            generation=int(bench.get("generation", 0)),
            refs=_binding_refs(page_events),
            trip=trip_active(self._tail_events(identity, bench_id)),
            started_run_id=started_run_id,
            replayed=replayed,
            prior_started=prior_started,
            # Trusted package-rendered HTML (the §C.2 partial), not
            # request data — S704's escape hatch is not in play.
            no_authority_html=Markup(  # noqa: S704
                render_disabled_label(
                    DisabledLabelData(
                        reason="no-authority",
                        label="No lease or policy authority",
                    )
                )
            ),
        )

    # --- the routes ---------------------------------------------------------

    def register(self, router: APIRouter) -> None:
        router.add_api_route(
            "/benches/{bench_id}/staging",
            self.stage_binding,
            methods=["POST"],
            include_in_schema=False,
        )
        router.add_api_route(
            "/benches/{bench_id}/run-checks",
            self.run_checks,
            methods=["POST"],
            include_in_schema=False,
        )
        router.add_api_route(
            "/benches/{bench_id}/staging/arm",
            self.staging_arm,
            methods=["POST"],
            include_in_schema=False,
        )
        router.add_api_route(
            "/benches/{bench_id}/staging/disarm",
            self.staging_disarm,
            methods=["POST"],
            include_in_schema=False,
        )
        router.add_api_route(
            "/benches/{bench_id}/run-starts",
            self.run_starts,
            methods=["POST"],
            include_in_schema=False,
        )

    async def stage_binding(self, bench_id: str, request: Request) -> Response:
        """GW-50: stage the binding selection — a session-layer action,
        no seam write. The digest pre-check refuses garbage pre-send; a
        STORED binding pins the §9 request id (the binding document's
        own — the seam's binding-match rule); an unstored digest stages
        unverified (``not_found`` tolerated) and the check/arm steps
        answer honestly. Any stage change clears the recorded check and
        the armed flag (GW-51)."""
        authed = self._authed(request)
        if authed is None:
            return self._unauthenticated_page(request)
        record, identity = authed
        if not self._has_control(record):
            return self._observe_refusal(request)
        form = dict(await request.form())
        sha = str(form.get("binding_sha256", ""))
        if not _is_digest(sha):
            return self._failure_page(
                OperationFailure(
                    failure(
                        "invalid_request",
                        "binding_sha256 must be a 64-character hex digest",
                    )
                ),
                request,
            )
        request_id: str | None = None
        binding_ref: dict[str, Any] = {"sha256": sha}
        try:
            content = self._operations.document_get(identity, sha)["content"]
            doc_request = content.get("request_id")
            contract_version = content.get("contract_version")
            if (
                isinstance(doc_request, str)
                and doc_request
                and isinstance(contract_version, str)
                and contract_version
                and isinstance(content.get("procedure"), dict)
            ):
                # The catalog's binding_ref requires the closed triple; a
                # binding document carries no id/version of its own, so the
                # ref names the binding by its request id over its contract
                # version — the interface suites' own convention. The seam
                # keys on the digest and the document's own request_id;
                # nothing here invents authority.
                binding_ref = {
                    "id": doc_request,
                    "version": contract_version,
                    "sha256": sha,
                }
                request_id = doc_request
        except OperationFailure as fail:
            if fail.failure.code != "not_found":
                return self._failure_page(fail, request)
            # not_found tolerated: the digest stages; the check reports
            # its findings and the arm's chain read refuses honestly.
        prior = self._sessions.staged_start(record.session_id, bench_id)
        # FOLD-3: a same-digest restage preserves the started-run memory
        # (the §9 id is the binding's own — the knowledge belongs to the
        # binding, not the check cycle); a different binding is a new
        # cycle without it.
        prior_started: str | None = None
        if prior is not None and str(prior.binding_ref.get("sha256", "")) == sha:
            prior_started = prior.started_run_id
        self._sessions.record_staged_start(
            record.session_id,
            bench_id,
            StagedStart(
                request_id=request_id,
                binding_ref=binding_ref,
                check=None,
                armed=False,
                started_run_id=prior_started,
            ),
        )
        try:
            bench = self._operations.bench_get(identity, bench_id)
        except OperationFailure as fail:
            return self._failure_page(fail, request)
        return self._fragment(record, bench, bench_id, identity)

    async def run_checks(self, bench_id: str, request: Request) -> Response:
        """GW-51: the preflight on the staged binding — ``run_check``
        on the seam; the verdict (valid, findings, generation) records
        in the staging record and the start control's guard reads it."""
        authed = self._authed(request)
        if authed is None:
            return self._unauthenticated_page(request)
        record, identity = authed
        if not self._has_control(record):
            return self._observe_refusal(request)
        staged = self._sessions.staged_start(record.session_id, bench_id)
        if staged is None:
            return self._failure_page(
                OperationFailure(
                    failure("invalid_request", "stage a binding before checking")
                ),
                request,
            )
        try:
            result = self._operations.run_check(identity, bench_id, staged.binding_ref)
        except OperationFailure as fail:
            return self._failure_page(fail, request)
        self._sessions.record_staged_start(
            record.session_id,
            bench_id,
            replace(
                staged,
                check={
                    "valid": bool(result["valid"]),
                    "generation": int(result["generation"]),
                    "findings": list(result.get("findings", [])),
                },
            ),
        )
        try:
            bench = self._operations.bench_get(identity, bench_id)
        except OperationFailure as fail:
            return self._failure_page(fail, request)
        return self._fragment(record, bench, bench_id, identity)

    async def staging_arm(self, bench_id: str, request: Request) -> Response:
        """GW-52's arm step: read the DEP7 chain, compose the armed
        confirm from the documents, and run GW-56's bound check —
        reads only (no seam mutation; the spies in the suite pin it).
        An unstored/unreadable chain refuses ``not_found`` honestly; the
        de-energising class has no arm (its start is one action)."""
        authed = self._authed(request)
        if authed is None:
            return self._unauthenticated_page(request)
        record, identity = authed
        if not self._has_control(record):
            return self._observe_refusal(request)
        staged = self._sessions.staged_start(record.session_id, bench_id)
        if staged is None:
            return self._failure_page(
                OperationFailure(
                    failure("invalid_request", "nothing is staged on this bench")
                ),
                request,
            )
        try:
            binding_doc, procedure_doc = _binding_chain(
                self._operations, identity, staged.binding_ref
            )
        except OperationFailure as fail:
            return self._failure_page(fail, request)
        energy, _manual, _text = armed_composition(binding_doc, procedure_doc)
        if not energy:
            return self._failure_page(
                OperationFailure(
                    failure(
                        "invalid_request",
                        "the staged procedure is the de-energising class;"
                        " its start needs no arm",
                    )
                ),
                request,
            )
        gw56 = self._attention_failure(record, bench_id, procedure_doc)
        if gw56 is not None:
            return self._failure_page(gw56, request)
        self._sessions.record_staged_start(
            record.session_id, bench_id, replace(staged, armed=True)
        )
        try:
            bench = self._operations.bench_get(identity, bench_id)
        except OperationFailure as fail:
            return self._failure_page(fail, request)
        return self._fragment(record, bench, bench_id, identity)

    async def staging_disarm(self, bench_id: str, request: Request) -> Response:
        """The operator's Cancel: clears the armed flag, keeps the
        staged binding and the recorded check — the staged intent is
        never silently discarded (GW-52's no-auto-disarm inverse)."""
        authed = self._authed(request)
        if authed is None:
            return self._unauthenticated_page(request)
        record, identity = authed
        if not self._has_control(record):
            return self._observe_refusal(request)
        staged = self._sessions.staged_start(record.session_id, bench_id)
        if staged is None:
            return self._failure_page(
                OperationFailure(
                    failure("invalid_request", "nothing is staged on this bench")
                ),
                request,
            )
        self._sessions.record_staged_start(
            record.session_id, bench_id, replace(staged, armed=False)
        )
        try:
            bench = self._operations.bench_get(identity, bench_id)
        except OperationFailure as fail:
            return self._failure_page(fail, request)
        return self._fragment(record, bench, bench_id, identity)

    async def run_starts(self, bench_id: str, request: Request) -> Response:
        """GW-50–53's start: the staged cycle's fire path. Pre-send
        guards (no seam write): a staged set with a check on record, the
        form's §9 id matching the staged cycle (a foreign id replays
        through run_find first — §9's own resolution), the armed flag
        for the energy class. Fire-time guards (GW-52/54, R-PROTECT-1):
        a trip arrived while armed — re-render the armed state with the
        protection-active disable, no seam call; GW-56's bound again at
        fire. Then one ``run_start`` (the §9 id IS the binding's own
        request id); a non-OperationFailure composes the §C.3
        no-response row with the reconcile link. Keep-record-on-start
        (RULED DEVIATION): the staged record survives a committed start
        as the replay handle, so a resubmission reaches the seam and
        replays (§9), never a second run."""
        authed = self._authed(request)
        if authed is None:
            return self._unauthenticated_page(request)
        record, identity = authed
        if not self._has_control(record):
            return self._observe_refusal(request)
        form = dict(await request.form())
        form_request = str(form.get("request_id", ""))
        staged = self._sessions.staged_start(record.session_id, bench_id)
        if staged is None or (form_request and staged.request_id != form_request):
            # The record cleared, or the form carries another cycle's
            # §9 id: the id may still resolve to an accepted run —
            # replay it before refusing the stale form.
            if form_request:
                try:
                    replay = self._operations.run_find(identity, form_request)
                except OperationFailure:
                    replay = None
                if replay is not None:
                    try:
                        bench = self._operations.bench_get(identity, bench_id)
                    except OperationFailure:
                        bench = {}
                    return self._fragment(
                        record,
                        bench,
                        bench_id,
                        identity,
                        started=(str(replay["run_id"]), True),
                    )
            return self._failure_page(
                OperationFailure(
                    failure(
                        "invalid_request",
                        "stage and check a binding first — the form names no"
                        " cycle this session holds",
                    )
                ),
                request,
            )
        if staged.check is None:
            return self._failure_page(
                OperationFailure(
                    failure(
                        "invalid_request",
                        "no check is on record for the staged set — run the"
                        " check before starting",
                    )
                ),
                request,
            )
        if staged.request_id is None:
            return self._failure_page(
                OperationFailure(
                    failure(
                        "invalid_request",
                        "the staged binding's request id is unknown — restage a"
                        " stored binding",
                    )
                ),
                request,
            )
        try:
            binding_doc, procedure_doc = _binding_chain(
                self._operations, identity, staged.binding_ref
            )
        except OperationFailure as fail:
            return self._failure_page(fail, request)
        energy, _manual, _text = armed_composition(binding_doc, procedure_doc)
        if energy and not staged.armed:
            return self._failure_page(
                OperationFailure(
                    failure(
                        "invalid_request",
                        "the staged procedure energises an output — arm the"
                        " staged set before confirming",
                    )
                ),
                request,
            )
        if energy and trip_active(self._tail_events(identity, bench_id)):
            # GW-52/54's fire-time guard: a trip arrived while armed —
            # refuse WITHOUT a seam call, re-rendering the armed state
            # with the §E.1 protection-active disable; no auto-disarm.
            try:
                bench = self._operations.bench_get(identity, bench_id)
            except OperationFailure:
                bench = {}
            return self._fragment(record, bench, bench_id, identity)
        gw56 = self._attention_failure(record, bench_id, procedure_doc)
        if gw56 is not None:
            return self._failure_page(gw56, request)
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
        pre_started = staged.started_run_id
        held = self._sessions.held_lease(record.session_id, bench_id)
        lease_id = held.lease_id if held is not None else None
        try:
            run = self._operations.run_start(
                identity,
                bench_id,
                staged.request_id,
                staged.binding_ref,
                expected_generation,
                lease_id,
            )
        except OperationFailure as fail:
            return self._failure_page(fail, request)
        except Exception:
            # Transport-shaped (no interface answer): §C.3's no-response
            # row, sent status UNKNOWN, the reconcile link to run_find's
            # view. An in-process adapter cannot honestly produce this;
            # the suite induces it (the G2 §7-F posture).
            return HTMLResponse(
                render_no_response(staged.request_id), status_code=504
            )
        # Keep-record-on-start (ruled deviation): the staged record
        # stays as the replay handle — §9 makes the resubmission
        # idempotent — and now carries the started id itself (FOLD-3),
        # so every later render discloses the prior start; the returned
        # id EQUALS the record's memory iff this fire was the §9 replay
        # of the first start.
        started_id = str(run["run_id"])
        replayed = pre_started is not None and started_id == pre_started
        self._sessions.record_staged_start(
            record.session_id, bench_id, replace(staged, started_run_id=started_id)
        )
        try:
            bench = self._operations.bench_get(identity, bench_id)
        except OperationFailure:
            bench = {}
        return self._fragment(
            record, bench, bench_id, identity, started=(started_id, replayed)
        )
