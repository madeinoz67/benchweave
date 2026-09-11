"""Role binding, resource reservation and the run's own bench lease.

Document admission proved structure and the digest pin lattice; the semantic
stage proved procedure-internal rules. This stage binds every procedure role
to exactly one commissioned bench device, enforces the declared-ness lattice
between what the procedure demands (profiles, invoked actions, read/write
parameters, channel aliases) and what the bound devices declare, computes the
reserved-resource closure, and takes the run's own lease on the bench. The
lease holder is the run's identity — the coordinator passes
``holder="run:{run_id}"`` — and both ``expires_at`` and ``now_wall`` are
caller-supplied, so the store never sees device I/O and this module never
reads a clock.

Scope boundary: policy evaluation and step execution belong to later stages,
and run creation belongs to the coordinator. Rejections raise
:class:`BindingError` with machine-matchable prefixes: ``unknown_role:``,
``duplicate_role:``, ``unbound_role:``, ``unknown_device:``,
``missing_profile:``, ``unbound_channel:``, ``undeclared_channel:``,
``undeclared_action:``, ``undeclared_parameter:``, ``duplicate_resource:``,
``unknown_resource:``, ``resource_cycle:``, ``bench_mismatch:``,
``invalid_timestamp:`` and ``bench_busy:``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from benchweave.control.documents import AdmittedDocuments
from benchweave.state.store import Lease, Store


class BindingError(Exception):
    """A role binding, resource closure or bench-lease failure."""


@dataclass(frozen=True)
class ResolvedBinding:
    """Procedure roles mapped to bench devices and resolved channels."""

    device_by_role: dict[str, str]  # role -> commissioned device id
    channels_by_role: dict[str, dict[str, str]]  # role -> {alias -> actual channel}


@dataclass(frozen=True)
class Reservation:
    """The reserved bench resources plus the run's own active lease."""

    resources: frozenset[str]
    lease: Lease


