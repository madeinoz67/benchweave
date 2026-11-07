# Design — issue #501: bound the gateway docs assembly's children and its Build Docs job

Date: 2026-11-07 · Repo: benchweave (gateway) · Tracker: gateway #501 (single issue
stream; the SDK twin's work tracked under #475/#476)
· Precedent record: `packages/sdk/.claude/deep-review/2026-10-19-issue476-docs-exit-path-design.md`
(merged in the SDK, refuted twice — its F1/F3/F4 folds and its second addendum are load-bearing here)

**Verdict: BUILD** — with one premise correction to the issue's scope item 2 (§3): the
gateway has no `--from-repo` call site, so the literal marker `Site built successfully`
never appears in this repository's child output. The issue's *principle* (watch the OUTER
completion line, never the inner banner) transfers; its literal does not.

---

## 1. The defect, verified in this tree (not from the issue text)

`scripts/assemble_docs_site.py` (current `main` @ `084c5e6c`):

| Site | Lines | Shape |
|---|---|---|
| `run()` helper | :177-182 | `subprocess.run(..., capture_output=True, text=True, env=env)` — **no `timeout`**, and captured output is printed only on non-zero exit, so a hung child shows nothing live |
| `ref_has_config` | :693-698 | direct `subprocess.run`, no timeout |
| bucket-mode build | :1655-1657 | direct `subprocess.run([great_docs, "build", ...])`, no timeout |
| `tag_ymls` loop | :1683-1688 | direct `subprocess.run(["git","show",...])`, no timeout |
| dev build (tagged regime) | :1716-1718 | direct `subprocess.run`, no timeout |
| zero-tag build | :1722 | direct `subprocess.run`, no timeout |
| bucket child (`uv run`) | :1564-1581 | through `run()` → unbounded, fully captured |

`.github/workflows/docs.yml:35-38`: the `build-docs` job carries no `timeout-minutes` —
GitHub's 360-minute default is the only frame.

The hang class is proven on the twin, not yet observed here: SDK run `38758274375`
(completion banner as last log line, 5m54s silence, cancel; at cancel the runner killed
`great-docs` and two `python3.13` grandchildren). Root cause is named upstream in the SDK
record (§2 there): great-docs 0.17.0 prints its banner and then never exits on CI — the
hang lives in interpreter shutdown, and the banner is provably `build()`'s final statement
(`core.py:16389-16393`, single-version arm `:16507-16513`). The gateway runs the same
pinned tool (`docs.yml` installs `great-docs[svg]==0.17.0`) through the same invocation
shapes, with **no bound at all** where the SDK at least has `GREAT_DOCS_TIMEOUT=900`.

Live corroboration (2026-11-07): SDK run `42335082486` sat in `Build Docs` >20 minutes
against a ~6-minute gateway baseline and completed green at 24m53s — the twin's
multi-version reality, under its 45-minute frame. The gateway has no frame.

### The CI shape today (measured, this session)

`git ls-remote --tags origin 'refs/tags/v*'` → **exactly one remote tag: `v0.4.0`**. So
each Build Docs job runs **two** great-docs invocations: the parent's dev build
(`--versions dev`, a direct child) and the v0.4.0 build inside **one** bucket child
(`run_bucket_build` → `uv run ... --bucket v0.4.0`, which runs the *tag's own frozen
script* — its inner great-docs call is also unguarded, and cannot be fixed retroactively:
tag bytes are frozen). Twenty further `vX.Y.Z` tags exist **locally only** (not pushed);
CI never sees them (§7 R7).

Measured green `build-docs` job durations (gh API, 2026-11-06/07):
6m18s, 5m36s, 6m43s, 4m28s (runs 42335093073, 42296614805, 42196305966, 42190113279) —
max **6m43s**, n=4; the issue's 6m37s baseline is consistent.

## 2. Precedent — the mechanism being ported (all file:line from `packages/sdk/scripts/assemble_docs_site.py`, the merged post-fold shape)

