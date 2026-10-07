"""Issue #422 increment 1: the serve env-file loader and its refusals.

``benchweave serve`` bridges ``<data-dir>/benchweave.env`` — the credential
file ``setup`` writes and operators may hand-extend — into the process
environment, set-if-not-set, before ``app_entry.build()`` runs. This module
pins the loader's REFUSAL surface (arms A5-A14 of the design record's
section 7) and the allowlist's inventory coupling: every ``BENCHWEAVE_*``
key app_entry or the serve command reads must be allowlisted or carry a
documented exclusion reason, so a new env read cannot ship silently
unreachable from the env file.

The parse rules and refusal wording are shared verbatim with the SDK twin
(``benchweave_sdk_server/env_file.py``); the twin arms here assert the same
literal expected strings the SDK suite asserts, so the two repos cannot
drift silently.

Builder-note discipline (design section 7): env-file fixture lines for
``BENCHWEAVE_SECRET`` are UNQUOTED and runtime-generated — a quoted literal
would enroll in the public-secret denylist pin and redden it, and a
committed literal is public.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from benchweave.cli import atrest
from benchweave.cli.commands import cli

REPO = Path(__file__).resolve().parents[2]
APP_ENTRY = REPO / "src" / "benchweave" / "interfaces" / "app_entry.py"
COMMANDS = REPO / "src" / "benchweave" / "cli" / "commands.py"


def _combined(result: Result) -> str:
    """stdout + stderr, robust to click < 8.2's mixed-stream Result."""
    try:
        return result.output + result.stderr
    except ValueError:
        return result.output


