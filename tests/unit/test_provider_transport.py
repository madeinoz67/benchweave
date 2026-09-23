"""The provider grant: the grammar guard and the construction gate.

Metric C of the increment-3 design record — five arms on the construction
seam (``build_capture_services`` with ``providers=``), each pinned to its
own mechanism, plus the guard-level grammar arms. Fixtures use invented
names where the bytes do not matter; the corpus ``reference-*`` pair is
reused where they do (the standing grammar control).

Arm/mechanism map (the design's five arms over the gate's three checks):

1. full grant — provider + ``scoped_transport`` + admitted + resolved key
   → the guard is bound (its transfer refuses with the LANE refusal, not
   the generic no-transport one);
2. no ``scoped_transport`` → refusal names the permission (the permission
   check);
3. contract not admitted → refusal names the triple (the admission check);
4. ``connection_key`` bound to a DIFFERENT admitted contract → refusal
   names the key (the resolution check — arms 3 and 4 fail
   independently);
5. empty registry → refused (the admission check's degenerate state: no
   admitted triple exists to match — the design's five arms ride three
   checks by construction).

The guard validates the transaction PAYLOAD (the transaction minus the
``kind`` selector) against the kind's ``request_schema``: the corpus's own
reference grammar types the fields with ``additionalProperties: false``
and no ``kind`` property, so the selector is not payload — whole-dict
validation would refuse every corpus-grammar transaction.

The module under test is new: names resolve at call time so the module
COLLECTS against the parent commit (the new-module RED convention).
"""

from __future__ import annotations

import hashlib
import importlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from benchweave.content import capture_services as services_module
from benchweave.content.store import ContentStore
from benchweave.control.provider_settings import load_transport_settings
from benchweave.host.services import QuotaLimits
from benchweave.state.store import Store

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "standards" / "otdp" / "0.2.2" / "examples"
NOW = "2026-09-22T00:00:00Z"
CONTEXT_KEY = "run-host-1/device-2/session-3"


def _module() -> Any:
    return importlib.import_module("benchweave.content.provider_transport")


def _registry(tmp_path: Path, *, crossbound: bool = False) -> Any:
    """A validated registry over the corpus pair (optionally binding the
    descriptor's connection key to a second, different provider)."""
    package = tmp_path / "settings-package"
    package.mkdir(exist_ok=True)
    contract_raw = (EXAMPLES / "reference-provider.json").read_bytes()
    (package / "reference-provider.json").write_bytes(contract_raw)
    contract = json.loads(contract_raw)
    settings: dict[str, Any] = {
        "config_version": "1",
        "admitted": [
            {
                "id": contract["id"],
                "version": contract["version"],
                "sha256": hashlib.sha256(contract_raw).hexdigest(),
                "feature_id": contract["feature_id"],
                "document": "reference-provider.json",
            }
        ],
        "connections": [
            {"connection_key": "power_meter", "provider_id": contract["id"]}
        ],
    }
    if crossbound:
        other = json.loads(json.dumps(contract))
        other["id"] = "urn:otdp:transport-provider:meter-probe:1.0.0"
        other["feature_id"] = "otdp.transport.meter-probe/1.0.0"
        other["description"] = "Synthetic second provider (cross-bound arm)"
        other_raw = (json.dumps(other, indent=2) + "\n").encode()
        (package / "meter-probe.json").write_bytes(other_raw)
        settings["admitted"].append(
            {
                "id": other["id"],
                "version": other["version"],
                "sha256": hashlib.sha256(other_raw).hexdigest(),
                "feature_id": other["feature_id"],
                "document": "meter-probe.json",
            }
        )
        settings["connections"] = [
            {"connection_key": "power_meter", "provider_id": other["id"]}
        ]
    path = package / "transport-settings.json"
    path.write_text(json.dumps(settings, indent=2) + "\n")
    return load_transport_settings(path)


def _provider_descriptor(permissions: list[str]) -> dict[str, Any]:
    """The corpus reference-hid-meter descriptor with a permission override."""
    descriptor: dict[str, Any] = json.loads(
        (EXAMPLES / "reference-hid-meter.json").read_text()
    )
    descriptor["integration"]["adapter"]["permissions"] = permissions
    return descriptor


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = Store.open(tmp_path / "grant.db")
    yield opened
    opened.close()


