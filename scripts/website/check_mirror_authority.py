#!/usr/bin/env python3
"""Verify the plugin-catalogue mirror against its immutable registry authority.

Author: Stephen Eaton

Issue #224 slice 2 — the gateway-side authority pin (invariants CON-13
amendment). ``website/plugins-index.json`` must byte-equal the registry
repository's generated ``index.json`` at the commit named in
``website/plugins-index.ref``. A commit SHA is immutable — the CON-12
gitlink-pin argument inverted for an external repository — so every
gateway PR can verify its mirror offline-deterministically against a pinned
ref, never a moving branch.

Refuses ``mirror_authority_drift:`` on byte mismatch, on a 404 (a rewritten
or mistyped ref), or on fetch failure (one retry; a network failure is
indistinguishable from a missing mirror — fail closed). That covers
synchronously, at every gateway PR: a hand-edited mirror (even a
non-rendering field the render guard cannot see), a mirror advanced without
its pin, and a pin advanced without its mirror.

CI runs this in the ``gates`` job (network); the tests exercise the
comparison offline via ``--expected`` and the fail-closed arms via
``--index-url``.

Usage::

    python scripts/website/check_mirror_authority.py
    python scripts/website/check_mirror_authority.py --expected path/to/index.json
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REGISTRY_RAW = "https://raw.githubusercontent.com/madeinoz67/benchweave-registry"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _fetch(url: str) -> bytes | None:
    """The authority bytes, or None when unreachable (one retry, fail-closed)."""
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(url, timeout=20) as response:  # noqa: S310
                return response.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
            if attempt == 2:
                return None
            time.sleep(1)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO)
    parser.add_argument(
        "--expected",
        type=Path,
        default=None,
        help="compare against this local file instead of fetching (test seam)",
    )
    parser.add_argument(
        "--index-url",
        default=None,
        help="override the authority URL (test seam for the fail-closed arms)",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    mirror_path = root / "website" / "plugins-index.json"
    ref_path = root / "website" / "plugins-index.ref"
    if not mirror_path.is_file() or not ref_path.is_file():
        print(
            "mirror_authority_drift: the mirror or its pin is missing "
            f"({mirror_path.name}, {ref_path.name})",
            file=sys.stderr,
        )
        return 1
    mirror = mirror_path.read_bytes()
    pin = ref_path.read_text(encoding="utf-8").strip()
    if args.expected is not None:
        authority = args.expected.read_bytes()
    else:
        if not SHA_RE.match(pin):
            print(
                f"mirror_authority_drift: the pin {pin!r} is not a full commit SHA — "
                "the mirror's authority is an immutable registry commit",
                file=sys.stderr,
            )
            return 1
        url = args.index_url or f"{REGISTRY_RAW}/{pin}/index.json"
        fetched = _fetch(url)
        if fetched is None:
            print(
                f"mirror_authority_drift: the registry index at {pin} could not be "
                "fetched (a rewritten or mistyped ref, or a network failure) — fail "
                "closed; re-run the documented sync from a maintainer checkout",
                file=sys.stderr,
            )
            return 1
        authority = fetched
    if mirror != authority:
        print(
            f"mirror_authority_drift: website/plugins-index.json differs from the "
            f"registry index at {pin} (a hand-edited mirror, a mirror advanced "
            "without its pin, or a pin advanced without its mirror) — re-run the "
            "documented sync; never hand-edit",
            file=sys.stderr,
        )
        return 1
    print(f"mirror matches the registry index at {pin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
