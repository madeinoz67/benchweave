"""Website version-stamp contract (issue #188, design 2026-09-24, CON-13).

`website/index.html` is the one public surface that states corpus and SDK
versions in prose. The stamp contract (design §2, invariants CON-13): the
source carries `{{stg-<key>}}` tokens and never a version literal — every
version claim renders from the standards manifest at assembly time, so a
bump moves no website byte and a stale claim is structurally impossible.

The stamp map reads the same authorities the compatibility matrix renders
from (CON-12's chain: the standards manifest and its `sdk_compatibility`
mirror), so the two surfaces agree by construction, not by sweep. Mutations
below operate on copies; the committed source is never written.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]

SOURCE = ROOT / "website" / "index.html"
SEMVER_RE = re.compile(r"\d+\.\d+\.\d+")
TOKEN_RE = re.compile(r"\{\{stg-([a-z0-9-]+)\}\}")


def _assembler() -> Any:
    path = ROOT / "scripts" / "assemble_docs_site.py"
    spec = importlib.util.spec_from_file_location("assemble_docs_site", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hand_stamped_versions(text: str) -> list[str]:
    """Every three-component version literal as `<line>:<literal>` (1-based)."""
    return [
        f"{number}:{match}"
        for number, line in enumerate(text.splitlines(), start=1)
        for match in SEMVER_RE.findall(line)
    ]


def _tokens(text: str) -> list[str]:
    """Every stamp token occurrence in order, as its map key (`stg-<id>`)."""
    return [f"stg-{key}" for key in TOKEN_RE.findall(text)]


def _spec_cards(html: str) -> list[str]:
    """The standards panel's spec cards, one chunk per card.

    A markup refactor that hides the panel or its cards fails loudly here
    (design risk R4: any scanner miss is a red test, never a silent pass).
    """
    start = html.index('<section class="panel" id="panel-standards">')
    panel = html[start : html.index("</section>", start)]
    cards = panel.split('<div class="spec-card">')[1:]
    assert cards, "no spec card found in the standards panel — scanner blind"
    return cards


def _assert_cards_agree(html: str) -> None:
    """T4's scanner: each card carries exactly one token, exactly twice."""
    for card in _spec_cards(html):
        tokens = _tokens(card)
        assert len(tokens) == 2, f"card does not carry one token twice: {tokens}"
        assert len(set(tokens)) == 1, f"card mixes tokens: {sorted(set(tokens))}"


def test_source_carries_no_version_literals() -> None:
    """T2, the issue #188 RED vehicle: version claims are stamp tokens.

    A three-component literal in the source is a hand-stamped claim that no
    bump train moves and no gate sees (the design's root cause: the site's
    link checker resolves against copy-never-move history, so a stale-version
    href passes). On the pre-fix tree this failed naming the filed 14
    occurrences on their 13 lines.
    """
    hits = _hand_stamped_versions(SOURCE.read_text(encoding="utf-8"))
    assert not hits, (
        "hand-stamped version literal(s) in website/index.html — version claims "
        "are {{stg-*}} tokens derived at assembly (CON-13): " + ", ".join(hits)
    )


def test_stamp_map_derives_from_committed_state() -> None:
    """T1: the map is the manifest's actives plus the mirror — nothing hardcoded."""
    from benchweave.standards.manifest import load_manifest, load_sdk_compatibility

    expected = {f"stg-{entry.id}": entry.version for entry in load_manifest(ROOT).standards}
    expected["stg-sdk"] = load_sdk_compatibility(ROOT).sdk
    assert _assembler().website_stamp_map(ROOT) == expected


def test_token_coverage_is_exact_in_both_directions() -> None:
    """T3: every token maps, every map key is used (R3 — fail-closed both ways:
    a new standard admission reddens the site until a card exists, and an
    unknown token can never pass for a claim)."""
    stamps = _assembler().website_stamp_map(ROOT)
    tokens = set(_tokens(SOURCE.read_text(encoding="utf-8")))
    unmapped = sorted(tokens - set(stamps))
    unused = sorted(set(stamps) - tokens)
    assert not unmapped, f"token(s) with no map entry: {unmapped}"
    assert not unused, f"map key(s) no website token carries: {unused}"


def test_each_standards_card_carries_one_token_twice() -> None:
    """T4: a card's badge and link are ONE token — a claim disagreeing with
    its own href is unrepresentable at the value level."""
    html = SOURCE.read_text(encoding="utf-8")
    _assert_cards_agree(html)
    card_tokens = {token for card in _spec_cards(html) for token in set(_tokens(card))}
    stamps = _assembler().website_stamp_map(ROOT)
    assert card_tokens == set(stamps) - {"stg-sdk"}, (
        "the standards panel must carry exactly the manifest's standards"
    )


def test_tamper_literal_badge_is_detected() -> None:
    """T5a: reintroducing a hand-stamped literal reddens the hygiene arm (T2)."""
    text = SOURCE.read_text(encoding="utf-8").replace("v{{stg-otdp}}", "v0.1.0", 1)
    hits = _hand_stamped_versions(text)
    assert len(hits) == 1 and hits[0].endswith(":0.1.0"), hits


def test_tamper_cross_card_badge_is_detected() -> None:
    """T5b: swapping a badge token for another standard's reddens T4."""
    text = SOURCE.read_text(encoding="utf-8").replace("v{{stg-otdp}}", "v{{stg-registry}}", 1)
    with pytest.raises(AssertionError, match="card mixes tokens"):
        _assert_cards_agree(text)


