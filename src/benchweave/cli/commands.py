"""The ``benchweave`` Click command tree (Task 9: CLI foundation).

Eight commands — ``setup status demo report backup restore verify serve`` —
so ``--help`` is already the full operator surface. ``status`` (Task 9), the
four at-rest commands (Task 10), ``demo`` (Task 11: live-gateway mode or the
labelled ephemeral fresh-install simulation) and ``report`` (Task 13: the
store-derived report model with markdown/JSON emitters, at-rest only) are
live; ``serve`` raises the exact stub message below until Task 14 lands it.

``status`` speaks to a live gateway over the stdlib-only REST client; the
at-rest commands operate directly on the data directory under the
one-coordinator rule (``state.hold``). Both emit through
:mod:`benchweave.cli.output` — ``--json`` is the machine contract (shape
pinned in that module's docstring and in the test suite). On a TTY the
Task 12 Textual views render (:mod:`benchweave.cli.render` — ``status``
rides ``emit``'s TTY branch on its render callable; ``demo`` runs its live
event-fed view during the drive); non-TTY and ``--json`` paths are
unchanged plain/JSON.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import click

from benchweave import __version__
from benchweave.cli import atrest
from benchweave.cli import demo as demo_lib
from benchweave.cli.client import GatewayClient, GatewayError
from benchweave.cli.demo import View
from benchweave.cli.output import Renderer, emit
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
    except (atrest.AtRestError, OSError) as error:
        # T10 review carry: an unwritable/unusable parent (e.g. --data-dir
        # under a file) is a truthful refusal, never a traceback.
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
    except (atrest.AtRestError, StoreHeldError, OSError) as error:
        # OSError as a safety net (review I2): every mapped failure is an
        # AtRestError, but an unforeseen filesystem error must still be a
        # handled message, never a traceback.
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
    except (atrest.AtRestError, StoreHeldError, OSError) as error:
        # OSError as a safety net (review I2): e.g. staging into a
        # nonexistent parent is a refusal, not a FileNotFoundError traceback.
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
    try:
        # T10 review carry: a truncated/invalid manifest.json raises
        # AtRestError out of _load_manifest — exit truthfully, no traceback.
        problems = atrest.verify_problems(data_dir)
    except atrest.AtRestError as error:
        raise click.ClickException(str(error)) from error
    for problem in problems:
        click.echo(f"verify: {problem}", err=True)
    emit({"ok": not problems, "problems": problems})
    if problems:
        raise click.exceptions.Exit(1)


@cli.command()
@click.option(
    "--gateway",
    "gateway_url",
    envvar="BENCHWEAVE_GATEWAY",
    default=None,
    help=(
        "Drive the LIVE gateway at this base URL (e.g. http://127.0.0.1:8123) "
        "instead of booting an ephemeral simulation."
    ),
)
@click.option(
    "--token",
    envvar="BENCHWEAVE_TOKEN",
    default=None,
    help=(
        "Bearer token for --gateway mode (control tier or higher). "
        "Ignored in fresh-install mode."
    ),
)
@click.option(
    "--scratch",
    "scratch",
    type=click.Path(path_type=Path),
    default=None,
    help=(
        "Fresh-install mode: directory for the ephemeral store (created if "
        "absent; removed on exit unless --keep — a pre-existing directory "
        "itself is never deleted, only the demo's store files). "
        "Fresh-install mode only — ignored with --gateway."
    ),
)
@click.option(
    "--keep",
    "keep",
    is_flag=True,
    help=(
        "Fresh-install mode: keep the scratch directory after the demo. "
        "Ignored with --gateway."
    ),
)
@click.option(
    "--timeout",
    "timeout_s",
    type=float,
    default=demo_lib.DEFAULT_TIMEOUT_S,
    show_default=True,
    help="Seconds to wait for the demonstration run to reach a terminal state.",
)
@click.option(
    "--fixtures",
    "fixtures",
    type=click.Path(path_type=Path),
    default=None,
    envvar="BENCHWEAVE_FIXTURES",
    help="Fixture lattice directory (default: the repository execution lattice).",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Emit the stable machine JSON contract instead of text.",
)
def demo(
    gateway_url: str | None,
    token: str | None,
    scratch: Path | None,
    keep: bool,
    timeout_s: float,
    fixtures: Path | None,
    json_output: bool,
) -> None:
    """Run the built-in simulator demonstration."""
    _set_json(json_output)
    if timeout_s <= 0:
        raise click.ClickException("--timeout must be a positive number of seconds")
    view: View | None = None
    if sys.stdout.isatty() and not json_output:
        # Task 12: on a TTY the demo is a LIVE Textual view the command
        # feeds events to as they arrive (the view never drives the
        # gateway); the plain summary still prints after the view closes.
        from benchweave.cli.render import TextualRenderer

        view = TextualRenderer().demo_view
    if gateway_url is not None:
        if token is None:
            raise click.ClickException(
                "--gateway mode needs --token (or BENCHWEAVE_TOKEN)"
            )
        try:
            payload = demo_lib.drive_live_gateway(
                gateway_url, token, fixtures=fixtures, timeout_s=timeout_s, view=view
            )
        except (demo_lib.DemoError, GatewayError) as error:
            raise click.ClickException(str(error)) from error
    else:
        try:
            payload = demo_lib.run_simulation(
                scratch=scratch,
                keep=keep,
                fixtures=fixtures,
                timeout_s=timeout_s,
                view=view,
            )
        except (demo_lib.DemoError, GatewayError) as error:
            raise click.ClickException(str(error)) from error
    emit(payload, render=demo_lib.render_demo)


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
    "--bench",
    "bench_id",
    default=None,
    help="Restrict the report to one bench id (default: every bench).",
)
@click.option(
    "--out",
    "out",
    type=click.Path(path_type=Path),
    default=None,
    help="Write the report to FILE (markdown; JSON with --json) instead of stdout.",
)
@click.option(
    "--gateway",
    "gateway_url",
    envvar="BENCHWEAVE_GATEWAY",
    default=None,
    help=(
        "NOT IMPLEMENTED: compose the report from a live gateway over REST. "
        "The report is at-rest only in this task — read the data directory."
    ),
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Emit the stable machine JSON contract instead of text.",
)
def report(
    data_dir: Path,
    bench_id: str | None,
    out: Path | None,
    gateway_url: str | None,
    json_output: bool,
) -> None:
    """Render run evidence into an operator report (store at rest)."""
    _set_json(json_output)
    if gateway_url is not None:
        # Controller ruling 2: --gateway composition would fork the model
        # into a second read path — a documented stub this task, not a
        # silent fallthrough to at-rest reads.
        raise click.ClickException(
            "not implemented in this task: --gateway report composition — "
            "the report reads the data directory at rest; drop --gateway"
        )
    from benchweave.cli import report as report_lib
    from benchweave.cli.atrest import AtRestError

    try:
        model = report_lib.report_from_data_dir(
            data_dir, bench_id=bench_id, now=report_lib.now_iso()
        )
    except (AtRestError, StoreHeldError, ValueError, OSError) as error:
        raise click.ClickException(str(error)) from error
    if json_output:
        if out is not None:
            _write_out(out, report_lib.render_json(model))
            return
        emit(model)
        return
    if out is not None:
        _write_out(out, report_lib.render_markdown(model))
        return
    if sys.stdout.isatty():
        # The Task 12 view layer: on a TTY the Textual report view runs.
        from benchweave.cli.render import TextualRenderer

        TextualRenderer().report_view(model)
        return
    click.echo(report_lib.render_markdown(model))


def _write_out(out: Path, text: str) -> None:
    """Write an --out report file; an unusable path refuses truthfully."""
    try:
        out.write_text(text + "\n", encoding="utf-8")
    except OSError as error:
        raise click.ClickException(f"cannot write {out}: {error}") from error
    click.echo(f"wrote {out}", err=True)


@cli.command()
def serve() -> None:
    """Run a BenchWeave gateway locally."""
    _not_implemented()


# --- status: the first live command -------------------------------------------


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
    render: Renderer | None = None
    if sys.stdout.isatty() and not json_output:
        # Task 12 wiring: the render callable carries the Textual view for
        # emit's TTY branch; non-TTY and --json keep their pinned paths.
        from benchweave.cli.render import StatusRender

        render = StatusRender(
            info, cast(Sequence[Mapping[str, object]], benches["items"])
        )
    emit({"gateway": info, "benches": benches}, render=render)


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
