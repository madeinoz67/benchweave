"""validate-and-record arms (owner ruling 2026-10-02, issue #223).

The registry validates + publishes + labels, never signs: the lane key is
gone. A publisher-signed submission validates against the publisher's
RECORDED public key; signed-but-invalid REJECTS; unsigned publishes labeled;
a trusted timestamp keeps a signature valid past key expiry/revocation.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

REPO = Path(__file__).resolve().parents[2]
SDK_SRC = REPO / "packages" / "sdk" / "src"
SIGN_RELEASE = REPO / "scripts" / "registry" / "sign_release.py"

pytestmark = pytest.mark.skipif(
    not (SDK_SRC / "benchweave_sdk" / "publishing.py").is_file(),
    reason="packages/sdk absent (deinitialized submodule); CI checks it out",
)

HEX40 = "1" * 40
CAPABILITIES_NONE = {
    "network_egress": False,
    "subprocess_or_native_library": False,
    "filesystem_writes_beyond_evidence_retention": False,
}
#: A DER token carrying a UTCTime inside the fixture window below.
TIMESTAMP_TOKEN = bytes([0x17, 13]) + b"260101120000Z"
TIMESTAMP_RECORD = {
    "signature_sha256": None,  # filled per-fixture (binds the actual sig)
    "signed_at": "260101120000Z",
    "token_sha256": hashlib.sha256(TIMESTAMP_TOKEN).hexdigest(),
    "tsa": "https://tsa.example",
}
KEY_WINDOW = {"not_before": "2020-01-01T00:00:00Z", "not_after": "2026-06-01T00:00:00Z"}


def _load_sign_release() -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location("sign_release_test", SIGN_RELEASE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sign_release = _load_sign_release()


def _sdk_publishing() -> Any:
    if str(SDK_SRC) not in sys.path:
        sys.path.insert(0, str(SDK_SRC))
    import benchweave_sdk.publishing as publishing

    return publishing


def _make_plugin(root: Path) -> Path:
    plugin = root / "wgt_widget"
    source = plugin / "src" / "benchweave_wgt_widget"
    source.mkdir(parents=True, exist_ok=True)
    descriptor = {
        "otdp_version": "0.2.2",
        "descriptor_version": "0.2.0",
        "id": "org.example.widget",
        "display_name": "Widget fixture",
        "description": "Synthetic widget fixture for the validator arms.",
        "identity": {
            "strategy": "adapter",
            "manufacturer": "Exampleworks",
            "model": "widget-1",
            "firmware_policy": "commissioned",
        },
        "integration": {
            "mode": "adapter",
            "adapter": {
                "entry_point": "benchweave_wgt_widget.adapter:create_plugin",
                "api_version": "1.1",
                "version": "0.1.0",
                "dependencies": [],
                "permissions": [],
            },
        },
        "transport": {"type": "serial"},
        "capabilities": ["identify", "read"],
    }
    (source / "descriptor.json").write_bytes(json.dumps(descriptor).encode())
    (source / "adapter.py").write_text("def create_plugin():\n    return object()\n")
    (source / "__init__.py").write_text("")
    docs = plugin / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "protocol-evidence.md").write_text("# Evidence\n\nSynthetic mocks only.\n")
    (plugin / "LICENSE").write_text("MIT (fixture)\n")
    (plugin / "README.md").write_text("# Widget\n")
    (plugin / "pyproject.toml").write_text(
        '[project]\nname = "widget"\nversion = "0.1.0"\nrequires-python = ">=3.13"\n'
    )
    return plugin


def _public_pem(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()


def _make_clone(
    root: Path,
    *,
    key: Ed25519PrivateKey | None = None,
    window: dict[str, str] | None = None,
) -> Path:
    clone = root / "registry-clone"
    (clone / "records").mkdir(parents=True, exist_ok=True)
    entry: dict[str, Any] = {
        "github": "madeinoz67",
        "namespace": "madeinoz67",
        "publisher_id": "madeinoz67",
        "publisher_repo_protections": [
            {"protection": "push-protection", "state": "declared-not-verified"}
        ],
        "vetted_at": "2026-10-01T00:00:00Z",
    }
    if key is not None:
        entry["ed25519_public_key_pem"] = _public_pem(key)
    if window is not None:
        entry["key_validity"] = window
    (clone / "records" / "publishers.json").write_bytes(
        json.dumps(
            {"publishers": [entry], "publishers_version": 1},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n"
    )
    (clone / "lane-rules.json").write_bytes(
        json.dumps(
            {
                "rules_version": 1,
                "namespace_rules": {
                    "reserved_namespaces": ["benchweave", "otdp", "dev", "stg"],
                    "reserved_plugins": [],
                    "dev_registry_prefix": "dev-",
                },
                "similarity_rule": {
                    "params": {
                        "case_sensitive": False,
                        "separator_characters": ["-", "_", ".", "/"],
                        "confusable_map": {"0": "o"},
                        "max_edit_distance": 2,
                    }
                },
            }
        ).encode()
        + b"\n"
    )
    return clone


def _submission(
    root: Path, *, key: Ed25519PrivateKey | None = None
) -> tuple[Path, Path, dict[str, Any]]:
    """A packaged submission (+ publisher signature when a key is given)."""
    publishing = _sdk_publishing()
    plugin = _make_plugin(root)
    clone = _make_clone(root, key=key)
    artifacts = publishing.build_submission(
        plugin,
        registry_clone=clone,
        source_url="https://github.com/example/widget",
        revision=HEX40,
        publisher="madeinoz67",
        capability_declaration=dict(CAPABILITIES_NONE),
    )
    submission_dir = root / "artifacts"
    artifacts.write(submission_dir)
    if key is not None:
        (submission_dir / "manifest.sig").write_bytes(
            publishing.sign_manifest_bytes(artifacts.manifest_bytes, _key_path(root, key))
        )
    record = {
        "record_type": "review",
        "record_version": "1.0.0",
        "kind": "admitted-release",
        "created_at": "2026-10-01T00:00:00Z",
        "actor": "madeinoz67",
        "review": {
            "publisher": "madeinoz67",
            "plugin": "widget",
            "version": "0.1.0",
            "checklist_id": "review-checklist",
            "checklist_version": "1",
            "reviewer_id": "madeinoz67",
            "outcome": "accepted",
            "submission_manifest_sha256": hashlib.sha256(artifacts.manifest_bytes).hexdigest(),
            "source_revision": HEX40,
            "closure_digest": artifacts.submission["closure_digest"],
            "capability_declaration": dict(CAPABILITIES_NONE),
            "platform_findings": [
                {"source": "code-scanning", "state": "consulted-no-findings"}
            ],
            "execution_model_disclosure": (
                "in-process execution with full gateway authority; no Python sandbox"
            ),
        },
    }
    record_path = root / "review-1.json"
    record_path.write_bytes(sign_release.canonical_bytes(record))
    return submission_dir, record_path, record


_KEY_CACHE: dict[int, Ed25519PrivateKey] = {}


def _key_path(root: Path, key: Ed25519PrivateKey) -> Path:
    path = root / "publisher-key.pem"
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return path


def _fresh_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def test_publisher_signed_submission_records_signed_valid(tmp_path: Path) -> None:
    key = _fresh_key()
    submission_dir, record_path, _record = _submission(tmp_path, key=key)
    release_dir, state, timestamp, recommended = sign_release.validate_and_record(
        submission_dir, record_path, tmp_path / "releases",
        registry_clone=tmp_path / "registry-clone",
    )
    assert state == "signed-valid"
    assert timestamp is None
    assert (release_dir / "manifest.sig").is_file()
    # The registry NEVER signs: no registry-produced signature anywhere.
    assert sorted(p.name for p in release_dir.iterdir()) == [
        "manifest.json", "manifest.sig", "payload.zip", "submission-manifest.json",
    ]
    manifest = json.loads((release_dir / "manifest.json").read_bytes())
    assert manifest["review"]["record_sha256"] == hashlib.sha256(
        record_path.read_bytes()
    ).hexdigest()


def test_signed_but_invalid_is_rejected(tmp_path: Path) -> None:
    """RED arm (a): a present signature that does not verify refuses."""
    key = _fresh_key()
    submission_dir, record_path, _record = _submission(tmp_path, key=key)
    manifest = json.loads((submission_dir / "manifest.json").read_bytes())
    manifest["summary"] = "changed after signing"
    (submission_dir / "manifest.json").write_bytes(sign_release.canonical_bytes(manifest))
    record = json.loads(record_path.read_bytes())
    record["review"]["submission_manifest_sha256"] = hashlib.sha256(
        (submission_dir / "manifest.json").read_bytes()
    ).hexdigest()
    record_path.write_bytes(sign_release.canonical_bytes(record))
    with pytest.raises(sign_release.ValidationError) as exc:
        sign_release.validate_and_record(
            submission_dir, record_path, tmp_path / "releases",
            registry_clone=tmp_path / "registry-clone",
        )
    assert str(exc.value).startswith("signature_invalid:")


def test_signature_without_recorded_key_is_rejected(tmp_path: Path) -> None:
    key = _fresh_key()
    submission_dir, record_path, _record = _submission(tmp_path, key=key)
    # The clone records the publisher WITHOUT a key.
    clone = _make_clone(tmp_path / "nokey", key=None)
    (tmp_path / "nokey" / "registry-clone" / "records").mkdir(parents=True, exist_ok=True)
    with pytest.raises(sign_release.ValidationError) as exc:
        sign_release.validate_and_record(
            submission_dir, record_path, tmp_path / "releases", registry_clone=clone,
        )
    assert str(exc.value).startswith("signature_invalid:")


def test_unsigned_submission_publishes_labeled(tmp_path: Path) -> None:
    """RED arm (b): unsigned is ACCEPTED, labeled in the record fields."""
    submission_dir, record_path, _record = _submission(tmp_path)
    release_dir, state, timestamp, recommended = sign_release.validate_and_record(
        submission_dir, record_path, tmp_path / "releases",
        registry_clone=tmp_path / "registry-clone",
    )
    assert state == "unsigned"
    assert timestamp is None
    assert not (release_dir / "manifest.sig").exists()
    assert (release_dir / "manifest.json").is_file()


def test_timestamped_signature_survives_expired_key(tmp_path: Path) -> None:
    """RED arm (c): validity judged at the TSA-attested time.

    The key window CLOSED 2026-06-01 (expired long before today); the trusted
    timestamp attests 2026-01-01, inside the window — the signature stays
    valid. Without the timestamp the same submission would fail the window.
    """
    key = _fresh_key()
    submission_dir, record_path, _record = _submission(tmp_path, key=key)
    record = dict(TIMESTAMP_RECORD)
    record["signature_sha256"] = hashlib.sha256(
        (submission_dir / "manifest.sig").read_bytes()
    ).hexdigest()
    (submission_dir / "timestamp.token").write_bytes(TIMESTAMP_TOKEN)
    (submission_dir / "timestamp.json").write_bytes(sign_release.canonical_bytes(record))
    # The clone's publisher records the EXPIRED window.
    clone = _make_clone(tmp_path / "expired", key=key, window=KEY_WINDOW)
    release_dir, state, timestamp, recommended = sign_release.validate_and_record(
        submission_dir, record_path, tmp_path / "releases", registry_clone=clone,
    )
    assert state == "signed-valid"
    assert timestamp is not None and timestamp["signed_at"] == "260101120000Z"
    assert recommended is False
    assert (release_dir / "timestamp.token").is_file()


def test_untimestamped_expired_window_is_accepted_with_advisory(
    tmp_path: Path,
) -> None:
    """Owner refinement (2026-10-02): timestamping is optional but
    recommended — an un-timestamped signed release NEVER refuses; the
    advisory records the honest horizon (valid until key expiry). RED
    baseline (quoted from the pre-refinement run): this exact fixture
    refused with 'signature_invalid: the signing key was not valid at the
    signing time (2026-10-01 ...) outside [2020-01-01, 2026-06-01]'."""
    key = _fresh_key()
    submission_dir, record_path, _record = _submission(tmp_path, key=key)
    clone = _make_clone(tmp_path / "expired2", key=key, window=KEY_WINDOW)
    _release_dir, state, timestamp, recommended = sign_release.validate_and_record(
        submission_dir,
        record_path,
        tmp_path / "releases",
        registry_clone=clone,
    )
    assert state == "signed-valid"
    assert timestamp is None
    assert recommended is True


