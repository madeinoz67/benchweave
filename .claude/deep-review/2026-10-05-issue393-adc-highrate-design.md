# Design record — issue #393: ADC single-channel high-rate sampling (protocol v2 + SW-60/61 serial backend)

**Date:** 2026-10-05 · **Issue:** [madeinoz67/benchweave#393](https://github.com/madeinoz67/benchweave/issues/393) · **Status:** design, pre-implementation
**Scope:** the PRD-12 I3 serial-provider leg (SW-60, SW-61) plus the #393 protocol-v2 work (slim frame, baud negotiation), as one change set across the SDK submodule and the main repository.
**Hardware available:** none. Every rate figure below is labelled **modelled** (derived from wire arithmetic) or **estimate** (static cycle budget). Silicon behaviour is a human-gated bench checklist (§11).

---

## 1. Premise verification (why this increment exists)

Issue #393's core claim checks out arithmetically, and one number in it is now known wrong:

- The legacy SAMPLE frame is a fixed **23 B** (5 header + 16 payload + 2 CRC — `plugins/adc_6ch_12bit/protocol.py:12-16` in the contributor fork, mirrored by the wire spec §4.1/4.3 of `docs/superpowers/specs/2026-09-11-adc-board-uart-driver-design.md`). At 2 Mbps 8N1 that is 230 bit-times = **115.0 µs** on the wire, i.e. a hard ceiling of **8,696 frames/s**. 19,000 SPS at 23 B/frame would need 437 kB/s on a 200 kB/s link — impossible by configuration alone. **Premise holds.**
- The fork's measured firmware model `SPS = 1e6/(n_ch × max(avg,1) × 31.6 µs + 115 µs)` is internally consistent: the mysterious 115 µs constant **is** the 23 B wire time at 2 Mbps. The model therefore generalises exactly as:

  ```
  SPS(n_active, avg, baud, fmt) = 1e6 / (n_active × max(avg,1) × t_conv + frame_bytes(n_active, fmt) × 10 / baud)
  frame_bytes(n, slim) = 11 + 2n     # header 5 + counter 4 + n×u16 + CRC 2;  n=6 → 23 B (byte-identical to legacy)
  ```

- **The issue's assumed 6 Mbps target baud is not achievable** — the MCU's USART ceiling is 3 Mbps (§3). The 19k SPS target survives, but only on the DMA/scan firmware path (§6, §7).

## 2. Decision inputs already ruled by the owner (designed within, not reopened)

1. Slim SAMPLE frame is **channel-mask-sized**, not a 1-channel special case; mask = all six ⇒ byte-identical to the legacy 23 B frame.
2. The **u32 sample counter** remains the drop-detection basis; the spec defines the **nominal timing basis** (§4.4).
3. Negotiation order and revert semantics exactly as ruled: IDENTIFY → capability check → ACKed SET_BAUD → ACKed SET_FRAME_FORMAT; device reverts to 2 Mbps + legacy on post-switch silence; both cross-version combinations keep working on the legacy path.
4. Protocol version bumps to **2**; IDENTIFY advertises the new capabilities.

## 3. The hard gate: CH32V006 USART maximum baud — RESOLVED, 3 Mbps

**Ruling: 6 Mbps is not achievable. The gated baud is 3,000,000 (3 Mbps), exact at BRR = 0x0010 (USARTDIV = 1.0). Confidence: high — three independent, concordant sources.**

Evidence chain (all verifiable):

1. **Active clock config** — fork `firmware/ch32v006e8r_adc/User/system_ch32v00X.c:22` `#define SYSCLK_FREQ_48MHZ_HSI 48000000`; `SetSysClockTo_48MHZ_HSI()` (line 225) sets `RCC_HPRE_DIV1` (HCLK = SYSCLK) and PLL = HSI×2 = 48 MHz.
2. **No APB2 prescaler on this family** — `Peripheral/src/ch32v00X_rcc.c:441`: `RCC_Clocks->PCLK2_Frequency = RCC_Clocks->HCLK_Frequency;` unconditionally. So **PCLK2 = 48 MHz**.
3. **Vendor library is 16×-oversampling only** — `Peripheral/src/ch32v00X_usart.c:122-130`: `USART_Init` computes `integerdivider = ((25 * apbclock) / (4 * USART_BaudRate))`, mantissa = ÷100 into BRR[15:4], fraction in 16ths into BRR[3:0]. There is **no OVER8 path anywhere** in the EVT tree (grep clean; `ch32v00X_usart.h` defines no OVER8 symbol).
4. **Vendor reference manual** — *CH32V00X Reference Manual V1.5 (EN)*, WCH file id 399 (EN) / 472 (ZH), scope CH32V002/004/005/006/007/M007, fetched 2026-10-05 from the public WCH document mirror (`wch-ic.com` file endpoint, recorded by `documents.json` in the mirror repo):
   - **§14.1 Main Features** (p.185): *"Fractional baud rate generator, up to 3Mbps"*.
   - **§14.3 Baud Rate Generator** (p.186): *"The baud rate of the transceiver = HCLK/(16\*USARTDIV), and HCLK is the clock of HB. The value of USARTDIV is determined based on the fields DIV_M and DIV_F in USART_BRR. The formula for calculation is: USARTDIV = DIV_M + (DIV_F/16)"*.
   - **§14.2 block diagram** (p.186): *"CONVENTIONAL BAUD RATE GENERATOR"*, clock path `fHCLKx(x=1,2) → /16 → /USARTDIV` — 16× only, no OVER8 leg.
   - **§14.8.3 USART_BRR** (pp.191-192): `DIV_Mantissa[11:0]` at bits [15:4], `DIV_Fraction[3:0]` at [3:0].

Derivation: baud = PCLK2/(16 × USARTDIV) with USARTDIV = DIV_M + DIV_F/16 ≥ 1 (integer part at least 1 — the register encodes the integer portion in [15:4]) ⇒ baud_max = 48 MHz/16 = **3 Mbps**, at which USARTDIV = 1.0 exactly (DIV_M = 1, DIV_F = 0): **zero baud-rate error**. DIV_M = 0 (USARTDIV < 1) would produce > 3 Mbps, which the manual's own feature line bounds out of the specified operating range.

**Honest residual on mantissa-0:** the BRR register description (§14.8.3) carries **no explicit "DIV_M = 0 is refused" clause** — the ceiling rests on the "up to 3Mbps" feature line plus the formula's USARTDIV ≥ 1 domain, not on a named prohibition. I did not find, and did not invent, a workaround; operating a WCH USART above its documented ceiling is out of scope by A02 (qualified, not assumed) and by the repo's no-guessing rules.

**Unverified hardware facts stated as such** (bench checklist owns them, §11): the CH343G USB-UART bridge's behaviour at sustained 3 Mbps (the issue's "USB-UART supports 6 Mbps" claim was never evidenced; the bridge datasheet was not re-consulted in this design), signal integrity of the board's PCB traces at 3 Mbps, and USB-FS scheduling at 375 kB/s sustained.

