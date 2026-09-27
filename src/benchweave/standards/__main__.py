"""Command line: python -m benchweave.standards.

Subcommands: export | check | matrix | versions | repin | list | pin | upgrade.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export", help="write the SDK-facing bundle")
    export.add_argument("--out", type=Path, default=Path(".standards-bundle"))
    sub.add_parser("check", help="verify the pinned SDK against a fresh export")
    matrix = sub.add_parser("matrix", help="write or verify docs/compatibility-matrix.md")
    matrix.add_argument(
        "--check", action="store_true", help="compare the committed file; exit 1 when stale"
    )
    sub.add_parser("versions", help="print main, standard, SDK lock and submodule versions")
    sub.add_parser(
        "repin", help="recompute corpus-manifest sha256 rows from the on-disk corpus"
    )
    sub.add_parser(
        "list",
        help="print per-standard range, retained/carried/served sets, yanks, retirements",
    )
    pin = sub.add_parser(
        "pin", help="resolve a package's constraints into its contracts/lock.json"
    )
    pin.add_argument(
        "--package",
        type=Path,
        default=None,
        help="the package directory (default: the single in-tree package)",
    )
    pin.add_argument(
        "--set",
        dest="sets",
        action="append",
        default=[],
        metavar="ID=INTERVAL",
        help="author one constraint interval (caret sugar accepted, expanded on write);"
        " repeatable",
    )
    pin.add_argument(
        "--locked",
        action="store_true",
        help="verify only: refuse plugin_lock_drift when the on-disk lock is not the"
        " resolution; never writes",
    )
    pin.add_argument(
        "--revision",
        metavar="SHA",
        default=None,
        help="record a new revision alongside same-version digest motion (the"
        " revision-scissors override)",
    )
    upgrade = sub.add_parser(
        "upgrade", help="move exactly one standard's lock row to a precise version"
    )
    upgrade.add_argument("standard", help="the standard id whose row moves")
    upgrade.add_argument(
        "--precise", required=True, help="the exact target version (served or yanked)"
    )
    upgrade.add_argument(
        "--package",
        type=Path,
        default=None,
        help="the package directory (default: the single in-tree package)",
    )
    arguments = parser.parse_args()
    root = Path.cwd()
    if arguments.command == "export":
        from .export import export_bundle

        try:
            export_bundle(root, arguments.out)
        except ValueError as exc:
            # Fail-closed exports fail styled like the check/matrix/versions
            # lanes, never as a raw traceback — the corpus-pin gate's refusal
            # (#215 fold-wave F-B) reaches the operator by name.
            print(f"standards export error: {exc}", file=sys.stderr)
            return 1
        print(f"standards bundle exported to {arguments.out}")
        return 0
    if arguments.command == "check":
        from .check import count_failures, run_check

        try:
            lines = run_check(root)
        except ValueError as exc:
            print(f"standards check error: {exc}", file=sys.stderr)
            return 1
        for line in lines:
            print(line)
        if count_failures(lines):
            print(
                f"{count_failures(lines)} standards check failure(s); "
                "run make sync-sdk-standards",
                file=sys.stderr,
            )
            return 1
        print("standards check clean: manifest, bundle, lock and vendored tree agree")
        return 0
    if arguments.command == "matrix":
        from .matrix import DOCS_PATH, check_matrix, render_matrix

        try:
            if arguments.check:
                failures = check_matrix(root)
                for line in failures:
                    print(line)
                if failures:
                    print(
                        "stale compatibility matrix; run "
                        "uv run python -m benchweave.standards matrix",
                        file=sys.stderr,
                    )
                    return 1
                print("compatibility matrix clean: committed file matches the rendered matrix")
                return 0
            target = root / DOCS_PATH
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(render_matrix(root), encoding="utf-8")
            print(f"compatibility matrix written to {target}")
            return 0
        except (ValueError, OSError) as exc:
            # Fail-closed renders fail styled like the check/versions/repin
            # lanes, never as a raw traceback — a missing committed source is
            # an OSError (absent pyproject/.gitmodules), a malformed one a
            # ValueError (StandardsError, TOMLDecodeError).
            print(f"standards matrix error: {exc}", file=sys.stderr)
            return 1
    if arguments.command == "versions":
        from .check import version_lines

        try:
            lines = version_lines(root)
        except ValueError as exc:
            print(f"standards versions error: {exc}", file=sys.stderr)
            return 1
        for line in lines:
            print(line)
        return 0
    if arguments.command == "repin":
        from .repin import repin_manifest

        try:
            changed = repin_manifest(root)
        except ValueError as exc:
            print(f"standards repin error: {exc}", file=sys.stderr)
            return 1
        if changed:
            print(f"re-pinned {len(changed)} row(s): {', '.join(changed)}")
        else:
            print("corpus manifest already current")
        return 0
    if arguments.command == "list":
        from .dependency import list_lines

        try:
            lines = list_lines(root)
        except ValueError as exc:
            print(f"standards list error: {exc}", file=sys.stderr)
            return 1
        for line in lines:
            print(line)
        return 0
    if arguments.command in ("pin", "upgrade"):
        from .dependency import (
            default_package,
            parse_set_argument,
            pin_lock,
            upgrade_lock,
        )

        try:
            package = (
                arguments.package
                if arguments.package is not None
                else default_package(root)
            )
            if arguments.command == "pin":
                sets = [parse_set_argument(value) for value in arguments.sets]
                lines = pin_lock(
                    root,
                    package,
                    sets,
                    locked=arguments.locked,
                    revision=arguments.revision,
                )
            else:
                lines = upgrade_lock(root, package, arguments.standard, arguments.precise)
        except ValueError as exc:
            print(f"standards {arguments.command} error: {exc}", file=sys.stderr)
            return 1
        for line in lines:
            print(line)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
