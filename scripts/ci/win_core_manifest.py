"""The Windows core-subset ratchet manifest (issue #471).

The windows CI lane runs the cross-platform core subset (``-m wincore``,
design of record ``.claude/deep-review/2026-10-15-windows-core-subset-design.md``).
This script is the no-silent-drop ratchet for that selection, the #221
docs-baseline shape applied to the test partition: every test file's
``(total, core)`` counts are pinned in ``tests/win_core_manifest.json``;
growth AND shrinkage refuse ``--check`` until ``--refresh`` moves the file —
the refresh diff is the review surface.

Three checks, one exit contract (0 green, 1 drifted, 2 failed closed):

1. Count ratchet — the collected ``(total, core)`` per file equal the
   manifest rows exactly; an extra or missing file is drift, not noise.
2. W1 probe — the live win32/msvcrt text scan of ``src/benchweave`` equals
   the manifest's ``w1_map`` key set. A new win32 branch in an unmapped src
   file reds here until the file joins ``w1_map`` (and its tests are marked);
   a mapped file whose branch disappears reds the same equality from the
   other side.
3. W1 shape — every ``w1_map`` row's test files exist and are marked
   WHOLE-MODULE (``core == total`` in the manifest), because the W1 branch
   executes at module-level call depth that per-test curation cannot bound
   honestly.

``--refresh`` moves ONLY the counts (and validates the rows it writes); the
``w1_map`` is human-authored and is carried verbatim, so a probe-set change
stays red under ``--check`` until the map is edited by hand. What this check
does NOT catch: a test-side platform construct (e.g. a tzset-guarded test)
in a file with no src win32 branch — the probe covers src-side branching
only; the classes and the owner-reviewed manifest diff are the boundary
(design §9, under-selection residual).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCHEMA = "benchweave.win-core-manifest/1"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "tests" / "win_core_manifest.json"
SRC_ROOT = REPO_ROOT / "src" / "benchweave"
_PROBE_RE = re.compile(r"win32|msvcrt")
_COLLECT_RE = re.compile(r"^([^ :]+): (\d+)$")


def probe_set(root: Path = REPO_ROOT) -> set[str]:
    """The win32/msvcrt-branching src files, as repo-relative posix paths."""
    hits: set[str] = set()
    src = root / "src" / "benchweave"
    for path in sorted(src.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if _PROBE_RE.search(text):
            hits.add(path.relative_to(root).as_posix())
    return hits


def collect_counts(
    root: Path, marker: str | None
) -> dict[str, int]:
    """Per-file collected test counts for a marker expression (or all tests).

    Parses pytest's ``--collect-only -q`` per-file summary lines
    (``<path>: <count>``). Paths are normalized to posix form; lines outside
    the collected ``tests/`` and ``docs/`` trees are ignored.
    """
    cmd = [sys.executable, "-m", "pytest", "--collect-only", "-q"]
    if marker is not None:
        cmd += ["-m", marker]
    proc = subprocess.run(
        cmd,
        cwd=root,
        capture_output=True,
        text=True,
        timeout=300,
        env={"PYTEST_ADDOPTS": "", "PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        check=False,
    )
    if proc.returncode not in (0, 5):
        # 5 is pytest's empty-selection exit — data (e.g. -m wincore on a
        # tree with nothing marked yet), not a collection failure. Any other
        # nonzero code fails closed.
        print(
            f"win_core_manifest: collection failed (exit {proc.returncode})\n"
            f"{proc.stdout}\n{proc.stderr}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    counts: dict[str, int] = {}
    for line in proc.stdout.splitlines():
        match = _COLLECT_RE.match(line.strip())
        if match is None:
            continue
        path = match.group(1).replace("\\", "/")
        if (path.startswith("tests/") or path.startswith("docs/")) and (
            path.endswith(".py") or path.endswith(".md")
        ):
            counts[path] = int(match.group(2))
    return counts


def build_rows(
    root: Path,
) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    """Fresh per-file ``(total, core)`` rows plus the raw per-file core counts."""
    totals = collect_counts(root, None)
    cores = collect_counts(root, "wincore")
    rows = {
        path: {"total": totals[path], "core": cores.get(path, 0)}
        for path in sorted(totals)
    }
    return rows, cores


def load_manifest(path: Path) -> dict:
    """Read the manifest, refusing a foreign schema (fail closed)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(
            f"win_core_manifest: manifest absent at {path} — run --refresh "
            "to found it, then commit it",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    except json.JSONDecodeError as exc:
        print(f"win_core_manifest: manifest is not JSON: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        print(
            f"win_core_manifest: manifest schema mismatch (want {SCHEMA})",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return data


def check(root: Path, manifest_path: Path) -> int:
    """Compare the live tree against the manifest. Returns the exit code."""
    manifest = load_manifest(manifest_path)
    rows, _ = build_rows(root)
    problems: list[str] = []

    committed = manifest.get("files", {})
    expected_keys = set(rows)
    committed_keys = set(committed)
    for key in sorted(expected_keys - committed_keys):
        problems.append(f"file not in manifest: {key} (total {rows[key]['total']})")
    for key in sorted(committed_keys - expected_keys):
        problems.append(f"manifest row for absent file: {key}")
    for key in sorted(expected_keys & committed_keys):
        want, have = rows[key], committed[key]
        if want["total"] != have.get("total"):
            problems.append(
                f"total drift: {key} collected {want['total']}, "
                f"manifest {have.get('total')}"
            )
        if want["core"] != have.get("core"):
            problems.append(
                f"core drift: {key} collected {want['core']}, "
                f"manifest {have.get('core')}"
            )

    w1_map = manifest.get("w1_map", {})
    if not isinstance(w1_map, dict):
        problems.append("w1_map is not an object")
        w1_map = {}
    live_probe = probe_set(root)
    map_keys = set(w1_map)
    for key in sorted(live_probe - map_keys):
        problems.append(
            f"win32-branching src file not in w1_map: {key} "
            "(map the file and whole-module mark its tests)"
        )
    for key in sorted(map_keys - live_probe):
        problems.append(
            f"w1_map row without a live win32/msvcrt probe hit: {key} "
            "(dead row — remove it)"
        )
    for src_key in sorted(live_probe & map_keys):
        for test_file in w1_map[src_key]:
            row = committed.get(test_file)
            if row is None:
                problems.append(
                    f"w1_map row names a test file with no manifest row: "
                    f"{src_key} -> {test_file}"
                )
            elif row.get("core") != row.get("total"):
                problems.append(
                    f"W1 whole-module mark incomplete: {test_file} "
                    f"(core {row.get('core')} != total {row.get('total')})"
                )

    if problems:
        print(
            f"win_core_manifest: {len(problems)} drift problem(s) "
            f"(--refresh moves the counts; the w1_map is hand-edited):"
        )
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(
        f"win_core_manifest: ok — {len(committed)} files, "
        f"{sum(r['core'] for r in committed.values())} core of "
        f"{sum(r['total'] for r in committed.values())} tests, "
        f"w1_map {len(map_keys)} src file(s)"
    )
    return 0


def refresh(root: Path, manifest_path: Path) -> int:
    """Rewrite the count rows; carry w1_map verbatim (human-authored)."""
    existing = load_manifest(manifest_path) if manifest_path.exists() else {}
    rows, _ = build_rows(root)
    document = {
        "schema": SCHEMA,
        "w1_map": existing.get("w1_map", {}),
        "files": rows,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    live_probe = probe_set(root)
    map_keys = set(document["w1_map"])
    if live_probe != map_keys:
        print(
            "win_core_manifest: counts refreshed, but the w1_map does not "
            "match the live probe set — hand-edit w1_map "
            f"(probe-only keys: {sorted(live_probe - map_keys)}; "
            f"dead rows: {sorted(map_keys - live_probe)})",
            file=sys.stderr,
        )
    print(f"win_core_manifest: refreshed {manifest_path} ({len(rows)} file rows)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--check", action="store_true", help="refuse on any drift from the manifest"
    )
    action.add_argument(
        "--refresh", action="store_true", help="rewrite the count rows"
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="manifest path override (default: tests/win_core_manifest.json)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="repo root override (default: the checkout this script lives in)",
    )
    args = parser.parse_args(argv)
    if args.check:
        return check(args.root, args.manifest)
    return refresh(args.root, args.manifest)


if __name__ == "__main__":
    raise SystemExit(main())
