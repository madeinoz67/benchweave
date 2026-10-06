"""The versioned-docs assembly contract (issue #381, design record §3).

``refuse_if_tagged`` is retired by the port: the unversioned assembly it
guarded becomes a two-regime assembly — zero ``vX.Y.Z`` tags is today's tree
exactly, one or more tags is per-tag ``docs/v/<tag>/`` buckets with the
latest at the ``docs/`` root. This file is the mechanism's contract test.

The refusal pin's own namespace contract is the load-bearing transfer: the
``ui-html-v*`` line releases from THIS repository under a ``v*``-prefixed
sibling tag namespace, so **``ui-html-v*`` tags must never be treated as
gateway release tags** — no bucket, no selector row, no registration
refusal. The arms below move with the mechanism (design §1.1: "that contract
survives the mechanism's replacement by moving into the new contract test");
a replaced test whose arms die with the old mechanism is how the exclusion
gets lost.

Injection technique unchanged from the refusal pin: the tag listing is
injected at the ``run`` helper (no git subprocess, no tag created in the
working tree — xdist-safe) and reaches ``TAG_RE`` UNFILTERED. The real
pipeline's ``git tag --list v*`` glob excludes ``ui-html-v*`` upstream of
the filter; the injection point is downstream of the glob, so the pin holds
the FILTER in isolation — strictly stronger than the real pipeline, and the
only posture under which the mutation control can bite.

Arms — namespace (transferred from the refusal pin):

- N1 — ``ui-html-v*`` tags pass alone and alongside a gateway tag; a mixed
  listing's refusal names ONLY the gateway tag.
- N2 — a pre-release-suffixed ``v*`` tag passes (``TAG_RE`` is exact-match;
  the stable-only policy is procedural, not this mechanism's).
- N3 — wiring: ``release_tags`` consults the tag listing through the ``run``
  helper via the EXACT command literal ``['git', 'tag', '--list', 'v*']``.
- N4 — a ui-html-only listing yields zero release tags, hence zero buckets
  and a single ``dev`` selector row (the zero-tag regime).

Arms — registration refusals (design §1.3, each with its own scenario where
it is the ONLY check that can fire, so the mutation control is honest):

- R1 — completeness: a release tag absent from the current tree's
  ``versions:`` block refuses, naming the tag.
- R2 — tag self-registration: a tag whose OWN ``great-docs.yml`` does not
  list itself as ``latest: true`` refuses, naming the tag-self rule.
- R3 — inverse: a ``versions:`` entry naming a tag that is not a real
  release tag refuses, naming the stale entry.
- R4 — regime consistency: a ``versions:`` block with zero release tags
  refuses (a stale registration — the key must not exist while zero tags
  exist, design §1.3).

Arms — selector generation (design §1.4):

- S1 — rows derive from the tags: newest ``(latest)`` valued ``docs/``,
  older tags valued ``docs/v/<tag>/``, final row ``dev`` valued
  ``docs/v/dev/``.
- S2 — a ``(latest)`` label exists iff release tags exist.
- S3 — token bidirectionality: a scaffold without its token refuses; the
  generation fills the token in the assembly copy only.

Mutation controls (design acceptance A3, RED evidence in the commit): with
each registration check's code reverted in place (test kept) the
corresponding arm FAILS to refuse — the unproven-guard failure. With
``TAG_RE`` weakened to accept an arbitrary prefix (``.*v(\\d+)\\.\\.(\\d+)\\.(
\\d+)$``) N1's mixed arm FAILS; with the ``$`` anchor dropped N2 FAILS; with
the listing's selector pattern mutated (``v*`` → ``ui-html-*``) N3's
command-literal assert FAILS.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "website" / "index.html"


def _assembler() -> Any:
    path = ROOT / "scripts" / "assemble_docs_site.py"
    spec = importlib.util.spec_from_file_location("assemble_docs_site", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_asm = _assembler()

# The synthetic registration a scratch release commits BEFORE its tag
# (design §1.3's ordering constraint: the tag's own yml is what its bucket
# build filters).
YML_WITH_V040 = """\
display_name: Scratch
site_url: https://www.benchweave.dev/docs/
versions:
  - tag: v0.4.0
    label: v0.4.0
    latest: true
    git_ref: v0.4.0
  - tag: dev
    label: dev
    prerelease: true
"""

YML_DEV_ONLY = """\
display_name: Scratch
site_url: https://www.benchweave.dev/docs/
versions:
  - tag: dev
    label: dev
    prerelease: true
