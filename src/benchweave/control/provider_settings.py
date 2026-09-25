"""The commissioned transport-settings surface (issue #147 increment 3).

The identity axis of the execution contract's commissioned-state sentence
(``standards/execution/0.2.0/execution-contract.md``: "The connection key
resolves through administrator-owned transport settings and secret storage;
it is not an endpoint supplied by the procedure") realized NOW as
gateway-local validated configuration — the #43 retention-policy precedent
(owner call 2): gateway-local carrier today, commissioning promotion on a
named trigger (design deferral 2 / record deferral 3).

The document: an operator-owned, optional ``transport-settings.json`` in the
fixtures directory (the administrator-configuration locus), validated
against a schema in gateway source — NOT corpus: provider instances are
deliberately versioned elsewhere (transport-providers §1). Identity only:
the contract triple plus the ``connection_key`` binding. **No field can
express an endpoint, path target, process, credential or secret — by
schema, not by policy** (``additionalProperties: false`` throughout; every
string is pattern-constrained except the settings-relative document name,
which carries the package-relative path rules). Extension-contract §6's "no
direct unrestricted SDK/filesystem/network access" stays truthful in the
only way that survives review drift: this surface cannot express the thing
it must not grant. Endpoint and secret configuration arrives with the first
runtime implementation through the deferred operator admission surface,
never here.

Nothing in the execution lattice pins this file. Its authority is the
operator's file act plus its internal consistency; promotion into the
commissioning shape (pinned, expiring with the commissioning) is the
deferred execution-standard row's. Refusals carry the typed
``settings_schema:`` / ``settings_digest_mismatch:`` prefixes,
machine-matchable like every other admission refusal, and every document
named here decodes through the exact-byte decoder (duplicate keys,
non-finite numbers, size, strict UTF-8).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from benchweave.content.json_document import DocumentRejected, load_document
from benchweave.standards.manifest import StandardsError
from benchweave.vendoring import contract_family

#: The one settings filename the bootstrap seam looks for (optional).
TRANSPORT_SETTINGS_FILENAME = "transport-settings.json"

#: The admission byte cap shared with every other admission document.
_MAX_SETTINGS_BYTES = 1_048_576

#: The vendored provider-contract schema's normative name — resolved
#: manifest-derived exactly like ``documents._descriptor_validator`` resolves
#: the descriptor schema (never a hardcoded path; the active version is the
#: manifest's, and the manifest names it exactly once).
PROVIDER_SCHEMA_NAME = "otdp-transport-provider.schema.json"

#: The identity-only settings schema (gateway source, not corpus). Every
#: string pattern mirrors the corpus authority it names: the provider urn,
#: version and feature_id patterns are the provider schema's own; the
#: connection_key pattern is the descriptor schema's customTransport one.
TRANSPORT_SETTINGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "config_version": {"const": "1"},
        "admitted": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "pattern": (
                            "^urn:otdp:transport-provider:"
                            "[a-z][a-z0-9-]*:[0-9]+\\.[0-9]+\\.[0-9]+$"
                        ),
                    },
                    "version": {
                        "type": "string",
                        "pattern": "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$",
                    },
                    "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                    "feature_id": {
                        "type": "string",
                        "pattern": (
                            "^otdp\\.transport\\.[a-z][a-z0-9-]*/"
                            "[0-9]+\\.[0-9]+\\.[0-9]+$"
                        ),
                    },
                    "document": {"type": "string", "minLength": 1},
                },
                "required": ["id", "version", "sha256", "feature_id", "document"],
                "additionalProperties": False,
            },
        },
        "connections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "connection_key": {
                        "type": "string",
                        "pattern": "^[a-z][a-z0-9_]*$",
                    },
                    "provider_id": {
                        "type": "string",
                        "pattern": (
                            "^urn:otdp:transport-provider:"
                            "[a-z][a-z0-9-]*:[0-9]+\\.[0-9]+\\.[0-9]+$"
                        ),
                    },
                },
                "required": ["connection_key", "provider_id"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["config_version", "admitted", "connections"],
    "additionalProperties": False,
}

_VALIDATORS: dict[str, Any] = {}


class SettingsRejected(ValueError):
    """The transport-settings document failed validation or consistency."""


def provider_contract_validator() -> Any:
    """The ACTIVE vendored provider-contract schema's validator, cached.

    Same manifest-derived resolution as ``documents._descriptor_validator``
    (the second normative-name lookup): the active version derives from the
    vendored standards manifest, never a hardcoded gateway constant — there
    is no gateway path constant that could drift from the corpus.
    """
    validator = _VALIDATORS.get(PROVIDER_SCHEMA_NAME)
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
            if Path(relative).name == PROVIDER_SCHEMA_NAME
        ]
        if len(matches) != 1:
            raise StandardsError(
                f"provider_schema_unresolved: {PROVIDER_SCHEMA_NAME} is not "
                "named exactly once in the otdp entry's normative list"
            )
        schema = json.loads(
            (corpus / matches[0].removeprefix("standards/")).read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        _VALIDATORS[PROVIDER_SCHEMA_NAME] = validator
    return validator


def _relative_pin_path(relative: object) -> PurePosixPath:
    """The settings-relative document name, judged as a string.

    Mirrors the SDK's package-relative pin rules so both lanes refuse the
    same shapes: no backslash, no colon segment (platform-blind drive
    anchor), not absolute, no ``.``/``..``/empty segments. The settings
    document is operator-owned; a name that escapes its directory is not a
    settings-relative document name at all.
    """
    if (
        not isinstance(relative, str)
        or not relative
        or "\\" in relative
        or ":" in relative
        or PurePosixPath(str(relative)).is_absolute()
        or any(part in (".", "..") for part in relative.split("/"))
        or any(not part for part in relative.split("/"))
    ):
        raise SettingsRejected(
            f"settings_schema: {relative!r} is not a settings-relative document name"
        )
    return PurePosixPath(relative)


@dataclass(frozen=True)
class AdmittedProvider:
    """One admitted provider contract: the triple plus the validated bytes.

    ``document`` is the parsed, schema-validated instance the operator's
    admission record names — the operator's record and the reviewed bytes
    are one act, deterministically checkable (the triple's ``sha256`` pins
    them together).
    """

    id: str
    version: str
    sha256: str
    feature_id: str
    document: dict[str, Any]


@dataclass(frozen=True)
class ProviderRegistry:
    """The validated settings object: admitted contracts + key bindings."""

    admitted: tuple[AdmittedProvider, ...]
    #: (connection_key, provider_id) pairs, keys unique by construction.
    connections: tuple[tuple[str, str], ...]

    def feature_ids(self) -> frozenset[str]:
        """Layer 2 of the known-features union: the host-admitted features."""
        return frozenset(entry.feature_id for entry in self.admitted)

    def find(self, provider_id: object, version: object, sha256: object) -> AdmittedProvider | None:
        """The admitted entry for an EXACT triple match, else None.

        Partial matches (right id, wrong version or digest) are not
        admissions — "the declared provider triple is not exactly an
        admitted triple" refuses (the S12-extended posture).
        """
        for entry in self.admitted:
            if (entry.id, entry.version, entry.sha256) == (provider_id, version, sha256):
                return entry
        return None

    def resolve_connection(self, connection_key: object) -> AdmittedProvider | None:
        """The admitted contract a connection key is bound to, else None."""
        if not isinstance(connection_key, str):
            return None
        provider_id = next(
            (bound for key, bound in self.connections if key == connection_key), None
        )
        if provider_id is None:
            return None
        return next(
            (entry for entry in self.admitted if entry.id == provider_id), None
        )


def load_transport_settings(path: Path) -> ProviderRegistry:
    """Exact-byte decode, validate, and materialize the settings document.

    The settings document itself decodes through the exact-byte decoder and
    validates against :data:`TRANSPORT_SETTINGS_SCHEMA`; every admitted
    ``document`` resolves settings-relative, decodes through the same
    decoder with the triple's ``sha256`` as the expected digest
    (``settings_digest_mismatch:`` on disagreement), and validates against
    the active vendored provider-contract schema. Internal consistency is
    part of the document's authority: a duplicate admission, a connection
    naming an unadmitted provider, or a connection key bound twice refuses
    with ``settings_schema:``.
    """
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        document = load_document(raw, digest, max_bytes=_MAX_SETTINGS_BYTES)
    except DocumentRejected as exc:
        raise SettingsRejected(f"settings_schema: {path.name} ({exc})") from exc
    error = next(
        iter(
            Draft202012Validator(
                TRANSPORT_SETTINGS_SCHEMA, format_checker=FormatChecker()
            ).iter_errors(document.content)
        ),
        None,
    )
    if error is not None:
        raise SettingsRejected(
            f"settings_schema: {path.name} {error.json_path}: {error.message}"
        )

    admitted: list[AdmittedProvider] = []
    seen_triples: set[tuple[str, str, str]] = set()
    seen_id_versions: set[tuple[str, str]] = set()
    for entry in document.content["admitted"]:
        triple = (entry["id"], entry["version"], entry["sha256"])
        if triple in seen_triples:
            raise SettingsRejected(
                f"settings_schema: {path.name} admits {entry['id']}@{entry['version']} "
                f"({entry['sha256'][:12]}…) more than once; an ambiguous admission "
                "record is not one"
            )
        seen_triples.add(triple)
        id_version = (entry["id"], entry["version"])
        if id_version in seen_id_versions:
            # Same identity at the same version but different bytes: two
            # rival "reviewed bytes" claims for one contract version. A
            # connection binds by provider id, so the ambiguity would be
            # unresolvable downstream — refuse it here.
            raise SettingsRejected(
                f"settings_schema: {path.name} admits {entry['id']}"
                f"@{entry['version']} twice with different sha256 values; one "
                "contract version has one set of reviewed bytes"
            )
        seen_id_versions.add(id_version)
        relative = _relative_pin_path(entry["document"])
        target = path.parent
        for part in relative.parts:
            target = target / part
            if target.is_symlink():
                raise SettingsRejected(
                    f"settings_schema: {entry['document']!r} crosses a symlink; "
                    "settings documents resolve through a strict no-follow posture"
                )
        try:
            document_raw = target.read_bytes()
        except OSError as exc:
            raise SettingsRejected(
                f"settings_schema: {entry['document']!r} could not be read "
                f"(os error {exc.errno})"
            ) from exc
        try:
            contract = load_document(
                document_raw, entry["sha256"], max_bytes=_MAX_SETTINGS_BYTES
            )
        except DocumentRejected as exc:
            if str(exc) == "digest_mismatch":
                raise SettingsRejected(
                    f"settings_digest_mismatch: {path.name} admits {entry['id']}"
                    f"@{entry['version']} with sha256 {entry['sha256']}, but "
                    f"{entry['document']!r} hashes to "
                    f"{hashlib.sha256(document_raw).hexdigest()}"
                ) from exc
            raise SettingsRejected(
                f"settings_schema: {path.name} names {entry['document']!r} "
                f"({exc}); an admitted document must decode exactly"
            ) from exc
        error = next(
            iter(provider_contract_validator().iter_errors(contract.content)), None
        )
        if error is not None:
            raise SettingsRejected(
                f"settings_schema: {entry['document']!r} fails the vendored "
                f"provider-contract schema at {error.json_path}: {error.message}"
            )
        admitted.append(
            AdmittedProvider(
                id=entry["id"],
                version=entry["version"],
                sha256=entry["sha256"],
                feature_id=entry["feature_id"],
                document=contract.content,
            )
        )

    known_ids = {entry.id for entry in admitted}
    connections: list[tuple[str, str]] = []
    seen_keys: set[str] = set()
    for binding in document.content["connections"]:
        key = binding["connection_key"]
        provider_id = binding["provider_id"]
        if key in seen_keys:
            raise SettingsRejected(
                f"settings_schema: {path.name} binds connection key {key!r} "
                "more than once"
            )
        seen_keys.add(key)
        if provider_id not in known_ids:
            raise SettingsRejected(
                f"settings_schema: {path.name} binds {key!r} to {provider_id!r}, "
                "which the document does not admit"
            )
        connections.append((key, provider_id))
    return ProviderRegistry(admitted=tuple(admitted), connections=tuple(connections))
