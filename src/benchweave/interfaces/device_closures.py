"""Run-time resolution of a bench device's commissioned OTDP closure (issue #167).

The design of record (``.claude/deep-review/2026-09-23-issue167-run-engine-
activation-design.md``, Decision 1) pins the authority chain: a run may
construct a bridge for an adapter-mode bench device only from the bench's
**admitted closure**, and the linkage is the bench device's declared
``generation`` — the activation record the admin act wrote for exactly that
generation is the commissioning evidence (A11: a downloaded package is data
until commissioned locally; the closure WAS commissioned by the admin act).

This module resolves that chain WITHOUT inventing a second admission path
(the design's DON'T-BUILD line): it reads the admitted state the admin flow
already produced —

* the activation record ``<records_dir>/<bench_id>/activation-<n>.json``
  (``registry.activation.activate``), binding the commissioned generation to
  the package-lock digest;
* the package lock at the session's ``lock_path``, whose ``packages[]`` rows
  carry every closure release's coordinates and manifest digest;
* each release's manifest bytes, read through the resolver's own origin
  sources and digest-verified against the lock row (the manifest re-read is
  pinned by the lock, not re-trusted: admission verified authenticity when
  the closure was admitted, and the digest pin makes any registry drift a
  hard mismatch — the resolver itself cannot be reused here because its
  strictly-advancing high-water fence refuses a second resolve of the same
  release sequences, by design);
* each release's STATUS document, consulted through the same origin
  sources (issue #226 slice 4): schema-loaded, signature-verified against
  the session's trust root, release-bound, gate-checked on the consult
  clock (expiry, future-time, sequence FLOOR — replaying the same
  authenticated sequence is the healthy case) and lifecycle-checked; a
  session consult-water remembers every authenticated sequence
  (lifecycle refusals included), so an origin rollback below an
  authenticated sequence refuses as well (fold adv1-F1). A
  published revocation or yank refuses the run-build
  (``closure_status_revoked`` / ``closure_status_yanked``); advisories
  DELIVER as append-once operator records and never refuse the run
  (Q14); a published review block contradicting the local commissioning
  surfaces as ``approval_drift`` (CR-42 — surfaced, never enforced).
  Views are cached per session under a stated staleness bound
  (:data:`_STATUS_CONSULT_BOUND_NS`).
* the admission cache at ``<cache_root>/<manifest_sha256>/`` (the loader
  re-verifies every payload byte against the manifest inventory anyway).

A device whose generation has NO activation record returns ``None`` — that
is the demo-lattice declarative fallback's discriminator, not an error: the
startup-admitted generation was never commissioned through the registry
admin act, so its devices keep the committed sim plugins (disclosed loudly
by the caller). An INCONSISTENT commissioned state (record without lock,
lock digest drift, a closure that does not serve the device's pinned
descriptor digest, a missing cache) raises
:class:`ClosureResolutionError` — the run refuses rather than silently
substituting a different device implementation than the one commissioned.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from benchweave.interfaces.bootstrap import RegistrySession, StatusView
from benchweave.registry.admission import AdmissionRejected, _load_persisted_high_water
from benchweave.registry.authenticity import (
    AuthenticityRejected,
    consult_status,
    verify_document,
)
from benchweave.registry.resolver import _STATUS_MAX_BYTES, PackageSource
from benchweave.registry.schemas import RegistryRejected, load_status_document

_LOG = logging.getLogger(__name__)

#: Manifest inventory roles the resolution reads.
_DESCRIPTOR_ROLE = "descriptor"
_IMPLEMENTATION_ROLE = "implementation"

#: The staleness bound on a consulted status view (issue #226 slice 4,
#: NFR-S2/NFR-S3). A view read from the origin at ``consulted_at_ns``
#: serves every consult while ``now_ns() - consulted_at_ns`` stays within
#: this bound; the next consult beyond it re-reads and re-verifies.
#:
#: Denominator (NFR-S2), stated where the bound is claimed: the bound
#: covers gateways REACHABLE at next run-build after publication — a
#: revocation, yank or advisory published now reaches the next run-build
#: of an already-commissioned closure with delay at most this bound.
#: Gateways OFFLINE since publication, or running no builds, are NOT
#: covered by it: their refusal or advisory lands at their next consult
#: whenever that happens (the recorded operator-delivery half), and until
#: then this constant makes no claim about them. Per-bench commissioning
#: of the bound is deferred (the design's S4-D3).
_STATUS_CONSULT_BOUND_NS = 300 * 1_000_000_000


class ClosureResolutionError(ValueError):
    """The commissioned state is inconsistent; the message names the break.

    Every message is machine-prefixed (``closure_*``) so a refused run's
    poison-guard log line is greppable.
    """


@dataclass(frozen=True)
class DeviceClosure:
    """One commissioned device's bridge construction inputs."""

    cache_root: Path
    manifest: dict[str, Any]
    manifest_sha256: str
    entry_relpath: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _consult_iso(now_ns: int) -> str:
    """The consult's wall stamp, derived from the session clock."""
    return datetime.fromtimestamp(now_ns / 1_000_000_000, tz=UTC).isoformat()