def test_tamper_unknown_token_is_detected(tmp_path: Path) -> None:
    """T5c: an injected unknown token reddens T3's unmapped arm, and the
    assembler refuses it with its machine prefix."""
    text = SOURCE.read_text(encoding="utf-8").replace(
        "v{{stg-otdp}}", "v{{stg-otdp}}{{stg-nope}}", 1
    )
    stamps = _assembler().website_stamp_map(ROOT)
    assert sorted(set(_tokens(text)) - set(stamps)) == ["stg-nope"]
    copy = tmp_path / "index.html"
    copy.write_text(text, encoding="utf-8")
    with pytest.raises(SystemExit, match="stamp_unmapped_token:"):
        _assembler().stamp_website(copy, stamps)


def test_tamper_whole_card_restamp_is_detected(tmp_path: Path) -> None:
    """T5d: restamping a whole card with the wrong standard's token (x2)
    reddens T3's unused-key arm, and the assembler refuses with its prefix."""
    text = SOURCE.read_text(encoding="utf-8").replace("{{stg-registry}}", "{{stg-execution}}")
    stamps = _assembler().website_stamp_map(ROOT)
    assert sorted(set(stamps) - set(_tokens(text))) == ["stg-registry"]
    copy = tmp_path / "index.html"
    copy.write_text(text, encoding="utf-8")
    with pytest.raises(SystemExit, match="stamp_unused_key:"):
        _assembler().stamp_website(copy, stamps)


def test_stamped_output_carries_the_active_versions(tmp_path: Path) -> None:
    """T6: stamping the real source yields zero residue, the manifest's
    actives at every claim-site, and hrefs that resolve against the in-tree
    corpus — the frozen-history loophole closed by tokenisation."""
    from benchweave.standards.manifest import load_manifest, load_sdk_compatibility

    assembler = _assembler()
    stamps = assembler.website_stamp_map(ROOT)
    copy = tmp_path / "index.html"
    copy.write_text(SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
    assembler.stamp_website(copy, stamps)
    stamped = copy.read_text(encoding="utf-8")

    assert "{{stg-" not in stamped, "unstamped token residue in the assembled copy"

    for entry in load_manifest(ROOT).standards:
        assert f"v{entry.version}" in stamped, f"{entry.id} badge missing its active version"
        assert f"/{entry.id}/{entry.version}" in stamped, f"{entry.id} link missing it"
    compatibility = load_sdk_compatibility(ROOT)
    assert f"SDK {compatibility.sdk} · OTDP {stamps['stg-otdp']} baseline" in stamped

    for standard_id, version, page in re.findall(
        r'href="docs/standards/([a-z-]+)/([0-9.]+)/([a-z-]+)\.html"', stamped
    ):
        source = ROOT / "standards" / standard_id / version
        assert source.is_dir(), f"href names no in-tree version: {standard_id}/{version}"
        candidates = [source / f"{page}.md"]
        if page == "overview":  # README.md is the primary prose some standards keep
            candidates.append(source / "README.md")
        assert any(p.is_file() for p in candidates), (
            f"{standard_id}/{version}/{page}.html has no prose source in the tree"
        )
    preview = stamps["stg-plugin-ui-preview"]
    assert (ROOT / "standards" / "plugin-ui-preview" / preview).is_dir(), (
        "the GitHub href names no in-tree plugin-ui-preview version"
    )


def _minimal_dest(tmp_path: Path, index_html: str) -> Path:
    """A verify_tree-shaped artifact root around the given index.html.

    Every file verify_tree requires exists as a stub and every relative
    ``docs/`` href the index names is materialised, so the sweep's verdict
    isolates the stamp behaviour (design §2.3's residue arm; the full sweep
    runs again in CI's docs workflow against the real assembly).
    """
    assembler = _assembler()
    dest = tmp_path / "site"
    (dest / "assets").mkdir(parents=True)
    for name in ("logo.svg", "styles.css", "site.js"):
        (dest / "assets" / name).write_text("", encoding="utf-8")
    docs = dest / "docs"
    docs.mkdir()
    for rel in (
        "index.html",
        "reference/cli/index.html",
        "standards/index.html",
        "standards/otdp/0.2.0/otdp-runtime.schema.json",  # verify_tree's frozen probe
        "user-guide/changelog.html",
        "llms.txt",
        "llms-full.txt",
    ):
        path = docs / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    (docs / "index.html").write_text(assembler.SITE_LINK_MARKER, encoding="utf-8")
    for link in sorted(set(re.findall(r'href="(docs/[^"#]*)"', index_html))):
        target = dest / link
        if link.endswith("/"):
            target = target / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("", encoding="utf-8")
    # the footer's bare docs/ link re-creates docs/index.html as an empty stub
    # above — restore the marker so exactly one docs page links home
    (docs / "index.html").write_text(assembler.SITE_LINK_MARKER, encoding="utf-8")
    (dest / "index.html").write_text(index_html, encoding="utf-8")
    return dest


def test_verify_tree_green_on_a_stamped_artifact(tmp_path: Path) -> None:
    """GREEN-2's sweep: a stamped artifact root passes verify_tree whole."""
    assembler = _assembler()
    copy = tmp_path / "index.html"
    copy.write_text(SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
    assembler.stamp_website(copy, assembler.website_stamp_map(ROOT))
    stamped = copy.read_text(encoding="utf-8")
    assembler.verify_tree(_minimal_dest(tmp_path, stamped), paths={})


def test_verify_tree_refuses_stamp_residue(tmp_path: Path) -> None:
    """R1's guard: an unresolved token in the artifact is a loud scar, never a
    shipped lie — verify_tree refuses it with its machine prefix."""
    assembler = _assembler()
    dest = _minimal_dest(tmp_path, SOURCE.read_text(encoding="utf-8"))
    with pytest.raises(SystemExit, match="stamp_residue:"):
        assembler.verify_tree(dest, paths={})
