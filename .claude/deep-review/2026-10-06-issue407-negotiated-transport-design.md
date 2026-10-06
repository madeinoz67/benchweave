# Issue #407 design — the negotiated serial transport: `reconfigure_link` + live link state

- **Issue:** madeinoz67/benchweave#407 (`sdk` label) — the owner-approved follow-on to #393.
- **Verdict:** BUILD. Two PRs, one issue, sequential (SDK first, then the gateway pointer).
  Maximum tier across slices: **Tier 3** (keyword rule; scan below).
- **Evidence baseline (read, not assumed):** gateway `main` at `1c4e18f` (the #393/#406 merge
  `7fdae81` underneath); SDK standalone checkout at `51f1938` = `origin/main` (`2f9bbd0`) plus
  one unrelated capture-test commit; `gh issue view 407` (no comments); pre-flight clean —
  no rival branches on either repo touching serial/interfaces paths, one open SDK PR (#123,
  unrelated). Files read: `plugins/benchweave/adc_6ch_12bit/src/adc_wire/{negotiate.py,codec.py}`,
  `plugins/.../tests/{emulator.py,a3_sustained_stream.py}`,
  SDK `src/benchweave_sdk_server/{serial.py,seam.py,session.py,mcp.py,catalogue.py,events.py,cli.py}`,
  SDK `src/benchweave_sdk/interfaces.py`, SDK `tests/server/test_serial_conformance.py`
  (outlined), `tests/server/test_cli_serial_wiring.py` (header), gateway
  `tests/sdk/test_adapter_agreement.py`, `docs/internal/{invariants.md,review-rubric.md,
  drift-and-obligations.md}`.

## 1. Root cause — why the negotiation is emulator-only today

