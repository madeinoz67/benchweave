"""Class-reference derivation, gateway-side (L4 capability a; design record
2026-10-15 §1; parent record §3 semantics, mirrored from the SDK expander).

Derives the attachment triple — envelope, manifest, binding catalogue —
from (descriptor × reference) at READ time. The derived documents NEVER
enter the admitted store: this is a read-time composition over admitted
bytes (the descriptor, the digest-pinned vendor catalogs the composition
supplies from the admission store) plus corpus bytes (the reference). No
admission event, no store write, no mutation of the accountability
boundary (A07 untouched; admission stays a plugin-owned act).

The SDK is read-not-imported (REG-4): this module is the gateway's own
derivation. Agreement with the SDK expander is fixture-pinned (B8) — the
committed fixtures under ``tests/presentation/classref_fixtures/`` were
generated ONCE from the SDK expander at the submodule pin (v0.14.0,
``201c343``) and are the drift alarm: a divergence between the two
derivations reddens the parity test, and a corpus byte that moves re-pins
through the fixtures' own regeneration.

Mirrored-source pin: the derivation functions mirror
``benchweave_sdk.classref`` at v0.14.0. A re-pin that moves the SDK
derivation moves these functions in the same arc (the design's
fixture-freeze re-pin rule); B8 reds otherwise.

Corpus discipline: every corpus file this module reads is digest-verified
against its corpus-manifest row before parsing (``_verify_corpus_pin`` —
the same gate ``interfaces.ui_presentation`` keeps local; the tiny gate is
kept local here rather than importing a private symbol across layers, the
``_corpus_state`` discipline; B8's pin reddens if either copy drifts).

Fail-closed cases carry the same typed ``classref_*:`` refusals the
parent record's §3.3 table names (``ClassRefusal``). An unknown class —
no descriptor profile with a corpus reference; vendor-only; custom
devices — fails OPEN: ``select_references`` returns ``None`` and the
composition renders today's ``no-attachment`` absence byte-identically
(B3). The fallback never invents obligations the descriptor does not
create.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from benchweave.standards.manifest import (
    StandardsError,
    active_version_from_corpus,
)

#: The namespaced layout block's manifest seam key (parent record §2.6;
#: verified against the SDK bytes at fixture freeze — the design's §9.1
#: assumption CONFIRMED).
LAYOUT_EXTENSION_KEY = "plugin-ui-class-reference:layout"

_LANE_CEILING = 64
_GROUP_SIZE = 8
_HOST_SUPPLIED_UNIVERSAL = ("acquisition_id", "configuration_id")
_NUMERIC_TYPES = ("number", "integer")
#: The closed constraint vocabulary (parent record §3.7): the first group
#: narrows a rendered control; the riders (required/properties/items/
#: min/max/unique) ride the conjunctive validation lanes untouched and
#: derive no controls.
_CONSTRAINT_CONTROL_KEYWORDS = frozenset(
    {
        "type",
        "enum",
        "const",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "pattern",
    }
)
_CONSTRAINT_RIDER_KEYWORDS = frozenset(
    {"required", "properties", "items", "minItems", "maxItems", "uniqueItems"}
)

_FAMILY = "plugin-ui-class-reference"

#: The reference's layout vocabulary the panel registry renders against —
#: the registry's corpus pin (design record §3; R4's mitigation) cites the
#: served family version, derived from the corpus manifest, never a
#: literal in the render path (the constant documents the founding pin).
FOUNDING_FAMILY_VERSION = "0.1.0"


class ClassRefusal(ValueError):
    """One typed ``classref_*:`` refusal (parent record §3.3's table)."""


def _refuse(prefix: str, detail: str) -> ClassRefusal:
    return ClassRefusal(f"{prefix}: {detail}")


# --- the corpus set (digest-verified reads) -----------------------------------


def _corpus_pin_rows(corpus: Path) -> dict[str, str] | None:
    """The corpus manifest's ``{path: sha256}`` rows, or ``None`` when the
    manifest is absent — the absent-manifest tolerance
    ``interfaces.ui_presentation._corpus_state`` documents. Same row shape
    as ``standards.manifest._corpus_pins``, kept local rather than
    importing a private symbol across layers."""
    path = corpus / "corpus-manifest.json"
    if not path.is_file():
        return None
    document = json.loads(path.read_bytes())
    return {
        str(row["path"]): str(row["sha256"]) for row in document.get("files", [])
    }


def _verify_corpus_pin(raw: bytes, key: str, pins: dict[str, str] | None) -> str:
    """Digest-verify one corpus read against its manifest row BEFORE
    parsing (the #446 fold's gate); returns the digest. ``pins is None``
    is the absent-manifest tolerance; with the manifest present the gate
    is mandatory and fail-closed."""
    if pins is None:
        return hashlib.sha256(raw).hexdigest()
    pinned = pins.get(key)
    if pinned is None:
        raise StandardsError(
            f"corpus_pin_mismatch: {key} is present in the corpus tree "
            "but not recorded by the corpus manifest; record it through "
            "a standards bump or restore the tree"
        )
    digest = hashlib.sha256(raw).hexdigest()
    if digest != pinned:
        raise StandardsError(
            f"corpus_pin_mismatch: {key} hashes to {digest} but the "
            f"manifest pins {pinned}"
        )
    return digest


def _read_corpus_json(corpus: Path, relpath: str, pins: dict[str, str] | None) -> Any:
    """One corpus file, digest-verified then parsed."""
    raw = (corpus / relpath).read_bytes()
    _verify_corpus_pin(raw, relpath, pins)
    return json.loads(raw)


def _corpus_state(corpus: Path) -> tuple[str, str]:
    """Cache-key discipline (VR-19 shape): digests of the two manifest
    files the family set derives from — a mid-process corpus change serves
    the NEXT derivation from the new bytes."""
    digests = []
    for name in ("standards-manifest.json", "corpus-manifest.json"):
        path = corpus / name
        if path.is_file():
            digests.append(hashlib.sha256(path.read_bytes()).hexdigest())
        else:
            digests.append("")
    return digests[0], digests[1]


@lru_cache(maxsize=8)
def _family_documents_cached(
    corpus_text: str, state: tuple[str, str]
) -> dict[str, Any]:
    """The family's machine files, digest-verified, for one corpus state:
    the reference schema and the layout schema (the layout block's only
    validation authority — the canonical manifest validator is
    extension-blind)."""
    corpus = Path(corpus_text)
    version = active_version_from_corpus(corpus, _FAMILY)
    pins = _corpus_pin_rows(corpus)
    return {
        "version": version,
        "reference_schema": _read_corpus_json(
            corpus, f"{_FAMILY}/{version}/class-reference.schema.json", pins
        ),
        "layout_schema": _read_corpus_json(
            corpus, f"{_FAMILY}/{version}/layout.schema.json", pins
        ),
    }


def _family_documents(corpus: Path) -> dict[str, Any]:
    """The digest-verified family set for the corpus's current state."""
    return dict(_family_documents_cached(str(corpus), _corpus_state(corpus)))


def layout_schema(corpus: Path) -> dict[str, Any]:
    """The family layout vocabulary schema (the block's only authority)."""
    family = _family_documents(corpus)
    layout: dict[str, Any] = family["layout_schema"]
    return layout


def family_version(corpus: Path) -> str:
    """The served family version, derived from the corpus manifest —
    never a literal in any render path."""
    return str(_family_documents(corpus)["version"])


def _reference_registry(corpus: Path) -> Any:
    """A jsonschema ``Registry`` carrying the digest-verified layout
    schema at its ``$id`` (the reference schema's ``layouts`` rows $ref
    it by $id; without the registration the validator would fetch a
    remote URL — never)."""
    from jsonschema import Draft202012Validator  # noqa: F401 (registry shape)
    from referencing import Registry, Resource

    layout = layout_schema(corpus)
    return Registry().with_resource(
        str(layout.get("$id")), Resource.from_contents(layout)
    )


def validate_reference_document(document: Any, *, corpus: Path) -> dict[str, Any]:
    """One reference document against the family schema (the SDK
    expander's ``_validate_reference`` shape; the same typed refusal)."""
    from jsonschema import Draft202012Validator

    family = _family_documents(corpus)
    registry = _reference_registry(corpus)
    findings = sorted(
        Draft202012Validator(
            family["reference_schema"], registry=registry
        ).iter_errors(document),
        key=lambda error: list(error.path),
    )
    if findings:
        first = findings[0]
        where = "/".join(str(part) for part in first.path) or "(root)"
        raise _refuse("classref_invalid_reference", f"{where}: {first.message}")
    return document  # type: ignore[no-any-return]


def select_references(
    corpus: Path, descriptor: Mapping[str, Any]
) -> list[dict[str, Any]] | None:
    """The class references this descriptor's profiles select, or ``None``
    for the fail-open signal (no profile names a class with a reference).

    Selection: profiles sorted bytewise; profiles without a corpus
    reference are skipped; a multi-profile descriptor merges per parent
    §3.8 (first bare, later ``{slug}-`` prefixed) — the merge happens in
    ``derive_attachment`` over the sorted list."""
    pins = _corpus_pin_rows(corpus)
    version = active_version_from_corpus(corpus, _FAMILY)
    profile_ids = sorted(str(profile) for profile in (descriptor.get("profiles") or []))
    found: list[dict[str, Any]] = []
    for profile_id in profile_ids:
        reference = _find_reference(corpus, pins, version, profile_id)
        if reference is not None:
            found.append(reference)
    return found or None


def _find_reference(
    corpus: Path, pins: dict[str, str] | None, version: str, profile_id: str
) -> dict[str, Any] | None:
    """The corpus reference document for one profile id, or ``None`` —
    digest-verified reads, profile matching by the document's own
    ``profile_id``, validated against the family schema."""
    root = corpus / _FAMILY / version
    if not root.is_dir():
        return None
    for path in sorted(root.glob("class-*.json")):
        relpath = f"{_FAMILY}/{version}/{path.name}"
        try:
            raw = path.read_bytes()
            _verify_corpus_pin(raw, relpath, pins)
            document = json.loads(raw)
        except (OSError, StandardsError, ValueError):
            continue
        if isinstance(document, dict) and str(document.get("profile_id")) == profile_id:
            return validate_reference_document(document, corpus=corpus)
    return None


def _satisfies_target(active: str, target: str) -> bool:
    """Per-parsed-operator comparison (parent record §2.2
    admission-fold note): active A satisfies ``>=V`` iff A >= V, and the
    same reading for ``>``, ``<`` and ``<=``."""
    match = re.fullmatch(r"(>=|<=|>|<)?(\d+(?:\.\d+)*)", target)
    if match is None:
        raise _refuse("classref_invalid_reference", f"target {target!r} unparsable")
    operator, version = match.group(1) or ">=", match.group(2)

    def parts(text: str) -> tuple[int, ...]:
        return tuple(int(piece) for piece in text.split("."))

    left, right = parts(active), parts(version)
    width = max(len(left), len(right))
    left += (0,) * (width - len(left))
    right += (0,) * (width - len(right))
    if operator == ">=":
        return left >= right
    if operator == "<=":
        return left <= right
    if operator == ">":
        return left > right
    return left < right


# --- the effective schema (parent record §3.7, mirrored) -----------------------


def _intersect_property(
    action_urn: str,
    property_name: str,
    catalogue_schema: dict[str, Any],
    constraint: dict[str, Any],
) -> dict[str, Any]:
    """One property's effective admittance: catalogue AND constraint
    (parent record §3.7). Narrowing only; a fragment that would offer an
    unadmitted value refuses loudly instead of being dropped."""
    for keyword in constraint:
        if keyword in _CONSTRAINT_CONTROL_KEYWORDS or keyword in _CONSTRAINT_RIDER_KEYWORDS:
            continue
        raise _refuse(
            "classref_constraint_unsupported",
            f"action {action_urn} field {property_name}: keyword {keyword!r} "
            "is outside the closed intersection vocabulary",
        )
    effective = dict(catalogue_schema)
    declared_type = (
        catalogue_schema.get("type") if isinstance(catalogue_schema, dict) else None
    )

    # Bounds INTERSECT: a looser constraint can never widen the catalogue's
    # admittance — the tighter end of each side wins, the exclusivity flags
    # carry, and an empty result refuses.
    def _bound(
        source: dict[str, Any], exclusive_key: str, plain_key: str
    ) -> tuple[Any, bool] | None:
        if exclusive_key in source:
            return source[exclusive_key], True
        if plain_key in source:
            return source[plain_key], False
        return None

    low_catalogue = _bound(effective, "exclusiveMinimum", "minimum")
    high_catalogue = _bound(effective, "exclusiveMaximum", "maximum")
    low_constraint = _bound(constraint, "exclusiveMinimum", "minimum")
    high_constraint = _bound(constraint, "exclusiveMaximum", "maximum")
    if (
        low_constraint is not None or high_constraint is not None
    ) and declared_type not in _NUMERIC_TYPES:
        raise _refuse(
            "classref_effective_schema_conflict",
            f"action {action_urn} field {property_name}: numeric bound "
            f"applied to catalogue type {declared_type!r}",
        )
    low: tuple[Any, bool] | None
    if low_catalogue is None or low_constraint is None:
        low = low_catalogue if low_constraint is None else low_constraint
    else:
        low = max(low_catalogue, low_constraint)
    high: tuple[Any, bool] | None
    if high_catalogue is None or high_constraint is None:
        high = high_catalogue if low_constraint is None else high_constraint
    else:
        high = min(high_catalogue, high_constraint)
    for keyword in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
        effective.pop(keyword, None)
    if low is not None:
        value, exclusive = low
        effective["exclusiveMinimum" if exclusive else "minimum"] = value
    if high is not None:
        value, exclusive = high
        effective["exclusiveMaximum" if exclusive else "maximum"] = value
    if "multipleOf" in constraint:
        effective["multipleOf"] = constraint["multipleOf"]
    if "enum" in constraint:
        catalogue_enum = catalogue_schema.get("enum")
        if catalogue_enum is not None:
            allowed = [value for value in constraint["enum"] if value in catalogue_enum]
        else:
            allowed = list(constraint["enum"])
        if not allowed:
            raise _refuse(
                "classref_effective_schema_empty",
                f"action {action_urn} field {property_name}: enum intersection empty",
            )
        effective["enum"] = allowed
        for keyword in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
            effective.pop(keyword, None)
    if "const" in constraint:
        # A const NARROWS to one value; outside the catalogue's own
        # admittance it is a conflict (never a replace that pops the
        # enum or the bounds).
        value = constraint["const"]
        catalogue_enum = catalogue_schema.get("enum")
        if catalogue_enum is not None and value not in catalogue_enum:
            raise _refuse(
                "classref_effective_schema_conflict",
                f"action {action_urn} field {property_name}: const {value!r} "
                f"outside the catalogue enum {list(catalogue_enum)!r}",
            )
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            for bound, edge in ((low_catalogue, "minimum"), (high_catalogue, "maximum")):
                if bound is None:
                    continue
                bound_value, exclusive = bound
                outside = (
                    value < bound_value or (exclusive and value == bound_value)
                    if edge == "minimum"
                    else value > bound_value or (exclusive and value == bound_value)
                )
                if outside:
                    raise _refuse(
                        "classref_effective_schema_conflict",
                        f"action {action_urn} field {property_name}: const "
                        f"{value!r} outside the catalogue {edge} {bound_value!r}",
                    )
        effective = {**effective, "const": value}
        effective.pop("enum", None)
        for keyword in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
            effective.pop(keyword, None)
    if "pattern" in constraint:
        effective["pattern"] = constraint["pattern"]
    if "type" in constraint:
        declared = catalogue_schema.get("type")
        wanted = constraint["type"]
        same_family = wanted == declared or (
            wanted in _NUMERIC_TYPES and declared in _NUMERIC_TYPES
        )
        if not same_family:
            raise _refuse(
                "classref_effective_schema_conflict",
                f"action {action_urn} field {property_name}: constraint type "
                f"{wanted!r} vs catalogue type {declared!r}",
            )
        effective["type"] = wanted
    return effective


def _check_admittance(
    action_urn: str, property_name: str, effective: dict[str, Any]
) -> None:
    """A required field narrowed to an empty admittance set refuses
    (parent record §3.7); exclusivity is part of emptiness — a closed
    bound meeting an open bound at the same value admits nothing, in
    both crossing directions."""
    if effective.get("const") is not None:
        return
    if "minimum" in effective:
        low: tuple[float, bool] | None = (float(effective["minimum"]), False)
    elif "exclusiveMinimum" in effective:
        low = (float(effective["exclusiveMinimum"]), True)
    else:
        low = None
    if "maximum" in effective:
        high: tuple[float, bool] | None = (float(effective["maximum"]), False)
    elif "exclusiveMaximum" in effective:
        high = (float(effective["exclusiveMaximum"]), True)
    else:
        high = None
    if low is None or high is None:
        return
    if effective.get("type") not in _NUMERIC_TYPES:
        return
    empty = low[0] > high[0] or (low[0] == high[0] and (low[1] or high[1]))
    if empty:
        raise _refuse(
            "classref_effective_schema_empty",
            f"action {action_urn} field {property_name}: bounds admit no value",
        )


def _effective_action_schema(
    action_urn: str,
    catalogue_action: dict[str, Any],
    constraints: dict[str, Any],
) -> dict[str, Any]:
    """The action's effective input schema: catalogue AND descriptor
    constraints, per property (parent record §3.7). Validation lanes stay
    conjunctive and untouched; this derives per-field admittance for the
    derived manifest's settings-schema asset."""
    catalogue_input = catalogue_action.get("input_schema", {}) or {}
    # Deep copy: the served catalog document may be cached module state
    # shared across derivations; the intersection must never narrow the
    # served bytes in place.
    catalogue_input = json.loads(json.dumps(catalogue_input))
    properties = {
        name: dict(schema)
        for name, schema in (catalogue_input.get("properties") or {}).items()
        if isinstance(schema, dict)
    }
    required = set(catalogue_input.get("required") or ())
    constraint_properties = constraints.get("properties") or {}
    for keyword in constraints:
        if (
            keyword in _CONSTRAINT_CONTROL_KEYWORDS
            or keyword in _CONSTRAINT_RIDER_KEYWORDS
        ):
            continue
        raise _refuse(
            "classref_constraint_unsupported",
            f"action {action_urn}: top-level keyword {keyword!r} is outside the "
            "closed intersection vocabulary",
        )
    for name, fragment in constraint_properties.items():
        if not isinstance(fragment, dict):
            raise _refuse(
                "classref_constraint_unsupported",
                f"action {action_urn} field {name}: constraint fragment must be "
                "an object",
            )
        base = properties.get(name)
        if base is None:
            base = {"type": fragment.get("type", "object")}
            properties[name] = base
        if "properties" in fragment or "items" in fragment:
            properties[name] = _merge_deep(action_urn, name, base, fragment)
        else:
            properties[name] = _intersect_property(action_urn, name, base, fragment)
            _check_admittance(action_urn, name, properties[name])
    required.update(constraints.get("required") or ())
    return {"properties": properties, "required": sorted(required)}


def _merge_deep(
    action_urn: str, prefix: str, base: dict[str, Any], fragment: dict[str, Any]
) -> dict[str, Any]:
    """Intersect nested ``properties``/``items`` shapes one level at a
    time (the SDK expander's ``_merge_deep`` shape)."""
    effective = dict(base)
    constraint_props = fragment.get("properties") or {}
    base_props = dict(base.get("properties") or {})
    items_fragment = fragment.get("items")
    if isinstance(items_fragment, dict) and "properties" in items_fragment:
        items_base = dict(base.get("items") or {"type": "object"})
        effective["items"] = _merge_deep(
            action_urn, f"{prefix}[]", items_base, items_fragment
        )
    for name, sub in constraint_props.items():
        sub_base = dict(base_props.get(name) or {"type": sub.get("type", "object")})
        if "properties" in sub or "items" in sub:
            effective.setdefault("properties", {})[name] = _merge_deep(
                action_urn, f"{prefix}{name}.", sub_base, sub
            )
        else:
            merged = _intersect_property(action_urn, f"{prefix}{name}", sub_base, sub)
            _check_admittance(action_urn, f"{prefix}{name}", merged)
            effective.setdefault("properties", {})[name] = merged
    if "required" in fragment:
        effective["required"] = sorted(
            set(effective.get("required") or ()) | set(fragment["required"])
        )
    return effective


def _field_rows(
    action_urn: str, prefix: str, schema: dict[str, Any]
) -> list[dict[str, Any]]:
    """The renderable field rows (numeric bounds / const / enum) of one
    effective schema, descending array items and object properties."""
    rows: list[dict[str, Any]] = []
    for name, sub in (schema.get("properties") or {}).items():
        full = f"{prefix}{name}"
        if sub.get("const") is not None:
            rows.append({"field": full, "mode": "const", "const": sub["const"]})
        elif sub.get("enum") is not None:
            rows.append({"field": full, "mode": "enum", "enum": sub["enum"]})
        elif sub.get("type") in _NUMERIC_TYPES:
            row: dict[str, Any] = {"field": full, "mode": "numeric"}
            for keyword in (
                "minimum",
                "maximum",
                "multipleOf",
                "exclusiveMinimum",
                "exclusiveMaximum",
            ):
                if keyword in sub:
                    row[keyword] = sub[keyword]
            rows.append(row)
        if isinstance(sub.get("properties"), dict):
            rows.extend(_field_rows(action_urn, f"{full}.", sub))
        if isinstance(sub.get("items"), dict) and isinstance(
            sub["items"].get("properties"), dict
        ):
            rows.extend(_field_rows(action_urn, f"{full}[].", sub["items"]))
    return rows


def _ladder_level(
    effective: dict[str, Any],
    host_supplied: frozenset[str],
    slot_kind: str | None,
) -> str:
    """The reachability ladder (parent record §2.5), evaluated first-match.
    A configuration slot's action is L3 (preset-mediated); a dataset
    slot's action is L4 (dataset binding + plot/table). Otherwise the
    effective required set (minus the acquisition-lifecycle names the
    host supplies) decides: empty L1, all numeric L2, anything else L0."""
    if slot_kind == "configuration":
        return "L3"
    if slot_kind == "dataset":
        return "L4"
    required = [name for name in effective["required"] if name not in host_supplied]
    if not required:
        return "L1"
    schemas = effective["properties"]
    if all(schemas.get(name, {}).get("type") in _NUMERIC_TYPES for name in required):
        return "L2"
    return "L0"


def _derive_controls(
    actions: Mapping[str, Any],
    catalog_actions: Mapping[str, Any],
    slot_for_urn: dict[str, tuple[str, dict[str, Any]]],
    page_for_slot: dict[str, str],
    intended_controls: dict[str, str],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    """Per-action ladder level + renderable fields (the SDK expander's
    ``_derive_controls`` shape; the plan the layout block builds from)."""
    plan: dict[str, dict[str, Any]] = {}
    divergences: list[dict[str, str]] = []
    for urn in sorted(actions):
        constraints = actions[urn].get("input_constraints") or {}
        slot_kind = None
        host_supplied = frozenset(_HOST_SUPPLIED_UNIVERSAL)
        _slot_name, slot = slot_for_urn.get(urn, ("", {}))
        if slot:
            slot_kind = str(slot.get("kind"))
            if slot_kind != "vendor_actions":
                host_supplied = frozenset(slot.get("host_supplied") or ())
        effective = _effective_action_schema(urn, catalog_actions[urn], constraints)
        level = _ladder_level(effective, host_supplied, slot_kind)
        fields = _field_rows(urn, "", effective)
        slot_key = _slot_name if slot else ""
        page = page_for_slot.get(slot_key, "device-features")
        plan[urn] = {
            "level": level,
            "page": page,
            "fields": fields,
            "declared_deviation": (
                bool(intended_controls.get(urn) == "deviation")
                or level == "L0"
                or slot_kind == "configuration"
            ),
        }
    return plan, divergences


def _check_slot_conflicts(references: list[dict[str, Any]]) -> None:
    """A URN claimed by named slots in two references refuses (parent
    record §3.8's ``classref_profile_slot_conflict``)."""
    seen: dict[str, str] = {}
    for item in references:
        for key, slot in item.get("slots", {}).items():
            urn = slot.get("action")
            if not urn:
                continue
            if urn in seen and seen[urn] != key:
                raise _refuse(
                    "classref_profile_slot_conflict",
                    f"{urn} claimed by slots {seen[urn]!r} and {key!r}",
                )
            seen[urn] = key


def _merge_references(references: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic multi-profile merge (parent record §3.8): sorted
    bytewise by profile id; the first reference keeps bare ids, every
    later one prefixes page ids and binding ids with its profile slug;
    layouts prefix to match."""
    merged: dict[str, Any] = {
        "slots": {},
        "pages": [],
        "layouts": [],
        "expect": {"components": {}, "controls": {}, "forbid": []},
        "cannot_derive": [],
    }
    for index, item in enumerate(references):
        slug = ""
        if index > 0:
            slug = str(item["profile_id"]).split("/")[0].replace(".", "-")
        slot_map: dict[str, str] = {}
        for key, slot in item.get("slots", {}).items():
            merged["slots"][f"{slug}-{key}" if slug else key] = slot
            slot_map[key] = f"{slug}-{key}" if slug else key
        for page in item.get("pages", []):
            row = dict(page)
            if slug:
                row["id"] = f"{slug}-{page['id']}"
            row["bindings"] = [
                slot_map.get(key, key) for key in page.get("binding_slots", [])
            ]
            row["_slot_keys"] = list(page.get("binding_slots", []))
            merged["pages"].append(row)
        for layout_page in item.get("layouts", []):
            row = dict(layout_page)
            if slug:
                row["page_id"] = f"{slug}-{layout_page['page_id']}"
            merged["layouts"].append(row)
        for name, row in item.get("expect", {}).get("components", {}).items():
            merged["expect"]["components"][name] = dict(row)
        for urn, intended in item.get("expect", {}).get("controls", {}).items():
            merged["expect"]["controls"][urn] = intended
        merged["expect"]["forbid"].extend(item.get("expect", {}).get("forbid", []))
        merged["cannot_derive"].extend(item.get("cannot_derive", []))
    return merged


def _resolve_channels(
    descriptor: Mapping[str, Any], merged: dict[str, Any]
) -> list[dict[str, Any]]:
    """The class-role lanes, in declaration order; fail-closed count
    refusals (parent record §3.3)."""
    slot = next(
        (slot for slot in merged["slots"].values() if slot.get("kind") == "channels"),
        None,
    )
    if slot is None:
        return []
    role = str(slot.get("where_role", ""))
    lanes = [
        row
        for row in descriptor.get("channels", [])
        if str(row.get("role")) == role
    ]
    if not lanes:
        raise _refuse("classref_no_lanes", "0 channels carry role " + role)
    if len(lanes) > _LANE_CEILING:
        raise _refuse(
            "classref_lane_ceiling",
            f"{len(lanes)} channels carry role {role} (ceiling {_LANE_CEILING})",
        )
    return list(lanes)


# --- the layout block (parent record §2.6, mirrored) ---------------------------


def _urn_for_binding(plan: Mapping[str, Mapping[str, Any]], binding_id: str) -> str | None:
    for urn in plan:
        if urn.split("/")[0].rsplit(".", 1)[-1] == binding_id:
            return urn
    return None


def _insert_ladder_numerics(
    sections: list[dict[str, Any]], plan: Mapping[str, Mapping[str, Any]]
) -> None:
    """Authored button nodes for an L2 action gain the action's numeric
    field nodes immediately before the button (the staging-pair order)."""
    for section in sections:
        children = section.get("children", [])
        out: list[dict[str, Any]] = []
        for node in children:
            if node.get("kind") == "button" and isinstance(node.get("binding_id"), str):
                urn = _urn_for_binding(plan, str(node["binding_id"]))
                row = plan.get(urn or "", {}) if urn else {}
                for field_row in row.get("fields", []):
                    if field_row["mode"] == "numeric":
                        out.append(
                            {
                                "binding_id": node["binding_id"],
                                "kind": "numeric",
                                "field": field_row["field"],
                            }
                        )
            out.append(node)
        section["children"] = out


def _complete_authored_buttons(
    sections: list[dict[str, Any]],
    plan: Mapping[str, Mapping[str, Any]],
    page_id: str,
) -> None:
    """A when-declared action that derives onto this page owes its button
    node too, or the census and the coverage arm both miss it (the SDK
    expander's ``_complete_authored_buttons`` shape)."""
    present: set[str] = set()
    for section in sections:
        for node in section.get("children", []):
            if node.get("kind") == "button":
                present.add(str(node.get("binding_id", "")))
    if not sections:
        return
    for urn, row in sorted(plan.items()):
        if str(row.get("page", "")) != page_id:
            continue
        if row.get("level") not in ("L1", "L2"):
            continue
        slug = urn.split("/")[0].rsplit(".", 1)[-1]
        if slug in present:
            continue
        sections[-1].setdefault("children", []).append(
            {"binding_id": slug, "kind": "button"}
        )


def _build_layout(
    corpus: Path,
    pages: list[dict[str, Any]],
    plots: list[dict[str, Any]],
    authored: list[dict[str, Any]],
    plan: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """The namespaced layout block: authored sections where the reference
    carries them, derived single-section pages otherwise. Numeric staging
    nodes derive from the ladder plan (L2/L3 actions render their numeric
    fields); the expander's own emission satisfies the family schema — a
    violation refuses loudly (never a block that fails its own authority)."""
    by_page = {str(row.get("page_id")): row for row in authored}
    block_pages: list[dict[str, Any]] = []
    plot_done = False
    for page in pages:
        page_id = str(page["id"])
        authored_page = by_page.get(page_id)
        if authored_page is not None:
            sections = [
                {**section, "children": list(section.get("children", []))}
                for section in authored_page.get("sections", [])
            ]
        else:
            children: list[dict[str, Any]] = []
            if page.get("plots") and not plot_done and plots:
                children.append({"plot_index": 0})
                plot_done = True
            for row in page.get("bindings", []):
                binding_id = str(row if isinstance(row, str) else row.get("id"))
                urn = _urn_for_binding(plan, binding_id)
                level = plan.get(urn, {}).get("level") if urn else None
                if level == "L2" and urn is not None:
                    for field_row in plan[urn]["fields"]:
                        if field_row["mode"] == "numeric":
                            children.append(
                                {
                                    "binding_id": binding_id,
                                    "kind": "numeric",
                                    "field": field_row["field"],
                                }
                            )
                if level in ("L1", "L2"):
                    children.append({"binding_id": binding_id, "kind": "button"})
                if level == "L3" and urn is not None:
                    # L3 is preset-mediated; the numeric fields still offer
                    # their effective admittance beside the preset surface.
                    for field_row in plan[urn]["fields"]:
                        if field_row["mode"] == "numeric":
                            children.append(
                                {
                                    "binding_id": binding_id,
                                    "kind": "numeric",
                                    "field": field_row["field"],
                                }
                            )
                    children.append(
                        {"binding_id": binding_id, "kind": "data-table"}
                    )
            # Actions whose bindings carry no page (vendor actions) still
            # derive their controls on their plan page.
            bound = {
                str(row if isinstance(row, str) else row.get("id"))
                for row in page.get("bindings", [])
            }
            for urn, plan_row in sorted(plan.items()):
                if str(plan_row["page"]) != page_id:
                    continue
                slug = urn.split("/")[0].rsplit(".", 1)[-1]
                if slug in bound or plan_row["level"] == "L4":
                    continue
                if plan_row["level"] in ("L1", "L2", "L3"):
                    for field_row in plan_row["fields"]:
                        if field_row["mode"] == "numeric":
                            children.append(
                                {
                                    "binding_id": slug,
                                    "kind": "numeric",
                                    "field": field_row["field"],
                                }
                            )
                    if plan_row["level"] in ("L1", "L2"):
                        children.append({"binding_id": slug, "kind": "button"})
            sections = (
                [
                    {
                        "id": f"{page_id}-section",
                        "title": str(page.get("title", page_id)),
                        "surface": "raised",
                        "span": 12,
                        "children": children,
                    }
                ]
                if children
                else []
            )
        _insert_ladder_numerics(sections, plan)
        _complete_authored_buttons(sections, plan, page_id)
        if sections:
            block_pages.append({"page_id": page_id, "sections": sections})
    block: dict[str, Any] = {
        "contract_version": family_version(corpus),
        "pages": block_pages,
    }
    return block


# --- the derived attachment triple --------------------------------------------


@dataclass(frozen=True)
class DerivedAttachment:
    """One derivation's output: the attachment triple, its exact bytes and
    the resource map the unchanged validator consumes. The derived
    documents never enter the admitted store — the composition validates
    and renders them read-time, visibly host-derived."""

    envelope: dict[str, Any]
    manifest: dict[str, Any]
    catalogue: dict[str, Any]
    envelope_raw: bytes
    manifest_raw: bytes
    catalogue_raw: bytes
    #: ``{resource path: bytes}`` — the manifest bytes plus every declared
    #: asset's exact bytes; ``validate_attachment`` digest-verifies each.
    resources: dict[str, bytes]
    profile_ids: tuple[str, ...]


def _vendor_catalog_documents(
    descriptor: Mapping[str, Any],
    vendor_catalogs: Mapping[str, bytes] | None,
) -> dict[str, Any]:
    """Action schemas from the descriptor's pinned vendor catalogs,
    resolved from ADMISSION bytes (the composition supplies them from the
    content store by digest — the gateway has no plugin package dir; the
    SDK resolves descriptor-relative files, the admission store is the
    gateway's equivalent). Missing or digest-divergent pinned bytes
    refuse typed, never silent."""
    actions: dict[str, Any] = {}
    for row in descriptor.get("contracts", []):
        identifier = str(row.get("id", ""))
        if identifier.startswith("urn:otdp:"):
            continue
        pin = str(row.get("sha256", ""))
        raw = (vendor_catalogs or {}).get(pin)
        if raw is None:
            raise _refuse(
                "classref_unknown_action",
                f"pinned vendor catalog {row.get('path')} is not admitted "
                f"(digest {pin})",
            )
        if hashlib.sha256(raw).hexdigest() != pin:
            raise _refuse(
                "classref_unknown_action",
                f"pinned vendor catalog {row.get('path')} digest mismatch",
            )
        document = json.loads(raw)
        actions.update(document.get("actions", {}))
    return actions


def _catalog_document(
    corpus: Path,
    pins: dict[str, str] | None,
    descriptor: Mapping[str, Any],
) -> dict[str, Any]:
    """The served OTDP device-profile catalog for the descriptor's pinned
    version, digest-verified from the corpus (the derivation's profile
    rows and action schemas). A descriptor pinning a version whose catalog
    the corpus does not carry refuses typed."""
    row_key = f"otdp/{descriptor['otdp_version']}/device-profile-catalog.json"
    try:
        return dict(_read_corpus_json(corpus, row_key, pins))
    except FileNotFoundError as exc:
        raise _refuse(
            "classref_unknown_action",
            f"the descriptor's profile catalog {row_key} is not served",
        ) from exc


def _assemble_triple(
    descriptor: Mapping[str, Any],
    descriptor_raw: bytes,
    references: list[dict[str, Any]],
    actions: Mapping[str, Any],
    catalog_actions: Mapping[str, Any],
    corpus: Path,
) -> DerivedAttachment:
    """The derived triple (the SDK expander's ``_finish`` assembly, minus
    the SDK-side surfaces the gateway does not consume — the expectation
    document, the declaration and the preset scaffolds, the design's §9.3
    confirmation). Byte shapes mirror the SDK's canonical serialization."""
    merged = _merge_references(references)
    lanes = _resolve_channels(descriptor, merged)
    slot_for_urn = {
        slot["action"]: (key, slot)
        for key, slot in merged["slots"].items()
        if slot.get("action")
    }
    page_for_slot: dict[str, str] = {}
    for page in merged["pages"]:
        for key in page.get("_slot_keys", []):
            page_for_slot.setdefault(key, str(page["id"]))
    plan, _divergences = _derive_controls(
        actions,
        catalog_actions,
        slot_for_urn,
        page_for_slot,
        merged["expect"]["controls"],
    )
    return _assemble_documents(
        descriptor,
        descriptor_raw,
        tuple(sorted({str(item["profile_id"]) for item in references})),
        merged,
        lanes,
        actions,
        catalog_actions,
        plan,
        corpus,
    )


def _assemble_documents(
    descriptor: Mapping[str, Any],
    descriptor_raw: bytes,
    profile_ids: tuple[str, ...],
    merged: dict[str, Any],
    lanes: list[dict[str, Any]],
    actions: Mapping[str, Any],
    catalog_actions: Mapping[str, Any],
    plan: dict[str, dict[str, Any]],
    corpus: Path,
) -> DerivedAttachment:
    """The document assembly (the SDK expander's ``_finish`` port):
    bindings, targets, pages, assets, the layout block and the triple,
    byte-shaped like the SDK's emission (B8's pin)."""
    version = active_version_from_corpus(corpus, "plugin-ui")
    dataset_slots = {
        key: slot
        for key, slot in merged["slots"].items()
        if slot.get("kind") == "dataset"
    }
    capture_key = next(iter(dataset_slots), None)
    capture_slot: Mapping[str, Any] = dataset_slots.get(capture_key or "", {})
    measurement_id = next(
        (
            str(row["id"])
            for row in descriptor.get("contracts", [])
            if str(row.get("id", "")).startswith("urn:otdp:measurement")
        ),
        f"urn:otdp:measurement:{descriptor['otdp_version']}",
    )
    lane_vars = [
        {"id": row["id"], "type": "string", "unit": None, "shape": "vector"}
        for row in lanes
    ]
    x_var = {"id": "t", "type": "number", "unit": "s", "shape": "vector", "axis_role": "x"}
    bindings: list[dict[str, Any]] = []
    targets: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    if capture_key:
        targets.append(
            {
                "id": capture_key,
                "kind": "dataset",
                "action_id": capture_slot["action"],
                "profile_ids": profile_ids,
                "measurement_schema_id": measurement_id,
                "variables": [x_var, *lane_vars],
            }
        )
        bindings.append({"id": capture_key, "kind": "dataset", "target_id": capture_key})
    capture_binding_id = capture_key or ""
    decode_key = next((key for key in dataset_slots if key != capture_key), None)
    decode_slot: Mapping[str, Any] = dataset_slots.get(decode_key or "", {})
    decode_declared = bool(decode_slot and str(decode_slot.get("action")) in actions)
    decode_annotated_urn = next(
        (
            urn
            for urn in actions
            if urn.split("/")[0].rsplit(".", 1)[-1] == "decode_annotated"
        ),
        None,
    )
    decoder_lanes: list[dict[str, Any]] = []
    if (
        (decode_declared or decode_annotated_urn)
        and descriptor.get("decoders")
    ):
        # The SDK resolves decoder documents from descriptor-relative
        # files; the gateway's equivalent is the admission store, and a
        # pin the store cannot resolve skips the decoder (the SDK's own
        # unreadable-document arm). The F1/F2 fixtures carry none.
        for _pin in descriptor["decoders"]:
            continue
    if decode_key and decode_declared:
        targets.append(
            {
                "id": decode_key,
                "kind": "dataset",
                "action_id": decode_slot["action"],
                "profile_ids": profile_ids,
                "measurement_schema_id": measurement_id,
                "variables": [x_var, *lane_vars],
            }
        )
        bindings.append({"id": decode_key, "kind": "dataset", "target_id": decode_key})
    configuration_slots = {
        key: slot
        for key, slot in merged["slots"].items()
        if slot.get("kind") == "configuration"
    }
    settings_schema: dict[str, Any] = {"type": "object", "properties": {}}
    settings_blobs: dict[str, bytes] = {}
    for config_key, config_slot in configuration_slots.items():
        urn = str(config_slot["action"])
        if urn not in actions:
            continue
        effective = _effective_action_schema(
            urn, catalog_actions[urn], actions[urn].get("input_constraints") or {}
        )
        catalogue_input = catalog_actions[urn].get("input_schema", {}) or {}
        settings_schema = {
            **effective,
            "$id": catalogue_input.get("$id", f"urn:otdp:action:{urn}:input"),
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
        }
        schema_name = f"settings/{config_key}.schema.json"
        schema_raw = (json.dumps(settings_schema, indent=2) + "\n").encode()
        assets.append(
            {
                "id": schema_name,
                "path": schema_name,
                "sha256": hashlib.sha256(schema_raw).hexdigest(),
            }
        )
        settings_blobs[str(schema_name)] = schema_raw
        targets.append(
            {
                "id": config_key,
                "kind": "configuration",
                "action_id": urn,
                "profile_ids": profile_ids,
                "input_schema_id": catalogue_input.get("$id"),
                "schema_asset_id": schema_name,
                "preset_asset_ids": [],
            }
        )
        bindings.append(
            {"id": config_key, "kind": "configuration", "target_id": config_key}
        )
    procedure_slots = {
        key: slot for key, slot in merged["slots"].items() if slot.get("kind") == "procedure"
    }
    for proc_key, proc_slot in procedure_slots.items():
        urn = str(proc_slot["action"])
        if urn not in actions:
            continue  # a when_declared slot the descriptor does not declare
        targets.append(
            {
                "id": proc_key,
                "kind": "procedure",
                "action_id": urn,
                "profile_ids": profile_ids,
                "input_schema_id": catalog_actions[urn]
                .get("input_schema", {})
                .get("$id"),
            }
        )
        bindings.append({"id": proc_key, "kind": "procedure", "target_id": proc_key})
    # Vendor actions carry no manifest target (the vendored validator
    # admits catalogue targets for profile actions only); their controls
    # render through the layout block on their plan page.
    pages_out: list[dict[str, Any]] = []
    for page in merged["pages"]:
        page_id = str(page["id"])
        kind = str(page.get("kind", "readings"))
        allowed = {
            "dataset": {"dataset"},
            "configuration": {"configuration", "procedure"},
            "readings": {"observation"},
        }.get(kind, {"observation"})
        rows = [
            b
            for b in page.get("bindings", [])
            if b in {row["id"] for row in bindings}
            and {row["id"]: row["kind"] for row in bindings}.get(b, "") in allowed
        ]
        pages_out.append(
            {
                "id": page_id,
                "title": str(page["title"]) if "title" in page else page_id,
                "kind": kind,
                "bindings": rows,
                "required": True,
            }
        )
    plots: list[dict[str, Any]] = []
    for page in pages_out:
        template = next(
            (row for row in merged["pages"] if str(row["id"]) == page["id"]), None
        )
        plot_spec = (template or {}).get("plot")
        if plot_spec is None:
            continue
        over_key = str(plot_spec.get("over_slot", ""))
        if over_key not in merged["slots"] or over_key not in {
            row["id"] for row in bindings
        }:
            continue
        groups = []
        full = len(lane_vars) // _GROUP_SIZE
        remainder = len(lane_vars) % _GROUP_SIZE
        total = full + (1 if remainder >= 2 else 0)
        for k in range(total):
            start = k * _GROUP_SIZE
            width = _GROUP_SIZE if k < full else remainder
            members = [row["id"] for row in lane_vars[start : start + width]]
            groups.append(
                {
                    "id": f"lanes-{k + 1}",
                    "label": f"D{start + 1}-D{start + width}",
                    "member_ids": members,
                    "radix": str(plot_spec.get("group_radix", "hex")),
                }
            )
        plots.append(
            {
                "kind": "digital_lanes",
                "binding_id": capture_binding_id,
                "x": "t",
                "y": [row["id"] for row in lane_vars],
                "channel_hints": [
                    {"variable_id": row["id"], "visible": True} for row in lane_vars
                ],
                "lane_groups": groups,
                "decoder_lanes": decoder_lanes,
            }
        )
        page["plots"] = [plots[-1]]
    layout_block = _build_layout(corpus, pages_out, plots, merged["layouts"], plan)
    manifest = {
        "contract_version": version,
        "plugin_id": str(descriptor["id"]),
        "descriptor_sha256": hashlib.sha256(descriptor_raw).hexdigest(),
        "bindings": bindings,
        "pages": pages_out,
        "assets": assets,
        "extensions": {LAYOUT_EXTENSION_KEY: layout_block},
    }
    manifest_raw = (json.dumps(manifest, indent=2) + "\n").encode()
    envelope = {
        "contract_version": version,
        "descriptor_sha256": hashlib.sha256(descriptor_raw).hexdigest(),
        "resource_root": "ui",
        "manifest": {
            "path": "manifest.json",
            "sha256": hashlib.sha256(manifest_raw).hexdigest(),
        },
    }
    envelope_raw = (json.dumps(envelope, indent=2) + "\n").encode()
    catalogue = {
        "contract_version": version,
        "descriptor_sha256": hashlib.sha256(descriptor_raw).hexdigest(),
        "targets": targets,
    }
    catalogue_raw = (json.dumps(catalogue, indent=2) + "\n").encode()
    resources: dict[str, bytes] = {"manifest.json": manifest_raw, **settings_blobs}
    return DerivedAttachment(
        envelope=envelope,
        manifest=manifest,
        catalogue=catalogue,
        envelope_raw=envelope_raw,
        manifest_raw=manifest_raw,
        catalogue_raw=catalogue_raw,
        resources=resources,
        profile_ids=profile_ids,
    )


def derive_attachment(
    descriptor_raw: bytes,
    *,
    corpus: Path,
    vendor_catalogs: Mapping[str, bytes] | None = None,
    references_override: list[dict[str, Any]] | None = None,
) -> DerivedAttachment:
    """Expand (descriptor × reference) into the derived attachment triple.

    Raises ``ClassRefusal`` for every fail-closed case (parent record
    §3.3's table); the caller renders the typed refusal, never a partial
    page. Selection is the fail-open boundary: call ``select_references``
    first — ``None`` there means the unknown-class arm renders today's
    ``no-attachment`` absence (B3), never a derivation.

    ``references_override`` exists for the refusal arms that mutate a
    reference document in tests; production callers never pass it."""
    descriptor = json.loads(descriptor_raw)
    if references_override is not None:
        references = [
            validate_reference_document(item, corpus=corpus)
            for item in references_override
        ]
        references.sort(key=lambda item: str(item["profile_id"]))
    else:
        references = select_references(corpus, descriptor) or []
    if not references:
        raise _refuse(
            "classref_invalid_reference",
            "no reference applies to the descriptor's profiles",
        )
    for item in references:
        profile = str(item["profile_id"])
        if profile not in (descriptor.get("profiles") or []):
            raise _refuse(
                "classref_invalid_reference",
                f"profile {profile} is not claimed by the descriptor",
            )
    for item in references:
        active = active_version_from_corpus(corpus, "plugin-ui")
        if not _satisfies_target(active, item["targets"]["plugin_ui"]):
            raise _refuse(
                "classref_target_version",
                f"active plugin-ui {active} does not satisfy "
                f"the reference target {item['targets']['plugin_ui']}",
            )
    pins = _corpus_pin_rows(corpus)
    catalog = _catalog_document(corpus, pins, descriptor)
    catalog_actions: dict[str, Any] = dict(catalog.get("actions", {}))
    catalog_actions.update(_vendor_catalog_documents(descriptor, vendor_catalogs))
    actions = descriptor.get("actions") or {}
    # A descriptor-declared action absent from every served catalog is a
    # typed refusal — the ladder cannot derive what the catalogs do not
    # describe (the SDK expander's F8b arm).
    for urn in actions:
        if urn not in catalog_actions:
            raise _refuse(
                "classref_unknown_action",
                f"descriptor declares {urn}, absent from every served catalog",
            )
    for item in references:
        slot_keys = set(item.get("slots", {}))
        for page in item.get("pages", []):
            unknown = [
                key for key in page.get("binding_slots", []) if key not in slot_keys
            ]
            if unknown:
                raise _refuse(
                    "classref_unknown_slot",
                    f"page {page.get('id')!r} binds unknown slot(s) "
                    f"{', '.join(sorted(unknown))}",
                )
    # Every claimed profile's required actions (the merge order must not
    # decide which profile gets checked — the SDK expander's M7 arm).
    profile_rows = {
        str(row.get("id")): row
        for row in catalog.get("profiles", [])
        if isinstance(row, dict) and row.get("id")
    }
    for item in references:
        row = profile_rows.get(str(item["profile_id"]))
        if row is None:
            raise _refuse(
                "classref_unknown_action",
                f"profile {item['profile_id']} absent from the served profile catalog",
            )
        for urn in row.get("required_actions", []):
            if urn not in actions:
                raise _refuse(
                    "classref_required_action_absent",
                    f"required-class action {urn} is not declared by the descriptor",
                )
    for item in references:
        for key, slot in item.get("slots", {}).items():
            urn = slot.get("action")
            if urn and urn not in catalog_actions:
                raise _refuse(
                    "classref_unknown_action",
                    f"slot {key} names {urn}, absent from the served catalogs",
                )
    _check_slot_conflicts(references)
    return _assemble_triple(
        descriptor,
        descriptor_raw,
        references,
        actions,
        catalog_actions,
        corpus,
    )


def validate_layout_block(block: Any, *, corpus: Path) -> str | None:
    """The namespaced layout block against the digest-verified corpus
    layout schema — the block's only validation authority (the canonical
    manifest validator is extension-blind). ``None`` when the block
    validates; the first sorted finding's message otherwise (the typed
    ``classref_layout_invalid`` refusal's text)."""
    from jsonschema import Draft202012Validator

    findings = sorted(
        Draft202012Validator(layout_schema(corpus)).iter_errors(block),
        key=lambda error: list(error.path),
    )
    if not findings:
        return None
    first = findings[0]
    where = "/".join(str(part) for part in first.path) or "(root)"
    return f"{where}: {first.message}"
