"""HTML assertions over a rendered component string (G1b design record §1.1).

Stdlib ``html.parser`` only — no browser, no selector engine. The checks are
exactly the contract's item classes: root element (first start tag),
attribute items (present / ``=`` exact / ``~=`` contains, over any element in
the component), class-hook containment (a class token some element carries),
required-text substring (over decoded text content), and roles.

Roles go through G1a's ``roles.ImplicitRoleResolver`` (UR-05's G1a
authority). One deliberate exception lives here, not in the resolver: the
§B.1 Live-region cells name ``alert`` for critical/trip, which is outside the
resolver's pinned §E.1 role set and raises ``RoleUnresolvable`` BY DESIGN —
severity rows assert their live region as an explicit ``role`` attribute
(``explicit_role`` below), an equality over the rendered string, never an
implicit-role computation. The resolver's pinned set stays exactly as G1a
landed it.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser

from benchweave_ui_html.items import AttributeItem
from benchweave_ui_html.roles import ImplicitRoleResolver, RoleUnresolvable

_RESOLVER = ImplicitRoleResolver()


@dataclass(frozen=True)
class Element:
    """One start-tag sighting: tag name plus its attributes."""

    tag: str
    attrs: dict[str, str | None]

    @property
    def class_tokens(self) -> tuple[str, ...]:
        value = self.attrs.get("class")
        return tuple(value.split()) if value else ()

    def attribute_value(self, name: str) -> str | None:
        value = self.attrs.get(name)
        return None if value is None else value


class _Collector(HTMLParser):
    """Collects start tags (tag + attrs) and decoded text, in document order.

    Per-element text is tracked with an open-element stack (a text run is
    attributed to its innermost open element); void elements never open a
    frame. ``texts[i]`` aligns with ``elements[i]``."""

    _VOID = frozenset(
        {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
         "meta", "param", "source", "track", "wbr"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[Element] = []
        self.texts: list[list[str]] = []
        self.text_parts: list[str] = []
        self._open: list[int] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # First occurrence wins for a duplicated attribute (invalid HTML and
        # never emitted by our templates); a bare attribute parses as None.
        self.elements.append(Element(tag, dict(attrs)))
        self.texts.append([])
        if tag not in self._VOID:
            self._open.append(len(self.elements) - 1)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append(Element(tag, dict(attrs)))
        self.texts.append([])

    def handle_endtag(self, tag: str) -> None:
        if self._open:
            self._open.pop()

    def handle_data(self, data: str) -> None:
        self.text_parts.append(data)
        if self._open:
            self.texts[self._open[-1]].append(data)


class RenderedComponent:
    """A rendered HTML string parsed once, asserted many times."""

    def __init__(self, html: str) -> None:
        collector = _Collector()
        collector.feed(html)
        collector.close()
        self.html = html
        self.elements: list[Element] = collector.elements
        self.text_parts: list[str] = collector.text_parts
        self._element_texts = ["".join(parts) for parts in collector.texts]

    def texts_of_elements(
        self,
        *,
        class_hook: str | None = None,
        attribute: tuple[str, str] | None = None,
    ) -> list[str]:
        """The decoded text of every element carrying the given class hook
        and/or the given ``name=value`` attribute (either filter optional)."""
        out: list[str] = []
        for element, text in zip(self.elements, self._element_texts, strict=True):
            if class_hook is not None and class_hook not in element.class_tokens:
                continue
            if attribute is not None and element.attrs.get(attribute[0]) != attribute[1]:
                continue
            out.append(text)
        return out

    def texts_of_elements_with_attribute(self, name: str) -> list[str]:
        """The decoded text of every element carrying ``name`` (any value) —
        the §C.2 visible-label check (the label is element text in a
        ``data-bw-disabled-label`` element, never an aria-only attribute)."""
        return [
            text
            for element, text in zip(self.elements, self._element_texts, strict=True)
            if name in element.attrs
        ]

    @property
    def root_tag(self) -> str | None:
        return self.elements[0].tag if self.elements else None

    @property
    def text_content(self) -> str:
        """All decoded text, concatenated (entity-decoded by ``convert_charrefs``)."""
        return "".join(self.text_parts)

    def has_class_hook(self, hook: str) -> bool:
        return any(hook in element.class_tokens for element in self.elements)

    def satisfies_attribute_item(self, item: AttributeItem) -> bool:
        for element in self.elements:
            if item.name not in element.attrs:
                continue
            if item.match == "present":
                return True
            value = element.attrs[item.name]
            if value is None:
                continue
            if item.match == "equals" and value == item.value:
                return True
            if item.match == "contains" and item.value is not None and item.value in value:
                return True
        return False

    def explicit_role(self, role: str) -> bool:
        """True when some element carries ``role="<role>"`` exactly — the
        explicit-attribute check the §B.1 live-region cells need (``alert`` is
        outside the resolver's pinned set by design; see the module docstring)."""
        return any(element.attrs.get("role") == role for element in self.elements)

    def unsatisfied(
        self,
        *,
        root: str | None = None,
        attributes: list[AttributeItem] | None = None,
        roles: list[str] | None = None,
        class_hooks: list[str] | None = None,
        required_texts: list[str] | None = None,
    ) -> list[str]:
        """Run the contract's item classes over the rendered string; each
        unsatisfied item is returned as a message naming the item (the
        mutation controls rely on failures naming their item)."""
        messages: list[str] = []
        if root is not None and self.root_tag != root:
            messages.append(f"root element: expected <{root}>, got <{self.root_tag}>")
        for item in attributes or []:
            if not self.satisfies_attribute_item(item):
                messages.append(f"attribute item `{item.describe()}` not satisfied")
        for role in roles or []:
            try:
                if not _RESOLVER.has_role(self.html, role):
                    messages.append(f"role item `{role}` not found by the role resolver")
            except RoleUnresolvable:
                messages.append(
                    f"role item `{role}`: outside the resolver's pinned role set"
                )
        for hook in class_hooks or []:
            if not self.has_class_hook(hook):
                messages.append(f"class-hook item `{hook}` not carried by any element")
        for text in required_texts or []:
            if text not in self.text_content:
                messages.append(f"required-text item `{text}` absent from rendered text")
        return messages
