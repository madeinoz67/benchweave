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
import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]

SOURCE = ROOT / "website" / "index.html"
SEMVER_RE = re.compile(r"\d+\.\d+\.\d+")
TOKEN_RE = re.compile(r"\{\{stg-([a-z0-9-]+)\}\}")
BRACES = "{{"


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


def _class11_literal_hits(root: Path | None = None) -> list[str]:
    """Three-component literals over the class-11 source set, `path:line:literal`.

    The hygiene ban's scope (review fold F2): every file under `website/` plus
    `index.qmd` — a literal in an asset file or the docs landing page is the
    same unmoved, unseen hand-stamp as one in the index.
    """
    tree = root if root is not None else ROOT
    files = sorted(p for p in (tree / "website").rglob("*") if p.is_file())
    index_qmd = tree / "index.qmd"
    if index_qmd.is_file():
        files.append(index_qmd)
    hits: list[str] = []
    for path in files:
        rel = path.relative_to(tree).as_posix()
        hits += [f"{rel}:{hit}" for hit in _hand_stamped_versions(path.read_text(encoding="utf-8"))]
    return hits


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
    occurrences on their 13 lines. The ban's scope is the class-11 source set
    — every file under `website/` plus `index.qmd` (review fold F2: the
    index-only ban let a literal anywhere else ship green); widening it
    reddened `index.qmd`'s `interface 0.1.0` live claim, reworded in the same
    slice. Two-component prose claims (`Python 3.13+`, `Architecture v1.5`)
    sit outside the pattern — design deferral 5.
    """
    hits = _class11_literal_hits()
    assert not hits, (
        "hand-stamped version literal(s) in the class-11 source set (website/ tree, "
        "index.qmd) — version claims are {{stg-*}} tokens derived at assembly "
        "(CON-13): " + ", ".join(hits)
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


def test_tamper_asset_file_literal_is_detected(tmp_path: Path) -> None:
    """F2's scope vehicle: a three-component literal in a website asset file is
    the same hand-stamp as one in the index — the class-11 scan reddens it
    (the index-only scan this replaces could not see it; like T5a, this pins
    the scanner's detection power, while T2 itself is the green pin on the
    real tree)."""
    root = tmp_path / "tree"
    shutil.copytree(ROOT / "website", root / "website")
    site_js = root / "website" / "assets" / "site.js"
    site_js.write_text(site_js.read_text(encoding="utf-8") + "\n/* v0.9.9 */\n", encoding="utf-8")
    hits = _class11_literal_hits(root)
    assert (
        len(hits) == 1
        and hits[0].startswith("website/assets/site.js:")
        and hits[0].endswith(":0.9.9")
    ), hits


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


# ── the `{{` residue class (adversary F1) ────────────────────────────────────
#
# The token grammar is well-formed-only, so a case-variant (`{{stg-Adapter}}`),
# nested (`{{stg-{{stg-otdp}}}}`) or unterminated (`{{stg-otdp} Y`) delimiter,
# and any `{{` in a non-index file, match nothing and ship raw with every
# grammar-keyed gate green. The delimiter itself — not the grammar — is the
# residue signal: the source pin refuses any `{{` under `website/` except
# well-formed tokens in `index.html`, and verify_tree refuses any `{{` in any
# copied static-site file.


def _stray_braces(text: str, *, tokens_allowed: bool) -> list[str]:
    """Every `{{` occurrence that is not a well-formed stamp token start.

    With ``tokens_allowed`` false, every `{{` is stray (non-index files carry
    no tokens at all). Reported as 1-based `line:column` positions.
    """
    stray: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        column = line.find(BRACES)
        while column != -1:
            if not tokens_allowed or TOKEN_RE.match(line, column) is None:
                stray.append(f"{number}:{column + 1}")
            column = line.find(BRACES, column + 1)
    return stray


def _website_brace_violations(root: Path | None = None) -> list[str]:
    """Stray `{{` anywhere under a `website/` tree, as `path:line:column`."""
    tree = root if root is not None else ROOT / "website"
    violations: list[str] = []
    for path in sorted(p for p in tree.rglob("*") if p.is_file()):
        rel = path.relative_to(tree).as_posix()
        text = path.read_text(encoding="utf-8")
        for site in _stray_braces(text, tokens_allowed=rel == "index.html"):
            violations.append(f"{rel}:{site}")
    return violations


def _stamped_text(tmp_path: Path, text: str) -> str:
    """Stamp a copy of the given source text and return the stamped bytes."""
    assembler = _assembler()
    copy = tmp_path / "to-stamp.html"
    copy.write_text(text, encoding="utf-8")
    assembler.stamp_website(copy, assembler.website_stamp_map(ROOT))
    return copy.read_text(encoding="utf-8")


def test_website_source_braces_are_tokens_in_index_only() -> None:
    """The `{{` delimiter exists nowhere under `website/` except as
    well-formed tokens in `index.html` — a malformed or misplaced token is a
    residue at the source, not just in the assembled artifact."""
    violations = _website_brace_violations()
    assert not violations, (
        "stray `{{` delimiter(s) in website/ (only index.html carries tokens, "
        "well-formed): " + ", ".join(violations)
    )


def test_tamper_case_variant_token_is_detected(tmp_path: Path) -> None:
    """F1 vehicle 1: `{{stg-Adapter}}` matches no grammar — the braces pin
    flags it at source and verify_tree refuses its raw delimiter in the
    assembled tree (the stamper is grammar-keyed and leaves it untouched)."""
    text = SOURCE.read_text(encoding="utf-8").replace(
        "OTDP {{stg-otdp}} baseline", "OTDP {{stg-otdp}} baseline · AD {{stg-Adapter}}", 1
    )
    assert _stray_braces(text, tokens_allowed=True), "case-variant token invisible at source"
    with pytest.raises(SystemExit, match="stamp_residue:"):
        _assembler().verify_tree(_minimal_dest(tmp_path, _stamped_text(tmp_path, text)), paths={})


def test_tamper_nested_token_is_detected(tmp_path: Path) -> None:
    """F1 vehicle 2: `{{stg-{{stg-otdp}}}}` — the stamper substitutes the inner
    token and ships `{{stg-<version>}}`; the source pin flags the outer `{{`
    and verify_tree refuses the delimiter the grammar cannot even see."""
    text = SOURCE.read_text(encoding="utf-8").replace(
        "v{{stg-otdp}}", "v{{stg-{{stg-otdp}}}}", 1
    )
    assert _stray_braces(text, tokens_allowed=True), "nested token invisible at source"
    stamped = _stamped_text(tmp_path, text)
    assert BRACES in stamped, "expected the inner-only substitution to leave the outer delimiter"
    with pytest.raises(SystemExit, match="stamp_residue:"):
        _assembler().verify_tree(_minimal_dest(tmp_path, stamped), paths={})


def test_tamper_missing_brace_is_detected(tmp_path: Path) -> None:
    """F1 vehicle 3: `{{stg-otdp} Y` matches nothing, stamps nothing — the
    braces pin flags it and verify_tree refuses the shipped delimiter."""
    text = SOURCE.read_text(encoding="utf-8").replace(
        "OTDP {{stg-otdp}} baseline", "OTDP {{stg-otdp}} baseline · X {{stg-otdp} Y", 1
    )
    assert _stray_braces(text, tokens_allowed=True), "unterminated token invisible at source"
    with pytest.raises(SystemExit, match="stamp_residue:"):
        _assembler().verify_tree(_minimal_dest(tmp_path, _stamped_text(tmp_path, text)), paths={})


def test_tamper_asset_file_token_is_detected(tmp_path: Path) -> None:
    """F1 vehicle 4: a token in `assets/site.js` never reaches the stamper
    (index-only) — the source pin refuses any `{{` outside index.html and
    verify_tree sweeps every copied static-site file, not just the index."""
    tree = tmp_path / "website"
    shutil.copytree(ROOT / "website", tree)
    (tree / "assets" / "site.js").write_text("/* {{stg-otdp}} */\n", encoding="utf-8")
    assert _website_brace_violations(tree), "non-index token invisible at source"

    stamped = _stamped_text(tmp_path, SOURCE.read_text(encoding="utf-8"))
    dest = _minimal_dest(tmp_path / "site-root", stamped)
    (dest / "assets" / "site.js").write_text("/* {{stg-otdp}} */\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="stamp_residue:"):
        _assembler().verify_tree(dest, paths={})


# ── the reserved stamp namespace (adversary F4) ──────────────────────────────


def _fake_root(tmp_path: Path, entry_id: str) -> Path:
    """A minimal tree whose standards manifest carries one `<entry_id>` entry.

    Only the loaders' closed-world shape is exercised (no file existence
    checks fire from `website_stamp_map`), so the fake names no real files.
    """
    root = tmp_path / f"root-{entry_id}"
    (root / "standards").mkdir(parents=True)
    (root / "standards" / "standards-manifest.json").write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "standards": [
                    {
                        "id": entry_id,
                        "version": "9.9.9",
                        "status": "stable",
                        "released": "2026-01-01",
                        "normative": [f"standards/{entry_id}/9.9.9/x.md"],
                    }
                ],
                "sdk_compatibility": {"sdk": "0.2.0", "main_project": ">=0.1.0", "notes": None},
            }
        ),
        encoding="utf-8",
    )
    return root


def test_stamp_map_refuses_a_manifest_id_colliding_with_the_reserved_key(
    tmp_path: Path,
) -> None:
    """F4: a manifest entry id `sdk` would silently shadow the
    sdk_compatibility-derived `stg-sdk` key (the mirror overwrites the entry's
    value) and be invisible to every coverage arm — the map refuses the
    collision with its own machine prefix instead."""
    with pytest.raises(SystemExit, match="stamp_reserved_key:"):
        _assembler().website_stamp_map(_fake_root(tmp_path, "sdk"))


def test_stamp_map_control_unknown_id_reaches_the_unused_key_arm(tmp_path: Path) -> None:
    """F4 control: a merely-unknown manifest id (`frob`) maps without refusal,
    and an unused key reddens at the stamp site exactly as before — the
    reserved-key refusal fires only on the colliding key, not on every new
    standard."""
    assembler = _assembler()
    assert assembler.website_stamp_map(_fake_root(tmp_path, "frob")) == {
        "stg-frob": "9.9.9",
        "stg-sdk": "0.2.0",
    }
    stamps = assembler.website_stamp_map(ROOT) | {"stg-frob": "9.9.9"}
    copy = tmp_path / "index.html"
    copy.write_text(SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(SystemExit, match="stamp_unused_key:"):
        assembler.stamp_website(copy, stamps)
