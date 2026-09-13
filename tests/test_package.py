from benchweave import __version__


def test_version_is_available() -> None:
    assert __version__


# The version-print entrypoint test moved to tests/cli/test_commands.py
# (test_version_flag_prints_package_version): `main` now dispatches to the
# Click tree, so the version surfaces via `benchweave --version`.
