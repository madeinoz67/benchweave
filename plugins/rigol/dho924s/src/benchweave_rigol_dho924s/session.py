# author: Stephen Eaton
"""The one session operation whose shape is documented: identify.

DOCUMENTARY, NOT HARDWARE-QUALIFIED. The guide gives the identity reply as
four comma-separated fields. Whether this unit answers in that form is not
evidenced; the operation fails closed when it does not.

The session has no open or close command. None is evidenced, and opening a
connection sends nothing.

The manufacturer in the returned identity is the committed attribution from
the descriptor. The text a unit puts in the first field of its reply is not
evidenced and is not matched. The model must equal the committed model
exactly, or the operation refuses.
"""

from dataclasses import dataclass

from .client import ScpiClient
from .codec import decode_ascii, parse_idn


@dataclass(frozen=True)
class Identity:
    """What one identity exchange established: the reply's model, serial and firmware.

    ``manufacturer`` is the committed attribution, not a field of the reply.
    """

    manufacturer: str
    model: str
    serial: str
    firmware: str


class IdentityMismatch(ValueError):
    """The reply named a model other than the committed one."""


async def identify(
    client: ScpiClient,
    *,
    manufacturer: str,
    model: str,
    timeout: float,
    max_bytes: int,
) -> Identity:
    """Send the identity query once and return the identity it established.

    The reply is parsed strictly. A reply that is not four non-empty fields
    raises ``TextFormatError``; a reply that names another model raises
    ``IdentityMismatch``. Neither case returns an identity.
    """
    reply = await client.query("idn", timeout=timeout, max_bytes=max_bytes)
    idn = parse_idn(decode_ascii(reply))
    if idn.model != model:
        raise IdentityMismatch(f"Device model does not match the committed model {model!r}")
    return Identity(
        manufacturer=manufacturer,
        model=idn.model,
        serial=idn.serial,
        firmware=idn.firmware,
    )