## 4. Mechanism

### 4.1 Wire protocol v2 (the contract, lands first)

Supersedes-but-cites the 2026-09-11 v1 spec (public fork document, cited as provenance). Additive changes; v1 frames remain valid on the wire at all times until negotiated away:

| Item | v1 | v2 |
|---|---|---|
| SAMPLE payload | fixed 16 B (u32 counter + 6×u16) | `4 + 2×n_active` B — **LEN byte already encodes it**; decoder cross-checks LEN against the negotiated mask popcount, mismatch ⇒ resync + protocol error |
| Frame types | 0x01–0x09, 0x81/0x82/0x83/0x90 | adds `0x0A SET_BAUD` (H→D, u32 LE baud), `0x0B SET_FRAME_FORMAT` (H→D, u8: 0 = legacy fixed, 1 = mask-sized) |
| IDENTIFY_RSP payload | 5 B: proto, fw_major, fw_minor, n_ch, resolution | 7 B when proto_ver = 2: same five + `caps u16 LE` (bit0 SET_BAUD, bit1 slim frame; rest reserved-0). A v2 reader parses proto_ver first, then by declared length — a 5-byte payload reads as proto 1 |
| Baud | fixed 2 Mbps | negotiated; device-supported set = {2,000,000; 3,000,000} — anything else ⇒ NAK(bad parameter) |
| Boot state | — | unchanged: 2 Mbps + legacy frame. **A v1 host talking to a v2 device changes nothing** (it never sends 0x0A/0x0B) |