def _append_once_record(
    advisories_dir: Path, identity: dict[str, Any], record: dict[str, Any]
) -> None:
    """Write one append-once delivery record (tmp + :func:`os.replace`).

    The record NAME is the sha256 of the canonical DELIVERY-IDENTITY
    bytes: what the delivery IS — kind, release coordinates, advisory id
    or review outcome, and the ADVISORY/REVIEW CONTENT VERBATIM (fold
    adv2-F2, disclosed as deviation 3.2). Escalated content names a NEW
    record, so an in-place advisory escalation lands a second durable
    record; unchanged content names the same record forever. Two
    volatile fields are deliberately OUT of the identity: the record's
    ``consulted_at`` (it churns on every beyond-bound re-read — naming on
    it would falsify the design's append-once rule, risk 6) and the
    status document digest (a pure sequence revision carrying an
    unchanged advisory must not double-deliver).
    """
    target = advisories_dir / (
        "advisory-" + hashlib.sha256(_canonical(identity)).hexdigest()[:16] + ".json"
    )
    if target.exists():
        return
    try:
        advisories_dir.mkdir(parents=True, exist_ok=True)
        staged = target.with_name(target.name + ".tmp")
        staged.write_bytes(_canonical(record))
        os.replace(staged, target)
    except OSError as exc:
        # R1 (PR #391): advisory delivery and drift surfacing are
        # informational (CR-29) — an unusable advisories path must never
        # refuse a commissioned run. Residual, stated plainly here and in
        # the warning: while the path is unusable the operator record is
        # NOT written; the log line is the only delivery surface.
        _LOG.warning(
            "closure_status_record_unwritten: identity=%s — the run proceeds "
            "(advisories are informational, CR-29); the operator record is "
            "NOT written while the advisories path is unusable (%s)",
            _canonical(identity).decode(),
            exc,
        )


def _deliver_status_advisories(
    session: RegistrySession,
    key: tuple[str, str, str],
    status: dict[str, Any],
    served_sha256: str,
    now_ns: int,
) -> None:
    """Advisory delivery (Q14's recorded operator half): an advisory does
    NOT refuse the run (CR-29 fixes advisory semantics as informational)
    — the advisory is delivered as one append-once operator record plus a
    warning line, and re-consults write no duplicate record."""
    for entry in status.get("advisories") or []:
        advisory = dict(entry)
        release = {"registry_id": key[0], "package_id": key[1], "version": key[2]}
        _LOG.warning(
            "closure_status_advisory: release=%s advisory=%s severity=%s "
            "summary=%s url=%s",
            key,
            advisory.get("id"),
            advisory.get("severity"),
            advisory.get("summary"),
            advisory.get("url"),
        )
        _append_once_record(
            session.advisories_dir,
            identity={
                "kind": "operator_advisory",
                "release": release,
                "advisory_id": str(advisory.get("id")),
                "advisory": advisory,
            },
            record={
                "kind": "operator_advisory",
                "release": release,
                "advisory": advisory,
                "status_sha256": served_sha256,
                "consulted_at": _consult_iso(now_ns),
            },
        )


