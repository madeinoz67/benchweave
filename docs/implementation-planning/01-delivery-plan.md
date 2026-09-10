# Smart Test Gateway PoC/MVP Implementation Plan

> **For agentic workers:** Use the executing-plans skill to execute reviewed tasks with checkpoints. Do not start production code from this document without the implementation go-ahead. Subagent execution is optional only when separately authorised. The first detailed task is in 03-first-slice-plan.md; later work packages require their own code-level task expansion at the stated entry gate.

**Goal:** Deliver the PRD's reusable simulated bench PoC, then a separately qualified DPS-150/ESP32 hardware MVP.

**Architecture:** One supervised Linux gateway, one control coordinator and one active controlling procedure. REST/MCP share core operations; adapters use scoped host services; a curated authenticated registry distributes immutable releases. Physical protection and commissioning remain separate from plugin installation.

**Tech stack proposal:** Python 3.13 reference runtime, standard asyncio, SQLite on local disk, a local immutable content directory, Draft 2020-12 validation, FastAPI for HTTP routing, official Python MCP SDK only after pinned-version interoperability is demonstrated, pytest for the test suite. Exact package/OS versions are selected and locked in WP01/WP02; these names are not claims that dependencies have already been installed or validated.

## Global constraints

- STG 1.5; OTDP 0.3.0; adapter API 1.1; registry/execution 1.0.0; interface 1.1.0; MCP 2026-07-28.
- No arbitrary code in procedures, raw-device bypass endpoint, hidden plugin I/O or automatic retry of uncertain physical actions.
- No production trust roots, real credentials, live firmware flashing or energisation in simulator tests.
- Existing synthetic descriptor fixtures are structural examples; create genuinely executable simulator descriptors with complete finite device constraints and real test artefact hashes.
- Hardware target is FNIRSI DPS-150; ESP32 remains a family-level provisional choice.
- A partial milestone advertises only implemented operations/profiles. Full 20 REST/17 MCP operation coverage is required at G2.
- No production repository currently exists for this work. Paths below are proposed paths relative to a future repository root named `smart-test-gateway`; they are not existing workspace files.

## Technology decisions to verify early

