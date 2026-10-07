# Issue #394 — Standalone mock transport for binary §8.1 SEND/RECEIVE plugins (design of record)

**Date:** 2026-10-05
**Status:** Design of record (pre-implementation). Owner ruling received and incorporated: **GO on (a)+(d)** — the vectors.json evidence file carries the dialect+encoding declaration (additive keys; `request`/`response` unchanged; request-less rows valid), and a demand-driven byte-stream host sibling of `LoopingMockHost` serves it with the serial backend's exact RECEIVE semantics. Rejected on the record: (b) an ignorable-by-contract descriptor `x-` extension; (c) a corpus descriptor field (disproportionate standards bump — upgrade path documented in §10). Ruling posted to issue #394.
**Issues:** gateway #394 (this fix), #285 (the hardware exit gate that wants an offline rehearsal path — PRD 11 increment I3).
**Reporter's context:** an external contributor's 6-channel ADC plugin (`adc_6ch_12bit`, an external project; PRD 11 §Background cites the same contributor fork as the standalone-host demand evidence). Nothing in this design depends on that plugin being in either tree — the proof runs on a synthetic fixture (§8, Step-0 discrepancy 2).

---

## 0. Step-0 findings (gate answers, carried from the 2026-10-05 study)

All line numbers verified against `benchweave-sdk` standalone HEAD `da932e3` (edit target) and, where noted, the gateway submodule pin `8d17c10` (tag v0.6.0). Mechanism text is byte-equivalent at both for everything this design touches except `serial.py`, which is standalone-only (I3a, post-pin).

### Q1 — transaction-grammar declaration: FAIL as originally posed; RESOLVED by the owner ruling

Findings (all verified):

1. The descriptor declares transport **type and bounds only**: `standards/otdp/0.2.2/otdp-device-descriptor.schema.json` `$defs/transport` = `oneOf` nine transport types, each `type`/`connection_key`/`settings` (baud, terminations, `max_frame_bytes`, …). No transaction-kind or dialect field exists anywhere in the block.
2. `transaction_grammar[]` exists only on transport-provider contracts (`standards/otdp/0.2.2/otdp-transport-provider.schema.json:28`, required at `:214`) and **by rule cannot express generic dialects**: `transport-providers.md:45` — "a provider grammar introduces **new** kinds and never shadows an entry of this table; the §8.1 kinds … are reserved". The reserved seven are pinned at `packages/sdk/src/benchweave_sdk/validation.py:372–380` (SDK) and `src/benchweave/control/documents.py:129–131` (gateway twin; drift obligation 17).
3. `mock_exchanges` consults no declaration and hardcodes the scaffold dialect: `src/benchweave_sdk_server/session.py:140–165` at HEAD (`row["request"]` unconditional at `:160`; same mechanism at the pin, `row["request"]` at `session.py:102`). Its own docstring (~`:144–148`) states the R7 bound: "a plugin whose adapter speaks a different shape will fail the mock's exact-match discipline honestly".
4. Even where a grammar declaration exists (provider lane), the standalone session never reads it at connect: `load_plugin_project` validates descriptor + presentation only; `validate_transport_provider` (`validation.py:610`) has no standalone caller.

