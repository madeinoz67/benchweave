# Timed leg 1 — clean-install demo (author-run, wall-clock)

**PRD §6 target:** a prepared engineer completes the documented clean
simulated demo in **≤ 30 minutes**, excluding dependency download time.
**Verdict: PASS — 10 s total / 8 s post-download.**

> **Author-run disclosure.** This leg was executed by the WP09
> implementer (the author), not an independent operator, on the
> development host (macOS, warm uv cache). The wall-clock measures the
> documented command path, not an unpracticed operator's reading time.
> Single pass; timestamps are `date -u` marks (1 s resolution) retained
> in the shell log at `.superpowers/sdd/task-8-leg1-shell.log`
> (uncommitted per repo rule). No quiet restarts — the one aborted
> attempt is disclosed below.

## Clock

| | UTC (2026-09-14) |
|---|---|
| Start | 08:02:24Z |
| Stop | 08:02:34Z |
| **Total wall-clock** | **10 s** |
| Dependency acquisition (step 3: fresh-venv `uv pip install`) | 2 s |
| **Post-download** | **8 s** |

**Exclusion basis.** The excluded segment is the whole fresh-venv
`uv pip install` — the only network-dependent step in the guide's
clean-install path (75 packages: resolved 1.18 s, prepared 235 ms,
installed 136 ms; the uv cache on this host was warm, so the true
download component was near zero — a cold machine's excluded segment
would be larger). `uv build` (build isolation, cached) and all local
steps are INCLUDED in both numbers.

## Commands executed (guide § references)

Guide followed: `docs/operator-guide.md` @ commit `3ce682b`. All output
piped (machine paths — the guide's `[interactive]` views fall back to
plain text when piped). `BENCHWEAVE_*` env stripped (operator hygiene).
Work root `/tmp/bw-timed/leg-1` created fresh.

| # | Guide | Command (as executed) | Dur. |
|---|---|---|---|
| 1 | §1 | `uv build` (cwd = checkout) | 2 s |
| 2 | §1 | `uv venv /tmp/bw-timed/leg-1/venv` | <1 s |
| 3 | §1 | `uv pip install --python /tmp/bw-timed/leg-1/venv/bin/python dist/benchweave-*.whl` | 2 s (excluded segment) |
| 4 | §1 | `/tmp/bw-timed/leg-1/venv/bin/benchweave --version` | 1 s |
| 5 | §2 | `benchweave setup --data-dir /tmp/bw-timed/leg-1/data` | <1 s |
| 6 | §4 | `benchweave demo --scratch /tmp/bw-timed/leg-1/demo --keep --fixtures <repo>/fixtures/execution` | 4 s |
| 7 | §5 | `benchweave report --data-dir /tmp/bw-timed/leg-1/demo --json` | <1 s |
| 8 | §6 | `benchweave backup --data-dir /tmp/bw-timed/leg-1/demo --out /tmp/bw-timed/leg-1/backups` | <1 s |
| 9 | §6 | `benchweave verify --data-dir /tmp/bw-timed/leg-1/backups/backup-20260914T080233Z` | <1 s |
| 10 | §6 | `benchweave restore --archive …backup-20260914T080233Z --data-dir /tmp/bw-timed/leg-1/demo` | <1 s |
| 11 | §6 | `benchweave verify --data-dir /tmp/bw-timed/leg-1/demo` | <1 s |

Recorded substitutions (host constraints, not guide defects):
`/opt/benchweave-venv` → `/tmp/bw-timed/leg-1/venv`; `/var/lib/benchweave`
→ `/tmp/bw-timed/leg-1/data`; `/tmp/demo` → `/tmp/bw-timed/leg-1/demo`;
`/path/to/fixtures/execution` → the repository's `fixtures/execution`
(the guide's named reference lattice).

Scoping: §3 `serve` was not run — the demo's fresh-install mode boots its
own ephemeral gateway (§4); the guide does not require `serve` for the
demo. Deliberate damage (§6's test-form step) is not a guide operator
step — not performed; the restore here exercised the documented
backup → verify → restore → verify arc.

## Result

Every step exited 0. Demo run `run-ed51a61846c44fbc`: `state=terminal`,
`outcome=passed`, `safe_state=verified`, label `SIMULATION`, terminal
record sha256 `4b317a37abae9e60b84602dc03e17248ca147d68e7ae5d6635275201ac4816c8`;
the report read back 36 evidence entries, all present,
`missing_evidence: []`; backup → verify → restore → verify all clean.

## Aborted attempt (disclosed)

Attempt 1 (08:00:26Z, log retained at
`.superpowers/sdd/task-8-leg1-shell-attempt1.log`) aborted after 12 s at
step 3: a transcription error in the timing harness executed
`--python /tmp/bw-timed/leg-1/bin/python` (missing `/venv`) — **not the
guide's command**. No product step beyond `uv build`/`uv venv` had run.
The harness was fixed and the leg restarted from a fresh work root; the
recorded pass above is attempt 2 in its entirety.

## Guide-friction findings

1. **Root-path examples** — §1–§3 write `/opt/benchweave-venv`,
   `/var/lib/benchweave`, `/var/backups` (and §3 `sudo`), with no
   non-root note. Harmless substitution for a dev-host run; a one-line
   "substitute your own writable paths" note would remove the stumble.
2. **Venv activation unstated** — §1 verifies
   `<venv>/bin/benchweave --version`, then §2+ write bare `benchweave`
   without saying "activate the venv or prepend its bin/ to PATH".
   Interpreted here as `export PATH=<venv>/bin:$PATH`.
3. **Install warning** — `uv pip install` prints
   `warning: The package fastmcp==4.0.3 does not have an extra named
   'server'` (package metadata nit, upstream of the guide; install
   succeeds). Pre-existing; worth an upstream fix, not a guide change.
4. **§5's report example depends on §4's `--keep` variant** —
   `report --data-dir /tmp/demo` only has a store to read if the demo
   ran with `--scratch /tmp/demo --keep`. The adjacency implies it; one
   clause would make it explicit.
