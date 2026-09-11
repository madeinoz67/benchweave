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

import importlib.util
import json
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
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
    the :class:`ActivationRecord` fields. The store owns generation
    monotonicity; re-activating the same ``bench_generation`` overwrites that
    generation's record (single-operator bench).
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
    (records_dir / f"activation-{record.new_generation}.json").write_bytes(
        _canonical(asdict(record))
    )
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

    ``entry_relpath`` must appear in the manifest inventory with role
    ``implementation`` (``entry_not_implementation`` otherwise); matching a
    listed path is also what contains the load — inventory paths already
    passed the §4 path rules at admission, so no unlisted (and no traversing)
    path can ever reach the filesystem. The module is imported by explicit
    location under a name suffixed with the manifest sha, so two cache
    versions of one package never collide in ``sys.modules``. Construction
    goes through the module's ``create_plugin(now_fn, monotonic_ns_fn)``
    factory — the construction seam every plugin module exposes and the
    conforming suite exercises. The instance is returned without
    ``plugin_open``: the host opens it.
    """
    files = manifest.get("payload", {}).get("files", [])
    entry = next((f for f in files if f.get("path") == entry_relpath), None)
    if entry is None or entry.get("role") != IMPLEMENTATION_ROLE:
        raise ActivationRejected("entry_not_implementation")

    entry_path = cache_root / manifest_sha256 / entry_relpath
    if not entry_path.is_file():
        raise FileNotFoundError(f"admitted cache entry missing: {entry_path}")

    module_name = f"{entry_relpath.replace('/', '_').replace('.', '_')}_{manifest_sha256}"
    spec = importlib.util.spec_from_file_location(module_name, entry_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    create = getattr(module, "create_plugin", None)
    if not callable(create):
        raise ActivationRejected("unsupported_plugin_module")
    now_fn, monotonic_ns_fn = _default_clock()
    return cast(DevicePlugin, create(now_fn=now_fn, monotonic_ns_fn=monotonic_ns_fn))
