# G1a design — renderer-neutral contract gate as a pytest plugin (issue #297)

**Verdict: BUILD**, with one sequencing fork ruled by the maintainer (F-A: G1a is the first
commit(s) of the G1 branch, not an independently mergeable slice). Triage call: this body
carries no person, client, bench, serial, commercial term, or install-specific operational
detail — public path as named is defensible.

## 1. Root cause / the problem this slice solves

The contract (`docs/internal/ui-contract.md`) is normative and machine-pinned, but its only
enforcement today is two vitest files in the React reference renderer
(`ui/src/contract-coverage.test.ts`, `ui/src/contract-enforcement.test.ts`). PRD 12 §6 R-1
orders that enforcement ported to a pytest harness **before any partial exists**, and that
the ported harness fail on every row against an empty renderer: *a harness that passes
against nothing is not a gate*.

A structural finding, verified while deriving the row counts (not assumed): the TS L1 test's
own enumeration is **stale relative to the contract**. Its docstring enumerates 144 rows
across 25 tables. The contract's own 28 `Schema: … — N rows` lines sum to **168 rows across
28 tables**. The gap reconciles to the docstring's own double-count (the 10 icon rows are
already inside its `5+15+4+3+3+6+10+1+4+3 = 54` slice-1 term) plus four tables outside the
enumeration: `#### §E.2.0 Pass-2 composition (channel_hints)` (4), `#### §E.2.1 Slot
mapping` (16), `#### §E.2.2 Sequences` (10), `#### §E.4.6 Decoder lanes` (4) — 34 rows.
144 − 10 + 34 = 168. (The original derivation below said "144 + 23 = 167" via
§E.2.0 + §E.2.1 + §E.4.4 — §E.4.4 is *inside* the docstring's `#244 S2 = 4+4+4+3+4 = 19`
term, not outside it; see the Build-time correction.) The gap was
silent because the TS test's docstring enumeration was documentation. The port must carry
the corrected 28-table manifest, and the PR must record the reconciliation.

## 2. The mechanism

**Collection is the parse.** A `pytest11` entry-point plugin registers a collector for
`docs/internal/ui-contract.md` (via `pytest_collect_file`). It emits two item families and
no test file:

| Layer | Items | Asserts | State at G1a |
|---|---|---|---|
| Pin | 28 (one per pinned table) | parse integrity + stated count + independent enumeration | **green** (the contract is landed and well-formed) |
| Row | 168 (one per pinned row) | the row's canonical artifact exists and satisfies its items | **all red** (empty registry) |

Item ids carry the row-id, so `-k`, junitxml names and CI greps are stable.

**Grammar** (ported from `contract-enforcement.test.ts:38-50` `contractTable` and
`contract-coverage.test.ts:27-40` `parseTable`, which already fail closed):

1. Exact heading match: `line.trim() === heading` (heading strings are literal, e.g.
   `"### §E.1 Components"`, `"#### §E.2.1 Slot mapping"` — the full 28-entry manifest is
   in §5).
2. Collect lines whose trim starts with `|` until the next line whose trim starts with `#`.
3. Header = first pipe row, separator = second (must match a pipe-dash pattern), body =
   `rows[2:]`. Cells split on `|`, trimmed, backticks stripped (`literal`).
4. **Fail-closed, never skip:** missing heading → error naming it; no table under the
   heading → error; header cells ≠ expected (cell-for-cell) → error naming both; body
   count ≠ stated count → error naming expected/actual; body count ≠ the enumeration
   entry → error (the independent second count).
5. The `Schema: \`<cells>\` — <N> rows` line is itself parsed: the backticked cell list
   must equal the actual header row (stated schema vs actual header agreement), and `N`
   is the stated count.

