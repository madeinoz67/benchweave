"""The zero-literal end state: the gate, its register, and the derivations.

Issue #221 (#203 slice 7, design record committed beside this tree): every
executable version literal in the gateway source tree is either DERIVED from
its machine authority (the vendored manifest, the validating schema's own
const) or REGISTERED with a reason and an expected site count — and the
committed counter refuses anything else (SM-2 = 0 outside the register).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from assembly_shapes import (
    BATTERY_MODULE,
    BOUNDARY_CAUGHT_MODULE,
    BOUNDARY_CAUGHT_NAMES,
    BOUNDARY_MISS_MODULE,
    BOUNDARY_MISS_NAMES,
    MISS_MODULE,
    MISS_SHAPE_NAMES,
    SHAPE_NAMES,
    shape_lines,
)

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
        assert active_version_from_corpus(corpus, "registry") == "0.1.2"
        assert active_version_from_corpus(corpus, "execution") == "0.2.0"
        assert active_version_from_corpus(corpus, "interface") == "0.1.0"
        assert active_version_from_corpus(corpus, "plugin-ui") == "0.3.0"
        assert active_version_from_corpus(corpus, "plugin-ui-preview") == "0.2.0"

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
        assert active_contract_family("registry") == contract_family("registry/0.1.2")

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
        result = _counter_run("--scope", "gateway,plugins,docs,scripts", "--json")
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["mode"] == "zero"
        for scope in ("gateway", "plugins", "docs", "scripts"):
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
        for scope in ("gateway", "plugins", "sdk", "docs", "scripts"):
            if scope == "sdk" and not (ROOT / "packages/sdk/src/benchweave_sdk").is_dir():
                continue
            first = _counter_run("--scope", scope, "--json")
            second = _counter_run("--scope", scope, "--json")
            assert first.returncode == 0, first.stdout + first.stderr
            assert first.stdout == second.stdout, f"{scope}: nondeterministic"

    def test_census_pins_the_class_set_per_scope(self) -> None:
        """Design risk 4: silent scope shrinkage fails. plugins, docs and
        scripts carry exclusion constants (scripts also self-exempts the
        counter), so their census is pinned EXACTLY; the sdk census is
        pinned too (fold wave row 1's observability half — the
        marker-truth hole was half an unobserved census). The gateway
        scope has no exclusions (its glob change would be a review-visible
        script edit and the plant arms catch a broken walk), so it pins a
        floor only."""
        scopes = "gateway,plugins,docs,scripts"
        if (ROOT / "packages/sdk/src/benchweave_sdk").is_dir():
            scopes += ",sdk"
        result = _counter_run("--scope", scopes, "--json")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["scopes"]["plugins"]["scanned"] == 15, (
            "the plugins class set moved (issue #269 widened the rule to "
            "flat plugins: 13 + the two dps150 script files) — update this "
            "pin in the same commit as the tree change (the ratchet "
            "discipline)"
        )
        assert payload["scopes"]["docs"]["scanned"] == 31, (
            "the docs class set moved — update this pin in the same commit "
            "as the tree change, or refresh the snapshot deliberately"
        )
        assert payload["scopes"]["scripts"]["scanned"] == 17, (
            "the scripts class set moved (17 .py minus the self-exempted "
            "counter) — update this pin in the same commit as the tree "
            "change (the ratchet discipline)"
        )
        if "sdk" in payload["scopes"]:
            assert payload["scopes"]["sdk"]["scanned"] == 19, (
                "the sdk class set moved — update this pin in the same "
                "commit as the submodule tree change (the ratchet "
                "discipline)"
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
        with pytest.raises(ValueError) as raised:
            build_terminal_record(
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
        # Fold row 11 (issue #260): the RUNTIME arbiter refuses the
        # swept-wrong const at the record build — the schema's const
        # disagrees with the version directory it resolved from — and the
        # MANIFEST is the independent second layer (the const the schema
        # claims cannot be the manifest's active version).
        assert "swept-wrong const" in str(raised.value), raised.value
        assert manifest_version != "9.9.9"

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


class TestScopeMembershipRules:
    """H4 (issue #269 §7): the flat-plugin rule and marker-based
    environments. RED at the rules' base: the src/-required rule could not
    see a flat plugin, and the name-set filter silently excluded a
    venv-NAMED code tree (both arms pass-as-invisible there)."""

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
        # The registered dps150 rows must hold in the scratch too — the
        # arms below isolate the membership rule, not the register.
        shutil.copytree(
            ROOT / "plugins/fnirsi/dps150/src",
            scratch / "plugins/fnirsi/dps150/src",
        )
        return scratch

    def test_plugins_census_pins_fifteen_with_the_flat_scripts_inside(self) -> None:
        """Census 13 -> 15: the two dps150 script files (zero literals in
        either) joined the denominator. The pin moves in the same commit
        as the rule (the ratchet discipline the message instructs)."""
        result = _counter_run("--scope", "plugins", "--json")
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout)["scopes"]["plugins"]["scanned"] == 15, (
            "the plugins class set moved — update this pin in the same "
            "commit as the tree change (the ratchet discipline)"
        )

    def test_a_literal_in_a_flat_plugin_refuses(self, tmp_path: Path) -> None:
        """A plugin module with NO src/ component is gated — the plant
        refuses. RED at base: the src/-required rule never scanned it."""
        scratch = self._scratch_plugins_repo(tmp_path)
        flat = scratch / "plugins/acme_instruments/mod.py"
        flat.parent.mkdir(parents=True)
        flat.write_text('_PLANT = "9.9.9"\n', encoding="utf-8")
        result = _scratch_run(scratch, "--scope", "plugins")
        assert result.returncode == 1, result.stdout + result.stderr
        assert "unregistered literal: plugins/acme_instruments/mod.py" in result.stdout

    def test_a_venv_named_directory_without_marker_is_scanned(self, tmp_path: Path) -> None:
        """A directory merely NAMED ``venv`` carries project code until it
        carries ``pyvenv.cfg`` — its literals refuse. RED at base: the
        name-set filter silently excluded the same tree (exit 0)."""
        scratch = self._scratch_plugins_repo(tmp_path)
        nested = scratch / "plugins/acme_instruments/venv/lib/mod.py"
        nested.parent.mkdir(parents=True)
        nested.write_text('_PLANT = "9.9.9"\n', encoding="utf-8")
        result = _scratch_run(scratch, "--scope", "plugins")
        assert result.returncode == 1, result.stdout + result.stderr
        assert "unregistered literal" in result.stdout
        assert "venv/lib/mod.py" in result.stdout

    def test_a_marker_carrying_environment_is_excluded(self, tmp_path: Path) -> None:
        """The same plant inside a marker-carrying directory is excluded
        and the census is unchanged (a no-regression arm: it held at base
        under the NAME rule and holds here for the MARKER's sake)."""
        scratch = self._scratch_plugins_repo(tmp_path)
        env_dir = scratch / "plugins/acme_instruments/venv"
        (env_dir / "lib").mkdir(parents=True)
        (env_dir / "bin").mkdir()
        (env_dir / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
        (env_dir / "lib/mod.py").write_text('_PLANT = "9.9.9"\n', encoding="utf-8")
        result = _scratch_run(scratch, "--scope", "plugins")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "9.9.9" not in result.stdout


class TestEnvironmentMarkerTruth:
    """Fold wave row 1 (critic Q3 + adv-lane2 M1, BREAK-class): the marker
    alone is gameable — a PLANTED pyvenv.cfg (even a directory so named)
    silently exempts a tree from every scope. Truth re-check: an
    environment directory carries the marker AND environment layout
    (``bin/`` or ``lib/python*/``); a marker without layout is code and is
    SCANNED. RED at the fold-wave base: both plant shapes exited 0."""

    def _scratch_with(self, tmp_path: Path, marker: str) -> Path:
        import shutil

        scratch = tmp_path / f"scratch-repo-{marker}"
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

    def test_a_marker_without_environment_layout_is_scanned(self, tmp_path: Path) -> None:
        """A planted bare pyvenv.cfg file beside new code does NOT exempt
        it — the tree scans and the literal refuses. RED at base: the
        marker alone exempted the tree (exit 0)."""
        scratch = self._scratch_with(tmp_path, "bare")
        planted = scratch / "plugins/acme/venvish/mod.py"
        planted.parent.mkdir(parents=True)
        planted.write_text('_PLANT = "9.9.9"\n', encoding="utf-8")
        (scratch / "plugins/acme/venvish/pyvenv.cfg").write_text("", encoding="utf-8")
        result = _scratch_run(scratch, "--scope", "plugins")
        assert result.returncode == 1, result.stdout + result.stderr
        assert "unregistered literal: plugins/acme/venvish/mod.py" in result.stdout

    def test_a_directory_named_pyvenv_cfg_is_not_a_marker(self, tmp_path: Path) -> None:
        """A DIRECTORY named pyvenv.cfg (with bin/ layout beside it) is not
        an environment — the tree scans. RED at base: .exists() is True for
        a directory, so the plant exempted the tree (exit 0)."""
        scratch = self._scratch_with(tmp_path, "dir")
        planted = scratch / "plugins/acme/venvish/mod.py"
        planted.parent.mkdir(parents=True)
        planted.write_text('_PLANT = "9.9.9"\n', encoding="utf-8")
        (scratch / "plugins/acme/venvish/pyvenv.cfg").mkdir()
        (scratch / "plugins/acme/venvish/bin").mkdir()
        result = _scratch_run(scratch, "--scope", "plugins")
        assert result.returncode == 1, result.stdout + result.stderr
        assert "unregistered literal: plugins/acme/venvish/mod.py" in result.stdout

    def test_a_real_environment_is_still_excluded(self, tmp_path: Path) -> None:
        """No-regression: marker FILE + bin/ layout (a real venv shape) is
        excluded, census unchanged. Held at base under the marker-only
        rule; holds here for marker-AND-layout."""
        scratch = self._scratch_with(tmp_path, "real")
        env_dir = scratch / "plugins/acme/venvish"
        (env_dir / "lib").mkdir(parents=True)
        (env_dir / "bin").mkdir()
        (env_dir / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
        (env_dir / "lib/mod.py").write_text('_PLANT = "9.9.9"\n', encoding="utf-8")
        result = _scratch_run(scratch, "--scope", "plugins")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "9.9.9" not in result.stdout


class TestSharedRegionParity:
    """H5 (issue #269 §4): the two counters' shared regions are
    byte-identical — the structural twin pin, extending the proven
    digest-identity shape (tests/sdk/test_presentation_packaging.py).
    Skips when the submodule is absent (the sdk scope's own condition).
    RED at base: the markers do not exist in the pinned twin — that is
    this test's RED."""

    REGION_BEGIN = "# >>> BEGIN SHARED COUNTER REGION"
    REGION_END = "# <<< END SHARED COUNTER REGION <<<"

    def _twin_path(self) -> Path:
        return ROOT / "packages/sdk/scripts/count_version_literals.py"

    def _region(self, path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        if self.REGION_BEGIN not in text or self.REGION_END not in text:
            raise AssertionError(f"shared-region markers absent from {path}")
        return text[text.index(self.REGION_BEGIN) : text.index(self.REGION_END)]

    def test_shared_regions_are_byte_identical(self) -> None:
        if not self._twin_path().is_file():
            pytest.skip("submodule not checked out in this environment")
        gateway = self._region(ROOT / "scripts/standards/count_version_literals.py")
        twin = self._region(self._twin_path())
        assert (
            hashlib.sha256(gateway.encode("utf-8")).hexdigest()
            == hashlib.sha256(twin.encode("utf-8")).hexdigest()
        ), (
            "the shared counter regions drifted — the twin's definition "
            "block must be byte-identical to the gateway's (issue #269 §4); "
            "re-sync the twin in the same work (obligation 22)"
        )

    def test_a_one_character_region_mutation_is_detected(self, tmp_path: Path) -> None:
        """The pin's teeth: one character changed inside the twin's region
        changes the digest — the parity check cannot pass a drifted copy."""
        if not self._twin_path().is_file():
            pytest.skip("submodule not checked out in this environment")
        scratch = tmp_path / "twin-mutated.py"
        text = self._twin_path().read_text(encoding="utf-8")
        mutated = text.replace(
            'ENVIRONMENT_MARKER = "pyvenv.cfg"',
            'ENVIRONMENT_MARKER = "pyvenv.cfg"  # touched',
            1,
        )
        assert mutated != text, "the mutation arm's needle vanished from the twin"
        scratch.write_text(mutated, encoding="utf-8")
        gateway = self._region(ROOT / "scripts/standards/count_version_literals.py")
        with pytest.raises(AssertionError):
            assert gateway == self._region(scratch)

    def test_the_shared_region_defines_each_name_exactly_once(self) -> None:
        """Fold wave row 2 (three lanes corroborated): the fold-block
        header/constants/_Unfoldable were duplicated INSIDE the pinned
        region on both sides — identical duplication, so parity stayed
        green while the file defined the same names twice. Each shared
        name must appear exactly once in the region (RED at base: the
        header trio counted 2)."""
        gateway = self._region(ROOT / "scripts/standards/count_version_literals.py")
        for name in (
            "FOLD_MAX_DEPTH =",  # definitions, not usages
            "FOLD_MAX_LENGTH =",
            "class _Unfoldable",
            "def _shadowed_builtin_names",
            "def _folded_string",
            "def _stringify",
            "def _fold_expression",
            "def _fold_sites",
            "def _docstring_ids",
            "def _is_environment_dir",
            "def _outside_environment",
            "ENVIRONMENT_MARKER =",
            "ENVIRONMENT_NAMED_COMPONENTS =",
            "PATTERN_A =",
            "PATTERN_BARE =",
            "STANDARD_IDS =",
        ):
            assert gateway.count(name) == 1, (
                f"the shared region defines {name!r} "
                f"{gateway.count(name)} times — dedupe in lockstep with the twin"
            )


class TestScriptsScope:
    """H3 (issue #269 §7): the scripts ledger — three derivations, twenty
    registrations with value pins, the counter's self-exemption.

    RED at the scope's base: ``scripts`` was not a scope (unknown-scope
    refusal), the adc pins were hand-swept literals blind to a corrupted
    manifest, and the docs site pinned the retained OLD otdp family.
    """

    def _scratch_scripts_repo(self, tmp_path: Path) -> Path:
        import shutil

        scratch = tmp_path / "scratch-repo"
        shutil.copytree(
            ROOT / "scripts",
            scratch / "scripts",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        (scratch / "standards").mkdir()
        shutil.copy(
            ROOT / "standards/standards-manifest.json",
            scratch / "standards/standards-manifest.json",
        )
        return scratch

    def _scratch_control_repo(self, tmp_path: Path, mutate: str) -> Path:
        """A scratch checkout for the adc control's derivation arms: the
        control anchors REPO_ROOT on its own location, so a copied tree
        with a mutated manifest exercises the authority read."""
        import shutil

        scratch = tmp_path / f"scratch-control-{mutate}"
        (scratch / "scripts").mkdir(parents=True)
        (scratch / "standards").mkdir()
        shutil.copy(ROOT / "scripts/adc_conformance_control.py", scratch / "scripts/")
        manifest = json.loads(
            (ROOT / "standards/standards-manifest.json").read_text(encoding="utf-8")
        )
        if mutate == "zero-yanked":
            manifest["dependency_policy"]["standards"]["otdp"]["yanked"] = {}
        elif mutate == "otdp-absent":
            manifest["standards"] = [
                s for s in manifest["standards"] if s.get("id") != "otdp"
            ]
        elif mutate == "yanked-is-active":
            active = next(
                s["version"] for s in manifest["standards"] if s.get("id") == "otdp"
            )
            manifest["dependency_policy"]["standards"]["otdp"]["yanked"] = {
                active: {"reason": "fold-wave probe", "since": "2026-09-29"}
            }
        # unreadable-* variants leave the manifest intact — the arm
        # corrupts it after the copy (directory / invalid JSON).
        (scratch / "standards/standards-manifest.json").write_text(json.dumps(manifest))
        return scratch

    def test_the_scripts_ledger_holds_over_the_real_tree(self) -> None:
        """The 23 sites are accounted: 20 registered across the 7 authored
        rows holding exactly, the 3 former literals DERIVED (no site —
        textual or assembled — in the adc control or the docs site), the
        counter self-exempted (census 16, not 17)."""
        result = _counter_run("--scope", "scripts", "--json")
        assert result.returncode == 0, result.stdout + result.stderr
        report = json.loads(result.stdout)["scopes"]["scripts"]
        assert report["outside"] == 0, report["violations"]
        assert report["scanned"] == 17
        assert report["count"] == 22
        carried = {row["file"] for row in report["sites"]}
        assert carried == {
            "scripts/architecture/check_closure.py",
            "scripts/architecture/check_devices.py",
            "scripts/architecture/check_interface.py",
            "scripts/architecture/check_registry.py",
            "scripts/registry/build_fixtures.py",
            "scripts/registry/publish_dev.py",
            "scripts/registry/registry_common.py",
            "scripts/registry/sign_release.py",
            "scripts/sdk_smoke.py",
        }, carried

    def test_a_plant_in_a_registered_scripts_file_fails(self, tmp_path: Path) -> None:
        scratch = self._scratch_scripts_repo(tmp_path)
        target = scratch / "scripts/sdk_smoke.py"
        target.write_bytes(target.read_bytes() + b'\n_PLANT = "9.9.9"\n')
        result = _scratch_run(scratch, "--scope", "scripts")
        assert result.returncode == 1, result.stdout + result.stderr
        assert (
            "register expectation failed: scripts/sdk_smoke.py expects 2 literals, found 3"
            in result.stdout
        )

    def test_a_plant_in_an_unregistered_scripts_file_fails(self, tmp_path: Path) -> None:
        scratch = self._scratch_scripts_repo(tmp_path)
        target = scratch / "scripts/adc_conformance_control.py"
        target.write_bytes(target.read_bytes() + b'\n_PLANT = "9.9.9"\n')
        result = _scratch_run(scratch, "--scope", "scripts")
        assert result.returncode == 1, result.stdout + result.stderr
        assert "unregistered literal: scripts/adc_conformance_control.py" in result.stdout

    def test_a_non_unique_yank_block_refuses_the_control(self, tmp_path: Path) -> None:
        """A scratch authority with ZERO yanked entries ⇒
        ``adc_yank_not_unique:`` non-zero exit — the derivation reads the
        committed policy block, never guesses. RED at base: the hand-swept
        literals never read the manifest, so the same corrupted authority
        let the control proceed to argparse (exit 0)."""
        scratch = self._scratch_control_repo(tmp_path, "zero-yanked")
        result = subprocess.run(
            [sys.executable, str(scratch / "scripts/adc_conformance_control.py"), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0, result.stdout + result.stderr
        assert "adc_yank_not_unique:" in result.stderr

    def test_a_yanked_entry_equal_to_active_refuses_the_control(
        self, tmp_path: Path
    ) -> None:
        """Fold wave row 4 (adv-lane1 F1): under yanked == active the
        derivation returns (active, active) and the substring checks pass
        against ANY output naming the active version — the anti-gaming arm
        goes vacuous. The derivation refuses the shape instead. RED at
        base: the same scratch policy let the control proceed (exit 0)."""
        scratch = self._scratch_control_repo(tmp_path, "yanked-is-active")
        result = subprocess.run(
            [sys.executable, str(scratch / "scripts/adc_conformance_control.py"), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0, result.stdout + result.stderr
        assert "adc_yank_is_active:" in result.stderr

    def test_a_malformed_authority_refuses_with_the_adc_prefix(
        self, tmp_path: Path
    ) -> None:
        """Fold wave row 8 tail: a manifest that cannot be read or parsed
        (IsADirectoryError / JSONDecodeError / FileNotFoundError) exits
        with an ``adc_policy_unreadable:`` prefix, never a raw traceback.
        RED at base: the raw exception escaped."""
        for mutate, corrupt in (
            ("dir", "mkdir"),
            ("json", "text"),
        ):
            scratch = self._scratch_control_repo(tmp_path, f"unreadable-{mutate}")
            manifest = scratch / "standards/standards-manifest.json"
            if corrupt == "mkdir":
                manifest.unlink()
                manifest.mkdir()
            else:
                manifest.write_text("{not json", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(scratch / "scripts/adc_conformance_control.py"), "--help"],
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode != 0, result.stdout + result.stderr
            assert "adc_policy_unreadable:" in result.stderr, (
                f"mutate={mutate}: {result.stderr[-200:]}"
            )

    def test_an_assembled_plant_in_a_registered_scripts_file_counts_both_sites(
        self, tmp_path: Path
    ) -> None:
        """Fold wave row 8 tail: the register arithmetic pins the +2 — an
        S6-class shape in a registered file contributes the folded ASM site
        AND the inner textual BARE site, and the expectation names both
        (found 4 = 2 registered + 2 planted)."""
        scratch = self._scratch_scripts_repo(tmp_path)
        target = scratch / "scripts/sdk_smoke.py"
        plant_line = len(target.read_text(encoding="utf-8").splitlines()) + 1
        target.write_bytes(
            target.read_bytes() + b'_PLANT_S6 = "execution/%s" % "9.9.9"\n'
        )
        result = _scratch_run(scratch, "--scope", "scripts", "--json")
        assert result.returncode == 1, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        report = payload["scopes"]["scripts"]
        assert (
            "register expectation failed: scripts/sdk_smoke.py expects 2 literals, found 4"
            in "\n".join(report["violations"])
        )
        plant_rows = [
            row
            for row in report["sites"]
            if row["file"] == "scripts/sdk_smoke.py" and row["line"] == plant_line
        ]
        patterns = sorted(row["pattern"] for row in plant_rows)
        assert "ASM-A" in patterns and "BARE" in patterns, plant_rows

    def test_an_absent_otdp_entry_refuses_the_control(self, tmp_path: Path) -> None:
        """A scratch authority without the otdp entry ⇒
        ``adc_policy_absent:`` non-zero exit."""
        scratch = self._scratch_control_repo(tmp_path, "otdp-absent")
        result = subprocess.run(
            [sys.executable, str(scratch / "scripts/adc_conformance_control.py"), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0, result.stdout + result.stderr
        assert "adc_policy_absent:" in result.stderr

    def test_the_docs_site_runtime_schema_path_is_the_active_family(self) -> None:
        """H3's docs-site arm: the site's verified runtime-schema path is
        DERIVED from the committed manifest's ACTIVE otdp family, replacing
        the stale retained-old-version pin. RED at base: the module had no
        such constant and the pin named 0.2.0 while the active family is
        0.2.2."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "assemble_docs_site_under_test", ROOT / "scripts/assemble_docs_site.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        derived = module.ACTIVE_OTDP_RUNTIME_SCHEMA
        assert derived == "standards/otdp/0.2.2/otdp-runtime.schema.json", derived
        assert active_version_from_corpus(ROOT / "standards", "otdp") == "0.2.2"
        # The derived path exists in the real corpus at the same
        # repo-relative path (and copy_standards_resources ships every
        # non-dev family beside the prose, so the built tree carries it by
        # construction).
        assert (ROOT / derived).is_file()


class TestAssemblyShapesBattery:
    """H1 (issue #269 §7): the twelve-shape battery, committed as the spec.

    The battery module is written into a scratch gateway tree and the
    counter must refuse EVERY shape: each shape's assignment line
    contributes at least one violation row (the folded ``ASM-*`` site, the
    textual ``A``/``BARE`` site, or both). RED at the battery's base: the
    pre-fold counter caught exactly 3 of 12 (the shapes leaving a complete
    string ``Constant`` in the AST) and 9 passed — the recorded arithmetic.
    KILL: any shape passing under the folded counter.
    """

    def _scratch_minimal_repo(self, tmp_path: Path, name: str) -> Path:
        """Counter + manifest + an empty gateway tree — for scratch arms
        that plant their own files (the battery arm's own scratch carries
        the (refused) twelve-shape file and would fail every run)."""
        import shutil

        scratch = tmp_path / f"scratch-repo-{name}"
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
        (scratch / "src/benchweave/presentation").mkdir(parents=True)
        # The registered gateway row must hold in the scratch too — the
        # arms below isolate the assembly boundary, not the register.
        shutil.copy(
            ROOT / "src/benchweave/presentation/contracts.py",
            scratch / "src/benchweave/presentation/contracts.py",
        )
        return scratch

    def _scratch_battery_repo(self, tmp_path: Path) -> Path:
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
        (scratch / "src/benchweave").mkdir(parents=True)
        (scratch / "src/benchweave/assembly_shapes.py").write_text(
            BATTERY_MODULE, encoding="utf-8"
        )
        return scratch

    def test_every_shape_is_refused_by_the_gate(self, tmp_path: Path) -> None:
        scratch = self._scratch_battery_repo(tmp_path)
        result = _scratch_run(scratch, "--scope", "gateway", "--json")
        assert result.returncode == 1, result.stdout + result.stderr
        sites = json.loads(result.stdout)["scopes"]["gateway"]["sites"]
        caught = {
            row["line"] for row in sites if row["file"].endswith("assembly_shapes.py")
        }
        lines = shape_lines(BATTERY_MODULE)
        assert len(lines) == len(SHAPE_NAMES), "the battery map lost a shape"
        missing = sorted(name for name in SHAPE_NAMES if lines[name] not in caught)
        assert not missing, (
            f"{len(missing)} of {len(SHAPE_NAMES)} battery shapes pass the "
            f"gate (uncaught): {missing}"
        )

    def test_every_documented_miss_shape_passes_the_gate(self, tmp_path: Path) -> None:
        """Fold wave row 3, the miss side: each M-shape exercises a named
        miss class and MUST pass — no fragment matches textually and no
        sub-expression folds to a version, so a refusal here means the
        residual list and the mechanism disagree."""
        scratch = self._scratch_minimal_repo(tmp_path, "miss")
        target = scratch / "src/benchweave/miss_shapes.py"
        target.write_text(MISS_MODULE, encoding="utf-8")
        result = _scratch_run(scratch, "--scope", "gateway", "--json")
        assert result.returncode == 0, result.stdout + result.stderr
        sites = json.loads(result.stdout)["scopes"]["gateway"]["sites"]
        offenders = [
            row for row in sites if row["file"].endswith("miss_shapes.py")
        ]
        assert not offenders, (
            f"{len(offenders)} documented-miss shapes were REFUSED (the "
            f"residual list is stale or the allowlist narrowed): {offenders}"
        )
        assert (
            len(shape_lines(MISS_MODULE, MISS_SHAPE_NAMES)) == len(MISS_SHAPE_NAMES)
        )

    def test_the_boundary_table_pins_both_caps(self, tmp_path: Path) -> None:
        """Fold wave row 5, at the MEASURED boundary: 24 chained BinOps
        fold (caught), 25 are bounded out (documented miss — no site);
        a 4096-char fold is caught, 4097 bounded out. The caught file
        refuses with an ASM row at each shape's line; the miss file is
        invisible."""
        scratch = self._scratch_minimal_repo(tmp_path, "boundary")
        (scratch / "src/benchweave/boundary_caught.py").write_text(
            BOUNDARY_CAUGHT_MODULE, encoding="utf-8"
        )
        (scratch / "src/benchweave/boundary_miss.py").write_text(
            BOUNDARY_MISS_MODULE, encoding="utf-8"
        )
        result = _scratch_run(scratch, "--scope", "gateway", "--json")
        assert result.returncode == 1, result.stdout + result.stderr
        sites = json.loads(result.stdout)["scopes"]["gateway"]["sites"]
        patterns_by_file_line: dict[str, dict[int, set[str]]] = {}
        for row in sites:
            file_map = patterns_by_file_line.setdefault(row["file"], {})
            file_map.setdefault(row["line"], set()).add(row["pattern"])
        caught_lines = shape_lines(BOUNDARY_CAUGHT_MODULE, BOUNDARY_CAUGHT_NAMES)
        for name in BOUNDARY_CAUGHT_NAMES:
            line = caught_lines[name]
            file_sites = patterns_by_file_line.get("src/benchweave/boundary_caught.py", {})
            assert line in file_sites, f"{name} (line {line}) was not caught"
            assert any(
                pattern.startswith("ASM-") for pattern in file_sites[line]
            ), f"{name} caught only textually"
        miss_lines = shape_lines(BOUNDARY_MISS_MODULE, BOUNDARY_MISS_NAMES)
        for name in BOUNDARY_MISS_NAMES:
            line = miss_lines[name]
            file_sites = patterns_by_file_line.get("src/benchweave/boundary_miss.py", {})
            assert line not in file_sites, (
                f"{name} (line {line}) produced a site — the bounded-out "
                "disclosure is stale"
            )

    def test_the_counter_docstring_names_every_documented_miss_class(self) -> None:
        """Fold wave rows 3+5, the honesty layer: the residual list in the
        counter's own docstring must name every miss class the mechanism
        actually has, so the prose is regenerable from the allowlist. RED
        at the fold-wave base: the classes were unnamed (the old sentence
        claimed only 'dynamic' and os.path.join)."""
        text = (ROOT / "scripts/standards/count_version_literals.py").read_text(
            encoding="utf-8"
        )
        for token in (
            "format-spec",  # M1
            "kwargs",  # M2
            "%-with-dict",  # M3
            'decode with argument',  # M4
            "conditional-expression",  # M5
            "starred",  # M6
            "os.path.join",  # M7
            "non-literal",  # the dynamic class
            "depth > 24",  # the depth cap, as a disclosure
            "length > 4096",  # the length cap, as a disclosure
            "indistinguishable from dynamic",  # the bounded-out disclosure
            "module-level",  # the shadow-prepass scope residual
        ):
            assert token in text, f"the residual list does not name: {token!r}"


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
