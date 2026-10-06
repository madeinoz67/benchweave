# author: Stephen Eaton
"""The negotiation's real lane: the SDK serial backend over a pty (issue #407).

The A3 harness shape promoted from one-off instrument to cells: real
pyserial on the pty slave, the pinned SDK's ``SerialLink``/
``SerialCaptureServices``/``reconfigure_link`` from the PINNED submodule
(the ``test_adapter_agreement`` import precedent; the sys.path insert
comes first so an installed SDK never wins), the baud-aware emulator
pumped on the master, and ``negotiate_stream`` with ``reopen`` driving
``services.reconfigure_link`` (the production driver — one bounded
attempt, never a retry).

The far-end baud coupling (the load-bearing test decision, record §2.2):
a pty has no bit timing — bytes never physically garble on any platform;
even at real termios speeds the kernel stores the number and times
nothing. Wrong-baud observability is therefore a MODEL at the far end
regardless of harness; the only question is what feeds the model. The
wrapper opener records the requested settings and drives the far end's
``host_baud`` from the REQUEST — the only coupling from the production
reopen path to the far end. A backend that lies (keeps the old port,
skips the reopen) leaves the far end at boot, every post-switch frame
garbles, and the negotiation cannot reach slim: that is what the N2
control in this file proves.

Disclosed residuals: kernel-level line-speed setting is never tested by
a pty (commissioning evidence, not CI evidence). The N4 bounded arm's
timeout enforcement sits at the await boundary — the services cannot
interrupt a blocked port open mid-``to_thread``, so the abandoned
thread's transport leaks inside the cell; production enforcement is the
host's per-operation timeout at the same boundary (A06's honest
ambiguity, bounded). CI posture: the device-plugins lane is stdlib-only
by design (issue #393's ruling), so this module skips cleanly there
(importorskip) and proves on a posix dev host with the SDK [server]
extra present.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

# The pinned-submodule path goes in BEFORE any import: an importorskip
# that ran first would resolve benchweave_sdk_server from an installed
# (editable) SDK and cache THAT in sys.modules — the lane would then test
# a different checkout's bytes than the pointer names (proven live during
# this increment's N2 control work). The submodule path first, then the
# skip gate: the import resolves from the pointer's exact commit, or the
# module skips cleanly where no submodule exists (the stdlib-only CI lane).
_ROOT = Path(__file__).resolve().parents[4]
_SDK_SRC = _ROOT / "packages" / "sdk" / "src"
sys.path.insert(0, str(_SDK_SRC))
pytest.importorskip(
    "serial", reason="the real lane needs pyserial (the SDK [server] extra)"
)
pytest.importorskip(
    "benchweave_sdk_server.serial",
    reason="the real lane imports the pinned SDK backend",
)

from adc_wire.negotiate import negotiate_stream
from emulator import AdcEmulator

_BOOT_BAUD = 2_000_000
_TARGET = 3_000_000
#: The planted separations (record §7, N3/N4): 0.05 vs 0.3 s — 6x above
#: scheduler noise; every cell asserts outcomes, never a time difference.
_SHRUNK_REVERT_S = 0.05
_PLANTED_SLEEP_S = 0.3


class _FarEnd:
    """The emulator pumped onto the pty master by a drain thread (the
    A3 ``_PtyFar`` shape, baud-coupled through the wrapper opener)."""

    def __init__(self, emu: Any, master_fd: int) -> None:
        self._fd = master_fd
        self._emu = emu
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        while not self._stop.is_set():
            try:
                import select

                readable, _, _ = select.select([self._fd], [], [], 0.02)
                if not readable:
                    continue
                data = os.read(self._fd, 4096)
            except OSError:
                break
            if not data:
                break
            self._emu.write(data)
            out = self._emu.read(4096)
            if out:
                with contextlib.suppress(OSError):
                    os.write(self._fd, out)

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)
        with contextlib.suppress(OSError):
            os.close(self._fd)


class _Lane:
    """One pty lane: real pyserial on the slave, the pinned-SDK services,
    the emulator pumped on the master, the far end coupled ONLY through
    the wrapped opener (the load-bearing decision)."""

    def __init__(
        self,
        *,
        variant: str = "v2",
        t_revert_s: float = 0.25,
        opener_sleep_s: float = 0.0,
        sleep_only_first_reopen: bool = False,
    ) -> None:
        import tty

        self.emu = AdcEmulator(variant=variant, t_revert_s=t_revert_s)
        master_fd, slave_fd = os.openpty()
        tty.setraw(master_fd)
        self._master = master_fd
        self.slave_path = os.ttyname(slave_fd)
        self._slave_fd = slave_fd
        # The recorded REQUESTS and the published link rows: the two
        # observation surfaces every cell asserts on.
        self.requests: list[int] = []
        self.events: list[dict[str, Any]] = []
        self._opener_lock = threading.Lock()
        self._opener_sleep_s = opener_sleep_s
        self._sleep_only_first_reopen = sleep_only_first_reopen
        settings = {"baud": _BOOT_BAUD, "x-negotiated-bauds": [_TARGET]}
        first = self._open_wrapped(self.slave_path, settings)
        from benchweave_sdk_server.serial import (
            LinkReconfigurator,
            SerialCaptureServices,
            SerialLink,
            negotiable_bauds,
        )
        self.services = SerialCaptureServices(
            SerialLink(first),
            max_frame_bytes=64,
            reconfigurator=LinkReconfigurator(
                opener=self._open_wrapped,
                device_path=self.slave_path,
                boot_settings=settings,
                allowed_bauds=negotiable_bauds(settings),
                on_link_event=self.events.append,
            ),
        )
        self._far = _FarEnd(self.emu, master_fd)

    def _open_wrapped(self, device: str, settings: dict[str, Any]) -> Any:
        """The production opener wrapped ONCE (record §2.2): record the
        request, couple the far end from the REQUEST (the only
        host-to-far-end news channel), then open at a pty-legal speed.
        The planted sleep rides the opener itself — the production path
        must sit inside it (that is what makes N4's window a
        device-enforced one)."""
        import serial

        baud = int(settings["baud"])
        with self._opener_lock:
            self.requests.append(baud)
            self.emu.host_baud = baud
        if (
            self._opener_sleep_s
            and not self._sleep_only_first_reopen
            or self._opener_sleep_s
            and self._sleep_only_first_reopen
            and len(self.requests) == 2
        ):
            time.sleep(self._opener_sleep_s)
        return serial.Serial(
            self.slave_path, baudrate=115200, timeout=0.05, write_timeout=1.0
        )

    async def reconfigure_driver(self, baud: int, context: Any) -> None:
        """The production driver: the reopen move the negotiation calls —
        one bounded ``reconfigure_link`` under the operation's context."""
        await self.services.reconfigure_link({"baud": baud}, context)

    def close(self) -> None:
        self._far.close()
        with contextlib.suppress(Exception):
            self.services.link.close()
        with contextlib.suppress(OSError):
            os.close(self._slave_fd)