**Row layer / registry.** `row_id = "<heading-slug>::<literal(row[0])>"`. A fixture
registry maps row_id → Artifact. An artifact's `satisfies(row) -> list[str]` returns the
unsatisfied item descriptions; empty list = that row is green. Artifact kinds by table
shape: `component_render` (§E.1 — render the canonical fixture through the row's partial,
then assert each required attribute / role / class-hook / required-text item; the
`name` / `name=value` / `name~=substring` micro-syntax and the `~ ` item separator port
verbatim from ui-contract.md:22-34); `label_render` (§C.2 — key, data-bw-disabled-reason
attribute, visible label with the {state} slot resolved to the canonical blocking state
`idle`); `refusal_render` (§C.3 — severity attribute, what-happened, operator-action,
sent-status wording: NO -> "Nothing was sent.", UNKNOWN -> "It is unknown whether anything
was sent"); `token_pair` (§A.1) and `token_value` (§A.2-A.4) for CSS value equality both
directions; `slot_value` (§E.2.1), `hint_row` (§E.2.0), `severity_row` (§B.1), `mode_row`
(§D.1), `state_row` (§B.3), `triad_row` (§E.3), `icon_partial` (§F.1) for value/wording/
item assertions over the row's artifact; `rule_proof` (§B.2, §C.1, §E.2.3-E.2.6,
§E.4.x Property|Requirement rows) where the artifact is a named proof obligation (module +
test) that later slices discharge.

**The RED mechanism, one rule:** fail-closed on unknown or unregistered — never
pass-by-default. An unregistered row-id fails with `no canonical artifact for <row-id>`;
an unknown kind fails with `unimplemented row-kind: <kind>`; a role the resolver cannot
compute fails with `role-unresolvable`. No skip, no xfail, no empty-pass anywhere in the
row layer. Green-able per row: registering that row's artifact turns exactly that item
green and nothing else.

**The gate cannot be silenced where it is collected** (reworded at the F2 fold — the
original wording, "The gate cannot be disabled by configuration", overstated; see §15).
The fail-closed default is a module constant (`REQUIRE_ARTIFACT = True`); no ini option,
environment variable or marker flips THE CONSTANT — a harness unit test pins the
constant and the meta env arm pins the environment surface. What holds for the GATE as
a whole: a pure contract invocation stays red under a deselect (exit 5, nothing
collected) and under plugin disable (exit 4, uncollectable target). The residual class,
disclosed rather than fixed: a MIXED invocation (a tests/ path plus the contract path)
with `PYTEST_ADDOPTS="-m 'not contract'"` in the ambient environment deselects the
contract items and runs green — pytest applies `-m` at collection and the plugin cannot
distinguish that deselect from an operator's explicit one. A meta arm pins the mixed
invocation carrying all 196 contract items, so the suite itself reds under that attack.

**TOTALS:** 196 collected items = 28 pin-layer + 168 row-layer. At G1a the pin layer is
green and all 168 row items are red (empty registry).

## 3. Sequencing — the fork (F-A), ruled

The row layer is live-or-dormant, and R-1 forbids it being green without artifacts. A G1a
merged into main with a live gate leaves main's CI red until the partials land, which
merge-on-green will not permit. The binary is airtight: live-and-red or
dormant-and-passing-against-nothing. PRD §10 G1 is one increment whose internal order is
port gates → prove red against an empty renderer → implement partials until green →
delete; R-4 puts the ui/ deletion in the same change that makes R-1 to R-3 green.
Therefore: **G1a is the first commit(s) of the G1 branch.** The red-against-empty run is
an in-branch milestone whose junitxml evidence lands in the PR; the merge gate is green at
the G1 end. Consequence: until R-4, `ui/src/contract-*.test.ts` still enforce the contract
in the React CI, and ui-contract.md:16-20 naming them stays truthful. Obligation 12 is
rewritten at R-6, not here — no obligation gap opens during G1a.

## 4. Dependency boundary (UR-11)

Runtime dependencies: Jinja2 and MarkupSafe only. pytest is a TEST-ONLY dependency. The
harness module lives in the package (so the pytest11 entry point ships with the wheel) and
may import pytest; nothing in the runtime import path may import the harness module — a
harness unit test walks the package's import graph and fails if anything outside
`contract_harness/` imports it. pytest11 entry points are inert unless pytest is running,
so a host that installs the wheel for rendering never pulls pytest. HTML parsing:
stdlib `html.parser` over the rendered string. CSS parsing for token equality: regex over
`--name: value;` declarations inside a selector-matched block — the exact shape of
`cssBlock` in contract-coverage.test.ts; stdlib, no dep. Role assertions (UR-05) go
through a `RoleResolver` protocol that computes an accessibility tree from the rendered
HTML (implicit ARIA roles from element name + explicit role= attributes), never a CSS
selector stand-in; G1a ships a pure-Python resolver covering the roles the contract
actually names (§E.1 Required-roles cells), and a role it cannot compute fails with
`role-unresolvable` rather than passing. The browser-grade resolver (Playwright + axe,
UR-05 Direction and UR-09) lands later behind the SAME protocol as a test extra
`[project.optional-dependencies] browser = [...]`. Marker boundary: generated items carry
a `contract` marker; the `browser` marker arrives with the axe slice — when it does, the
fast lane may run `-m "not browser"` but the full battery must run them; a
deselect-by-default marker is a hole this design forbids.

