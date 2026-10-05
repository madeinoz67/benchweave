"""The scaffold seeds the agent-native tree: CLAUDE.md/AGENTS.md + skills.

Issue #71 slice 2 (design record section 8): the file-set pin below is the
SRF-1 contract — the sorted file list of every generated project. A
deliberate shape change edits the pin in the same change; an accidental one
fails here. The generated runtime keeps its no-SDK-dependency property: the
seeded files are markdown only.
"""

from __future__ import annotations

import sys
from pathlib import Path

SDK_SRC = Path(__file__).resolve().parents[2] / "packages/sdk/src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from benchweave_sdk.scaffold import create_project  # noqa: E402

PACKAGE = "lumen_probe"

#: The complete generated file set (sorted relative paths). Skills live under
#: src/<package>/ so they ship in the wheel and catalogue under the registry
#: ``skill`` role; CLAUDE.md is root-level dev tooling and never ships.
#: Re-pinned at the SDK 0.7.0 copier render: the .claude/skills tree,
#: .copier-answers.yml and AGENTS.md joined the set (the SDK-managed agent
#: notes the upgrade path rewrites). The byte-exact authority for the tree
#: is the SDK's own fixture comparison (tests/test_scaffold_copier.py at
#: the pinned tree); this pin keeps the gateway-side shape alarm.
PINNED_FILE_SET = [
    ".claude/skills/benchweave-adapter-testing/SKILL.md",
    ".claude/skills/benchweave-capture/SKILL.md",
    ".claude/skills/benchweave-descriptor/SKILL.md",
    ".claude/skills/benchweave-plugin-ui/SKILL.md",
    ".claude/skills/benchweave-plugin-workflow/SKILL.md",
    ".copier-answers.yml",
    "AGENTS.md",
    "AI-GUIDE.md",
    "CLAUDE.md",
    "README.md",
    "pyproject.toml",
    f"src/{PACKAGE}/__init__.py",
    f"src/{PACKAGE}/adapter.py",
    f"src/{PACKAGE}/descriptor.json",
    f"src/{PACKAGE}/protocol.md",
    f"src/{PACKAGE}/protocol.py",
    f"src/{PACKAGE}/skills/develop-plugin/SKILL.md",
    f"src/{PACKAGE}/skills/drive-device/SKILL.md",
    f"src/{PACKAGE}/vectors.json",
    "tests/test_plugin.py",
]

SEEDED_FILES = [
    "CLAUDE.md",
    f"src/{PACKAGE}/skills/develop-plugin/SKILL.md",
    f"src/{PACKAGE}/skills/drive-device/SKILL.md",
]


