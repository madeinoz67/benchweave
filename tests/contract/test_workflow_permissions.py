"""Executable pin for issue #509: PR-reachable jobs hold no Pages/OIDC write scope.

The reader is stdlib-only and line-oriented on purpose: PyYAML is only a
transitive lock entry today, and declaring it would turn this permission pin
into a dependency-change diff (design record §5,
``.claude/deep-review/2026-10-21-issue509-docs-permissions.md``). It structures
exactly the shapes the repository's root workflow files use and REFUSES
anything else — a shape it cannot structure is a refusal naming ``path:line``,
never a silent skip. Over-approximation is the safe direction throughout: an
``if:`` expression whose PR-exclusion cannot be proven counts the job as
PR-reachable. Exclusion is proven ONLY by exact conjunct equality — every
top-level ``||`` alternative of an ``if:`` expression must be a ``&&``
conjunction of the recognized forms, never substring containment (fold F1 of
the review wave: the first shipped prover matched by substring and falsely
excluded ``!(...)``-negated and parenthesised-disjunction guards, both of
which are true on PRs).

What this check does NOT catch (design §5, stated guard): write scopes other
than ``pages``/``id-token`` on PR runs (``security-events`` has a legitimate
PR use — codeql.yml's SARIF upload); grants on push-, dispatch-, release- and
schedule-triggered runs; third-party action internals (the SHA-pinning
discipline owns that surface); the submodule's workflows (the SDK owns its own
twin and may be absent); and the repo-default token posture for jobs that
declare no permissions block anywhere (ci.yml's unlabeled jobs ride the
repository default — design deferral D4, not silently missed).
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

PINNED_SCOPES = ("pages", "id-token")

# Permission blocks are recognized ONLY as block mappings of
# ``scope: read|write|none`` lines. Flow maps (``{...}``) and scalar forms
# (``read-all``) are refusals, not parses.
_PERMISSION_LINE = re.compile(r"^([a-z][a-z0-9-]*):\s*(read|write|none)$")
_KEY_LINE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")

# An ``if:`` expression PROVABLY excludes pull_request events only when every
# top-level ``||`` alternative is a ``&&`` conjunction of these EXACT forms
# (equality after whitespace normalization — never substring containment: a
# form under negation or inside a nested disjunction proves nothing, fold F1).
# Everything unprovable counts as reachable — a false "reachable" fails loudly
# and gets reasoned about; a false "unreachable" would hide a grant.
_RECOGNIZED_EXCLUSIONS = (
    "github.event_name == 'push'",
    "github.ref == 'refs/heads/main'",
    "github.event_name != 'pull_request'",
    "github.event_name == 'schedule'",
    "startsWith(github.event.release.tag_name, 'ui-html-v')",
)


class WorkflowRefusal(RuntimeError):
    """The reader met a workflow shape it cannot structure; fail closed."""


@dataclass(frozen=True)
class Job:
    """One job block: its ``if:`` text and its own permissions, if declared."""

    id: str
    if_expr: str | None
    permissions: dict[str, str] | None  # None = no job-level block


@dataclass(frozen=True)
class Workflow:
    """One root workflow file: trigger events, workflow permissions, jobs."""

    path: Path
    events: frozenset[str]
    permissions: dict[str, str] | None  # None = no workflow-level block
    jobs: tuple[Job, ...]


# (line number, indent, comment-stripped content) for every non-blank line.
_Entry = tuple[int, int, str]


def _refusal(path: Path, lineno: int, detail: str) -> NoReturn:
    raise WorkflowRefusal(f"{path.name}: line {lineno}: {detail}")


def _strip_outer_quotes(value: str) -> str:
    """Strip ONE balanced outer quote pair (YAML-quoted ``if:`` scalars)."""
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1].strip()
    return v


def _strip_comment(line: str) -> str:
    """Drop a trailing ``# comment`` that starts outside quotes."""
    out: list[str] = []
    quote = ""
    for i, ch in enumerate(line):
        if quote:
            out.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def _entries(path: Path) -> list[_Entry]:
    entries: list[_Entry] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if raw.startswith("\t"):
            _refusal(path, lineno, "tab-indented line")
        content = _strip_comment(raw).rstrip()
        if not content.strip():
            continue
        entries.append((lineno, len(content) - len(content.lstrip(" ")), content))
    return entries


