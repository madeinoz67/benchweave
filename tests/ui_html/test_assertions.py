"""Unit tests for the HTML assertion layer (G1b design record §1.1).

The checks mirror the contract's item classes exactly: root element,
attribute present/equals/contains over ANY element, class-hook containment,
required-text over decoded text, roles through G1a's resolver — plus the
explicit-role equality the §B.1 live-region cells need.
"""

from __future__ import annotations

from benchweave_ui_html.assertions import RenderedComponent
from benchweave_ui_html.items import parse_attribute_item

HTML = """
<section class="bw-reading" data-severity="advisory" aria-label="Supply rail">
  <p class="bw-reading__quality">steady &middot; 2 s</p>
  <button aria-label="Dismiss">&times;</button>
  <input type="range" min="0" max="100" step="5" aria-describedby="help">
</section>
"""


def _rendered() -> RenderedComponent:
    return RenderedComponent(HTML)


def test_root_element_is_the_first_start_tag() -> None:
    assert _rendered().root_tag == "section"
    assert RenderedComponent("<div><span></span></div>").root_tag == "div"


def test_attribute_items_match_over_any_element() -> None:
    rendered = _rendered()
    assert rendered.satisfies_attribute_item(parse_attribute_item("data-severity"))
    assert rendered.satisfies_attribute_item(parse_attribute_item("aria-label=Dismiss"))
    assert rendered.satisfies_attribute_item(parse_attribute_item("type=range"))
    assert rendered.satisfies_attribute_item(parse_attribute_item("min"))
    assert not rendered.satisfies_attribute_item(parse_attribute_item("min=1"))
    assert not rendered.satisfies_attribute_item(parse_attribute_item("aria-label=Open"))


def test_contains_item_matches_substring_of_any_value() -> None:
    rendered = _rendered()
    assert rendered.satisfies_attribute_item(parse_attribute_item("aria-label~=Dismiss"))
    assert not rendered.satisfies_attribute_item(parse_attribute_item("aria-label~=Open"))


def test_class_hook_is_token_containment_not_substring() -> None:
    rendered = _rendered()
    assert rendered.has_class_hook("bw-reading")
    assert rendered.has_class_hook("bw-reading__quality")
    # A substring of a token is NOT a carried hook.
    assert not rendered.has_class_hook("bw-read")


def test_required_text_runs_over_decoded_text_content() -> None:
    rendered = _rendered()
    assert "steady · 2 s" in rendered.text_content
    assert "steady" in rendered.text_content


def test_roles_resolve_through_the_g1a_resolver() -> None:
    rendered = _rendered()
    # input[type=range] carries the implicit slider role (G1a resolver).
    assert rendered.unsatisfied(roles=["slider"]) == []
    assert rendered.unsatisfied(roles=["button"]) == []  # the dismiss button
    messages = rendered.unsatisfied(roles=["img"])
    assert messages == ["role item `img` not found by the role resolver"]


def test_role_outside_the_pinned_set_fails_loud_not_false() -> None:
    messages = _rendered().unsatisfied(roles=["alert"])
    assert messages == ["role item `alert`: outside the resolver's pinned role set"]


def test_explicit_role_is_attribute_equality() -> None:
    assert RenderedComponent('<aside role="status"></aside>').explicit_role("status")
    assert not _rendered().explicit_role("status")


def test_unsatisfied_names_every_failing_item_class() -> None:
    messages = RenderedComponent("<div><p>text</p></div>").unsatisfied(
        root="section",
        attributes=[parse_attribute_item("data-severity=advisory")],
        roles=["region"],
        class_hooks=["bw-reading"],
        required_texts=["steady · 2 s"],
    )
    assert messages == [
        "root element: expected <section>, got <div>",
        "attribute item `data-severity=advisory` not satisfied",
        "role item `region` not found by the role resolver",
        "class-hook item `bw-reading` not carried by any element",
        "required-text item `steady · 2 s` absent from rendered text",
    ]
