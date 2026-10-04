"""The G3a browser acceptance lane (design arm L): a real browser drives
the composed gateway's control surface - the seams a REST-level suite
cannot see.

The lane exists because no browser arm had ever exercised a
session-bearing POST on this UI before G3a's refute found the control
surface browser-dead: the CSRF token was never delivered to the page
(FOLD-1 - the htmx:configRequest listener in bw-host.js), and htmx 2's
default response handling refused to swap the 4xx fragments the refusal
path draws (the responseHandling override in base.j2). The arms:

- the take/renew/release cycle through the REAL buttons: the CSRF
  header must ride htmx's configRequest listener (asserted on the
  wire); every outcome re-renders the controls section in place, no 403
  anywhere in the network log;
- a conflict renewal (the sequence bumped behind the held view) draws
  its section-C.3 refusal row inside the controls region - a fragment
  swap, not a page, not nothing;
- an observe-scoped session: every rendered control is disabled with
  the no-authority reason, and a direct POST presenting the session's
  own token still 403s at the seam;
- GW-44: a lease in the warning window keeps its section-B.1 bubble
  across a poll-equivalent swap; the cadence attribute tightens by 6;
- hx-preserve (FOLD-8): a half-typed duration survives one poll swap;
- axe at WCAG 2.2 AA on the one shape the G2 census cannot render (the
  forms-and-facts shape, control scope + held lease): zero violations;
- GW-95: a session too short for any offered lease renders the bounded
  disabled shape with the ui-login clearing action.

Serialized in the browser marker (CI's browser job). The served app's
clock is the mutable cell the REST-level suite uses: arms advance it and
reload, so expiry, warnings and the GW-95 bound move deterministically.
Each arm that takes a lease releases it in teardown - the bench is
shared module-wide.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright
from ui_gateway_support import FIXTURES, LIMITS, NOW_EPOCH, SECRET, boot, stop

from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.sessions import SessionStore
from benchweave.interfaces.ui_control import DEFAULT_PANEL_POLL_MS
from benchweave.state.store import Store

pytestmark = pytest.mark.browser

BENCH_ID = "sim-bench"

CONTROL = frozenset({"stg:observe", "stg:control"})
OBSERVE = frozenset({"stg:observe"})

WCAG_22_AA_TAGS = ["wcag2a", "wcag2aa", "wcag22a", "wcag22aa"]


class _Clock:
    """One mutable epoch cell; the REST-level suite's exact pattern."""

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


def _session_identity(record: Any) -> Identity:
    """The seam Identity for a session record (ui.py's _session_identity
    rule), restated here for teardown calls that act as the session:
    the holder releases what it took."""
    return Identity(
        principal=record.principal,
        audience=record.audience,
        scopes=record.scopes,
        expires_at=record.expires_at,
    )


def _mint(
    served: SimpleNamespace, *, principal: str, scopes: frozenset[str], ttl_s: int
) -> Any:
    """A live session minted at the CURRENT clock epoch (inside-test
    mints stay live no matter how far earlier arms advanced the clock)."""
    sessions: SessionStore = served.sessions
    code = sessions.mint_login_code(
        Identity(
            principal=principal,
            audience="stg",
            scopes=scopes,
            expires_at=NOW_EPOCH + 12 * 3600,
        ),
        ttl_seconds=ttl_s,
    )
    return sessions.exchange(code)


