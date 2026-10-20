"""The docs claim register's permanent pins (issue #459, design §3-§5).

The register closes the one truth gap no owner covers (design §0): a green,
correctly-pinned docs-literal baseline sat over a FALSE "is active" claim
for a full train cycle (the 9b879cf8 miss) because no mechanism derives
docs prose version claims from the standards manifest. These pins hold the
register's two halves:

- A2 (the clean-tree arm): ``train_preflight.py --claims-only`` over the
  real tree exits 0 — all 18 register rows verify against the committed
  manifest. The expectations in these tests are DERIVED from the manifest
  (never hand-typed), so a standards bump moves them for free.
- A1 (the differential control, as a permanent pin): the 9b879cf8 class —
  a stale active literal that a ``--refresh-docs-baseline`` blessing would
  hide from every existing gate — refuses, naming the file and the
  manifest's active version. The scratch arms plant over a COPIED tree so
  the real tree never moves.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = ROOT / "scripts/standards/train_preflight.py"

# The five claim files (design §3) — the register's whole file set, so a
# scratch arm copies exactly what the checker reads and nothing else.
CLAIM_FILES = (
    "docs/develop-your-device.md",
    "docs/device-developer-guide.md",
    "docs/ai-device-reviewer.md",
    "docs/development.md",
    "docs/smart-test-gateway-architecture-v1.5.md",
)


def _preflight(*argv: str, root: Path | None = None) -> subprocess.CompletedProcess[str]:
    """The test_zero_literal_gate subprocess shape: the real script, no cwd
    anchoring (the checker roots itself on ``--root`` / its own __file__)."""
    return subprocess.run(
        [sys.executable, str(PREFLIGHT), *argv],
        capture_output=True,
        text=True,
        check=False,
        cwd=root if root is not None else ROOT,
    )


def _manifest_at(root: Path) -> dict[str, object]:
    return cast(
        "dict[str, object]",
        json.loads(
            (root / "standards" / "standards-manifest.json").read_text(encoding="utf-8")
        ),
    )


def _active_version(root: Path, standard_id: str) -> str:
    document = _manifest_at(root)
    entries = document["standards"]
    assert isinstance(entries, list)
    for entry in entries:
        if entry["id"] == standard_id:
            return str(entry["version"])
    raise AssertionError(f"the manifest carries no {standard_id} entry")


def _scratch_tree(tmp_path: Path) -> Path:
    """A minimal claim-check root: the five claim files plus the manifest,
    copied verbatim — a plant then edits one file in isolation (every other
    register row keeps verifying, so the arm refuses on exactly one surface)."""
    (tmp_path / "standards").mkdir()
    (tmp_path / "standards" / "standards-manifest.json").write_text(
        (ROOT / "standards" / "standards-manifest.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir()
    for relative in CLAIM_FILES:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((ROOT / relative).read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


def _previous_patch(version: str) -> str:
    """One patch step back — the 9b879cf8 plant's exact shape (a claim left
    one bump behind the manifest)."""
    major, minor, patch = (int(part) for part in version.split("."))
    assert patch > 0, f"the plant needs a patch floor; {version} has none"
    return f"{major}.{minor}.{patch - 1}"


class TestClaimsOverTheRealTree:
    def test_clean_tree_holds_every_row(self) -> None:
        """A2: at a coherent tree tip all 18 rows verify — the anchor
        matched, and every claim equals the manifest's own derivation."""
        result = _preflight("--claims-only")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "[ok] docs version claims" in result.stdout
        assert "18/18 rows verified" in result.stdout
        assert "0 unmoved" in result.stdout

    def test_the_register_covers_exactly_five_files(self) -> None:
        """The register's file set is the design's five sites — a sixth
        site joins by a visible register edit (the anti-laundering shape),
        never by widening this pin silently."""
        result = _preflight("--claims-only", "--json")
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert sorted(payload["files"]) == sorted(CLAIM_FILES)
        assert payload["rows"] == 18


