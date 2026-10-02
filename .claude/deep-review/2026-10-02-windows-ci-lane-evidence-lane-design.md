# The Windows CI lane — an evidence lane over the gates selection

**Design record** · 2026-10-02 · Tracking: the owner's session directive
(2026-10-02); serves issue #207 (D2 arrival), #329 deferral D2, and the
#241/#329 Windows-evidence triggers named below · Tree: `origin/main` at
`3f4ad11` (verified at design start; local checkout was stale at `ddff1c1`
and every code citation below is read from `origin/main`, not the working
tree).

Standards tripwire, stated: this diff moves no standards bytes
(`git diff origin/main...HEAD -- standards/` will be empty; no version
strings touched). Constraint honored: no self-hosted runners — the repo is
public, GitHub-hosted `windows-latest` runners are free.

## 0. Premise established, not assumed

**The gap this closes.** Two Windows-compatibility batches (#237, #329) have
landed on this repository with the same verification framing, stated in each
PR body: *"no Windows CI leg, so the Windows executions are
contributor-attested"*. The contributor census on #207 (a full-suite run at
`a5fd51d`, re-run at `019a2ba`) is the only Windows execution evidence that
exists. #329's design record carries this as deferral D2 verbatim:

> a Windows CI leg (or standing contributor rig) — converts every
> simulated-Windows proof in this batch into lane evidence, and gives the two
> intermittent `sqlite3.OperationalError` disk-I/O items
> (`test_kill_mid_disposition_leaves_neither_audit_nor_deletion`, the ar5a
> item) a place to be reproduced — home: issue #207 (owner call on close,
> §5 AR-8) — trigger: owner/team decision.

The owner's 2026-10-02 directive IS that trigger firing. This increment is
D2 arriving, in its named shape: a GitHub-hosted Windows lane whose purposes,
in the owner's stated priority order, are (1) convert contributor-attested
findings into CI-proven evidence, (2) give the two intermittent sqlite
disk-I/O census items a reproduction surface, (3) let Windows-keyed evidence
triggers fire on real reds instead of attested ones.

**What already works on Windows (verified in-tree, not assumed).** The
platform is not foreign to this codebase:

- The store's single-writer hold has a first-class win32 branch —
  `src/benchweave/state/hold.py:37-51` (`msvcrt.locking` with
  `LK_NBLCK`/`LK_UNLCK`, EACCES mapped to `BlockingIOError`) beside the
  POSIX `fcntl` branch; the sibling docstring (`hold.py:76-80`) even records
  a Windows behavior verified against `MoveFileExW` (a directory containing
  any open descriptor cannot be renamed, WinError 5).
- The census itself: 2048 passed / 17 failed / 2 errors at `a5fd51d`, then
  the deterministic families fixed by #237 (separator/CRLF writes in test
  fixtures, `as_posix()` export keys, LF-pinned repin fixtures, traversal
  fixture containment) and #329 (tzset guard via `getattr`, conversion-free
  exhaustion rendering, capability-probed dispose arms, row-B ceiling
  relativization).
