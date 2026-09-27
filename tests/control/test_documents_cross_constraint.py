"""The pairwise cross-constraint admission check (issue #217).

Design §3.3: each device's OTDP pin must sit inside the BENCH's execution
version's declared range, read from ``standards/cross-constraints.json`` —
device A pinned 0.2.0 and device B pinned 0.2.2 share a bench; a device
outside the range refuses with ``cross_constraint_violation:`` naming both
versions and the row's evidence. The row set is single-sourced with the
resolver's resolve-time check (VR-31) — the same loader, the same file.

The seed corpus's one row (execution 0.2.0 requires otdp >=0.2.0,<0.3.0 and
adapter_api 1.1, citing PR #201) means the DEFAULT bench refuses pre-0.2.0
devices outright — an operator acknowledgement authorises the non-conforming
LOAD (the otdp window), never the execution runtime interface — and the
execution/0.1.0 composition (no row: the honest negative in the file's
note) is where the acked class is reachable at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_documents_perpin import CORPUS, _admit, _controller_document, _psu_document

from benchweave.control.documents import AdmissionRejected


def test_in_range_devices_share_the_bench(tmp_path: Path) -> None:
    """The design's own example: 0.2.0 and 0.2.2 sit inside the execution
    0.2.0 row's declared otdp range — both admit on one bench, the pairwise
    check refusing nothing."""
    psu = _psu_document()
    psu["otdp_version"] = "0.2.0"
    docs = _admit(tmp_path, {"psu": psu})
    assert set(docs.pins) == {"psu", "controller"}


def test_out_of_range_device_refuses_with_both_versions_and_evidence(
    tmp_path: Path,
) -> None:
    """A 0.1.2 device on the execution 0.2.0 bench — ACKED (so the
    non-conforming load itself is authorised) — still refuses: the row's
    declared range is a compatibility fact, and the refusal names the
    bench's execution version, the device's pin, and the row's evidence."""
    psu = _psu_document()
    psu["otdp_version"] = "0.1.2"
    with pytest.raises(AdmissionRejected) as raised:
        _admit(
            tmp_path,
            {"psu": psu},
            operator_acknowledgements={"psu": "0.1.2"},
        )
    message = str(raised.value)
    assert message.startswith("cross_constraint_violation:"), message
    assert "execution@0.2.0" in message, message
    assert "otdp" in message and "0.1.2" in message, message
    assert "PR #201" in message, message  # the row's evidence, named


def test_the_row_is_enforced_on_every_device_pairwise(tmp_path: Path) -> None:
    """Pairwise means per device, not per bench majority: the controller's
    in-range 0.2.2 pin does not carry the psu's out-of-range one."""
    psu = _psu_document()
    psu["otdp_version"] = "0.1.1"
    controller = _controller_document()
    controller["otdp_version"] = "0.2.2"
    with pytest.raises(AdmissionRejected, match=r"^cross_constraint_violation:"):
        _admit(
            tmp_path,
            {"psu": psu, "controller": controller},
            operator_acknowledgements={"psu": "0.1.1"},
        )


def test_a_rowless_execution_version_constrains_nothing(tmp_path: Path) -> None:
    """The honest negative: execution 0.1.0 carries no row, so the acked
    non-conforming device admits there — the cross-constraint lane refuses
    nothing it has no evidence for."""
    psu = _psu_document()
    psu["otdp_version"] = "0.1.2"
    docs = _admit(
        tmp_path,
        {"psu": psu},
        execution="0.1.0",
        operator_acknowledgements={"psu": "0.1.2"},
    )
    assert docs.pins["psu"].conformance == "non-conforming"


def test_the_adapter_api_leg_rides_the_same_row(tmp_path: Path) -> None:
    """The row's adapter_api requirement is enforced from the PIN's own
    schema — the pinned descriptor schema's ``$defs.adapter`` api_version
    const (G-2's authority) must equal the row's exact value. The seed
    corpus's served pins all declare 1.1 (the row's own value), so the
    in-range bench above already proves the satisfied side; this arm pins
    the derivation source by asserting the const the check reads."""
    import json

    schema = json.loads(
        (CORPUS / "otdp" / "0.2.2" / "otdp-device-descriptor.schema.json").read_text()
    )
    const = schema["$defs"]["adapter"]["properties"]["api_version"]["const"]
    assert const == "1.1"


def test_the_adapter_leg_bites_on_a_planted_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F1 (#217 review fold): the adapter_api leg is enforced by code no
    COMMITTED byte can fail — every retained otdp schema's
    ``$defs.adapter`` api_version const is 1.1, equal to the committed
    row's ``requires.adapter_api`` — so the leg needs a planted
    disagreement to be falsifiable at all (the design's own C2
    planted-disagreement pattern). A planted row requiring adapter_api 1.2
    against a served 0.2.2 device (whose pinned schema declares 1.1, its
    otdp requirement satisfied so ONLY this leg can fire) refuses with
    ``cross_constraint_violation:`` naming the pinned version, both API
    values, and the row's evidence. The corpus copy is byte-identical
    except the planted row; the resolver is pointed at it the way the
    census teeth arm points its sabotage."""
    import shutil

    import benchweave.control.documents as documents_module

    corpus = tmp_path / "standards"
    shutil.copytree(CORPUS, corpus)
    planted = json.loads((corpus / "cross-constraints.json").read_text())
    planted["rows"][0]["requires"]["adapter_api"] = "1.2"
    (corpus / "cross-constraints.json").write_text(json.dumps(planted))
    monkeypatch.setattr(documents_module, "_otdp_corpus", lambda: corpus)

    psu = _psu_document()  # served 0.2.2 pin; the otdp leg stays satisfied
    with pytest.raises(AdmissionRejected) as raised:
        _admit(tmp_path, {"psu": psu})
    message = str(raised.value)
    assert message.startswith("cross_constraint_violation:"), message
    assert "adapter API is 1.1" in message, message
    assert "requires adapter_api 1.2" in message, message
    assert "otdp@0.2.2" in message and "execution@0.2.0" in message, message
    assert "PR #201" in message, message  # the row's evidence, named
