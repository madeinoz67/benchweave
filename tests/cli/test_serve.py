"""Task 14: ``serve`` + the deploy surface (systemd template, env example).

RED-first suite for the production composition point:

- **Secret posture** — ``serve`` (through :func:`app_entry.build`) REFUSES
  to boot on the default test secret when ``BENCHWEAVE_ENV=production``
  (unset secret and the explicit default literal both refuse), and the
  refusal happens before the store is opened. Default posture (no
  ``BENCHWEAVE_ENV``) keeps the suites' test-secret behaviour.
- **T7 carry wiring** — ``app_entry.registry_session_from_env`` builds the
  fixture resolver session (:func:`bootstrap.build_registry_session`) from
  the environment: repo fixture registry by default, an explicit
  ``BENCHWEAVE_REGISTRY_DIR`` honoured, a missing registry root documented
  as the fail-closed ``not_ready`` posture (``None``).
- **Live serve** — a real subprocess ``python -m benchweave serve`` boots
  on an ephemeral port with a real secret under production posture and
  serves REST (the existing child-process pattern — no mocks).
- **Deploy surface** — the systemd template renders with the nine
  hardening directives; the env example is placeholder-only with 0600
  guidance and carries no fixtures coupling; and the whole ``deploy/``
  tree greps clean of secret-looking content.
"""

from __future__ import annotations

import os
import re
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import cast

import httpx
import pytest
from click.testing import CliRunner, Result

from benchweave.cli.commands import cli

REPO = Path(__file__).resolve().parents[2]
FIXTURES_REGISTRY = REPO / "fixtures" / "registry"
TEMPLATE = REPO / "deploy" / "systemd" / "benchweave.service.template"
ENV_EXAMPLE = REPO / "deploy" / "systemd" / "benchweave.env.example"
DEPLOY = REPO / "deploy"
DATA_DIR = "/var/lib/benchweave"
ENV_FILE = "/etc/benchweave/benchweave.env"
# The test secret app_entry falls back to (refused under production posture).
DEFAULT_SECRET = "wp07-task-eleven-secret"
# The live-serve test's production secret is GENERATED at runtime (the WP08
# closing audit: a committed literal is public, so booting production on one
# is the exact bug the denylist closes).


def _combined(result: Result) -> str:
    """stdout + stderr, robust to click < 8.2's mixed-stream Result."""
    try:
        return result.output + result.stderr
    except ValueError:
        return result.output


def _production_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Production posture over a scratch DB: everything but the secret."""
    monkeypatch.setenv("BENCHWEAVE_ENV", "production")
    monkeypatch.setenv("BENCHWEAVE_DB", str(tmp_path / "state.sqlite"))
    return Path(tmp_path / "state.sqlite")


# --- secret posture: refuse the default test secret in production ---------------


def test_serve_refuses_unset_secret_in_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _production_env(monkeypatch, tmp_path)
    monkeypatch.delenv("BENCHWEAVE_SECRET", raising=False)
    result = CliRunner().invoke(cli, ["serve"])
    assert result.exit_code != 0
    combined = _combined(result)
    assert "refusing" in combined
    assert "BENCHWEAVE_SECRET" in combined
    assert not db.exists(), "the refusal must fire before the store is opened"


def test_serve_refuses_the_default_secret_literal_in_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _production_env(monkeypatch, tmp_path)
    monkeypatch.setenv("BENCHWEAVE_SECRET", DEFAULT_SECRET)
    result = CliRunner().invoke(cli, ["serve"])
    assert result.exit_code != 0
    assert "refusing" in _combined(result)
    assert not db.exists()


def test_serve_refusal_is_a_handled_cli_error_not_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _production_env(monkeypatch, tmp_path)
    monkeypatch.delenv("BENCHWEAVE_SECRET", raising=False)
    result = CliRunner().invoke(cli, ["serve"])
    assert result.exception is None or isinstance(result.exception, SystemExit), (
        f"must be a handled error, not a traceback: {result.exception!r}"
    )


def test_app_entry_build_refuses_production_default_secret_before_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The enforcement lives in ``app_entry.build`` itself, so every entry
    (``serve``, bare ``uvicorn benchweave.interfaces.app_entry:app``) gets
    the same refusal — before any store file is created."""
    from benchweave.interfaces import app_entry

    db = _production_env(monkeypatch, tmp_path)
    monkeypatch.delenv("BENCHWEAVE_SECRET", raising=False)
    with pytest.raises(RuntimeError) as raised:
        app_entry.build()
    assert "BENCHWEAVE_SECRET" in str(raised.value)
    assert not db.exists()


