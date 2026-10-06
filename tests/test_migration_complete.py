"""AR-D2: deletion completeness — zero references to the removed surfaces.

The hand-rolled stack (the ``benchweave`` web package, the stdio MCP server
module, and the ``plugins`` package) is gone; nothing under version control
may still instruct a reader, an import, or a tool to reach for it. The one
excluded tree is ``.claude/deep-review/`` — the migration's design records,
which name the removed surfaces as their subject (anything else under
``.claude/`` is still scanned).

The forbidden tokens are assembled by concatenation so that this file's own
source cannot match them.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Dotted (import) and slashed (path/prose) spellings of each removed
#: surface, joined at assert time so the literals never appear here.
REMOVED_SURFACE_TOKENS = [
    "benchweave" + "." + "web",
    "benchweave" + "/" + "web",
    "benchweave" + "." + "mcp_server",
    "benchweave" + "/" + "mcp_server",
    "plugins" + "." + "adc_6ch_12bit",
    "plugins" + "/" + "adc_6ch_12bit",
]

#: The migration's design records document the removed surfaces by name;
#: that tree is excluded rather than rewritten to amnesia. Everything else
#: under ``.claude/`` is scanned like the rest of the repo.
EXCLUDED_PREFIXES = (".claude/deep-review/",)


def _tracked_files() -> list[Path]:
    listing = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [
        REPO_ROOT / name
        for name in listing.splitlines()
        if not name.startswith(EXCLUDED_PREFIXES) and (REPO_ROOT / name).is_file()
    ]


def test_no_references_to_removed_surfaces() -> None:
    pattern = re.compile("|".join(re.escape(token) for token in REMOVED_SURFACE_TOKENS))
    offenders: list[str] = []
    for path in _tracked_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary artifacts are out of scope
        for line_number, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_number}: {line.strip()}")
    assert not offenders, "references to removed surfaces remain:\n" + "\n".join(offenders)
