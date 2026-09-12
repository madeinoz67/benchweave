"""Startup bench admission: the fixture lattice becomes the store inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from benchweave.content.store import ContentStore
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