def _walk_steps(steps: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Yield every step in the procedure, nested blocks included once."""
    for step in steps:
        yield step
        if step["kind"] == "if":
            yield from _walk_steps(step["then"])
            yield from _walk_steps(step.get("else", []))
        elif step["kind"] == "repeat":
            yield from _walk_steps(step["steps"])


def _parse_utc(text: str, label: str) -> datetime:
    """Parse an ISO-8601 timestamp, treating a naive value as UTC."""
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise BindingError(
            f"invalid_timestamp: {label} {text!r} is not an ISO-8601 timestamp"
        ) from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment


def _resolve_roles(docs: AdmittedDocuments) -> ResolvedBinding:
    bench_devices = {str(device["id"]): device for device in docs.bench["devices"]}
    procedure_roles = {str(role["id"]): role for role in docs.procedure["roles"]}

    device_by_role: dict[str, str] = {}
    channels_by_role: dict[str, dict[str, str]] = {}
    for entry in docs.binding["bindings"]:
        role = str(entry["role"])
        device_id = str(entry["device_id"])
        if role not in procedure_roles:
            raise BindingError(f"unknown_role: {role!r} is not declared by the procedure")
        if role in device_by_role:
            raise BindingError(f"duplicate_role: {role!r} is bound more than once")
        if device_id not in bench_devices:
            raise BindingError(
                f"unknown_device: {device_id!r} is not a commissioned bench device"
            )
        device_by_role[role] = device_id
        channels_by_role[role] = {
            str(alias): str(channel) for alias, channel in entry["channels"].items()
        }

    for role, role_declaration in procedure_roles.items():
        if role not in device_by_role:
            raise BindingError(f"unbound_role: {role}")
        device_id = device_by_role[role]
        descriptor = docs.descriptors[device_id]

        missing_profiles = [
            profile
            for profile in role_declaration["required_profiles"]
            if profile not in descriptor["profiles"]
        ]
        if missing_profiles:
            raise BindingError(
                f"missing_profile: role {role!r} requires {missing_profiles}, "
                f"which device {device_id!r} does not declare"
            )

        declared_aliases = set(role_declaration["channels"])
        bound_channels = channels_by_role[role]
        extra_aliases = sorted(set(bound_channels) - declared_aliases)
        if extra_aliases:
            raise BindingError(
                f"undeclared_channel: binding maps alias(es) {extra_aliases} for role "
                f"{role!r}, which the procedure role does not declare"
            )
        missing_aliases = sorted(declared_aliases - set(bound_channels))
        if missing_aliases:
            raise BindingError(
                f"unbound_channel: role {role!r} declares channel alias(es) "
                f"{missing_aliases} with no binding entry"
            )
        bench_channels = set(bench_devices[device_id]["channels"])
        for alias, actual in bound_channels.items():
            if actual not in bench_channels:
                raise BindingError(
                    f"undeclared_channel: role {role!r} alias {alias!r} binds channel "
                    f"{actual!r}, which device {device_id!r} does not declare"
                )

    return ResolvedBinding(device_by_role=device_by_role, channels_by_role=channels_by_role)


def _check_declared_usage(docs: AdmittedDocuments, resolved: ResolvedBinding) -> None:
    """Enforce action/parameter declared-ness for every role-bearing step."""
    for step in _walk_steps(docs.procedure["steps"]):
        kind = step["kind"]
        if kind not in ("invoke", "read", "write"):
            continue
        role = str(step["role"])
        if role not in resolved.device_by_role:
            raise BindingError(f"unbound_role: {role}")
        device_id = resolved.device_by_role[role]
        descriptor = docs.descriptors[device_id]
        if kind == "invoke":
            action_id = str(step["action_id"])
            declared_actions = {str(action["action_id"]) for action in descriptor["actions"]}
            if action_id not in declared_actions:
                raise BindingError(
                    f"undeclared_action: step {step['id']!r} invokes {action_id!r}, "
                    f"which device {device_id!r} does not declare"
                )
        else:
            parameter = str(step["parameter"])
            if parameter not in set(descriptor["parameters"]):
                raise BindingError(
                    f"undeclared_parameter: step {step['id']!r} {kind}s parameter "
                    f"{parameter!r}, which device {device_id!r} does not declare"
                )


def resolve_binding(docs: AdmittedDocuments) -> ResolvedBinding:
    """Bind procedure roles to commissioned devices or reject.

    Every procedure role must be bound to exactly one commissioned bench
    device; binding entries naming unknown roles or devices are rejected, as
    are role channels the binding omits or maps outside the device's declared
    channels. Role ``required_profiles`` must be a subset of the bound
    device's descriptor profiles, every invoked ``action_id`` must be declared
    by the descriptor's ``actions``, and every read/write ``parameter`` must
    be declared by the descriptor's ``parameters``.
    """
    resolved = _resolve_roles(docs)
    _check_declared_usage(docs, resolved)
    return resolved


def _resource_index(docs: AdmittedDocuments) -> dict[str, dict[str, Any]]:
    """Index bench resources by id, rejecting duplicate declarations."""
    by_id: dict[str, dict[str, Any]] = {}
    for resource in docs.bench["resources"]:
        resource_id = str(resource["id"])
        if resource_id in by_id:
            raise BindingError(
                f"duplicate_resource: {resource_id!r} is declared more than once"
            )
        by_id[resource_id] = resource
    return by_id


def _check_resource_graph(by_id: dict[str, dict[str, Any]]) -> None:
    """Reject dangling depends_on edges and dependency cycles.

    Depth-first with an entering/exiting stack and a visiting set of the
    nodes on the current path: a node encountered while still on the path is
    a cycle. Completed nodes are memoised so shared dependencies are walked
    once.
    """
    for resource in by_id.values():
        for dependency in resource["depends_on"]:
            if dependency not in by_id:
                raise BindingError(
                    f"unknown_resource: resource {resource['id']!r} depends on "
                    f"{dependency!r}, which the bench does not declare"
                )

    done: set[str] = set()
    for root in by_id:
        stack: list[tuple[str, bool]] = [(root, False)]
        visiting: set[str] = set()
        while stack:
            resource_id, exiting = stack.pop()
            if exiting:
                visiting.discard(resource_id)
                done.add(resource_id)
                continue
            if resource_id in visiting:
                raise BindingError(
                    f"resource_cycle: {resource_id!r} participates in a "
                    "dependency cycle"
                )
            if resource_id in done:
                continue
            visiting.add(resource_id)
            stack.append((resource_id, True))
            for dependency in by_id[resource_id]["depends_on"]:
                if dependency not in done:
                    stack.append((dependency, False))


def _resource_closure(
    docs: AdmittedDocuments, by_id: dict[str, dict[str, Any]], bound_devices: set[str]
) -> frozenset[str]:
    """Reserve every resource the bound run touches, transitively.

    Seeds are resources whose ``device_ids`` intersect the bound devices,
    plus the resources named by bench-declared protection mechanisms and
    signals; ``depends_on`` edges are then expanded iteratively until the
    reserved set reaches a fixed point (the graph was proven acyclic).
    """
    reserved: set[str] = set()
    frontier: list[str] = []
    for resource_id, resource in by_id.items():
        if bound_devices & set(resource["device_ids"]):
            reserved.add(resource_id)
            frontier.append(resource_id)
    for mechanism in docs.bench["protection_mechanisms"]:
        resource_id = str(mechanism["resource_id"])
        if resource_id not in by_id:
            raise BindingError(
                f"unknown_resource: protection mechanism {mechanism['id']!r} names "
                f"resource {resource_id!r}, which the bench does not declare"
            )
        if resource_id not in reserved:
            reserved.add(resource_id)
            frontier.append(resource_id)
    for signal in docs.bench["signals"]:
        resource_id = str(signal["resource_id"])
        if resource_id not in by_id:
            raise BindingError(
                f"unknown_resource: signal {signal['id']!r} names resource "
                f"{resource_id!r}, which the bench does not declare"
            )
        if resource_id not in reserved:
            reserved.add(resource_id)
            frontier.append(resource_id)

    while frontier:
        resource_id = frontier.pop()
        for dependency in by_id[resource_id]["depends_on"]:
            if dependency not in reserved:
                reserved.add(dependency)
                frontier.append(dependency)
    return frozenset(reserved)


def reserve(
    store: Store,
    docs: AdmittedDocuments,
    bench_id: str,
    holder: str,
    expires_at: str,
    now_wall: str,
) -> Reservation:
    """Resolve, close over resources and take the bench lease, or reject.

    The whole binding and closure validation runs before any store write, so
    a rejected admission leaves no lease and no partially-reserved state. The
    one-active check treats a store lease whose ``expires_at`` is still in
    the future at ``now_wall`` as busy; one expired by the clock belongs to a
    dead or recovering run and does not block. The lease is the run's own:
    ``holder`` is conventionally ``run:{run_id}`` and ``lease_id`` derives
    from the binding request id.
    """
    if bench_id != str(docs.bench["id"]):
        raise BindingError(
            f"bench_mismatch: lease bench {bench_id!r} is not the bound bench "
            f"{docs.bench['id']!r}"
        )
    resolved = resolve_binding(docs)
    by_id = _resource_index(docs)
    _check_resource_graph(by_id)
    resources = _resource_closure(docs, by_id, set(resolved.device_by_role.values()))

    active = store.get_active_lease(bench_id)
    if active is not None:
        expiry = _parse_utc(active.expires_at, "active lease expires_at")
        if expiry > _parse_utc(now_wall, "now_wall"):
            raise BindingError(
                f"bench_busy: bench {bench_id!r} holds active lease "
                f"{active.lease_id!r} until {active.expires_at}"
            )

    lease = store.next_lease(
        bench_id,
        lease_id=f"lease-{docs.binding['request_id']}",
        holder=holder,
        expires_at=expires_at,
    )
    return Reservation(resources=resources, lease=lease)


def release(store: Store, reservation: Reservation, now_wall: str) -> None:
    """Release the reservation's bench lease; idempotent.

    The store only releases a lease in state ``active`` and raises
    :class:`ValueError` otherwise; for ``release`` that outcome means the
    lease is already gone (released, superseded or never durably active),
    which is the desired end state, so it is swallowed rather than surfaced.
    """
    try:
        store.release_lease(
            reservation.lease.bench_id, reservation.lease.sequence, now_wall
        )
    except ValueError:
        return