## 5. The 28-table manifest (exact heading | header cells | stated rows)

1. `### §A.1 Colour palette` | Token, Light, Dark, Use | 25
2. `### §A.2 Spacing and layout` | Token, Value, Typical use | 6
3. `### §A.3 Radius` | Token, Value, Use | 2
4. `### §A.4 Typography fonts` | Token, Value, Use | 2
5. `### §B.1 Severities` | Severity key, Meaning, Dismissal class, Live region | 6
6. `### §B.2 State rules` | Rule id, Requirement | 3
7. `### §B.3 Reading states` | State key, Meaning, Rendering, Announcement | 1
8. `### §B.4 Staleness` | Rule id, Requirement | 4
9. `### §C.1 Safety rules` | Rule id, Requirement | 3
10. `### §C.2 Disabled-reason enum` | Key, Required label text, Parameter | 5
11. `### §C.3 Refusal mapping` | Code, Severity, What happened, Sent status, Operator action | 15
12. `### §D.1 Modes` | Mode, Fixed wording, Fires when | 4
13. `### §E.1 Components` | Component, Root element, Required attributes, Required roles, Required class hooks, Required text, Notes | 11
14. `#### §E.2.0 Pass-2 composition (channel_hints)` | Hint, Effect | 4
15. `#### §E.2.1 Slot mapping` | Slot i, Colour, Dash, Symbol | 16
16. `#### §E.2.2 Sequences` | Key, Shape description, Reference binding | 10
17. `#### §E.2.3 Y-axis assignment` | Condition, Rendering | 4
18. `#### §E.2.4 Reference lines` | Property, Requirement | 4
19. `#### §E.2.5 Acquisition disclosure` | Property, Requirement | 3
20. `#### §E.2.6 Trace provenance` | Provenance, Required marker, Disclosure, Constraint | 4
21. `### §E.3 Setpoint presentation (reading-tile sub-rows)` | Role, Placement, Required labelling, Never | 3
22. `#### §E.4.1 Lane layout` | Property, Requirement | 4
23. `#### §E.4.2 State rendering` | Property, Requirement | 4
24. `#### §E.4.3 Groups and buses` | Property, Requirement | 4
25. `#### §E.4.4 Edge-preserving decimation (NORMATIVE)` | Property, Requirement | 3
26. `#### §E.4.5 Time axis` | Property, Requirement | 4
27. `#### §E.4.6 Decoder lanes` | Property, Requirement | 4
28. `### §F.1 Icons` | Icon key, Class, Shape description, Reference binding | 10

TOTAL: 168 rows / 28 tables. Arithmetic over the contract's own 28 `Schema:` lines at the
read commit: 25+6+2+2+6+3+1+4+3+5+15+4+11+4+16+10+4+4+3+4+3+4+4+4+3+4+4+10 = 168. The
acceptance rule binds to the PARSED number; 168 is the expected value and the builder
reports the per-table counts in the PR. `### §E.2` and `### §E.4` are parent headings with
no table and no Schema: line — not pinned tables.

## 6. Token equality (UR-04) and inventory hashing (UR-10)

UR-04, both directions × both themes. Parse the `--bw-*` custom properties from the light
block of tokens.css and the dark block of themes.css (the cssBlock shape).
Contract → CSS: every §A.1 row's Light value equals that custom property's value in the
light block, and the Dark value in the dark block; §A.2-A.4 values likewise. CSS →
contract: every `--bw-*` custom property declared in the pinned blocks has a contract row
with the same value in the matching column; an extra CSS property with no row FAILS — the
"extra unpinned token" class, now enforced mechanically rather than by enumeration.

