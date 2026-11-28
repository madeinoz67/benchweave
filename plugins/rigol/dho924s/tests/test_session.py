# author: Stephen Eaton
"""A5: no transport I/O outside the declared grammar, and the session layer
over an injected transport.

Every reply in this module is SYNTHETIC: it has the shape the manufacturer's
programming guide documents and invented values. Nothing was recorded on an
instrument. The declared grammar is one query, the identity query. No other
command is evidenced for this unit, so no other command can be sent.
"""

import asyncio
import math
from types import MappingProxyType
from typing import Any

import pytest
from support import RecordingTransport, run

from benchweave_rigol_dho924s.client import (
    COMMANDS,
    IEEE488_2_NL,
    Framing,
    OperationBusy,
    ScpiClient,
    SessionUnusable,
    UnsupportedCommand,
)
from benchweave_rigol_dho924s.codec import FrameError, TextFormatError
from benchweave_rigol_dho924s.session import Identity, IdentityMismatch, identify

REPLY = b"RIGOL TECHNOLOGIES,DHO924S,SYNTHETIC-SERIAL,SYNTHETIC-FIRMWARE\n"
MESSAGE = REPLY[:-1]
BOUND = 256

# Commands a later increment might send once they are evidenced. None may be
# sent today, by short name, by long name, or as raw SCPI text.
UNEVIDENCED = [
    "*IDN?",
    "*RST",
    ":STOP",
    ":SINGle",
    ":RUN",
    ":ACQuire:MDEPth 1M",
    ":WAV:DATA?",
    "reset",
    "stop",
    "single",
    "run",
    "wav_data",
    "idn ",
    "IDN",
    "idn?",
    "",
]


def client(transport: RecordingTransport, framing: Framing = IEEE488_2_NL) -> ScpiClient:
    return ScpiClient(transport, framing=framing)


def query(
    transport: RecordingTransport, framing: Framing = IEEE488_2_NL, **overrides: Any
) -> bytes:
    arguments: dict[str, Any] = {"timeout": 1.0, "max_bytes": BOUND}
    arguments.update(overrides)
    return run(client(transport, framing).query("idn", **arguments))


@pytest.mark.parametrize("name", UNEVIDENCED)
def test_an_unknown_command_raises_before_any_write(name: str) -> None:
    transport = RecordingTransport(REPLY)
    session = client(transport)
    with pytest.raises(UnsupportedCommand):
        run(session.query(name, timeout=1.0, max_bytes=BOUND))
    assert transport.sent == []
    assert transport.received_sizes == []
    # A refusal before I/O says nothing about the link, so it does not poison it.
    assert session.unusable is False


def test_no_write_is_evidenced_so_no_command_can_be_written() -> None:
    transport = RecordingTransport(REPLY)
    session = client(transport)
    for name in ("idn", "reset", "*RST", ""):
        with pytest.raises(UnsupportedCommand):
            run(session.write(name, timeout=1.0))
    assert transport.sent == []


def test_the_declared_grammar_is_exactly_the_identity_query() -> None:
    assert type(COMMANDS) is MappingProxyType
    assert dict(COMMANDS) == {"idn": b"*IDN?"}


def test_query_sends_the_command_with_its_terminator_and_strips_the_reply_terminator() -> None:
    transport = RecordingTransport(REPLY)
    assert query(transport) == MESSAGE
    assert transport.sent == [b"*IDN?\n"]
    assert transport.received_sizes == [BOUND]


def test_the_framing_is_an_explicit_choice_and_never_a_default() -> None:
    with pytest.raises(TypeError):
        ScpiClient(RecordingTransport(REPLY))  # type: ignore[call-arg]
    crlf = Framing(write_termination=b"\r\n", read_termination="crlf")
    transport = RecordingTransport(REPLY[:-1] + b"\r\n")
    assert query(transport, framing=crlf) == MESSAGE
    assert transport.sent == [b"*IDN?\r\n"]
    eom = Framing(write_termination=b"", read_termination="eom")
    transport = RecordingTransport(MESSAGE)
    assert query(transport, framing=eom) == MESSAGE
    assert transport.sent == [b"*IDN?"]


