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
- ``docs/`` — one Great Docs build of the current tree, or per-tag version
  buckets once a release tag exists. The assembly has TWO REGIMES, derived
  from one tag scan (design §1.1):

  * **Zero ``vX.Y.Z`` tags** (port landing → first cut): byte-for-byte
    today's tree — one unversioned build at ``docs/``, no ``v/`` tree, no
    aliases, no ``versions:`` key, the front-door selector showing a single
    ``dev`` row valued ``docs/``. Every PR's Build Docs lane stays green
    through the port's own merge.
  * **One or more tags** (first cut onward): versioned serving — ``docs/``
    root = the latest tag's bucket, ``docs/v/<tag>/`` per tag,
    ``docs/v/dev/`` = the current tree, ``v/latest/`` and ``v/stable/``
    alias redirects, and the selector populated from the registered
    versions.

  The regime boundary is ``release_tags()`` — the ``git tag --list v*`` glob
  plus the anchored ``TAG_RE``, which already excludes the ui-html line's
  ``ui-html-vX.Y.Z`` sibling namespace. Per-tag buckets are built by the
  TAG'S OWN assembly script (``--bucket <tag>``) in the tag's own uv
  environment: the gateway's docs tree is a two-phase build with gitignored
  staging, so an isolated ``great-docs --from-repo`` build of a tag would
  find no staging at all. The pre-tag registration ordering constraint
  (``check_registration``, design §1.3) is mechanized in three loud checks
  plus regime consistency — register the release in ``great-docs.yml`` and
  merge BEFORE pushing its tag, because the tag's own yml is what its bucket
  build filters.

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
from urllib.parse import urlparse

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
ALIASES = ("latest", "stable")
# The front-door selector's scaffold token (CON-13 discipline: a token in the
# website source, rows only in the assembly copy). Filled by
# fill_selector_token from release_tags() BEFORE stamp_website runs — an
# unfilled {{stg-versions}} would otherwise trip stamp_unmapped_token.
SELECTOR_PLACEHOLDER = "stg-versions"
# great-docs 0.17.0's version-selector trigger composes the navbar label as
# "v" + tag, but the tags already carry the v (as do the yml labels), so the
# trigger renders "vv0.4.0". Dropdown items and warning banners use `label`
# directly and are correct — the yml labels stay untouched.
VS_TRIGGER_DOUBLE_V = '(currentVersion.tag === "dev" ? "dev" : "v" + currentVersion.tag)'

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


# ── release tags and the registration constraint ─────────────────────────────
#
# The scan (release_tags) is ported from the SDK assembly verbatim: the
# `git tag --list v*` glob plus the anchored TAG_RE already excludes the
# ui-html line's `ui-html-vX.Y.Z` sibling namespace (the `^v` anchor cannot
# match a prefixed tag), so a ui-html release can never become a gateway
# bucket, a selector row, or a registration refusal.


def release_tags() -> list[str]:
    """Release tags (vX.Y.Z) in ascending version order (SDK port).

    The ui-html line's tags never appear here: the `v*` glob and the
    anchored TAG_RE both exclude `ui-html-vX.Y.Z`. This namespace contract
    is the refusal pin's load-bearing transfer (tests/contract/
    test_docs_site_versioned.py arms N1-N4).
    """
    tags = run(["git", "tag", "--list", "v*"], cwd=REPO).split()
    parsed = [t for t in tags if TAG_RE.match(t)]
    return sorted(parsed, key=lambda t: tuple(int(g) for g in TAG_RE.match(t).groups()))  # type: ignore[union-attr]


def ref_has_config(ref: str) -> bool:
    """True if ``great-docs.yml`` exists at the given git ref (SDK port)."""
    proc = subprocess.run(
        ["git", "cat-file", "-e", f"{ref}:great-docs.yml"],
        cwd=REPO,
        capture_output=True,
    )
    return proc.returncode == 0


# The versions: block parse (SDK's yml_version_tags regex, :134-140) — pure
# over its input so the registration checks are testable without a tree.
# The body is OPTIONAL and the key's newline optional: a bare `versions:`
# key at EOF (a truncated registration) is a stale registration too, not a
# match failure (PR #415 row 1) — the block is "present, empty".
VERSIONS_BLOCK_RE = re.compile(r"^versions:[ \t]*\n?((?:[ \t]+.*\n?)*)", re.MULTILINE)
VERSIONS_ENTRY_RE = re.compile(r"^\s*-?\s*tag:\s*(\S+)", re.MULTILINE)


def yml_versions_block(text: str) -> str | None:
    """The ``versions:`` block body, or None when the key is absent."""
    block = VERSIONS_BLOCK_RE.search(text)
    return block.group(1) if block else None


def yml_version_tags(text: str) -> set[str]:
    """Tags listed under ``versions:`` (must cover every release tag)."""
    body = yml_versions_block(text)
    if body is None:
        return set()
    return set(VERSIONS_ENTRY_RE.findall(body))


