# BenchWeave simulated oscilloscope (sim_scope)

A deterministic, entirely synthetic four-channel oscilloscope — the
settings-presets reference instance for issue #6 row A: the first in-tree
plugin whose named measurement setups ship as `ui/presets/` documents next to
a `ui/settings/` schema, a binding catalogue and a presentation envelope.
`benchweave` is the maintainer namespace; it does not identify a hardware
manufacturer. The package is `benchweave-sim-scope`; import
`benchweave_sim_scope.plugin:create_plugin`.

```text
sim_scope/
  pyproject.toml
  README.md
  src/benchweave_sim_scope/
    __init__.py
    plugin.py
    descriptor.json
    vectors.json
    presentation.json
    binding-catalogue.json
    ui/
      manifest.json
      settings/oscilloscope-configure.schema.json
      presets/fast-survey.json
      presets/low-noise-pair.json
```

The simulator implements identify, scalar reads/writes and all five
`otdp.oscilloscope/1.0.0` profile actions over INVOKE (configure, arm,
trigger, fetch, abort). Its clock is injected. Channel enablement is
behaviorally real: `fetch` returns samples for exactly the channels the last
`configure` named. The `arm` configuration-token check catches token
MISMATCH — a half-substituted apply path that configures under one
`configuration_id` and arms under another is refused. It does NOT catch
consistent replay: configure and arm under the same literal preset
`configuration_id` pass clean (pinned by
`test_arm_accepts_consistent_replay_documenting_the_trap`). Defense against
consistent replay belongs to the apply path, which must substitute the
gateway-issued token (CTL-7 marks `configuration_id` issued) — a mechanism
that cannot attach to this full-form descriptor, whose actions declare no
issued keys.

Unlike sim_psu/sim_controller, this descriptor is full OTDP 0.1.2 form and
passes `benchweave-sdk check`. That also means it is NOT admissible by the
runtime execution-contract path (`control/documents.py` requires the minimal
list dialect) — sim_scope is a presentation/presets vehicle, not an
execution-contract fixture, and cannot join `fixtures/execution/` until the
descriptor dialect fork is reconciled.

Settings are writable `semantic: configuration` parameters with
`effect: "setting"` write policies — a settings bundle implies no
energisation. Model averaging is the one settings family with no action-input
home (the closed 0.1.x action schemas cannot represent it in preset
settings), so `averaging_count` is a live-write-only parameter.

## Fetch semantics

Acquisition state is honest, not laundered: arming completes an
immediate-trigger acquisition at arm time; every other trigger kind stays
armed until the `trigger` action fires it. Fetching an incomplete
acquisition refuses (`DEVICE_REJECTED`) unless `allow_partial` is true, in
which case the dataset returns `status: partial` carrying the pretrigger
buffer (`pretrigger_fraction x sample_count` samples) with a `status_reason`
naming the cause. `max_bytes` caps the materialized payload at 8 bytes per
sample per channel: an insufficient budget refuses when `allow_partial` is
false, truncates to the budget (with the actual axis length reported) when
true, and a budget below one sample per channel always refuses — no
representable dataset. `started_at` is the arm time, `dataset_id` is
acquisition-scoped with a per-acquisition fetch counter, and the dataset
carries the configuration snapshotted at arm, so a reconfigure between arm
and fetch cannot re-attribute the evidence.

Dispatch-state posture inside actions: refusals on device state mid-invoke
(incomplete acquisition, aborted acquisition, byte budget, single-use id
violations) report `DEVICE_REJECTED` with dispatch state `DISPATCHED` — the
invoke reached the handler and the plugin did work. Input-shape validation
failures before any handler state is touched report `INVALID_ARGUMENT` with
`NOT_DISPATCHED`. Acquisition ids are single-use: re-arming under an
existing id, live or aborted, is refused rather than silently discarding the
recorded state evidence refers to.

## Authored envelopes

The acquisition envelopes are authored for the simulator, not measured on
hardware: `sample_rate_hz` is capped at 1e6 and `sample_count` at 1e6 samples
per acquisition (32 MB of float64 across four channels). Both bounds are
declared twice, in the descriptor's configure `input_constraints` (enforced by
`check-ui` on presets) and in the plugin's dispatch validation.

## Compatibility

This simulator uses BenchWeave 0.1.0's private synchronous host API, like
sim_psu. It is separately buildable and installable, but not yet independent
of core at runtime; its explicit `benchweave==0.1.0` dependency must be
supplied as a reviewed local wheel while unpublished. The main-repo dispatch
suite (`tests/contract/test_sim_scope_plugin.py`) and the SDK lane suite
(`tests/sdk/test_sim_scope_presets.py`) are the behavioral authorities.
Source and replay vectors are owned here.

Publication and hardware operation require separate authorisation. All
qualification here is synthetic. The existing proprietary project licence
applies; this relocation grants no new distribution rights.