def test_timestamped_time_outside_window_still_refuses(tmp_path: Path) -> None:
    """The genuine-invalid case that survives the refinement: a TSA-attested
    signing time OUTSIDE the key window means the key was not valid when the
    signing happened — that refuses."""
    import hashlib

    key = _fresh_key()
    submission_dir, record_path, _record = _submission(tmp_path, key=key)
    token = bytes([0x18, 19]) + b"20180101120000.000Z"  # GeneralizedTime, 2018 (19 chars)
    record = {
        "signature_sha256": hashlib.sha256(
            (submission_dir / "manifest.sig").read_bytes()
        ).hexdigest(),
        "signed_at": "20180101120000.000Z",
        "token_sha256": hashlib.sha256(token).hexdigest(),
        "tsa": "https://tsa.example",
    }
    (submission_dir / "timestamp.token").write_bytes(token)
    (submission_dir / "timestamp.json").write_bytes(sign_release.canonical_bytes(record))
    clone = _make_clone(tmp_path / "outside", key=key, window=KEY_WINDOW)
    with pytest.raises(sign_release.ValidationError) as exc:
        sign_release.validate_and_record(
            submission_dir, record_path, tmp_path / "releases", registry_clone=clone,
        )
    assert str(exc.value).startswith("signature_invalid:")