def _surface_approval_drift(
    session: RegistrySession,
    key: tuple[str, str, str],
    manifest: dict[str, Any],
    now_ns: int,
) -> None:
    """Approval-drift surfacing (D4, CR-42): a published review block
    (registry 0.1.2, optional — every 0.1.1 manifest is out of scope)
    whose outcome is not ``accepted`` is SURFACED — one ``approval_drift``
    operator record plus a warning line — and the run continues.

    Deliberately NOT an identity-equivalence check (the local approval's
    principal and the registry reviewer name different roles; the signed
    approval channel that would make identity-level cross-checks honest
    is the design's S4-D2 deferral), and never a gate: REG-5 holds for
    ADMISSION byte-for-byte, and this reads ``review`` for surfacing
    only — never as provenance, never for gating.
    """
    review = manifest.get("review")
    if not isinstance(review, dict):
        return
    outcome = str(review.get("outcome"))
    if outcome == "accepted":
        return
    release = {"registry_id": key[0], "package_id": key[1], "version": key[2]}
    _LOG.warning(
        "closure_status_approval_drift: release=%s outcome=%s reviewer=%s — "
        "the commissioned release's published review records a non-acceptance",
        key,
        outcome,
        review.get("reviewer_id"),
    )
    _append_once_record(
        session.advisories_dir,
        identity={
            "kind": "approval_drift",
            "release": release,
            "outcome": outcome,
            "review": {
                "reviewer_id": str(review.get("reviewer_id")),
                "outcome": outcome,
                "record_sha256": str(review.get("record_sha256")),
            },
        },
        record={
            "kind": "approval_drift",
            "release": release,
            "review": {
                "reviewer_id": str(review.get("reviewer_id")),
                "outcome": outcome,
                "record_sha256": str(review.get("record_sha256")),
            },
            "consulted_at": _consult_iso(now_ns),
        },
    )


