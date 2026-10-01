"""The docs site's generated standards-CLI page (issue #291, design section 3).

`python -m benchweave.standards` is an argparse sibling the site's CLI
reference cannot see (it introspects the Click tree), so the assembly
GENERATES the page from the captured `--help` at build time — generated
beats hand-written, or the page would be exactly the hand-written verb list
obligation 23 exists to kill. These tests pin the generation:

- T1 — the rendered page carries every pinned verb plus its one-liner
  fragment and the provenance marker, BIDIRECTIONALLY: the page's verb SET
  must equal the pin exactly (refute fold F2 — a subset-only check is
  stale-silent about a verb ADDED to the family). Adding or removing a
  verb anywhere reddens this pin: that red is the tripwire doing its job,
  not noise.
- T2 — the renderer is fail-closed: an empty or garbage capture refuses
  (``standards_cli_help_unparsed:``), so the page cannot exist in an
  empty or silently-degraded state.
- T3 — the wiring: ``site_paths()`` carries the generated mapping (so
  ``verify_tree`` pins the rendered page's presence) and great-docs.yml
  lists the staged name in the Guides section.
- T5 — the silent-shrink discriminator: a doctored capture with one verb
  deleted is internally consistent, so it RENDERS (T2 does not fire) and
  the PIN is what fails — proving the pin, not the parser, catches silent
  shrinkage. T5b is the mirror arm for silent GROWTH. T2 and T5 are the
  pair; either alone proves the wrong thing.
- T6 — the capture's subprocess environment is CONSTRUCTED, not inherited:
  a PYTHONPATH shadow package never reaches the capture (refute fold F3).
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
    """Remove one verb CONSISTENTLY (choices line, detail row) so the doctored
    capture is internally consistent and the renderer accepts it.

    The deletion is token-boundary-safe: a bare substring delete would
    corrupt neighbours ("pin" would mangle "repin"). "why" — T5's choice —
    is additionally safe (no other pinned verb contains it), but the
    boundary discipline holds for any verb choice.
    """
    out: list[str] = []
    for line in capture.splitlines():
        if re.match(rf"^    {verb}\s{{2,}}", line):
            continue  # the detail row
        line = re.sub(rf",{verb}\b", "", line)
        line = re.sub(rf"\b{verb},", "", line)
        out.append(line)
    return "\n".join(out)


def _add_verb(capture: str, verb: str, one_liner: str) -> str:
    """Add one verb CONSISTENTLY (choices line + a detail row) — the
    silent-GROWTH doctoring shape of refute lane 1."""
    out: list[str] = []
    for line in capture.splitlines():
        if re.match(r"^\s*\{[a-z][a-z0-9_,]*\}\s*$", line):
            out.append(line.rstrip()[:-1] + f",{verb}}}")
            out.append(f"    {verb}              {one_liner}")
            continue
        out.append(line)
    return "\n".join(out)


def _rendered_verbs(page: str) -> set[str]:
    """The verb set as the PAGE's table carries it (parsed back out)."""
    return set(re.findall(r"^\| `([a-z][a-z0-9_]*)` \|", page, re.MULTILINE))


def test_t1_the_pin_every_pinned_verb_and_fragment_renders() -> None:
    page = _asm.render_standards_cli_page(_asm.capture_standards_help())
    for verb, fragment in PINNED_VERBS.items():
        assert f"`{verb}`" in page, f"pinned verb missing from the table: {verb}"
        assert fragment in page, f"pinned one-liner fragment missing for {verb}: {fragment}"
    assert PROVENANCE in page, "the page must carry its generation provenance"
    assert "```text" in page, "the verbatim --help block must be present"
    # Bidirectional (refute fold F2): the page's set must EQUAL the pin — a
    # subset check is stale-silent about a verb the family grew.
    rendered = _rendered_verbs(page)
    assert rendered == set(PINNED_VERBS), (
        f"the page's verb set must equal the pin exactly: "
        f"missing={sorted(set(PINNED_VERBS) - rendered)} "
        f"extra={sorted(rendered - set(PINNED_VERBS))}"
    )


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


def test_t5b_silent_growth_discriminator_the_set_equality_not_the_parser() -> None:
    # Refute fold F2, mirror arm: a GROWN 10-verb capture (lane 1's shape)
    # renders — internally consistent, T2 silent — and passed the OLD
    # subset-only pin (pre-fix evidence: 'missing pinned verbs: NONE' at
    # rendered-set size 10). The set-equality is what catches the growth.
    grown = _add_verb(_asm.capture_standards_help(), "describe", "a refute-lane probe verb")
    page = _asm.render_standards_cli_page(grown)
    assert "`export`" in page
    assert "`describe`" in page
    with pytest.raises(AssertionError, match="extra"):
        rendered = _rendered_verbs(page)
        assert rendered == set(PINNED_VERBS), (
            f"the page's verb set must equal the pin exactly: "
            f"missing={sorted(set(PINNED_VERBS) - rendered)} "
            f"extra={sorted(rendered - set(PINNED_VERBS))}"
        )


def test_t6_capture_env_is_constructed_no_shadow_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Refute fold F3: an inherited-with-overrides env would forward a
    # PYTHONPATH that shadows the real package. The capture's env is
    # CONSTRUCTED, so a shadow package never reaches the subprocess: with
    # the leak present this capture would run the shadow's __main__ (exit
    # 3) and refuse; with it closed the REAL help renders.
    shadow = tmp_path / "shadow"
    (shadow / "benchweave").mkdir(parents=True)
    (shadow / "benchweave" / "__init__.py").write_text("", encoding="utf-8")
    (shadow / "benchweave" / "standards").mkdir()
    (shadow / "benchweave" / "standards" / "__init__.py").write_text("", encoding="utf-8")
    (shadow / "benchweave" / "standards" / "__main__.py").write_text(
        "raise SystemExit(3)\n", encoding="utf-8"
    )
    monkeypatch.setenv("PYTHONPATH", str(shadow))
    page = _asm.render_standards_cli_page(_asm.capture_standards_help())
    assert "`export`" in page, "the capture must see the real tree, not a PYTHONPATH shadow"
