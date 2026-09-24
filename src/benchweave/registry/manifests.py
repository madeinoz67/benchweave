# src/benchweave/registry/manifests.py
"""Registry contract §10 semantic admission over schema-valid manifests.

Structural validation (Task 1 loaders) runs first; this module owns the
closure-level semantics the schema cannot express. Reason codes raised via
``RegistryRejected``:

- ``duplicate_package`` — one ``(registry_id, package_id)`` twice in a closure
- ``missing_dependency`` — a declared dependency absent from the closure
- ``cycle`` — the dependency graph is not acyclic
- ``conflict`` — the same provided profile/descriptor id (per kind) from
  packages outside the §3 ownership direction (only an implementation
  re-expressing the id its direct descriptor dependency provides is exempt;
  profile ids and descriptor ids are separate namespaces)
- ``path_unsafe`` / ``duplicate_path`` / ``case_fold_collision`` — payload path hygiene
- ``invalid_spdx`` — licence expression is not a token/operator expression
- ``mutable_source_revision`` — source revision is EXACTLY one of the denied
  mutable names (``main``/``master``/``HEAD``/``latest``). This is a denylist,
  not a ref model: other branch or tag names are NOT recognized as mutable
  (real tag/ref semantics are carried to WP07)
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from itertools import combinations
from typing import Any

from benchweave.registry.schemas import RegistryRejected

#: Closure key: ``(registry_id, package_id, version)``.
Key = tuple[str, str, str]

#: Exact revision names denied as mutable (contract §10). A denylist, not a
#: ref model — any other branch/tag name passes (WP07 carry).
_MUTABLE_REVISIONS = frozenset({"main", "master", "HEAD", "latest"})

#: PoC SPDX licence-expression shape: licence and exception ids are short
#: dot/dash/plus words joined by the SPDX binary operators.
_SPDX_TOKEN = re.compile(r"[A-Za-z0-9.+-]+")
_SPDX_OPERATORS = frozenset({"AND", "OR", "WITH"})


def canonical_manifest_bytes(parsed: dict[str, Any]) -> bytes:
    """The ONE canonical serialization the manifest pin lattice is keyed by.

    Bytes are ``json.dumps(parsed, sort_keys=True, separators=(",", ":"))
    + "\\n"`` — sorted keys, compact separators, ASCII-escaped, LF line
    endings with the trailing newline. Both enforcement sites call this
    single function — the resolver's canonicality refusal
    (``Resolver._resolve_release``) and the loader's re-hash gate
    (``load_otdp_plugin``) — so the two can never drift apart (the
    ``check_payload_path`` single-sourcing shape). The gF2 agreement pin
    additionally pins these bytes to the test's own independent oracle.
    """
    return (json.dumps(parsed, sort_keys=True, separators=(",", ":")) + "\n").encode()


def check_payload_path(path: str) -> None:
    """Contract §4 payload-path rule, single-sourced for every consumer.

    Raises ``RegistryRejected("path_unsafe")`` on an absolute path, a ``..``
    segment, or a backslash. Both layers that enforce §4 call this one
    function — ``_check_payload_paths`` on declared inventory paths at
    closure admission, and admission's verified extraction on real zip
    member names — so the two can never drift.
    """
    if path.startswith("/") or ".." in path.split("/") or "\\" in path:
        raise RegistryRejected("path_unsafe")


def _check_payload_paths(manifest: Mapping[str, Any]) -> None:
    """Defence in depth for contract §4 path rules the schema regex mostly covers."""
    seen: set[str] = set()
    seen_folded: set[str] = set()
    for entry in manifest["payload"]["files"]:
        path = entry["path"]
        check_payload_path(path)
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


def _re_expresses(
    manifests: Mapping[Key, dict[str, Any]],
    dependencies: Mapping[Key, set[Key]],
    dependent: Key,
    depended_upon: Key,
) -> bool:
    """Contract §3 ownership: ``dependent`` is an implementation re-expressing
    an id its direct dependency ``depended_upon`` — a descriptor — provides.
    The direction is fixed: only the implementation side of the edge can own
    the re-expressed id.
    """
    return (
        manifests[dependent]["kind"] == "implementation"
        and manifests[depended_upon]["kind"] == "descriptor"
        and depended_upon in dependencies[dependent]
    )


def check_closure(manifests: Mapping[Key, dict[str, Any]]) -> None:
    """Admit a schema-valid dependency closure or raise ``RegistryRejected``.

    ``manifests`` maps ``(registry_id, package_id, version)`` to already
    schema-valid manifest dicts and is not modified.
    """
    # Pass 1 — per-manifest checks; index packages and provided ids per kind.
    by_package: dict[tuple[str, str], Key] = {}
    profile_providers: dict[str, set[Key]] = {}
    descriptor_providers: dict[str, set[Key]] = {}
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
        for ident in manifest["provides"]["profile_ids"]:
            profile_providers.setdefault(ident, set()).add(key)
        for ident in manifest["provides"]["descriptor_ids"]:
            descriptor_providers.setdefault(ident, set()).add(key)

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

    # Pass 3 — one owning definition per provided id, PER KIND. Profile ids
    # and descriptor ids live in separate namespaces, so the same string
    # provided as different kinds never collides. Within a kind, an
    # implementation re-expresses the descriptor id of the descriptor package
    # it depends on (contract §3: "executable adapter and its supported
    # descriptors") — the ONLY exemption, and it is ownership-direction-only:
    # the DEPENDENT must be the implementation and the DEPENDED-UPON the
    # descriptor. A wrapper descriptor sharing its implementation's id is
    # not exempt (wrappers need distinct ids), and anything else claiming
    # the same provided id conflicts (contract §10/§11).
    for providers in (profile_providers, descriptor_providers):
        for keys in providers.values():
            for left, right in combinations(sorted(keys), 2):
                if _re_expresses(manifests, dependencies, left, right) or _re_expresses(
                    manifests, dependencies, right, left
                ):
                    continue
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
