# author: Stephen Eaton
"""The project's Claude Code configuration stays inside its own boundaries (issue #664).

Arms over ``.claude/settings.json`` and ``.claude/agents/*.md``:

1. The allow list does not pre-approve ``sed``. ``sed -n 'A,Bp' <path>`` prints any file
   the user can read, with no prompt and no path for the harness to show. Read with
   offset and limit is the path-visible way to read a range.
2. Every agent definition declares its ``tools:``. An agent without the key inherits
   every tool of the session, MCP servers included, so one new server changes that agent
   with no diff under ``.claude/agents/``.
3. No agent reaches a memory write. A ``tools:`` list may carry the memory read tools
   only, and an agent that reads memory also names the writes it refuses in
   ``disallowedTools:``.

Each arm has a tamper arm that feeds it the bad shape, so a green arm is a measured zero
and not a scanner that cannot see.

What this test does NOT catch:

- ``Bash(rg:*)`` stays on the allow list by decision (issue #664, finding 5). It is the
  exact-string tool the Codanna workflow instructs agents to use, and it can still print
  a whole file (``rg --passthru``). This file has no arm on it.
- A read reached through an allowed command: ``Bash(codanna:*)`` and ``Bash(git:*)`` run
  programs, and what those programs read is outside an allow-list scan.
- Tools reached from Bash (a script, ``curl``). The arms read declarations, not a session.
- That a declared ``tools:`` list is the list a running session resolved. The frontmatter
  is the only evidence here.
- The main session's own allow entries. The memory arms cover ``.claude/agents/*.md``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLAUDE_DIR = ROOT / ".claude"
AGENTS_DIR = CLAUDE_DIR / "agents"
SETTINGS = CLAUDE_DIR / "settings.json"

# The per-user file is gitignored and carries one person's own rules, not the project's.
_UNSCOPED = "settings.local.json"

_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(.*)$")
_TOOL_RULE = re.compile(r"^[A-Za-z]+\((?P<command>.*)\)$")
# ``mcp__<server>__muninn_<verb>``, whatever the server is named.
_MEMORY_TOOL = re.compile(
    r"^mcp__(?P<server>[a-z0-9_-]*muninn[a-z0-9_-]*)__muninn_(?P<verb>[a-z_]+)$"
)
# The memory tools an agent may hold: reads and navigation only. Every other memory verb
# counts as a write, so a new verb is refused until it is read and listed here.
_MEMORY_READ_VERBS = frozenset(
    {
        "recall",
        "read",
        "find_by_entity",
        "entity",
        "entities",
        "entity_timeline",
        "traverse",
        "contradictions",
        "where_left_off",
        "status",
        "guide",
    }
)
# The three write tools the sibling agents name when they refuse the writes.
_MEMORY_WRITE_REFUSALS = ("muninn_remember", "muninn_remember_batch", "muninn_remember_tree")
_WILDCARD_SUFFIX = ":*"


# ---- readers -----------------------------------------------------------------------


def _frontmatter(text: str) -> dict[str, str]:
    """The keys of the leading ``---`` block, each with its raw one-line value.

    Only a key's own line is read. The indented lines of a block scalar or a block
    list are not keys. An absent block reads as an empty mapping.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        match = _KEY.match(line)
        if match is not None:
            fields[match[1]] = match[2].strip()
    return fields


def _block_list(text: str, key: str) -> list[str]:
    """The items of a frontmatter block list: ``key:`` then one indented ``- item`` each.

    A single-line value (``key: a, b`` or ``key: [a, b]``) reads as that list.
    """
    lines = text.splitlines()
    items: list[str] = []
    body = False
    for line in lines:
        stripped = line.strip()
        if body:
            if stripped.startswith("- "):
                items.append(stripped[2:].strip().strip("\"'"))
                continue
            if stripped == "" or line[:1] in (" ", "\t"):
                continue
            break
        if stripped.startswith(f"{key}:"):
            rest = stripped[len(key) + 1 :].strip()
            if rest:
                return _names(rest)
            body = True
    return items


def _names(raw: str) -> list[str]:
    """The names in a one-line list: ``a, b`` or ``["a", "b"]``. An empty value is ``[]``."""
    value = raw.strip()
    if value.startswith("["):
        value = value[1:]
        if value.endswith("]"):
            value = value[:-1]
    return [name.strip().strip("\"'") for name in value.split(",") if name.strip()]


def _agent_files() -> list[Path]:
    agent_files = sorted(AGENTS_DIR.glob("*.md"))
    # The glob, not a hand-list: a new agent joins every arm by existing.
    assert agent_files, f"no agent definitions under {AGENTS_DIR} — path moved?"
    return agent_files


