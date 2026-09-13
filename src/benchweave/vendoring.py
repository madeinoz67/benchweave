"""Vendored-asset resolution: wheel-packaged first, dev-checkout fallback.

The runtime reads vendored contract corpora (``contracts/``) and the
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

from pathlib import Path

#: Packaged trees (present in a wheel install; absent in a dev checkout).
_PACKAGED_ROOT = Path(__file__).resolve().parent / "_vendored"
#: The repository root (a dev checkout; garbage in a wheel install).
_REPO_ROOT = Path(__file__).resolve().parents[2]


def contract_family(name: str) -> Path:
    """A vendored contract family directory (e.g. ``interface-v1.1.1``)."""
    packaged = _PACKAGED_ROOT / "contracts" / name
    if packaged.is_dir():
        return packaged
    return _REPO_ROOT / "contracts" / name


def sim_plugins_root() -> Path:
    """The BenchWeave simulator plugins root (``plugins/benchweave``)."""
    packaged = _PACKAGED_ROOT / "plugins" / "benchweave"
    if packaged.is_dir():
        return packaged
    return _REPO_ROOT / "plugins" / "benchweave"
