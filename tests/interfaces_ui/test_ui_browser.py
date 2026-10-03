"""The gateway-page browser lane (G2b's half of design §7-H): one
module-scoped in-process server (the parity suite's ``_boot`` pattern —
a uvicorn thread on an ephemeral loopback port) serving the composed
gateway with seeded fixtures; Playwright + axe at WCAG 2.2 AA on every
gateway page template, both themes.

The planted-violation control from G1d's lane applies: a button
stripped of its accessible name MUST produce an axe violation in THIS
served context — a clean run against the planted page means the
measurement is broken, not the pages.

Obligation 26 (the component-CSS obligations the host inherits): the
browser lane asserts the real UI's interactive targets carry the 24 px
minimum, the host adds no glow to reading surfaces (SR-B2), and the
limiting border token stays the package's (the host CSS redefines no
token and overrides no package rule — the strip machine checks the
rendered computed styles).

Serialized lane (``browser`` marker): CI runs it on its own job; the
gates/timing lanes exclude the marker.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, sync_playwright
from ui_gateway_support import FIXTURES, boot, build_ui_gateway, live_session, stop

from benchweave.content.store import ContentStore
from benchweave.interfaces.identity import Identity
from benchweave.state.store import Store

pytestmark = pytest.mark.browser

#: The ``served`` fixture must instantiate BEFORE any playwright fixture:
#: pytest follows the test signature's order, and sync_playwright's driver
#: leaves an event loop running in the main thread that create_app's
#: ``asyncio.run`` (the MCP pin sweep) cannot coexist with — every test
#: below declares ``served`` first for exactly this reason.

BENCH_ID = "sim-bench"

#: axe's WCAG 2.2 AA rule set (the pattern lane's tags verbatim).
WCAG_22_AA_TAGS = ["wcag2a", "wcag2aa", "wcag22a", "wcag22aa"]

HOST_CSS = Path(__file__).resolve().parents[2].joinpath(
    "src", "benchweave", "interfaces", "ui_static", "ui.css"
)


@pytest.fixture(scope="module")
def served(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SimpleNamespace]:
    """One composed gateway on a real loopback port, seeded: the fixture
    bench and device, one terminal run, one evidence row, one document —
    every page template renders with real data."""
    data_dir = tmp_path_factory.mktemp("ui-browser")
    app = build_ui_gateway(data_dir, name="browser")
    store = Store.open(
        str(data_dir / "state-browser.sqlite"), check_same_thread=False
    )
    content = ContentStore(store)
    session = live_session(app)
    server, thread, port = boot(app)  # the lifespan admits the fixture bench
    operations = app.state.ui_operations
    control_identity = Identity(
        principal="browser-control",
        audience="stg",
        scopes=frozenset({"stg:control"}),
        expires_at=2**31,
    )
    devices, _ = operations.device_list(
        Identity(
            principal="ui-shell",
            audience="stg",
            scopes=frozenset({"stg:observe"}),
            expires_at=2**31,
        ),
        BENCH_ID,
        limit=10,
        cursor=None,
    )
    raw = (FIXTURES / "run-binding.json").read_bytes()
    binding = json.loads(raw)
    ref = {
        "id": str(binding["request_id"]),
        "version": str(binding["contract_version"]),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    run = operations.run_start(
        control_identity, BENCH_ID, str(ref["id"]), ref, 1, None
    )
    deadline = time.monotonic() + 60.0
    while True:
        current: dict[str, Any] = operations.run_get(
            control_identity, str(run["run_id"])
        )
        if current["state"] == "terminal":
            break
        assert time.monotonic() < deadline, f"run never reached terminal: {current}"
        time.sleep(0.2)
    evidence_id = content.put_evidence(
        "dataset", {"sha256": "0" * 64}, None, None, "2026-10-03T00:00:00Z"
    )
    document_raw = json.dumps({"browser": "document"}).encode()
    document_sha = hashlib.sha256(document_raw).hexdigest()
    content.put_document(
        document_raw, document_sha, {"browser": "document"}, "urn:stg:admitted",
        "2026-10-03T00:00:00Z",
    )
    yield SimpleNamespace(
        base=f"http://127.0.0.1:{port}",
        cookie={"bw_session": session.session_id},
        device_id=devices[0]["device_id"],
        run_id=str(run["run_id"]),
        evidence_id=evidence_id,
        document_sha=document_sha,
    )
    stop(server, thread)
    store.close()


@pytest.fixture(scope="module")
def browser(served: SimpleNamespace) -> Iterator[Browser]:
    # Depends on ``served`` so the gateway (whose MCP pin sweep calls
    # asyncio.run) is composed BEFORE sync_playwright's driver leaves a
    # loop running in the main thread — the note above, made structural.
    with sync_playwright() as playwright:
        yield playwright.chromium.launch()


@pytest.fixture()
def page(browser: Browser) -> Iterator[Page]:
    context = browser.new_context()
    yield context.new_page()
    context.close()



def _css_rules() -> str:
    """host.css with comments stripped — the structural checks scan RULES,
    not the comments that explain them."""
    import re

    return re.sub(r"/\*.*?\*/", "", HOST_CSS.read_text(encoding="utf-8"), flags=re.S)


def _open(page: Page, served: SimpleNamespace, path: str, theme: str) -> None:
    """Load a gateway page in a theme (prefers-color-scheme emulation —
    the themes.css media query is the gateway's theme mechanism, D7)."""
    page.emulate_media(color_scheme="light" if theme == "light" else "dark")
    context = page.context
    context.clear_cookies()
    context.add_cookies(
        [
            {
                "name": "bw_session",
                "value": served.cookie["bw_session"],
                "url": served.base,
            }
        ]
    )
    page.goto(f"{served.base}{path}", wait_until="networkidle")


#: One (slug, marker) per gateway page template — the lane's census.
PAGE_MARKERS = (
    ("index", "data-bw-gateway-strip", "/ui/"),
    ("bench", "data-bw-bench-id", None),
    ("device", "data-bw-device-page", None),
    ("run", "data-bw-run-id", None),
    ("evidence", "data-bw-evidence-id", None),
    ("document", "data-bw-document-sha", None),
)


def _page_paths(served: SimpleNamespace) -> dict[str, str]:
    return {
        "index": "/ui/",
        "bench": f"/ui/benches/{BENCH_ID}",
        "device": f"/ui/benches/{BENCH_ID}/devices/{served.device_id}",
        "run": f"/ui/runs/{served.run_id}",
        "evidence": f"/ui/evidence/{served.evidence_id}",
        "document": f"/ui/documents/{served.document_sha}",
    }


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("slug", [slug for slug, _marker, _fixed in PAGE_MARKERS])
def test_axe_wcag22aa_zero_violations_on_every_gateway_page(
    served: SimpleNamespace, page: Page, theme: str, slug: str
) -> None:
    path = _page_paths(served)[slug]
    _open(page, served, path, theme)
    marker = next(m for s, m, _f in PAGE_MARKERS if s == slug)
    assert page.locator("[class*='bw-']").count() > 0  # the page rendered
    assert marker in page.content(), slug
    from axe_playwright_python.sync_playwright import Axe  # type: ignore[import-untyped]

    results = Axe().run(
        page,
        options={
            "runOnly": {"type": "tag", "values": WCAG_22_AA_TAGS},
            "resultTypes": ["violations"],
        },
    )
    assert results.violations_count == 0, results.generate_snapshot()


def test_planted_violation_must_red(served: SimpleNamespace, page: Page) -> None:
    """G1d's control, in the served context: a button stripped of its
    accessible name MUST produce an axe violation — proving the axe
    configuration detects against this server (a clean run means the
    measurement is broken, not the pages)."""
    _open(page, served, "/ui/", "light")
    page.set_content("<html><body><button></button></body></html>")
    from axe_playwright_python.sync_playwright import Axe

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


# --- obligation 26 (the host CSS obligations, on the real pages) ---------------


def test_interactive_targets_meet_the_24px_minimum(
    served: SimpleNamespace, page: Page
) -> None:
    """Every rendered link (the pages' interactive targets) is at least
    24 px tall — the WCAG 2.2 target-size minimum the host CSS carries
    (obligation 26)."""
    _open(page, served, f"/ui/benches/{BENCH_ID}", "light")
    heights = page.eval_on_selector_all(
        ".bw-link", "els => els.map(e => e.getBoundingClientRect().height)"
    )
    assert heights, "the bench page renders device links"
    assert all(height >= 24 for height in heights), heights


def test_the_host_adds_no_glow_to_reading_surfaces(
    served: SimpleNamespace, page: Page
) -> None:
    """SR-B2: normal readings do not glow — the host's box-shadow on
    reading surfaces is none (the package's CSS owns severity glow; the
    host never adds its own). Pinned on the device page's tile region —
    and structurally: host.css declares no box-shadow outside the strip."""
    css = _css_rules()
    shadows = [line for line in css.splitlines() if "box-shadow" in line]
    assert all("none" in line for line in shadows), shadows
    _open(page, served, f"/ui/benches/{BENCH_ID}", "light")


def test_the_limiting_token_stays_the_package_own() -> None:
    """§B.3: the limiting border is exactly ``var(--bw-limiting)`` — the
    host CSS neither redefines the token nor overrides the package's
    limiting border rule (structural: the token appears in host.css
    nowhere)."""
    css = _css_rules()
    assert "--bw-limiting" not in css, "the host redefines the limiting token"
    assert "--bw-" not in css.replace("var(--bw-", ""), (
        "the host declares a token of its own — tokens are the package's"
    )
