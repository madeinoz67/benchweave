"""Env-driven ASGI entry: the composed gateway, production-posture aware.

``uvicorn benchweave.interfaces.app_entry:app`` (or a programmatic
``uvicorn.run(app_entry.build(), ...)`` — what ``benchweave serve`` runs)
boots exactly what ``create_app`` composes for the integration suites —
bootstrap, REST ``/v1``, the MCP mount, the run worker — reading its inputs
from the environment so a child process can run the real app against a
chosen database file:

- ``BENCHWEAVE_DB`` (required): state database path.
- ``BENCHWEAVE_PORT``: the intended port (serve/uvicorn own the actual bind).
- ``BENCHWEAVE_FIXTURES``: fixtures directory (default: the repository
  execution lattice, resolved like the app's plugin root).
- ``BENCHWEAVE_SECRET``: identity issuer secret (default: the suites' test
  secret — REFUSED under production posture, see below).
- ``BENCHWEAVE_ENV``: set ``production`` to arm the secret posture.
- ``BENCHWEAVE_REGISTRY_DIR``: fixture registry root for the resolver
  session (default: the repository ``fixtures/registry``).

Production secret posture (WP08 Task 14): with
``BENCHWEAVE_ENV=production`` the composition REFUSES to boot when the
secret is unset or is the suites' default test secret — a test secret in a
deployment mints tokens anyone with the public source can mint. The
refusal fires before the store is opened, so a refused boot leaves no
file behind. Every other posture keeps the suites' default-secret
behaviour unchanged.

Registry wiring (the Task 7 carry): ``registry_session_from_env`` builds
the fixture resolver session (:func:`bootstrap.build_registry_session`) so
the two admin change kinds are reachable in production; its work root
lives under the data directory (the DB's parent), keeping the systemd
unit's ``ReadWritePaths={{DATA_DIR}}`` the only writable root.

The module-level ``app`` is lazy (PEP 562 ``__getattr__``): importing the
module never composes anything, so importing under a hostile/absent env
cannot half-boot a gateway — ``uvicorn ...:app`` and ``build()`` both pay
the (posture-checked) composition at access time.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.interfaces.bootstrap import RegistrySession, build_registry_session
from benchweave.state.store import Store

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_FIXTURES = _REPO_ROOT / "fixtures" / "execution"
_DEFAULT_REGISTRY = _REPO_ROOT / "fixtures" / "registry"
_DEFAULT_SECRET = b"wp07-task-eleven-secret"
#: The env value that arms the production secret posture.
PRODUCTION_ENV_VALUE = "production"
_LIMITS: dict[str, int] = {
    "max_json_bytes": 1048576,
    "max_page_size": 1000,
    "max_chunk_bytes": 65536,
    "max_lease_ms": 600000,
    "min_poll_ms": 100,
    "max_admission_ms": 5000,
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _now_epoch() -> int:
    return int(datetime.now(UTC).timestamp())


def _require_production_secret(secret: bytes) -> None:
    """Refuse the default test secret under production posture.

    The check runs before any store is opened, so a refused boot creates
    nothing on disk. Unset ``BENCHWEAVE_SECRET`` falls back to the default
    and is refused with it.
    """
    if (
        os.environ.get("BENCHWEAVE_ENV") == PRODUCTION_ENV_VALUE
        and secret == _DEFAULT_SECRET
    ):
        raise RuntimeError(
            "refusing to boot: BENCHWEAVE_ENV=production with the default test "
            "secret — set BENCHWEAVE_SECRET to a real secret (e.g. the one "
            "`benchweave setup` wrote to benchweave.env, kept mode 0600)"
        )


def registry_session_from_env(data_dir: Path) -> RegistrySession | None:
    """The fixture resolver session from the environment (Task 7 carry).

    ``BENCHWEAVE_REGISTRY_DIR`` overrides the registry root (default: the
    repository ``fixtures/registry``). A root that does not carry the
    origin-main trust root yields ``None`` — the documented fail-closed
    ``not_ready`` posture for the two registry change kinds in stripped
    deployments (an explicitly wrong root refuses at first use, never
    silently here). The session's work root lives under ``data_dir`` (the
    DB's parent directory), so a deployment's single writable root stays
    the data directory. ``now_ns`` is the real wall clock: status gates
    judge expiry against it, not a frozen test instant.
    """
    registry_dir = Path(
        os.environ.get("BENCHWEAVE_REGISTRY_DIR", str(_DEFAULT_REGISTRY))
    )
    if not (registry_dir / "keys" / "main.pub.pem").is_file():
        return None
    return build_registry_session(
        registry_dir, data_dir / "registry", now_ns=time.time_ns
    )


def build() -> FastAPI:
    """Compose the gateway from ``BENCHWEAVE_*`` environment inputs."""
    db_path = os.environ["BENCHWEAVE_DB"]
    fixtures = Path(os.environ.get("BENCHWEAVE_FIXTURES", str(_DEFAULT_FIXTURES)))
    secret = os.environ.get("BENCHWEAVE_SECRET", _DEFAULT_SECRET.decode()).encode()
    _require_production_secret(secret)
    store = Store.open(db_path, check_same_thread=False)
    content = ContentStore(store)
    return create_app(
        store=store,
        content=content,
        secret=secret,
        limits=_LIMITS,
        gateway_id="gw-app-entry",
        fixtures_dir=fixtures,
        now_iso=_now_iso,
        now_epoch=_now_epoch,
        # Task 7 carry: the fixture resolver session (None keeps the WP07
        # fail-closed not_ready posture where no registry root exists).
        registry_session=registry_session_from_env(Path(db_path).parent),
    )


def __getattr__(name: str) -> Any:
    """Lazy ``app``: composing happens at attribute access, never at import."""
    if name == "app":
        built = build()
        globals()["app"] = built
        return built
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
