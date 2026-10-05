#!/usr/bin/env python3
"""Assemble the public BenchWeave Pages site: static front door + docs tree.

Author: Stephen Eaton

Two-tier layout, the same shape the SDK repository deploys
(``packages/sdk/scripts/assemble_docs_site.py``):

- ``website/`` — the hand-written static site (one page, four panels — Home,
  Standards, User guides, SDK — styled per ``docs/internal/public-site-
  styleguide.html``; no build chain) is copied to the artifact root and its
  ``{{stg-*}}`` version tokens are stamped there from committed state
  (``website_stamp_map`` / ``stamp_website`` — the source carries tokens at
  its claim sites and no three-component version literal anywhere under
  ``website/`` or in ``index.qmd``, pinned by
  ``tests/contract/test_website_stamps.py``, so a raw ``website/`` preview
  shows tokens; preview through this assembler, e.g.
  ``--dest /tmp/site-preview``). Its links into
  the docs are relative ``docs/…`` paths, so the pair previews from any
  server root, GitHub Pages included.
- ``docs/`` — one Great Docs build of the current tree. The gateway has no
  release tags yet, so the tree is UNVERSIONED by design: no ``versions:``
  list, no ``v/<tag>/`` buckets, no selector. The day the first ``vX.Y.Z``
  tag lands this script refuses to run (see ``refuse_if_tagged``) rather than
  silently publishing an unversioned tree for a released gateway — at that
  point port the SDK's per-tag snapshot design.

Source staging — the doc taxonomy (``docs/doc-taxonomy.md``, rule 1: one home
per class) forbids a second checked-in copy of any guide, and Great Docs only
reads user-guide pages from a flat ``user_guide/`` directory at the project
root. So the guide pages are STAGED at build time from ``USER_GUIDE`` below
(source path → staged name), the directory is gitignored, and it is removed
again after the build. Staging also:

- lifts each page's leading ``# H1`` into Quarto frontmatter (``title:``), so
  the sidebar and page header carry the real document title rather than a
  filename-derived one;
- rewrites relative Markdown links: targets that are staged or rendered
  elsewhere in the site resolve to their site path; anything else (JSON
  corpora, planning history, working material) resolves to its GitHub blob
  URL on the main branch — never a dangling relative link.

The standards prose companions are staged the same way, into a build-time
``standards_pages/`` tree that mirrors ``standards/<id>/<version>/`` (each
standard's README.md becomes ``overview.qmd`` — Great Docs skips README.md in
a section), rendered through a Great Docs custom section, and moved to
``docs/standards/`` after the build (``rename_standards_section``). Their
JSON neighbours (schemas, catalogs, vectors) are copied alongside so the
prose's relative links to the machine corpus resolve.

Repairs on the tool's output (mirroring the SDK assembly where they apply):
raster favicon set at the docs root (cairosvg via ``great-docs[svg]``), and a
navbar link from every docs page back to the static front door.

Any failure aborts non-zero — this runs in CI where a docs failure must fail
the job. ``verify_tree`` is equally loud. Run from the repository root with
``great-docs`` on PATH (see .github/workflows/docs.yml).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from benchweave.standards.manifest import (
    active_version_from_corpus,
    load_manifest,
    load_sdk_compatibility,
)
from benchweave.vendoring import corpus_root

REPO = Path(__file__).resolve().parent.parent
# The runtime schema the built site must carry is the ACTIVE otdp family's
# (issue #269 §2.1): derived from the committed manifest so a future otdp
# bump moves the verified path with it — no sweep. copy_standards_resources
# copies every non-dev corpus family beside the prose, so the derived path
# exists in the built tree by construction.
ACTIVE_OTDP_RUNTIME_SCHEMA = (
    f"standards/otdp/{active_version_from_corpus(corpus_root(), 'otdp')}"
    "/otdp-runtime.schema.json"
)
GITHUB_BLOB = "https://github.com/madeinoz67/benchweave/blob/main/"
GITHUB_TREE = "https://github.com/madeinoz67/benchweave/tree/main/"

TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
RASTER_FAVICONS = ("favicon.ico", "favicon-16x16.png", "favicon-32x32.png", "apple-touch-icon.png")

# The left navbar list every content page carries.
NAVBAR_NAV_ANCHOR = '<ul class="navbar-nav navbar-nav-scroll me-auto">'
SITE_LINK_MARKER = '<span class="menu-text">← BenchWeave</span>'

# Guide pages: repository source → staged filename (flat, as Great Docs wants).
# Order here is documentary; great-docs.yml's user_guide sections set the order.
USER_GUIDE: dict[str, str] = {
    "docs/operator-guide.md": "operator-guide.md",
    "docs/device-developer-guide.md": "device-developer-guide.md",
    "docs/develop-your-device.md": "develop-your-device.md",
    "docs/ai-device-reviewer.md": "ai-device-reviewer.md",
    "docs/plugin-sdk.md": "plugin-sdk.md",
    "docs/development.md": "development.md",
    "docs/smart-test-gateway-architecture-v1.5.md": "architecture.md",
    "docs/smart-test-gateway-decisions.md": "decisions.md",
    "docs/architecture-validation.md": "architecture-validation.md",
    "docs/architecture-closure.md": "architecture-closure.md",
    "docs/compatibility.md": "compatibility.md",
    "docs/compatibility-matrix.md": "compatibility-matrix.md",
    "docs/implementation-planning/00-poc-mvp-prd.md": "poc-mvp-prd.md",
    "docs/implementation-planning/01-delivery-plan.md": "delivery-plan.md",
    "docs/implementation-planning/03-first-slice-plan.md": "first-slice-plan.md",
    "docs/dps150-protocol.md": "dps150-protocol.md",
    "docs/devices/dps150/compatibility-record.md": "dps150-compatibility-record.md",
    "docs/devices/esp32-selection.md": "esp32-selection.md",
    # Project: git-cliff maintains CHANGELOG.md; the gateway has no GitHub Releases yet,
    # which is the only source Great Docs' own changelog page reads.
    "CHANGELOG.md": "changelog.md",
}

# Generated user-guide pages: staged filename → docs-relative rendered path.
# Unlike USER_GUIDE there is NO repository source — the page is derived at
# build time from a live capture, so the key here is the staged name alone.
# Merged into site_paths() below; verify_tree then pins the rendered page's
# presence, so a listed-but-missing page fails assembly (the wiring hole).
GENERATED_PAGES: dict[str, str] = {
    "standards-cli.md": "user-guide/standards-cli.html",
}

LINK_RE = re.compile(r"(?<!\!)\[([^\]]*)\]\(([^)\s]+)(\s+\"[^\"]*\")?\)")
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def log(msg: str) -> None:
    print(f"[assemble] {msg}")


def run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        raise SystemExit(f"command failed ({proc.returncode}): {' '.join(cmd)}")
    return proc.stdout


# ── site path map ────────────────────────────────────────────────────────────


def site_paths() -> dict[str, str]:
    """Repository-relative source path → docs-relative rendered path.

    Covers the staged guide pages and the staged standards prose
    (``standards/<id>/<version>/<page>.md`` →
    ``standards/<id>/<version>/<page>.html``, README.md → overview.html).
    The standards' ``NN-`` ordering prefixes are stripped, as the tool strips them.
    """
    paths: dict[str, str] = {}
    for src, staged in USER_GUIDE.items():
        paths[src] = "user-guide/" + staged[:-3] + ".html"
    for src, staged in standards_manifest().items():
        paths[src] = "standards/" + strip_prefixes(staged)[:-4] + ".html"
    paths.update(GENERATED_PAGES)
    return paths


def standards_manifest() -> dict[str, str]:
    """``standards/**/*.md`` → path inside the staged ``standards_pages/`` tree.

    Mirrors the real tree. README.md files (the interface and plugin-ui
    standards keep their primary prose there) are staged as ``overview.qmd``
    because Great Docs drops README.md from custom sections. GOVERNANCE.md
    stays at the top level. Dev-stage directories never stage (review row 1):
    the site is a released-bytes surface, and a head's schemas ship beside
    its prose — skipping the prose but shipping the schemas (or either alone)
    breaks the staged tree's own link resolution.
    """
    manifest: dict[str, str] = {}
    for md in sorted((REPO / "standards").rglob("*.md")):
        rel = md.relative_to(REPO / "standards")
        if _is_dev_tree(rel):
            continue
        if md.name == "README.md":
            rel = rel.with_name("overview.md")
        parts = list(rel.parts)
        if len(parts) > 1:  # <id>/<version>/... — order the standard and its primary page
            order = STANDARD_ORDER.index(parts[0]) + 1 if parts[0] in STANDARD_ORDER else 9
            parts[0] = f"{order:02d}-{parts[0]}"
            parts[-1] = f"{page_rank(parts[-1]):02d}-{parts[-1]}"
        # Staged as .qmd: Great Docs treats a section subdirectory holding no .qmd
        # file as an asset directory and copies it verbatim, prefixes and all.
        manifest[md.relative_to(REPO).as_posix()] = Path(*parts).with_suffix(".qmd").as_posix()
    return manifest


# Sidebar order of the standards (Great Docs otherwise sorts the directories
# alphabetically) and, within one, of its pages: the specification or contract
# first, its companions next, the validation report last. The ``NN-`` prefixes
# are stripped from URLs and sidebar labels by the tool.
STANDARD_ORDER = ("otdp", "registry", "execution", "interface", "plugin-ui", "plugin-ui-preview")


def page_rank(name: str) -> int:
    if name == "overview.md" or name.endswith("-specification.md"):
        return 1
    if name.endswith("-contract.md"):
        return 2  # the primary page where a standard has no specification; else right after it
    if name == "validation-report.md":
        return 9
    return 5


def strip_prefixes(staged: str) -> str:
    return Path(*[re.sub(r"^\d+-", "", part) for part in Path(staged).parts]).as_posix()


def rewrite_links(
    content: str, src: Path, staged_html: str, paths: dict[str, str], *, keep_relative: bool = False
) -> str:
    """Rewrite relative Markdown links in a staged page (see module docstring)."""

    def sub(m: re.Match[str]) -> str:
        text, target, title = m.group(1), m.group(2), m.group(3) or ""
        if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
            return m.group(0)  # absolute URL, mailto:, or in-page anchor
        path, _, frag = target.partition("#")
        frag = f"#{frag}" if frag else ""
        resolved = (src.parent / path).resolve()
        try:
            rel = resolved.relative_to(REPO).as_posix()
        except ValueError:
            return m.group(0)  # escapes the repository — leave it
        if rel in paths:
            here = Path(staged_html).parent
            new = (
                Path(*([".."] * len(here.parts)), paths[rel]).as_posix()
                if here.parts
                else paths[rel]
            )
            return f"[{text}]({new}{frag}{title})"
        if keep_relative and resolved.is_file() and resolved.suffix != ".md":
            return m.group(0)  # machine corpus beside the prose — copied alongside after the build
        base = GITHUB_TREE if resolved.is_dir() else GITHUB_BLOB
        return f"[{text}]({base}{rel}{frag}{title})"

    return LINK_RE.sub(sub, content)


def stage_pages(
    manifest: dict[str, str], dest: Path, paths: dict[str, str], *, keep_relative: bool = False
) -> None:
    """Materialise a build-time page tree (gitignored) from source → staged-name pairs."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for src_rel, staged in manifest.items():
        src = REPO / src_rel
        if not src.is_file():
            raise SystemExit(f"page source missing: {src_rel}")
        content = src.read_text(encoding="utf-8")
        m = H1_RE.search(content)
        if not m:
            raise SystemExit(f"page source has no H1 title: {src_rel}")
        title = m.group(1).replace('"', '\\"')
        body = content[: m.start()] + content[m.end() :]
        body = rewrite_links(
            body.lstrip("\n"), src, paths[src_rel], paths, keep_relative=keep_relative
        )
        out = dest / staged
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f'---\ntitle: "{title}"\nsource: {src_rel}\n---\n\n{body}', encoding="utf-8")
    log(f"staged {len(manifest)} pages -> {dest.relative_to(REPO)}/")


