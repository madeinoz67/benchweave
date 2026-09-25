"""Child process for disposition-transaction SIGKILL injection. Not a test
module.

Protocol (stdout markers, line-flushed):
  READY     the disposition invocation transaction is OPEN with one row
            fully processed (the mid-transaction hook fired), uncommitted;
            OR — with an archive target (issue #199) — Phase A placed and
            verified its FIRST object (the stage hook fired), no store
            transaction open
  COMMITTED the whole invocation committed (the survivor twin)
Parent kills the process after seeing the marker. argv:
  _dispose_child.py <mode> <data_dir> [<archive-target>]
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from benchweave.cli.dispose import dispose_from_data_dir

NOW = "2026-09-27T00:00:00Z"


def _hold_hook(index: int) -> None:
    if index == 0:
        print("READY", flush=True)
        sys.stdin.read()  # block until killed


def _stage_hook(index: int) -> None:
    if index == 0:
        print("READY", flush=True)
        sys.stdin.read()  # block until killed


def main() -> None:
    mode: Any = sys.argv[1]
    data_dir = Path(sys.argv[2])
    target = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    dispose_from_data_dir(
        data_dir,
        now=NOW,
        execute=True,
        archive_target=target,
        mid_transaction_hook=_hold_hook if mode == "hold" else None,
        stage_hook=_stage_hook if mode == "stage-hold" else None,
    )
    print("COMMITTED", flush=True)
    sys.stdin.read()  # block until killed


if __name__ == "__main__":
    main()
