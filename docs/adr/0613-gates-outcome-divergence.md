# 0613. Investigate divergent outcomes in the gates lane

- **Status:** Accepted
- **Issue:** #613
- **Decision:** Investigation and publication approved by the repository owner. A product repair requires evidence from the investigation.

## Context

Two attempts of CI run [42189358817](https://github.com/madeinoz67/benchweave/actions/runs/42189358817) on commit `13b450f0f4072db3fa34ac0d3cfead0de1da4284` failed at different assertions. Attempt 1 reported a missing evidence gap. Attempt 2 reported `outcome_unknown` in R15. The original stop and UI job IDs and effective runner capacity remain unknown. The current gates lane uses Ubuntu, a locked environment and parallel pytest (`.github/workflows/ci.yml:jobs.gates`).

## Decision

Compare matched baseline and loaded executions for each outcome. Start with 30 fresh executions per test per condition on a CI-equivalent Linux runner. Treat zero failures as an observation with a denominator and an uncertainty interval. Run a targeted ordering experiment wherever instrumentation identifies a plausible mechanism. A shared repair requires a controlled intervention that changes the outcome or lowers the measured failure rate in every row attributed to that mechanism. Record remaining rows separately as explained or unresolved.

## Options considered

| Option | Consequence |
|---|---|
| Fix presumed shared starvation | Small if the hypothesis is right. A shared timing change could mask evidence or alter real supervision behavior. |
| Investigate and repair each row independently | Limits the scope of each repair. Could duplicate work and miss a shared cause. |
| Matched measurements and targeted ordering probes | An upfront experiment costs runner time and supports a decision about which rows, if any, share a repair. Selected. |

## Evidence contract

Use one record per test execution with the test ID, Git SHA, SDK pin, run/job/attempt or unique local trial ID, OS and image, effective CPU capacity, Python and lockfile versions, test selection, worker count, load profile, elapsed time, failure signature and relevant boundary observations. Keep the checkout, fixtures, runner class and selection fixed within each comparison. Use one worker and no added load as baseline. For the loaded condition keep the worker count fixed and add repeatable CPU contention scaled to effective capacity. If the isolated test fails to reproduce, replay the gates job's parallel selection as a separate venue and record its actual worker count. Report per-condition failure counts, attempted counts and infrastructure errors separately. Keep timing and ordering observations in the investigation output. No runtime API, schema or configuration change is needed to collect this evidence.

| Test boundary | Observation and proving check |
|---|---|
| `tests/integration/test_event_recovery.py:test_evidence_storage_failure_emits_evidence_gap` | Trace retention attempts, quota rejection and publication relative to terminal visibility. Distinguish a quota never reached from a gap missing after a recorded rejection. Preserve the exact-one event, quota and evidence-reference assertions. |
| `tests/integration/test_run_activation.py:test_r15_fast_bench_signal_degrades_loudly` | Capture the refusal, any monitor or adapter failure and the terminal reason. Preserve the passed outcome, warning and absence of a live subscription. |
| `tests/cli/test_lifecycle.py:test_l11_two_concurrent_stops_one_action_truthful_reports` | Record request consumption, hold and pid observations, terminal outcome and both typed reports. Probe the permitted plain-first and protective-first orders using real supervision behavior. Preserve one protective action at most and both truthful reports. Escalate for review if runtime supervision needs a change. |
| `tests/interfaces_ui/test_ui_stream.py:test_abort_deregisters_and_the_pair_starts_clean` | At expiry report the last result of `src/benchweave/interfaces/sessions.py:bridge_benches` for the test session. Keep the 20 ms poll, five-second synchronization budget and subsequent same-pair reconnect assertion. A deliberately held fixture bridge should produce the diagnostic. |

## Tasks

1. Recover historical CI metadata and build the per-attempt ledger. Verify each located signature against its original logs. Mark missing provenance explicitly.
2. Measure the four rows with the evidence contract. Use the existing gates entry point and locked dependencies. Report comparable counts and the residual baseline rate for rows 1–3. Depends on task 1 for historic comparison.
3. Improve only the timeout diagnostic in `tests/interfaces_ui/test_ui_stream.py`. Check the delayed failure and the normal reconnect. This can proceed independently in a separate worktree. Use the original test in measurement before comparing baseline rates.
4. Run targeted causal probes and record the disposition and next repair scope per row. Depends on task 2. A shared change needs a before/after comparison with a control. An inconclusive experiment ends with an unresolved finding.

## Stability and rollback

Keep #605 timing bands, the #576 clock seam, the gates selection and existing product contracts in place. No new dependency or migration is needed. Revert the test-only diagnostic independently if needed. Keep measured evidence with the issue when an experiment or subsequent repair is reverted.
