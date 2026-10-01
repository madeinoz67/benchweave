"""sign_release arms: the digest chain from review record to signed release (CR-11/12/14).

The signer re-verifies the chain before any key is touched: the review record
pins the submission digest, the closure digest and the source revision; a
post-review change anywhere refuses. The happy path signs with a scratch key
(the lane key is maintainer-custodied; the test key never leaves tmp_path).
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
    Ed25519PublicKey,
)

from scripts.registry import sign_release

REPO = Path(__file__).resolve().parents[2]
SDK_SRC = REPO / "packages" / "sdk" / "src"

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
        "description": "Synthetic widget fixture for the signer arms.",
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


def _make_clone(root: Path) -> Path:
    clone = root / "registry-clone"
    (clone / "records").mkdir(parents=True, exist_ok=True)
    (clone / "records" / "publishers.json").write_bytes(
        b'{"publishers":[{"github":"madeinoz67","namespace":"madeinoz67",'
        b'"publisher_id":"madeinoz67","publisher_repo_protections":[{"protection":"push-protection",'
        b'"state":"declared-not-verified"}],"vetted_at":"2026-10-01T00:00:00Z"}],"publishers_version":1}\n'
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


def _submission(root: Path) -> tuple[Path, Path, Path, dict[str, Any]]:
    """A packaged submission, its review record, and a scratch lane key."""
    publishing = _sdk_publishing()
    plugin = _make_plugin(root)
    clone = _make_clone(root)
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
            "submission_manifest_sha256": hashlib.sha256(
                artifacts.manifest_bytes
            ).hexdigest(),
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
    key = Ed25519PrivateKey.generate()
    key_path = root / "lane-key.pem"
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return submission_dir, record_path, key_path, record


def _record_path(root: Path, record: dict[str, Any]) -> Path:
    path = root / "review-mutant.json"
    path.write_bytes(sign_release.canonical_bytes(record))
    return path


def test_signs_and_pins_the_review_record(tmp_path: Path) -> None:
    submission_dir, record_path, key_path, _record = _submission(tmp_path)
    release_dir = sign_release.sign(submission_dir, record_path, key_path, tmp_path / "releases")
    manifest_raw = (release_dir / "manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    assert manifest["manifest_version"] == "0.1.2"
    assert manifest["review"]["record_sha256"] == hashlib.sha256(
        record_path.read_bytes()
    ).hexdigest()
    # The one signature attests release and review together (Q2).
    private = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    assert isinstance(private, Ed25519PrivateKey)
    public = private.public_key()
    assert isinstance(public, Ed25519PublicKey)
    public.verify((release_dir / "manifest.sig").read_bytes(), manifest_raw)
    status = json.loads((release_dir / "status.json").read_bytes())
    assert status["release"]["manifest_sha256"] == hashlib.sha256(manifest_raw).hexdigest()
    public.verify(
        (release_dir / "status.sig").read_bytes(), (release_dir / "status.json").read_bytes()
    )


def test_post_review_submission_change_refuses(tmp_path: Path) -> None:
    submission_dir, record_path, key_path, _record = _submission(tmp_path)
    manifest = json.loads((submission_dir / "manifest.json").read_bytes())
    manifest["summary"] = "changed after review"
    (submission_dir / "manifest.json").write_bytes(sign_release.canonical_bytes(manifest))
    with pytest.raises(sign_release.SignError) as exc:
        sign_release.sign(submission_dir, record_path, key_path, tmp_path / "releases")
    assert str(exc.value).startswith("submission_digest_mismatch:")


def test_closure_digest_disagreement_refuses(tmp_path: Path) -> None:
    submission_dir, record_path, key_path, record = _submission(tmp_path)
    record["review"]["closure_digest"] = "f" * 64
    with pytest.raises(sign_release.SignError) as exc:
        sign_release.sign(
            submission_dir, _record_path(tmp_path, record), key_path, tmp_path / "releases"
        )
    assert str(exc.value).startswith("closure_digest_mismatch:")


def test_unaccepted_review_refuses(tmp_path: Path) -> None:
    submission_dir, record_path, key_path, record = _submission(tmp_path)
    record["review"]["outcome"] = "changes-requested"
    record["review"]["cited_failures"] = ["P-03"]
    with pytest.raises(sign_release.SignError) as exc:
        sign_release.sign(
            submission_dir, _record_path(tmp_path, record), key_path, tmp_path / "releases"
        )
    assert str(exc.value).startswith("review_not_accepted:")


def test_revision_pin_disagreement_refuses(tmp_path: Path) -> None:
    submission_dir, record_path, key_path, record = _submission(tmp_path)
    record["review"]["source_revision"] = "9" * 40
    with pytest.raises(sign_release.SignError) as exc:
        sign_release.sign(
            submission_dir, _record_path(tmp_path, record), key_path, tmp_path / "releases"
        )
    assert str(exc.value).startswith("source_revision_mismatch:")


def test_payload_lie_refuses(tmp_path: Path) -> None:
    submission_dir, record_path, key_path, _record = _submission(tmp_path)
    manifest = json.loads((submission_dir / "manifest.json").read_bytes())
    manifest["payload"]["sha256"] = "0" * 64
    (submission_dir / "manifest.json").write_bytes(sign_release.canonical_bytes(manifest))
    record = json.loads(record_path.read_bytes())
    record["review"]["submission_manifest_sha256"] = hashlib.sha256(
        (submission_dir / "manifest.json").read_bytes()
    ).hexdigest()
    with pytest.raises(sign_release.SignError) as exc:
        sign_release.sign(
            submission_dir, _record_path(tmp_path, record), key_path, tmp_path / "releases"
        )
    assert str(exc.value).startswith("payload_digest_mismatch:")


def test_rederivation_mismatch_refuses(tmp_path: Path) -> None:
    """CR-14's falsifier: the plugin tree changed after review."""
    submission_dir, record_path, key_path, _record = _submission(tmp_path)
    plugin = _make_plugin(tmp_path)
    (plugin / "src" / "benchweave_wgt_widget" / "adapter.py").write_text(
        "def create_plugin():\n    return 'mutated after review'\n"
    )
    clone = _make_clone(tmp_path)
    with pytest.raises(sign_release.SignError) as exc:
        sign_release.sign(
            submission_dir,
            record_path,
            key_path,
            tmp_path / "releases",
            plugin_tree=plugin,
            registry_clone=clone,
        )
    assert str(exc.value).startswith("rederivation_mismatch:")


