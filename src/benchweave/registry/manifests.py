# src/benchweave/registry/manifests.py
"""Registry contract §10 semantic admission over schema-valid manifests.

Structural validation (Task 1 loaders) runs first; this module owns the
closure-level semantics the schema cannot express. Reason codes raised via
``RegistryRejected``:

- ``duplicate_package`` — one ``(registry_id, package_id)`` twice in a closure
- ``missing_dependency`` — a declared dependency absent from the closure
- ``cycle`` — the dependency graph is not acyclic
- ``conflict`` — the same provided profile/descriptor id from unrelated packages
- ``path_unsafe`` / ``duplicate_path`` / ``case_fold_collision`` — payload path hygiene
- ``invalid_spdx`` — licence expression is not a token/operator expression
- ``mutable_source_revision`` — source revision names a mutable branch or tag
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from itertools import combinations
from typing import Any

from benchweave.registry.schemas import RegistryRejected

#: Closure key: ``(registry_id, package_id, version)``.
Key = tuple[str, str, str]

#: Bare branch/tag names never identify immutable source content (contract §10).
_MUTABLE_REVISIONS = frozenset({"main", "master", "HEAD", "latest"})

#: PoC SPDX licence-expression shape: licence and exception ids are short
#: dot/dash/plus words joined by the SPDX binary operators.
_SPDX_TOKEN = re.compile(r"[A-Za-z0-9.+-]+")
_SPDX_OPERATORS = frozenset({"AND", "OR", "WITH"})


def _check_payload_paths(manifest: Mapping[str, Any]) -> None:
    """Defence in depth for contract §4 path rules the schema regex mostly covers."""
    seen: set[str] = set()
    seen_folded: set[str] = set()
    for entry in manifest["payload"]["files"]:
        path = entry["path"]
        if path.startswith("/") or ".." in path.split("/") or "\\" in path:
            raise RegistryRejected("path_unsafe")
        if path in seen:
            raise RegistryRejected("duplicate_path")
        folded = path.casefold()
        if folded in seen_folded:
            raise RegistryRejected("case_fold_collision")
        seen.add(path)
        seen_folded.add(folded)


def _spdx_parses(expression: str) -> bool:
    """Minimal licence-expression parser: ``token (OPERATOR token)*``.

    Contract §10 rejects a nonempty string that is not an expression: plain
    prose (adjacent words with no operator) fails, as do leading or dangling
    operators. Token shape stands in for the configured SPDX id list (PoC).
    """
    parts = expression.split()
    if not parts:
        return False
    expect_token = True
    for part in parts:
        if part in _SPDX_OPERATORS:
            if expect_token:
                return False
            expect_token = True
        else:
            if not expect_token or _SPDX_TOKEN.fullmatch(part) is None:
                return False
            expect_token = False
    return not expect_token


def check_closure(manifests: Mapping[Key, dict[str, Any]]) -> None:
    """Admit a schema-valid dependency closure or raise ``RegistryRejected``.

    ``manifests`` maps ``(registry_id, package_id, version)`` to already
    schema-valid manifest dicts and is not modified.
    """
    # Pass 1 — per-manifest checks; index packages and provided ids.
    by_package: dict[tuple[str, str], Key] = {}
    providers: dict[str, set[Key]] = {}
    for key, manifest in manifests.items():
        package = (manifest["registry_id"], manifest["package_id"])
        if package in by_package:
            raise RegistryRejected("duplicate_package")
        by_package[package] = key
        _check_payload_paths(manifest)
        if not _spdx_parses(manifest["licence"]["spdx_expression"]):
            raise RegistryRejected("invalid_spdx")
        if manifest["source"]["revision"] in _MUTABLE_REVISIONS:
            raise RegistryRejected("mutable_source_revision")
        for ids in (manifest["provides"]["profile_ids"], manifest["provides"]["descriptor_ids"]):
            for ident in ids:
                providers.setdefault(ident, set()).add(key)

    dependencies: dict[Key, set[Key]] = {
        key: {
            (dep["registry_id"], dep["package_id"], dep["version"])
            for dep in manifest["dependencies"]
        }
        for key, manifest in manifests.items()
    }

    # Pass 2 — every declared dependency resolves inside the closure.
    for deps in dependencies.values():
        for dep_key in deps:
            if dep_key not in manifests:
                raise RegistryRejected("missing_dependency")

    # Pass 3 — one owning definition per provided id. An implementation
    # re-expresses the descriptor id of the descriptor package it depends on
    # (contract §3: "executable adapter and its supported descriptors"), so a
    # direct dependency edge between two providers establishes ownership;
    # unrelated packages claiming the same provided id conflict (contract §10).
    for keys in providers.values():
        for left, right in combinations(sorted(keys), 2):
            if right not in dependencies[left] and left not in dependencies[right]:
                raise RegistryRejected("conflict")

    # Pass 4 — the dependency graph is acyclic (depth-first search).
    visiting: set[Key] = set()
    done: set[Key] = set()

    def visit(key: Key) -> None:
        if key in done:
            return
        if key in visiting:
            raise RegistryRejected("cycle")
        visiting.add(key)
        for dep_key in sorted(dependencies[key]):
            visit(dep_key)
        visiting.remove(key)
        done.add(key)

    for key in manifests:
        visit(key)
