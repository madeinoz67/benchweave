# G2 gate record — PoC exit

**Gate:** G2 (PRD §7) · **Date:** 2026-09-14 · **Record:** WP09 Task 12, Step 1

## Scope

G2 claims exactly what PRD §7 defines: PRD-01 through PRD-12 pass with
live software, simulated devices, an independently exercised MCP client,
a curated authenticated registry and second-installation reuse, with
fault results and performance measurements retained. This record exists
to satisfy PRD §8's release control — "gate records bind actual
evidence, owner and exact content digests" — so that no draft planning
assumption is mistaken for approval.

Boundaries, stated up front:

- **Simulation only — no hardware claim.** Every run in the retained
  evidence is labelled `SIMULATION`; every timing and volume artifact
  carries `"simulation": true`. PRD §3 step 8 and gates G3/G4 own
  hardware; simulation approvals cannot authorise it.
- **No twelve-class claim.** Two device profiles are implemented (DC
  PSU + embedded-controller simulators) — PRD §7's explicit sentence.

## Index binding

The evidence tree's digest authority is `index.md` in this directory
(WP09 Task 11): one row per retained artifact, each carrying the sha256
over the file's bytes, in two classes — `generated` (regenerable by the
named command; regenerating rewrites the artifact and its digest row)
and `record` (digest-bound, never regenerated). The index excludes
itself by construction, so it is **not** regenerated to include this
record; this record binds the index as committed at `c3556cd`:

- `docs/evidence/poc/index.md` — sha256
  `44427366f2674dda7f36ea4a955b67470de2c3442100973465c2eae31fdbc3ce`

## Evidence set

109 retained artifacts under `docs/evidence/poc/`, every one digested
by the index above:

| Family | Count | Contents |
|---|---|---|
| `runs/` | 101 | `run-001.json` … `run-100.json` + `summary.json` — the seeded 100-run volume leg (PRD §6), fixed seed 20260914 |
| `timing/` | 2 | `prd-load.json` (reference, gating) + `stress-16.json` (non-reference, non-gating) |
| `timed-demos/` | 2 | `leg-1-clean-demo.md` + `leg-2-second-install-reuse.md` — digest-bound records |
| `fault-matrix/` | 2 | `legs.json` + `junit.xml` — the PRD §3 step-6 fault legs with occurrence oracles |
| `decisions/` | 2 | `d13-async-posture.md` + `deferred-deviations.md` — digest-bound records |

## PRD-01 … PRD-12 live-pass map

Sourced from the acceptance suite's docstring coverage contract
(`tests/integration/test_poc_acceptance.py`); every named test and
suite verified present at record time. The journey assertion is the
live leg inside the acceptance suite; the deep suite carries the named
behaviour at depth.

