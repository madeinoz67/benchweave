"""Strict admission of execution-contract documents.

Decodes each admission input with the exact-byte JSON decoder, validates the
five execution-contract documents against the vendored execution/0.1.0
schemas, and verifies the digest pin lattice between them. Device descriptors
are full-form OTDP documents: each validates against the ACTIVE vendored OTDP
descriptor schema (version derived from the vendored standards manifest, never
a hardcoded constant), the S01/S02 semantic mirrors and the gateway-owned
``x-stg-issued-inputs`` extension, then projects the execution view
binding/semantics/coordinator read (CON-10). The package lock keeps a minimal
structural check (id and version strings) — it has no vendored schema.

Structure and pins only for the contract documents: semantic admission
(profile satisfaction, policy envelope evaluation, binding completeness)
belongs to later stages; the descriptor gate's semantic checks are the SDK's
own S01/S02, mirrored here. Every rejection carries a machine-matchable
prefix: ``schema:`` (structure, including the mirrors and the issued map),
``digest_mismatch:`` (a pin disagrees with the bytes it names), or
``pin_absent:`` (a required pin or descriptor is missing). File-level errors
for the given paths propagate unchanged.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

from benchweave.content.json_document import DocumentRejected, load_document
from benchweave.control.provider_settings import (
    ProviderRegistry,
    load_transport_settings,
    provider_contract_validator,
)
from benchweave.measurement.derivation import DerivationRejected, check_derived_variables
from benchweave.standards.manifest import DESCRIPTOR_SCHEMA_NAME, StandardsError
from benchweave.vendoring import contract_family

#: The vendored execution contracts (packaged in the wheel, repo-relative
#: in a dev checkout — :mod:`benchweave.vendoring`).
_CONTRACTS = contract_family("execution/0.1.0")
_PACKAGE_LOCK_FILENAME = "package-lock.json"
_MAX_DOCUMENT_BYTES = 1_048_576

#: The gateway-owned OTDP extension key carrying the issued-input map
#: (action_id -> input fields accepting the gateway-issued token, CTL-7).
#: OTDP tooling ignores x- keys by contract; the gateway refuses an x-map
#: naming an action the descriptor does not declare.
_ISSUED_INPUTS_KEY = "x-stg-issued-inputs"

#: The sanctioned provider sub-namespace (transport-providers §2) and the
#: declaration-site feature_id shape — the provider-contract schema's own
#: pattern, mirrored so a declaration outside ``otdp.transport.<name>/<semver>``
#: can never link to an admissible contract (mirrors the SDK's constants).
_PROVIDER_FEATURE_NAMESPACE = "otdp.transport."
_SANCTIONED_PROVIDER_FEATURE = re.compile(
    r"^otdp\.transport\.[a-z][a-z0-9-]*/[0-9]+\.[0-9]+\.[0-9]+$"
)
_FEATURE_ID = re.compile(r"^[a-z][a-z0-9_.-]*/[0-9]+\.[0-9]+(?:\.[0-9]+)?$")

#: The generic §8.1 transfer kinds (specification §8.1; transport-providers
#: §3): a provider grammar introduces NEW kinds and never shadows one. The
#: set is prose-carried — the vendored runtime schema does not enumerate the
#: transaction kinds — so it is spelled here and moves with the corpus; the
#: spelling test in ``tests/control/test_documents_provider.py`` pins it
#: (extends the record's deferral-8 posture to both sides).
_RESERVED_TRANSFER_KINDS = frozenset(
    {
        "stream_send",
        "stream_receive",
        "stream_exchange",
        "can_receive",
        "can_send",
        "i2c_transfer",
        "spi_transfer",
    }
)

#: The grammar subschema nesting cap, mirrored from the SDK (the same bound
#: the S19 derivation grammar uses — one number governs both grammar depths,
#: well under the metaschema walk's recursion limits).
_GRAMMAR_SUBSCHEMA_MAX_DEPTH = 32

#: The provider-pin read cap — the SDK's bounded-read ``INPUT_BYTE_LIMIT``
#: (presentation.py), mirrored so the two admission lanes agree on the size
#: window (a corpus-valid contract can exceed it: ``description`` carries no
#: maxLength). The cap is a shared resource bound, not a semantic judgement;
#: the census pins the constant equal across lanes.
_PROVIDER_PIN_MAX_BYTES = 262_144

_SCHEMA_FILES = {
    "procedure": "procedure.schema.json",
    "policy": "safety-policy.schema.json",
    "bench": "bench.schema.json",
    "binding": "run-binding.schema.json",
    "commissioning": "commissioning.schema.json",
}

_VALIDATORS: dict[tuple[Path, str], Any] = {}


class AdmissionRejected(ValueError):
    """An admission input failed structure or pin-lattice verification."""


@dataclass(frozen=True)
class AdmittedDocuments:
    procedure: dict[str, Any]
    policy: dict[str, Any]
    bench: dict[str, Any]
    binding: dict[str, Any]
    commissioning: dict[str, Any]
    descriptors: dict[str, dict[str, Any]]  # device_id -> projected descriptor view
    digests: dict[str, str]  # logical name -> sha256 hex


def _validator(schema_filename: str, contracts: Path = _CONTRACTS) -> Any:
    """The execution-schema validator for one corpus directory (cached).

    Keyed per directory so an ACTIVE and a DEV_HEAD composition in one
    process never share a validator — the DEV_HEAD corpus validates the
    capture shapes the frozen-literal corpus refuses.
    """
    key = (contracts, schema_filename)
    validator = _VALIDATORS.get(key)
    if validator is None:
        schema = json.loads((contracts / schema_filename).read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        _VALIDATORS[key] = validator
    return validator


_DESCRIPTOR_CACHE: dict[str, Any] = {}


def _descriptor_validator() -> Any:
    """The ACTIVE vendored OTDP descriptor schema's validator, cached.

    The active version derives from the vendored standards manifest — the
    same authority :func:`benchweave.standards.manifest.validate_identity`
    resolves the descriptor schema by for identity derivation — never a
    hardcoded gateway constant; the schema's ``otdp_version`` const then
    enforces corpus alignment itself. OTDP stays manifest-ACTIVE in every
    composition (the seam is execution-only), so this cache is filename-
    keyed and deliberately separate from the per-corpus execution-schema
    cache.
    """
    validator = _DESCRIPTOR_CACHE.get(DESCRIPTOR_SCHEMA_NAME)
    if validator is None:
        schema = json.loads(
            _otdp_normative_path(DESCRIPTOR_SCHEMA_NAME).read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        _DESCRIPTOR_CACHE[DESCRIPTOR_SCHEMA_NAME] = validator
    return validator


def _otdp_normative_path(document_name: str) -> Path:
    """The vendored path of the one otdp normative file with this name.

    Manifest-derived (the active version is the manifest's, never a
    hardcoded gateway constant); refuses unless the name appears exactly
    once in the otdp entry's normative list.
    """
    # contract_family serves both layouts (``_vendored/contracts`` in a
    # wheel, ``standards`` in a checkout); the corpus root is its parent
    # and carries the standards manifest beside the version dirs.
    corpus = contract_family("otdp").parent
    manifest = json.loads(
        (corpus / "standards-manifest.json").read_text(encoding="utf-8")
    )
    matches = [
        relative
        for entry in manifest["standards"]
        if entry.get("id") == "otdp"
        for relative in entry["normative"]
        if Path(relative).name == document_name
    ]
    if len(matches) != 1:
        raise StandardsError(
            f"otdp_document_unresolved: {document_name} is not named exactly "
            "once in the otdp entry's normative list"
        )
    return corpus / str(matches[0]).removeprefix("standards/")


def _decode(
    path: Path,
    logical: str,
    schema_filename: str | None = None,
    contracts: Path = _CONTRACTS,
) -> tuple[dict[str, Any], str]:
    """Decode ``path`` exactly; return its content and byte digest.

    The digest is computed from the original bytes and the decoder's
    duplicate-key, nonfinite-number and size gates apply. When a schema
    filename is given the document must also validate against it (against
    ``contracts`` — the composition-resolved corpus directory, the module
    default when none is threaded).
    """

    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        document = load_document(raw, digest, max_bytes=_MAX_DOCUMENT_BYTES)
    except DocumentRejected as exc:
        raise AdmissionRejected(f"schema: {logical} ({exc})") from exc
    if schema_filename is not None:
        error = next(
            iter(
                _validator(schema_filename, contracts).iter_errors(
                    document.content
                )
            ),
            None,
        )
        if error is not None:
            raise AdmissionRejected(
                f"schema: {logical} {error.json_path}: {error.message}"
            )
    return document.content, digest


def decode_resolution_document(path: Path, logical: str) -> dict[str, Any]:
    """Exact-byte decode of one document the resolution step reads (typed).

    ``bootstrap.admit_fixture_lattice`` parses the binding and the bench
    before ``admit_documents`` decodes them; those resolution parses run
    through the same exact-byte decoder gates (duplicate keys, non-finite
    numbers, size) so a malformed document refuses with the typed
    ``schema:`` prefix instead of a raw ``JSONDecodeError`` traceback.
    Both documents are decoded again — with their schemas — inside
    ``admit_documents``; this wrapper owns the resolution step's refusal
    channel only.
    """
    document, _digest = _decode(path, logical)
    return document


def _require_string(doc: dict[str, Any], field: str, logical: str) -> None:
    value = doc.get(field)
    if not isinstance(value, str) or not value:
        raise AdmissionRejected(f"schema: {logical} requires non-empty string {field}")


def _check_package_lock(lock: dict[str, Any]) -> None:
    _require_string(lock, "id", "package_lock")
    _require_string(lock, "version", "package_lock")


def _check_semantic_mirrors(logical: str, descriptor: dict[str, Any]) -> None:
    """The SDK's S01/S02 descriptor checks, mirrored at the gateway.

    The SDK is not a gateway dependency (REG-4 pins the protocol by reading
    its tree in tests, not by importing it); the census in
    ``tests/sdk/test_descriptor_equivalence.py`` pins this mirror
    equivalent to ``benchweave_sdk.validation.validate_descriptor`` over
    the in-tree corpus x mutation matrix.
    """
    capabilities = descriptor["capabilities"]
    if len(capabilities) != len(set(capabilities)) or set(capabilities) != set(
        descriptor["operations"]
    ):
        raise AdmissionRejected(
            f"schema: {logical} S01: capabilities and operation policies must match"
        )
    names = [parameter["name"] for parameter in descriptor["parameters"]]
    if len(names) != len(set(names)):
        # Load-bearing for binding: _check_declared_usage builds a set from
        # the names, so a duplicate must be structurally refused, not
        # silently deduped.
        raise AdmissionRejected(f"schema: {logical} S01: parameter names must be unique")
    for parameter in descriptor["parameters"]:
        bounds = parameter.get("range")
        # The dict branch mirrors the SDK's S02 verbatim; the array branch
        # is the live one on 0.2.0-valid documents — the schema admits only
        # the two-number array form, so the SDK's dict branch cannot fire
        # there (the census pins this gateway as strictly stricter).
        reversed_bounds = isinstance(bounds, dict) and bounds.get("min", 0) > bounds.get(
            "max", 0
        )
        if not reversed_bounds and isinstance(bounds, list):
            reversed_bounds = (
                len(bounds) == 2
                and all(
                    isinstance(bound, (int, float)) and not isinstance(bound, bool)
                    for bound in bounds
                )
                and bounds[0] > bounds[1]
            )
        if reversed_bounds:
            raise AdmissionRejected(f"schema: {logical} S02: parameter bounds are reversed")


def _check_issued_map(logical: str, descriptor: dict[str, Any]) -> dict[str, Any]:
    """Validate the gateway-owned issued-input extension; return the map.

    Keys are restricted to declared actions, and each field must be an
    input the target action itself declares (its
    ``input_constraints.properties``); an action declaring no properties
    names no inputs, so no field may be marked issued for it — the
    conservative close. Verifying the fields against the profile catalog's
    canonical action inputs remains the deferred profile-satisfaction
    stage; this closes the in-descriptor silent path (a typo'd field would
    otherwise admit, the executor would mint at exactly that key, and the
    plugin would read only the correctly-spelled one — an optional token's
    absence is legal, so nothing would refuse).
    """
    issued_map = descriptor.get(_ISSUED_INPUTS_KEY)
    if issued_map is None:
        return {}
    if not isinstance(issued_map, dict):
        raise AdmissionRejected(
            f"schema: {logical} issued_map: {_ISSUED_INPUTS_KEY} must be an object "
            "of action_id to a list of input field names"
        )
    for action_id, fields in issued_map.items():
        action = descriptor.get("actions", {}).get(action_id)
        if action is None:
            raise AdmissionRejected(
                f"schema: {logical} issued_map: names undeclared action {action_id!r}"
            )
        if not isinstance(fields, list) or not all(
            isinstance(field, str) for field in fields
        ):
            raise AdmissionRejected(
                f"schema: {logical} issued_map: action {action_id!r} requires "
                "a list of input field names"
            )
        constraints = action.get("input_constraints")
        properties = constraints.get("properties") if isinstance(constraints, dict) else None
        declared = properties if isinstance(properties, dict) else {}
        for field in fields:
            if field not in declared:
                raise AdmissionRejected(
                    f"schema: {logical} issued_map: action {action_id!r} "
                    f"issued field {field!r} is not a declared action input"
                )
    return issued_map


def _check_derived(logical: str, derived: Any) -> None:
    """Run the S19 grammar/static checks; refuse with the derivation prefix.

    A no-op when ``derived`` is None (the descriptor declares none) or
    well-formed; ``DerivationRejected`` becomes an admission refusal
    carrying ``derivation:`` followed by the ``derivation_*:`` reason.
    """
    if derived is None:
        return
    try:
        check_derived_variables(derived)
    except DerivationRejected as exc:
        raise AdmissionRejected(f"schema: {logical} derivation: {exc}") from exc


_KNOWN_FEATURES: frozenset[str] | None = None


def _corpus_known_otdp_features() -> frozenset[str]:
    """The corpus-known ``otdp.*`` feature ids, derived from the vendored tree.

    The gateway mirror of the SDK's derivation (its ``validation.py`` —
    the census pins the two derivations equal at the same vendored
    version): the feature-shaped ``const`` values the ACTIVE vendored
    descriptor schema itself carries (its ``required_features``
    contains-conditions spell the core lanes) plus the vendored catalog's
    ``profiles[].id`` — never hand-listed. Layer 1 of the known-features
    union; layer 2 is the host-admitted set (transport-providers §2).
    """
    global _KNOWN_FEATURES
    if _KNOWN_FEATURES is None:
        schema = json.loads(
            _otdp_normative_path(DESCRIPTOR_SCHEMA_NAME).read_text(encoding="utf-8")
        )
        lanes: set[str] = set()

        def sweep(node: object) -> None:
            if isinstance(node, dict):
                const = node.get("const")
                if isinstance(const, str) and _FEATURE_ID.fullmatch(const):
                    lanes.add(const)
                for value in node.values():
                    sweep(value)
            elif isinstance(node, list):
                for item in node:
                    sweep(item)

        sweep(schema)
        catalog = json.loads(
            _otdp_normative_path("device-profile-catalog.json").read_text(
                encoding="utf-8"
            )
        )
        profiles = {profile["id"] for profile in catalog["profiles"]}
        _KNOWN_FEATURES = frozenset(lanes | profiles)
    return _KNOWN_FEATURES


def _check_provider_placement(logical: str, descriptor: dict[str, Any]) -> None:
    """The §6.4 placement row: a provider declaration rides an adapter-mode
    integration (mirror of the SDK's ``_check_provider_placement``).

    Belt-and-braces post-schema (the schema's declarative row already
    refuses custom+declarative); it earns its keep in the schema-refused
    branch, where the census prefix — not the generic schema error — is
    the actionable refusal (the S19 posture the SDK's
    ``validate_descriptor`` except-branch establishes). Defensive by
    design: a malformed section is a non-event here, the schema or the
    fuller census owns it.
    """
    transport = descriptor.get("transport")
    provider = transport.get("provider") if isinstance(transport, dict) else None
    if not isinstance(provider, dict):
        return
    integration = descriptor.get("integration")
    mode = integration.get("mode") if isinstance(integration, dict) else None
    if mode != "adapter":
        raise AdmissionRejected(
            f"schema: {logical} provider_transport_undeclared: a transport "
            "provider requires the adapter integration mode (specification §6.4)"
        )


def _check_provider_mirror(
    logical: str,
    descriptor: dict[str, Any],
    provider_state: ProviderRegistry | None,
) -> None:
    """S04 extended: provider declarations and the closed ``otdp.*`` namespace.

    The SDK's five census refusals (its ``_check_provider_features``),
    mirrored refusal-for-refusal and in the same order so each single
    fault lands on its named prefix, with one divergence by design: the
    known set is the TWO-LAYER union — corpus-known (layer 1, derived
    above) plus the feature ids of the operator's admitted contracts
    (layer 2). The SDK proves the declaration well-formed; only the
    gateway can prove it admitted.
    """
    transport = descriptor["transport"]
    provider = transport.get("provider")
    required = descriptor["required_features"]
    _check_provider_placement(logical, descriptor)
    if isinstance(provider, dict):
        declared = provider.get("feature_id")
        if (
            not isinstance(declared, str)
            or _SANCTIONED_PROVIDER_FEATURE.fullmatch(declared) is None
        ):
            raise AdmissionRejected(
                f"schema: {logical} provider_transport_undeclared: {declared!r} "
                "is not a sanctioned transport-provider feature id; a "
                "declaration must live in the otdp.transport.<name>/<semver> "
                "sub-namespace exactly (the contract schema's feature_id pattern)"
            )
    if isinstance(provider, dict) and provider.get("feature_id") not in required:
        raise AdmissionRejected(
            f"schema: {logical} provider_feature_missing: "
            f"{provider.get('feature_id')!r} is pinned by the transport "
            "provider but is not in required_features"
        )
    effective = (
        isinstance(provider, dict)
        and transport.get("type") == "custom"
        and descriptor["integration"]["mode"] == "adapter"
    )
    for feature in required:
        if not feature.startswith(_PROVIDER_FEATURE_NAMESPACE):
            continue
        if effective and feature == provider.get("feature_id"):
            continue
        if not isinstance(provider, dict):
            detail = "no transport provider is declared"
        else:
            detail = "the declared provider pins a different feature_id"
        raise AdmissionRejected(
            f"schema: {logical} provider_transport_undeclared: {feature!r} "
            f"is required but {detail}"
        )
    known = _corpus_known_otdp_features()
    if provider_state is not None:
        known = known | provider_state.feature_ids()
    for feature in required:
        if not feature.startswith("otdp.") or feature.startswith(
            _PROVIDER_FEATURE_NAMESPACE
        ):
            continue
        if feature not in known:
            raise AdmissionRejected(
                f"schema: {logical} unknown_otdp_feature: {feature!r} is "
                "neither a corpus feature nor declared through a transport "
                "provider; the otdp.* namespace is corpus-owned"
            )


def _exceeds_depth(node: object, limit: int) -> bool:
    """Whether ``node`` nests containers deeper than ``limit`` (iterative: a
    recursive walker would itself crash on the depth it is measuring)."""
    stack: list[tuple[object, int]] = [(node, 1)]
    while stack:
        current, depth = stack.pop()
        if depth > limit:
            return True
        if isinstance(current, dict):
            stack.extend((value, depth + 1) for value in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
    return False


def _carries_ref(node: object) -> bool:
    """Whether a grammar subschema tree carries any ``$ref`` key anywhere.

    Meta-validation cannot see this hole: ``check_schema`` validates a
    ``$ref``-bearing subschema (references resolve at EVALUATION, not
    meta-validation), and the runtime guard resolves nothing — an
    unresolvable or self-referential grammar would crash transfer outside
    the transaction discipline. Grammar subschemas are inline Draft 2020-12
    by design; a reference is a refusal at admission, never a crash at
    runtime.
    """
    stack: list[object] = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if "$ref" in current:
                return True
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return False


def _validate_provider_contract(
    logical: str, document: dict[str, Any], relative: str
) -> None:
    """A provider contract against the vendored schema plus the checks JSON
    Schema cannot express (mirror of the SDK's ``validate_transport_provider``):
    grammar-subschema meta-validation, the inline-only ``$ref`` ban,
    kind-string uniqueness, reserved-seven disjointness, and the three
    identity equalities."""
    error = next(iter(provider_contract_validator().iter_errors(document)), None)
    if error is not None:
        raise AdmissionRejected(
            f"schema: {logical} provider_contract_invalid: {relative} fails the "
            f"vendored provider-contract schema at {error.json_path}: "
            f"{error.message}"
        )
    grammar = document["transaction_grammar"]
    kinds: list[str] = []
    for entry in grammar:
        kind = entry["kind"]
        if kind in _RESERVED_TRANSFER_KINDS:
            raise AdmissionRejected(
                f"schema: {logical} provider_contract_invalid: grammar kind "
                f"{kind!r} reuses a generic transfer-table kind; a provider "
                "grammar extends the table and never shadows it"
            )
        for field in ("request_schema", "result_schema"):
            if _carries_ref(entry[field]):
                raise AdmissionRejected(
                    f"schema: {logical} provider_contract_invalid: {kind}.{field} "
                    "carries a $ref; grammar subschemas are inline Draft 2020-12 — "
                    "the runtime guard resolves nothing, so a reference would be a "
                    "fail-closed crash, not a grammar"
                )
            if _exceeds_depth(entry[field], _GRAMMAR_SUBSCHEMA_MAX_DEPTH):
                raise AdmissionRejected(
                    f"schema: {logical} provider_contract_invalid: {kind}.{field} "
                    f"nests deeper than {_GRAMMAR_SUBSCHEMA_MAX_DEPTH} levels"
                )
            try:
                Draft202012Validator.check_schema(entry[field])
            except (SchemaError, RecursionError) as exc:
                raise AdmissionRejected(
                    f"schema: {logical} provider_contract_invalid: {kind}.{field} "
                    "is not a valid Draft 2020-12 schema"
                ) from exc
        kinds.append(kind)
    if len(set(kinds)) != len(kinds):
        raise AdmissionRejected(
            f"schema: {logical} provider_contract_invalid: grammar kinds must "
            "be unique strings across transaction_grammar"
        )
    version = document["version"]
    urn_parts = document["id"].split(":")
    urn_name, urn_version = urn_parts[3], urn_parts[4]
    feature_name, _, feature_version = (
        document["feature_id"][len(_PROVIDER_FEATURE_NAMESPACE) :].rpartition("/")
    )
    if urn_version != version:
        raise AdmissionRejected(
            f"schema: {logical} provider_contract_invalid: {relative}: the id "
            f"embeds version {urn_version!r} but the contract is version "
            f"{version!r}"
        )
    if feature_version != version:
        raise AdmissionRejected(
            f"schema: {logical} provider_contract_invalid: {relative}: the "
            f"feature_id embeds version {feature_version!r} but the contract "
            f"is version {version!r}"
        )
    if feature_name != urn_name:
        raise AdmissionRejected(
            f"schema: {logical} provider_contract_invalid: {relative}: the "
            f"feature_id names {feature_name!r} but the id names {urn_name!r}"
        )


def _verify_provider_pin(
    logical: str, descriptor: dict[str, Any], descriptor_path: Path
) -> None:
    """Resolve and verify the descriptor's pinned provider contract.

    Mirror of the SDK's ``verify_provider_pin``, run at descriptor
    admission (the S14-family gateway row): the triple resolves
    DESCRIPTOR-relative (the descriptor's own directory — the plugin and
    its pinned contract travel one package), strict no-follow on symlinks
    (the SDK's stricter posture, held on both sides knowingly), hash
    against the pinned ``sha256``, decode through the exact-byte decoder
    (strict UTF-8 — a BOM'd or UTF-16 contract refuses HERE and only here:
    the sanctioned gateway-stricter census cell), then the vendored
    provider schema plus the beyond-schema mirror checks, then the
    declaration-agreement pair (feature_id AND id — the AR-6 SDK-added
    equality kept gateway-side knowingly: the pin names the reviewed
    document, and the gateway is the authority moment for that name).
    """
    transport = descriptor.get("transport")
    provider = transport.get("provider") if isinstance(transport, dict) else None
    if provider is None:
        return  # no declaration: the honestly-incomplete custom posture
    if not isinstance(provider, dict):
        raise AdmissionRejected(
            f"schema: {logical} provider_contract_invalid: the transport "
            f"provider declaration is a {type(provider).__name__}, not an object"
        )
    relative = provider.get("path")
    if (
        not isinstance(relative, str)
        or not relative
        or "\\" in relative
        or ":" in relative
        or PurePosixPath(relative).is_absolute()
        or any(part in (".", "..") for part in relative.split("/"))
        or any(not part for part in relative.split("/"))
    ):
        raise AdmissionRejected(
            f"schema: {logical} provider_contract_missing: {relative!r} is not "
            "a package-relative pin path"
        )
    package_root = descriptor_path.parent
    target = package_root
    try:
        for part in PurePosixPath(relative).parts:
            target = target / part
            if target.is_symlink():
                raise AdmissionRejected(
                    f"schema: {logical} provider_contract_missing: {relative!r} "
                    "crosses a symlink; provider pins resolve through a "
                    "strict no-follow posture"
                )
        if not target.is_file() or not target.resolve().is_relative_to(
            package_root.resolve()
        ):
            raise AdmissionRejected(
                f"schema: {logical} provider_contract_missing: {relative!r} "
                "does not name a contained regular file in the descriptor's "
                "package"
            )
        size = target.stat().st_size
        if size > _PROVIDER_PIN_MAX_BYTES:
            raise AdmissionRejected(
                f"schema: {logical} provider_contract_invalid: {relative!r} is "
                f"{size} bytes, above the {_PROVIDER_PIN_MAX_BYTES}-byte "
                "provider-pin read cap (the SDK's bounded-read bound, mirrored "
                "so both admission lanes agree on the window); the cap is a "
                "shared resource bound, not a semantic disagreement with the "
                "contract"
            )
        raw = target.read_bytes()
    except OSError as exc:
        # ENAMETOOLONG, permission-denied, the race faces: pins this check
        # could not resolve or read. The message names the relative pin and
        # the errno only — the OSError's own text carries the absolute host
        # path, which is not ours to print.
        raise AdmissionRejected(
            f"schema: {logical} provider_contract_missing: {relative!r} could "
            f"not be resolved or read (os error {exc.errno})"
        ) from exc
    pinned = provider.get("sha256")
    if not isinstance(pinned, str):
        raise AdmissionRejected(
            f"schema: {logical} provider_contract_invalid: the declaration "
            f"pinning {relative!r} carries no sha256 digest to verify against"
        )
    digest = hashlib.sha256(raw).hexdigest()
    if digest != pinned:
        raise AdmissionRejected(
            f"digest_mismatch: {logical} provider_contract_hash_mismatch: "
            f"{relative!r} hashes to {digest} but the descriptor pins {pinned}"
        )
    try:
        contract = load_document(raw, digest, max_bytes=_PROVIDER_PIN_MAX_BYTES)
    except DocumentRejected as exc:
        raise AdmissionRejected(
            f"schema: {logical} provider_contract_invalid: {relative!r} ({exc}); "
            "provider pins decode through the exact-byte decoder (strict UTF-8)"
        ) from exc
    _validate_provider_contract(logical, contract.content, relative)
    if (
        contract.content.get("feature_id") != provider.get("feature_id")
        or contract.content.get("id") != provider.get("id")
    ):
        raise AdmissionRejected(
            f"schema: {logical} provider_contract_invalid: the pinned contract "
            f"at {relative!r} does not declare the descriptor's provider "
            "feature and identity"
        )


def _check_provider_admission(
    logical: str,
    descriptor: dict[str, Any],
    provider_state: ProviderRegistry | None,
    now_wall: str | None,
) -> None:
    """The gateway-only admission row (design §1.1b): ``provider_not_admitted:``.

    A gateway-owned prefix in the ``issued_map:`` tradition — the SDK
    cannot see commissioned state, so no offline prefix exists and none is
    invented offline. Fires, with typed detail naming the failed axis,
    when the declared triple is not exactly an admitted triple, when the
    approval is expired (arithmetic on declared values against the
    caller-supplied ``now_wall`` — never an ambient clock read), or when
    ``connection_key`` does not resolve to a connection bound to the SAME
    admitted contract (S12-extended: exact id+version+sha256). A missing
    settings document refuses every provider-declaring descriptor — the
    closed default (A02).
    """
    transport = descriptor.get("transport")
    if not isinstance(transport, dict):
        return
    provider = transport.get("provider")
    if not isinstance(provider, dict):
        return
    # The declaration carries no version field of its own — the URN embeds
    # it, and the contract-side identity equality (urn-embedded version ==
    # contract version) makes the URN's segment THE declared version.
    provider_id = provider.get("id")
    urn_parts = str(provider_id).split(":") if isinstance(provider_id, str) else []
    declared_version = urn_parts[4] if len(urn_parts) == 5 else None
    declared_triple = (provider_id, declared_version, provider.get("sha256"))
    if provider_state is None:
        raise AdmissionRejected(
            f"provider_not_admitted: {logical} declares transport provider "
            f"{provider_id!r} but no transport settings document is "
            "configured; the closed default refuses provider-declaring "
            "descriptors (A02)"
        )
    entry = provider_state.find(*declared_triple)
    if entry is None:
        raise AdmissionRejected(
            f"provider_not_admitted: {logical} declares "
            f"{provider_id}@{declared_version} "
            f"({str(provider.get('sha256'))[:12]}…) and no admitted contract "
            "carries that exact triple"
        )
    if now_wall is None:
        raise AdmissionRejected(
            f"provider_not_admitted: {logical} declares "
            f"{provider_id}@{declared_version} but no now_wall was supplied "
            "to judge the approval's expiry; freshness cannot be assumed (A04)"
        )
    approval = entry.document.get("approval")
    expires_raw = approval.get("expires_at") if isinstance(approval, dict) else None
    try:
        expires = datetime.fromisoformat(str(expires_raw))
        now = datetime.fromisoformat(now_wall)
        expired = now >= expires
    except (TypeError, ValueError) as exc:
        raise AdmissionRejected(
            f"provider_not_admitted: {logical}: the approval expiry "
            f"({expires_raw!r}) cannot be compared against now_wall "
            f"{now_wall!r}: {exc}"
        ) from exc
    if expired:
        raise AdmissionRejected(
            f"provider_not_admitted: {provider_id}@{declared_version} "
            f"approval expired at {expires_raw} (now_wall {now_wall}) — an "
            "expired approval is not an admitted contract"
        )
    key = transport.get("connection_key")
    bound = provider_state.resolve_connection(key)
    if bound is None or (bound.id, bound.version, bound.sha256) != declared_triple:
        detail = (
            "does not resolve to a connection"
            if bound is None
            else f"is bound to a different admitted contract ({bound.id})"
        )
        raise AdmissionRejected(
            f"provider_not_admitted: {logical}: connection key {key!r} "
            f"{detail} backing the declared triple "
            f"{provider_id}@{declared_version}"
        )


def _project_full_form(
    device_id: str,
    descriptor: dict[str, Any],
    provider_state: ProviderRegistry | None = None,
) -> dict[str, Any]:
    """Validate a full-form OTDP descriptor; project the execution view.

    Schema first (the active vendored corpus schema), then the S01/S02
    mirrors, then the issued-input extension, then the projection — a
    total function of the schema-guaranteed fields, so nothing downstream
    can see an unvalidated shape.
    """
    logical = f"descriptor[{device_id}]"
    derived = descriptor.get("derived_variables")
    error = next(iter(_descriptor_validator().iter_errors(descriptor)), None)
    if error is not None:
        # Mirror the SDK's precedence (validate_descriptor's except branch):
        # when derived_variables is present, the S19 grammar/static checks
        # run even on a schema-invalid document, because the derivation_*
        # reason is the actionable one for the author and both checkers
        # then agree on the reason. The gateway runs them for ANY present
        # value, not only lists, so a non-list array keeps the
        # derivation_shape refusal this seam has always pinned; otherwise
        # the schema refusal stands. The provider placement row joins it
        # (§6.4): a custom+declarative provider declaration refuses with
        # its census prefix, not the generic schema error.
        _check_derived(logical, derived)
        _check_provider_placement(logical, descriptor)
        raise AdmissionRejected(f"schema: {logical} {error.json_path}: {error.message}")
    _check_semantic_mirrors(logical, descriptor)
    _check_provider_mirror(logical, descriptor, provider_state)
    issued_map = _check_issued_map(logical, descriptor)
    if derived is not None:
        # Same admission posture as the slim branch: grammar and static
        # checks here (M15/S19), operand existence and unit agreement at
        # evaluation time.
        _check_derived(logical, derived)
    actions: list[dict[str, Any]] = []
    for action_id in descriptor.get("actions", {}):
        entry: dict[str, Any] = {"action_id": action_id}
        fields = issued_map.get(action_id, [])
        if fields:
            entry["issued"] = list(fields)
        actions.append(entry)
    view: dict[str, Any] = {
        "id": descriptor["id"],
        "version": descriptor["descriptor_version"],
        "profiles": list(descriptor.get("profiles", [])),
        "parameters": [parameter["name"] for parameter in descriptor["parameters"]],
        "actions": actions,
        # The capture surface (CON-10, issue #176 increment 2): the
        # artifact_writer permission flag and, when the descriptor carries
        # BOTH capture keys, the declared formats and limits the
        # admission-time CTL-7 mirror reads. OTDP 0.2.2 pairs the keys
        # only under the `capture` capability conditional — a descriptor
        # may legally declare formats without limits, limits without
        # formats, or neither — so the both-or-neither conjunction here
        # (and the mirror's requirement of both) is the gateway's
        # intentional conservative posture: a half-declared capture
        # surface grants no capture surface. A transport-only adapter
        # reads False with no capture keys — no permission is granted by a
        # malformed shape (the adapter_permissions posture, projected).
        "artifact_writer": "artifact_writer" in adapter_permissions(descriptor),
    }
    capture_formats = descriptor.get("capture_formats")
    capture_limits = descriptor.get("capture_limits")
    if isinstance(capture_formats, list) and isinstance(capture_limits, dict):
        view["capture_formats"] = [
            fmt for fmt in capture_formats if isinstance(fmt, str)
        ]
        view["capture_limits"] = {
            str(key): capture_limits[key]
            for key in ("max_samples", "max_bytes")
            if key in capture_limits
        }
    if derived is not None:
        view["derived_variables"] = derived
    return view


def _project_descriptor(
    device_id: str,
    descriptor: dict[str, Any],
    provider_state: ProviderRegistry | None = None,
) -> dict[str, Any]:
    """Validate one descriptor and return the execution view (CON-10).

    A device descriptor is a full-form OTDP document: it validates against
    the active vendored schema plus the S01/S02 mirrors and the gateway's
    issued-input extension, then projects the execution view binding,
    semantics and the coordinator read. The pre-conversion slim list
    dialect is refused — it fails the schema; a descriptor that is not
    OTDP-valid is not execution-admissible.
    """
    # The CON-10 anchor: the single admission path. The dual-accept branch
    # that lived here during the tree conversion is gone by design — do not
    # hunt for it; the slim-death control (test_documents_fullform) pins its
    # absence.
    return _project_full_form(device_id, descriptor, provider_state)


def _verify_pin(
    pin: dict[str, Any],
    source: str,
    logical: str,
    doc_id: str,
    version: str,
    digest: str,
) -> None:
    """Verify a full ``{id, version, sha256}`` pin against the named document."""

    if pin.get("sha256") != digest:
        raise AdmissionRejected(
            f"digest_mismatch: {source} pins {logical} sha256 {pin.get('sha256')}, "
            f"bytes hash to {digest}"
        )
    if pin.get("id") != doc_id or pin.get("version") != version:
        raise AdmissionRejected(
            f"digest_mismatch: {source} pins {logical} as {pin.get('id')}@{pin.get('version')}, "
            f"document declares {doc_id}@{version}"
        )


def _check_allow_rule_constraints(logical: str, policy: dict[str, Any]) -> None:
    """Meta-validate every allow-rule constraints document (L2-F1(a)).

    The safety-policy schema types each constraints member as a plain
    object — any object validates, including one JSON Schema cannot
    evaluate (an unknown ``type``, a non-object ``properties``). Without
    this row the malformed document admits and crashes ``check_allowed``
    mid-body, PAST PROTECTION. The checker lane already runs
    ``check_schema`` over the examples' constraints
    (``scripts/architecture/check_execution.py``); admission now does it
    for every admitted policy, so the refusal is ``schema:`` before any
    run exists. ``RecursionError`` mirrors the provider-contract row.
    """
    for index, rule in enumerate(policy.get("allow_rules") or []):
        if not isinstance(rule, dict):
            continue  # the document schema owns the rule's own shape
        for key in ("input_constraints", "value_constraints", "capture_constraints"):
            constraints = rule.get(key)
            if constraints is None:
                continue
            try:
                Draft202012Validator.check_schema(constraints)
            except (SchemaError, RecursionError) as exc:
                raise AdmissionRejected(
                    f"schema: {logical} allow_rules[{index}].{key} is not a "
                    f"valid Draft 2020-12 schema: {exc}"
                ) from exc


def admit_documents(
    procedure_path: Path,
    policy_path: Path,
    bench_path: Path,
    binding_path: Path,
    commissioning_path: Path,
    descriptor_paths: dict[str, Path],
    *,
    provider_settings: Path | None = None,
    now_wall: str | None = None,
    contracts: Path = _CONTRACTS,
) -> AdmittedDocuments:
    """Admit an execution document set or raise :class:`AdmissionRejected`.

    All five contract documents are decoded with the exact-byte decoder and
    validated against their vendored execution schemas (``contracts`` — the
    composition-resolved corpus directory; the module default is the frozen
    ``execution/0.1.0`` literal, the ACTIVE posture), then the full
    pin lattice is verified: the binding pins procedure, bench, policy,
    package lock and commissioning; the bench pins policy, package lock and
    every device descriptor, and names the commissioning; the commissioning
    pins bench, policy, package lock and lists the procedure; the procedure
    names the policy. The package lock is resolved as
    ``bench_path.parent / "package-lock.json"``.

    The provider lane (issue #147 increment 3): ``provider_settings`` names
    the operator's ``transport-settings.json``; it validates BEFORE any
    descriptor is projected (fail-at-startup, the #85 posture — a
    :class:`~benchweave.control.provider_settings.SettingsRejected`
    propagates with its own typed prefixes). A provider-declaring
    descriptor then passes the census mirror (inside the projection), the
    descriptor-relative pin verification, and the gateway-only
    ``provider_not_admitted:`` admission row judged against ``now_wall``
    (caller-supplied; expiry is arithmetic on declared values, never an
    ambient clock read). A provider-less lattice is untouched by every
    check above.
    """
    provider_state: ProviderRegistry | None = None
    if provider_settings is not None:
        provider_state = load_transport_settings(provider_settings)

    procedure, procedure_digest = _decode(
        procedure_path, "procedure", _SCHEMA_FILES["procedure"], contracts
    )
    policy, policy_digest = _decode(
        policy_path, "policy", _SCHEMA_FILES["policy"], contracts
    )
    bench, bench_digest = _decode(bench_path, "bench", _SCHEMA_FILES["bench"], contracts)
    binding, binding_digest = _decode(
        binding_path, "binding", _SCHEMA_FILES["binding"], contracts
    )
    commissioning, commissioning_digest = _decode(
        commissioning_path, "commissioning", _SCHEMA_FILES["commissioning"], contracts
    )
    lock, lock_digest = _decode(bench_path.parent / _PACKAGE_LOCK_FILENAME, "package_lock")
    _check_package_lock(lock)
    _check_allow_rule_constraints("policy", policy)

    _verify_pin(
        bench["policy"],
        "bench",
        "policy",
        doc_id=policy["id"],
        version=policy["version"],
        digest=policy_digest,
    )
    _verify_pin(
        bench["package_lock"],
        "bench",
        "package_lock",
        doc_id=lock["id"],
        version=lock["version"],
        digest=lock_digest,
    )
    if bench["commissioning_id"] != commissioning["id"]:
        raise AdmissionRejected(
            f"digest_mismatch: bench.commissioning_id {bench['commissioning_id']!r} "
            f"does not name commissioning {commissioning['id']!r}"
        )
    procedure_reference = procedure["safety_policy"]
    if (
        procedure_reference["id"] != policy["id"]
        or procedure_reference["version"] != policy["version"]
    ):
        raise AdmissionRejected(
            "digest_mismatch: procedure.safety_policy names "
            f"{procedure_reference['id']}@{procedure_reference['version']}, "
            f"policy document declares {policy['id']}@{policy['version']}"
        )

    _verify_pin(
        commissioning["bench"],
        "commissioning",
        "bench",
        doc_id=bench["id"],
        version=bench["version"],
        digest=bench_digest,
    )
    _verify_pin(
        commissioning["policy"],
        "commissioning",
        "policy",
        doc_id=policy["id"],
        version=policy["version"],
        digest=policy_digest,
    )
    _verify_pin(
        commissioning["package_lock"],
        "commissioning",
        "package_lock",
        doc_id=lock["id"],
        version=lock["version"],
        digest=lock_digest,
    )
    procedure_ref = next(
        (
            ref
            for ref in commissioning["procedure_refs"]
            if ref["id"] == procedure["id"] and ref["version"] == procedure["version"]
        ),
        None,
    )
    if procedure_ref is None:
        raise AdmissionRejected(
            f"pin_absent: commissioning.procedure_refs lacks "
            f"{procedure['id']}@{procedure['version']}"
        )
    _verify_pin(
        procedure_ref,
        "commissioning.procedure_refs",
        "procedure",
        doc_id=procedure["id"],
        version=procedure["version"],
        digest=procedure_digest,
    )

    device_pins: dict[str, Any] = {}
    for device in bench["devices"]:
        device_pins.setdefault(str(device["id"]), device["descriptor"])
    missing = sorted(set(device_pins) - set(descriptor_paths))
    if missing:
        raise AdmissionRejected(f"pin_absent: no descriptor provided for device(s) {missing}")
    extra = sorted(set(descriptor_paths) - set(device_pins))
    if extra:
        raise AdmissionRejected(f"pin_absent: bench pins no descriptor for device(s) {extra}")

    descriptors: dict[str, dict[str, Any]] = {}
    descriptor_digests: dict[str, str] = {}
    for device_id, pin in device_pins.items():
        descriptor, descriptor_digest = _decode(
            descriptor_paths[device_id], f"descriptor[{device_id}]"
        )
        view = _project_descriptor(device_id, descriptor, provider_state)
        # The pin verifies against the RAW document's identity and the RAW
        # bytes' digest; consumers see the projected view.
        _verify_pin(
            pin,
            f"bench.devices[{device_id}].descriptor",
            "descriptor",
            doc_id=descriptor["id"],
            version=view["version"],
            digest=descriptor_digest,
        )
        # The provider rows mirror the SDK check lane's order — census
        # (inside the projection above), then the descriptor-relative pin —
        # with the gateway-only admission row last: only the gateway can
        # see commissioned state.
        _verify_provider_pin(
            f"descriptor[{device_id}]", descriptor, descriptor_paths[device_id]
        )
        _check_provider_admission(
            f"descriptor[{device_id}]", descriptor, provider_state, now_wall
        )
        descriptors[device_id] = view
        descriptor_digests[f"descriptor/{device_id}"] = descriptor_digest

    pinned_by_binding = {
        "procedure": (procedure, procedure_digest),
        "bench": (bench, bench_digest),
        "policy": (policy, policy_digest),
        "package_lock": (lock, lock_digest),
        "commissioning": (commissioning, commissioning_digest),
    }
    for logical, (doc, digest) in pinned_by_binding.items():
        _verify_pin(
            binding[logical],
            "binding",
            logical,
            doc_id=doc["id"],
            version=doc["version"],
            digest=digest,
        )

    digests = {
        "procedure": procedure_digest,
        "policy": policy_digest,
        "bench": bench_digest,
        "binding": binding_digest,
        "commissioning": commissioning_digest,
        "package_lock": lock_digest,
        **descriptor_digests,
    }
    return AdmittedDocuments(
        procedure=procedure,
        policy=policy,
        bench=bench,
        binding=binding,
        commissioning=commissioning,
        descriptors=descriptors,
        digests=digests,
    )


def adapter_permissions(descriptor: dict[str, Any]) -> frozenset[str]:
    """The adapter's declared permission set from a RAW full-form descriptor.

    The CON-10 projected execution view deliberately drops ``integration``,
    so post-admission callers cannot read permissions from what they hold —
    the capture factory re-derives the raw form by pinned digest (one
    ``get_document`` call) and reads this. Total: absent integration (the
    declarative mode), a missing adapter, a non-list or non-string-bearing
    permissions field all yield the empty set — no permission is granted by
    a malformed shape. The vocabulary lives in the descriptor schema's
    ``$defs.adapter.properties.permissions``; slice 1 gates only on
    ``artifact_writer``.
    """
    integration = descriptor.get("integration")
    if not isinstance(integration, dict):
        return frozenset()
    adapter = integration.get("adapter")
    if not isinstance(adapter, dict):
        return frozenset()
    permissions = adapter.get("permissions")
    if not isinstance(permissions, list):
        return frozenset()
    return frozenset(
        permission for permission in permissions if isinstance(permission, str)
    )
