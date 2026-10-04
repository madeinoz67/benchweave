"""The G4 browser acceptance lane (issue #305, design record §6 arm F as
ruled for this lane): a real browser drives the composed gateway's
administration surface — the seams the REST-level G4 suites cannot see.

The lane exists because the REST-level suites exercise the handlers
through TestClient only: the CSRF configRequest pipeline, htmx's
responseHandling override (the 45x fragment swaps), the in-place swap
discipline and the approval forms' browser-side validation never run
there. The arms (each meaningful by a cp-backup mutation of the
mechanism it pins, verbatim RED captured in the run report; the file
and line the mutation attacked is named in each docstring):

- the admin cycle through the REAL buttons: submit the region's
  trip_reset form (CSRF asserted on the wire, no 403 anywhere), the
  review page renders the ten-field record, the region lists the change
  in place, and the store holds exactly one row;
- the approval workspace: paste the approval digest + ref through the
  real form — the approver principal DISPLAYS with the binding facts —
  and a self-approval displays its approver while apply is NOT offered:
  the disabled control carries §C.2 ``no-authority`` and the
  independence note, and no live apply form exists;
- the apply flow through real buttons: a binding independent approval
  loads, the detached token applies, the applied shape renders the
  generation increment, and the token appears in no response byte; the
  §9 replay: the original form re-POSTed through htmx's own pipeline
  under an induced no-response draws the §C.3 no-response row with the
  carried resubmit form, and clicking the carried button returns the
  original change (one row, §9);
- the carried reconcile's swap duty (xfail — see that test for the
  cited defect evidence; reported, not fixed, per the brief);
- GW-72: a failed apply renders the §B.1 critical alert (``reasons[0]``
  verbatim, the reconciliation route) persistently across reloads, the
  proposed row's apply affordance renders disabled under
  ``no-authority``, and the region's acknowledge button clears the
  alert and lifts the disable — submit stays armed;
- axe at WCAG 2.2 AA on the shapes the G2 census cannot render (the
  admin-scoped bench page, the observe bench page carrying the new
  region, the change page with a loaded independent approval, and the
  failed change page with the alert) — zero violations, with the
  planted-violation control re-proven in this served context (the
  meaningfulness instrument for the measurement arm, per the G2
  census's own control).

Serialized in the browser marker (CI's browser job, ``uv run pytest -q
-m browser``). One module-scoped gateway, one admin session; state
accumulates across the arms by design (a session's index is the
surface under test) — every arm seeds its own changes and scopes its
assertions to rows it can name.
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright
from ui_gateway_support import (
    FIXTURES,
    LIMITS,
    NOW_EPOCH,
    SECRET,
    boot,
    put_approval,
    stop,
)

from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.operations import Operations
from benchweave.interfaces.sessions import SessionStore
from benchweave.state.store import Store

pytestmark = pytest.mark.browser

BENCH_ID = "sim-bench"

ADMIN = frozenset({"stg:observe", "stg:control", "stg:admin"})
OBSERVE = frozenset({"stg:observe"})

WCAG_22_AA_TAGS = ["wcag2a", "wcag2aa", "wcag22a", "wcag22aa"]


class _Clock:
    """One frozen epoch cell (the G4 arms need no clock motion; the
    REST-level G4 suites' exact shape)."""

    def __init__(self) -> None:
        self.epoch = NOW_EPOCH

    def epoch_s(self) -> int:
        return self.epoch

    def iso(self) -> str:
        from datetime import UTC, datetime

        return (
            datetime.fromtimestamp(self.epoch, tz=UTC)
            .isoformat()
            .replace("+00:00", "Z")
        )


def _session(
    sessions: SessionStore, *, principal: str, scopes: frozenset[str]
) -> Any:
    code = sessions.mint_login_code(
        Identity(
            principal=principal,
            audience="stg",
            scopes=scopes,
            expires_at=NOW_EPOCH + 12 * 3600,
        ),
        ttl_seconds=8 * 3600,
    )
    return sessions.exchange(code)


@pytest.fixture(scope="module")
def served(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SimpleNamespace]:
    """One composed gateway on a real loopback port (the G3a lane's
    rig, frozen clock): a real store, the fixture bench admitted at
    lifespan, one admin + one observe session minted at setup."""
    clock = _Clock()
    data_dir = tmp_path_factory.mktemp("g4-browser")
    db_path = str(data_dir / "state-g4-browser.sqlite")
    store = Store.open(db_path, check_same_thread=False)
    content = ContentStore(store)
    app = create_app(
        store=store,
        content=content,
        secret=SECRET,
        limits=dict(LIMITS),
        gateway_id="ui-test",
        fixtures_dir=FIXTURES,
        now_iso=clock.iso,
        now_epoch=clock.epoch_s,
    )
    server, thread, port = boot(app)  # the lifespan admits the fixture bench
    sessions_store: SessionStore = app.state.ui_sessions
    yield SimpleNamespace(
        base=f"http://127.0.0.1:{port}",
        operations=app.state.ui_operations,
        sessions=sessions_store,
        content=content,
        store=store,
        db_path=db_path,
        admin=_session(
            sessions_store, principal="g4-browser-admin", scopes=ADMIN
        ),
        observe=_session(
            sessions_store, principal="g4-browser-observe", scopes=OBSERVE
        ),
    )
    stop(server, thread)
    store.close()


@pytest.fixture(scope="module")
def browser(served: SimpleNamespace) -> Iterator[Browser]:
    # Depends on served so the gateway (whose MCP pin sweep calls
    # asyncio.run) is composed BEFORE sync_playwright's driver leaves a
    # loop running in the main thread - the G2b note, made structural.
    with sync_playwright() as playwright:
        yield playwright.chromium.launch()


@pytest.fixture()
def page(browser: Browser) -> Iterator[Page]:
    context = browser.new_context()
    yield context.new_page()
    context.close()


def _identity(record: Any) -> Identity:
    """The seam Identity for a session record (ui.py's _session_identity
    rule), restated for in-test seam reads."""
    return Identity(
        principal=record.principal,
        audience=record.audience,
        scopes=record.scopes,
        expires_at=record.expires_at,
    )


def _open(page: Page, served: SimpleNamespace, record: Any, path: str) -> None:
    """Load a gateway page behind a session cookie."""
    context = page.context
    context.clear_cookies()
    context.add_cookies(
        [
            {
                "name": "bw_session",
                "value": record.session_id,
                "url": served.base,
            }
        ]
    )
    page.goto(f"{served.base}{path}", wait_until="networkidle")


def _store_rows(served: SimpleNamespace) -> list[tuple[str, str]]:
    """The store's change rows — the lane's own enumeration (the seam
    has none; G4-D2). Read-only SQL over the rig's database file."""
    connection = sqlite3.connect(f"file:{served.db_path}?mode=ro", uri=True)
    try:
        return list(
            connection.execute(
                "SELECT change_id, state FROM changes ORDER BY change_id"
            )
        )
    finally:
        connection.close()


def _dom_row_ids(page: Page) -> set[str]:
    """The change ids currently rendered in the admin region."""
    return set(
        page.eval_on_selector_all(
            "[data-bw-change-row]", "els => els.map(e => e.dataset.bwChangeId)"
        )
    )


def _submit_via_region(
    page: Page, served: SimpleNamespace, *, reason: str, kind: str = "trip_reset"
) -> str:
    """Fill the region's REAL form and click its REAL button; returns
    the newly filed change's id (the one row the DOM gained). Caller
    must already be on the bench page behind the admin session."""
    before = _dom_row_ids(page)
    page.select_option(f"#bw-change-kind-{BENCH_ID}", kind)
    page.fill(f"#bw-change-reason-{BENCH_ID}", reason)
    page.click('form[data-bw-change-submit] button[type="submit"]')
    expect(page.locator("[data-bw-change-row]")).to_have_count(len(before) + 1)
    new = _dom_row_ids(page) - before
    assert len(new) == 1, f"expected exactly one new row, got {sorted(new)}"
    return new.pop()


def _load_approval_via_form(
    page: Page, served: SimpleNamespace, change_id: str, ref: dict[str, str]
) -> None:
    """Paste the approval digest + ref into the REAL load form and click
    Load approval; the caller must already be on the change page."""
    page.fill("#bw-approval-sha", ref["sha256"])
    page.fill("#bw-approval-id", ref["id"])
    page.fill("#bw-approval-version", ref["version"])
    page.click('[data-bw-approval-load] button[type="submit"]')
    page.wait_for_selector("[data-bw-approval-facts]", state="attached")


def _region_form_fields(page: Page) -> dict[str, str]:
    """The submit form's live field values (the replay's snapshot)."""
    fields = page.eval_on_selector(
        "form[data-bw-change-submit]",
        """form => {
            const out = {};
            for (const el of form.elements) {
                if (el.name) out[el.name] = el.value;
            }
            return out;
        }""",
    )
    typed: dict[str, str] = {str(k): str(v) for k, v in fields.items()}
    assert typed.get("request_id"), "the form carries no §9 request id"
    return typed


def _seed_via_page_request(
    served: SimpleNamespace,
    page: Page,
    record: Any,
    *,
    reason: str,
) -> str:
    """File one change through the UI route with ``page.request`` (the
    context shares the session cookie) and return its id. The handler
    indexes the change into the session's view — a seam-level seed
    would be invisible to the index — while skipping the browser-form
    ceremony this lane's other arms prove."""
    bench = served.operations.bench_get(_identity(record), BENCH_ID)
    configuration = bench.get("configuration") or {}
    data: dict[str, str | float | bool] = {
        "request_id": "ui-" + uuid.uuid4().hex[:12],
        "kind": "trip_reset",
        "target_id": str(configuration.get("id", "")),
        "target_version": str(configuration.get("version", "")),
        "target_sha256": str(configuration.get("sha256", "")),
        "expected_generation": str(bench.get("generation", 0)),
        "reason": reason,
    }
    before = {row[0] for row in _store_rows(served)}
    response = page.request.post(
        f"{served.base}/ui/benches/{BENCH_ID}/changes",
        form=data,
        headers={"x-csrf-token": record.csrf_token, "origin": served.base},
    )
    assert response.status == 200, response.text()[:500]
    new = {row[0] for row in _store_rows(served)} - before
    assert len(new) == 1, f"expected exactly one new row, got {sorted(new)}"
    return new.pop()


# --- arm 1: the admin cycle through the real buttons ------------------


def test_admin_cycle_through_real_buttons(served: SimpleNamespace, page: Page) -> None:
    """An admin session submits the trip_reset change from the region's
    REAL form: the CSRF header rides htmx's configRequest listener
    (asserted on the wire), no 403 anywhere in the network log, the
    region re-renders in place with the change's row (proposed) and its
    review link, the review page renders the ten-field record, a reload
    lists the change, and the store holds exactly one row.

    Mutation A1 pins this arm: the rows loop removed from
    admin-region.j2 → the region never lists the change (RED captured)."""
    record = served.admin
    responses: list[Any] = []
    post_tokens: list[str | None] = []

    def _on_response(response: Any) -> None:
        responses.append(response)

    def _on_request(request: Any) -> None:
        if request.method == "POST":
            post_tokens.append(request.header_value("x-csrf-token"))

    page.on("response", _on_response)
    page.on("request", _on_request)

    _open(page, served, record, f"/ui/benches/{BENCH_ID}")
    assert (
        page.locator('meta[name="bw-csrf-token"]').get_attribute("content")
        == record.csrf_token
    ), "the shell did not deliver the session's CSRF token"
    region = page.locator("section[data-bw-admin]")
    assert region.count() == 1, "the bench page carries no administration region"
    form = page.locator("form[data-bw-change-submit]")
    assert form.count() == 1, "an admin session must be handed the live submit form"
    request_id = form.locator('input[name="request_id"]').input_value()
    assert re.fullmatch(r"ui-[0-9a-f]{12}", request_id), (
        f"the server-minted §9 id is not the ui-hex12 shape: {request_id!r}"
    )
    # The target prefills from the bench's own configuration ref (the
    # R5 convention) and the generation from bench_get.
    bench = served.operations.bench_get(_identity(record), BENCH_ID)
    configuration = bench.get("configuration") or {}
    assert form.locator('input[name="target_id"]').input_value() == str(
        configuration.get("id", "")
    )
    assert form.locator('input[name="target_version"]').input_value() == str(
        configuration.get("version", "")
    )
    assert form.locator('input[name="target_sha256"]').input_value() == str(
        configuration.get("sha256", "")
    )
    assert form.locator('input[name="expected_generation"]').input_value() == str(
        bench.get("generation", 0)
    )

    change_id = _submit_via_region(
        page, served, reason="browser lane: the admin cycle"
    )
    assert post_tokens, "no POST reached the wire"
    assert post_tokens[-1] == record.csrf_token, (
        "the submit POST carried no CSRF token on the wire"
    )
    assert [r for r in responses if r.status == 403] == [], (
        "a session-bearing POST was refused: "
        + "; ".join(
            f"{r.url} -> {r.status}" for r in responses if r.status == 403
        )
    )

    row = page.locator(f'[data-bw-change-row][data-bw-change-id="{change_id}"]')
    assert row.get_attribute("data-bw-change-state") == "proposed"
    assert row.locator(f'a[href="/ui/changes/{change_id}"]').count() == 1, (
        "the region row carries no review link"
    )
    assert row.locator("[data-bw-two-phase-note]").count() == 1, (
        "the proposed row does not carry the independent-approval statement"
    )
    assert page.locator("[data-bw-bench-facts]").count() == 1, (
        "the bench page navigated: the submit outcome must swap in place"
    )
    assert page.url == f"{served.base}/ui/benches/{BENCH_ID}"

    page.goto(
        f"{served.base}/ui/changes/{change_id}", wait_until="networkidle"
    )
    record_section = page.locator("[data-bw-change-record]")
    assert record_section.count() == 1, "the review page renders no record"
    for hook in (
        "data-bw-change-bench-id",
        "data-bw-change-kind",
        "data-bw-change-state",
        "data-bw-change-target",
        "data-bw-change-generation",
        "data-bw-change-reason",
        "data-bw-change-reasons",
        "data-bw-change-created_at",
        "data-bw-change-updated_at",
    ):
        assert page.locator(f"[{hook}]").count() == 1, (
            f"the ten-field record is missing its {hook} field"
        )
    assert page.locator("[data-bw-change-page]").get_attribute(
        "data-bw-change-id"
    ) == change_id
    assert ">trip_reset<" in page.content()
    assert "browser lane: the admin cycle" in page.content()

    _open(page, served, record, f"/ui/benches/{BENCH_ID}")
    assert page.locator(
        f'[data-bw-change-row][data-bw-change-id="{change_id}"]'
    ).count() == 1, "the region does not list the change after a reload"

    states = dict(_store_rows(served))
    assert states[change_id] == "proposed", (
        f"the store does not hold the submitted change as proposed:"
        f" {states.get(change_id)!r}"
    )
    filed = [row for row in _store_rows(served) if row[0] == change_id]
    assert len(filed) == 1, f"the change id is not unique in the store: {filed}"


# --- arm 2: the approval workspace -------------------------------------


def test_approval_load_displays_the_approver_and_self_approval_is_not_offered(
    served: SimpleNamespace, page: Page
) -> None:
    """Paste the approval digest + ref into the REAL load form: the
    approver principal DISPLAYS with the binding facts and the live
    apply form is offered (a binding independent approval). A
    self-approval displays its approver while the apply control renders
    DISABLED under §C.2 ``no-authority`` with the independence note —
    and no live apply form exists anywhere in the workspace.

    Mutation A2 pins this arm: the self-approval branch removed from
    ``AdminRoutes._apply_control_html`` (ui_admin.py) → the live form is
    offered for a self-approval (RED captured)."""
    record = served.admin

    # A binding INDEPENDENT approval: the approver displays, apply offered.
    _open(page, served, record, f"/ui/benches/{BENCH_ID}")
    independent = _submit_via_region(
        page, served, reason="browser lane: the independent load"
    )
    ref, token = put_approval(
        served.content, change_id=independent, approver="approver-x"
    )
    assert token
    page.goto(
        f"{served.base}/ui/changes/{independent}", wait_until="networkidle"
    )
    assert page.locator("[data-bw-approval-load]").count() == 1, (
        "the workspace does not open on the approval-load form"
    )
    _load_approval_via_form(page, served, independent, ref)
    facts = page.locator("[data-bw-approval-facts]")
    assert facts.get_attribute("data-bw-approval-binds") == "true"
    approver = page.locator('[data-bw-approval-approver="approver-x"]')
    assert approver.count() == 1, "the approver principal does not display"
    assert approver.inner_text().strip() == "approver-x"
    assert page.locator(
        f'[data-bw-approval-change="{independent}"]'
    ).count() == 1, "the loaded approval does not name the bound change"
    assert page.locator(
        f'a[href="/ui/documents/{ref["sha256"]}"]'
    ).count() == 1, "the approval facts carry no link to the stored document"
    apply_form = page.locator(
        f'form[data-bw-apply-control][hx-post="/ui/changes/{independent}/apply"]'
    )
    assert apply_form.count() == 1, "the live apply form is not offered"
    assert apply_form.locator(
        'input[name="approver_token"][type="password"][autocomplete="off"]'
    ).count() == 1, "the token field is not the never-echo password shape"

    # A SELF-approval: the approver displays, apply NOT offered.
    _open(page, served, record, f"/ui/benches/{BENCH_ID}")
    own = _submit_via_region(page, served, reason="browser lane: the self load")
    own_ref, _own_token = put_approval(
        served.content, change_id=own, approver=record.principal
    )
    page.goto(f"{served.base}/ui/changes/{own}", wait_until="networkidle")
    _load_approval_via_form(page, served, own, own_ref)
    own_facts = page.locator("[data-bw-approval-facts]")
    assert own_facts.get_attribute("data-bw-approval-binds") == "true"
    own_approver = page.locator(f'[data-bw-approval-approver="{record.principal}"]')
    assert own_approver.count() == 1, "the self-approval's approver does not display"
    disabled = page.locator(
        '[data-bw-change-workspace]'
        ' button[disabled][data-bw-disabled-reason="no-authority"]'
    )
    assert disabled.count() == 1, "the self-approval apply control is not disabled"
    note = page.locator("[data-bw-apply-note]")
    assert note.count() == 1
    assert "Independent approval" in note.inner_text(), (
        "the independence note is absent from the disabled shape"
    )
    assert page.locator(
        f'form[hx-post="/ui/changes/{own}/apply"]'
    ).count() == 0, "a live apply form is offered for a self-approval"


# --- arm 3: the apply flow through real buttons + the §9 replay --------


def test_apply_with_an_independent_approval_and_no_token_echo(
    served: SimpleNamespace, page: Page
) -> None:
    """The apply flow end-to-end through real buttons: a binding
    independent approval loads, the approver's detached token applies,
    the applied shape renders the generation increment (US9), the store
    holds the applied record — and the token appears in no response
    byte (the apply response, the change page, the bench page)."""
    record = served.admin
    _open(page, served, record, f"/ui/benches/{BENCH_ID}")
    change_id = _submit_via_region(
        page, served, reason="browser lane: the apply"
    )
    ref, token = put_approval(
        served.content, change_id=change_id, approver="approver-x"
    )
    page.goto(
        f"{served.base}/ui/changes/{change_id}", wait_until="networkidle"
    )
    _load_approval_via_form(page, served, change_id, ref)

    with page.expect_response(
        lambda r: r.url.endswith(f"/changes/{change_id}/apply")
    ) as apply_info:
        page.fill("#bw-approver-token", token)
        page.click('[data-bw-apply-control] button[type="submit"]')
    apply_response = apply_info.value
    assert apply_response.status == 200, apply_response.text()[:500]
    assert apply_response.request.header_value("x-csrf-token") == record.csrf_token, (
        "the apply POST carried no CSRF token on the wire"
    )
    page.wait_for_selector('[data-bw-change-applied="true"]', state="attached")
    assert "Generation 1 → 2" in page.content(), (
        "the applied shape does not render the generation increment"
    )
    assert token not in apply_response.text(), (
        "the approver token is echoed in the apply response"
    )
    for path in (f"/ui/changes/{change_id}", f"/ui/benches/{BENCH_ID}"):
        page.goto(f"{served.base}{path}", wait_until="networkidle")
        assert token not in page.content(), (
            f"the approver token appears on {path}"
        )
    states = dict(_store_rows(served))
    assert states[change_id] == "applied"


def test_the_section9_replay_of_the_carried_form_returns_the_original_change(
    served: SimpleNamespace, page: Page, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The §9 replay in a real browser: land a change from the region's
    form, re-POST the ORIGINAL form bytes through htmx's own pipeline
    under an induced no-response (the G2 §7-F posture: an in-process
    adapter cannot honestly fail to answer) — the §C.3 no-response row
    draws with the carried resubmit form (the §9 id and the staged
    fields hidden); restoring the seam and clicking the carried button
    returns the ORIGINAL change: one row, the same id.

    Mutation A3 pins this arm: the submit handler's no-response path
    removed (ui_admin.py ``submit_change``) → the replay POST surfaces a
    bare 500 and the carried form never renders (RED captured)."""
    record = served.admin
    operations: Operations = served.operations

    _open(page, served, record, f"/ui/benches/{BENCH_ID}")
    # Snapshot the form bytes BEFORE the click: the replay must carry the
    # §9 id that LANDED (the re-rendered region mints a fresh id — replaying
    # THAT would file a second change, honestly refused by nothing).
    page.fill(f"#bw-change-reason-{BENCH_ID}", "browser lane: the replay original")
    original_fields = _region_form_fields(page)
    assert original_fields["request_id"], "the landing form carries no §9 id"
    dom_before = _dom_row_ids(page)
    page.click('form[data-bw-change-submit] button[type="submit"]')
    expect(page.locator("[data-bw-change-row]")).to_have_count(len(dom_before) + 1)
    new_ids = _dom_row_ids(page) - dom_before
    assert len(new_ids) == 1
    original_id = new_ids.pop()
    rows_before = _store_rows(served)

    def _crash(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("induced: no interface answer")

    monkeypatch.setattr(operations, "change_submit", _crash)
    replay_fields = dict(original_fields)
    # Re-POST the original form bytes through htmx's own pipeline (the
    # double-click / browser-back shape: the same §9 id and body).
    # The CSRF header rides the configRequest listener exactly as the
    # real form's POST does.
    page.evaluate(
        """async ({url, fields}) => {
            await htmx.ajax('POST', url, {
                target: '[data-bw-admin]', swap: 'outerHTML',
                values: fields,
            });
        }""",
        {
            "url": f"{served.base}/ui/benches/{BENCH_ID}/changes",
            "fields": replay_fields,
        },
    )
    refusal = page.locator('[data-bw-refusal-code="no-response"]')
    assert refusal.count() == 1, (
        "the no-response row did not draw after the induced transport death"
    )
    assert page.locator('[data-bw-sent-status="UNKNOWN"]').count() == 1
    carried = page.locator("form[data-bw-change-resubmit]")
    assert carried.count() == 1, (
        "the refusal body carries no resubmit form (the reconcile is not"
        " executable from the surface it renders on)"
    )
    hidden_names = carried.locator("input[type=hidden]").evaluate_all(
        "els => els.map(e => e.name)"
    )
    hidden_values = carried.locator("input[type=hidden]").evaluate_all(
        "els => els.map(e => e.value)"
    )
    carried_fields = dict(zip(hidden_names, hidden_values, strict=True))
    assert carried_fields.get("request_id") == original_fields["request_id"], (
        f"the carried form does not carry the original §9 id:"
        f" {carried_fields.get('request_id')!r}"
    )
    assert carried_fields.get("reason") == "browser lane: the replay original"
    assert carried_fields.get("kind") == "trip_reset"

    monkeypatch.undo()
    page.click('[data-bw-change-resubmit] button[type="submit"]')
    expect(page.locator("[data-bw-change-row]")).not_to_have_count(0)
    # §9: the identical form returns the ORIGINAL change — one row.
    rows_after = _store_rows(served)
    assert rows_after == rows_before, (
        f"the carried-form resubmit filed a second change:"
        f" {rows_after} != {rows_before}"
    )
    assert page.locator(
        f'[data-bw-change-row][data-bw-change-id="{original_id}"]'
    ).count() == 1, "the resubmitted region does not name the original change"


def test_the_carried_reconcile_swaps_in_place(
    served: SimpleNamespace, page: Page, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The in-place swap discipline for the carried reconcile (the G3a
    rule: an outcome must swap where its section was — never destroy
    the document). After the carried form's successful resubmit, the
    bench page's own facts must still be in the DOM."""
    record = served.admin
    operations: Operations = served.operations

    _open(page, served, record, f"/ui/benches/{BENCH_ID}")
    _submit_via_region(page, served, reason="browser lane: the swap duty")
    original_fields = _region_form_fields(page)

    def _crash(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("induced: no interface answer")

    monkeypatch.setattr(operations, "change_submit", _crash)
    page.evaluate(
        """async ({url, fields}) => {
            await htmx.ajax('POST', url, {
                target: '[data-bw-admin]', swap: 'outerHTML',
                values: fields,
            });
        }""",
        {
            "url": f"{served.base}/ui/benches/{BENCH_ID}/changes",
            "fields": original_fields,
        },
    )
    assert page.locator("form[data-bw-change-resubmit]").count() == 1
    monkeypatch.undo()
    page.click('[data-bw-change-resubmit] button[type="submit"]')
    expect(page.locator("[data-bw-change-row]")).not_to_have_count(0)
    assert page.locator("[data-bw-bench-facts]").count() == 1, (
        "the successful resubmit swapped the entire bench section: the"
        " carried reconcile destroyed the document it recovered"
    )


# --- arm 4: GW-72 — the persistent alert until reconciled --------------


def test_gw72_failed_apply_renders_the_persistent_alert_until_acknowledged(
    served: SimpleNamespace, page: Page
) -> None:
    """A failed apply (the seam's decided ``unauthenticated`` refusal on
    a garbage token) renders the §B.1 critical alert on the bench
    region — ``reasons[0]`` verbatim, the reconciliation route, the
    acknowledge affordance — persistently across reloads; the proposed
    row's apply affordance renders disabled under ``no-authority``
    naming the blocking change; the region's REAL acknowledge button
    clears the alert and lifts the disable; submit stays armed.

    Mutation A4 pins this arm: ``_alert_markup`` neutralized (returns
    None) in ui_admin.py → the alert never renders (RED captured)."""
    record = served.admin

    _open(page, served, record, f"/ui/benches/{BENCH_ID}")
    failed = _submit_via_region(
        page, served, reason="browser lane: the failed apply"
    )
    proposed = _submit_via_region(
        page, served, reason="browser lane: the correction"
    )
    generation = int(
        served.operations.bench_get(_identity(record), BENCH_ID)["generation"]
    )
    ref, _token = put_approval(
        served.content,
        change_id=failed,
        approver="approver-x",
        expected_generation=generation,
    )

    page.goto(f"{served.base}/ui/changes/{failed}", wait_until="networkidle")
    _load_approval_via_form(page, served, failed, ref)
    with page.expect_response(
        lambda r: r.url.endswith(f"/changes/{failed}/apply")
    ) as apply_info:
        page.fill("#bw-approver-token", "not-a-token")
        page.click('[data-bw-apply-control] button[type="submit"]')
    assert apply_info.value.status == 401, (
        apply_info.value.text()[:500]
    )
    refusal = page.locator('[data-bw-refusal-code="unauthenticated"]')
    assert refusal.count() == 1, "the decided refusal row did not draw"
    states = dict(_store_rows(served))
    assert states[failed] == "failed", "the seam did not record the failure"

    _open(page, served, record, f"/ui/benches/{BENCH_ID}")
    alert = page.locator(
        '[data-bw-admin] aside.bw-alert-bubble[data-severity="critical"]'
    )
    assert alert.count() == 1, "the critical alert did not render on the region"
    expected_reason = served.operations.change_get(
        _identity(record), failed
    )["reasons"][0]
    assert expected_reason in alert.inner_text(), (
        "the alert does not carry reasons[0] verbatim"
    )
    assert f"Change {failed} failed" in alert.inner_text()
    assert "never re-apply" in alert.inner_text(), (
        "the alert does not state the reconciliation route"
    )
    acknowledge = page.locator("form[data-bw-change-acknowledge]")
    assert acknowledge.count() == 1, "the region carries no acknowledge affordance"
    assert (
        page.locator(f'[hx-post="/ui/changes/{failed}/acknowledgements"]').count()
        == 1
    ), "the acknowledge form does not POST the failed change's route"

    # The proposed row's apply affordance is inhibited, naming the blocker.
    row = page.locator(f'[data-bw-change-row][data-bw-change-id="{proposed}"]')
    assert row.locator("[data-bw-change-inhibited]").count() == 1, (
        "the proposed row renders no disabled apply affordance under inhibition"
    )
    assert row.locator(
        '[data-bw-change-inhibited] button[disabled]'
        '[data-bw-disabled-reason="no-authority"]'
    ).count() == 1
    assert failed in row.locator("[data-bw-inhibit-note]").inner_text(), (
        "the inhibit note does not name the blocking change"
    )
    # Submit stays armed (filing a new change is the reconciliation route).
    assert page.locator("form[data-bw-change-submit]").count() == 1

    # The disable shows in the proposed change's workspace too.
    page.goto(
        f"{served.base}/ui/changes/{proposed}", wait_until="networkidle"
    )
    assert page.locator("[data-bw-change-inhibited]").count() == 1, (
        "the proposed change's workspace renders no inhibited apply control"
    )

    # The alert persists across reloads (server-side session state).
    _open(page, served, record, f"/ui/benches/{BENCH_ID}")
    assert page.locator(
        '[data-bw-admin] aside.bw-alert-bubble[data-severity="critical"]'
    ).count() == 1, "the alert did not persist across a reload"

    # Acknowledge through the region's REAL button: the alert clears and
    # the disable lifts.
    page.click("form[data-bw-change-acknowledge] button[type=submit]")
    page.wait_for_selector(
        '[data-bw-admin] aside.bw-alert-bubble[data-severity="critical"]',
        state="detached",
    )
    assert page.locator(
        f'[data-bw-change-row][data-bw-change-id="{proposed}"]'
        " [data-bw-change-inhibited]"
    ).count() == 0, "the acknowledge did not lift the disable"
    _open(page, served, record, f"/ui/benches/{BENCH_ID}")
    assert page.locator(
        '[data-bw-admin] aside.bw-alert-bubble[data-severity="critical"]'
    ).count() == 0, "the acknowledged alert came back on a fresh render"
    assert page.locator(
        f'[data-bw-change-row][data-bw-change-id="{proposed}"]'
        " [data-bw-change-inhibited]"
    ).count() == 0, "the disable came back on a fresh render"
    # The gateway record never changed (the acknowledgement is per-session).
    states = dict(_store_rows(served))
    assert states[failed] == "failed" and states[proposed] == "proposed"


# --- arm 5: axe on the shapes the census cannot render -----------------


def test_planted_violation_must_red_in_this_context(
    served: SimpleNamespace, page: Page
) -> None:
    """The G2 census's control, re-proven in THIS served context: a
    button stripped of its accessible name MUST produce an axe
    violation — a clean run against the planted page means the
    measurement is broken, not the pages."""
    _open(page, served, served.admin, "/ui/")
    page.set_content("<html><body><button></button></body></html>")
    from axe_playwright_python.sync_playwright import Axe  # type: ignore[import-untyped]

    results = Axe().run(
        page,
        options={
            "runOnly": {"type": "tag", "values": WCAG_22_AA_TAGS},
            "resultTypes": ["violations"],
        },
    )
    assert results.violations_count > 0, (
        "the planted unnamed button produced no violation — the axe "
        "measurement is broken in this context"
    )


@pytest.mark.parametrize(
    "shape",
    [
        "admin-bench",
        "observe-bench",
        "change-independent",        "change-failed",
    ],
)
def test_axe_zero_violations_on_the_admin_shapes(
    served: SimpleNamespace, page: Page, shape: str
) -> None:
    """axe at WCAG 2.2 AA, zero violations, on the shapes the G2 census
    cannot render (the census runs observe-scoped pages only; the
    change pages are new): the admin-scoped bench page (the live admin
    region), the observe bench page carrying the new region, the change
    page with a loaded independent approval (the fullest live-form
    workspace), and the failed change page with the §B.1 critical
    alert."""
    record = served.admin
    if shape in ("change-independent", "change-failed"):
        # The context needs the session cookie before the seeded POST:
        # page.request shares the context's cookie jar, and _open sets it.
        _open(page, served, record, f"/ui/benches/{BENCH_ID}")
        change_id = _seed_via_page_request(
            served,
            page,
            record,
            reason=f"browser lane: axe {shape}",
        )
        page.goto(
            f"{served.base}/ui/changes/{change_id}", wait_until="networkidle"
        )
        if shape == "change-independent":
            gen = int(
                served.operations.change_get(_identity(record), change_id)[
                    "expected_generation"
                ]
            )
            ref, _token = put_approval(
                served.content,
                change_id=change_id,
                approver="approver-x",
                expected_generation=gen,
            )
            _load_approval_via_form(page, served, change_id, ref)
        else:
            gen = int(
                served.operations.change_get(_identity(record), change_id)[
                    "expected_generation"
                ]
            )
            ref, _token = put_approval(
                served.content,
                change_id=change_id,
                approver="approver-x",
                expected_generation=gen,
            )
            page.fill("#bw-approval-sha", ref["sha256"])
            page.fill("#bw-approval-id", ref["id"])
            page.fill("#bw-approval-version", ref["version"])
            page.click('[data-bw-approval-load] button[type="submit"]')
            page.wait_for_selector("[data-bw-approval-facts]", state="attached")
            page.fill("#bw-approver-token", "not-a-token")
            page.click('[data-bw-apply-control] button[type="submit"]')
            page.wait_for_selector(
                '[data-bw-refusal-code="unauthenticated"]', state="attached"
            )

    if shape == "admin-bench":
        _open(page, served, record, f"/ui/benches/{BENCH_ID}")
        assert page.locator("form[data-bw-change-submit]").count() == 1
    elif shape == "observe-bench":
        _open(page, served, served.observe, f"/ui/benches/{BENCH_ID}")
        assert page.locator(
            '[data-bw-disabled-reason="no-authority"]'
        ).count() >= 1
    elif shape.startswith("change-"):
        assert page.locator("[data-bw-change-page]").count() == 1

    from axe_playwright_python.sync_playwright import Axe

    results = Axe().run(
        page,
        options={
            "runOnly": {"type": "tag", "values": WCAG_22_AA_TAGS},
            "resultTypes": ["violations"],
        },
    )
    assert results.violations_count == 0, results.generate_snapshot()