def _cell_context(operation_id: str, timeout_ms: int = 5000) -> Any:
    """A live host context with the dispatch marker set (the backend's
    transmit discipline: negotiation steps inherit it)."""
    from benchweave_sdk_server.session import HostOperationContext

    context = HostOperationContext(operation_id, timeout_ms=timeout_ms)
    context.dispatched = True
    return context


def _run_negotiation(lane: Any, context: Any, *, reopen: Any = None,
                     target_baud: int = _TARGET,
                     switch_timeout_s: float = 0.5) -> Any:
    """``negotiate_stream`` over the lane under the cell's context."""

    async def scenario() -> Any:
        return await negotiate_stream(
            lane.services,
            context,
            reopen=reopen if reopen is not None else (
                lambda baud: lane.reconfigure_driver(baud, context)
            ),
            target_baud=target_baud,
            switch_timeout_s=switch_timeout_s,
        )

    return asyncio.run(scenario())


def test_n1_negotiation_reaches_slim_over_the_real_backend() -> None:
    """N1 (green v2): ``negotiate_stream`` reaches slim at 3 Mbps over the
    REAL backend with zero garble and a clean link state; exactly one
    link event rides (the switch; none other); the opener saw the boot
    open then the one reopen."""
    lane = _Lane()
    try:
        context = _cell_context("cell-n1")
        result = _run_negotiation(lane, context)
        assert result.slim, f"the negotiation did not reach slim: {result.events}"
        assert result.baud == _TARGET
        assert result.link_state == "ok"
        assert lane.emu.garbled_bytes == 0, "zero garble across the switch"
        assert lane.emu.slim is True, "the device side applied the slim frame format"
        assert [row["event"] for row in lane.events] == ["reconfigured"]
        assert lane.events[0]["from_baud"] == _BOOT_BAUD
        assert lane.events[0]["to_baud"] == _TARGET
        assert lane.requests == [_BOOT_BAUD, _TARGET]
    finally:
        lane.close()


def test_n2_control_the_neutralized_reconfigure_must_not_reach_slim() -> None:
    """N2 (the control the fluff cannot pass): with the reopen neutralized
    to a no-op (no opener call — the far end's only news channel goes
    silent), the post-switch exchange MUST garble and the negotiation
    MUST fall back. If this cell cannot hold, the lane is insensitive to
    the reopen and the opener-coupling claim is theater (the record's
    KILL branch)."""
    lane = _Lane()
    try:
        context = _cell_context("cell-n2")

        async def neutral(baud: int) -> None:
            return None  # the skip-the-reopen backend lie

        result = _run_negotiation(lane, context, reopen=neutral)
        assert not result.slim, "a neutralized reopen must not reach slim"
        assert lane.emu.garbled_bytes > 0, "the post-switch exchange must garble"
        assert result.link_state == "unresolved", (
            "the fallback reopen is the neutralized no-op: the device may "
            "sit at the switched baud — the M8 fold class"
        )
        assert lane.requests == [_BOOT_BAUD], "the neutralized driver never opens"
        assert lane.events == [], "no link events without a real reconfigure"
    finally:
        lane.close()


