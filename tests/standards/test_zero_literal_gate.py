"""The zero-literal end state: the gate, its register, and the derivations.

Issue #221 (#203 slice 7, design record committed beside this tree): every
executable version literal in the gateway source tree is either DERIVED from
its machine authority (the vendored manifest, the validating schema's own
const) or REGISTERED with a reason and an expected site count — and the
committed counter refuses anything else (SM-2 = 0 outside the register).
"""

from __future__ import annotations

import json
import subprocess
import sys
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
        assert payload["scopes"]["docs"]["scanned"] == 19, (
            "the docs class set moved — update this pin in the same commit "
            "as the tree change, or refresh the snapshot deliberately"
        )
        assert payload["scopes"]["gateway"]["scanned"] >= 93

    def test_absent_sdk_tree_refuses_loudly_in_a_scratch_copy(self, tmp_path: Path) -> None:
        import shutil

        scratch = tmp_path / "scratch-repo"
        (scratch / "scripts/standards").mkdir(parents=True)
        shutil.copy(
            ROOT / "scripts/standards/count_version_literals.py",
            scratch / "scripts/standards/count_version_literals.py",
        )
        result = _scratch_run(scratch, "--scope", "sdk")
        assert result.returncode == 1
        assert "sdk_tree_absent:" in result.stderr


class TestRegisterTeeth:
    """G2b: the register cannot become a laundering list (design risk 1)."""

    def test_a_plant_inside_a_registered_file_fails_via_expected_sites(
        self, tmp_path: Path
    ) -> None:
        import shutil

        scratch = tmp_path / "scratch-repo"
        (scratch / "scripts/standards").mkdir(parents=True)
        shutil.copy(
            ROOT / "scripts/standards/count_version_literals.py",
            scratch / "scripts/standards/count_version_literals.py",
        )
        shutil.copytree(ROOT / "src/benchweave", scratch / "src/benchweave")
        contracts_py = scratch / "src/benchweave/presentation/contracts.py"
        contracts_py.write_bytes(contracts_py.read_bytes() + b'\n_PLANT = "9.9.9"\n')
        result = _scratch_run(scratch, "--scope", "gateway")
        assert result.returncode == 1, result.stdout + result.stderr
        assert "register expectation failed:" in result.stdout
        assert "expects 3 literals, found 4" in result.stdout


class TestDocsRatchet:
    """The docs scope's snapshot ratchet (VR-24, design §1.3)."""

    def _scratch_docs_repo(self, tmp_path: Path) -> Path:
        import shutil

        scratch = tmp_path / "scratch-repo"
        (scratch / "scripts/standards").mkdir(parents=True)
        shutil.copy(
            ROOT / "scripts/standards/count_version_literals.py",
            scratch / "scripts/standards/count_version_literals.py",
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

    def test_a_removal_passes_the_ratchet(self, tmp_path: Path) -> None:
        """Removals only lower the count — deleting a literal never gates."""
        import re

        scratch = self._scratch_docs_repo(tmp_path)
        target = scratch / "docs/README.md"
        text = target.read_text(encoding="utf-8")
        match = re.search(r"\d+\.\d+\.\d+", text)
        assert match is not None
        lines = [
            line for line in text.splitlines(keepends=True) if match.group(0) not in line
        ]
        target.write_text("".join(lines))
        clean = _scratch_run(scratch, "--scope", "docs")
        assert clean.returncode == 0, clean.stdout + clean.stderr

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
