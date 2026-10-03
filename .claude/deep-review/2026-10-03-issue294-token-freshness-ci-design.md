# Issue #294 — cross-repo token-freshness CI gate: design record

- **Issue:** madeinoz67/benchweave#294 (label `sdk` — the moving surfaces live in the
  SDK repository; the gateway diff is docs-only)
- **Verdict:** **BUILD**, one minimal slice, premise-corrected. The gate the issue
  literally specifies is unimplementable today (its two byte sets no longer exist);
  the risk it guarded against survives in a different shape and gets the machine
  check that shape admits.
- **Date:** 2026-10-03. Gateway base `c183db4` (origin/main); SDK base `d6dd0a3`
  (origin/main, post-I2b #98).
- **Standards touch:** none. No `standards/` bytes, no version strings added (the
  tripwire `git diff origin/main...HEAD -- standards/` is empty; the new test reads
  the pinned version, it never writes or hardcodes one — see R5).

---

## 1. Root cause and premise correction (evidence, not assumption)

### 1.1 What issue #294 asks for, and why that mechanism is gone

The issue (filed from the I1 design record's deferral D5) asks: *"standalone CI
compares its vendored `ui_assets/tokens.css` + `themes.css` against the canonical
`ui/src/styles` corpus … and fails on mismatch."* Both halves of that comparison
were deleted by later, already-merged work:

- **The vendored copies are gone.** The SDK's
  `src/benchweave_sdk_server/ui_assets/` at SDK `origin/main` contains
  `bw-plot.js`, `htmx.min.js`, `inventory.json`, `sse.js`, `standalone.css`,
  `uplot.*` — no `tokens.css`, no `themes.css`. The tokens now come from the
  **installed `benchweave-ui-html` package** at runtime:
  `benchweave-sdk/src/benchweave_sdk_server/assets.py` (`RENDERER_ASSETS`,
  `renderer_assets_root`, `verify_renderer_assets` — called by `build_app`,
  `web.py:85`). Its module docstring states the ruling: tokens/themes "come from
  the installed `benchweave-ui-html` package (PRD 12 Q5: freshness arrives by
  release and an exact pin bump in this repository, never by a copied template —
  **the pin closes design record I1's deferral D5**)."
- **The canonical `ui/src/styles` path is gone.** `git ls-files ui/` on gateway
  main returns 0 tracked files (only untracked build artifacts remain). The
  canonical token corpus is `packages/ui-html/src/benchweave_ui_html/assets/`
  (`tokens.css`, `themes.css`, `globals.css`, `inventory.json`), shipped as the
  `benchweave-ui-html` wheel.

The mechanism change is the #309 packaging fold (SDK commit `0dc9826`, PR #92,
"the published ui-html wheel is consumed at an exact pin"), whose design record
`.claude/deep-review/2026-10-03-issue309-sa-preview-design.md` §4.6 is titled
"Consuming the published `benchweave-ui-html` wheel (Q5, NFR-P2, **I1-D5's
closure**)" and states: *"The I1 design record is frozen history (never
retrofitted); its §2 placement and D5 are superseded by this record."* PRD 12 §8
Q5 (`docs/implementation-planning/12-gateway-web-ui-prd.md:287`) rules the
mechanism: a contract change reaches the standalone host *"through a package
release and a pin bump in the SDK repository, never through a copied template."*

So: **byte-for-byte drift between a vendor copy and the canonical corpus is
structurally impossible now** — there is one byte set (the wheel), and it is
digest-verified at serve time by the package's own inventory
(`verify_renderer_assets` → the package's `verify_vendored_assets`, refusing
startup on mismatch). The issue's requested comparison has nothing to compare.

### 1.2 The risk that survives, in its new shape

The #309 record itself names the residual (its R5): *"the ui-html exact pin lags
the gateway's workspace tree … This is Q5's designed behavior, not a defect — but
**forgetting the bump is the real risk**. Mitigation: the obligation-12 drift row
amendment names the pin as a motion surface (D-B5's trigger)."*

Today that mitigation is **prose only**. Verified state of every cross-repo
token/lock surface (survey 2026-10-03):

| Surface | Byte integrity (machine-checked) | Freshness / provenance (machine-checked) |
|---|---|---|
| SDK host assets `ui_assets/` | yes — `inventory.json` digests, verified every call (`assets.py::verify_ui_assets`) + regen-and-compare test | n/a (same repo) |
| Installed ui-html package bytes | yes — package's own verifier at `build_app` (`web.py:85`) | n/a (integrity) |
| SDK exact pin `benchweave-ui-html==0.1.0` (`pyproject.toml:52`, `uv.lock`) | `uv sync --locked` (CI) | **NOTHING** compares the pin to the latest published release |
| Pin *shape* (exact `==`, not a range) | **NOTHING** — a pyproject comment says "a range would re-open silent drift"; no test refuses a range | n/a |
| Registry `vendored/gateway/*` + `vendored/htmx/*` | yes — pin-record digest tests (`tests/test_styleguide_tokens.py`, `test_htmx_vendor.py`, `test_validate_release_status.py`) | repo-level only: warn-only `drift` job on `gateway-ref` (records.yml) |
| Registry pin citations (`madeinoz67/benchweave@<sha>:<path>` in `.pin.json`) | **NOTHING** — the test asserts `pin["source"] == ORIGIN` (a literal); nothing checks the cited commit exists on gateway main or carries bytes hashing to the pin | n/a |

Measured baseline (mine, 2026-10-03, gateway `c183db4` / SDK `d6dd0a3`):

- PyPI `benchweave-ui-html`: latest `0.1.0`, sole release. The founding pin is
  **current** — D-B5's trigger (first release past 0.1.0) has not fired.
- Gateway tree vs installed-0.1.0 wheel digests (sha256, first 16 hex):
  `tokens.css 76353723fd3e1265`, `themes.css 197eda5ad9d8bcf8`,
  `globals.css 3666401981bf801c` — identical both sides. The designed lag has
  not materialised. Honest negative: there is no live staleness to detect yet;
  the gate must be proven against a synthetic one.
- Registry citations: `gateway-ref` `45d5e7f` and styleguide pin `ba42dd0` are
  both ancestors of gateway `origin/main`. Current citations are durable — but
  the `release-status.pin.json` comment records that a citation once pointed at
  an unmerged branch tip and was re-cited **by hand** ("the fragile form"). That
  class has no machine check.

### 1.3 Root cause statement

D5's intent — *token freshness across repos must be machine-checked, not left to
discipline* — was carried forward by #309 into a pin-mediated world, but only the
integrity half got a mechanism (the exact pin + the package verifier). The
freshness half got a doc obligation (drift-and-obligations.md obligation 12) and
no signal. The failure mode is: gateway releases `benchweave-ui-html` >0.1.0,
nothing anywhere turns red or warns, the standalone host serves the old tokens
indefinitely, and nobody knows. That is the gate this design builds.

---

## 2. Mechanism (buildable as specified)

Three deliverables, CI/test-only, zero runtime code. The authority chain being
instrumented:

> gateway tree → (release pipeline, #302's lane) → **PyPI** → *(missing arrow,
> built here)* → SDK exact pin → (uv) → installed bytes → (package verifier) →
> served bytes.

### 2.1 SDK — pin-shape test (new `tests/test_ui_html_pin.py`, ~30 lines)

Extends the proven `tests/test_release_version.py` class (tiny `tomllib` +
pyproject assertion tests):

```python
"""The renderer pin discipline (PRD 12 Q5, gateway obligation 12).

The [server] extra pins benchweave-ui-html EXACTLY. A range would let
resolution drift the host's renderer bytes between installs — re-opening
the silent drift the exact pin exists to close (I1-D5's closure, #309
record §4.6). This test refuses the range shape and the removal.
"""
import re, tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_REQ = re.compile(r"^benchweave-ui-html==(\d+\.\d+\.\d+)$")

def test_server_extra_pins_benchweave_ui_html_exactly() -> None:
    extras = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
        ["project"]["optional-dependencies"]["server"]
    pins = [r for r in extras if r.startswith("benchweave-ui-html")]
    assert len(pins) == 1, pins            # present, not duplicated
    assert _REQ.fullmatch(pins[0]), pins[0]  # ==X.Y.Z, one specifier, no range
```

No version literal is written (the number is read, never asserted) — the SDK's
version-literal zero gate stays clean by construction.

### 2.2 SDK — pin-freshness lane (new `.github/workflows/pin-freshness.yml`)

A dedicated workflow (adding `schedule` to `ci.yml` would run the whole 3-OS
matrix on a timer; `codeql.yml` is the repo's existing scheduled-workflow
precedent):

```yaml
name: ui-html-pin-freshness
on:
  push: { branches: [main] }
  schedule: [ { cron: "23 4 * * 1" } ]   # weekly; staleness develops with no SDK activity
  workflow_dispatch:
permissions: { contents: read }
jobs:
  freshness:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@<pinned>  # same pin as ci.yml
      - name: Compare the [server] extra's ui-html pin to PyPI
        run: |
          python3 - <<'PY'
          # stdlib only: read pin from pyproject (tomllib), fetch PyPI JSON
          # (urllib, 3 retries), compare parsed version tuples.
          # pin == latest  -> print "pin CURRENT: <v>"
          # pin  < latest  -> print ::warning::... advance on the next train
          #                   (gateway obligation 12 / PRD 12 Q5)
          # ANY inability to determine (network, shape) -> raise (red job)
          PY
```

Posture decisions, each pinned to in-tree precedent:

- **WARN on staleness, never fail.** The pin is *designed* to lag between trains
  (Q5; #309 R5). A hard fail would force same-day bumps and contradict the train
  discipline. This is exactly the registry's `drift` job posture ("the CON-12
  staleness pattern … the pin advances deliberately per train",
  `benchweave-registry/.github/workflows/records.yml`, from the #223 publishing
  design F5).
- **Fail (red) on inability to determine.** PyPI unreachable or the pin
  unparsable is an honest unknown, and a green run would read as "fresh" — the
  substitution the project refuses. Same posture as the registry drift job,
  which lets a failed `ls-remote` fail the job.
- **NOT on `pull_request`.** PR authors cannot fix staleness; the state changes
  in the gateway, not the PR. Push-to-main records the state at each train's
  landing; the weekly schedule is the watcher for the no-SDK-activity case (the
  actual R5 scenario).
- **Single ubuntu job, seconds of CI.** No install, no matrix (OS-independent).

### 2.3 Gateway — obligation-12 amendment (docs-only, rides this issue's gateway PR)

`docs/internal/drift-and-obligations.md` obligation 12 gains one sentence naming
the SDK-side lane as the pin's freshness signal (so the "motion surface" named
there has a pointer to its detector), and the CI map gains a cross-repo row for
the SDK lane (the map already narrates sibling-repo jobs in obligation 27's
prose; the row makes it findable from the map itself).

### 2.4 Tracker

The issue #294 body's mechanism paragraph is superseded; the outcome comment the
main session posts (design-outcome posting rule) carries the premise correction
and this record's path. The issue's own stated carrier ("the I2
presentation/parity work, or the first `ui/src/styles` … commit") has **fired**:
I2a (#97) and I2b (#98) are merged — this design is the response, re-shaped by
#309.

---

## 3. Minimal first increment and explicit deferrals

**IN (slice 1):** §2.1 (test), §2.2 (workflow), §2.3 (docs amendment), §2.4
(tracker note). Nothing else. No runtime code, no schema, no standards bytes.

**DEFERRED — each with carrier and reopen trigger:**

| id | deferred | carrier | reopen trigger |
|---|---|---|---|
| D-1 | Registry citation-authenticity job: for each `vendored/**/*.pin.json` citing `madeinoz67/benchweave@<sha>:<path>`, shallow-fetch the cited commit, assert (a) it is an ancestor of gateway main, (b) sha256 of the bytes at the cited path equals the pin's `sha256` — making citations self-proving; catches the hand-caught "unmerged branch tip" class | the registry repo's publishing lane (its next repin train) | the first `.pin.json` added or repinned after this design merges, or the owner's call to fold earlier |
| D-2 | SDK wheel-vs-tree digest cross-check: at pin-bump time, compare the installed package's `tokens/themes/globals.css` digests against the gateway repo's bytes at the release tag (catches a wrong-wheel release the package's own self-verified inventory cannot) | the SDK bump train that follows the first post-0.1.0 release | a `benchweave-ui-html` release >0.1.0 existing on PyPI (obligation 12's own exercise trigger, #309 D-B5) |
| D-3 | Staleness escalation policy (scheduled WARNING → fail after N weeks, or auto-filed gateway issue) | the owner's F1 resolution below | the first scheduled WARNING persisting across ≥2 consecutive weekly runs with no bump train filed |

---

## 4. Precedent (why no new architecture)

- **Registry `drift` job** (`benchweave-registry/.github/workflows/records.yml`):
  warn-only `git ls-remote` staleness on the `gateway-ref` pin — the exact
  CON-12 staleness posture, twice-accepted by the owner (#223 design F5; the
  #309 record reaffirms). The freshness lane is this pattern applied to the
  PyPI-mediated pin, with ls-remote replaced by the PyPI JSON API.
- **SDK `ci.yml` cross-repo discipline steps**: `sync-standards --check` and the
  "Version-literal zero gate" step — SDK-own CI steps enforcing a
  cross-repo-discipline rule inside SDK CI. The pin-shape test extends this
  class; `tests/test_release_version.py` (tomllib + pyproject assertion) is the
  direct test-shape precedent.
- **Registry pin-record tests** (`tests/test_styleguide_tokens.py` et al.) — the
  pin-integrity test family this design's D-1 completes for the citation half.
- New architecture would be required only if the freshness authority were not
  already machine-addressable (PyPI's JSON API) — it is, so none is invented.

---

## 5. Invariant and drift impacts

- **Invariants:** no new rows, no amendments. CON-12 (`docs/internal/invariants.md:586`,
  the committed-authority/pure-render family whose staleness posture the registry
  drift job instantiates) is *applied*, not changed. The exact-pin mechanism is
  PRD 12 Q5's ruling — unchanged, now shape-enforced by §2.1.
- **Obligations (drift-and-obligations.md):** obligation 12 (renderer freshness /
  the SDK pin as motion surface) is the row this slice instruments — §2.3 adds
  the lane pointer. Obligation 27 (publishing-lane surfaces) is untouched
  (registry CI unchanged in slice 1). The CI map gains one cross-repo row.
- **Surfaces moved:** SDK repo (`.github/workflows/` + `tests/`) via its own PR;
  gateway repo (docs only) via this issue's gateway PR. Single issue stream: both
  PR bodies cite #294; the SDK PR notes no SDK-side issue exists by design.
- **On-disk formats / schemas: none.** No store, no migration, no lock rows
  moved (the pin already exists; `uv.lock` is untouched by this slice).
- **CI cost:** one ubuntu job, seconds, on SDK pushes to main + weekly. The
  pin-shape test adds <1s to the existing matrix lane.
- **Standards tripwire:** empty diff on `standards/`; no version strings.

---

## 6. Review tier and the Step-1 keyword scan (rubric #254)

Two diffs, stated per slice; **maximum tier: TIER 2.**

- **Gateway diff (docs only: the drift-doc amendment + this record):** Tier 1
  (docs, no Tier-3 path or keyword).
- **SDK diff (`tests/test_ui_html_pin.py` + `.github/workflows/pin-freshness.yml`):**
  Tier 2 — rubric Tier-2 rule "any other change to production or test code under
  … or `.github/`". Not Tier 3: no `standards/`, `contracts/`, `state/`,
  `registry/`, schema or fixture-lattice path; **no dependency added or
  re-pinned** (`pyproject.toml`/`uv.lock` rows are read, not moved); no submodule
  pointer (the gateway PR carries no pointer change — SDK-internal files only).

**Keyword scan over the whole expected slice-1 diff text** (docs + code, the
eight Step-1 keywords, counted over the skeletons in §2 as they will land,
comment text included):

`threading` 0 · `asyncio` 0 · `subprocess` 0 · `sha256` 0 · `hashlib` 0 ·
`migrate` 0 · `recovery` 0 · `protection` 0.

Design notes keeping it at zero honestly: the freshness lane compares *versions*,
never digests (digest comparison is D-2's lane, which will carry `sha256` and
take its Tier-3-scan consequences then); the test asserts specifier *shape*,
not bytes. The zero is by scope, not by euphemism — no protective or
digest-carrying text is being smuggled past the scan.

---

## 7. Pre-committed acceptance rule (written before any implementation number exists)

The premise-verification numbers in §1.2 were measured to establish the *design's
premise* (the survey of what exists); the rule below governs the
**implementation's** evidence, which does not exist yet. Deterministic arms make
sample size 1 sufficient; the only sampled quantity is network reachability.

**Metric A — the pin-shape test discriminates (RED control).** In a scratch
SDK checkout with the specifier relaxed to `benchweave-ui-html>=0.1.0`, the new
test MUST fail (collected ≥ 1, failures ≥ 1, read from junitxml/exit code — not
an output-filter line); restored to `==0.1.0` it MUST pass. Also RED under
outright removal of the requirement.

**Metric B — the freshness lane has exactly two machine-readable terminal
states.** (i) LIVE current: with the real PyPI index (expected first state:
pin 0.1.0 == latest 0.1.0), the run prints `pin CURRENT: 0.1.0` and exits 0.
(ii) SYNTHETIC warning: fed a replayed index response with latest `0.2.0`, it
emits the `::warning` annotation naming the pin, the latest, and the bump
procedure, and exits 0 (a warning is not a failure). (iii) Inability (offline /
malformed) MUST exit non-zero with the reason — a green run never means
"unknown". Run each state 3× to bound reachability flake.

**SHIP if** A shows red-then-green for both the range and the removal, AND B(i)
is live-green, AND B(ii) shows the synthetic warning, AND B(iii) reddens offline.

**KILL the mechanism if** A cannot be made RED by the relaxation (the test
proves nothing and no test of this shape is worth landing), or B produces any
state a human must interpret (no machine-readable terminal state ⇒ no gate, just
log noise), or the lane cannot be made to fail on inability (green-on-unknown
violates the honest-negative discipline and the job is worse than absent because
it *looks* like coverage).

**UNDERPOWERED, not conclusive, if** the live index still serves only 0.1.0 at
evaluation (then B(ii) stays mock-proven — disclosed, and the first LIVE warning
fire is deferred to D-2's trigger, the first post-0.1.0 release), or PyPI is
unreachable on the evaluation day (B(i) inconclusive — re-run within 48h; the
red job in the meantime is the honesty arm working, not a failure of it).

---

## 8. Top risks, each with its falsifier

- **R1 — warn-only lanes rot: nobody reads a weekly warning.** Falsifier: a real
  post-0.1.0 release lands and ≥2 weekly warnings accumulate with no bump train
  filed. That is D-3's reopen trigger verbatim; escalation (fail or auto-file)
  is the owner's F1 call, taken on evidence, not snuck in now.
- **R2 — PyPI reachability flake turns the lane red weekly.** Falsifier: repeated
  B(iii) reds across weeks. Mitigation in-slice: 3 retries; honest red otherwise.
  If flake persists, re-anchor the query (e.g. `uv`'s own resolution output)
  rather than widening the timeout silently.
- **R3 — the premise correction gets lost and someone "restores" byte-vendoring
  to satisfy the issue's literal text.** Falsifier: any PR adding
  `tokens.css`/`themes.css` copies under `benchweave_sdk_server/ui_assets/`. The
  §2.1 test refuses the *range* shape but cannot refuse a re-vendor; the guards
  are this record, the issue outcome comment, and PRD 12 Q5's "never a copied
  template" — the reviewer applying Q5 kills it.
- **R4 — keyword-scan honesty erosion.** The slice-1 diff carries zero keywords
  because it compares versions, not digests; D-2's diff will contain `sha256`
  and MUST take its scan then. Falsifier: a future fold that computes digests
  while claiming this record's zero-count. The per-slice statement here is the
  anchor the review re-derives against.
- **R5 — version-literal collateral.** The test reads the pin; if an
  implementation hardcodes `0.1.0` anywhere (test body, workflow text), the SDK
  version-literal zero gate reddens — by design. Falsifier: any literal in the
  slice-1 diff; the gate catches it before review does.

---

## 9. Forks for the owner

- **F1 — WARN vs FAIL on scheduled staleness.** Recommend WARN (CON-12 pattern;
  Q5's deliberate trains). FAIL is defensible only with an explicit grace policy
  — that is D-3, deferred to evidence.
- **F2 — run the lane on `pull_request` too.** Recommend NO (authors cannot fix
  staleness; an unrelated red door). `workflow_dispatch` covers on-demand runs.
- **F3 — fold D-1 (registry citation authenticity) into this increment.**
  Recommend DEFER: the registry lane is young, its pins are currently durable
  (§1.2), and its next repin is the natural carrier; slice 1 stands alone.

---

## 10. Gates for the implementing run

SDK lane: bare `uv run ruff check .` + fresh-cache bare `uv run mypy` + focused
`uv run pytest tests/test_ui_html_pin.py` (plus the full suite per the SDK
battery at push); RED evidence per Metric A in the PR body. Gateway lane:
docs-only fast lane (ruff + mypy bare, no test change beyond none-needed), full
battery before push per the standing two-lane rule. Counts read from
junitxml/exit codes, never a filtered summary line.
