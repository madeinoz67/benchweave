"""The committed evasion battery: twelve constant-assembly shapes (issue #269, design §1.3).

Every shape assembles a version-shaped string from constants only. The
zero-literal gate must refuse each one once the constant-folding pass is
live; at the battery's base exactly three were caught (the shapes leaving a
complete string ``Constant`` in the AST) and nine passed — the arithmetic
that ties this reconstruction to the recorded 9/12. This module is henceforth
the spec for the class: the next evasion probe extends this file, not a
session's memory. The gateway's own scopes never scan ``tests/`` — the
shapes are inert fixture data here, and the battery test writes them into a
scratch tree to exercise the counter.
"""

from __future__ import annotations

BATTERY_MODULE = '''\
"""The twelve adversarial assembly shapes (issue #269, design §1.3).

Committed as the evasion-class spec: every shape assembles a version-shaped
string from constants only, and the zero-literal gate must refuse each one.
"""

S1_CONCAT = "execution/0." + "2.0"
S2_CONCAT_CHAIN = "exec" + "ution/" + "0." + "2." + "0"
S3_FSTRING_INTS = f"0.{2}.{0}"
S4_FSTRING_MIXED = f"execution/{0}.{2}.{0}"
S5_PERCENT_TUPLE = "0.%d.%d" % (2, 0)
S6_PERCENT_SINGLE = "execution/%s" % "0.2.0"
S7_BYTES_DECODE = b"execution/0.2.0".decode()
S8_JOIN_BARE = ".".join(["0", "2", "0"])
S9_JOIN_PATH = "/".join(["execution", "0.2.0"])
S10_CHR_ASSEMBLY = chr(48) + ".2.0"
S11_FORMAT = "{}/{}.{}.{}".format("execution", 0, 2, 0)
S12_PLAIN_CONSTANT = "0.2.0"
'''

SHAPE_NAMES = (
    "S1_CONCAT",
    "S2_CONCAT_CHAIN",
    "S3_FSTRING_INTS",
    "S4_FSTRING_MIXED",
    "S5_PERCENT_TUPLE",
    "S6_PERCENT_SINGLE",
    "S7_BYTES_DECODE",
    "S8_JOIN_BARE",
    "S9_JOIN_PATH",
    "S10_CHR_ASSEMBLY",
    "S11_FORMAT",
    "S12_PLAIN_CONSTANT",
)


def shape_lines(module_text: str) -> dict[str, int]:
    """The line number of each shape's assignment in the written module."""
    lines: dict[str, int] = {}
    for number, line in enumerate(module_text.splitlines(), start=1):
        name = line.split(" = ", 1)[0] if " = " in line else None
        if name in SHAPE_NAMES:
            lines[name] = number
    return lines
