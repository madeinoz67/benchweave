"""The G3b browser acceptance lane (issue #304): a real browser drives
the staging → confirm → replay → cancel surface of the runs control
panel — the seams a REST-level suite cannot see.

The lane is a CHAIN, not a cycle: G3b's binding carries its own §9
request id, and the seam's replay rule keys on it, so the module shares
one binding and one started run on purpose — the confirm arm starts the
module's first (and only) run; the cancel arm drives it; the replay arm
restages the same binding and proves the §9 replay in the real browser.
Each run-bearing arm re-enters the cycle through real buttons (stage,
re-stage, arm, confirm) exactly as an operator would.

One disclosed gap the lane works around (found on orientation, not a
defect of an arm): the staging panel renders the check verdict
(data-bw-check-state) and the check gate, but NO check button — the
design record §2.4 specifies the check as a route (POST run-checks)
that records into the staging record; a browser operator cannot
initiate the preflight from the panel. The arms drive the check through
the page's own htmx pipeline (htmx.ajax POST — the same configRequest
CSRF stamping every button click rides), and the gap is reported to the
owner with this lane.

The served app's clock is the mutable cell the other UI suites use; no
arm advances it (nothing here tests expiry). The cancel arm pins its
during-live-window render on an INDUCED live window (a counter-based
run_get wrap reporting the run's own accepted state — labelled
induction, the G2 §7-F posture, FOLD-4's exact lesson: the render must
not be decided by the sim's speed). Every arm that reaches the seam
asserts the CSRF header rode the configRequest listener and no response
is a 403.

Serialized in the browser marker (CI's browser job). The bench is
shared module-wide; the chain's lease is taken once (the confirm arm)
and released by the replay arm's end (the seam admits one controlling
lease per bench, so the second cycle runs under the first's — the REST
repro's note).
"""

from __future__ import annotations

import contextlib
import hashlib
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from g3b_lattice import author_g3b_lattice
from playwright.sync_api import (
    Browser,
    Page,
    Request,
    Response,
    expect,
    sync_playwright,
)
from ui_gateway_support import LIMITS, NOW_EPOCH, SECRET, boot, stop

from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.sessions import SessionStore
from benchweave.state.store import Store

pytestmark = pytest.mark.browser

BENCH_ID = "sim-bench"
CHAIN_REQUEST_ID = "req-g3b-energise"  # the lattice binding's own §9 id

CONTROL = frozenset({"stg:observe", "stg:control"})

WCAG_22_AA_TAGS = ["wcag2a", "wcag2aa", "wcag22a", "wcag22aa"]

ARM_URL = f"/ui/benches/{BENCH_ID}/staging/arm"
CHECK_URL = f"/ui/benches/{BENCH_ID}/run-checks"