# ── generated pages ──────────────────────────────────────────────────────────
#
# The standards resolver family is an argparse sibling of the Click CLI, so
# the site's CLI reference (which introspects the Click tree) cannot see it.
# Its page is GENERATED at build from the captured `--help` (issue #291):
# generated beats hand-written — a hand-maintained verb list on the site is
# exactly the drift class obligation 23 (docs/internal/drift-and-obligations.md)
# exists to kill. The generator itself names no verb: every literal on the
# page is parsed out of the capture.

# The subcommand choices metavar line (argparse renders the positional's
# choices as an indented, braces-wrapped, comma-separated list on its own
# line): the usage line carries the braces too but never alone on its line,
# so only the positional-arguments block's copy matches.
STANDARDS_CHOICES_RE = re.compile(r"^\s*\{([a-z][a-z0-9_,]*)\}\s*$", re.MULTILINE)
# A subcommand detail row: exactly four spaces, the verb, two-plus spaces,
# then the one-liner. Deeper-indented non-empty lines are argparse's own
# wrapping of the current verb's description and append to it.
STANDARDS_VERB_RE = re.compile(r"^    ([a-z][a-z0-9_]*)\s{2,}(\S.*)$")


def capture_standards_help() -> str:
    """Capture ``python -m benchweave.standards --help`` — the page's authority.

    COLUMNS is pinned so argparse wrapping is deterministic: a width-varying
    capture would make the verb pin flaky. The env is CONSTRUCTED, not
    inherited-with-overrides: an inherited env can forward a PYTHONPATH that
    shadows the real package (refute fold F3) — the capture must see THIS
    tree's module and nothing else. The captured text is the honest
    artifact — what the shipped page shows is what this tree runs.
    """
    text = run(
        [sys.executable, "-m", "benchweave.standards", "--help"],
        cwd=REPO,
        env={"PATH": os.environ.get("PATH", ""), "COLUMNS": "100"},
    )
    if not text.strip():
        raise SystemExit("standards_cli_capture_failed: empty --help output")
    return text


