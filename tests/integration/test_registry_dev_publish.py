# tests/integration/test_registry_dev_publish.py
"""unsigned-dev-plugins slice (WP06 follow-up): the unsigned dev publisher
and the keyless developer loop.

``scripts/registry/publish_dev.py`` packages a plugin directory into a local
dev registry — fresh manifests under registry id ``dev-local``, no ``.sig``
files, and no private key material anywhere in the loop. The full developer
path this file pins: publish (unsigned) → resolve (a ``dev-unsigned`` origin
over the dev root alongside the signed origin-main fixtures that serve the
pinned dependencies) → admit (fresh cache + lock) → ``load_plugin`` from the
content-addressed cache → the configure dispatch exactly as
``tests/contract/test_sim_plugins.py`` constructs it.

Honest posture, restated from the design: a dev origin's status bytes are
unauthenticated by design — a local process that can write the dev root can
forge lifecycle state. Every integrity, identity, and sequence gate stays on,
and the origin-main dependencies in the default closure are still
signature-verified against the committed public root. The mixed closure
(unsigned implementation over signed production descriptor/profile) is
intentional; the package lock records both origins.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchweave.host import QuotaState
from benchweave.host.types import OperationRequest, OperationVerb
from benchweave.registry.activation import load_plugin
from benchweave.registry.admission import (
    AdmissionLimits,
    Approval,
    admit,
)
from benchweave.registry.authenticity import load_trust_root
from benchweave.registry.resolver import (
    LocalDirectorySource,
    OriginConfig,
    Resolver,
)

REPO = Path(__file__).resolve().parents[2]
REG = REPO / "fixtures" / "registry"
PUBLISH_DEV = REPO / "scripts" / "registry" / "publish_dev.py"
# Fixed admission/resolve clock, same date the WP06 contract suite freezes
# (never a hand-typed nanosecond literal — see the Task 1 review ruling).
NOW_NS = int(datetime(2026, 9, 12, tzinfo=UTC).timestamp() * 1_000_000_000)

DEV_ID = "dev-local"
DEV_IMPL_PACKAGE = "dev/sim_psu"
DEV_DESC_PACKAGE = "dev/sim-psu-descriptor"
ORIGIN_MAIN = "origin-main"
PROFILE_PACKAGE = "benchweave/dc-psu-profile"
CATALOGUE_DESC_PACKAGE = "benchweave/sim-psu-descriptor"

# The configure vector, verbatim from tests/contract/test_sim_plugins.py (the
# construction authority) via tests/integration/test_registry_reuse.py.
ACTION_CONFIGURE = "otdp.dc_psu.configure/1.0.0"
CONFIGURE_INPUT: dict[str, Any] = {
    "configuration_id": "cfg-1",
    "channel": "ch1",
    "voltage_v": 5.0,
    "current_limit_a": 0.5,
    "ovp_v": 5.5,
    "ocp_a": 0.5,
}
RELEASE_FILES = ("manifest.json", "payload.zip", "status.json")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _main_root() -> Any:
    return load_trust_root(ORIGIN_MAIN, REG / "keys" / "main.pub.pem")


def _catalogue_pins() -> dict[tuple[str, str], str]:
    """Origin-main manifest digests from the committed fixture catalogue."""
    catalogue = json.loads((REG / "catalogue.json").read_bytes())
    return {
        (row["registry_id"], row["package_id"]): row["manifest_sha256"]
        for row in catalogue["releases"]
    }


def _publish(*args: str) -> subprocess.CompletedProcess[bytes]:
    """Run the dev publisher exactly as a developer would, from the repo root."""
    return subprocess.run(
        [sys.executable, str(PUBLISH_DEV), *args],
        cwd=REPO,
        capture_output=True,
    )


def test_publish_dev_transitively_imports_no_cryptography() -> None:
    """The keyless dev loop must not pull in the signing stack.

    A fresh interpreter imports publish_dev; ``cryptography`` must stay out
    of ``sys.modules``: the dev loop neither signs nor verifies, and the
    publisher's builders are keyless by design (registry_common carries them;
    build_fixtures keeps only the signing bits).
    """
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import publish_dev; "
        "print('CLEAN' if 'cryptography' not in sys.modules else 'CRYPTO')"
    )
    probe = subprocess.run(
        [sys.executable, "-c", code, str(PUBLISH_DEV.parent)],
        capture_output=True,
        cwd=REPO,
    )
    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.strip() == b"CLEAN"


def _dev_origins(reg_root: Path) -> dict[str, OriginConfig]:
    """The developer's origin map: an unsigned dev origin plus signed origin-main.

    The dev origin routes the ``dev`` namespace with ``signature_policy=
    "dev-unsigned"`` (``root=None`` is valid only there); origin-main keeps
    the fail-closed default and serves the ``benchweave``-namespace
    dependencies the publisher pinned from the catalogue.
    """
    return {
        DEV_ID: OriginConfig(
            registry_id=DEV_ID,
            root=None,
            source=LocalDirectorySource(reg_root / DEV_ID),
            namespaces=("dev",),
            signature_policy="dev-unsigned",
        ),
        ORIGIN_MAIN: OriginConfig(
            registry_id=ORIGIN_MAIN,
            root=_main_root(),
            source=LocalDirectorySource(REG / ORIGIN_MAIN),
            namespaces=("benchweave",),
        ),
    }


def _resolve_impl(reg_root: Path) -> Any:
    return Resolver(_dev_origins(reg_root)).resolve(
        DEV_ID, DEV_IMPL_PACKAGE, "0.0.0", now_ns=NOW_NS, high_water={}
    )


def _impl_release(closure: Any) -> Any:
    return next(r for r in closure.releases if r.package_id == DEV_IMPL_PACKAGE)


def _impl_deps(release: Any) -> dict[tuple[str, str], str]:
    return {
        (dep["registry_id"], dep["package_id"]): dep["manifest_sha256"]
        for dep in release.manifest["dependencies"]
    }


def _admit(closure: Any, work: Path) -> None:
    admit(
        closure,
        cache_root=work / "cache",
        lock_path=work / "packages.lock.json",
        limits=AdmissionLimits(
            max_archive_bytes=1_000_000, max_files=100, max_unpacked_bytes=1_000_000
        ),
        approval=Approval(
            principal_id="benchweave-test",
            approved_at="2026-09-12T00:00:00Z",
            policy_id="local-policy",
            policy_version="1.0.0",
        ),
        now_ns=NOW_NS,
        roots={DEV_ID: None, ORIGIN_MAIN: _main_root()},
    )


class _NullServices:
    """Scoped-services stand-in, mirrored from test_registry_reuse."""

    def resolve_content(self, content_id: str) -> bytes:
        return b"{}"

    def retain_evidence(self, key: str, payload: bytes) -> str:
        return f"evidence-{key}"

    def emit_event(self, kind: str, body: dict[str, Any]) -> None:
        pass

    def quota_state(self) -> QuotaState:
        return QuotaState(dataset_bytes_used=0, evidence_entries_used=0, events_emitted=0)

    def register_reading_sink(self, sink: Any) -> None:
        pass


def _invoke(action_id: str, input_: dict[str, Any]) -> OperationRequest:
    """Verbatim construction from test_sim_plugins._invoke."""
    return OperationRequest(
        operation_id="op-1",
        verb=OperationVerb.INVOKE,
        arguments={"action_id": action_id, "input": input_},
    )


# --- the keyless developer loop ------------------------------------------------


def test_publish_admit_load_dispatch_roundtrip(tmp_path: Path) -> None:
    reg_root = tmp_path / "reg"
    published = _publish("plugins/sim_psu", "--out", str(reg_root))
    assert published.returncode == 0, published.stderr.decode()
    release_dir = reg_root / DEV_ID / DEV_IMPL_PACKAGE / "0.0.0"
    assert sorted(path.name for path in release_dir.iterdir()) == list(RELEASE_FILES)
    # Unsigned by construction: no signature sidecars anywhere in the dev tree.
    assert not list((reg_root / DEV_ID).rglob("*.sig"))

    closure = _resolve_impl(reg_root)
    # The dev closure: the unsigned implementation over its two signed
    # origin-main dependencies.
    assert len(closure.releases) == 3
    impl = _impl_release(closure)
    pins = _catalogue_pins()
    assert _impl_deps(impl) == {
        (ORIGIN_MAIN, CATALOGUE_DESC_PACKAGE): pins[(ORIGIN_MAIN, CATALOGUE_DESC_PACKAGE)],
        (ORIGIN_MAIN, PROFILE_PACKAGE): pins[(ORIGIN_MAIN, PROFILE_PACKAGE)],
    }

    _admit(closure, tmp_path)
    # Mixed closures are visible by construction: the lock records both origins.
    lock = json.loads((tmp_path / "packages.lock.json").read_bytes())
    assert {(row["registry_id"], row["package_id"]) for row in lock["packages"]} == {
        (DEV_ID, DEV_IMPL_PACKAGE),
        (ORIGIN_MAIN, CATALOGUE_DESC_PACKAGE),
        (ORIGIN_MAIN, PROFILE_PACKAGE),
    }

    plugin = load_plugin(
        tmp_path / "cache",
        impl.manifest,
        impl.manifest_sha256,
        entry_relpath="plugin/plugin.py",
    )
    plugin.plugin_open(_NullServices())
    try:
        configured = plugin.dispatch(
            _invoke(ACTION_CONFIGURE, CONFIGURE_INPUT), deadline_ns=10**12
        )
        assert configured.status.value == "ok"
        assert configured.data["result"]["configuration_id"] == "cfg-1"
    finally:
        plugin.plugin_close()


def test_publisher_is_deterministic(tmp_path: Path) -> None:
    outputs: list[dict[str, bytes]] = []
    for root in (tmp_path / "first", tmp_path / "second"):
        published = _publish("plugins/sim_psu", "--out", str(root))
        assert published.returncode == 0, published.stderr.decode()
        release = root / DEV_ID / DEV_IMPL_PACKAGE / "0.0.0"
        outputs.append({name: (release / name).read_bytes() for name in RELEASE_FILES})
    assert outputs[0] == outputs[1]


def test_descriptor_override_repins_dep(tmp_path: Path) -> None:
    reg_root = tmp_path / "reg"
    published = _publish(
        "plugins/sim_psu",
        "--descriptor",
        str(REPO / "fixtures" / "execution" / "descriptor-sim-psu.json"),
        "--out",
        str(reg_root),
    )
    assert published.returncode == 0, published.stderr.decode()
    # The override publishes a second dev release: the unsigned descriptor.
    dev_desc_dir = reg_root / DEV_ID / DEV_DESC_PACKAGE / "0.0.0"
    assert sorted(path.name for path in dev_desc_dir.iterdir()) == list(RELEASE_FILES)
    dev_desc_sha = _sha((dev_desc_dir / "manifest.json").read_bytes())

    closure = _resolve_impl(reg_root)
    assert len(closure.releases) == 3  # impl + dev descriptor + origin-main profile
    impl = _impl_release(closure)
    deps = _impl_deps(impl)
    assert (DEV_ID, DEV_DESC_PACKAGE) in deps
    # The implementation's descriptor dependency is repinned to the DEV
    # descriptor's digest (recomputed from the published manifest bytes), not
    # origin-main's.
    assert deps[(DEV_ID, DEV_DESC_PACKAGE)] == dev_desc_sha
    assert dev_desc_sha != _catalogue_pins()[(ORIGIN_MAIN, CATALOGUE_DESC_PACKAGE)]
    # The profile default pin survives the override untouched.
    assert deps[(ORIGIN_MAIN, PROFILE_PACKAGE)] == _catalogue_pins()[
        (ORIGIN_MAIN, PROFILE_PACKAGE)
    ]


def test_bad_plugin_dir_fails_clean(tmp_path: Path) -> None:
    reg_root = tmp_path / "reg"
    published = _publish("plugins/does_not_exist", "--out", str(reg_root))
    assert published.returncode != 0
    # A message naming the offender, not a bare traceback.
    assert b"plugins/does_not_exist" in published.stderr
    # No partial output tree: nothing was written before the failure.
    assert not reg_root.exists()