UR-10, deferred with the mechanism named (D3). The inventory (path + sha256 per vendored
asset, plus a digest over the inventory itself) and its serve-time verification are a host
concern and land with the asset-vendoring slice. G1a's token equality reads the two CSS
files by path and asserts values only. What G1a does pin: the token-equality source is
the same asset directory the future inventory will hash. Named deferral D3.

## 7. Precedents (in-tree)

Row-generated assertions from a parsed spec table + fail-closed parsing:
`ui/src/contract-enforcement.test.ts:38-50` (`contractTable` — throws on missing heading,
on no table) and `ui/src/contract-coverage.test.ts:27-40` (`parseTable`). The port is a
translation, not a redesign. "Row with no fixture fails": contract-enforcement.test.ts's
`expect(fixtures[row.component], ...).toBeDefined()` loop over every parsed row — the
red-by-construction arm the registry generalizes. Cell micro-syntax (name / name=value /
name~=substring, `~ ` separator, backtick literal): ui-contract.md:22-34, normative,
ported verbatim. Digest pinning of shipped bytes: pyproject.toml:62-77 (vendored assets
shipped verbatim, packaged-first) + `benchweave/vendoring.py`; fallback precedent for an
inventory-with-digests is the standards corpus-manifest sha256 rows. OPEN: the exact
hash-helper shape in vendoring.py (builder reads it; if it is a resolver rather than a
hasher, the corpus-manifest pattern is the precedent). pytest11 entry point in-tree:
OPEN — none in the root pyproject.toml as read; the builder checks packages/sdk and
tests/ before inventing one. If none exists this is the first, and the justification for
the new mechanism is that UR-02 requires a plugin (collect-time generation), which a
conftest cannot do for a non-Python target file. Workspace member shape: pyproject.toml
has NO `[tool.uv.workspace]` today. G1a adds it with `members = ["packages/ui-html"]`;
packages/sdk stays a submodule and is NOT a member (AGENTS.md two-repo discipline).
packages/ui-html must be LINTED, so it must not be added to `[tool.ruff]` extend-exclude
(which excludes packages/sdk), and it must be added to `[tool.mypy]` files. Root
testpaths stays `["tests"]`; the harness's own unit tests go in `tests/ui_html/` so the
existing pytest gate covers them with zero CI-config change.

## 8. Measurable proof — pre-committed acceptance rule

(Deterministic gate; no sampling, so exact cardinalities replace effect sizes. Counts read
from `--junitxml` attributes, never from a summary line; the three counts cross-check each
other.)

**METRIC A — RED against the empty renderer.** With the fixture registry empty (zero
partials, zero vendored CSS):
`UV_PROJECT_ENVIRONMENT=venv uv run pytest docs/internal/ui-contract.md -q --junitxml=/tmp/g1a-red.xml`
— expected 196 collected = 28 pin + 168 row; the row layer reads 168 collected / 168
failed / 0 passed / 0 skipped / 0 xfailed (the primary assertion, layer-scoped by item
name prefix); pin layer 28 collected / 28 passed; suite totals `tests="196"
failures="168"` as additional evidence from the same junitxml; exit code non-zero.

**METRIC B — fail-closed mutations**, each on a scratch copy of ui-contract.md, one at a
time: (1) delete the `### §A.1 Colour palette` heading line → the §A.1 pin item fails,
message names the table and the missing-heading class; (2) delete one §C.3 body row → the
stated-count pin fails (parsed 14 vs stated 15); (3) rename one §E.1 header cell
(Required roles → Roles) → the header-cell pin fails, naming both; (4) change `— 25 rows`
to `— 24 rows` under §A.1 → the stated-count pin fails. Each must leave the run red with
the pin item naming the table and the defect class.

**METRIC C — green-able per row.** Register a fake artifact for the `button` row only →
exactly 1 of the 168 row items turns green; the other 167 stay red. Over-broad matching
(more than one green) and ignored registration (zero green) both kill.

**MECHANISM-TOGGLE CONTROL (the RED check).** Flip `REQUIRE_ARTIFACT` to False, re-run
Metric A → the run must go fully green (196 passed). This proves the 168 failures come
from the fail-closed default and not from incidental parser errors. Revert. A harness
unit test pins that no external configuration can flip the constant.

