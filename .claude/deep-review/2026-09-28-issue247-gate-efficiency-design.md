# Issue #247 — Gate efficiency: batched-fold doctrine, parallel suite, honest summaries

**Design record** · 2026-09-28 · Tracking: [issue #247](https://github.com/madeinoz67/benchweave/issues/247) · Evidence base: the #217 run's measured costs plus a three-leg measurement pass (xdist trial, incident recheck, timing-gate audit), all numbers below from that pass.

## 0. The problem, measured

The #217 fold-all (11 LOW/NIT rows) took ~75 min, ~70% ceremony: five full ~2400-test batteries for five trivial commits that pushed together. Three cost centers, three legs:

1. **Gate doctrine applies full batteries per commit** — including trivially-batched folds.
2. **The suite runs serially** — baseline 2339 tests / 234.9 s junit (236.3 s wall) on a 10-core host.
3. **rtk's filtered pytest summaries lie** (both directions), forcing per-agent junitxml discipline; 5+ documented instances 2026-09-14 → 2026-09-27.

## 1. Leg A — the gate-doctrine amendment

**Rule change (supersedes the 2026-09-24/25 "gates re-run after EVERY commit" wording):**

- **Per-commit FAST lane, every commit, no exemptions** (test-only and docs-only included): bare `uv run ruff check .` + fresh-cache bare `uv run mypy` + focused `uv run pytest` for touched modules (+ `tests/faults/` for `state/`/`control/`/concurrency, per existing rule).
- **Per-PUSH full battery** (the fast triple + the full suite + both standards tripwires): once, immediately before push.
- **Batches fold as ONE commit** — a row-call fold is one commit carrying per-row RED evidence in its message, one battery. The per-commit rule's intent ("nothing reaches push ungated") is preserved by the push battery for batched work.
- **Evidence discipline is part of the gate definition, not hygiene** (from incident 2): gates read TRUE exit codes (unpiped, `PIPESTATUS`, or output-to-file — `cmd | tail -1; echo $?` echoes tail's status); any claimed mypy result comes from a fresh cache (`rm -rf .mypy_cache` or `--no-incremental`). Running a lying gate more often catches nothing.

**Incident-protection recheck (the precondition, PASSED with the conditions above):**

| Incident | Class | Fast lane catches? | Push battery catches? |
|---|---|---|---|
| F841 ruff miss (#176 row-B re-seat `a16fe07`, test-only commit) | lint in test code — invisible to pytest by construction | YES at the offending commit (ruff leg; improvement over status quo — the adversary found it 1 h later) | YES (battery includes ruff) |
| Stale-evidence mypy (#146 slice-2 `950e861`) | strict-mypy errors in touched modules; the miss was EVIDENCE (piped exit + warm cache), not coverage | YES, conditional on the fresh-cache + true-exit rules riding the gate definition (empirical proof: refute lane's fresh-cache exit 1) | YES, same condition |

The load-bearing condition repeated once: the fast lane must never acquire a "test-only commits run pytest only" exemption — that exemption IS the hole that produced incident 1.

**Encoding surfaces:** the how-we-work section in `CLAUDE.md` §3 item 2 (rewrite — correction 2026-09-28: the section lives in CLAUDE.md, not AGENTS.md; AGENTS.md has no §3); `CLAUDE.md` @-imports unchanged; `.claude/skills/increment/SKILL.md` step 3's standing gate line (rewrite to the fast/push split + one-commit folds); the memory rule ("Gates re-run in order after EVERY commit" retro item) superseded with this doctrine; benchweave-sdk's AGENTS.md if it mirrors the line (check at build).

## 2. Leg B — pytest-xdist

**Measured:** `-n auto` (10 workers): 41.4–53.3 s vs 234.9 s serial — **4.4–5.7×**, ~3.2–3.5 min saved per full run; honest range under ambient load (30+ concurrent agent lanes). pytest-xdist 3.8.0 / execnet 2.1.2.

**The one xdist-only failure is a known class, now structurally excluded:** `test_instrument_range_gate_per_axis_per_cell` tripped under 10-way contention (spread 113.9 ms) — load-sensitive, NOT order-coupled (isolated `tmp_path` per worker; passes serially; second parallel run green). With PR #246 merged, `gates` runs `-m "not timing"` and that test lives in the `timing` lane — the exclusion is already structural. Verification at build: `-n auto -m "not timing"` green 3×.

**Changes:** `pytest-xdist` in dev deps; `addopts` gains nothing (marker discipline stays per #246: no `-m` in addopts); local full-run convention + CI `gates` job adopt `-n auto -m "not timing"`. `make`/script surfaces unchanged otherwise.

**Acceptance:** full battery wall ≤ 90 s locally (from ~235 s); CI gates lane proportionally reduced; zero xdist-only failures across 3 consecutive full runs (excluding `timing`, which stays serialized in its own lane).

## 3. Leg C — absorbed by #241 (not this issue's scope, recorded for the handoff)

The timing-gate audit examined 51 gates; three genuinely spike-brittle, all inside other records' scope — the inventory hands to #241 slice 2 (evidence-backed re-bands): the per-trial upper band (`test_axis_trials_complete_all_four_axes:1694`), the two row-B clamp bands in `test_otdp_bridge.py` (2862 = the tightest: 50 ms headroom, LOWER-bound trip so the trim pattern does NOT apply — fix shape is a wider band or re-derived stamp, by amendment to the #146 row-B record). The run-wall hang-cut gate is magnitude-safe (outside the one-spike class).

## 4. Leg D — honest summaries

Consolidation already landed (2026-09-28): canonical MuninnDB record (default vault), RTK.md warning + evidence protocol section, OPERATIONAL_RULES unchanged as the rule home.

**In-repo structural fix:** a `scripts/gate.py` (or `make gate-fast` / `gate-full`) wrapper that runs each gate command, captures true exit codes, parses junitxml attributes, and prints one machine-readable line per gate (`GATE pytest 2413 0 0 11 PASS`-shape) — making the evidence protocol structural so no agent hand-parses a summary line again. rtk itself is an external binary; the wrapper reads through it (`rtk proxy`) where applicable. Build agents' briefs reference the wrapper instead of raw commands.

## 5. Increments

1. **Increment 1 (Leg A + encoding)**: rule text in CLAUDE.md §3 item 2 (see encoding-surfaces correction) + increment skill + memory-rule supersede note; no code. Acceptance: the texts name the fast/push split, the no-exemption condition, the evidence rules, and one-commit folds; the incident table above is reproduced in the rule's rationale.
2. **Increment 2 (Leg B)**: dev dep + CI gates `-n auto -m "not timing"` + 3× green verification + the measured before/after posted to #247.
3. **Increment 3 (Leg D)**: the gate wrapper + one consumer (the increment-builder brief line) + its own tests (a planted failing gate reads FAIL, a piped lie cannot false-green it).

Each rides its own working branch against this design; none touches standards bytes (`git diff origin/main...HEAD -- standards/` empty is a standing check per increment).

## 6. Deferrals

| # | Deferred | Carrier / trigger |
|---|---|---|
| D1 | Timing-gate re-bands (audit inventory §3) | #241 slice 2 — posted there at this design's merge, not rebuilt here |
| D2 | rtk binary-side filter fix (upstream) | Only if the wrapper proves insufficient; not this repo's work |
| D3 | benchweave-sdk AGENTS.md mirror of the doctrine | Checked at increment 1 build; mirrored only if the line exists there |

## 7. Risks

- **Fast-lane scope drift** (a future "docs-only skips ruff" carve-out) reopens incident 1's hole — mitigated by writing the no-exemption clause INTO the rule text, not leaving it to habit.
- **xdist masking order-dependent tests** the serial suite would catch: the 3× green verification + the faults suite running in every battery is the net; any future xdist-only pass with serial-fail is a finding by definition.
- **Wrapper adoption lag**: briefs must reference the wrapper; old habit commands keep working (the wrapper wraps them), so adoption is additive, not breaking.
