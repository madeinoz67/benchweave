"""Strict admission of execution-contract documents.

Decodes each admission input with the exact-byte JSON decoder, validates the
five execution-contract documents against the vendored execution/0.1.0
schemas, and verifies the digest pin lattice between them. The package lock
and device descriptors have no vendored schema this work package, so they are
decoded exactly and gated by a minimal structural check instead.

Structure and pins only: semantic admission (profile satisfaction, policy
envelope evaluation, binding completeness) belongs to later stages. Every
rejection carries a machine-matchable prefix: ``schema:`` (structure),
``digest_mismatch:`` (a pin disagrees with the bytes it names), or
``pin_absent:`` (a required pin or descriptor is missing). File-level errors
for the given paths propagate unchanged.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from benchweave.content.json_document import DocumentRejected, load_document
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

_SCHEMA_FILES = {
    "procedure": "procedure.schema.json",
    "policy": "safety-policy.schema.json",
    "bench": "bench.schema.json",
    "binding": "run-binding.schema.json",
    "commissioning": "commissioning.schema.json",
}

_VALIDATORS: dict[str, Any] = {}


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


def _validator(schema_filename: str) -> Any:
    validator = _VALIDATORS.get(schema_filename)
    if validator is None:
        schema = json.loads((_CONTRACTS / schema_filename).read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        _VALIDATORS[schema_filename] = validator
    return validator


def _descriptor_validator() -> Any:
    """The ACTIVE vendored OTDP descriptor schema's validator, cached.

    The active version derives from the vendored standards manifest — the
    same authority :func:`benchweave.standards.manifest.validate_identity`
    resolves the descriptor schema by for identity derivation — never a
    hardcoded gateway constant; the schema's ``otdp_version`` const then
    enforces corpus alignment itself.
    """
    validator = _VALIDATORS.get(DESCRIPTOR_SCHEMA_NAME)
    if validator is None:
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
            if Path(relative).name == DESCRIPTOR_SCHEMA_NAME
        ]
        if len(matches) != 1:
            raise StandardsError(
                f"descriptor_schema_unresolved: {DESCRIPTOR_SCHEMA_NAME} is not "
                "named exactly once in the otdp entry's normative list"
            )
        schema = json.loads(
            (corpus / matches[0].removeprefix("standards/")).read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        _VALIDATORS[DESCRIPTOR_SCHEMA_NAME] = validator
    return validator


def _decode(
    path: Path, logical: str, schema_filename: str | None = None
) -> tuple[dict[str, Any], str]:
    """Decode ``path`` exactly; return its content and byte digest.

    The digest is computed from the original bytes and the decoder's
    duplicate-key, nonfinite-number and size gates apply. When a schema
    filename is given the document must also validate against it.
    """

    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        document = load_document(raw, digest, max_bytes=_MAX_DOCUMENT_BYTES)
    except DocumentRejected as exc:
        raise AdmissionRejected(f"schema: {logical} ({exc})") from exc
    if schema_filename is not None:
        error = next(iter(_validator(schema_filename).iter_errors(document.content)), None)
        if error is not None:
            raise AdmissionRejected(f"schema: {logical} {error.json_path}: {error.message}")
    return document.content, digest


def _require_string(doc: dict[str, Any], field: str, logical: str) -> None:
    value = doc.get(field)
    if not isinstance(value, str) or not value:
        raise AdmissionRejected(f"schema: {logical} requires non-empty string {field}")


def _require_string_list(doc: dict[str, Any], field: str, logical: str) -> None:
    value = doc.get(field)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AdmissionRejected(f"schema: {logical} requires {field} to be a list of strings")


def _check_package_lock(lock: dict[str, Any]) -> None:
    _require_string(lock, "id", "package_lock")
    _require_string(lock, "version", "package_lock")


def _check_descriptor(device_id: str, descriptor: dict[str, Any]) -> None:
    logical = f"descriptor[{device_id}]"
    _require_string(descriptor, "id", logical)
    _require_string(descriptor, "version", logical)
    _require_string_list(descriptor, "profiles", logical)
    _require_string_list(descriptor, "parameters", logical)
    actions = descriptor.get("actions")
    if not isinstance(actions, list):
        raise AdmissionRejected(f"schema: {logical} requires actions to be a list")
    for action in actions:
        if not isinstance(action, dict):
            raise AdmissionRejected(f"schema: {logical} requires each action to be an object")
        _require_string(action, "action_id", f"{logical} action")
        if "issued" in action and (
            not isinstance(action["issued"], list)
            or not all(isinstance(item, str) for item in action["issued"])
        ):
            raise AdmissionRejected(
                f"schema: {logical} action {action.get('action_id')!r} requires "
                "issued to be a list of strings"
            )
    # OTDP 0.1.2 M15/S19: grammar and static checks at admission, so a
    # malformed expression cannot reach a run. NOT checked here: operand
    # existence (datasets vary by action) and unit agreement (operand
    # units live in datasets) — both are evaluation-time in
    # benchweave.measurement.derivation.
    _check_derived(logical, descriptor.get("derived_variables"))


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

    Shape-checked only (action_id -> list of strings, keys restricted to
    declared actions): verifying the field names against the profile
    catalog's action inputs is the deferred profile-satisfaction stage.
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
        if action_id not in descriptor.get("actions", {}):
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


def _project_full_form(device_id: str, descriptor: dict[str, Any]) -> dict[str, Any]:
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
        # the schema refusal stands.
        _check_derived(logical, derived)
        raise AdmissionRejected(f"schema: {logical} {error.json_path}: {error.message}")
    _check_semantic_mirrors(logical, descriptor)
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
    }
    if derived is not None:
        view["derived_variables"] = derived
    return view


def _project_descriptor(device_id: str, descriptor: dict[str, Any]) -> dict[str, Any]:
    """Validate one descriptor and return the execution view (CON-10).

    A full-form OTDP descriptor (the single descriptor dialect) validates
    against the active vendored schema plus the mirrors and the issued
    extension, and projects the slim view binding, semantics and the
    coordinator read. The legacy slim dialect is still structurally gated
    and passes through as its own view (the dual-accept interim of issue
    #63; the tree converts and the slim branch dies there).
    """
    if "otdp_version" in descriptor:
        return _project_full_form(device_id, descriptor)
    _check_descriptor(device_id, descriptor)
    return descriptor


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


def admit_documents(
    procedure_path: Path,
    policy_path: Path,
    bench_path: Path,
    binding_path: Path,
    commissioning_path: Path,
    descriptor_paths: dict[str, Path],
) -> AdmittedDocuments:
    """Admit an execution document set or raise :class:`AdmissionRejected`.

    All five contract documents are decoded with the exact-byte decoder and
    validated against their vendored execution/0.1.0 schemas, then the full
    pin lattice is verified: the binding pins procedure, bench, policy,
    package lock and commissioning; the bench pins policy, package lock and
    every device descriptor, and names the commissioning; the commissioning
    pins bench, policy, package lock and lists the procedure; the procedure
    names the policy. The package lock is resolved as
    ``bench_path.parent / "package-lock.json"``.
    """

    procedure, procedure_digest = _decode(
        procedure_path, "procedure", _SCHEMA_FILES["procedure"]
    )
    policy, policy_digest = _decode(policy_path, "policy", _SCHEMA_FILES["policy"])
    bench, bench_digest = _decode(bench_path, "bench", _SCHEMA_FILES["bench"])
    binding, binding_digest = _decode(binding_path, "binding", _SCHEMA_FILES["binding"])
    commissioning, commissioning_digest = _decode(
        commissioning_path, "commissioning", _SCHEMA_FILES["commissioning"]
    )
    lock, lock_digest = _decode(bench_path.parent / _PACKAGE_LOCK_FILENAME, "package_lock")
    _check_package_lock(lock)

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
        view = _project_descriptor(device_id, descriptor)
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