def _consult_release_status(
    session: RegistrySession,
    key: tuple[str, str, str],
    source: PackageSource,
    row: dict[str, Any],
    manifest: dict[str, Any],
    floor: int,
) -> None:
    """Consult one release's status at run-build (issue #226 slice 4).

    The EXISTING checks — schema load, signature verification against
    the session's trust root, release binding, expiry/future/floor
    gates, lifecycle refusal — wired into the third moment they were
    missing from: resolve and admit already run them, and run-build of
    an already-commissioned closure now does too. No new verification
    logic; that is the whole design. A view cached within
    :data:`_STATUS_CONSULT_BOUND_NS` serves with ZERO origin reads — its
    content is already verified — while the gates re-run on the consult
    clock (a cached view is not a licence to serve past expiry) and
    advisory delivery stays idempotent.
    """
    now = session.now_ns()
    view = session.status_cache.get(key)
    fresh = False
    if view is not None and now - view.consulted_at_ns <= _STATUS_CONSULT_BOUND_NS:
        status: dict[str, Any] = view.status
        served_sha256 = view.served_sha256
    else:
        fresh = True
        root = session.roots.get(key[0])
        if root is None:
            # Fail-closed posture: the consult verifies against the
            # session's trust roots exactly as admission does. An origin
            # routed without a root (a dev-unsigned origin) has no
            # consultable status channel — no skip-signature consult
            # posture exists (the design's S4-D1 deferral).
            raise ClosureResolutionError(
                f"closure_status_root_absent: release {key} routes an origin "
                "the session holds no trust root for"
            )
        try:
            raw, served_sha256 = source.status_bytes(key[1], key[2])
            status_doc = load_status_document(
                raw, served_sha256, max_bytes=_STATUS_MAX_BYTES
            )
        except RegistryRejected as exc:
            raise ClosureResolutionError(f"closure_status_{exc.reason}: {key}") from exc
        except OSError as exc:
            # A missing or unreadable status is a typed refusal, never a
            # raw OS error (F1, fail-closed).
            raise ClosureResolutionError(
                f"closure_status_absent: no servable status document for {key}"
            ) from exc
        try:
            signature = source.status_signature(key[1], key[2])
        except OSError as exc:
            # Under `required` the signature is part of the status, never
            # an optional extra file (the resolver's own rule).
            raise ClosureResolutionError(
                f"closure_status_bad_signature: {key}"
            ) from exc
        try:
            verify_document(status_doc, signature, root)
        except AuthenticityRejected as exc:
            raise ClosureResolutionError(f"closure_status_{exc.reason}: {key}") from exc
        # Release binding BEFORE the gates: the signature proves the
        # bytes are authentic, not that they describe THIS release — a
        # validly-signed foreign "published" status cannot mask this
        # release's revocation.
        status_release = status_doc.content["release"]
        if (
            status_release["registry_id"],
            status_release["package_id"],
            status_release["version"],
        ) != key or str(status_release["manifest_sha256"]) != str(
            row.get("manifest_sha256")
        ):
            raise ClosureResolutionError(
                "closure_status_release_mismatch: the served status for "
                f"{key} does not name this release and pin the admitted "
                "manifest digest"
            )
        status = status_doc.content
    # Gates on the consult clock — a fresh read and a cached view alike.
    # A passing sequence is AUTHENTICATED: it raises the session's
    # consult-water even when the lifecycle check below refuses, so a
    # revoked view counts and a later rollback to lower bytes cannot
    # replay past it (fold adv1-F1).
    try:
        sequence = consult_status(status, now_ns=now, floor=floor)
    except AuthenticityRejected as exc:
        raise ClosureResolutionError(f"closure_status_{exc.reason}: {key}") from exc
    if sequence > session.consult_water.get(key, 0):
        session.consult_water[key] = sequence
    lifecycle = str(status["lifecycle"])
    if lifecycle == "revoked":
        raise ClosureResolutionError(
            f"closure_status_revoked: release {key} is revoked at sequence "
            f"{sequence} — the commissioned closure cannot run"
        )
    if lifecycle == "yanked":
        raise ClosureResolutionError(
            f"closure_status_yanked: release {key} is yanked at sequence "
            f"{sequence} — the commissioned closure cannot run"
        )
    _deliver_status_advisories(session, key, status, served_sha256, now)
    _surface_approval_drift(session, key, manifest, now)
    if fresh:
        session.status_cache[key] = StatusView(status, served_sha256, now)


def _module_components(path: str, code_paths: set[str]) -> list[str]:
    """The dotted module a payload file implements, its package chain stripped.

    Mirrors the bundle loader's walk exactly: the contiguous ``__init__.py``
    chain above the file is walked to its TOP, that top directory becomes
    the import root, and the module is everything below it plus the stem —
    ``plugin/plugin.py`` (with ``plugin/__init__.py``) implements module
    ``plugin``; ``a/b/c.py`` over packages ``a``/``a/b`` implements ``b.c``.
    """
    pure = PurePosixPath(path)
    directories = list(pure.parts[:-1])
    top = len(directories)
    while top > 0 and str(PurePosixPath(*directories[:top]) / "__init__.py") in code_paths:
        top -= 1
    if pure.stem == "__init__":
        return directories[top + 1:]
    return [*directories[top + 1:], pure.stem]