**Negotiation (host side, one attempt, no silent retry loops — A06):** connect at 2 Mbps → send IDENTIFY (the only frame permitted before its response; it is non-mutating) → if proto ≥ 2 and caps bits set: SET_BAUD(3M) at 2 M → **ACK arrives at 2 M in the pre-switch format** (the device applies a switch only after ACKing it) → host reopens the port at 3 M → SET_FRAME_FORMAT(slim) → ACK at 3 M in legacy format → stream. Failure at any step after IDENTIFY: fall back to the legacy path (2 Mbps, fixed frame), **surface the fallback as an event + evidence entry**, do not retry the switch. A v1 device answers SET_BAUD with NAK(bad command) — the fallback path is identical.

**Device revert:** after ACKing SET_BAUD and switching, if no CRC-valid frame arrives within `T_revert` (spec value 250 ms; commissioned per bench per A02 — the default is a hint), the device reverts to 2 Mbps + legacy format. Host mirror: if SET_FRAME_FORMAT is not ACKed within `T_switch` (500 ms default) after the host reopened at 3 M, the host reopens at 2 M, re-IDENTIFYs to confirm the legacy path, and reports.

**Sequence-gap surfacing:** on decode, `counter ≠ prev + 1` ⇒ emit a gap record (missed = Δ−1) into the stream's event/evidence channel; gaps are never silently skipped. Ring-overflow (drop-oldest, §4.2) therefore surfaces as gaps — visible, counted, bounded per capture.

### 4.2 Timing basis (ruled decision 2, defined here)

The device carries no clock. The spec defines: `t_sample(counter_i) = t_stream_start + counter_i × T_nominal`, where `T_nominal = 1 / SPS_model(current config)` from the §6 rate table. Every such timestamp is labelled **nominal** (model-derived, never device-measured). A gap keeps the nominal grid (the counter defines time; there is nothing better on the wire, and the spec says so instead of implying measured timing).

### 4.3 SDK serial provider backend (SW-60) — `packages/sdk`

New module `src/benchweave_sdk_server/serial.py`: a `HostServices` implementation generalised from the fork's proven `src/benchweave/web/host.py` (read-only reference; the fork's shapes are the precedent — dedicated reader thread into a bounded ring, `take(exact, terminator, max_bytes, timeout)` mapped onto OTDP §8.1 `stream_receive` semantics: `exact_bytes` takes precedence, terminator bounded by `max_bytes`, incomplete frames never returned as complete):

