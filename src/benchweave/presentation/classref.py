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
committed fixtures under ``tests/presentation/classref_fixtures/`` are the
drift alarm: a divergence between the two derivations reddens the parity
test, and a corpus byte that moves re-pins through the fixtures' own
regeneration. The F1/F2/F1-da fixtures were generated ONCE from the SDK
expander at the submodule pin (v0.14.0, ``201c343``); the F5 trio fixture
was generated from the SDK expander on the L5 widening branch
(``feat/l5-sdk-widening`` @ ``8f6b5ee``), whose semantics the derivation
functions here mirror. At the L11 family bump (0.2.0 -> 0.3.0) the four
triples were regenerated from THIS derivation over the new corpus, an
8-line stamp-only delta (the layout block's ``contract_version`` and the
envelope's derived manifest pin), verified against the SDK derivation at
the pin reproducing the pre-bump bytes exactly — the SDK's own vendored
corpus carries 0.2.0 until the batched promotion leg re-stamps its side.
At the 0.4.0 family bump (0.3.0 -> 0.4.0) the five triples were re-stamped
the same way over the new corpus, a 10-line stamp-only delta (each layout
block's ``contract_version`` and each envelope's derived manifest pin:
five pairs); every pre-edit manifest digest equaled its envelope's recorded
pin, so the delta is the version line and its digest only. The SDK's own
vendored corpus carries 0.3.0 until the SDK leg re-stamps its side. At
issue #556 Track A the five triples were REGENERATED from the pinned
v0.21.0 expander (``88dcc4d``, materialized through ``git archive`` —
the submodule working tree stays pristine), a 44-line delta in exactly
the design record §5's stated class: the W8 fold collapses each doubled
staging numeric to one occurrence (f1/f2/f1-da's ``margin_ppm``/
``hysteresis_mv``, f6-smu's ``max_duration_ms``/``max_bytes``) and the
envelope's manifest pin follows; f5-trio moved zero bytes and no
completion-appended pair appeared (the W1 prediction held). At the 0.6.0
family bump (0.5.0 -> 0.6.0, issue #560 — the content-count cap removal)
the parity fixture pairs were re-stamped from THIS derivation over the
new corpus — SEVEN pairs on the final tree (f1, f2, f1-da, f5-trio,
f6-smu, m400 at the first pass; dmm joining with the #563 rebase and
re-stamped in the same arc): each manifest's layout ``contract_version``
and each envelope's derived manifest pin, a stamp-only delta; the
derivation itself moved zero bytes, so the delta is the version line and
its digest. The SDK's own vendored corpus carries 0.5.0 until the SDK leg
re-stamps its side.

Mirrored-source pin: the derivation functions mirror
``benchweave_sdk.classref`` at v0.14.0 PLUS the L5 input-trio widening
(``_row_mode`` / ``_MODE_KIND`` / the widened ``_field_rows`` /
``_ladder_level`` / ``_staging_nodes``; the SDK branch above, landing as
v0.15.0 at the pointer leg) PLUS the plot-kind mirror at v0.18.0
(issue #521; design record 2026-10-21-classref-plot-kind-mirror-design):
the per-slot plot kind, the (channel, quantity) variable ids, the
readings-page observation expansion and the reading-tile layout strip,
pinned byte for byte by the f6-smu fixture — PLUS the three-layer
resolution mirror at v0.21.0 (issue #556 Track A; design record
2026-10-25-issue556-track-a-gateway-mirror): the refusal split, the
residual (custom) resolution with its fold hardening (W2/W3/W5/M6/W7/
W9/G4), the composed walk with its conflict arms and disclosures, the
W1/W8 emission order, and the m400 acceptance tag pinning all three
layers in one descriptor — PLUS the composed-member mirror (issue #556
Track B, slice B7; the SDK's composed-member tips
``feat/556-b3-members`` ``2dd718d`` through
``feat/556-b5-datasets-plots`` ``bac0ac3``, folds included): the member
walk (one ``_pin_shape_groups`` definition, the generalized ambiguity
refusal, the member conflict family, the shared ``pinned_id_shadow``
guard over the accepted set), the injection seam with per-slot channel
resolution and the page-level join, the member target arms (the vendor
profile row the seam admits), the plot-kind inheritance and the member
plot, the computed variables, the placement dispositions and the
mint-collision refusal, and the residual rows the SDK gate renders on
its REPORTED channel — carried on ``PresentationState.disclosures`` in
the SDK's own wording. The member-declaration SCHEMA itself joined the
family at 0.5.0 (the B2 standards motion, merged 2026-10-26): before
that merge a member pin against this corpus refused typed as a platform
fault (the lazy-loader rule below); since it, member pins validate
against the served schema and member-pin-free derivations are unaffected.
A re-pin that moves the SDK
derivation moves these functions in the same arc (the design's
fixture-freeze re-pin rule); B8 reds otherwise.

Disclosed residuals of the plot-kind mirror: (1) a decoder-carrying
numeric descriptor keeps its decode binding and target — the lanes
simply do not ride the analog plot (the schema bans decoder lanes
there; the SDK's own emission, mirrored); (2) the serve-side parameter
guard ``_resolve_parameters`` documents below. (The SDK's empty-page
fallback WAS this list's second residual until the 2026-10-26 B7
refute fold F2 mirrored it — every declared page now renders its panel,
the dmm tag pinning the bytes; Track A's "the regen decides" deferral
closed by decision, not by regeneration, because no committed fixture
carried the shape until that tag.)

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
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from dataclasses import field as dataclass_field
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
#: The manifest schema's analog-plot y ceiling (the ``$defs.plot`` analog
#: branch, ``y maxItems 16``). The SDK expander ships no over-16 arm; the
#: gateway refuses typed (``classref_series_ceiling``, the
#: ``classref_lane_ceiling`` shape) rather than emitting a manifest the
#: schema would refuse diffusely — the fail-closed-arm-the-SDK-lacks
#: precedent (the non-object decoder-document arm).
_ANALOG_Y_CEILING = 16
_HOST_SUPPLIED_UNIVERSAL = ("acquisition_id", "configuration_id")
_NUMERIC_TYPES = ("number", "integer")
#: The layout-node kind each field-row mode emits (the L5 widening, gateway
#: #463; mirrored from the SDK expander's ``_MODE_KIND`` — REG-4). A literal
#: const renders the §E.1 select's read-only fixed display — the F2 ruling
#: (design-record addendum, 2026-10-16): the landed contract row and the
#: renderer both say a const renders the fixed display.
_MODE_KIND: dict[str, str] = {
    "numeric": "numeric",
    "text": "text",
    "const": "select",
    "enum": "select",
    "boolean": "boolean",
}
#: The closed constraint vocabulary (parent record §3.7): the first group
#: narrows a rendered control; the riders (required/properties/items/
#: min/max/unique) ride the conjunctive validation lanes untouched and
#: derive no controls. #541 W9 fold (mirrored, issue #556 Track A):
#: minLength/maxLength join the control group — a vendor action declaring
#: a string length bound used to refuse classref_constraint_unsupported,
#: so "never refuses" was false for that input class.
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
        "minLength",
        "maxLength",
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
FOUNDING_FAMILY_VERSION = "0.6.0"


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
    the reference schema, the layout schema (the layout block's only
    validation authority — the canonical manifest validator is
    extension-blind) and the composed-class schema (the composed walk's
    validation authority, joined at the family's 0.4.0 — already
    vendored and manifest-pinned; zero standards bytes move)."""
    corpus = Path(corpus_text)
    version = active_version_from_corpus(corpus, _FAMILY)
    pins = _corpus_pin_rows(corpus)
    # The member-declaration schema joins the family at 0.5.0 (#556 Track
    # B); a tree serving an older family carries no such file, and the
    # member walk's validation arm reads ``None`` for it — a member PIN on
    # such a tree refuses loudly there (the lazy-loader rule), while a
    # member-pin-free derivation is unaffected.
    try:
        member_schema: dict[str, Any] | None = _read_corpus_json(
            corpus,
            f"{_FAMILY}/{version}/composed-member-declaration.schema.json",
            pins,
        )
    except FileNotFoundError:
        member_schema = None
    return {
        "version": version,
        "reference_schema": _read_corpus_json(
            corpus, f"{_FAMILY}/{version}/class-reference.schema.json", pins
        ),
        "layout_schema": _read_corpus_json(
            corpus, f"{_FAMILY}/{version}/layout.schema.json", pins
        ),
        "composed_schema": _read_corpus_json(
            corpus, f"{_FAMILY}/{version}/composed-action-class.schema.json", pins
        ),
        "member_schema": member_schema,
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
    ``profile_id``, validated against the family schema.

    A reference file whose bytes diverge from their manifest pin, or
    whose bytes do not parse, is corpus corruption on a SERVED family —
    it refuses loud as a typed refusal (the corpus-pin gate's own
    loudness everywhere else: ``layout_schema`` and the document set
    raise on the same state), never a silent skip that renders the
    plain no-attachment absence."""
    root = corpus / _FAMILY / version
    if not root.is_dir():
        return None
    for path in sorted(root.glob("class-*.json")):
        relpath = f"{_FAMILY}/{version}/{path.name}"
        try:
            raw = path.read_bytes()
            _verify_corpus_pin(raw, relpath, pins)
            document = json.loads(raw)
        except OSError:
            # An unreadable directory entry is not corpus state this
            # walk can name a finding about; the pin gate stays loud on
            # the bytes it CAN read.
            continue
        except StandardsError as exc:
            raise ClassRefusal(str(exc)) from exc
        except ValueError as exc:
            raise _refuse(
                "classref_invalid_reference", f"{relpath}: {exc}"
            ) from exc
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


def _tighter_bound(
    catalogue_bound: tuple[Any, bool],
    constraint_bound: tuple[Any, bool],
    *,
    higher_value_is_tighter: bool,
) -> tuple[Any, bool]:
    """One side of the bounds intersection: the pair admitting FEWER
    values (parent record §3.7).

    On the high side the SMALLER value is tighter; on the low side the
    LARGER one is. On EQUAL values the exclusive spelling is the tighter
    end on both sides — the effective schema must never admit what the
    plugin's own declaration refuses. Comparing ``(value, exclusive)``
    tuples cannot express that: ``min((5, False), (5, True))`` returns the
    INCLUSIVE pair while ``max()`` returns the exclusive one, so tuple
    order tie-broke the two sides in opposite directions. Both sides read
    through this one comparator, so the tie rule is stated once rather
    than re-derived per side.
    """
    if catalogue_bound[0] == constraint_bound[0]:
        return (catalogue_bound[0], catalogue_bound[1] or constraint_bound[1])
    if higher_value_is_tighter:
        return (
            catalogue_bound
            if catalogue_bound[0] > constraint_bound[0]
            else constraint_bound
        )
    return (
        catalogue_bound
        if catalogue_bound[0] < constraint_bound[0]
        else constraint_bound
    )


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
    # G4 fold (mirrored): both SIDES of the intersection are value-typed
    # before any comparison — an ill-typed catalogue or constraint bound
    # used to crash the max()/min() intersection arithmetic, and an
    # ill-typed length bound rode silently into the row.
    _check_value_types(action_urn, property_name, constraint)
    _check_value_types(action_urn, property_name, catalogue_schema)
    effective = dict(catalogue_schema)
    declared_type = (
        catalogue_schema.get("type") if isinstance(catalogue_schema, dict) else None
    )

    # Bounds INTERSECT: a looser constraint can never widen the catalogue's
    # admittance — the tighter end of each side wins (on equal values the
    # exclusive end, ``_tighter_bound``), the exclusivity flags carry, and an
    # empty result refuses.
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
        low = _tighter_bound(
            low_catalogue, low_constraint, higher_value_is_tighter=True
        )
    high: tuple[Any, bool] | None
    if high_catalogue is None or high_constraint is None:
        # The high-bound selection reads HIGH_constraint (the mirrored
        # body; the gateway copy transposed it to low_constraint, which
        # silently DROPPED a constraint-only maximum against an
        # unbounded catalogue row — an admittance widening).
        high = high_catalogue if high_constraint is None else high_constraint
    else:
        high = _tighter_bound(
            high_catalogue, high_constraint, higher_value_is_tighter=False
        )
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
    # W9 fold (mirrored): string length bounds are inside the closed
    # vocabulary and INTERSECT like the numeric ones — the tighter end of
    # each side wins. An accepted keyword the intersection silently
    # dropped would be a narrowing the rendered control never sees; a
    # length bound on a non-string catalogue type is the same conflict
    # the numeric bounds raise.
    if "minLength" in constraint or "maxLength" in constraint:
        if declared_type != "string":
            raise _refuse(
                "classref_effective_schema_conflict",
                f"action {action_urn} field {property_name}: length bound "
                f"applied to catalogue type {declared_type!r}",
            )
        if "minLength" in constraint:
            current = effective.get("minLength")
            effective["minLength"] = (
                max(current, constraint["minLength"])
                if current is not None
                else constraint["minLength"]
            )
        if "maxLength" in constraint:
            current = effective.get("maxLength")
            effective["maxLength"] = (
                min(current, constraint["maxLength"])
                if current is not None
                else constraint["maxLength"]
            )
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
    """A field narrowed to an empty admittance set refuses (parent record
    §3.7). M6 (mirrored): exclusivity is part of emptiness — a closed
    bound meeting an open bound at the same value admits nothing, in
    both crossing directions. W5 fold (mirrored): an empty declared enum
    is the same emptiness — a select that admits no value never derives,
    residual or catalogued alike; and inverted string length bounds
    (W9) admit no string either."""
    if effective.get("const") is not None:
        return
    enum_values = effective.get("enum")
    if isinstance(enum_values, list) and not enum_values:
        raise _refuse(
            "classref_effective_schema_empty",
            f"action {action_urn} field {property_name}: enum admits no value",
        )
    min_length = effective.get("minLength")
    max_length = effective.get("maxLength")
    if (
        isinstance(min_length, (int, float))
        and not isinstance(min_length, bool)
        and isinstance(max_length, (int, float))
        and not isinstance(max_length, bool)
        and min_length > max_length
    ):
        raise _refuse(
            "classref_effective_schema_empty",
            f"action {action_urn} field {property_name}: string length "
            "bounds admit no value",
        )
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


def _bounds_of(
    fragment: dict[str, Any],
) -> tuple[tuple[float, bool] | None, tuple[float, bool] | None]:
    """The fragment's declared numeric bounds as (value, exclusive)
    pairs, the exclusive spelling winning when both appear (mirrored
    from the SDK expander at the v0.21.0 pin)."""
    def _one(exclusive_key: str, plain_key: str) -> tuple[float, bool] | None:
        if exclusive_key in fragment:
            return float(fragment[exclusive_key]), True
        if plain_key in fragment:
            return float(fragment[plain_key]), False
        return None
    return _one("exclusiveMinimum", "minimum"), _one("exclusiveMaximum", "maximum")


def _check_value_types(
    action_urn: str, property_name: str, fragment: dict[str, Any]
) -> None:
    """A CONTROL keyword whose value is ill-typed refuses
    ``classref_constraint_unsupported`` (the G4 fold, mirrored): W9
    admitted keywords to the closed vocabulary without validating their
    values, and `enum` under `minLength: "3"` crashed the narrowing
    with a bare TypeError. The rider covers every control keyword's
    value type — on the constraint side, the catalogue side and the
    row-descent side alike, wherever a fragment enters. `const` admits
    any JSON value: nothing orders or lens it before the row is
    minted."""
    def _refuse_value(keyword: str, wanted: str, value: Any) -> ClassRefusal:
        return _refuse(
            "classref_constraint_unsupported",
            f"action {action_urn} field {property_name}: {keyword} "
            f"must be {wanted}, got {value!r}",
        )

    for keyword in (
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
    ):
        if keyword in fragment:
            value = fragment[keyword]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise _refuse_value(keyword, "a number", value)
    for keyword in ("minLength", "maxLength"):
        if keyword in fragment:
            value = fragment[keyword]
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise _refuse_value(keyword, "a non-negative integer", value)
    if "pattern" in fragment and not isinstance(fragment["pattern"], str):
        raise _refuse_value("pattern", "a string", fragment["pattern"])
    if "enum" in fragment and not isinstance(fragment["enum"], list):
        raise _refuse_value("enum", "a list", fragment["enum"])
    if "type" in fragment:
        # The committed corpus's own nullable spelling is a type ARRAY
        # (JSON Schema's `type` array — `['number', 'null']` on the
        # function-generator class's load_ohm): admitted, consumed
        # inexpressible exactly as before this rider. A value that is
        # neither a string nor a non-empty list of strings keys no
        # consumer comparison anywhere in the module.
        value = fragment["type"]
        if not (
            isinstance(value, str)
            or (
                isinstance(value, list)
                and value
                and all(isinstance(item, str) for item in value)
            )
        ):
            raise _refuse_value("type", "a string or a list of strings", value)


def _check_residual_fragment(
    action_urn: str, name: str, fragment: dict[str, Any]
) -> None:
    """The residual mode's gates, applied at EVERY depth (the W2 fold,
    mirrored): the closed keyword vocabulary, the empty-admittance
    refusal, and the bound/type conflicts the catalogued intersection
    raises — a fragment under ``properties``/``items`` is as much a
    declared constraint as a top-level one, and its catalogued twin
    refuses the same shape through ``_merge_deep``'s recursion."""
    for keyword in fragment:
        if (
            keyword in _CONSTRAINT_CONTROL_KEYWORDS
            or keyword in _CONSTRAINT_RIDER_KEYWORDS
        ):
            continue
        raise _refuse(
            "classref_constraint_unsupported",
            f"action {action_urn} field {name}: keyword {keyword!r} "
            "is outside the closed intersection vocabulary",
        )
    # G4 fold: value-typed before the admittance and bound checks.
    _check_value_types(action_urn, name, fragment)
    _check_admittance(action_urn, name, fragment)
    declared_type = fragment.get("type")
    value_typed = "enum" in fragment or "const" in fragment
    low, high = _bounds_of(fragment)
    if (
        (low is not None or high is not None)
        and declared_type is not None
        and declared_type not in _NUMERIC_TYPES
        and not value_typed
    ):
        # W3 fold (mirrored): numeric bounds on a declared non-numeric
        # type are a self-contradiction — the catalogued twin refuses
        # the same shape when a constraint's bounds meet a non-numeric
        # catalogue type. A fragment carrying enum/const is handled at
        # row time, where the declared values intersect the bounds.
        raise _refuse(
            "classref_effective_schema_conflict",
            f"action {action_urn} field {name}: numeric bound "
            f"applied to declared type {declared_type!r}",
        )
    if (
        ("minLength" in fragment or "maxLength" in fragment)
        and declared_type is not None
        and declared_type != "string"
        and not value_typed
    ):
        raise _refuse(
            "classref_effective_schema_conflict",
            f"action {action_urn} field {name}: length bound "
            f"applied to declared type {declared_type!r}",
        )
    for sub_name, sub in (fragment.get("properties") or {}).items():
        if not isinstance(sub, dict):
            raise _refuse(
                "classref_constraint_unsupported",
                f"action {action_urn} field {name}.{sub_name}: constraint "
                "fragment must be an object",
            )
        _check_residual_fragment(action_urn, f"{name}.{sub_name}", sub)
    items = fragment.get("items")
    if isinstance(items, dict):
        _check_residual_fragment(action_urn, f"{name}[]", items)


def _intersect_declared_values(
    action_urn: str, property_name: str, fragment: dict[str, Any]
) -> None:
    """A fragment declaring a value set (enum/const) under declared
    bounds renders exactly the values both admit (the W3 fold,
    mirrored — the generic surface admits what the declaration admits,
    no more). A non-empty enum NARROWS to the admitted subset; an
    emptied one refuses under the empty-admittance survivor; a const
    outside the bounds is a conflict, never a silently dropped bound.
    Applied where rows are minted, so every path (catalogue row,
    intersection, residual) gets it at every depth; the conjunctive
    validation schemas keep both keywords untouched."""
    low, high = _bounds_of(fragment)
    min_length = fragment.get("minLength")
    max_length = fragment.get("maxLength")
    if (
        low is None and high is None
        and min_length is None and max_length is None
    ):
        return

    def _admitted(value: Any) -> bool:
        numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
        if low is not None or high is not None:
            if not numeric:
                return False
            if low is not None:
                edge, exclusive = low
                if value < edge or (exclusive and value == edge):
                    return False
            if high is not None:
                edge, exclusive = high
                if value > edge or (exclusive and value == edge):
                    return False
        if min_length is not None or max_length is not None:
            if not isinstance(value, str):
                return False
            if min_length is not None and len(value) < min_length:
                return False
            if max_length is not None and len(value) > max_length:
                return False
        return True

    if "const" in fragment:
        if not _admitted(fragment["const"]):
            raise _refuse(
                "classref_effective_schema_conflict",
                f"action {action_urn} field {property_name}: const "
                f"{fragment['const']!r} outside the declared bounds",
            )
        return
    enum_values = fragment.get("enum")
    if isinstance(enum_values, list) and enum_values:
        allowed = [value for value in enum_values if _admitted(value)]
        if not allowed:
            raise _refuse(
                "classref_effective_schema_empty",
                f"action {action_urn} field {property_name}: every declared "
                "enum value falls outside the declared bounds",
            )
        if allowed != enum_values:
            fragment["enum"] = allowed


def _effective_action_schema(
    action_urn: str,
    catalogue_action: dict[str, Any] | None,
    constraints: dict[str, Any],
) -> dict[str, Any]:
    """The action's effective input schema: catalogue AND descriptor
    constraints, per property (parent record §3.7). Validation lanes stay
    conjunctive and untouched; this derives per-field admittance for the
    derived manifest's settings-schema asset.

    A ``None`` catalogue row is the residual mode (issue #556 Track A,
    design §3.3): no served catalog describes the action, so the
    effective schema is the descriptor's own constraints, still gated
    by the same closed keyword vocabulary and the same empty-admittance
    refusal — the gateway invents no admittance a catalogue granted; it
    renders the plugin's own declared constraints and the plan row
    carries resolution "custom"."""
    properties: dict[str, Any] = {}
    required: set[str] = set()
    if catalogue_action is not None:
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
        # G4 fold (mirrored): the catalogue side validates too — a served
        # or vendor-pinned row with an ill-typed control value refuses
        # typed where it enters, never at the row descent's crash.
        for name, schema in properties.items():
            _check_value_types(action_urn, name, schema)
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
        if base is None and catalogue_action is None:
            # Residual: no catalogue side exists to intersect — the
            # declared fragment IS the effective schema, verbatim, after
            # the same closed-vocabulary and admittance gates — applied
            # at EVERY depth (the W2 fold): a nested fragment under
            # properties/items is as much a declared constraint as a
            # top-level one.
            _check_residual_fragment(action_urn, name, fragment)
            properties[name] = json.loads(json.dumps(fragment))
            continue
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


def _row_mode(fragment: dict[str, Any]) -> str | None:
    """The field-row mode one property fragment renders, or ``None`` when
    the fragment is inexpressible: a pattern-narrowed string admits values
    no staging control can enumerate, so it derives no row and keeps the
    action off L2 (RC-L5-3/4, the closed intersection vocabulary). Mirrors
    the SDK expander's ``_row_mode`` (the L5 widening; REG-4)."""
    if fragment.get("const") is not None:
        return "const"
    if fragment.get("enum") is not None:
        return "enum"
    declared = fragment.get("type")
    if declared == "string":
        return None if "pattern" in fragment else "text"
    if declared == "boolean":
        return "boolean"
    if declared in _NUMERIC_TYPES:
        return "numeric"
    return None


def _field_rows(
    action_urn: str,
    prefix: str,
    schema: dict[str, Any],
    _seen: set[str] | None = None,
) -> list[dict[str, Any]]:
    """The renderable field rows (numeric bounds / const / enum / text /
    boolean) of one effective schema, descending array items and object
    properties. A pattern-narrowed string emits no row (inexpressible).

    Fully-qualified field names are REFUSED on collision (mirrored from
    the SDK expander): dotted flattening gives a nested ``a``→``b`` and
    a flat property literally named ``a.b`` the same name, and two rows
    under one name render two controls for one declared field. The
    collision refuses typed, naming the field. A declared value set
    under declared bounds narrows here (the W3 fold) — one mechanism
    for every path a fragment arrives by, at every depth this descent
    visits; the value types check first (the G4 fold)."""
    rows: list[dict[str, Any]] = []
    seen = _seen if _seen is not None else set()
    for name, sub in (schema.get("properties") or {}).items():
        full = f"{prefix}{name}"
        _check_value_types(action_urn, full, sub)
        _intersect_declared_values(action_urn, full, sub)
        mode = _row_mode(sub)
        if mode is not None:
            if full in seen:
                raise _refuse(
                    "classref_duplicate_field",
                    f"{action_urn} mints field {full!r} from two schema paths "
                    "(a nested object/array descent and a literal property "
                    "name collide after qualification)",
                )
            seen.add(full)
            row: dict[str, Any] = {"field": full, "mode": mode}
            if mode == "const":
                row["const"] = sub["const"]
            elif mode == "enum":
                row["enum"] = sub["enum"]
            elif mode == "text":
                for keyword in ("minLength", "maxLength"):
                    if keyword in sub:
                        row[keyword] = sub[keyword]
            elif mode == "numeric":
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
            rows.extend(_field_rows(action_urn, f"{full}.", sub, seen))
        if isinstance(sub.get("items"), dict) and isinstance(
            sub["items"].get("properties"), dict
        ):
            rows.extend(_field_rows(action_urn, f"{full}[].", sub["items"], seen))
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
    host supplies) decides: empty L1, all-required-expressible L2 (the L5
    widening: a field is expressible when the derivation renders it —
    numeric, text, enum, const or boolean; a pattern-narrowed string
    stays inexpressible), anything else L0."""
    if slot_kind == "configuration":
        return "L3"
    if slot_kind == "dataset":
        return "L4"
    required = [name for name in effective["required"] if name not in host_supplied]
    if not required:
        return "L1"
    schemas = effective["properties"]
    if all(_row_mode(schemas.get(name, {})) is not None for name in required):
        return "L2"
    return "L0"


def _catalogue_row(
    action_urn: str, catalog_actions: Mapping[str, Any]
) -> dict[str, Any] | None:
    """One action's served catalogue row, or ``None`` (the W4 fold,
    mirrored): a key ABSENT from the map is the residual mode — no
    served catalog describes the action. A key PRESENT with a
    non-object row is a malformed catalog entry and refuses typed:
    reading it as "no catalog" would mint a false ``custom`` provenance
    (and the pre-split code crashed on it with a bare AttributeError
    downstream)."""
    if action_urn not in catalog_actions:
        return None
    row = catalog_actions[action_urn]
    if not isinstance(row, dict):
        raise _refuse(
            "classref_catalog_row_invalid",
            f"the served catalog describes {action_urn} with a "
            f"{type(row).__name__} row, not an object",
        )
    return row


def _derive_controls(
    actions: Mapping[str, Any],
    catalog_actions: Mapping[str, Any],
    slot_for_urn: dict[str, tuple[str, dict[str, Any]]],
    page_for_slot: dict[str, str],
    intended_controls: dict[str, str],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    """Per-action ladder level + renderable fields + resolution (the SDK
    expander's ``_derive_controls`` shape, mirrored at the v0.21.0 pin).
    A catalogue row (served OTDP or pinned vendor) resolves layer 1; no
    row at all resolves layer 3 — the residual member derives from the
    descriptor's own constraints, never refuses for being unknown. The
    composed layer (a row the composed walk injected) resolves layer 2
    and names its class — the value names the layer that produced the
    row (provenance is data, not a log)."""
    plan: dict[str, dict[str, Any]] = {}
    divergences: list[dict[str, str]] = []
    for urn in sorted(actions):
        raw_constraints = actions[urn].get("input_constraints")
        constraints = raw_constraints or {}
        slot_kind = None
        host_supplied = frozenset(_HOST_SUPPLIED_UNIVERSAL)
        _slot_name, slot = slot_for_urn.get(urn, ("", {}))
        if slot:
            slot_kind = str(slot.get("kind"))
            if slot_kind != "vendor_actions":
                host_supplied = frozenset(slot.get("host_supplied") or ())
        catalogue_row = _catalogue_row(urn, catalog_actions)
        composed_of = (
            catalogue_row.get("composed_class")
            if catalogue_row is not None
            else None
        )
        composed_side_effect = (
            catalogue_row.get("side_effect")
            if catalogue_row is not None
            else None
        )
        if composed_of is not None:
            resolution = "composed"
        elif catalogue_row is not None:
            resolution = "catalog"
        else:
            resolution = "custom"
        effective = _effective_action_schema(urn, catalogue_row, constraints)
        level = _ladder_level(effective, host_supplied, slot_kind)
        # W7 (mirrored): "declares nothing" and "declares no inputs" are
        # different states. A residual action whose input_constraints
        # carries no properties key at all declared NOTHING — silence
        # must not become a one-click dispatch (an L1 button), so it
        # derives L0 with the marker naming the absence. An explicit
        # properties (even {}) declared no inputs, and the ladder reads
        # it as before.
        declared_no_input = not (
            isinstance(raw_constraints, dict) and "properties" in raw_constraints
        )
        if catalogue_row is None and declared_no_input:
            level = "L0"
        fields = _field_rows(urn, "", effective)
        slot_key = _slot_name if slot else ""
        page = page_for_slot.get(slot_key, "device-features")
        row: dict[str, Any] = {
            "level": level,
            "page": page,
            "fields": fields,
            "resolution": resolution,
        }
        if composed_of is not None:
            # The class's declared side_effect rides the plan row as
            # data, mirroring the SDK; the gateway's consumers of it are
            # SDK surfaces and are not mirrored (the gateway has no
            # authored deviation ledger to feed).
            row["class"] = composed_of
            row["side_effect"] = composed_side_effect
        if catalogue_row is None and declared_no_input:
            row["input_undeclared"] = True
        row["declared_deviation"] = (
            bool(intended_controls.get(urn) == "deviation")
            or level == "L0"
            or slot_kind == "configuration"
        )
        plan[urn] = row
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


def _channels_slots(merged: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every channels slot in merge order (#556 B3: the reference's own
    and every applied composed member's injection) — per-slot lane
    resolution keys on exactly this set."""
    return {
        key: slot
        for key, slot in merged["slots"].items()
        if slot.get("kind") == "channels"
    }


def _resolve_channels(
    descriptor: Mapping[str, Any], merged: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    """The lanes each channels slot resolves, keyed by slot in merge
    order; fail-closed count refusals per slot (record §3.3 — zero
    matching channels and over-ceiling counts refuse naming the slot's
    role, every channels slot alike: the reference's own and a composed
    member's injection are one rule)."""
    resolved: dict[str, list[dict[str, Any]]] = {}
    for key, slot in _channels_slots(merged).items():
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
        resolved[key] = list(lanes)
    return resolved


#: The ledger vocabulary each member kind lands under (#556 §3 rule 2):
#: one key per composed vocabulary, the design's own names. The gateway's
#: ledger-equivalent surface is ``DerivedAttachment.composed_members``,
#: read by the disclosure channel — the same four names, one tuple.
_MEMBER_VOCABULARY = {
    "procedure": "procedures",
    "configuration": "settings",
    "dataset": "datasets",
    "channels": "channels",
}
_MEMBER_LEDGER_VOCABULARIES = ("procedures", "settings", "datasets", "channels")


def _member_applies(member: Mapping[str, Any], descriptor: Mapping[str, Any]) -> bool:
    """(#556 §3 rule 1, the R1 rule verbatim) A member applies when the
    descriptor declares its claim: an action member (dataset,
    configuration, procedure) when any claimed URN names a declared
    action; the claim-less channels kind when any declared channel carries
    its ``where_role``."""
    if member.get("kind") == "channels":
        role = str(member.get("where_role", ""))
        return any(
            isinstance(row, dict) and str(row.get("role")) == role
            for row in descriptor.get("channels") or ()
        )
    declared = descriptor.get("actions") or {}
    return any(str(claim) in declared for claim in member.get("claims") or ())


def _applied_member_row(
    member: Mapping[str, Any], descriptor: Mapping[str, Any]
) -> dict[str, str]:
    """The ledger row one APPLIED member lands (#556 §4's per-vocabulary
    rows): channels carry ``where_role``; the claim-carrying kinds carry
    the action — the FIRST claim the descriptor declares, in document
    claim order. A dataset member's declared ``plot`` (B5, §4 V5) rides
    as ``plot_kind`` — the derived plot row is wire-shaped BY DESIGN
    (indistinguishable from a class plot), so the ledger row is the
    provenance surface for the vendor's choice."""
    row: dict[str, str] = {
        "slot": str(member.get("slot", "")),
        "page": str(member.get("page", "")),
    }
    if member.get("kind") == "channels":
        row["where_role"] = str(member.get("where_role", ""))
    else:
        declared = descriptor.get("actions") or {}
        row["action"] = next(
            str(claim) for claim in member.get("claims") or () if str(claim) in declared
        )
    if member.get("kind") == "dataset" and isinstance(member.get("plot"), dict):
        row["plot_kind"] = str(member["plot"].get("kind", ""))
    return row


def _member_nowhere_reason(member: Mapping[str, Any]) -> str:
    """Why one member applied nowhere (the B3 fold's F2): the claim half
    mirrors the composed-class row's own wording; the claim-less channels
    half names the role no declared channel carries."""
    if member.get("kind") == "channels":
        return (
            "no declared channel carries role "
            f"{str(member.get('where_role', ''))}"
        )
    return "its claims name no action this descriptor declares"


def _composed_member_inventory(
    declarations: tuple[ComposedMemberDeclaration, ...],
    descriptor: Mapping[str, Any],
) -> tuple[
    dict[str, tuple[dict[str, str], ...]],
    tuple[str, ...],
    tuple[tuple[str, str, str], ...],
]:
    """(#556 §3 rules 1-2) The composed-members inventory: the APPLIED set
    per vocabulary, the pins whose members apply nowhere, and — the B3
    fold's F2 — the dead MEMBERS inside pins that applied. Only the
    composed-member walk feeds this; the applied set records exactly what
    the derivation applied, so a pin whose members apply nowhere (a shape
    the schema sanctions) stays out of it BY DESIGN and rides back as its
    pin path for the disclosure channel — the R1 discipline, never
    drift."""
    rows: dict[str, list[dict[str, str]]] = {}
    unapplied: list[str] = []
    unapplied_members: list[tuple[str, str, str]] = []
    for declaration in declarations:
        applied_any = False
        for member in declaration.members:
            if not _member_applies(member, descriptor):
                unapplied_members.append(
                    (
                        declaration.pin_path,
                        str(member.get("slot", "")),
                        _member_nowhere_reason(member),
                    )
                )
                continue
            applied_any = True
            vocabulary = _MEMBER_VOCABULARY[str(member.get("kind", ""))]
            rows.setdefault(vocabulary, []).append(
                _applied_member_row(member, descriptor)
            )
        if not applied_any:
            unapplied.append(declaration.pin_path)
    frozen = {key: tuple(value) for key, value in rows.items()}
    return frozen, tuple(unapplied), tuple(unapplied_members)


def _check_member_reference_conflicts(
    merged: dict[str, Any],
    declarations: tuple[ComposedMemberDeclaration, ...],
) -> None:
    """(#556 §3 rule 4; README rules 1 and 3) The reference-side member
    conflicts, over the MERGED reference (final page ids and slot keys —
    later profiles' ids carry their slug): a member slot key a reference
    slot already holds, a claim a reference slot already binds, and a
    ``page`` naming no page the composed reference declares all refuse
    ``classref_composed_slot_conflict`` — the composed slot composes
    BESIDE the reference, never over it.

    (#556 B5 refute fold F3, 2026-10-26) A member plot of a
    DATASET-BINDING kind naming a readings page is a malformed placement,
    not a capacity limit: readings pages admit observation bindings alone,
    so the plot's dataset binding can never sit on the page and the
    emission would mint a plot the host refuses untyped. It refuses here,
    the ``plot.over_slot`` mismatch's sibling under the placement
    family's code; ``time_series`` — the one kind a readings page hosts,
    binding the page's first observation — composes."""
    pages = {str(page.get("id")) for page in merged["pages"]}
    page_kind_of = {
        str(page.get("id")): str(page.get("kind", "readings"))
        for page in merged["pages"]
    }
    for declaration in declarations:
        for member in declaration.members:
            slot = str(member.get("slot", ""))
            if slot in merged["slots"]:
                raise _refuse(
                    "classref_composed_slot_conflict",
                    f"member slot {slot} is already a slot of the composed "
                    "reference",
                )
            page = str(member.get("page", ""))
            if page not in pages:
                raise _refuse(
                    "classref_composed_slot_conflict",
                    f"member {slot} names page {page}, which the composed "
                    "reference does not declare",
                )
            plot = member.get("plot")
            if (
                isinstance(plot, dict)
                and str(plot.get("kind", "")) in ("waveform", "digital_lanes")
                and page_kind_of.get(page) == "readings"
            ):
                raise _refuse(
                    "classref_composed_plot_page_mismatch",
                    f"member {slot} carries plot kind {plot.get('kind')!r}, "
                    f"which readings page {page} cannot host (readings "
                    "pages admit observation bindings alone, so only a "
                    "time_series plot — binding an observation — composes "
                    "there)",
                )
            for claim in member.get("claims") or ():
                claim = str(claim)
                for key, ref_slot in merged["slots"].items():
                    if str(ref_slot.get("action", "")) == claim:
                        raise _refuse(
                            "classref_composed_slot_conflict",
                            f"member {slot} claims {claim}, which reference "
                            f"slot {key} already binds",
                        )


def _inject_composed_members(
    descriptor: Mapping[str, Any],
    merged: dict[str, Any],
    declarations: tuple[ComposedMemberDeclaration, ...],
) -> None:
    """(#556 §3) The injection seam: every APPLIED composed member's slot
    joins the merged reference, after ``_merge_references`` and after the
    conflict checks, so the existing derivation arms run unchanged on the
    injected rows — the channels kind (V3 layer 2, per-slot lane
    resolution consumes it), the procedure and configuration kinds
    (V1/V6 layer 2, the loops consume them; the claimed URN is the first
    claim the descriptor declares), and the dataset kind (V4 layer 2; a
    member's ``plot`` whose named page hosts no template plot joins that
    page's template so the existing plot emission derives it, V5 layer
    2). A member that applies nowhere injects nothing — its disclosure
    is the applied-nowhere row. An APPLIED action-kind member composes a
    target naming the declaration's vendor profile row (the seam); a
    declaration with no row is malformed for the surface it requests —
    a cross-array conditional the dialect schema cannot express, refused
    under the declaration's own invalidity code."""
    declared_actions = descriptor.get("actions") or {}
    for declaration in declarations:
        for member in declaration.members:
            kind = member.get("kind")
            if kind not in ("channels", "procedure", "configuration", "dataset"):
                continue
            if not _member_applies(member, descriptor):
                continue
            slot_key = str(member.get("slot", ""))
            if kind != "channels" and declaration.profile is None:
                raise _refuse(
                    "classref_invalid_member_declaration",
                    f"pinned document {declaration.pin_path}: member "
                    f"{slot_key} (kind {kind}) composes a target naming "
                    "the declaration's vendor profile row, which the "
                    "document does not carry",
                )
            if kind == "channels":
                merged["slots"][slot_key] = {
                    "kind": "channels",
                    "where_role": str(member.get("where_role", "")),
                    "key": "id",
                    "label": "label",
                }
            else:
                slot_row: dict[str, Any] = {
                    "kind": str(kind),
                    "action": next(
                        str(claim)
                        for claim in member.get("claims") or ()
                        if str(claim) in declared_actions
                    ),
                }
                if member.get("when_declared") is not None:
                    slot_row["when_declared"] = member["when_declared"]
                if member.get("host_supplied"):
                    slot_row["host_supplied"] = list(member["host_supplied"])
                if member.get("schema_source") is not None:
                    slot_row["schema_source"] = member["schema_source"]
                merged["slots"][slot_key] = slot_row
            page_id = str(member.get("page", ""))
            for page in merged["pages"]:
                if str(page.get("id")) == page_id:
                    page.setdefault("_slot_keys", []).append(slot_key)
                    page.setdefault("bindings", []).append(slot_key)
                    # (#556 §4 V5, B5) The member's ``plot`` choice joins
                    # the page template when the page hosts no plot of its
                    # own and its kind admits one — the existing emission
                    # derives it from the template. The internal marker
                    # distinguishes an INJECTED member plot from a class
                    # template plot downstream (the placement rows key on
                    # the CLASS template alone).
                    if (
                        kind == "dataset"
                        and isinstance(member.get("plot"), dict)
                        and page.get("plot") is None
                        and str(page.get("kind", "readings"))
                        in ("dataset", "readings")
                    ):
                        page["plot"] = dict(member["plot"])
                        page["_member_plot_of"] = slot_key
                    break


def _resolve_parameters(
    descriptor: Mapping[str, Any], lanes: list[dict[str, Any]]
) -> dict[tuple[str, str], dict[str, Any]]:
    """The descriptor parameters the channels bind to their declared
    quantities: ``parameter_names`` positionally over ``quantities`` (the
    descriptor's own channel-level mapping), mirrored from the SDK
    expander at the v0.18.0 pin — a readings page that owes a tile per
    scalar variable and meets a quantity with no named readable parameter
    refuses typed (``classref_parameter_map``): the tile's data path is
    structure the derivation cannot invent.

    The gateway's one deliberate divergence from the SDK arm: a descriptor
    that declares NO readable parameter at all derives WITHOUT the
    readings expansion (no tiles, no observation bindings, the plot over
    the dataset binding) instead of refusing — the committed OTDP class
    examples ship exactly that shape (parameters empty), and their
    derivability is pinned by the committed-pair suites; the SDK meets
    the same descriptor at authoring time, where the refusal is the
    honest gate. Every descriptor with at least one readable parameter
    resolves exactly as the SDK does, refusals included (the f6-smu
    parity fixture pins the agreement byte for byte)."""
    parameters = {
        str(row.get("name")): row
        for row in descriptor.get("parameters", [])
        if row.get("access") in ("ro", "rw")
    }
    if not parameters:
        return {}
    mapping: dict[tuple[str, str], dict[str, Any]] = {}
    for channel in lanes:
        names = [str(name) for name in channel.get("parameter_names") or []]
        for index, quantity in enumerate(channel.get("quantities") or []):
            if index >= len(names):
                raise _refuse(
                    "classref_parameter_map",
                    f"channel {channel.get('id')!r} declares quantity "
                    f"{quantity!r} with no named parameter (parameter_names "
                    "covers quantities positionally)",
                )
            row = parameters.get(names[index])
            if row is None:
                raise _refuse(
                    "classref_parameter_map",
                    f"channel {channel.get('id')!r} quantity {quantity!r} "
                    f"names {names[index]!r}, which is no declared readable "
                    "parameter",
                )
            mapping[(str(channel.get("id")), str(quantity))] = row
    return mapping


# --- the layout block (parent record §2.6, mirrored) ---------------------------


def _urn_for_binding(
    plan: Mapping[str, Mapping[str, Any]],
    binding_id: str,
    slot_urns: Mapping[str, str] | None = None,
) -> str | None:
    """The action a binding id names. The class convention is binding id ==
    action slug; a placed slot key (#556 B4) may name its slot anything the
    schema admits, so the page-placed slot map wins when carried — the map
    a caller passes covers exactly the slot keys placed on the page under
    construction (the B4 fold's F1: a slot key placed elsewhere must not
    capture a binding id that only shares its spelling) — and the slug scan
    stays the founding fallback for binding ids no placed slot holds (the
    authored sections' conventions). Derivation-MINTED buttons never come
    here: the mint site knows its own URN and records it (see
    ``_insert_ladder_numerics``)."""
    if slot_urns is not None and binding_id in slot_urns:
        return slot_urns[binding_id]
    for urn in plan:
        if urn.split("/")[0].rsplit(".", 1)[-1] == binding_id:
            return urn
    return None


def _numeric_nodes(
    binding_id: str, fields: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The numeric-only staging nodes (the preset-mediated L3 arm; the L5
    widening leaves this arm un-widened — its shape is pinned)."""
    return [
        {"binding_id": binding_id, "kind": "numeric", "field": field["field"]}
        for field in fields
        if field["mode"] == "numeric"
    ]


def _staging_nodes(
    binding_id: str, fields: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Per-mode staging nodes (the L5 widening, mirrored from the SDK
    expander's ``_staging_nodes``): numeric→numeric, text→text,
    enum/const→select, boolean→boolean. Inexpressible fields emit no node
    (they derived no row)."""
    out: list[dict[str, Any]] = []
    for field in fields:
        kind = _MODE_KIND.get(field["mode"])
        if kind is not None:
            out.append(
                {"binding_id": binding_id, "kind": kind, "field": field["field"]}
            )
    return out


def _insert_ladder_numerics(
    sections: list[dict[str, Any]],
    plan: Mapping[str, Mapping[str, Any]],
    slot_urns: Mapping[str, str] | None = None,
    minted: Mapping[str, str] | None = None,
) -> None:
    """Authored button nodes for an L2 action gain the action's numeric
    field nodes immediately before the button (the staging-pair order).

    W8 (issue #556 Track A; the SDK expander's fold, mirrored): a
    numeric node the section already carries — a derived page's staging
    emission, or a layout that authored its own numerics — is not
    re-emitted: one field, one control (the pair used to render twice on
    every derived page, catalogued pairs included).

    #556 B4 fold F1: ``minted`` carries the binding ids the DERIVATION
    minted on this page mapped to the URN each was minted for —
    resolution consults it first, so a slug-minted button keeps its own
    action even when its slug spells a slot key placed on another page
    (the slot map would otherwise weld the slot action's numerics onto
    the vendor button). Authored nodes — no mint record — resolve
    through the page-placed slot map and the founding slug scan as
    before."""
    for section in sections:
        children = section.get("children", [])
        present = {
            (str(node.get("binding_id")), node.get("field"))
            for node in children
            if node.get("kind") == "numeric"
        }
        out: list[dict[str, Any]] = []
        for node in children:
            if node.get("kind") == "button" and isinstance(node.get("binding_id"), str):
                binding_id = str(node["binding_id"])
                urn = (
                    minted.get(binding_id)
                    if minted is not None and binding_id in minted
                    else _urn_for_binding(plan, binding_id, slot_urns)
                )
                row = plan.get(urn or "", {}) if urn else {}
                for field_row in row.get("fields", []):
                    if field_row["mode"] != "numeric":
                        continue
                    key = (str(node["binding_id"]), field_row["field"])
                    if key in present:
                        continue
                    present.add(key)
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
    minted: dict[str, str] | None = None,
) -> None:
    """A when-declared action that derives onto this page owes its button
    node too, or the census and the coverage arm both miss it (the SDK
    expander's ``_complete_authored_buttons`` shape).

    The scoping rules (the W1 fold, mirrored): a residual member never
    welds into the reference's authored sections (an authored page
    stands as authored — parent record §11 risk 4; the member surfaces
    through the plan and the disclosure channel), and the append
    targets the page's MAIN derived section when one exists — the last
    section may be the custom one, and a catalogued action's button
    must never land there.

    #556 B4 fold F1: the completion minted this button FOR this urn;
    record it so the ladder-numeric insert resolves the button by its
    own action, never by whatever a slot key sharing the slug's
    spelling resolves to."""
    if not sections:
        return
    present: set[str] = set()
    for section in sections:
        for node in section.get("children", []):
            if node.get("kind") == "button":
                present.add(str(node.get("binding_id", "")))
    target = next(
        (
            section
            for section in sections
            if section.get("id") == f"{page_id}-section"
        ),
        sections[-1],
    )
    for urn, row in sorted(plan.items()):
        if str(row.get("page", "")) != page_id:
            continue
        if row.get("level") not in ("L1", "L2"):
            continue
        if row.get("resolution") == "custom":
            continue
        slug = urn.split("/")[0].rsplit(".", 1)[-1]
        if slug in present:
            continue
        target.setdefault("children", []).append(
            {"binding_id": slug, "kind": "button"}
        )
        if minted is not None:
            minted[slug] = urn


def _build_layout(
    corpus: Path,
    pages: list[dict[str, Any]],
    plots: list[dict[str, Any]],
    authored: list[dict[str, Any]],
    plan: Mapping[str, Mapping[str, Any]],
    *,
    templates: Mapping[str, dict[str, Any]] | None = None,
    slot_urns: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """The namespaced layout block: authored sections where the reference
    carries them, derived single-section pages otherwise. Staging nodes
    derive from the ladder plan per mode (the L5 widening: an L2 action
    renders its text/select/boolean/numeric fields through
    ``_staging_nodes``; L3 stays numeric-only beside the preset surface);
    the expander's own emission satisfies the family schema — a violation
    refuses loudly (never a block that fails its own authority).

    #556 B4 fold F1 (mirrored): the slot map this page's nodes resolve
    through covers exactly the slot keys PLACED on this page, and every
    derivation-minted button records its own urn — a placed slot key must
    not capture a binding id that only shares its spelling (an unclaimed
    vendor action slugged ``capture`` beside a reference ``capture`` slot
    on another page keeps its own numeric staging)."""
    by_page = {str(row.get("page_id")): row for row in authored}
    block_pages: list[dict[str, Any]] = []
    plot_done = False
    for page in pages:
        page_id = str(page["id"])
        # The placed-slot map for THIS page alone: a slot key placed
        # elsewhere must not capture a binding id here.
        page_slots: dict[str, str] = {}
        if slot_urns:
            for row in page.get("bindings", []):
                key = str(row if isinstance(row, str) else row.get("id"))
                if key in slot_urns:
                    page_slots[key] = slot_urns[key]
        minted: dict[str, str] = {}
        authored_page = by_page.get(page_id)
        if authored_page is not None:
            # The reading-tile expansion consumes authored reading-tile
            # children (they become the page's observation tiles — see
            # _assemble_documents); a section left empty by the expansion
            # drops with them. data-table children render as always.
            sections = []
            for section in authored_page.get("sections", []):
                kept = [
                    child
                    for child in section.get("children", [])
                    if child.get("kind") != "reading-tile"
                ]
                if kept:
                    sections.append({**section, "children": kept})
        else:
            children: list[dict[str, Any]] = []
            custom_children: list[dict[str, Any]] = []
            if page.get("plots") and not plot_done and plots:
                children.append({"plot_index": 0})
                plot_done = True
            for row in page.get("bindings", []):
                binding_id = str(row if isinstance(row, str) else row.get("id"))
                urn = _urn_for_binding(plan, binding_id, page_slots)
                level = plan.get(urn, {}).get("level") if urn else None
                if level == "L2" and urn is not None:
                    children.extend(_staging_nodes(binding_id, plan[urn]["fields"]))
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
            # derive their controls on their plan page. A residual
            # member's controls derive into the page's CUSTOM section —
            # the visible label for uncatalogued actions, minted the way
            # the derivation mints every other derived id. Catalogued
            # vendor actions keep the main section, so resolution
            # partitions the two, never mixes them.
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
                    target = (
                        custom_children
                        if plan_row.get("resolution") == "custom"
                        else children
                    )
                    if plan_row["level"] == "L3":
                        # L3 is preset-mediated; its numeric admittance
                        # renders beside the preset surface and data-table
                        # (the pinned family shape — no per-mode widening
                        # on this arm).
                        target.extend(_numeric_nodes(slug, plan_row["fields"]))
                    else:
                        target.extend(_staging_nodes(slug, plan_row["fields"]))
                    if plan_row["level"] in ("L1", "L2"):
                        target.append({"binding_id": slug, "kind": "button"})
                        # (#556 B4 fold F1) The unclaimed-slug mint records
                        # its own urn — the insert must never re-resolve the
                        # slug through a slot key placed on any page.
                        minted[slug] = urn
            sections = []
            if children:
                sections.append(
                    {
                        "id": f"{page_id}-section",
                        "title": str(page.get("title", page_id)),
                        "surface": "raised",
                        "span": 12,
                        "children": children,
                    }
                )
            if custom_children:
                # The custom section exists exactly when residual members
                # rendered on this page. It never appends into an authored
                # page: this whole branch is the no-authored-layout path
                # (parent record §11 risk 4 — an authored device-features
                # layout stands as authored, and the residual member
                # surfaces through the plan and the disclosure channel
                # instead).
                sections.append(
                    {
                        "id": f"{page_id}-custom",
                        "title": "Custom device actions",
                        "surface": "raised",
                        "span": 12,
                        "children": custom_children,
                    }
                )
        _complete_authored_buttons(sections, plan, page_id, minted)
        # W1 (issue #556 Track A; the SDK expander's fold, mirrored):
        # completion runs BEFORE the ladder-numeric insert — a button the
        # completion pass appends must arrive in time for the insert to
        # give it its numeric staging pair.
        _insert_ladder_numerics(sections, plan, page_slots, minted)
        if not sections:
            # The empty-page fallback (issue #556, the B7 refute fold F2;
            # the SDK expander's own emission since the 0.3.0 widening,
            # mirrored verbatim): every declared page renders as a panel
            # (the expect row's meaning) — a page whose surface is fully
            # placed, or whose actions surface as disclosures elsewhere,
            # derives the honest text body, never a page without its
            # panel. Before this mirror the gateway OMITTED such a page;
            # the dmm tag pins the emitted bytes.
            template = (templates or {}).get(page_id, {})
            sections = [
                {
                    "id": f"{page_id}-section",
                    "title": str(page.get("title", page_id)),
                    "surface": "raised",
                    "span": 12,
                    "children": [
                        {
                            "body": (
                                "No additional device features."
                                if template.get("vendor_features")
                                else "No additional surfaces for this page."
                            )
                        }
                    ],
                }
            ]
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
    #: The per-action resolution surface (issue #556 Track A, design
    #: §3.4): one ``(urn, resolution, class_urn | None)`` row per
    #: declared action, sorted by urn — ``resolution`` is one of
    #: ``catalog``/``composed``/``custom`` naming the layer that
    #: produced the row, and ``class_urn`` names the composed class
    #: when the row resolved layer 2 (provenance is data, not a log;
    #: the SDK's plan rows carry the same fields).
    resolutions: tuple[tuple[str, str, str | None], ...] = ()
    #: Pins whose documents matched neither shape discriminator
    #: (digest-verified, contributed nothing) — disclosed, never silently
    #: dropped (the SDK's B7 row).
    ignored_pins: tuple[str, ...] = ()
    #: Pin-declared composed classes that applied nowhere (their claims
    #: name no action this descriptor declares), as (class urn, pin
    #: path) pairs keyed to the APPLIED rule — a sanctioned
    #: claims-nowhere class discloses, never drifts.
    unapplied_classes: tuple[tuple[str, str], ...] = ()
    #: Pins whose vendor-catalog documents declare an empty actions map
    #: — shape-valid, contributed nothing, disclosed beside the unapplied
    #: classes.
    empty_action_pins: tuple[str, ...] = ()
    #: The walk's accepted composed-member declarations (issue #556 Track
    #: B, record §3) — schema-validated, conflict-free, carried for the
    #: injection seam and the disclosure channel.
    member_declarations: tuple[ComposedMemberDeclaration, ...] = ()
    #: The APPLIED composed-member set per vocabulary (#556 §3 rule 2) —
    #: the ledger-equivalent surface the disclosure channel reads (the
    #: SDK writes the same four-key map into ui/class-reference.json).
    composed_members: Mapping[str, tuple[dict[str, str], ...]] = (
        dataclass_field(default_factory=dict)
    )
    #: Pins whose members applied nowhere, and the dead members inside
    #: pins that applied (the B3 fold's F2) — the disclosure channel's
    #: applied-nowhere rows.
    unapplied_member_pins: tuple[str, ...] = ()
    unapplied_members: tuple[tuple[str, str, str], ...] = ()
    #: Every declared member's residual row — ``(kind, member, detail)``
    #: rendered as the SDK gate's ``{kind} {member}: {detail}`` REPORTED
    #: wording on the disclosure channel (#556 §3 rule 3: a declared
    #: member lands a derived surface or a row here, never silence).
    residual_rows: tuple[tuple[str, str, str], ...] = ()


@dataclass(frozen=True)
class ComposedClass:
    """One pinned, digest-verified composed action-class declaration
    (issue #556 Track A, design §3.2): the document that supplies the
    catalogue side of the derivation for the URNs it claims. Mirrors the
    SDK dataclass at the v0.21.0 pin."""

    urn: str
    side_effect: str
    input_schema: dict[str, Any]
    claims: tuple[str, ...]
    pin_path: str


@dataclass(frozen=True)
class ComposedMemberDeclaration:
    """One pinned, digest-verified composed-member declaration (issue
    #556 Track B, record §3): the vendor-authored document that supplies
    the reference side — one slot per member, its page placement,
    optionally one vendor profile row — the served corpus does not carry.
    Mirrors the SDK dataclass at the composed-member tips.

    ``profile`` is the declaration's one vendor profile row (the
    device-profile-catalog row shape, carried under the plural
    ``profiles`` key the canonical validator's map reads) or ``None``;
    ``members`` are the raw schema-validated member rows; ``pin_path``
    names the pinned file."""

    profile: dict[str, Any] | None
    members: tuple[dict[str, Any], ...]
    pin_path: str


def _validate_composed_class(
    document: Any, pin_path: Any, *, corpus: Path
) -> dict[str, Any]:
    """One pinned document against the digest-verified corpus composed
    schema (the mirror of the SDK's ``_validate_composed_class``): the
    claims items $ref resolves through the family's reference schema, so
    both documents ride one registry — the same cross-file $ref style
    ``validate_reference_document`` uses for the layout schema."""
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    family = _family_documents(corpus)
    registry = Registry().with_resource(
        str(family["reference_schema"].get("$id")),
        Resource.from_contents(family["reference_schema"]),
    )
    findings = sorted(
        Draft202012Validator(
            family["composed_schema"], registry=registry
        ).iter_errors(document),
        key=lambda error: list(error.path),
    )
    if findings:
        first = findings[0]
        where = "/".join(str(part) for part in first.path) or "(root)"
        raise _refuse(
            "classref_invalid_composed_class",
            f"pinned document {pin_path}: {where}: {first.message}",
        )
    return document  # type: ignore[no-any-return]


def _validate_member_declaration(
    document: Any, pin_path: Any, *, corpus: Path
) -> dict[str, Any]:
    """One pinned document against the corpus's served member-declaration
    schema (the mirror of the SDK's ``_validate_member_declaration``;
    every closed set in that schema is an owner's own — the reference
    schema's slot vocabulary, the page id shape, the plot block verbatim,
    the profile-catalog row shape). The schema joins the family at 0.5.0;
    on a corpus whose active family serves none, a member pin is a
    PLATFORM FAULT that refuses loudly here — the SDK's lazy-loader rule
    in the gateway's typed face — never a silently-empty read and never
    the ignored-pin disclosure."""
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    family = _family_documents(corpus)
    schema = family["member_schema"]
    if not isinstance(schema, dict):
        raise _refuse(
            "classref_invalid_member_declaration",
            f"pinned document {pin_path}: the active family "
            f"{family['version']} serves no composed-member-declaration "
            "schema (the member vocabulary joins the family at 0.5.0) — "
            "a platform fault, never a silent read",
        )
    registry = Registry().with_resource(
        str(family["reference_schema"].get("$id")),
        Resource.from_contents(family["reference_schema"]),
    )
    findings = sorted(
        Draft202012Validator(schema, registry=registry).iter_errors(document),
        key=lambda error: list(error.path),
    )
    if findings:
        first = findings[0]
        where = "/".join(str(part) for part in first.path) or "(root)"
        raise _refuse(
            "classref_invalid_member_declaration",
            f"pinned document {pin_path}: {where}: {first.message}",
        )
    return document  # type: ignore[no-any-return]


def _pin_shape_groups(document: dict[str, Any]) -> list[str]:
    """The pin-shape key sets a document carries (#556 Track B, the B4
    fold's F4): the member keys, the composed-class keys and the catalog
    keys are three disjoint vocabularies, and the groups a document
    carries decide what the walk does with it — one group is that shape,
    more than one refuses as ambiguous, none is IGNORED (disclosed,
    contributing nothing). ONE definition serves the walk's
    discrimination AND the presentation-side pin reader's filter, so the
    derive and the canonical validation agree on which documents are
    accepted by construction — a second copy of the key sets is how the
    two halves would drift."""
    shape_groups: list[str] = []
    if "members" in document:
        shape_groups.append("members")
    if "urn" in document or "claims" in document:
        shape_groups.append("composed-class")
    if "actions" in document:
        shape_groups.append("actions")
    return shape_groups


def _vendor_catalog_documents(
    descriptor: Mapping[str, Any],
    vendor_catalogs: Mapping[str, bytes] | None,
    served_actions: Mapping[str, Any],
    corpus: Path,
) -> tuple[
    dict[str, Any],
    dict[str, ComposedClass],
    tuple[str, ...],
    tuple[tuple[str, str], ...],
    tuple[str, ...],
    tuple[ComposedMemberDeclaration, ...],
]:
    """Action rows, composed classes, member declarations, ignored pins,
    unapplied classes and empty-catalog pins from the descriptor's pinned
    documents — the mirror of the SDK expander's ``_vendor_documents``
    walk (issue #556 Track A design §3.2; Track B record §3 for the
    member half), resolved from ADMISSION bytes (the composition supplies
    them from the content store by digest — the gateway has no plugin
    package dir; the SDK resolves descriptor-relative files, the
    admission store is the gateway's equivalent).

    The walk discriminates by shape through ONE definition
    (``_pin_shape_groups``): the member keys, the composed-class keys and
    the catalog keys are three disjoint vocabularies, and a document
    carrying keys from more than one refuses as an AMBIGUOUS pin naming
    the carried shape groups and keys (the R2 question generalized — a
    key set is not a shape claim); a document carrying exactly the
    class shape (``urn`` AND ``claims``) is a composed action class,
    validated against the corpus composed schema; a document carrying
    the member shape (``members``) is a composed-member declaration,
    validated against the corpus member schema with the over-slot
    self-reference refusal (``classref_composed_plot_slot_mismatch``);
    a document carrying none of the three is IGNORED (disclosed, never
    silently dropped); a vendor catalog whose ``actions`` map is empty
    contributed nothing (disclosed); a vendor-catalog action row
    carrying a stray ``composed_class`` key is stripped — composed
    provenance has exactly one writer, this walk. Every ACCEPTED
    document rides the shared ``pinned_id_shadow`` guard
    (``merge_pinned_documents`` over exactly the accepted set) so the
    derive and the canonical validation refuse the same shape under the
    same code — the B4 fold's F3, one shared enforcement point.

    Integrity arms fire before any discrimination (a pinned file's bytes
    are verified whatever shape they turn out to carry) and keep the
    refusal split's codes: a pin the admission store cannot serve
    refuses ``classref_vendor_catalog_unreadable`` — the ONE deliberate
    code-vocabulary divergence of detail, disclosed here as the
    ``_resolve_parameters`` divergence is disclosed beside its own
    mechanism — and digest-divergent or non-object pins keep their own
    codes (the digest detail names the pin neutrally: the walk verifies
    member declarations and vendor catalogs through one seam, and a
    members document is not a vendor catalog — the code keeps its
    historical name, the prose does not).

    Conflicts refuse, never merge: a claim against a served or pinned
    catalogue row, a claim another class already holds, a second
    document carrying one class urn (all ``classref_composed_claim_conflict``,
    naming WHICH side the claim collided with), a class
    ``side_effect`` of ``none`` under a descriptor action declaring
    ``state_change`` (``classref_composed_side_effect_under`` — the S20
    direction at the class layer; over-classification stays legal), and
    the member family under ``classref_composed_slot_conflict`` — a slot
    key two members declare (whatever pin each rode, with the
    same-document form naming the document once), a claim held by
    another member, and a claim a composed action class holds (the
    class owns the catalogue side, the member the placement; one claim,
    one owner).

    Survivors' claimed URNs join the catalogue side as
    ``{input_schema, side_effect, composed_class}`` — including claims
    the descriptor does not declare (DS3: a named reference slot may
    bind a composed-claimed URN; the slot check runs against the merged
    map, exactly the SDK's order). D13 narrowing runs on them
    unchanged. A class none of whose claims the descriptor declares
    applied NOWHERE — it rides back as (class urn, pin path) pairs in
    ``unapplied`` for the disclosure channel (the applied rule, not the
    pin-declared rule)."""
    from benchweave.presentation.contracts import DocumentError, merge_pinned_documents

    actions: dict[str, Any] = {}
    classes: dict[str, ComposedClass] = {}
    ignored: list[str] = []
    empty_pins: list[str] = []
    member_declarations: list[ComposedMemberDeclaration] = []
    pinned_sources: dict[str, str] = {}
    accepted_documents: dict[str, dict[str, Any]] = {}
    for row in descriptor.get("contracts", []):
        identifier = str(row.get("id", ""))
        if identifier.startswith("urn:otdp:"):
            continue
        pin = str(row.get("sha256", ""))
        raw = (vendor_catalogs or {}).get(pin)
        if raw is None:
            raise _refuse(
                "classref_vendor_catalog_unreadable",
                f"pinned vendor catalog {row.get('path')} is not admitted "
                f"(digest {pin})",
            )
        if hashlib.sha256(raw).hexdigest() != pin:
            raise _refuse(
                "classref_vendor_catalog_digest_mismatch",
                f"pinned document {row.get('path')} digest mismatch",
            )
        document = json.loads(raw)
        if not isinstance(document, dict):
            # The SDK's B7 row: a non-object pin refuses typed — the
            # pre-split walk crashed on a bare AttributeError, which is
            # not a typed refusal face.
            raise _refuse(
                "classref_vendor_catalog_invalid",
                f"pinned vendor catalog {row.get('path')} is not a JSON object",
            )
        # R2 generalized (#556 §3): the ambiguity question is KEY-SET
        # overlap, decided by the one shared definition.
        shape_groups = _pin_shape_groups(document)
        if len(shape_groups) > 1:
            carried = sorted(
                key for key in ("members", "urn", "claims", "actions") if key in document
            )
            raise _refuse(
                "classref_invalid_composed_class",
                f"pinned document {row.get('path')} carries keys of more "
                f"than one pin shape ({', '.join(shape_groups)}: "
                f"{', '.join(carried)}) — an ambiguous pin",
            )
        if shape_groups:
            accepted_documents[str(row.get("path", ""))] = document
        if "members" in document:
            _validate_member_declaration(document, row.get("path"), corpus=corpus)
            # The self-reference rule (README rule 2): ``plot.over_slot``
            # names the member's own slot or the document contradicts
            # itself — refused here, before any member can inject.
            for member in document["members"]:
                slot = str(member.get("slot", ""))
                plot = member.get("plot")
                if (
                    isinstance(plot, dict)
                    and str(plot.get("over_slot", "")) != slot
                ):
                    raise _refuse(
                        "classref_composed_plot_slot_mismatch",
                        f"member {slot} carries plot.over_slot "
                        f"{plot.get('over_slot')!r}, which is not the "
                        "member's own slot (a document referring to itself "
                        "inconsistently)",
                    )
            member_declarations.append(
                ComposedMemberDeclaration(
                    profile=(
                        document["profiles"][0]
                        if isinstance(document.get("profiles"), list)
                        and document["profiles"]
                        else None
                    ),
                    members=tuple(document["members"]),
                    pin_path=str(row.get("path", "")),
                )
            )
            continue
        composed_keys = "urn" in document and "claims" in document
        if composed_keys:
            _validate_composed_class(document, row.get("path"), corpus=corpus)
            cls = ComposedClass(
                urn=str(document["urn"]),
                side_effect=str(document["side_effect"]),
                input_schema=document["input_schema"],
                claims=tuple(str(claim) for claim in document["claims"]),
                pin_path=str(row.get("path", "")),
            )
            existing = classes.get(cls.urn)
            if existing is not None:
                raise _refuse(
                    "classref_composed_claim_conflict",
                    f"class urn {cls.urn} is declared by two pinned "
                    f"documents ({existing.pin_path} and {cls.pin_path})",
                )
            classes[cls.urn] = cls
        else:
            if "actions" not in document:
                # Neither shape discriminator: digest-verified, then
                # dropped — returned in ``ignored`` so the derivation
                # can disclose it (never silently).
                ignored.append(str(row.get("path", "")))
                continue
            if not isinstance(document["actions"], dict):
                # The SDK's R4 row: a digest-valid object whose
                # ``actions`` map is not an object refuses typed.
                raise _refuse(
                    "classref_vendor_catalog_invalid",
                    f"pinned vendor catalog {row.get('path')} 'actions' is "
                    "not a JSON object (got "
                    f"{type(document['actions']).__name__})",
                )
            if not document["actions"]:
                # The R5 row: a shape-valid catalog that declares NO
                # actions contributed nothing — disclosed, never blamed
                # on the descriptor alone.
                empty_pins.append(str(row.get("path", "")))
                continue
            for action_urn, action_row in document["actions"].items():
                if isinstance(action_row, dict) and "composed_class" in action_row:
                    # N2: composed provenance is written only by the
                    # composed walk above — a vendor-catalog row carrying
                    # a stray ``composed_class`` key is not composed and
                    # must not launder the label.
                    action_row = {
                        key: value
                        for key, value in action_row.items()
                        if key != "composed_class"
                    }
                actions[action_urn] = action_row
                pinned_sources[action_urn] = str(row.get("path", ""))
    # The walk-side half of the shared ``pinned_id_shadow`` guard (the B4
    # fold's F3): check-ui's merge has refused colliding embedded $ids
    # since #446 slice 2, but the derive keyed actions by URN and never
    # read $ids — two pinned catalogs sharing an input-schema $id derived
    # green and the author learned only at validation. The SAME guard
    # runs here, over exactly the accepted set, so both surfaces refuse
    # the same shape under the same code (the guard's own code, not a
    # ``classref_*`` name — one shared enforcement point by construction).
    try:
        merge_pinned_documents({}, accepted_documents)
    except DocumentError as exc:
        raise ClassRefusal(f"pinned_id_shadow: {exc}") from exc
    descriptor_actions = descriptor.get("actions") or {}
    claimant: dict[str, str] = {}
    for cls_urn in sorted(classes):
        cls = classes[cls_urn]
        for claim in cls.claims:
            if claim in served_actions:
                raise _refuse(
                    "classref_composed_claim_conflict",
                    f"class {cls_urn} claims {claim}, which the served "
                    "OTDP catalog describes",
                )
            if claim in actions:
                raise _refuse(
                    "classref_composed_claim_conflict",
                    f"class {cls_urn} claims {claim}, which pinned "
                    f"document {pinned_sources.get(claim, 'unknown')} "
                    "describes",
                )
            holder = claimant.get(claim)
            if holder is not None:
                raise _refuse(
                    "classref_composed_claim_conflict",
                    f"{claim} is claimed by both class {holder} and class "
                    f"{cls_urn}",
                )
            claimant[claim] = cls_urn
    for cls_urn in sorted(classes):
        cls = classes[cls_urn]
        for claim in sorted(cls.claims):
            declared = descriptor_actions.get(claim)
            if (
                isinstance(declared, dict)
                and declared.get("side_effect") == "state_change"
                and cls.side_effect == "none"
            ):
                raise _refuse(
                    "classref_composed_side_effect_under",
                    f"class {cls_urn} declares side_effect 'none' for "
                    f"{claim}, whose descriptor action declares "
                    "'state_change' (the S20 direction at the class layer: "
                    "over-classification is legal, under-classification "
                    "refuses)",
                )
    # Claimed URNs join the catalogue side of the derivation (D13 runs
    # unchanged on them), marked so the plan row can name the layer and
    # the class. A claim the descriptor does not declare simply does not
    # apply (a corpus-promoted class legitimately claims URNs across many
    # plugins).
    for cls_urn in sorted(classes):
        cls = classes[cls_urn]
        for claim in cls.claims:
            actions[claim] = {
                "input_schema": cls.input_schema,
                "side_effect": cls.side_effect,
                "composed_class": cls_urn,
            }
    # The classes that applied nowhere — every claim names an action
    # this descriptor does not declare — ride back as (class urn, pin
    # path) pairs for the disclosure channel.
    unapplied = tuple(
        (urn, classes[urn].pin_path)
        for urn in sorted(classes)
        if not any(claim in descriptor_actions for claim in classes[urn].claims)
    )
    # #556 §3 rule 4: member conflicts across the whole pin set — a slot
    # key two members declare (whatever pin each rode), and a claim held
    # by another member or by a composed action class (the class owns the
    # catalogue side, the member the placement; one claim, one owner).
    # One slot per member, one claim per owner — refuse, never merge.
    member_slot_owner: dict[str, str] = {}
    member_claim_owner: dict[str, str] = {}
    class_claims = {
        claim: cls_urn
        for cls_urn, cls in classes.items()
        for claim in cls.claims
    }
    for declaration in member_declarations:
        for member in declaration.members:
            slot = str(member.get("slot", ""))
            holder_pin = member_slot_owner.get(slot)
            if holder_pin is not None:
                # The B3 fold's NIT: two members of ONE document naming the
                # same slot printed the pin twice ("x and x"); the message
                # names the document once and says the pair is internal.
                if holder_pin == declaration.pin_path:
                    raise _refuse(
                        "classref_composed_slot_conflict",
                        f"member slot {slot} is declared by two members in "
                        f"the same pinned document ({holder_pin})",
                    )
                raise _refuse(
                    "classref_composed_slot_conflict",
                    f"member slot {slot} is declared by two members "
                    f"({holder_pin} and {declaration.pin_path})",
                )
            member_slot_owner[slot] = declaration.pin_path
            for claim in member.get("claims") or ():
                claim = str(claim)
                member_holder = member_claim_owner.get(claim)
                if member_holder is not None:
                    raise _refuse(
                        "classref_composed_slot_conflict",
                        f"{claim} is claimed by both member {member_holder} "
                        f"and member {slot}",
                    )
                class_holder = class_claims.get(claim)
                if class_holder is not None:
                    raise _refuse(
                        "classref_composed_slot_conflict",
                        f"member {slot} claims {claim}, which composed class "
                        f"{class_holder} claims",
                    )
                member_claim_owner[claim] = slot
    return (
        actions,
        classes,
        tuple(ignored),
        unapplied,
        tuple(empty_pins),
        tuple(member_declarations),
    )


def pinned_contract_documents(
    descriptor: Mapping[str, Any],
    admitted: Mapping[str, bytes] | None,
) -> dict[str, dict[str, Any]]:
    """The descriptor's digest-verified pinned contract documents an
    ACCEPTED pin shape carries (the presentation-side pin reader — the
    mirror of the SDK's ``pinned_contract_documents``, B4 motion 1): the
    documents the canonical validator's profile map reads beside the
    corpus set, so a composed member's target naming its declaration's
    vendor row validates (the seam).

    The shape filter is the walk's own one definition
    (``_pin_shape_groups`` — the B4 fold's F4): only documents the walk
    accepts may contribute anywhere — an ignored-shape pin (matched no
    key vocabulary) is digest-verified and DROPPED here exactly as the
    walk drops it, so the derive and the validation agree on the
    accepted set by construction. Integrity is the caller's: the bytes
    arrive from the admission store, digest-keyed (the composition's
    resolution), and the digest gate itself lives in the walk."""
    documents: dict[str, dict[str, Any]] = {}
    for row in descriptor.get("contracts", []):
        identifier = str(row.get("id", ""))
        if identifier.startswith("urn:otdp:"):
            continue
        raw = (admitted or {}).get(str(row.get("sha256", "")))
        if raw is None:
            continue
        document = json.loads(raw)
        if not isinstance(document, dict):
            continue
        groups = _pin_shape_groups(document)
        if len(groups) == 1:
            documents[str(row.get("path", ""))] = document
    return documents


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
        # A platform fault (incomplete corpus), never the recoverable
        # knowledge gap — its own code since the split (the SDK's).
        raise _refuse(
            "classref_profile_catalog_unserved",
            f"the descriptor's profile catalog {row_key} is not served",
        ) from exc


def _assemble_triple(
    descriptor: Mapping[str, Any],
    descriptor_raw: bytes,
    references: list[dict[str, Any]],
    actions: Mapping[str, Any],
    catalog_actions: Mapping[str, Any],
    corpus: Path,
    decoder_docs: Mapping[str, bytes] | None,
    *,
    ignored_pins: tuple[str, ...] = (),
    unapplied_classes: tuple[tuple[str, str], ...] = (),
    empty_action_pins: tuple[str, ...] = (),
    member_declarations: tuple[ComposedMemberDeclaration, ...] = (),
    composed_members: Mapping[str, tuple[dict[str, str], ...]] | None = None,
    unapplied_member_pins: tuple[str, ...] = (),
    unapplied_members: tuple[tuple[str, str, str], ...] = (),
) -> DerivedAttachment:
    """The derived triple (the SDK expander's ``_finish`` assembly, minus
    the SDK-side surfaces the gateway does not consume — the expectation
    document, the declaration and the preset scaffolds, the design's §9.3
    confirmation). Byte shapes mirror the SDK's canonical serialization."""
    merged = _merge_references(references)
    # #556 §3 rule 4: the reference-side member conflicts run over the
    # MERGED reference (final page ids and slot keys) and before any
    # member injects — the composed slot composes beside the reference,
    # never over it.
    _check_member_reference_conflicts(merged, member_declarations)
    _inject_composed_members(descriptor, merged, member_declarations)
    lanes_by_slot = _resolve_channels(descriptor, merged)
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
    # RC-4's decode_annotated overlay: the annotation form derives the
    # same pinned-decoder lanes (same code surface); its coverage rides
    # them. The plan row demotes the action to L4 on the plot page — it
    # renders through the decoder lanes, never as a bare control.
    plot_page = next(
        (str(page["id"]) for page in merged["pages"] if page.get("plot")),
        "",
    )
    for urn in actions:
        if urn.split("/")[0].rsplit(".", 1)[-1] != "decode_annotated":
            continue
        if descriptor.get("decoders") and plot_page:
            # The SDK's shape: the overlay PRESERVES the plan row's own
            # provenance (resolution and, when present, the class) — the
            # row claims a rendering, not a different derivation.
            plan[urn] = {
                **plan[urn],
                "level": "L4",
                "page": plot_page,
                "fields": [],
                "declared_deviation": False,
            }
    return _assemble_documents(
        descriptor,
        descriptor_raw,
        tuple(sorted({str(item["profile_id"]) for item in references})),
        merged,
        lanes_by_slot,
        actions,
        catalog_actions,
        plan,
        corpus,
        decoder_docs,
        ignored_pins=ignored_pins,
        unapplied_classes=unapplied_classes,
        empty_action_pins=empty_action_pins,
        member_declarations=member_declarations,
        composed_members=composed_members,
        unapplied_member_pins=unapplied_member_pins,
        unapplied_members=unapplied_members,
    )


def _decoder_no_host_detail(plot_kinds: Iterable[str]) -> str:
    """V3's decoder row detail (#556 Track B §4 V3 layer 3): the structural
    reason the decoder's lanes have no host.

    The canonical manifest schema admits ``decoder_lanes`` on a
    ``digital_lanes`` plot alone, so only a class whose plot IS
    digital_lanes can host a decoder at all. When such a plot derives and
    the lanes still do not land, the reason is not the kind — the row
    says no derived plot carries them rather than blaming a plot kind
    that admits them."""
    kinds = sorted({str(kind) for kind in plot_kinds if kind})
    if not kinds or "digital_lanes" in kinds:
        return (
            "no lane host (no derived plot carries its lanes; lanes host in "
            "digital_lanes plots alone)"
        )
    if len(kinds) == 1:
        return (
            f"no lane host (this class's plot is {kinds[0]}; lanes host in "
            "digital_lanes plots alone)"
        )
    return (
        f"no lane host (this class's plots are {', '.join(kinds)}; lanes host "
        "in digital_lanes plots alone)"
    )


def _computed_variable_detail(
    member: str,
    dataset_variables: Mapping[str, Collection[str]],
    series_overflow: Mapping[str, Collection[str]],
) -> str:
    """V2's row detail (#556 Track B §4 V2), naming what the computed
    variable actually derives into and what it was dropped from.

    ``dataset_variables`` maps each derived dataset target's id to the
    variable ids its wire shape carries WITHOUT the computed rows — a
    target whose base set already holds the computed id cannot compose
    it (the emitted set would carry a duplicate id).
    ``series_overflow`` maps a target whose PLOT ``y`` set the kind's
    schema ceiling forced to drop composed series, to the ids dropped —
    the variable still derives into the dataset, the plot cannot show
    it inside the manifest schema."""
    if not dataset_variables:
        return (
            "computes no dataset variable (no dataset target derives); "
            "no tile (no parameter to read)"
        )
    collided = sorted(
        target for target, ids in dataset_variables.items() if member in ids
    )
    total = len(dataset_variables)
    if len(collided) == total:
        detail = (
            f"id collides with a dataset variable on {', '.join(collided)}; "
            "no tile (no parameter to read)"
        )
    elif collided:
        detail = (
            f"id collides with a dataset variable on {', '.join(collided)}; "
            f"derives into {total - len(collided)} of {total} dataset targets "
            "(no tile; no parameter to read)"
        )
    else:
        detail = (
            "computed variable derives into dataset variables "
            "(no tile; no parameter to read)"
        )
    overflow = sorted(
        target for target, ids in series_overflow.items() if member in ids
    )
    if overflow:
        detail += (
            f"; no plot series on {', '.join(overflow)} (the plot's y admits "
            f"{_ANALOG_Y_CEILING} numeric series)"
        )
    return detail


def _residual_member_rows(
    descriptor: Mapping[str, Any],
    derived_decoder_ids: Iterable[str],
    *,
    channel_roles: Iterable[str] = (),
    dataset_variables: Mapping[str, Collection[str]] | None = None,
    series_overflow: Mapping[str, Collection[str]] | None = None,
    plot_kinds: Iterable[str] = (),
) -> tuple[tuple[str, str, str], ...]:
    """(#541 slice 3 fold R10; #556 Track B §3 rule 3) Declared members
    whose surface the derivation owes an account of, as (kind, member,
    detail) rows rendered on the disclosure channel — the SDK gate's
    ``{kind} {member}: {detail}`` REPORTED wording, mirrored verbatim.

    Layer 3's promise is two-sided — never refuses AND never silent:
    every declared member lands either a derived surface or a row here.
    Computed variables (V2) are composed-state disclosures (the variable
    derives into dataset shapes and never a tile); a channel whose role
    matches no resolved channels slot derives nothing and reports (the
    B1 closure); a decoder whose lanes no derived plot carries reports
    with the structural reason."""
    rows: list[tuple[str, str, str]] = []
    base_ids = dict(dataset_variables or {})
    overflow = dict(series_overflow or {})
    for row in descriptor.get("derived_variables") or []:
        member = str(row.get("id", "")) if isinstance(row, dict) else ""
        if not member:
            continue
        rows.append(
            (
                "observation variable",
                member,
                _computed_variable_detail(member, base_ids, overflow),
            )
        )
    resolved_roles = {str(role) for role in channel_roles}
    for row in descriptor.get("channels") or []:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        role = str(row.get("role", ""))
        if role in resolved_roles:
            continue
        rows.append(
            (
                "channel",
                f"{row['id']} (role {role})",
                "resolves to no lanes surface",
            )
        )
    derived_ids = {str(value) for value in derived_decoder_ids}
    decoder_detail = _decoder_no_host_detail(plot_kinds)
    for pin in descriptor.get("decoders") or []:
        member = str(pin.get("id", "")) if isinstance(pin, dict) else ""
        if member and member not in derived_ids:
            rows.append(
                (
                    "custom decoder",
                    member,
                    decoder_detail,
                )
            )
    return tuple(rows)


def _assemble_documents(
    descriptor: Mapping[str, Any],
    descriptor_raw: bytes,
    profile_ids: tuple[str, ...],
    merged: dict[str, Any],
    lanes_by_slot: Mapping[str, list[dict[str, Any]]],
    actions: Mapping[str, Any],
    catalog_actions: Mapping[str, Any],
    plan: dict[str, dict[str, Any]],
    corpus: Path,
    decoder_docs: Mapping[str, bytes] | None,
    *,
    ignored_pins: tuple[str, ...] = (),
    unapplied_classes: tuple[tuple[str, str], ...] = (),
    empty_action_pins: tuple[str, ...] = (),
    member_declarations: tuple[ComposedMemberDeclaration, ...] = (),
    composed_members: Mapping[str, tuple[dict[str, str], ...]] | None = None,
    unapplied_member_pins: tuple[str, ...] = (),
    unapplied_members: tuple[tuple[str, str, str], ...] = (),
) -> DerivedAttachment:
    """The document assembly (the SDK expander's ``_finish`` port):
    bindings, targets, pages, assets, the layout block and the triple,
    byte-shaped like the SDK's emission (B8's pin). The composed-member
    arms mirror the SDK's at the tips: the profile seam (a member's
    target names the declaration's vendor row), per-slot lane resolution
    with the page-level join, the plot-kind inheritance, the computed
    variables, the dataset tail, the placement dispositions and the
    mint-collision refusal."""
    version = active_version_from_corpus(corpus, "plugin-ui")
    # (#556 §4 V1/V6/V4, the seam) The profile ids a COMPOSED member's
    # target names: the declaration's own vendor row — the row the
    # canonical validator's profile map reads from the pinned documents
    # (the seam, B4's motion 1) — never the served set, whose rows list
    # none of the member's claimed actions. A reference slot's target
    # keeps the served set exactly as before.
    member_profile_for_slot: dict[str, str] = {}
    for member_declaration in member_declarations:
        if member_declaration.profile is None:
            continue
        for member in member_declaration.members:
            if member.get("kind") not in ("procedure", "configuration", "dataset"):
                continue
            if not _member_applies(member, descriptor):
                continue
            member_profile_for_slot[str(member.get("slot", ""))] = str(
                member_declaration.profile["id"]
            )

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
    # (#556 B3, V3 layer 2) Per-slot lanes: every channels slot resolves
    # its role's channels; a page's plot consumes the lanes of the
    # channels slots PLACED on that page (an applied composed member's
    # placement), keeping the founding default — the FIRST slot's lanes —
    # for pages that place none. Every corpus reference places none, so
    # member-pin-free derivations are byte-identical under the
    # generalization (the record's M6, pinned by the parity arms).
    channels_order = list(lanes_by_slot)
    default_lanes: list[dict[str, Any]] = (
        lanes_by_slot[channels_order[0]] if channels_order else []
    )

    def _lanes_for_page(page_id: str) -> list[dict[str, Any]]:
        placed = [
            key
            for page in merged["pages"]
            if str(page.get("id")) == page_id
            for key in page.get("_slot_keys", [])
            if key in lanes_by_slot
        ]
        # The founding default is the BASE (the class's implicit
        # slot-to-plot association), and a placed slot's lanes JOIN it:
        # composing beside, never replacing.
        order = [channels_order[0]] if channels_order else []
        order.extend(key for key in placed if key not in order)
        lane_rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for key in order:
            for row in lanes_by_slot[key]:
                if str(row.get("id")) not in seen:
                    seen.add(str(row.get("id")))
                    lane_rows.append(row)
        return lane_rows

    # The lanes feeding each page-template plot, keyed by its over-slot —
    # the map every lane-derived variable set reads (a dataset slot with
    # no plot of its own keeps the founding default).
    lanes_for_over_slot: dict[str, list[dict[str, Any]]] = {}
    for page in merged["pages"]:
        spec = page.get("plot")
        if not spec:
            continue
        lanes_for_over_slot[str(spec.get("over_slot", ""))] = _lanes_for_page(
            str(page["id"])
        )
    x_var = {"id": "t", "type": "number", "unit": "s", "shape": "vector", "axis_role": "x"}
    # The plot kind each dataset slot serves, from the reference's page
    # templates (the 0.3.0 vocabulary widening): a slot's variables are
    # the wire shape its kind declares — the digital_lanes logic
    # alphabet, the scalar variables of a measure dataset (one per
    # channel and declared quantity), or the array-valued traces of a
    # waveform dataset over the explicit time axis. A slot with no plot
    # keeps the founding shape — UNLESS its binding page hosts one
    # (#556 §4 V4, B5): a plot-less slot INHERITS the page's plot kind,
    # so a vendor capture bound beside a waveform plot derives the
    # waveform wire shape rather than the founding digital-lanes
    # string-lane shape that contradicts the page.
    plot_kind_for_slot: dict[str, str] = {}
    plot_kind_for_page: dict[str, str] = {}
    page_of_slot: dict[str, str] = {}
    for page in merged["pages"]:
        page_id = str(page["id"])
        for key in page.get("_slot_keys", []):
            page_of_slot.setdefault(key, page_id)
        spec = page.get("plot")
        if spec:
            plot_kind_for_slot.setdefault(
                str(spec.get("over_slot", "")),
                str(spec.get("kind", "digital_lanes")),
            )
            plot_kind_for_page.setdefault(
                page_id, str(spec.get("kind", "digital_lanes"))
            )

    def _slot_plot_kind(slot_key: str) -> str:
        """The plot kind a dataset slot's wire shape speaks: its own plot
        spec's kind first, then — B5's inheritance refinement — the
        binding page's plot kind, then the founding digital_lanes
        shape."""
        own = plot_kind_for_slot.get(slot_key)
        if own is not None:
            return own
        return plot_kind_for_page.get(
            page_of_slot.get(slot_key, ""), "digital_lanes"
        )

    readings_slots = {
        key
        for page in merged["pages"]
        if str(page.get("kind", "readings")) == "readings"
        for key in page.get("_slot_keys", [])
        if key in dataset_slots
    }
    # The parameter map is descriptor-wide (channel identity to readable
    # parameter): built over every resolved lane, so a page's tiles read
    # their own lanes' parameters from one map.
    all_lanes: list[dict[str, Any]] = [
        row for rows in lanes_by_slot.values() for row in rows
    ]
    parameter_rows = (
        _resolve_parameters(descriptor, all_lanes) if readings_slots else {}
    )

    def _quantity_vars(
        lane_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": f"{row['id']}-{quantity}",
                "type": "number",
                "unit": (
                    parameter_rows.get((str(row["id"]), str(quantity))) or {}
                ).get("unit"),
                "shape": "scalar",
                "axis_role": "value",
            }
            for row in lane_rows
            for quantity in row.get("quantities") or []
        ]

    def _trace_vars(
        lane_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": f"{row['id']}-{quantity}",
                "type": "number",
                "unit": (
                    parameter_rows.get((str(row["id"]), str(quantity))) or {}
                ).get("unit"),
                "shape": "vector",
            }
            for row in lane_rows
            for quantity in row.get("quantities") or []
        ]

    # time_series speaks receipt time (the canonical validator's own rule:
    # the x axis is receipt_time in seconds, every axis scalar); waveform
    # speaks the explicit time-axis vector alongside its traces.
    receipt_var = {
        "id": "time",
        "type": "number",
        "unit": "s",
        "shape": "scalar",
        "axis_role": "receipt_time",
    }
    # (#556 Track B §4 V2) A computed measurement — the descriptor's own
    # ``derived_variables`` declaration — is an ordinary value variable of
    # EVERY dataset target: the host computes the value into the dataset,
    # so the wire carries it and the derived shape asserting it is
    # honest. The shape follows the dataset's own wire shape (a
    # time_series dataset's value variables are scalars; a waveform or
    # digital-lanes dataset carries a vector per sample). A computed id
    # that collides with ANY variable id a dataset's wire shape already
    # carries cannot be composed into that dataset (the emitted set would
    # carry a duplicate id); the residual channel names that collision.
    computed_rows = [
        {
            "id": str(row["id"]),
            "type": "number",
            "unit": str(row["unit"]),
        }
        for row in descriptor.get("derived_variables") or []
        if isinstance(row, dict) and row.get("id")
    ]
    computed_ids = {str(row["id"]) for row in computed_rows}

    def _dataset_base(slot_key: str) -> tuple[list[dict[str, Any]], str]:
        """The wire shape a dataset slot carries WITHOUT the computed rows,
        and its axis variable id. The lane-derived rows are the lanes of
        the PLOT over this slot (#556 B3) — the founding default for a
        slot with no plot of its own. The KIND is the slot's own plot's,
        or its binding page's (#556 B5)."""
        kind = _slot_plot_kind(slot_key)
        lane_rows = lanes_for_over_slot.get(slot_key, default_lanes)
        if kind == "time_series":
            return [receipt_var, *_quantity_vars(lane_rows)], str(receipt_var["id"])
        if kind == "waveform":
            return [x_var, *_trace_vars(lane_rows)], str(x_var["id"])
        return [
            x_var,
            *(
                {"id": row["id"], "type": "string", "unit": None, "shape": "vector"}
                for row in lane_rows
            ),
        ], str(x_var["id"])

    def _dataset_shape(slot_key: str) -> list[dict[str, Any]]:
        kind = _slot_plot_kind(slot_key)
        wire_shape = "scalar" if kind == "time_series" else "vector"
        base, _axis = _dataset_base(slot_key)
        base_ids = {row["id"] for row in base}
        return [
            *base,
            *[
                {**row, "shape": wire_shape}
                for row in computed_rows
                if row["id"] not in base_ids
            ],
        ]

    bindings: list[dict[str, Any]] = []
    targets: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    if capture_key:
        targets.append(
            {
                "id": capture_key,
                "kind": "dataset",
                "action_id": capture_slot["action"],
                # (#556 §4 V4) A composed dataset member in the capture
                # position (a class whose reference carries no dataset slot
                # of its own) names the vendor row — the seam — exactly as
                # a composed procedure/configuration target does.
                "profile_ids": (
                    [member_profile_for_slot[capture_key]]
                    if capture_key in member_profile_for_slot
                    else profile_ids
                ),
                "measurement_schema_id": measurement_id,
                "variables": _dataset_shape(capture_key),
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
    # The lanes a decoder's sources map onto: the lanes of the plot that
    # hosts decoder lanes — the digital_lanes plot (#556 B3: per-page lane
    # sets; founding behavior is the default set, the one channels slot).
    decode_host_lanes: list[dict[str, Any]] = next(
        (
            lanes_for_over_slot[str(spec.get("over_slot", ""))]
            for page in merged["pages"]
            if str((spec := page.get("plot") or {}).get("kind", "")) == "digital_lanes"
        ),
        default_lanes,
    )
    if (
        (decode_declared or decode_annotated_urn)
        and descriptor.get("decoders")
        and decoder_docs is not None
    ):
        # The SDK resolves decoder documents from descriptor-relative
        # files; the gateway's equivalent is the admission store (keyed
        # by the pins' digests), and a pin the store cannot resolve skips
        # the decoder (the SDK's own unreadable-document arm).
        for pin in descriptor["decoders"]:
            raw = decoder_docs.get(str(pin.get("sha256", "")))
            if raw is None:
                continue
            try:
                document = json.loads(raw)
                if not isinstance(document, dict):
                    # The SDK's expander crashes on a non-object decoder
                    # document (its check-ui gates it at authoring time);
                    # the gateway's only gate is this derivation, so a
                    # non-object joins the unreadable arm — never a 500.
                    raise ValueError("decoder document is not an object")
                line_ids = [
                    str(row.get("id"))
                    for row in (
                        document.get("optional_channels")
                        or document.get("channels")
                        or []
                    )
                    if isinstance(row, dict) and row.get("id")
                ]
            except ValueError:
                line_ids = []
            if not line_ids or len(line_ids) > len(decode_host_lanes):
                continue
            sources = [row["id"] for row in decode_host_lanes[: len(line_ids)]]
            settings = {
                str(line): source
                for line, source in zip(line_ids, sources, strict=False)
            }
            decoder_lanes.append(
                {
                    "id": f"decode-{pin['id']}",
                    "label": str(document.get("name", pin["id"])),
                    "decoder": str(pin["id"]),
                    "settings": settings,
                    "source_channel_ids": sources,
                    "binding_id": decode_key,
                }
            )
    if decoder_lanes and decode_key and not decode_declared:
        # Annotation-form lanes with no decode declaration bind the capture
        # dataset binding (no decode target exists to carry them).
        for lane_row in decoder_lanes:
            lane_row["binding_id"] = capture_binding_id
    if decode_key and decode_declared:
        targets.append(
            {
                "id": decode_key,
                "kind": "dataset",
                "action_id": decode_slot["action"],
                # (#556 §4 V4/V3) A composed dataset member in the decode
                # position is the decoder lanes' binding host — and names
                # the vendor row when the slot is a member's, exactly as
                # the capture position does.
                "profile_ids": (
                    [member_profile_for_slot[decode_key]]
                    if decode_key in member_profile_for_slot
                    else profile_ids
                ),
                "measurement_schema_id": measurement_id,
                "variables": _dataset_shape(decode_key),
            }
        )
        bindings.append({"id": decode_key, "kind": "dataset", "target_id": decode_key})
    # (#556 §4 V4, B5) The dataset loop's composed tail: every dataset
    # slot beyond the founding pair (the capture position and the decode
    # position) whose action the descriptor declares composes its own
    # target and binding through the same arm. Only an injected member
    # reaches here — the corpus references carry at most two dataset
    # slots — and an APPLIED member's action is declared by construction;
    # the guard keeps the arm honest for any future corpus shape.
    for tail_key, tail_slot in dataset_slots.items():
        if tail_key in (capture_key, decode_key):
            continue
        if str(tail_slot.get("action", "")) not in actions:
            continue
        targets.append(
            {
                "id": tail_key,
                "kind": "dataset",
                "action_id": tail_slot["action"],
                "profile_ids": (
                    [member_profile_for_slot[tail_key]]
                    if tail_key in member_profile_for_slot
                    else profile_ids
                ),
                "measurement_schema_id": measurement_id,
                "variables": _dataset_shape(tail_key),
            }
        )
        bindings.append(
            {"id": tail_key, "kind": "dataset", "target_id": tail_key}
        )
    # The readings expansion (the L11 rule; the SDK expander at the pin):
    # a readings page's rendered tiles are OBSERVATION bindings — one per
    # scalar variable of its dataset slot — each naming the descriptor
    # parameter the channel binds to that quantity. The layout's authored
    # reading-tile nodes are consumed by this expansion (see
    # _build_layout): one authored child becomes the page's observation
    # tiles, never an admittance table beside them. A channel quantity
    # with no named readable parameter SKIPS its tile only in the
    # zero-readable-parameters shape (the _resolve_parameters guard);
    # a descriptor with parameters resolves fully or refuses typed.
    observation_ids_for_page: dict[str, list[str]] = {}
    observation_value_ids: dict[str, str] = {}
    # (#556 B5 refute fold F4, 2026-10-26) The derived id namespace is
    # shared: a member slot key that spells an observation binding id
    # makes the member's dataset target and the class's observation
    # target share one id — the derive stays green and the canonical
    # validation dies in the host's untyped duplicate-identifiers
    # refusal. The collision refuses at the mint, under the
    # composed-slot conflict code: the declaration names an id the
    # derivation already owns and the author can rename the slot.
    minted_binding_ids = {row["id"] for row in bindings}
    for page in merged["pages"]:
        if str(page.get("kind", "readings")) != "readings":
            continue
        page_id = str(page["id"])
        # The page's own tiles read the page's lanes (#556 B3: the placed
        # channels slots' lanes, the founding default when none is placed).
        page_lanes = _lanes_for_page(page_id)
        for key in page.get("_slot_keys", []):
            if key not in dataset_slots:
                continue
            ids: list[str] = []
            for row in page_lanes:
                for quantity in row.get("quantities") or []:
                    parameter = parameter_rows.get((str(row["id"]), str(quantity)))
                    if parameter is None:
                        continue  # the guard's shape: no readable parameters
                    binding_id = f"{key}-{row['id']}-{quantity}"
                    if binding_id in minted_binding_ids:
                        raise _refuse(
                            "classref_composed_slot_conflict",
                            f"observation binding {binding_id} on page "
                            f"{page_id} collides with an id the derivation "
                            "already mints (a member slot key must not spell "
                            "a derived id — rename the slot)",
                        )
                    minted_binding_ids.add(binding_id)
                    value_id = f"{row['id']}-{quantity}"
                    targets.append(
                        {
                            "id": binding_id,
                            "kind": "observation",
                            "parameter_id": str(parameter.get("name")),
                            # The canonical observation shape (the
                            # scaffold's own): receipt time in seconds plus
                            # the one value variable this tile reads.
                            "variables": [
                                {
                                    "id": "time",
                                    "type": "number",
                                    "unit": "s",
                                    "shape": "scalar",
                                    "axis_role": "receipt_time",
                                },
                                {
                                    "id": value_id,
                                    "type": "number",
                                    "unit": parameter.get("unit"),
                                    "shape": "scalar",
                                    "axis_role": "value",
                                },
                            ],
                        }
                    )
                    bindings.append(
                        {"id": binding_id, "kind": "observation", "target_id": binding_id}
                    )
                    ids.append(binding_id)
                    observation_value_ids[binding_id] = value_id
            observation_ids_for_page.setdefault(page_id, []).extend(ids)
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
        # The catalogue-row resolution (§3.5, mirrored): a custom or
        # composed action bound to a configuration slot derives its
        # settings schema from the effective schema alone — the $id
        # falls back to the derived action-input urn when the row (or
        # the class's input_schema) declares none.
        slot_catalogue_row = _catalogue_row(urn, catalog_actions)
        effective = _effective_action_schema(
            urn, slot_catalogue_row, actions[urn].get("input_constraints") or {}
        )
        catalogue_input = (slot_catalogue_row or {}).get("input_schema", {}) or {}
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
                # (#556 §4 V6) A composed settings member's target names
                # the declaration's vendor profile row (the seam); a
                # class slot's keeps the served set.
                "profile_ids": (
                    [member_profile_for_slot[config_key]]
                    if config_key in member_profile_for_slot
                    else profile_ids
                ),
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
                # (#556 §4 V1) A composed procedure member's target names
                # the declaration's vendor profile row (the seam); a
                # class slot's keeps the served set.
                "profile_ids": (
                    [member_profile_for_slot[proc_key]]
                    if proc_key in member_profile_for_slot
                    else profile_ids
                ),
                # The catalogue-row resolution (§3.5, mirrored): a
                # catalog-less action's target carries no input schema
                # id (None), never a KeyError.
                "input_schema_id": (_catalogue_row(urn, catalog_actions) or {})
                .get("input_schema", {})
                .get("$id"),
            }
        )
        bindings.append({"id": proc_key, "kind": "procedure", "target_id": proc_key})
    # Vendor actions carry no manifest target (the vendored validator
    # admits catalogue targets for profile actions only); their controls
    # render through the layout block on their plan page.
    resolved = {row["id"] for row in bindings}
    binding_kind = {row["id"]: row["kind"] for row in bindings}
    pages_out: list[dict[str, Any]] = []
    for page in merged["pages"]:
        page_id = str(page["id"])
        kind = str(page.get("kind", "readings"))
        allowed = {
            "dataset": {"dataset"},
            "configuration": {"configuration", "procedure"},
            "readings": {"observation"},
        }.get(kind, {"observation"})
        candidates = list(page.get("bindings", [])) + observation_ids_for_page.get(
            page_id, []
        )
        rows = [
            b
            for b in dict.fromkeys(candidates)
            if b in resolved and binding_kind.get(b, "") in allowed
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
    if decoder_lanes and decode_key and capture_key:
        # Decoder lanes name the decode dataset binding on the plot's page
        # (the other-action rule): the lanes render there even when the
        # reference's own page template did not list the decode slot.
        plot_page_id = next(
            (str(row["id"]) for row in merged["pages"] if row.get("plot")),
            None,
        )
        for page in pages_out:
            if plot_page_id is not None and page["id"] == plot_page_id:
                if decode_key not in page["bindings"]:
                    page["bindings"].append(decode_key)
                break
    plots: list[dict[str, Any]] = []
    # Slots whose plot ``y`` set the kind's schema ceiling forced to drop
    # composed series: slot key -> the ids dropped (#556 B1 fold F2). The
    # disclosure channel names them; the dataset's variable set still
    # carries them.
    series_overflow: dict[str, tuple[str, ...]] = {}
    # (#556 B3 fold F1) The page-level lane join over the ceiling: page id
    # to (joined count, dropped lane rows) — the disclosure source beside
    # ``series_overflow``.
    lane_join_overflow: dict[str, tuple[int, tuple[dict[str, Any], ...]]] = {}
    for page in pages_out:
        template = next(
            (row for row in merged["pages"] if str(row["id"]) == page["id"]), None
        )
        plot_spec = (template or {}).get("plot")
        if plot_spec is None:
            continue
        over_key = str(plot_spec.get("over_slot", ""))
        if over_key not in merged["slots"] or over_key not in resolved:
            continue
        kind = str(plot_spec.get("kind", "digital_lanes"))
        if kind in ("time_series", "waveform"):
            # The scalar/trace plot (the 0.3.0 widening): no group
            # machinery (the schema bans it exactly as for the other
            # non-lanes kind). A dataset-page plot binds its slot and
            # carries one series per numeric variable (the closed
            # ``series: "numeric_variables"`` rule); a READINGS page
            # admits observation bindings only and one observation
            # target carries one value variable, so its trend binds the
            # page's first observation. A decoder-carrying numeric
            # descriptor keeps its decode binding/target — the lanes
            # simply do not ride the analog plot (a disclosed residual,
            # the module docstring's).
            if kind == "time_series" and observation_ids_for_page.get(
                str(page["id"])
            ):
                bound = observation_ids_for_page[str(page["id"])][0]
                y_ids = [observation_value_ids[bound]]
                x_id = "time"
            else:
                shape = _dataset_shape(over_key)
                x_id = "time" if kind == "time_series" else "t"
                y_ids = [row["id"] for row in shape if row["id"] != x_id]
                # (#556 B1 fold F2, mirrored) The analog kinds cap ``y`` at
                # the manifest schema's ceiling, and the COMPOSED series
                # are the drop candidates: the overflow drops from the
                # plot and lands the residual channel; the dataset's
                # variable set still carries every row (the wire keeps
                # them). A class whose own traces already exceed the
                # ceiling keeps the gateway's pre-existing typed arm —
                # the documented fail-closed face the SDK lacks.
                base_y = [
                    identifier for identifier in y_ids if identifier not in computed_ids
                ]
                if len(base_y) > _ANALOG_Y_CEILING:
                    raise _refuse(
                        "classref_series_ceiling",
                        f"{len(base_y)} numeric variables ride the {kind} plot "
                        f"(ceiling {_ANALOG_Y_CEILING})",
                    )
                budget = max(0, _ANALOG_Y_CEILING - len(base_y))
                composed_y = [
                    identifier for identifier in y_ids if identifier in computed_ids
                ]
                if len(composed_y) > budget:
                    overflow = composed_y[budget:]
                    dropped = set(overflow)
                    y_ids = [
                        identifier
                        for identifier in y_ids
                        if identifier not in dropped
                    ]
                    series_overflow[str(over_key)] = tuple(overflow)
                bound = over_key
            plots.append(
                {
                    "kind": kind,
                    "binding_id": bound,
                    "x": x_id,
                    "y": y_ids,
                }
            )
            page["plots"] = [plots[-1]]
            continue
        # The logic-alphabet lanes of THIS plot (#556 B3): the placed
        # channels slots' lanes, the founding default when none is placed.
        plot_lanes = lanes_for_over_slot.get(over_key, default_lanes)
        # (#556 B3 fold F1) The PAGE-LEVEL JOIN is bounded: per-slot
        # resolution refuses a slot over the ceiling alone, but the join
        # of the first slot's lanes with every placed member slot's lanes
        # bounded nothing — a schema-invalid y and a host-load refusal.
        # The join over the cap is a capacity limit no single declaration
        # is at fault for (the 2026-10-25 boundary's join half): the
        # overflow drops from the PLOT alone — the wire shape keeps every
        # joined lane — and each dropped lane REPORTs on the disclosure
        # channel. The overflow is structurally composed lanes: the first
        # slot's own count is inside the per-slot ceiling and the join
        # order puts it first.
        if len(plot_lanes) > _LANE_CEILING:
            lane_join_overflow[str(page["id"])] = (
                len(plot_lanes),
                tuple(plot_lanes[_LANE_CEILING:]),
            )
            plot_lanes = plot_lanes[:_LANE_CEILING]
        lane_var_rows = [
            {"id": row["id"], "type": "string", "unit": None, "shape": "vector"}
            for row in plot_lanes
        ]
        groups = []
        full = len(lane_var_rows) // _GROUP_SIZE
        remainder = len(lane_var_rows) % _GROUP_SIZE
        total = full + (1 if remainder >= 2 else 0)
        for k in range(total):
            start = k * _GROUP_SIZE
            width = _GROUP_SIZE if k < full else remainder
            members = [row["id"] for row in lane_var_rows[start : start + width]]
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
                # (#556 §4 V5, B5) The lanes plot binds the dataset whose
                # shape carries its lane alphabet — the over-slot's own
                # binding. The corpus's every lanes plot hosts the capture
                # slot itself, so this equals the founding
                # capture_binding_id on every committed fixture (the
                # parity arms); a composed lanes plot over the member's
                # own slot binds that member's dataset, whose digital-lanes
                # shape carries exactly these lane variables.
                "binding_id": over_key,
                "x": "t",
                "y": [row["id"] for row in lane_var_rows],
                "channel_hints": [
                    {"variable_id": row["id"], "visible": True} for row in lane_var_rows
                ],
                "lane_groups": groups,
                "decoder_lanes": decoder_lanes,
            }
        )
        page["plots"] = [plots[-1]]
    # The R9 fold (mirrored): a plan row advertises a rendering only when
    # that rendering occurs — the decode-annotated row's claim rides the
    # decoder annotation lanes, and those lanes derive into a
    # digital-lanes plot's ``decoder_lanes`` key alone, so a descriptor
    # whose plot is a waveform or time-series never renders them and the
    # row carries no claim.
    if any(plot.get("decoder_lanes") for plot in plots):
        for urn, row in plan.items():
            if urn.split("/")[0].rsplit(".", 1)[-1] == "decode_annotated":
                row["rendered_by"] = "decoder annotation lanes"
    # (#556 §4 V4 provenance, B5; risk #6's falsifier) A COMPOSED dataset
    # row advertises a rendering only when a derived plot carries its
    # binding — the R9 stamp discipline, landed after plot construction.
    # The membership test is SCOPED to a plot on the member's own page
    # whose binding resolves to a DATASET binding (the B5 fold's F4):
    # a readings page's plot binds an OBSERVATION id, and a member slot
    # that shares its spelling would win a false stamp and lose its
    # honest disclosure row to the skip below.
    page_of_dataset_plot_binding: dict[str, str] = {}
    plot_binding_of_page: dict[str, str] = {}
    for page in pages_out:
        for plot in page.get("plots") or ():
            bound = str(plot.get("binding_id"))
            plot_binding_of_page.setdefault(str(page["id"]), bound)
            if binding_kind.get(bound) == "dataset":
                page_of_dataset_plot_binding[bound] = str(page["id"])
    for member_row in (composed_members or {}).get("datasets", ()):
        if page_of_dataset_plot_binding.get(str(member_row["slot"])) == str(
            member_row["page"]
        ):
            plan_row = plan.get(str(member_row["action"]))
            if plan_row is not None:
                plan_row["rendered_by"] = "the page plot"
    # --- the residual/member disclosure rows (the SDK's member_residual_rows
    # + residual_members, mirrored verbatim in wording) ---
    member_residual_rows: list[tuple[str, str, str]] = []
    pages_with_plot = {
        str(page.get("id")) for page in merged["pages"] if page.get("plot")
    }
    # (#556 §4 V3 layer 2) An APPLIED channels member whose page hosts no
    # plot applies but renders nothing: its channels resolved (the B1
    # closure is quiet) yet no surface carries them. A page whose plot IS
    # analog renders the member's channels as their quantity/trace
    # variables, so only the plot-less page reaches this row.
    for row in (composed_members or {}).get("channels", ()):
        if row["page"] not in pages_with_plot:
            member_residual_rows.append(
                (
                    "composed channels",
                    str(row["slot"]),
                    f"no lane host (page {row['page']} hosts no plot; lanes "
                    "render into the named page's plot alone)",
                )
            )
    # (#556, the 0.5.0 README rule 4; the 2026-10-25 capacity-versus-
    # declaration ruling) A dataset member's ``plot`` on a page whose
    # class template already hosts a plot is ADMISSIBLE — a placement
    # limit the declaration cannot see — so it never refuses: the page
    # keeps the class's plot and every run REPORTS the row. The second
    # row names a page whose KIND the manifest schema admits no plot on
    # (configuration pages). The injected member plots are marked, so the
    # class-template question stays answerable after injection.
    member_plot_pages = {
        str(page.get("id"))
        for page in merged["pages"]
        if page.get("_member_plot_of")
    }
    page_kind_of_rows = {
        str(page.get("id")): str(page.get("kind", "readings"))
        for page in merged["pages"]
    }
    for member_document in member_declarations:
        for member in member_document.members:
            if not isinstance(member.get("plot"), dict):
                continue
            if not _member_applies(member, descriptor):
                continue
            page_id = str(member.get("page", ""))
            if page_id in pages_with_plot and page_id not in member_plot_pages:
                member_residual_rows.append(
                    (
                        "composed plot",
                        str(member.get("slot", "")),
                        f"page {page_id} already hosts a plot (the page "
                        "keeps the class's plot)",
                    )
                )
            elif page_kind_of_rows.get(page_id) not in ("dataset", "readings"):
                member_residual_rows.append(
                    (
                        "composed plot",
                        str(member.get("slot", "")),
                        f"page {page_id} admits no plot (plots render on "
                        "dataset and readings pages alone)",
                    ),
                )
    # (#556 §4 V4/V5 layer 3, B5) A composed dataset slot NO derived plot
    # carries discloses on the same channel — applied is not rendered, and
    # the L4 census on a plot-bearing page must not launder a binding the
    # neighbour plot does not carry. The skip is the stamp's own scoped
    # test above; the reason names the EMITTED plot's binding (the B5
    # fold's F2: on a readings page the emitted time-series plot binds
    # the page's first OBSERVATION, so a reason naming the template's
    # over_slot states a binding the plot does not carry).
    for member_row in (composed_members or {}).get("datasets", ()):
        slot = str(member_row["slot"])
        page_id = str(member_row["page"])
        if page_of_dataset_plot_binding.get(slot) == page_id:
            continue
        emitted = plot_binding_of_page.get(page_id)
        if emitted is not None:
            detail = (
                f"no plot carries its binding (the plot on page {page_id} "
                f"binds {emitted})"
            )
        else:
            detail = f"no plot carries its binding (page {page_id} hosts no plot)"
        member_residual_rows.append(
            (
                "composed dataset",
                slot,
                detail,
            )
        )
    # (#556 B3 fold F1) The join overflow rows — one per dropped lane,
    # each naming the page, the joined count and the ceiling (the number
    # and its denominator). The lane's role RESOLVED, so the channel
    # closure stays quiet: this row is the disclosure, not a second one.
    for page_id, (joined, dropped_rows) in lane_join_overflow.items():
        for lane_row in dropped_rows:
            member_residual_rows.append(
                (
                    "composed lane",
                    f"{lane_row.get('id')} (role {lane_row.get('role', '')})",
                    "no lane surface on page "
                    f"{page_id} (the page's channels slots join to "
                    f"{joined} lanes; the plot's y admits {_LANE_CEILING})",
                )
            )
    # (#556 §4 V6 layer 3; B4 fold F5) A declared action whose controls
    # render STAGED on device-features carries the settings idiom's
    # control shape without the idiom — REPORTs every run. The classifier
    # is the derived state (OTDP types no verbs): unclaimed by any slot
    # AND level L2 — EXCEPT an action a claimed profile's served row
    # lists (the one honest class-action signal; otdp.smu.arm and
    # otdp.smu.fetch are class run-verbs, never vendor settings members,
    # whatever their derived level).
    catalog_rows_for_plan = _catalog_document(
        corpus, _corpus_pin_rows(corpus), descriptor
    ).get("profiles", [])
    claimed_profiles = set(descriptor.get("profiles") or [])
    class_listed_actions = {
        str(action)
        for row in catalog_rows_for_plan
        if isinstance(row, dict) and str(row.get("id")) in claimed_profiles
        for action in [
            *(row.get("required_actions") or []),
            *(row.get("optional_actions") or []),
        ]
    }
    # (#556 §4 V4 layer 3, B5) The dataset vocabulary's own row: an
    # unclaimed L1 action (the bare-button shape) derives its control
    # only, and no dataset surface names it — same classifier, same
    # class-listed exclusion.
    for urn, row in sorted(plan.items()):
        if (
            row.get("page") == "device-features"
            and urn not in class_listed_actions
        ):
            if row.get("level") == "L2":
                member_residual_rows.append(
                    (
                        "settings member",
                        urn,
                        "no settings surface declared "
                        "(controls render staged on device-features)",
                    )
                )
            elif row.get("level") == "L1":
                member_residual_rows.append(
                    (
                        "dataset member",
                        urn,
                        "no dataset surface declared (the action's control "
                        "renders on device-features)",
                    ),
                )
    # The residual rows (the SDK's channel closure is resolution-keyed —
    # every channels slot's role, reference or composed: a channel of a
    # role no slot resolves reports; a channel of a RESOLVED role whose
    # member renders nowhere is disclosed by the member's own row above).
    residual_rows = tuple(
        [
            *_residual_member_rows(
                descriptor,
                {
                    str(lane.get("decoder", ""))
                    for plot in plots
                    for lane in (plot.get("decoder_lanes") or [])
                },
                channel_roles=(
                    str(slot.get("where_role", ""))
                    for slot in _channels_slots(merged).values()
                ),
                dataset_variables={
                    str(target["id"]): frozenset(
                        str(row["id"])
                        for row in _dataset_base(str(target["id"]))[0]
                    )
                    for target in targets
                    if target["kind"] == "dataset"
                },
                series_overflow=series_overflow,
                plot_kinds=[str(plot.get("kind", "")) for plot in plots],
            ),
            *member_residual_rows,
        ]
    )
    # (#556 B4) Binding-to-action resolution consults the slot keys: a
    # composed member's slot may name its binding anything the schema
    # admits, where the class convention binding id == action slug does
    # not hold (the M-400 shape: a vendor-configure slot naming the
    # profile_mode action). The map rides to the layout block's mint
    # sites, page-scoped (the B4 fold's F1).
    slot_urns = {
        key: str(slot["action"])
        for key, slot in merged["slots"].items()
        if slot.get("action")
    }
    layout_block = _build_layout(
        corpus,
        pages_out,
        plots,
        merged["layouts"],
        plan,
        templates={str(row["id"]): row for row in merged["pages"]},
        slot_urns=slot_urns,
    )
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
    resolutions = tuple(
        (
            str(urn),
            str(row.get("resolution", "catalog")),
            str(row["class"]) if row.get("class") is not None else None,
        )
        for urn, row in sorted(plan.items())
    )
    return DerivedAttachment(
        envelope=envelope,
        manifest=manifest,
        catalogue=catalogue,
        envelope_raw=envelope_raw,
        manifest_raw=manifest_raw,
        catalogue_raw=catalogue_raw,
        resources=resources,
        profile_ids=profile_ids,
        resolutions=resolutions,
        ignored_pins=ignored_pins,
        unapplied_classes=unapplied_classes,
        empty_action_pins=empty_action_pins,
        member_declarations=member_declarations,
        composed_members=composed_members or {},
        unapplied_member_pins=unapplied_member_pins,
        unapplied_members=unapplied_members,
        residual_rows=residual_rows,
    )


def derive_attachment(
    descriptor_raw: bytes,
    *,
    corpus: Path,
    vendor_catalogs: Mapping[str, bytes] | None = None,
    references_override: list[dict[str, Any]] | None = None,
    decoder_docs: Mapping[str, bytes] | None = None,
) -> DerivedAttachment:
    """Expand (descriptor × reference) into the derived attachment triple.

    Raises ``ClassRefusal`` for every fail-closed case (parent record
    §3.3's table); the caller renders the typed refusal, never a partial
    page. Selection is the fail-open boundary: call ``select_references``
    first — ``None`` there means the unknown-class arm renders today's
    ``no-attachment`` absence (B3), never a derivation.

    ``references_override`` exists for the refusal arms that mutate a
    reference document in tests; production callers never pass it.
    ``decoder_docs`` maps the descriptor's decoder pins' digests to
    admitted bytes (the composition's resolution, mirroring
    ``vendor_catalogs``); ``None`` is the SDK's no-descriptor-path
    posture — no decoder resolution, no lanes."""
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
    # The SDK's position (``derive_ui`` runs the slot-conflict check
    # immediately after reference resolution): a multi-fault descriptor
    # raises the same code both sides.
    _check_slot_conflicts(references)
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
    (
        vendor_actions,
        _composed_classes,
        ignored_pins,
        unapplied_classes,
        empty_action_pins,
        member_declarations,
    ) = _vendor_catalog_documents(
        descriptor, vendor_catalogs, catalog_actions, corpus
    )
    catalog_actions.update(vendor_actions)
    # #556 §3 rule 1: the applied member set (per vocabulary), the pins
    # whose members applied nowhere and the dead members inside pins that
    # applied (the B3 fold's F2) — computed from the descriptor here so
    # every consumer reads ONE derivation of application.
    composed_members, unapplied_member_pins, unapplied_members = (
        _composed_member_inventory(member_declarations, descriptor)
    )
    actions = descriptor.get("actions") or {}
    # A descriptor-declared action no served catalog describes is a
    # residual member, not a refusal (issue #556 Track A, design §3.3) —
    # it derives from the descriptor's own input_constraints and its
    # plan row carries resolution "custom". The recoverable
    # ``classref_unknown_action`` refusal this loop carried is retired;
    # the reference-slot site below keeps refusing (D4).
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
            # A platform fault — the profile catalog is served but
            # carries no row for this profile (re-coded since the split,
            # the SDK's own code; still refusing).
            raise _refuse(
                "classref_profile_absent",
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
    # (#556 §4 V1/V6, B4; B5's dataset half) The D4 rule's member half:
    # an APPLIED procedure or configuration member composes a target
    # whose input_schema_id names the catalogue side — an action no
    # served or pinned catalog describes has none, and the canonical
    # validator refuses the target twice over, so the derivation refuses
    # at the claim instead of emitting a document the validator rejects.
    # A member that applies nowhere composes nothing and stays the
    # applied-nowhere disclosure. The dataset kind stays OUT of this rule
    # structurally (B5): its composed target carries
    # measurement_schema_id — the descriptor's pinned measurement
    # contract — never input_schema_id, so there is no catalogue side for
    # the claim to need.
    for declaration in member_declarations:
        for member in declaration.members:
            if member.get("kind") not in ("procedure", "configuration"):
                continue
            if not _member_applies(member, descriptor):
                continue
            claim = next(
                (
                    str(row)
                    for row in member.get("claims") or ()
                    if str(row) in actions
                ),
                None,
            )
            if claim is not None and claim not in catalog_actions:
                raise _refuse(
                    "classref_unknown_action",
                    f"member slot {member.get('slot', '')} names {claim}, "
                    "absent from the served catalogs (the composed target "
                    "needs the catalogue side — pin a vendor catalog row "
                    "carrying input_schema with an $id)",
                )
    return _assemble_triple(
        descriptor,
        descriptor_raw,
        references,
        actions,
        catalog_actions,
        corpus,
        decoder_docs,
        ignored_pins=ignored_pins,
        unapplied_classes=unapplied_classes,
        empty_action_pins=empty_action_pins,
        member_declarations=member_declarations,
        composed_members=composed_members,
        unapplied_member_pins=unapplied_member_pins,
        unapplied_members=unapplied_members,
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