def _memory_writes(names: list[str]) -> list[str]:
    """The names that reach a memory write: a memory tool whose verb is not a read."""
    flagged = []
    for name in names:
        match = _MEMORY_TOOL.match(name)
        if match is not None and match["verb"] not in _MEMORY_READ_VERBS:
            flagged.append(name)
    return flagged


def _memory_reads(names: list[str]) -> list[str]:
    """The names that are a memory read tool."""
    matched = []
    for name in names:
        match = _MEMORY_TOOL.match(name)
        if match is not None and match["verb"] in _MEMORY_READ_VERBS:
            matched.append(name)
    return matched


def _refused_writes(disallowed: list[str]) -> list[str]:
    """The names in ``disallowed`` that refuse a memory write, whatever the server is."""
    return [name for name in disallowed if _memory_writes([name]) == [name]]


def _settings_files() -> list[Path]:
    """Every project settings file: tracked-shape ``settings*.json`` and the project
    plugin records. The per-user file is not one."""
    files = [path for path in sorted(CLAUDE_DIR.glob("settings*.json")) if path.name != _UNSCOPED]
    files += sorted((CLAUDE_DIR / "plugins").glob("*.json"))
    assert files, f"no project settings file under {CLAUDE_DIR} — path moved?"
    return files


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path.name} is not a JSON object"
    return data


def _command_words(rule: str) -> list[str]:
    """The words of the command a ``Bash(...)`` rule allows. Any other rule is ``[]``."""
    match = _TOOL_RULE.match(rule)
    if match is None:
        return []
    command = match["command"]
    if command.endswith(_WILDCARD_SUFFIX):
        command = command[: -len(_WILDCARD_SUFFIX)]
    return command.split()


def _sed_rules(rules: list[str]) -> list[str]:
    """The rules that pre-approve a ``sed`` command."""
    return [rule for rule in rules if _command_words(rule)[:1] == ["sed"]]


def _allow_rules() -> list[tuple[str, str]]:
    """``permissions.allow`` of every project settings file, as ``(path.name, rule)``.

    The file name travels beside the rule and never inside it: a rule is matched as it
    is written, and the name is for the message.
    """
    rules: list[tuple[str, str]] = []
    for path in _settings_files():
        allow = _load(path).get("permissions", {}).get("allow", [])
        assert isinstance(allow, list), f"{path.name}: permissions.allow is not a list"
        rules += [(path.name, rule) for rule in allow]
    return rules


# ---- arm 1: the allow list and sed --------------------------------------------------


def test_allow_list_does_not_pre_approve_sed() -> None:
    offenders = [f"{name}: {rule}" for name, rule in _allow_rules() if rule in _sed_rules([rule])]
    assert not offenders, (
        "the allow list pre-approves sed, which prints any file range with no prompt and "
        "no path for the harness to show; Read with offset and limit is the path-visible "
        f"way to read a range (issue #664, finding 5): {offenders}"
    )


def test_tamper_a_sed_rule_is_flagged() -> None:
    """Arm 1's detection power: the rule the finding named is flagged, its neighbours not."""
    rules = ["Bash(codanna mcp:*)", "Bash(sed -n:*)"]
    assert _sed_rules(rules) == ["Bash(sed -n:*)"]
    assert _sed_rules(["Bash(rg:*)", "mcp__github__issue_read", "Bash(awk -f x:*)"]) == []


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        ("Bash(sed -n:*)", ["sed", "-n"]),
        ("Bash(sed:*)", ["sed"]),
        ("Bash(rg:*)", ["rg"]),
        ("Bash(codanna mcp:*)", ["codanna", "mcp"]),
        ("mcp__github__issue_read", []),
    ],
    ids=["sed-with-flag", "sed-bare", "rg", "two-words", "not-a-bash-rule"],
)
def test_command_words_read_a_bash_rule_and_nothing_else(rule: str, expected: list[str]) -> None:
    assert _command_words(rule) == expected


# ---- arm 2: every agent declares its tools -------------------------------------------


def test_every_agent_declares_its_tools() -> None:
    undeclared = [
        path.name
        for path in _agent_files()
        if "tools" not in _frontmatter(path.read_text(encoding="utf-8"))
    ]
    assert not undeclared, (
        "agent definition(s) without a tools: list inherit every tool of the session, MCP "
        f"servers included (issue #664, finding 6): {undeclared}"
    )


def test_tamper_an_undeclared_agent_is_seen() -> None:
    """Arm 2's detection power: an inherited toolset reads as an absent key."""
    declared = _frontmatter("---\nname: a\ntools: Read\n---\nbody\n")
    inheriting = _frontmatter("---\nname: a\ndisallowedTools: []\n---\nbody\n")
    assert "tools" in declared
    assert "tools" not in inheriting


# ---- arm 3: no agent reaches a memory write -----------------------------------------