def test_timestamp_binding_lies_are_rejected(tmp_path: Path) -> None:
    key = _fresh_key()
    submission_dir, record_path, _record = _submission(tmp_path, key=key)
    record = dict(TIMESTAMP_RECORD)
    record["signature_sha256"] = hashlib.sha256(b"not-the-signature").hexdigest()
    (submission_dir / "timestamp.token").write_bytes(TIMESTAMP_TOKEN)
    (submission_dir / "timestamp.json").write_bytes(sign_release.canonical_bytes(record))
    with pytest.raises(sign_release.ValidationError) as exc:
        sign_release.validate_and_record(
            submission_dir, record_path, tmp_path / "releases",
            registry_clone=tmp_path / "registry-clone",
        )
    assert str(exc.value).startswith("timestamp_invalid:")


def test_post_review_submission_change_refuses(tmp_path: Path) -> None:
    key = _fresh_key()
    submission_dir, record_path, _record = _submission(tmp_path, key=key)
    manifest = json.loads((submission_dir / "manifest.json").read_bytes())
    manifest["summary"] = "changed after review"
    (submission_dir / "manifest.json").write_bytes(sign_release.canonical_bytes(manifest))
    with pytest.raises(sign_release.ValidationError) as exc:
        sign_release.validate_and_record(
            submission_dir, record_path, tmp_path / "releases",
            registry_clone=tmp_path / "registry-clone",
        )
    assert str(exc.value).startswith("submission_digest_mismatch:")


