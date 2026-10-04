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
        # The G2c event bridge (§2.5): a READ route over events_get —
        # the stream polls the seam; the bridge registry (session-side
        # ownership, no seam call) is the route's own state.
        path="/benches/{bench_id}/events/stream",
        methods=_methods("GET"),
        operations=frozenset({"events_get"}),
        classification="interface",
    ),
    RouteSpec(
        # G3a lease control (issue #304, design §2.2): the three mutating
        # rows each map EXACTLY ONE operation (GW-10); the fragment GET
        # below is G3a's one deliberate non-interface row — it renders
        # this session's own response-sourced views beside the bench
        # projection, so it is session-classified (the "complete
        # non-interface set" assertion names it deliberately).
        path="/benches/{bench_id}/leases",
        methods=_methods("POST"),
        operations=frozenset({"lease_create"}),
        classification="interface",
    ),
    RouteSpec(
        path="/leases/{lease_id}/renewals",
        methods=_methods("POST"),
        operations=frozenset({"lease_renew"}),
        classification="interface",
    ),
    RouteSpec(
        path="/leases/{lease_id}/release",
        methods=_methods("POST"),
        operations=frozenset({"lease_release"}),
        classification="interface",
    ),
    RouteSpec(
        path="/benches/{bench_id}/controls",
        methods=_methods("GET"),
        operations=frozenset({"bench_get", "events_get"}),
        classification="session",
    ),
    RouteSpec(
        # G3b (issue #304, design §2.4): staging is a session-layer
        # action — no seam write, so no interface mapping; the staging
        # record it updates is presentation of this session's own
        # cycle. Reads it composes: the binding pin (document_get) and
        # the bench projection.
        path="/benches/{bench_id}/staging",
        methods=_methods("POST"),
        operations=frozenset(),
        classification="session",
    ),
    RouteSpec(
        # The arm/disarm pair: session-layer state transitions over the
        # recorded cycle — reads only (the DEP7 chain + GW-56's bound).
        path="/benches/{bench_id}/staging/arm",
        methods=_methods("POST"),
        operations=frozenset(),
        classification="session",
    ),
    RouteSpec(
        path="/benches/{bench_id}/staging/disarm",
        methods=_methods("POST"),
        operations=frozenset(),
        classification="session",
    ),
    RouteSpec(
        # The preflight (GW-51): one seam mutation — run_check.
        path="/benches/{bench_id}/run-checks",
        methods=_methods("POST"),
        operations=frozenset({"run_check"}),
        classification="interface",
    ),
    RouteSpec(
        # The start (GW-50–53): one seam mutation — run_start.
        path="/benches/{bench_id}/run-starts",
        methods=_methods("POST"),
        operations=frozenset({"run_start"}),
        classification="interface",
    ),
    RouteSpec(
        # G4 (issue #305, design record §2.2): the submit half of GW-10's
        # last two rows — one operation, change_submit; the §9 id is the
        # form's own (the GW-13 rule) and a §9 replay of the identical
        # form returns the original change.
        path="/benches/{bench_id}/changes",
        methods=_methods("POST"),
        operations=frozenset({"change_submit"}),
        classification="interface",
    ),
    RouteSpec(
        # The review page: a read composing change_get (the record); the
        # approval workspace renders from the session's own loaded view
        # (design §2.3), the document link pointing at the existing
        # document page.
        path="/changes/{change_id}",
        methods=_methods("GET"),
        operations=frozenset({"change_get"}),
        classification="interface",
    ),
    RouteSpec(
        # G4 (issue #305, design record §2.6): GW-10's LAST mutating row —
        # one operation, change_apply. The form carries only the §9 id
        # and the approver's detached token; generation and approval ref
        # are server-side truth. The GW-71 fire-time guard re-reads the
        # approval document before the send (no seam call when the UI
        # can see the gateway would refuse).
        path="/changes/{change_id}/apply",
        methods=_methods("POST"),
        operations=frozenset({"change_apply"}),
        classification="interface",
    ),
    RouteSpec(
        # G4 §2.3 step 1: the approval load is a session-layer action
        # (the staging trio's shape) — no seam write; it composes
        # ``change_get`` + ``document_get`` reads and records what the
        # approval document says in the session's change view.
        path="/changes/{change_id}/approval",
        methods=_methods("POST"),
        operations=frozenset(),
        classification="session",
    ),
    RouteSpec(
        path="/runs/{run_id}",
        methods=_methods("GET"),
        operations=frozenset({"run_get"}),
        classification="interface",
    ),
    RouteSpec(
        # The cancel (GW-53/55): one seam mutation — run_cancel; the
        # pending-cancel marker it records is session-side presentation.
        path="/runs/{run_id}/cancellations",
        methods=_methods("POST"),
        operations=frozenset({"run_cancel"}),
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