- The testing convention is already platform-conditional by capability
  probe, "never a skip" (`docs/internal/drift-and-obligations.md`, testing
  conventions: the #207 lineage is the cited example).

So the lane is not opening a new platform frontier; it is instrumenting a
platform the code already carries first-class branches for.

**Currency risk, stated plainly.** The census is stale as of `019a2ba`.
Since then the tree absorbed #241 slice 4, the #244 digital_lanes train,
#300 G1d (the browser lane + pattern export), and #329 itself. Every test
added by those trains has executed on Windows zero times. The lane's first
runs are therefore a fresh census, not a corroboration-only formality —
which is precisely why the posture below is evidence-first.

## 1. The load-bearing gotcha, resolved from the repo's own machinery: CRLF at checkout

The hazard: GitHub's Windows runner images ship Git for Windows with
`core.autocrlf=true` system config. Unmitigated, checkout rewrites every
text blob LF→CRLF in the working tree. This repository's admission and
test surfaces digest **working-tree bytes**:

- `src/benchweave/control/documents.py:713` — `raw = path.read_bytes()`;
  `hashlib.sha256(raw)` feeds `load_document` (`content/json_document.py:40`,
  the CON-1 exact-byte decoder — bytes-in, digest-over-bytes).
- `src/benchweave/standards/manifest.py:857` and `:908` —
  `hashlib.sha256(path.read_bytes())` for corpus-manifest row digests.
- `documents.py:339` — the classification cache key digests
  `path.read_bytes()`.

A CRLF-rewritten checkout would fail these by construction — manufactured
false reds across the corpus, export, and pin tests.

**The repo already solved this, deliberately.** `.gitattributes` at the repo
root (verified on `origin/main`):

```
# Preserve the exact document bytes used by contract digest fixtures on every OS.
* text=auto eol=lf
```

`eol=lf` on every path **overrides `core.autocrlf` at checkout**: text files
materialize with LF bytes (worktree == index bytes), auto-detected binaries
pass through untouched. The SDK submodule (`packages/sdk`, the only
submodule — `.gitmodules` verified) carries the same file with the failure
mode named in its own comment: *"a CRLF checkout would fail every digest"*.

**Design consequence: the lane needs NO git-config step.** Adding
`git config core.autocrlf false` would be belt-and-braces with a cost (a
mutating step before checkout is awkward to sequence with `actions/checkout`;
and config-level disable is redundant where the attribute already binds).
The committed `.gitattributes` pair IS the mechanism; the lane trusts it and
— better — **proves it every run**: any regression of the attribute (an
edit, a new submodule without one) presents as a deterministic digest-mismatch
red in this lane first, on the OS where the failure mode lives. The lane is
the canary for the byte-exactness posture, not a consumer that needs
protecting from it.

Residual, named: a future THIRD repo added as a submodule without its own
`eol=lf` attributes would be rewritten on Windows checkout. No such
submodule exists; the addition is the reopen trigger for revisiting a
workflow-level guard (see the deferral table, D7).

## 2. Posture: evidence-only first (continue-on-error on the test step), graduate by deleting one line

**The finding that decides it.** `main` has NO branch protection (verified:
`gh api repos/madeinoz67/benchweave/branches/main/protection` → 404 "Branch
not protected"). Blocking in this repository is enforced entirely by the
rollup discipline — `scripts/merge-verified.sh` refuses on any `fail` or
`pending` line in the complete `gh pr checks` output (#181 R1). Two
consequences:

1. A plain gating `windows` job needs no protection-settings change to
   block — a red job conclusion reds the rollup and the tool refuses.
   Graduation later is zero-config.
2. Conversely, an ungated red would block every merge through the tool the
   day it appears — including merges of PRs whose authors cannot see or fix
   a Windows platform failure. With three active developers and a census
   that is a week stale (§0), day-one reds are expected, and their meaning
   on day one is **evidence, not blocker** (owner purpose (1)).

**The mechanism.** `continue-on-error: true` on the pytest STEP only.
Setup steps (checkout, uv sync, key materialisation) carry no
continue-on-error: a broken lane blocks like any broken CI, which is the
honest split — setup red means the lane is broken; test red means the lane
is WORKING (it found platform evidence). With the step-level flag the job
conclusion stays green, `merge-verified.sh`'s zero-red rule holds unmodified
(no tooling change, no carve-out in the merge gate), and the red is carried
visibly by three first-class surfaces:

- a `::warning::` annotation naming the failing test ids (annotations render
  on the run page and the PR checks timeline);
- a GitHub Actions **job summary** (parsed from the junitxml: counts plus
  failing ids verbatim, plus the census pointer);
- the **junitxml artifact** (durable past log expiry — the intermittents
  census needs run-level records that survive).

This is NOT the timing lane's shape — the timing lane gated from day one
(#241 slice 1). The difference is principled, not drift: the timing lane
split an existing green execution surface (every marked test already ran in
`gates` on Linux; the lane moved them to a quieter host — a red there was a
pre-existing class of failure, already triaged). This lane opens a NEW
execution surface (a platform the suite has never run on in CI) whose red
inventory is unknown. Evidence-first is what "convert attested findings
into CI-proven evidence" means operationally: the first reds are the
product. The graduation path is the timing-lane precedent played forward:
accumulate lane data → pre-committed rule decides → gate (slice 2, owner
call).

**The anti-pattern this avoids:** a CI lane whose reds are invisible would
be a silent-pass hole. The warning/summary/artifact trio is the loudness
mechanism; the falsifier for "red gets seen" is deferral D5's trigger (a red
unrecorded on #207 for 7 days reopens automated routing).

## 3. Mechanism — the concrete job (builder-ready)

New `windows` job appended to `.github/workflows/ci.yml` (same workflow, same
triggers, one rollup — the timing/browser-lane precedent; NOT a new workflow
file: `package.yml`/`device-plugins.yml` are separate because their TRIGGERS
differ, and this lane's do not). Every step is a byte-sibling of the `gates`
job's, minus lint/mypy/standards-check (the timing-lane precedent for a
non-gates lane: those run over the same tree in `gates`; their logic is
platform-neutral and their Windows execution buys no evidence), plus the
evidence steps. Action pins reuse the exact SHAs already pinned in-tree.

```yaml
  windows:
    # The Windows evidence lane (issue #207; #329 deferral D2 arriving by
    # owner directive 2026-10-02). Runs the SAME selection as the gates
    # job on windows-latest, so contributor-attested Windows findings
    # become CI-proven evidence and the intermittent sqlite disk-I/O
    # census items have a reproduction surface. EVIDENCE POSTURE (slice
    # 1): continue-on-error on the test step only — a test red does not
    # block merges (merge-verified.sh reads the job conclusion; its
    # zero-red rollup rule is unchanged) and is carried instead by the
    # warning annotation, the job summary, and the junitxml artifact.
    # Setup failures have NO continue-on-error: a broken lane blocks
    # like any broken CI. Graduation (slice 2) deletes one line.
    runs-on: windows-latest
    timeout-minutes: 30
    permissions:
      contents: read
    defaults:
      run:
        shell: bash
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          submodules: recursive
          fetch-depth: 0 # train_window reads version-dir history (#97)

      - name: Install uv
        uses: astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9 # v9.0.0
        with:
          python-version: "3.13"

      - name: Materialise fixture signing keys from repo secrets
        env:
          BENCHWEAVE_FIXTURE_KEY_MAIN: ${{ secrets.BENCHWEAVE_FIXTURE_KEY_MAIN }}
          BENCHWEAVE_FIXTURE_KEY_ORIGINB: ${{ secrets.BENCHWEAVE_FIXTURE_KEY_ORIGINB }}
        run: |
          if [ -n "$BENCHWEAVE_FIXTURE_KEY_MAIN" ]; then
            printf '%s' "$BENCHWEAVE_FIXTURE_KEY_MAIN" > fixtures/registry/keys/main.pem
          else
            echo "::notice::BENCHWEAVE_FIXTURE_KEY_MAIN unavailable (fork PR?); signing tests will skip"
          fi
          if [ -n "$BENCHWEAVE_FIXTURE_KEY_ORIGINB" ]; then
            printf '%s' "$BENCHWEAVE_FIXTURE_KEY_ORIGINB" > fixtures/registry/keys/originb.pem
          else
            echo "::notice::BENCHWEAVE_FIXTURE_KEY_ORIGINB unavailable (fork PR?); signing tests will skip"
          fi

      - name: Sync environment
        run: uv sync --locked

      # Byte-exactness: checkout relies on the committed .gitattributes
      # (`* text=auto eol=lf`) in this repo AND in packages/sdk — eol=lf
      # overrides the Windows runner's default core.autocrlf, so worktree
      # bytes equal the committed LF bytes and every digest reads the same
      # input as on Linux. No git-config step is wanted; a digest-mismatch
      # red here is the canary for that posture regressing, on the OS
      # where it would regress.
      - name: Test (windows evidence lane)
        continue-on-error: true
        run: >-
          uv run pytest -q -n auto -m "not timing and not browser"
          --junitxml=windows-evidence.xml

      - name: Evidence summary
        if: always()
        run: |
          uv run python - <<'PY'
          import os, xml.etree.ElementTree as ET
          root = ET.parse("windows-evidence.xml").getroot()
          counts = {k: int(root.get(k, "0")) for k in
                    ("tests", "failures", "errors", "skipped")}
          failed = [tc.get("name") for tc in root.iter("testcase")
                    if tc.find("failure") is not None or tc.find("error") is not None]
          lines = [f"### Windows evidence lane",
                   f"- tests {counts['tests']} · failures {counts['failures']} "
                   f"· errors {counts['errors']} · skipped {counts['skipped']}"]
          if failed:
              lines.append("- failing ids (evidence for #207 — non-blocking by design, slice 1):")
              lines += [f"  - `{n}`" for n in failed]
              print(f"::warning::windows evidence lane: {len(failed)} failing id(s) — "
                    f"see summary; census discipline: record on #207")
          with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
              fh.write("\n".join(lines) + "\n")
          PY

      - name: Upload junitxml evidence
        if: always()
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1fc6a875d1fc6a0a # v7.0.1
        with:
          name: windows-evidence-junit
          path: windows-evidence.xml
```

Notes on choices inside that YAML:

- **`defaults.run.shell: bash`** — Windows defaults to pwsh; every step here
  (keys, heredoc) is bash. Git for Windows' bash ships on the runner images.
- **`fetch-depth: 0`** — the full gates selection includes
  `tests/standards/test_train_window.py`, which reads version-dir addition
  history (#97); mirroring `gates`' checkout keeps the selection executable,
  not partially skipped.
- **Fixture keys materialised identically to `gates`** — the signing tests
  are registry tests, unmarked, inside this selection; omitting the step
  would silently convert them to skips on every run (a different selection
  than gates — the parity check in §5 AR-1 would catch it, but not silently
  allowing it is cheaper). Fork PRs get the documented skip-with-reason
  shape, same as `gates`.
- **`-n auto`** — mirrors `gates` (#247 leg B); the child-process fault
  tests already run under xdist on Linux in that shape.
- **`--junitxml`** — junit_family is `xunit1` in `pyproject.toml` (pinned so
  `--junitxml` runs agree with the evidence-faults harvest); the summary
  step and artifact consume it. Counts read from the xml attributes, per
  the evidence discipline (never an output-filter summary line).
- **The summary step is inline, not a `scripts/` file** — `.github/` sits
  outside every gated tree; a new file under `scripts/` would move the
  pinned scripts census (obligation 20's same-commit-diff discipline) for
  no gain.
- **`timeout-minutes: 30`** — generous bound (expectation §5); a timeout is
  a lane-broken state and blocks, consistently with setup failures.

## 4. Scope of what runs — and the AR-8 asymmetry it creates

**Selection: exactly the gates selection** — `pytest -q -n auto -m "not
timing and not browser"`. No new marker, no fourth partition state: the
marker partition (gates / timing / browser, union = full collection, #241
slice-1 AR-1 + #300 G1d slice 4) is untouched; this job is a **platform axis
over an existing partition member**, so the partition-integrity story needs
no extension — only per-OS parity of what one member collects (§5 AR-1).

**Timing-marked set: EXCLUDED on Windows.** The call and why: the timing
lane is a load-honest measurement construct — bands calibrated on
GitHub-hosted ubuntu runners, serialized on a fresh VM within ~2 min of
boot (#241 slice 1's design, its "what this honestly buys" paragraph).
Windows adds a second, uncharacterized variance axis (scheduler,
filesystem latency, background scanning) — running the bands there without
Windows-calibrated baselines would produce band reds that are attributable
to NEITHER platform nor load, destroying exactly the attribution property
the timing lane exists to provide. Slice-2-style re-banding on Windows has
no measurement basis and no asker.

**The asymmetry this creates, stated rather than hidden:** #329's AR-8
requested a contributor Windows rerun of FIVE ids. Four of them are in this
lane's selection and get in-band corroboration from its first runs:

1. `tests/cli/test_retention.py::test_fw5_naive_stamps_anchor_unresolved_and_never_host_local`
2. `tests/cli/test_retention.py::test_fold2_wedge_exhaustion_beyond_domain_renders_decidable_output`
3. `tests/cli/test_dispose.py::test_fold1_fsync_chain_covers_the_target_and_its_parent`
4. `tests/cli/test_dispose.py::test_fold2_durability_errors_refuse_typed_never_laundered`

The fifth — `test_row_b_clamp_is_entry_time_remaining_disclosed_overshoot`
— is timing-marked (`tests/unit/test_otdp_bridge.py:2640`, #241 slice 1) and
therefore does NOT run here. Its Windows corroboration stays on the
contributor-rerun path, and #329-D4's valve ("a Windows red of the row-B
test inside `clamp + 300`") remains reachable exactly as its letter reads —
by "a Windows red", not "a CI Windows red". Deferral D1 below carries the
future decision.

**Browser-marked set: excluded** — the browser lane is an ubuntu+chromium
construct (#300 G1d); no purpose names Windows browser evidence. **Lint,
mypy, `make check-sdk-standards`: not in the lane** (the timing-lane
precedent for a non-gates job; all platform-neutral, all already executed
over the same tree in `gates`). `mypy --platform win32` is #329-D3's own
deferred lane with the tree-wide stub count unknown — deferred again here
(D2 below), first as an out-of-band count, never a blind gate.

**What the intermittents need from the scope:** the two census items live in
`tests/faults/test_disposition_faults.py` (unmarked, child-process
orchestration) — inside this selection, executed every run, exactly what D2
asked for ("a place to be reproduced"). Their occurrences become data under
§5's pre-committed counting rule.

**Cost/wall expectation (disclosure, not a gate):** POSIX `gates` ≈ 2.5–4
min (post-#247 xdist; local measured 41–53 s suite on a 10-core host,
2339-test baseline since grown). Windows hosted runners typically ~2× Linux
for Python suites, plus a cold `uv sync` (ci.yml jobs enable no uv cache):
expect 5–10 min per run, one extra hosted job per push/PR, free on this
public repo. Timeout 30 min bounds the tail.

## 5. Measurable proof and the pre-committed acceptance rule

### 5.1 PR-time (builder, before push)

- **AR-1 (selection parity, mechanical):** POSIX-side
  `uv run pytest --collect-only -q -m "not timing and not browser"` count
  recorded in the PR body; the lane's own first PR execution must report the
  SAME collected count (junitxml `tests` attribute modulo runtime skips;
  fork-PR key-skips excluded by running this on a same-repo branch). A
  count mismatch is a collection-time platform failure — a finding, not
  noise. Skip-count difference between the PR's `gates` and `windows` runs
  beyond the empty set is likewise a finding (the suite's convention is
  capability-probed branches, never skips).
- **AR-2 (plant-branch RED — the G2-plant precedent, wire-level):** a
  throwaway branch adds ONE deliberately-failing canary test; its lane run
  must show (a) the pytest step RED, (b) the JOB conclusion GREEN
  (continue-on-error holds; `gh pr checks` shows no fail — the
  merge-verified rule unbroken), (c) the summary listing the canary id,
  (d) the artifact uploaded. Branch never merged; run URL + outputs pasted
  in the PR body. This is the increment's RED: the evidence machinery
  demonstrably fires on a real Windows red before any real one arrives.
- **AR-3 (gates and battery):** fast triple per commit (`scripts/gate.py
  --fast` discipline — bare ruff, fresh-cache bare mypy, focused pytest);
  full battery + both tripwires once before push; **cold full-suite run**
  (obligation 5's workflow-change rule); standards diff empty; merge on the
  full rollup via `scripts/merge-verified.sh`.
- **AR-4 (first census point):** the PR's own `windows` run is census data
  point 0, recorded in the PR body with its counts.

### 5.2 Post-merge — pre-committed BEFORE any lane number is read

**Unit of observation:** one `windows` job execution on a main-branch push.
PR-branch runs (different trees) and fork-PR runs (keys absent — a
different selection) are counted separately and never enter the
corroboration denominator. **Red id:** a failing test id in the junitxml.
**Deterministic red (the operational definition):** a red id that reds in
TWO CONSECUTIVE executions at the same commit (`gh run rerun --failed`
satisfies the second). Anything that greens on its rerun is an
intermittent, the #207 family — data, never a failure of this increment.

- **SHIP (corroboration holds; graduation becomes available to the owner):**
  across the first **10 main-push executions**, zero deterministic reds,
  and the four runnable AR-8 ids green in all 10. This is #329's AR-8
  satisfied in-band: the deterministic fixes hold on real Windows, proven
  by CI rather than attested. Slice 2 (deleting the continue-on-error
  line) may then be proposed; gating remains the owner's call.
- **KILL (corroboration refuted — the lane's claim dies, the lane stays):**
  any deterministic red that is not one of the two ledgered intermittents.
  AR-8's REOPEN arm fires: the "deterministic set is green on Windows"
  claim is refuted; the finding is filed as its own issue with the two
  same-commit run URLs; graduation is off the table until it is fixed.
  The LANE is not reverted — a find is this lane succeeding at purpose
  (1); reverting the instrument because it detected would be backwards.
- **INTERMITTENTS (pure data):** every occurrence of the two ledgered ids
  (`test_kill_mid_disposition_leaves_neither_audit_nor_deletion`,
  `test_ar5a_kill_mid_phase_a_leaves_store_untouched_whole_objects_only`)
  is recorded on #207 (run URL + ids + generation) per the census
  discipline. **No frequency claim before 50 main-push executions** —
  below that, occurrences are listed with their denominator and nothing
  stronger ("3 occurrences in 17 executions" is a legal sentence; "the
  flake rate is ~18%" is not). This is D2's "place to be reproduced"
  satisfied structurally the moment the lane runs them.
- **UNDERPOWERED (measurement, not conclusion):** if fewer than 10
  main-push executions accumulate within 14 days of merge, the window
  extends and every claim carries its partial denominator; no deterministic
  verdict from n<10. (Repo cadence — near-daily trains — makes 10 ≈ 1–2
  weeks.)
- **LANE-REWORK (the lane itself fails):** three consecutive executions
  unable to produce a valid junitxml/count (setup reds, collection crash,
  timeout). The evidence machinery is broken; fix before any corroboration
  claim either way.

**Signal routing (how a red reaches the tracker):** the warning annotation
+ summary + artifact make the red visible at the run; the DISCIPLINE that
moves it to the tracker is the standing census practice on #207 — any
observer (agent or human) seeing a red records it as a census comment with
the run URL, exactly as the contributor census and the owner's cross-reference
comments have done all along. No automated issue-posting exists anywhere in
this repo's workflows and none is introduced (new architecture; D5 carries
the reopen). The #207 closure question — whether the intermittents' new home
closes the issue or it stays open for a follow-up — is the owner's call per
#329 §5.2's own language and is deliberately not designed here.

## 6. Precedent (all in-tree, all extended not invented)

- **The timing lane** (#241 slice 1; `.github/workflows/ci.yml` `timing`
  job): a dedicated OS-shared job with its own checkout/uv/sync spine, a
  marker-selected pytest command, a responsibilities comment, and no
  lint/mypy/keys/standards steps. This job is that shape on a new axis,
  with the keys step retained (the selection includes the signing tests).
  The graduation pattern (lane data → pre-committed rule → owner call) is
  slice-1's §5 played forward.
- **The browser lane** (#300 G1d slice 4): the second instance of the same
  shape; the gates comment's three-way partition statement is the text this
  design leaves untouched.
- **The package.yml OS matrix** (`ubuntu-latest` + `macos-latest`,
  `fail-fast: false`): the existing proof that cross-OS jobs are a native
  pattern here — and the surface whose census comment ("No Windows lane
  exists — coverage claims state that honestly") this diff updates, because
  it becomes stale the moment the lane lands.
- **The G2 plant branches** (obligation 20's wire-level proof): the
  never-merged branch that proves a gate fires — reused as AR-2.
- **The #140/#237/#329 platform-fix lineage**: the suite's
  capability-probed, never-skip convention is why this lane can expect
  runnable parity instead of a skip wall.
- **actions/upload-artifact pinned at
  `043fb46d1a93c77aae656e7c1fc6a875d1fc6a0a` (v7.0.1)** — the exact pin
  already used twice in `docs.yml`; no new action dependency class.

## 7. Invariant, drift, and cross-surface impacts

- **No CTL/STO/CON/REG invariant is touched.** No production code under
  `src/` changes; no store, executor, admission or protection path moves.
  The A06 principle (evidence over assertion) is the load-bearing one, in
  its purest form: this lane IS an A06 instrument — attestation becomes
  CI-proven evidence, and intermittents get a measured home instead of
  anecdotes.
- **Obligations walked:** 4 (CI is operator-visible → CI-map row mandatory;
  `docs/development.md`'s GitHub-workflows section names the lane — and its
  existing staleness re: the browser job is fixed in the same sweep, the
  in-arc pattern); 5 (workflow change → cold full-suite run at PR time;
  key-materialisation parity carried into the new job verbatim); 10 (no
  dependency change — pytest-xdist and the browser pins already in the lock
  cover the lane's imports; `uv sync --locked` resolves them); 20
  (`.github/` is outside every version-literal gated scope — named so the
  zero-gate denominators cannot silently move; the inline summary step
  avoids `scripts/` census motion by the same token).
- **CI map** (`docs/internal/drift-and-obligations.md`): gains the
  `windows` row (what it catches: platform evidence over the gates
  selection, the intermittents' reproduction surface, the byte-exactness
  canary; what it does not: gating — slice 1 is evidence-posture, and the
  timing/browser/ui/systemd lanes stay Linux constructs); the derivation
  census row's "(no Windows lane; the design record's risk 4 states the
  coverage)" parenthetical updates to name the lane (checkout-context
  binary64 agreement now measured on Windows by this lane — the
  installed-wheel-context matrix extension stays deferred, D4).
- **`package.yml` census comment**: one-line rewording (the "No Windows
  lane exists" sentence becomes false at merge).
- **Standards tripwire:** empty, both directions; no governor dispatch
  (no `standards/` bytes, no version strings, no SDK pointer motion).
- **merge-verified.sh:** unchanged — the job's conclusion stays green under
  the evidence posture, so the zero-red rollup rule holds without
  modification. This interaction is WHY the continue-on-error is
  step-level and documented in the job comment.
- **No on-disk format or schema is involved** (workflow YAML + docs + this
  record only) — the rubric's formats clause does not fire; the tier below
  is keyword-carried.

## 8. Review tier and the Step-1 keyword scan (#254)

**Tier 3.** Path rules say Tier 2 (`.github/` + docs), but the Step-1
keyword rule is text-based first-match-wins over the WHOLE expected diff,
and the diff text carries keywords — unavoidably twice over: this record,
which lands as the branch's commit 1, cites the digest machinery by name in
§1, and this scan table itself names every keyword once per row (the
rubric's own self-fire property — "the diff carries the keywords by
construction — intended"). The scan below was run mechanically over the
written record plus the drafted ci.yml/package.yml/docs hunks (those hunks
contain none of the eight). Measured:

| keyword | total in expected diff | in table only (self-ref) | in body |
|---|---|---|---|
| `sha256` | 3 | 1 | 2 — §1's `hashlib.sha256(...)` digest citations |
| `hashlib` | 3 | 1 | 2 — §1's read-bytes digest citations |
| `protection` | 6 | 1 | 5 — §2's branch-protection findings (×4, incl. the `gh api` quote), §7's "no … protection path moves", §11's no-change list |
| `threading` | 1 | 1 | 0 |
| `asyncio` | 1 | 1 | 0 |
| `subprocess` | 1 | 1 | 0 |
| `migrate` | 1 | 1 | 0 |
| `recovery` | 2 | 2 | 0 |

Any hit takes the deep lane; this diff carries several. The counts are the
design-time record's own scan of its written text; the reviewer re-derives
the tier independently per the rubric, and any count drift between this
table and the landed diff is a review finding on the record (the #254
rule). Standing consequence: Tier 3 → the G6 adversarial refute with two
independent lanes (the standing two-lane rule) is owed before merge.

## 9. Deferral table

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D1 | the timing-marked set on Windows (Windows-calibrated bands, or a decision that row-B's Windows reds stay contributor-rerun evidence) | documentation here + #241's outcome thread | #329-D4 firing from a contributor Windows rerun (a row-B red inside `clamp + 300`), or the owner's explicit call for Windows timing bands |
| D2 | `mypy --platform win32` as a standing lane (#329-D3; its trigger "the Windows lane" fires NOW with this landing) | issue #207 outcome comment; this lane's follow-up slice | the out-of-band whole-tree count being taken (a one-off lane-log measurement, not a gate) and the owner calling gate-vs-report on its result |
| D3 | browser / ui / systemd lanes on Windows | documentation here | a plugin or contributor workflow requiring Windows browser or UI evidence (none names one today) |
| D4 | `windows-latest` in `package.yml`'s derivation matrix (the installed-wheel context; checkout-context agreement is already measured by this lane) | documentation here | slice-2 graduation (the lane green over its first 10 executions) or the owner's ask |
| D5 | automated red→tracker routing (a workflow step or bot posting census comments with run URLs) | documentation here | a Windows red that goes unrecorded on #207 for 7 days after its run, or the owner asking for automation |
| D6 | graduation — deleting the pytest step's `continue-on-error` | follow-up slice (this lane's slice 2) | the SHIP arm of §5.2 holding over the first 10 main-push executions, plus the owner's explicit gating call |
| D7 | a workflow-level submodule-attributes guard (refusing a submodule without `eol=lf` coverage) | documentation here | a third submodule being added, or a digest-mismatch red in this lane that traces to checkout-time byte rewriting |

## 10. Top risks and their falsifiers

1. **Post-census tree motion reds deterministically on Windows** (the
   #241-s4/#244/#300/#329 trains have never executed there). This is the
   expected case, not the edge — the evidence posture exists for it.
   Falsifier of the corroboration claim: the KILL arm (a deterministic red
   outside the two ledgered intermittents). The lane keeps running either
   way; the finding gets its own issue.
2. **`os.symlink` privilege on the runner** —
   `tests/control/test_documents_provider.py:203` symlinks a fixture.
   GitHub Windows runners run elevated and generally permit symlinks, but
   "generally" is not a guarantee. If it fails, it fails DETERMINISTICALLY
   — the KILL arm catches it, it becomes a filed finding (likely a
   capability-probe fix in the #329 style), and the corroboration claim
   waits for it. Named here so it is not mistaken for lane breakage.
3. **The evidence posture green-washes a red into invisibility.** A red
   under continue-on-error does not red the rollup; if nobody looks at the
   summary, the evidence exists but is unobserved. Mitigated by the
   warning annotation (visible on the PR timeline) and the census
   discipline; the falsifier is D5's trigger — one red unrecorded for 7
   days and automation becomes owed.
4. **Windows runner noise trips an unmarked wall-clock assert** (the #241
   D5 marker-rot class — bounds that should carry the timing marker but
   do not). Such a red is intermittent-shaped (greens on rerun), lands in
   the data bucket, and corroborates #241's family rather than blocking
   anything; the marker-rot guard remains #241's deferred item, not this
   lane's.
5. **The junitxml/summary parsing is wrong in a way that reports green
   over red** (e.g. xunit1 shape differences swallowing failures). This
   would be an evidence-integrity defect — the worst kind for this lane.
   Mitigated by AR-2's plant-branch proof (the machinery is shown firing
   on a REAL red before merge) and by the artifact retaining the raw xml
   for hand-audit; falsifier: any run whose junitxml `failures+errors` is
   nonzero while the summary prints zero.
6. **The lane's wall-clock or cost profile is worse than disclosed**
   (cold sync + 2× suite). Bounded by `timeout-minutes: 30`; free on the
   public repo; the merge-time wall is unaffected (jobs run in parallel;
   the slowest job — `gates` — owns PR wall-time today and the lane is
   scoped to stay under it). Falsifier: the lane becoming the slowest job
   in the rollup — then D4/D2-style trimming is the owner's lever, not a
   silent scope cut.

## 11. What this design deliberately does NOT do

- No branch, no implementation, no PR (design-only mandate).
- No new marker, no partition change, no `pyproject.toml` motion.
- No change to `merge-verified.sh`, branch protection, or the rollup rule.
- No automated tracker posting (D5), no `scripts/` additions, no mypy step
  (D2), no timing-on-Windows (D1), no package matrix motion (D4).
- No design of #207's closure — the intermittents' home and the issue's
  end state stay the owner's call (#329 §5.2's language, honored).
