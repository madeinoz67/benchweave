"""The canonical fixtures (G1b design record §1.1): one instance per row's
needs, values taken from the contract's own canonical literals.

The contract rows are normative and the fixtures follow them: §E.1's Notes
carry the canonical values (reading-tile quality ``steady`` freshness
``2 s``; confirm-action's exact armed literals incl. ``PSU-07 output``; the
plot 100→2 voltage decimation; the lanes 1000→12 capture at 1 MHz), and
§E.2.6/§E.4.6 name their canonical markers (``UART-REF · 115200 8N1``).
The React compositions are semantic reference only — the rows are the
authority (design record O3).
"""

from __future__ import annotations

from benchweave_ui_html.data import ButtonData


def button() -> ButtonData:
    """§E.1 ``button``: an enabled primary button with a text label (the
    Notes column: destructive/protective always carry a text label — the
    canonical fixture is primary, also labelled)."""
    return ButtonData(label="Energise output", variant="primary", busy=False)
