# Issue #66 — sim_psu/sim_controller DISPATCHED posture on post-dispatch refusals

Design record for the increment closing madeinoz67/benchweave#66 (row-A FR1 parity).
Committed before the build so the acceptance rule is provably pre-committed.

## Summary

sim_psu and sim_controller report `dispatch_state: NOT_DISPATCHED` on refusals that
occur after the operation was dispatched into the plugin handler and the *device*
evaluated it — contradicting the doctrine the same plugins already pin elsewhere
(`_write_parameter` re-homing, the trip-after-apply comment,
`test_psu_ovp_trip_raw_write_reports_dispatched`) and the precedent sim_scope shipped
in row A (`_state_reject`, PR #58 FR1).

The consumer that makes it run-meaningful: `Executor._dispatch`
(`src/benchweave/control/executor.py`) maps `NOT_DISPATCHED` failures to
`BODY_EXECUTION_ERROR` and any dispatched failure to `BODY_OUTCOME_UNKNOWN`. A
device-state refusal that lies about dispatch therefore launders an
outcome-uncertain step into a clean pre-dispatch error — exactly the ambiguity
collapse A06 forbids.

## Mechanism

Port sim_scope's `_state_reject(request, message)` verbatim in doctrine (docstring
and all): `ErrorCode.DEVICE_REJECTED` + `DispatchState.DISPATCHED`, for refusals
where the plugin did evaluation work. Input-validation failures before any handler
state is touched keep `_reject` / NOT_DISPATCHED.

### Sites flipped (5)

| Plugin | Site | Refusal |
|---|---|---|
| sim_psu | `_write` | tripped latch (`tripped (…); reset required`) |
| sim_psu | `_write` | envelope bounds (out-of-range **and** wrong-type — one branch) |
| sim_psu | `_action_output` | configuration_id token mismatch |
| sim_psu | `_action_measure` | configuration_id mismatch |
| sim_controller | `_write` | operator_note length limit |

### Decision D1 — wrong-type flips with the bounds branch

The bounds check runs before `_coerce`, so a non-numeric value for a bounded
parameter is refused by the envelope branch as DEVICE_REJECTED today. The branch is
one code path; flipping its dispatch posture flips both inputs. Reclassifying
wrong-type to INVALID_ARGUMENT is an error-code change owned by the dialect/classification
reconciliation (#63), not this increment. Pinned by
`test_psu_write_wrong_type_on_bounded_parameter_reports_dispatched`.

## Fault-matrix knock-on (the vectors the issue predicted)

`vectors.json` in both plugins is replayed verbatim by
`tests/contract/test_fault_matrix.py`; the WP05 plan prescribes extending them this
way.

- sim_psu: `write_setpoint_out_of_bounds`, `write_wrong_type_invalid_framing`,
  `invoke_measure_requires_current_configuration` → `dispatched`.
  New vectors: `write_while_tripped_reports_dispatched`,
  `invoke_output_stale_token_reports_dispatched` (previously unpinned sites).
- sim_controller: `write_note_too_long_device_rejected` → `dispatched`.

**Refute correction (2026-09-19):** an earlier draft of this section claimed "no
digest pins them (verified by search)" — true for `vectors.json`, false for the
plugin sources themselves: the registry fixture lattice
(`fixtures/registry/origin-*/benchweave/*`) embeds the plugin bytes in signed
`payload.zip`s, and `tests/contract/test_registry_admission.py` asserts byte-identity
with the live source (G5 lockstep). The initial gate run missed that suite; the
adversary refute caught it (Finding 1, HIGH). Fixed by rebuilding the lattice via
`scripts/registry/build_fixtures.py --out fixtures/registry` in this branch — the
same-commit rebuild precedent is `9505db0`.

**Refute disclosure addendum (Finding 2, LOW):** the `_action_measure` token check
fuses type and mismatch (`not isinstance(configuration_id, str) or … !=`), so a
non-string measure token also reports DEVICE_REJECTED + DISPATCHED on this branch,
where `_action_configure` refuses a non-string token as INVALID_ARGUMENT /
not_dispatched. Same judgment class as D1, same #63 deferral; splitting the fused
check is row-called in the PR rather than silently reclassified here.

## Invariant impacts

- `OperationResult.__post_init__`: ERROR + DISPATCHED is a legal combination (only
  UNKNOWN status cannot claim NOT_DISPATCHED). No ABI change.
- `OTDPBridge._convert` contradiction check applies to out-of-process adapters;
  these sims are in-process and unaffected.
- Executor mapping itself is untouched — its conservatism (dispatched failure →
  outcome_unknown) is by design; the plugins stop lying to it.

## Deferrals (each cites an open issue)

- Error-code classification reconciliation (INVALID_ARGUMENT vs DEVICE_REJECTED for
  envelope/wrong-type) — #63.
- sim_scope polish items — #65.

## Acceptance rule (pre-committed)

RED-first: the new/extended pytest assertions in `tests/contract/test_sim_plugins.py`
are shown failing on the pre-change tree; then the plugin edit lands and the focused
suites go green (`test_sim_plugins.py`, `test_fault_matrix.py`, plus ruff and bare
mypy). RED control: reverting the plugin edit (cp backup) flips the assertions back
to failing. Executor consequence: the two legs (sim refusal dispatch_state; executor
mapping) are each tool-proven, and the composed flip execution_error →
outcome_unknown is stated as their composition.

Measured value: run records for steps hitting these five refusals stop claiming
pre-dispatch cleanliness — the honest `outcome_unknown` bucket per A06.
