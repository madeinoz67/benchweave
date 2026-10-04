"""The docs-site tag-namespace refusal pin (issue #380, design record §3).

``refuse_if_tagged`` (``scripts/assemble_docs_site.py``) is the loud gate
that keeps the gateway's UNVERSIONED docs assembly from ever shipping for a
released gateway: once an exact ``vX.Y.Z`` release tag exists, every docs
run refuses rather than silently publishing an unversioned tree. The
ui-html line releases from THIS SAME repository under ``ui-html-vX.Y.Z``
tags, so the namespace contract this pin holds is: **``ui-html-v*`` tags
must never trip the gateway's refusal** — a regression here bricks docs CI
on every open PR the moment an ordinary ui-html release lands.

The listing is injected at the ``run`` helper (no git subprocess, no tag
created in the working tree — xdist-safe), and it reaches ``TAG_RE``
UNFILTERED. The real pipeline's ``git tag --list v*`` glob excludes
``ui-html-v*`` upstream of the filter; the injection point is downstream
of the glob, so the pin holds the FILTER in isolation — strictly stronger
than the real pipeline, and the only posture under which the mutation
control can bite (a glob-faithful listing would make the ui-html arm
unprovable: the glob would mask any TAG_RE regression that matters).

Arms:

- R1 — an exact ``vX.Y.Z`` tag in the listing refuses, naming the tag.
- R2 — ``ui-html-v*`` tags pass, alone and alongside a gateway tag; a
  mixed listing's refusal names ONLY the gateway tag.
- R3 — a pre-release-suffixed ``v*`` tag passes (``TAG_RE`` is exact-match
  — the stable-only policy is procedural, the walk's tag↔version row is
  the semantic gate; this refusal is not where that policy lives).
- R4 — wiring: the refusal reads the tag listing through the ``run``
  helper via the EXACT command literal ``['git', 'tag', '--list', 'v*']`` —
  closing both halves of the silent lie: a pass arm that passed by doing
  nothing, and a mutated selector pattern that can no longer carry a
  gateway tag (adv2 fold F1: the pattern ``v*`` → ``ui-html-*`` reddens
  here).

Mutation control (design acceptance A2, RED evidence in the commit): with
``TAG_RE`` weakened to accept an arbitrary prefix before the version core
(``.*v(\\d+)\\.(\\d+)\\.(\\d+)$``) the R2 arm FAILS — the exact shape an
anchor regression takes; with the ``$`` anchor dropped the R3 arm FAILS;
with the listing's selector pattern mutated (``v*`` → ``ui-html-*``) every
pass arm's R4 command-literal assert FAILS (adv2 fold F1). A pin that
passes under any of these mutations proves nothing.
"""

from __future__ import annotations

import importlib.util
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


def _refuse_with_listing(monkeypatch: pytest.MonkeyPatch, tags: list[str]) -> None:
    """Run ``refuse_if_tagged`` over a synthetic tag listing (see module docstring).

    Raises the refusal's own ``SystemExit`` for a tripped listing, so the
    call site's ``pytest.raises`` is the assertion; a listing that passes
    simply returns.
    """
    seen: list[list[str]] = []

    def fake_run(
        cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None
    ) -> str:
        seen.append(cmd)
        return "".join(f"{tag}\n" for tag in tags)

    monkeypatch.setattr(_asm, "run", fake_run)
    _asm.refuse_if_tagged()
    # R4 (pass arms only — a tripped listing raises past this point): the
    # refusal consulted the REAL listing command, exact literal — pattern
    # token included: a mutated selector (`git tag --list ui-html-*`, or
    # any pattern that cannot carry a gateway tag) reddens here instead of
    # silently greening (adv2 fold F1).
    assert seen and seen[0] == ["git", "tag", "--list", "v*"], (
        "refuse_if_tagged must list tags via exactly ['git', 'tag', '--list', 'v*']"
    )


def test_r1_exact_gateway_tag_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit, match=r"release tag\(s\) present \(v0\.9\.0\)"):
        _refuse_with_listing(monkeypatch, ["v0.9.0"])


def test_r2_ui_html_tags_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    # Alone: the whole ui-html tag line must leave the gateway's docs
    # assembly alone.
    _refuse_with_listing(monkeypatch, ["ui-html-v0.1.0", "ui-html-v0.2.0"])


def test_r2b_mixed_listing_refuses_naming_only_the_gateway_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Alongside a gateway tag: the refusal fires (the gateway tag is real)
    # and names ONLY the gateway tag — a ui-html release landing next to a
    # gateway tag must not widen the refusal's blast radius.
    with pytest.raises(SystemExit, match=r"release tag\(s\) present \(v0\.9\.0\)") as excinfo:
        _refuse_with_listing(monkeypatch, ["ui-html-v0.2.0", "v0.9.0"])
    assert "ui-html-v0.2.0" not in str(excinfo.value)


@pytest.mark.parametrize("tag", ["v0.9.0rc1", "v1.0.0b2"])
def test_r3_pre_release_suffixed_tags_pass(
    monkeypatch: pytest.MonkeyPatch, tag: str
) -> None:
    _refuse_with_listing(monkeypatch, [tag])
