# author: Stephen Eaton
"""A3: the sustained-stream measurement (issue #393 design §10 A3).

ONE-OFF measurement instrument — recorded on the tracker, never a CI
gate. 3 runs x 10 s: the emulator sources mask-sized 13 B frames as fast
as the pty accepts, the consumer decodes through the REAL SDK serial
backend (bounded stream_receive) and the reference codec, with a planted
5-gap drop list.

Ship iff every run: decoded >= 190,000 frames (>= 19,000 SPS model
rate), gap reports exactly equal the planted list (0 unreported, 0
invented), tracemalloc peak delta < 1 MiB after warm-up, ring bounded.
Kill on any shortfall; the underpowered arm (null-consumer sink below
23,077 fps on the source lane) records runner-starved, never a lowered
bar.

Invocation contract: run FROM the plugin project directory
(`plugins/benchweave/adc_6ch_12bit/`) with a Python environment that
carries benchweave_sdk_server with its [server] extra (pyserial) —
e.g. the SDK worktree venv:
  uv run --project <sdk-worktree> python tests/a3_sustained_stream.py
The harness bootstraps its own src/tests paths; everything else must
already be importable.
"""

from __future__ import annotations

import asyncio
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / "src"))

import serial  # pyserial, [server] extra
from adc_wire import codec
from adc_wire.gaps import GapDetector
from adc_wire.negotiate import negotiate_stream
from emulator import AdcEmulator

DROP_LIST = (100, 500, 1500, 9000, 20000)
RUN_S = 10.0
SLIM_FRAME = 13  # mask=1 negotiated slim frame
RUNS = 3


def _open_pty():
    master_fd, slave_fd = os.openpty()
    import tty

    tty.setraw(master_fd)
    host_port = serial.Serial(
        os.ttyname(slave_fd), baudrate=115200, timeout=0.02, write_timeout=1.0
    )
    return master_fd, slave_fd, host_port


class _Ctx:
    """Minimal negotiation context (deadline, cancel, dispatch)."""

    def __init__(self, timeout_s: float) -> None:
        self.deadline_monotonic = time.monotonic() + timeout_s
        self.dispatched = True

    def is_cancelled(self) -> bool:
        return False


async def _main(run_s: float) -> dict[str, object]:
    master_fd, slave_fd, host_port = _open_pty()
    emu = AdcEmulator(variant="v2", drop_list=DROP_LIST)
    far = _PtyFar(master_fd)
    from benchweave_sdk_server.serial import SerialCaptureServices, SerialLink

    link = SerialLink(host_port, quiet_s=0.05)
    # M13 (fold, disclosure): max_frame_bytes=65536 is this instrument's
    # DECLARED host configuration — the services clamp the per-receive
    # ceiling to min(transfer_ceiling, max_frame_bytes), so an honest
    # frame-scale descriptor (max_frame_bytes ~ 23) would cap receives at
    # frame size and this 40,950 B bulk transfer would refuse. The A3
    # measurement is a bulk-stream instrument, not a descriptor-driven
    # host; the conflation of the two clamps is a candidate follow-up
    # issue for the backend owner (filed by the run lead).
    services = SerialCaptureServices(link, max_frame_bytes=65536)
    try:
        ctx = _Ctx(5.0)

        async def _reopen(baud: int) -> None:
            # The in-process reopen: the HOST side moves to the new baud.
            # Since fold M7 the emulator tracks both ends — a no-op here
            # leaves host_baud at the boot rate and the post-reopen
            # SET_FRAME_FORMAT lands as wrong-baud garble (the regression
            # the A3 vet caught at the fold tip).
            emu.host_baud = baud

        far.attach(emu)
        result = await negotiate_stream(services, ctx, reopen=_reopen)
        assert result.slim, result.events
        # one active channel: the 13 B slim frame
        from adc_wire import codec as _codec

        def _frame(ftype: Any, payload: bytes) -> bytes:
            return _codec.encode_frame(_codec.Frame(type=int(ftype), seq=0, payload=payload))
        await services.transfer(
            {"kind": "stream_send", "data": _frame(_codec.FrameType.SET_CHANNELS, b"\x01")}, ctx
        )
        await services.transfer(
            {"kind": "stream_send", "data": _frame(_codec.FrameType.START_STREAM, b"")}, ctx
        )
        detector = GapDetector()
        decoded = 0
        ring_max = 0
        first_counter = None
        warm = 1.0
        started = time.monotonic()
        tracked = False
        sample_type = int(_codec.FrameType.SAMPLE)
        chunk = SLIM_FRAME * 3150  # 40,950 B: one 64 KiB-bounded exact receive
        while True:
            now = time.monotonic()
            elapsed = now - started
            if elapsed >= run_s:
                break
            if elapsed > warm and not tracked:
                tracemalloc.start()  # the <1 MiB delta is measured post-warm-up
                tracked = True
            got = (await services.transfer(
                {"kind": "stream_receive", "max_bytes": chunk,
                 "termination": "lf", "exact_bytes": chunk},
                _Ctx(2.0)))["data"]
            if not got:
                continue
            ring_max = max(ring_max, link.ring_length())
            for frame in parser_state.feed(got):
                if frame.type != sample_type:
                    continue
                counter, _values = _codec.parse_sample(frame.payload, n_active=1)
                if first_counter is None:
                    first_counter = counter
                detector.feed(counter)
                decoded += 1
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        gaps = detector.gaps
        return {
            "decoded": decoded,
            "fps": decoded / run_s,
            "ring_max": ring_max,
            "ring_bound": link.ring_capacity,
            "mem_peak_mib": peak / 2**20,
            "gaps": gaps,
        }
    finally:
        link.close()
        far.close()
        os.close(slave_fd)


class _PtyFar:
    """The emulator pushed onto the pty master by a drain thread."""

    def __init__(self, master_fd: int) -> None:
        self._fd = master_fd
        self._stop = False
        self._emu = None
        import threading

        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def attach(self, emu: AdcEmulator) -> None:
        self._emu = emu

    def _pump(self) -> None:
        while not self._stop:
            try:
                import select

                readable, _, _ = select.select([self._fd], [], [], 0.001)
                if readable:
                    data = os.read(self._fd, 65536)
                    if data and self._emu is not None:
                        self._emu.write(data)
                if self._emu is not None:
                    if self._emu.streaming:
                        buf = bytearray()
                        for _ in range(2048):  # bulk-generate: the emulator is the line
                            buf += self._emu.read(4096)
                    else:
                        buf = self._emu.read(65536)  # queued replies only
                    if buf:
                        os.write(self._fd, bytes(buf))
            except OSError:
                break

    def close(self) -> None:
        self._stop = True
        self._thread.join(timeout=2.0)


parser_state = None  # set in _main
if __name__ == "__main__":
    rows = []
    for i in range(RUNS):
        parser_state = codec.FrameParser()
        row = asyncio.run(_main(RUN_S))
        rows.append(row)
        print(f"run {i + 1}: decoded={row['decoded']} fps={row['fps']:.0f} "
              f"ring_max={row['ring_max']}/{row['ring_bound']} "
              f"mem_peak={row['mem_peak_mib']:.2f} MiB gaps={row['gaps']}")
    fps_list = [r['fps'] for r in rows]
    print(f"median fps: {statistics.median(fps_list):.0f}")