def _generate(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    create_project(project, PACKAGE)
    return project


def _relative_files(project: Path) -> list[str]:
    return sorted(
        path.relative_to(project).as_posix() for path in project.rglob("*") if path.is_file()
    )


def test_new_seeds_skills_and_claude_md(tmp_path: Path) -> None:
    project = _generate(tmp_path)
    for relative in SEEDED_FILES:
        assert (project / relative).is_file(), f"scaffold did not seed {relative}"


def test_scaffold_file_set_pinned(tmp_path: Path) -> None:
    project = _generate(tmp_path)
    assert _relative_files(project) == PINNED_FILE_SET


def test_seeded_files_byte_stable(tmp_path: Path) -> None:
    first = _generate(tmp_path / "one")
    second = _generate(tmp_path / "two")
    for relative in SEEDED_FILES:
        assert (first / relative).read_bytes() == (second / relative).read_bytes(), (
            f"{relative} is not byte-stable across runs"
        )


def test_seeded_skill_frontmatter_present(tmp_path: Path) -> None:
    """An output pin on our own bytes, not a format rule (D2 stays deferred):
    each SKILL.md leads with a name/description block, names carrying the
    package so skills from multiple plugins cannot collide in one harness
    skill directory; the name hyphenates the package, matching the
    generated pyproject project name and descriptor id practice."""
    dashed = PACKAGE.replace("_", "-")
    expected_names = {
        f"src/{PACKAGE}/skills/develop-plugin/SKILL.md": f"{dashed}-plugin-development",
        f"src/{PACKAGE}/skills/drive-device/SKILL.md": f"{dashed}-device-operation",
    }
    project = _generate(tmp_path)
    for relative, skill_name in expected_names.items():
        text = (project / relative).read_text(encoding="utf-8")
        assert text.startswith("---\n"), f"{relative} does not lead with a frontmatter block"
        block = text.split("\n...\n", 1)[0] if "\n...\n" in text else text.split("\n---\n", 1)[0]
        name_lines = [line for line in block.splitlines() if line.startswith("name:")]
        description_lines = [line for line in block.splitlines() if line.startswith("description:")]
        assert name_lines == [f"name: {skill_name}"], f"{relative} frontmatter name: {name_lines}"
        assert description_lines and len(description_lines[0]) > len("description: "), (
            f"{relative} frontmatter description is empty"
        )


def test_claude_md_references_real_commands(tmp_path: Path) -> None:
    """SDK 0.7.0 shape: CLAUDE.md is the project-owned stub deferring to the
    SDK-managed AGENTS.md (rewritten by ``benchweave-sdk upgrade``). The
    references-are-real anti-drift survives as: the stub's one command
    reference names a subcommand the CLI actually registers, and the
    SDK-managed file it defers to exists in the rendered tree. The content
    needles the pre-0.7.0 CLAUDE.md carried moved into AGENTS.md and the
    .claude/skills tree, pinned by the SDK's own agent-assets suite."""
    import importlib

    from click.testing import CliRunner

    project = _generate(tmp_path)
    text = (project / "CLAUDE.md").read_text(encoding="utf-8")
    assert "@AGENTS.md" in text, "CLAUDE.md no longer defers to the SDK-managed AGENTS.md"
    assert "benchweave-sdk upgrade" in text, "CLAUDE.md does not name the upgrade path"
    assert (project / "AGENTS.md").is_file(), "the deferred AGENTS.md is absent from the tree"
    cli = importlib.import_module("benchweave_sdk.cli")
    result = CliRunner().invoke(cli.cli, ["--help"])
    assert result.exit_code == 0
    assert "upgrade" in result.output, "CLAUDE.md names a subcommand the CLI does not register"


def test_drive_device_honesty_label_pinned(tmp_path: Path) -> None:
    """R11's mitigation is text in the skill itself: the seeded device skill
    states it drives the synthetic protocol, not a real instrument, and says
    to rewrite it for the real device (the synthetic-adapter honesty
    pattern)."""
    project = _generate(tmp_path)
    text = (project / f"src/{PACKAGE}/skills/drive-device/SKILL.md").read_text(encoding="utf-8")
    for needle in ("not a real instrument", "Rewrite this skill for the real device"):
        assert needle in text, f"drive-device skill drops its honesty label: {needle!r}"


def test_root_docs_stay_out_of_the_built_wheel(tmp_path: Path) -> None:
    """The CLAUDE.md shipping claim the templates make is the WHEEL one:
    `packages = ["src/<package>"]` keeps root-level docs out of wheel
    members. (The sdist is deliberately NOT asserted - hatchling's default
    sdist ships the whole tree, and no exclusion is emitted.)"""
    import subprocess
    import zipfile

    project = _generate(tmp_path)
    dist = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--wheel", str(project), "--out-dir", str(dist)],
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(dist.glob("*.whl"))
    names = zipfile.ZipFile(wheel).namelist()
    for root_doc in ("CLAUDE.md", "AI-GUIDE.md", "README.md"):
        assert root_doc not in names, f"{root_doc} leaked into the built wheel"
    assert any(name.startswith(f"{PACKAGE}/skills/") for name in names), (
        "the seeded skills are not in the wheel"
    )


def test_ai_guide_names_seeded_files(tmp_path: Path) -> None:
    """Drift obligation 2: the AI-GUIDE's layout paragraph names CLAUDE.md and
    the seeded skills tree."""
    project = _generate(tmp_path)
    text = (project / "AI-GUIDE.md").read_text(encoding="utf-8")
    assert "CLAUDE.md" in text, "AI-GUIDE layout paragraph does not name CLAUDE.md"
    assert "skills/" in text, "AI-GUIDE layout paragraph does not name the skills tree"