def test_n3_revert_on_silence_takes_the_real_boot_baud_reopen() -> None:
    """N3: the silent_revert device applies the switch then goes dead; its
    own T_revert (shrunk, planted) reverts it to boot. The fallback path
    performs the REAL boot-baud reopen (requests 2M,3M,2M), the device
    reverts (its guard fires), the confirm identifies cleanly, and two
    link rows ride (the switch up, the revert down)."""
    lane = _Lane(variant="silent_revert", t_revert_s=_SHRUNK_REVERT_S)
    try:
        context = _cell_context("cell-n3")
        result = _run_negotiation(lane, context)
        assert not result.slim, "a silent device must not reach slim"
        assert result.link_state == "ok", (
            "the REAL fallback reopen landed, so the legacy state is known"
        )
        assert lane.emu.reverts, "the device reverted on its own window"
        assert lane.requests == [_BOOT_BAUD, _TARGET, _BOOT_BAUD]
        assert [row["event"] for row in lane.events] == [
            "reconfigured",
            "reconfigured",
        ]
        assert (lane.events[0]["to_baud"], lane.events[1]["to_baud"]) == (
            _TARGET,
            _BOOT_BAUD,
        )
    finally:
        lane.close()


def test_n4_the_reopen_latency_window_is_device_enforced_and_bounded() -> None:
    """N4: a planted 0.3 s sleeping opener against the device's 0.05 s
    revert window. Arm (a): the revert fires WHILE the host sits inside
    its reopen; the post-switch exchange garbles; the negotiation falls
    back through the REAL second reopen. Arm (b): the context deadline
    expires inside the planted sleep — the typed TimeoutError surfaces at
    the await boundary and the opener ran at most once for the switch."""
    lane = _Lane(
        t_revert_s=_SHRUNK_REVERT_S,
        opener_sleep_s=_PLANTED_SLEEP_S,
        sleep_only_first_reopen=True,
    )
    try:
        context = _cell_context("cell-n4")
        result = _run_negotiation(lane, context)
        assert not result.slim, "a 6x-late reopen must not hold the slim path"
        assert lane.emu.reverts, "the device reverted inside the host's reopen"
        assert lane.emu.garbled_bytes > 0, "the post-switch exchange garbles"
        assert result.link_state == "ok", "the fallback reopen restored legacy"
        assert lane.requests == [_BOOT_BAUD, _TARGET, _BOOT_BAUD]

        bounded_lane = _Lane(
            opener_sleep_s=_PLANTED_SLEEP_S,
        )
        try:
            from benchweave_sdk_server.session import HostOperationContext

            ctx = HostOperationContext("cell-n4-bounded", timeout_ms=150)
            ctx.dispatched = True

            async def bounded() -> None:
                await bounded_lane.services.reconfigure_link(
                    {"baud": _TARGET}, ctx
                )

            # The outer bound sits STRICTLY ABOVE the context's own
            # deadline (5 s vs timeout_ms 150): the typed TimeoutError
            # can then only come from the services' own deadline
            # re-checks — an outer bound numerically equal to the inner
            # deadline masks the mechanism (wave-2: a mutant removing
            # BOTH context checks stayed green under the equal bound).
            with pytest.raises(TimeoutError):
                asyncio.run(asyncio.wait_for(bounded(), timeout=5.0))
            assert bounded_lane.requests[-1] == _TARGET
            assert bounded_lane.requests.count(_TARGET) == 1, "opener ran at most once"
        finally:
            bounded_lane.close()
    finally:
        lane.close()


def test_n5_a_v1_device_never_sees_the_capability() -> None:
    """N5: a v1 device NAKs SET_BAUD — the negotiation stays on the legacy
    path, no reconfigure is ever attempted (the opener count never moves
    past the boot open) and no link row rides: the capability is
    invisible to a v1 conversation."""
    lane = _Lane(variant="v1")
    try:
        context = _cell_context("cell-n5")
        result = _run_negotiation(lane, context)
        assert not result.slim
        assert result.baud == _BOOT_BAUD
        assert result.link_state == "ok"
        assert any(
            row["step"] == "v2_attempt" and row["outcome"] == "skipped"
            for row in result.events
        ), "the v1 device skips the v2 attempt"
        assert lane.requests == [_BOOT_BAUD], "no reconfigure attempted"
        assert lane.events == [], "no link events for a v1 conversation"
    finally:
        lane.close()
