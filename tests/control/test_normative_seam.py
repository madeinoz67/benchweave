"""The runtime normative-row seam (issue #367, D1).

Two RUNTIME gateway sites resolve normative rows by parsing
``standards-manifest.json`` directly — the ACTIVE descriptor-schema
resolver (``documents._descriptor_validator``'s None arm, through
``_otdp_normative_path``) and the vendored provider-contract resolver
(``provider_settings.provider_contract_validator``). The sweep routes both
through the canonical load discipline's corpus-rooted resolver
(``manifest.normative_path_from_corpus``), so every structural and
row-lexicon refusal of ``load_manifest`` — the #238 boundary — is a site
refusal too, with the loader's own words.

The planted shape is #238's reachability premise at the runtime seam: a
hand-corrupted manifest row (no in-tree writer produces it) whose basename
matches on every host while its interior ``..`` resolves through the
EXISTING active directory into an open dev tree. Pre-fix the sites parsed
the row, matched the basename, stripped the ``standards/`` prefix, joined
the corpus root, and built their validators on the DEV tree's bytes —
unpinned by any check at either site (row trust, not byte trust: the
manifest is the authority both sites skipped). The arms pin that shut; the
clean-tree arm pins the other side — a clean corpus resolves unchanged, so
the discipline is not over-broad at the sites.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import benchweave.vendoring as vendoring
from benchweave.control import documents as documents_module
from benchweave.control import provider_settings as provider_settings_module
from benchweave.control.provider_settings import PROVIDER_SCHEMA_NAME
from benchweave.standards.manifest import DESCRIPTOR_SCHEMA_NAME, StandardsError

#: The planted active/dev version pair — the committed otdp pair's shape
#: (0.2.2 active, an open dev sibling), with invented bytes.
_ACTIVE = "0.2.2"
_DEV = "0.2.2-dev"


def _otdp_entry(rows: list[str]) -> dict[str, object]:
    return {
        "id": "otdp",
        "version": _ACTIVE,
        "status": "stable",
        "released": "2026-10-01",
        "normative": rows,
    }


def _corpus_root(root: Path) -> Path:
    """Write the planted manifest at the corpus root (the wheel's packaged
    layout shape: ``standards-manifest.json`` beside the version dirs)."""
    corpus = root / "standards"
    corpus.mkdir(parents=True)
    return corpus


def _write_manifest(corpus: Path, entry: dict[str, object]) -> None:
    (corpus / "standards-manifest.json").write_text(
        json.dumps({"manifest_version": 1, "standards": [entry]}), encoding="utf-8"
    )


def _traversal_tree(tmp_path: Path, document_name: str) -> Path:
    """The #238 laundering shape, planted whole: the active directory and a
    dev sibling BOTH carry ``document_name`` with different bytes, and the
    manifest's single normative row is the interior-``..`` form — basename
    match on every host, prefix strip, corpus join resolving through the
    EXISTING active directory into the dev tree."""
    root = tmp_path / "repo"
    corpus = _corpus_root(root)
    for version, marker in ((_ACTIVE, "active"), (_DEV, "dev-tree")):
        family = corpus / "otdp" / version
        family.mkdir(parents=True)
        (family / document_name).write_text(
            json.dumps({"type": "object", "properties": {"bytes": {"const": marker}}}),
            encoding="utf-8",
        )
    _write_manifest(
        corpus, _otdp_entry([f"standards/otdp/{_ACTIVE}/../{_DEV}/{document_name}"])
    )
    return root


def _clean_tree(tmp_path: Path) -> Path:
    """A clean planted corpus: canonical rows, both site documents present,
    each schema carrying a marker property — a validator built over these
    bytes is distinguishable from one over the real corpus."""
    root = tmp_path / "repo"
    corpus = _corpus_root(root)
    family = corpus / "otdp" / _ACTIVE
    family.mkdir(parents=True)
    marker = {
        "type": "object",
        "properties": {"planted_marker": {"const": "site"}},
        "required": ["planted_marker"],
        "additionalProperties": False,
    }
    for name in (DESCRIPTOR_SCHEMA_NAME, PROVIDER_SCHEMA_NAME):
        (family / name).write_text(json.dumps(marker), encoding="utf-8")
    _write_manifest(
        corpus,
        _otdp_entry(
            [
                f"standards/otdp/{_ACTIVE}/{DESCRIPTOR_SCHEMA_NAME}",
                f"standards/otdp/{_ACTIVE}/{PROVIDER_SCHEMA_NAME}",
            ]
        ),
    )
    return root


def _route_at(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The packaged-first MISS plus the planted repo root — both sites
    derive the planted corpus through ``contract_family``'s module globals
    (documents and provider_settings import the same function)."""
    packaged = root.parent / "packaged-miss"
    (packaged / "contracts").mkdir(parents=True)
    monkeypatch.setattr(vendoring, "_PACKAGED_ROOT", packaged)
    monkeypatch.setattr(vendoring, "_REPO_ROOT", root)


def test_documents_site_refuses_a_traversal_normative_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ACTIVE descriptor validator refuses the interior-``..`` row at
    the load discipline (``normative_path_escape``). RED pre-fix: the site
    parsed the manifest itself, the basename matched, the prefix strip
    fired, and the validator was BUILT on the dev tree's bytes — the
    laundering this arm pins shut (issue #367 D1; #238's premise planted
    at the runtime seam)."""
    root = _traversal_tree(tmp_path, DESCRIPTOR_SCHEMA_NAME)
    _route_at(root, monkeypatch)
    with pytest.raises(StandardsError, match="normative_path_escape"):
        documents_module._descriptor_validator()


def test_sites_resolve_a_clean_tree_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No over-broad refusal: over a CLEAN planted corpus both sites build
    validators over the planted bytes — the marker property proves the
    validators are the planted tree's, not the real corpus's (green before
    AND after the sweep; the discrimination for the refusal arms)."""
    root = _clean_tree(tmp_path)
    _route_at(root, monkeypatch)
    monkeypatch.setattr(provider_settings_module, "_VALIDATORS", {})
    descriptor = documents_module._descriptor_validator()
    assert not list(descriptor.iter_errors({"planted_marker": "site"}))
    assert list(descriptor.iter_errors({"planted_marker": "no"}))
    provider = provider_settings_module.provider_contract_validator()
    assert not list(provider.iter_errors({"planted_marker": "site"}))
    assert list(provider.iter_errors({"planted_marker": "no"}))
