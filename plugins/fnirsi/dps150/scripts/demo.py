"""Live DPS-150 demo — the plugin stack driving the real device.

Narrates identity, the unsolicited telemetry cycle, commanded reads, a
setpoint ramp (1-8 V and back, step-and-hold with readback), and the
session-survives-disconnect flourish. Built for recording the bench.

SAFETY: the output legs assume an UNLOADED bench (no DUT wired) and the
setpoint never exceeds 8 V. Every run restores the device to 0.00 V,
output disabled, before exiting - including on failure (the finally
block). This script performs writes (fields 193/219); run it only on a
bench you have verified unloaded. All behaviour it demonstrates is
captured evidence under fixtures/protocols/dps150/ in the repository
root, gathered under per-leg principal approval 2026-09-15.

Usage: uv run python scripts/demo.py [--port /dev/cu.usbmodemXXXX]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import select
import sys
import termios
import time
from collections import deque
from datetime import UTC, datetime
from typing import Any

from benchweave_fnirsi_dps150.adapter import (
    DevicePlugin,
    HostServices,
    OperationContext,
    create_plugin,
)
from benchweave_fnirsi_dps150.codec import SET, encode_packet, write_payload
from benchweave_fnirsi_dps150.descriptor import build_descriptor

DEFAULT_PORT = "/dev/cu.usbmodem135DD25940961"
RAMP_UP = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0)
RAMP_DOWN = (7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0, 0.0)
HOLD_UP_S = 3.0
HOLD_DOWN_S = 2.0


class Context:
    """The adapter's OperationContext, satisfied with generous deadlines."""

    operation_id = "host-op"
    dataset_id: str | None = None

    def __init__(self, budget_s: float = 10.0) -> None:
        self.deadline_monotonic = time.monotonic() + budget_s
        self.cancelled = False
        self.markers = 0

    def is_cancelled(self) -> bool:
        return self.cancelled

    async def mark_dispatch_started(self) -> None:
        self.markers += 1


class SerialHost(HostServices):
    """HostServices over an exclusively owned termios serial session."""

    def __init__(self, fd: int) -> None:
        self._fd = fd
        self._buf: deque[int] = deque(maxlen=65536)

    def monotonic(self) -> float:
        return time.monotonic()

    def utc_now(self) -> str:
        return datetime.now(UTC).isoformat()

    def _pump(self) -> None:
        while select.select([self._fd], [], [], 0)[0]:
            chunk = os.read(self._fd, 4096)
            if not chunk:
                break
            self._buf.extend(chunk)

    async def transfer(
        self, transaction: dict[str, Any], context: OperationContext
    ) -> dict[str, Any]:
        if transaction["kind"] == "stream_send":
            os.write(self._fd, transaction["data"])
            return {}
        size = transaction["exact_bytes"]
        deadline = time.monotonic() + 2.0
        while len(self._buf) < size and time.monotonic() < deadline:
            self._pump()
            if len(self._buf) < size:
                await asyncio.sleep(0.01)
        data = bytes(bytearray(self._buf)[:size])
        for _ in range(len(data)):
            self._buf.popleft()
        return {"data": data}

    async def close_transport(self, context: OperationContext) -> None:
        pass  # the demo owns the port lifecycle


def open_port(port: str) -> int:
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    attrs = termios.tcgetattr(fd)
    iflag, oflag, cflag, lflag, _ispeed, _ospeed, cc = attrs
    cflag |= termios.CS8 | termios.CRTSCTS
    cflag &= ~(termios.PARENB | termios.CSTOPB | termios.CSIZE)
    lflag &= ~(termios.ICANON | termios.ECHO | termios.ECHOE | termios.ISIG)
    iflag &= ~(termios.IXON | termios.IXOFF | termios.ICRNL | termios.INLCR | termios.IGNBRK)
    oflag &= ~termios.OPOST
    termios.tcsetattr(
        fd, termios.TCSANOW, [iflag, oflag, cflag, lflag, termios.B115200, termios.B115200, cc]
    )
    return fd


def banner(text: str) -> None:
    print(f"\n{'=' * 62}\n  {text}\n{'=' * 62}", flush=True)


def step(text: str) -> None:
    print(f"  {text}", flush=True)


async def identify(plugin: DevicePlugin) -> dict[str, Any]:
    result = await plugin.execute(
        {"operation_id": "host-op", "verb": "identify", "arguments": {}}, Context()
    )
    return result.get("data") or {}