@pytest.fixture()
def clean_benchweave_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Scrub every ``BENCHWEAVE_*`` process-env key for the arm (the
    operator's clean shell), restoring the exact prior state afterwards —
    INCLUDING keys serve derives into ``os.environ`` with a bare write (the
    locator's ``BENCHWEAVE_DB`` derivation), which monkeypatch cannot
    track."""
    original = {
        key: value for key, value in os.environ.items() if key.startswith("BENCHWEAVE_")
    }
    for key in original:
        monkeypatch.delenv(key, raising=False)
    yield
    for key in [key for key in os.environ if key.startswith("BENCHWEAVE_") and key not in original]:
        del os.environ[key]


def _serve_with_build_probe(
    monkeypatch: pytest.MonkeyPatch, args: list[str]
) -> tuple[Result, bool, dict[str, str] | None]:
    """Invoke serve with uvicorn parked and ``app_entry.build`` replaced by
    a call probe that snapshots ``os.environ`` (the issue #422 arm pattern:
    the arms assert on the environment build actually received, never on
    uvicorn side effects)."""
    import uvicorn

    from benchweave.interfaces import app_entry

    built = {"value": False}
    snapshot: dict[str, dict[str, str]] = {}

    def probe() -> object:
        built["value"] = True
        snapshot["env"] = dict(os.environ)
        return object()

    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)
    monkeypatch.setattr(app_entry, "build", probe)
    result = CliRunner().invoke(cli, args)
    return result, built["value"], snapshot.get("env")


def _legacy_data_dir_with_env_file(tmp_path: Path, body: str) -> Path:
    """A data dir reached through the legacy ``BENCHWEAVE_DB`` locator,
    whose credential file carries ``body`` (0600, as setup leaves it). The
    store file is NOT created: the legacy locator guards nothing by design
    (risk R7) and build is parked in every arm that uses this helper."""
    data_dir = tmp_path / "legacy"
    data_dir.mkdir()
    path = data_dir / atrest.CREDENTIAL_FILE
    path.write_text(body, encoding="utf-8")
    path.chmod(0o600)
    return data_dir


# --- A5-A8: parse refusals — loud, typed, build never called -------------------


def test_a5_malformed_line_refuses_and_never_calls_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_benchweave_env: None
) -> None:
    data_dir = _legacy_data_dir_with_env_file(tmp_path, "BENCHWEAVE_SECRET\n")
    monkeypatch.setenv("BENCHWEAVE_DB", str(data_dir / atrest.DB_NAME))
    result, built, _ = _serve_with_build_probe(monkeypatch, ["serve"])
    assert result.exit_code != 0, _combined(result)
    combined = _combined(result)
    assert "env_file:" in combined
    # The twin literal — identical bytes in the SDK suite's S4 arm:
    assert (
        f'env_file: {data_dir / atrest.CREDENTIAL_FILE}: line 1: no "=" in line'
        " — expected KEY=VALUE" in combined
    )
    assert not built, "a refused parse must never reach build()"


def test_a6_unknown_key_refuses_naming_the_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_benchweave_env: None
) -> None:
    data_dir = _legacy_data_dir_with_env_file(tmp_path, "BENCHWEAVE_NOT_A_THING=1\n")
    monkeypatch.setenv("BENCHWEAVE_DB", str(data_dir / atrest.DB_NAME))
    result, built, _ = _serve_with_build_probe(monkeypatch, ["serve"])
    assert result.exit_code != 0
    combined = _combined(result)
    assert "env_file:" in combined
    assert "BENCHWEAVE_NOT_A_THING" in combined
    assert "allowlisted" in combined, "the refusal points at the allowlist"
    assert not built


def test_a7_file_setting_db_refuses_as_derived(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_benchweave_env: None
) -> None:
    data_dir = _legacy_data_dir_with_env_file(
        tmp_path, "BENCHWEAVE_DB=/elsewhere/state.sqlite\n"
    )
    monkeypatch.setenv("BENCHWEAVE_DB", str(data_dir / atrest.DB_NAME))
    result, built, _ = _serve_with_build_probe(monkeypatch, ["serve"])
    assert result.exit_code != 0
    combined = _combined(result)
    assert "env_file:" in combined
    assert "BENCHWEAVE_DB" in combined
    assert "may not come from the env file" in combined
    assert not built


def test_a8_file_setting_port_refuses_as_click_preread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_benchweave_env: None
) -> None:
    """``BENCHWEAVE_HOST``/``BENCHWEAVE_PORT`` are read by click BEFORE the
    command body runs — a file value could never take effect, which is the
    silent-no-op posture this repo refuses."""
    data_dir = _legacy_data_dir_with_env_file(tmp_path, "BENCHWEAVE_PORT=9000\n")
    monkeypatch.setenv("BENCHWEAVE_DB", str(data_dir / atrest.DB_NAME))
    result, built, _ = _serve_with_build_probe(monkeypatch, ["serve"])
    assert result.exit_code != 0
    combined = _combined(result)
    assert "env_file:" in combined
    assert "BENCHWEAVE_PORT" in combined
    assert "may not come from the env file" in combined
    assert not built


# --- A9-A10: the --data-dir locator's own refusals --------------------------------


def test_a9_conflicting_locators_refuse_naming_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_benchweave_env: None
) -> None:
    named = tmp_path / "named"
    named.mkdir()
    via_db = tmp_path / "via-db"
    via_db.mkdir()
    monkeypatch.setenv("BENCHWEAVE_DB", str(via_db / atrest.DB_NAME))
    result, built, _ = _serve_with_build_probe(monkeypatch, ["serve", "--data-dir", str(named)])
    assert result.exit_code != 0
    combined = _combined(result)
    assert "serve_locator_conflict:" in combined
    # Both paths, RESOLVED (a relative --data-dir must not false-conflict;
    # macOS tmp paths resolve /var -> /private/var).
    assert str(named.resolve()) in combined
    assert str((via_db / atrest.DB_NAME).resolve().parent) in combined
    assert not built


def test_a10_data_dir_without_a_store_refuses_naming_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_benchweave_env: None
) -> None:
    """A typo'd data dir must not silently create a fresh store: the
    derivation guard fires before build() (which is what would create it)."""
    data_dir = tmp_path / "empty"
    data_dir.mkdir()
    result, built, _ = _serve_with_build_probe(monkeypatch, ["serve", "--data-dir", str(data_dir)])
    assert result.exit_code != 0
    combined = _combined(result)
    assert "benchweave setup" in combined
    assert not (data_dir / atrest.DB_NAME).exists(), "no store file may be created"
    assert not built


# --- A11-A13: posture refusals ----------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits; W1 residual")
def test_a11_group_readable_file_refuses_naming_the_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_benchweave_env: None
) -> None:
    data_dir = _legacy_data_dir_with_env_file(tmp_path, "BENCHWEAVE_ENV=production\n")
    (data_dir / atrest.CREDENTIAL_FILE).chmod(0o644)
    monkeypatch.setenv("BENCHWEAVE_DB", str(data_dir / atrest.DB_NAME))
    result, built, _ = _serve_with_build_probe(monkeypatch, ["serve"])
    assert result.exit_code != 0
    combined = _combined(result)
    # The twin literal — identical bytes in the SDK suite's S5 arm:
    assert (
        f"env_file: {data_dir / atrest.CREDENTIAL_FILE}: mode 644 allows group"
        " or other access — the file carries a live secret; restrict it to"
        " the owner (chmod 0600)" in combined
    )
    assert not built


def test_a12_quoted_crlf_value_loads_unquoted_without_cr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_benchweave_env: None
) -> None:
    """Quote-stripping (systemd ``EnvironmentFile`` compatibility for
    operators copying shell-export lines) on a Windows-edited CRLF file —
    using a non-SECRET key's value per the builder note (a quoted SECRET
    fixture literal would enroll in the public-secret denylist pin)."""
    data_dir = tmp_path / "legacy"
    data_dir.mkdir()
    path = data_dir / atrest.CREDENTIAL_FILE
    path.write_bytes(b'BENCHWEAVE_ENV="production"\r\n')
    path.chmod(0o600)
    monkeypatch.setenv("BENCHWEAVE_DB", str(data_dir / atrest.DB_NAME))
    result, built, env = _serve_with_build_probe(monkeypatch, ["serve"])
    assert result.exit_code == 0, _combined(result)
    assert built
    assert env is not None
    assert env.get("BENCHWEAVE_ENV") == "production"
    assert "\r" not in env.get("BENCHWEAVE_ENV", "")


def test_a13_set_but_empty_secret_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_benchweave_env: None
) -> None:
    """``BENCHWEAVE_SECRET=`` (the trailing-``=`` typo class) refuses at the
    loader — before production posture would even see it."""
    data_dir = _legacy_data_dir_with_env_file(tmp_path, "BENCHWEAVE_SECRET=\n")
    monkeypatch.setenv("BENCHWEAVE_DB", str(data_dir / atrest.DB_NAME))
    result, built, _ = _serve_with_build_probe(monkeypatch, ["serve"])
    assert result.exit_code != 0
    combined = _combined(result)
    assert "env_file:" in combined
    assert "BENCHWEAVE_SECRET is set but empty" in combined
    assert not built


# --- A14: success logging names key NAMES and the path, never values ---------------


def test_a14_success_logging_names_keys_and_path_never_the_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_benchweave_env: None
) -> None:
    data_dir = tmp_path / "gateway"
    atrest.setup(data_dir)
    file_secret = atrest.read_secret(data_dir)
    with (data_dir / atrest.CREDENTIAL_FILE).open("a", encoding="utf-8") as handle:
        handle.write("BENCHWEAVE_ENV=production\n")
    result, built, _ = _serve_with_build_probe(monkeypatch, ["serve", "--data-dir", str(data_dir)])
    assert result.exit_code == 0, _combined(result)
    assert built
    combined = _combined(result)
    assert "BENCHWEAVE_SECRET" in combined, "the key NAME is logged"
    assert str(data_dir / atrest.CREDENTIAL_FILE) in combined, "the path is logged"
    assert file_secret not in combined, "the secret VALUE never reaches output (risk R1)"


# --- the loader's shared semantics (twin of the SDK suite's arms) ------------------


def test_loader_applies_set_if_not_set_and_returns_applied_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_benchweave_env: None
) -> None:
    from benchweave.cli.env_file import load_env_file, serve_env_file_keys

    path = tmp_path / "svc.env"
    path.write_text(
        "# operator notes\n"
        "\n"
        "BENCHWEAVE_ENV=production\n"
        "BENCHWEAVE_UI=0\n"
        "BENCHWEAVE_REGISTRY_DIR=/registry/with=equals#and-hash\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    monkeypatch.setenv("BENCHWEAVE_UI", "1")
    applied = load_env_file(path, serve_env_file_keys())
    # Blank and comment-only lines are skipped; a mid-line '#' is value
    # content; the FIRST '=' separates so a value may contain '='.
    assert applied == ["BENCHWEAVE_ENV", "BENCHWEAVE_REGISTRY_DIR"]
    assert os.environ["BENCHWEAVE_ENV"] == "production"
    assert os.environ["BENCHWEAVE_REGISTRY_DIR"] == "/registry/with=equals#and-hash"
    # Explicit process environment always wins (set-if-not-set).
    assert os.environ["BENCHWEAVE_UI"] == "1"
    assert "BENCHWEAVE_UI" not in applied


def test_loader_skips_blank_and_comment_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from benchweave.cli.env_file import load_env_file, serve_env_file_keys

    path = tmp_path / "only-comments.env"
    path.write_text(
        "# a full-line comment\n\n   # indented comment\n\n", encoding="utf-8"
    )
    path.chmod(0o600)
    assert load_env_file(path, serve_env_file_keys()) == []


# --- the allowlist's inventory coupling (design section 2.3) -----------------------

_ENV_READ_PATTERNS = (
    re.compile(r'os\.environ\.get\(\s*["\']([A-Z][A-Z0-9_]*)["\']'),
    re.compile(r'os\.environ\[\s*["\']([A-Z][A-Z0-9_]*)["\']\s*\]'),
    re.compile(r'envvar=["\']([A-Z][A-Z0-9_]*)["\']'),
)


def _env_key_reads(text: str) -> set[str]:
    """Every ``BENCHWEAVE_*`` key the text reads from the environment or
    binds as a click ``envvar``. What this does NOT catch: an indirectly
    read key (``os.environ.get(name)`` through a variable) — the quota
    keys ride the imported tuple, so the known indirect reads are covered
    by construction, and a NEW indirect read is a review-lane catch."""
    found: set[str] = set()
    for pattern in _ENV_READ_PATTERNS:
        found.update(pattern.findall(text))
    return {key for key in found if key.startswith("BENCHWEAVE_")}


def _serve_command_block() -> str:
    """The serve command's source block INCLUDING its click decorators
    (the ``envvar=`` declarations live above the ``def``)."""
    text = COMMANDS.read_text(encoding="utf-8")
    start = text.index("def serve(")
    decorator = text.rfind("@cli.command()", 0, start)
    end = text.find("\n\n\n", start)
    assert decorator != -1 and end != -1, "the serve block must slice cleanly"
    return text[decorator:end]


def test_allowlist_is_hand_named_plus_the_imported_quota_keys() -> None:
    from benchweave.cli.env_file import ENV_FILE_HAND_NAMED_KEYS, serve_env_file_keys
    from benchweave.interfaces.app_entry import _QUOTA_ENV_KEYS

    assert serve_env_file_keys() == frozenset(ENV_FILE_HAND_NAMED_KEYS) | {
        env for _, env in _QUOTA_ENV_KEYS
    }
    # The quota keys are imported from app_entry, never re-spelled, so the
    # allowlist and build()'s quota reads cannot drift silently.
    for _, env in _QUOTA_ENV_KEYS:
        assert env in serve_env_file_keys()


def test_every_app_entry_and_serve_env_key_is_allowlisted_or_excluded() -> None:
    from benchweave.cli.env_file import serve_env_file_keys

    documented_exclusions = {
        "BENCHWEAVE_DB": "set/derived by the locator",
        "BENCHWEAVE_DATA_DIR": "the locator itself",
        "BENCHWEAVE_HOST": "click pre-reads the listener bind",
        "BENCHWEAVE_PORT": "click pre-reads the listener bind",
    }
    allowed = serve_env_file_keys() | set(documented_exclusions)
    reads = _env_key_reads(APP_ENTRY.read_text(encoding="utf-8")) | _env_key_reads(
        _serve_command_block()
    )
    missing = sorted(reads - allowed)
    assert not missing, (
        "env key(s) read by app_entry/serve but neither allowlisted for the "
        f"env file nor documented as excluded: {missing} — join "
        "serve_env_file_keys() or the documented exclusion set"
    )


def test_the_inventory_scan_discriminates_a_planted_key() -> None:
    """The scan's falsifier (design section 9): a planted unknown read MUST
    be reported by the same collector the inventory arm uses — proving the
    arm reds on a future un-allowlisted key instead of passing vacuously."""
    planted = _env_key_reads('x = os.environ.get("BENCHWEAVE_PLANTED_THING")')
    assert planted == {"BENCHWEAVE_PLANTED_THING"}