def _factory(
    store: Store, tmp_path: Path, descriptor: dict[str, Any], **overrides: Any
) -> Any:
    content = ContentStore(store)
    payload = json.dumps(descriptor, sort_keys=True).encode()
    digest = hashlib.sha256(payload).hexdigest()
    content.put_document(payload, digest, descriptor, "otdp-descriptor", NOW)
    from benchweave.content.capture_store import CaptureStagingStore

    writer = CaptureStagingStore(store, max_capture_bytes=1000, max_dataset_bytes=2000)
    settings: dict[str, Any] = {
        "descriptor_digest": digest,
        "content": content,
        "writer": writer,
        "clock": lambda: 1.0,
        "wall": lambda: NOW,
        "quota": QuotaLimits(
            max_dataset_bytes=2000, max_evidence_entries=50, max_event_batch=10
        ),
        "context_key": CONTEXT_KEY,
    }
    settings.update(overrides)
    return services_module.build_capture_services(**settings)


# --- arm 1: the full grant ------------------------------------------------

OUTPUT_REPORT = {"kind": "hid_output_report", "report_id": 0, "data": "aGk="}


def test_full_grant_binds_the_guard(store: Store, tmp_path: Path) -> None:
    bundle, controller = _factory(
        store,
        tmp_path,
        _provider_descriptor(["scoped_transport", "artifact_writer"]),
        providers=_registry(tmp_path),
    )
    assert controller is not None  # artifact_writer stands
    import asyncio

    # The guard is bound: an IN-GRAMMAR transaction refuses with the LANE
    # refusal (no runtime injected — provider implementations are a
    # separate act), not the generic no-transport one.
    with pytest.raises(NotImplementedError, match="provider runtime.*#147"):
        asyncio.run(bundle.transfer(dict(OUTPUT_REPORT), context=None))
    # close_transport is a no-op: nothing was opened.
    asyncio.run(bundle.close_transport(context=None))


def test_out_of_grammar_kind_refused_before_any_runtime(store: Store) -> None:
    mod = _module()
    contract = json.loads((EXAMPLES / "reference-provider.json").read_text())
    guard = mod.ProviderTransport(contract=contract)
    import asyncio

    for transaction in (
        {"kind": "stream_send", "data": "aGk="},  # generic kind: never shadowed
        {"kind": "watt_link_query", "voltage": 1.0},  # unknown provider kind
        {"report_id": 0, "data": "aGk="},  # kindless
        ["hid_output_report"],  # not an object
    ):
        with pytest.raises(ValueError, match="provider_transaction:"):
            asyncio.run(guard.transfer(transaction, context=None))


def test_schema_violating_request_refused(store: Store) -> None:
    mod = _module()
    contract = json.loads((EXAMPLES / "reference-provider.json").read_text())
    guard = mod.ProviderTransport(contract=contract, runtime=_FakeRuntime([]))
    import asyncio

    bad = {"kind": "hid_output_report", "report_id": 0, "data": 12}  # data not base64 text
    with pytest.raises(ValueError, match="provider_transaction:.*data"):
        asyncio.run(guard.transfer(bad, context=None))


def test_well_formed_transaction_reaches_the_runtime_and_back(store: Store) -> None:
    mod = _module()
    contract = json.loads((EXAMPLES / "reference-provider.json").read_text())
    seen: list[dict[str, Any]] = []
    # hid_output_report's result schema is the EMPTY object (transport
    # acceptance only, like stream_send) — the standing grammar control.
    runtime = _FakeRuntime(seen, result={})
    guard = mod.ProviderTransport(contract=contract, runtime=runtime)
    import asyncio

    result = asyncio.run(guard.transfer(dict(OUTPUT_REPORT), context=None))
    assert result == {}
    assert seen == [OUTPUT_REPORT]  # byte-exact passthrough of the transaction
    # close_transport delegates to the runtime when one is bound.
    asyncio.run(guard.close_transport(context=None))
    assert runtime.closed


def test_malformed_runtime_result_refused(store: Store) -> None:
    """A misbehaving host-side runtime cannot launder a malformed result
    into the adapter."""
    mod = _module()
    contract = json.loads((EXAMPLES / "reference-provider.json").read_text())
    runtime = _FakeRuntime([], result={"report_id": 0})  # missing required data
    guard = mod.ProviderTransport(contract=contract, runtime=runtime)
    import asyncio

    with pytest.raises(ValueError, match="provider_transaction:.*result"):
        asyncio.run(guard.transfer(dict(OUTPUT_REPORT), context=None))


class _FakeRuntime:
    """The injected host-side runtime double: records transactions."""

    def __init__(
        self, seen: list[dict[str, Any]], *, result: dict[str, Any] | None = None
    ) -> None:
        self._seen = seen
        self._result: dict[str, Any] = dict(result) if result is not None else {}
        self.closed = False

    async def transfer(
        self, transaction: dict[str, Any], context: Any
    ) -> dict[str, Any]:
        self._seen.append(transaction)
        return dict(self._result)

    async def close_transport(self, context: Any) -> None:
        self.closed = True