def render_standards_cli_page(help_text: str) -> str:
    """Render the standards-CLI page from a captured ``--help`` (pure).

    Fail-closed: a capture whose subcommand block cannot be parsed refuses
    (``standards_cli_help_unparsed:``) — the page can never exist in an empty
    or silently-degraded state. An internally consistent capture renders
    even if a verb was lost upstream; the VERB PIN
    (tests/contract/test_docs_site_standards_cli.py) is what catches that.
    """
    choices = STANDARDS_CHOICES_RE.findall(help_text)
    if not choices:
        raise SystemExit("standards_cli_help_unparsed: no subcommand choices line")
    verbs = choices[0].split(",")
    rows: dict[str, str] = {}
    current: str | None = None
    for line in help_text.splitlines():
        matched = STANDARDS_VERB_RE.match(line)
        if matched:
            rows[matched.group(1)] = matched.group(2).strip()
            current = matched.group(1)
        elif current is not None and line.startswith("      ") and line.strip():
            rows[current] += " " + line.strip()
    if not rows:
        raise SystemExit("standards_cli_help_unparsed: no subcommand detail rows")
    if set(rows) != set(verbs):
        raise SystemExit(
            "standards_cli_help_unparsed: choices and detail rows disagree (choices "
            f"only: {sorted(set(verbs) - set(rows))}; details only: "
            f"{sorted(set(rows) - set(verbs))})"
        )
    table = "\n".join(f"| `{verb}` | {rows[verb]} |" for verb in verbs)
    # No body H1: Great Docs renders the frontmatter title as the page header
    # AND derives the Markdown twin's `# <title>` from it (the staged pages'
    # H1-lift, verified on the rendered tree) — a body H1 would duplicate the
    # title on the rendered page.
    return (
        "---\n"
        'title: "Standards CLI"\n'
        "source: generated from python -m benchweave.standards --help at build time\n"
        "---\n"
        "\n"
        "The standards resolver family is a separate argparse command tree beside the\n"
        "Click CLI, so its commands do not appear on the CLI reference pages. This page\n"
        "is generated at assembly time from `python -m benchweave.standards --help`;\n"
        "the in-repo quick reference is the operator guide's section 10.\n"
        "\n"
        "| Command | What it does |\n"
        "|---|---|\n"
        f"{table}\n"
        "\n"
        "## The captured `--help` output\n"
        "\n"
        "```text\n"
        f"{help_text.rstrip()}\n"
        "```\n"
    )


