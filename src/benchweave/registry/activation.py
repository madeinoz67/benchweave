# src/benchweave/registry/activation.py
"""Idle-boundary activation records and the cache plugin loader.

Activation is the only moment plugin code executes (registry contract §2):
search, inspect and admission treat packages as bytes; :func:`load_plugin`
imports them — from the content-addressed cache admission produced, never
from a source tree — when the host activates a configuration. Two surfaces:

* :func:`activate` — the idle boundary: refuse while a bench lease is live
  (``not_idle``), then write one generation record binding the package-lock
  digest into the new configuration generation. Pure file I/O; no plugin
  import happens here.
* :func:`load_plugin` — import one admitted release's implementation entry
  from ``<cache_root>/<manifest_sha256>/<entry_relpath>`` and construct the
  plugin instance, returned UNOPENED: the host calls ``plugin_open`` with
  scoped services (host ABI rule).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, cast

from benchweave.host.plugin import DevicePlugin
from benchweave.registry.admission import Admitted

#: The manifest inventory role an activation entry must carry.
IMPLEMENTATION_ROLE = "implementation"


class ActivationRejected(ValueError):
    """Activation refused; ``reason`` names the refusing rule."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ActivationRecord:
    """One activation: the lock digest bound into a new generation."""

    lock_sha256: str
    previous_generation: int
    new_generation: int
    activated_at: str


def _canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def activate(
    admitted: Admitted,
    *,
    bench_generation: int,
    bench_has_live_lease: bool,
    records_dir: Path,
    activated_at: str,
) -> ActivationRecord:
    """Activate an admitted closure at the idle boundary.

    Refuses with ``not_idle`` before touching the filesystem while a bench
    lease is live. Otherwise writes ``<records_dir>/activation-<n>.json``
    where ``<n>`` is the new generation — the record's identity, so
    sequential activations never collide — as canonical JSON carrying exactly
    the :class:`ActivationRecord` fields. A record already present for the
    new generation means the caller regressed ``bench_generation``; refused
    with ``generation_conflict`` rather than silently overwritten (the
    store owns generation monotonicity, so the audit trail stays
    append-only in practice). The bytes go to a temporary sibling first and
    are moved onto the record path with :func:`os.replace`, so a crash
    mid-write can never leave truncated JSON in the audit trail.
    """
    if bench_has_live_lease:
        raise ActivationRejected("not_idle")
    record = ActivationRecord(
        lock_sha256=admitted.lock_sha256,
        previous_generation=bench_generation,
        new_generation=bench_generation + 1,
        activated_at=activated_at,
    )
    records_dir.mkdir(parents=True, exist_ok=True)
    record_path = records_dir / f"activation-{record.new_generation}.json"
    if record_path.exists():
        raise ActivationRejected("generation_conflict")
    staged = record_path.with_name(record_path.name + ".tmp")
    staged.write_bytes(_canonical(asdict(record)))
    os.replace(staged, record_path)
    return record


def _default_clock() -> tuple[Callable[[], str], Callable[[], int]]:
    """Loader-supplied plugin clocks (the load signature carries none).

    ``now_fn`` reports real UTC time. ``monotonic_ns_fn`` reports real
    monotonic nanoseconds elapsed since this call — zero-based, like every
    injected test clock in the tree, so deadlines issued against plugin
    construction (the contract suite's ``deadline_ns=10**12``) keep their
    meaning instead of expiring against a machine-uptime timebase.
    """
    anchor_ns = time.monotonic_ns()

    def now_fn() -> str:
        return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    def monotonic_ns_fn() -> int:
        return time.monotonic_ns() - anchor_ns

    return now_fn, monotonic_ns_fn


def load_plugin(
    cache_root: Path,
    manifest: dict[str, Any],
    manifest_sha256: str,
    *,
    entry_relpath: str,
) -> DevicePlugin:
    """Import and construct the plugin from its admitted cache copy.

    ``entry_relpath`` must be relative and free of ``..`` parts — the
    structural containment guard, raised as ``entry_not_implementation``
    before the manifest is consulted, so even a forged manifest cannot lend
    admission's authority to a path escaping
    ``<cache_root>/<manifest_sha256>/`` — and must appear in the manifest
    inventory with role ``implementation`` (``entry_not_implementation``
    otherwise). Before anything executes, the entry file's on-disk bytes are
    re-hashed against the inventory's pinned ``bytes``/``sha256`` for that
    path (``file_hash_mismatch``) — a cache tampered after admission never
    reaches the import machinery, and the module then executes exactly those
    verified bytes — the spec supplies module identity only, never a second
    disk read, so nothing can change on disk between the check and the
    execution (surface-audit wave 1, item 4). The module is imported by
    explicit location under a name suffixed with the manifest sha, so two
    cache versions of one package never collide in ``sys.modules``. Construction
    goes through the module's ``create_plugin(now_fn, monotonic_ns_fn)``
    factory — the construction seam every plugin module exposes and the
    conforming suite exercises. An import that raises is rolled back out of
    ``sys.modules`` before the error propagates. The instance is returned
    without ``plugin_open``: the host opens it.
    """
    entry_p = PurePosixPath(entry_relpath)
    if entry_p.is_absolute() or ".." in entry_p.parts:
        raise ActivationRejected("entry_not_implementation")

    files = manifest.get("payload", {}).get("files", [])
    entry = next((f for f in files if f.get("path") == entry_relpath), None)
    if entry is None or entry.get("role") != IMPLEMENTATION_ROLE:
        raise ActivationRejected("entry_not_implementation")

    entry_path = cache_root / manifest_sha256 / entry_relpath
    if not entry_path.is_file():
        raise FileNotFoundError(f"admitted cache entry missing: {entry_path}")

    # Exec-time integrity: re-hash the entry bytes on disk against the
    # manifest inventory's pinned digest BEFORE importlib executes anything —
    # the interval between admission and activation is not trusted.
    entry_bytes = entry_path.read_bytes()
    if (
        entry.get("bytes") != len(entry_bytes)
        or entry.get("sha256") != hashlib.sha256(entry_bytes).hexdigest()
    ):
        raise ActivationRejected("file_hash_mismatch")

    module_name = f"{entry_relpath.replace('/', '_').replace('.', '_')}_{manifest_sha256}"
    # Module identity from the spec; execution from the VERIFIED bytes — the
    # loader never re-reads the file, so a swap on disk after the hash check
    # above cannot change what executes (surface-audit wave 1, item 4).
    spec = importlib.util.spec_from_file_location(module_name, entry_path)
    assert spec is not None  # noqa: S101 — narrowing only; entry_path is a verified .py
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        # S102: executing VERIFIED bundle bytes is this loader's whole job —
        # digest-checked above, never re-read from disk.
        exec(compile(entry_bytes, str(entry_path), "exec"), module.__dict__)  # noqa: S102
    except BaseException:
        # A module whose body raised never leaves a half-initialized entry
        # in sys.modules; the plugin's own error is the honest surface
        # (surface-audit wave 1, item 3).
        sys.modules.pop(spec.name, None)
        raise

    create = getattr(module, "create_plugin", None)
    if not callable(create):
        raise ActivationRejected("unsupported_plugin_module")
    now_fn, monotonic_ns_fn = _default_clock()
    return cast(DevicePlugin, create(now_fn=now_fn, monotonic_ns_fn=monotonic_ns_fn))