def yml_latest_tag(text: str) -> str | None:
    """The tag whose versions: entry carries ``latest: true`` (None if no entry does)."""
    marked = yml_latest_marked(text)
    return marked[0] if marked else None


def yml_latest_marked(text: str) -> list[str]:
    """Every tag whose versions: entry carries ``latest: true``, in list order.

    The current tree's registration must mark exactly one — great-docs
    accepts two silently, so the assembly validates the flags itself (fold
    A-F3).
    """
    body = yml_versions_block(text)
    if body is None:
        return []
    marked: list[str] = []
    for entry in re.split(r"(?=^\s*-?\s*tag:)", body, flags=re.MULTILINE):
        if re.search(r"^\s*latest:\s*true\b", entry, re.MULTILINE):
            matched = VERSIONS_ENTRY_RE.search(entry)
            if matched:
                marked.append(matched.group(1))
    return marked


def check_registration(tags: list[str], yml_text: str, tag_ymls: dict[str, str]) -> None:
    """The pre-tag registration ordering constraint, mechanized (design §1.3).

    Six checks, each with a scenario where it is the only one that can fire
    (so the mutation controls in the contract test are honest):

    1. Completeness — every release tag appears in the current tree's
       ``versions:`` block (the SDK check, :613-618).
    2. Dev entry — with tags present the block must also carry the ``dev``
       entry: the parent assembly's ``--versions dev`` build filters against
       this same list, and a block without it fails with "Multi-version
       build: 0 version(s)" (fold A-F2).
    3. Tag self-registration — the tag's OWN ``great-docs.yml`` lists the tag
       itself and marks it ``latest: true`` (at its own ref a
       correctly-registered tag is always the newest release). This is the
       v0.0.4 lesson turned into a machine check the SDK never had: the
       per-tag bucket build filters against the tag's own yml, so a
       registration that lands AFTER the tag is cut produces a zero-version
       build. Register and merge BEFORE pushing the tag.
    4. Inverse — every release-tag-shaped ``versions:`` entry is a real
       release tag (a stale registration for a deleted or never-pushed tag
       refuses). The tool's own ``dev`` special is not release-tag-shaped
       and is not this check's concern.
    5. Latest flag — exactly one ``latest: true``, naming the newest release
       tag; great-docs accepts two silently, so the assembly validates the
       flags itself (fold A-F3).
    6. Regime consistency — a ``versions:`` block with zero release tags is
       a stale registration: the key must not exist while zero tags exist
       (design §1.3), which is what makes the vacuous-green window honest.
       The converse (tags with no list) is check 1's failure.
    """
    registered = yml_version_tags(yml_text)
    missing = [t for t in tags if t not in registered]
    if missing:
        raise SystemExit(
            f"release tag(s) absent from great-docs.yml 'versions:': {', '.join(missing)} — "
            "the list is static and complete by design; register every release in "
            "great-docs.yml and merge BEFORE pushing its tag (the tag's own yml is what "
            "its bucket build filters)"
        )
    if tags and "dev" not in registered:
        # Fold A-F2: the registration is not just the release entries — the
        # parent assembly's --versions dev build filters against this same
        # list, and a block without the dev entry fails it with
        # "Multi-version build: 0 version(s)" (the SDK's v0.0.4 failure
        # class, one layer up). Refused here so the first cut's own docs
        # run cannot red on its own registration.
        raise SystemExit(
            "registration lacks the dev entry — great-docs.yml's versions: must carry "
            "the release entries AND the dev entry (prerelease: true): the parent "
            "assembly's --versions dev build filters against this list, and a block "
            "without it fails with 'Multi-version build: 0 version(s)'"
        )
    for tag in tags:
        own = tag_ymls.get(tag)
        if own is None:
            raise SystemExit(f"tag_self_registration: no great-docs.yml readable at {tag}")
        if tag not in yml_version_tags(own):
            raise SystemExit(
                f"tag_self_registration: {tag}'s own great-docs.yml does not list {tag} — "
                "register the release in great-docs.yml and merge BEFORE pushing the tag "
                "(the tag's own yml is what its bucket build filters)"
            )
        if yml_latest_tag(own) != tag:
            raise SystemExit(
                f"tag_self_registration: {tag}'s own great-docs.yml does not mark {tag} "
                "'latest: true' (at its own ref a correctly-registered tag is always the "
                "newest release)"
            )
    stale = sorted(t for t in registered if t not in tags and t != "dev")
    if stale:
        raise SystemExit(
            f"stale version registration(s) in great-docs.yml 'versions:': {', '.join(stale)} "
            "— every entry must name a real release tag or the dev special"
        )
    if tags:
        # Fold A-F3: great-docs accepts two latest: true entries silently;
        # the current tree's registration must mark exactly one, naming the
        # newest release tag.
        marked = yml_latest_marked(yml_text)
        if len(marked) != 1 or marked[0] != tags[-1]:
            raise SystemExit(
                f"versions: must mark exactly one entry latest: true, naming the newest "
                f"release tag ({tags[-1]}); found: {', '.join(marked) if marked else 'none'}"
            )
    if yml_versions_block(yml_text) is not None and not tags:
        raise SystemExit(
            "versions: block present with zero release tags — a stale registration; the "
            "key must not exist while zero tags exist (it lands with the first release's "
            "pre-tag registration)"
        )