def write_standards_cli_page(dest_dir: Path) -> None:
    """Stage the generated standards-CLI page into the user-guide staging tree."""
    (dest_dir / "standards-cli.md").write_text(
        render_standards_cli_page(capture_standards_help()), encoding="utf-8"
    )
    log("staged generated page: standards-cli.md <- benchweave.standards --help")


def rename_standards_section(docs_root: Path) -> None:
    """Move the built ``standards-pages/`` section to ``standards/`` (URL of record).

    Great Docs derives a section's URL slug from its source directory, and
    the real ``standards/`` tree cannot be the source (see module docstring),
    so the staged ``standards_pages/`` renders under ``standards-pages/``.
    Rename the directory and rewrite the slug in every text artifact
    (pages, sitemap, search index, version metadata, Markdown twins).
    """
    built = docs_root / "standards-pages"
    if not built.is_dir():
        raise SystemExit(
            "standards-pages/ missing from the built tree (sections: in great-docs.yml?)"
        )
    target = docs_root / "standards"
    if target.exists():
        shutil.rmtree(target)
    built.rename(target)
    rewritten = 0
    for f in docs_root.rglob("*"):
        if f.is_file() and f.suffix in {".html", ".json", ".xml", ".txt", ".md", ".js"}:
            text = f.read_text(encoding="utf-8", errors="surrogateescape")
            if "standards-pages" in text:
                f.write_text(
                    text.replace("standards-pages", "standards"),
                    encoding="utf-8",
                    errors="surrogateescape",
                )
                rewritten += 1
    log(f"standards section: standards-pages/ -> standards/ ({rewritten} file(s) rewritten)")


