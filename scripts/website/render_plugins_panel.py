#!/usr/bin/env python3
"""Render the plugin catalogue panel block from the committed mirror.

Author: Stephen Eaton

Issue #224 slice 2 (parent #209), invariants CON-13 amendment: the Plugins
panel's rows are a COMMITTED GENERATED BLOCK in ``website/index.html``
between machine markers, rewritten only by this tool — regenerate, never
hand-edit (the git-cliff CHANGELOG discipline). The mirror
``website/plugins-index.json`` is a byte-identical copy of the registry
repository's generated ``index.json``; its authority stays with that
repository's generator (the CON-4 ``sdk_compatibility`` derived-copy
precedent), and ``website/plugins-index.ref`` records the registry commit
the mirror was synced from. The website slice RENDERS the index and never
reshapes it.

Default-view rule (CR-22, load-bearing): the block contains exactly the
rows with ``kind == "admitted-release"`` AND ``signature_state ==
"signed-valid"``. Everything else is absent from the static bytes and
reachable only through explicit client-side filters (which render it with
its kind tag — CR-56). In-flight submissions are structurally absent
everywhere: the index is generated from ``releases/``, and a submission
only becomes a release at publish.

Seven contract fields per row (CR-20 — rendered or explicitly "none"):
publisher; the immutable release id (``registry_id``/``package_id``
static, version and manifest digest JS-filled from the index); compatibility
(JS-filled, verbatim per CR-19); licence and provenance; test evidence;
maintenance; advisories. Unverified markers render as fixed badge-warning
strings via ``MARKER_DISPLAY`` (the two slice-1 markers); any unknown
marker id renders verbatim — forward-honest, never dropped.

Fail-closed at generation time (the class-11 ban holds here, not only in
the tests): an unparseable mirror or an unknown ``kind`` refuses with
``panel_input_invalid:``; output containing a three-component version
literal refuses with ``panel_literal_refused:``; output containing ``{{``
refuses with ``panel_braces_refused:``; a block that drifted from a fresh
render refuses with ``panel_drift:`` under ``--check``.

Stdlib only — this tool must run from a bare gateway checkout inside the
registry repository's sync path.

Usage::

    python scripts/website/render_plugins_panel.py            # print the block
    python scripts/website/render_plugins_panel.py --write    # rewrite the block
    python scripts/website/render_plugins_panel.py --check    # refuse drift
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]

BEGIN_MARKER = (
    "<!-- bw:plugins-panel begin (generated from website/plugins-index.json by\n"
    "     scripts/website/render_plugins_panel.py — regenerate, do not hand-edit) -->"
)
END_MARKER = "<!-- bw:plugins-panel end -->"

SEMVER_RE = re.compile(r"\d+\.\d+\.\d+")
BRACES = "{{"

#: The two slice-1 unverified markers' display strings (CR-37/NFR-S1). An
#: unknown marker id renders VERBATIM — forward-honest, never dropped. This
#: map is the generation-time authority; ``website/assets/plugins.js`` carries
#: a twin for cloned rows, pinned byte-equal by
#: ``tests/contract/test_website_plugins_panel.py``.
MARKER_DISPLAY: dict[str, str] = {
    "conformance-evidence-self-attested": "conformance evidence self-attested",
    "review-is-process-not-proof": "review is process, not proof",
}

#: Machine kind -> rendered tag text (CR-56: a row never renders without it).
KIND_DISPLAY: dict[str, str] = {
    "admitted-release": "admitted-release",
    "community-shared": "community-shared",
    "in-tree-fixture": "in-tree-fixture",
}

#: Maintenance state -> badge class (unknown is the muted pill).
MAINTENANCE_BADGE: dict[str, str] = {
    "maintained": "badge-success",
    "maintenance_only": "badge-warning",
    "unmaintained": "badge-danger",
    "unknown": "badge-version",
}

# The registry repository of record (the evidence link's host). The row
# carries no source-repository URL (the frozen index format has no such
# field), so only the registry repo — the catalogue's own home — is
# derivable; the release-directory link is the data-driven one.
REGISTRY_REPO_URL = "https://github.com/madeinoz67/benchweave-registry"

EMPTY_EVIDENCE = "no test evidence"
EMPTY_ADVISORIES = "no advisories"
HONEST_EMPTY = "No published releases yet"


def _esc(text: str) -> str:
    """HTML-escape a row-derived value (mirror rows are data, never markup)."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _short(hex_digest: str) -> str:
    return hex_digest[:12] + "…" if len(hex_digest) > 12 else hex_digest