**PRE-COMMITTED KILL DIRECTIONS** (written before any number is looked at). SHIP iff A, B
and C all hold exactly as stated (168/0/0/0, all four mutations caught,
exactly-one-green). KILL if: any row passes at empty registry; any mutation class is
undetected; the RED failure count does not equal the collected row count; the package's
runtime import path pulls in pytest (UR-11 violated); or the mechanism-toggle control
does not turn the run green. INVALID MEASUREMENT (not a result) if: the pin layer itself
fails on the unmodified contract (the parser is wrong — a RED run with pin-layer failures
is a broken measurement, not evidence), or the collected item count differs between the
RED run and the mutation runs under the same invocation (nondeterministic collection,
e.g. an xdist interaction — re-run without xdist before concluding anything).

## 9. Top risks

1. G1a alone reddens main (the live-or-dormant binary). Mitigation: G1a rides the G1
   branch; the red stage is evidenced in-branch. Falsifier: if a live row layer can be
   green with zero artifacts, the binary is wrong — that would mean R-1 is unsatisfiable
   as written and the requirement itself needs a ruling.
2. The 167 total is arithmetic, not a run. Mitigation: acceptance binds to the parsed
   number; the builder reports per-table counts in the PR. Falsifier: the parser's sum is
   not 167 at the read commit.
3. The stale enumeration (144) would fail well-formed rows if copied. Mitigation: the
   harness carries the 28-table manifest; the PR records the 144+23=167 reconciliation.
   Falsifier: the 23-row arithmetic does not hold at build time.
4. Pure-Python role resolver fidelity. Mitigation: the resolver is a protocol; the
   browser-grade resolver is the named follow-on; uncomputable roles fail rather than
   pass. Falsifier: when the Playwright+axe resolver lands, any row it calls red that the
   pure-Python resolver called green kills the G1a resolver's authority retroactively —
   run that disagreement check in the axe slice.
5. Generated items under xdist / junitxml xunit1. Mitigation: the collector is pure (no
   ordering dependence), item ids stable; RED evidence taken under a plain invocation
   with counts cross-checked. Falsifier: counts differ between plain and `-n auto` runs.

Minor, recorded: mypy strict on pytest.Item subclassing may need targeted ignores if the
installed pytest does not ship py.typed — build-time detail, not a design risk.

## 10. Invariant, drift and CI impact

No CTL/STO/CON/REG invariant changes — presentation-layer test infrastructure only. No
on-disk format, no schema, no standards-corpus bytes. Drift obligation 12 still names the
TS tests as the enforcement until R-6 rewrites it; G1a does not delete ui/, so no
obligation gap opens. Standards-involvement tripwire: `git diff origin/main...HEAD --
standards/` must be empty for G1a. Expected diff: `packages/ui-html/**` (new), root
`pyproject.toml` (workspace table, pytest11 entry point, optional extras, mypy files),
`tests/ui_html/**` (new), and the design record. ZERO ui-contract.md bytes move — all 28
tables already carry stated row counts. CI cost: one new collection target plus ~200
trivial generated items (milliseconds) and one new package in the lint/mypy lanes. No new
CI job at G1a.

REVIEW TIER: Tier 2 (source + tests + tooling config; no on-disk format, no schema, no
standards bytes, no trust boundary). Step-1 keyword scan over the EXPECTED diff text (to
be re-run over the actual diff at PR open): schema 0, migration 0, on-disk 0, standards/
0, trust 0, credential 0, sha256/digest at least 1 only in the UR-10 deferral comment.
`token` appears many times as CSS custom-property names — NOT a credential/tier-3
keyword and the scan must not count it as one. Tier rises to 3 only if the actual diff
touches standards/, a corpus manifest, or introduces a persisted inventory file with a
pinned format.

## 11. Deferrals (explicit, named)

D1 partials + canonical fixtures (UR-01, G1b) — the registry stays empty until then.
D2 browser-grade a11y-tree role resolution + axe in CI (UR-05 Direction, UR-09) — same
RoleResolver protocol; browser test extra + marker.
D3 inventory hashing + serve-time verification + one-inventory-two-hosts (UR-10) — G1a
pins only that token equality and the future inventory read the same asset bytes.
D4 pattern library, static export, screenshots (UR-06, UR-13).
D5 series-colour / lane / LTTB proof ports (R-2), composition proofs (R-3), ui/ + Node
CI deletion (R-4), obligation-12 rewrite (R-6), styleguide rewrite (R-7).
D6 the §6 enumeration update (the three missing tables) folds into G1a's manifest; the TS
docstring is not edited (it dies with ui/).