| Row | Journey assertion (live) | Deep suite | Retained artifact |
|---|---|---|---|
| PRD-01 reproducible setup | Every journey test boots from the fixture lattice over `create_app` (suite start: `test_journey_discover_admit_select`) | `tests/integration/test_clean_install.py` (wheel-proven); Linux build legs = CI | `timed-demos/leg-1-clean-demo.md` |
| PRD-02 package reuse | `test_journey_second_install_reuse` | `tests/integration/test_registry_reuse.py` (second-install digest identity) | `timed-demos/leg-2-second-install-reuse.md` |
| PRD-03 authenticated admission | The live admit path itself in `test_journey_discover_admit_select` (resolver closure → change_submit/change_apply; two-phase admin surface is REST-only per the catalog) | `tests/integration/test_registry_reuse.py` + `tests/integration/test_registry_changes.py` (tamper / unknown trust / missing dependency / conflict / revoked vectors) | — |
| PRD-04 real plugin ABI | Both sim plugins execute via the app's published factory/host services (`test_journey_run_rest_retrieve_mcp_report`, fault and reuse legs) | `tests/contract/test_sim_plugins.py` + `tests/contract/test_host_abi.py` | — |
| PRD-05 ownership/admission | `test_journey_admin_change_and_stale_generation_rejected` — run starts on the admitted bench; stale-generation start rejected after the in-journey admin change | `tests/integration/test_takeover.py` + `tests/integration/test_event_recovery.py` | — |
| PRD-06 bounded procedures | The fixture procedure executes all its step kinds (run legs: `test_journey_run_rest_retrieve_mcp_report`, `test_journey_fault_legs`) | `tests/integration/test_procedures.py` | — |
| PRD-07 run/request identity | `test_journey_run_rest_retrieve_mcp_report` — REST start + MCP retrieve = one run; retry legs in `test_journey_fault_legs` | `tests/integration/test_event_recovery.py` + `tests/unit/test_seam_control.py` | — |
| PRD-08 protection/recovery | `test_journey_fault_legs` — lost_response, restart, stale_sample, trip: 4/4 legs verdict `passed`, occurrence oracles exact (8/0/5/2), `failed: 0` | `tests/integration/test_event_recovery.py` + `tests/contract/test_fault_matrix.py` | `fault-matrix/legs.json` + `fault-matrix/junit.xml` |
| PRD-09 measurement honesty | Assertions + verified final safe condition in `test_journey_run_rest_retrieve_mcp_report` (`safe_state == "verified"`; SIMULATION visibly identified via the commissioning document's evidence limitation, byte-pinned read-back) | `tests/integration/test_procedures.py` (stale / wrong-unit) | — |
| PRD-10 parity/access | Same admitted inventory over both transports (discovery leg); same run over both (run leg) | `tests/integration/test_interface_parity.py` (full parity) | — |
| PRD-11 network independence | PRD §5's own observable, verbatim: "finishes within policy through client/registry loss". Client loss and process loss are proven live by the fault legs (`lost_response`, `restart` — verdict `passed`); registry loss during a run is **unevidenced by fault injection and claimed structurally only** — post-admission execution reads the content-addressed cache, never the registry. No dedicated registry-loss journey leg — the Task-6 leg was conditional ("if uncovered") | `tests/integration/test_event_recovery.py` + `tests/integration/test_registry_reuse.py::test_control_stack_run_on_cached_plugin` (the coordinated run executes on a `load_plugin` cache instance — manifest-sha module pin) | `runs/summary.json` (100 runs, `duplicate_dispatch_total: 0`) |
| PRD-12 controlled admin | `test_journey_admin_change_and_stale_generation_rejected` — one staged admission at a safe idle boundary, then one staged `trip_reset` at the safe idle boundary after terminal | `tests/unit/test_seam_admin.py` + `tests/integration/test_registry_changes.py` | — |

The mapped suites' live pass is exercised by the WP09 close gates
(whole-branch double review + gates, Step 2–3 of this task) immediately
following this record.

## Measured targets (PRD §6)

| Target | Result | Verdict | Evidence |
|---|---|---|---|
| Clean demo ≤ 30 min (excl. dependency download) | 10 s total / 8 s post-download on the documented command path | PASS | `timed-demos/leg-1-clean-demo.md` |
| Second-install reuse ≤ 30 min, zero plugin-source changes | 5 s total; 16/16 vendored plugin files digest-identical across installs and byte-identical to the checkout | PASS | `timed-demos/leg-2-second-install-reuse.md` |
| 100 consecutive runs: complete, consistent evidence, no duplicate dispatch | 100/100 `passed`, seed 20260914, `dispatch_occurrences_total: 800`, `duplicate_dispatch_total: 0`, 41.5 s | PASS | `runs/summary.json` (+ the 100 per-run records) |
| Every applicable fault case deterministic; no false passed | 4 applicable legs, all verdict `passed`, occurrence oracles exact (lost_response 8/8, restart 0/0, stale_sample 5/5, trip 2/2), `failed: 0` | PASS | `fault-matrix/legs.json`, `fault-matrix/junit.xml` |
| Reference-host p95 metadata reads ≤ 500 ms | **4.746 ms** (100 reads, 2 observers, one active run, `active_run_coverage: 1.0`) | PASS | `timing/prd-load.json` (`prd-load-reads`) |
| Reference-host p95 run acceptance ≤ 2 s | **4.790 ms** (100 accepts on the idle bench, sequential — see the observer caveat below; concurrent proxy bound: the stress tier's ~5.2× p95 inflation at 16 observers bounds a concurrent-acceptance p95 at ≲25 ms, ~80× under the 2000 ms target) | pass — sequential, idle-bench, observers 1-achieved/2-declared per the caveat below | `timing/prd-load.json` (`prd-load-acceptance`) |
| Product owner accepts the reuse and operator journey | — | ACCEPTED 2026-09-14 | Owner line below |

**Stress tier — non-gating, labelled as such:** `timing/stress-16.json`
records read p95 24.614 ms / max 32.833 ms over 1600 reads at 16
observers (verdict `recorded`, `"reference": false`, `"gating": false`).
It exists to make the D13 disclosure honest, not to gate anything.

**Decision record:** `decisions/d13-async-posture.md` — the
pre-registered protocol's branch three applied as written (PRD-load
targets met on both gating measurements, stress tier clean of material
degradation): the single-loop gateway (blocking SQLite on one ASGI
event loop) stands as the disclosed PoC architecture; no fix slice
named; reopen rule stated there.

## Deviation registrations

| # | Disposition | Binding |
|---|---|---|
| D13 (async single-loop posture) | **CLOSED AS PERMANENT DISCLOSURE** (protocol branch three) — register row updated at `2f6ad46`; the adjacent `create_run`→`put_run_state` crash-window residual remains ledgered, untouched by this close | `decisions/d13-async-posture.md` |
| D4 (legacy free-form event evidence) | **ACCEPTED G2 DEVIATION**, resolution deferred to the dedicated interface-errata slice; pinned meanwhile by `test_interface_parity.py::test_event_evidence_shape_deviation` | `decisions/deferred-deviations.md` (D4 section) |
| D14, details half (six-key error `details` envelope) | **ACCEPTED G2 DEVIATION**, same interface-errata slice as D4; the correlation_id half is **CLOSED** by WP09 Task 1 (`3ebfcb5` — every failure envelope mints a real id); details half pinned by `tests/unit/test_error_model.py::test_failure_body_is_the_rendered_error_envelope` | `decisions/deferred-deviations.md` (D14-details section) |
| D15 (`lease_create` §9 replay-peek asymmetry) | **ACCEPTED**, ledgered — a corpus-permitted behavioural asymmetry, not interface errata | Register row D15, `docs/compatibility.md` |
| D16 (session-wide admission-lock identity) | **ACCEPTED**, ledgered — an internal design question, no wire divergence | Register row D16, `docs/compatibility.md` |

## Boundary disclosures

1. **Author-run timed legs.** Both timed-demo records were executed by
   the WP09 implementer (the author), not an independent operator or
   second engineer, on the development host with a warm uv cache; the
   wall-clock measures the documented command path, not an
   unpracticed operator's reading time; single pass, 1 s timestamp
   resolution; each record discloses its aborted attempts (all
   timing-harness defects, none product or guide defects). The
   records' own caveats are part of the evidence.
2. **Acceptance-observer caveat.** `prd-load-acceptance` records
   `observers: 1` achieved against `observers_declared: 2` —
   concurrent acceptance is structurally impossible on the committed
   fixture lattice (one bench per gateway; §5 holds one live run per
   bench, so a second concurrent `run_start` CONFLICTS at accept
   rather than measuring). The measurement ran sequentially on the
   one bench over distinct §9 keys; the artifact's method text
   discloses the full reasoning.
3. **Reference-host posture.** Every timing and volume artifact carries
   the same `host` block: Darwin 25.6.0, arm64, CPython 3.13.13 — this
   development Mac, not PRD §4's "one Linux host" deployment target;
   Linux build coverage rides CI (PRD-01 map row), not this host's
   measurements.
4. **Restart leg — staged in-process idiom.** The journey's restart leg
   stages the crash in-process (per the task brief's sketch); the
   real-process proof is delegated by map row to
   `test_event_recovery.py::test_kill_mid_run_child_process_recovers_interrupted`
   (`@pytest.mark.slow`: real child process, real SIGKILL mid-body,
   real restart child over the same database, same recovery
   assertions over HTTP).
5. **Single-session admission fence — a product property.** Exactly one
   dependency-closure root goes through live admission per session:
   the resolver's strictly-advancing high-water fence (rollback
   protection) refuses a second resolve of the shared profile package
   at the same status sequence. The journey admits the psu closure
   (profile package + descriptor and implementation releases — three
   exact releases); discovery covers both implementations over fresh
   per-read views. This fence is why PRD-12's in-journey admin pair is
   one admission + one `trip_reset` (the registry change kinds cannot
   re-apply in the same session).
6. **PRD-11 registry-loss — structural, not fault-injected.** The fault
   legs prove client loss (`lost_response`) and process loss
   (`restart`) live; registry loss during a run has no injected leg.
   The PRD §5 sentence — "finishes within policy through
   client/registry loss" — is met on the registry half structurally:
   once admission lands the releases in the content-addressed cache,
   execution reads the cache, never the registry (pinned by
   `tests/integration/test_registry_reuse.py::test_control_stack_run_on_cached_plugin`,
   whose coordinated run executes on a `load_plugin` cache instance,
   module name carrying the manifest sha). Removing the registry after
   admission is not exercised by any leg; the independence claim comes
   from the execution path, not a live registry-outage run.

## Owner

Product decision owner acceptance: ACCEPTED — Stephen Eaton, 2026-09-14,
on review of this record and the evidence tree it binds.

## Commit range

The WP09 work this record binds: `cf0f4c7..c3556cd` (23 commits at
write time; this record's own commit extends the range).

```
3ebfcb5 fix(errors): mint correlation_id on every failure envelope (D14 cheap half)
38eba9d docs(compat): D14 correlation_id half CLOSED by WP09 Task 1 (3ebfcb5)
9f645ec fix(mcp): serve the interface-v1.1.1 tools corpus (align with seam validation)
0a02bd0 fix(checks): check_documents ignores fenced code blocks when scanning links
717581d test(parity): _masked_error helper + wrong-typed approver_token 400 pin
56b48ee test(backup): T10 whole-branch minors — served events_get letter, second-boot refusal, autocheckpoint pin
40f7c2f test(cli): T11 teardown pin + T12 real events_observed assertion
2f4cc93 docs(wall): D14 mint-sites phrasing + HEAD-guard durability note; ledger re-ledgers
4b2e64f test(acceptance): PRD journey scaffold — discover/admit/select live
b38322e test(acceptance): run journey REST+MCP+report, admin + stale-generation legs
b48ead0 test(acceptance): fault legs + second-install reuse — journey complete
d9f7317 feat(evidence): seeded journey volume generator
40f9804 docs(evidence): 100-run seeded volume leg — PRD §3 retained evidence
3ce682b docs(operator-guide): second-install reuse runbook — the PRD §3 step-7 operator flow
8eae570 docs(evidence): timed operator legs — author-run, wall-clock recorded
7373157 docs(evidence): timed-leg record precision — abort duration, verdict scoping, runbook ordering note
939fb5e feat(performance): PRD target measurement + non-gating stress tier
545d527 docs(evidence): PRD §6 reference timing + stress tier — both targets pass
2f6ad46 docs(register): D13 decision landed; G2 deviation registrations
a2638cc feat(evidence): fault-matrix harvest + digest index — evidence group complete
5f7f9a7 docs(evidence): fault-matrix harvest + deterministic digest index
9a04c18 fix(evidence): review minors — command count, hostname scrub at retention, parse guard, dotfile skip, junit family pin, index precondition
c3556cd docs(evidence): regenerated tree post-scrub
```
