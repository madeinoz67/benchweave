"""The docs site's generated standards-CLI page (issue #291, design section 3).

`python -m benchweave.standards` is an argparse sibling the site's CLI
reference cannot see (it introspects the Click tree), so the assembly
GENERATES the page from the captured `--help` at build time — generated
beats hand-written, or the page would be exactly the hand-written verb list
obligation 23 exists to kill. These tests pin the generation:

- T1 — the rendered page carries every pinned verb plus its one-liner
  fragment and the provenance marker. Adding or removing a verb anywhere
  reddens this pin: that red is the tripwire doing its job, not noise.
- T2 — the renderer is fail-closed: an empty or garbage capture refuses
  (``standards_cli_help_unparsed:``), so the page cannot exist in an
  empty or silently-degraded state.
- T3 — the wiring: ``site_paths()`` carries the generated mapping (so
  ``verify_tree`` pins the rendered page's presence) and great-docs.yml
  lists the staged name in the Guides section.
- T5 — the silent-shrink discriminator: a doctored capture with one verb
  deleted is internally consistent, so it RENDERS (T2 does not fire) and
  the PIN is what fails — proving the pin, not the parser, catches silent
  shrinkage. T2 and T5 are the pair; either alone proves the wrong thing.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _assembler() -> Any:
    path = ROOT / "scripts" / "assemble_docs_site.py"
    spec = importlib.util.spec_from_file_location("assemble_docs_site", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_asm = _assembler()

# The pinned set — the spec for the page (N = 9, the full family). The
# one-liners are FRAGMENTS, not full lines, so argparse wrapping cannot flake
# the pin (design R4). These are the only verb literals in the pair of files.
PINNED_VERBS: dict[str, str] = {
    "export": "SDK-facing bundle",
    "check": "fresh export",
    "matrix": "compatibility-matrix",
    "versions": "submodule versions",
    "repin": "corpus-manifest sha256",
    "list": "served sets",
    "pin": "constraints into its contracts/lock.json",
    "upgrade": "exactly one standard",
    "why": "the rung that fired",
}

PROVENANCE = "generated from python -m benchweave.standards --help"


def _delete_verb(capture: str, verb: str) -> str:
    """Remove one verb CONSISTENTLY (choices line, detail row, usage) so the
    doctored capture is internally consistent and the renderer accepts it."""
    out: list[str] = []
    for line in capture.splitlines():
        if re.match(rf"^    {verb}\s{{2,}}", line):
            continue  # the detail row
        out.append(line.replace(f",{verb}", "").replace(f"{verb},", ""))
    return "\n".join(out)


def test_t1_the_pin_every_pinned_verb_and_fragment_renders() -> None:
    page = _asm.render_standards_cli_page(_asm.capture_standards_help())
    for verb, fragment in PINNED_VERBS.items():
        assert f"`{verb}`" in page, f"pinned verb missing from the table: {verb}"
        assert fragment in page, f"pinned one-liner fragment missing for {verb}: {fragment}"
    assert PROVENANCE in page, "the page must carry its generation provenance"
    assert "```text" in page, "the verbatim --help block must be present"


@pytest.mark.parametrize("garbage", ["", "<garbage>"])
def test_t2_unparsable_captures_refuse(garbage: str) -> None:
    with pytest.raises(SystemExit, match="standards_cli_help_unparsed:"):
        _asm.render_standards_cli_page(garbage)


def test_t3_wiring_site_paths_and_guides_listing() -> None:
    paths = _asm.site_paths()
    assert paths.get("standards-cli.md") == "user-guide/standards-cli.html"
    yml = (ROOT / "great-docs.yml").read_text(encoding="utf-8")
    guides = yml.index('section: "Guides"')
    listed = yml.index("- standards-cli.md")
    assert listed > guides, "standards-cli.md must be listed in the Guides section"


def test_t5_silent_shrink_discriminator_the_pin_not_the_parser() -> None:
    doctored = _delete_verb(_asm.capture_standards_help(), "why")
    # The doctored capture is internally consistent: the renderer ACCEPTS it
    # (8 verbs parse fine — T2 does not fire) ...
    page = _asm.render_standards_cli_page(doctored)
    assert "`export`" in page
    assert "`why`" not in page
    # ... and the PIN is what catches the shrink.
    with pytest.raises(AssertionError, match="pinned verb missing"):
        for verb in PINNED_VERBS:
            assert f"`{verb}`" in page, f"pinned verb missing from the table: {verb}"