- **Reader thread** (daemon) drains the port into a bounded ring; overflow drops **oldest** bytes (parser resynchronises on the next SYNC downstream; gaps surface via the counter).
- **All constants are configuration** with defaults re-sized for the gated byte rate, arithmetic in comments:
  - `ring_bytes` default **512 KiB** — ≥ 1.3 s of buffering at the 3 Mbps byte rate (375 kB/s), ≥ 2.5 s at the legacy 200 kB/s. (Recon catch: the fork's 256 KiB ring comment claims "~4 s of full-rate SAMPLE traffic"; 262,144 B ÷ 200 kB/s ≈ **1.3 s** — the comment overstates ~3×. Copy the mechanism, not the comment.)
  - `transfer_ceiling` default **64 KiB** per `stream_receive` (unchanged — one transfer carries ~5,077 slim frames at 13 B; the capture path is *not* per-frame transactions).
  - `quiet_line_ms` default **100 ms** (fork-proven).
- **pyserial** (`>=3.5`, BSD-3, zero transitive deps) added to the **`[server]` extra** — already the ruled posture (PRD NFR-P1: "Web, MCP and serial dependencies live in the `benchweave-sdk[server]` optional extra"); PKG-1/PKG-2 hold because the default dependency set is unchanged. Import is **lazy inside the factory** with a typed graceful-degrade refusal when absent — the exact pattern of `benchweave_sdk_server/cli.py:57` `_require_server_extra` and its test `tests/server/test_cli.py:121`.
- Every transfer is bounded: deadline from `OperationContext`, byte ceiling, cooperative cancellation (SW-13). No auto-retry, no auto-reconnect (A06).

### 4.4 Wire-family v2 reference implementation — main repo device project

Landing zone (precedent in §5): a first-party device project `plugins/benchweave/adc_6ch_12bit/` containing **only** what the fork boundary leaves us: the contract, the firmware, the reference host-side wire code, the emulator, the tests. **No descriptor, no adapter** — those live in the contributor's repository, untouched.

- `docs/wire-protocol.md` — the v2 wire spec (§4.1/4.2 above, normative) with v1 recorded as superseded-but-cited history.
- `docs/rate-model.md` — the §6 table, every row labelled modelled/estimate; recomputed by `tests/test_rate_model.py` from the frame-format constants (no hand-typed numbers — a model-honesty mechanism).
- `src/adc_wire/` (tiny package, MIT, `# author: Stephen Eaton` headers):
  - `codec.py` — dual-format encode/decode selected by negotiated state; the same `FrameParser` resync discipline as the fork's (proven).
  - `negotiate.py` — the host-side state machine of §4.1, written **against `HostServices` transactions** (not against the serial backend directly), so the contributor's adapter can adopt it verbatim over any conformant host — and so the emulator tests can drive it over `MockHost` with no port at all.
  - `gaps.py` — counter-gap detection and surfacing (§4.1).
- `tests/emulator.py` — the scripted device emulator, generalising the fork's `tests/adc/fakeboard.py` (proven shape: `Transport` protocol implementation that parses real frames and answers like firmware). Scriptable variants: v2 device, v1 device, silent-after-SET_BAUD (revert), deliberate counter drops, sustained-rate source. Uses the table-driven CRC both for fidelity to the firmware plan and so the emulator itself can source ≥ 23k frames/s in Python.
- `firmware/ch32v006e8r_adc/` — the v2 firmware, re-homed from the contributor's tree (that `main.c` is authored by Stephen Eaton and carries the header line; the fork is MIT with a madeinoz67 copyright line — re-homing is provenance-clean, the fork's copy stays as the v1 snapshot). Changes: ADC rule-group **scan + DMA** replacing polled conversion; **USART TX via DMA** double-buffered (the current `uart_tx_byte` busy-wait at §main.c:123 serialises the wire into the CPU path and alone caps the device below 9k SPS); **nibble-table CRC-16** (16×u16) replacing the bitwise loop (§7 budget); mask-sized frame build; SET_BAUD/SET_FRAME_FORMAT handlers + revert-on-silence timer; IDENTIFY v2 payload.

### 4.5 SW-61 conformance (the proof shape, no hardware)

Two fixtures, one cell set:

1. **In-process loopback** (deterministic, every platform incl. Windows): the emulator injected as the backend's `Transport` port. This is the fork's own proven test shape (`FakeBoardTransport`).
2. **pty-pair lane** (posix; `os.openpty()` + pyserial on the slave, emulator serving the master): exercises the real pyserial/termios read path. No in-repo pty fixture exists today (searched — zero `openpty` hits); this is new but minimal, and skips cleanly on Windows.

The cells are the transport-level transaction-grammar behaviours the fork's 26-cell adapter suite pins (read-only reference, `tests/adc/test_adapter_conformance.py`): exact-byte contract break ⇒ transport error; a frame the line pauses inside is kept until complete; reply after a quiet read still completes; no reply by deadline ⇒ unknown timeout; expired/cancelled context never transmits; fetch budget truncates or refuses; interleaved samples inside a reply are buffered. Re-expressed host-side against the backend, they are the PRD's SW-61 "same conformance cells" — adapter-independent, so they run in our tree without the fork's adapter. **The fork's own 26/26 control (`scripts/adc_conformance_control.py`, CI-wired at `.github/workflows/package.yml:148`) stays green by construction**: `MockHost`/`testing.py` are untouched; the backend is new code beside them. Verified at PR time by the control's own CI run.

## 5. Precedent (every landing zone)

