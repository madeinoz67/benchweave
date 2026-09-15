"""Strict admission of execution-contract documents.

Decodes each admission input with the exact-byte JSON decoder, validates the
five execution-contract documents against the vendored execution/1.0.0
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
from benchweave.vendoring import contract_family

#: The vendored execution contracts (packaged in the wheel, repo-relative
#: in a dev checkout — :mod:`benchweave.vendoring`).
_CONTRACTS = contract_family("execution/1.0.0")
_PACKAGE_LOCK_FILENAME = "package-lock.json"
_MAX_DOCUMENT_BYTES = 1_048_576

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
    descriptors: dict[str, dict[str, Any]]  # device_id -> descriptor doc
    digests: dict[str, str]  # logical name -> sha256 hex


def _validator(schema_filename: str) -> Any:
    validator = _VALIDATORS.get(schema_filename)
    if validator is None:
        schema = json.loads((_CONTRACTS / schema_filename).read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        _VALIDATORS[schema_filename] = validator
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
    validated against their vendored execution/1.0.0 schemas, then the full
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
        _check_descriptor(device_id, descriptor)
        _verify_pin(
            pin,
            f"bench.devices[{device_id}].descriptor",
            "descriptor",
            doc_id=descriptor["id"],
            version=descriptor["version"],
            digest=descriptor_digest,
        )
        descriptors[device_id] = descriptor
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