- Bounds + marker regexes + reclaim ceilings: :84-133 (`GIT_TIMEOUT=60`,
  `GREAT_DOCS_TIMEOUT=900`, `OK_BANNER_HEAD_RE`, `SITE_READY_RE`, `FAIL_BANNER_RE`,
  `RECLAIM_TERM_TO_KILL_S=10.0`, `RECLAIM_GROUP_DEADLINE_S=30.0`).
- `log()` flush: :158-161 ("an unflushed print is exactly the invisible phase issue #475
  chased").
- `run(cmd, *, cwd=None, timeout=None, stream=False, done_marker=False, grace=30.0)`: :164-204.
- `_forward_and_mark` (daemon reader; forwards every line flushed, time-stamps first marker
  sight; per-kind rules): :207-234.
- `_wait_group_empty` (wait for the *property* — group empty, no zombies; ESRCH=empty,
  EPERM/success=members-may-remain): :237-256.
- `_reclaim_group` (win32 loud refusal; SIGTERM → wait → group SIGKILL → wait; R6
  disclosure): :259-305. `_join_reader`: :308-314.
- `_run_marker_guarded` — four endings, all loud: **E1** child exits (real code honored),
  **E2** OK marker + hang past grace (group reclaimed, `""` returned, masked exit code
  disclosed in the log), **E3** FAIL marker + hang (reclaim, loud SystemExit), **E4** no
  marker, no exit (outer timeout, now with group reclaim before the named SystemExit): :317-384.
- Call-site discipline: great-docs sites get `timeout=GREAT_DOCS_TIMEOUT` + a marker kind;
  git helpers get plain `GIT_TIMEOUT` (`ref_has_config` keeps direct `subprocess.run` with
  `timeout=GIT_TIMEOUT` because the returncode IS the answer: :394-404; `guard_dest`
  through `run()`: :856-858).
- Workflow frame: SDK `docs.yml` `build-docs` carries `timeout-minutes: 45` with the
  derivation in a comment (8 green runs, max 20m42s, 2.2×, growth headroom).
- Test template: `packages/sdk/tests/test_assemble_run_guard.py` (525 lines, 13 arms) with
  byte-capture fixtures `tests/fixtures/great_docs_0.17.0_{inproc_banner,isolated_tail}.txt`.

This is the proven in-tree mechanism (core principle 9); nothing here invents architecture.

## 3. Premise correction the code forces (issue scope item 2)

The issue says: *"The port must use the OUTER completion line for the `--from-repo` call
site … Use `Site built successfully`, from `great_docs/core.py:16734-16736`."*

The gateway **has no `--from-repo` call site**. `run_bucket_build` (:1520-1541) replaces
it — the module docstring says why (:908-918): the gateway's docs tree is a two-phase
build with gitignored staging, so an isolated `--from-repo` build of a tag finds no
staging; instead *"the tag's own assembly script is what the bucket build runs"*. The
`--from-repo` wrapper's `Site built successfully` line (printed only after that wrapper
copies into `--output-dir`) is therefore **never emitted anywhere in the gateway's
process tree**. Porting `SITE_BUILT_RE` verbatim would be a dead marker: E2 could never
fire and the bucket child would degrade to the E4 bound — the port would look identical
to the fix while protecting nothing.

The issue's principle survives and transfers, one level up (this is the SDK fold F1
lesson, generalized): the watched line must be the OUTER process's statement that its
work is done — after every copy/lift — never the inner build's banner. In the gateway:

- The **inner banner appears on the parent's pipe** (the tag's script invokes great-docs
  uncaptured — verified at v0.4.0's script line 1416 and current :1655-1657 — so it
  inherits the child's stdout) **well before the child's own work is done**: staging
  cleanup, `replace_dir` lift, `rename_standards_section`, corpus copy, pattern-library
  export, previews, favicons, llms.txt, `verify_tree` all still run after it. A marker on
  the inner banner truncates a healthy assembly — the exact defect the SDK's F1 lane
  reproduced at 1337/3000 files.