def test_rederivation_agreement_signs(tmp_path: Path) -> None:
    """The control arm: the unmutated tree re-derives the submitted bytes."""
    submission_dir, record_path, key_path, _record = _submission(tmp_path)
    plugin = tmp_path / "wgt_widget"
    clone = _make_clone(tmp_path)
    release_dir = sign_release.sign(
        submission_dir,
        record_path,
        key_path,
        tmp_path / "releases",
        plugin_tree=plugin,
        registry_clone=clone,
    )
    assert (release_dir / "manifest.sig").is_file()


def test_release_immutability_refuses_resign(tmp_path: Path) -> None:
    submission_dir, record_path, key_path, _record = _submission(tmp_path)
    sign_release.sign(submission_dir, record_path, key_path, tmp_path / "releases")
    with pytest.raises(sign_release.SignError) as exc:
        sign_release.sign(submission_dir, record_path, key_path, tmp_path / "releases")
    assert str(exc.value).startswith("release_exists:")


def test_submission_artifacts_are_reproducible(tmp_path: Path) -> None:
    """A1's second-run discipline, through the signer's own view."""
    publishing = _sdk_publishing()
    plugin = _make_plugin(tmp_path)
    clone = _make_clone(tmp_path)
    first = publishing.build_submission(
        plugin,
        registry_clone=clone,
        source_url="https://github.com/example/widget",
        revision=HEX40,
        publisher="madeinoz67",
        capability_declaration=dict(CAPABILITIES_NONE),
    )
    second = publishing.build_submission(
        plugin,
        registry_clone=clone,
        source_url="https://github.com/example/widget",
        revision=HEX40,
        publisher="madeinoz67",
        capability_declaration=dict(CAPABILITIES_NONE),
    )
    assert first.manifest_bytes == second.manifest_bytes
    assert first.payload_bytes == second.payload_bytes
