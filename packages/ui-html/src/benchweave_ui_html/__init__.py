"""BenchWeave renderer-neutral HTML renderer namespace (package ``benchweave-ui-html``).

UR-11 boundary: this namespace and its submodules depend on Jinja2 and
MarkupSafe only. The pytest harness lives in
``benchweave_ui_html.contract_harness`` (loaded via the pytest11 entry point
when pytest is the running process) — nothing in this runtime import path may
import it, and tests/ui_html/ pins that by walking the import graph.
"""

from benchweave_ui_html.grammar import Contract, PinDefect, Row, TableSpec, parse_contract
from benchweave_ui_html.manifest import MANIFEST, TOTAL_ROWS, TOTAL_TABLES, ManifestTable

__version__ = "0.2.1"

__all__ = [
    "Contract",
    "MANIFEST",
    "ManifestTable",
    "PinDefect",
    "Row",
    "TableSpec",
    "TOTAL_ROWS",
    "TOTAL_TABLES",
    "parse_contract",
]
