"""GW-10's route-mapping gate (design §7-D): the mounted ``/ui`` routes
are EXACTLY the declared set, every mutating method maps to exactly one
of the interface's eight mutating operations, and the session-layer
routes are explicitly flagged non-interface.

The enumeration comes from the app object (``build_ui_app``'s router —
the same object ``create_app`` mounts), never from the module's own
self-description alone: the checker compares BOTH directions, so a route
registered without a registry row reds (the planted-route kill control
proves the checker polices rather than documents), and a registry row
without a mounted route reds too.

Mutating vocabulary (GW-10, the PRD's fixed eight): lease_create,
lease_renew, lease_release, run_check, run_start, run_cancel,
change_submit, change_apply — G2 mounts NONE of them; G3/G4 add them
and this suite polices each addition's mapping the day it lands.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from fastapi.routing import APIRoute
from ui_gateway_support import NOW_EPOCH

from benchweave.interfaces.sessions import SessionStore
from benchweave.interfaces.ui import build_ui_app, build_ui_router
from benchweave.interfaces.ui_routes import (
    MUTATING_OPERATIONS,
    READ_OPERATIONS,
    UI_ROUTES,
    RouteSpec,
    route_mapping_violations,
)


class _NullOperations:
    """An operations seam stand-in (the routing suite's shape): the
    mapping arms must never reach it."""

    def __getattr__(self, name: str) -> object:
        def _unreachable(*args: object, **kwargs: object) -> object:
            raise AssertionError(f"the mapping arm must not reach operations.{name}")

        return _unreachable


def _mounted_routes() -> list[APIRoute]:
    """The UI sub-app's OWN routes — the object ``create_app`` mounts,
    enumerated from the app (this FastAPI wraps an included router in a
    lazy ``_IncludedRouter``; its effective candidates carry each real
    route as ``original_route``)."""
    store = SessionStore(now_epoch=lambda: NOW_EPOCH)
    app = build_ui_app(
        cast(Any, _NullOperations()),
        store,
        secret=b"route-mapping",
        limits={"max_json_bytes": 64},
    )
    routes: list[APIRoute] = []
    for mounted in app.router.routes:
        candidates = getattr(mounted, "effective_candidates", None)
        if candidates is None:
            if isinstance(mounted, APIRoute):
                routes.append(mounted)
            continue
        routes.extend(
            candidate.original_route for candidate in candidates()
        )
    assert routes, "the UI sub-app has no routes to enumerate"
    return routes


def test_every_mounted_route_is_declared_and_vice_versa() -> None:
    """Both directions: the mounted set IS ``UI_ROUTES`` (path + methods)
    — nothing extra mounted, nothing declared but missing."""
    mounted = {
        (route.path, frozenset(route.methods or ())) for route in _mounted_routes()
    }
    declared = {(spec.path, spec.methods) for spec in UI_ROUTES}
    assert mounted == declared, (
        f"mounted-but-undeclared: {sorted(mounted - declared)}; "
        f"declared-but-unmounted: {sorted(declared - mounted)}"
    )


def test_no_route_has_unmapped_violations() -> None:
    assert route_mapping_violations(_mounted_routes()) == []


def test_interface_routes_map_to_catalog_operations_only() -> None:
    """Every interface-classified route maps to operations that exist in
    the interface's own split: mutating methods map to EXACTLY ONE of
    the eight mutating operations (GW-10); read methods map within the
    twelve read operations."""
    for spec in UI_ROUTES:
        if spec.classification != "interface":
            continue
        if spec.methods & {"POST", "PUT", "PATCH", "DELETE"}:
            assert len(spec.operations) == 1, spec.path
            assert next(iter(spec.operations)) in MUTATING_OPERATIONS, spec.path
        else:
            assert spec.operations, f"{spec.path} maps no operation"
            assert set(spec.operations) <= READ_OPERATIONS, spec.path


def test_the_non_interface_set_is_exactly_the_declared_one() -> None:
    """The session trio (mint/exchange/logout) plus the assets route and
    the shell routes (root hop, the namespace 404) are the COMPLETE
    non-interface set — itself asserted, so a new non-interface route
    must extend this list deliberately (R7's tripwire: any mutating
    ``/ui`` route beyond the session trio is scope creep into G3)."""
    non_interface = {
        spec.path for spec in UI_ROUTES if spec.classification != "interface"
    }
    assert non_interface == {
        "/login-codes",
        "/login",
        "/logout",
        "/assets/{name}",
        "/benches/{bench_id}/controls",
        "/benches/{bench_id}/staging",
        "/benches/{bench_id}/staging/arm",
        "/benches/{bench_id}/staging/disarm",
        "/{path:path}",
    }


def test_g2b_read_surface_is_the_declared_operations() -> None:
    """The operation vocabulary the interface routes serve, regenerable
    from the registry: the read pages' eleven reads (GET interface
    routes) plus — since G3a — the three lease mutations (POST
    interface routes, one each, GW-10's one-operation rule policed
    separately)."""
    served_reads = set[str]()
    served_mutations = set[str]()
    for spec in UI_ROUTES:
        if spec.classification != "interface":
            continue
        if spec.methods & {"POST", "PUT", "PATCH", "DELETE"}:
            served_mutations.update(spec.operations)
        else:
            served_reads.update(spec.operations)
    assert served_reads == {
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
    assert served_mutations == {
        "lease_create",
        "lease_renew",
        "lease_release",
        "run_check",
        "run_start",
        "run_cancel",
        # G4 mounts GW-10's last two rows, one operation each
        # (design record §2.6): submit here; apply joins with its
        # commit.
        "change_submit",
    }


# --- the kill control (design §7-D): a planted route must RED the checker -----


def test_a_planted_mutating_route_without_mapping_reds() -> None:
    """A planted mutating route (the G3-shaped scope-creep this gate
    exists to catch) MUST produce a violation naming it — proving the
    checker polices the enumeration, not documents it."""
    store = SessionStore(now_epoch=lambda: 1)
    router = build_ui_router(
        cast(Any, _NullOperations()),
        store,
        secret=b"route-mapping",
        limits={"max_json_bytes": 64},
    )

    @router.post("/benches/{bench_id}/runs", include_in_schema=False)
    async def _planted(bench_id: str) -> object:  # pragma: no cover - never called
        return {}

    routes = [
        route for route in router.routes if isinstance(route, APIRoute)
    ]
    violations = route_mapping_violations(routes)
    assert any("/benches/{bench_id}/runs" in violation for violation in violations), (
        f"the checker did not name the planted route: {violations}"
    )


def test_a_planted_undeclared_read_route_reds() -> None:
    """The enumeration direction: a route mounted without a registry row
    (read-shaped) also reds — both directions police."""
    store = SessionStore(now_epoch=lambda: 1)
    router = build_ui_router(
        cast(Any, _NullOperations()),
        store,
        secret=b"route-mapping",
        limits={"max_json_bytes": 64},
    )

    @router.get("/extra/{thing}", include_in_schema=False)
    async def _planted_read(thing: str) -> object:  # pragma: no cover
        return {}

    routes = [route for route in router.routes if isinstance(route, APIRoute)]
    violations = route_mapping_violations(routes)
    assert any("/extra/{thing}" in violation for violation in violations)


# --- H1 (lane-2 F2 rec, #368): the checker's own mapping clauses pinned ----------
#
# The mutation proof showed both mutating-mapping clauses deletable green:
# no arm drove a spec that maps TWO operations on a mutating route, or one
# outside GW-10's vocabulary. Both arms below drive the CHECKER with
# registry rows the mounted router never carries (monkeypatched in) —
# the planted-route arms above prove the ENUMERATION; these prove the
# MAPPING JUDGEMENT, which is the clauses' own input space.


def _checker_input(
    monkeypatch: pytest.MonkeyPatch, spec: RouteSpec
) -> list[APIRoute]:
    """A one-route list matching ``spec`` against a registry carrying it
    (param-free paths keep the planted handler honest — it is never
    called; the checker reads the route table, not handlers)."""
    from fastapi import APIRouter

    import benchweave.interfaces.ui_routes as ui_routes

    monkeypatch.setattr(ui_routes, "UI_ROUTES", (*UI_ROUTES, spec))
    router = APIRouter()
    method = next(iter(spec.methods))

    async def _planted() -> object:  # pragma: no cover - never called
        return {}

    router.add_api_route(
        spec.path, _planted, methods=[method], include_in_schema=False
    )
    return [route for route in router.routes if isinstance(route, APIRoute)]


def test_a_mutating_route_mapping_two_operations_reds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clause 1: a mutating route mapping MORE THAN ONE operation violates
    GW-10's exactly-one rule — the checker must name it."""
    spec = RouteSpec(
        path="/planted-both",
        methods=frozenset({"POST"}),
        operations=frozenset({"run_start", "run_cancel"}),
        classification="interface",
    )
    violations = route_mapping_violations(_checker_input(monkeypatch, spec))
    assert any(
        "maps 2 operations" in violation
        and "exactly one" in violation
        and "/planted-both" in violation
        for violation in violations
    ), violations


def test_a_mutating_route_mapping_outside_the_vocabulary_reds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clause 2: a mutating route mapping an operation OUTSIDE GW-10's
    eight (a read operation, here) violates the vocabulary — named."""
    spec = RouteSpec(
        path="/planted-sneaky",
        methods=frozenset({"POST"}),
        operations=frozenset({"gateway_info"}),
        classification="interface",
    )
    violations = route_mapping_violations(_checker_input(monkeypatch, spec))
    assert any(
        "outside GW-10's mutating vocabulary" in violation
        and "/planted-sneaky" in violation
        for violation in violations
    ), violations
