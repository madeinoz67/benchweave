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
```

The simulator implements identify, scalar reads/writes and all five
`otdp.oscilloscope/1.0.0` profile actions over INVOKE (configure, arm,
trigger, fetch, abort). Its clock is injected. Channel enablement is
behaviorally real: `fetch` returns samples for exactly the channels the last
`configure` named. Configuration token discipline matches sim_psu — `arm`
requires the stored `configuration_id`, so replaying a preset's literal
placeholder token into a future apply path fails visibly.

Unlike sim_psu/sim_controller, this descriptor is full OTDP 0.1.1 form and
passes `benchweave-sdk check`. That also means it is NOT admissible by the
runtime execution-contract path (`control/documents.py` requires the minimal
list dialect) — sim_scope is a presentation/presets vehicle, not an
execution-contract fixture, and cannot join `fixtures/execution/` until the
descriptor dialect fork is reconciled.

Settings are writable `semantic: configuration` parameters with
`effect: "setting"` write policies — a settings bundle implies no
energisation. Model averaging is the one settings family with no action-input
home (the closed 0.1.1 action schemas cannot represent it in preset
settings), so `averaging_count` is a live-write-only parameter.

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