# ── the front-door version selector ─────────────────────────────────────────
#
# The selector is GENERATED, not hand-coded (design §1.4): a hand-coded
# selector carrying three-component version literals would redden the
# class-11 hygiene ban (tests/contract/test_website_stamps.py refuses
# \d+\.\d+\.\d+ anywhere under website/), and a hand-coded selector drifts
# from the tags it points at. website/index.html carries the scaffold — the
# <select class="version-select"> element with one {{stg-versions}} token
# placeholder and zero option rows — and this generation fills the rows into
# the ASSEMBLY COPY only (CON-13's discipline extended from version stamps to
# version rows).


def selector_rows(tags: list[str]) -> list[tuple[str, str]]:
    """(label, value) rows for the front-door selector (design §1.4).

    Tagged regime: one row per release tag in descending order — the newest
    labelled ``(latest)`` valued ``docs/`` (the root serves the latest
    build), older tags valued ``docs/v/<tag>/`` — then the final ``dev`` row
    valued ``docs/v/dev/``. Zero-tag regime: the single ``dev`` row valued
    ``docs/`` (the root is the current tree's build). A ``(latest)`` label
    with no releases is a lie and cannot be generated here.
    """
    if not tags:
        return [("dev", "docs/")]
    rows: list[tuple[str, str]] = []
    newest = tags[-1]
    for tag in reversed(tags):
        if tag == newest:
            rows.append((f"{tag} (latest)", "docs/"))
        else:
            rows.append((tag, f"docs/v/{tag}/"))
    rows.append(("dev", "docs/v/dev/"))
    return rows


def selector_options_html(tags: list[str]) -> str:
    """The selector's generated ``<option>`` rows (design §1.4).

    The rows are the ``{{stg-versions}}`` token's map value, so the
    substitution rides ``stamp_website``'s existing fail-closed arms
    (design §1.4: "fail-closed both directions, mirroring stamp_website"):
    a scaffold without its token refuses via ``stamp_unused_key`` (the
    selector was hand-edited away), and a token the generation cannot fill
    refuses via ``stamp_unmapped_token``. The ``{{`` delimiter residue sweep
    in ``verify_tree`` covers a token neither arm replaced.
    """
    rows = [f'<option value="{value}">{label}</option>' for label, value in selector_rows(tags)]
    # The first row carries no generator indent: it lands where the scaffold
    # token sat, whose line already indents it (PR #415 row 7a — the
    # double-indent was the cosmetic artifact).
    return ("\n" + " " * 8).join(rows)


def copy_website(dest: Path) -> None:
    src = REPO / "website"
    if not (src / "index.html").is_file():
        raise SystemExit(f"static website missing or incomplete: {src / 'index.html'} not found")
    shutil.copytree(src, dest, dirs_exist_ok=True)
    stamp_website(dest / "index.html", website_stamp_map(REPO))
    log(
        f"static site <- {src.relative_to(REPO)}/ (artifact root, version stamps + "
        "selector rows applied)"
    )


# ── per-tag buckets (SDK port, generalized one level up) ─────────────────────
#
# The SDK's isolated `great-docs build --from-repo` cannot work for the
# gateway: the docs tree is a two-phase build (staged user_guide/ and
# standards_pages/ are gitignored build-time trees) and an isolated build of
# a tag finds no staging, no generated standards-CLI page, no pattern
# library. So the bucket mechanism generalizes the SDK's own principle —
# *the tag's own configuration is what the bucket build reads* — one level
# up: the tag's OWN assembly script is what the bucket build runs. Each
# release tag gets a local --shared clone, the tag's own uv environment, and
# the tag's own `assemble_docs_site.py --bucket <tag>`.


def bucket_source(out_dir: Path, tag: str) -> Path:
    """Source dir of one version inside a bucket build's output (SDK port).

    A filtered ``--versions <tag>`` build renders the requested version
    either as a bucket (``out/v/<tag>/``, when the version is not the
    config's latest) or flat at the output root (when it is the latest).
    Both shapes are valid inputs here.
    """
    bucket = out_dir / "v" / tag
    if (bucket / "index.html").is_file():
        return bucket
    if (out_dir / "index.html").is_file():
        return out_dir
    raise SystemExit(
        f"bucket build output for {tag} has neither v/{tag}/ bucket nor flat index: {out_dir}"
    )