class TestPlantedClaims:
    def test_stale_active_claim_refuses_naming_file_and_active_version(
        self, tmp_path: Path
    ) -> None:
        """A1's permanent pin: the 9b879cf8 class refuses. The counter's
        docs scope alone would exit 0 over this plant after a
        ``--refresh-docs-baseline`` blessing (proven once, live, in the
        slice's acceptance run) — the claim register is the gate that
        owns the class."""
        scratch = _scratch_tree(tmp_path)
        active = _active_version(scratch, "otdp")
        previous = _previous_patch(active)
        claim_file = scratch / "docs/develop-your-device.md"
        planted = claim_file.read_text(encoding="utf-8").replace(
            f"Version {active} is active", f"Version {previous} is active"
        )
        assert planted != claim_file.read_text(encoding="utf-8"), "the plant did not land"
        claim_file.write_text(planted, encoding="utf-8")

        result = _preflight("--claims-only", "--root", str(scratch))
        assert result.returncode != 0, result.stdout + result.stderr
        combined = result.stdout + result.stderr
        assert "docs_claim_stale:" in combined
        assert "docs/develop-your-device.md" in combined
        assert f"claims otdp {previous} active" in combined
        assert f"standards-manifest.json says {active}" in combined

    def test_served_claim_on_an_unretained_version_refuses(
        self, tmp_path: Path
    ) -> None:
        """The served row's derivation: the claimed version must be carried
        by the dependency-policy block's retained set (in range, not yanked,
        not retired). Planted to the yanked entry — the policy's own
        machine-named refusal input."""
        scratch = _scratch_tree(tmp_path)
        document = _manifest_at(scratch)
        policy = document["dependency_policy"]
        assert isinstance(policy, dict)
        entry = policy["standards"]["otdp"]
        yanked = sorted(entry["yanked"])
        retired = sorted(entry["retired"])
        assert yanked or retired, "the plant needs one unretained declared version"
        unretained = yanked[0] if yanked else retired[0]
        claim_file = scratch / "docs/develop-your-device.md"
        current = re.search(
            r"version (\d+\.\d+\.\d+) remains served",
            claim_file.read_text(encoding="utf-8"),
        )
        assert current is not None, "the served claim site is absent from the copy"
        assert current.group(1) != unretained, "the plant target equals the held claim"
        planted = claim_file.read_text(encoding="utf-8").replace(
            f"version {current.group(1)} remains served",
            f"version {unretained} remains served",
        )
        assert planted != claim_file.read_text(encoding="utf-8"), "the plant did not land"
        claim_file.write_text(planted, encoding="utf-8")

        result = _preflight("--claims-only", "--root", str(scratch))
        assert result.returncode != 0, result.stdout + result.stderr
        combined = result.stdout + result.stderr
        assert "docs_claim_stale:" in combined
        assert "docs/develop-your-device.md" in combined
        assert f"claims otdp {unretained} served" in combined
        assert "does not retain" in combined

    def test_moved_anchor_refuses_loudly(self, tmp_path: Path) -> None:
        """A prose rewrite that dissolves the claim token reds with
        ``docs_claim_anchor_lost:`` — a moved claim site is a reviewable
        register edit, never a silent pass (the counter register's own
        anti-laundering shape)."""
        scratch = _scratch_tree(tmp_path)
        active = _active_version(scratch, "otdp")
        claim_file = scratch / "docs/develop-your-device.md"
        planted = claim_file.read_text(encoding="utf-8").replace(
            f"Version {active} is active; ", ""
        )
        assert planted != claim_file.read_text(encoding="utf-8"), "the plant did not land"
        claim_file.write_text(planted, encoding="utf-8")

        result = _preflight("--claims-only", "--root", str(scratch))
        assert result.returncode != 0, result.stdout + result.stderr
        combined = result.stdout + result.stderr
        assert "docs_claim_anchor_lost:" in combined
        assert "docs/develop-your-device.md" in combined


class TestAnchorAmbiguity:
    """MED-1 + governor L1 (the fold wave): an anchor matching MORE THAN
    ONE site refuses with ``docs_claim_anchor_ambiguous:``. A decoy
    sentence inserted above the declared site must not launder the
    declared row — pre-fix, first-match semantics verified the decoy's
    TRUE literal while the staled real line below it went unchecked, and
    ``--claims-only`` exited 0 (the anchor-hijack the adversary planted)."""

    def test_decoy_baseline_line_cannot_launder_the_staled_real_line(
        self, tmp_path: Path
    ) -> None:
        """The adversary's plant shape: a worked-example ``**Baseline:**``
        line carrying the TRUE OTDP version above the real line, the real
        line's literal staled one bump behind the manifest."""
        scratch = _scratch_tree(tmp_path)
        active = _active_version(scratch, "otdp")
        previous = _previous_patch(active)
        claim_file = scratch / "docs/device-developer-guide.md"
        text = claim_file.read_text(encoding="utf-8")
        marker = "**Baseline:** architecture"
        assert marker in text, "the real Baseline sentence moved; re-derive the plant"
        decoy = (
            f"**Baseline:** (worked example) plugin authors may target OTDP {active} "
            "when they review the worked example below.\n\n"
        )
        planted = text.replace(marker, decoy + marker, 1)
        staled = planted.replace(f"OTDP {active} ·", f"OTDP {previous} ·", 1)
        assert staled != planted, "the stale did not land on the real line"
        claim_file.write_text(staled, encoding="utf-8")

        result = _preflight("--claims-only", "--root", str(scratch))
        assert result.returncode != 0, result.stdout + result.stderr
        combined = result.stdout + result.stderr
        assert "docs_claim_anchor_ambiguous:" in combined
        assert "docs/device-developer-guide.md" in combined
        assert "(otdp active row)" in combined
        assert "matches 2 sites" in combined

    def test_decoy_served_sentence_cannot_launder_the_staled_real_sentence(
        self, tmp_path: Path
    ) -> None:
        """The served-row variant of the same hijack: a decoy sentence
        carrying a RETAINED version above the real sentence, the real
        served claim staled to the yanked entry."""
        scratch = _scratch_tree(tmp_path)
        document = _manifest_at(scratch)
        policy = document["dependency_policy"]
        assert isinstance(policy, dict)
        entry = policy["standards"]["otdp"]
        unretained = sorted(entry["yanked"])[0] if entry["yanked"] else sorted(entry["retired"])[0]
        claim_file = scratch / "docs/develop-your-device.md"
        text = claim_file.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        served_line = next((i for i, line in enumerate(lines) if "remains served" in line), None)
        assert served_line is not None, "the served sentence moved; re-derive the plant"
        held = re.search(r"version (\d+\.\d+\.\d+) remains served", lines[served_line])
        assert held is not None
        lines.insert(
            served_line,
            f"(Worked example) version {held.group(1)} remains served for older installs.\n",
        )
        planted = "".join(lines).replace(
            f"version {held.group(1)} remains served. Confirm",
            f"version {unretained} remains served. Confirm",
            1,
        )
        assert unretained in planted, "the stale did not land on the real sentence"
        claim_file.write_text(planted, encoding="utf-8")

        result = _preflight("--claims-only", "--root", str(scratch))
        assert result.returncode != 0, result.stdout + result.stderr
        combined = result.stdout + result.stderr
        assert "docs_claim_anchor_ambiguous:" in combined
        assert "docs/develop-your-device.md" in combined
        assert "(otdp served row)" in combined
        assert "matches 2 sites" in combined


