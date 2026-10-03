"""The UI route registry: the declared set gate D enumerates against
(GW-10, design §7-D).

One row per mounted route — path, methods, the seam operations the
route's handler calls, and a classification. ``interface`` rows carry
their operation mapping; ``session``/``assets``/``shell`` rows are the
explicitly-non-interface set (the login trio, the vendored-assets
route, the root hop and the namespace 404). The route-mapping suite
enumerates the mounted sub-app and compares BOTH directions against
this table, so a route registered without a row (or a row without a
route) reds — and the planted-route arms prove the checker polices.

Mutating vocabulary (GW-10, the PRD's fixed eight): G2 mounts none of
them; when G3/G4 add a mutating route its row names EXACTLY ONE of
``MUTATING_OPERATIONS`` — that is the gate's own tripwire against scope
creep (design R7).
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi.routing import APIRoute

#: The interface's eight mutating operations (GW-10's fixed list).
MUTATING_OPERATIONS: frozenset[str] = frozenset(
    {
        "lease_create",
        "lease_renew",
        "lease_release",
        "run_check",
        "run_start",
        "run_cancel",
        "change_submit",
        "change_apply",
    }
)

#: The twelve read operations (the 20-operation catalog minus the eight
#: mutating ones — ``operation-catalog.json`` is the authority).
READ_OPERATIONS: frozenset[str] = frozenset(
    {
        "gateway_info",
        "bench_list",
        "bench_get",
        "device_list",
        "device_get",
        "document_get",
        "run_get",
        "run_find",
        "events_get",
        "evidence_get",
        "artifact_read",
        "change_get",
    }
)


@dataclass(frozen=True)
class RouteSpec:
    """One declared route: its path, methods, the seam operations the
    handler calls, and its classification."""

    path: str
    methods: frozenset[str]
    operations: frozenset[str]
    classification: str  # "interface" | "session" | "assets" | "shell"


def _methods(*names: str) -> frozenset[str]:
    return frozenset(names)


#: The declared set — one row per route the UI router registers, in
#: registration order (registration order IS match order: the namespace
#: 404 must stay last).
UI_ROUTES: tuple[RouteSpec, ...] = (
    RouteSpec(
        path="/",
        methods=_methods("GET"),
        operations=frozenset({"gateway_info", "bench_list"}),
        classification="interface",
    ),
    RouteSpec(
        path="/login-codes",
        methods=_methods("POST"),
        operations=frozenset(),
        classification="session",
    ),
    RouteSpec(
        path="/login",
        methods=_methods("GET"),
        operations=frozenset(),
        classification="session",
    ),
    RouteSpec(
        path="/logout",
        methods=_methods("POST"),
        operations=frozenset(),
        classification="session",
    ),
    RouteSpec(
        path="/benches/{bench_id}",
        methods=_methods("GET"),
        operations=frozenset({"bench_get", "device_list", "events_get"}),
        classification="interface",
    ),
    RouteSpec(
        path="/benches/{bench_id}/devices/{device_id}",
        methods=_methods("GET"),
        operations=frozenset({"device_get", "document_get"}),
        classification="interface",
    ),
    RouteSpec(
        path="/runs/{run_id}",
        methods=_methods("GET"),
        operations=frozenset({"run_get"}),
        classification="interface",
    ),
    RouteSpec(
        path="/requests/{request_id}",
        methods=_methods("GET"),
        operations=frozenset({"run_find"}),
        classification="interface",
    ),
    RouteSpec(
        path="/evidence/{evidence_id}",
        methods=_methods("GET"),
        operations=frozenset({"evidence_get"}),
        classification="interface",
    ),
    RouteSpec(
        path="/artifacts/{artifact_id}",
        methods=_methods("GET"),
        operations=frozenset({"artifact_read"}),
        classification="interface",
    ),
    RouteSpec(
        path="/documents/{sha256}",
        methods=_methods("GET"),
        operations=frozenset({"document_get"}),
        classification="interface",
    ),
    RouteSpec(
        path="/assets/{name}",
        methods=_methods("GET"),
        operations=frozenset(),
        classification="assets",
    ),
    RouteSpec(
        path="/{path:path}",
        methods=_methods(
            "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"
        ),
        operations=frozenset(),
        classification="shell",
    ),
)


def route_mapping_violations(routes: list[APIRoute]) -> list[str]:
    """GW-10's checker: every route in ``routes`` must appear in
    ``UI_ROUTES`` with the same methods, and the declared set must be
    fully present. Returns one message per violation (the suite asserts
    the empty set on the real app and non-empty on the planted arms)."""
    declared = {spec.path: spec for spec in UI_ROUTES}
    seen: set[str] = set()
    violations: list[str] = []
    for route in routes:
        path = route.path
        seen.add(path)
        spec = declared.get(path)
        if spec is None:
            violations.append(
                f"route {path} is mounted but has no UI_ROUTES row"
            )
            continue
        methods = frozenset(route.methods or ())
        if methods != spec.methods:
            violations.append(
                f"route {path} serves {sorted(methods)} but its row declares"
                f" {sorted(spec.methods)}"
            )
        if spec.classification == "interface" and methods & {
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
        }:
            if len(spec.operations) != 1:
                violations.append(
                    f"mutating route {path} maps {len(spec.operations)}"
                    " operations — GW-10 requires exactly one"
                )
            elif not spec.operations <= MUTATING_OPERATIONS:
                violations.append(
                    f"mutating route {path} maps {sorted(spec.operations)}"
                    " — outside GW-10's mutating vocabulary"
                )
    for spec in UI_ROUTES:
        if spec.path not in seen:
            violations.append(
                f"UI_ROUTES row {spec.path} is declared but not mounted"
            )
    return violations