def test_app_entry_build_default_posture_keeps_the_test_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without ``BENCHWEAVE_ENV=production`` the composition is unchanged:
    the suites' test-secret default still boots (the event-recovery child
    and the WP07 suites depend on it)."""
    from fastapi import FastAPI

    from benchweave.interfaces import app_entry

    monkeypatch.delenv("BENCHWEAVE_ENV", raising=False)
    monkeypatch.delenv("BENCHWEAVE_SECRET", raising=False)
    monkeypatch.setenv("BENCHWEAVE_DB", str(tmp_path / "state.sqlite"))
    assert isinstance(app_entry.build(), FastAPI)


# --- review I1: empty and placeholder secrets are publicly-known boots ------------


@pytest.mark.parametrize("value", ["", " ", "\t "])
def test_app_entry_build_refuses_empty_secret_in_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """``BENCHWEAVE_SECRET=`` (a trailing-``=`` typo in the env file) must
    refuse in production — an empty secret boots production signing tokens
    with no secret at all."""
    from benchweave.interfaces import app_entry

    db = _production_env(monkeypatch, tmp_path)
    monkeypatch.setenv("BENCHWEAVE_SECRET", value)
    with pytest.raises(RuntimeError) as raised:
        app_entry.build()
    assert "BENCHWEAVE_SECRET" in str(raised.value)
    assert not db.exists(), "the refusal must fire before the store is opened"


def test_app_entry_build_refuses_the_env_example_placeholder_in_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The deploy example's placeholder is public in the repo — an operator
    who copies the example and forgets to fill it must not boot production
    on it (PERMISSIONS-REVIEW §1's operator-error row, exactly)."""
    from benchweave.interfaces import app_entry

    db = _production_env(monkeypatch, tmp_path)
    monkeypatch.setenv(
        "BENCHWEAVE_SECRET", "__GENERATE_AND_STORE_A_REAL_RANDOM_SECRET__"
    )
    with pytest.raises(RuntimeError) as raised:
        app_entry.build()
    assert "BENCHWEAVE_SECRET" in str(raised.value)
    assert not db.exists()


# --- WP08 closing audit (Forge Important 1): the denylist is the FULL public set ----


