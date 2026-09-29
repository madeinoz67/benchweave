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


def _chain(fragments: tuple[str, ...]) -> str:
    """A left-nested concat chain over the given literal fragments —
    len(fragments) - 1 BinOps deep."""
    text = repr(fragments[0])
    for fragment in fragments[1:]:
        text = f"({text} + {fragment!r})"
    return text


# 24 chained BinOps folding to exactly "0.2.0" (caught, at the measured
# depth boundary); 25 chained BinOps whose OUTERMOST node would complete
# "0.2.0" — bounded out, and no inner node folds past "0.2." so no site
# exists anywhere (documented miss). 25 fragments = 24 ops; 26 fragments
# = 25 ops (the completing "0" rides the OUTERMOST op; the constants sit
# at fold depth 25 > the cap).
_DEPTH24: tuple[str, ...] = ("0", ".", "2", ".", *(("",) * 20), "0")
_DEPTH25: tuple[str, ...] = ("0", ".", "2", ".", *(("",) * 21), "0")

# The DOCUMENTED-MISS shapes (fold wave row 3): one arm per named miss
# class in the counter docstring's residual list. Every shape here MUST
# pass the gate — a documented miss, never a silent catch-side change —
# and every FRAGMENT is chosen so the textual walk cannot catch it either
# (no fragment is a complete version, no sub-expression folds to one), so
# the arm truly isolates its miss class.
MISS_MODULE = (
    '"""The documented-miss shapes (issue #269 fold wave row 3)."""\n'
    "\n"
    "import os\n"
    "\n"
    'M1_FORMAT_SPEC = "{:.1f}".format(2.0) + "0"\n'
    'M2_KWARG_FORMAT = "{v}.{w}".format(v="0", w="2.0")\n'
    'M3_PERCENT_DICT = "%(v)s.%(w)s" % {"v": "0", "w": "2.0"}\n'
    'M4_DECODE_WITH_ARGS = b"execution/0.2.0".decode("utf-8")\n'
    'M5_CONDITIONAL_ARM = ("0" if True else "x") + ".2.0"\n'
    'M6_STARRED_FORMAT = "{}".format(*["execution/0.", "2.0"])\n'
    'M7_OS_PATH_JOIN = os.path.join("execution/", "0", ".2", ".0")\n'
)

# The BOUNDARY-TABLE shapes (fold wave row 5), at the MEASURED boundary:
# a 24-BinOp chain folds (caught); a 25-chain is bounded out (documented
# miss — indistinguishable from dynamic, same disclosure class); a
# 4096-char folded string folds (caught); 4097 is bounded out. The
# bounded-out shapes carry no fragment or sub-fold that matches (B3's
# inner nodes stop at "0.2."; B4's tail is prose), so the miss file is
# truly invisible.
BOUNDARY_CAUGHT_MODULE = (
    '"""The fold-cap boundary, caught side (issue #269 fold wave row 5)."""\n'
    "\n"
    f"B1_DEPTH_24_FOLDS = {_chain(_DEPTH24)}\n"
    # 4096 folded chars matching Pattern A: the pad rides BEFORE the id
    # and is non-word ("."), so the \b before "execution" survives.
    'B2_LENGTH_4096_FOLDS = ("." * 4081) + "execution/" + "0.2.0"\n'
)

BOUNDARY_MISS_MODULE = (
    '"""The fold-cap boundary, bounded-out side (issue #269 fold wave row 5)."""\n'
    "\n"
    f"B3_DEPTH_25_BOUNDED_OUT = {_chain(_DEPTH25)}\n"
    # 4097 folded chars — bounded out; no fragment or sub-fold matches.
    'B4_LENGTH_4097_BOUNDED_OUT = ("." * 4082) + "execution/" + "tail"\n'
)

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

MISS_SHAPE_NAMES = (
    "M1_FORMAT_SPEC",
    "M2_KWARG_FORMAT",
    "M3_PERCENT_DICT",
    "M4_DECODE_WITH_ARGS",
    "M5_CONDITIONAL_ARM",
    "M6_STARRED_FORMAT",
    "M7_OS_PATH_JOIN",
)

BOUNDARY_CAUGHT_NAMES = ("B1_DEPTH_24_FOLDS", "B2_LENGTH_4096_FOLDS")
BOUNDARY_MISS_NAMES = ("B3_DEPTH_25_BOUNDED_OUT", "B4_LENGTH_4097_BOUNDED_OUT")


def shape_lines(
    module_text: str, names: tuple[str, ...] = SHAPE_NAMES
) -> dict[str, int]:
    """The line number of each shape's assignment in the written module."""
    lines: dict[str, int] = {}
    for number, line in enumerate(module_text.splitlines(), start=1):
        name = line.split(" = ", 1)[0] if " = " in line else None
        if name in names:
            lines[name] = number
    return lines
