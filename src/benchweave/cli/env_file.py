"""The serve env-file loader (issue #422 increment 1).

``benchweave serve`` bridges ``<data-dir>/benchweave.env`` — the credential
file ``setup`` writes and operators may hand-extend with allowlisted
service keys — into the process environment, set-if-not-set, before
``app_entry.build()`` runs. The parse rules and refusal wording are shared
VERBATIM with the SDK twin (``benchweave_sdk_server/env_file.py``); the
twin test suites assert the same literal expected strings, so the two
repos cannot drift silently.

Refusals are typed with the ``env_file:`` prefix and name the path, the
line number, the key (when parseable) and the problem class — never the
raw line, because a refusal that echoes the line echoes the secret. Serve
exits non-zero, ``build()`` is never called, and nothing touches disk.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import NoReturn

#: The machine-matchable refusal prefix (the ``no_matching_rule:`` family
#: style — ``env_file:`` joins the vocabulary).
ENV_FILE_REFUSAL_PREFIX = "env_file:"

#: The hand-named half of the serve allowlist. The quota keys are DERIVED
#: from ``app_entry._QUOTA_ENV_KEYS`` in :func:`serve_env_file_keys` so the
#: allowlist and build()'s quota reads cannot drift silently.
ENV_FILE_HAND_NAMED_KEYS = (
    "BENCHWEAVE_SECRET",
    "BENCHWEAVE_ENV",
    "BENCHWEAVE_FIXTURES",
    "BENCHWEAVE_REGISTRY_DIR",
    "BENCHWEAVE_UI",
)

#: Keys that may NEVER come from the file, each with its refusal reason
#: (design section 2.3's exclusion table). The SDK twin passes no map: its
#: two-key allowlist refuses everything else as unknown already.
ENV_FILE_EXCLUDED_KEYS: dict[str, str] = {
    "BENCHWEAVE_DATA_DIR": "it is a locator; the file is found by it",
    "BENCHWEAVE_DB": (
        "it is derived from the data-dir — the directory you point serve"
        " at is the store you serve"
    ),
    "BENCHWEAVE_HOST": (
        "click reads it from flags/process env before the command body"
        " runs — a file value could never take effect"
    ),
    "BENCHWEAVE_PORT": (
        "click reads it from flags/process env before the command body"
        " runs — a file value could never take effect"
    ),
}

_KEY_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
#: Line splitting on the three newline forms ONLY (fold R4): U+2028/NEL
#: are not line ends here — ``str.splitlines()`` would split on them and
#: truncate values. They are not C0, so they stay in the value verbatim.
_LINE_SEPARATOR = re.compile(r"\r\n|\r|\n")
#: Any C0 control in a VALUE refuses (fold R3): allowlist value domains
#: (paths, urlsafe tokens, ints, enums) never carry controls.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f]")


class EnvFileError(RuntimeError):
    """A typed env-file refusal (the CLI shows it and exits non-zero)."""


def _refuse(path: Path, lineno: int, detail: str) -> NoReturn:
    raise EnvFileError(f"{ENV_FILE_REFUSAL_PREFIX} {path}: line {lineno}: {detail}")


def _strip_one_quote_layer(value: str, path: Path, lineno: int, key: str) -> str:
    """Strip ONE layer of matching single or double quotes (systemd
    ``EnvironmentFile`` compatibility for operators copying shell-export
    lines). No escape sequences, no variable expansion — a value that
    opens a quote it does not close refuses rather than half-apply."""
    first = value[:1]
    if first not in ("\"", "'"):
        return value
    if len(value) >= 2 and value[-1] == first:
        return value[1:-1]
    _refuse(path, lineno, f"{key}: mismatched quotes")


def _check_owner_only(path: Path) -> None:
    """Refuse group/other access on POSIX (the file carries a live secret;
    ssh's posture, not a warning). Windows: mode bits do not reach the ACL
    and setup enforces owner-only at write time — no check here (W1
    residual, corroborated by the Windows CI leg)."""
    if sys.platform == "win32":
        return
    mode = path.stat().st_mode
    # Fold R2: 0o077 (group/other), not 0o177 — the owner-execute bit is
    # not group access, so a 0700 file loads. Bits above 0o777
    # (setuid/setgid/sticky) are unexamined — disclosed residual.
    if mode & 0o077:
        raise EnvFileError(
            f"{ENV_FILE_REFUSAL_PREFIX} {path}: mode {mode & 0o7777:o} allows"
            " group or other access — the file carries a live secret;"
            " restrict it to the owner (chmod 0600)"
        )


def parse_env_file(
    path: Path,
    allowed: frozenset[str],
    excluded: Mapping[str, str] | None = None,
) -> list[tuple[int, str, str]]:
    """Validate the WHOLE file and return ``(lineno, key, value)`` entries.

    This is the two-phase core (fold R5): nothing touches ``os.environ``
    until every line has parsed and validated, so a refused file leaves no
    residue. Per-line rules beyond the original set: a value whose first
    character is a space/tab after the ``=`` refuses (fold R1 — the ``KEY
    = value`` typo class; NOT systemd-style trimming, which would re-open
    the silent-corruption class); any C0 control character in a value
    refuses (fold R3); a duplicate key refuses naming both lines (fold
    R9 — an editing mistake must not silently keep the old value).
    Refuses carry the ``env_file:`` prefix and never echo the raw line.
    """
    _check_owner_only(path)
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            # newline="" keeps \r/\r\n untranslated so the loader's own
            # separator split (fold R4) is the only line splitting.
            text = handle.read()
    except OSError as error:
        raise EnvFileError(
            f"{ENV_FILE_REFUSAL_PREFIX} {path}: cannot read it: {error}"
        ) from error
    except UnicodeDecodeError as error:
        raise EnvFileError(
            f"{ENV_FILE_REFUSAL_PREFIX} {path}: not valid UTF-8: {error}"
        ) from error
    entries: list[tuple[int, str, str]] = []
    first_line: dict[str, int] = {}
    for lineno, raw in enumerate(_LINE_SEPARATOR.split(text), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            _refuse(path, lineno, 'no "=" in line — expected KEY=VALUE')
        key, _, value = line.partition("=")
        if _KEY_PATTERN.fullmatch(key) is None:
            # A BOM lands here too: it corrupts the first key into an
            # invalid key name and refuses (the exact-byte decoder's
            # posture).
            _refuse(path, lineno, f"key name {key!r} does not match [A-Za-z_][A-Za-z0-9_]*")
        if excluded is not None and key in excluded:
            _refuse(path, lineno, f"{key} may not come from the env file — {excluded[key]}")
        if key not in allowed:
            _refuse(
                path,
                lineno,
                f"{key} is not allowlisted for the serve env file — allowed"
                " keys: " + ", ".join(sorted(allowed)),
            )
        if value[:1] in (" ", "\t"):
            _refuse(path, lineno, f'{key}: value starts with whitespace after "="')
        value = _strip_one_quote_layer(value, path, lineno, key)
        if not value.strip():
            _refuse(path, lineno, f"{key} is set but empty")
        control = _CONTROL_CHARS.search(value)
        if control is not None:
            _refuse(
                path,
                lineno,
                f"{key}: value contains a control character"
                f" (0x{ord(control.group()):02x})",
            )
        if key in first_line:
            _refuse(
                path,
                lineno,
                f"{key} appears twice (first at line {first_line[key]})"
                " — one value per key",
            )
        first_line[key] = lineno
        entries.append((lineno, key, value))
    return entries


def apply_env_entries(entries: list[tuple[int, str, str]]) -> list[str]:
    """Apply parsed entries set-if-not-set into ``os.environ``; return the
    applied key names (a key already present in the environment is left
    alone — explicit process environment always wins)."""
    applied: list[str] = []
    for _lineno, key, value in entries:
        if key not in os.environ:
            os.environ[key] = value
            applied.append(key)
    return applied


def load_env_file(
    path: Path,
    allowed: frozenset[str],
    excluded: Mapping[str, str] | None = None,
) -> list[str]:
    """Parse ``path`` per the shared rules, apply set-if-not-set into
    ``os.environ``, and return the applied key names (``parse_env_file``
    followed by ``apply_env_entries`` — kept as the section-2.7 contract).

    Rules (design section 2.4 as amended by the fold wave, shared verbatim
    with the SDK twin): lines split on ``\r\n``/``\r``/``\n`` only; blank
    lines and full-line ``#`` comments are skipped (no inline comments);
    KEY must match ``[A-Za-z_][A-Za-z0-9_]*`` and be allowlisted; the
    first ``=`` separates so a value may contain ``=``; a leading
    space/tab after the ``=``, a C0 control in the value, a duplicate key,
    or a set-but-empty (whitespace-only) value all refuse; VALUE strips
    one layer of matching quotes. Malformed anything refuses loudly,
    prefix ``env_file:``, never echoing the raw line.
    """
    return apply_env_entries(parse_env_file(path, allowed, excluded))


def serve_env_file_keys() -> frozenset[str]:
    """The closed serve allowlist: the hand-named service keys plus the
    quota keys imported from ``app_entry`` (never re-spelled). No
    bench-safety envelope is file-settable — A02's commissioning rule
    governs bench hazards, not ambient service configuration."""
    from benchweave.interfaces.app_entry import _QUOTA_ENV_KEYS

    return frozenset(ENV_FILE_HAND_NAMED_KEYS) | {env for _, env in _QUOTA_ENV_KEYS}