**Verdict:** for a generic-§8.1 plugin there is no declared dialect surface. The owner ruling (2026-10-05, issue #394) resolves the contract question: the declaration lives in the plugin's own evidence file, `vectors.json` — additive keys, `request`/`response` meaning unchanged, request-less rows valid — and the host serves it demand-driven. This design implements that ruling.

### Q2 — RECEIVE semantics in the serial backend: PASS

Authoritative implementation: `src/benchweave_sdk_server/serial.py` (I3a); prose twin `user_guide/plugin-sdk.qmd` §"A standalone runtime around the writer" (`SerialStandaloneHost`), test-pinned by `tests/test_guide_serial_host.py`.

- Strict field sets (`serial.py:37–43` `_FIELDS`): `stream_send {kind, data}`; `stream_receive {kind, max_bytes, termination, exact_bytes}`; `stream_exchange` adds `data`. Unspecified fields → `ValueError("not a section 8.1 stream transaction")`.
- `exact_bytes` positive **takes precedence over** `termination`; `termination` ∈ {lf, crlf} on serial (no `eom` → ValueError); `exact_bytes` ∈ None|0..max_bytes; `max_bytes` int 1..transfer_ceiling (64 KiB default), clamped by the descriptor's `max_frame_bytes`.
- No terminator within `max_bytes` → those bytes discarded + `ValueError("no terminator within N bytes")` — an incomplete frame is never returned as complete.
- **Quiet-line is not an error code**: empty buffer + expired quiet window (100 ms default) → `{"data": b""}` ("nothing offered: a quiet line, not an error"; the DPS-150 telemetry drain ends on it — guide lines ~180–182). A deadline mid-frame → `TimeoutError`, partial bytes stay buffered for the next receive; once a partial frame is buffered the quiet window no longer applies (serial.py `_IDLE_POLL_S`, FOLD-C).
- Short write → `ConnectionError("serial write reported N of M bytes")` (`tests/test_guide_serial_host.py::test_a_short_write_is_a_connection_error_and_nothing_is_read`).

The byte-stream mock reproduces each of these **outcomes** (not the timings — §3.5).

### Q3 — vectors.json consumption: PARTIAL — the named path is out-of-tree; in-tree consumers enumerated

`if key not in ex: continue` exists in **no in-tree file** (text search, both repos, 0 hits). It is the reporter's plugin's own codec tests. In-tree:

- Contract A — the standalone/scaffold evidence file `{evidence, exchanges: [{request, response}]}` (`template/src/{{ package_name }}/vectors.json`, mirrored in `tests/fixtures/scaffold_expected/{base,ui}/src/example_plugin/vectors.json`) — is consumed **only** by `mock_exchanges` (`session.py:140–165`), which hard-indexes `row["request"]` (the issue's symptom 1).
- The generated codec tests (`template/tests/test_plugin.py.jinja`) script `MockHost` via `protocol.transaction()` and literal responses — they never read vectors.json, so their meaning cannot change.
- Contract B — `plugins/benchweave/sim_*/src/*/vectors.json` (`{plugin, meta, vectors: [{name, setup, request, expect}]}`, e.g. `plugins/benchweave/sim_scope/src/benchweave_sim_scope/vectors.json`) — is auto-replayed by the gateway fault matrix (`tests/contract/test_fault_matrix.py`). A different contract with different consumers; untouched by this design.

**Fix constraint (binding):** `request`/`response` keep their existing meaning (strings); request-less rows stay valid; every new key is additive and ignorable by row-iterating consumers.

### Discrepancy 1 — `tools/bridge_integration_check.py`: absent (resolved)

`find` over both trees returns nothing; no `tools/` carrier exists. What carries the §8.1 SEND/RECEIVE shapes today: the normative table `standards/otdp/0.2.2/otdp-specification.md` §8.1 ("Scoped transfer grammar"); the reference implementation `src/benchweave_sdk_server/serial.py`; the pinned guide twin (`user_guide/plugin-sdk.qmd` + `tests/test_guide_serial_host.py`); and the gateway bridge `src/benchweave/host/otdp_bridge.py` (REG-4's mirror — "the real bridge" the reporter's adapter was proven against). **Single authoritative source the mock must match: the corpus §8.1 table, with `serial.py` as the behavioural reference** — the acceptance rule (§9) pins outcome parity against the backend, not against prose. SW-61's shared conformance cells (the `MockHost` cells run against the serial backend over a loopback fixture) do **not** exist yet; `tests/server/test_serial_link.py:22` `LoopbackPort` is the loopback precedent. This design builds the shared cells (§9, family E).

### Discrepancy 2 — the reporter's plugin: absent (resolved)

`plugins/` holds `benchweave/` (sim_controller, sim_psu, sim_scope), `esp32_controller/`, `fnirsi/`. The reproducer cannot run from a stock checkout and the proof must not depend on an external project. **Offline proof home: a synthetic binary-grammar fixture** built to the issue's stated shape (hex-encoded rows, one response-only row, a `stream_send`/`stream_receive` adapter) under an invented name — `tests/fixtures/binary_frames_plugin/src/binary_frames_demo/` in the SDK repo, mirroring `tests/fixtures/setpoint_plugin/` (the presentation/preset fixture precedent). In-tree shape precedent only (not a proof dependency): `plugins/fnirsi/dps150` — binary frames, `stream_send` at `adapter.py:115`, its own Host doubles in `tests/test_adapter.py`; it carries no vectors.json and stays a real-hardware plugin.

---

## 1. Mechanism

### 1.1 The vectors.json declaration contract (ruling (a))

Additive keys on Contract A only (§0 Q3). Contract B files are untouched.

| Key | Level | Values | Default when absent | Refusal |
|---|---|---|---|---|
| `transaction_dialect` | file | `"stream_exchange"` \| `"send_receive"` | `"stream_exchange"` (today's behaviour, byte-for-byte) | `standalone_vectors_dialect_unknown:` naming the value |
| `encoding` | file | `"ascii"` \| `"hex"` | `"ascii"` (the string's ASCII bytes — today's behaviour) | `standalone_vectors_encoding_unknown:` naming value + row |
| `encoding` | row | same; overrides the file-level default for that row | file-level value | same |
| `name` | row | string, echoed in diagnostics when present | row index | — |
| rows | — | `{request, response}` (request-bearing) or `{response}` (response-only / device-initiated) | — | `standalone_vectors_row_shape:` (both keys missing, or non-string payload); `standalone_vectors_row_unscriptable:` (a response-only row under the `stream_exchange` dialect — the default dialect cannot script an unsolicited frame; the message names the row and says response-only rows require `transaction_dialect: "send_receive"`) |

Decoding: `ascii` → `frame = row_string.encode("ascii")` (a non-ASCII string refuses `standalone_vectors_encoding_invalid:` naming the row); `hex` → `frame = bytes.fromhex(row_string)` (odd length or non-hex characters refuse `standalone_vectors_encoding_invalid:` naming the row). The existing `standalone_transport_script:` no-exchanges refusal (session.py) is unchanged and applies to both dialects.

### 1.2 Script construction (`session.py`)

`mock_exchanges(plugin)` keeps its exact current behaviour for the default dialect. New, beside it:

- `vectors_script(plugin) -> VectorsScript` — parses and decodes once; raises the `standalone_vectors_*:` family above (a `PluginLoadError`-shaped ValueError, so the connect path maps it to a typed `not_ready` carrying the diagnostic — the same seam mapping `standalone_transport_script:` already rides).
- `frame_script(plugin) -> list[FrameRow]` — the `send_receive` script: ordered `FrameRow(name, request: bytes | None, response: bytes)`.
- `mock_transport_factory(plugin) -> Callable[[], HostServices]` — the dialect selector, late-bound on the session's CURRENT plugin exactly as `mock_plugin_session` (`session.py:303` at HEAD) is today, so a reload's reconnect speaks the reloaded plugin's own script (the M1-fold closure shape). Default dialect → `lambda: LoopingMockHost(mock_exchanges(plugin))`; `send_receive` → `lambda: ByteStreamMockHost(frame_script(plugin))`. `mock_plugin_session` and scenario mode (`scenarios.py:448–459`, whose `_transaction` at `:141` scripts `stream_exchange`) keep their current construction; scenario mode is deferred (§7 D5).

Transport selection itself stays where it lives: `cli.py::_build_seam` ("Transport selection happens HERE and nowhere else", cli.py:80–82; the mock branch at `:150`). The seam still receives a `PluginSession` over the mock; the dialect only selects which mock host the session's services factory builds at connect.

### 1.3 The byte-stream host (`benchweave_sdk_server/transport.py`, new class beside `LoopingMockHost`)

`ByteStreamMockHost(MockHost)` — same file, same package (`benchweave_sdk_server`, the `[server]` extra; see §6 PKG ruling). It inherits `MockHost`'s clock discipline hooks, evidence recording, `close_transport`, and exhaustion posture, mirrors `LoopingMockHost`'s real-clock overrides (`monotonic`/`utc_now`/`_check`, transport.py:100–115) and its establishment/tail-recycle semantics (`cycles`/`establishment`/`_plays`, transport.py:69–98), and **replaces** `transfer` with frame semantics:

State: a deque of `FrameRow`s (the script), an `_inbound: bytearray`, the recycle cursor.

- **Advance rule:** whenever the oldest unconsumed row is response-only, append its response bytes to `_inbound`, consume it, and repeat (recycling the tail if the deque empties and cycles permit — `LoopingMockHost`'s exact tail rule: the script after its establishment head; a single-row script is its own cycle).
- **`stream_send {kind, data}`:** advance; if no request-bearing row remains (exhausted, no cycles left) → the inherited honest-exhaustion `ConformanceError` (the `test_exhausted_transport_fails_honestly_with_correlation` posture, `tests/server/test_seam.py:137`). Take the head request-bearing row; if `data != row.request` → **`ConformanceError`** carrying the row key (name or index) and the hex diff: expected-vs-got frames, hex-rendered (this is the genuine-mismatch half of the R7 split — the exact-match discipline, now at frame granularity). On match: consume the row, append `row.response` bytes to `_inbound`, return `{}`.
- **`stream_receive {kind, max_bytes, termination, exact_bytes}`:** validate bounds exactly as `serial.py::_receive_bounds` does (imported — see below); then serve from `_inbound` with `serial.py`'s `_receive` semantics: positive `exact_bytes` pops exactly N when buffered; otherwise terminator search within the first `max_bytes` (found → return including terminator; `max_bytes` filled without terminator → discard those bytes + `ValueError("no terminator within N bytes")`); empty `_inbound` → the quiet-line answer `{"data": b""}` **immediately** (same outcome as the backend's 100 ms window, deterministically — a receive-before-send against a pending request row is a quiet line, exactly as on real hardware); deadline reached with a partial frame buffered → `TimeoutError`, partial bytes retained (FOLD-C: no quiet answer once a partial frame is buffered).
- **`stream_exchange {kind, data, …receive}`:** the SEND step then the RECEIVE step in one call.
- **Field-set strictness:** `_FIELDS` is imported from `.serial` (`serial.py:37–43`) — one definition shared by the backend and the mock; unspecified fields refuse `ValueError` on both, and the shared definition cannot drift (the SW-61 spirit, made structural).
- **Other §8.1 kinds** (`can_receive`, `can_send`, `i2c_transfer`, `spi_transfer`): not served by the mock — the inherited `ConformanceError` mismatch path (R7-honest; §7 D2).

### 1.4 The R7 split (binding discipline)

- A **scripting problem** — the evidence file cannot express what it is being asked to script (unknown dialect, bad encoding, malformed row, response-only row under the default dialect) — surfaces as a stable `snake_case:` refusal naming the row, at connect, through the existing typed-`not_ready` seam mapping. Never a raw `KeyError` (today's symptom 1) and never a bare `ConformanceError`.
- A **genuine adapter/script disagreement** — the adapter SENDs a frame that differs from the scripted row's frame — IS a `ConformanceError`, carrying the row key and the hex diff. That is the point of the exact-match discipline, preserved at frame granularity.

### 1.5 Timing posture

The mock matches the backend's **outcomes**, not its timings: the quiet-line answer is immediate (not 100 ms), and a receive that cannot complete holds until the operation's own deadline (`HostOperationContext`, descriptor-declared `timeout_ms`) and then raises `TimeoutError` — the same exception the backend raises. No test in this slice asserts a wall-clock duration; the timing-lane rule is respected by construction (outcome asserts only).

### 1.6 Scaffold and guidance surfaces (same PR)

- **Base scaffold unchanged** (byte-identical `scaffold_expected/base`; default dialect is the omitted-key default).
- **`--with-ui` starter** moves to the binary dialect so the response-only path is exercised by default: its `vectors.json` declares `"transaction_dialect": "send_receive"`, keeps text frames, and carries one response-only row (a status line) placed after the identify exchange; its `protocol.py` gains the guide's drain idiom (receive until `{"data": b""}`) before each read's send, so the unsolicited frame is consumed deterministically (the DPS-150 telemetry-drain pattern the guide already teaches); `template/src/{{ package_name }}/vectors.json` and `protocol.py` become jinja-conditional on `with_ui`; `tests/fixtures/scaffold_expected/ui/` re-pins (it already differs from base: `UI-GUIDE.md`, `presentation.json`, `binding-catalogue.json`, `ui/`, `test_presentation_preview.py`).
- **`template/CLAUDE.md.jinja`** grows the agent guidance: declare the transaction dialect explicitly; the vectors row contract including response-only rows; verify offline (`serve --transport mock`, connect, read, apply, capture) before hardware.
- **Plugin-authoring guidance** lives at: `user_guide/plugin-sdk.qmd` (the SDK's authoring guide — its serial-host section is the worked example), `template/AI-GUIDE.md`, and the seeded per-plugin skills `template/src/{{ package_name }}/skills/{develop-plugin,drive-plugin}/SKILL.md.jinja` plus `template/.claude/skills/benchweave-adapter-testing/SKILL.md.jinja`. There is no `.claude/skills/` plugin-authoring skill in either repo (verified: main has `generated/`, `increment/`, `panel/`, `retrospective/`; the SDK submodule has `increment/`, `panel/`, `release-review/`). The new "Mock transports" section lands in `user_guide/plugin-sdk.qmd` (both grammars, how selection works, the row contract, what each mock can and cannot rehearse, when `--transport serial` and hardware are required, and the R7 bound in plain English); `AI-GUIDE.md` and the develop-plugin skill cross-reference it.
- **Changelog:** git-cliff renders both repos' changelogs from conventional commits — no hand edits (standing rule). The SDK commits carry `feat(server): … (gateway #394, #285)`; the gateway entry rides the merge event.

---

## 2. Minimal first slice

Ships in this slice: the declaration contract (§1.1), `vectors_script`/`frame_script`/`mock_transport_factory` (§1.2), `ByteStreamMockHost` (§1.3), the synthetic fixture `tests/fixtures/binary_frames_plugin/` (descriptor with serial transport + identify/read/write/capture, presentation for the stage→apply→read-back triad, hex vectors with one response-only row — mirroring `tests/fixtures/setpoint_plugin/`), the shared parity cells (§9 family E), the refusal-taxonomy tests (NFR-Q4), the no-write arm over the new host (NFR-O3), the `--with-ui` starter change (§1.6), the guide section + template guidance, and the changelog-carrying commits.

## 3. Deferral table

Deferral homes per the increment skill's amended rule (at most ONE follow-on issue per merged PR; the rest defer as documentation): **D1 = follow-on issue, created at PR-open time on the gateway tracker (single issue stream), body naming this record as the carrier increment — its carrier (#285's hardware run) is scheduled. D2–D5 = documentation (this table); the issue files when the reopen trigger arrives.**

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D1 | Unsolicited-frame interleaving control (row-level delay/ordering beyond row-order release) — the mock releases response-only bytes strictly in row order | follow-on issue (opened at PR-open) | the first #285-class hardware run producing a captured trace whose unsolicited interleaving the row-order model cannot rehearse — a named trace attached to that issue |
| D2 | Mock coverage of `can_receive`/`can_send`/`i2c_transfer`/`spi_transfer` (today: inherited honest ConformanceError) | documentation (this table) | a plugin declaring any of those kinds reaching `serve --transport mock` — an admission or tracker issue arriving that names the kind |
| D3 | `eom` termination on the mock (serial has none; `lan_scpi`/`usbtmc` transports do) | documentation (this table) | the first non-serial-transport plugin (`transport.type` in {lan_scpi, usbtmc}) with `send_receive` vectors reaching connect on the mock |
| D4 | Promoting the proven vectors.json dialect semantics into the corpus (the rejected (c), as upgrade path) | documentation (this table) | the dialect becoming cross-bench-semantic — a procedure, run record, capture or admission consumer needing to know a device's frame dialect (the arrival of such a consumer on the tracker or a corpus train) |
| D5 | Scenario mode over the byte-stream host (scenario mode today scripts `stream_exchange` via `scenarios.py:141/_transaction` and works for the reporter per the issue; a `send_receive` plugin whose scenario flow must drive its real adapter would hit the R7-honest mismatch) | documentation (this table) | a `send_receive` plugin whose scenario-mode flow fails at connect with the ConformanceError mismatch — a reproduced failure attached to the issue |

## 4. Precedent

- **`LoopingMockHost`** (`benchweave_sdk_server/transport.py:33`) — the sibling's direct precedent: subclass `MockHost`, change exactly the pieces a live server needs (tail recycle, real clocks), inherit the tested discipline. `ByteStreamMockHost` does the same and changes only `transfer` + the script shape.
- **`MockHost`'s exact-match discipline** (`benchweave_sdk/testing.py` — whole-dict comparison, `ConformanceError` naming expected/got, dispatch-marker enforcement, honest exhaustion) — preserved at frame granularity; the dict-exact original is untouched and remains the default dialect's host.
- **`serial.py`'s receive semantics + `_FIELDS`** — imported, not re-implemented; one definition serves backend and mock (outcome parity is pinned, not hoped).
- **`mock_plugin_session`'s late-bound closure** (`session.py:303`) — reload-safety precedent for `mock_transport_factory`.
- **The typed-`not_ready` connect mapping** (session.py `connect`, the refute-fold-2 class) — the `standalone_vectors_*:` family rides it; `standalone_transport_script:` is the naming precedent.
- **The guide's drain idiom** (`user_guide/plugin-sdk.qmd`, the DPS-150 telemetry drain ending on the quiet-line answer) — the `--with-ui` starter's unsolicited-frame handling.
- **`tests/fixtures/setpoint_plugin/`** — the fixture precedent for a presentation-bearing test plugin.
- New architecture? No new architecture is introduced; the one genuinely new contract surface (the vectors.json declaration keys) is the owner-ruled (a), an additive extension of an existing plugin-owned evidence file.

## 5. Invariant impacts

- **CTL/STO: untouched.** No `control/`, `state/`, or protective-path change; this slice lives in the SDK's standalone server package.
- **REG-1/REG-2:** unchanged and inherited — the byte-stream host is a `HostServices` double under the same lifecycle (import → open → execute → close), dispatch-marker enforcement and `TimeoutError` deadline honesty come from `MockHost`/`LoopingMockHost` (the spec §8 "minimal mock-host contract" exception classes).
- **CON-4 / obligation 6–7 (pointer):** no standards bytes move (the point of ruling (a)); the gateway PR advances the `packages/sdk` pointer to the SDK release tag that carries this work, paired with the SDK's own version bump, lock anchor and mirror per obligation 7 — the release train carries the pairing (the anchor-before-tag ritual the v0.7.1 recovery re-taught). Note: the pin currently sits at v0.6.0 while v0.7.1 is released, so the `sdk-drift` lane is red until the next pointer advance — this train's pointer PR clears it.
- **Obligation 3 (device-developer-guide):** no gateway-side motion — the changed behavior is standalone-SDK plugin-visible behavior whose surface is the SDK guide + scaffold (§1.6), not the gateway host.
- **Obligations 12/17/19/23:** untouched (no renderer surface, no reserved-seven motion, no shared-skill clause change, no CLI verb-set change — `--transport mock` behavior extends, no verb added).
- **Obligation 20 (version-literal zero gate):** no new version literals; the counter scans `.py` ASTs, and the new template/fixture JSON introduces none anyway.
- **NFR-O3 (no device writes on page load/reconnect/preset selection):** must hold over the new host — an explicit proof cell (§9 family G), not an assumption.
- **NFR-Q4 / STD-4 (error text prefixes are API):** every new `standalone_vectors_*:` prefix is pinned by a test (§9 family D).
- **R7 (design-level bound):** preserved with the §1.4 split.
- **No `invariants.md` amendment is required** — no hard invariant changes meaning; the design records its own contract in this record and in the guide.

## 6. Packaging ruling (PKG-1/PKG-2)

The new host lives in `benchweave_sdk_server/transport.py` — the `[server]` extra — **not** in `benchweave_sdk/testing.py`. The base wheel's contents and dependency set are unchanged: `testing.py` stays the finite, dict-exact, manual-clock double that base-wheel consumers and the generated plugin tests use; a serving-only, real-clock, frame-script host belongs to the server package that already owns `LoopingMockHost` and `serial.py`. No new dependency; `bytes.fromhex` is stdlib.

## 7. Top risks

| # | risk | failure mode | falsified by |
|---|---|---|---|
| R1 | recycle semantics drift between the two hosts (the byte-stream tail restore diverges from `LoopingMockHost`'s) | a polling server desyncs after N cycles (an unsolicited row re-released at the wrong point) | a soak cell over ≥50 cycles asserting the frame sequence repeats exactly (the `tests/server/test_serial_soak.py` pattern), plus the unchanged `tests/server/test_transport.py` recycle arms |
| R2 | the ConformanceError hex-diff format becomes de-facto API and drifts | operators' (and the reporter's) tooling matches on a message that changes | pin the exact one-line format in a dedicated test; treat format changes as STD-4 API changes |
| R3 | row-order unsolicited release does not model a real streaming device's interleaving | an offline rehearsal passes while the hardware run (#285) sees interleavings the mock never produced | disclosed as D1; the hardware run's captured trace is the real proof — the acceptance rule (§9) explicitly does not claim hardware-coverage |
| R4 | the `--with-ui` starter's drain idiom regresses the scaffold (generated tests, presentation preview) | scaffold_expected/ui mismatch or a generated-project test failure | the scaffold suite re-pins both expected trees in-slice; base stays byte-identical (a byte-equality assert, not a spot check) |
| R5 | the declaration is advisory — an adapter can contradict its declared dialect | a plugin declares `send_receive` but its adapter sends frames the script never scripted; failure appears only at connect/first transfer | by design (R7 honest failure): the ConformanceError names the row and both hex frames; nothing silently passes |
| R6 | someone asserts a timing (the mock's immediate quiet answer vs the backend's 100 ms) | a flaky or false-parity test | outcome-only asserts written into the parity cells; the record names timings out of scope |
| R7 | the record's own diff carries `asyncio` (tests) → Tier 3 → mandatory two-lane refute cost | review cost, not a defect — budgeted in §10 | — |

## 8. Measurable proof

Fixture: `tests/fixtures/binary_frames_plugin/src/binary_frames_demo/` (invented name) — serial transport, identify/read/write capabilities plus capture declaration, presentation for the setpoint triad, hex-encoded vectors with one response-only row. Today, at the merge base, its connect-on-mock fails exactly as the issue reports (`KeyError: 'request'` through `standalone_plugin_connect`).

**RED control (mandatory, G3):** neutralize only the selector — restore `mock_plugin_session`'s factory to the unconditional `LoopingMockHost(mock_exchanges(plugin))` (a `cp`-backup mechanism-neutralization per the worktree discipline, never a stash pop) — and run the new suite: the fixture's connect must fail with the pre-fix failure shape; every family-D refusal cell must lose its typed prefix (the raw KeyError/ConformanceError returns); the parity family E's mock legs must fail (no byte-stream host). Restore; all green. `no tests ran` counts as FAILED — collected counts read from `--junitxml` attributes or exit codes, never a filtered summary line.

## 9. Pre-committed acceptance rule (written before any measurement runs)

**Metric:** pass rate over a pre-declared matrix of **25 new-behaviour cells**, plus zero regressions in the existing suites.

- **A — connect-and-operate over the mock (5 cells):** on the binary fixture, `serve --transport mock` + connect completes (A1) identify, (A2) parameter read, (A3) write stage→apply→read-back, (A4) bounded capture (declared `sample_count` served, artifact manifest digest-bearing), (A5) reconnect after disconnect re-speaks the establishment head (the M1-fold shape).
- **B — response-only rows on both dialects (2 cells):** served as unsolicited frames under `send_receive`; typed `standalone_vectors_row_unscriptable:` naming the row under the default dialect.
- **C — genuine SEND mismatch (1 cell):** `ConformanceError` carrying the row key and the hex diff of expected vs got.
- **D — refusal taxonomy (4 cells):** `standalone_vectors_dialect_unknown:`, `standalone_vectors_encoding_unknown:`, `standalone_vectors_encoding_invalid:` (bad hex, named row), `standalone_vectors_row_shape:` — each surfacing through the typed-not_ready connect mapping, each pinned (NFR-Q4/STD-4).
- **E — RECEIVE outcome parity, SW-61 (12 cells = 6 behaviours × 2 hosts):** exact_bytes precedence over termination; `lf` termination including the terminator; `crlf` termination; no-terminator-within-max_bytes → discard + `ValueError("no terminator within N bytes")`; quiet-line → `{"data": b""}`; partial frame at deadline → `TimeoutError` with bytes retained. Hosts: `ByteStreamMockHost`, and the serial backend over the `LoopbackPort` fixture fed the **same wire bytes** — the cells are one parametrized battery over a host factory.
- **F — unchanged existing behavior (0 new cells, gate):** the full SDK suite (`tests/` + `tests/server/`, including `test_transport.py`, `test_seam.py`, `test_scenarios.py`, `test_nowrite.py`, scaffold suites) green with the base scaffold fixture byte-identical.
- **G — NFR-O3 over the new host (1 cell):** the `test_nowrite.py` recording pattern over the binary fixture on `ByteStreamMockHost` — zero writes on page load/reconnect/preset selection.

**Sample size:** the 25 cells once at the slice commit, plus one cold full SDK suite run and the fast-lane gates (`ruff`, config-driven bare `mypy` fresh-cache, focused pytest) at every commit per #247.

**SHIP if:** 25/25 pass AND family F fully green AND the RED control shows every family failing without the mechanism.

**KILL if:** any family-E cell diverges between the mock and the serial backend (an outcome mismatch is a design failure — the cell is not tuned until it passes); any family-D cell surfaces a raw `KeyError`/`ConformanceError` to the operator; family F regresses; or the base scaffold fixture changes by a single byte.

**UNDERPOWERED (not conclusive → DEFER), if:** the serial-backend legs of family E cannot execute in the reviewing environment (loopback fixture unconstructible), or the `--with-ui` scaffold legs cannot run on this platform — in that case the missing legs are carried by CI (the Windows doctrine: CI-corroborated, never locally claimed) and the verdict is DEFER, not SHIP.

## 10. Review tier and Step-1 keyword scan (issue #254, design-time call)

**Tier 3.** Triggering rules: (i) the expected diff text contains the keyword `asyncio` (test code — the new host's and parity batteries use `asyncio.run`); (ii) the gateway-side PR **advances the `packages/sdk` submodule pointer**. Both are Tier-3 rules on their own. Consequences: full cold suite for the touched packages, mandatory refute pass, and — per the standing two-lane doctrine — **two independent adversary lanes**.

Keyword scan over the whole expected diff (SDK: `transport.py` +~170 lines, `session.py` +~90, template jinja +~60, fixture tree, `user_guide` section +~70, tests +~450; gateway: this record, the gitlink, no gateway code). Counts are expected-diff enumerations the review re-derives from the actual diff:

| keyword | expected count | carrier |
|---|---|---|
| `asyncio` | ~22 | new test files (`asyncio.run` per cell), the record's own §1.5/§10 text |
| `threading` | 0 | serial.py untouched; the record says "reader thread", not the token |
| `subprocess` | 0 | — |
| `sha256` | 0 | no digest work; record cites no digests |
| `hashlib` | 0 | — |
| `migrate` | 0 | — |
| `recovery` | 0 | — |
| `protection` | 0 | no protective-path content; the record does not use the token |

No `standards/` path, no JSON Schema, no `state/`, no registry seam, no fixture-digest lattice (SDK test fixtures are not the gateway `fixtures/registry/` lattice), no dependency change.

## 11. Repository and PR-stack layout

Two repos, one work; complete only when every PR in both is merged. All issues on the gateway tracker (single issue stream — #394 links every PR; SDK PRs note that no SDK-side issue exists by design).

1. **SDK repo** — work in `/Users/seaton/Documents/src/benchweave-sdk` (standalone; never edit `packages/sdk` in place), branch `feat/issue394-mock-bytestream`:
   - PR-1 (SDK): the whole slice — mechanism, fixture, tests, template, guide, deferral issues opened at PR-open time per §3. Conventional commits reference gateway #394/#285 (git-cliff renders the changelog at release).
   - The release train (version bump → standards-lock anchor inside the SDK repo before tagging → tag) turns the work into a pointer-advanceable release; the v0.7.1 anchor ritual applies verbatim.
2. **Gateway repo** — `/Users/seaton/Documents/src/BenchWeave`, slice branch carrying this record as its first commit:
   - PR-2 (gateway): the submodule pointer advance to the SDK release tag (paired per obligation 7 with whatever version motion the release train recorded). No gateway code, no standards bytes. Merge on the complete `gh pr checks` rollup (`scripts/merge-verified.sh`), never a filtered view.
   - The D1 follow-on issue (§3) opens at PR-1 time; D2–D5 are documentation rows in this record's table. This record is committed before the measurement runs — the pre-commitment provability the deep-review directory exists for.

**Builder obligations:** every new source file carries an `author: Stephen Eaton` header; RED first (a failing test from the issue's reproducer shape before any production line); gates read from true exit codes / junitxml attributes; the fast lane runs at every commit including docs-only.

## 12. Rejected alternatives

- **(b) Descriptor `x-` extension key** (e.g. a transport-settings `x-…-stream-dialect`): schema-legal today and zero corpus bytes, but ignorable-by-contract — `x-` keys are unread-when-unmirrored by design, so the declaration would be structurally optional in a way nothing ever surfaces. Rejected on the owner ruling; recorded here because it was the closest zero-corpus descriptor-side cousin.
- **(c) A corpus field on the descriptor schema** (`stream_dialect`): the only home where admission *enforces* the declaration — but an OTDP standards bump (governance event, in-arc sweeps 6/7/8/18) is disproportionate for a host-scripting concern whose consumer is one offline mock. Rejected on the owner ruling. **Upgrade path (D4):** if the dialect ever becomes cross-bench-semantic — a procedure, run record, capture or admission consumer needing a device's frame dialect — promote the proven vectors.json semantics into the corpus through a normal bump, with this slice's field experience as the evidence.
- **Per-row transaction-shape declarations** (the issue's direction 2, taken literally): rejected in favor of a file-level dialect with per-row `encoding` override only. The dialect is a property of the adapter's whole conversation — per-row kind declarations would permit scripts no single adapter could replay (a `stream_exchange` row between two `send_receive` rows) and would multiply the refusal taxonomy; rows keep only data-level variation.
- **Switching the base scaffold to `send_receive`:** rejected — the base starter and its expected fixture stay byte-identical (family F's byte-equality assert), proving the omitted-key default is exactly today's behavior; only the `--with-ui` starter moves.
- **Docs-only (state the R7 bound, ship no mechanism):** rejected — #285's exit gate (full-rate capture on this plugin class) wants an offline rehearsal path, and the demand is proven by a real external plugin, not hypothetical.
- **Extending `benchweave_sdk/testing.py` with the byte-stream host:** rejected on packaging (§6) — it would move base-wheel contents for a serving-only concern.