# --- arms 2–5: the gate's named refusals ----------------------------------


def test_no_scoped_transport_refuses_naming_the_permission(
    store: Store, tmp_path: Path
) -> None:
    bundle, _controller = _factory(
        store,
        tmp_path,
        _provider_descriptor(["artifact_writer"]),  # no scoped_transport
        providers=_registry(tmp_path),
    )
    import asyncio

    with pytest.raises(NotImplementedError, match="scoped_transport"):
        asyncio.run(bundle.transfer(dict(OUTPUT_REPORT), context=None))


def test_unadmitted_triple_refuses_naming_the_triple(
    store: Store, tmp_path: Path
) -> None:
    descriptor = _provider_descriptor(["scoped_transport"])
    # Unadmitted triple: the descriptor declares a digest the registry
    # never admitted (the gate re-checks; it does not trust its caller).
    descriptor["transport"]["provider"]["sha256"] = "c" * 64
    bundle, _controller = _factory(
        store, tmp_path, descriptor, providers=_registry(tmp_path)
    )
    import asyncio

    with pytest.raises(NotImplementedError, match="not admitted"):
        asyncio.run(bundle.transfer(dict(OUTPUT_REPORT), context=None))


def test_crossbound_connection_key_refuses_naming_the_key(
    store: Store, tmp_path: Path
) -> None:
    bundle, _controller = _factory(
        store,
        tmp_path,
        _provider_descriptor(["scoped_transport"]),
        providers=_registry(tmp_path, crossbound=True),
    )
    import asyncio

    with pytest.raises(NotImplementedError, match="power_meter"):
        asyncio.run(bundle.transfer(dict(OUTPUT_REPORT), context=None))


def test_empty_registry_refuses(store: Store, tmp_path: Path) -> None:
    from benchweave.control.provider_settings import ProviderRegistry

    bundle, _controller = _factory(
        store,
        tmp_path,
        _provider_descriptor(["scoped_transport"]),
        providers=ProviderRegistry(admitted=(), connections=()),
    )
    import asyncio

    with pytest.raises(NotImplementedError, match="no provider contracts"):
        asyncio.run(bundle.transfer(dict(OUTPUT_REPORT), context=None))


def test_a_providerless_descriptor_is_untouched_by_the_gate(
    store: Store, tmp_path: Path
) -> None:
    """The gate applies only to provider-declaring descriptors: a
    provider-less raw descriptor keeps the caller's transport (here None →
    the bundle's existing generic refusal), registry or not."""
    raw = {
        "id": "dev.local.watt-link",
        "descriptor_version": "1.0.0",
        "integration": {
            "mode": "adapter",
            "adapter": {
                "entry_point": "watt_link:create_plugin",
                "api_version": "1.1",
                "version": "1.0.0",
                "dependencies": [],
                "permissions": ["scoped_transport"],
            },
        },
        "transport": {"type": "serial", "connection_key": "power_meter"},
    }
    bundle, _controller = _factory(
        store, tmp_path, raw, providers=_registry(tmp_path)
    )
    import asyncio

    with pytest.raises(NotImplementedError, match="no transport is bound"):
        asyncio.run(bundle.transfer({"kind": "x"}, context=None))


# --- fold wave C: $ref grammar subschemas (crash shape, then the ban) -----


@pytest.mark.parametrize(
    ("ref", "label"),
    [
        ({"$ref": "#"}, "self reference"),
        ({"$ref": "https://example.invalid/grammar.json"}, "remote URI"),
    ],
)
def test_ref_grammar_subschemas_refuse_with_the_transaction_discipline(
    store: Store, ref: dict[str, str], label: str
) -> None:
    """Fold wave C: a grammar subschema carrying a $ref passes both
    admission lanes (check_schema meta-validates it — resolution is not
    meta-validation) and then crashes the guard's transfer with
    RecursionError/_WrappedReferencingError — OUTSIDE the
    provider_transaction: ValueError discipline. Watched failing (RED)
    before the admission-side $ref ban; the arm asserts the discipline the
    guard owes every transaction, whatever the grammar."""
    mod = _module()
    contract = json.loads((EXAMPLES / "reference-provider.json").read_text())
    contract["transaction_grammar"][0]["request_schema"] = ref
    import asyncio

    guard = mod.ProviderTransport(contract=contract, runtime=_FakeRuntime([], result={}))
    with pytest.raises(ValueError, match="provider_transaction:"):
        asyncio.run(guard.transfer(dict(OUTPUT_REPORT), context=None)), label
