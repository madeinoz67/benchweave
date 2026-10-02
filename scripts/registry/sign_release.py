"""Validate and record an accepted submission into a published release.

Owner ruling (2026-10-02, issue #223): the registry repository VALIDATES +
PUBLISHES + LABELS, never signs. The lane key is gone. This tool:

1. re-derives the manifest from the submission's pinned inputs (never
   trusting the submitted bytes) and requires byte-identity;
2. verifies the PUBLISHER's signature when one is present, against the
   publisher's public key recorded in the registry clone's publishers.json:
   - signed and valid → recorded ``signed-valid``;
   - signed but INVALID (or the publisher has no recorded key) → REJECTED —
     a present signature that does not verify is a hard refusal;
   - unsigned → ACCEPTED, labeled ``unsigned`` in the publish record and
     the index;
3. verifies an RFC 3161 trusted timestamp when one rides the artefacts:
   the token's digest matches its record, the record binds the signature's
   digest, and the signing time is re-extracted from the token bytes. With
   a timestamp, signature validity is judged AT THE TSA-ATTESTED TIME — a
   signature stays valid after the signer's key expires or is revoked.
   TSA-chain validation (the token's own certificate chain) is the platform
   residual, disclosed: this verifies the binding, not the TSA's identity.

Usage (from the repository root):

    uv run python scripts/registry/sign_release.py \
        --submission <dir> --record <review-record.json> \
        --out <registry-repo>/releases [--plugin-tree T --registry-clone C]

The release tree carries manifest.json, payload.zip and — when present —
the publisher's manifest.sig and the timestamp artefacts. No registry-side
signature is written anywhere; lifecycle state lives in the records and the
index.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

REPO = Path(__file__).resolve().parents[2]
SDK_SRC = REPO / "packages" / "sdk" / "src"

#: The signed form's manifest version (the submission is the 0.1.1 shape; the
#: review block rides inside the recorded manifest, which flips the version).
SIGNED_MANIFEST_VERSION = "0.1.2"

_IMMUTABLE_REVISION = re.compile(r"^([a-f0-9]{40}|[a-f0-9]{64})$")


class ValidationError(ValueError):
    """Validation refused; the message carries a stable machine prefix."""


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
        raise ValidationError("submission_not_canonical: manifest bytes are not canonical JSON")
    block = manifest.get("payload", {})
    if block.get("sha256") != sha256_hex(payload):
        raise ValidationError(
            "payload_digest_mismatch: manifest payload.sha256 != payload.zip bytes"
        )
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    inventoried = {entry["path"]: entry for entry in block.get("files", [])}
    if set(members) != set(inventoried):
        raise ValidationError(
            f"payload_inventory_mismatch: archive carries {sorted(set(members) ^ set(inventoried))}"
        )
    for name, data in sorted(members.items()):
        if inventoried[name].get("sha256") != sha256_hex(data):
            raise ValidationError(f"payload_member_digest_mismatch: {name}")


def _verify_review_record(
    record_raw: bytes, manifest_raw: bytes, manifest: dict[str, Any]
) -> dict[str, Any]:
    """The review record pins this exact submission (D_sub) and its closure."""
    record: dict[str, Any] = json.loads(record_raw)
    review: dict[str, Any] = record.get("review", {})
    if review.get("submission_manifest_sha256") != sha256_hex(manifest_raw):
        raise ValidationError(
            "submission_digest_mismatch: the review record pins "
            f"{review.get('submission_manifest_sha256')}, the submission is "
            f"{sha256_hex(manifest_raw)} — the reviewed bytes changed (CR-11/CR-14)"
        )
    expected_closure = closure_digest_of(manifest.get("dependencies", []))
    if review.get("closure_digest") != expected_closure:
        raise ValidationError(
            "closure_digest_mismatch: the review sign-off names "
            f"{review.get('closure_digest')}, the submission closure is {expected_closure}"
        )
    if review.get("outcome") != "accepted":
        raise ValidationError(f"review_not_accepted: outcome is {review.get('outcome')!r}")
    revision = manifest.get("source", {}).get("revision", "")
    if _IMMUTABLE_REVISION.fullmatch(revision) is None:
        raise ValidationError(f"source_ref_mutable: {revision!r} is not a commit digest (CR-36)")
    if revision != review.get("source_revision"):
        raise ValidationError(
            "source_revision_mismatch: the record reviewed "
            f"{review.get('source_revision')}, the submission pins {revision}"
        )
    return record


def _publisher_key(
    registry_clone: Path, publisher: str
) -> tuple[Ed25519PublicKey | None, dict[str, str] | None]:
    """The recorded public key and validity window for a vetted publisher."""
    publishers = json.loads((registry_clone / "records" / "publishers.json").read_bytes())
    entry = next(
        (e for e in publishers["publishers"] if e.get("publisher_id") == publisher), None
    )
    if entry is None:
        raise ValidationError(f"publisher_unknown:{publisher} (not in records/publishers.json)")
    pem = entry.get("ed25519_public_key_pem")
    key = None
    if pem:
        loaded = serialization.load_pem_public_key(pem.encode())
        if not isinstance(loaded, Ed25519PublicKey):
            raise ValidationError(f"publisher_key_unsupported:{publisher}")
        key = loaded
    window = entry.get("key_validity")
    return key, window


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_signing_time(value: str) -> datetime:
    """RFC 3161 genTime: UTCTime (YYMMDDHHMMSSZ) or GeneralizedTime.

    UTCTime's two-digit year is not what fromisoformat reads (26 parses as
    2601, not 2026); the RFC 5280 50-year window applies.
    """
    basic = value.rstrip("Z")
    fractional = basic.find(".")
    if fractional != -1:
        basic = basic[:fractional]
    if len(basic) == 12:  # UTCTime YYMMDDHHMMSS
        two_digit = int(basic[:2])
        century = 2000 if two_digit < 50 else 1900
        year = century + two_digit
        rest = basic[2:]
    elif len(basic) == 14:  # GeneralizedTime YYYYMMDDHHMMSS
        year = int(basic[:4])
        rest = basic[4:]
    else:
        return _parse_time(value)
    return datetime(
        year,
        int(rest[0:2]),
        int(rest[2:4]),
        int(rest[4:6]),
        int(rest[6:8]),
        int(rest[8:10]),
        tzinfo=UTC,
    )


def _verify_signature(
    submission_dir: Path,
    manifest_raw: bytes,
    publisher: str,
    registry_clone: Path,
    released_at: str,
) -> tuple[str, dict[str, Any] | None, bool]:
    """Verify the publisher signature and timestamp; (label, timestamp, advisory).

    ``signed-valid`` / ``unsigned`` — anything else refuses. Timestamping is
    OPTIONAL but recommended (owner refinement, 2026-10-02): a signed release
    WITHOUT one is accepted — no refusal — and carries
    ``timestamp_recommended`` so the record and index state the honest
    validity horizon (an un-timestamped signature is valid until the key
    expires; a timestamped one stays valid past expiry or revocation). With
    a timestamp, key validity is judged at the TSA-attested signing time,
    and a TSA-attested time OUTSIDE the window is a genuine invalid
    signature (the key was not valid when the signing happened) — that
    still refuses.
    """
    sig_path = submission_dir / "manifest.sig"
    if not sig_path.is_file():
        return "unsigned", None, False

    key, window = _publisher_key(registry_clone, publisher)
    if key is None:
        raise ValidationError(
            f"signature_invalid: a manifest.sig is present but publisher {publisher!r} "
            "has no recorded public key (publishers.json) — a present signature that "
            "cannot verify is rejected"
        )
    # The publisher signed the SUBMISSION manifest (pre-review bytes); that
    # is what manifest.sig verifies over.
    try:
        key.verify(sig_path.read_bytes(), manifest_raw)
    except InvalidSignature as exc:
        raise ValidationError(
            "signature_invalid: the publisher signature does not verify over the "
            "manifest bytes — a present signature that does not verify is rejected"
        ) from exc

    timestamp: dict[str, Any] | None = None
    token_path = submission_dir / "timestamp.token"
    record_path = submission_dir / "timestamp.json"
    if token_path.is_file() and record_path.is_file():
        token = token_path.read_bytes()
        recorded: dict[str, Any] = json.loads(record_path.read_bytes())
        if recorded.get("token_sha256") != sha256_hex(token):
            raise ValidationError("timestamp_invalid: token bytes do not match the record digest")
        if recorded.get("signature_sha256") != sha256_hex(sig_path.read_bytes()):
            raise ValidationError(
                "timestamp_invalid: the record does not bind this signature's digest"
            )
        # Fold H1: the token's messageImprint must COVER the signature - a
        # structurally genuine token over different content refuses.
        imprint, extracted = _parse_timestamp_token(token)
        if imprint != hashlib.sha256(sig_path.read_bytes()).digest():
            raise ValidationError(
                "timestamp_binding_mismatch: the token's messageImprint does not "
                "cover this signature (it timestamps other content)"
            )
        if extracted != recorded.get("signed_at"):
            raise ValidationError(
                "timestamp_invalid: the token's own time disagrees with the record"
            )
        timestamp = recorded
        # Timestamped: validity judged at the TSA-attested time — a timestamp
        # OUTSIDE the window is a genuine invalid signature (refuses); one
        # inside stays valid past expiry/revocation.
        signing_time = _parse_signing_time(extracted)
        if window is not None:
            not_before = _parse_time(window["not_before"])
            not_after = _parse_time(window["not_after"])
            if not (not_before <= signing_time <= not_after):
                raise ValidationError(
                    "signature_invalid: the TSA-attested signing time falls "
                    f"outside the key validity window ({signing_time.isoformat()} "
                    f"outside [{window['not_before']}, {window['not_after']}]) — "
                    "the key was not valid when the signing happened"
                )
        return "signed-valid", timestamp, False

    # Un-timestamped (optional but recommended): accepted, no refusal — the
    # advisory records the honest validity horizon (valid until key expiry).
    return "signed-valid", None, True


#: id-ct-TSTInfo (1.2.840.113549.1.9.16.1.4), the OID naming the TSTInfo
#: content type inside an RFC 3161 TimeStampToken.
_TSTINFO_OID = bytes.fromhex("2a864886f70d0109100104")


def _der_tlv(data: bytes, offset: int) -> tuple[int, int, int]:
    """One DER TLV -> (tag, content_offset, content_length); ValueError."""
    if offset + 2 > len(data):
        raise ValueError("truncated TLV header")
    tag = data[offset]
    first = data[offset + 1]
    header = 2
    length = first
    if first & 0x80:
        count = first & 0x7F
        if count == 0 or count > 4 or offset + 2 + count > len(data):
            raise ValueError("unsupported DER length form")
        length = int.from_bytes(data[offset + 2 : offset + 2 + count], "big")
        header = 2 + count
    if offset + header + length > len(data):
        raise ValueError("TLV content overruns buffer")
    return tag, offset + header, length


def _iter_tlv(data: bytes, start: int, end: int) -> Any:
    offset = start
    while offset < end:
        tag, content, length = _der_tlv(data, offset)
        yield tag, content, length
        offset = content + length


def _find_tstinfo(data: bytes) -> bytes | None:
    """The TSTInfo SEQUENCE content by structural descent - never a byte scan.

    Walks proper TLV boundaries for the contentInfo whose contentType is
    id-ct-TSTInfo; the following [0] EXPLICIT wraps the TSTInfo SEQUENCE. A
    digest containing 0x17/0x18 bytes can never be misread this way (fold M2).
    """

    def descend(start: int, end: int) -> bytes | None:
        offset = start
        while offset < end:
            try:
                tag, content, length = _der_tlv(data, offset)
            except ValueError:
                return None
            if tag == 0x06 and data[content : content + length] == _TSTINFO_OID:
                nxt = content + length
                if nxt >= end:
                    return None
                try:
                    tag2, content2, _length2 = _der_tlv(data, nxt)
                    tag3, content3, length3 = _der_tlv(data, content2)
                except ValueError:
                    return None
                if tag2 == 0xA0 and tag3 == 0x30:
                    return data[content3 : content3 + length3]
                return None
            if tag in (0x30, 0x31, 0xA0):
                found = descend(content, content + length)
                if found is not None:
                    return found
            offset = content + length
        return None

    return descend(0, len(data))


def _parse_timestamp_token(token: bytes) -> tuple[bytes, str]:
    """(messageImprint digest, genTime) from a structurally parsed TSTInfo.

    Malformed or non-token bytes raise ValidationError with the
    timestamp_token_malformed prefix - never a raw traceback (fold M2).
    """
    body = _find_tstinfo(token)
    if body is None:
        raise ValidationError(
            "timestamp_token_malformed: no TSTInfo found (not an RFC 3161 "
            "TimeStampToken)"
        )
    imprint: bytes | None = None
    gen_time: str | None = None
    try:
        for tag, content, length in _iter_tlv(body, 0, len(body)):
            if tag == 0x30 and imprint is None:
                for sub_tag, sub_content, sub_length in _iter_tlv(
                    body, content, content + length
                ):
                    if sub_tag == 0x04:
                        imprint = body[sub_content : sub_content + sub_length]
            elif tag in (0x17, 0x18) and gen_time is None:
                gen_time = body[content : content + length].decode("ascii")
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValidationError(f"timestamp_token_malformed: {exc}") from exc
    if imprint is None or gen_time is None:
        raise ValidationError(
            "timestamp_token_malformed: TSTInfo lacks messageImprint or genTime"
        )
    return imprint, gen_time


def _rederive(
    plugin_tree: Path,
    registry_clone: Path,
    submission: dict[str, Any],
    manifest: dict[str, Any],
) -> bytes:
    """The real re-derivation: rebuild from the plugin tree at the pinned rev."""
    if not (SDK_SRC / "benchweave_sdk" / "publishing.py").is_file():
        raise ValidationError(
            f"validate_sdk_absent: {SDK_SRC} does not carry the SDK; init the "
            "submodule for the full re-derivation (validation does not trust "
            "submitted bytes)"
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
            licence_spdx=str(submission.get("licence_spdx", "MIT")),
        )
    except Exception as exc:
        raise ValidationError(f"rederivation_failed: {exc}") from exc
    return artifacts.manifest_bytes


def validate_and_record(
    submission_dir: Path,
    record_path: Path,
    out_root: Path,
    *,
    plugin_tree: Path | None = None,
    registry_clone: Path | None = None,
) -> tuple[Path, str, dict[str, Any] | None, bool]:
    """Validate the chain, label the signature state, and write the release.

    Returns (release_dir, signature_state, timestamp_record,
    timestamp_recommended). No key is taken and no signature is made here —
    the registry validates, publishes and labels.
    """
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
            "licence_spdx": manifest.get("licence", {}).get("spdx_expression", "MIT"),
        }
        derived = _rederive(plugin_tree, registry_clone, rederive_inputs, manifest)
        if derived != manifest_raw:
            raise ValidationError(
                "rederivation_mismatch: the submission manifest differs from a "
                "fresh derivation of the pinned inputs — the reviewed bytes "
                "changed (CR-14)"
            )

    publisher = str(manifest.get("publisher_id", ""))
    clone = registry_clone if registry_clone is not None else out_root.parent
    signature_state, timestamp, timestamp_recommended = _verify_signature(
        submission_dir, manifest_raw, publisher, clone, str(manifest.get("released_at", ""))
    )

    recorded = dict(manifest)
    recorded["manifest_version"] = SIGNED_MANIFEST_VERSION
    recorded["review"] = {
        "checklist_id": record["review"]["checklist_id"],
        "checklist_version": record["review"]["checklist_version"],
        "reviewer_id": record["review"]["reviewer_id"],
        "outcome": record["review"]["outcome"],
        "record_sha256": sha256_hex(record_raw),
    }
    recorded_raw = canonical_bytes(recorded)

    # Fold L2: identity segments are shape-checked before any path is built -
    # a traversal-shaped registry_id can never escape releases/.
    _segment = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
    for label, value in (
        ("registry_id", str(manifest["registry_id"])),
        ("package_id", str(manifest["package_id"])),
        ("version", str(manifest["version"])),
    ):
        for part in value.split("/"):
            if _segment.fullmatch(part) is None:
                raise ValidationError(f"release_path_unsafe:{label}={value!r}")
    release_dir: Path = (
        out_root
        / str(manifest["registry_id"])
        / str(manifest["package_id"])
        / str(manifest["version"])
    )
    if release_dir.exists():
        raise ValidationError(f"release_exists: {release_dir} (releases are immutable)")
    release_dir.mkdir(parents=True)
    (release_dir / "manifest.json").write_bytes(recorded_raw)
    (release_dir / "payload.zip").write_bytes(payload)
    # The publisher's signature was made over the SUBMISSION manifest at
    # package time; the recorded manifest adds the review block afterwards.
    # The signed bytes ride the release tree as submission-manifest.json so
    # the signature stays verifiable in place (and the review record's D_sub
    # pin names exactly these bytes).
    (release_dir / "submission-manifest.json").write_bytes(manifest_raw)
    sig_path = submission_dir / "manifest.sig"
    if sig_path.is_file():
        (release_dir / "manifest.sig").write_bytes(sig_path.read_bytes())
    for name in ("timestamp.token", "timestamp.json"):
        source = submission_dir / name
        if source.is_file():
            (release_dir / name).write_bytes(source.read_bytes())
    return release_dir, signature_state, timestamp, timestamp_recommended


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--plugin-tree", type=Path, default=None)
    parser.add_argument("--registry-clone", type=Path, default=None)
    args = parser.parse_args()
    try:
        release_dir, state, timestamp, recommended = validate_and_record(
            args.submission,
            args.record,
            args.out,
            plugin_tree=args.plugin_tree,
            registry_clone=args.registry_clone,
        )
    except ValidationError as exc:
        print(f"sign_release: {exc}", file=sys.stderr)
        return 1
    print(f"recorded {release_dir} (signature_state={state})")
    if timestamp is not None:
        print(f"  timestamp: {timestamp['tsa']} at {timestamp['signed_at']}")
    if recommended:
        print("  timestamp_recommended: true (an un-timestamped signature is "
              "valid until key expiry; timestamping keeps it valid past expiry)")
    print(
        "publish record fields: "
        + json.dumps(
            {
                "signature_state": state,
                "timestamp": timestamp,
                "timestamp_recommended": recommended,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
