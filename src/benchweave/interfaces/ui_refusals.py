"""The §C.3 refusal rows as the UI's carried data (G2b, design §2.4).

The gateway renders refusals from ONE table: ui-contract.md §C.3's 15
rows (the 14 interface error codes plus ``no-response``, the
transport-absence row), each carried as a :class:`RefusalData` with the
table's own severity, what-happened wording, sent status and operator
action. The suite pins the carried copy against the contract table
character for character, so wording drift reds in pytest, not in a
browser (G2a pinned the single ``unauthenticated`` row; G2b generalises).

GW-11: a failure renders its own code's row — never a softer one.
GW-12's presentation half: ``no-response`` (the one row with no seam
emitter — an in-process adapter cannot fail to answer) renders through
``render_no_response`` with sent status ``UNKNOWN`` and a reconcile
action naming :meth:`Operations.run_find`'s view for the same
``request_id``; the mutating-form half of GW-12 is G3's (design D2).
"""

from __future__ import annotations

from benchweave_ui_html.data import RefusalData
from benchweave_ui_html.partials import render_refusal
from markupsafe import Markup, escape

#: §C.3's 15 rows, keyed by code. Wording is the contract's own
#: (``docs/internal/ui-contract.md`` §C.3); the pin test refuses drift.
REFUSAL_ROWS: dict[str, RefusalData] = {
    row.code: row
    for row in (
        RefusalData(
            code="invalid_request",
            severity="warning",
            what_happened="The request was not accepted: it failed validation.",
            sent_status="NO",
            operator_action="Correct the staged input and submit it again.",
        ),
        RefusalData(
            code="unauthenticated",
            severity="warning",
            what_happened="The request was not accepted: the caller is not authenticated.",
            sent_status="NO",
            operator_action="Authenticate and submit again.",
        ),
        RefusalData(
            code="forbidden",
            severity="warning",
            what_happened=(
                "The request was not accepted: the caller lacks the required permission."
            ),
            sent_status="NO",
            operator_action=(
                "Have an operator with the required authority act, or request the role."
            ),
        ),
        RefusalData(
            code="not_found",
            severity="advisory",
            what_happened="The addressed resource is unavailable to this caller.",
            sent_status="NO",
            operator_action=(
                "Check the identifier and the caller's scope; do not infer existence "
                "from the answer."
            ),
        ),
        RefusalData(
            code="conflict",
            severity="warning",
            what_happened=(
                "The request was not accepted: the addressed revision or state has "
                "moved on."
            ),
            sent_status="NO",
            operator_action="Re-read current state and re-stage the request.",
        ),
        RefusalData(
            code="policy_denied",
            severity="warning",
            what_happened="The request was not accepted: policy refuses this action.",
            sent_status="NO",
            operator_action=(
                "Request a policy change or an authorised path; do not retry unchanged."
            ),
        ),
        RefusalData(
            code="not_ready",
            severity="advisory",
            what_happened=(
                "The request was not accepted: the target is not ready for this action."
            ),
            sent_status="NO",
            operator_action="Wait for readiness and submit again.",
        ),
        RefusalData(
            code="gone",
            severity="advisory",
            what_happened="The request was not accepted: the addressed resource is gone.",
            sent_status="NO",
            operator_action="Refresh the view and address a current resource.",
        ),
        RefusalData(
            code="cursor_expired",
            severity="advisory",
            what_happened="The listing cursor expired or its snapshot was superseded.",
            sent_status="NO",
            operator_action="Restart the listing and deduplicate by stable resource identity.",
        ),
        RefusalData(
            code="event_gap",
            severity="warning",
            what_happened=(
                "Retention overtook the event cursor; events are missing from the stream."
            ),
            sent_status="NO",
            operator_action=(
                "Re-read the affected snapshots from a new cursor; do not skip the gap."
            ),
        ),
        RefusalData(
            code="payload_too_large",
            severity="warning",
            what_happened="The request was not accepted: its payload exceeds the limit.",
            sent_status="NO",
            operator_action="Reduce the payload and submit again.",
        ),
        RefusalData(
            code="rate_limited",
            severity="advisory",
            what_happened="The request was not accepted: the rate limit was hit.",
            sent_status="NO",
            operator_action="Wait the advertised interval and submit again.",
        ),
        RefusalData(
            code="unavailable",
            severity="critical",
            what_happened="The gateway is unavailable.",
            sent_status="NO",
            operator_action=(
                "Restore or await the gateway; treat observation and protection "
                "visibility as degraded."
            ),
        ),
        RefusalData(
            code="internal_error",
            severity="warning",
            what_happened="The request was not accepted: an internal error occurred.",
            sent_status="NO",
            operator_action=(
                "Retry from known state or contact the operator; the correlation ID "
                "links diagnostics."
            ),
        ),
        RefusalData(
            code="no-response",
            severity="critical",
            what_happened="No interface answer arrived (transport failure or timeout).",
            sent_status="UNKNOWN",
            operator_action=(
                "Do not retry blindly; reconcile via run identity and duplicate "
                "suppression before acting again."
            ),
        ),
    )
}

