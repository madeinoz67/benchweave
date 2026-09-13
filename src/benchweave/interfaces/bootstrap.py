"""Startup bench admission: the fixture lattice becomes the store inventory.

WP08 Task 7 adds the fixture resolver session: the local registry surface
(``registry/resolver.py`` over ``fixtures/registry/``) the two registry
change kinds dispatch through. Construction mirrors
``tests/integration/test_registry_reuse.py`` — one signed origin-main, the
same trust root, namespace routing, the same admission budgets — no
parallel invention (controller ruling: mirror the proven pattern).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from benchweave.content.store import ContentStore
from benchweave.registry.admission import AdmissionLimits
from benchweave.registry.authenticity import TrustRoot, load_trust_root
from benchweave.registry.manifests import Key
from benchweave.registry.resolver import LocalDirectorySource, OriginConfig, Resolver
from benchweave.state.store import Store

# The fixture lattice as it exists under fixtures/execution/ (verified
# 2026-09-12): singular documents are exact names, only the device
# descriptors and procedures are families. commissioning.json is admitted
# explicitly (it is also the bench configuration document). package-lock.json
# is referenced by lattice documents but is not itself admitted here.
_EXTRA_DOC_PATHS = ("safety-policy.json", "run-binding.json")
_EXTRA_DOC_GLOBS = ("procedure-*.json",)


def admit_startup_bench(
    store: Store, content: ContentStore, fixtures_dir: Path, *, now: str
) -> dict[str, Any]:
    bench_path = fixtures_dir / "bench.json"
    if not bench_path.is_file():
        raise FileNotFoundError(f"no bench document under {fixtures_dir}")
    bench_raw = bench_path.read_bytes()
    bench = json.loads(bench_raw)
    bench_id = str(bench["id"])

    commissioning_path = fixtures_dir / "commissioning.json"
    if not commissioning_path.is_file():
        raise FileNotFoundError(f"no commissioning document under {fixtures_dir}")
    commissioning_raw = commissioning_path.read_bytes()
    commissioning_text = commissioning_raw.decode()
    commissioning = json.loads(commissioning_raw)

    generation = store.current_generation(bench_id) or store.bump_generation(bench_id, now)
    store.put_bench(
        bench_id,
        generation,
        str(bench.get("qualification", "observation")),
        commissioning_text,
        str(bench.get("licence", "proprietary")),
        now,
    )
    stored: list[str] = [
        content_sha(content, bench_raw, bench, now),
        content_sha(content, commissioning_raw, commissioning, now),
    ]

    for descriptor_path in sorted(fixtures_dir.glob("descriptor-*.json")):
        raw = descriptor_path.read_bytes()
        descriptor = json.loads(raw)
        device_id = str(descriptor["id"])
        store.put_device(
            device_id,
            bench_id,
            generation,
            json.dumps(descriptor.get("profiles", [])),
            raw.decode(),
            "matched",
            str(descriptor.get("licence", "proprietary")),
            now,
        )
        stored.append(content_sha(content, raw, descriptor, now))

    for name in _EXTRA_DOC_PATHS:
        path = fixtures_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"lattice document {name} missing under {fixtures_dir}")
        raw = path.read_bytes()
        stored.append(content_sha(content, raw, json.loads(raw), now))
    for pattern in _EXTRA_DOC_GLOBS:
        for path in sorted(fixtures_dir.glob(pattern)):
            raw = path.read_bytes()
            stored.append(content_sha(content, raw, json.loads(raw), now))
    return {"bench_id": bench_id, "documents": stored}


def content_sha(
    content: ContentStore, raw: bytes, parsed: dict[str, Any], now: str
) -> str:
    sha = hashlib.sha256(raw).hexdigest()
    schema_id = str(parsed.get("$schema", parsed.get("schema_id", "urn:stg:admitted")))
    content.put_document(raw, sha, parsed, schema_id, now)
    return sha


# --- WP08 Task 7: the fixture resolver session --------------------------------

#: The one origin the gateway routes: the committed fixture catalogue's
#: signed origin-main (scope ruling: fixture registry only — no curated
#: remote publication paths, no network egress, no new registry
#: capabilities; this is wiring, not extension).
REGISTRY_ORIGIN = "origin-main"
REGISTRY_NAMESPACES = ("benchweave",)
#: Admission budgets mirrored verbatim from test_registry_reuse's proven
#: construction (sized for the contract-test fixture catalogue).
REGISTRY_ADMISSION_LIMITS = AdmissionLimits(
    max_archive_bytes=1_000_000, max_files=100, max_unpacked_bytes=1_000_000
)


@dataclass
class RegistrySession:
    """One gateway-local resolver session over the fixture registry.

    Constructed once (``build_registry_session``) and attached to the
    Operations seam; the two registry change kinds dispatch through it
    (resolve → admit → activate). ``high_water`` is the session's mutable
    rollback view shared between resolve and admit — the same map
    threading test_registry_reuse proves; admission also persists it under
    ``<cache_root>/high-water.json`` so the enforced sequences survive
    restarts. ``records_dir`` is the BASE for per-bench activation records
    (``<records_dir>/<bench_id>/activation-<n>.json``) — generations are
    per-bench, so the audit trail partitions by bench to keep record
    identities (the new generation) collision-free across benches.
    """

    resolver: Resolver
    #: Trust roots admission re-checks statuses against, keyed by registry
    #: id — must cover every origin the resolver routes.
    roots: dict[str, TrustRoot]
    high_water: dict[Key, int]
    cache_root: Path
    lock_path: Path
    records_dir: Path
    limits: AdmissionLimits
    #: Registry clock (status expiry / future-time / sequence gates).
    now_ns: Callable[[], int]
    registry_id: str = REGISTRY_ORIGIN


def build_registry_session(
    registry_dir: Path, work_root: Path, *, now_ns: Callable[[], int]
) -> RegistrySession:
    """Construct the fixture resolver session (the proven pattern).

    ``registry_dir`` is the committed fixture catalogue (``fixtures/registry``):
    the origin-main trust root loads from ``keys/main.pub.pem`` and its
    releases serve from ``origin-main/`` under the ``benchweave`` namespace
    — the exact construction ``tests/integration/test_registry_reuse.py``
    exercises, minus the fault-injection extras this gateway never routes
    (origin-b stays absent, present-never-routed is a test posture, not a
    gateway capability). ``work_root`` owns the session's local state:
    ``cache/`` (content-addressed admission cache), ``packages.lock.json``
    (the package lock each admission writes) and ``activations/`` (per-bench
    activation records). Signature posture is the fail-closed default
    (``required``): every manifest and status is verified against the trust
    root.
    """
    root = load_trust_root(REGISTRY_ORIGIN, registry_dir / "keys" / "main.pub.pem")
    origins: dict[str, OriginConfig] = {
        REGISTRY_ORIGIN: OriginConfig(
            registry_id=REGISTRY_ORIGIN,
            root=root,
            source=LocalDirectorySource(registry_dir / "origin-main"),
            namespaces=REGISTRY_NAMESPACES,
        )
    }
    return RegistrySession(
        resolver=Resolver(origins),
        roots={REGISTRY_ORIGIN: root},
        high_water={},
        cache_root=work_root / "cache",
        lock_path=work_root / "packages.lock.json",
        records_dir=work_root / "activations",
        limits=REGISTRY_ADMISSION_LIMITS,
        now_ns=now_ns,
    )
