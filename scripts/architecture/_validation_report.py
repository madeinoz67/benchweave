"""Shared machinery for the machine-written validation-report family.

One renderer, one author-side writer epilogue, one manifest-derived version
lookup; the family scripts supply only their constants and their checks
(issue #102 D1, generalizing the #79 devices writer and its #102 D2
manifest derivation to every suite with a machine-written report).
"""

import json
import sys
from pathlib import Path
from typing import NoReturn

from benchweave.standards.manifest import load_manifest


def active_standard_version(standards_root: Path, standard_id: str) -> str:
    """The active version of a standard, derived from the standards manifest.

    Never a hardcoded literal and never a silent fallback: a missing manifest
    or a manifest without the standard's entry is a loud refusal — the corpus
    a family script validates IS the manifest's active version. Only the
    refusal PREFIX is byte-stable across the family: ``{standard_id}_manifest_absent:``
    is byte-identical to the historical ``otdp_manifest_absent:`` for devices
    (what the #119/#125 surfaces match on); the message text after the prefix
    is generic and lowercase ("active otdp", not the historical "active OTDP").
    An unparseable manifest raises ``json.JSONDecodeError`` instead — loud,
    but outside the named refusal prefix family (disclosed residual, the
    D2 record's accepted posture). First-match on a duplicate-row manifest
    stands as-is (mirrors the in-tree manifest.py precedent).
    """

    manifest_path = standards_root / "standards-manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(
            f"{standard_id}_manifest_absent: standards-manifest.json not found — the "
            f"active {standard_id} version cannot be derived"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest.get("standards", []):
        if entry.get("id") == standard_id:
            version = entry.get("version")
            if isinstance(version, str) and version:
                return version
    raise SystemExit(
        f"{standard_id}_manifest_absent: standards-manifest.json carries no {standard_id} "
        f"entry with a version — the active {standard_id} version cannot be derived"
    )


def corpus_directory(standards_root: Path, standard_id: str) -> Path:
    """The corpus directory a family script validates (the dev-proof lane).

    Default (no ``--corpus`` in argv): the manifest-active version's
    directory, resolved — byte-identical to the per-script derivations this
    replaced. With ``--corpus <dir>``: exactly the manifest-declared dev
    head's directory for ``standard_id``, or a loud refusal. The override is
    a view, never a mutation — this function resolves and returns a path and
    touches nothing (the SDK lock, vendored tree and pointer are not on this
    path at all; the acceptance replay's arm-B extension proves the stillness
    live). ``--corpus`` cannot combine with ``--write-report``: the
    machine-written reports are a property of released versions, and a dev
    run is a check, not a report (devstage record §13.8).
    """
    argv = sys.argv[1:]
    override = _corpus_override(argv)
    if override is None:
        return (
            standards_root / standard_id / active_standard_version(standards_root, standard_id)
        ).resolve()
    head_version = _declared_dev_head(standards_root, standard_id)
    expected = (standards_root / standard_id / head_version).resolve()
    if Path(override).resolve() != expected:
        raise SystemExit(
            f"corpus_override_not_dev_head: {override} — the dev-proof lane accepts "
            f"exactly the manifest-declared head for {standard_id} "
            f"(standards/{standard_id}/{head_version})"
        )
    if "--write-report" in argv:
        raise SystemExit(
            "corpus_override_write_refused: --corpus and --write-report are mutually "
            "exclusive — the machine-written reports are a property of released "
            "versions; a dev run is a check, not a report"
        )
    return expected


def _corpus_override(argv: list[str]) -> str | None:
    """The ``--corpus`` value from argv (``--corpus=dir`` or ``--corpus dir``).

    The family's epilogue reads ``--write-report`` positionally the same way;
    a valueless or empty override is a usage refusal, not a silent default —
    a typo'd proof run must not quietly prove the released tree instead.
    """
    for index, argument in enumerate(argv):
        if argument == "--corpus":
            if index + 1 >= len(argv) or not argv[index + 1]:
                raise SystemExit(
                    "corpus_override_invalid: --corpus requires a directory value "
                    "(the manifest-declared dev head for this script's standard)"
                )
            return argv[index + 1]
        if argument.startswith("--corpus="):
            value = argument.removeprefix("--corpus=")
            if not value:
                raise SystemExit(
                    "corpus_override_invalid: --corpus requires a directory value "
                    "(the manifest-declared dev head for this script's standard)"
                )
            return value
    return None


