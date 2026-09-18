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

Production secret posture (WP08 Task 14, completed by the closing
audit): with ``BENCHWEAVE_ENV=production`` the composition REFUSES to
boot when the secret is unset, empty/whitespace, or ANY publicly known
secret literal committed to the repository — not just the suites'
default test secret; the full inventory is ``_KNOWN_PUBLIC_SECRETS`` —
since a known secret in a deployment mints tokens anyone with the
public source can mint. The refusal fires before the store is opened,
so a refused boot leaves no file behind. Every other posture keeps the
suites' default-secret behaviour unchanged.

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
import sys
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
#: The deploy example's placeholder value (keep in sync with
#: deploy/systemd/benchweave.env.example) — public in the repo, so it is
#: refused alongside the default test secret under production posture.
ENV_EXAMPLE_PLACEHOLDER_SECRET = b"__GENERATE_AND_STORE_A_REAL_RANDOM_SECRET__"
#: Secret values that are publicly known and therefore unusable in
#: production (empty/whitespace is refused separately, below). The set is
#: the repository's FULL committed literal inventory (the WP08 closing
#: audit, Forge Important 1: an operator pasting ANY public test secret
#: must not boot production) — mechanically pinned by
#: ``tests/cli/test_serve.py``
#: (``test_known_public_secrets_covers_every_repo_secret_literal``),
#: which greps the tracked tree for secret-shaped literals and fails if
#: any is missing here, so a future test literal cannot ship
#: un-deniedlisted.
_KNOWN_PUBLIC_SECRETS = frozenset(
    {
        _DEFAULT_SECRET,
        ENV_EXAMPLE_PLACEHOLDER_SECRET,
        b"wp02-test-secret-not-a-credential",  # tests/integration/test_mcp_baseline.py
        b"wp07-cursor-v1",  # interfaces/operations.py (cursor principal-binding constant)
        b"wp07-task-eight-secret",  # tests/integration/test_mcp_tools.py
        b"wp07-task-nine-secret",  # tests/integration/test_rest_routes.py
        b"wp07-task-ten-secret",  # tests/integration/test_interface_parity.py
        b"wp08-task-seven-secret",  # tests/integration/test_registry_changes.py
        b"wp08-task-nine-secret",  # tests/cli/test_commands.py
        b"wp08-task-ten-secret",  # tests/integration/test_backup_restore.py
        b"wp08-task-eleven-secret",  # tests/cli/test_live.py
        b"wp08-task-twelve-secret",  # tests/cli/test_render.py
        b"wp08-task-fourteen-live-secret",  # retired from the tree; public via git history
        b"wp09-task-four-secret",  # tests/integration/test_poc_acceptance.py
        b"test-issuer-secret",  # tests/unit/test_seam_admin.py
    }
)
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
    """Refuse unusable secrets under production posture.

    Refused: empty/whitespace values (a trailing-``=`` typo in the env file
    must not boot token-signing with no secret) and every known-public
    value — any secret literal committed to the repository (the default
    test secret, the deploy example's placeholder, and the test suites'
    literals), all readable by anyone with the public source. The check
    runs before any store is opened, so a refused boot creates nothing on
    disk. Unset ``BENCHWEAVE_SECRET`` falls back to the default and is
    refused with it.
    """
    if os.environ.get("BENCHWEAVE_ENV") != PRODUCTION_ENV_VALUE:
        return
    stripped = secret.strip()
    if stripped and stripped not in _KNOWN_PUBLIC_SECRETS:
        return
    raise RuntimeError(
        "refusing to boot: BENCHWEAVE_ENV=production with an unusable "
        "BENCHWEAVE_SECRET (empty or whitespace, or a publicly known value "
        "— any secret literal committed to the repository, e.g. the "
        "default test secret) — set a real secret (e.g. the one "
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
    if not fixtures.is_dir():
        # In a wheel install the repo-relative default resolves into the
        # environment's site-packages parent, where no lattice exists (the
        # execution fixtures are deliberately not vendored — they are
        # operator-supplied input). Fail fast naming the knob instead of
        # booting toward a cryptic downstream error.
        raise RuntimeError(
            f"benchweave: fixtures directory not found: {fixtures} — set "
            "BENCHWEAVE_FIXTURES to your bench/procedure/policy lattice"
        )
    secret = os.environ.get("BENCHWEAVE_SECRET", _DEFAULT_SECRET.decode()).encode()
    _require_production_secret(secret)
    store = Store.open(db_path, check_same_thread=False)
    content = ContentStore(store)
    session = registry_session_from_env(Path(db_path).parent)
    if session is None:
        # M2 (review): make the fail-closed posture observable at build
        # time — a silent capability downgrade is indistinguishable from
        # "the admin kinds work" until the first refusal.
        print(
            "benchweave: no fixture registry root — the registry admin "
            "change kinds stay not_ready (fail-closed)",
            file=sys.stderr,
        )
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
        registry_session=session,
    )


def __getattr__(name: str) -> Any:
    """Lazy ``app``: composing happens at attribute access, never at import."""
    if name == "app":
        built = build()
        globals()["app"] = built
        return built
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
