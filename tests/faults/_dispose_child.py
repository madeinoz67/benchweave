"""Child process for disposition-transaction SIGKILL injection. Not a test
module.

Protocol (stdout markers, line-flushed):
  READY     the disposition invocation transaction is OPEN with one row
            fully processed (the mid-transaction hook fired), uncommitted
  COMMITTED the whole invocation committed (the survivor twin)
Parent kills the process after seeing the marker.
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


def main() -> None:
    mode: Any = sys.argv[1]
    data_dir = Path(sys.argv[2])
    hook = _hold_hook if mode == "hold" else None
    dispose_from_data_dir(
        data_dir, now=NOW, execute=True, mid_transaction_hook=hook
    )
    print("COMMITTED", flush=True)
    sys.stdin.read()  # block until killed


if __name__ == "__main__":
    main()