def _release_dir_url(row: dict[str, Any]) -> str:
    """The versionless releases directory of the row's package.

    The exact release directory carries the version literal in its path, so
    the committed href is the versionless parent (legitimate, literal-free);
    ``website/assets/plugins.js`` upgrades the href to the exact version
    directory from the served row data at runtime.
    """
    registry_id = str(row.get("registry_id") or "")
    package_id = str(row.get("package_id") or "")
    return f"{REGISTRY_REPO_URL}/tree/main/releases/{registry_id}/{package_id}"


def _evidence_html(row: dict[str, Any]) -> str:
    entries = row.get("evidence") or []
    parts: list[str] = []
    for entry in entries:
        level = _esc(str(entry.get("level") or "unknown"))
        result = _esc(str(entry.get("result") or "unknown"))
        tone = "badge-success" if result == "passed" else "badge-danger"
        if result == "partial":
            tone = "badge-warning"
        parts.append(f'<span class="badge {tone}">{level} · {result}</span>')
        path = entry.get("report_path")
        if path:
            parts.append(f"<code>{_esc(str(path))}</code>")
    if not parts:
        parts.append(f'<span class="text-muted">{EMPTY_EVIDENCE}</span>')
    parts.append(
        f'<a class="spec-link" data-bw-slot="evidence-link" '
        f'href="{_esc(_release_dir_url(row))}">release files →</a>'
    )
    return " ".join(parts)


def _advisories_html(row: dict[str, Any]) -> str:
    advisories = row.get("advisories") or []
    if not advisories:
        return f'<span class="text-muted">{EMPTY_ADVISORIES}</span>'
    return " ".join(
        f'<span class="badge badge-danger">{_esc(str(item))}</span>' for item in advisories
    )


def _markers_html(row: dict[str, Any]) -> str:
    markers = row.get("unverified_markers") or []
    return " ".join(
        f'<span class="badge badge-warning">{_esc(MARKER_DISPLAY.get(str(m), str(m)))}</span>'
        for m in markers
    )


def _card(row: dict[str, Any], *, blank: bool = False) -> str:
    """One catalogue card. ``blank`` renders the hidden template card: the
    same shape with every slot empty, cloned by the page's JS for rows the
    static block does not carry (so one shape source — this renderer —
    serves both the committed and the on-demand cards)."""
    kind = str(row.get("kind") or "")
    if not blank and kind not in KIND_DISPLAY:
        raise SystemExit(f"panel_input_invalid: unknown kind {kind!r} in mirror row")
    values: dict[str, str] = {
        "display-name": "" if blank else str(row.get("display_name") or ""),
        "summary": "" if blank else str(row.get("summary") or ""),
        "publisher": "" if blank else str(row.get("publisher") or ""),
        "licence": "" if blank else str(row.get("licence_spdx") or ""),
        "release-id": ""
        if blank
        else f"{row.get('registry_id') or ''}/{row.get('package_id') or ''}",
        "source-revision": "" if blank else str(row.get("source_revision") or ""),
    }
    maintenance = "" if blank else str(row.get("maintenance") or "unknown")
    badge = MAINTENANCE_BADGE.get(maintenance, "badge-version")
    kind_text = "" if blank else KIND_DISPLAY[kind]
    summary = _esc(values["summary"])
    source = values["source-revision"]
    source_title = "" if blank else f' title="{_esc(source)}"'
    source_text = "" if blank else _short(source)
    attrs = "" if blank else f' data-bw-package-id="{_esc(str(row.get("package_id") or ""))}"'
    evidence = "" if blank else _evidence_html(row)
    advisories = "" if blank else _advisories_html(row)
    markers = "" if blank else _markers_html(row)
    head = (
        '<div class="spec-head">'
        f'<h4 data-bw-slot="display-name">{_esc(values["display-name"])}</h4>'
        '<span class="badge badge-version" data-bw-slot="version" hidden></span>'
        "</div>"
    )
    meta_identity = (
        '<p class="catalogue-meta">'
        f'<span data-bw-slot="publisher">{_esc(values["publisher"])}</span> · '
        f'<span data-bw-slot="licence">{_esc(values["licence"])}</span> · '
        f'<span class="badge {badge}" data-bw-slot="maintenance">{_esc(maintenance)}</span> · '
        f'<span class="badge badge-info" data-bw-slot="kind">{_esc(kind_text)}</span>'
        "</p>"
    )
    meta_release = (
        '<p class="catalogue-meta">'
        f'<span class="mono" data-bw-slot="release-id">{_esc(values["release-id"])}</span> · '
        '<span class="mono" data-bw-slot="digest" hidden></span>'
        "</p>"
    )
    meta_source = (
        '<p class="catalogue-meta">source: '
        f'<span class="mono" data-bw-slot="source-revision"{source_title}>'
        f"{_esc(source_text)}</span></p>"
    )
    return "\n".join(
        [
            f'<div class="spec-card"{attrs}',
            head,
            f'<p data-bw-slot="summary">{summary}</p>',
            meta_identity,
            meta_release,
            '<p class="catalogue-meta" data-bw-slot="compat" hidden></p>',
            f'<p class="catalogue-meta">evidence: {evidence}</p>',
            f'<p class="catalogue-meta">advisories: {advisories}</p>',
            f'<p class="catalogue-meta">unverified: {markers}</p>',
            meta_source,
            "</div>",
        ]
    )