if len(REFUSAL_ROWS) != 15:  # a construction bug, not a runtime refusal
    raise RuntimeError(
        f"§C.3 carries exactly 15 rows; the table has {len(REFUSAL_ROWS)}"
    )


def row_for(code: str) -> RefusalData:
    """The §C.3 row for an interface error code (all 14 are table rows)."""
    row = REFUSAL_ROWS.get(code)
    if row is None:
        raise KeyError(f"{code!r} has no §C.3 row — not an interface error code")
    return row


def render_no_response(request_id: str) -> str:
    """The no-response render: §C.3's row plus GW-12's reconcile action.

    The reconcile action is a LINK to ``run_find``'s view for the same
    ``request_id`` — the interface's own idempotent resolution path (§9),
    so an operator reconciles before acting again. Sent status stays
    ``UNKNOWN`` (A06): the render never asserts the request was or was
    not dispatched.
    """
    row = REFUSAL_ROWS["no-response"]
    # request_id is caller data on a G3 form; it escapes here so the
    # reconcile link cannot carry markup whatever the id contains.
    safe_id = str(escape(request_id))
    return (
        render_refusal(row)
        + '<p class="bw-refusal__reconcile" data-bw-reconcile-action>'
        f'Reconcile: <a href="/ui/requests/{safe_id}">look up request '
        f"<code>{safe_id}</code></a> before you act again.</p>"
    )


def markup_no_response(request_id: str) -> Markup:
    """``render_no_response`` as trusted markup for a Jinja context slot.

    Trusted because every interpolable byte is escaped at construction
    (``render_no_response``'s own rule); the partials' output is the
    package's own HTML.
    """
    # Trusted package-rendered HTML over escaped interpolables — S704's
    # escape hatch is not in play (same rule as ui.py's refusal slots).
    return Markup(render_no_response(request_id))  # noqa: S704


def render_no_response_change_submit(request_id: str) -> str:
    """GW-12's change half for submit (G4, design record §2.5): the §C.3
    no-response row with the change-honest reconcile action — resubmit
    the IDENTICAL form. §9 makes that retry safe by construction (same
    principal, same operation key, same body digest → the original
    change returns; a different body → conflict). ``run_find``'s link
    would be a lie here: change keys are invisible to it. The run-shaped
    ``render_no_response`` stays byte-identical (suite-pinned wording)."""
    row = REFUSAL_ROWS["no-response"]
    safe_id = str(escape(request_id))
    return (
        render_refusal(row)
        + '<p class="bw-refusal__reconcile" data-bw-reconcile-action>'
        "Reconcile: resubmit the identical form (request id "
        f"<code>{safe_id}</code>) — duplicate suppression returns the "
        "original change.</p>"
    )


def render_no_response_change_apply(change_id: str) -> str:
    """GW-12's change half for apply (G4, design record §2.5): the row
    plus the change-page link — ``change_get`` shows the outcome the
    apply left behind (proposed, applied, failed or unknown). No retry
    action: the seam's advice is ``never`` (the D13 retry honesty; a
    re-apply of a decided change is the two-phase ``conflict``)."""
    row = REFUSAL_ROWS["no-response"]
    safe_id = str(escape(change_id))
    return (
        render_refusal(row)
        + '<p class="bw-refusal__reconcile" data-bw-reconcile-action>'
        f'Reconcile: <a href="/ui/changes/{safe_id}">read the change record</a>'
        " before you act again — do not re-apply this change.</p>"
    )