def _split_key(content: str) -> tuple[str, str]:
    """Split ``key: value``; the value is ``""`` for the block form."""
    key, sep, value = content.partition(":")
    if not sep:
        return "", ""
    return key.strip().strip("\"'"), value.strip()


def _skip_subtree(entries: list[_Entry], i: int) -> int:
    """Index just past entry ``i`` and every entry nested under it."""
    j = i + 1
    while j < len(entries) and entries[j][1] > entries[i][1]:
        j += 1
    return j


def _parse_permissions(
    path: Path, entries: list[_Entry], i: int
) -> tuple[dict[str, str], int]:
    """Parse the block-mapping permissions starting AT entry ``i``."""
    lineno, indent, content = entries[i]
    key, value = _split_key(content)
    assert key == "permissions"
    if value:
        _refusal(
            path, lineno, f"permissions in scalar/flow form not structured: {value!r}"
        )
    scopes: dict[str, str] = {}
    j = i + 1
    while j < len(entries) and entries[j][1] > indent:
        child_lineno, child_indent, child = entries[j]
        if child_indent != indent + 2:
            _refusal(path, child_lineno, f"irregular permissions indent: {child!r}")
        match = _PERMISSION_LINE.match(child.lstrip())
        if not match:
            _refusal(path, child_lineno, f"unstructured permissions line: {child!r}")
        scopes[match.group(1)] = match.group(2)
        j += 1
    return scopes, j


def _parse_events(path: Path, entries: list[_Entry], i: int) -> tuple[frozenset[str], int]:
    """Parse the ``on:`` block or flow list starting AT entry ``i``."""
    _, indent, content = entries[i]
    key, value = _split_key(content)
    assert key == "on"
    if value:
        tokens = [t.strip().strip("\"'") for t in value.strip("[]").split(",")]
        if any(not _KEY_LINE.match(t) for t in tokens):
            _refusal(path, entries[i][0], f"unstructured flow event list: {value!r}")
        return frozenset(tokens), i + 1
    events: set[str] = set()
    j = i + 1
    child_indent = -1
    while j < len(entries) and entries[j][1] > indent:
        child_lineno, ci, child = entries[j]
        if child_indent == -1:
            child_indent = ci
        if ci > child_indent:
            # Nested config under the previous event key (e.g. push.branches).
            j = _skip_subtree(entries, j)
            continue
        if ci != child_indent:
            _refusal(path, child_lineno, f"irregular on: indent: {child!r}")
        if child.lstrip().startswith("- "):
            j = _skip_subtree(entries, j)
            continue
        event, event_value = _split_key(child)
        if not _KEY_LINE.match(event) or event_value:
            _refusal(path, child_lineno, f"unstructured event line: {child!r}")
        events.add(event)
        j += 1
    return frozenset(events), j


def _parse_jobs(path: Path, entries: list[_Entry], i: int) -> tuple[tuple[Job, ...], int]:
    """Parse the ``jobs:`` block starting AT entry ``i``."""
    _, indent, content = entries[i]
    key, value = _split_key(content)
    assert key == "jobs"
    if value:
        _refusal(path, entries[i][0], f"flow-form jobs not structured: {value!r}")
    jobs: list[Job] = []
    j = i + 1
    job_indent = -1
    while j < len(entries) and entries[j][1] > indent:
        head_lineno, ji, head = entries[j]
        if job_indent == -1:
            job_indent = ji
        if ji != job_indent:
            _refusal(path, head_lineno, f"irregular jobs: indent: {head!r}")
        if head.lstrip().startswith("- "):
            _refusal(path, head_lineno, "sequence item under jobs: not structured")
        job_id, job_value = _split_key(head)
        if not _KEY_LINE.match(job_id) or job_value:
            _refusal(path, head_lineno, f"unstructured job line: {head!r}")
        if_expr: str | None = None
        permissions: dict[str, str] | None = None
        j += 1
        body_indent = entries[j][1] if j < len(entries) and entries[j][1] > ji else -1
        while j < len(entries) and entries[j][1] > ji:
            body_lineno, bi, body = entries[j]
            if bi > body_indent > -1:
                # Nested under the current body key (e.g. a step's with: block).
                j += 1
                continue
            if bi != body_indent:
                _refusal(path, body_lineno, f"irregular job-body indent: {body!r}")
            if body.lstrip().startswith("- "):
                j = _skip_subtree(entries, j)
                continue
            bkey, bvalue = _split_key(body)
            if not _KEY_LINE.match(bkey):
                _refusal(path, body_lineno, f"unstructured job-body line: {body!r}")
            if bkey == "if":
                if_expr = _strip_outer_quotes(bvalue) or None  # block form: unprovable
            elif bkey == "permissions":
                permissions, j = _parse_permissions(path, entries, j)
                continue
            else:
                j = _skip_subtree(entries, j)
                continue
            j += 1
        jobs.append(Job(id=job_id, if_expr=if_expr, permissions=permissions))
    return tuple(jobs), j