## 12. Maintainer decisions

F-A (ruled 2026-10-01): G1a is the first commit(s) of the G1 branch. F-B (ruled): the
pure-Python role resolver is G1a's authority, with the browser-grade resolver as the
named follow-on behind the same protocol. F-C (ruled): the 28-table manifest (168 rows)
is the corrected enumeration, superseding the TS docstring's 144.

## 13. Open items (named, not guessed)

The exact hash-helper shape in `benchweave/vendoring.py` (precedent for D3) — OPEN for
the builder. Whether any in-tree pytest11 entry point already exists (packages/sdk,
tests/) — OPEN; if none, this is the first and §7's justification applies. The precise
implicit-role table the pure-Python resolver must cover — the builder extracts the role
names from the §E.1 Required-roles cells and pins exactly those, no broader.

Files cited: docs/implementation-planning/12-gateway-web-ui-prd.md (§5 UR-01 to UR-05,
UR-10, UR-11; §6 R-1; §9 Q5; §10 G1 row); docs/internal/ui-contract.md (authoring rule
:14-34, §A.1 :49-80, and the 28 Schema: lines); ui/src/contract-coverage.test.ts;
ui/src/contract-enforcement.test.ts; pyproject.toml.

## 14. Build-time correction (2026-10-01, build pass — appended before commit 1)

The build brief's count tripwire ("if your count differs from 28/167, STOP and report")
fired before any commit was made. The design's 167 was hand arithmetic derived from the
TS docstring; the measured count is **168 rows across the same 28 tables**. Ruling from
the controller (2026-10-01): build to the measured 168; this section records the
correction so the record shows both the original claim and what changed.

Evidence — three independent sources, all agreeing on 168:

1. The contract's own 28 `Schema: … — N rows` lines: stated counts
   [25,6,2,2,6,3,1,4,3,5,15,4,11,4,16,10,4,4,3,4,3,4,4,4,3,4,4,10], sum 168, each
   matching its table's parsed body exactly (0 stated-vs-body mismatches).
2. Parsed bodies (this design's grammar: pipe rows until the next heading, body =
   rows[2:]): 168 rows, 168 unique row ids, no empty or duplicate key cells.
3. The TS gate's own live assertions (`contract-coverage.test.ts`): the "92 definition
   rows" test (20 tables) + the 8 remaining pinned tables (25+6+2+2+11+4+16+10 = 76)
   = 168.

Where the original derivation went wrong: the TS L1 docstring's "144 rows / 25 tables"
double-counts the 10 icon rows (already inside its `…+10+… = 54` slice-1 term) and
omits four tables — §E.2.0 (4), §E.2.1 (16), §E.2.2 (10), §E.4.6 (4) = 34 rows — and
§E.4.4, which the original named as unenumerated, is in fact inside the docstring's
`#244 S2 = 4+4+4+3+4 = 19` term. Correct decomposition: 144 − 10 (double-counted
icons) + 34 (four omitted tables) = 168.

§5's manifest list carries the corrected per-table counts. Three entries were
mis-transcribed relative to the contract (Schema lines + parsed bodies + TS live
assertions agree on the corrected values):

- `#### §E.4.2 State rendering`: 3 → **4** — this is the +1 that made the original
  total 167 instead of 168;
- `#### §E.2.4 Reference lines`: 3 → **4** and `#### §E.2.5 Acquisition disclosure`:
  4 → **3** — an adjacent swap, net zero against the total but wrong per table.