`adc_wire.negotiate.negotiate_stream` (the #393 host-side sequence) drives the OTDP §8.1
transaction surface through a `reopen: Callable[[int], Awaitable[None]]` hook — the host's
port-reopen move (`plugins/.../adc_wire/negotiate.py`, `Reopen` and `negotiate_stream`'s
signature). The SDK serial backend implements the transaction half
(`SerialCaptureServices.transfer`, `serial.py:639`) but **nothing implements the reopen
half**: `SerialLink` is single-transport for life (`serial.py:109` — one reader thread
started at `__init__`, `close()` is terminal), and `SerialCaptureServices` exposes no
link-control member. Every existing proof of the negotiation therefore runs against
`EmulatorServices` in-process, where `reopen` is `emu.host_baud = baud`
(`tests/a3_sustained_stream.py`, `_reopen`: "The in-process reopen"), or against the pty
harness where the same closure merely updates the emulator's host-baud model. No adapter
can negotiate against real hardware because the host cannot reopen a port at new settings
while keeping the services object (and its capture state) alive. That is the whole defect:
one missing, protocol-blind capability.

## 2. The mechanism

### 2.1 SDK — the capability (the substance of the increment)

**`benchweave_sdk/interfaces.py` — one new capability Protocol, base contract untouched.**

```python
class LinkControlServices(HostServices, Protocol):
    """A transport whose line settings the adapter may reconfigure ..."""
    async def reconfigure_link(
        self, settings: dict[str, Any], context: OperationContext
    ) -> dict[str, Any]: ...
```

`HostServices` itself (five members: `monotonic`, `utc_now`, `transfer`, `close_transport`,
`record_evidence`) does NOT change, so `EXPECTED_HOST_SERVICES` in the gateway's three-way
pin keeps matching. The precedent is `CaptureServices` and `DatasetServices`
(`interfaces.py:114`, `:155`) — capability-optional Protocols with the documented-gap row in
`tests/sdk/test_adapter_agreement.py` (`EXPECTED_CAPTURE_SERVICES`, `EXPECTED_DATASET_SERVICES`).
A host without the capability hands adapters plain `HostServices`; adapters detect with
`hasattr(services, "reconfigure_link")` (no `runtime_checkable` machinery needed — the
member check is the whole test).

**`serial.py` — four additions.**

1. `negotiable_bauds(settings) -> frozenset[int]` — the guard-rail derivation: the allowed
   switch set is `{boot baud} ∪ settings["x-negotiated-bauds"]`. The `x-` key rides
   `transport.settings` (the schema-legal lane; the descriptor schema grants serialTransport
   no standard VID/PID — the same lane `usb_identity_filter` uses for
   `x-standalone-usb-vid/pid`, `serial.py:793`). Validation is structural only — a non-empty
   list of positive non-bool ints — and fails LOUD at session build with the prefixed error
   `standalone_serial_negotiated_bauds: ...` (the `standalone_serial_usb_hint` FOLD-F
   posture: an unparseable declared value must not become a silently-empty capability). No
   range table, no speed-plausibility check — A02: which bauds a bench may use is the
   descriptor author's declaration, not a constant we tune. A missing key is not an error:
   the allowed set is `{boot baud}` and every switch refuses (fail-closed opt-in).

2. `SerialLink.receive_depth` — an int counter on the link, incremented under `self._cond`
   at `take()` entry, decremented in a `finally` at exit. This is the "refused
   mid-receive" guard's fact source: a parked or running receive is structurally visible.

3. `LinkReconfigurator` (frozen dataclass): `opener`, `device_path`, `boot_settings`,
   `allowed_bauds`, `on_link_event`. It is the factory's knowledge (opener + settings)
   made reusable for the reopen — minted by `serial_plugin_session`, which already holds
   every input (`serial.py:737`).

4. `SerialCaptureServices.reconfigure_link(settings, context)` — the member, in the
   house discipline order (grammar first, then liveness, then guards, then I/O — the
   `transfer` order at `serial.py:639`):

   - **Grammar:** the closed field set is `{"baud"}` — any other key refuses
     `ValueError("standalone_serial_reconfigure_fields: ...")` (the §8.1 strict-field-set
     style). Boot settings never change: the reopen settings are literally
     `{**boot_settings, "baud": N}`; parity/stop bits/data bits/rtscts are boot-carried,
     and a request naming any of them is refused by the field-set rule, not silently
     applied.
   - **Liveness:** cancelled or expired context refuses `TimeoutError` before any I/O
     (the C06/C07 posture).
   - **Guard rails:** baud ∉ allowed set refuses
     `ValueError("standalone_serial_baud_not_negotiable: ...")` naming the allowed set;
     `link.receive_depth > 0` refuses `ValueError("standalone_serial_reconfigure_busy: ...")`.
     Constructed without a reconfigurator (the conformance cells' direct construction),
     the member refuses `standalone_serial_reconfigure_not_configured:` — the capability
     is configuration, present-but-degrading-loudly, never a silent no-op.
   - **The swap (one attempt, no retry — A06):** copy the link configuration
     (`ring_capacity`, `quiet_s`, `transfer_ceiling` off the live link), `old.close()`
     (joins the reader through the proven path), check the deadline again, then
     `await asyncio.to_thread(opener, device_path, {**boot, "baud": N})`; mint a FRESH
     `SerialLink` over the new transport and rebind `self._link`; update
     `self._link_settings`; publish the applied event; return the applied settings dict
     (the read-back is the caller's proof).
   - **Failure posture:** an opener error publishes the failed event and re-raises as
     `ConnectionError` — the services then have NO link (the NFR-O2 faulted posture: a
     faulted link never serves a second conversation). The host NEVER retries; the
     adapter's fallback may call `reconfigure_link` again for the boot baud explicitly —
     that is the caller's move (the negotiate fallback shape), not a host retry.

   **Why a fresh link, not a transport swap inside the link:** the M1 fold's law — "a
   reconnect starts a new conversation over a new link" (`serial_plugin_session`'s
   docstring). A baud change is a line reset: every byte in the old ring arrived at the
   old baud and is residue by definition, so "drain" is correctly implemented as the old
   ring dying with the old link. This dissolves the two hardest questions in the brief
   for free: there is no mid-switch ring (no drop-oldest accounting during the swap, no
   double-count risk — the old link's counters die with it), and the reader thread's
   drain-and-rejoin is the already-proven `close()` join plus one thread start. In-flight
   `take()` waiters cannot exist (the busy guard); an in-flight `write` on the old
   transport either completed (stale bytes the far end garbles — harmless) or raises the
   already-typed `ConnectionError` at the transfer layer.

**`session.py` / `seam.py` / `catalogue.py` — live state and events.**

- `PluginSession` gains a settable `link_event_publisher` field (None default). The
  factory in `serial_plugin_session` reads it at MINT time and threads it into each
  `SerialCaptureServices` — late binding in the factory is the established shape
  (`cli.py`'s own docstring: "session factories read the CURRENT plugin at connect
  time... the late-bound shape").
- `StandaloneSeam.__init__`, serial kind only, sets
  `session.link_event_publisher = self._publish_link_event`; `_publish_link_event`
   publishes **kind `"link"`** on the seam bus. The bus is the every-surface channel by
   construction (events.py: "one append-only order for every surface" — REST, SSE,
   MCP all serve it), so switch and fallback-revert events reach every surface with zero
   web.py/mcp.py work. The seam stays the only publisher; the services hold a callback,
   not the bus.
- Event taxonomy (small, closed): `{"event": "reconfigured" | "reconfigure_refused" |
  "reconfigure_failed", "from_baud": int, "to_baud": int, "reason": str?,
  "operation_id": str}`. The protocol-level story (which frame was lost, why the fallback
  fired) stays in adapter `record_evidence` — the host has no protocol knowledge by
  design; the bus carries the LINK state machine only.
- `_op_host_info` adds a `"link"` block: `{"baud": N, "boot_baud": M, "negotiable":
  bool}` from `session.services` when serial and connected, `null` otherwise (mock and
  scenario transports). `_op_device_get` overlays the same block additively.
  `catalogue.py` motion: `_HOST_INFO_RESULT` gains the declared `link` property
  (`["object","null"]`, `additionalProperties: False` inside, required); `_IDENTITY_RESULT`
  gains `link` as an optional property; the `events_get` description names the link
  family. The event `kind` is a free string in the schema (`catalogue.py:690`) — no enum
  motion.
- No dispatch marker is required for `reconfigure_link`: the §8.1 marker discipline gates
  transmits to the device (`serial.py:655`); a link control transmits nothing.

**Compatibility with #119 (the merged conformance suite):** additive by construction.
`SerialLink` gains one counter; `SerialCaptureServices` gains constructor args with
defaults and one member; nothing in the C01–C13 cell bodies or the four mutants changes
semantics — `take()`'s loops, the quiet-line rule, the closed-link drain-then-refuse, and
the faulted posture are untouched. The acceptance rule below makes "the #119 file stays
byte-stable and green" a ship condition rather than a hope.

### 2.2 Gateway — the pointer, the REG-4 row, and the real lane

1. `packages/sdk` pointer advance (obligation 7: pushed, existing commit).
2. `tests/sdk/test_adapter_agreement.py`: one additive row in the documented-gap family —
   `EXPECTED_LINK_CONTROL = frozenset({"reconfigure_link"})` with the "SDK-only surface"
   comment, checked against the pinned submodule's Protocol exactly as the capture and
   dataset rows are. No gateway `src/` change; no `ADAPTER_API_VERSION` bump (the
   capability-protocol precedent: `DatasetServices` landed as a gap row, not a version).
3. `plugins/benchweave/adc_6ch_12bit/tests/test_negotiation_real_backend.py` — the real
   lane (the issue's test scope). The A3 harness shape, promoted from one-off instrument
   to cells: `os.openpty` + real pyserial on the slave + `SerialLink`/`SerialCaptureServices`
   from the PINNED submodule (`sys.path` insert — the `test_adapter_agreement` import
   precedent) + the baud-aware `AdcEmulator` pumped on the master (`_PtyFar` generalized)
   + `negotiate_stream` with `reopen` now driving `services.reconfigure_link`.

   **The far-end baud coupling (the load-bearing test decision).** A pty has no bit
   timing — bytes never physically garble, on any platform; even at real termios speeds
   the kernel stores the number and times nothing. So wrong-baud observability must be a
   MODEL at the far end regardless; the only question is what feeds the model. Termios
   read-back is dead on the dev platform, measured: macOS termios has no `B2000000`/
   `B3000000` and pyserial cannot even open a pty slave at 2 Mbps (`OSError [Errno 25]
   Inappropriate ioctl for device`, reproduced in the SDK venv this session). The design
   therefore couples the far end through the **opener injection seam**: the test wraps
   the real opener once — `record(settings["baud"]); return real_opener(device, {**
   settings, "baud": <pty-legal>})` — and the pump sets `emu.host_baud` from the recorded
   request. The emulator's existing M7 discipline does the rest (writes at a disagreeing
   host baud are dropped and counted as `garbled_bytes`). Why this is honest: the
   recording sits INSIDE the production reopen path — `reconfigure_link` must actually
   call the configured opener with the requested baud for the far end to switch. A
   backend that lies (keeps the old port, skips the reopen) leaves the far end at the old
   baud and every post-switch frame garbles — the negotiation cannot reach slim. The
   lane's real layers (link swap, join, thread restart, ring reset, guards, events,
   state) are exercised for real; the baud layer is model-coupled through the same seam
   production uses. On silicon the same opener sets a real UART. Disclosed residual:
   kernel-level line-speed setting is never tested by a pty and is commissioning
   evidence, not CI evidence.

### 2.3 What the real lane proves that the in-process lane cannot

- **Revert-on-silence, host side for real:** the fallback's boot-baud reopen is a real
  `reconfigure_link` (close/join/open over the pty), not `emu.host_baud = ...`.
- **Reopen latency as a device-enforced window:** the emulator's `t_revert_s` guard is a
  real wall clock that fires while the host is inside its reopen. Green arm: default
  `t_revert_s = 0.25` vs a pty reopen of milliseconds — ≥ 5x margin, asserted on outcome
  only. Red arm: `t_revert_s = 0.05` with a planted 0.3 s sleeping opener — the device
  must revert (6x separation), the post-switch exchange must garble, the negotiation must
  fall back. Neither assert reads a wall clock (#119's lesson, applied).
- **Sequencing across the reopen:** SET_BAUD's ACK is consumed at the old baud BEFORE the
  swap (the negotiate order), and the new link's ring starts empty — proven by
  `garbled_bytes == 0` on the green arm.

## 3. Slices, carriers, and deferrals

**One increment, two sequential PRs (no stacking — the gateway PR needs only the SDK
merge, not an open SDK branch):**

- **PR-1 (SDK repo, `feat/issue407-reconfigure-link`):** the interfaces Protocol; the four
  serial.py additions; the session/seam/catalogue wiring; new
  `tests/server/test_serial_reconfigure.py` (the R-cells and mutants — a NEW file with its
  own minimal doubles, deliberately not touching `test_serial_conformance.py`; see
  compatibility clause); `tests/server/test_link_state.py` (host_info/device_get/events);
  parity additions for the host_info `link` block; user-guide section (published docs —
  document-writer agent, STE register) and the events/catalogue description text.
- **PR-2 (gateway repo, `feat/issue407-negotiated-lane`):** the pointer advance, the
  REG-4 additive row, the real-lane test file. No `src/`, no `standards/`, no descriptor
  motion.

**Deferrals (explicit):**

1. **The ADC plugin's descriptor and adapter wiring.** The plugin project has NO
   descriptor and NO adapter today — only the `adc_wire` library (`src/adc_wire/` is the
   whole `src/`). Wiring `negotiate_stream` into an adapter's open path (with
   `x-negotiated-bauds` declared in a real descriptor) is the plugin's next increment;
   #407 delivers and proves the capability. The `x-` key lands as a validated,
   documented, host-side derivation exercised through synthetic settings.
2. **Agent-facing reconfigure (a catalogue operation).** Refused by design: an
   agent-driven link switch is host-side protocol knowledge with no safety story; the
   adapter drives every protocol step (the issue's own scope). Revisit only with a
   commissioned use case.
3. **Real-hardware commissioning** (actual UART garble, USB-adapter reopen latency on
   silicon) — per-bench qualification evidence under A02, out of CI's reach by nature.
4. **Linux real-baud arms** (real `B3000000` termios on CI runners, no opener remap) —
   an optional additive cell; CI-corroborated posture if cheap, dropped without ceremony.
5. **Dropped-byte diagnostic continuity across reconfigures** (a services-level
   accumulator) — `dropped_bytes` is "surfaced nowhere yet, by design"; extend it when a
   status surface wants it.
6. **Non-baud negotiable settings** (parity, stop bits) — the field set refuses them;
   widening is a descriptor-schema question with no current evidence.
7. **A `link`/`established` event at connect** — the boot baud is already visible via
   host_info; the family stays switch/refuse/fail until a watcher demonstrates the need.
8. **UI presentation of link state** — host_info's block is machine-readable; any widget
   is the UI lane's call.

## 4. Precedent register (every landing zone)

| Landing zone | Precedent |
|---|---|
| Capability Protocol beside the base contract | `CaptureServices`/`DatasetServices`, `interfaces.py:114/:155`; gap rows `EXPECTED_CAPTURE_SERVICES`/`EXPECTED_DATASET_SERVICES` |
| Fresh link per line reset | the M1 fold (`serial_plugin_session` docstring: a reconnect starts a new conversation over a new link) |
| Reader join + close semantics | `SerialLink.close()` (`serial.py:325`) — reused verbatim for the old link |
| Strict field-set grammar, grammar-first order | `_FIELDS` + `transfer` (`serial.py:49`, `:639`) |
| `x-` extension keys under `transport.settings`, loud validation at use | `usb_identity_filter` + the FOLD-F `standalone_serial_usb_hint` refusal (`serial.py:793`, `:963`) |
| Late-bound factory reading session state | `cli.py` `_build_seam` docstring; `mock_plugin_session` shape |
| Events: new family on the seam bus | the reload family publishing outside `call()` (events.py docstring; seam.py reload paths) |
| Catalogue result motion, additive | `_HOST_INFO_RESULT` history (transport/sdk_version/presentation additions) |
| Real-lane harness over pty + emulator + pinned SDK import | `a3_sustained_stream.py` (the whole shape) and `test_adapter_agreement.py` (the submodule import) |
| One attempt, failure = faulted posture | NFR-O2 (a faulted link never serves a second conversation), REG-2's no-silent-retry clause (A06) |

## 5. Invariant and drift impacts

- **No CTL, no STO.** No protective path, no store, no persisted format, no migration.
- **No standards bytes move.** No `standards/` path is touched; no corpus manifest row; no
  version-string motion; `ADAPTER_API_VERSION` stays `"1.1"`. The standards-involvement
  tripwire (`git diff origin/main...HEAD -- standards/` empty) holds on both PRs. The
  bws catalogue is SDK-server source, not vendored standards — its schema edit is
  ordinary SDK code motion with its own parity pins in the same PR.
- **REG-4 gains an additive amendment** (the new documented-gap row pinning
  `LinkControlServices`' member set). This is the only invariants-adjacent motion; it
  lands in PR-2 with the pointer.
- **Obligation walk (drift-and-obligations.md):** 7 (pointer exists and pushed — PR-2),
  8 (adapter protocol surface: additive gap row, no version bump — this design's
  obligation-8 motion is exactly the agreement-test row), 19 (shared skills — the
  increment skill's flow, already followed). Obligations 1/2/15/16/17 do not fire (no
  `stg_v1` tool, no openapi, no provider lane, no transport-settings.json, no transfer-kind
  change). SDK-side: the user guide gains a section (the guide's example stays untouched,
  still pinned by `tests/test_guide_serial_host.py`); `test_cli_serial_wiring.py`'s
  factory-path arms stay green by construction (the publisher is late-bound, transport
  selection unchanged); presentation-page tests that read host_info get the additive
  `link: null` expectation in PR-1.
- **Module contract:** `serial.py`'s docstring gains the reconfigure law (the fresh-link
  rule, the busy refusal, the one-attempt rule) — module docstrings are where SDK-side
  behavioral contracts live; no `docs/internal/invariants.md` row is proposed (that file
  anchors gateway `src/benchweave/` paths).
- **A02 posture:** the allowed-baud set is descriptor configuration; `t_revert`/`T_switch`
  remain the adapter/plugin's commissioned windows. Nothing in this increment hardcodes a
  numeric envelope — the only constants are structural (field sets, event names).
- **A06 posture:** one close+open per call, no host retry, ambiguous outcomes stay
  ambiguous (a failed reconfigure leaves a typed `ConnectionError` and a closed link; the
  negotiate layer's `link_state: "unresolved"` classification is unchanged and still the
  adapter's).

## 6. Tier call and the Step-1 keyword scan (#254)

**Tier 3, both PRs; the train's maximum is Tier 3** → two independent adversary lanes at
review (the standing two-lane doctrine for Tier 3).

- **PR-1 (SDK), expected diff** — `interfaces.py`, `serial.py`, `session.py`, `seam.py`,
  `catalogue.py`, `events.py` (docstring), two new test files, parity test additions,
  guide/docs. Scan over the expected diff text (docs and code alike):
  `asyncio` ≈ 8 (the `reconfigure_link` body's `asyncio.to_thread`, liveness checks,
  test cells), `threading` ≈ 3 (the mid-receive cell's worker thread, the reconfigurator
  docstring, a mutant), `subprocess` 0, `sha256` 0, `hashlib` 0, `migrate` 0,
  `recovery` 0, `protection` 0. **Rule that fires: the diff text contains `asyncio` and
  `threading` → Tier 3.**
- **PR-2 (gateway), expected diff** — pointer, `tests/sdk/test_adapter_agreement.py`
  (additive row), the new plugin test file. Scan: `threading` ≈ 2 (the pty pump far-end
  thread), `asyncio` ≈ 5 (async cells, `negotiate_stream` drivers), others 0.
  **Rule that fires: keyword → Tier 3.** (Path rules alone would say Tier 2 — test-only,
  no `standards/` bytes — the keywords buy the deep lane, which this change wants anyway:
  it is concurrency-shaped transport lifecycle code.)

## 7. Measurable proof and the pre-committed acceptance rule

**The proof set (all cells assert observed state; no wall-clock difference appears in any
assert — greppable as a ship condition):**

- **R-cells (SDK, `test_serial_reconfigure.py`), both fixture flavors where meaningful:**
  - R1 apply: reconfigure returns the applied settings; a NEW link serves the next
    transfer (old `reader_alive()` False; new True); the counting opener saw
    `{**boot, baud: N}`; ring empty.
  - R2 mid-receive refusal: a parked `take()` in a worker thread → typed
    `standalone_serial_reconfigure_busy` refusal; the parked receive still completes
    correctly afterwards.
  - R3 guard rail: out-of-set baud refused with the prefix naming the allowed set; the
    no-`x-`-key case refuses (allowed = {boot}).
  - R4 strict field set: `{"baud", "parity"}` refused; empty refused.
  - R5 bounded: expired/cancelled context refuses before any I/O (opener count 0).
  - R6 failure posture: a raising opener → `ConnectionError`, no link afterwards
    (`close_transport` still safe), failed event published, and a SECOND reconfigure is
    still possible (the adapter's explicit fallback move) — but the host never retried
    on its own.
  - R7 events: applied/refused/failed rows on the bus with the closed data shape.
  - R8 state: `host_info["link"]` reflects before/after; `device_get` overlay;
    `link: null` on the mock transport.
- **Mutants (RED-first, the suite's own doctrine):** M5 reconfigure-keeps-the-old-link
  (rebinding removed) → R1 red; M6 allowed-set check removed → R3 red; M7 busy check
  removed → R2 red (the mid-receive receive is corrupted or the close deadlocks);
  M8 event publication removed → R7 red.
- **Real lane (gateway, `test_negotiation_real_backend.py`):**
  - N1 green (v2): `negotiate_stream` reaches slim at 3 Mbps with
    `emu.garbled_bytes == 0` and `link_state == "ok"`; two link events observed
    (the switch; none other).
  - N2 RED control (the control fluff cannot pass): the reconfigure neutralized to the
    old in-process shape (no opener call) → the post-switch exchange MUST garble
    (`garbled_bytes > 0`) and the negotiation MUST fall back — N1's assertions fail.
    Red-then-green pasted in the PR body. This control is what makes the opener-coupled
    lane evidence rather than theater: if the neutralized mechanism still passes, the
    lane is insensitive and the KILL branch fires.
  - N3 revert-on-silence (`silent_revert`, shrunk `t_revert_s`): fallback path with the
    REAL boot-baud reopen; `link_state` per the M8/M10 fold classes; revert event rows.
  - N4 reopen-latency window: planted 0.3 s opener sleep vs `t_revert_s = 0.05` →
    `emu.reverts` non-empty, negotiation falls back; and the bounded arm — a context
    deadline inside the planted sleep → typed `TimeoutError`, opener called at most once.
  - N5 v1 device: SET_BAUD NAKs, no reconfigure is ever attempted (opener count 0),
    legacy path — the capability must be invisible to a v1 conversation.

**PRE-COMMITTED ACCEPTANCE RULE (written before any cell runs):**

- **SHIP iff all of:** (a) R1–R8 + N1–N5 green locally (macOS) and in both repos' CI;
  (b) the N2 RED control demonstrated red-then-green in the PR-1/PR-2 bodies; (c) M5–M8
  each redden their named cell (RED-first pasted); (d) `tests/server/test_serial_conformance.py`
  is BYTE-STABLE in PR-1 (`git diff --stat` names no such file) and the full #119 suite
  passes unmodified on both fixtures — compatibility by construction, not by re-baselining;
  (e) no new cell asserts on a measured time difference (grep over the new test files for
  monotonic-difference asserts returns only fixture plumbing).
- **KILL the increment if:** any existing C-cell or mutant needs modification to stay
  green (the landed #119 semantics moved — redesign, do not re-baseline); or the N2
  control cannot be made to fail (the pty lane is provably insensitive to the reopen —
  the "real lane" claim is unmeasurable on a pty and the capability's proof defers to
  hardware commissioning; file the honest negative on the issue); or the fresh-link swap
  cannot be made without touching `take()`'s wait discipline (then the design's premise
  is wrong and the increment needs a link-internal transport-swap design instead).
- **UNDERPOWERED (not conclusive) if:** any timing-flavored arm (N3/N4) flakes — the
  planted separations (0.05 vs 0.3 s; 0.25 s vs milliseconds) sit far above scheduler
  noise, so a flake means the pump thread starved or the join stalled, not a marginal
  window. Exactly one retry with doubled separations is allowed; a second flake records
  `runner-starved` on the issue and the arm moves to the underpowered ledger — never a
  lowered bar.
- **Sample size:** N=1 per cell per run — the arms are deterministic by construction
  (windows are planted, not sampled); the A3 soak is #393's instrument and is NOT rerun
  here.

## 8. Top risks, each with its falsifier

1. **The opener-coupled far end is theater** (the lane passes even when the reopen is
   skipped). Falsified by N2 at build time — that is N2's only job. If N2 cannot be made
   red, KILL (above).
2. **The receive-depth guard races a just-started `take()`** (thread-startup gap between
   the adapter's transfer and the worker's increment). Honest callers never race
   (negotiate awaits each exchange before reopening), so this is defense-in-depth with a
   disclosed residual: a `take()` entering after the check parks on a closing/closed link
   and gets the typed `ConnectionError`. The record states the residual; R2 pins the
   covered case. Falsifier: an adversary lane exhibiting a corruption that passes R2.
3. **The 5 s join bound stalls a reconfigure past its deadline on a stuck port.** Bounded
   by design: deadline checked after the close; expiry raises `TimeoutError` with the
   link already closed (the honest ambiguous posture). Falsifier: a port class whose
   `read()` blocks past `close()` — none known on pyserial (the timeout=0.05 read
   returns); the warning log already covers the pathological shape.
4. **Catalogue result motion breaks pinned parity or page cells.** Same-PR additive
   updates (declared property, `null` on mock); the drift is compile-time-visible in the
   SDK's own suite. Falsifier: any parity/page cell that cannot express `link: null`
   additively — none expected; if found, fork F3 collapses to host_info-only.
5. **REG-4 row fights the pinned-submodule timing** (the gateway test reading a submodule
   that does not yet have the Protocol). Structurally impossible with the sequential
   carrier: PR-2 advances the pointer and adds the row in the same diff; PR-1 alone never
   touches the gateway.

## 9. Owner forks, with recommendations

- **F1 — is `reconfigure_link` a contract surface or a duck-typed member?**
  Recommendation: **the Protocol (`LinkControlServices`) + the REG-4 gap row.** The
  member is the adapter-facing capability of record; an unpinned member is exactly the
   silent-drift class the three-way pin exists to catch. Cost: ~10 lines gateway-side.
  The alternative (duck-typing only, docs as the contract) saves the row and loses the
  pin — wrong trade at this price.
- **F2 — where does `x-negotiated-bauds` validate?** Recommendation: **runtime, in
  `serial.py`, at session build and at each reconfigure** (one shared derivation).
  The `x-` space is host-extension-by-design (#386's ruling); the gateway's descriptor
  admission must not become the validator of another host's extensions, and the SDK's
  own `validate_descriptor` checking a `standalone`-namespace key would leak
  server-specific semantics into the shared checker. The loud-prefixed,
  fail-closed-at-use posture matches the USB-hint precedent exactly.
- **F3 — `device_get` overlay vs host_info-only.** Recommendation: **both, additively**
  (the issue names both; the device panel is where an operator looks). If review finds
  the overlay muddies "established identity", collapsing to host_info-only is a
  one-line schema revert with no mechanism loss.
- **F4 — event kind shape.** Recommendation: one new kind `"link"` with a closed
  `event` vocabulary inside `data` (reconfigured/refused/failed), rather than reusing
  `"refused"` (that family is seam-exit refusals of catalogue operations — a link refusal
  is not one) or minting three top-level kinds (taxonomy sprawl).

## 10. CI cost

SDK suite: +~18–22 tests (8 R-cells, 4 mutants, 3–4 state/parity, fixtures), all
sub-second except the pty-free R-cells (threaded but fast). Gateway: +~6 real-lane cells
(N1–N5 plus the v1 arm), each < 1.5 s wall (the planted windows dominate), +1 agreement
row (no runtime). No new CI jobs, no new dependencies, no matrix changes. The pty cells
skip cleanly where `os.openpty` is absent (the #119 fixture's own skip posture).
