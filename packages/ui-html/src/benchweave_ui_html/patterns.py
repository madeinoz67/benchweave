"""The pattern library (G1d design record §1.3): one frozen ``PATTERNS``
registry serving BOTH the row checkers' fixtures and the library pages —
no second mirror to drift. The pages derive from the SAME contract the
gate parses (row-as-data: §C.3 refusal cells, §C.2 label cells, §B.1
severity cells, §D.1 wording cells), so the library cannot drift from the
contract without the gate's own rows reding first.

The export writes a static tree — plain rendered HTML files, no server:
``patterns/<theme>/<page>.html`` plus ``patterns/index.html``; twelve pages
(one per §E.1 component + one refusal page) × two themes; every page root
carries ``data-bw-pattern-library``. Screenshots (UR-13) are captured into
the same tree by the browser lane (slice 4). Styling inlines the REAL token
CSS read through G1a's path constants (one mirror, no copy) and the export
REDS LOUDLY when the styles are absent — the token rows' own fail-loud
shape, recorded as a G1e checklist row (the CSS source re-point).

Dev-mount-only guard, structural: this package ships render functions and
a static-file writer ONLY — there is no app/ASGI/route object to mount;
serving is a host concern (the G2 GW-04 obligation row carries the
never-served-by-production half).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from benchweave_ui_html import artifacts, compositions, fixtures, partials
from benchweave_ui_html.data import (
    AlertBubbleData,
    ButtonData,
    DisabledLabelData,
    ModeBannerData,
    ModeEntry,
    ReadingData,
    RefusalData,
    Severity,
)
from benchweave_ui_html.env import ENV
from benchweave_ui_html.grammar import Row, literal, parse_contract
from benchweave_ui_html.manifest import MANIFEST

if TYPE_CHECKING:
    from playwright.sync_api import Browser as PlaywrightBrowser
    from playwright.sync_api import Page as PlaywrightPage
    from playwright.sync_api import ViewportSize

#: The contract lives at the repository root (the token-CSS posture: live
#: where the gate runs from the repository root, fail loud otherwise).
_REPO_ROOT = Path(__file__).resolve().parents[4]
CONTRACT_MD = _REPO_ROOT / "docs" / "internal" / "ui-contract.md"

#: The export's two themes (the ``data-theme`` root attribute values).
THEMES: tuple[Literal["light", "dark"], ...] = ("light", "dark")

PatternKind = Literal[
    "component",
    "severity",
    "state",
    "staleness",
    "disabled-reason",
    "refusal",
    "mode",
    "composition",
]


@dataclass(frozen=True)
class PatternEntry:
    """One visual fixture: the contract row it serves, its unique fixture id
    (the screenshot filename component), its kind, the page it renders on,
    and its render."""

    row_id: str
    fixture_id: str
    kind: PatternKind
    page: str
    render: Callable[[], str]


class PatternExportRefused(Exception):
    """The export's fail-loud refusal (absent styles, unreadable contract)."""


@lru_cache(maxsize=1)
def _rows_by_id() -> dict[str, Row]:
    """Parse the contract once; every row-id → row. Row-as-data: the library
    pages derive their §C.3/§C.2/§B.1/§D.1 content from these cells."""
    if not CONTRACT_MD.is_file():
        raise PatternExportRefused(
            f"the contract is absent at {CONTRACT_MD} — the pattern library is "
            "live where the gate runs from the repository root (the token-CSS "
            "posture); a wheel install renders partials, never the library"
        )
    contract = parse_contract(CONTRACT_MD.read_text(encoding="utf-8"), MANIFEST)
    return {row.row_id: row for table in contract.tables for row in table.body}


def _keys(slug: str) -> tuple[str, ...]:
    return next(table.keys for table in MANIFEST if table.slug == slug)


def _severity_render(key: str) -> Callable[[], str]:
    def render() -> str:
        return partials.render_alert_bubble(_severity_data(key))

    return render


def _severity_data(key: str) -> AlertBubbleData:
    row = _rows_by_id()[f"b-1-severities::{key}"]
    return AlertBubbleData(
        severity=cast(Severity, literal(row.cells[0])),
        title=literal(row.cells[0]),
        message=literal(row.cells[1]),
        live_region="alert" if key in ("critical", "trip") else "status",
        dismissible=literal(row.cells[2]) == "dismissible",
        source="pattern library",
        aria_label=literal(row.cells[0]),
    )


def _disabled_reason_render(key: str) -> Callable[[], str]:
    def render() -> str:
        button, label = _disabled_reason_data(key)
        return partials.render_button(button) + partials.render_disabled_label(label)

    return render