"""

YML_UNVERSIONED = """\
display_name: Scratch
site_url: https://www.benchweave.dev/docs/
"""


# ── namespace arms (transferred from the retired refusal pin) ───────────────


def _release_tags_with_listing(monkeypatch: pytest.MonkeyPatch, tags: list[str]) -> list[str]:
    """Run ``release_tags`` over a synthetic listing (see module docstring).

    Asserts the exact listing command literal (N3) on every call, so a pass
    arm that passed by doing nothing — or a mutated selector pattern —
    reddens here instead of silently greening.
    """
    seen: list[list[str]] = []

    def fake_run(
        cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None
    ) -> str:
        seen.append(cmd)
        return "".join(f"{tag}\n" for tag in tags)

    monkeypatch.setattr(_asm, "run", fake_run)
    result: list[str] = list(_asm.release_tags())
    assert seen and seen[0] == ["git", "tag", "--list", "v*"], (
        "release_tags must list tags via exactly ['git', 'tag', '--list', 'v*']"
    )
    return result


def test_n1_ui_html_tags_are_never_gateway_release_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Alone: the whole ui-html tag line must yield zero release tags —
    # no bucket, no selector row, no registration refusal.
    assert _release_tags_with_listing(monkeypatch, ["ui-html-v0.1.0", "ui-html-v0.2.1"]) == []


def test_n1b_mixed_listing_names_only_the_gateway_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Alongside a gateway tag: the scan yields ONLY the gateway tag — a
    # ui-html release landing next to a gateway tag must not widen the
    # blast radius to buckets, rows or refusals.
    assert _release_tags_with_listing(monkeypatch, ["ui-html-v0.2.1", "v0.9.0"]) == ["v0.9.0"]


@pytest.mark.parametrize("tag", ["v0.9.0rc1", "v1.0.0b2"])
def test_n2_pre_release_suffixed_tags_pass(
    monkeypatch: pytest.MonkeyPatch, tag: str
) -> None:
    assert _release_tags_with_listing(monkeypatch, [tag]) == []


def test_n3_listing_command_literal(monkeypatch: pytest.MonkeyPatch) -> None:
    # The command-literal arm runs on its own too: a mutation of the
    # selector pattern (v* -> ui-html-*) reddens here even if some pass arm
    # were to skip the call entirely.
    _release_tags_with_listing(monkeypatch, ["v0.1.0"])


def test_n4_ui_html_only_listing_is_the_zero_tag_regime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tags = _release_tags_with_listing(monkeypatch, ["ui-html-v0.1.0", "ui-html-v0.2.0"])
    assert tags == []
    # Zero release tags -> the zero-tag regime: a single dev row valued
    # docs/ (the root is the current tree's build), never a bucket row.
    assert _asm.selector_rows(tags) == [("dev", "docs/")]


# ── registration refusals (design §1.3) ─────────────────────────────────────


def test_r1_completeness_tag_without_registering_refuses() -> None:
    # (a) of acceptance A3: a tag pushed with no registration in the
    # current tree's great-docs.yml refuses, naming the tag.
    with pytest.raises(SystemExit, match=r"v0\.4\.0"):
        _asm.check_registration(["v0.4.0"], YML_DEV_ONLY, {"v0.4.0": YML_WITH_V040})


def test_r1_completeness_registers_a_tag_that_is_registered() -> None:
    # The green counterpart: the same tag with its registration present
    # passes — the arm is not a blanket refusal of any tag.
    _asm.check_registration(["v0.4.0"], YML_WITH_V040, {"v0.4.0": YML_WITH_V040})


def test_r2_tag_self_registration_refuses_when_the_tags_own_yml_lacks_it() -> None:
    # (b) of acceptance A3: the current tree registers v0.4.0, but the
    # tagged commit's OWN great-docs.yml predates the registration (the
    # v0.0.4 lesson) — refuses, naming the tag-self-registration rule.
    stale_self = YML_DEV_ONLY  # the tag's own yml has no v0.4.0 entry
    with pytest.raises(SystemExit, match=r"tag_self_registration"):
        _asm.check_registration(["v0.4.0"], YML_WITH_V040, {"v0.4.0": stale_self})


def test_r2_tag_self_registration_accepts_a_correct_self_entry() -> None:
    # A tag whose own yml lists itself as latest passes (at its own ref a
    # correctly-registered tag is always the newest release).
    _asm.check_registration(["v0.4.0"], YML_WITH_V040, {"v0.4.0": YML_WITH_V040})


def test_r3_inverse_stale_registration_refuses() -> None:
    # A versions: entry naming a tag that is not a real release tag
    # (deleted or never-pushed) refuses, naming the stale entry. The
    # scenario is chosen so ONLY this check can fire: v0.4.0 is a real tag
    # and is registered; v0.9.9 is registered but is not a tag.
    yml = YML_WITH_V040.replace(
        "  - tag: dev",
        "  - tag: v0.9.9\n    label: v0.9.9\n    git_ref: v0.9.9\n  - tag: dev",
    )
    with pytest.raises(SystemExit, match=r"v0\.9\.9"):
        _asm.check_registration(["v0.4.0"], yml, {"v0.4.0": YML_WITH_V040})


def test_r4_regime_consistency_a_versions_block_with_no_tags_refuses() -> None:
    # A list with no tags is a stale registration: the versions: key must
    # not exist while zero release tags exist (design §1.3). The block
    # carries only the tool's dev special, so R3 (TAG_RE-shaped entries)
    # cannot fire — this arm is the only one that can.
    with pytest.raises(SystemExit, match=r"versions"):
        _asm.check_registration([], YML_DEV_ONLY, {})


def test_r4_regime_consistency_zero_tags_and_no_block_is_the_honest_window() -> None:
    # The vacuous-green window: zero tags and no versions: key is
    # consistent — the port lands before any tag and stays green there.
    _asm.check_registration([], YML_UNVERSIONED, {})


def test_registration_parse_reads_only_the_versions_block() -> None:
    # The parse must not pick up tag-shaped strings outside versions:
    # (a git_ref: line or a prose comment is not a registration).
    text = YML_UNVERSIONED + "\n# tag: v9.9.9\nseo:\n  tag: not-a-version\n"
    assert _asm.yml_version_tags(text) == set()


# ── selector generation (design §1.4) ───────────────────────────────────────


def test_s1_rows_derive_from_the_tags() -> None:
    rows = _asm.selector_rows(["v0.1.0", "v0.4.0"])
    assert rows == [
        ("v0.4.0 (latest)", "docs/"),
        ("v0.1.0", "docs/v/v0.1.0/"),
        ("dev", "docs/v/dev/"),
    ]


def test_s1_zero_tag_regime_is_one_dev_row_valued_at_the_root() -> None:
    assert _asm.selector_rows([]) == [("dev", "docs/")]


def test_s2_latest_label_exists_iff_tags_exist() -> None:
    tagged = [label for label, _ in _asm.selector_rows(["v0.4.0"])]
    untagged = [label for label, _ in _asm.selector_rows([])]
    assert sum(1 for label in tagged if "(latest)" in label) == 1
    assert sum(1 for label in untagged if "(latest)" in label) == 0


def _stamped_copy(html: str) -> Path:
    """Stamp a copy of ``html`` and return its path (the assembly-copy seam)."""
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tmp:
        tmp.write(html)
        path = Path(tmp.name)
    _asm.stamp_website(path, _asm.website_stamp_map(ROOT))
    return path


def test_s3_scaffold_without_its_token_has_no_rows() -> None:
    # The selector was hand-edited away: nothing fills the select, so the
    # assembled copy carries zero option rows — which verify_tree's
    # selector-honesty arm refuses (design §1.4's fail-closed direction).
    html = SOURCE.read_text(encoding="utf-8").replace("{{stg-versions}}", "", 1)
    path = _stamped_copy(html)
    out = path.read_text(encoding="utf-8")
    select = re.search(r'<select class="version-select".*?</select>', out, re.DOTALL)
    assert select is not None, "the selector element must survive"
    assert "<option" not in select.group(0)


def test_s3_generation_fills_the_token_in_the_assembly_copy() -> None:
    html = SOURCE.read_text(encoding="utf-8")
    path = _stamped_copy(html)
    out = path.read_text(encoding="utf-8")
    assert "{{" not in out
    assert '<option value="docs/">dev</option>' in out  # zero tags on the real repo
    assert "(latest)" not in out  # a '(latest)' label with no releases is a lie
    # The source shape is untouched by construction: stamping writes the
    # assembly copy only (CON-13).
    assert "{{stg-versions}}" in html


def test_s3_a_token_the_generation_cannot_fill_refuses() -> None:
    # An unknown stg-* token is not the selector family and has no map
    # entry — stamp_website's stamp_unmapped_token arm refuses it rather
    # than letting it reach the published site.
    html = SOURCE.read_text(encoding="utf-8").replace(
        "v{{stg-otdp}}", "v{{stg-otdp}}{{stg-nope}}", 1
    )
    copy = _tmp_index(html)
    with pytest.raises(SystemExit, match=r"stamp_unmapped_token:"):
        _asm.stamp_website(copy, _asm.website_stamp_map(ROOT))


def _tmp_index(html: str) -> Path:
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tmp:
        tmp.write(html)
        return Path(tmp.name)
