"""Command line: python -m benchweave.standards export."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("--out", type=Path, default=Path(".standards-bundle"))
    arguments = parser.parse_args()
    if arguments.command == "export":
        from .export import export_bundle

        export_bundle(Path.cwd(), arguments.out)
        print(f"standards bundle exported to {arguments.out}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