# ── build ────────────────────────────────────────────────────────────────────


def refuse_if_tagged() -> None:
    tags = [t for t in run(["git", "tag", "--list", "v*"], cwd=REPO).split() if TAG_RE.match(t)]
    if tags:
        raise SystemExit(
            f"release tag(s) present ({', '.join(tags)}) but this assembly is unversioned by "
            "design — port the SDK's per-tag snapshot assembly before publishing a released "
            "gateway's docs"
        )


def copy_website(dest: Path) -> None:
    src = REPO / "website"
    if not (src / "index.html").is_file():
        raise SystemExit(f"static website missing or incomplete: {src / 'index.html'} not found")
    shutil.copytree(src, dest, dirs_exist_ok=True)
    stamp_website(dest / "index.html", website_stamp_map(REPO))
    log(f"static site <- {src.relative_to(REPO)}/ (artifact root, version stamps applied)")


# ── website version stamps ───────────────────────────────────────────────────

STAMP_TOKEN_RE = re.compile(r"\{\{stg-([a-z0-9-]+)\}\}")
# `stg-sdk` derives from the sdk_compatibility mirror, never from a standards
# entry: an entry id `sdk` would silently shadow the mirror's key (the mirror
# write wins) and be invisible to every coverage arm (review fold F4).
RESERVED_STAMP_IDS = frozenset({"sdk"})


def website_stamp_map(root: Path) -> dict[str, str]:
    """Committed state -> the website's version claims (invariants CON-13).

    ``stg-<id>`` -> the standard's active version from the standards manifest;
    ``stg-sdk`` -> the ``sdk_compatibility`` mirror's SDK version (CON-12's
    authority chain). One authoritative parse: the loaders' closed-world
    refusals (``standards_entry_duplicate``, ``standards_entry_version_invalid``,
    ``sdk_compatibility_invalid``) apply here for free, and dev heads never
    stamp — only each entry's active version is read. An entry id colliding
    with the reserved ``sdk`` key refuses (``stamp_reserved_key:``) rather
    than silently shadowing the mirror.
    """
    stamps: dict[str, str] = {}
    for entry in load_manifest(root).standards:
        if entry.id in RESERVED_STAMP_IDS:
            raise SystemExit(
                f"stamp_reserved_key: standards entry id '{entry.id}' collides with the "
                "reserved stamp namespace — stg-sdk derives from sdk_compatibility (CON-12)"
            )
        stamps[f"stg-{entry.id}"] = entry.version
    stamps["stg-sdk"] = load_sdk_compatibility(root).sdk
    return stamps


