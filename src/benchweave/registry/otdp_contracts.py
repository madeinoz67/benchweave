"""Resolve a descriptor's pinned OTDP contracts against the verified bundle
inventory (issue #146 design §2.1 — the C01 leg).

Nothing resolved ``descriptor.contracts`` before this module: the pinned
catalog was never read, digest-verified or schema-validated anywhere in the
gateway. Resolution here is a lookup + sha256 compare + parse against the
inventory the loader ALREADY digest-verified before the adapter module was
imported (the inventory is an explicit argument, never a module global and
never a filesystem re-read — Amendment 1 NIT-1). No new trust decision
exists in this step.

The refusal taxonomy (integrity-hard at load, completeness-soft at the
verb — the design's risk-1 ordering, kept as a named decision):

* LOAD-level (:class:`ActivationRejected` before any dispatch) — pinned
  bytes that ARE present and LIE: a digest mismatch (R9), unparsable
  bytes, a document that is neither the measurement schema nor
  catalog-schema-valid (C01/M14: unknown required contracts are rejected,
  never treated as opaque success), a measurement schema whose dataset
  definition declares no required keys (fix wave F4), more than one
  catalog-shaped document
  (Amendment 1 NIT-2: overlapping ``action_id``\\ s would let merge order
  silently pick the ``input_schema`` that gates I4 — closed by refusal, not
  resolution), and any ``$ref`` that does not resolve within the pinned
  set (the load-time probe, Amendment 1 MEDIUM-3 / R14, corrected by fix
  wave F2: the probe walks ``$ref`` AND ``$dynamicRef`` and roots
  resolution exactly where the runtime validators root it — the per-action
  subschema and the measurement dataset wrapper, never the bare document —
  so a structural validation alone never passes a reference that would
  raise lazily at dispatch and poison through the generic channel). The
  real corpus catalog is the in-tree witness that resolution is
  SET-scoped: its dataset-producing actions reference the measurement
  schema's dataset def by urn, so a catalog pinned without the
  measurement schema refuses HERE. The hard arm is NOT gated on the
  invoke capability: resolution runs for every descriptor that pins
  contracts, so a transport-only descriptor whose pins lie dies at load
  exactly an invoke-capable one's does — only the SOFT arm (an
  unassemblable or half pair) leaves a non-invoking run untouched.
* VERB-level (structural, never a runtime flag) — "unresolved contracts"
  in the design's own words (§2.2's table row, R16's soft arm): a pin
  whose path the verified inventory does not carry (nothing was verified
  false — the class surface simply cannot be assembled from this bundle),
  or a pinned set that resolves cleanly but yields only one half of the
  pair, constructs no class surface at all (the CON-10 capture-keys
  precedent: a half-declared class surface grants no class surface);
  ``invoke`` then refuses UNSUPPORTED at the bridge gate. The committed
  demo lattice loads under exactly this arm: its descriptor pins the
  corpus pair, its historical payload predates contract shipping, and no
  demo run invokes.

External ``$ref`` retrieval stays disabled (extension-contract §1): the
compiled validators resolve through a CLOSED ``referencing`` registry
holding exactly the pinned documents and their embedded ``$id``
subschemas (the interfaces/validation.py construction precedent) — a
registry with no retrieve callable, so an in-bundle ref resolves and
anything else raises at the probe, never at dispatch.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

from benchweave.control.documents import otdp_normative_path
from benchweave.registry.activation import ActivationRejected

#: The vendored catalog document's schema (the active version is the
#: manifest's, via ``otdp_normative_path`` — never a hardcoded constant).
CATALOG_SCHEMA_NAME = "device-profile-catalog.schema.json"

_MEASUREMENT_URN_PREFIX = "urn:otdp:measurement:"

_CATALOG_VALIDATORS: dict[str, Any] = {}


@dataclass(frozen=True)
class CompiledAction:
    """One catalog action's compiled validators and declarations (§2.1's
    ``action_id -> {input_schema, output_schema, side_effect, lifecycle}``
    mapping; compiled once per bridge construction and cached — the
    documents.py lazy-singleton precedent)."""

    input_validator: Any
    output_validator: Any
    side_effect: str
    lifecycle: str


@dataclass(frozen=True)
class ResolvedOtdpContracts:
    """The complete pinned class surface: the catalog's compiled action
    registry and the pinned measurement schema's dataset shape.

    ``dataset_required_keys`` is the bridge-side dataset-shaped detector
    (a result carrying every ``$defs/dataset`` required key); the full
    dataset validator is compiled for slice 3's ``dataset_publish``
    validation surface and rides here so the pair stays one resolution.
    """

    actions: Mapping[str, CompiledAction]
    dataset_required_keys: frozenset[str]
    dataset_validator: Any


def _catalog_validator() -> Any:
    """The vendored catalog-schema validator, cached per resolved path."""
    path = otdp_normative_path(CATALOG_SCHEMA_NAME)
    key = str(path)
    validator = _CATALOG_VALIDATORS.get(key)
    if validator is None:
        schema = json.loads(path.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        _CATALOG_VALIDATORS[key] = validator
    return validator


def _is_measurement_schema(document: dict[str, Any]) -> bool:
    """The pinned measurement schema, identified by its ``$id`` urn and
    ``$defs/dataset`` presence (design §2.1)."""
    identifier = document.get("$id")
    defs = document.get("$defs")
    return (
        isinstance(identifier, str)
        and identifier.startswith(_MEASUREMENT_URN_PREFIX)
        and isinstance(defs, dict)
        and "dataset" in defs
    )


def _walk_refs(node: Any, refs: list[str]) -> None:
    """Collect every reference target — ``$ref`` AND ``$dynamicRef`` (fix
    wave F2: a dangling dynamic reference raises lazily at validation
    exactly a dangling static one does)."""
    if isinstance(node, dict):
        for keyword in ("$ref", "$dynamicRef"):
            ref = node.get(keyword)
            if isinstance(ref, str):
                refs.append(ref)
        for value in node.values():
            _walk_refs(value, refs)
    elif isinstance(node, list):
        for item in node:
            _walk_refs(item, refs)


def _walk_ids(node: Any, ids: list[tuple[str, dict[str, Any]]]) -> None:
    """Collect every ``$id``-bearing subschema."""
    if isinstance(node, dict):
        identifier = node.get("$id")
        if isinstance(identifier, str):
            ids.append((identifier, node))
        for value in node.values():
            _walk_ids(value, ids)
    elif isinstance(node, list):
        for item in node:
            _walk_ids(item, ids)


def _closed_registry(documents: list[tuple[str, dict[str, Any]]]) -> Registry:
    """A registry over exactly the pinned set: every ``$id``-bearing
    subschema (embedded action schemas included) as its own resource,
    crawled so subschema ids and anchors resolve. No retrieve callable —
    resolution outside the pinned set is impossible by construction."""
    registry: Registry = Registry()
    for _identifier, document in documents:
        ids: list[tuple[str, dict[str, Any]]] = []
        _walk_ids(document, ids)
        for uri, subschema in ids:
            registry = registry.with_resource(
                uri, Resource.from_contents(subschema, default_specification=DRAFT202012)
            )
    return registry.crawl()


def _probe_runtime_schemas(
    catalog: tuple[str, dict[str, Any]] | None,
    measurement: tuple[str, dict[str, Any]] | None,
    registry: Registry,
) -> None:
    """The load-time reference probe (Amendment 1 MEDIUM-3, R14; fix wave
    F2): every ``$ref`` and ``$dynamicRef`` in every schema the RUNTIME
    validators are built from must resolve within the pinned set, rooted
    exactly where the runtime roots it — each action's input/output schema
    (the per-action subschema ``Draft202012Validator`` validates against,
    NOT the catalog document: a valid document-root pointer that walks
    outside the action subschema raises ``PointerToNowhere`` at first
    dispatch) and the measurement dataset wrapper. An unresolvable
    reference is an ``ActivationRejected`` at load, never a lazy
    ``PointerToNowhere``/``NoSuchAnchor`` escaping dispatch-time
    validation into the generic poison channel."""
    roots: list[tuple[str, dict[str, Any]]] = []
    if catalog is not None:
        for action_id, spec in catalog[1].get("actions", {}).items():
            roots.append((f"{catalog[0]}:{action_id}:input", spec["input_schema"]))
            roots.append((f"{catalog[0]}:{action_id}:output", spec["output_schema"]))
    if measurement is not None:
        defs = measurement[1].get("$defs", {})
        roots.append(
            (f"{measurement[0]}:dataset", {"$ref": "#/$defs/dataset", "$defs": defs})
        )
    for label, schema in roots:
        refs: list[str] = []
        _walk_refs(schema, refs)
        if not refs:
            continue
        resolver = registry.resolver_with_root(
            Resource.from_contents(schema, default_specification=DRAFT202012)
        )
        for ref in dict.fromkeys(refs):
            try:
                resolver.lookup(ref)
            except Unresolvable:
                raise ActivationRejected(
                    f"contract_ref_unresolvable: {label}: {ref}"
                ) from None


def resolve_otdp_contracts(
    entries: Any, *, inventory: dict[str, bytes]
) -> ResolvedOtdpContracts | None:
    """Resolve the descriptor's ``contracts`` entries against the verified
    bundle inventory.

    Returns the complete class surface when the pinned set resolves to
    exactly one catalog-schema-valid catalog AND the measurement schema;
    ``None`` when the descriptor pins no contracts, a pinned path is
    absent from the verified inventory, or the pair is incomplete (the
    soft "unresolved contracts" arms — no class surface, invoke refuses
    UNSUPPORTED at the bridge). Every integrity failure of PRESENT bytes
    raises :class:`ActivationRejected` at load, before any dispatch.
    """
    if not isinstance(entries, list) or not entries:
        return None
    catalog: tuple[str, dict[str, Any]] | None = None
    measurement: tuple[str, dict[str, Any]] | None = None
    documents: list[tuple[str, dict[str, Any]]] = []
    unresolved = False
    for entry in entries:
        if not isinstance(entry, dict):
            raise ActivationRejected("contract_entry_malformed")
        identifier = entry.get("id")
        path = entry.get("path")
        declared = entry.get("sha256")
        if (
            not isinstance(identifier, str)
            or not identifier
            or not isinstance(path, str)
            or not path
            or not isinstance(declared, str)
            or not re.fullmatch(r"[0-9a-f]{64}", declared)
        ):
            raise ActivationRejected("contract_entry_malformed")
        data = inventory.get(path)
        if data is None:
            # The soft "unresolved contracts" arm (§2.2's table, R16's
            # verb-level row): no bytes exist to disagree with anything —
            # the class surface cannot be assembled from this bundle, which
            # refuses the VERB (no controller), never the run. Bytes that
            # ARE present and lie refuse the load below.
            unresolved = True
            continue
        if hashlib.sha256(data).hexdigest() != declared:
            raise ActivationRejected("contract_hash_mismatch")
        try:
            document = json.loads(data)
        except (UnicodeDecodeError, ValueError):
            raise ActivationRejected("contract_unparsable") from None
        if not isinstance(document, dict):
            raise ActivationRejected("contract_not_an_object")
        if _is_measurement_schema(document):
            if measurement is not None:
                # NIT-2's symmetry: two measurement schemas leave the same
                # ambiguity (which one compiles for publish) two catalogs do.
                raise ActivationRejected("contract_multi_measurement")
            measurement = (identifier, document)
        else:
            error = next(iter(_catalog_validator().iter_errors(document)), None)
            if error is not None:
                raise ActivationRejected(
                    f"contract_schema: {identifier} {error.json_path}: {error.message}"
                )
            if catalog is not None:
                raise ActivationRejected("contract_multi_catalog")
            catalog = (identifier, document)
        documents.append((identifier, document))
    registry = _closed_registry(documents)
    _probe_runtime_schemas(catalog, measurement, registry)
    if unresolved or catalog is None or measurement is None:
        # The soft arms: an unassemblable set (a path the inventory does
        # not carry) or a cleanly-resolving half pair — no controller,
        # verb-level UNSUPPORTED.
        return None
    actions: dict[str, CompiledAction] = {}
    for action_id, spec in catalog[1].get("actions", {}).items():
        actions[action_id] = CompiledAction(
            input_validator=Draft202012Validator(
                spec["input_schema"], registry=registry
            ),
            output_validator=Draft202012Validator(
                spec["output_schema"], registry=registry
            ),
            side_effect=str(spec["side_effect"]),
            lifecycle=str(spec["lifecycle"]),
        )
    defs = measurement[1].get("$defs", {})
    dataset_def = defs.get("dataset")
    if not isinstance(dataset_def, dict):
        raise ActivationRejected("contract_measurement_dataset_def_absent")
    required = frozenset(str(key) for key in dataset_def.get("required", []))
    if not required:
        # Present bytes that lie (fix wave F4): an empty/absent required
        # set degenerates the dataset-shape detector to "every object" —
        # frozenset() is a subset of any key set — so every dict result
        # would poison as a dataset. Refuse at load.
        raise ActivationRejected(
            "contract_measurement_degenerate: the pinned measurement schema's "
            "$defs/dataset declares no required keys"
        )
    dataset_validator = Draft202012Validator(
        {"$ref": "#/$defs/dataset", "$defs": defs}, registry=registry
    )
    return ResolvedOtdpContracts(
        actions=actions,
        dataset_required_keys=required,
        dataset_validator=dataset_validator,
    )