Also corrected in place: §1's reconciliation paragraph (the corrected decomposition
replaces "144 + 23 = 167"; the original three-table gap list named §E.4.4, which is
enumerated), §2's row-layer cardinality and TOTALS line (168 rows; 196 = 28 + 168),
§5's TOTAL and arithmetic string, §8's Metric A (196 collected; row layer 168
collected / 168 failed / 0 passed / 0 skipped layer-scoped by item-name prefix, pin
layer 28/28 passed, suite totals tests="196" failures="168"), Metric C (1 of 168
green, 167 stay red), the mechanism-toggle control (fully green at 196 passed) and
the kill-direction cardinality (168/0/0/0), and §12's F-C line (168 rows). §9 is left
verbatim as the pre-committed risk register: its risk 2 falsifier ("the parser's sum
is not 167 at the read commit") fired exactly as designed, and the tripwire plus this
ruling are the mitigation working. One further inaccuracy in §1 noted here without
rewriting it: the TS body does not "only hard-code two row-count assertions" — it pins
counts for §A.1, §B.1, §C.2, §C.3, §D.1, §E.1, §F.1, §E.2.0-§E.2.2, §B.3 and §E.2.3
and exact key lists elsewhere; the staleness lived in the docstring enumeration, not
the assertions.

The acceptance rule's SHAPE was pre-committed — exact cardinalities, the four
fail-closed classes, the per-row green-able control, the mechanism toggle, the
no-external-config pin, and the kill directions. The cardinality constant is
corrected to 168 before any measurement runs; no measurement was taken against 167.

## 15. Fold note — refute F1/F2 (2026-10-01, appended after the adversarial refute)

**F1 HIGH, ruled FOLD:** the pin layer as first built pinned STRUCTURE (heading present,
header cells, stated and enumerated counts) — not IDENTITY. Five corruption classes ran
green while the TS gate reds on them: (a) a row swapped between equal-count same-schema
tables (§E.4.1 ↔ §E.4.5); (b) a mid-table interleaved non-pipe line under §E.1 (the
ported L2 grammar collected all pipe rows to the next heading and skipped it); (c) §A.1
token delete-and-pad; (d) §E.4.5 delete-and-pad plus a duplicated whole §A.1 section;
and the forward kill — with a satisfying artifact registered for every parsed row (the
G1b end state), all of it ran 196/196 green exit 0, the deleted row's artifact sitting
orphaned and a duplicated key binding two row items to one artifact.

Three mechanisms landed (commit `a162273`), each RED-first against the refuter's exact
classes:

1. **Ordered key lists** — every manifest entry pins its exact ordered key cells (168
   literal keys; the coupling IS the pin, the same shape as the TS fold-P5 key arrays).
   Defect class `wrong row keys` names the first divergence: the §E.4.1/§E.4.5 swap
   reds both tables ("first divergence at index 2: expected 'Hidden lanes', got
   'Cursors'" and the mirror), delete-and-pad and reorder red on the key list with
   counts and header cells still green.
2. **Contiguity** — the table region ends at the first non-pipe line after the header
   (the TS parseTable stop semantics, closing the TS/Python parity divergence at its
   root). Defect class `table interrupted`; the body truncates at the gap, so the
   count and key pins red as well.
3. **Orphan check** — `ArtifactRegistry.orphaned_artifacts(row_ids)`: every registered
   key must be a row the contract parses, else collection fails with `orphaned
   artifact: <ids> (registered for rows this contract does not parse)`. A new control
   arm registers an artifact for every manifest key against the pristine contract and
   asserts the run fully green (196 passed, exit 0) — the G1b end state is
   legitimately green and the orphan check false-positives on nothing.

What the key-list pin still does not catch (the honesty rule): a duplicated PINNED
SECTION pasted cleanly elsewhere in the file under a repeated heading is invisible to
this gate AND to the TS gate — both parse the first occurrence of a heading. The
refuter's class (d) reds here via its §E.4.5 key-list half; a duplicate-heading
detector (assert each pinned heading occurs exactly once in the file) remains OPEN as
a named follow-up. Non-key CELL corruption (a mutated non-first cell) is also not the
pin layer's job — it is the row layer's, once G1b's artifacts assert their items
against the parsed row; at G1a, with an empty registry, every row is red regardless.

**F2 MEDIUM, ruled FOLD:** "The gate cannot be disabled by configuration" overstated.
`PYTEST_ADDOPTS="-m 'not contract'"` on a MIXED invocation (a tests/ path plus the
contract path) deselects the gate and runs green (the refuter's repro: exit 0, 17
tests, zero contract items). §2's claim is reworded above to what holds — the gate
cannot be SILENCED where collected; pure invocations red under deselect (exit 5) and
plugin disable (exit 4) — and the mixed-invocation deselect via ambient env is the
disclosed residual, pinned by a new meta arm asserting the mixed invocation carries
all 196 contract items (the arm itself goes red under the attack).
