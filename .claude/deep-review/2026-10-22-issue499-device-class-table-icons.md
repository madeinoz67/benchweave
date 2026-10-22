# Issue #499 follow-up — icon cells for the generated device-class table

Date: 2026-10-22
Branch: `fix/device-class-table-icons`
Slice: one (this record covers the whole diff — generator, gate, nothing else)

## Tier call (design-time, issue #254)

**Tier 2** — the diff touches `scripts/assemble_docs_site.py` and
`tests/contract/test_docs_site_device_classes.py` (the Step-1 "any other
change to production or test code under `scripts/`, `tests/`" rule; no
Tier-3 rule fires).

Step-1 keyword scan over the expected diff text (code and docs alike),
keywords and counts: `threading` 0, `asyncio` 0, `subprocess` 0,
`sha256` 0, `hashlib` 0, `migrate` 0, `recovery` 0, `protection` 0.
No standards-governor surface is touched (`standards/`, contract locks,
the SDK vendored tree, version strings: none).

## The defect, measured

The principal read the published page
(`docs/v/dev/user-guide/device-classes.html`) and reported two defects:
the table needs horizontal scrolling to reach the preview column even on
a large display, and the State and Preview cells should be icons. The
first was reproduced and root-caused on a locally built site (great-docs
0.17.0, the CI tree, IBM Plex loaded — CDP on a headless Chrome, not
eyeballed):

- The table's rendered width is its max-content width, **962 px** — the
  parenthetical corpus title in the Class cell and the slot sentence in
  the planned State cell are the width.
- The docs theme wraps every content table in a scroll region
  (`responsive-tables.js`: `.gd-table-scroll[role=region]` with
  `overflow-x: auto`), so a table wider than its column scrolls instead
  of squeezing.
- The content column (the page carries a ~300 px sidebar) is narrower
  than 962 px below ~1280 CSS px viewport: measured overflow TRUE at
  1024 and 1100 (table right edge 1198/1224 vs viewport), and at 1280
  the fit was two pixels of margin — a maximised-window coincidence, not
  a design. Any narrower browser window, or the same window with the
  sidebar expanded, scrolls.
- Content-driven, proven in-page: stripping the titles and shortening
  the State prose shrank the same table from 962 px to its 561 px
  container. No CSS invariant forces the width.

## The design

- **State cell** — one inline Lucide SVG (tick = implemented, clock =
  planned) inside a span that carries the machine-readable token
  (`data-state="implemented|planned"`, plus `data-slot="L<n>"` on
  planned rows) and an accessible label. The planned label keeps the
  full honesty sentence — `Planned (post-MVP, future slot L18)` — as the
  row's `aria-label`/`title`, so the slot stays available (hover, screen
  reader, gate) without rendering as cell prose. The visible cell is the
  icon alone.
- **Preview cell** — a link icon (Lucide link) where a preview exists,
  wrapped in the same `<a href="device-classes/class-<slug>.html">` URL
  shape as before; a plainly inert dimmed dash (opacity 0.45, no href,
  `data-preview="none"`) where it does not.
- **Class cell** — the machine slug stays in the code span; the corpus
  title moves into a `<span class="dc-title">` styled `display: block`,
  smaller and dimmed under the slug, wrapping freely. The parenthetical
  in the cell is the width the defect removed.
- **Styles** — the page carries its own `<style class="dc-table-style">`
  block, generated WITH the table (not hand-kept beside it), every rule
  scoped through `table:has(.dc-state)` so no other table on the site is
  touched. The renderer passes a body style block through verbatim —
  probed on the real great-docs 0.17.0 build before committing to the
  mechanism, not assumed. Icons are inlined SVG stroked with
  `currentColor` (no CDN, both colour schemes theme them; the link icon
  picks up the anchor's link colour in dark mode, which reads as an
  affordance). Both icon wrappers pin `font-size: 1rem` so the theme's
  anchor styles cannot resize one column's icons relative to the other.
- **Gate** — `tests/contract/test_docs_site_device_classes.py` T2/T2b
  re-pinned to the icon grammar (closed state vocabulary via the token,
  slot equality against the plan row, title-span equality against the
  corpus title, preview href shape, inertness — no `href` — for planned
  rows) and a new T2d pins the style block. The derivation arms (T1,
  T3–T8) are untouched: a class file is implemented, a plan row is
  planned, the corpus wins for a landed slug, the derived state is never
  authored.

## Acceptance rule and proof

Pre-committed by the dispatching brief before any measurement ran: no
horizontal scroll at 1280, 1440 and 1920 CSS px, with the table's own
`scrollWidth` not exceeding the viewport width; browser verification
through the sanctioned CDP path only; full-page screenshots in both
themes.

- RED (updated gate, unchanged generator): 26 collected, 3 failed —
  `t2` (state cell `'Implemented'` not icon-shaped), `t2b` (same, closed
  vocabulary arm), `t2d` (style block absent). GREEN after the
  implementation: 26/26.
- Fixed page, measured (table scrollWidth vs viewport; document
  scrollWidth equals clientWidth at every width — no page scroll):
  1024 → 535 (right edge 772), 1100 → 561 (823), 1280 → 663 (964),
  1440 → 749 (1087), 1920 → 749 (1327). The table now compresses with
  its column instead of holding 962 px; the pre-fix build overflowed at
  1024 and 1100.
- Icon paint, machine-verified in both themes: all 24 icons non-zero
  boxes; stroke `currentColor` resolves (light `rgb(33,37,41)`, dark
  `rgb(224,224,224)`); `data-bs-theme` and the body background flip with
  the emulated colour scheme (the light and dark screenshots are
  genuinely different themes, not one theme twice).
- Full assembly of the branch tree (tagged regime, v0.4.0 bucket
  included): `verification OK ... 545 pages`, exit 0.
- Full-page screenshots (lane scratch, not committed):
  `.wt/tableui-8f4c/scratch/screens/device-classes-light-1440.png`,
  `device-classes-dark-1440.png`, `device-classes-dark-1280.png`. Pixel
  decoded: the light shot's page ground samples rgb(238,241,240) with
  ~3.1k near-white pixels in the table band; the dark shot's ground
  samples rgb(27,32,39) — the configured dark navbar colour — with ~3.1k
  near-black pixels; the band carries 88 distinct colours in both (icon
  strokes, borders, code text), so neither is a blank capture.

## Invariant impacts

None of CTL/STO/CON/REG. Obligations row 30 (the device-class table
surface) holds in substance: state is still derived, never authored; the
plan record still carries slug and slot only; the planned rows still
name post-MVP future slots (in the icon's accessible label and token
rather than cell prose); the previews are still byte-identical copies.
No version-bearing surface moves.

## Deferrals

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D1 | The pre-existing `run_bucket_build` crash when `--dest` sits outside the repository root in the tagged regime (`scripts/assemble_docs_site.py`, the `dest.relative_to(REPO)` log line at the lift) — out of this slice's bounds; worked around by building with a dest inside the build tree | documentation here | any run of `scripts/assemble_docs_site.py` with an external `--dest` in the tagged regime fails at that log line — reproducible on demand by the README's own `--dest /tmp/site-preview` advice once a release tag exists |
| D2 | Icon treatment is not retrofitted to the site's other tables | documentation here | a second site table whose `.gd-table-scroll` region scrolls at a viewport of 1280 CSS px or wider, measured the same way |
| D3 | The mockup pages (`class-*.html`) keep their own prose state badges — the brief bounds this slice to the generated table | documentation here | the owner asks for the mockups' badges to match the table's icon vocabulary |