def _entry_relpath(entry_point: str, manifest: dict[str, Any]) -> str:
    """Derive the payload entry file from the descriptor's entry point.

    The OTDP spec pins the form ``package.module:create_plugin``; the bundle
    loader imports a module whose dotted path is the file's package-stripped
    position. The derivation therefore matches the entry module's trailing
    components against every implementation file's module path and requires
    exactly ONE match — a payload whose layout makes the entry ambiguous is
    a packaging defect, refused loudly rather than guessed.
    """
    module, separator, _factory = entry_point.partition(":")
    if not separator or not module:
        raise ClosureResolutionError(
            f"closure_entry_invalid: entry point {entry_point!r} is not module:factory"
        )
    files = manifest["payload"]["files"]
    code_paths = {
        str(file["path"])
        for file in files
        if file.get("role") == _IMPLEMENTATION_ROLE and str(file["path"]).endswith(".py")
    }
    components = module.split(".")
    matches: list[str] = []
    for path in sorted(code_paths):
        file_module = _module_components(path, code_paths)
        if file_module and file_module == components[-len(file_module):]:
            matches.append(path)
    if len(matches) != 1:
        raise ClosureResolutionError(
            "closure_entry_ambiguous: entry point "
            f"{entry_point!r} matches implementation files {matches} — exactly one is required"
        )
    return matches[0]


