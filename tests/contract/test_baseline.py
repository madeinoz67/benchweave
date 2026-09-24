"""Baseline integrity of the vendored architecture contract corpus.

Proves the four properties WP01 requires of the vendored contracts: byte
hashes, duplicate keys, nonfinite values, schema references and the source
manifest. The corpus under ``standards/`` is the admitted architecture contract
set; this file detects any drift, tampering or
accidental admission of obsolete schema versions.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import pytest
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "standards"


def _strict_loads(text: str) -> Any:
    def reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        raise ValueError(f"non-finite JSON number: {value}")

    return json.loads(
        text,
        object_pairs_hook=reject_pairs,
        parse_constant=reject_constant,
    )


def _load_strict(path: Path) -> Any:
    return _strict_loads(path.read_text(encoding="utf-8"))


def _manifest() -> dict[str, Any]:
    manifest = _load_strict(CONTRACTS / "corpus-manifest.json")
    assert isinstance(manifest, dict)
    return manifest


def _contract_files() -> list[Path]:
    return sorted(
        p
        for p in CONTRACTS.rglob("*.json")
        if p.name not in ("corpus-manifest.json", "standards-manifest.json")
        # Mirrors check_documents.py's exclusion (review row 2): a dev copy
        # shares the active documents' $ids and shadows them — the mirror
        # must not condemn released files for a head's edits either.
        and not any(part.endswith("-dev") for part in p.relative_to(CONTRACTS).parts)
    )


def _all_corpus_json_files() -> list[Path]:
    """Every machine file the corpus manifest may pin, heads included.

    The listing/hash pair owns file-level coverage for the WHOLE corpus: a
    dev head's files are pinned exactly like active ones (repin's coverage
    is dev-inclusive both directions), so the listing test compares the
    full row set against the full disk walk. ``_contract_files`` keeps the
    -dev exclusion for the content tests a dev copy's $id shadowing would
    otherwise condemn released files in.
    """
    return sorted(
        p
        for p in CONTRACTS.rglob("*.json")
        if p.name not in ("corpus-manifest.json", "standards-manifest.json")
    )


def _walk(value: Any, base: str) -> list[tuple[Any, str]]:
    nodes: list[tuple[Any, str]] = []
    if isinstance(value, dict):
        if "$id" in value and isinstance(value["$id"], str):
            base = urljoin(base, value["$id"])
        nodes.append((value, base))
        for child in value.values():
            nodes.extend(_walk(child, base))
    elif isinstance(value, list):
        for child in value:
            nodes.extend(_walk(child, base))
    return nodes


def test_manifest_lists_every_contract_file() -> None:
    listed = {entry["path"] for entry in _manifest()["files"]}
    # as_posix(): the manifest records forward-slash paths on every OS.
    actual = {p.relative_to(CONTRACTS).as_posix() for p in _all_corpus_json_files()}
    assert listed == actual, f"manifest drift: missing={actual - listed} extra={listed - actual}"


def test_manifest_hashes_match_contract_files() -> None:
    for entry in _manifest()["files"]:
        path = CONTRACTS / entry["path"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == entry["sha256"], f"hash mismatch: {entry['path']}"


def test_no_obsolete_interface_version_present() -> None:
    assert not (CONTRACTS / "interface" / "1.0.0").exists(), "obsolete interface 1.0.0 imported"
    for entry in _manifest()["files"]:
        assert not entry["path"].startswith("interface/1.0.0/")


def test_manifest_identity_pins_admitted_versions() -> None:
    identity = _manifest()["identity"]
    assert identity["architecture"] == "STG 1.5"
    assert identity["interface"] == "0.1.0"
    assert identity["registry"] == "0.1.1"
    assert identity["execution"] == "0.1.0"
    assert identity["otdp"] == "0.2.2"
    assert identity["mcp"] == "2026-07-28"


def test_contract_documents_are_strict_json() -> None:
    for path in _contract_files():
        _load_strict(path)


def test_schema_references_resolve_within_corpus() -> None:
    """Mirrors scripts/architecture/check_documents.py's resolution semantics.

    Root documents follow its conventions: mcp-tools.json validates each tool
    schema as an independent document; operation-catalog.json splices in the
    shared interface.schema.json $defs; every other file is its own root.
    """
    registry = Registry()
    documents: dict[Path, Any] = {p: _load_strict(p) for p in _contract_files()}
    for path, data in documents.items():
        registry = registry.with_resource(
            path.as_uri(),
            Resource.from_contents(data, default_specification=DRAFT202012),
        )
        for node, base in _walk(data, path.as_uri()):
            if "$id" in node:
                registry = registry.with_resource(
                    base,
                    Resource.from_contents(node, default_specification=DRAFT202012),
                )
    unresolved: list[str] = []
    for path, data in documents.items():
        if path.name == "mcp-tools.json":
            roots = [
                (f"{path.as_uri()}?tool={index}&direction={direction}", tool[direction])
                for index, tool in enumerate(data["tools"])
                for direction in ("inputSchema", "outputSchema")
            ]
        elif path.name == "operation-catalog.json":
            shared = documents[path.parent / "interface.schema.json"]
            roots = [(path.as_uri(), {**data, "$defs": shared["$defs"]})]
        else:
            roots = [(path.as_uri(), data)]
        for base_uri, root in roots:
            scoped = registry.with_resource(
                base_uri, Resource.from_contents(root, default_specification=DRAFT202012)
            )
            for node, base in _walk(root, base_uri):
                ref = node.get("$ref") if isinstance(node, dict) else None
                if not isinstance(ref, str):
                    continue
                try:
                    scoped.resolver(base).lookup(ref)
                except Unresolvable:
                    unresolved.append(f"{path.relative_to(CONTRACTS).as_posix()} -> {ref}")
    assert not unresolved, f"unresolvable $refs: {unresolved}"


def test_manifest_tamper_is_detected() -> None:
    """A single flipped byte anywhere in the corpus must fail hash verification."""
    target = _contract_files()[0]
    original = target.read_bytes()
    try:
        target.write_bytes(original[:-1] + bytes([original[-1] ^ 0x01]))
        with pytest.raises(AssertionError, match="hash mismatch"):
            test_manifest_hashes_match_contract_files()
    finally:
        target.write_bytes(original)


# --- #78: the corpus dir closed world is derived, never hand-listed ------------


def _standards_manifest() -> dict[str, Any]:
    manifest = _load_strict(CONTRACTS / "standards-manifest.json")
    assert isinstance(manifest, dict)
    return manifest


def _version_dir(relative: str) -> str:
    """The ``<family>/<version>`` dir a corpus path or source lives in."""
    return "/".join(relative.split("/")[:2])


def _derived_corpus_dirs(
    standards_manifest: dict[str, Any], corpus_rows: list[dict[str, Any]]
) -> set[str]:
    """The closed world of corpus version-dirs, derived (never hand-listed).

    Active: version-dirs of the standards manifest's normative paths that
    live under ``standards/`` (normative paths elsewhere — e.g. a
    presentation package's ``src/`` tree — are not corpus dirs), plus the
    version-dirs of any manifest-declared dev head's normative paths. Retained:
    the transitive closure of corpus-manifest ``source`` chains while they
    stay under ``standards/`` — the copy-never-move lineage GOVERNANCE
    requires every bump to cite. A source naming a ``standards/`` path with
    no matching row still contributes its dir (the chain gap then fires in
    the derived-actual direction). What this derivation does not catch:
    file-vs-manifest drift inside a dir (the manifest-listing and hash
    tests own that; this owns dir-level justification only); a cyclic
    source chain (a→b→a self-justifies both dirs — the visited set
    terminates the traversal, but termination is not origination, and no
    ``docs/`` root is required); and traversal-shaped source tokens
    (``standards/a/0.1.0/../../b/0.1.0/x`` contributes its literal first
    two segments and the chain breaks cleanly at the unmatched row —
    paths are split, never opened, so there is no escape and no crash).
    """
    active: set[str] = set()
    for entry in standards_manifest["standards"]:
        paths = list(entry["normative"])
        head = entry.get("dev")
        # A manifest-declared dev head's dir is admitted by the same
        # authority as an active dir (the standards manifest) — without
        # this, every open head reads as a stray corpus dir and the guard
        # reddens accumulation branches (caught live by the devstage
        # replay; fixed with it).
        if isinstance(head, dict):
            paths.extend(head.get("normative") or [])
        for path in paths:
            if path.startswith("standards/"):
                active.add(_version_dir(path.removeprefix("standards/")))
    by_path = {str(row["path"]): row for row in corpus_rows}
    retained: set[str] = set()
    for row in corpus_rows:
        # The visited set makes a source cycle terminate (the real corpus is
        # acyclic; a synthetic or tampered cycle must not hang the guard).
        visited: set[str] = set()
        # BOTH edges seed the walk (the lineage amendment): `source` is the
        # direct producer, `lineage` the pre-dev active version a dev-stage
        # promotion names separately — the deleted staging directory cannot
        # carry the retention chain on its own.
        for edge in ("source", "lineage"):
            source = row.get(edge)
            while isinstance(source, str) and source not in visited:
                if not source.startswith("standards/"):
                    break
                visited.add(source)
                relative = source.removeprefix("standards/")
                if _version_dir(relative).split("/")[1].endswith("-dev"):
                    # A -dev segment is a historical TERMINAL (review row 3,
                    # extended to lineage identically by the governor's
                    # ruling). The promoted version's rows cite the dev
                    # directory as their producer (the resets rule: never a
                    # path that did not produce the bytes), and that
                    # directory is deleted by design at teardown — so it is
                    # exempt from the missing direction (deletion is the
                    # design, not a gap) and justifies nothing downstream
                    # (an undeclared leftover dev dir stays stray;
                    # provenance cannot launder it).
                    break
                retained.add(_version_dir(relative))
                cited = by_path.get(relative)
                if cited is None:
                    break
                source = cited.get("source")
    return active | retained


def _corpus_dir_justification(
    standards_manifest: dict[str, Any], corpus_rows: list[dict[str, Any]]
) -> tuple[list[str], list[str]]:
    """``(stray, missing)``: dirs unjustified by derivation / justified but absent."""
    derived = _derived_corpus_dirs(standards_manifest, corpus_rows)
    actual = {_version_dir(str(row["path"])) for row in corpus_rows}
    return sorted(actual - derived), sorted(derived - actual)


def test_corpus_dirs_match_derived_closed_world() -> None:
    """Every corpus version-dir is justified by derivation, both directions.

    Replaces the dead ``ADMITTED_DIRS`` hand-list, which had drifted four
    version-dirs behind the real corpus while nothing read it. The derived
    set is the active dirs (standards-manifest normative paths under
    ``standards/``) plus the retained dirs (the transitive closure of
    corpus-manifest ``source`` chains while they stay under ``standards/`` —
    the copy-never-move lineage GOVERNANCE requires every bump to cite).
    This guard does NOT catch file-vs-manifest drift inside a justified
    dir: ``test_manifest_lists_every_contract_file`` and the hash tests own
    that surface; this owns dir-level justification only.
    """
    stray, missing = _corpus_dir_justification(
        _standards_manifest(), _manifest()["files"]
    )
    assert not stray, (
        "corpus dir(s) not justified by the standards manifest or any source "
        f"chain (stray family/version): {stray}"
    )
    assert not missing, (
        "justified dir(s) missing from the corpus (copy-never-move deletion "
        f"or broken source chain): {missing}"
    )


def _sm_entry(standard_id: str, paths: list[str]) -> dict[str, Any]:
    return {"id": standard_id, "normative": paths}


def _row(path: str, source: str | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {"path": path, "sha256": "0" * 64}
    if source is not None:
        row["source"] = source
    return row


def test_derived_dir_guard_matched_control() -> None:
    """Synthetic matched corpus: active dir + one retained hop, equality."""
    manifest = {"standards": [_sm_entry("alpha", ["standards/alpha/0.2.0/a.schema.json"])]}
    rows = [
        _row("alpha/0.2.0/a.schema.json", "standards/alpha/0.1.0/a.schema.json"),
        _row("alpha/0.1.0/a.schema.json", "docs/alpha/a.schema.json"),
    ]
    stray, missing = _corpus_dir_justification(manifest, rows)
    assert stray == []
    assert missing == []


def test_derived_dir_guard_stray_dir_fires_actual_minus_derived() -> None:
    """A dir no manifest entry names and no chain retains fires stray only."""
    manifest = {"standards": [_sm_entry("alpha", ["standards/alpha/0.2.0/a.schema.json"])]}
    rows = [
        _row("alpha/0.2.0/a.schema.json", "docs/alpha/a.schema.json"),
        _row("ghost/9.9.9/a.schema.json", "docs/ghost/a.schema.json"),
    ]
    stray, missing = _corpus_dir_justification(manifest, rows)
    assert stray == ["ghost/9.9.9"]
    assert missing == []


def test_derived_dir_guard_deleted_retained_dir_fires_derived_minus_actual() -> None:
    """A citing row whose retained dir's rows were deleted fires missing only."""
    manifest = {"standards": [_sm_entry("alpha", ["standards/alpha/0.2.0/a.schema.json"])]}
    rows = [_row("alpha/0.2.0/a.schema.json", "standards/alpha/0.1.0/a.schema.json")]
    stray, missing = _corpus_dir_justification(manifest, rows)
    assert stray == []
    assert missing == ["alpha/0.1.0"]


def test_derived_dir_guard_active_version_move_keeps_equality() -> None:
    """A compliant bump (new active dir, old one retained by chain) holds."""
    manifest = {"standards": [_sm_entry("alpha", ["standards/alpha/0.3.0/a.schema.json"])]}
    rows = [
        _row("alpha/0.3.0/a.schema.json", "standards/alpha/0.2.0/a.schema.json"),
        _row("alpha/0.2.0/a.schema.json", "docs/alpha/a.schema.json"),
    ]
    stray, missing = _corpus_dir_justification(manifest, rows)
    assert stray == []
    assert missing == []


def test_derived_dir_guard_chain_gap_fires_derived_minus_actual() -> None:
    """The gap one hop beyond the citing row: closure, not one-hop matching.

    0.3.0 cites 0.2.0 (rows present) and 0.2.0 cites 0.1.0 (rows absent):
    a one-hop derivation would hold equality here; the transitive closure
    must flag 0.1.0.
    """
    manifest = {"standards": [_sm_entry("alpha", ["standards/alpha/0.3.0/a.schema.json"])]}
    rows = [
        _row("alpha/0.3.0/a.schema.json", "standards/alpha/0.2.0/a.schema.json"),
        _row("alpha/0.2.0/a.schema.json", "standards/alpha/0.1.0/a.schema.json"),
    ]
    stray, missing = _corpus_dir_justification(manifest, rows)
    assert stray == []
    assert missing == ["alpha/0.1.0"]


def test_derived_dir_guard_ignores_non_standards_normative_paths() -> None:
    """Normative paths outside standards/ contribute no corpus dir."""
    manifest = {
        "standards": [
            _sm_entry(
                "ui",
                ["standards/ui/0.2.0/a.schema.json", "src/plugin_ui/presentation.ts"],
            )
        ]
    }
    rows = [
        _row("ui/0.2.0/a.schema.json", "standards/ui/0.1.0/a.schema.json"),
        _row("ui/0.1.0/a.schema.json", "docs/ui/a.schema.json"),
    ]
    stray, missing = _corpus_dir_justification(manifest, rows)
    assert stray == []
    assert missing == []


# --- review row 3: a -dev source segment is a historical terminal -----------------


def test_promoted_rows_citing_a_dev_source_are_justified() -> None:
    """The governor's probe: a full promotion + teardown. The promoted
    version's rows cite the (deleted) dev directory as their source — the
    resets rule's "never a path that did not produce the bytes". A -dev
    source is a historical terminal: the deleted staging dir is the DESIGN
    of teardown, not a copy-never-move gap, so it must not fire missing."""
    manifest = {"standards": [_sm_entry("alpha", ["standards/alpha/0.3.0/a.schema.json"])]}
    rows = [_row("alpha/0.3.0/a.schema.json", "standards/alpha/0.2.0-dev/a.schema.json")]
    stray, missing = _corpus_dir_justification(manifest, rows)
    assert stray == []
    assert missing == []
    # Disclosed seam for the governor re-review this row is flagged for: on a
    # REAL promotion the pre-dev active version's only justifier was the
    # (deleted) dev row citing it, so the terminal walk orphans it — a
    # minimal probe carries no predecessor dir and cannot see this; whether
    # promotion keeps a lineage citation is a governance ruling, not a
    # builder improvisation.


def test_leftover_dev_dir_after_a_botched_teardown_is_stray() -> None:
    """The adversary's fourth teardown shape: the promotion happened, the
    dev block was removed, but the dev directory and its rows were left in
    the tree. The leftover must fire STRAY — a -dev source justifies nothing
    downstream, so no laundered provenance can keep an undeclared staging
    dir admitted."""
    manifest = {"standards": [_sm_entry("alpha", ["standards/alpha/0.3.0/a.schema.json"])]}
    rows = [
        _row("alpha/0.3.0/a.schema.json", "standards/alpha/0.2.0-dev/a.schema.json"),
        # the leftover: rows for a directory no block declares
        _row("alpha/0.2.0-dev/a.schema.json", "standards/alpha/0.2.1/a.schema.json"),
        _row("alpha/0.2.1/a.schema.json", "standards/alpha/0.2.0/a.schema.json"),
        _row("alpha/0.2.0/a.schema.json", "docs/alpha/a.schema.json"),
    ]
    stray, missing = _corpus_dir_justification(manifest, rows)
    assert stray == ["alpha/0.2.0-dev"], stray
    assert missing == []


# --- the lineage amendment (governor re-check ruling, 2026-09-23) ------------------


def _promotion_rows(with_lineage: bool) -> list[dict[str, Any]]:
    """The real dev-stage promotion shape: promoted rows citing the (deleted)
    dev directory as source, the pre-dev active version still retained with
    its own chain — optionally carrying the predecessor edge as lineage."""
    rows = [
        _row("alpha/0.3.0/a.schema.json", "standards/alpha/0.2.0-dev/a.schema.json"),
        _row("alpha/0.2.1/a.schema.json", "standards/alpha/0.2.0/a.schema.json"),
        _row("alpha/0.2.0/a.schema.json", "docs/alpha/a.schema.json"),
    ]
    if with_lineage:
        rows[0]["lineage"] = "standards/alpha/0.2.1/a.schema.json"
    return rows


_PROMOTION_MANIFEST = {
    "standards": [_sm_entry("alpha", ["standards/alpha/0.3.0/a.schema.json"])]
}


def test_real_promotion_with_lineage_justifies_the_predecessor() -> None:
    """The governor's contour: promoted rows cite the dev path as source AND
    the pre-dev active version's corresponding paths as lineage — the
    predecessor edge survives the teardown, walked by the same guard."""
    stray, missing = _corpus_dir_justification(_PROMOTION_MANIFEST, _promotion_rows(True))
    assert stray == []
    assert missing == []


def test_real_promotion_orphaned_predecessor_without_lineage() -> None:
    """The named control: without the lineage edge the predecessor reads
    stray — omitting the field is visible, never silent."""
    stray, missing = _corpus_dir_justification(_PROMOTION_MANIFEST, _promotion_rows(False))
    assert stray == ["alpha/0.2.1"], stray
    assert missing == []


def test_lineage_naming_a_dev_path_justifies_nothing() -> None:
    """The terminal rule applies to lineage identically: a lineage naming a
    -dev path launders no leftover — the dev edge is what source carries."""
    rows = _promotion_rows(False)
    rows[0]["lineage"] = "standards/alpha/0.2.0-dev/a.schema.json"
    rows.append(_row("alpha/0.2.0-dev/a.schema.json", "standards/alpha/0.2.1/a.schema.json"))
    stray, missing = _corpus_dir_justification(_PROMOTION_MANIFEST, rows)
    assert stray == ["alpha/0.2.0-dev"], stray
