"""Role-resolver unit tests (UR-05, fork F-B): implicit roles, explicit
overrides, and fail-closed on uncomputable roles."""

from __future__ import annotations

import pytest
from benchweave_ui_html.roles import (
    ROLE_UNRESOLVABLE,
    SUPPORTED_ROLES,
    ImplicitRoleResolver,
    RoleUnresolvable,
)


def test_supported_roles_are_exactly_the_contract_section_e1_set() -> None:
    assert {"button", "slider", "region", "status", "img", "table"} == SUPPORTED_ROLES


@pytest.mark.parametrize(
    ("html", "role"),
    [
        ("<button>Apply</button>", "button"),
        ('<input type="range" aria-label="Voltage">', "slider"),
        ("<section aria-label=\"Output set-point\">…</section>", "region"),
        ("<output>Updated</output>", "status"),
        ("<img alt=\"Trace\">", "img"),
        ("<table><caption>Readings</caption></table>", "table"),
        ('<div role="status">Saved</div>', "status"),
        ('<span role="img" aria-label="Traces"></span>', "img"),
    ],
)
def test_has_role_true(html: str, role: str) -> None:
    assert ImplicitRoleResolver().has_role(html, role) is True


def test_has_role_false_is_a_clean_negative() -> None:
    assert ImplicitRoleResolver().has_role("<button>Apply</button>", "table") is False


def test_explicit_role_overrides_the_implicit_one() -> None:
    """role=presentation suppresses the implicit table role (a real override,
    not just an absent attribute); asking for a role outside the pinned set
    still raises — the negative is only clean inside SUPPORTED_ROLES."""
    resolver = ImplicitRoleResolver()
    assert resolver.has_role('<table role="presentation"></table>', "table") is False
    assert resolver.has_role('<table role="status"></table>', "table") is False
    assert resolver.has_role('<table role="status"></table>', "status") is True


def test_uncomputable_role_raises_rather_than_passing() -> None:
    with pytest.raises(RoleUnresolvable, match=ROLE_UNRESOLVABLE):
        ImplicitRoleResolver().has_role("<div role='presentation'></div>", "presentation")


def test_input_types_outside_the_pinned_set_do_not_resolve() -> None:
    with pytest.raises(RoleUnresolvable):
        ImplicitRoleResolver().has_role('<input type="number">', "spinbutton")