def test_rederivation_mismatch_refuses(tmp_path: Path) -> None:
    key = _fresh_key()
    submission_dir, record_path, _record = _submission(tmp_path, key=key)
    plugin = _make_plugin(tmp_path)
    (plugin / "src" / "benchweave_wgt_widget" / "adapter.py").write_text(
        "def create_plugin():\n    return 'mutated after review'\n"
    )
    clone = _make_clone(tmp_path, key=key)
    with pytest.raises(sign_release.ValidationError) as exc:
        sign_release.validate_and_record(
            submission_dir, record_path, tmp_path / "releases",
            plugin_tree=plugin, registry_clone=clone,
        )
    assert str(exc.value).startswith("rederivation_mismatch:")


def test_rederivation_agreement_records(tmp_path: Path) -> None:
    key = _fresh_key()
    submission_dir, record_path, _record = _submission(tmp_path, key=key)
    plugin = tmp_path / "wgt_widget"
    clone = _make_clone(tmp_path, key=key)
    _release_dir, state, _timestamp, _recommended = sign_release.validate_and_record(
        submission_dir, record_path, tmp_path / "releases",
        plugin_tree=plugin, registry_clone=clone,
    )
    assert state == "signed-valid"


def test_non_mit_licence_survives_rederivation(tmp_path: Path) -> None:
    publishing = _sdk_publishing()
    plugin = _make_plugin(tmp_path)
    clone = _make_clone(tmp_path, key=_fresh_key())
    artifacts = publishing.build_submission(
        plugin, registry_clone=clone,
        source_url="https://github.com/example/widget", revision=HEX40,
        publisher="madeinoz67", capability_declaration=dict(CAPABILITIES_NONE),
        licence_spdx="LicenseRef-Proprietary AND MIT",
    )
    submission_dir = tmp_path / "artifacts-nonmit"
    artifacts.write(submission_dir)
    manifest = json.loads(artifacts.manifest_bytes)
    assert manifest["licence"]["spdx_expression"] == "LicenseRef-Proprietary AND MIT"
    record = {
        "review": {
            "submission_manifest_sha256": hashlib.sha256(artifacts.manifest_bytes).hexdigest(),
            "closure_digest": artifacts.submission["closure_digest"],
            "outcome": "accepted",
        }
    }
    record_path = tmp_path / "review-nonmit.json"
    record_path.write_bytes(sign_release.canonical_bytes(record))
    _full_record = {
        **record,
        "review": {
            **record["review"],
            "checklist_id": "review-checklist",
            "checklist_version": "1",
            "reviewer_id": "madeinoz67",
            "source_revision": HEX40,
            "capability_declaration": dict(CAPABILITIES_NONE),
            "platform_findings": [{"source": "code-scanning", "state": "consulted-no-findings"}],
            "execution_model_disclosure": (
                "in-process execution with full gateway authority; no Python sandbox"
            ),
        },
    }
    record_path.write_bytes(sign_release.canonical_bytes(_full_record))
    release_dir, _state, _ts, _rec = sign_release.validate_and_record(
        submission_dir, record_path, tmp_path / "releases",
        plugin_tree=plugin, registry_clone=clone,
    )
    signed = json.loads((release_dir / "manifest.json").read_bytes())
    assert signed["licence"]["spdx_expression"] == "LicenseRef-Proprietary AND MIT"


def test_release_immutability_refuses_rerun(tmp_path: Path) -> None:
    submission_dir, record_path, _record = _submission(tmp_path)
    sign_release.validate_and_record(
        submission_dir, record_path, tmp_path / "releases",
        registry_clone=tmp_path / "registry-clone",
    )
    with pytest.raises(sign_release.ValidationError) as exc:
        sign_release.validate_and_record(
            submission_dir, record_path, tmp_path / "releases",
            registry_clone=tmp_path / "registry-clone",
        )
    assert str(exc.value).startswith("release_exists:")
