"""The Jinja environment (UR-01): strict, escaped, package-loaded.

One module-level factory builds the single environment every partial renders
through: ``StrictUndefined`` (a partial called with missing data reds loudly
at render time — never a silent hole in the output), ``autoescape=True``
(every interpolated value is escaped; templates interpolate plain data
only), ``trim_blocks``/``lstrip_blocks`` (block tags leave no stray
whitespace in the emitted HTML), and a ``PackageLoader`` over the package's
``templates/`` directory so the same loader serves source checkouts and
wheel installs (the packaging guard pins the directory's contents).
"""

from __future__ import annotations

from jinja2 import Environment, PackageLoader, StrictUndefined

TEMPLATE_PACKAGE = "benchweave_ui_html"
TEMPLATE_DIRECTORY = "templates"


def build_environment() -> Environment:
    """Build the partials' rendering environment (UR-01, G1b record §1.1)."""
    return Environment(
        loader=PackageLoader(TEMPLATE_PACKAGE, TEMPLATE_DIRECTORY),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


#: The module-level environment every partial renders through.
ENV = build_environment()