def replace_dir(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)


def replace_root(src: Path, dest: Path) -> None:
    """Clear the site root outside ``v/`` and MERGE a bucket build into it.

    ``shutil.copytree(..., dirs_exist_ok=True)`` merges src into dest — src's
    own ``v/`` subtree (if any) merges into dest's ``v/`` beside the lifted
    buckets rather than replacing it. The fold's source strip means the
    bucket output carries no alias stubs, so in practice nothing lands under
    ``v/`` from here and ``fix_alias_stubs`` remains the sole creator of the
    real aliases.
    """
    for entry in dest.iterdir():
        if entry.name == "v":
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    shutil.copytree(src, dest, dirs_exist_ok=True)


def site_path_prefix() -> str:
    """URL path prefix of the deployed docs (e.g. ``/docs/``) (SDK port)."""
    text = (REPO / "great-docs.yml").read_text(encoding="utf-8")
    matched = re.search(r"^site_url:\s*(\S+)", text, re.MULTILINE)
    if not matched:
        return "/"
    path = urlparse(matched.group(1)).path or "/"
    return path if path.endswith("/") else path + "/"


def redirect_page(target: str) -> str:
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '  <meta charset="utf-8">\n'
        f'  <meta http-equiv="refresh" content="0; url={target}">\n'
        f'  <link rel="canonical" href="{target}">\n'
        "  <title>Redirecting…</title>\n"
        "</head>\n<body>\n"
        f'  <p>Redirecting to <a href="{target}">{target}</a>…</p>\n'
        "</body>\n</html>\n"
    )


def fix_alias_stubs(dest: Path, prefix: str) -> None:
    """Point ``v/latest/`` and ``v/stable/`` redirect stubs at the prefixed root.

    The tool writes ``url=/`` stubs, which redirect to the GitHub Pages
    ORIGIN root on a project site — one level too high. The gateway's
    ``site_url`` yields the ``/docs/`` prefix (SDK port, :249-267).
    """
    for alias in ALIASES:
        stub = dest / "v" / alias / "index.html"
        if not stub.is_file():
            stub.parent.mkdir(parents=True, exist_ok=True)
            stub.write_text(redirect_page(prefix), encoding="utf-8")
            log(f"created missing alias stub v/{alias}/ -> {prefix}")
            continue
        html = stub.read_text(encoding="utf-8")
        if "url=/" in html:
            html = html.replace("url=/", f"url={prefix}").replace('href="/"', f'href="{prefix}"')
            stub.write_text(html, encoding="utf-8")
            log(f"rewrote alias stub v/{alias}/ redirect: / -> {prefix}")


def fix_version_selector_trigger(docs_root: Path) -> None:
    """Un-double the version label in great-docs' version-selector trigger.

    0.17.0 renders the navbar trigger as ``"v" + tag`` while the tags
    already carry the ``v`` (``v0.4.0``), so the widget shows ``vv0.4.0``.
    The dropdown items and warning banners read ``label`` and render
    correctly, so the fix is this one expression in every generated
    ``version-selector.js`` copy (one per bucket) — not the yml labels.
    Delete when a released great-docs renders the trigger without the extra
    prefix (SDK port, :377-404).
    """
    copies = sorted(docs_root.rglob("version-selector.js"))
    fixed = 0
    for widget in copies:
        js = widget.read_text(encoding="utf-8")
        if VS_TRIGGER_DOUBLE_V not in js:
            continue
        widget.write_text(js.replace(VS_TRIGGER_DOUBLE_V, "currentVersion.tag"), encoding="utf-8")
        fixed += 1
    if fixed == 0:
        log(
            f"WARNING: doubled-v trigger rewrite matched 0 of {len(copies)} "
            "version-selector.js copies — great-docs fixed or changed the widget "
            "(if fixed, delete this rewrite)"
        )
    else:
        log(f"version-selector trigger un-doubled in {fixed}/{len(copies)} widget copies")


# ── website version stamps ───────────────────────────────────────────────────

