"""Package boundaries are tested without installing BenchWeave core."""

import importlib
import importlib.util
import json
from importlib.metadata import requires, version
from importlib.resources import files

from benchweave_fnirsi_dps150.descriptor import build_descriptor


def test_core_is_not_a_development_or_runtime_dependency() -> None:
    assert importlib.util.find_spec("benchweave") is None
    assert not requires("benchweave-fnirsi-dps150")
    assert version("benchweave-fnirsi-dps150") == "0.1.0"


def test_descriptor_factory_and_packaged_vectors() -> None:
    package = files("benchweave_fnirsi_dps150")
    descriptor = json.loads(package.joinpath("descriptor.json").read_text())
    assert descriptor == build_descriptor()
    module, factory_name = descriptor["integration"]["adapter"]["entry_point"].split(":")
    factory = getattr(importlib.import_module(module), factory_name)
    assert factory() is not factory()
    for vector in descriptor["provenance"]["test_vectors"]:
        assert package.joinpath(vector["path"]).is_file()
