"""The plugins teaser panel contract (issue #224 slice 2 pivot, design §3.4).

The registry repository generates and serves the catalogue itself
(deploy-time generation, design §3.1); the gateway website keeps a static
teaser — timeless prose plus ONE outbound link — and carries zero
catalogue-derived bytes (no counts, no names, no versions: a count is a
mini-mirror with its own staleness clock and no gate). This suite
byte-pins the ENTIRE teaser section and the home honesty paragraph (the
strongest guard: any change to those bytes reddens, so a planted count,
name, or link cannot pass), string-pins the teaser prose with the
honesty-sentence discipline, pins
the single outbound link, pins the no-registry-derived-bytes property over
the whole ``website/`` tree (invariants CON-13, pivot amendment), and keeps
the home panel's honesty sentence (CR-23) pinned with its scan scope on
the panel the sentence actually lives on — a pin scanning the wrong
section passes while the claim drifts (the lane finding this closes).

It also pins the nav/DOM agreement (``PANEL_INDEX`` in ``site.js`` vs the
nav button order) so the teaser panel stays reachable: ``openFromHash``
indexes buttons by position, so a disagreeing order silently deep-links to
the wrong panel.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "website" / "index.html"
SITE_JS = ROOT / "website" / "assets" / "site.js"

SEMVER_RE = re.compile(r"\d+\.\d+\.\d+")

#: The catalogue's home: the registry repository's GitHub Pages URL (project
#: pages of madeinoz67/benchweave-registry; no custom domain is declared —
#: the domain cutover is the styleguide's gated future event, and the
#: registry Pages URL in plain language is not).
CATALOGUE_URL = "https://madeinoz67.github.io/benchweave-registry/"

# The teaser prose, string-pinned (design §5 B3′: the teaser carries zero
# catalogue-derived data and its text is string-pinned).
TEASER_NO_COPY = (
    "The catalogue is generated from that repository's records and served "
    "from its own site; this page carries no copy of it"
)
TEASER_LOCAL_ADMISSION = "Installation is local admission: publication never authorizes control."
TEASER_YANK = (
    "a yanked or revoked release drops out at the next regeneration — what "
    "is absent there is absent everywhere"
)

# CR-23's home-panel honesty sentence (design §2.6, substance unchanged by
# the pivot): states exactly what exists — a git-native registry repository
# of record with published, signed releases, now with its own catalogue
# site; no hosted front end; installation stays local admission.
HONESTY_SENTENCE = (
    "a catalogue of published, signed releases now exists as a git-native "
    "registry repository of record with its own catalogue site"
)
HONESTY_NO_SERVICE = "no hosted registry front end and no device-install command exist"

# The whole-section byte pins (fold G2, lane B F1): the exact bytes of the
# teaser section and of the home honesty paragraph, generated from the file
# bytes — never hand-typed. A substring pin cannot see a planted count, name,
# or link appended around the pinned prose (proven: "Currently 3 published
# releases." passed every prior guard); byte equality makes ANY change to
# these bytes redden, so updating the pin is part of any intentional edit.
TEASER_SECTION_BYTES = (
    "<section class=\"panel\" id=\"panel-plugins\">\n"
    "    <div class=\"page-head\">\n"
    "      <h1>Plugins</h1>\n"
    "      <p>Plugin releases are published and signed in a git-native registry repository "
    "of record — not a hosted front end. The catalogue is generated from that repository's "
    "records and served from its own site; this page carries no copy of it, so what you "
    "reach is always the published state. Installation is local admission: publication never "
    "authorizes control.</p>\n"
    "    </div>\n"
    "    <div class=\"ai-callout\">\n"
    "      <div>\n"
    "        <h2>The plugin catalogue</h2>\n"
    "        <p>Every published release with its version, digest, compatibility and "
    "advisories — searchable, kind-tagged, and stamped with the commit it was generated "
    "from.</p>\n"
    "      </div>\n"
    "      <a class=\"btn btn-secondary\" href=\"https://madeinoz67.github.io/benchweave-regi"
    "stry/\" target=\"_blank\" rel=\"noopener\">Browse the catalogue →</a>\n"
    "    </div>\n"
    "    <p class=\"note\">What the catalogue offers is generated from published releases "
    "only: a yanked or revoked release drops out at the next regeneration — what is absent "
    "there is absent everywhere.</p>\n"
    "  "
)# CR-23's honesty paragraph on the home panel (the <p> whose bytes carry
# HONESTY_SENTENCE and HONESTY_NO_SERVICE), pinned the same way: the words of
# an honesty claim are reviewable state, and drift in either direction —
# over-claiming or under-claiming around the pinned sentences — is a visible
# same-commit diff.
HONESTY_PARAGRAPH_BYTES = (
    "<p><strong>Next.</strong> Gateway and devices talking through the registry: the gateway "
    "side of the registry contract is done (signed catalogue, admission with a "
    "content-addressed cache, activation, an unsigned dev loop), and a catalogue of "
    "published, signed releases now exists as a git-native registry repository of record "
    "with its own catalogue site — but no hosted registry front end and no device-install "
    "command exist, so installation stays local admission. The OTDP bridge's remaining scope "
    "is profile scheduling on a native async host. The gateway's first operator web UI will "
    "be server-rendered, with the React reference renderer retired in a gated cutover. "
    "Hardware qualification and unattended bench operation remain separate, commissioned "
    "work.</p>"
)
def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def _section(html: str, panel_id: str) -> str:
    """One panel's bytes, from its opening ``<section>`` to its ``</section>``.

    Panels are flat siblings on this page (no nested sections), so the next
    closing tag after the opener is the panel's own. Fails loudly when the
    panel is missing — a scanner over an absent section is blind, not green.
    """
    opener = re.search(rf'<section[^>]*\bid="panel-{panel_id}"[^>]*>', html)
    assert opener is not None, f"panel-{panel_id} section missing from index.html"
    end = html.index("</section>", opener.end())
    return html[opener.start() : end]


def test_teaser_prose_is_string_pinned() -> None:
    """§3.4: timeless prose, pinned verbatim so a drift back toward a
    catalogue-shaped claim (or a stale-mirror story) reddens."""
    teaser = _section(_html(), "plugins")
    for pin in (TEASER_NO_COPY, TEASER_LOCAL_ADMISSION, TEASER_YANK):
        assert pin in teaser, f"teaser prose drifted: {pin!r}"


def test_teaser_section_bytes_are_pinned() -> None:
    """Fold G2 (lane B F1): the ENTIRE teaser section is byte-pinned. The
    substring pins and shape bans below cannot see a count, name, or link
    appended around the pinned prose (proven: "Currently 3 published
    releases." passed every prior guard 7/7); byte equality makes any such
    plant redden. What this does not catch: nothing about the catalogue
    itself — the teaser's honesty is that it carries no catalogue data at
    all, and these bytes are the proof."""
    assert _section(_html(), "plugins") == TEASER_SECTION_BYTES, (
        "panel-plugins bytes drifted — if the change is intentional, update "
        "TEASER_SECTION_BYTES in the same commit"
    )


def test_teaser_link_is_the_one_outbound_link() -> None:
    """§3.4: exactly ONE outbound link, to the registry catalogue's Pages
    URL, noopener — dead-link degradation is honest (a link either resolves
    or it doesn't), so there is nothing else to gate."""
    teaser = _section(_html(), "plugins")
    outbound = re.findall(r'href="(https?://[^"]+)"', teaser)
    assert outbound == [CATALOGUE_URL], (
        f"the teaser must carry exactly one outbound link: {outbound}"
    )
    assert 'rel="noopener"' in teaser, "the outbound link opens a new tab: it carries rel=noopener"


def test_teaser_carries_zero_catalogue_derived_data() -> None:
    """§3.4: no counts, no names, no versions, no inline rows — mechanized
    as the absence of every catalogue-shaped hook (row slots, filters,
    template cards, form controls) and of any three-component version
    literal inside the panel."""
    teaser = _section(_html(), "plugins")
    for banned in (
        "data-bw-",
        "bw-filter",
        "catalogue-",
        "<template",
        "<select",
        "<input",
        "spec-card",
        "plugins-index",
    ):
        assert banned not in teaser, f"catalogue-derived shape in the teaser: {banned!r}"
    literals = SEMVER_RE.findall(teaser)
    assert not literals, f"version literal(s) in the teaser: {literals}"


def test_website_carries_no_registry_derived_bytes() -> None:
    """CON-13's pivot amendment, mechanized: no mirror file exists under
    ``website/``, nothing references one, and the page loads no catalogue
    client script. What this does not catch: a NEW file name not containing
    "plugins-index" — the class-11 literal scan (T2) and the teaser shape
    pin above carry that side."""
    website = ROOT / "website"
    files = sorted(p for p in website.rglob("*") if p.is_file())
    assert files, "website/ tree missing — scanner blind"
    for path in files:
        rel = path.relative_to(website).as_posix()
        assert "plugins-index" not in rel, f"registry-derived file: {rel}"
        assert "plugins-index" not in path.read_text(encoding="utf-8"), (
            f"registry-index reference in website file: {rel}"
        )
    assert "assets/plugins.js" not in _html(), "index.html still loads a catalogue client script"


def test_home_honesty_sentence_is_string_pinned() -> None:
    """CR-23 (§2.6, substance unchanged): the sentence is pinned verbatim
    ON THE PANEL IT LIVES ON (home) — the scan scope is the claim's page,
    not some other section."""
    home = _section(_html(), "home")
    assert HONESTY_SENTENCE in home, "the honesty sentence drifted (home panel)"
    assert HONESTY_NO_SERVICE in home, "the honesty sentence's no-service clause drifted"


def test_home_honesty_paragraph_bytes_are_pinned() -> None:
    """Fold G2's home arm: the whole paragraph carrying CR-23's honesty
    sentence is byte-pinned, not just the sentence — a claim appended or
    reworded AROUND the pinned sentences (the same plant class the teaser
    arm closes) reddens here too."""
    match = re.search(r"<p><strong>Next\.</strong>.*?</p>", _html())
    assert match is not None, "honesty paragraph (the Next. <p>) missing — scanner blind"
    assert match.group(0) == HONESTY_PARAGRAPH_BYTES, (
        "home honesty paragraph bytes drifted — if the change is intentional, "
        "update HONESTY_PARAGRAPH_BYTES in the same commit"
    )


def test_no_registry_service_language_where_claims_live() -> None:
    """The words "registry service" appear nowhere on the two panels the
    catalogue claims live on (teaser + home): the phrase is the stale
    framing — it implies a service-shaped thing that does not exist."""
    html = _html()
    for panel_id in ("plugins", "home"):
        section = _section(html, panel_id)
        assert "registry service" not in section.lower(), (
            f"panel-{panel_id} claims a registry service"
        )


def test_panel_index_agrees_with_the_dom() -> None:
    """The nav keeps working after the pivot: ``PANEL_INDEX`` positions
    equal the DOM button order, and every key names an existing panel —
    ``openFromHash`` indexes buttons by position, so a disagreeing order
    deep-links to the wrong panel with every gate green."""
    html = _html()
    nav = html[html.index('<nav class="panels"') : html.index("</nav>")]
    dom_order = re.findall(r"showPanel\('([a-z]+)'", nav)
    assert dom_order, "no nav buttons found — scanner blind"

    js = SITE_JS.read_text(encoding="utf-8")
    mapping = re.search(r"var PANEL_INDEX = \{ ([^}]*) \};", js)
    assert mapping is not None, "PANEL_INDEX not found in site.js"
    positions = {
        name: int(value)
        for name, value in re.findall(r"([a-z]+): (\d+)", mapping.group(1))
    }
    assert positions, "PANEL_INDEX parsed empty — scanner blind"
    indexed_order = [name for name, _ in sorted(positions.items(), key=lambda kv: kv[1])]

    assert dom_order == indexed_order, (
        f"nav/DOM disagreement: buttons {dom_order} vs PANEL_INDEX {indexed_order}"
    )
    sections = set(re.findall(r'<section[^>]*\bid="panel-([a-z]+)"', html))
    assert set(dom_order) == sections, (
        f"nav names panels the page lacks (or vice versa): {set(dom_order) ^ sections}"
    )