| Decision | Precedent |
|---|---|
| Plugin-family project root `plugins/<mfr>/<name>/` with `firmware/` inside | `docs/develop-your-device.md`: *"In this repository, use `plugins/<manufacturer>/<name>/` as the independent project root"*; *"For custom hardware, put firmware source, board configuration, toolchain locks, firmware tests and documentation for flashing and recovery in `firmware/` alongside the plugin"*; live examples `plugins/fnirsi/dps150/` (full layout) and `plugins/benchweave/{sim_*}` (first-party bucket) |
| Protocol doc pointer stub in `docs/` | `docs/dps150-protocol.md` — the canonical doc lives with the device project, `docs/` carries a pointer |
| Serial backend shapes (reader thread / ring / ceiling / quiet-line / exact-byte take) | fork `src/benchweave/web/host.py:80-199` (`SerialLink`), generalised per PRD §5 fold-in row 1 ("Take, generalise … Constants become config") |
| Lazy-import graceful degrade for the extra | `benchweave_sdk_server/cli.py:57` + `tests/server/test_cli.py:121` |
| Conformance cells against a scripted far end | fork `tests/adc/fakeboard.py` + `tests/adc/test_adapter_conformance.py`; SDK `MockHost` (`testing.py:86`) exact-transaction discipline |
| Negotiation module written against `HostServices` | OTDP §8.1 transaction table (`standards/otdp/0.2.2/otdp-specification.md:230-238`) — the adapter-side protocol ownership rule (`docs/develop-your-device.md`: "The library encodes device commands… the caller supplies transport") |
| Anti-gaming / planted-defect arms | `scripts/adc_conformance_control.py` (yank-pin arm); #245 mutation-discrimination arm |
| Two-repo landing order | AGENTS.md two-repo discipline (SDK PR first, then the main-repo pointer) |

**Deviation from the dispatch brief, argued:** the brief suggested the negotiated-baud/frame-format state machine land in the SDK. This design puts it in the main-repo device project (§4.4) because the SDK is the device-agnostic authoring surface (PKG-1/PKG-2 spirit; no device protocol lives in it today), the PRD — the stated authority for benchweave-side scope — scopes SW-60 as the *generic* backend, and OTDP assigns device-protocol ownership adapter-side. The module is still pure-Python-over-`HostServices`, so the standalone server, the contributor's adapter, and the emulator tests all consume the same code. **Flagged as owner fork F1** (§12).

## 6. Rate model, re-run at the gated baud (all rows MODELLED; t_conv terms: 31.6 µs = firmware-measured v1 polled path; 1.0 µs = ESTIMATE for the DMA-scan path, see §7)

Single channel (n_active = 1, avg = 0):