def _default_row(row: dict[str, Any]) -> bool:
    return row.get("kind") == "admitted-release" and row.get("signature_state") == "signed-valid"


def render_panel_rows(mirror_bytes: bytes) -> str:
    """The block content for the given mirror bytes (pure; no filesystem).

    Fail-closed: an unparseable mirror or a row whose ``kind`` the
    catalogue does not know refuses (``panel_input_invalid:``) — the block
    can never exist in a silently-degraded state. Output carrying a
    three-component version literal or a ``{{`` delimiter refuses
    (``panel_literal_refused:`` / ``panel_braces_refused:``): the class-11
    ban holds at generation time, not only at test time.
    """
    try:
        document = json.loads(mirror_bytes)
    except (ValueError, UnicodeDecodeError) as exc:
        raise SystemExit(f"panel_input_invalid: mirror is not parseable JSON ({exc})") from exc
    rows = document.get("rows") if isinstance(document, dict) else None
    if not isinstance(rows, list):
        raise SystemExit("panel_input_invalid: mirror carries no rows list")
    for row in rows:
        if not isinstance(row, dict):
            raise SystemExit("panel_input_invalid: mirror row is not an object")
        kind = row.get("kind")
        if kind not in KIND_DISPLAY:
            raise SystemExit(f"panel_input_invalid: unknown kind {kind!r} in mirror row")

    defaults = [row for row in rows if _default_row(row)]
    parts = [f'<template data-bw-template>\n{_card({}, blank=True)}\n</template>']
    for row in defaults:
        parts.append(_card(row))
    if not defaults:
        parts.append(f'<p class="catalogue-empty-static">{HONEST_EMPTY}</p>')
    block = "\n".join(parts)

    literals = SEMVER_RE.findall(block)
    if literals:
        raise SystemExit(
            "panel_literal_refused: the generated block carries three-component "
            f"version literal(s) {sorted(set(literals))} — class-11 surfaces render "
            "versions from the index at runtime, never as committed literals"
        )
    if BRACES in block:
        raise SystemExit(
            "panel_braces_refused: the generated block carries a {{ delimiter — "
            "the panel block carries no stamp tokens at all"
        )
    return block


def extract_block(html: str) -> str | None:
    """The committed block content, or None when the marker pair is not exactly once."""
    if html.count(BEGIN_MARKER) != 1 or html.count(END_MARKER) != 1:
        return None
    start = html.index(BEGIN_MARKER) + len(BEGIN_MARKER)
    end = html.index(END_MARKER)
    if end < start:
        return None
    return html[start:end]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO)
    parser.add_argument(
        "--write", action="store_true", help="rewrite the block in website/index.html"
    )
    parser.add_argument("--check", action="store_true", help="refuse drift; write nothing")
    args = parser.parse_args()
    if args.write and args.check:
        print("panel_input_invalid: --write and --check are mutually exclusive", file=sys.stderr)
        return 1
    root = args.root.resolve()
    mirror_path = root / "website" / "plugins-index.json"
    index_path = root / "website" / "index.html"
    if not mirror_path.is_file():
        print(f"panel_input_invalid: mirror missing: {mirror_path}", file=sys.stderr)
        return 1
    block = render_panel_rows(mirror_path.read_bytes())
    if not args.write and not args.check:
        print(block)
        return 0
    html = index_path.read_text(encoding="utf-8")
    current = extract_block(html)
    if current is None:
        print(
            "panel_input_invalid: website/index.html does not carry exactly one "
            "bw:plugins-panel marker pair",
            file=sys.stderr,
        )
        return 1
    if args.check:
        if current != block:
            print(
                "panel_drift: the committed panel block differs from a fresh render "
                "of the committed mirror (hand-edited panel row or hand-edited mirror "
                "row — regenerate with --write, never hand-edit)",
                file=sys.stderr,
            )
            return 1
        print("panel block is current")
        return 0
    updated = html.replace(BEGIN_MARKER + current + END_MARKER, BEGIN_MARKER + block + END_MARKER)
    index_path.write_text(updated, encoding="utf-8")
    print(f"panel block rewritten ({block.count('spec-card')} card(s) incl. template)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