STAMP_TOKEN_RE = re.compile(r"\{\{stg-([a-z0-9-]+)\}\}")
# `stg-sdk` derives from the sdk_compatibility mirror, never from a standards
# entry: an entry id `sdk` would silently shadow the mirror's key (the mirror
# write wins) and be invisible to every coverage arm (review fold F4).
RESERVED_STAMP_IDS = frozenset({"sdk", "versions", "stg-versions"})


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

    The front-door selector (design §1.4) is a SECOND claim-site family,
    outside the map's derivation (CON-13: ``website_stamp_map`` derives from
    the standards manifest and the ``sdk_compatibility`` mirror — the
    selector derives from the release tags). Its ``{{stg-versions}}`` token
    is filled here from ``release_tags()`` rather than the map, so a raw
    source stamps cleanly for every caller. The fail-closed directions are
    the generation's own: a ``{{stg-*}}`` token it cannot fill refuses via
    ``stamp_unmapped_token``, and a scaffold whose token was hand-edited
    away ships zero option rows, which ``verify_tree``'s selector-honesty
    arm refuses. The ``{{`` residue sweep covers a token neither replaced.
    """
    html = dest_index.read_text(encoding="utf-8")
    used: set[str] = set()

    def substitute(match: re.Match[str]) -> str:
        key = f"stg-{match.group(1)}"
        if key == SELECTOR_PLACEHOLDER:
            used.add(key)
            return selector_options_html(release_tags())
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
    """Generate the raster favicon set at the docs root when it is missing (cosmetic).

    Bucket builds run their own tag's script under the parent's toolchain,
    so a bucket can miss the raster set; the root's set is copied into any
    bucket that lacks it (SDK port, :297-321). Cosmetic-only: pages
    reference the docs-root favicon absolutely and the SVG favicon is always
    present.
    """
    if not all((docs_root / name).is_file() for name in RASTER_FAVICONS):
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
            master.save(
                docs_root / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48)]
            )
            log("generated raster favicon set at docs root")
        except Exception as exc:
            log(
                f"WARNING: raster favicons missing and generation failed ({exc}); "
                "SVG favicon remains"
            )
    # Per-bucket copy: a bucket that lacks the set gets the root's (SDK
    # port). Alias stubs are redirect pages, not buckets.
    vdir = docs_root / "v"
    if not vdir.is_dir():
        return
    for name in (*RASTER_FAVICONS, "favicon.svg"):
        src = docs_root / name
        if not src.is_file():
            continue
        for bucket in vdir.iterdir():
            if bucket.is_dir() and bucket.name not in ALIASES and not (bucket / name).is_file():
                shutil.copy2(src, bucket / name)


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


def verify_tree(
    dest: Path, paths: dict[str, str], tags: list[str] | None = None, *, bucket_mode: bool = False
) -> None:
    """Verify the assembled tree. ``tags=None`` is the pre-port call shape
    (stamp-residue callers): the versioned and selector arms are skipped.
    A list — empty included — switches them on per regime (design §1.5)."""
    docs = dest / "docs"
    failures: list[str] = []
    if not bucket_mode:
        # The website is the parent's front door (a bucket ships only its
        # docs/ tree; the parent owns the website copy, its stamps and its
        # selector).
        for rel in ("index.html", "assets/logo.svg", "assets/styles.css", "assets/site.js"):
            if not (dest / rel).is_file():
                failures.append(f"static site {rel} missing (website/ incomplete?)")
    if not (docs / "index.html").is_file():
        failures.append("docs root index.html missing (Great Docs build failed?)")
    # The CURRENT TREE's render map and the active-corpus schema verify
    # where the current tree's build lives (fold A-F1): the docs root in
    # the zero-tag regime, the dev bucket in the tagged regime — the root
    # is the latest tag's bucket there, so a page or schema added after
    # the tag is absent from it BY CONSTRUCTION and the arm would red on
    # the first post-release guide. Root-level arms (index, reference,
    # standards, changelog, patterns, llms) stay on the root: the tag's own
    # bucket build produced them.
    current = docs / "v" / "dev" if tags else docs
    rendered_at = "docs/v/dev" if tags else "docs"
    for rel in (
        "reference/cli/index.html",
        "standards/index.html",
        "user-guide/changelog.html",
        "user-guide/patterns/index.html",  # the staged pattern library (#300)
        "user-guide/patterns/light/button.html",
        "user-guide/patterns/dark/refusals.html",
        "llms.txt",
        "llms-full.txt",
    ):
        if not (docs / rel).is_file():
            failures.append(f"docs/{rel} missing")
    if not (current / ACTIVE_OTDP_RUNTIME_SCHEMA).is_file():
        failures.append(f"{rendered_at}/{ACTIVE_OTDP_RUNTIME_SCHEMA} missing")
    for src, html in paths.items():
        if not (current / html).is_file():
            failures.append(f"{src} did not render to {rendered_at}/{html}")
    # Every relative docs/ link on the static site must resolve in the
    # assembled tree. Options are VALUES, not hrefs — the arm reads both.
    index = (dest / "index.html").read_text(encoding="utf-8") if not bucket_mode else ""
    if not bucket_mode:
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
        hrefs = set(re.findall(r'href="(docs/[^"#]*)"', index))
        hrefs |= set(re.findall(r'value="(docs/[^"#]*)"', index))
        for link in sorted(hrefs):
            target = dest / link
            ok = (target / "index.html").is_file() if link.endswith("/") else target.is_file()
            if not ok:
                failures.append(f"website links to {link}, which the assembled tree lacks")
    home_linked = sum(
        1 for p in docs.rglob("*.html") if SITE_LINK_MARKER in p.read_text(encoding="utf-8")
    )
    if home_linked == 0 and not bucket_mode:
        failures.append("no docs page links back to the static site root")

    # ── versioned arms (design §1.5), conditional on regime ───────────────
    if tags is None:
        pass  # pre-port call shape: no versioned or selector arms
    elif bucket_mode:
        # A bucket verifies its own tree: the root arms above minus the
        # home-link arm (the link is depth-relative and wrong at bucket
        # depth — the parent's pass adds it after lifting).
        pass
    elif tags:
        # Tagged regime: per-tag buckets, the dev bucket, alias stubs.
        for tag in tags:
            if not (docs / "v" / tag / "index.html").is_file():
                failures.append(f"docs/v/{tag}/index.html missing (bucket build failed?)")
        if not (docs / "v" / "dev" / "index.html").is_file():
            failures.append("docs/v/dev/index.html missing")
        for alias in ALIASES:
            if not (docs / "v" / alias / "index.html").is_file():
                failures.append(f"alias docs/v/{alias}/ missing")
        # Fold B-F2: a lifted bucket carries no nested v/ tree — the aliases
        # live at docs/v/{latest,stable}, never inside a bucket.
        vdir = docs / "v"
        if vdir.is_dir():
            for bucket in vdir.iterdir():
                if (
                    bucket.is_dir()
                    and bucket.name not in ALIASES
                    and bucket.name != "dev"
                    and (bucket / "v").exists()
                ):
                    failures.append(
                        f"nested v/ tree inside the lifted bucket docs/v/{bucket.name}/ — "
                        "alias stubs are stripped at the bucket source; the aliases live at "
                        "docs/v/{latest,stable}"
                    )
    else:
        # Zero-tag regime: today's tree exactly — no v/ tree at all.
        if (docs / "v").exists():
            failures.append(
                "docs/v/ present with zero release tags — the zero-tag regime must not "
                "emit a versioned tree"
            )

    # Selector honesty (design §1.4): every option value resolves to a real
    # directory, and exactly one row is labelled (latest) iff release tags
    # exist — a "(latest)" label with no releases is a lie.
    if tags is not None and not bucket_mode:
        select = re.search(r'<select class="version-select".*?</select>', index, re.DOTALL)
        if select is None:
            failures.append("the assembled site's version selector is missing")
        else:
            options = re.findall(
                r'<option value="([^"]*)">\s*([^<]+?)\s*</option>', select.group(0)
            )
            if not options:
                failures.append("the assembled site's version selector has no option rows")
            for value, label in options:
                target = dest / value
                ok = (target / "index.html").is_file() if value.endswith("/") else target.is_dir()
                if not ok:
                    failures.append(
                        f"selector advertises {label!r} -> {value}, which the assembled tree lacks"
                    )
            latest_labelled = [label for _, label in options if "(latest)" in label]
            if tags and len(latest_labelled) != 1:
                failures.append(
                    f"selector must label exactly one option '(latest)' when release tags exist: "
                    f"{[label for _, label in options]}"
                )
            if not tags and latest_labelled:
                failures.append(
                    "selector labels an option '(latest)' with zero release tags — a "
                    "'(latest)' label with no releases is a lie"
                )

    # Doubled-v labels (great-docs 0.17.0's selector-trigger bug): none may
    # ship in any gd-version-map meta, _version_map.json, or widget copy. The
    # parent un-doubles every bucket's widget after lifting
    # (fix_version_selector_trigger), so the arm is parent-side.
    if tags is not None and not bucket_mode:
        vv_pattern = re.compile(r"vv\d")
        for page in docs.rglob("*.html"):
            html = page.read_text(encoding="utf-8")
            if re.search(r'<meta name="gd-version-map"[^>]*vv\d', html):
                failures.append(
                    f"doubled-v version label in gd-version-map meta: {page.relative_to(docs)}"
                )
        for vmap in docs.rglob("_version_map.json"):
            if vv_pattern.search(vmap.read_text(encoding="utf-8")):
                failures.append(f"doubled-v version label in {vmap.relative_to(docs)}")
        vs_widgets = sorted(docs.rglob("version-selector.js"))
        if tags and not vs_widgets:
            failures.append("version-selector.js missing from the tagged tree — widget changed?")
        for widget in vs_widgets:
            if VS_TRIGGER_DOUBLE_V in widget.read_text(encoding="utf-8"):
                failures.append(
                    "version-selector.js still composes the doubled-v trigger: "
                    f"{widget.relative_to(docs)}"
                )

    if failures:
        raise SystemExit("assembled site verification FAILED:\n  " + "\n  ".join(failures))
    regime = (
        f"tagged ({len(tags)} release tag(s))"
        if tags and not bucket_mode
        else ("bucket" if bucket_mode else "zero-tag (unversioned)")
    )
    log(
        f"verification OK: static root + {regime} docs/ "
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


def run_bucket_build(great_docs: str, tag: str, dest: Path) -> None:
    """Build one release tag's bucket through the TAG's OWN assembly script.

    The SDK's isolated ``great-docs --from-repo`` cannot work here (the
    gateway's docs tree is a two-phase build with gitignored staging), so
    the bucket mechanism generalizes the SDK's principle one level up: the
    tag's own configuration is what the bucket build reads -> the tag's own
    ASSEMBLY SCRIPT is what the bucket build runs. Each step is forced:

    1. ``git clone --shared`` — a local object-sharing clone of the tag's
       tree. No worktree metadata in the user's repo (the multi-agent
       worktree discipline stays untouched).
    2. ``git submodule update --init`` — the ``packages/sdk`` gitlink at
       that tag's pinned SHA.
    3. ``uv run --project`` — the tag's own environment (its own ``uv.lock``)
       with ``UV_PROJECT_ENVIRONMENT`` set inside the scratch tree so the
       parent's non-dot-venv convention cannot leak.
    4. The tag's own ``scripts/assemble_docs_site.py --bucket <tag>``.

    The tag's staging, standards manifest, stamps, generated standards-CLI
    page and corpus copy all derive from the tag's tree through the tag's
    code — no cross-version re-derivation.
    """
    staging = (REPO / ".docs-assembly").resolve()
    staging.mkdir(parents=True, exist_ok=True)
    tree = staging / f"{tag}-tree"
    out = staging / f"{tag}-out"
    for path in (tree, out):
        if path.exists():
            shutil.rmtree(path)
    log(f"bucket {tag}: cloning tag tree (shared)")
    run(["git", "clone", "--shared", str(REPO), str(tree)], cwd=REPO)
    run(["git", "checkout", "--detach", tag], cwd=tree)
    run(["git", "submodule", "update", "--init"], cwd=tree)
    venv = tree / ".bucket-venv"
    env = dict(os.environ)
    env["UV_PROJECT_ENVIRONMENT"] = str(venv)
    # The child runs with cwd=<tag tree>: a relative --great-docs would
    # resolve against the CLONE, not the parent — resolve it here (PR #415
    # row 6; the alternative was a loud refusal, but resolving preserves the
    # invocation for every absolute/PATH-resolved case and fixes the
    # relative one).
    great_docs_abs = str(Path(great_docs).resolve())
    log(f"bucket {tag}: running the tag's own assembly --bucket {tag}")
    run(
        [
            "uv",
            "run",
            "--project",
            str(tree),
            "python",
            "scripts/assemble_docs_site.py",
            "--bucket",
            tag,
            "--dest",
            str(out),
            "--great-docs",
            great_docs_abs,
        ],
        cwd=tree,
        env=env,
    )
    # The tool emits alias stubs (v/latest, v/stable with url=/ — origin-root
    # redirects) inside the version output; the REAL aliases are the parent's
    # (fix_alias_stubs at docs/v/{latest,stable}). Strip them at the SOURCE so
    # neither the lifted bucket nor the root carries them (fold B-F2) — an
    # unswept stub inside a bucket redirects to the hosting origin's root.
    for alias in ALIASES:
        stub = out / "docs" / "v" / alias
        if stub.is_dir():
            shutil.rmtree(stub)
            log(
                f"bucket {tag}: stripped nested alias stub v/{alias}/ "
                "(the parent's fix_alias_stubs owns the real ones)"
            )
    nested_v = out / "docs" / "v"
    if nested_v.is_dir() and not any(nested_v.iterdir()):
        nested_v.rmdir()  # the emptied husk is still unexpected structure
    src = bucket_source(out / "docs", tag)
    replace_dir(src, dest)
    log(f"bucket {tag}: lifted {src.relative_to(out)} -> {dest.relative_to(REPO)}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Assemble the public site (see module docstring)")
    ap.add_argument("--dest", default="site")
    ap.add_argument("--great-docs", default=shutil.which("great-docs") or "great-docs")
    ap.add_argument(
        "--keep-staging",
        action="store_true",
        help="leave the staged page trees in place for inspection",
    )
    ap.add_argument(
        "--bucket",
        metavar="TAG",
        help="build ONE release tag's bucket through this tag's own script (the "
        "parent's per-tag driver invokes this; three documented deltas from the "
        "main assembly)",
    )
    args = ap.parse_args()

    dest = (REPO / args.dest).resolve()
    guard_dest(dest)

    # One scan drives both regimes (design §1.1).
    tags = release_tags()
    yml_text = (REPO / "great-docs.yml").read_text(encoding="utf-8")

    if args.bucket:
        # ── --bucket mode: today's main() verbatim — stage -> build -> repairs
        # -> verify_tree — with exactly three deltas (design §1.2):
        #   1. the registration checks are NOT called (a bucket build of a
        #      tag's own snapshot is precisely what the refusal demanded;
        #      the parent runs the checks).
        #   2. the Great Docs invocation passes --versions <tag> (the tag's
        #      own yml registers itself, so the filtered render is exactly
        #      this tag's pages).
        #   3. add_site_home_link and its verify_tree arm are omitted (the
        #      link is depth-relative and wrong at bucket depth — the
        #      parent's pass covers every page after lifting).
        # The website step is parent-owned (only docs/ is lifted), so the
        # bucket's selector is the zero-tag shape it serves itself.
        if dest.exists():
            shutil.rmtree(dest)
        paths = site_paths()
        staging = REPO / "user_guide"
        standards_staging = REPO / "standards_pages"
        try:
            stage_pages(USER_GUIDE, staging, paths)
            write_standards_cli_page(staging)
            stage_pages(standards_manifest(), standards_staging, paths, keep_relative=True)
            cache = REPO / ".great-docs-cache"
            if cache.exists():
                shutil.rmtree(cache)
            proc = subprocess.run(
                [args.great_docs, "build", "--versions", args.bucket], cwd=REPO
            )
            if proc.returncode != 0:
                raise SystemExit(f"docs build failed ({proc.returncode})")
        finally:
            if not args.keep_staging:
                for d in (staging, standards_staging):
                    if d.exists():
                        shutil.rmtree(d)
        docs_root = dest / "docs"
        site = REPO / "great-docs" / "_site"
        replace_dir(bucket_source(site, args.bucket), docs_root)
        rename_standards_section(docs_root)
        copy_standards_resources(docs_root)
        stage_pattern_library(docs_root)
        complete_favicons(docs_root, REPO / "website" / "assets" / "logo.svg")
        write_llms_txt(docs_root)
        fix_root_doc_links(docs_root)
        verify_tree(dest, paths, [], bucket_mode=True)
        log(f"assembled bucket {args.bucket} at {dest}")
        return
    # ── the parent assembly: the registration ordering constraint first ──
    # (design §1.3 — loud, before anything is built: a tag whose own yml
    # lacks its entry cannot build a bucket at all)
    tag_ymls: dict[str, str] = {}
    for tag in tags:
        proc = subprocess.run(
            ["git", "show", f"{tag}:great-docs.yml"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        # None (not "") for the unreadable case: an absent yml at the ref is a
        # different refusal from a yml that does not list the tag (PR #415
        # row 7b — the None branch of check_registration was dead wiring).
        tag_ymls[tag] = proc.stdout if proc.returncode == 0 else None
    check_registration(tags, yml_text, tag_ymls)

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
        if tags:
            # Tagged regime: the in-process current-tree render becomes the
            # dev bucket (SDK invocation shape, :627-629).
            proc = subprocess.run(
                [args.great_docs, "build", "--versions", "dev"], cwd=REPO
            )
        else:
            # Zero-tag regime: byte-for-byte today's build — no versions
            # filter, no v/ tree, no aliases (design §1.1).
            proc = subprocess.run([args.great_docs, "build"], cwd=REPO)
        if proc.returncode != 0:
            raise SystemExit(f"docs build failed ({proc.returncode})")
    finally:
        if not args.keep_staging:
            for d in (staging, standards_staging):
                if d.exists():
                    shutil.rmtree(d)
    docs_root = dest / "docs"
    site = REPO / "great-docs" / "_site"
    if not tags:
        shutil.copytree(site, docs_root)
    else:
        # The dev bucket's own render, normalized through bucket_source's
        # two-shape tolerance (flat when dev is the config's latest, bucket
        # otherwise).
        replace_dir(bucket_source(site, "dev"), docs_root / "v" / "dev")
    copy_website(dest)
    rename_standards_section(docs_root if not tags else docs_root / "v" / "dev")
    copy_standards_resources(docs_root if not tags else docs_root / "v" / "dev")
    stage_pattern_library(docs_root if not tags else docs_root / "v" / "dev")
    if not tags:
        write_llms_txt(docs_root)
        fix_root_doc_links(docs_root)
    else:
        write_llms_txt(docs_root / "v" / "dev")
        fix_root_doc_links(docs_root / "v" / "dev")
        # Per-tag buckets, each built by its own tag's own script.
        for tag in tags:
            run_bucket_build(args.great_docs, tag, docs_root / "v" / tag)
        # The latest tag's bucket also serves at the docs/ root.
        latest = tags[-1]
        latest_out = REPO / ".docs-assembly" / f"{latest}-out" / "docs"
        replace_root(bucket_source(latest_out, latest), docs_root)
        log(f"docs/ root <- bucket of {latest} (latest stable)")
    complete_favicons(docs_root, REPO / "website" / "assets" / "logo.svg")
    if tags:
        fix_alias_stubs(docs_root, site_path_prefix())
        fix_version_selector_trigger(docs_root)
    add_site_home_link(docs_root)
    verify_tree(dest, paths, tags)
    log(f"assembled site at {dest}")


if __name__ == "__main__":
    main()
