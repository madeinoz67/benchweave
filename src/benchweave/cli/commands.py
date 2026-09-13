"""The ``benchweave`` Click command tree (Task 9: CLI foundation).

Eight commands — ``setup status demo report backup restore verify serve`` —
so ``--help`` is already the full operator surface. ``status`` (Task 9) and
the four at-rest commands (Task 10) are live; ``demo``/``report``/``serve``
raise the exact stub message below until Tasks 11-14 land them.

``status`` speaks to a live gateway over the stdlib-only REST client; the
at-rest commands operate directly on the data directory under the
one-coordinator rule (``state.hold``). Both emit through
:mod:`benchweave.cli.output` — ``--json`` is the machine contract (shape
pinned in that module's docstring and in the test suite). Rendering is
plain text for now; the Textual renderers (Task 12) slot in as ``render``
callables beside the current one.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import click

from benchweave import __version__
from benchweave.cli import atrest
from benchweave.cli.client import GatewayClient, GatewayError
from benchweave.cli.output import emit
from benchweave.state.hold import StoreHeldError


@click.group()
@click.version_option(version=__version__, prog_name="benchweave")
def cli() -> None:
    """BenchWeave operator CLI."""


def _not_implemented() -> None:
    """The Task 9 stub: honest failure, exact brief message."""
    raise click.ClickException("not implemented in this task")


def _set_json(json_output: bool) -> None:
    """Carry the ``--json`` flag to :func:`benchweave.cli.output.emit`."""
    ctx = click.get_current_context()
    obj = ctx.ensure_object(dict)
    obj["json"] = json_output


# --- at-rest commands (Task 10) -------------------------------------------------


_DATA_DIR_HELP = "At-rest data directory (holds state.sqlite + content/)."


@cli.command()
@click.option(
    "--data-dir",
    "data_dir",
    type=click.Path(path_type=Path),
    required=True,
    envvar="BENCHWEAVE_DATA_DIR",
    help=_DATA_DIR_HELP,
)
@click.option(
    "--show-secret",
    "show_secret",
    is_flag=True,
    help=(
        "Print the generated gateway secret to stdout. Default: the secret is "
        "written only to <data-dir>/benchweave.env (mode 0600) and never printed."
    ),
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Emit the stable machine JSON contract instead of text.",
)
def setup(data_dir: Path, show_secret: bool, json_output: bool) -> None:
    """Initialize an at-rest data directory (fresh store + credentials)."""
    _set_json(json_output)
    try:
        db = atrest.setup(data_dir)
    except atrest.AtRestError as error:
        raise click.ClickException(str(error)) from error
    secret_file = data_dir / atrest.CREDENTIAL_FILE
    click.echo(
        f"initialized {data_dir}\n"
        f"store: {db} (migrations applied at creation, as at app boot)\n"
        f"secret: written to {secret_file} — keep it 0600; it is never printed"
        + ("" if show_secret else " (use --show-secret to print it)"),
        err=True,
    )
    payload: dict[str, object] = {
        "data_dir": str(data_dir),
        "db_path": str(db),
        "secret_file": str(secret_file),
    }
    if show_secret:
        try:
            payload["secret"] = atrest.read_secret(data_dir)
        except atrest.AtRestError as error:
            raise click.ClickException(str(error)) from error
    emit(payload)


@cli.command()
@click.option(
    "--data-dir",
    "data_dir",
    type=click.Path(path_type=Path),
    required=True,
    envvar="BENCHWEAVE_DATA_DIR",
    help=_DATA_DIR_HELP,
)
@click.option(
    "--out",
    "out",
    type=click.Path(path_type=Path),
    default=Path("."),
    help="Directory to place backup-<iso>/ under (default: cwd).",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Emit the stable machine JSON contract instead of text.",
)
def backup(data_dir: Path, out: Path, json_output: bool) -> None:
    """Snapshot the store + content into a verified backup directory."""
    _set_json(json_output)
    try:
        target = atrest.backup(data_dir, out)
    except (atrest.AtRestError, StoreHeldError) as error:
        raise click.ClickException(str(error)) from error
    manifest = json.loads(
        (target / atrest.MANIFEST_NAME).read_text(encoding="utf-8")
    )
    files = manifest.get("files", {})
    emit(
        {
            "backup": str(target),
            "wal_included": bool(manifest.get("wal_included", False)),
            "files": len(files) if isinstance(files, dict) else 0,
        }
    )


@cli.command()
@click.option(
    "--archive",
    "archive",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
    required=True,
    help="Backup directory (backup-<iso>/) to restore from.",
)
@click.option(
    "--data-dir",
    "data_dir",
    type=click.Path(path_type=Path),
    required=True,
    envvar="BENCHWEAVE_DATA_DIR",
    help=_DATA_DIR_HELP,
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Emit the stable machine JSON contract instead of text.",
)
def restore(archive: Path, data_dir: Path, json_output: bool) -> None:
    """Verify a backup archive and swap it in as the data directory."""
    _set_json(json_output)
    try:
        atrest.restore(archive, data_dir)
    except (atrest.AtRestError, StoreHeldError) as error:
        raise click.ClickException(str(error)) from error
    emit({"restored": str(data_dir), "archive": str(archive)})


@cli.command()
@click.option(
    "--data-dir",
    "data_dir",
    type=click.Path(path_type=Path),
    required=True,
    envvar="BENCHWEAVE_DATA_DIR",
    help="Data directory (or backup archive) carrying manifest.json.",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Emit the stable machine JSON contract instead of text.",
)
def verify(data_dir: Path, json_output: bool) -> None:
    """Check manifest digests + store integrity (exit 0 iff clean)."""
    _set_json(json_output)
    problems = atrest.verify_problems(data_dir)
    for problem in problems:
        click.echo(f"verify: {problem}", err=True)
    emit({"ok": not problems, "problems": problems})
    if problems:
        raise click.exceptions.Exit(1)


@cli.command()
def demo() -> None:
    """Run the built-in simulator demonstration."""
    _not_implemented()


@cli.command()
def report() -> None:
    """Render run evidence into an operator report."""
    _not_implemented()


@cli.command()
def serve() -> None:
    """Run a BenchWeave gateway locally."""
    _not_implemented()


# --- status: the first live command -------------------------------------------


def _render_status(data: Mapping[str, object]) -> str:
    """Plain-text TTY rendering (the Textual renderer lands beside it in Task 12)."""
    gateway = cast(Mapping[str, object], data["gateway"])
    benches = cast(Mapping[str, object], data["benches"])
    items = cast(Sequence[Mapping[str, object]], benches["items"])
    lines = [
        f"gateway_id:        {gateway['gateway_id']}",
        f"interface_version: {gateway['interface_version']}",
        f"mcp_version:       {gateway['mcp_version']}",
        f"benches:           {len(items)}",
    ]
    for item in items:
        lines.append(
            "  {bench_id}  generation={generation} "
            "qualification={qualification} busy={busy} tripped={tripped}".format_map(
                {k: str(v) for k, v in item.items()}
            )
        )
    return "\n".join(lines)


@cli.command()
@click.option(
    "--gateway",
    "gateway_url",
    required=True,
    envvar="BENCHWEAVE_GATEWAY",
    help="Gateway base URL, e.g. http://127.0.0.1:8123",
)
@click.option(
    "--token",
    required=True,
    envvar="BENCHWEAVE_TOKEN",
    help="Bearer token (observe tier or higher).",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Emit the stable machine JSON contract instead of text.",
)
def status(gateway_url: str, token: str, json_output: bool) -> None:
    """Show gateway identity and the bench inventory."""
    ctx = click.get_current_context()
    obj = ctx.ensure_object(dict)
    obj["json"] = json_output
    try:
        client = GatewayClient(gateway_url, token=token)
        info = client.gateway_info()
        benches = client.bench_list()
    except GatewayError as error:
        raise click.ClickException(str(error)) from error
    emit({"gateway": info, "benches": benches}, render=_render_status)


# --- entrypoint ---------------------------------------------------------------


def main(args: Sequence[str] | None = None) -> int:
    """Console-script entrypoint: run the Click tree, return an exit code.

    Success is 0; a ClickException (bad usage, unreachable gateway, rejected
    token) is shown on stderr and returns 1; Ctrl-C style aborts return 130.
    """
    try:
        return int(cli.main(args=args, standalone_mode=False) or 0)
    except click.ClickException as error:
        error.show()
        return 1
    except click.exceptions.Exit as requested:
        # A command's own exit code (e.g. ``verify`` failing its checks).
        return int(requested.exit_code)
    except click.Abort:
        click.echo("aborted", err=True)
        return 130
