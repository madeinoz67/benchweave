"""The docs site's generated device-class table (gateway issue #499).

The mockups under ``docs/internal/ui-styleguide-mockups/`` are the authored
specification for each device class, and the corpus family
``plugin-ui-class-reference`` carries one ``class-<slug>.json`` per
implemented class — but neither was published, so a new user could not see
what a class page looks like before installing anything. The assembly now
GENERATES the Device classes page (a staged page, the standards-CLI
precedent) from three committed inputs and publishes each authoring mockup
as a byte-identical preview copy. Generated beats hand-written — a
hand-kept table is exactly the drift class the issue exists to kill.

The three inputs, and the state derivation the issue pins:

- IMPLEMENTED — a ``class-<slug>.json`` in the ACTIVE family version (the
  version derives from the standards manifest, never a literal). The row
  links the mockup's published preview copy.
- PLANNED — a row in the sweep-plan record
  (``docs/internal/classref-sweep-plan.json``), which carries slug and
  sweep slot ONLY. The record never carries an "implemented" claim: state
  is derived, so a class file landing moves the row to implemented with no
  edit to the plan record (the corpus wins for a slug both carry — the
  plan is append-only by design, so parallel sweep lanes never conflict on
  one shared file).
- The preview set — the mockup glob, never a hand list. The public copy
  is a byte-identical build-time copy at ``user-guide/device-classes/``,
  beside the rendered table page.

These tests pin the generation (the standards-CLI pin's shape):

- T1 — the row set derives from the corpus and the plan, bidirectionally:
  the table's set must EQUAL corpus classes plus unlanded plan rows, or a
  class or plan row added anywhere reddens here. That red is the tripwire
  doing its job, not noise.
- T2 — the rendered page: every implemented row links its preview at the
  published URL shape, every planned row carries its sweep slot, the state
  vocabulary is closed, and the provenance marker is present.
- T3 — the reverse direction over the REAL tree: every mockup has exactly
  one row and that row is state=implemented (an orphan preview, or a
  mockup the table calls planned, fails).
- T4 — the copy is fail-closed both directions on a synthetic tree: a
  mockup without a corpus class refuses, and a corpus class without a
  mockup refuses.
- T5 — the plan loader is fail-closed: absent, malformed, over-carried or
  duplicated plan records refuse; a landed slug staying in the plan is
  VALID (append-only, the corpus wins).
- T6 — the published preview bytes equal the authoring home's bytes
  (sha256 per file), and the copied set equals the mockup glob exactly —
  the two trees cannot drift.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: The published preview URL shape: the file name beside the rendered page
#: (``user-guide/device-classes/class-<slug>.html``), linked from the page
#: as ``device-classes/class-<slug>.html``.
PREVIEW_LINK_RE = re.compile(r"^device-classes/class-(?P<slug>[a-z0-9_]+)\.html$")
PLANNED_STATE_RE = re.compile(r"^Planned \(sweep slot (?P<slot>L\d+)\)$")
PROVENANCE = (
    "generated from the class-reference corpus, the sweep plan record and the authoring mockups"
)

MANIFEST_STUB = {"manifest_version": 1, "standards": []}


def _assembler() -> Any:
    path = ROOT / "scripts" / "assemble_docs_site.py"
    spec = importlib.util.spec_from_file_location("assemble_docs_site", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_asm = _assembler()


def _mockups() -> list[str]:
    """The authoring mockup slugs, from the glob the assembly walks."""
    return sorted(
        p.name[len("class-") : -len(".html")]
        for p in (ROOT / "docs/internal/ui-styleguide-mockups").glob("class-*.html")
    )


def _corpus_class_files() -> list[str]:
    """The class-*.json file names under the family's ACTIVE version, from
    the same manifest derivation the assembly uses (never a literal), with
    the production walk's own acceptance: a file whose parsed document
    carries no ``otdp.``-prefixed ``profile_id`` is not a class (the family
    schema file matches the glob)."""
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from benchweave.standards.manifest import active_version_from_corpus
    from benchweave.vendoring import corpus_root

    version = active_version_from_corpus(corpus_root(), "plugin-ui-class-reference")
    names = []
    for path in sorted(
        (ROOT / "standards/plugin-ui-class-reference" / version).glob("class-*.json")
    ):
        document = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(document, dict) and str(
            document.get("profile_id", "")
        ).startswith("otdp."):
            names.append(path.name)
    return names


# --- the synthetic tree: every fixture name is invented -----------------------


def _synthetic_tree(tmp_path: Path, *, mockups: list[str], classes: list[str], plan: Any) -> Path:
    """A minimal repo tree for the derivation: a standards manifest naming a
    9.9.9 family version, class files, mockups and a sweep-plan record.

    ``classes`` are slugs; each gets a class file whose ``profile_id``
    follows the production acceptance (``otdp.<slug>/1.0.0``) and a
    ``title``. The family schema file is planted too — it matches the
    class glob and must be excluded (the production walk's acceptance).
    """
    root = tmp_path / "repo"
    family = root / "standards/plugin-ui-class-reference/9.9.9"
    family.mkdir(parents=True)
    manifest = dict(MANIFEST_STUB)
    manifest["standards"] = [
        {"id": "plugin-ui-class-reference", "version": "9.9.9", "status": "stable"}
    ]
    (root / "standards/standards-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (family / "class-reference.schema.json").write_text("{}", encoding="utf-8")
    for slug in classes:
        (family / f"class-{slug}.json").write_text(
            json.dumps({"profile_id": f"otdp.{slug}/1.0.0", "title": slug.replace("_", " ")}),
            encoding="utf-8",
        )
    mockup_dir = root / "docs/internal/ui-styleguide-mockups"
    mockup_dir.mkdir(parents=True)
    for slug in mockups:
        (mockup_dir / f"class-{slug}.html").write_text(
            f"<!doctype html>mock {slug}", encoding="utf-8"
        )
    if plan is not None:
        (root / "docs/internal/classref-sweep-plan.json").write_text(
            plan if isinstance(plan, str) else json.dumps(plan), encoding="utf-8"
        )
    return root


def _bind_repo(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr(_asm, "REPO", root)
    monkeypatch.setattr(_asm, "corpus_root", lambda: root / "standards")


# --- T1: the derivation, bidirectional ----------------------------------------


def test_t1_rows_derive_from_corpus_and_plan() -> None:
    rows = _asm.device_class_rows()
    corpus = {
        name[len("class-") : -len(".json")] for name in _corpus_class_files()
    }
    plan = json.loads((ROOT / "docs/internal/classref-sweep-plan.json").read_text("utf-8"))
    planned = {row["slug"] for row in plan["planned"]} - corpus
    by_slug = {row["slug"]: row for row in rows}
    assert set(by_slug) == corpus | planned, (
        f"the table's set must equal corpus classes plus unlanded plan rows: "
        f"missing={sorted((corpus | planned) - set(by_slug))} "
        f"extra={sorted(set(by_slug) - corpus - planned)}"
    )
    for slug in corpus:
        assert by_slug[slug]["state"] == "implemented", slug
    for slug in planned:
        assert by_slug[slug]["state"] == "planned", slug


def test_t1b_the_schema_file_is_not_a_class() -> None:
    slugs = {row["slug"] for row in _asm.device_class_rows()}
    assert "reference.schema" not in slugs, (
        "class-reference.schema.json matches the class glob and must be "
        "excluded by the profile_id acceptance, not shipped as a class"
    )


def test_t1c_order_is_deterministic() -> None:
    rows = _asm.device_class_rows()
    implemented = [r["slug"] for r in rows if r["state"] == "implemented"]
    planned = [r["slot"] for r in rows if r["state"] == "planned"]
    assert implemented == sorted(implemented), "implemented rows sort by slug"
    assert planned == sorted(planned, key=lambda s: int(s[1:])), (
        "planned rows order by sweep slot number"
    )


# --- T2: the rendered page -----------------------------------------------------


def _row_lines(page: str) -> list[list[str]]:
    """The table rows as split cells (the leading pipe row grammar)."""
    return [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in page.splitlines()
        if line.startswith("| `")
    ]


def test_t2_page_renders_every_row_with_resolvable_preview_links() -> None:
    page = _asm.render_device_classes_page(_asm.device_class_rows())
    assert PROVENANCE in page, "the page must carry its generation provenance"
    rows = {r["slug"]: r for r in _asm.device_class_rows()}
    seen: set[str] = set()
    for cells in _row_lines(page):
        assert len(cells) == 3, f"every row has Class, State, Preview: {cells}"
        slug = cells[0].split("`")[1]
        seen.add(slug)
        if rows[slug]["state"] == "implemented":
            assert cells[1] == "Implemented", cells
            match = re.match(r"\[Preview\]\(([^)]+)\)", cells[2])
            assert match is not None, f"implemented row links its preview: {cells}"
            assert PREVIEW_LINK_RE.match(match.group(1)) is not None, cells
            assert match.group(1) == f"device-classes/class-{slug}.html", cells
        else:
            state = PLANNED_STATE_RE.match(cells[1])
            assert state is not None, f"planned state carries its sweep slot: {cells}"
            assert state.group("slot") == rows[slug]["slot"], cells
            assert cells[2] == "Not yet available", cells
    assert seen == set(rows), (
        f"every derived row renders exactly once: missing={sorted(set(rows) - seen)} "
        f"extra={sorted(seen - set(rows))}"
    )


def test_t2b_state_vocabulary_is_closed() -> None:
    page = _asm.render_device_classes_page(_asm.device_class_rows())
    for cells in _row_lines(page):
        assert cells[1] == "Implemented" or PLANNED_STATE_RE.match(cells[1]) is not None, (
            f"the state column is derived and closed: {cells[1]!r}"
        )


# --- T3: the reverse direction over the real tree ------------------------------


def test_t3_every_mockup_is_exactly_one_implemented_row() -> None:
    rows = {r["slug"]: r for r in _asm.device_class_rows()}
    for slug in _mockups():
        assert slug in rows, (
            f"the class-{slug}.html mockup has no table row — an orphan preview"
        )
        assert rows[slug]["state"] == "implemented", (
            f"the class-{slug}.html mockup's row must be state=implemented — a "
            "mockup cannot claim to be planned"
        )
    mockup_rows = {s for s, r in rows.items() if r["state"] == "implemented"}
    assert set(_mockups()) == mockup_rows, (
        "every implemented row has a mockup (the pair is atomic): "
        f"mockups_without_a_row={sorted(set(_mockups()) - mockup_rows)} "
        f"rows_without_a_mockup={sorted(mockup_rows - set(_mockups()))}"
    )


# --- T4: the copy refuses both directions on a synthetic tree -------------------


def test_t4_orphan_mockup_refuses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _synthetic_tree(
        tmp_path,
        mockups=["widget", "gizmo"],
        classes=["widget"],
        plan={"planned": [{"slug": "gadget", "slot": "L18"}]},
    )
    _bind_repo(monkeypatch, root)
    with pytest.raises(SystemExit, match="classref_preview_orphan:"):
        _asm.publish_device_class_previews(tmp_path / "docs_out")


def test_t4b_class_without_mockup_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _synthetic_tree(
        tmp_path,
        mockups=["widget"],
        classes=["widget", "gizmo"],
        plan={"planned": [{"slug": "gadget", "slot": "L18"}]},
    )
    _bind_repo(monkeypatch, root)
    with pytest.raises(SystemExit, match="classref_class_without_mockup:"):
        _asm.publish_device_class_previews(tmp_path / "docs_out")


# --- T5: the plan loader is fail-closed -----------------------------------------


def _plan_cases() -> dict[str, Any]:
    good_row = {"slug": "gadget", "slot": "L18"}
    return {
        "not_an_object": "[]",
        "not_a_list": {"planned": {"slug": "gadget"}},
        "unknown_top_key": {"planned": [], "note": "x"},
        "row_without_slot": {"planned": [{"slug": "gadget"}]},
        "row_without_slug": {"planned": [{"slot": "L18"}]},
        "row_with_extra_key": {"planned": [dict(good_row, state="planned")]},
        "row_bad_slug": {"planned": [{"slug": "Gadget", "slot": "L18"}]},
        "row_bad_slot": {"planned": [{"slug": "gadget", "slot": "18"}]},
        "duplicate_slug": {"planned": [good_row, dict(good_row)]},
    }


@pytest.mark.parametrize("name", sorted(_plan_cases()))
def test_t5_malformed_plan_records_refuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root = _synthetic_tree(
        tmp_path, mockups=["widget"], classes=["widget"], plan=_plan_cases()[name]
    )
    _bind_repo(monkeypatch, root)
    with pytest.raises(SystemExit, match="classref_sweep_plan"):
        _asm.device_class_rows()


def test_t5b_absent_plan_record_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _synthetic_tree(tmp_path, mockups=["widget"], classes=["widget"], plan=None)
    _bind_repo(monkeypatch, root)
    with pytest.raises(SystemExit, match="classref_sweep_plan_absent:"):
        _asm.device_class_rows()


def test_t5c_a_landed_slug_may_stay_in_the_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Append-only design: the corpus wins for a slug both carry, and the
    # plan record needs no edit when a class lands (parallel sweep lanes
    # never conflict on one shared file). The landed row derives
    # implemented; only the unlanded row stays planned.
    root = _synthetic_tree(
        tmp_path,
        mockups=["widget"],
        classes=["widget"],
        plan={"planned": [{"slug": "widget", "slot": "L11"}, {"slug": "gadget", "slot": "L18"}]},
    )
    _bind_repo(monkeypatch, root)
    rows = {r["slug"]: r for r in _asm.device_class_rows()}
    assert rows["widget"]["state"] == "implemented"
    assert rows["gadget"]["state"] == "planned"
    assert rows["gadget"]["slot"] == "L18"


# --- T6: the published copy cannot drift from the authoring home -----------------


def test_t6_preview_copy_is_byte_identical_and_total(tmp_path: Path) -> None:
    out = tmp_path / "docs_out"
    copied = _asm.publish_device_class_previews(out)
    src_dir = ROOT / "docs/internal/ui-styleguide-mockups"
    srcs = sorted(src_dir.glob("class-*.html"))
    assert copied == sorted(f"class-{slug}.html" for slug in _mockups()), (
        "the copied set equals the mockup glob exactly — no extras, none missing"
    )
    for src in srcs:
        dst = out / "user-guide/device-classes" / src.name
        assert dst.is_file(), f"{src.name} was not copied"
        assert hashlib.sha256(src.read_bytes()).hexdigest() == hashlib.sha256(
            dst.read_bytes()
        ).hexdigest(), f"{src.name}: the published preview must be byte-identical"
    extra = sorted(
        p.name for p in (out / "user-guide/device-classes").iterdir() if p.name not in copied
    )
    assert extra == [], f"the preview directory carries non-mockup files: {extra}"


# --- T7: the wiring — the page, the previews and the front door -----------------

AUTHORING_PAGE = ROOT / "docs/adding-a-device-class.md"


def test_t7_wiring_maps_and_listings() -> None:
    assert _asm.GENERATED_PAGES.get("device-classes.md") == "user-guide/device-classes.html", (
        "site_paths carries the generated mapping, so verify_tree pins the "
        "rendered page's presence"
    )
    assert "docs/adding-a-device-class.md" in _asm.USER_GUIDE, (
        "the authoring page stages with the user guides"
    )
    yml = (ROOT / "great-docs.yml").read_text(encoding="utf-8")
    guides = yml.index('section: "Guides"')
    for staged in ("- device-classes.md", "- adding-a-device-class.md"):
        assert yml.index(staged) > guides, f"{staged} must be listed in the Guides section"


def test_t7b_the_front_door_links_the_table() -> None:
    index = (ROOT / "website/index.html").read_text(encoding="utf-8")
    assert 'href="{{stg-docs-prefix}}user-guide/device-classes.html"' in index, (
        "the front door links the table through the docs-prefix token, so the "
        "link resolves in both release regimes (issue #456)"
    )


def test_t7c_generated_page_links_the_authoring_guide() -> None:
    page = _asm.render_device_classes_page(_asm.device_class_rows())
    assert "](adding-a-device-class.md)" in page, (
        "the table page links the authoring guide (the staged .md link; "
        "the renderer resolves it)"
    )


def test_t7d_staged_name_links_rewrite_to_the_rendered_path() -> None:
    # The link rewriter's generated-page branch: a guide page linking a
    # generated page by its staged name resolves to the site path, relative
    # to the rendered page — never the GitHub blob fallback (which would
    # point at a repository file that does not exist).
    paths = _asm.site_paths()
    assert paths.get("docs/adding-a-device-class.md") == (
        "user-guide/adding-a-device-class.html"
    )
    out = _asm.rewrite_links(
        "see [Device classes](device-classes.md)",
        ROOT / "docs/adding-a-device-class.md",
        "user-guide/adding-a-device-class.html",
        paths,
    )
    assert out == "see [Device classes](../user-guide/device-classes.html)"


# --- T8: the authoring guide pins its load-bearing sentences --------------------


def test_t8_authoring_guide_carries_the_convention() -> None:
    text = AUTHORING_PAGE.read_text(encoding="utf-8")
    # The theme-block convention, stated exactly (the owner corrected this
    # wording twice — it must not drift):
    assert (
        "Each theme block is a complete page. The banner, the ground and the "
        "footer sit inside the block. `body` and `html` own no theme."
    ) in text
    # Guides, not walls:
    assert "The mockup is a guide, not a wall." in text
    assert "Do not add vocabulary only to copy a decorative detail of the mockup." in text
    # The profiles array:
    assert "The array has no maximum" in text and "unique" in text
    # The census instrument and the exact gate commands:
    assert "tests/ui_html/classref_census.py" in text
    assert "uv run pytest tests/ui_html/test_classref_" in text
    assert "uv run ruff check ." in text
    assert "uv run mypy" in text
