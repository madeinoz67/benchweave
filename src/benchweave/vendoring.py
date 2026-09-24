"""Vendored-asset resolution: wheel-packaged first, dev-checkout fallback.

The runtime reads vendored contract corpora (``standards/``) and the
BenchWeave simulator plugins (``plugins/benchweave/``) that live at the
REPOSITORY root beside the suites that pin them. A wheel install has no
repository around it, so the wheel packages the same trees verbatim under
``benchweave/_vendored/`` (hatch ``force-include`` — one source of truth,
no copies under ``src/``). Resolution is packaged-first: the packaged tree
when it exists (a wheel install), else the repository layout (a dev
checkout or editable install).

The fixture lattice (``fixtures/execution``) is deliberately NOT vendored:
it is an operator-supplied input with its own flag and env var
(``--fixtures`` / ``BENCHWEAVE_FIXTURES``) and a disclosed repo-relative
default (see :mod:`benchweave.cli.demo` and the operator guide) — a
wheel-installed CLI passes it explicitly.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from benchweave.standards.manifest import StandardsError, load_manifest

#: Packaged trees (present in a wheel install; absent in a dev checkout).
_PACKAGED_ROOT = Path(__file__).resolve().parent / "_vendored"
#: The repository root (a dev checkout; garbage in a wheel install).
_REPO_ROOT = Path(__file__).resolve().parents[2]


class CorpusResolution(StrEnum):
    """Which contract corpus the composed gateway resolves execution
    documents against (issue #176 increment 2, design §1b).

    ``ACTIVE`` is today's frozen-literal posture, byte-identical; the
    promotion's literal sweep is what moves it. ``DEV_HEAD`` resolves the
    manifest-declared dev head once at composition — the gateway runtime
    twin of the checker lane's ``--corpus`` override. There is no path
    member and no third state: the manifest's declared head is the only
    thing a dev composition can resolve (accept-exactly-the-declared-head,
    made typal), and an installed wheel physically cannot resolve
    ``DEV_HEAD`` (the head never exports — the devstage wheel exclusion).
    """

    ACTIVE = "active"
    DEV_HEAD = "dev_head"


def contract_family(name: str) -> Path:
    """A vendored contract family directory (e.g. ``interface/0.1.0``)."""
    packaged = _PACKAGED_ROOT / "contracts" / name
    if packaged.is_dir():
        return packaged
    return _REPO_ROOT / "standards" / name


def sim_plugins_root() -> Path:
    """The BenchWeave simulator plugins root (``plugins/benchweave``)."""
    packaged = _PACKAGED_ROOT / "plugins" / "benchweave"
    if packaged.is_dir():
        return packaged
    return _REPO_ROOT / "plugins" / "benchweave"


def declared_dev_family(standard_id: str) -> Path:
    """The manifest-declared dev head's contract directory, or a loud refusal.

    The runtime twin of the checker lane's ``_declared_dev_head``
    (``scripts/architecture/_validation_report.py``): the manifest is
    loaded through the canonical loader, so every dev-block shape refusal
    the loader enforces — a malformed block, a non-``<target>-dev``
    version, a target that is not strictly greater than active — is this
    resolver's refusal too, with the loader's own message (same words on
    both surfaces). ``{standard_id}_dev_head_absent:`` when no head is
    declared (the post-promotion shape — the seam cannot outlive the
    head); ``dev_head_unresolvable:`` naming the missed path when the
    resolved directory does not exist (a packaged install never carries a
    dev head — never a silent fallback to the active family).

    There is no path parameter anywhere: the manifest's declared head is
    the only thing this function can return (the
    accept-exactly-the-declared-head rule, made typal). A manifest the
    loader cannot find refuses ``{standard_id}_manifest_absent:`` — the
    lane's own word for that state.
    """
    try:
        manifest = load_manifest(_REPO_ROOT)
    except FileNotFoundError as exc:
        raise StandardsError(
            f"{standard_id}_manifest_absent: standards-manifest.json not found — "
            f"the dev head for {standard_id} cannot be derived"
        ) from exc
    # StandardsError (the loader's dev-block shape refusals) propagates
    # verbatim: its prefixed message IS this resolver's refusal.
    entry = next((e for e in manifest.standards if e.id == standard_id), None)
    if entry is None:
        raise StandardsError(
            f"{standard_id}_manifest_absent: standards-manifest.json carries no "
            f"{standard_id} entry — the dev head cannot be derived"
        )
    if entry.dev is None:
        raise StandardsError(
            f"{standard_id}_dev_head_absent: the manifest declares no dev head "
            f"for {standard_id} — nothing for a dev composition to resolve"
        )
    family = contract_family(f"{standard_id}/{entry.dev.version}")
    if not family.is_dir():
        raise StandardsError(
            f"dev_head_unresolvable: {family} — the resolved dev head directory "
            f"for {standard_id} does not exist (a packaged install never "
            "carries a dev head; the active family is never substituted)"
        )
    return family