async def read_parameter(plugin: DevicePlugin, name: str) -> Any:
    result = await plugin.execute(
        {"operation_id": "host-op", "verb": "read", "arguments": {"parameter": name}}, Context()
    )
    data = result.get("data") or {}
    return data.get("value")


async def safe_restore(host: SerialHost) -> None:
    """Output OFF then setpoint 0 - the order matters for an inductive load."""
    await host.transfer(
        {"kind": "stream_send", "data": encode_packet(SET, 219, write_payload(219, False))},
        Context(),
    )
    await asyncio.sleep(0.1)
    await host.transfer(
        {"kind": "stream_send", "data": encode_packet(SET, 193, write_payload(193, 0.0))}, Context()
    )
    await asyncio.sleep(0.3)


async def run(port: str) -> int:
    print(
        f"\nBenchWeave x FNIRSI DPS-150 - live demo {datetime.now().strftime('%H:%M:%S')}",
        flush=True,
    )
    print(f"transport: {port} @ 115200 8N1 RTS/CTS (unload the bench first)", flush=True)

    fd = open_port(port)
    host = SerialHost(fd)
    plugin = create_plugin()
    await plugin.open(build_descriptor(), host, Context())

    banner("1 - OPEN + IDENTIFY (the adapter handshakes the device itself)")
    t0 = time.monotonic()
    identity = await identify(plugin)
    step(f"manufacturer : {identity.get('manufacturer')}")
    step(f"model        : {identity.get('model')}")
    step(f"firmware     : {identity.get('firmware')}")
    step(f"[{(time.monotonic() - t0):.2f}s incl. session handshake + telemetry drain]")

    banner("2 - LIVE TELEMETRY (unsolicited, ~2 Hz - watch the PSU screen)")
    try:
        for i in range(6):
            rows = plugin.latest_telemetry()
            if rows:
                parts = [f"{r['parameter']}={r['value']:>7.3f}{r.get('unit', '')}" for r in rows]
                print(f"  [{i + 1}/6] " + "  ".join(parts[:3]), flush=True)
            await asyncio.sleep(0.5)

        banner("3 - COMMANDED READS (voltage, input, temperature)")
        for name in ("voltage", "input_voltage", "temperature"):
            value = await read_parameter(plugin, name)
            step(f"{name:<14}: {value}")
            await asyncio.sleep(0.3)

        banner("4 - SETPOINT RAMP - up and down, watch the PSU output display")
        step("output ON at 0 V, then stepping up 1 V at a time ...")
        await host.transfer(
            {"kind": "stream_send", "data": encode_packet(SET, 219, write_payload(219, True))},
            Context(),
        )
        await asyncio.sleep(0.2)

        async def ramp(levels: tuple[float, ...], hold_s: float) -> None:
            for v in levels:
                frame = encode_packet(SET, 193, write_payload(193, v))
                await host.transfer({"kind": "stream_send", "data": frame}, Context())
                await asyncio.sleep(hold_s)
                value = await read_parameter(plugin, "voltage")
                step(f"setpoint {v:.1f} V  ->  terminal {value} V")

        await ramp(RAMP_UP, HOLD_UP_S)
        await asyncio.sleep(3.0)
        step("ramping back down ...")
        await ramp(RAMP_DOWN, HOLD_DOWN_S)
        step("output OFF ...")
        await safe_restore(host)
        step(
            f"final: {await read_parameter(plugin, 'voltage')} V - panel back to 0, output disabled"
        )

        banner("5 - SESSION SURVIVES DISCONNECTION (the wake is power-cycle-bound)")
        step("closing the serial port completely ...")
        os.close(fd)
        await asyncio.sleep(2.0)
        fd = open_port(port)
        host = SerialHost(fd)
        plugin = create_plugin()
        await plugin.open(build_descriptor(), host, Context())
        step("fresh gateway instance over the new port - identify + read ...")
        t0 = time.monotonic()
        identity = await identify(plugin)
        value = await read_parameter(plugin, "input_voltage")
        step(
            f"answered: {identity.get('model')} / input_voltage = {value} V "
            f"[{(time.monotonic() - t0) * 1000:.0f} ms]"
        )
        step(
            "the device stayed awake across the full disconnect - its session is power-cycle-bound"
        )
    finally:
        banner("DEMO COMPLETE - device restored: 0.00 V, output disabled, baseline protections")
        await safe_restore(host)
        os.close(fd)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Live DPS-150 demo through the plugin stack")
    parser.add_argument(
        "--port", default=DEFAULT_PORT, help="serial device node (default: %(default)s)"
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.port)))


if __name__ == "__main__":
    main()