def stamp_website(dest_index: Path, stamps: dict[str, str]) -> None:
    """Substitute ``{{stg-*}}`` tokens in the ASSEMBLY COPY only (CON-13).

    The source under ``website/`` is never written. Coverage is bidirectional
    and fail-closed: a token with no map entry refuses
    (``stamp_unmapped_token:``) and a map key used by no token refuses
    (``stamp_unused_key:``) — the standards panel cannot silently omit a
    standard, and an unmapped token can never reach the published site.
    """
    html = dest_index.read_text(encoding="utf-8")
    used: set[str] = set()

    def substitute(match: re.Match[str]) -> str:
        key = f"stg-{match.group(1)}"
        if key not in stamps:
            raise SystemExit(f"stamp_unmapped_token: {match.group(0)} has no map entry")
        used.add(key)
        return stamps[key]

    stamped = STAMP_TOKEN_RE.sub(substitute, html)
    unused = sorted(set(stamps) - used)
    if unused:
        raise SystemExit(
            "stamp_unused_key: " + ", ".join(unused) + " (no token in the website "
            "carries it — a new standard needs a spec card, a removed one a token sweep)"
        )
    dest_index.write_text(stamped, encoding="utf-8")
    log(f"website stamps: {len(used)} token(s) resolved against committed state")


def copy_standards_resources(docs_root: Path) -> None:
    """Copy the machine corpus beside its rendered prose so in-page links resolve.

    Great Docs copies only asset-like subdirectories of a section; the
    schemas, catalogs and vectors the prose links to sit beside the prose.
    Dev-stage directories are skipped on the same lexical rule as the page
    staging (review row 1): never staged, never shipped, either half.
    """
    src_root = REPO / "standards"
    dst_root = docs_root / "standards"
    if not dst_root.is_dir():
        raise SystemExit(
            "docs/standards/ missing from the built tree (rename_standards_section ran?)"
        )
    copied = 0
    for f in src_root.rglob("*"):
        if f.is_file() and f.suffix != ".md" and not _is_dev_tree(f.relative_to(src_root)):
            dst = dst_root / f.relative_to(src_root)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)
            copied += 1
    log(f"standards corpus: {copied} non-Markdown file(s) copied beside the rendered prose")


def _is_dev_tree(relative: Path) -> bool:
    """The packaging-side lexical rule, shared by the site's two halves.

    Mirrors hatch_build.py: any path segment ending in ``-dev`` is a dev-stage
    directory — no manifest read, so a stray head governance has not admitted
    yet ships nowhere either.
    """
    return any(part.endswith("-dev") for part in relative.parts)


def fit_to_square(img, size: int):
    from PIL import Image

    img.thumbnail((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2))
    return canvas


