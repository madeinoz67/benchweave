"""Child-process gateway for kill-mid-run fault injection. Not a test module.

Usage: ``python _event_recovery_child.py <db_path> <port> [--hold]``

Boots the real composed gateway (``app_entry.build```` — the same
``create_app`` stack the in-process suites use) on a fixed loopback port,
against the database path the parent chose. ``--hold`` parks the first
run's configure dispatch (the body's first device operation, which by
construction runs after ``_prepare_run`` has reserved the run's bench
lease), so the parent's SIGKILL lands mid-body with an active lease — the
exact durable state restart recovery exists to close. Without ``--hold``
this is the plain restarted gateway.

The park event is never set: the only exit is the parent's kill. The hold
wrapper duplicates the suite's ``_HoldPsu`` shape because this script runs
standalone (tests/ is not a package).
"""

from __future__ import annotations

import os
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[2]


class _HoldPsu:
    """Parks the body's first configure dispatch until released (never)."""

    def __init__(self, inner: Any, release: threading.Event) -> None:
        self._inner = inner
        self._release = release
        self._parked_once = False

    @property
    def simulation(self) -> Any:
        return self._inner.simulation

    def plugin_open(self, services: Any) -> None:
        self._inner.plugin_open(services)

    def plugin_close(self) -> None:
        self._inner.plugin_close()

    def dispatch(self, request: Any, *, deadline_ns: int) -> Any:
        arguments = getattr(request, "arguments", {}) or {}
        action = str(arguments.get("action_id", ""))
        verb = getattr(request, "verb", None)
        if (
            not self._parked_once
            and verb is not None
            and str(verb.value) == "invoke"
            and action.startswith("otdp.dc_psu.configure")
        ):
            self._parked_once = True
            self._release.wait()
        return self._inner.dispatch(request, deadline_ns=deadline_ns)


def _install_hold() -> None:
    """Patch the app's sim-plugin loader to wrap the PSU with the park."""
    from benchweave.interfaces import app as app_module

    original = app_module._load_sim_plugin
    release = threading.Event()

    def loader(name: str) -> ModuleType:
        module = original(name)
        if name != "sim_psu":
            return module

        class _Shim:
            @staticmethod
            def create_plugin(
                *, now_fn: Callable[[], str], monotonic_ns_fn: Callable[[], int]
            ) -> Any:
                inner = module.create_plugin(now_fn=now_fn, monotonic_ns_fn=monotonic_ns_fn)
                return _HoldPsu(inner, release)

        return cast(ModuleType, _Shim())

    app_module._load_sim_plugin = loader


def main() -> None:
    db_path, port = sys.argv[1], int(sys.argv[2])
    hold = "--hold" in sys.argv[3:]
    os.environ["BENCHWEAVE_DB"] = db_path
    os.environ["BENCHWEAVE_PORT"] = str(port)
    if hold:
        _install_hold()

    import uvicorn

    from benchweave.interfaces import app_entry

    uvicorn.run(app_entry.build(), host="127.0.0.1", port=port, log_level="error")


if __name__ == "__main__":
    main()
