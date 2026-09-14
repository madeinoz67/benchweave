# Timed leg 2 — second-install reuse (author-run, wall-clock)

**PRD §6 target:** a second engineer discovers/admits the published
integrations and repeats the demo in **≤ 30 minutes** with **zero
plugin-source changes**.
**Verdict: PASS on the documented command path — 5 s total / 5 s
post-download (excluded segment sub-second); zero plugin-source changes
proven by digest identity.**

> **Author-run disclosure.** This leg was executed by the WP09
> implementer (the author), not an independent second engineer, on the
> development host (macOS, warm uv cache). The wall-clock measures the
> documented command path, not an unpracticed operator's reading time.
> Single pass; timestamps are `date -u` marks (1 s resolution) retained
> in the shell log at `.superpowers/sdd/task-8-leg2-shell.log`
> (uncommitted per repo rule). No quiet restarts — the three aborted
> attempts are disclosed below; all were timing-harness defects, none
> were runbook defects.

The runbook followed is `docs/operator-guide.md` §1 "Second-install
reuse" (added for this task in commit `3ce682b` — the guide previously
had no explicit reuse step). Install one = leg 1's venv; the published
artifact = the wheel leg 1 built (`dist/benchweave-0.1.0-py3-none-any.whl`).

## Clock

| | UTC (2026-09-14) |
|---|---|
| Start | 08:06:33Z |
| Stop | 08:06:38Z |
| **Total wall-clock** | **5 s** |
| Dependency acquisition (step 2: fresh-venv `uv pip install`) | <1 s (sub-second; uv: resolved 8 ms, installed 233 ms) |
| **Post-download** | **5 s** (within the log's 1 s resolution) |

**Exclusion basis.** Same as leg 1: the excluded segment is the whole
fresh-venv `uv pip install` — fully cache-served on this host, so
total ≈ post-download here. All other steps are local and included.

## Commands executed (runbook lines)

All output piped; `BENCHWEAVE_*` env stripped; work root
`/tmp/bw-timed/leg-2` created fresh; cwd = the checkout (the runbook's
`dist/` and `plugins/` context).

| # | Command (as executed) | Dur. |
|---|---|---|
| 1 | `uv venv /tmp/bw-timed/leg-2/venv` | <1 s |
| 2 | `uv pip install --python /tmp/bw-timed/leg-2/venv/bin/python dist/benchweave-*.whl` | <1 s (excluded segment) |
| 3 | `/tmp/bw-timed/leg-2/venv/bin/benchweave --version` | <1 s |
| 4 | `SITE_ONE="$(echo /tmp/bw-timed/leg-1/venv/lib/python*/site-packages)"` ; `SITE_TWO="$(echo /tmp/bw-timed/leg-2/venv/lib/python*/site-packages)"` | <1 s |
| 5 | `(cd "$SITE_ONE/benchweave/_vendored/plugins/benchweave" && find . -type f ! -name '*.pyc' -print0 \| sort -z \| xargs -0 shasum -a 256) > /tmp/plugins-one.sha256` | <1 s (16 lines) |
| 6 | same, `$SITE_TWO` → `/tmp/plugins-two.sha256` | <1 s (16 lines) |
| 7 | `diff /tmp/plugins-one.sha256 /tmp/plugins-two.sha256` | <1 s — **empty** |
| 8 | `(cd plugins/benchweave && find . -type f ! -name '*.pyc' -print0 \| sort -z \| xargs -0 shasum -a 256) > /tmp/plugins-repo.sha256` | <1 s (16 lines) |
| 9 | `diff /tmp/plugins-one.sha256 /tmp/plugins-repo.sha256` | <1 s — **empty** |
| 10 | `/tmp/bw-timed/leg-2/venv/bin/benchweave demo --scratch /tmp/bw-timed/leg-2/demo-two --keep --fixtures <repo>/fixtures/execution --json` | 4 s |

Recorded substitutions (as in leg 1): `/opt/benchweave-venv-two` →
`/tmp/bw-timed/leg-2/venv`, `/opt/benchweave-venv` → leg 1's venv,
`/tmp/demo-two` kept literal (under the leg root), fixtures → the
repository's `fixtures/execution`.

## Result — the reuse contract, evidenced

- **Same packages:** both installs' vendored plugin trees hash to 16/16
  identical sha256 lines (`diff` empty; the runbook's echo confirmed).
- **Zero plugin-source changes:** install one's shipped tree is
  byte-identical to the checkout's `plugins/benchweave/` (`diff` empty)
  — the second install required no source modification.
- **The reused install executes:** demo from install two —
  `run-bd8fb3e2c66648aa`, `state=terminal`, `outcome=passed`,
  `safe_state=verified`, label `SIMULATION`, terminal record sha256
  `6ef5e3341f2a3f26a81e07204dd54a23faa0f455b0dbc38e8521a8dc1683bc0b`.

## Aborted attempts (disclosed)

Three attempts aborted on timing-harness defects before the recorded
pass (logs retained as `task-8-leg2-shell-attempt{1,2,3}.log`):

1. Attempt 1 (08:03:53Z) — the harness translated the runbook's
   `(cd … && …)` subshell into `bash -c`, whose child does not inherit
   unexported `SITE_ONE`/`SITE_TWO`; `cd` failed on an empty prefix.
   The runbook's own subshell form has no such defect.
2. Attempt 2 (08:04:54Z) — `export` added inside the child (still
   wrong: it cannot inherit what the parent never exported), and the
   `SITE_*` assignments were hoisted above venv creation, baking the
   literal glob into `SITE_TWO`. The runbook correctly orders the
   assignments AFTER the installs.
3. Attempt 3 (08:05:40Z) — the harness's `date -u` mark lines were
   redirected into the digest manifests, so the diff compared marks,
   not digests (the 16 digest lines themselves already matched).

The recorded pass above is attempt 4, run start-to-finish from a fresh
work root after each abort. No product or guide defect was involved in
any abort.

## Runbook-friction findings

1. **`SITE_ONE`/`SITE_TWO` are plain shell variables** — correct in the
   interactive shell the runbook assumes, but fragile if an operator
   wraps lines in separate shells/scripts (the variables arrive empty
   and `cd` fails with a confusing `/benchweave/...` path).
2. **Same `fastmcp==4.0.3` install warning as leg 1** (upstream
   metadata nit; harmless).
3. The runbook's ordering (install first, then resolve `SITE_*`) is
   load-bearing — resolving before the venv exists bakes the literal
   glob. A one-line comment in the runbook could pin that.