def commissioned_device_closure(
    session: RegistrySession | None,
    bench_id: str,
    device: dict[str, Any],
    descriptor: dict[str, Any],
) -> DeviceClosure | None:
    """Resolve the commissioned closure for one bench device, or ``None``.

    ``None`` means "no admin act commissioned a closure for this device's
    declared generation" — the caller's declarative-fallback discriminator.
    Everything else about the commissioned state is verified or raises.
    ``descriptor`` is the device's RAW full-form descriptor document (the
    same bytes the bench pins by digest); its ``integration.adapter``
    block names the entry point the payload must serve.
    """
    if session is None:
        return None
    generation = device.get("generation")
    if not isinstance(generation, int) or generation < 1:
        raise ClosureResolutionError(
            f"closure_generation_invalid: bench {bench_id} device "
            f"{device.get('id')!r} declares no usable generation"
        )
    record_path = session.records_dir / bench_id / f"activation-{generation}.json"
    if not record_path.is_file():
        # Not commissioned by an admin act at this generation: the honest
        # None — the declarative fallback's discriminator.
        return None
    record = json.loads(record_path.read_bytes())
    if not session.lock_path.is_file():
        raise ClosureResolutionError(
            f"closure_lock_absent: activation record {record_path} exists but "
            f"the admitted package lock {session.lock_path} does not"
        )
    lock_raw = session.lock_path.read_bytes()
    if _sha256(lock_raw) != str(record.get("lock_sha256")):
        raise ClosureResolutionError(
            "closure_lock_drift: the session's current package lock is not the "
            f"one commissioned for bench {bench_id} generation {generation}"
        )
    lock = json.loads(lock_raw)
    rows: dict[tuple[str, str, str], dict[str, Any]] = {
        (str(row["registry_id"]), str(row["package_id"]), str(row["version"])): row
        for row in lock.get("packages", [])
    }
    if not rows:
        raise ClosureResolutionError(
            f"closure_lock_empty: the admitted lock {session.lock_path} names no packages"
        )
    manifests: dict[tuple[str, str, str], dict[str, Any]] = {}
    try:
        # The consult's sequence floor: admission's own persisted rollback
        # view, reused read-only. A file malformed enough to refuse
        # ADMISSION refuses the consult too — under this module's prefix
        # discipline, not admission's.
        floor_map = _load_persisted_high_water(session.cache_root)
    except AdmissionRejected as exc:
        raise ClosureResolutionError(
            f"closure_status_{exc.reason}: {session.cache_root}"
        ) from exc
    for key, row in sorted(rows.items()):
        registry_id, package_id, version = key
        source = session.resolver.origin_source(registry_id)
        if source is None:
            raise ClosureResolutionError(
                f"closure_origin_unknown: lock row {key} names an origin the "
                "session does not route"
            )
        # The registry chain pins RAW served-byte digests (load_document
        # verifies expected_sha256 over the exact bytes — CON-1's exact-byte
        # decoder). Since row G (issue #176) the resolver refuses
        # non-canonical manifest bytes at resolution, so locks written
        # since then pin canonical bytes; only a PRE-row-G lock over
        # content-identical non-canonical bytes still resolves on this
        # raw-digest comparison (its pin matches the served bytes) and
        # then fails misleadingly at ``load_otdp_plugin`` as
        # ``manifest_hash_mismatch`` — the upgrade-only residual, deferred.
        # The comparison stays the SERVED raw digest (F4), never a
        # canonical re-encode that only coincides with the pin.
        raw, served_digest = source.manifest_bytes(package_id, version)
        manifest = json.loads(raw)
        if served_digest != str(row.get("manifest_sha256")):
            raise ClosureResolutionError(
                "closure_manifest_drift: the served manifest for "
                f"{key} does not match the admitted lock's pinned digest"
            )
        manifests[key] = manifest
        # The same iteration that digest-verified the manifest consults
        # the release's status — the third moment (issue #226 slice 4).
        # The gate floor is the PERSISTED admission high-water and the
        # session's consult-water taken together: the persisted floor
        # forbids pre-admission rollback, the session water forbids
        # rolling an origin back below a sequence this session already
        # authenticated (fold adv1-F1 — same-session resurrection).
        _consult_release_status(
            session,
            key,
            source,
            row,
            manifest,
            max(floor_map.get(key, 0), session.consult_water.get(key, 0)),
        )

    descriptor_digest = str(device["descriptor"]["sha256"])

    def serves_descriptor(manifest: dict[str, Any]) -> bool:
        return any(
            str(file.get("sha256")) == descriptor_digest
            for file in manifest["payload"]["files"]
            if file.get("role") == _DESCRIPTOR_ROLE
        )

    serving = {key for key, manifest in manifests.items() if serves_descriptor(manifest)}
    if not serving:
        raise ClosureResolutionError(
            "closure_descriptor_absent: the admitted closure serves no payload "
            f"descriptor digest {descriptor_digest[:12]}… pinned by bench "
            f"{bench_id} device {device.get('id')!r}"
        )
    implementations: set[tuple[str, str, str]] = set()
    for key, manifest in manifests.items():
        if manifest.get("kind") != _IMPLEMENTATION_ROLE:
            continue
        if key in serving:
            implementations.add(key)
            continue
        for dependency in manifest.get("dependencies", []):
            dep_key = (
                str(dependency["registry_id"]),
                str(dependency["package_id"]),
                str(dependency["version"]),
            )
            if dep_key in serving:
                implementations.add(key)
    if len(implementations) != 1:
        raise ClosureResolutionError(
            "closure_implementation_ambiguous: expected exactly one "
            f"implementation release serving the descriptor, found {sorted(implementations)}"
        )
    impl_key = next(iter(implementations))
    manifest = manifests[impl_key]
    manifest_sha256 = str(rows[impl_key]["manifest_sha256"])
    cache_dir = session.cache_root / manifest_sha256
    if not cache_dir.is_dir():
        raise ClosureResolutionError(
            "closure_cache_absent: the admitted cache directory "
            f"{cache_dir} for {impl_key} is missing"
        )
    entry_point = str(
        ((descriptor.get("integration") or {}).get("adapter") or {}).get("entry_point") or ""
    )
    if not entry_point:
        raise ClosureResolutionError(
            "closure_entry_absent: the device descriptor declares no "
            "integration.adapter.entry_point"
        )
    return DeviceClosure(
        cache_root=session.cache_root,
        manifest=manifest,
        manifest_sha256=manifest_sha256,
        entry_relpath=_entry_relpath(entry_point, manifest),
    )