@pytest.fixture(scope="module")
def served(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SimpleNamespace]:
    """One composed gateway on a real loopback port, its clock mutable.

    Same discipline as the G2b lane: a real store, the fixture bench
    admitted at lifespan, one module-scoped chromium. The control
    session (3600 s TTL) is minted at setup; observe and GW-95 sessions
    are minted inside their arms so clock advances cannot outlive them.
    """
    clock = _Clock()
    data_dir = tmp_path_factory.mktemp("g3a-browser")
    store = Store.open(
        str(data_dir / "state-g3a-browser.sqlite"), check_same_thread=False
    )
    app = create_app(
        store=store,
        content=ContentStore(store),
        secret=SECRET,
        limits=dict(LIMITS),
        gateway_id="ui-test",
        fixtures_dir=FIXTURES,
        now_iso=clock.iso,
        now_epoch=clock.epoch_s,
    )
    server, thread, port = boot(app)  # the lifespan admits the fixture bench
    sessions_store: SessionStore = app.state.ui_sessions
    code = sessions_store.mint_login_code(
        Identity(
            principal="g3a-browser-control",
            audience="stg",
            scopes=CONTROL,
            expires_at=NOW_EPOCH + 12 * 3600,
        ),
        ttl_seconds=3600,
    )
    control = sessions_store.exchange(code)
    yield SimpleNamespace(
        base=f"http://127.0.0.1:{port}",
        clock=clock,
        operations=app.state.ui_operations,
        sessions=sessions_store,
        control=control,
        store=store,
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


def _release_any_lease(served: SimpleNamespace) -> None:
    """Teardown: whatever lease the control session left live on the
    shared bench, release it as its holder. The seam judges holder
    authority (and release reads the bench's own stored sequence -
    FOLD-3), so the release succeeds even when the held view's sequence
    went stale behind a conflict arm; the view is cleared regardless."""
    record = served.control
    view = served.sessions.held_lease(record.session_id, BENCH_ID)
    if view is None:
        return
    with contextlib.suppress(Exception):
        # Teardown: the next arm needs a free bench; a refusal here (a
        # lease already gone) leaves the bench as free as it was.
        served.operations.lease_release(
            _session_identity(record),
            view.lease_id,
            "g3a-browser-teardown",
            "test teardown release",
        )
    served.sessions.clear_held_lease(record.session_id, BENCH_ID)


@pytest.fixture()
def free_bench(served: SimpleNamespace) -> Iterator[SimpleNamespace]:
    """Yield the rig; release any lease the arm left behind."""
    yield served
    _release_any_lease(served)


@pytest.mark.usefixtures("free_bench")
def test_take_renew_release_through_real_buttons_no_403(
    served: SimpleNamespace, page: Page
) -> None:
    """The cycle the UI had never survived in a browser: click Take,
    the fragment re-renders held; Renew, held with a bumped sequence;
    Release, none. The CSRF header rides htmx's configRequest listener
    (asserted on the wire) and no response is a 403."""
    record = served.control
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
    assert page.locator('[data-bw-lease-state="none"]').count() == 1

    page.click('[data-bw-lease-take] button[type="submit"]')
    page.wait_for_selector('[data-bw-lease-state="held"]', state="attached")
    assert post_tokens[-1] == record.csrf_token, "the take POST carried no CSRF token"
    assert page.locator(
        f'[data-bw-lease-holder="{record.principal}"]'
    ).count() == 1, "the held facts row does not name this session as holder"
    assert page.locator("[data-bw-controls]").count() == 1
    assert page.locator("[data-bw-bench-facts]").count() == 1, (
        "the bench page navigated: the take outcome must swap in place"
    )
    assert page.url == f"{served.base}/ui/benches/{BENCH_ID}"

    page.click('[data-bw-lease-renew] button[type="submit"]')
    expect(
        page.locator('[data-bw-lease-renew] input[name=sequence]')
    ).to_have_value("2")
    assert post_tokens[-1] == record.csrf_token, "the renew POST carried no CSRF token"
    assert page.locator("[data-bw-bench-facts]").count() == 1

    page.click('[data-bw-lease-release] button[type="submit"]')
    page.wait_for_selector("[data-bw-lease-none]", state="attached")
    assert post_tokens[-1] == record.csrf_token, "the release POST carried no CSRF token"
    assert page.locator("form[data-bw-lease-take]").count() == 1, (
        "after release the take control returns (the no-lease shape)"
    )

    refused = [r for r in responses if r.status == 403]
    assert refused == [], (
        "a session-bearing POST was refused: "
        + "; ".join(f"{r.url} -> {r.status}" for r in refused)
    )


def test_conflict_renewal_draws_the_refusal_inside_the_controls_region(
    served: SimpleNamespace, page: Page, free_bench: SimpleNamespace
) -> None:
    """A renewal whose sequence moved elsewhere (a REST-class renewal
    behind the held view) draws its section-C.3 conflict row INSIDE the
    controls region: the failure fragment swaps where the section was -
    not a full page, not nothing."""
    record = served.control
    operations = served.operations

    _open(page, served, record, f"/ui/benches/{BENCH_ID}")
    page.click('[data-bw-lease-take] button[type="submit"]')
    page.wait_for_selector('[data-bw-lease-state="held"]', state="attached")

    view = served.sessions.held_lease(record.session_id, BENCH_ID)
    assert view is not None
    operations.lease_renew(
        _session_identity(record),
        view.lease_id,
        "g3a-browser-rest-bump",
        view.sequence,
        600_000,
    )

    page.reload(wait_until="networkidle")
    assert page.locator('[data-bw-lease-state="held"]').count() == 1, (
        "the re-rendered view still shows the (stale) held lease"
    )
    page.click('[data-bw-lease-renew] button[type="submit"]')
    page.wait_for_selector('section[data-bw-failure="conflict"]', state="attached")

    assert page.locator(
        '[data-bw-controls-region] section[data-bw-failure="conflict"]'
    ).count() == 1, "the refusal did not draw inside the controls region"
    assert page.locator('[data-bw-refusal-code="conflict"]').count() == 1, (
        "the section-C.3 row for the conflict code is absent"
    )
    assert page.locator('[data-bw-sent-status="NO"]').count() == 1
    action = page.locator("[data-bw-operator-action]").inner_text().strip()
    assert action, "the section-C.3 row names no operator action"
    assert page.locator("[data-bw-correlation-id]").count() == 1
    assert page.locator("[data-bw-bench-facts]").count() == 1, (
        "a full page replaced the document: the refusal must swap in place"
    )
    assert page.locator('meta[name="bw-csrf-token"]').count() == 1
    assert page.url == f"{served.base}/ui/benches/{BENCH_ID}"


def test_observe_session_renders_controls_disabled_and_direct_post_still_403s(
    served: SimpleNamespace, page: Page, free_bench: SimpleNamespace
) -> None:
    """Observe scope, no control authority: every rendered control is
    disabled with the no-authority reason; a direct POST that presents
    the session's own CSRF token is still refused by the seam (403), and
    no lease is created."""
    observe = _mint(served, principal="g3a-browser-observe", scopes=OBSERVE, ttl_s=3600)
    _open(page, served, observe, f"/ui/benches/{BENCH_ID}")

    for control in ("take", "renew", "release"):
        assert page.locator(
            f'[data-bw-lease-{control}] button[disabled]'
            f'[data-bw-disabled-reason="no-authority"]'
        ).count() == 1, (
            f"the {control} control is not the disabled observe shape"
        )
    assert page.locator("[data-bw-controls] form").count() == 0, (
        "an observe session must not be handed a live form"
    )
    assert page.locator('[data-bw-disabled-reason="no-authority"]').count() >= 3

    token = page.locator('meta[name="bw-csrf-token"]').get_attribute("content")
    assert token, "the observe session's page carries no CSRF token"
    response = page.request.post(
        f"{served.base}/ui/benches/{BENCH_ID}/leases",
        form={"duration_ms": "300000", "expected_generation": "1"},
        headers={"x-csrf-token": token, "origin": served.base},
    )
    assert response.status == 403
    assert 'data-bw-failure="forbidden"' in response.text(), (
        "the refusal is not the seam's forbidden row"
    )

    page.reload(wait_until="networkidle")
    assert page.locator("[data-bw-lease-none]").count() == 1, (
        "the refused POST created a lease"
    )


def test_lease_in_warning_window_persists_banner_and_tightens_poll(
    served: SimpleNamespace, page: Page, free_bench: SimpleNamespace
) -> None:
    """GW-44: a live lease driven into its warning window renders the
    section-B.1 warning bubble and the by-6 cadence - and both persist
    across a poll-equivalent swap (the same GET the poll timer issues,
    through htmx's own request pipeline)."""
    record = served.control
    _open(page, served, record, f"/ui/benches/{BENCH_ID}")
    page.click('[data-bw-lease-take] button[type="submit"]')
    page.wait_for_selector('[data-bw-lease-state="held"]', state="attached")

    served.clock.advance(480)  # 600 s taken, 480 s pass, 120 s remain: the warning floor
    page.reload(wait_until="networkidle")

    section = page.locator("[data-bw-controls]")
    expected_ms = str(DEFAULT_PANEL_POLL_MS // 6)
    assert section.get_attribute("data-bw-panel-poll-ms") == expected_ms, (
        "the poll cadence did not tighten inside the warning window"
    )
    bubble = page.locator(
        '[data-bw-controls] aside.bw-alert-bubble[data-severity="warning"]'
    )
    assert bubble.count() == 1, "the section-B.1 warning bubble did not render"
    assert "Lease ending soon" in bubble.inner_text()
    assert "every" in (section.get_attribute("hx-trigger") or "")

    page.eval_on_selector(
        "[data-bw-controls]", "el => { el.__staleMarker = true; }"
    )
    page.evaluate(
        """async (url) => {
            await htmx.ajax('GET', url, {
                target: '[data-bw-controls]', swap: 'outerHTML',
            });
        }""",
        f"{served.base}/ui/benches/{BENCH_ID}/controls",
    )
    assert page.evaluate(
        "() => document.querySelector('[data-bw-controls]').__staleMarker === undefined"
    ), "the poll-equivalent swap did not replace the section"
    assert (
        page.locator("[data-bw-controls]").get_attribute("data-bw-panel-poll-ms")
        == expected_ms
    ), "the tightened cadence did not survive the poll re-render"
    assert page.locator(
        '[data-bw-controls] aside.bw-alert-bubble[data-severity="warning"]'
    ).count() == 1, "the warning bubble did not persist across the poll re-render"


def test_typed_duration_survives_a_poll_swap(
    served: SimpleNamespace, page: Page, free_bench: SimpleNamespace
) -> None:
    """A half-typed duration input keeps its value across one poll
    re-render: htmx's hx-preserve carries the live element over the
    section's outerHTML swap."""
    record = served.control
    _open(page, served, record, f"/ui/benches/{BENCH_ID}")
    selector = f"#bw-lease-duration-{BENCH_ID}"
    page.fill(selector, "111111")
    page.eval_on_selector(selector, "el => { el.__liveInput = true; }")
    page.eval_on_selector(
        '[data-bw-lease-take] button[type="submit"]',
        "el => { el.__staleButton = true; }",
    )

    page.evaluate(
        """async (url) => {
            await htmx.ajax('GET', url, {
                target: '[data-bw-controls]', swap: 'outerHTML',
            });
        }""",
        f"{served.base}/ui/benches/{BENCH_ID}/controls",
    )
    value, live = page.eval_on_selector(
        selector, "el => [el.value, el.__liveInput === true]"
    )
    assert value == "111111", (
        f"the typed duration was reset by the poll swap (value now {value!r})"
    )
    assert live, (
        "the input is a fresh node: hx-preserve did not carry the live "
        "element across the swap"
    )
    swapped = page.eval_on_selector(
        '[data-bw-lease-take] button[type="submit"]',
        "el => el.__staleButton === undefined",
    )
    assert swapped, "the poll-equivalent swap did not replace the section"


def test_axe_zero_violations_on_the_control_scoped_bench_page(
    served: SimpleNamespace, page: Page, free_bench: SimpleNamespace
) -> None:
    """The G2 census runs every page through axe at WCAG 2.2 AA in the
    observe-scoped shape (every control disabled). This arm covers the
    shape that census cannot render: control scope, live forms, a held
    lease's facts row - zero violations."""
    record = served.control
    _open(page, served, record, f"/ui/benches/{BENCH_ID}")
    page.click('[data-bw-lease-take] button[type="submit"]')
    page.wait_for_selector('[data-bw-lease-state="held"]', state="attached")

    from axe_playwright_python.sync_playwright import Axe  # type: ignore[import-untyped]

    results = Axe().run(
        page,
        options={
            "runOnly": {"type": "tag", "values": WCAG_22_AA_TAGS},
            "resultTypes": ["violations"],
        },
    )
    assert results.violations_count == 0, results.generate_snapshot()


def test_session_too_short_for_any_lease_renders_the_bounded_shape(
    served: SimpleNamespace, page: Page
) -> None:
    """GW-95's disabled shape: a control-scoped session with less
    remaining time than the offered minimum renders the take control
    disabled with the session expiry stated and the ui-login clearing
    action beside it - no live form."""
    short = _mint(served, principal="g3a-browser-short", scopes=CONTROL, ttl_s=30)
    _open(page, served, short, f"/ui/benches/{BENCH_ID}")
    bounded = page.locator(
        '[data-bw-lease-take] button[disabled][data-bw-session-bound="true"]'
    )
    assert bounded.count() == 1, "the take control is not the GW-95 bounded shape"
    note = page.locator("[data-bw-session-bound-note]")
    assert note.count() == 1
    inner = note.inner_text()
    assert "session ends at" in inner
    assert "benchweave ui-login" in inner, (
        "the bounded note does not name the ui-login clearing action"
    )
    assert page.locator("[data-bw-lease-take] form").count() == 0, (
        "a session too short for any lease must not be handed a form"
    )
    assert page.locator("[data-bw-lease-renew]").count() == 0
    assert page.locator("[data-bw-lease-release]").count() == 0