def _disabled_reason_data(key: str) -> tuple[ButtonData, DisabledLabelData]:
    row = _rows_by_id()[f"c-2-disabled-reason-enum::{key}"]
    label = literal(row.cells[1])
    if key == "device-state":
        # The row's own Parameter cell names the canonical example (`idle`).
        label = label.replace("{state}", "idle")
    return (
        ButtonData(
            label="Energise output",
            disabled_reason=literal(row.cells[0]),
            disabled_label=label,
        ),
        DisabledLabelData(reason=literal(row.cells[0]), label=label),
    )


def _refusal_render(code: str) -> Callable[[], str]:
    def render() -> str:
        return partials.render_refusal(_refusal_data(code))

    return render


def _refusal_data(code: str) -> RefusalData:
    row = _rows_by_id()[f"c-3-refusal-mapping::{code}"]
    return RefusalData(
        code=literal(row.cells[0]),
        severity=cast(Severity, literal(row.cells[1])),
        what_happened=literal(row.cells[2]),
        sent_status=literal(row.cells[3]),
        operator_action=literal(row.cells[4]),
    )


def _mode_render(key: str) -> str:
    row = _rows_by_id()[f"d-1-modes::{key}"]
    entry = ModeEntry(
        key=literal(row.cells[0]),  # type: ignore[arg-type]
        wording=literal(row.cells[1]),
    )
    return partials.render_mode_banner(ModeBannerData(modes=(entry,)))


def _staleness_variant(fixture: str) -> str:
    """The §B.4 variants on the canonical tile: fresh / stale / no-cadence /
    null-freshness, each rendered through the computed-verdict field (never
    a caller-supplied boolean alone)."""
    base = fixtures.reading()
    variants: dict[str, ReadingData] = {
        "st-fresh": dataclasses.replace(
            base, freshness="120 ms", stale_verdict="fresh"
        ),
        "st-stale": dataclasses.replace(
            base, freshness="301 ms", stale_verdict="stale"
        ),
        "st-no-cadence": dataclasses.replace(
            base, freshness="120 ms", stale_verdict="no-verdict"
        ),
        "st-unavailable": dataclasses.replace(
            base, freshness="Unavailable", stale_verdict="no-verdict"
        ),
    }
    return partials.render_reading(variants[fixture])


def _composition_scene(fixture: str) -> str:
    """The composition scenes on the confirm-action page: armed /
    guarded-while-armed / trip / no-authority — the workbench scene at the
    states the §C.1 rules traverse."""
    scene = compositions.psu_scene()
    de_energised = dataclasses.replace(
        scene, output=compositions.OutputState(energised=False, trip=False)
    )
    if fixture == "armed":
        state = compositions.reduce(de_energised, compositions.Arm("energise"))
    elif fixture == "guarded-while-armed":
        state = compositions.reduce(
            compositions.reduce(de_energised, compositions.Arm("energise")),
            compositions.TripArrives(),
        )
    elif fixture == "trip":
        state = compositions.reduce(scene, compositions.TripArrives())
    elif fixture == "no-authority":
        state = compositions.reduce(scene, compositions.AuthorityLost())
    else:
        raise KeyError(fixture)
    return compositions.render_workbench(state)


