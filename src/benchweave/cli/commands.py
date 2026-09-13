"""The ``benchweave`` Click command tree (Task 9: CLI foundation).

Eight commands — ``setup status demo report backup restore verify serve`` —
so ``--help`` is already the full operator surface. Only ``status`` is live
in this task; the other seven raise the exact stub message below (they exist
so the surface is complete and stable today, not to pretend functionality).

``status`` speaks to a live gateway over the stdlib-only REST client and
emits through :mod:`benchweave.cli.output` — ``--json`` is the machine
contract (shape pinned in that module's docstring and in the test suite).
Rendering is plain text for now; the Textual renderers (Task 12) slot in as
``render`` callables beside the current one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

import click

from benchweave import __version__
from benchweave.cli.client import GatewayClient, GatewayError
from benchweave.cli.output import emit


@click.group()
@click.version_option(version=__version__, prog_name="benchweave")
def cli() -> None:
    """BenchWeave operator CLI."""


def _not_implemented() -> None:
    """The Task 9 stub: honest failure, exact brief message."""
    raise click.ClickException("not implemented in this task")


@cli.command()
def setup() -> None:
    """Register benches and fixtures with a running gateway."""
    _not_implemented()


@cli.command()
def demo() -> None:
    """Run the built-in simulator demonstration."""
    _not_implemented()


@cli.command()
def report() -> None:
    """Render run evidence into an operator report."""
    _not_implemented()


@cli.command()
def backup() -> None:
    """Capture gateway state and evidence into a backup bundle."""
    _not_implemented()


@cli.command()
def restore() -> None:
    """Replay a backup bundle into a gateway."""
    _not_implemented()


@cli.command()
def verify() -> None:
    """Check a gateway's operational health and contract posture."""
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
    client = GatewayClient(gateway_url, token=token)
    try:
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
    except click.Abort:
        click.echo("aborted", err=True)
        return 130
