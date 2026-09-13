"""BenchWeave command line entrypoint (dispatches to the Click tree)."""

from benchweave.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
