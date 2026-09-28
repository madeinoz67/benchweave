"""The zero-literal end state: the gate, its register, and the derivations.

Issue #221 (#203 slice 7, design record committed beside this tree): every
executable version literal in the gateway source tree is either DERIVED from
its machine authority (the vendored manifest, the validating schema's own
const) or REGISTERED with a reason and an expected site count — and the
committed counter refuses anything else (SM-2 = 0 outside the register).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchweave.standards.manifest import StandardsError, active_version_from_corpus
from benchweave.vendoring import active_contract_family, contract_family, corpus_root

ROOT = Path(__file__).resolve().parents[2]


def _scratch_corpus(tmp_path: Path, document: dict[str, object]) -> Path:
    """A minimal corpus directory carrying one manifest."""
    corpus = tmp_path / "standards"
    corpus.mkdir()
    (corpus / "standards-manifest.json").write_text(json.dumps(document))
    return corpus


def _minimal_manifest() -> dict[str, object]:
    return {
        "manifest_version": 1,
        "identity": {},
        "standards": [
            {"id": "otdp", "version": "0.2.2"},
            {"id": "execution", "version": "0.2.0"},
        ],
    }


class TestActiveVersionFromCorpus:
    """The fourth corpus-shaped twin loader (design §1.1)."""

    def test_happy_path_over_the_real_corpus(self) -> None:
        """The committed manifest's active entries, read back per id."""
        corpus = ROOT / "standards"
        assert active_version_from_corpus(corpus, "otdp") == "0.2.2"
        assert active_version_from_corpus(corpus, "registry") == "0.1.1"
        assert active_version_from_corpus(corpus, "execution") == "0.2.0"
        assert active_version_from_corpus(corpus, "interface") == "0.1.0"
        assert active_version_from_corpus(corpus, "plugin-ui") == "0.2.0"
        assert active_version_from_corpus(corpus, "plugin-ui-preview") == "0.1.1"

    def test_entry_absent_refuses_loudly(self, tmp_path: Path) -> None:
        """A manifest without the requested id is corruption (a countable
        manifest always carries all six) — refused, never defaulted."""
        corpus = _scratch_corpus(tmp_path, _minimal_manifest())
        with pytest.raises(StandardsError, match="standards_entry_absent: interface"):
            active_version_from_corpus(corpus, "interface")

    def test_non_semver_active_version_refuses(self, tmp_path: Path) -> None:
        """The same ACTIVE_VERSION_PATTERN guard declared_dev_head applies:
        a -dev suffix on the ACTIVE entry refuses before any derivation."""
        document = _minimal_manifest()
        document["standards"] = [{"id": "execution", "version": "0.3.0-dev"}]
        corpus = _scratch_corpus(tmp_path, document)
        with pytest.raises(StandardsError, match="standards_entry_version_invalid"):
            active_version_from_corpus(corpus, "execution")

    def test_unsupported_manifest_version_refuses(self, tmp_path: Path) -> None:
        document = _minimal_manifest()
        document["manifest_version"] = 99
        corpus = _scratch_corpus(tmp_path, document)
        with pytest.raises(StandardsError, match="standards_manifest_version_unsupported"):
            active_version_from_corpus(corpus, "execution")


class TestVendoringHelpers:
    """``corpus_root`` + ``active_contract_family`` (design §1.1)."""

    def test_corpus_root_is_the_repo_standards_tree_in_a_checkout(self) -> None:
        root = corpus_root()
        assert root.is_dir()
        assert (root / "standards-manifest.json").is_file()

    def test_active_contract_family_matches_the_literal_family(self) -> None:
        """Same value as the literal call each site makes today — the
        derivation is byte-identical in behavior wherever the literal
        validated, by construction."""
        assert active_contract_family("execution") == contract_family("execution/0.2.0")
        assert active_contract_family("interface") == contract_family("interface/0.1.0")
        assert active_contract_family("registry") == contract_family("registry/0.1.1")

    def test_active_contract_family_refuses_an_unknown_standard(self) -> None:
        with pytest.raises(StandardsError, match="standards_entry_absent: nosuch"):
            active_contract_family("nosuch")
