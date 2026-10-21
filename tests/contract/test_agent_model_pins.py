"""Declaration completeness of the review-lane model pins (``.claude/agents/*.md``).

Issue #519: the review rubric's G6 lane says each refute run's model is whatever
the installation resolves the agent's DECLARED pin to — that claim presupposes
every agent definition declares a ``model:`` line, and this test is what makes
the presupposition regenerable instead of assumed.

What this test does NOT catch:
- Same-pin convergence: two lanes declaring the same pin is an owner-accepted
  posture (``adversary`` and ``increment-builder`` both pin ``opus``) — this
  test never compares pins.
- Vendor identity: which vendor an installation resolves a pin to is an
  installation property, invisible to repository state — no in-repo test can
  catch it.
- Presence-only: all that is proved is a non-empty ``model:`` line in each
  frontmatter. That the pin names a real alias (the repo holds no authority
  for the alias set), or that the declared pin served any given run, is not
  proved.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = ROOT / ".claude" / "agents"


def _frontmatter_lines(text: str) -> list[str]:
    """The lines inside the leading ``---`` frontmatter block, else ``[]``."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    body: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            return body
        body.append(line)
    # No closing fence: treat the frontmatter as absent rather than guessing.
    return []


def _declares_model_pin(frontmatter: list[str]) -> bool:
    return any(
        line.startswith("model:") and line.removeprefix("model:").strip()
        for line in frontmatter
    )


def test_every_agent_definition_declares_a_model_pin() -> None:
    agent_files = sorted(AGENTS_DIR.glob("*.md"))
    # The glob, not a hand-list: a new agent joins the check by existing.
    assert agent_files, f"no agent definitions under {AGENTS_DIR} — path moved?"
    missing = [
        path.name
        for path in agent_files
        if not _declares_model_pin(_frontmatter_lines(path.read_text(encoding="utf-8")))
    ]
    assert not missing, (
        "agent definition(s) without a declared model pin (review rubric G6, issue "
        f"#519 — the pin must be declared so an installation can resolve it): {missing}"
    )