def _parse_workflow(path: Path) -> Workflow:
    entries = _entries(path)
    events: frozenset[str] = frozenset()
    permissions: dict[str, str] | None = None
    jobs: tuple[Job, ...] = ()
    i = 0
    while i < len(entries):
        lineno, indent, content = entries[i]
        if indent != 0:
            _refusal(path, lineno, f"expected a top-level key: {content!r}")
        key, value = _split_key(content)
        if not key:
            _refusal(path, lineno, f"unstructured top-level line: {content!r}")
        if key == "on":
            events, i = _parse_events(path, entries, i)
        elif key == "permissions":
            permissions, i = _parse_permissions(path, entries, i)
        elif key == "jobs":
            jobs, i = _parse_jobs(path, entries, i)
        else:
            i = _skip_subtree(entries, i)
    return Workflow(path=path, events=events, permissions=permissions, jobs=jobs)


def _parse_workflows(directory: Path) -> list[Workflow]:
    return [_parse_workflow(p) for p in sorted(directory.glob("*.yml"))]


def _split_top_level(expr: str, operator: str) -> list[str]:
    """Split ``expr`` on ``||``/``&&`` at paren depth 0, outside quotes."""
    assert operator in ("||", "&&")
    lead = operator[0]
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    quote = ""
    i = 0
    while i < len(expr):
        ch = expr[i]
        if quote:
            current.append(ch)
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
            current.append(ch)
        elif ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == lead and depth == 0 and expr.startswith(operator, i):
            parts.append("".join(current))
            current = []
            i += 1
        else:
            current.append(ch)
        i += 1
    parts.append("".join(current))
    return parts


def _provable_pr_exclusion(if_expr: str) -> bool:
    """Exact conjunct analysis: every top-level ``||`` alternative must be a
    ``&&`` conjunction of RECOGNIZED forms, each matched by EQUALITY after
    whitespace normalization.

    Substring containment is deliberately absent (fold F1): a recognized form
    under negation (``!(...)``) or inside a nested (parenthesised) disjunction
    never equals a recognized form — parentheses and ``!`` survive
    normalization — so such guards leave the job PR-reachable, the safe
    direction. The one parenthesised recognized form is the exact in-tree
    release guard ``startsWith(github.event.release.tag_name, 'ui-html-v')``;
    a different release-tag prefix in a future guard reads reachable until it
    is added here (D3's exception register, not a silent pass).
    """
    for alternative in _split_top_level(if_expr, "||"):
        for conjunct in _split_top_level(alternative, "&&"):
            token = " ".join(conjunct.split())
            if token not in _RECOGNIZED_EXCLUSIONS:
                return False
    return True


def _pr_reachable(events: frozenset[str], if_expr: str | None) -> bool:
    """Over-approximate: PR-reachable unless exclusion is provable."""
    if "pull_request" not in events:
        return False
    if not if_expr:
        return True
    return not _provable_pr_exclusion(if_expr)