@pytest.mark.parametrize(
    "arguments",
    [
        pytest.param({"write_termination": b"\n", "read_termination": "any"}, id="unknown-read"),
        pytest.param({"write_termination": "\n", "read_termination": "lf"}, id="text-not-bytes"),
        pytest.param(
            {"write_termination": b"*RST\n", "read_termination": "lf"}, id="carries-a-command"
        ),
        pytest.param({"write_termination": b"\n\n", "read_termination": "lf"}, id="two-line-feeds"),
    ],
)
def test_an_invalid_framing_is_refused_at_construction(arguments: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        Framing(**arguments)


def test_a_reply_that_lacks_the_read_terminator_is_refused() -> None:
    transport = RecordingTransport(MESSAGE)
    session = client(transport)
    with pytest.raises(FrameError) as info:
        run(session.query("idn", timeout=1.0, max_bytes=BOUND))
    assert str(info.value).startswith("SCPI_FRAME: ")
    assert session.unusable is True


def test_an_empty_reply_is_a_lost_link_and_blocks_reuse() -> None:
    transport = RecordingTransport()
    session = client(transport)
    with pytest.raises(ConnectionError):
        run(session.query("idn", timeout=1.0, max_bytes=BOUND))
    assert session.unusable is True
    with pytest.raises(SessionUnusable):
        run(session.query("idn", timeout=1.0, max_bytes=BOUND))
    assert transport.sent == [b"*IDN?\n"]


@pytest.mark.parametrize(
    "timeout",
    [0, -1.0, math.nan, math.inf, 3601.0, "1", True, None],
)
def test_an_invalid_timeout_is_refused_before_io(timeout: Any) -> None:
    transport = RecordingTransport(REPLY)
    with pytest.raises(ValueError):
        query(transport, timeout=timeout)
    assert transport.sent == []


@pytest.mark.parametrize("max_bytes", [0, -1, True, 1.5, "256", None])
def test_an_invalid_bound_is_refused_before_io(max_bytes: Any) -> None:
    transport = RecordingTransport(REPLY)
    with pytest.raises(ValueError):
        query(transport, max_bytes=max_bytes)
    assert transport.sent == []


def test_a_receive_that_never_completes_times_out_once_and_blocks_reuse() -> None:
    transport = RecordingTransport()
    transport.hang = True
    session = client(transport)
    with pytest.raises(TimeoutError):
        run(session.query("idn", timeout=0.01, max_bytes=BOUND))
    assert session.unusable is True


def test_a_send_failure_blocks_reuse() -> None:
    transport = RecordingTransport()
    transport.send_error = ConnectionError("link lost")
    session = client(transport)
    with pytest.raises(ConnectionError):
        run(session.query("idn", timeout=1.0, max_bytes=BOUND))
    assert session.unusable is True


def test_concurrent_calls_are_rejected_and_never_queued() -> None:
    transport = RecordingTransport(REPLY)
    session = client(transport)

    async def scenario() -> None:
        entered = asyncio.Event()

        async def blocking_receive(max_bytes: int) -> bytes:
            entered.set()
            await asyncio.Event().wait()
            return b""

        transport.receive_hook = blocking_receive
        first = asyncio.create_task(session.query("idn", timeout=5.0, max_bytes=BOUND))
        await entered.wait()
        with pytest.raises(OperationBusy):
            await session.query("idn", timeout=1.0, max_bytes=BOUND)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first

    run(scenario())
    assert transport.sent == [b"*IDN?\n"]
    assert session.unusable is True


def test_cancellation_propagates_and_blocks_reuse() -> None:
    transport = RecordingTransport()
    transport.hang = True
    session = client(transport)

    async def scenario() -> None:
        task = asyncio.create_task(session.query("idn", timeout=5.0, max_bytes=BOUND))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    run(scenario())
    assert session.unusable is True


def test_identify_sends_exactly_the_identity_query_and_returns_the_identity() -> None:
    transport = RecordingTransport(REPLY)
    identity = run(
        identify(
            client(transport),
            manufacturer="RIGOL",
            model="DHO924S",
            timeout=1.0,
            max_bytes=BOUND,
        )
    )
    assert identity == Identity(
        manufacturer="RIGOL",
        model="DHO924S",
        serial="SYNTHETIC-SERIAL",
        firmware="SYNTHETIC-FIRMWARE",
    )
    assert transport.sent == [b"*IDN?\n"]
    assert transport.received_sizes == [BOUND]


def test_identify_refuses_a_reply_that_names_another_model() -> None:
    transport = RecordingTransport(REPLY.replace(b"DHO924S", b"DHO914S"))
    with pytest.raises(IdentityMismatch):
        run(
            identify(
                client(transport),
                manufacturer="RIGOL",
                model="DHO924S",
                timeout=1.0,
                max_bytes=BOUND,
            )
        )


@pytest.mark.parametrize("reply", [b"a,b,c\n", b"a,b,c,d,e\n", b"a,,c,d\n", b"\xff\n"])
def test_identify_refuses_a_malformed_reply(reply: bytes) -> None:
    with pytest.raises(TextFormatError):
        run(
            identify(
                client(RecordingTransport(reply)),
                manufacturer="RIGOL",
                model="DHO924S",
                timeout=1.0,
                max_bytes=BOUND,
            )
        )


def test_identify_returns_the_committed_manufacturer_not_the_reply_field() -> None:
    # The manufacturer is a descriptor attribution. The text the unit puts in
    # that field is not evidenced and is not matched.
    identity = run(
        identify(
            client(RecordingTransport(REPLY)),
            manufacturer="RIGOL",
            model="DHO924S",
            timeout=1.0,
            max_bytes=BOUND,
        )
    )
    assert identity.manufacturer == "RIGOL"