def _declared_dev_head(standards_root: Path, standard_id: str) -> str:
    """The dev head version declared for ``standard_id``, or a loud refusal.

    Resolved through the CANONICAL loader (review row 6): every dev-block
    shape refusal ``load_manifest`` enforces — a malformed block, a
    non-``<target>-dev`` version, a target that is not strictly greater
    than active — is refused by the lane too, with the loader's own message.
    A stale-equal head can therefore no longer point the lane at a
    directory the active tree owns.
    """
    try:
        manifest = load_manifest(standards_root.parent)
    except FileNotFoundError:
        raise SystemExit(
            f"{standard_id}_manifest_absent: standards-manifest.json not found — the "
            f"dev head for {standard_id} cannot be derived"
        ) from None
    except ValueError as exc:
        # StandardsError and friends: the loader's prefixed message IS the
        # lane's refusal — same words on both surfaces.
        raise SystemExit(str(exc)) from None
    for entry in manifest.standards:
        if entry.id == standard_id:
            if entry.dev is not None:
                return entry.dev.version
            raise SystemExit(
                f"{standard_id}_dev_head_absent: the manifest declares no dev head "
                f"for {standard_id} — nothing for --corpus to prove"
            )
    raise SystemExit(
        f"{standard_id}_manifest_absent: standards-manifest.json carries no {standard_id} "
        f"entry — the dev head cannot be derived"
    )


def marker(script: str) -> str:
    """The family's generated-marker line, single-sourced: the per-suite
    ``GENERATED_MARKER`` constants and the writer's own output both call
    this, so the marker bytes cannot fork between scripts."""
    return (
        f"<!-- Generated by {script} --write-report — regenerate on check changes; "
        "do not hand-edit. -->"
    )


def render(
    checks: list[tuple[str, bool]],
    *,
    marker: str,
    title: str,
    coverage: str,
    limit: str | None = None,
) -> str:
    """Render a validation report markdown from a check list.

    Pure and order-canonical: the ``## Checks`` list is emitted sorted by
    name because suite accumulation order is partly glob order
    (directory-entry order), which is not portable across platforms; the
    rendered bytes are a function of the check set only. ``limit`` is
    optional for suites whose prose keeps coverage and limits in one
    paragraph.
    """

    passed = sum(1 for _, ok in checks if ok)
    lines: list[str] = [
        marker,
        "",
        title,
        "",
        f"**Result: {passed}/{len(checks)} checks passed; {len(checks) - passed} failed.**",
        "",
        coverage,
    ]
    if limit is not None:
        lines += ["", limit]
    lines += ["", "## Checks", ""]
    lines.extend(f"- {'PASS' if ok else 'FAIL'}: {name}" for name, ok in sorted(checks))
    lines.append("")
    return "\n".join(lines)


def main(
    checks: list[tuple[str, bool]],
    out_path: Path,
    *,
    script: str,
    title: str,
    coverage: str,
    limit: str | None = None,
) -> NoReturn:
    """The shared author-side epilogue: report, then maybe write the report.

    Only reachable under a real ``__main__`` — each family script calls this
    from its own ``if __name__ == "__main__":`` block, and ``runpy.run_path``
    executes the module body with ``__name__ == "<run_path>"``, so the
    pytest harness can never reach the writer. Refuses (exit 1) to write
    when any check fails. Always raises ``SystemExit`` (the refuse path with
    code 1, the tail with the run's overall verdict) — hence ``NoReturn``.
    """

    failures = [name for name, ok in checks if not ok]
    for failure in failures:
        print("FAIL:", failure)
    print(f"{len(checks) - len(failures)}/{len(checks)} checks passed")
    if "--write-report" in sys.argv[1:]:
        if failures:
            print(f"refusing to write the validation report: {len(failures)} failing check(s)")
            raise SystemExit(1)
        out_path.write_text(
            render(
                [(str(name), bool(ok)) for name, ok in checks],
                marker=marker(script),
                title=title,
                coverage=coverage,
                limit=limit,
            ),
            encoding="utf-8",
            newline="\n",
        )
        print(f"wrote {out_path}")
    raise SystemExit(bool(failures))
