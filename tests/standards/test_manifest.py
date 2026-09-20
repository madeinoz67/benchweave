"""The standards manifest is complete, consistent and hash-verified."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from benchweave.standards.manifest import (
    StandardEntry,
    StandardsError,
    StandardsManifest,
    load_identity,
    load_manifest,
    validate_identity,
    validate_manifest,
)

ROOT = Path(__file__).resolve().parents[2]
DESCRIPTOR_SCHEMA_NAME = "otdp-device-descriptor.schema.json"


def test_manifest_loads_all_six_standards() -> None:
    manifest = load_manifest(ROOT)
    assert {entry.id for entry in manifest.standards} == {
        "otdp",
        "registry",
        "execution",
        "interface",
        "plugin-ui",
        "plugin-ui-preview",
    }


def test_interface_reset_has_no_supersession() -> None:
    entry = next(e for e in load_manifest(ROOT).standards if e.id == "interface")
    assert entry.version == "0.1.0" and entry.supersedes is None


def test_validation_passes_on_the_canonical_corpus() -> None:
    validate_manifest(load_manifest(ROOT), ROOT)


def test_load_manifest_rejects_duplicate_standard_ids(tmp_path: Path) -> None:
    # Authority selection was list-order first-match and duplicate-tolerant: a
    # second otdp entry (even a deprecated one) made every downstream
    # derivation consult whichever copy came first, regardless of status.
    document = json.loads((ROOT / "standards/standards-manifest.json").read_bytes())
    entry = next(e for e in document["standards"] if e["id"] == "otdp")
    superseded = dict(entry)
    superseded["status"] = "deprecated"
    document["standards"] = [superseded, {**entry, "version": "0.2.0"}]
    (tmp_path / "standards").mkdir()
    (tmp_path / "standards/standards-manifest.json").write_text(json.dumps(document))
    with pytest.raises(StandardsError, match="standards_entry_duplicate"):
        load_manifest(tmp_path)


ANNOTATION_KEYS = ("title", "description")


def _annotation_offenders(standards_root: Path) -> list[str]:
    """Reset residue in vendored schema annotations, both keys the corpus
    carries (#47's title rule, extended to description per #97).

    Scope: each schema DOCUMENT ROOT's title/description only — nested
    property-level annotations are not walked (inherited from #47's shape;
    currently zero divergence between root-only and recursive counts on
    the active set).

    A human-readable annotation may name its standard's version (the
    2026-09-16 reset line) or omit it; naming a different one is reset
    residue — the corpus shipped "…datasets 0.3.0" under otdp@0.1.0 (#45).
    """

    version_like = re.compile(r"\d+\.\d+\.\d+")
    offenders: list[str] = []
    for entry in load_manifest(standards_root).standards:
        for relative in entry.normative:
            if not relative.startswith("standards/") or not relative.endswith(".schema.json"):
                continue
            document = json.loads((standards_root / relative).read_bytes())
            for key in ANNOTATION_KEYS:
                value = document.get(key)
                if not isinstance(value, str):
                    continue
                stale = [v for v in version_like.findall(value) if v != entry.version]
                if stale:
                    offenders.append(
                        f"{relative} ({key}): {stale} under {entry.id}@{entry.version}"
                    )
    return offenders


def test_vendored_schema_titles_match_standard_version() -> None:
    assert not _annotation_offenders(ROOT), (
        "reset residue in vendored schema annotations:\n"
        + "\n".join(_annotation_offenders(ROOT))
    )


def _planted_tree(tmp_path: Path, schema: dict[str, object]) -> Path:
    """A minimal repo-shaped tree: the manifest's normative paths are
    ROOT-relative ("standards/..."), so the returned root is the standards
    directory's PARENT — the same shape `_annotation_offenders(ROOT)` sees."""

    (tmp_path / "standards" / "demo" / "0.1.0").mkdir(parents=True)
    (tmp_path / "standards" / "demo" / "0.1.0" / "demo.schema.json").write_text(
        json.dumps(schema), encoding="utf-8"
    )
    (tmp_path / "standards" / "standards-manifest.json").write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "standards": [
                    {
                        "id": "demo",
                        "version": "0.1.0",
                        "status": "stable",
                        "released": "2026-09-20",
                        "normative": ["standards/demo/0.1.0/demo.schema.json"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_stale_description_is_refused(tmp_path: Path) -> None:
    # The #97 extension's RED-honesty arm: the pre-change guard read titles
    # only, so a stale DESCRIPTION under a clean title sailed through.
    standards = _planted_tree(
        tmp_path,
        {"title": "Demo schema", "description": "Demo datasets 0.9.9 contract"},
    )
    offenders = _annotation_offenders(standards)
    assert any("(description)" in line and "0.9.9" in line for line in offenders), offenders


def test_versionless_annotations_pass(tmp_path: Path) -> None:
    # The #47 rule's other half, on both keys: no version at all is fine.
    standards = _planted_tree(
        tmp_path, {"title": "Demo schema", "description": "No version mentioned"}
    )
    assert _annotation_offenders(standards) == []


def test_missing_normative_file_fails(tmp_path: Path) -> None:
    manifest = load_manifest(ROOT)
    (tmp_path / "standards").mkdir()
    with pytest.raises(StandardsError, match="missing_normative_file"):
        validate_manifest(manifest, tmp_path)


def test_hash_drift_against_corpus_manifest_fails(tmp_path: Path) -> None:
    # A standards/ normative file whose bytes disagree with standards/corpus-manifest.json.
    # Copy the real file in and corrupt only its pin, so the failure is the
    # disagreement — absence is the previous test's job.
    documents = json.loads((ROOT / "standards/corpus-manifest.json").read_bytes())
    first = load_manifest(ROOT).standards[0].normative[0]
    row = next(r for r in documents["files"] if r["path"] == first.removeprefix("standards/"))
    row["sha256"] = "0" * 64
    (tmp_path / first).parent.mkdir(parents=True)
    shutil.copyfile(ROOT / first, tmp_path / first)
    (tmp_path / "standards/corpus-manifest.json").write_text(json.dumps(documents))
    with pytest.raises(StandardsError, match="normative_hash_mismatch"):
        validate_manifest(load_manifest(ROOT), tmp_path)


def _active_descriptor_relative() -> str:
    return next(
        relative
        for entry in load_manifest(ROOT).standards
        if entry.id == "otdp"
        for relative in entry.normative
        if Path(relative).name == DESCRIPTOR_SCHEMA_NAME
    )


def _identity_root(tmp_path: Path, *, adapter_api: str | None = "1.1") -> Path:
    """A tmp corpus root staging only what validate_identity reads.

    The canonical tree is never mutated; the descriptor schema is copied in and
    only the identity block is edited.
    """
    descriptor = _active_descriptor_relative()
    (tmp_path / descriptor).parent.mkdir(parents=True)
    shutil.copyfile(ROOT / descriptor, tmp_path / descriptor)
    document = json.loads((ROOT / "standards/corpus-manifest.json").read_bytes())
    if adapter_api is None:
        document["identity"].pop("adapter_api", None)
    else:
        document["identity"]["adapter_api"] = adapter_api
    (tmp_path / "standards").mkdir(exist_ok=True)
    (tmp_path / "standards/corpus-manifest.json").write_text(json.dumps(document))
    return tmp_path


def test_identity_declares_the_active_adapter_api() -> None:
    assert load_identity(ROOT)["adapter_api"] == "1.1"


def test_validate_identity_accepts_the_canonical_corpus() -> None:
    validate_identity(load_manifest(ROOT), ROOT)


def test_descriptor_schema_otdp_const_matches_manifest_version() -> None:
    """The two version-authority heads are pinned together (#63, F2).

    The active descriptor schema's ``otdp_version`` const and the standards
    manifest's otdp entry version independently declare "the active
    corpus"; a bump that moves the version directory and the manifest but
    forgets the const would leave the schema silently enforcing the OLD
    corpus against every admitted descriptor — exactly the dps150
    condition before its re-version. (Discrimination proven by
    scratch-mutating one side: const -> 9.9.9 fails this test, restored
    byte-identical after.)"""
    schema = json.loads((ROOT / _active_descriptor_relative()).read_bytes())
    manifest_version = next(
        entry.version for entry in load_manifest(ROOT).standards if entry.id == "otdp"
    )
    assert schema["properties"]["otdp_version"]["const"] == manifest_version


def test_load_identity_fails_closed_without_an_identity_block(tmp_path: Path) -> None:
    (tmp_path / "standards").mkdir()
    (tmp_path / "standards/corpus-manifest.json").write_text(json.dumps({"files": []}))
    with pytest.raises(StandardsError, match="identity_block_invalid"):
        load_identity(tmp_path)


def test_identity_adapter_api_absent_fails(tmp_path: Path) -> None:
    root = _identity_root(tmp_path, adapter_api=None)
    with pytest.raises(StandardsError, match="identity_adapter_api_absent"):
        validate_identity(load_manifest(ROOT), root)


def test_identity_adapter_api_mismatch_fails(tmp_path: Path) -> None:
    root = _identity_root(tmp_path, adapter_api="1.0")
    with pytest.raises(StandardsError, match="identity_adapter_api_mismatch"):
        validate_identity(load_manifest(ROOT), root)


def test_identity_fails_when_the_const_is_absent_from_the_descriptor_schema(
    tmp_path: Path,
) -> None:
    root = _identity_root(tmp_path)
    descriptor = _active_descriptor_relative()
    schema = json.loads((root / descriptor).read_bytes())
    del schema["$defs"]["adapter"]["properties"]["api_version"]["const"]
    (root / descriptor).write_text(json.dumps(schema))
    with pytest.raises(StandardsError, match="identity_adapter_api_mismatch"):
        validate_identity(load_manifest(ROOT), root)


def _set_identity_value(root: Path, key: str, value: str | None) -> None:
    path = root / "standards/corpus-manifest.json"
    document = json.loads(path.read_bytes())
    if value is None:
        document["identity"].pop(key, None)
    else:
        document["identity"][key] = value
    path.write_text(json.dumps(document))


def test_identity_standard_version_mismatch_fails(tmp_path: Path) -> None:
    # identity.otdp stale vs its standards-manifest entry: the block misreports
    # the corpus while every existing gate stays green unless derived.
    root = _identity_root(tmp_path)
    _set_identity_value(root, "otdp", "0.1.0")
    with pytest.raises(StandardsError, match="identity_standard_mismatch"):
        validate_identity(load_manifest(ROOT), root)


def test_identity_standard_key_absent_fails(tmp_path: Path) -> None:
    root = _identity_root(tmp_path)
    _set_identity_value(root, "registry", None)
    with pytest.raises(StandardsError, match="identity_standard_absent"):
        validate_identity(load_manifest(ROOT), root)


def test_identity_unknown_key_fails(tmp_path: Path) -> None:
    # Fabricated keys (telemetry, otdp-ui, ...) sailed through while the
    # docstring claimed the block may not declare what the manifest does not
    # carry; the block is closed-world and a new key is a governance event.
    root = _identity_root(tmp_path)
    _set_identity_value(root, "telemetry", "0.1.0")
    with pytest.raises(StandardsError, match="identity_key_unknown"):
        validate_identity(load_manifest(ROOT), root)


def test_identity_standard_declared_without_manifest_entry_fails(tmp_path: Path) -> None:
    root = _identity_root(tmp_path)
    _set_identity_value(root, "execution", "9.9.9")
    manifest = StandardsManifest(
        tuple(e for e in load_manifest(ROOT).standards if e.id != "execution")
    )
    with pytest.raises(StandardsError, match="identity_standard_mismatch"):
        validate_identity(manifest, root)


def test_identity_fails_when_the_descriptor_is_not_in_the_normative_list(
    tmp_path: Path,
) -> None:
    root = _identity_root(tmp_path)
    entry = next(e for e in load_manifest(ROOT).standards if e.id == "otdp")
    without = StandardEntry(
        id=entry.id,
        version=entry.version,
        status=entry.status,
        released=entry.released,
        supersedes=entry.supersedes,
        normative=tuple(
            p for p in entry.normative if Path(p).name != DESCRIPTOR_SCHEMA_NAME
        ),
    )
    with pytest.raises(StandardsError, match="identity_otdp_descriptor_missing"):
        validate_identity(StandardsManifest((without,)), root)
