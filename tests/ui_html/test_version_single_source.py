"""The version single-source pin (the release-and-pin doc's rule).

``packages/ui-html/pyproject.toml`` ``[project].version`` is the only
version declaration — but ``__version__`` exists (added with the
package), so this pins it to ``importlib.metadata`` (the installed
distribution's metadata, which the wheel-proof CI separately proves
equals the pyproject). The attribute had drifted to 0.1.0 while the
pyproject moved to 0.2.x (fold-refute Finding 2); this arm keeps the
two from diverging silently again.
"""

from __future__ import annotations

import importlib.metadata

import benchweave_ui_html


def test_dunder_version_equals_the_distribution_metadata() -> None:
    assert benchweave_ui_html.__version__ == importlib.metadata.version(
        "benchweave-ui-html"
    )