FastAPI supplies OpenAPI/JSON Schema support, but the delivered contract remains authoritative; generated models must not widen accepted inputs or drop original document bytes. [FastAPI features](https://fastapi.tiangolo.com/features/)

SQLite is proposed for one gateway's durable state, with serialised writes, explicit transactions and local storage. Commit acceptance/request identity before dispatch; do not hold a transaction open during device I/O. Use a tested durability configuration and backup API/workflow that includes active WAL state. SQLite permits one writer at a time, and WAL durability depends on synchronisation settings; qualify the chosen settings and storage rather than inferring crash safety from the database name. [SQLite transactions](https://www.sqlite.org/lang_transaction.html), [SQLite WAL](https://www.sqlite.org/wal.html)

The MCP project reports Python SDK support for 2026-07-28. Still test the exact chosen package and actual client before building the gateway around it. [MCP release announcement](https://blog.modelcontextprotocol.io/posts/2026-07-28/)

## Proposed repository boundaries

| Path | Responsibility |
|---|---|
| `contracts/` | Exact admitted architecture schemas/catalogs and source manifest |
| `src/stg/contracts/` | Strict parsing, local schema registry and semantic admission |
| `src/stg/content/` | Original-byte content/evidence storage and integrity |
| `src/stg/state/` | Runs, request tombstones, leases, events, generations and recovery transactions |
| `src/stg/control/` | Binding/admission, ownership, scheduler, execution and protection |
| `src/stg/host/` | Scoped transport, clock, dispatch and dataset services |
| `src/stg/interfaces/` | Identity, REST, MCP and administrative adapters |
| `src/stg/registry/` | Verified package resolution, local admission and curated publishing support |
| `src/stg/cli/` | Setup, inspection, demo and report commands |
| `plugins/sim_psu/`, `plugins/sim_controller/` | Real plugins against faultable simulated transports |
| `plugins/fnirsi_dps150/`, `plugins/esp32_controller/` | Hardware plugins, created only after their evidence gate |
| `firmware/esp32_reference/` | Optional reference-DUT firmware, not protection firmware |
| `tests/unit/`, `tests/contract/`, `tests/integration/`, `tests/faults/`, `tests/hardware/` | Separate test purposes and explicit hardware opt-in |
| `fixtures/`, `docs/`, `deploy/` | Versioned demo fixtures, source/operation evidence and service packaging |

The core depends on abstract scoped services, not REST/MCP request objects. Transport exceptions preserve whether dispatch began. One plugin instance represents one physical device even when multiple descriptors/profiles refer to it. Database schemas and internal service signatures are fixed in each work package's detailed plan before code changes.

## Ordered work packages

Each package ends in its own reviewable result. Hardware discovery can proceed alongside simulator work when evidence is available; it is not a reason to block WP01–WP09. Test commands below describe the future repository's acceptance interface, not commands that currently pass.

| WP | Outcome and files | Dependencies / owner | Verification and gate |
|---|---|---|---|
| WP01 | Reproducible project, vendored contracts and strict original-byte JSON handling. `pyproject.toml`, `contracts/`, `src/stg/content/json_document.py`, `tests/unit/test_json_document.py`, `tests/contract/test_baseline.py` | None; core engineer | `python -m pytest tests/unit/test_json_document.py tests/contract/test_baseline.py`; byte hashes, duplicate keys, nonfinite values, schema references and source manifest verified |
| WP02 | Early MCP/client/authentication spike. `src/stg/interfaces/identity.py`, `tests/integration/test_mcp_baseline.py`, `docs/compatibility.md` | WP01; interface engineer | Exact 2026-07-28 live discovery/tool exchange and wrong-audience/expired/scope rejection; record exact dependency/client versions before freezing adapters |
| WP03 | Durable run/lease/request/event state. `src/stg/state/store.py`, `src/stg/state/migrations/`, `tests/faults/test_state_recovery.py` | WP01; core engineer | Process-kill before/after acceptance, same-key different-body conflict, retained tombstone, lease sequence and event continuity; no device I/O inside DB transaction |
| WP04 | Scoped host services and two simulator plugins. `src/stg/host/`, `plugins/sim_psu/`, `plugins/sim_controller/`, `fixtures/protocols/`, `tests/contract/test_sim_plugins.py` | WP01/03; integration engineer | Published ABI, typed datasets, finite device limits, invalid framing, partial delivery, timeout-after-dispatch and no implicit I/O on import/open; G1 |
| WP05 | Procedure admission/execution/protection. `src/stg/control/`, `tests/integration/test_procedures.py`, `tests/faults/test_protection.py` | WP03/04; core engineer | Eight step kinds, lexical scope, identity/resource closure, own lease, total qualification budget, fixed protection deadline and truthful terminal status |
| WP06 | Curated registry and package reuse. `src/stg/registry/`, `fixtures/registry/`, `tests/integration/test_registry_reuse.py` | WP01/04; registry engineer | Pinned signed metadata, full closure, licence/provenance display, tamper/expiry/revocation conflicts, independent local admission, second clean install reuses same plugin digests |
| WP07 | Complete REST/MCP/administration and evidence surface. `src/stg/interfaces/`, `tests/integration/test_interface_parity.py`, `tests/integration/test_event_recovery.py` | WP02/03/05/06; interface engineer | Twenty REST/seventeen MCP operations; start retry parity, original document bytes, chunk integrity, terminal storage gap, safe independently approved changes |
| WP08 | Operator CLI, reports and native service. `src/stg/cli/`, `deploy/`, `docs/operator-guide.md`, `tests/integration/test_clean_install.py` | WP07; delivery engineer | Fresh install, labelled simulation, concise truthful report, reviewed service permissions, backup/restore, fixture/credential separation |
| WP09 | PoC acceptance and performance report. `tests/faults/`, `tests/integration/test_poc_acceptance.py`, `docs/evidence/poc/` | WP01–08; QA + product owner | PRD-01–12, 100 normal simulator runs, fault matrix and second-user reuse; measured read/admission targets; G2 |
| WP10 | DPS-150 protocol/compatibility discovery. `docs/devices/dps150/`, `fixtures/protocols/dps150/`, `docs/devices/esp32-selection.md` | Available equipment/docs; integration + bench owner | HW-01–06 evidence; audit community reuse before coding; decide full PSU profile versus explicitly limited profile |
| WP11 | Hardware integrations, optional ESP32 firmware and supervised fixture. `plugins/fnirsi_dps150/`, `plugins/esp32_controller/`, `firmware/esp32_reference/`, `tests/hardware/test_supervised_fixture.py` | WP09/10 and approved commissioning setup; integration + bench owner | PRD-13/14, genuine protocol vectors, board/power-path review, independent measurement/protection and timing evidence; G3 |
| WP12 | Unattended MVP and operational handoff. `tests/hardware/test_qualified_procedure.py`, `docs/evidence/mvp/`, `docs/recovery.md` | WP11; QA + bench/test-safety + product owner | PRD-15/16, 20 normal hardware runs, approved faults, restore/update/revocation drills and signed qualified procedure; G4 |

No guessed calendar dates or story-point precision are assigned before staffing and hardware availability are known. WP02 and WP10 are explicit risk-reduction gates; a failed gate changes the relevant detailed plan, not the advertised compatibility claim.

## Test matrix and requirement traceability

| Requirements | Work packages | Required evidence |
|---|---|---|
| PRD-01 | WP01, WP08, WP09 | Reproducible build and two clean environments |
| PRD-02–03 | WP06, WP09 | Reuse, signatures, conflicts and revocation |
| PRD-04 | WP04 | Both plugins obey the actual host ABI |
| PRD-05–08 | WP03, WP05, WP09 | Admission, lifecycle, lost replies, process death and protection |
| PRD-09 | WP04, WP05, WP07, WP09 | Measurement validity, exact bytes and honest terminal evidence |
| PRD-10 | WP02, WP07, WP09 | Live MCP/REST/authentication parity |
| PRD-11–12 | WP05–07, WP09 | Network independence and independent administration |
| PRD-13–14 | WP10–11 | Device compatibility and supervised qualification |
| PRD-15–16 | WP12 | Unattended/operational qualification |
| PRD-17 | Post-MVP backlog | Separate prioritised requirement before expansion |

Execute applicable E01–E26 and R01–R16 from the architecture acceptance documents. At PoC exit, physical cases use simulation and are explicitly labelled as such; rerun applicable cases with approved hardware fault methods at MVP exit. A text check or schema specimen is not a substitute for the live behavioural test.

## Execution method and first handoff

- [ ] Review PRD scope and product targets before expanding the whole backlog into code-level tasks.
- [ ] Begin with the detailed first-slice plan; select/create the source repository only when implementation starts.
- [ ] Before each following WP, produce its concrete API/file/test plan against the now-existing repository, with failing tests, implementation steps, verification commands and review boundary.
- [ ] Run each meaningful test first to establish the expected failure, implement the bounded change, run the relevant suite and review the diff before committing.
- [ ] Record actual gate results and unresolved findings. Do not mark a stage complete because time has elapsed or its happy-path demo works.

This is a staged implementation plan with the first coding slice expanded. It does not pretend to contain complete implementations or exact internal signatures for all twelve work packages before their dependency gates have been exercised.