- The gateway's OUTER completion line is the bucket child's own final statement:
  `log(f"assembled bucket {args.bucket} at {dest}")` at current :1676 (immediately before
  `return`; same wording in the v0.4.0 tag's script, its :1435 — the marker contract
  holds against the frozen tag bytes CI actually builds).

**Marker kinds for this port:** `"inproc"` (banner-box conjunction, FAIL outranks — F3)
for the three *direct* great-docs builds; a new `"bucket"` kind watching only
`[assemble] assembled bucket <tag> at <path>` for the `uv run` child. `SITE_BUILT_RE` is
not ported.

## 4. The mechanism (build-ready)

One commit, three files + fixtures.

**`scripts/assemble_docs_site.py`:**

1. Constants (SDK :84-133 shape): `GIT_TIMEOUT=60`, `GREAT_DOCS_TIMEOUT=900`,
   `OK_BANNER_HEAD_RE`, `SITE_READY_RE`, `FAIL_BANNER_RE`, `RECLAIM_TERM_TO_KILL_S=10.0`,
   `RECLAIM_GROUP_DEADLINE_S=30.0`; plus `BUCKET_DONE_RE =
   re.compile(r"^\[assemble\] assembled bucket \S+ at \S")` and
   `SUBMODULE_TIMEOUT=300` (network fetch of the SDK repo on a cold runner; the 60s
   family is for local single-object lookups — the SDK's own wording, :88-89).
   The comment block carries the marker contract, pinned to great-docs 0.17.0, naming
   issue #501 and both marker kinds with the §3 reason the inner banner must not complete
   the bucket marker.
2. `log()` gains `flush=True` (SDK :158-161).
3. `run()` extended to the SDK signature **plus the gateway's existing `env=` parameter**
   (the SDK has no `env`; the gateway's help-capture and bucket child need it — thread it
   into both the plain `subprocess.run` and the guarded `Popen`). Plain path: timeout →
   `SystemExit` naming the command (SDK :198-199).
4. `_forward_and_mark` / `_wait_group_empty` / `_reclaim_group` / `_join_reader` /
   `_run_marker_guarded`: verbatim ports (SDK :207-384) with two deltas — the `"bucket"`
   marker kind (only `BUCKET_DONE_RE` completes OK; inner banner and inner FAIL lines
   deliberately ignored, the F1 rule one level up) and `env` pass-through. The E2
   disclosure log line is the SDK's (:376-379) with the marker kind named.
5. Call sites:
   - `capture_standards_help` :344-348, `release_tags` :686, `guard_dest` :1495 →
     `timeout=GIT_TIMEOUT` (local helpers; the help capture is a local interpreter run).
   - `ref_has_config` :693-698 and the `tag_ymls` `git show` :1683-1688 → stay direct
     `subprocess.run`, gain `timeout=GIT_TIMEOUT` (SDK :394-404 precedent: the returncode
     is the answer, so routing through `run()`'s non-zero refusal would be wrong).
   - `run_bucket_build`: `git clone`/`git checkout` :1551-1552 → `GIT_TIMEOUT`;
     `git submodule update --init` :1553 → `SUBMODULE_TIMEOUT`; the `uv run` child
     :1564-1581 → `run(..., timeout=GREAT_DOCS_TIMEOUT, done_marker="bucket")`.
   - The three direct great-docs builds (:1655-1657, :1716-1718, :1722 — the last two
     collapse into one guarded call on the existing `if tags:` split) →
     `run(..., cwd=REPO, timeout=GREAT_DOCS_TIMEOUT, done_marker="inproc")`, replacing
     the direct `subprocess.run` + returncode checks (output now forwards live instead of
     streaming only on success — the #475 "silent phase" fix rides along).
6. Module docstring: a bounds/marker paragraph mirroring the SDK's, naming #501.

**`.github/workflows/docs.yml`:** `build-docs` gains

```yaml
    # Issue #501: measured green build-docs max 6m43s (n=4, 2026-11-06/07) — 45m is
    # ~6.7x max, covers one full 15-minute script-level backstop window with margin,
    # and matches the SDK twin's frame. A hang fails the job loudly here instead of
    # sitting silent for the runner's 6h default.
    timeout-minutes: 45
```

**`tests/unit/test_assemble_run_guard.py`** (new; import via the existing
`importlib.util` loader shape from `tests/unit/test_assemble_docs_site.py:14-20`) and
**`tests/fixtures/great_docs_0.17.0_{inproc_banner,isolated_tail}.txt`** (byte-captured
real 0.17.0 runs, copied from the SDK twin's fixtures with the provenance named in the
test docstring — real captures, never hand-edited). Arms, grace/timeout scaled, from the
SDK template plus the gateway deltas:

a. inproc: fake child (exact fixture banner bytes, then hang, holding two sleeping
   grandchildren) → success < grace+15s, group empty afterwards (`killpg(pgid,0)` →
   `ProcessLookupError`), 3 trials.
b. clean-exit child → success, real exit code honored (non-zero → named SystemExit), no
   reclaim log (E1 pays no grace).
c. fail-banner hang → `SystemExit` naming the command; OK-then-FAIL → E3 (F3).
d. **bucket kind**: fake child printing the inner banner (which must NOT complete the
   marker), work lines, then `assembled bucket vX at /p`, then hang → success after the
   bucket line only; and the F1-generalization control — same child hung right after the
   inner banner *without* the bucket line, timeout=10s → named-timeout SystemExit.
e. lone `Site ready` line does not complete the inproc marker.
f. regex tripwires: fixtures match `OK_BANNER_HEAD_RE`/`SITE_READY_RE`; the real FAIL
   shape (`[FAIL] Build failed at Step …`) matches `FAIL_BANNER_RE`; `BUCKET_DONE_RE`
   matches the current tree's final-line format **and v0.4.0's** (the tag CI builds).
g. SIGTERM-ignoring grandchild → SIGKILL escalation, group empty (second-addendum arm);
   zombie-leader reap arm; win32 loud-refusal arm (the repo's 2 windows-latest lanes run
   it; POSIX group arms carry the twin's `POSIX_ONLY` skip).
h. `env` forwarding through the guarded path (gateway delta; drives a child that reads an
   env var the parent set).

## 5. Minimal first increment — explicit deferrals

In: the runner port + call-site bounds + both marker kinds, the `timeout-minutes` frame,
the test module + fixtures, this record. **Out:**

- Upstream great-docs issue for the banner-then-no-exit root cause — already owned by the
  SDK record's deferral list; stays there.
- Marker watching for git helpers — none exists in the twin either; plain timeouts are
  correct for them.
- Any artifact-verification addition — `bucket_source()` (:1598) and `verify_tree()`
  already gate what a reclaimed run may claim; the runner learns nothing about artifacts.
- `timeout-minutes` on `publish-docs` (an 18s job; the issue names `build-docs`).
- Widening mypy to `scripts/assemble_docs_site.py` — the gateway's `files` list excludes
  it (pyproject `[tool.mypy]`), exactly as the SDK's does; this slice keeps that boundary.
- Cleaning the 20 unpushed local `v*` tags (operator hygiene, not code; noted at §7 R7).

## 6. Invariants, drift, tier, CI cost

- **Hard invariants: none touched, none gained.** The only invariants naming this script
  are the CON-13-class website-stamp anchors (`docs/internal/invariants.md:975` —
  `website_stamp_map`/`stamp_website`), untouched by this change. Governing instincts:
  A06 (a banner is not a completed process; the masked exit code is disclosed and the
  artifacts stay gated by `verify_tree`) and A11 (§3's premise correction is published,
  not quietly worked around).
- **Surfaces that move:** `scripts/assemble_docs_site.py`, `.github/workflows/docs.yml`
  (one key + comment), `tests/unit/test_assemble_run_guard.py`,
  `tests/fixtures/great_docs_0.17.0_*.txt`, this record. No submodule pointer, no
  dependency, no standards tree, no on-disk format or schema — not a Tier-3 trigger by
  the format rule.
- **Drift obligations:** no row in `docs/internal/drift-and-obligations.md` names the
  assembler's subprocess handling or the build-docs frame (the rows naming the script are
  about the standards-CLI page :568-569, device classes :694, and the runtime-schema
  derivation :448 — all untouched). The twin-copy relationship itself is the drift
  surface this port *reduces*.
- **Review tier (design-time call, #254): Tier 3** — mandatory adversarial refute. Rule:
  the diff text contains `subprocess` and `threading` (rubric :42, first-match-wins).
  Expected whole-diff keyword scan (code + tests + workflow comment + this record):
  `subprocess` ≈ 40+, `threading` ≈ 8-12, `asyncio` 0, `sha256` 0, `hashlib` 0,
  `migrate` 0, `recovery` 0, `protection` 0. The reviewer re-derives; a deviation is a
  finding, not a retune.
- **CI cost:** one pytest module, ~15s, in the existing matrix (2 windows legs run the
  win32-refusal arm only). docs.yml runtime unchanged.

## 7. Top risks, each with its falsifier

- **R1 Marker drift** (a future great-docs changes the banner or a future tag's script
  changes the completion wording) → E2 degrades to the E4 bound. Falsifier: arm (f)
  pins both regex families against captured bytes and the current + v0.4.0 script
  wording; the docs.yml pin comment couples them to 0.17.0.
- **R2 Real work after the watched line** — grace would truncate it. Inproc: the banner
  is provably `build()`'s final statement. Bucket: `assembled bucket … at …` is the
  script's final statement before `return`. Falsifier: re-read both tails on any pin
  bump (the §8 reopen trigger); the F1 lane already falsified the naive single-marker
  version, which is why the kinds are per-call-site.
- **R3 False-positive marker** (output quoting marker text). Inproc: the two-string
  conjunction + FAIL-outranks. Bucket: the `[assemble] assembled bucket ` prefix is
  script-authored, once, after `verify_tree`. Falsifier: grep real run logs for the
  literals; tighten if co-occurring.
- **R4 setsid changes child behavior.** Falsifier: the real-tool companion (§8.2).
- **R5 Frozen-tag residual:** v0.4.0's bucket child hangs *inside its own unguarded
  script* → the bucket marker never fires → E4 bounds it to a loud 900s red, not a
  rescue. Disclosed scope boundary; post-fix tags self-heal (their scripts carry the
  guard). Falsifier: none available for frozen bytes — the E4 log names the phase.
- **R6 `uv run` under the guarded path** loses `env` or cwd → bucket child breaks.
  Falsifier: arm (h).
- **R7 Local tag soup:** 20 unpushed local `v*` tags make a local *full-parent* assembly
  refuse at `check_registration` (correct behavior — CI sees only v0.4.0). Build agent:
  local real-tool companions use `--bucket` mode (which runs before the registration
  checks), never the parent path.

## 8. Acceptance rule — pre-committed before any harness run

Mechanism-level proof is local (the CI defect does not reproduce locally — the twin's
§2.3 negative result carries over). Grace/timeout scaled in tests; production defaults
30s grace / 10s TERM→KILL / 900s outer / 45-min job frame.

1. **GREEN — mechanism present.** From the repo root with
   `UV_PROJECT_ENVIRONMENT=venv`, `uv run pytest tests/unit/test_assemble_run_guard.py`:
   all arms (a)-(h) pass; the module runs in <60s; collected count > 0 (a "no tests ran"
   is a failed check). The three-trial inproc arm (a) must show group-empty on every trial.
2. **Real-tool companion.** `uv pip install --python venv/bin/python "great-docs[svg]==0.17.0"`
   (per the vault's venv lesson — pipx-installed great-docs drops the CLI reference), then
   `uv run python scripts/assemble_docs_site.py --bucket v0.4.0 --dest /tmp/... ` (§7 R7:
   bucket mode precedes registration): ends via E1 in ≈ the build's own time (accept
   <10 min), success, reclaim log ABSENT (proves the normal path pays no grace), and the
   bucket tree assembles (verify_tree passes).
3. **RED control (G3, review-time).** Neutralize only the mechanism (`done_marker=False`
   at the guarded call sites), keep the harness; hang child, timeout=20s: elapsed ≥18s,
   outcome is the named-timeout SystemExit, and ≥1 grandchild alive at return — today's
   orphan-leak shape. That red-then-green pair is the proof the effect is the mechanism.
4. **Field rule (post-merge, pre-committed).** Over the gateway's next 20 Build Docs runs
   (pushes + PRs): **PASS** = zero runs exhibiting the #501 signature — a completion
   banner or a bucket child's completion line as the last assemble-step output with the
   step not ending within 120s of it — and zero runs killed by the 45-minute frame on a
   commit whose tree is otherwise green. **KILL** = ≥1 occurrence (reopen #501; the E2/E4
   log names the phase, so marker drift and a new hang class are distinguishable).
   **UNDERPOWERED** = the window closes with <10 runs that completed a full assembly —
   roll the rule forward unchanged rather than declaring victory.
   **Reopen triggers, independent of the field rule:** any bump of the great-docs pin
   re-opens the marker contract (re-derive the regexes, re-read `build()`'s tail — the
   twin's rule); any release tag whose script words the completion line differently
   re-opens the bucket marker (arm (f) catches it pre-merge because each future tag
   builds from the then-current tree); measured green build-docs runs exceeding 30m
   (tag growth) re-derive `timeout-minutes`.

---

## Addendum — 2026-11-07: adversarial refute findings folded

The Tier-3 refute (pass required by review rubric G6; the diff carries `subprocess` and
`threading`) returned **five findings, all LOW or NIT, and no defect reachable through
ordinary operation**. F1-F3 and the design-level items are folded below. The body of this
record is left as written — frozen bytes are not retrofitted; corrections land here.

### F1 (LOW) — E1 leaked a surviving grandchild and misattributed the warning — FIXED

*Repro (refute, macOS, real branch runner):* a child prints the inproc banner, spawns
`time.sleep(120)`, then `sys.exit(0)`. Pre-fix, E1 returned the instant `proc.wait()`
fired; the descendant outlived the step (observed reparented to PID 1), held the inherited
pipe write end, so `_join_reader` stalled its full `RECLAIM_TERM_TO_KILL_S` and logged
*"a pipe writer outside the child's group?"* — false, because the survivor was inside the
group and merely alive.

*Reachability:* requires a guarded child that exits 0 while a descendant lives. Neither
real child does this (great-docs and the bucket `uv run` child both wait on their own
subprocesses), so this is a hardening class, not an active defect. It was reachable only
from a synthetic child.

*Fold:* `scripts/assemble_docs_site.py` now reclaims on E1 before joining the reader, so
all four endings agree that the group is empty and that warning can only mean what it
says. Pinned by
`tests/unit/test_assemble_run_guard.py::test_a_clean_exit_that_leaves_a_grandchild_still_reclaims_the_group`,
which reddened before the fix with the exact signature above (`_group_is_empty` False, plus
the false-cause warning) and passes after it.

### F2 (LOW) — setsid'd children escape parent death and terminal SIGINT — DISCLOSED

SIGKILL of the guarded parent mid-grace leaves the child and its grandchildren alive,
reparented to launchd and still session leaders. For a local `--bucket` run this means
Ctrl-C no longer reaches the build child, which pre-#501 shared the terminal's foreground
group. CI is unaffected: the runner VM is ephemeral, and pre-#501 evidence
(run 38758274375) shows orphans surviving cancel even without setsid.

*Why it is not fixed here:* the escape is an inherent property of
`start_new_session=True`, which is the same flag that makes group reclamation possible at
all. Both are inherited verbatim from the twice-refuted SDK twin, which did not catch it
either. A `PR_SET_PDEATHSIG`-class self-bound is the real fix and belongs in one change
made to both copies.

### F3 (LOW) — the 45-minute frame understates the compound-hang worst case — COMMENT CORRECTED

Per-child E4 worst is 900s timeout + 10s TERM wait + 30s KILL wait + 10s join = 950s. A
one-tag job carries **two** guarded windows plus a 420s bucket preamble (60 + 60 + 300),
~5 x 60s git helpers and ~3min setup: an all-hang sum of roughly **46 minutes**, which the
45-minute frame would cut before the last E4 could name its phase. The realistic
single-hang case lands near 23 minutes, comfortably inside, and the measured-green margin
(6.7x over 6m43s, n=4) is unchanged.

*Fold:* the `docs.yml` comment now says the frame bounds the realistic single hang and
names the compound case explicitly, instead of claiming it "covers one full 15-minute
script-level backstop window". The frame value is deliberately unchanged: it is sized
against measured green runs, and the field rule's frame-kill counter is the instrument that
would catch a genuine compound hang.

### F4 (NIT) — the port is three deltas, not two — CORRECTED HERE

The body's §4 says "verbatim ports (SDK :207-384) with **two** deltas — the `bucket` marker
kind and `env` pass-through." The mechanism carries a third: the SDK twin's
`assert out is not None` becomes a loud guard at gateway
`scripts/assemble_docs_site.py:330-332`:

```python
if out is None:  # stdout=PIPE by construction; the guard refuses loudly, never -O-silent
    raise SystemExit("internal error: guarded child has no output pipe")
```

This is an improvement, not a regression: under `python -O` the twin's assert vanishes and
its reader thread would die on `for line in None`, silently degrading every guarded run to
E4-only. The gateway guard is `-O`-proof and loud. But a set named in prose must be
regenerable from the mechanism, and "two" was not. The third delta is named here so the
enumeration and the diff agree.

### F5 (NIT) — two missing surfaces, and a "holds" that outran its evidence — CORRECTED HERE

**(a)** §6's "Surfaces that move" lists five; the diff moves seven. Unlisted:
`tests/contract/test_docs_site_versioned.py` (two `fake_run` stubs widened from
`(cmd, *, cwd=None, env=None) -> str` to `(cmd, **_kwargs: Any) -> str` so they do not
`TypeError` on the new keyword arguments; the stubs pin the command literal, not the
bounds) and `tests/win_core_manifest.json` (registers the new module).

**(b)** §3 says the marker contract "holds against the frozen tag bytes CI actually
builds". Measured against the tag itself: `git show v0.4.0:scripts/assemble_docs_site.py`
gives `log()` as `print(f"[assemble] {msg}")`, with **no flush**. The gateway's own `log()`
comment states the consequence — the completion line must leave the child's stdio buffer at
once or the parent can never sight it, "so for them the marker degrades to the E4 bound
(disclosed, R5)". The wording of the sentence was true of the *wording*: the regex matches
the tag's line, which was verified against the bytes. It was not true of the *sighting*.

Corrected statement: **the wording holds; sighting degrades to the E4 timeout bound on
frozen tags whose `log()` lacks the flush.** For v0.4.0, which is the only tag CI builds
today, E2-for-bucket is therefore not established and the working protection is E4 alone —
which is why the 900s bound is not a belt-and-braces extra but the primary defence on the
frozen path. Tags cut after this fix carry the flush and get both.

### Note on F1's fix shape

The refute's suggested fix reclaimed only when `reader.is_alive()` after the join. The fold
reclaims unconditionally instead, because a descendant that closed its own stdout would not
hold the pipe, so the conditional version would leave exactly that leak in place. The
unconditional `killpg` is one syscall on an empty group and cannot reach outside the child's
own session, so the cost is nil and the coverage is strictly wider.

### Carried residual (unchanged from the body)

The frozen v0.4.0 tag's own inner `great-docs` call is unguarded forever. The parent's
bucket marker bounds a hang there to a loud 900s red; it cannot rescue it. Tags cut after
this fix self-heal.
