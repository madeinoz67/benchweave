#!/usr/bin/env python3
"""Prove the plugin catalogue works from a plain static deploy (issue #224 B4).

Author: Stephen Eaton

Lane 2 of the search proof — the wiring, on the real assembled artifact.
A static file server IS the static deploy ("no service" means no search
backend, CR-26): this script serves the assembly root and asserts, in a
real browser (Playwright, the #300 docs-lane precedent):

  (a) the committed default rows are present in the served DOM WITHOUT
      JavaScript decoration — and the version slots are still empty (the
      no-JS degradation: a smaller set of fields, none of them false);
  (b) with JS, a matching query keeps the real dogfooded row and a
      non-matching query empties the list behind the honest-empty state;
  (c) the only network request the catalogue issues is the same-origin
      ``plugins-index.json`` fetch at load — search interactions issue zero
      new requests (the page's unrelated star-count fetch to the GitHub API
      is pre-existing and out of scope).

Dimension breadth is lane 1's job (tests/contract/run_search_spec.mjs);
this arm proves the wiring against the served mirror.

Usage::

    python scripts/website/check_catalogue_served.py --dest site
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import sys
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=REPO / "site")
    args = parser.parse_args()
    dest = args.dest.resolve()
    if not (dest / "index.html").is_file() or not (dest / "plugins-index.json").is_file():
        print(
            f"catalogue_served_refused: {dest} lacks index.html or plugins-index.json",
            file=sys.stderr,
        )
        return 1
    mirror = json.loads((dest / "plugins-index.json").read_text(encoding="utf-8"))
    default_rows = [
        row
        for row in mirror.get("rows", [])
        if row.get("kind") == "admitted-release" and row.get("signature_state") == "signed-valid"
    ]
    first_id = str(default_rows[0]["package_id"]) if default_rows else ""

    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(dest)
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.RequestHandlerClass.log_message = lambda *a, **k: None  # type: ignore[assignment]
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}/"
    failures: list[str] = []

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        # (a) the static default rows, without JS decoration.
        no_js = browser.new_context(java_script_enabled=False)
        page = no_js.new_page()
        page.goto(base, wait_until="load")
        static_count = page.locator("#panel-plugins .spec-card[data-bw-package-id]").count()
        if static_count != len(default_rows):
            failures.append(
                f"static rows without JS: {static_count} rendered, {len(default_rows)} "
                "in the served mirror's default view"
            )
        if first_id and page.locator(
            f'#panel-plugins .spec-card[data-bw-package-id="{first_id}"]'
        ).count() != 1:
            failures.append(f"the default row {first_id} is not in the served DOM")
        undecorated = page.locator('#panel-plugins [data-bw-slot="version"]').evaluate_all(
            "els => els.every(el => !(el.textContent || '').trim())"
        )
        if not undecorated:
            failures.append("version slots are decorated without JS — the no-JS set must be static")
        no_js.close()

        # (b) search wiring, and (c) its network surface.
        context = browser.new_context()
        page = context.new_page()
        requests: list[str] = []
        page.on("request", lambda req: requests.append(req.url))
        page.goto(base, wait_until="load")
        page.wait_for_function(
            "() => document.getElementById('catalogue-count').textContent.length > 0",
            timeout=10000,
        )
        # The real user flow: open the panel before searching (the fill
        # needs a visible control).
        page.get_by_role("button", name="Plugins").click()
        index_fetches = [url for url in requests if url.endswith("/plugins-index.json")]
        if len(index_fetches) != 1 or not index_fetches[0].startswith(base):
            failures.append(
                f"the catalogue must fetch plugins-index.json exactly once, same-origin; "
                f"saw {index_fetches!r}"
            )
        decorated = page.locator(
            f'#panel-plugins .spec-card[data-bw-package-id="{first_id}"] '
            '[data-bw-slot="version"]'
        )
        if first_id and not (decorated.inner_text() if decorated.count() else "").strip():
            failures.append("the version slot is not decorated from the served index")

        before_search = len(requests)
        page.fill("#bw-filter-text", "dps")
        page.wait_for_timeout(150)
        visible = page.locator("#panel-plugins .spec-card[data-bw-package-id]:not([hidden])")
        if first_id and (visible.count() != 1 or "dps" not in visible.first.inner_text().lower()):
            failures.append(
                f"a matching query must keep the real row ({first_id}); "
                f"{visible.count()} card(s) visible"
            )
        page.fill("#bw-filter-text", "zzzz-no-such-plugin")
        page.wait_for_timeout(150)
        if page.locator("#panel-plugins .spec-card[data-bw-package-id]:not([hidden])").count():
            failures.append("a non-matching query must empty the list")
        if not page.locator("#catalogue-empty").is_visible():
            failures.append("a non-matching query must show the honest-empty state")
        if len(requests) != before_search:
            failures.append(
                "search issued network requests — only the one same-origin "
                f"plugins-index.json fetch is allowed (log grew by {len(requests) - before_search})"
            )
        context.close()
        browser.close()

    server.shutdown()
    if failures:
        print("catalogue_served FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print("catalogue wiring OK: static rows without JS, search over the served index, one fetch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
