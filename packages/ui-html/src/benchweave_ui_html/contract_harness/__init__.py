"""The pytest contract harness (pytest11 entry point).

This subpackage MAY import pytest — it is loaded only when pytest is the
running process. Nothing in the runtime namespace above may import it (the
UR-11 boundary pinned by tests/ui_html/test_package.py).
"""
