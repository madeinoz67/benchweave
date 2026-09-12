# BenchWeave simulated PSU

A deterministic, entirely synthetic PSU. `benchweave` is the maintainer namespace; it does not identify a hardware manufacturer. The package is `benchweave-sim-psu`; import `benchweave_sim_psu.plugin:create_plugin`.

```text
sim_psu/
  pyproject.toml
  README.md
  src/benchweave_sim_psu/
    __init__.py
    plugin.py
    descriptor.json
    vectors.json
  tests/
    test_vectors.py
```

The simulator implements identify, scalar reads/writes, reset, error retrieval and the existing dc_psu configure/output/measure actions. Its clock is injected. Output, protection trips and measurements are simulated; no hardware transport or firmware is involved. Source and replay vectors are owned here. The descriptor is the existing execution projection, not a complete OTDP device descriptor.

## Compatibility

This legacy simulator uses BenchWeave 0.1.0's **private synchronous host API**. It is separately buildable and installable, but not yet independent of core at runtime. Its explicit `benchweave==0.1.0` dependency must be supplied as a reviewed local wheel while unpublished. Do not resolve an unrelated same-name package from an index. The public SDK's OTDP bridge currently lacks profile actions; replacing this API during a directory cleanup would remove exercised behaviour. This package is not the template for new external plugins.

Build with `uv build`. In an isolated environment, install the supplied gateway wheel, this wheel and pytest 9.1.1, then run `python -m pytest tests`. No parent checkout or editable core install is required. The core contract/fault/procedure suites additionally exercise integration, deadlines, partial application and protective trips. Signed registry payloads remain immutable snapshots; the fixture builder reads this source when explicitly rebuilding them.

Publication and hardware operation require separate authorisation. All qualification here is synthetic. The existing proprietary project licence applies; this relocation grants no new distribution rights.
