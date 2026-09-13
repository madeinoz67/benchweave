"""Emission layer for the BenchWeave CLI: machine output is first-class.

Routing (the Task 9 contract):

- ``--json``  → ``json.dumps`` (``indent=2``, ``sort_keys=True``) to stdout.
                This is the MACHINE CONTRACT Tasks 10-15 build on — additive
                only; renaming or removing keys is a breaking change.
- TTY, no flags → the caller's ``render`` callable — plain text by
                default; a render callable that carries a ``textual_view()``
                method (the Task 12 render layer) RUNS that Textual view on
                the TTY instead of printing.
- non-TTY    → the built-in generic plain-text fallback below.

The ``--json`` flag travels via the active Click context object (``ctx.obj``)
so the callable signature stays exactly ``emit(data, *, render=None)``.

Pinned ``status --json`` shape (Tasks 10-15 consume this)::

    {
      "benches": {                # GET /v1/benches data payload, verbatim
        "items": [ ... contract bench objects ... ],
        "next_cursor": "..." | null
      },
      "gateway": {                # GET /v1 data payload, verbatim
        "gateway_id": "...",
        "interface_version": "1.1.0",
        "mcp_version": "2026-07-28",
        "limits": { ... }
      }
    }
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

import click


class Renderer(Protocol):
    """A TTY renderer: maps emitted data to display text."""

    def __call__(self, data: Mapping[str, object]) -> str: ...


def _json_requested() -> bool:
    """Read the ``--json`` flag from the active Click context, if any."""
    ctx = click.get_current_context(silent=True)
    if ctx is None or not isinstance(ctx.obj, dict):
        return False
    return bool(ctx.obj.get("json", False))


def _plain(value: object, indent: int = 0) -> list[str]:
    """Generic deterministic plain-text dump (the non-TTY fallback)."""
    pad = " " * indent
    lines: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(item, str) or not isinstance(item, Mapping | Sequence):
                lines.append(f"{pad}{key}: {item}")
            else:
                lines.append(f"{pad}{key}:")
                lines.extend(_plain(item, indent + 2))
    elif isinstance(value, Sequence) and not isinstance(value, str):
        for item in value:
            lines.extend(_plain(item, indent))
    else:
        lines.append(f"{pad}{value}")
    return lines


def emit(
    data: Mapping[str, object] | Sequence[Mapping[str, object]],
    *,
    render: Renderer | None = None,
) -> None:
    """Write ``data`` to stdout per the routing contract in the module docstring."""
    if _json_requested():
        click.echo(json.dumps(data, indent=2, sort_keys=True))
        return
    if sys.stdout.isatty() and render is not None and isinstance(data, Mapping):
        textual_view: Callable[[], None] | None = getattr(render, "textual_view", None)
        if textual_view is not None:
            # Task 12 wiring: the render callable carries the command's
            # Textual view — on a TTY the view runs; emit prints nothing.
            textual_view()
            return
        click.echo(render(data))
        return
    click.echo("\n".join(_plain(data)))
