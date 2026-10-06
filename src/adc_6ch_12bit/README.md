# ADC 6-channel 12-bit board

BenchWeave plugin for the 6-channel, 12-bit ADC board: an OTDP descriptor and
async SDK adapter over a custom binary UART protocol.

## Hardware

| | |
|---|---|
| MCU | WCH CH32V006E8R (RISC-V, 48 MHz) |
| USB-UART | CH343G (up to 6 Mbps) |
| ADC | 6 channels, 12-bit (0–4095) |
| UART | USART1, TX=PD5 / RX=PD6, 2,000,000 baud, 8N1, no flow control |

Canonical channel order (fixed by the wire protocol):

| Index | Pin | ADC ch | Meaning |
|---|---|---|---|
| 0 | PA2 | A0 | EN / DC-DC regulator input |
| 1 | PA6 | A1 | DC-DC output |
| 2 | PC4 | A2 | (reserved) |
| 3 | PD2 | A3 | R271 cap-current sense L |
| 4 | PD3 | A4 | R272 cap-current sense R |
| 5 | PD4 | A7 | (reserved) |

## Wire protocol

Binary frames at 2 Mbps:

```
[0xAA 0x55][type][seq][len][payload...][crc16 LE]
```

- CRC-16/CCITT-FALSE (poly `0x1021`, init `0xFFFF`) over `type..payload`.
- Commands (host → board): `identify`, `set_averaging`, `set_channels`,
  `set_sample_mode`, `start_stream`, `stop_stream`, `sample_once`, `reset`.
- Responses (board → host): `ACK`, `NAK`, `IDENTIFY_RSP`.
- Data (board → host): `SAMPLE` = u32 counter + 6× u16 (12-bit, little-endian).
- Averaging choices: `{0, 4, 8, 16, 32, 64, 128, 256}`.

Full spec: `docs/superpowers/specs/2026-09-11-adc-board-uart-driver-design.md`.

## Sample rate

A `SAMPLE` frame is 23 bytes, so the UART at 2 Mbps (200,000 bytes/s) tops out
at ~8,700 frames/s. In practice the ADC conversion time is the limiter: the
board does ~3,300 samples/s at averaging 0. Expected sample rates (6 channels):

| Averaging | Est. SPS |
|---|---|
| 0 (raw) | ~3,300 |
| 4 | ~1,140 |
| 8 | ~610 |
| 16 | ~320 |
| 32 | ~160 |
| 64 | ~81 |
| 128 | ~41 |
| 256 | ~20 |

Averaging trades noise against speed; the limiter is the ADC conversion time,
not the link.

## Usage

The plugin is served by the standalone BenchWeave host
(`benchweave-sdk[server]`, the optional `host` extra):

```sh
uv sync --locked --dev --extra host
uv run benchweave-sdk-server serve . --transport serial --device /dev/tty.usbserial-XXX
```

That serves the UI, REST and MCP surfaces (loopback by default) over this
project's adapter. Captures publish under the host's capture root
(`--capture-root`, else `BENCHWEAVE_CAPTURE_DIR`, else `captures/` under the
working directory).

Direct adapter use (async, one session per connection) follows the
benchweave-sdk contract: `create_plugin()`, `open(descriptor, services, ctx)`,
`execute` with `identify`/`reset`/`invoke` (`otdp.daq.*` actions), and
`next_event` for streamed samples. The SDK server's serial transport provides
the matching host services over a serial port.

`discover_adc_boards()` enumerates WCH USB-UART ports and probes each with
`IDENTIFY`, accepting only ports that reply with the ADC signature — so the
`/dev/ttyACM*` node can move between reboots without breaking the code.

## Firmware

`firmware/ch32v006e8r_adc/` — the CH32V006 implementation of the same protocol.
Build from the CLI with `make` (uses the MRS-bundled `riscv-wch-elf-gcc` toolchain).

## Deferred

- **ADC scan mode + DMA** — replace the per-channel polled conversion with the
  ADC scan sequencer + DMA, raising the raw rate from ~3,300 toward the ~8,700
  frames/s UART ceiling.
- **Link "show" to sampling** — stop sampling hidden channels (drive firmware
  `SET_CHANNELS` from the config `show` flags), so unticking channels speeds up
  collection. The `SAMPLE` frame stays fixed at 6× u16, so the speedup is
  bounded by the fixed transfer time.
- Timer-triggered ("cycle") sampling and external trigger (exact, jitter-free
  rate).
- **Separate graph update rate (multi-mode graphing)** — the live graph currently
  follows `sample_rate_hz` (same as recording). Explore a dedicated graph-update-rate
  setting so the graph can run faster *or* slower than the recorded rate, and a
  "live vs recorded-rate" graphing mode toggle.

## For AI agents

Context for a fresh AI session continuing work on this module. Read this, then
the linked spec, before changing anything.

**What this is:** an OTDP adapter plugin for a 6-channel, 12-bit ADC board
(WCH CH32V006E8R + CH343G USB-UART) speaking a custom binary protocol over UART
at 2 Mbps. Host is the master: it sends commands, the board replies or streams.

**Layout:**
- `src/adc_6ch_12bit/` — this plugin (`protocol.py` codec — including the
  parsed `Sample` vocabulary — `adapter.py` + `descriptor.json` SDK adapter,
  `discovery.py`).
- `firmware/ch32v006e8r_adc/` — matching CH32V006 firmware (C; `make`).
- `tests/adc/` — tests (adapter conformance over the SDK's MockHost, plus
  protocol/config/discovery).
- `docs/superpowers/specs/2026-09-11-adc-board-uart-driver-design.md` — the
  wire-protocol spec (**source of truth**).

The host side (serial transport, transfer services speaking OTDP §8.1's
stream grammar, capture publishing, UI/REST/MCP surfaces) is the standalone
BenchWeave host in `benchweave-sdk[server]`, not this repository.

**Protocol (summary):** `[0xAA 0x55][type][seq][len][payload][CRC16 LE]`,
CRC-16/CCITT-FALSE over type..payload. Commands: `identify`, `set_averaging`,
`set_channels`, `set_sample_mode`, `start_stream`, `stop_stream`, `sample_once`,
`reset`; responses `ACK`/`NAK`/`IDENTIFY_RSP`; data `SAMPLE` = u32 counter +
6× u16. Averaging ∈ `{0,4,8,16,32,64,128,256}`. `protocol.py` and firmware
`main.c` must stay byte-compatible.

**Conventions:**
- Wire-protocol changes go in the spec first, then both ends together.
- Python: ruff (line-length 100) + mypy strict + pytest — run
  `uv run pytest`, `uv run ruff check .`, `uv run mypy`.
- Firmware: `make -C firmware/ch32v006e8r_adc`.
- Captured data goes to the serving host's capture root (gitignored).

**Deferred work (next):** ADC scan mode + DMA (raw rate → UART ceiling); link
the config `show` flag to firmware `SET_CHANNELS` so hidden channels are not
sampled (speedup bounded by the fixed 6× u16 frame); timer-triggered "cycle"
sampling and external trigger; a separate graph-update-rate setting (the live
graph currently follows `sample_rate_hz`; see the Deferred section above).