def complete_favicons(docs_root: Path, logo: Path) -> None:
    """Generate the raster favicon set at the docs root when it is missing (cosmetic)."""
    if all((docs_root / name).is_file() for name in RASTER_FAVICONS):
        return
    try:
        import io

        import cairosvg
        from PIL import Image

        raw = Image.open(io.BytesIO(cairosvg.svg2png(url=str(logo), scale=4)))
        master = fit_to_square(raw, 512)
        for px, name in (
            (16, "favicon-16x16.png"),
            (32, "favicon-32x32.png"),
            (180, "apple-touch-icon.png"),
        ):
            master.resize((px, px), Image.Resampling.LANCZOS).save(docs_root / name, "PNG")
        master.save(docs_root / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
        log("generated raster favicon set at docs root")
    except Exception as exc:
        log(f"WARNING: raster favicons missing and generation failed ({exc}); SVG favicon remains")


def add_site_home_link(docs_root: Path) -> None:
    """Navbar link from every docs page back to the static site root (depth-relative)."""
    added = already = 0
    for page in sorted(docs_root.rglob("*.html")):
        html = page.read_text(encoding="utf-8")
        if SITE_LINK_MARKER in html:
            already += 1
            continue
        if NAVBAR_NAV_ANCHOR not in html:
            continue
        ups = "../" * (len(page.relative_to(docs_root).parent.parts) + 1)
        item = (
            f'  <li class="nav-item">\n    <a class="nav-link" href="{ups}">\n'
            f"{SITE_LINK_MARKER}</a>\n  </li>  \n"
        )
        page.write_text(
            html.replace(NAVBAR_NAV_ANCHOR, NAVBAR_NAV_ANCHOR + "\n" + item, 1), encoding="utf-8"
        )
        added += 1
    if added == 0 and already == 0:
        log("WARNING: site-home link injected nowhere — navbar markup changed?")
    log(f"site-home navbar link: {added} page(s) injected, {already} already linked")


def write_llms_txt(docs_root: Path) -> None:
    """Write ``llms.txt`` / ``llms-full.txt`` from the built Markdown twins.

    Great Docs 0.17.0 generates both only when an API reference section
    exists (``_generate_llms_txt`` returns early otherwise) yet still links
    them from the landing page. With ``reference: false`` here, build them
    from the ``.md`` twin Great Docs emits beside every rendered page.
    """
    pages = sorted(
        p for p in docs_root.rglob("*.md") if p.name != "skill.md" and ".well-known" not in p.parts
    )
    if not pages:
        raise SystemExit("no Markdown page twins in the built tree — cannot write llms.txt")

    def title_of(md: Path) -> str:
        for line in md.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
            if line.startswith("title:"):
                return line[6:].strip().strip('"')
        return md.stem.replace("-", " ")

    base = "https://www.benchweave.dev/docs/"
    index = [
        "# BenchWeave",
        "",
        "> Python test-bench gateway for embedded systems: reusable instrument and DUT "
        "plugins, shared device profiles, and safety-aware automated testing, exposed "
        "over REST and MCP.",
        "",
        "## Pages",
        "",
    ]
    full: list[str] = []
    for md in pages:
        rel = md.relative_to(docs_root).as_posix()
        index.append(f"- [{title_of(md)}]({base}{rel})")
        full.append(f"<!-- {rel} -->\n\n" + md.read_text(encoding="utf-8").strip() + "\n")
    (docs_root / "llms.txt").write_text("\n".join(index) + "\n", encoding="utf-8")
    (docs_root / "llms-full.txt").write_text("\n\n---\n\n".join(full), encoding="utf-8")
    log(f"llms.txt ({len(pages)} pages) + llms-full.txt written")


def fix_root_doc_links(docs_root: Path) -> None:
    """CONTRIBUTING.md links its root siblings by filename; the tool renders them as pages."""
    page = docs_root / "contributing.html"
    if not page.is_file():
        return
    html = page.read_text(encoding="utf-8")
    fixed = html.replace('href="CODE_OF_CONDUCT.md"', 'href="code-of-conduct.html"').replace(
        'href="SECURITY.md"', 'href="security.html"'
    )
    if fixed != html:
        page.write_text(fixed, encoding="utf-8")
        log("contributing.html: root-sibling links repointed at their rendered pages")


def verify_tree(dest: Path, paths: dict[str, str]) -> None:
    docs = dest / "docs"
    failures: list[str] = []
    for rel in ("index.html", "assets/logo.svg", "assets/styles.css", "assets/site.js"):
        if not (dest / rel).is_file():
            failures.append(f"static site {rel} missing (website/ incomplete?)")
    if not (docs / "index.html").is_file():
        failures.append("docs root index.html missing (Great Docs build failed?)")
    for rel in (
        "reference/cli/index.html",
        "standards/index.html",
        ACTIVE_OTDP_RUNTIME_SCHEMA,  # corpus copied beside the prose
        "user-guide/changelog.html",
        "user-guide/patterns/index.html",  # the staged pattern library (#300)
        "user-guide/patterns/light/button.html",
        "user-guide/patterns/dark/refusals.html",
        "llms.txt",
        "llms-full.txt",
    ):
        if not (docs / rel).is_file():
            failures.append(f"docs/{rel} missing")
    for src, html in paths.items():
        if not (docs / html).is_file():
            failures.append(f"{src} did not render to docs/{html}")
    # Every relative docs/ link on the static site must resolve in the assembled tree.
    index = (dest / "index.html").read_text(encoding="utf-8")
    # Stamp residue (R1): sweep the DELIMITER, not the grammar — a case-variant,
    # nested or unterminated `{{` matches no token pattern and would ship raw
    # (review fold F1) — and sweep every copied website/ file, not just the
    # index: the stamper only reads index.html, so a token anywhere else in the
    # static source stamps nothing at all.
    for f in sorted(p for p in dest.rglob("*") if p.is_file() and docs not in p.parents):
        if b"{{" in f.read_bytes():
            failures.append(
                f"stamp_residue: {f.relative_to(dest).as_posix()} carries an unstamped "
                "{{ delimiter (website/ carries well-formed tokens in index.html only)"
            )
    for link in sorted(set(re.findall(r'href="(docs/[^"#]*)"', index))):
        target = dest / link
        ok = (target / "index.html").is_file() if link.endswith("/") else target.is_file()
        if not ok:
            failures.append(f"website links to {link}, which the assembled tree lacks")
    home_linked = sum(
        1 for p in docs.rglob("*.html") if SITE_LINK_MARKER in p.read_text(encoding="utf-8")
    )
    if home_linked == 0:
        failures.append("no docs page links back to the static site root")
    if failures:
        raise SystemExit("assembled site verification FAILED:\n  " + "\n  ".join(failures))
    log(
        f"verification OK: static root + unversioned docs/ "
        f"({sum(1 for _ in docs.rglob('*.html'))} pages)"
    )


def guard_dest(dest: Path) -> None:
    if dest == REPO or dest in REPO.parents:
        raise SystemExit(f"--dest {dest} is the repository root or an ancestor of it — refusing")
    if REPO in dest.parents and dest.exists():
        tracked = run(["git", "ls-files", "--", str(dest.relative_to(REPO))], cwd=REPO).split()
        if tracked:
            raise SystemExit(
                f"--dest {dest} contains {len(tracked)} tracked file(s) — refusing to wipe them"
            )


def stage_pattern_library(docs_root: Path) -> None:
    """Stage the ui-html pattern library under the user guides (issue #300
    G1d / UR-06+UR-13): ``docs/user-guide/patterns/`` — plain rendered HTML
    pages over file:// URLs, one per §E.1 component plus the refusal page,
    both themes. The tree is GENERATED at assembly (never committed; the
    repo-side guard in tests/ui_html/test_patterns.py refuses a tracked
    ``patterns/`` dir); screenshots are captured into the same tree by the
    docs workflow's post-assembly step (the browser extra is a test-only
    dependency, so assembly itself writes the HTML only)."""
    from benchweave_ui_html import patterns as bw_patterns

    try:
        result = bw_patterns.export(docs_root / "user-guide")
    except bw_patterns.PatternExportRefused as exc:
        raise SystemExit(f"pattern-library export refused: {exc}") from exc
    log(f"pattern library staged: {len(result.pages)} pages under docs/user-guide/patterns/")


def main() -> None:
    ap = argparse.ArgumentParser(description="Assemble the public site (see module docstring)")
    ap.add_argument("--dest", default="site")
    ap.add_argument("--great-docs", default=shutil.which("great-docs") or "great-docs")
    ap.add_argument(
        "--keep-staging",
        action="store_true",
        help="leave the staged page trees in place for inspection",
    )
    args = ap.parse_args()

    dest = (REPO / args.dest).resolve()
    guard_dest(dest)
    refuse_if_tagged()
    if dest.exists():
        shutil.rmtree(dest)
    paths = site_paths()
    staging = REPO / "user_guide"
    standards_staging = REPO / "standards_pages"
    # All staging runs INSIDE the try/finally whose finally removes the
    # staged trees: an abort anywhere between the first stage and the build
    # otherwise leaves gitignored staging residue in the working tree —
    # residue the version-literal docs gate then scans and reddens on
    # (observed in the #291 build; refute fold F4).
    try:
        stage_pages(USER_GUIDE, staging, paths)
        write_standards_cli_page(staging)
        stage_pages(standards_manifest(), standards_staging, paths, keep_relative=True)
        cache = REPO / ".great-docs-cache"
        if cache.exists():
            shutil.rmtree(cache)
        proc = subprocess.run([args.great_docs, "build"], cwd=REPO)
        if proc.returncode != 0:
            raise SystemExit(f"docs build failed ({proc.returncode})")
    finally:
        if not args.keep_staging:
            for d in (staging, standards_staging):
                if d.exists():
                    shutil.rmtree(d)
    docs_root = dest / "docs"
    shutil.copytree(REPO / "great-docs" / "_site", docs_root)
    copy_website(dest)
    rename_standards_section(docs_root)
    copy_standards_resources(docs_root)
    stage_pattern_library(docs_root)
    complete_favicons(docs_root, REPO / "website" / "assets" / "logo.svg")
    write_llms_txt(docs_root)
    fix_root_doc_links(docs_root)
    add_site_home_link(docs_root)
    verify_tree(dest, paths)
    log(f"assembled site at {dest}")


if __name__ == "__main__":
    main()
