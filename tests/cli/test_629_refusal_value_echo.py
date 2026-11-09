"""Issue #629: a boot refusal must never print the env-file VALUE.

#626 closed the KEY-position leak in :mod:`benchweave.cli.env_file`. These arms
close the value half: the boot refusals in
:mod:`benchweave.interfaces.app_entry` fire on values that may have come from
the SAME credential file, and a mangled line can put a secret in value
position. Every arm drives the real ``serve --data-dir`` path, because that is
where the loader applies the file and ``build()`` refuses — a direct call to the
helper would pass while the composed path leaked.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from benchweave.cli.commands import cli

#: A key-shaped secret (invented): the same class #626 carried, because the env
#: file is the input an operator hand-edits and a mangled line can land one
#: here just as easily as in key position.
_SECRET = "a1B2c3D4e5F6g7H8_9I0jKlMnOpQrStUvWxYz012345"


@pytest.fixture(scope="module")
def gateway_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A data dir with a real store. ``serve`` refuses a storeless dir BEFORE
    it parses the environment, so the boot refusal is unreachable without one."""
    data_dir = tmp_path_factory.mktemp("gateway")
    result = CliRunner().invoke(cli, ["setup", "--data-dir", str(data_dir)])
    assert result.exit_code == 0, result.output
    return data_dir


@pytest.fixture()
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Scrub ``BENCHWEAVE_*`` and restore the exact prior state afterwards —
    INCLUDING keys the loader bridges in with a bare setdefault, which
    monkeypatch cannot track (the env-file suite carries this fixture for the
    same reason: a leaked value from one arm signs or configures the next)."""
    original = {key: value for key, value in os.environ.items() if key.startswith("BENCHWEAVE_")}
    for key in original:
        monkeypatch.delenv(key, raising=False)
    yield
    for key in [k for k in os.environ if k.startswith("BENCHWEAVE_") and k not in original]:
        del os.environ[key]


def _serve_with(data_dir: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> Result:
    """One mock serve over a data dir whose credential file carries ``body``;
    uvicorn parked so a non-refusing arm cannot bind a port."""
    import uvicorn

    env = data_dir / "benchweave.env"
    env.write_text(body, encoding="utf-8")
    env.chmod(0o600)
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)
    return CliRunner().invoke(cli, ["serve", "--data-dir", str(data_dir)])


@pytest.mark.parametrize(
    ("body", "key", "forbidden"),
    [
        # The enum site: an unknown word.
        (f"BENCHWEAVE_UI={_SECRET}\n", "BENCHWEAVE_UI", _SECRET),
        # The quota parse site: not an integer.
        (f"BENCHWEAVE_MAX_DATASET_BYTES={_SECRET}\n", "BENCHWEAVE_MAX_DATASET_BYTES", _SECRET),
        # The quota floor site: an integer under the seconds floor. The leak's
        # spelling is the repr (`='10'`), so that is what absence is pinned on.
        ("BENCHWEAVE_UI_SESSION_TTL_MS=10\n", "BENCHWEAVE_UI_SESSION_TTL_MS", "'10'"),
        # The fixtures site: the knob was SET, so its value is file content.
        (f"BENCHWEAVE_FIXTURES={_SECRET}\n", "BENCHWEAVE_FIXTURES", _SECRET),
    ],
)
def test_629_a_boot_refusal_never_echoes_a_value_from_the_env_file(
    gateway_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    clean_env: None,
    body: str,
    key: str,
    forbidden: str,
) -> None:
    result = _serve_with(gateway_dir, monkeypatch, body)
    combined = result.output + (str(result.exception) if result.exception else "")
    assert result.exit_code != 0, combined
    # The refusal still teaches: it names the setting (and, for the enum and
    # floor sites, the requirement), which is what finds the line.
    assert key in combined, combined
    assert forbidden not in combined, combined


def test_629_the_built_in_fixtures_path_is_still_named(
    gateway_dir: Path, monkeypatch: pytest.MonkeyPatch, clean_env: None
) -> None:
    """The other half of the fixtures rule: when the knob is UNSET the path is
    our own default, not file content, and naming it is the whole diagnostic
    value of the wheel-install refusal — so that case keeps the path.

    The default is pointed at a path that cannot exist, because a repo checkout
    HAS a fixtures lattice and would boot instead of refusing (the wheel case
    this refusal was written for is exactly the missing lattice).
    """
    from benchweave.interfaces import app_entry

    monkeypatch.setattr(app_entry, "_DEFAULT_FIXTURES", Path("/nonexistent/fixtures/lattice"))
    result = _serve_with(gateway_dir, monkeypatch, "BENCHWEAVE_UI=1\n")
    combined = result.output + (str(result.exception) if result.exception else "")
    assert result.exit_code != 0, combined
    assert "the built-in path" in combined, combined
    assert "BENCHWEAVE_FIXTURES" in combined, combined
