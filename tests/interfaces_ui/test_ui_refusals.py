"""The §C.3 refusal table as the UI's carried data (G2b, design §7-F's
table half).

Every refusal the gateway renders — session pages, seam failures, the
no-response row — renders ui-contract.md §C.3's OWN row: severity,
what-happened, sent status, operator action. The rows are carried data
pinned to the contract table HERE (G2a pinned the one unauthenticated
row; G2b generalises to the full 15), so wording drift reds in the suite
instead of in a browser. GW-11/GW-14: no code is rewritten softer, and
``not_found`` wording never implies non-existence.

Induced-not-emitted honesty rule (design §7-F): arms in this suite that
monkeypatch the seam for a code the read wire cannot produce naturally
say so in the test body; the no-response row has NO seam emitter at all
(it is the transport-absence row — §C.3's own 15th), so it is rendered
from the table and asserted at the renderer, not induced.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient
from ui_gateway_support import live_session, module_gateway

from benchweave.interfaces import errors
from benchweave.interfaces.ui_refusals import REFUSAL_ROWS, render_no_response

CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "internal" / "ui-contract.md"

#: §C.3's own stated row count (the harness manifest pins the same set;
#: this suite pins the gateway's carried copy against the table itself).
_ROW = re.compile(
    r"^\| `(?P<code>[\w-]+)` \| `(?P<severity>\w+)` \| (?P<what>.+?) "
    r"\| `(?P<sent>\w+)` \| (?P<action>.+?) \|$",
    re.MULTILINE,
)


def _contract_rows() -> dict[str, dict[str, str]]:
    """Parse §C.3's table from the normative doc (fail-closed: a missing
    heading or an unparsable table is a pin failure, not a skip)."""
    text = CONTRACT.read_text(encoding="utf-8")
    section = text.split("### §C.3 Refusal mapping", 1)
    assert len(section) == 2, "the §C.3 heading is missing from ui-contract.md"
    rows = {
        match["code"]: match.groupdict()
        for match in _ROW.finditer(section[1].split("## §D", 1)[0])
    }
    assert len(rows) == 15, f"§C.3 must parse 15 rows, parsed {len(rows)}"
    return rows


def test_every_contract_row_is_carried_verbatim() -> None:
    """The carried table IS §C.3 — 15 rows, each field character for
    character (severity, what-happened, sent status, operator action)."""
    rows = _contract_rows()
    assert set(REFUSAL_ROWS) == set(rows), (
        f"carried codes {sorted(set(rows) ^ set(REFUSAL_ROWS))} differ from §C.3"
    )
    for code, row in rows.items():
        carried = REFUSAL_ROWS[code]
        assert carried.code == code
        assert carried.severity == row["severity"], code
        assert carried.what_happened == row["what"], code
        assert carried.sent_status == row["sent"], code
        assert carried.operator_action == row["action"], code


def test_unauthenticated_refusal_alias_is_the_carried_row() -> None:
    """G2a's constant is now the table's row — one source, not two."""
    from benchweave.interfaces.ui import UNAUTHENTICATED_REFUSAL

    assert UNAUTHENTICATED_REFUSAL is REFUSAL_ROWS["unauthenticated"]


def test_not_found_wording_never_implies_non_existence() -> None:
    """GW-14: the not_found row says unavailable to this caller — the
    wording never asserts the resource does not exist."""
    row = REFUSAL_ROWS["not_found"]
    assert "unavailable to this caller" in row.what_happened
    assert "not exist" not in row.what_happened


def test_no_response_row_is_the_unknown_sent_status() -> None:
    """A06: no-response is severity critical with sent status UNKNOWN —
    the row that never launders an ambiguous outcome into a refusal."""
    row = REFUSAL_ROWS["no-response"]
    assert row.severity == "critical"
    assert row.sent_status == "UNKNOWN"


def test_no_response_renders_the_reconcile_action() -> None:
    """GW-12's presentation half: the no-response render carries the
    §C.3 row AND a reconcile action naming run_find's view for the same
    request id (the mutating-form half is G3's, per the design's D2)."""
    html = render_no_response("req-77")
    assert 'data-bw-refusal-code="no-response"' in html
    assert 'data-bw-sent-status="UNKNOWN"' in html
    assert "/ui/requests/req-77" in html
    assert "reconcile" in html.lower()


@pytest.fixture(scope="module")
def gateway(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    app = module_gateway("ui-refusals", tmp_path_factory.mktemp("ui-refusals"))
    return SimpleNamespace(app=app, session=live_session(app))


def test_seam_failure_renders_the_c3_row_with_correlation_id(
    gateway: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A seam failure on a /ui route renders its §C.3 row beside the
    message and correlation id. ``rate_limited`` is INDUCED (monkeypatched
    seam refusal) — the read wire cannot produce it naturally in this
    fixture; the naturally-inducible codes are covered in the read-view
    and isolation suites."""
    operations = gateway.app.state.ui_operations
    monkeypatch.setattr(
        operations,
        "gateway_info",
        lambda identity: (_ for _ in ()).throw(
            errors.OperationFailure(
                errors.failure("rate_limited", "induced for the row-render pin")
            )
        ),
    )
    with TestClient(gateway.app, base_url="http://testserver:8125") as client:
        response = client.get(
            "/ui/", cookies={"bw_session": gateway.session.session_id}
        )
    assert response.status_code == 429
    page = response.text
    assert 'data-bw-refusal-code="rate_limited"' in page
    assert 'data-bw-sent-status="NO"' in page
    assert "Wait the advertised interval and submit again." in page
    assert "induced for the row-render pin" in page
    assert re.search(r"[0-9a-f]{16}", page), "the correlation id renders"

