"""The zero-literal end state: the gate, its register, and the derivations.

Issue #221 (#203 slice 7, design record committed beside this tree): every
executable version literal in the gateway source tree is either DERIVED from
its machine authority (the vendored manifest, the validating schema's own
const) or REGISTERED with a reason and an expected site count — and the
committed counter refuses anything else (SM-2 = 0 outside the register).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from benchweave.standards.manifest import (
    StandardsError,
    active_version_from_corpus,
    declared_dev_head,
)
from benchweave.vendoring import active_contract_family, contract_family, corpus_root

ROOT = Path(__file__).resolve().parents[2]


def _scratch_corpus(
    tmp_path: Path, document: dict[str, object], name: str = "standards"
) -> Path:
    """A minimal corpus directory carrying one manifest (unique `name` per
    corpus when one test builds several)."""
    corpus = tmp_path / name
    corpus.mkdir(parents=True, exist_ok=True)
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

    def test_duplicate_entries_refuse(self, tmp_path: Path) -> None:
        """Fold row 9: the corpus twins refuse duplicate ids the way
        load_manifest does — first-match-wins would let a spliced second
        entry silently override the real one. RED at the fold base: the
        import was clean and returned the FIRST entry."""
        document = _minimal_manifest()
        document["standards"] = [
            {"id": "execution", "version": "0.2.0"},
            {"id": "execution", "version": "0.1.0"},
        ]
        corpus = _scratch_corpus(tmp_path, document)
        with pytest.raises(StandardsError, match="standards_entry_duplicate: execution"):
            active_version_from_corpus(corpus, "execution")
        with pytest.raises(StandardsError, match="standards_entry_duplicate: execution"):
            declared_dev_head(corpus, "execution")

    def test_all_five_corruption_modes_refuse_as_standards_error(
        self, tmp_path: Path
    ) -> None:
        """Fold row 10: the vendoring docstring's 'loud on corruption'
        claim is machine-true — every corruption mode surfaces as a
        StandardsError with a greppable prefix. RED at the fold base for
        modes 1-2: a raw FileNotFoundError / JSONDecodeError escaped."""
        missing = tmp_path / "mode1-absent"
        missing.mkdir()
        with pytest.raises(StandardsError, match="standards_manifest_absent"):
            active_version_from_corpus(missing, "execution")

        invalid = tmp_path / "mode2-invalid-json"
        invalid.mkdir()
        (invalid / "standards-manifest.json").write_text("{not json")
        with pytest.raises(StandardsError, match="standards_manifest_invalid_json"):
            active_version_from_corpus(invalid, "execution")

        unsupported = _scratch_corpus(
            tmp_path, dict(_minimal_manifest(), manifest_version=99), name="mode3-unsupported"
        )
        with pytest.raises(StandardsError, match="standards_manifest_version_unsupported"):
            active_version_from_corpus(unsupported, "execution")

        dev_active = _scratch_corpus(
            tmp_path,
            {"manifest_version": 1, "standards": [{"id": "execution", "version": "0.3.0-dev"}]},
            name="mode5-dev-active",
        )
        with pytest.raises(StandardsError, match="standards_entry_version_invalid"):
            active_version_from_corpus(dev_active, "execution")

        with pytest.raises(StandardsError, match="standards_entry_absent"):
            active_version_from_corpus(
                _scratch_corpus(tmp_path, _minimal_manifest(), name="mode4-absent-entry"),
                "interface",
            )


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


def _counter_run(*argv: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run the REAL counter (the scratch arms below copy it and invoke the
    copy's own path — the script anchors its roots on __file__, never cwd)."""
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/standards/count_version_literals.py"), *argv],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )


def _scratch_run(scratch: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    """Run the SCRATCH COPY of the counter (its __file__ anchors its roots
    inside the scratch tree — that is the whole point of a scratch copy)."""
    return subprocess.run(
        [sys.executable, str(scratch / "scripts/standards/count_version_literals.py"), *argv],
        capture_output=True,
        text=True,
        check=False,
    )


class TestZeroModeOverRealTrees:
    """G1a's SHIP state, asserted by the committed gate (issue #221 §5)."""

    def test_every_available_scope_counts_zero_outside_the_register(self) -> None:
        result = _counter_run("--scope", "gateway,plugins,docs", "--json")
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["mode"] == "zero"
        for scope in ("gateway", "plugins", "docs"):
            report = payload["scopes"][scope]
            assert report["outside"] == 0, f"{scope}: {report['violations']}"
            assert report["ok"] is True

    def test_registered_sites_are_marked_exempt_with_the_reason(self) -> None:
        """The display never hides what the gate forgives: the registered
        file's sites carry exempt: true and the register reason."""
        result = _counter_run("--scope", "gateway", "--json")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        sites = payload["scopes"]["gateway"]["sites"]
        exempt = [row for row in sites if row["file"].endswith("presentation/contracts.py")]
        assert len(exempt) == 3
        assert all(row["exempt"] is True for row in exempt)
        assert all("D2" in row["reason"] for row in exempt)

    def test_sdk_scope_joins_when_the_tree_is_present(self) -> None:
        """The sdk scope rides the submodule (CI: recursive checkout). An
        absent tree is a refusal (sdk_tree_absent:), never a silent skip —
        asserted by the absent-scratch arm below."""
        if not (ROOT / "packages/sdk/src/benchweave_sdk").is_dir():
            pytest.skip("submodule not checked out in this environment")
        result = _counter_run("--scope", "sdk")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "sdk: 0 outside register" in result.stdout

    def test_every_scope_is_reproducible_twice_byte_identical(self) -> None:
        """The A4 discipline extended to every scope, docs included (the
        KILL arm: any two consecutive runs differing)."""
        for scope in ("gateway", "plugins", "sdk", "docs"):
            if scope == "sdk" and not (ROOT / "packages/sdk/src/benchweave_sdk").is_dir():
                continue
            first = _counter_run("--scope", scope, "--json")
            second = _counter_run("--scope", scope, "--json")
            assert first.returncode == 0, first.stdout + first.stderr
            assert first.stdout == second.stdout, f"{scope}: nondeterministic"

    def test_census_pins_the_class_set_per_scope(self) -> None:
        """Design risk 4: silent scope shrinkage fails. plugins and docs
        carry exclusion constants, so their census is pinned EXACTLY; the
        gateway/sdk scopes have no exclusions (their glob change would be a
        review-visible script edit and the plant arms catch a broken walk),
        so they pin a floor only."""
        result = _counter_run("--scope", "gateway,plugins,docs", "--json")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["scopes"]["plugins"]["scanned"] == 13, (
            "the plugins class set moved — update this pin in the same "
            "commit as the tree change (the ratchet discipline)"
        )
        assert payload["scopes"]["docs"]["scanned"] == 30, (
            "the docs class set moved — update this pin in the same commit "
            "as the tree change, or refresh the snapshot deliberately"
        )
        assert payload["scopes"]["gateway"]["scanned"] >= 93

    def test_standard_id_set_is_pinned_to_the_manifest(self) -> None:
        """Fold row 5: STANDARD_IDS must equal the manifest's entry ids — a
        seventh standard would silently narrow Pattern A's coverage. The
        in-gate pin refuses (the scratch probe below proves the refusal
        fires on a drifted manifest)."""
        manifest = json.loads(
            (ROOT / "standards" / "standards-manifest.json").read_text(encoding="utf-8")
        )
        manifest_ids = sorted(str(e["id"]) for e in manifest.get("standards", []))
        assert manifest_ids == [
            "execution",
            "interface",
            "otdp",
            "plugin-ui",
            "plugin-ui-preview",
            "registry",
        ]

    def test_a_seventh_standard_drift_refuses(self, tmp_path: Path) -> None:
        """Fold row 5's probe: a manifest with a seventh id and a planted
        literal in the new id's path-shape must REFUSE, not silently pass
        the new-id literal. RED at the fold base: the import-anchored
        counter counted nothing for ``newstd/1.0.0`` and exited 0."""
        import shutil

        scratch = tmp_path / "scratch-repo"
        (scratch / "scripts/standards").mkdir(parents=True)
        (scratch / "standards").mkdir()
        shutil.copy(
            ROOT / "scripts/standards/count_version_literals.py",
            scratch / "scripts/standards/count_version_literals.py",
        )
        manifest = json.loads(
            (ROOT / "standards" / "standards-manifest.json").read_text(encoding="utf-8")
        )
        manifest["standards"].append({"id": "newstd", "version": "1.0.0"})
        (scratch / "standards/standards-manifest.json").write_text(json.dumps(manifest))
        result = _scratch_run(scratch, "--scope", "gateway")
        assert result.returncode == 1, result.stdout + result.stderr
        assert "standard_set_drift:" in result.stderr

    def test_absent_sdk_tree_refuses_loudly_in_a_scratch_copy(self, tmp_path: Path) -> None:
        import shutil

        scratch = tmp_path / "scratch-repo"
        (scratch / "scripts/standards").mkdir(parents=True)
        (scratch / "standards").mkdir()
        shutil.copy(
            ROOT / "scripts/standards/count_version_literals.py",
            scratch / "scripts/standards/count_version_literals.py",
        )
        shutil.copy(
            ROOT / "standards/standards-manifest.json",
            scratch / "standards/standards-manifest.json",
        )
        result = _scratch_run(scratch, "--scope", "sdk")
        assert result.returncode == 1
        assert "sdk_tree_absent:" in result.stderr


class TestRegisterTeeth:
    """G2b: the register cannot become a laundering list (design risk 1)."""

    def _scratch_gateway_repo(self, tmp_path: Path) -> Path:
        import shutil

        scratch = tmp_path / "scratch-repo"
        (scratch / "scripts/standards").mkdir(parents=True)
        (scratch / "standards").mkdir()
        shutil.copy(
            ROOT / "scripts/standards/count_version_literals.py",
            scratch / "scripts/standards/count_version_literals.py",
        )
        shutil.copy(
            ROOT / "standards/standards-manifest.json",
            scratch / "standards/standards-manifest.json",
        )
        shutil.copytree(ROOT / "src/benchweave", scratch / "src/benchweave")
        return scratch

    def test_a_plant_inside_a_registered_file_fails_via_expected_sites(
        self, tmp_path: Path
    ) -> None:
        scratch = self._scratch_gateway_repo(tmp_path)
        contracts_py = scratch / "src/benchweave/presentation/contracts.py"
        contracts_py.write_bytes(contracts_py.read_bytes() + b'\n_PLANT = "9.9.9"\n')
        result = _scratch_run(scratch, "--scope", "gateway")
        assert result.returncode == 1, result.stdout + result.stderr
        assert "register expectation failed:" in result.stdout
        assert "expects 3 literals, found 4" in result.stdout


class TestDocsRatchet:
    """The docs scope's exact-content snapshot ratchet (VR-24, design §1.3;
    fold rows 3+4: subtrees are in the scan, and BOTH directions refuse)."""

    def _scratch_docs_repo(self, tmp_path: Path) -> Path:
        import shutil

        scratch = tmp_path / "scratch-repo"
        (scratch / "scripts/standards").mkdir(parents=True)
        (scratch / "standards").mkdir()
        shutil.copy(
            ROOT / "scripts/standards/count_version_literals.py",
            scratch / "scripts/standards/count_version_literals.py",
        )
        shutil.copy(
            ROOT / "standards/standards-manifest.json",
            scratch / "standards/standards-manifest.json",
        )
        shutil.copy(
            ROOT / "scripts/standards/docs-literal-baseline.json",
            scratch / "scripts/standards/docs-literal-baseline.json",
        )
        shutil.copytree(ROOT / "docs", scratch / "docs")
        return scratch

    def test_a_planted_prose_literal_fails_the_ratchet(self, tmp_path: Path) -> None:
        scratch = self._scratch_docs_repo(tmp_path)
        target = scratch / "docs/README.md"
        target.write_text(target.read_text(encoding="utf-8") + "\nNew claim 9.9.9 here.\n")
        result = _scratch_run(scratch, "--scope", "docs")
        assert result.returncode == 1, result.stdout + result.stderr
        assert "docs literal beyond snapshot" in result.stdout
        assert "9.9.9" in result.stdout

    def test_a_subtree_doc_is_inside_the_ratchet(self, tmp_path: Path) -> None:
        """Fold row 3: the scan covers docs/ SUBTREES — a planted literal in
        docs/acceptance is refused. RED at the fold base: the root-only
        glob never scanned the subtree and the plant passed."""
        scratch = self._scratch_docs_repo(tmp_path)
        target = scratch / "docs/acceptance/end-to-end-review.md"
        target.write_text(target.read_text(encoding="utf-8") + "\nPlanted claim 9.9.9.\n")
        result = _scratch_run(scratch, "--scope", "docs")
        assert result.returncode == 1, result.stdout + result.stderr
        assert "docs/acceptance/end-to-end-review.md" in result.stdout

    def test_a_removal_refuses_without_an_explicit_refresh(self, tmp_path: Path) -> None:
        """Fold row 4: the snapshot is an EXACT-content bound — shrinkage
        refuses like growth. RED at the fold base: a deletion passed
        silently ('removals only lower the count')."""
        import re

        scratch = self._scratch_docs_repo(tmp_path)
        target = scratch / "docs/README.md"
        text = target.read_text(encoding="utf-8")
        match = re.search(r"(?<![\w.])\d+\.\d+\.\d+(?!\.\d)", text)
        assert match is not None
        lines = [
            line for line in text.splitlines(keepends=True) if match.group(0) not in line
        ]
        target.write_text("".join(lines))
        clean = _scratch_run(scratch, "--scope", "docs")
        assert clean.returncode == 1, clean.stdout + clean.stderr
        assert "docs literal removed from snapshot" in clean.stdout
        # The explicit refresh is what blesses the removal:
        refreshed = _scratch_run(scratch, "--refresh-docs-baseline")
        assert refreshed.returncode == 0, refreshed.stdout + refreshed.stderr
        accepted = _scratch_run(scratch, "--scope", "docs")
        assert accepted.returncode == 0, accepted.stdout + accepted.stderr

    def test_a_census_change_refuses_in_gate(self, tmp_path: Path) -> None:
        """Fold row 4's census clause: a scanned-file count that differs
        from the snapshot's records refuses — a silently added or removed
        doc cannot slip past unrecorded."""
        scratch = self._scratch_docs_repo(tmp_path)
        (scratch / "docs/brand-new-doc.md").write_text("No versions here at all.\n")
        result = _scratch_run(scratch, "--scope", "docs")
        assert result.returncode == 1, result.stdout + result.stderr
        assert "docs census changed:" in result.stdout

    def test_ip_fragments_do_not_count_but_versions_and_widenings_do(
        self, tmp_path: Path
    ) -> None:
        """Fold row 7: the anchored matcher refuses dotted-quad fragments
        (127.0.0 inside 127.0.0.1 — the committed snapshot carried four of
        these before the regen) and accepts the cheap widenings (v-prefix,
        prerelease) and sentence-final periods."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "counter_under_test",
            ROOT / "scripts/standards/count_version_literals.py",
        )
        assert spec is not None and spec.loader is not None
        counter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(counter)
        assert counter.PATTERN_DOCS.search("127.0.0.1") is None
        assert counter.PATTERN_DOCS.search("10.0.0.138") is None
        assert counter.PATTERN_DOCS.search("server at 192.168.1.1:8080") is None
        assert counter.PATTERN_DOCS.search("active is 0.2.2.") is not None
        assert counter.PATTERN_DOCS.search("the v1.2.3 release") is not None
        assert counter.PATTERN_DOCS.search("pins 0.3.0-dev") is not None
        assert counter.PATTERN_DOCS.search("candidate 1.0.0-rc2") is not None

    def test_refresh_is_an_explicit_flag_with_a_reviewable_diff(
        self, tmp_path: Path
    ) -> None:
        scratch = self._scratch_docs_repo(tmp_path)
        target = scratch / "docs/README.md"
        target.write_text(target.read_text(encoding="utf-8") + "\nNew claim 9.9.9 here.\n")
        refused = _scratch_run(scratch, "--scope", "docs")
        assert refused.returncode == 1
        refreshed = _scratch_run(scratch, "--refresh-docs-baseline")
        assert refreshed.returncode == 0, refreshed.stdout + refreshed.stderr
        assert "docs snapshot refreshed" in refreshed.stdout
        accepted = _scratch_run(scratch, "--scope", "docs")
        assert accepted.returncode == 0, accepted.stdout + accepted.stderr


class TestScopeMembershipAndValuePins:
    """Fold rows 6+8: the plugins scope's path-shape rule and the authored-
    data registers' value pins."""

    def _scratch_plugins_repo(self, tmp_path: Path) -> Path:
        import shutil

        scratch = tmp_path / "scratch-repo"
        (scratch / "scripts/standards").mkdir(parents=True)
        (scratch / "standards").mkdir()
        shutil.copy(
            ROOT / "scripts/standards/count_version_literals.py",
            scratch / "scripts/standards/count_version_literals.py",
        )
        shutil.copy(
            ROOT / "standards/standards-manifest.json",
            scratch / "standards/standards-manifest.json",
        )
        shutil.copytree(
            ROOT / "plugins/fnirsi/dps150/src",
            scratch / "plugins/fnirsi/dps150/src",
        )
        return scratch

    def test_a_tests_src_path_shape_is_out_of_scope(self, tmp_path: Path) -> None:
        """Fold row 8: ``plugins/x/tests/src/y.py`` is a TEST tree whatever
        its layout — the any-src-component rule counted it. RED at the fold
        base: the probe file's literal was counted and the plant failed the
        gate; the path-shape rule excludes it."""
        scratch = self._scratch_plugins_repo(tmp_path)
        probe = scratch / "plugins/fnirsi/dps150/tests/src/probe_module.py"
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text('TESTFIXTURE_VERSION = "0.2.2"\n', encoding="utf-8")
        result = _scratch_run(scratch, "--scope", "plugins")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "probe_module" not in result.stdout

    def test_a_registered_value_substitution_fails_the_value_pin(
        self, tmp_path: Path
    ) -> None:
        """Fold row 6: the descriptor register pins the VALUES — a
        semantics-changing substitution (the pin declaration 0.2.2 -> 9.9.9)
        fails at unchanged cardinality. RED at the fold base: the count
        stayed 3 and the substitution passed."""
        scratch = self._scratch_plugins_repo(tmp_path)
        descriptor = scratch / "plugins/fnirsi/dps150/src/benchweave_fnirsi_dps150/descriptor.py"
        text = descriptor.read_text(encoding="utf-8")
        assert '"0.2.2"' in text
        descriptor.write_text(text.replace('"0.2.2"', '"9.9.9"', 1), encoding="utf-8")
        result = _scratch_run(scratch, "--scope", "plugins")
        assert result.returncode == 1, result.stdout + result.stderr
        assert "register value pin failed:" in result.stdout


class TestSchemaConstDerivations:
    """The two caches stamp exactly what validates (design §1.2 rows 3/9)."""

    def test_terminal_record_stamps_the_schema_const(self) -> None:
        from benchweave.control.coordinator import build_terminal_record
        from benchweave.vendoring import active_contract_family

        binding: dict[str, object] = {
            "id": "req-const-check",
            "version": "1",
            "sha256": "0" * 64,
        }
        record = build_terminal_record(
            run_id="run-const-check",
            binding_pin=binding,
            principal_id="p1",
            started_at="2026-09-29T00:00:00Z",
            ended_at="2026-09-29T00:00:00Z",
            body_outcome="completed",
            safe_state="verified",
            reasons=["zero-literal gate const check"],
            evidence_refs=[binding],
        )
        schema = json.loads(
            (active_contract_family("execution") / "run-record.schema.json").read_text(
                encoding="utf-8"
            )
        )
        const = schema["properties"]["contract_version"]["const"]
        assert record["contract_version"] == const

    def test_terminal_record_stamp_is_manifest_arbitrated(self, tmp_path: Path) -> None:
        """Fold row 2: the stamped const is judged against the MANIFEST's
        active version, not merely against the schema it was read from —
        both-ends-read-the-same-bytes is a tautology (RED: with a copied
        corpus whose const was corrupted to 9.9.9, the prior assertions
        both held). The record still follows the validating schema (design
        row 3: stamp what validates); the manifest is the independent
        arbiter that catches a swept-wrong const."""
        from benchweave.control.coordinator import build_terminal_record

        binding: dict[str, object] = {
            "id": "req-arbiter",
            "version": "1",
            "sha256": "0" * 64,
        }
        record = build_terminal_record(
            run_id="run-arbiter",
            binding_pin=binding,
            principal_id="p1",
            started_at="2026-09-29T00:00:00Z",
            ended_at="2026-09-29T00:00:00Z",
            body_outcome="completed",
            safe_state="verified",
            reasons=["arbiter arm"],
            evidence_refs=[binding],
        )
        manifest_version = active_version_from_corpus(ROOT / "standards", "execution")
        assert record["contract_version"] == manifest_version

        # The teeth, shaped for the digest-verified resolution (issue #260):
        # the realistic swept-wrong-const scenario is a corpus whose schema
        # bytes changed and whose corpus row was RE-PINNED to them — the
        # digest check passes, the stamp follows the corrupted const, and
        # the MANIFEST is the independent authority that refutes it. (The
        # pre-#260 shape — a bare tmp schema copy — now refuses
        # version_unknown:, the digest-verified mechanism working as
        # designed.)
        import hashlib

        corrupt_corpus = tmp_path / "standards"
        shutil.copytree(ROOT / "standards", corrupt_corpus)
        corrupt_schema_path = corrupt_corpus / "execution/0.2.0/run-record.schema.json"
        schema = json.loads(corrupt_schema_path.read_text(encoding="utf-8"))
        schema["properties"]["contract_version"]["const"] = "9.9.9"
        corrupt_schema_path.write_text(json.dumps(schema, indent=2))
        manifest_path = corrupt_corpus / "corpus-manifest.json"
        manifest_doc = json.loads(manifest_path.read_text(encoding="utf-8"))
        new_digest = hashlib.sha256(corrupt_schema_path.read_bytes()).hexdigest()
        re_pinned = False
        for row in manifest_doc.get("files", []):
            if str(row.get("path")) == "execution/0.2.0/run-record.schema.json":
                row["sha256"] = new_digest
                re_pinned = True
        assert re_pinned, "the corpus row the probe re-pins must exist"
        manifest_path.write_text(json.dumps(manifest_doc, indent=2))
        corrupted_record = build_terminal_record(
            run_id="run-arbiter-2",
            binding_pin=binding,
            principal_id="p1",
            started_at="2026-09-29T00:00:00Z",
            ended_at="2026-09-29T00:00:00Z",
            body_outcome="completed",
            safe_state="verified",
            reasons=["arbiter teeth"],
            evidence_refs=[binding],
            contracts=corrupt_corpus / "execution/0.2.0",
        )
        # The stamp follows the validating schema (row 3's rule)...
        assert corrupted_record["contract_version"] == "9.9.9"
        # ...and the manifest REFUTES it — this assertion is the arbiter
        # that the pre-fold test lacked.
        assert corrupted_record["contract_version"] != manifest_version

    def test_lock_version_equals_the_schema_const(self) -> None:
        from benchweave.registry.schemas import lock_version
        from benchweave.vendoring import active_contract_family

        schema = json.loads(
            (active_contract_family("registry") / "package-lock.schema.json").read_text(
                encoding="utf-8"
            )
        )
        assert lock_version() == schema["properties"]["lock_version"]["const"]

    def test_derived_interface_version_names_the_active_family(self) -> None:
        from benchweave.interfaces.validation import VENDORED_INTERFACE_VERSION
        from benchweave.vendoring import active_contract_family

        assert active_contract_family("interface").name == VENDORED_INTERFACE_VERSION


class TestRegisteredDisposition:
    """G3a's four facts, asserted (design §5; the byte-identity of the two
    contracts.py copies stays pinned by tests/sdk/test_presentation_packaging.py
    — cited there, not re-built here)."""

    def test_the_policy_note_names_the_registered_file(self) -> None:
        """Fact 2: the dependency-policy block's plugin-ui note names the
        registered file — the VR-25 branch-2 pointer is present where the
        design says it lives."""
        manifest = json.loads(
            (ROOT / "standards/standards-manifest.json").read_text(encoding="utf-8")
        )
        note = manifest["dependency_policy"]["standards"]["plugin-ui"]["note"]
        assert "src/benchweave/presentation/contracts.py" in note
        assert "D2" in note

    def test_the_register_reason_cites_the_d2_trigger(self) -> None:
        """Facts 1+4 (gateway copy): the register entry cites VR-25/D2 and
        carries the exact expectation — asserted against the counter's own
        output, so the citation cannot silently rot."""
        result = _counter_run("--scope", "gateway", "--json")
        assert result.returncode == 0
        sites = json.loads(result.stdout)["scopes"]["gateway"]["sites"]
        reasons = {row["reason"] for row in sites if row.get("exempt")}
        assert len(reasons) == 1
        reason = reasons.pop()
        assert "VR-25" in reason and "D2" in reason
        assert len([row for row in sites if row.get("exempt")]) == 3