class _Clock:
    """One mutable epoch cell; the other UI suites' exact pattern."""

    def __init__(self) -> None:
        self.epoch = NOW_EPOCH

    def epoch_s(self) -> int:
        return self.epoch

    def iso(self) -> str:
        return (
            datetime.fromtimestamp(self.epoch, tz=UTC)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def advance(self, seconds: int) -> None:
        self.epoch += seconds


@pytest.fixture(scope="module")
def served(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SimpleNamespace]:
    """One composed gateway on the energy-sourcing lattice (manual mode,
    the enable step's ``enabled: true``), a real loopback port, its
    clock mutable. Same discipline as the G3a lane: a real store, the
    fixture bench admitted at lifespan, one module-scoped chromium. The
    control session (3600 s TTL) is minted at setup."""
    clock = _Clock()
    data_dir = tmp_path_factory.mktemp("g3b-browser")
    lattice_dir, binding_sha = author_g3b_lattice(data_dir, request_id=CHAIN_REQUEST_ID)
    store = Store.open(
        str(data_dir / "state-g3b-browser.sqlite"), check_same_thread=False
    )
    app = create_app(
        store=store,
        content=ContentStore(store),
        secret=SECRET,
        limits=dict(LIMITS),
        gateway_id="ui-test",
        fixtures_dir=lattice_dir,
        now_iso=clock.iso,
        now_epoch=clock.epoch_s,
    )
    server, thread, port = boot(app)  # the lifespan admits the fixture bench
    sessions_store: SessionStore = app.state.ui_sessions
    code = sessions_store.mint_login_code(
        Identity(
            principal="g3b-browser-control",
            audience="stg",
            scopes=CONTROL,
            expires_at=NOW_EPOCH + 12 * 3600,
        ),
        ttl_seconds=3600,
    )
    control = sessions_store.exchange(code)
    rig = SimpleNamespace(
        base=f"http://127.0.0.1:{port}",
        clock=clock,
        operations=app.state.ui_operations,
        sessions=sessions_store,
        control=control,
        store=store,
        lattice_dir=lattice_dir,
        binding_sha=binding_sha,
        chain_run_id=None,
    )
    yield rig
    view = sessions_store.held_lease(control.session_id, BENCH_ID)
    if view is not None:
        # Module-end safety net: whatever lease the chain left live (a
        # mid-chain failure) is released as its holder, so one red arm
        # cannot wedge the module's teardown. The replay arm releases on
        # the happy path.
        with contextlib.suppress(Exception):
            app.state.ui_operations.lease_release(
                _session_identity(control),
                view.lease_id,
                "g3b-browser-teardown",
                "test teardown release",
            )
        sessions_store.clear_held_lease(control.session_id, BENCH_ID)
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


def _session_identity(record: Any) -> Identity:
    """The seam Identity for a session record (ui.py's _session_identity
    rule), restated for teardown and poll calls that act as the
    session."""
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


def _wire(page: Page) -> tuple[list[str | None], list[Response]]:
    """Capture every POST's CSRF header and every response, for the
    wire assertions (the CSRF header rode the configRequest listener;
    no response is a 403)."""
    post_tokens: list[str | None] = []
    responses: list[Response] = []

    def _on_request(request: Request) -> None:
        if request.method == "POST":
            post_tokens.append(request.header_value("x-csrf-token"))

    def _on_response(response: Response) -> None:
        responses.append(response)

    page.on("request", _on_request)
    page.on("response", _on_response)
    return post_tokens, responses


def _assert_wire(post_tokens: list[str | None], responses: list[Response]) -> None:
    """Every POST carried the token; no response is a 403 (a session
    with the meta-delivered token must sail through the CsrfGuard)."""
    assert post_tokens, "no POST left the page"
    assert all(post_tokens), f"a POST carried no CSRF token: {post_tokens}"
    refused = [r for r in responses if r.status == 403]
    assert refused == [], (
        "a session-bearing POST was refused: "
        + "; ".join(f"{r.url} -> {r.status}" for r in refused)
    )


def _htmx_check(page: Page, served: SimpleNamespace) -> None:
    """The preflight through the page's own htmx pipeline (the configRequest
    CSRF stamp rides exactly as it does for button clicks). The panel
    renders no check button — the disclosed gap in this module's
    docstring — so the operator-facing POST this arm drives is the page's
    own htmx request."""
    page.evaluate(
        """async (url) => {
            await htmx.ajax('POST', url, {
                target: '[data-bw-controls]', swap: 'outerHTML',
            });
        }""",
        f"{served.base}{CHECK_URL}",
    )


def _wait_fresh_section(page: Page) -> None:
    """Wait for the controls section's own swap: the pre-click section
    was marked stale, so a section without the mark is the response's
    (the G3a stale-marker discipline — a row that pre-exists the click
    must not satisfy the arms' post-click waits)."""
    page.wait_for_function(
        "() => { const s = document.querySelector('[data-bw-controls]');"
        " return s && s.__staleSection === undefined; }"
    )


def _mark_stale_section(page: Page) -> None:
    page.eval_on_selector(
        "[data-bw-controls]", "el => { el.__staleSection = true; }"
    )


def _click_swap(page: Page, selector: str) -> None:
    """Click a panel control and wait for the section's own swap."""
    _mark_stale_section(page)
    page.click(selector)
    _wait_fresh_section(page)


def _stage_via_form(
    page: Page, served: SimpleNamespace, sha: str, *, staged: bool
) -> None:
    """Stage (or re-stage) a binding through the panel's REAL form: fill
    the digest input, click the submit button, wait for the section's
    own swap (the staged row may already be attached from an earlier
    cycle). ``staged`` selects the restage form (the staged branch
    renders it) vs the first-stage form."""
    if staged:
        page.fill('[data-bw-restage-control] input[name="binding_sha256"]', sha)
        _click_swap(page, '[data-bw-restage-control] button[type="submit"]')
    else:
        page.fill('[data-bw-stage-control] input[name="binding_sha256"]', sha)
        _click_swap(page, '[data-bw-stage-control] button[type="submit"]')
    page.wait_for_selector('[data-bw-staged="true"]', state="attached")


def _cycle_to_armed(
    page: Page, served: SimpleNamespace, sha: str, *, staged: bool
) -> None:
    """Re-stage, check, arm — the cycle every run-bearing arm re-enters
    through the panel's own controls."""
    _stage_via_form(page, served, sha, staged=staged)
    assert page.locator(
        '[data-bw-start-control] button[disabled]'
        '[data-bw-disabled-reason="invalid-staged-input"]'
    ).count() == 1, "a fresh stage must render the check-gated start control"
    _htmx_check(page, served)
    expect(
        page.locator('[data-bw-check-state="valid"]')
    ).to_be_attached()
    _click_swap(page, '[data-bw-arm-control] button[type="submit"]')
    page.wait_for_selector('[data-bw-confirm="armed"]', state="attached")


def _poll_terminal(served: SimpleNamespace, run_id: str, deadline_s: float = 60.0) -> None:
    """Drain the sim's settle deterministically: poll the seam until the
    run reports terminal (the REST lane's exact discipline — the settle
    is genuinely asynchronous, so the arm waits on the run's own report,
    never on a wall-clock guess)."""
    operations = served.operations
    identity = _session_identity(served.control)
    start = time.monotonic()
    while True:
        current = operations.run_get(identity, run_id)
        if current["state"] == "terminal":
            return
        assert time.monotonic() - start < deadline_s, current
        time.sleep(0.2)


def _lattice_procedure_sha(served: SimpleNamespace) -> str:
    """The rig lattice's procedure document digest — the STORED
    non-binding document the unreadable-chain arm stages by content
    digest (FOLD-1's repro)."""
    return hashlib.sha256(
        (served.lattice_dir / "procedure-voltage-check.json").read_bytes()
    ).hexdigest()


# --- the chain's first arm: staging and the check gate (FOLD-2) --------


def test_staging_cycle_renders_staged_and_the_check_gate_opens(
    served: SimpleNamespace, page: Page
) -> None:
    """Stage the lattice's binding through the REAL form: the staged row
    renders with the binding's own §9 request id; before any preflight
    the start control is the disabled invalid-staged-input shape (the
    check gate), and once the check has returned the verdict renders and
    the gate opens (the energy class's start path advances to the arm
    control)."""
    record = served.control
    post_tokens, responses = _wire(page)
    _open(page, served, record, f"/ui/benches/{BENCH_ID}")
    assert page.locator("[data-bw-staging]").count() == 1
    assert page.locator("[data-bw-staging-none]").count() == 1

    _stage_via_form(page, served, served.binding_sha, staged=False)
    staged_row = page.locator('[data-bw-staged="true"]')
    expect(staged_row).to_be_attached()
    assert page.locator("[data-bw-staged-sha]").inner_text() == served.binding_sha, (
        "the staged row does not name the staged digest"
    )
    assert page.locator("[data-bw-staged-request-id]").inner_text() == CHAIN_REQUEST_ID, (
        "the staged row does not name the binding's own §9 request id"
    )
    # the check gate, before any preflight
    assert page.locator("[data-bw-check-none]").count() == 1
    assert page.locator(
        '[data-bw-start-control] button[disabled]'
        '[data-bw-disabled-reason="invalid-staged-input"]'
    ).count() == 1, "the unchecked staged set must render the gated start control"
    assert page.locator("form[data-bw-start-control]").count() == 0, (
        "the unchecked staged set must not be handed a live start form"
    )
    assert page.locator("[data-bw-bench-facts]").count() == 1, (
        "the bench page navigated: the stage outcome must swap in place"
    )
    assert page.url == f"{served.base}/ui/benches/{BENCH_ID}"

    _htmx_check(page, served)
    verdict = page.locator('[data-bw-check-state="valid"]')
    expect(verdict).to_be_attached()
    # the gate opened: the gated shape is gone, the energy start path
    # advances to the arm control
    assert page.locator(
        '[data-bw-start-control] button[disabled]'
        '[data-bw-disabled-reason="invalid-staged-input"]'
    ).count() == 0, "the start control is still gated after the check returned"
    assert page.locator("form[data-bw-arm-control]").count() == 1, (
        "the checked energy-sourcing set must render the arm control"
    )
    assert page.locator("[data-bw-bench-facts]").count() == 1

    _assert_wire(post_tokens, responses)


def test_axe_zero_violations_on_the_staged_and_armed_panel(
    served: SimpleNamespace, page: Page
) -> None:
    """The G2 census and the G3a arm run axe on other shapes; this arm
    covers the shape neither can render — the staged set ARMED (the
    confirm-action pattern with its composed armed text) — at WCAG 2.2
    AA: zero violations."""
    record = served.control
    _open(page, served, record, f"/ui/benches/{BENCH_ID}")
    _cycle_to_armed(page, served, served.binding_sha, staged=True)

    from axe_playwright_python.sync_playwright import Axe  # type: ignore[import-untyped]

    results = Axe().run(
        page,
        options={
            "runOnly": {"type": "tag", "values": WCAG_22_AA_TAGS},
            "resultTypes": ["violations"],
        },
    )
    assert results.violations_count == 0, results.generate_snapshot()


def test_confirm_flow_starts_one_run_in_place_no_403(
    served: SimpleNamespace, page: Page
) -> None:
    """The energy-sourcing confirm (§E.1) through real buttons: the arm
    composes the confirm from the documents (FOLD-5's armed text — the
    exact values and mapped target of the lattice's enable step), the
    confirm POST carries the CSRF token and starts exactly ONE run, and
    the run-started row renders in place — not a page, not a 403."""
    record = served.control
    post_tokens, responses = _wire(page)
    _open(page, served, record, f"/ui/benches/{BENCH_ID}")

    # the manual-mode bench needs the controlling lease (A03) — through
    # the REAL take button, like the G3a cycle
    page.fill(f"#bw-lease-duration-{BENCH_ID}", "600000")
    page.click('[data-bw-lease-take] button[type="submit"]')
    page.wait_for_selector('[data-bw-lease-state="held"]', state="attached")

    _cycle_to_armed(page, served, served.binding_sha, staged=True)
    armed_text = page.locator("[data-bw-armed-text]").inner_text()
    assert "5 V" in armed_text, (
        f"the armed text does not carry the enable's configure value: {armed_text!r}"
    )
    assert "psu ch1" in armed_text, (
        f"the armed text does not carry the enable's mapped target: {armed_text!r}"
    )
    assert "Confirm: Start run" in page.locator(
        '[data-bw-confirm="armed"]'
    ).inner_text(), "the armed confirm does not offer the confirm action"

    _click_swap(page, '[data-bw-confirm-action="true"]')
    started = page.locator("[data-bw-run-started]")
    expect(started).to_be_attached()
    run_id = started.get_attribute("data-bw-run-started")
    assert run_id, "the started row does not name the run id"
    assert started.get_attribute("data-bw-replay") is None, (
        "the FIRST start must not render as a replay"
    )
    assert "accepted" in started.inner_text()
    assert page.locator("[data-bw-bench-facts]").count() == 1, (
        "the bench page navigated: the confirm outcome must swap in place"
    )
    assert page.url == f"{served.base}/ui/benches/{BENCH_ID}"

    runs = served.store.list_run_states(BENCH_ID)
    assert len(runs) == 1, runs
    served.chain_run_id = str(run_id)

    _assert_wire(post_tokens, responses)


def test_cancel_during_a_live_run_marks_the_page_in_place(
    served: SimpleNamespace, page: Page
) -> None:
    """GW-55: during a live run the run page's cancel region is one
    ungated action — no confirm dialog — and the cancel-requested marker
    renders in place (the region swaps, the document does not); once the
    run reports terminal the marker gives way to the state. The
    during-live-window render is pinned on an INDUCED live window (a
    counter-based run_get wrap reporting the run's own accepted state —
    labelled induction, FOLD-4's lesson: the marker must not be decided
    by the sim's speed); every seam call stays real."""
    run_id = served.chain_run_id
    assert run_id, "the chain's run has not started (the confirm arm runs first)"
    record = served.control
    post_tokens, responses = _wire(page)

    operations = served.operations
    real_get = operations.run_get
    forced = {"n": 2}  # the run page's render + the cancel POST's re-render

    def _live_window(*args: Any, **kwargs: Any) -> Any:
        projection = real_get(*args, **kwargs)
        if forced["n"] > 0:
            forced["n"] -= 1
            return {**projection, "state": "accepted"}
        return projection

    operations.run_get = _live_window
    dialogs: list[str] = []

    def _on_dialog(dialog: Any) -> None:
        dialogs.append(dialog.type)
        dialog.dismiss()

    page.on("dialog", _on_dialog)

    _open(page, served, record, f"/ui/benches/{BENCH_ID}")
    started_link = page.locator("[data-bw-run-started] a.bw-link")
    expect(started_link).to_be_attached()
    assert started_link.get_attribute("href") == f"/ui/runs/{run_id}"
    assert "already started run" in page.locator(
        "[data-bw-run-started]"
    ).inner_text(), "the prior-start disclosure does not render"

    page.goto(f"{served.base}/ui/runs/{run_id}", wait_until="networkidle")
    cancel_form = page.locator("form[data-bw-cancel-control]")
    expect(cancel_form).to_be_attached()
    assert page.locator("[data-bw-cancel-requested]").count() == 0

    page.evaluate("() => { window.__bwNoReload = true; }")
    page.fill('[data-bw-cancel-control] input[name="reason"]', "browser lane stopped the run")
    page.click('[data-bw-cancel-control] button[type="submit"]')
    expect(page.locator("[data-bw-cancel-requested]")).to_be_attached()
    forced["n"] = 0
    operations.run_get = real_get

    assert page.evaluate("() => window.__bwNoReload === true"), (
        "the document reloaded: the cancel outcome must swap the region in place"
    )
    assert page.url == f"{served.base}/ui/runs/{run_id}"
    assert page.locator("[data-bw-run-facts]").count() == 1, (
        "a full page replaced the document: the cancel region is its own swap target"
    )
    assert dialogs == [], f"a confirm dialog gated the cancel: {dialogs}"
    assert served.sessions.cancel_requested(record.session_id, run_id) is True
    _assert_wire(post_tokens, responses)

    _poll_terminal(served, run_id)
    page.reload(wait_until="networkidle")
    assert page.locator("[data-bw-cancel-requested]").count() == 0, (
        "the marker outlived the run's terminal report"
    )
    assert page.locator("[data-bw-terminal-note]").count() == 1


def test_replay_after_terminal_restage_renders_the_replay_row(
    served: SimpleNamespace, page: Page
) -> None:
    """§9 in the real browser: a full cycle whose run settles terminal,
    restage the SAME binding, check, arm, confirm — the seam's replay
    returns the FIRST run and the panel renders it AS a replay (the
    data-bw-replay marker, the first run's id, the replay text), never a
    fresh-looking start; the store holds exactly one run. The second
    cycle runs under the FIRST cycle's lease (the seam admits one
    controlling lease per bench — the REST repro's note), and the chain's
    lease is released at this arm's end."""
    record = served.control
    post_tokens, responses = _wire(page)
    run_id = served.chain_run_id
    assert run_id, "the chain's run has not started (the confirm arm runs first)"

    _poll_terminal(served, run_id)
    _open(page, served, record, f"/ui/benches/{BENCH_ID}")
    assert "already started run" in page.locator(
        "[data-bw-run-started]"
    ).inner_text(), "the prior-start disclosure does not render"

    _cycle_to_armed(page, served, served.binding_sha, staged=True)
    _click_swap(page, '[data-bw-confirm-action="true"]')
    started = page.locator("[data-bw-run-started]")
    expect(started).to_be_attached()
    assert started.get_attribute("data-bw-run-started") == run_id, (
        f"the replay did not return the first run: {started.get_attribute('data-bw-run-started')}"
    )
    assert started.get_attribute("data-bw-replay") == "true", (
        "the §9 replay did not render the replay marker"
    )
    assert "Replayed run" in started.inner_text()
    runs = served.store.list_run_states(BENCH_ID)
    assert len(runs) == 1, runs
    assert page.locator("[data-bw-bench-facts]").count() == 1
    assert page.url == f"{served.base}/ui/benches/{BENCH_ID}"

    _assert_wire(post_tokens, responses)

    # chain hygiene: the run-bearing legs are done; release the lease as
    # its holder (the G3a teardown rule) so the module ends free.
    view = served.sessions.held_lease(record.session_id, BENCH_ID)
    if view is not None:
        with contextlib.suppress(Exception):
            served.operations.lease_release(
                _session_identity(record),
                view.lease_id,
                "g3b-browser-replay-arm",
                "chain hygiene release",
            )
        served.sessions.clear_held_lease(record.session_id, BENCH_ID)


def test_staged_non_binding_digest_renders_the_unreadable_shape(
    served: SimpleNamespace, page: Page
) -> None:
    """FOLD-1 in the real browser: a STORED document that is not a
    binding — the lattice's own procedure document, staged by its
    content digest — must render the honest-disabled staged-chain-
    unreadable shape, not an error page. The stage answers 200, the
    bench page stays composed, and the start control names the reason."""
    record = served.control
    post_tokens, responses = _wire(page)
    procedure_sha = _lattice_procedure_sha(served)
    _open(page, served, record, f"/ui/benches/{BENCH_ID}")

    _stage_via_form(page, served, procedure_sha, staged=True)
    staged_row = page.locator('[data-bw-staged="true"]')
    expect(staged_row).to_be_attached()
    assert page.locator("[data-bw-staged-sha]").inner_text() == procedure_sha

    disabled = page.locator(
        '[data-bw-start-control] button[disabled]'
        '[data-bw-disabled-reason="staged-chain-unreadable"]'
    )
    assert disabled.count() == 1, (
        "the stored non-binding digest must render the unreadable-chain shape"
    )
    note = page.locator("[data-bw-staged-chain-note]")
    assert note.count() == 1
    assert "not readable" in note.inner_text()
    assert page.locator("[data-bw-bench-facts]").count() == 1, (
        "the bench page navigated: a non-binding stage must still compose the page"
    )
    assert page.url == f"{served.base}/ui/benches/{BENCH_ID}"
    _assert_wire(post_tokens, responses)
