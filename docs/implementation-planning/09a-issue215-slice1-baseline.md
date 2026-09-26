# Issue #215 slice 1 — A1 baseline measurement (committed before the mechanism)

**Status:** Measurement record · **Tracking issue:** madeinoz67/benchweave#215 ·
**Design:** `docs/implementation-planning/09-standards-dependency-design.md` §4 Slice 1, acceptance rule A1.

The design's kill direction for A1 requires the 23/26 baseline to reproduce
across three runs at this slice's merge base BEFORE any mechanism lands. This
file is that measurement, committed on the branch ahead of the first mechanism
commit. All figures below are this run's own measurements (the PRD §1.2 figures
are the contributor's report; A1 re-measures — design §9, third bullet).

## Environment

- Gateway merge base: `403c061` (origin/main at run time; submodule pin
  `packages/sdk` = `3b14d0e`).
- SDK under test: wheel built from `git archive 3b14d0e` of the standalone SDK
  checkout (never a clone-and-edit), `benchweave_sdk-0.3.0-py3-none-any.whl`,
  477,244 bytes, sha256
  `4251827438eb0826f7f2b4506f52a196fc601a614385b9fbd4fd6a724c42e36f`.
- Plugin under test: `parkview/benchweave` at `de132a292040415f9935b93b424ce15b9980843d`
  (pre-restamp), installed from `git archive` bytes into a clean `uv venv`
  (Python 3.13.13) — the fork root project `benchweave-adc` 0.1.0 non-editable,
  dev group deps pinned by the fork's own pyproject (pytest, pytest-timeout,
  httpx, benchweave-sdk>=0.1.0 satisfied by the wheel above).
- Network disabled at run time by a sitecustomize socket guard in the venv
  (connect/connect_ex/create_connection/getaddrinfo/gethostbyname raise); zero
  socket attempts were made by the suite (any attempt would have surfaced as a
  guard RuntimeError, none did).

## Conformance lane

The lane is `tests/adc/test_adapter_conformance.py` — the SDK-conformance
surface (imports `benchweave_sdk.conformance`/`testing`/`validation`). It
collects 26 tests at this commit. The wider `tests/adc` tree (105 tests) also
runs green-for-the-same-reason elsewhere; the 26-test conformance lane is the
PRD §1.2 denominator and is what A1 pins.

## Baseline matrix (three runs, network blocked)

| Run | Collected | Passed | Failed |
|---|---|---|---|
| 1 | 26 | 23 | 3 |
| 2 | 26 | 23 | 3 |
| 3 | 26 | 23 | 3 |

Machine-derived rows and failure texts: `issue215-baseline/baseline-matrix.json`
(generated from the three runs' junitxml; host paths and timestamps removed).

Identical failure set in all three runs (names and first lines verbatim from
the junitxml messages):

1. `test_descriptor_is_schema_valid` — `ValueError: Contract validation
   failed: '0.2.2' was expected` (the ACTIVE schema's `otdp_version` const
   dump; the descriptor pins 0.2.0).
2. `test_lifecycle_is_quiet` — same const-dump shape, same pin.
3. `test_capture_sequence_configure_arm_events_fetch_abort` —
   `ValueError: unknown_contract_schema: otdp/0.2.0/otdp-runtime.schema.json`
   (the SDK vendors one OTDP version; the suite resolves schema paths from the
   descriptor's own pin via `OTDP_SCHEMAS = f"otdp/{DESCRIPTOR['otdp_version']}"`).

This is exactly the PRD §1.2 snapshot: two "'0.2.2' was expected" failures and
one `unknown_contract_schema: otdp/0.2.0/otdp-runtime.schema.json`, 23/26. The
baseline reproduced on all three runs, so A1's re-baseline kill direction does
not fire and slice 1 proceeds.

## Wheel-size baseline (for the served-set payload delta)

Merge-base wheel (one served version per standard, 6 lock rows):
477,244 bytes. The post-slice wheel (9 served versions across 6 standards)
delta is re-measured from a wheel built the same way and committed with the
mechanism.