def _build_patterns() -> tuple[PatternEntry, ...]:
    entries: list[PatternEntry] = []

    component_renderers: dict[str, Callable[[], str]] = {
        "button": lambda: partials.render_button(fixtures.button()),
        "numeric-input": lambda: partials.render_numeric_input(fixtures.numeric_input()),
        "rotary-control": lambda: partials.render_rotary_control(fixtures.rotary_control()),
        "reading-tile": lambda: partials.render_reading(fixtures.reading()),
        "alert-bubble": lambda: partials.render_alert_bubble(fixtures.alert_bubble()),
        "engineering-plot": lambda: partials.render_plot(fixtures.engineering_plot()),
        "digital-lanes": lambda: partials.render_lanes(fixtures.digital_lanes()),
        "data-table": lambda: partials.render_data_table(fixtures.data_table()),
        "panel": lambda: partials.render_panel(fixtures.panel()),
        "mode-banner": lambda: partials.render_mode_banner(fixtures.mode_banner()),
        "confirm-action": lambda: partials.render_confirm_action(fixtures.confirm_action()),
    }
    for component, render in component_renderers.items():
        entries.append(
            PatternEntry(
                row_id=f"e-1-components::{component}",
                fixture_id="canonical",
                kind="component",
                page=component,
                render=render,
            )
        )

    for severity in _keys("b-1-severities"):
        entries.append(
            PatternEntry(
                row_id=f"b-1-severities::{severity}",
                fixture_id=severity,
                kind="severity",
                page="alert-bubble",
                render=_severity_render(severity),
            )
        )

    entries.append(
        PatternEntry(
            row_id="b-3-reading-states::limiting",
            fixture_id="limiting",
            kind="state",
            page="reading-tile",
            render=lambda: partials.render_reading(fixtures.reading()),
        )
    )
    for fixture, row in (
        ("st-fresh", "ST-2"),
        ("st-stale", "ST-4"),
        ("st-no-cadence", "ST-1"),
        ("st-unavailable", "ST-3"),
    ):
        entries.append(
            PatternEntry(
                row_id=f"b-4-staleness::{row}",
                fixture_id=fixture,
                kind="staleness",
                page="reading-tile",
                render=lambda fixture=fixture: _staleness_variant(fixture),  # type: ignore[misc]
            )
        )

    for reason in _keys("c-2-disabled-reason-enum"):
        entries.append(
            PatternEntry(
                row_id=f"c-2-disabled-reason-enum::{reason}",
                fixture_id=reason,
                kind="disabled-reason",
                page="button",
                render=_disabled_reason_render(reason),
            )
        )

    for code in _keys("c-3-refusal-mapping"):
        entries.append(
            PatternEntry(
                row_id=f"c-3-refusal-mapping::{code}",
                fixture_id=code,
                kind="refusal",
                page="refusals",
                render=_refusal_render(code),
            )
        )

    for mode in _keys("d-1-modes"):
        entries.append(
            PatternEntry(
                row_id=f"d-1-modes::{mode}",
                fixture_id=mode,
                kind="mode",
                page="mode-banner",
                render=lambda mode=mode: _mode_render(mode),  # type: ignore[misc]
            )
        )

    for fixture, row in (
        ("armed", "R-ENERGISE-1"),
        ("guarded-while-armed", "R-PROTECT-1"),
        ("trip", "R-PROTECT-1"),
        ("no-authority", "R-PROTECT-1"),
    ):
        entries.append(
            PatternEntry(
                row_id=f"c-1-safety-rules::{row}",
                fixture_id=fixture,
                kind="composition",
                page="confirm-action",
                render=lambda fixture=fixture: _composition_scene(fixture),  # type: ignore[misc]
            )
        )

    return tuple(entries)


#: The one registry: the row checkers' fixtures and the library pages share
#: it (no second mirror to drift — the census test derives its expectation
#: from the manifest keys, not a hand count).
PATTERNS: tuple[PatternEntry, ...] = _build_patterns()

_PAGE_TITLES: dict[str, str] = {
    "button": "Button",
    "numeric-input": "Numeric input",
    "rotary-control": "Rotary control",
    "reading-tile": "Reading tile",
    "alert-bubble": "Alert bubble",
    "engineering-plot": "Engineering plot",
    "digital-lanes": "Digital lanes",
    "data-table": "Data table",
    "panel": "Panel",
    "mode-banner": "Mode banner",
    "confirm-action": "Confirm action",
    "refusals": "Refusals",
}


def pages() -> tuple[str, ...]:
    """The library's page slugs: one per §E.1 component plus the refusal
    page (12), in §E.1's own order."""
    ordered = [key for key in _keys("e-1-components")]
    ordered.append("refusals")
    return tuple(ordered)


def entries_for_page(page: str) -> tuple[PatternEntry, ...]:
    return tuple(entry for entry in PATTERNS if entry.page == page)


def _read_css(path: Path) -> str:
    if not path.is_file():
        raise PatternExportRefused(
            f"the pattern library's styles are absent at {path} — the export "
            "inlines the REAL token CSS through G1a's path constants (one "
            "mirror, no copy); the re-point at G1e is a named checklist row"
        )
    return path.read_text(encoding="utf-8")


def _css_bundle() -> str:
    """tokens + themes + globals (fold F1): globals APPLIES the theme tokens
    to the html element, so the two themes actually render differently —
    the token definitions alone left every page pixel-identical across
    themes (lane B's refuter measured it)."""
    return "\n".join(
        _read_css(path)
        for path in (artifacts.TOKENS_CSS, artifacts.THEMES_CSS, artifacts.GLOBALS_CSS)
    )


@dataclass(frozen=True)
class ExportResult:
    """What the export wrote: the page paths (relative to the export root)
    and the themes."""

    pages: tuple[str, ...]
    themes: tuple[str, ...]
    index: str