def test_app_entry_build_refuses_a_committed_test_suite_secret_in_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An operator pasting any of the repo's committed test-suite secrets
    (here: the Task 12 render suite's) must not boot production — before
    this fix only the default and the deploy placeholder were denied."""
    from benchweave.interfaces import app_entry

    db = _production_env(monkeypatch, tmp_path)
    monkeypatch.setenv("BENCHWEAVE_SECRET", "wp08-task-twelve-secret")
    with pytest.raises(RuntimeError) as raised:
        app_entry.build()
    assert "BENCHWEAVE_SECRET" in str(raised.value)
    assert not db.exists()


def test_app_entry_build_refuses_every_known_public_secret_in_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The denylist itself is exercised end to end: every member refuses."""
    from benchweave.interfaces import app_entry
    from benchweave.interfaces.app_entry import _KNOWN_PUBLIC_SECRETS

    _production_env(monkeypatch, tmp_path)
    denied = sorted(value.decode() for value in _KNOWN_PUBLIC_SECRETS)
    assert len(denied) >= 14, "the denylist must be the repo's FULL public-literal set"
    for value in denied:
        monkeypatch.setenv("BENCHWEAVE_SECRET", value)
        with pytest.raises(RuntimeError, match="refusing"):
            app_entry.build()


# The denylist pin (Forge Important 1, requirement 3): the same mechanical
# inventory as `git grep 'SECRET *= *b?"'` — every static secret-shaped
# literal COMMITTED to the repository (tracked files: what ships and is
# therefore public) must be refused under production posture, so a future
# test literal cannot ship un-deniedlisted (the pin goes red in the very
# commit that introduces the literal).
_SECRET_LITERAL = re.compile(r'SECRET *= *b?"([^"]*)"')


def _repo_secret_literals() -> set[str]:
    """Every static secret-shaped string literal in the tracked tree."""
    tracked = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "-C", str(REPO), "ls-files"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.splitlines()
    assert tracked, "the tracked-file listing must not be vacuous"
    values: set[str] = set()
    for rel in sorted(tracked):
        path = REPO / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary/unreadable — not a literal source
        for line in text.splitlines():
            match = _SECRET_LITERAL.search(line)
            if match is None:
                continue
            value = match.group(1)
            if value and not value.startswith("$"):
                values.add(value)
    return values


def test_known_public_secrets_covers_every_repo_secret_literal() -> None:
    """The PIN: the mechanical inventory is a subset of the refused set."""
    from benchweave.interfaces.app_entry import _KNOWN_PUBLIC_SECRETS

    inventory = _repo_secret_literals()
    assert inventory, "a vacuous scan is a broken pin — the repo carries secret literals"
    missing = sorted(
        value for value in inventory if value.strip().encode() not in _KNOWN_PUBLIC_SECRETS
    )
    assert not missing, (
        "public secret literal(s) missing from the production denylist "
        "(app_entry._KNOWN_PUBLIC_SECRETS): " + ", ".join(missing)
    )


# --- review M2/M3: observability and the lazy mechanism ---------------------------


def test_build_notes_when_no_registry_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """M2: the fail-closed not_ready posture is observable at build time —
    a one-line stderr note, not a silent capability downgrade."""
    from benchweave.interfaces import app_entry

    monkeypatch.delenv("BENCHWEAVE_ENV", raising=False)
    monkeypatch.delenv("BENCHWEAVE_SECRET", raising=False)
    monkeypatch.setenv("BENCHWEAVE_DB", str(tmp_path / "state.sqlite"))
    empty = tmp_path / "no-registry"
    empty.mkdir()
    monkeypatch.setenv("BENCHWEAVE_REGISTRY_DIR", str(empty))
    app_entry.build()
    note = capsys.readouterr().err
    assert "not_ready" in note
    assert "registry" in note


def test_lazy_app_imports_without_env_and_builds_only_on_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M3: the PEP 562 mechanism pinned directly — importing the module
    composes nothing (an absent env cannot fail the import), and ``app``
    enters the module dict only at attribute access."""
    import importlib
    import sys as sys_module

    monkeypatch.delenv("BENCHWEAVE_DB", raising=False)
    sys_module.modules.pop("benchweave.interfaces.app_entry", None)
    module = importlib.import_module("benchweave.interfaces.app_entry")
    assert "app" not in vars(module), "import must not compose the gateway"
    monkeypatch.setenv("BENCHWEAVE_DB", str(tmp_path / "state.sqlite"))
    monkeypatch.delenv("BENCHWEAVE_ENV", raising=False)
    monkeypatch.delenv("BENCHWEAVE_SECRET", raising=False)
    assert module.app is not None, "attribute access builds the gateway"
    assert "app" in vars(module), "the built app caches in the module dict"


# --- T7 carry: the fixture resolver session wired from the environment ----------


def test_registry_session_from_env_default_wires_origin_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from benchweave.interfaces.app_entry import registry_session_from_env
    from benchweave.interfaces.bootstrap import REGISTRY_ORIGIN

    monkeypatch.delenv("BENCHWEAVE_REGISTRY_DIR", raising=False)
    session = registry_session_from_env(tmp_path)
    assert session is not None, "the repo fixture registry must wire by default"
    assert set(session.roots) == {REGISTRY_ORIGIN}
    assert session.registry_id == REGISTRY_ORIGIN
    # The work root lives under the data dir (the DB's parent), so the unit's
    # ReadWritePaths={{DATA_DIR}} stays the only writable root.
    assert session.cache_root == tmp_path / "registry" / "cache"
    assert session.lock_path == tmp_path / "registry" / "packages.lock.json"
    # A real ns clock (the T7 report's flagged requirement: status gates
    # judge expiry against wall time, not a frozen test instant).
    first = session.now_ns()
    second = session.now_ns()
    assert 0 < first <= second < time.time_ns() + 1_000_000_000


def test_registry_session_from_env_honours_override_and_absent_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from benchweave.interfaces.app_entry import registry_session_from_env

    # An explicit registry root that does not carry the trust root is the
    # documented fail-closed not_ready posture — None, never a half session.
    empty_root = tmp_path / "empty-registry"
    empty_root.mkdir()
    monkeypatch.setenv("BENCHWEAVE_REGISTRY_DIR", str(empty_root))
    assert registry_session_from_env(tmp_path / "other") is None

    # An explicit root carrying the committed public key wires against it,
    # with the work root derived from the caller's data dir.
    copied = tmp_path / "copied-registry"
    (copied / "keys").mkdir(parents=True)
    (copied / "keys" / "main.pub.pem").write_bytes(
        (FIXTURES_REGISTRY / "keys" / "main.pub.pem").read_bytes()
    )
    monkeypatch.setenv("BENCHWEAVE_REGISTRY_DIR", str(copied))
    session = registry_session_from_env(tmp_path / "data")
    assert session is not None
    assert session.cache_root == tmp_path / "data" / "registry" / "cache"


# --- live serve: real subprocess, real secret, production posture ---------------


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return cast(int, sock.getsockname()[1])


def test_serve_live_boots_and_serves_with_a_real_secret_in_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from benchweave.interfaces.identity import issue

    port = _free_port()
    live_secret = secrets.token_urlsafe(32)
    db = tmp_path / "state.sqlite"
    stderr_path = tmp_path / "serve.stderr.log"
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("BENCHWEAVE_")
    }
    env.update(
        {
            "BENCHWEAVE_ENV": "production",
            "BENCHWEAVE_DB": str(db),
            "BENCHWEAVE_SECRET": live_secret,
        }
    )
    with stderr_path.open("wb") as handle:
        proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            [
                sys.executable,
                "-m",
                "benchweave",
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=str(REPO),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=handle,
        )
        token = issue(
            live_secret.encode(),
            principal="task14-observe",
            audience="stg",
            scopes={"stg:observe"},
            expires_at=int(time.time()) + 3600,
        )
        last_error = "serve subprocess never became ready"
        try:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port}", timeout=5.0
            ) as client:
                deadline = time.monotonic() + 30.0
                while time.monotonic() < deadline:
                    if proc.poll() is not None:
                        tail = stderr_path.read_text(errors="replace")[-2000:]
                        raise AssertionError(
                            f"serve exited early (rc={proc.returncode})"
                            f"\nstderr tail:\n{tail}"
                        )
                    try:
                        resp = client.get(
                            "/v1", headers={"Authorization": f"Bearer {token}"}
                        )
                        if resp.status_code == 200:
                            body = resp.json()
                            break
                        last_error = f"/v1 -> {resp.status_code} {resp.text[:200]}"
                    except httpx.HTTPError as error:
                        last_error = repr(error)
                    time.sleep(0.2)
                else:
                    tail = stderr_path.read_text(errors="replace")[-2000:]
                    raise AssertionError(
                        f"serve gateway not ready: {last_error}\nstderr tail:\n{tail}"
                    )
                # The REST envelope ({"ok": true, "data": {...}}) carries
                # the composed gateway's identity.
                assert body["data"]["gateway_id"] == "gw-app-entry"
                assert body["data"]["interface_version"]
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
    tail = stderr_path.read_text(errors="replace")
    assert "Traceback" not in tail, f"serve must not traceback:\n{tail[-2000:]}"


# --- deploy surface: the nine directives, placeholders, zero secrets -----------


def _rendered_template() -> str:
    return (
        TEMPLATE.read_text(encoding="utf-8")
        .replace("{{DATA_DIR}}", DATA_DIR)
        .replace("{{ENV_FILE}}", ENV_FILE)
    )


def test_systemd_template_renders_with_the_nine_hardening_directives() -> None:
    raw = TEMPLATE.read_text(encoding="utf-8")
    # The template itself must carry the placeholders (CI renders them with
    # sed — hardcoded paths would silently break the render contract).
    assert "{{DATA_DIR}}" in raw
    assert "{{ENV_FILE}}" in raw
    rendered = _rendered_template()
    assert "{{" not in rendered, "rendering must consume every placeholder"
    # The nine (controller ruling 1), each exact:
    assert "Type=simple" in rendered  # serve is foreground (ruling 5)
    assert re.search(r"^User=benchweave$", rendered, re.MULTILINE)
    assert re.search(r"^NoNewPrivileges=true$", rendered, re.MULTILINE)
    assert re.search(r"^ProtectSystem=strict$", rendered, re.MULTILINE)
    assert re.search(rf"^ReadWritePaths={re.escape(DATA_DIR)}$", rendered, re.MULTILINE)
    assert re.search(r"^PrivateTmp=true$", rendered, re.MULTILINE)
    # Empty bounding set — the directive with an EMPTY value, not a stray
    # assignment of something else.
    assert re.search(r"^CapabilityBoundingSet=$", rendered, re.MULTILINE)
    assert re.search(r"^MemoryDenyWriteExecute=true$", rendered, re.MULTILINE)
    assert re.search(rf"^EnvironmentFile={re.escape(ENV_FILE)}$", rendered, re.MULTILINE)
    exec_start = re.search(r"^ExecStart=(.+)$", rendered, re.MULTILINE)
    assert exec_start is not None
    assert "serve" in exec_start.group(1), "ExecStart renders the serve command"
    assert "[Install]" in rendered and "WantedBy=" in rendered


def test_env_example_is_placeholder_only_and_carries_no_fixtures_coupling() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "BENCHWEAVE_ENV=production" in text
    # 0600 guidance (controller ruling 2) ...
    assert "0600" in text
    # ... and ruling 6: the credential env file carries no fixtures coupling.
    assert "BENCHWEAVE_FIXTURES" not in text
    secret_line = re.search(r"^BENCHWEAVE_SECRET=(.+)$", text, re.MULTILINE)
    assert secret_line is not None
    assert re.fullmatch(r"__[A-Z0-9_]+__|\{\{[A-Z_]+\}\}|<[A-Z_ ]+>", secret_line.group(1))


def test_env_example_secret_placeholder_equals_the_refused_constant() -> None:
    """T14 micro-carry (landed with T15): the example's placeholder text and
    the production denylist's refused constant are ONE value, pinned — if
    the example's placeholder text ever changes, this fails instead of the
    denylist silently going stale (a changed placeholder would boot
    production on a publicly-known secret again)."""
    from benchweave.interfaces.app_entry import ENV_EXAMPLE_PLACEHOLDER_SECRET

    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    secret_line = re.search(r"^BENCHWEAVE_SECRET=(.+)$", text, re.MULTILINE)
    assert secret_line is not None
    assert secret_line.group(1) == ENV_EXAMPLE_PLACEHOLDER_SECRET.decode()


# The secret-grep (controller ruling 2): deploy/ carries no real secrets —
# secret-shaped keys hold placeholders only, and no high-entropy blob
# survives once placeholders and filesystem paths are removed.
_PLACEHOLDER = re.compile(r"\{\{[^}]+\}\}|<[A-Za-z0-9_ .-]+>|__[A-Z0-9_]+__")
_ABS_PATH = re.compile(r"(?:/[A-Za-z0-9_.+-]+)+")
_SECRETISH_KEY = re.compile(
    r"^\s*[A-Z0-9_]*(?:SECRET|TOKEN|KEY|PASSWORD|PASSPHRASE|CREDENTIAL)[A-Z0-9_]*\s*="
)
_HIGH_ENTROPY = re.compile(r"[A-Za-z0-9+/=]{32,}")


def test_deploy_tree_carries_no_secret_looking_content() -> None:
    files = sorted(path for path in DEPLOY.rglob("*") if path.is_file())
    assert files, "the deploy surface must exist"
    for path in files:
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if _SECRETISH_KEY.match(line):
                value = line.split("=", 1)[1].strip()
                assert _PLACEHOLDER.fullmatch(value), (
                    f"{path}:{number} sets a secret-shaped key to a "
                    f"non-placeholder value"
                )
            remainder = _ABS_PATH.sub("", _PLACEHOLDER.sub("", line))
            match = _HIGH_ENTROPY.search(remainder)
            assert match is None, (
                f"{path}:{number} carries secret-looking content: {match.group()!r}"
            )
