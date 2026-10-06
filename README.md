# benchweave-adc

Plugin project for a custom **6-channel, 12-bit ADC board** (WCH CH32V006E8R,
2 Mbps binary serial protocol). Forked from
[BenchWeave](https://github.com/madeinoz67/benchweave) and focused on one job:
the OTDP adapter for streaming samples off the board, served by the standalone
BenchWeave host.

What's in the box:

- **Plugin** `src/adc_6ch_12bit/`: the binary protocol codec, SDK adapter
  (`descriptor.json` + `adapter.py`), board discovery, channel-conversion
  config, and a minimal presentation for the host's live-readings page.
- **Standalone host** (optional extra `host`, i.e. `benchweave-sdk[server]`):
  serves the plugin's UI, REST and MCP surfaces from one process — loopback by
  default — with the serial transport this adapter's stream grammar needs.
- **Firmware** `firmware/ch32v006e8r_adc/`: the board's CH32V006 firmware
  (MounRiver toolchain Makefile).

The fork's earlier hand-rolled web stack (FastAPI + SSE UI, Analyse tab,
capture library, stdio MCP server) was removed in v0.2.0 when the standalone
host took over: serve the project with `benchweave-sdk-server serve` instead.
MCP-over-HTTP is available while the host serves; a persistent stdio MCP
server is a disclosed gap with a planned follow-up (see TODO.md).

## Quickstart

Python 3.13 and [uv](https://docs.astral.sh/uv/) are required.

```sh
uv sync --locked --dev --extra host
uv run benchweave-sdk-server serve . --transport serial --device <port>
```

Without a board, the mock transport serves the same surfaces for development:

```sh
uv run benchweave-sdk-server serve .
```

Plug the board in over USB (CH343 bridge); the host's scan probes candidate
ports with an IDENTIFY exchange.

## Reflashing the firmware (kickstart)

The board's CH32V006 has **no external BOOT0 pin**, so the serial ISP path
(`wchisp`) **cannot** reflash a chip that is already running firmware — it
answers the ISP handshake with its own UART traffic instead of entering the
bootloader. The obvious `wchisp` command below will fail with `invalid serial
header`:

```sh
wchisp flash firmware/ch32v006e8r_adc/build/ch32v006e8r_adc.hex
```

Reflash over the debug interface instead (WCH-Link, 1-wire SDI).

Do this, then do that:

1. **Identify the devices.** The ADC UART (CH343G bridge) and the WCH-Link
   programmer enumerate as separate `/dev/ttyACM*` ports — trust the USB PID,
   not physical labels:
   ```sh
   uv run python -c "import serial.tools.list_ports as lp; [print(p.device, f'{p.vid:04x}:{p.pid:04x}' if p.vid else 'unknown', p.serial_number) for p in lp.comports()]"
   ```
   `55d3` = the ADC board; `8010` = the WCH-Link.

2. **Locate the hex.** `firmware/ch32v006e8r_adc/build/ch32v006e8r_adc.hex` is
   the current build (`make` in that directory rebuilds it). Ignore the stale
   `obj/CH32V006E8R-ADC-PCB.hex`.

3. **Flash via OpenOCD + WCH-Link.** The `-s <dir>` flag is required (OpenOCD
   does not search its own binary directory for `wch-riscv.cfg`), and `unlock`
   clears read-out protection:
   ```sh
   OPENOCD=/usr/share/MRS2/MRS-linux-x64/resources/app/resources/linux/components/WCH/OpenOCD/OpenOCD/bin
   HEX=firmware/ch32v006e8r_adc/build/ch32v006e8r_adc.hex
   "$OPENOCD/openocd" -s "$OPENOCD" -f wch-riscv.cfg \
     -c "chip_id CH32V002/4/5/6/7" -c "page_erase" -c "init" -c "reset halt" \
     -c "flash write_image erase unlock $HEX" -c "verify_image $HEX" \
     -c "reset run" -c "exit"
   ```

4. **Verify.** Discovery should report fw `0.2`, 6 ch, 12-bit:
   ```sh
   uv run python -c "from adc_6ch_12bit.discovery import discover_adc_boards; print(discover_adc_boards())"
   ```
   Then a `sample_once` action returning real 12-bit values confirms end-to-end.

## Security posture

The standalone host binds loopback by default and carries its own guard
policy; see the `benchweave-sdk` server documentation. Exposing it more widely
is at your own risk.

## Documentation

| Topic | Where |
|---|---|
| SDK adapter | [docs/adapter.md](docs/adapter.md) |
| Hardware + wire protocol | [src/adc_6ch_12bit/README.md](src/adc_6ch_12bit/README.md) |
| Hardware compatibility | [docs/hardware.md](docs/hardware.md) |
| nanoDLA logic analyser MCP server | [docs/nanodla-mcp-server.md](docs/nanodla-mcp-server.md) |
| Firmware | [firmware/ch32v006e8r_adc/](firmware/ch32v006e8r_adc/) |
| Development & CI | [docs/development.md](docs/development.md) |
| Measurement-profiles upstream note | [docs/feature-request-measurement-profiles.md](docs/feature-request-measurement-profiles.md) |

## Relationship to BenchWeave

This project began as a fork of BenchWeave's early scaffold and inherited its
architecture-contract corpus; that machinery now lives (much evolved) in the
upstream project and has been removed here. The ADC plugin tracks BenchWeave's
plugin SDK ([benchweave-sdk](https://pypi.org/project/benchweave-sdk/)); since
v0.2.0 the standalone host from that SDK is this project's serving surface.

## License

[MIT](LICENSE).