def export(dest: Path) -> ExportResult:
    """Write the static tree under ``dest``: ``patterns/<theme>/<page>.html``
    for both themes plus ``patterns/index.html``. Plain rendered HTML files
    — no server; the browser lane navigates file:// URLs."""
    css = _css_bundle()
    written: list[str] = []
    root = dest / "patterns"
    for theme in THEMES:
        for page in pages():
            body = ENV.get_template("pattern-page.j2").render(
                title=_PAGE_TITLES[page],
                page=page,
                theme=theme,
                css=css,
                entries=entries_for_page(page),
            )
            target = root / theme / f"{page}.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
            written.append(target.relative_to(dest).as_posix())
    index = ENV.get_template("pattern-index.j2").render(
        pages=tuple(
            {"slug": page, "title": _PAGE_TITLES[page]} for page in pages()
        ),
        themes=THEMES,
        count=len(PATTERNS),
    )
    (root / "index.html").write_text(index, encoding="utf-8")
    return ExportResult(
        pages=tuple(written),
        themes=tuple(THEMES),
        index=(root / "index.html").relative_to(dest).as_posix(),
    )


#: The screenshot viewport (PRD §5 UR-05's browser Direction, non-binding:
#: a fixed viewport so re-exports are comparable).
VIEWPORT: ViewportSize = {"width": 1280, "height": 1024}


def capture_screenshots(dest: Path, browser: PlaywrightBrowser | None = None) -> int:
    """Capture one PNG per ``PATTERNS`` entry per theme into
    ``patterns/screenshots/<theme>/<row-id>__<fixture-id>.png`` — keyed by
    contract row + fixture so guide links survive re-export. Requires the
    ``browser`` extra (Playwright; lazily imported — the runtime dep set is
    untouched) and an installed chromium; pass an existing Playwright
    ``browser`` when one is already live (the browser lane), or the
    function opens its own (the docs build's standalone invocation — the
    two Sync APIs cannot nest in one process). Returns the number of
    screenshots; the caller asserts the count equals
    ``len(PATTERNS) * len(THEMES)``.

    Determinism (fold F1): every entry shoots on its OWN fresh page after a
    fonts-ready + double-rAF settle. Page reuse flapped the armed scene's
    full-page height by 1px (1209 first render vs 1208 warmed) — hidden
    warm-up state is exactly the nondeterminism class a baseline must not
    carry.
    """
    if browser is None:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            chromium = playwright.chromium.launch()
            try:
                return _capture_with(chromium, dest)
            finally:
                chromium.close()
    return _capture_with(browser, dest)


def _settle(page: PlaywrightPage) -> None:
    """Wait for fonts plus two animation frames — the deterministic-render
    settle (fold F1)."""
    page.evaluate(
        "() => document.fonts.ready.then(() => new Promise(r => "
        "requestAnimationFrame(() => requestAnimationFrame(r))))"
    )


def _capture_with(browser: PlaywrightBrowser, dest: Path) -> int:
    written = 0
    css = _css_bundle()
    for theme in THEMES:
        shots = dest / "patterns" / "screenshots" / theme
        shots.mkdir(parents=True, exist_ok=True)
        for entry in PATTERNS:
            # Each entry screenshots on its own FRESH themed page carrying
            # the same CSS bundle as the library pages (fold F1: the
            # scratch render is themed, not bare), settled before the shot.
            scratch = (
                "<!doctype html><html data-theme="
                f'"{theme}"><head><meta charset="utf-8">'
                f"<style>{css}</style></head>"
                '<body data-bw-pattern-library>'
                f"{entry.render()}</body></html>"
            )
            page = browser.new_page(viewport=VIEWPORT)
            try:
                page.set_content(scratch)
                _settle(page)
                # The record's `<row-id>__<fixture-id>.png` key with the
                # row-id's `::` flattened to `__` (a portable filename —
                # `:` is not legal in filenames on every host the lane
                # runs on).
                filename = f"{entry.row_id.replace('::', '__')}__{entry.fixture_id}.png"
                page.screenshot(path=str(shots / filename), full_page=True)
                written += 1
            finally:
                page.close()
    return written


__all__ = [
    "CONTRACT_MD",
    "ExportResult",
    "PATTERNS",
    "PatternEntry",
    "PatternExportRefused",
    "PatternKind",
    "THEMES",
    "VIEWPORT",
    "capture_screenshots",
    "entries_for_page",
    "export",
    "pages",
]