def test_no_agent_tool_list_reaches_a_memory_write() -> None:
    offenders = []
    for path in _agent_files():
        fields = _frontmatter(path.read_text(encoding="utf-8"))
        writes = _memory_writes(_names(fields.get("tools", "")))
        if writes:
            offenders.append(f"{path.name}: {writes}")
    assert not offenders, (
        "an agent's tools: list reaches a memory write; memory is read through the read "
        f"tools and written through the proposal ledger (issue #664, finding 6): {offenders}"
    )


def test_an_agent_that_reads_memory_also_refuses_the_writes() -> None:
    """The convention the memory-reading siblings hold: reads in ``tools:``, the three
    write tools named in ``disallowedTools:``."""
    offenders = []
    for path in _agent_files():
        fields = _frontmatter(path.read_text(encoding="utf-8"))
        if not _memory_reads(_names(fields.get("tools", ""))):
            continue
        refused = {
            name.rsplit("__", 1)[-1]
            for name in _refused_writes(_names(fields.get("disallowedTools", "")))
        }
        if not set(_MEMORY_WRITE_REFUSALS) <= refused:
            offenders.append(f"{path.name}: refuses {sorted(refused)}")
    assert not offenders, (
        "an agent that reads memory does not name the memory writes it refuses "
        f"(issue #664, finding 6): {offenders}"
    )


def test_implementer_refuses_the_memory_writes_by_name() -> None:
    """The finding's own ask: the implementer names the writes it refuses, as its
    siblings do, beside its explicit ``tools:`` list."""
    fields = _frontmatter((AGENTS_DIR / "codanna-implementer.md").read_text(encoding="utf-8"))
    refused = {
        name.rsplit("__", 1)[-1]
        for name in _refused_writes(_names(fields.get("disallowedTools", "")))
    }
    assert set(_MEMORY_WRITE_REFUSALS) <= refused, (
        "codanna-implementer.md does not refuse the memory write tools "
        f"(issue #664, finding 6): names {sorted(refused)}"
    )


@pytest.mark.parametrize(
    ("name", "is_write"),
    [
        ("mcp__muninndb-benchweave__muninn_remember", True),
        ("mcp__muninndb-benchweave__muninn_remember_tree", True),
        ("mcp__muninndb-benchweave__muninn_evolve", True),
        ("mcp__muninndb__muninn_forget", True),
        ("mcp__muninndb-benchweave__muninn_new_verb", True),
        ("mcp__muninndb-benchweave__muninn_recall", False),
        ("mcp__muninndb-benchweave__muninn_where_left_off", False),
        ("mcp__codanna__find_symbol", False),
        ("Read", False),
    ],
    ids=[
        "remember",
        "remember-tree",
        "evolve",
        "other-server-forget",
        "unknown-verb",
        "recall",
        "where-left-off",
        "other-server",
        "builtin",
    ],
)
def test_memory_write_names_are_read_by_verb(name: str, is_write: bool) -> None:
    """Arm 3's detection power: an unknown memory verb counts as a write."""
    assert bool(_memory_writes([name])) is is_write


def test_tamper_a_memory_write_in_a_tool_list_is_seen() -> None:
    """Arm 3's detection power on a frontmatter shape: the write is found in ``tools:``
    and absent when the list carries a read only."""
    tainted = "---\nname: a\ntools: Read, mcp__muninndb-benchweave__muninn_remember\n---\n"
    clean = "---\nname: a\ntools: Read, mcp__muninndb-benchweave__muninn_recall\n---\n"
    assert _memory_writes(_names(_frontmatter(tainted)["tools"])) == [
        "mcp__muninndb-benchweave__muninn_remember"
    ]
    assert _memory_writes(_names(_frontmatter(clean)["tools"])) == []


def test_frontmatter_lists_read_every_shape_the_agents_use() -> None:
    """The readers behind arms 2 and 3, on the four list shapes in ``.claude/agents/``."""
    text = (
        "---\n"
        "name: a\n"
        "description: >-\n"
        "  tools: not a key, a scalar line\n"
        'tools: ["Read", "Grep"]\n'
        "disallowedTools: []\n"
        "skills:\n"
        "  - x-ray\n"
        "  - 'graph'\n"
        "---\n"
        "tools: body text\n"
    )
    fields = _frontmatter(text)
    assert fields["name"] == "a"
    assert "not a key, a scalar line" not in fields.values()
    assert _names(fields["tools"]) == ["Read", "Grep"]
    assert _names(fields["disallowedTools"]) == []
    assert _block_list(text, "skills") == ["x-ray", "graph"]
    assert _names(_frontmatter("---\nname: a\ndisallowedTools: \n---\n")["disallowedTools"]) == []
    assert _names("Read, Grep, Glob, Bash") == ["Read", "Grep", "Glob", "Bash"]
