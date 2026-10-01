"""Plain-data component models (UR-01: "plain data, never host objects").

One frozen dataclass per component family; the renderers (``partials.py``)
take these in and emit HTML strings. Closed enumerations are ``Literal``
aliases so a bad state is unrepresentable rather than validated at render
time — the values are the contract's own keys (§B.1 severities, §E.1 button
variants, §C.2 disabled reasons).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: §B.1 severity keys (the closed enum; renderers use names, never colour alone).
Severity = Literal["neutral", "success", "advisory", "warning", "critical", "trip"]

#: §E.1 button row Notes: the five variants.
ButtonVariant = Literal["primary", "secondary", "tertiary", "destructive", "protective"]


@dataclass(frozen=True)
class ButtonData:
    """§E.1 ``button``: a native button with its variant and busy state.

    ``disabled_reason``/``disabled_label`` carry §C.2's disabled-reason
    shape (the visible label renders beside the control, never aria-only);
    both ``None`` for an enabled canonical fixture.
    """

    label: str
    variant: ButtonVariant = "primary"
    busy: bool = False
    disabled_reason: str | None = None
    disabled_label: str | None = None
