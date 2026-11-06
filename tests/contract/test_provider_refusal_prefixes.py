"""The provider refusal-prefix family (issue #568, acceptance arm C2).

The refusal-prefix family is machine-matchable: every prefix named in the
design record's sections 1.2 and 2 has an emitter in the source, and no
prefix outside the pinned family leaks — the reverse pin catches a
typo'd or invented prefix the behavioral arms would name differently.

Three sets, one scan over the quoted refusal strings of the four
emitter modules:

- ``DESIGNED`` — the family the design record names (section 1.2's typed
  refusals + the loader's settings twin);
- ``EXTENSIONS`` — the runtime ladder's own typed vocabulary (driver
  fault, lifecycle and stream-ladder refusals) — this increment's
  additions, pinned here so the family stays closed;
- ``PRE_EXISTING`` — the guard's landed ``provider_transaction:`` family
  (issue #147 increment 3, unchanged).

The design's family sentence also names ``connections_digest_mismatch:``.
That prefix is DEAD vocabulary and is deliberately NOT carried here: no
reachable path can raise it, because no authority pins the connections
document's own bytes by digest (a mismatch needs a second party holding
the expected digest; the document has none). The reverse pin below is the
honest tripwire: if a future mechanism ever pins those bytes (the
commissioning-shape promotion would), its emitter shows up as a leak and
must be classified into ``DESIGNED`` with a behavioral arm — the prefix
earns its place only when it can fire.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: The design record's named family (sections 1.2/§2).
DESIGNED = frozenset(
    {
        "connections_schema:",
        "provider_grant_window_exceeded:",
        "provider_grant_endpoint_absent:",
        "provider_grant_endpoint_conflict:",
        "provider_not_admitted:",
        "provider_runtime_backend_missing:",
        "provider_runtime_device_unavailable:",
        "provider_runtime_op_unsupported:",
        "provider_runtime_kind_unsupported:",
        "provider_runtime_audit_refused:",
    }
)

#: The runtime ladder's typed vocabulary beyond the design's named set —
#: this increment's own additions (driver fault/lifecycle/stream refusals).
EXTENSIONS = frozenset(
    {
        "provider_runtime_driver_fault:",
        "provider_runtime_driver_absent:",
        "provider_runtime_faulted:",
        "provider_runtime_closed:",
        "provider_runtime_not_open:",
        "provider_runtime_open_refused:",
        "provider_runtime_result_grammar:",
        "provider_runtime_stream_shape:",
        "provider_runtime_stream_bounds:",
        "provider_runtime_stream_incomplete:",
    }
)

#: The landed guard family (issue #147 increment 3) — unchanged by #568.
PRE_EXISTING = frozenset({"provider_transaction:"})

_SOURCES = (
    "src/benchweave/control/provider_settings.py",
    "src/benchweave/control/documents.py",
    "src/benchweave/content/provider_transport.py",
    "src/benchweave/content/provider_runtime.py",
)

# Quoted refusal strings only (a typed refusal's prefix always lands inside
# a string literal; type annotations and prose identifiers never do).
_PREFIX_FINDER = re.compile(r"[\"']((?:provider|connections)_[a-z_]+:)")


def _quoted_prefixes() -> set[str]:
    found: set[str] = set()
    for relpath in _SOURCES:
        text = (ROOT / relpath).read_text(encoding="utf-8")
        found.update(_PREFIX_FINDER.findall(text))
    return found


def test_every_designed_prefix_has_an_emitter() -> None:
    found = _quoted_prefixes()
    missing = DESIGNED - found
    assert not missing, f"designed prefixes with no emitter: {sorted(missing)}"


def test_no_prefix_outside_the_pinned_family_leaks() -> None:
    found = _quoted_prefixes()
    leaks = found - DESIGNED - EXTENSIONS - PRE_EXISTING
    assert not leaks, f"undesigned prefixes in the source: {sorted(leaks)}"
