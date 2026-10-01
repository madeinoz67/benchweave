"""Sign an accepted submission into a published release (maintainer-side).

The one signing step of the publishing lane (design §3.2): re-derives the
manifest from the submission's pinned inputs — never trusting the submitted
manifest bytes — inserts the review block carrying the review record's digest,
and signs manifest + status with the maintainer-custodied lane key. Any
post-review change to payload, source or pins breaks the review record's pin
and this script refuses (CR-11/CR-14 falsifiers).

The signing key NEVER enters CI: CI verifies with the committed public root
only (CR-12). Unlike fixture keys, the lane key is maintainer-custodied;
CI-as-signing-oracle is structurally absent.

Usage (from the repository root):

    uv run python scripts/registry/sign_release.py \
        --submission <dir-with-manifest.json,payload.zip,submission.json> \
        --record <registry-repo>/records/submissions/<...>/review-1.json \
        --key <lane-key.pem> --out <registry-repo>/releases

With ``--plugin-tree`` and ``--registry-clone`` the submission manifest is
re-derived from the plugin tree through the SDK checkout at ``packages/sdk``
and must be byte-identical to the submitted manifest — the full
review-to-sign swap defense.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO = Path(__file__).resolve().parents[2]
SDK_SRC = REPO / "packages" / "sdk" / "src"

#: The signed form's manifest version (the submission is the 0.1.1 shape; the
#: review block rides inside the signed manifest, which flips the version).
SIGNED_MANIFEST_VERSION = "0.1.2"

#: Fixed status dates, mirroring the fixture discipline: no clock is read, the
#: output is byte-reproducible for identical inputs.
STATUS_UPDATED_AT = "2026-10-01T00:00:00Z"
STATUS_EXPIRES = "2027-10-01T00:00:00Z"

_IMMUTABLE_REVISION = __import__("re").compile(r"^([a-f0-9]{40}|[a-f0-9]{64})$")


class SignError(ValueError):
    """Signing refused; the message carries a stable machine prefix."""


def canonical_bytes(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def closure_digest_of(dependencies: list[dict[str, Any]]) -> str:
    pins = sorted(
        (dep["registry_id"], dep["package_id"], dep["version"], dep["manifest_sha256"])
        for dep in dependencies
    )
    return sha256_hex(canonical_bytes(pins))


def _verify_submission_consistency(
    manifest: dict[str, Any], manifest_raw: bytes, payload: bytes
) -> None:
    """The manifest tells the truth about its payload, and is canonical."""
    if canonical_bytes(manifest) != manifest_raw:
        raise SignError("submission_not_canonical: manifest bytes are not canonical JSON")
    block = manifest.get("payload", {})
    if block.get("sha256") != sha256_hex(payload):
        raise SignError("payload_digest_mismatch: manifest payload.sha256 != payload.zip bytes")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    inventoried = {entry["path"]: entry for entry in block.get("files", [])}
    if set(members) != set(inventoried):
        raise SignError(
            f"payload_inventory_mismatch: archive carries {sorted(set(members) ^ set(inventoried))}"
        )
    for name, data in sorted(members.items()):
        if inventoried[name].get("sha256") != sha256_hex(data):
            raise SignError(f"payload_member_digest_mismatch: {name}")


def _verify_review_record(
    record_raw: bytes, manifest_raw: bytes, manifest: dict[str, Any]
) -> dict[str, Any]:
    """The review record pins this exact submission (D_sub) and its closure."""
    record: dict[str, Any] = json.loads(record_raw)
    review: dict[str, Any] = record.get("review", {})
    if review.get("submission_manifest_sha256") != sha256_hex(manifest_raw):
        raise SignError(
            "submission_digest_mismatch: the review record pins "
            f"{review.get('submission_manifest_sha256')}, the submission is "
            f"{sha256_hex(manifest_raw)} — the reviewed bytes changed (CR-11/CR-14)"
        )
    expected_closure = closure_digest_of(manifest.get("dependencies", []))
    if review.get("closure_digest") != expected_closure:
        raise SignError(
            "closure_digest_mismatch: the review sign-off names "
            f"{review.get('closure_digest')}, the submission closure is {expected_closure}"
        )
    if review.get("outcome") != "accepted":
        raise SignError(f"review_not_accepted: outcome is {review.get('outcome')!r}")
    revision = manifest.get("source", {}).get("revision", "")
    if _IMMUTABLE_REVISION.fullmatch(revision) is None:
        raise SignError(f"source_ref_mutable: {revision!r} is not a commit digest (CR-36)")
    if revision != review.get("source_revision"):
        raise SignError(
            "source_revision_mismatch: the record reviewed "
            f"{review.get('source_revision')}, the submission pins {revision}"
        )
    return record


def _rederive(
    plugin_tree: Path,
    registry_clone: Path,
    submission: dict[str, Any],
) -> bytes:
    """The real re-derivation: rebuild from the plugin tree at the pinned rev."""
    if not (SDK_SRC / "benchweave_sdk" / "publishing.py").is_file():
        raise SignError(
            f"sign_sdk_absent: {SDK_SRC} does not carry the SDK; init the "
            "submodule for the full re-derivation (the sign step does not "
            "trust submitted bytes)"
        )
    sys.path.insert(0, str(SDK_SRC))
    from benchweave_sdk.publishing import (
        build_submission,
    )

    publisher, plugin = str(submission["package_id"]).split("/", 1)
    try:
        artifacts = build_submission(
            plugin_tree,
            registry_clone=registry_clone,
            source_url=str(submission["source_url"]),
            revision=str(submission["source_revision"]),
            publisher=publisher,
            plugin=plugin,
            version=str(submission["version"]),
            capability_declaration=submission["capability_declaration"],
            dependencies=list(submission.get("dependencies", [])),
        )
    except Exception as exc:
        raise SignError(f"rederivation_failed: {exc}") from exc
    return artifacts.manifest_bytes


def sign(
    submission_dir: Path,
    record_path: Path,
    key_path: Path,
    out_root: Path,
    *,
    plugin_tree: Path | None = None,
    registry_clone: Path | None = None,
) -> Path:
    """Verify the chain, insert the review block, sign, and write the release."""
    manifest_raw = (submission_dir / "manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    payload = (submission_dir / "payload.zip").read_bytes()
    submission = json.loads((submission_dir / "submission.json").read_bytes())
    record_raw = record_path.read_bytes()

    _verify_submission_consistency(manifest, manifest_raw, payload)
    record = _verify_review_record(record_raw, manifest_raw, manifest)

    if plugin_tree is not None and registry_clone is not None:
        rederive_inputs = {
            **submission,
            "source_url": manifest["source"]["url"],
            "dependencies": manifest.get("dependencies", []),
        }
        derived = _rederive(plugin_tree, registry_clone, rederive_inputs)
        if derived != manifest_raw:
            raise SignError(
                "rederivation_mismatch: the submission manifest differs from a "
                "fresh derivation of the pinned inputs — the reviewed bytes "
                "changed (CR-14)"
            )

    signed = dict(manifest)
    signed["manifest_version"] = SIGNED_MANIFEST_VERSION
    signed["review"] = {
        "checklist_id": record["review"]["checklist_id"],
        "checklist_version": record["review"]["checklist_version"],
        "reviewer_id": record["review"]["reviewer_id"],
        "outcome": record["review"]["outcome"],
        "record_sha256": sha256_hex(record_raw),
    }
    signed_raw = canonical_bytes(signed)

    status = {
        "status_version": "0.1.1",
        "release": {
            "registry_id": manifest["registry_id"],
            "package_id": manifest["package_id"],
            "version": manifest["version"],
            "manifest_sha256": sha256_hex(signed_raw),
        },
        "sequence": 1,
        "updated_at": STATUS_UPDATED_AT,
        "expires_at": STATUS_EXPIRES,
        "lifecycle": "published",
        "reason": "accepted submission signed by the publishing lane",
        "support_state": "maintained",
        "support_contact": manifest["support_url"],
        "reviews": [],
        "advisories": [],
    }
    status_raw = canonical_bytes(status)

    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    assert isinstance(key, Ed25519PrivateKey)  # noqa: S101 — narrowing only
    release_dir: Path = (
        out_root
        / str(manifest["registry_id"])
        / str(manifest["package_id"])
        / str(manifest["version"])
    )
    if release_dir.exists():
        raise SignError(f"release_exists: {release_dir} (releases are immutable)")
    release_dir.mkdir(parents=True)
    (release_dir / "manifest.json").write_bytes(signed_raw)
    (release_dir / "manifest.sig").write_bytes(key.sign(signed_raw))
    (release_dir / "status.json").write_bytes(status_raw)
    (release_dir / "status.sig").write_bytes(key.sign(status_raw))
    (release_dir / "payload.zip").write_bytes(payload)
    return release_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--plugin-tree", type=Path, default=None)
    parser.add_argument("--registry-clone", type=Path, default=None)
    args = parser.parse_args()
    try:
        release_dir = sign(
            args.submission,
            args.record,
            args.key,
            args.out,
            plugin_tree=args.plugin_tree,
            registry_clone=args.registry_clone,
        )
    except SignError as exc:
        print(f"sign_release: {exc}", file=sys.stderr)
        return 1
    print(f"signed {release_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