| # | Path | t_conv | frame | baud | wire µs | total µs | SPS (modelled) |
|---|---|---|---|---|---|---|---|
| 0 | v1 today (matches the ~6,800 in #393) | 31.6 µs (meas.) | 23 B | 2 M | 115.00 | 146.60 | **6,821** |
| 1 | v2 negotiated, no fw change | 31.6 µs | 23 B | 2 M | 115.00 | 146.60 | 6,821 |
| 2 | + ADC scan/DMA | ~1.0 µs (est.) | 23 B | 2 M | 115.00 | 116.00 | 8,621 |
| 3 | + 3 Mbps (gated; 6 M ruled out §3) | ~1.0 µs | 23 B | 3 M | 76.67 | 77.67 | 12,876 |
| 4 | + slim 13 B frame — **the target row** | ~1.0 µs | 13 B | 3 M | 43.33 | 44.33 | **22,556** |
| 5 | conservative: 3 M + slim, **no** DMA benefit | 31.6 µs | 13 B | 3 M | 43.33 | 74.93 | 13,345 |

Six channels (mask = all, byte-identical frame): v1 today 3,283 (matches the ~3,300 measured); v2 + DMA @ 3 M: **12,097 modelled** — the protocol work lifts the 6-channel case too.

Wire ceilings (frames/s): 2 M/23 B 8,696 · 2 M/13 B 15,385 · 3 M/23 B 13,043 · 3 M/13 B **23,077**.

**Target sensitivity, stated plainly:** 19,000 SPS needs 52.6 µs/sample; the wire takes 43.3 µs, leaving **9.3 µs** of serialised slack — or, pipelined (double-buffered DMA TX), CPU ≤ 52.6 µs against ~8-11 µs estimated (§7). The 19k claim is therefore *modelled-achievable only on the DMA path* (row 4); without the firmware DMA work the same protocol changes deliver row 5's 13.3k. The acceptance rule (§10) encodes both: the no-hardware proof covers wire+host; the firmware claim is an estimate behind a human bench gate.

## 7. Firmware cycle-budget static estimate (ESTIMATE; no silicon)

At 19,000 SPS the sample period is 52.63 µs = 2,526 cycles @ 48 MHz. Per-sample CPU on the v2 path (rv32ec, compressed ISA):

| Work | Estimate |
|---|---|
| ADC scan DMA EOC + buffer handoff | 100–200 cycles |
| counter++ + 13 B frame build into staging buffer | 50–100 cycles |
| CRC-16/CCITT-FALSE over 9 B — **bitwise (current fw)** | ~360–430 cycles — rejected: with the polled TX busy-wait this is part of why v1 caps where it does |
| CRC-16 over 9 B — **nibble table** (16×u16 = 32 B in flash) | ~150–200 cycles |
| DMA TX kick + bookkeeping | ~50 cycles |
| **Total (table CRC path)** | **~350–550 cycles ≈ 7–11 µs** |

Steady state is `max(wire, CPU)` under double buffering: max(43.3 µs, ~11 µs) = wire-bound at **23.1k SPS ceiling**; sustaining 19k uses 82% of the wire with ~4.8× CPU headroom. RAM: 2×32 B TX staging + ADC DMA buffers + existing RX ring ≪ 8 KB. The "firmware is no longer the bottleneck" claim is exactly this estimate plus the wire arithmetic — and nothing more until the bench measures it.

**Firmware build honesty.** The Makefile targets the **MRS-bundled `riscv-wch-elf-gcc`** toolchain (fork `firmware/ch32v006e8r_adc/Makefile:2-12`). "Builds cleanly" in this increment means: compiles and links with that documented toolchain locally, `size` output recorded against the RAM/flash budget, image hash recorded — **zero claim about silicon behaviour**. A CI firmware-build lane would need a pinned riscv toolchain with rv32ec multilib coverage (xpack `riscv-none-elf-gcc` plausibly has it; unverified) — **deferred, carrier named in §9**. The vendor EVT peripheral library ships under WCH's public EVT terms (cited as provenance, not claimed as evidence).

## 8. Minimal first increment

Two PRs, one gateway issue (#393), two-repo discipline:

1. **SDK PR** — `benchweave_sdk_server/serial.py` (SW-60 backend), pyserial in `[server]`, lazy-import degrade, the SW-61 transaction-grammar cell set over both fixtures, planted-defect discrimination arms. Touches no `MockHost`/`testing.py` bytes.
2. **Main PR** (after 1 lands; pointer bump) — the `plugins/benchweave/adc_6ch_12bit/` device project: wire spec v2 + rate model + test-pinned table, `adc_wire` reference package (codec / negotiate / gaps), emulator with the negotiation + sustained-stream cells, v2 firmware, `docs/adc-protocol.md` pointer stub.

**Explicit deferrals (each with its carrier):**

| # | Deferred | Carrier |
|---|---|---|
| D1 | SW-62 discovery (descriptor USB-hint port filtering + identify-confirm picker) | I3 discovery slice; PRD names #385/#386 dependencies |
| D2 | Capture writer/index/SSE/MCP capture tools, retention (the rest of I3) | I3 |
| D3 | Windows serial (fixture is posix-pty + in-process; CH343 Windows driver at 3 M untested) | PRD Q9 ruling |
| D4 | Firmware CI build lane (pinned riscv toolchain + rv32ec multilib verification) | new issue, filed at PR time |
| D5 | Contributor-fork migration to v2 (adapter adopting `adc_wire`; fork `host.py`/`mcp_server.py` deletion per the I3 exit gate) | the fork's own work; I3 migration PR |
| D6 | Averaging > 0 at high rate, external trigger, cycle/timer sample mode | wire-spec reserved fields (v1 already reserves; unchanged) |
| D7 | Intermediate bauds (e.g. 1 M for long cables) | wire-spec device-supported set stays {2 M, 3 M}; reopen with cable-loss evidence |
| D8 | Any UI/decimation work (Q12-ruled uPlot path) | I3 UI slice |

## 9. Invariant and cross-surface impacts

- **CTL/STO/CON/REG:** no rows change; no amendments. The change touches no `control/`, `state/`, `contracts/`, `registry/` code. Discipline-level application: A06 (one negotiation attempt, fallback surfaced, never a silent retry; ambiguous post-dispatch outcomes stay unknown — inherited from the cells), A08 (host/backend combination qualified by bench evidence, not assumed — the checklist), SW-13 (every transfer bounded).
- **`standards/`: untouched.** The wire spec is plugin-family, not corpus; OTDP §8.1 stream transactions are consumed, not modified. The standing push tripwire (`git diff origin/main...HEAD -- standards/`) reports empty; no standard-version strings move.
- **Standards-governor (#69): NOT dispatched** — no `standards/` bytes, no plugin contract locks, no SDK vendored tree (`benchweave_sdk/standards/`), no standard-version strings. Stated here because the SDK submodule moves; the governor trigger set was checked item by item.
- **MCP/REST/OpenAPI surfaces:** no motion (no new seam operations) — obligations 1/2 of `drift-and-obligations.md` vacuous.
- **Docs:** `docs/adc-protocol.md` pointer stub (obligation-3 shape); SDK README's server-extra note gains the serial dependency mention. `device-developer-guide.md` untouched — the layout used is the documented one.
- **CI cost:** +1 SDK pytest lane (cells, seconds); +1 main-repo job or extended job for the device project's tests (explicit wiring per the P3 rule — standalone plugins are not auto-discovered); `package.yml`'s ADC control unchanged and must stay 26/26. No perf thresholds in CI (standing one-off-benchmark rule) — the sustained-rate measurement runs once and is recorded on the issue.
- **On-disk formats/schemas: none.** (No state migrations, no persisted-format changes — this is why the change is Tier 3 by dependency/pointer/keyword, not by format.)

## 10. Measurable proof and the pre-committed acceptance rule

Written before any measurement ran. Metrics, sample sizes, and **both** kill directions follow.

**Part A — no-hardware proof (gates the PRs):**

- **A1 Conformance (SW-61).** The enumerated cell set (12 cells: the eight transport behaviours of §4.5 plus exact-byte echo, ring-overflow gap visibility, ceiling truncation, deadline-before-dispatch) passes on **both** fixtures (in-process; pty+pyserial posix). *RED control:* three planted mutants (ring drops newest-not-oldest; quiet-line wait removed; ceiling unchecked) — each must fail ≥ 1 cell; a mutant that passes everything falsifies the cell set, not the mutant.
- **A2 Negotiation vs emulator (6 cells).** v2-success (stream continues at slim 13 B, LEN matches mask); v1-device fallback (byte-identical legacy 23 B stream, fallback event emitted); v1 NAK on SET_BAUD; device silent-after-switch ⇒ both ends back at 2 M legacy and the link still streams; host switch-timeout ⇒ one fallback, reported, no retry loop; LEN/mask mismatch ⇒ resync + protocol error. *RED control:* a stub that skips negotiation must fail the slim-frame and fallback cells.
- **A3 Sustained stream (one-off measurement, recorded on #393, not a CI gate).** Emulator sources 13 B frames as fast as the pty accepts for **10 s**, 3 runs; consumer decodes through the SDK backend via bounded `stream_receive` and the reference codec, with a planted drop list (5 gaps, known counts). **Ship iff all 3 runs satisfy:** decoded ≥ 190,000 frames/run (≥ 19,000 SPS model rate); gap reports exactly equal the planted list (0 unreported, 0 invented); `tracemalloc` peak delta < 1 MiB after warm-up; ring occupancy never exceeds config. **Kill:** any run below 19k fps, any gap mismatch, or monotonic memory growth — the host reader/decode design is wrong; kill and redesign (do not tune thresholds). **Underpowered (distinct from kill):** if a null-consumer sink run shows the *emulator+pty source itself* cannot sustain ≥ 23,077 fps on that host, the lane is runner-starved — record, move to a quieter host, re-run once; if still starved, the measurement is inconclusive: escalate to the owner rather than shipping on a lowered bar.
- **A4 Model honesty.** `tests/test_rate_model.py` recomputes the §6 table from the frame constants; the doc table cites the test. (Fluff cannot pass: the numbers are regenerate-or-fail.)

**Part B — human hardware gate (PR labelled `needs-hardware-validation`; owns the 19k *claim*, not the merge):** flash v2 firmware (image hash recorded); IDENTIFY shows proto 2 + caps; negotiate to 3 M + slim; **measure actual SPS over 60 s and record the number whatever it is**; verify counter-gap count under a deliberate host pause; verify revert after unplug/replug; verify mask=all frames byte-identical to v1 (regression); verify the CH343G bridge sustains 3 Mbps; record board revision, firmware hash, host OS. **Kill for the firmware claim:** measured < 19,000 SPS with wire utilisation < 80% ⇒ the §7 estimate was wrong — file the number, revise firmware (Part A is unaffected; the SDK/host side ships on Part A).

Sample-size justification: gap matching is deterministic (zero-noise; 3 runs detect flakiness only); the throughput clause is variance-poor on an idle host, so 3×10 s ≈ 570k frames suffices; nothing here relies on statistical significance.

## 11. Review tier and the Step-1 keyword scan (#254)

**Tier 3 (maximum across both slices).** Triggers, first-match: (a) *adds a dependency* — pyserial enters the SDK `[server]` extra (`pyproject.toml`, `uv.lock`); (b) *advances the `packages/sdk` submodule pointer*; (c) diff-text keyword `threading`. Tier-3 consequences: full cold suite, **two independent adversary lanes** (standing Tier-3 rule), governor not dispatched (§9 determination).

**Step-1 keyword scan over the expected diff text** (design-time scan of the planned file set — SDK serial module + cells, device project `src/`/`tests/`/firmware/docs; the landed diff is re-derived independently at review):

| Keyword | Expected count | Where |
|---|---|---|
| `threading` | **~14** | serial backend (import, thread spawn, docstrings ~7), emulator ~2, tests ~5 |
| `asyncio` | **~5** | async↔thread bridge ~2, tests ~3 |
| `subprocess` | 0 | no Python subprocess planned; firmware build is a documented make invocation |
| `sha256` / `hashlib` | 0 / 0 | no digests computed in code this increment |
| `migrate` | 0 | no state migrations |
| `recovery` | **~2** | firmware README "flashing and recovery" (mandated by the develop-your-device firmware layout) |
| `protection` | 0 | deliberate: the serial path makes no protective-behaviour claims |

## 12. Top risks, each with its falsifier

1. **The DMA/timing estimate is wrong on silicon** (the 19k row rides §7). Falsified only by the Part-B bench measurement; if wrong, the honest outcome is a filed measured number and revised firmware — the design's protocol/host half is unaffected.
2. **Layering of the negotiation module** (deviation F1). Falsified if the owner rules the SDK-server home; the module's `HostServices`-only surface makes the move mechanical either way.
3. **pty fixture masks real-serial behaviour** (latency spikes, short reads, driver quirks at 3 M). Mitigated by inheriting the fork's read semantics (proven on real hardware at 2 M) and by the checklist; residual stated.
4. **Python emulator/consumer can't source 19–23k fps in CI-grade environments.** A3's underpowered arm covers this explicitly; the table-driven CRC is chosen partly for emulator speed.
5. **The pinned fork's 26/26 control breaks.** It cannot via `MockHost` (untouched), but the SDK wheel contents change — verified by the control's own CI run at PR time; a red there blocks the merge (nothing merges while its own expected lanes are red).
6. **Baud-rate error at 3 Mbps on the CH343G link.** Zero error at the MCU (USARTDIV = 1.0 exact); the bridge side is an unverified hardware fact — checklist owns it; D7 keeps intermediate rates out until cable-loss evidence exists.

## 13. Open forks for the owner

- **F1 — home of the wire-family v2 host module**: recommended main-repo device project (§5 argument); the dispatch brief suggested SDK-server. Decide before the SDK PR cuts its scope boundary.
- **F2 — claim posture for 19k**: recommended "modelled + human bench gate owns the measured number" (no hardware exists to do better); alternative is holding the increment until hardware validates (blocks SW-60/61 on hardware that may be weeks away).
- **F3 — firmware CI build lane now vs deferred** (D4): recommended deferred.
- **F4 — device-supported baud set**: recommended fixed {2 M, 3 M} (silicon-evidenced); confirm no intermediate rate is wanted for long-cable benches.

## 14. Provenance, public-hygiene, triage note

The contributor's fork (`parkview/benchweave`) is cited as read-only provenance — it is already publicly cited in this repository (PRD §1.3, `scripts/adc_conformance_control.py:51`). The firmware's authorship line (`Author: Stephen Eaton`) is quoted from that public tree and is the required header for authored code in this increment. No bench names, client identifiers, serials, or commercial terms appear; the CH32V006/CH343G facts are public vendor documentation cited as provenance. Triage rule checked: this record's person-name content is limited to already-public provenance, so it lands in the public `.claude/deep-review/` per the dispatching brief; if the maintainer prefers strict-name hygiene, demote to `private/` before commit (promotion is a review, demotion a leak — decide at commit time, not after).

No Claude/Anthropic attribution anywhere in the increment.
