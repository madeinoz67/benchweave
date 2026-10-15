# BenchWeave architecture map

The repo component map — what each subsystem owns (moved here from CLAUDE.md §1).

| Subsystem | Packages | What it owns |
|---|---|---|
| Control core | `src/benchweave/control/` | Admission (documents, semantics, binding, policy), the executor, the safe-transition engine, the run coordinator |
| State | `src/benchweave/state/` | The single-writer SQLite store, migrations, the one-coordinator file hold |
| Contracts | `src/benchweave/contracts/` | Architecture contract models and schema bindings |
| Registry | `src/benchweave/registry/` | Local registry admission, package locks, resolver, authenticity |
| Host / plugins | `src/benchweave/host/` | The device-plugin ABI, host services, the OTDP bridge |
| Interfaces | `src/benchweave/interfaces/` | MCP (17 vendored-exact `stg_v1` tools), REST, identity, the app/worker |
| Content & vendoring | `src/benchweave/content/`, `vendoring.py` | Exact-byte JSON documents, packaged-first vendored-asset resolution |