def _preflight_module() -> ModuleType:
    """The script as a module, for the in-process pins over its pure
    helpers (the A3 harness's script-shaped-module precedent; importlib
    beats a sys.path bootstrap — nothing leaks into the test session)."""
    spec = importlib.util.spec_from_file_location("train_preflight_under_test", PREFLIGHT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registration BEFORE exec is load-bearing: the module's dataclass
    # resolves string annotations through sys.modules[cls.__module__], and
    # an unregistered module makes that lookup return None (AttributeError
    # from inside dataclasses, not from the code under test).
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestGreenPathAnnotations:
    """MED-3 (fold wave): ``::``-prefixed annotation lines forward on the
    GREEN path, never swallowed. The pairing-pending ``::warning::`` is the
    one green-path signal the release-family walk reads at exactly the
    moment the preflight runs; the standalone checker prints it and exits
    0, and the orchestrator must not be the place it disappears."""

    def test_warning_annotation_forwards_on_green(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        module = _preflight_module()
        module.print_row(
            "packages/sdk pointer pin ↔ gitlink (drift checker)",
            True,
            [
                "sdk-drift OK: packages/sdk gitlink 9e0449ef is at the declared pin",
                "::warning::pin v0.16.0 trails latest v0.17.0 — pairing pending",
            ],
        )
        captured = capsys.readouterr().out
        assert (
            "[ok] packages/sdk pointer pin ↔ gitlink (drift checker) — sdk-drift OK:"
            in captured
        )
        assert "::warning::pin v0.16.0 trails latest v0.17.0 — pairing pending" in captured

    def test_plain_green_row_stays_lean(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A green step with no annotations prints one row and nothing
        indented — forwarding is for `::` lines, not all output."""
        module = _preflight_module()
        module.print_row("a quiet surface", True, [])
        captured = capsys.readouterr().out
        assert captured == "[ok] a quiet surface\n"

    def test_annotation_lines_forward_on_refusal_too(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        module = _preflight_module()
        module.print_row(
            "a surface",
            False,
            ["::notice::fetch failed — the annotation degrades", "a refusal line"],
        )
        captured = capsys.readouterr().out
        assert "[UNMOVED] a surface" in captured
        assert "::notice::fetch failed" in captured
        assert "a refusal line" in captured


class TestStatusGuard:
    """Governor M1 (fold wave): the manifest's status is part of the
    derivation, not just the version. A standard deprecated AT THE SAME
    VERSION would leave every is-active row green under a version-only
    map; an asserted standard whose manifest entry is not ``stable``
    refuses, naming the status."""

    def test_deprecated_at_the_same_version_refuses(self, tmp_path: Path) -> None:
        scratch = _scratch_tree(tmp_path)
        manifest_file = scratch / "standards" / "standards-manifest.json"
        document = _manifest_at(scratch)
        entries = document["standards"]
        assert isinstance(entries, list)
        planted = False
        for entry in entries:
            if isinstance(entry, dict) and entry.get("id") == "otdp":
                entry["status"] = "deprecated"
                planted = True
        assert planted, "the manifest carries no otdp entry to plant"
        manifest_file.write_text(json.dumps(document), encoding="utf-8")

        result = _preflight("--claims-only", "--root", str(scratch))
        assert result.returncode != 0, result.stdout + result.stderr
        combined = result.stdout + result.stderr
        assert "docs_claim_status_nonstable:" in combined
        assert "deprecated" in combined
        assert "docs/develop-your-device.md" in combined
