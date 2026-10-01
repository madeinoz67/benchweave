"""Builder parity: the SDK's submission builder and the gateway's deterministic
builder discipline agree byte-for-byte (design §3.1, issue #223 slice 1).

The two repos stay decoupled — the SDK never imports gateway code (REG-4) —
and this test is the agreement pin: the SDK-built DPS-150 submission manifest
is canonical under the GATEWAY's one canonical serialization, its payload
archive is byte-identical to the gateway builder's recipe over the same
members, and the gateway's manifest loader accepts it under the ACTIVE schema.
Diverge either builder's byte discipline (zip timestamps, member ordering,
canonical form) and this fails.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

from benchweave.registry.manifests import canonical_manifest_bytes
from benchweave.registry.schemas import load_manifest_document

REPO = Path(__file__).resolve().parents[2]
SDK_SRC = REPO / "packages" / "sdk" / "src"
DPS150 = REPO / "plugins" / "fnirsi" / "dps150"

pytestmark = pytest.mark.skipif(
    not (SDK_SRC / "benchweave_sdk" / "publishing.py").is_file(),
    reason="packages/sdk absent (deinitialized submodule); CI checks it out",
)

CAPABILITIES_NONE = {
    "network_egress": False,
    "subprocess_or_native_library": False,
    "filesystem_writes_beyond_evidence_retention": False,
}
SOURCE_URL = "https://github.com/madeinoz67/benchweave"
REVISION = "45d5e7fdc45dc6bbf765b1c8e85af70a2d830d94"


def _load_registry_common() -> Any:
    """The gateway's keyless builder module, by explicit path."""
    spec = importlib.util.spec_from_file_location(
        "parity_registry_common", REPO / "scripts" / "registry" / "registry_common.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
                    "reserved_plugins": ["sim-psu"],
                    "dev_registry_prefix": "dev-",
                },
                "similarity_rule": {
                    "params": {
                        "case_sensitive": False,
                        "separator_characters": ["-", "_", ".", "/"],
                        "confusable_map": {"0": "o", "1": "l", "5": "s"},
                        "max_edit_distance": 2,
                    }
                },
                # Fixture state: the parity arm builds the REAL dps150, whose
                # descriptor carries the scoped_transport permission; the
                # tier rule (Q15 fold) admits this fixture publisher so the
                # byte-parity claim keeps exercising the builders. The real
                # registry's lane rules record NO admission — pinned by the
                # refusal arm below.
                "transport_tier_rule": {"admissions": ["madeinoz67"]},
            }
        ).encode()
        + b"\n"
    )
    return clone


def _dps150_artifacts(tmp_path: Path) -> Any:
    if str(SDK_SRC) not in sys.path:
        sys.path.insert(0, str(SDK_SRC))
    from benchweave_sdk.publishing import build_submission

    return build_submission(
        DPS150,
        registry_clone=_make_clone(tmp_path),
        source_url=SOURCE_URL,
        revision=REVISION,
        publisher="madeinoz67",
        plugin="dps150",
        capability_declaration=dict(CAPABILITIES_NONE),
        licence_spdx="LicenseRef-Proprietary AND MIT",
    )


def test_sdk_manifest_is_canonical_under_the_gateway_serialization(
    tmp_path: Path,
) -> None:
    artifacts = _dps150_artifacts(tmp_path)
    assert canonical_manifest_bytes(artifacts.manifest) == artifacts.manifest_bytes


def test_sdk_payload_matches_the_gateway_zip_recipe(tmp_path: Path) -> None:
    """The gateway builder's zip discipline over the same members is byte-identical."""
    registry_common = _load_registry_common()
    artifacts = _dps150_artifacts(tmp_path)
    with zipfile.ZipFile(io.BytesIO(artifacts.payload_bytes)) as archive:
        members = [
            (name, archive.read(name))
            for name in sorted(archive.namelist())
        ]
    assert registry_common._zip_bytes(members) == artifacts.payload_bytes


def test_gateway_loader_accepts_the_sdk_submission(tmp_path: Path) -> None:
    """The gateway's exact-byte loader validates the SDK-built manifest."""
    artifacts = _dps150_artifacts(tmp_path)
    digest = hashlib.sha256(artifacts.manifest_bytes).hexdigest()
    document = load_manifest_document(
        artifacts.manifest_bytes, digest, max_bytes=1_000_000
    )
    assert document.content["package_id"] == "madeinoz67/dps150"
    assert document.content["manifest_version"] == "0.1.1"  # submission form
    assert document.content["source"]["revision"] == REVISION


def test_gateway_and_sdk_digest_derivation_agree(tmp_path: Path) -> None:
    """sha256/canonical-form agreement on the digest lattice's inputs."""
    registry_common = _load_registry_common()
    artifacts = _dps150_artifacts(tmp_path)
    assert (
        registry_common._sha(artifacts.manifest_bytes)
        == hashlib.sha256(artifacts.manifest_bytes).hexdigest()
    )
    assert (
        registry_common._canonical(artifacts.manifest)
        == canonical_manifest_bytes(artifacts.manifest)
    )


def test_parity_has_teeth_against_zip_discipline_drift(tmp_path: Path) -> None:
    """A deflated (non-STORED) archive is byte-different and detected."""
    artifacts = _dps150_artifacts(tmp_path)
    with zipfile.ZipFile(io.BytesIO(artifacts.payload_bytes)) as archive:
        members = [(name, archive.read(name)) for name in sorted(archive.namelist())]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as drifted:
        for path, data in sorted(members):
            info = zipfile.ZipInfo(path, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            drifted.writestr(info, data)
    assert buf.getvalue() != artifacts.payload_bytes  # the discipline detects drift


def test_the_real_dps150_descriptor_refuses_without_an_admission(tmp_path: Path) -> None:
    """The folded tier rule, on the real descriptor: scoped_transport with no
    recorded admission and no triples refuses (the M3 fold's RED arm, now
    green; the committed dogfood release predates the fold and is disclosed
    in the fold's report)."""
    import sys

    if str(SDK_SRC) not in sys.path:
        sys.path.insert(0, str(SDK_SRC))
    from benchweave_sdk.publishing import PublishingError, build_submission

    clone = _make_clone(tmp_path)
    rules = json.loads((clone / "lane-rules.json").read_bytes())
    rules.pop("transport_tier_rule", None)
    (clone / "lane-rules.json").write_bytes(json.dumps(rules).encode() + b"\n")
    with pytest.raises(PublishingError) as exc:
        build_submission(
            DPS150,
            registry_clone=clone,
            source_url=SOURCE_URL,
            revision=REVISION,
            publisher="madeinoz67",
            plugin="dps150",
            capability_declaration=dict(CAPABILITIES_NONE),
        )
    assert str(exc.value).startswith("transport_triples_absent:")