def _rule_offenders(workflows: list[Workflow]) -> list[str]:
    """The verdict: every PR-reachable job holding a pinned write scope."""
    offenders: list[str] = []
    for wf in workflows:
        for job in wf.jobs:
            if not _pr_reachable(wf.events, job.if_expr):
                continue
            if job.permissions is not None:
                effective, origin = job.permissions, "job-declared"
            else:
                effective, origin = wf.permissions or {}, "inherited from the workflow block"
            for scope in PINNED_SCOPES:
                if effective.get(scope) == "write":
                    offenders.append(
                        f"{wf.path.name}: job '{job.id}' holds {scope}: write ({origin})"
                    )
    return offenders


def test_no_pr_reachable_job_holds_pages_or_oidc_write() -> None:
    workflows = _parse_workflows(WORKFLOWS_DIR)
    assert workflows, f"no workflow files under {WORKFLOWS_DIR} — census must not be empty"
    census: list[str] = []
    for wf in workflows:
        for job in wf.jobs:
            if not _pr_reachable(wf.events, job.if_expr):
                continue
            effective = job.permissions if job.permissions is not None else wf.permissions or {}
            census.append(
                f"{wf.path.name}/{job.id}: "
                + (", ".join(f"{k}: {v}" for k, v in sorted(effective.items())) or "no block")
            )
    print(f"census: {len(workflows)} workflows, {len(census)} PR-reachable jobs")
    for line in census:
        print(f"  {line}")
    offenders = _rule_offenders(workflows)
    assert not offenders, (
        "PR-reachable jobs holding a pinned write scope (issue #509):\n  "
        + "\n  ".join(offenders)
    )


def test_reader_refuses_unstructured_permission_forms(tmp_path: Path) -> None:
    """Flow-map and read-all permission forms are refusals, never parses."""
    hostile = {
        "hostile-read-all.yml": (
            "on:\n  pull_request:\npermissions: read-all\n"
            "jobs:\n  build:\n    runs-on: ubuntu-latest\n"
        ),
        "hostile-flow-map.yml": (
            "on: [pull_request]\npermissions: {contents: read, pages: write}\n"
            "jobs:\n  build:\n    runs-on: ubuntu-latest\n"
        ),
    }
    for name, body in hostile.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
        with pytest.raises(WorkflowRefusal) as excinfo:
            _parse_workflows(tmp_path)
        assert name in str(excinfo.value)
        assert "line" in str(excinfo.value)


_HOSTILE_GUARDED = """\
name: hostile
on:
  pull_request:
permissions:
  contents: read
jobs:
  guarded:
    runs-on: ubuntu-latest
    if: {guard}
    permissions:
      pages: write
      id-token: write
    steps:
      - run: echo ok
"""


def _hostile_offenders(tmp_path: Path, guard: str) -> list[str]:
    """Offenders for one hostile workflow whose guarded job holds both scopes."""
    (tmp_path / "hostile.yml").write_text(
        _HOSTILE_GUARDED.format(guard=guard), encoding="utf-8"
    )
    return _rule_offenders(_parse_workflows(tmp_path))


def test_negated_recognised_exclusion_keeps_job_reachable(tmp_path: Path) -> None:
    """Fold F1: ``!(recognised)`` is TRUE on every PR — must stay reachable."""
    guard = '"!(github.event_name == \'schedule\')"'
    offenders = _hostile_offenders(tmp_path, guard)
    assert any("'guarded'" in o and "pages: write" in o for o in offenders), offenders


def test_parenthesised_disjunction_keeps_job_reachable(tmp_path: Path) -> None:
    """Fold F1: a nested ``||`` group with one PR-true arm — must stay reachable."""
    guard = '"(github.event_name == \'push\' || github.event_name == \'pull_request\')"'
    offenders = _hostile_offenders(tmp_path, guard)
    assert any("'guarded'" in o and "pages: write" in o for o in offenders), offenders


@pytest.mark.parametrize(
    "guard",
    [
        "github.event_name == 'push'",
        "github.event_name == 'push' && github.ref == 'refs/heads/main'",
    ],
    ids=["single-exact-form", "real-publish-docs-conjunction"],
)
def test_exact_recognised_exclusions_still_exclude(tmp_path: Path, guard: str) -> None:
    """The honest positives: exact recognized forms DO prove the exclusion."""
    assert _hostile_offenders(tmp_path, guard) == []
