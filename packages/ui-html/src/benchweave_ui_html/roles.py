"""Pure-Python accessibility-role resolver (UR-05, fork F-B ruled).

Computes an element's role from explicit ``role=`` attributes plus implicit
ARIA roles derived from element names — an accessibility-tree query, never a
CSS-selector stand-in. Coverage is pinned to EXACTLY the roles the contract's
§E.1 Required-roles cells name (button, slider, region, status, img, table —
design record §13: extract from the cells, pin exactly those, no broader); a
role outside that set cannot be computed by this resolver and raises
``RoleUnresolvable`` rather than answering false (a false negative here would
be a silent pass upstream).

The browser-grade resolver (Playwright + axe, UR-05 Direction and UR-09)
lands behind this same ``RoleResolver`` protocol as a test extra; when it
arrives, any row it calls red that this resolver called green kills this
resolver's authority retroactively (design record §9 risk 4).
"""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Protocol

ROLE_UNRESOLVABLE = "role-unresolvable"

SUPPORTED_ROLES: frozenset[str] = frozenset(
    {"button", "slider", "region", "status", "img", "table"}
)

# Implicit ARIA roles for the elements that can carry the contract's roles.
# Deliberately minimal: an element outside this map carries no implicit role
# this resolver can compute.
_IMPLICIT_ROLES: dict[str, str] = {
    "button": "button",
    "table": "table",
    "img": "img",
    "section": "region",
    "output": "status",
}


class RoleUnresolvable(Exception):
    """Raised when the resolver is asked about a role it cannot compute."""


class _RoleCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: value for name, value in attrs}
        explicit = attributes.get("role")
        if explicit is not None:
            self.found.append(explicit.strip())
            return
        if tag == "input":
            # input[type=range] carries the slider role; other input types
            # carry roles outside this resolver's pinned set.
            if attributes.get("type") == "range":
                self.found.append("slider")
            return
        implicit = _IMPLICIT_ROLES.get(tag)
        if implicit is not None:
            self.found.append(implicit)


class RoleResolver(Protocol):
    def has_role(self, html: str, role: str) -> bool: ...


class ImplicitRoleResolver:
    """The G1a authority: stdlib html.parser over the rendered string."""

    def has_role(self, html: str, role: str) -> bool:
        if role not in SUPPORTED_ROLES:
            raise RoleUnresolvable(f"{ROLE_UNRESOLVABLE}: {role}")
        collector = _RoleCollector()
        collector.feed(html)
        collector.close()
        return role in collector.found
