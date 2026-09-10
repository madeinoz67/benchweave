"""Child process for SIGKILL fault injection. Not a test module.

Protocol (stdout markers, line-flushed):
  OPENED    store opened and migrated
  READY     uncommitted transaction holding writes is open (mode=hold)
  COMMITTED transaction committed (mode=commit)
Parent kills the process after seeing the marker.
"""

from __future__ import annotations

import sys

from benchweave.state.store import Store


def main() -> None:
    mode, path = sys.argv[1], sys.argv[2]
    store = Store.open(path)
    print("OPENED", flush=True)
    if mode == "hold":
        store.begin_kill_window()  # BEGIN IMMEDIATE + writes, uncommitted
        print("READY", flush=True)
        sys.stdin.read()  # block until killed
    elif mode == "commit":
        store.commit_kill_window()
        print("COMMITTED", flush=True)
        sys.stdin.read()  # block until killed


if __name__ == "__main__":
    main()
