"""Three-way agreement: expected literals <-> pinned SDK <-> gateway code <-> corpus schema.

The adapter protocol is hand-mirrored — ``benchweave.host.otdp_bridge`` mirrors
``benchweave_sdk.interfaces`` — and before this module nothing in CI checked the
mirror (only the release smoke did, against the installed distribution). Every
comparison pins an expected literal and requires BOTH other parties to equal it,
so a mover on any side fails: an SDK protocol change, a gateway mirror change,
or a stale expectation. New SDK members break the set equality even when the
gateway is unchanged, forcing a conscious allowlist update.

What this does NOT catch (the honest boundary, per GOVERNANCE's promotion
trigger): semantics. Names, arity, keyword-only-ness, coroutine-ness and
key/enum sets are pinned; a signature-compatible semantic change passes. The
mutation tests at the bottom prove the comparator itself rejects drift rather
than re-asserting the gateway against itself.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import inspect
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, TypeGuard

import pytest

ROOT = Path(__file__).resolve().parents[2]
SDK_SRC = ROOT / "packages" / "sdk" / "src"

if not SDK_SRC.is_dir():
    # CI checks out submodules recursively (ci.yml); an absent submodule there
    # is an environment defect, not a skip. Locally, name the recovery command.
    if os.environ.get("CI"):
        pytest.fail(
            "packages/sdk/src is absent under CI; submodules must be checked out recursively",
            pytrace=False,
        )
    pytest.skip(
        "packages/sdk not initialized; run: git submodule update --init packages/sdk",
        allow_module_level=True,
    )

sys.path.insert(0, str(SDK_SRC))

from benchweave.host import otdp_bridge  # noqa: E402
from benchweave.host import types as gateway_types  # noqa: E402
from benchweave.standards.manifest import load_identity, load_manifest  # noqa: E402

BRIDGE_PATH = ROOT / "src/benchweave/host/otdp_bridge.py"
BRIDGE_SOURCE = BRIDGE_PATH.read_text()

# --- expected literals: the third party every comparison is pinned against ---

EXPECTED_ADAPTER_API = "1.1"
EXPECTED_CONTEXT_DATA = frozenset({"operation_id", "dataset_id", "deadline_monotonic"})
# gateway-internal context state beyond the SDK protocol surface
GATEWAY_CONTEXT_EXTRA = frozenset({"services", "dispatched", "cancelled"})
CONTEXT_METHODS: dict[str, bool] = {
    # name -> must be a coroutine function
    "is_cancelled": False,
    "mark_dispatch_started": True,
}
EXPECTED_ADAPTER_PARAMS: dict[str, tuple[str, ...]] = {
    "open": ("descriptor", "services", "context"),
    "execute": ("request", "context"),
    "next_event": ("subscription_id", "context"),
    "close": ("context",),
}
# Adapter data members: none today — the protocol is behavioral, and a data
# member appearing on the SDK side is a protocol change this pin must surface
EXPECTED_ADAPTER_DATA = frozenset[str]()
EXPECTED_BRIDGE_CALLS: dict[str, tuple[int, bool, bool]] = {
    # member -> (positional arguments, keyword arguments used, starred arguments)
    "open": (3, False, False),
    "execute": (2, False, False),
    "close": (1, False, False),
}
# documented gap: declared by the SDK protocol, never called by the bridge
# (identify/read/write only — the otdp_bridge module docstring)
ADAPTER_GAPS = frozenset({"next_event"})
EXPECTED_HOST_SERVICES = frozenset(
    {"monotonic", "utc_now", "transfer", "close_transport", "record_evidence"}
)
# documented gap: the gateway exercises only the monotonic-clock subset; the
# bridge's structural requirement is exactly callable(services.monotonic)
GATEWAY_SERVICES_SUBSET = frozenset({"monotonic"})
# documented gap: the capture surface is SDK-only
EXPECTED_CAPTURE_SERVICES = frozenset(
    {"artifact_append", "artifact_finalise", "artifact_abort"}
)
REQUEST_KEYS = frozenset({"operation_id", "verb", "arguments"})
RESULT_KEYS = frozenset({"operation_id", "verb", "status", "data"})
ERROR_PATH_KEYS = frozenset({"operation_id", "verb", "status", "error"})
ERROR_KEYS = frozenset({"code", "message", "dispatch_state"})
EXPECTED_ERROR_CODES = frozenset(
    {
        "INVALID_ARGUMENT",
        "UNSUPPORTED",
        "IDENTITY_MISMATCH",
        "DEVICE_REJECTED",
        "TRANSPORT_ERROR",
        "TIMEOUT",
        "PROTOCOL_ERROR",
        "RESOURCE_LIMIT",
        "CANCELLED",
        "INTERNAL_ERROR",
    }
)
EXPECTED_DISPATCH_STATES = frozenset({"not_dispatched", "dispatched", "unknown"})
EXPECTED_OPERATION_STATUSES = frozenset({"ok", "error", "unknown", "cancelled"})
EXPECTED_OPERATION_VERBS = frozenset(
    {
        "identify",
        "read",
        "write",
        "self_test",
        "get_errors",
        "capture",
        "stream_subscribe",
        "stream_unsubscribe",
        "reset",
        "invoke",
    }
)


# --- loaders ---


def _sdk_module(name: str) -> ModuleType:
    """Import an SDK module and prove it came from the pinned submodule.

    The guard is not optional: a venv carrying an editable install of the
    standalone SDK checkout (stale relative to the pinned submodule) would
    otherwise be tested by mistake; ``sys.path.insert(0)`` wins only when the
    submodule path exists, and this assertion makes the source unambiguous.
    """
    module = importlib.import_module(name)
    assert module.__file__ is not None, f"{name} has no source file"
    location = Path(module.__file__).resolve()
    assert location.is_relative_to(SDK_SRC.resolve()), (
        f"{name} resolved from {location}, not the pinned submodule {SDK_SRC}"
    )
    return module


def _active_otdp_version() -> str:
    return next(entry.version for entry in load_manifest(ROOT).standards if entry.id == "otdp")


def _load_active(filename: str) -> dict[str, Any]:
    path = ROOT / "standards" / "otdp" / _active_otdp_version() / filename
    document: dict[str, Any] = json.loads(path.read_bytes())
    return document


def _load_mutated_interfaces(
    tmp_path: Path, replacements: tuple[tuple[str, str], ...]
) -> ModuleType:
    """A mutated COPY of the pinned interfaces.py; the canonical tree is never touched."""
    source = (SDK_SRC / "benchweave_sdk" / "interfaces.py").read_text()
    for old, new in replacements:
        assert source.count(old) == 1, f"mutation fixture no longer applies: {old!r}"
        source = source.replace(old, new)
    mutated = tmp_path / "mutated_interfaces.py"
    mutated.write_text(source)
    spec = importlib.util.spec_from_file_location("mutated_interfaces", mutated)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- structural extraction (the gateway side is read from code, never assumed) ---


def _is_self_attr(node: ast.AST, name: str) -> TypeGuard[ast.Attribute]:
    """The node is exactly ``self.<name>``."""
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
        and node.attr == name
    )


def _is_self_member(node: ast.AST, holder: str) -> TypeGuard[ast.Attribute]:
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == holder
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "self"
    )


def bridge_adapter_pin(
    source: str,
) -> tuple[dict[str, set[tuple[int, bool, bool]]], int, list[int]]:
    """Total pin over the ``_adapter`` attribute; nothing else in the module may touch it.

    Returns (member -> call-site shapes, store count, linenos of occurrences in
    any other form). A shape is (positional args, keyword args used, starred
    args present). Every ``._adapter`` occurrence must be consumed as the base
    of a member call or as an assignment target — an alias, a bare read, a
    helper argument, a foreign receiver or a ``del`` lands in the unaccounted
    list and fails the check, because a call through any of those forms
    escapes the three-way pin silently.
    """
    tree = ast.parse(source)
    consumed: set[int] = set()
    stores = 0
    shapes: dict[str, set[tuple[int, bool, bool]]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            base = node.func.value
            if _is_self_attr(base, "_adapter"):
                consumed.add(id(base))
                shapes.setdefault(node.func.attr, set()).add(
                    (
                        len(node.args),
                        bool(node.keywords),
                        any(isinstance(argument, ast.Starred) for argument in node.args),
                    )
                )
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                elements = target.elts if isinstance(target, (ast.Tuple, ast.List)) else [target]
                for element in elements:
                    if _is_self_attr(element, "_adapter"):
                        consumed.add(id(element))
                        stores += 1
    unaccounted = sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "_adapter" and id(node) not in consumed
    )
    return shapes, stores, unaccounted


def bridge_services_members(source: str) -> set[str]:
    """Every ``self._services`` member the bridge touches (its exercised subset)."""
    return {
        node.attr for node in ast.walk(ast.parse(source)) if _is_self_member(node, "_services")
    }


def _string_set_literals(node: ast.AST) -> set[frozenset[str]]:
    """Key/element sets of set and dict literals whose parts are all plain strings."""
    literals: set[frozenset[str]] = set()
    for inner in ast.walk(node):
        parts: list[str] = []
        if isinstance(inner, ast.Set):
            constants = [element for element in inner.elts if isinstance(element, ast.Constant)]
            parts = [element.value for element in constants if isinstance(element.value, str)]
            if len(parts) != len(inner.elts) or not parts:
                continue
        elif isinstance(inner, ast.Dict):
            constants = [key for key in inner.keys if isinstance(key, ast.Constant)]
            parts = [key.value for key in constants if isinstance(key.value, str)]
            if len(parts) != len(inner.keys) or not parts:
                continue
        else:
            continue
        literals.add(frozenset(parts))
    return literals


def _protocol_methods(cls: Any) -> dict[str, Any]:
    return {
        name: value
        for name, value in vars(cls).items()
        if not name.startswith("__") and inspect.isfunction(value)
    }


def _protocol_surface(cls: Any) -> set[str]:
    """Own and inherited protocol members; typing's own machinery is not surface."""
    members: set[str] = set()
    for klass in cls.__mro__:
        if klass is object or getattr(klass, "__module__", None) == "typing":
            continue
        members |= set(_protocol_methods(klass))
        members |= set(getattr(klass, "__annotations__", {}))
    return members


def _signature_shape(func: Any) -> tuple[tuple[str, ...], int, int, bool]:
    """(names excluding self, positional count, keyword-only count, coroutine-ness)."""
    parameters = [
        parameter
        for parameter in inspect.signature(func).parameters.values()
        if parameter.name != "self"
    ]
    keyword_only = sum(
        1 for parameter in parameters if parameter.kind is inspect.Parameter.KEYWORD_ONLY
    )
    names = tuple(parameter.name for parameter in parameters)
    return names, len(parameters) - keyword_only, keyword_only, inspect.iscoroutinefunction(func)


# --- comparators: each pins expected literals and requires BOTH parties to equal them ---


def check_context_agreement(sdk: ModuleType) -> None:
    """expected literals <-> SDK OperationContext <-> gateway _Context."""
    protocol = sdk.OperationContext
    assert (
        set(getattr(protocol, "__annotations__", {})) == EXPECTED_CONTEXT_DATA
    ), "SDK OperationContext data members drifted"
    sdk_methods = _protocol_methods(protocol)
    assert set(sdk_methods) == set(CONTEXT_METHODS), "SDK OperationContext methods drifted"

    context = otdp_bridge._Context("agreement-check", 1.0, object())
    assert frozenset(vars(context)) == EXPECTED_CONTEXT_DATA | GATEWAY_CONTEXT_EXTRA, (
        "gateway _Context data members drifted"
    )
    # documented gap: dataset_id is pinned present on both sides and is always
    # None from the bridge (no dataset support in the synchronous host)
    assert context.dataset_id is None
    gateway_methods = _protocol_methods(otdp_bridge._Context)
    assert set(gateway_methods) == set(CONTEXT_METHODS), "gateway _Context methods drifted"

    for name, coroutine in CONTEXT_METHODS.items():
        for side, methods in (("sdk", sdk_methods), ("gateway", gateway_methods)):
            names, positional, keyword_only, is_coroutine = _signature_shape(methods[name])
            assert names == (), f"{side} OperationContext.{name} must take no arguments"
            assert keyword_only == 0, f"{side} OperationContext.{name} keyword-only drift"
            assert is_coroutine is coroutine, f"{side} OperationContext.{name} coroutine drift"
            assert positional == 0


def check_adapter_surface(sdk: ModuleType, source: str) -> None:
    """expected literals <-> SDK Adapter protocol <-> the bridge's actual call sites."""
    methods = _protocol_methods(sdk.Adapter)
    data = set(getattr(sdk.Adapter, "__annotations__", {}))
    assert data == EXPECTED_ADAPTER_DATA, "SDK Adapter data members drifted"
    assert set(methods) == set(EXPECTED_ADAPTER_PARAMS), "SDK Adapter member set drifted"
    shapes, stores, unaccounted = bridge_adapter_pin(source)
    assert not unaccounted, (
        f"._adapter is used outside the pinned call sites/store at lines {unaccounted}; "
        "an alias, bare read, helper argument or foreign receiver escapes the three-way "
        "pin silently — widen EXPECTED_BRIDGE_CALLS consciously instead"
    )
    assert stores == 1, "the bridge must store the adapter exactly once (OTDPBridge.__init__)"
    assert set(shapes) == set(EXPECTED_BRIDGE_CALLS), "bridge adapter call set drifted"
    assert set(methods) - set(shapes) == ADAPTER_GAPS, "documented adapter gaps drifted"
    for name, parameters in EXPECTED_ADAPTER_PARAMS.items():
        names, _, keyword_only, is_coroutine = _signature_shape(methods[name])
        assert names == parameters, f"SDK Adapter.{name} parameter names drifted"
        assert keyword_only == 0, f"SDK Adapter.{name} must not take keyword-only arguments"
        assert is_coroutine, f"SDK Adapter.{name} must stay async"
    for name, site_shapes in shapes.items():
        for positional, keywords, starred in site_shapes:
            assert not starred, f"unpinnable call shape: starred argument at a {name} call site"
            assert not keywords, f"bridge call to {name} must pass arguments positionally"
            assert positional == len(EXPECTED_ADAPTER_PARAMS[name]), (
                f"bridge call to {name} arity drifted"
            )
    for name, expected_shape in EXPECTED_BRIDGE_CALLS.items():
        assert shapes[name] == {expected_shape}, f"bridge call sites to {name} drifted"


def check_host_services(sdk: ModuleType, source: str) -> None:
    """expected literals <-> SDK HostServices/CaptureServices <-> the exercised subset."""
    services = _protocol_surface(sdk.HostServices)
    assert services == EXPECTED_HOST_SERVICES, "SDK HostServices member set drifted"
    capture = _protocol_surface(sdk.CaptureServices)
    assert capture == EXPECTED_HOST_SERVICES | EXPECTED_CAPTURE_SERVICES
    used = bridge_services_members(source)
    assert used == GATEWAY_SERVICES_SUBSET, "bridge services subset drifted"
    # each gap row asserts its own presence so silent narrowing becomes a diff
    assert EXPECTED_HOST_SERVICES - used == {
        "utc_now",
        "transfer",
        "close_transport",
        "record_evidence",
    }
    assert not (EXPECTED_CAPTURE_SERVICES & used), "capture surface must stay SDK-only"


def check_envelopes(source: str, runtime: dict[str, Any]) -> None:
    """expected literals <-> the bridge's enforced key sets <-> the active runtime schema."""
    defs = runtime["$defs"]
    assert set(defs["operationRequest"]["required"]) == REQUEST_KEYS
    assert defs["operationRequest"]["additionalProperties"] is False
    properties = set(defs["operationResult"]["properties"])
    assert properties - {"error"} == RESULT_KEYS
    assert properties - {"data"} == ERROR_PATH_KEYS
    assert set(defs["error"]["required"]) == ERROR_KEYS
    # documented delta (pre-existing, now pinned): the schema permits ^x-
    # extension keys in the error object (patternProperties) while the bridge
    # enforces the closed set — intentional gateway strictness; if either side
    # changes, this row surfaces it.
    assert defs["error"].get("patternProperties"), "error ^x- extension allowance changed"

    literals = _string_set_literals(ast.parse(source))
    assert frozenset(RESULT_KEYS) in literals, "success key set no longer enforced in the bridge"
    assert frozenset(ERROR_PATH_KEYS) in literals, "error key set no longer enforced in bridge"
    assert frozenset(ERROR_KEYS) in literals, "error-object key set no longer enforced in bridge"
    assert frozenset(REQUEST_KEYS) in literals, "request key set no longer built by the bridge"


def check_vocabularies(runtime: dict[str, Any]) -> None:
    """expected literals <-> gateway StrEnums <-> the active runtime schema enums."""
    defs = runtime["$defs"]
    _vocabulary(
        "ErrorCode",
        gateway_types.ErrorCode,
        EXPECTED_ERROR_CODES,
        defs["error"]["properties"]["code"]["enum"],
    )
    _vocabulary(
        "DispatchState",
        gateway_types.DispatchState,
        EXPECTED_DISPATCH_STATES,
        defs["error"]["properties"]["dispatch_state"]["enum"],
    )
    _vocabulary(
        "OperationStatus",
        gateway_types.OperationStatus,
        EXPECTED_OPERATION_STATUSES,
        defs["operationResult"]["properties"]["status"]["enum"],
    )
    _vocabulary(
        "OperationVerb",
        gateway_types.OperationVerb,
        EXPECTED_OPERATION_VERBS,
        defs["operationRequest"]["properties"]["verb"]["enum"],
    )


def _vocabulary(name: str, enum: Any, expected: frozenset[str], schema_values: Any) -> None:
    values = {member.value for member in enum}
    assert values == expected, f"gateway {name} drifted from the expected vocabulary"
    assert set(schema_values) == expected, f"schema enum for {name} drifted from expected"


def check_version_triplet(
    sdk_package: ModuleType, descriptor: dict[str, Any], identity: dict[str, str]
) -> None:
    """SDK constant == corpus identity == descriptor schema const == expected literal."""
    assert getattr(sdk_package, "ADAPTER_API_VERSION", None) == EXPECTED_ADAPTER_API
    assert identity.get("adapter_api") == EXPECTED_ADAPTER_API
    const = descriptor["$defs"]["adapter"]["properties"]["api_version"]["const"]
    assert const == EXPECTED_ADAPTER_API


# --- the pins ---


def test_context_agreement() -> None:
    check_context_agreement(_sdk_module("benchweave_sdk.interfaces"))


def test_adapter_call_surface() -> None:
    check_adapter_surface(_sdk_module("benchweave_sdk.interfaces"), BRIDGE_SOURCE)


def test_host_services_subset() -> None:
    check_host_services(_sdk_module("benchweave_sdk.interfaces"), BRIDGE_SOURCE)


def test_envelopes_and_extension_delta() -> None:
    check_envelopes(BRIDGE_SOURCE, _load_active("otdp-runtime.schema.json"))


def test_vocabularies() -> None:
    check_vocabularies(_load_active("otdp-runtime.schema.json"))


def test_version_triplet() -> None:
    check_version_triplet(
        _sdk_module("benchweave_sdk"),
        _load_active("otdp-device-descriptor.schema.json"),
        load_identity(ROOT),
    )


# --- anti-tautology proofs: the comparator must reject mutated copies ---


def test_comparator_rejects_a_renamed_context_method(tmp_path: Path) -> None:
    mutated = _load_mutated_interfaces(
        tmp_path,
        (("async def mark_dispatch_started(self)", "async def mark_dispatch_begun(self)"),),
    )
    with pytest.raises(AssertionError):
        check_context_agreement(mutated)


def test_comparator_rejects_a_keyword_only_execute_argument(tmp_path: Path) -> None:
    mutated = _load_mutated_interfaces(
        tmp_path,
        (
            (
                "self, request: dict[str, Any], context: OperationContext",
                "self, request: dict[str, Any], *, context: OperationContext",
            ),
        ),
    )
    with pytest.raises(AssertionError):
        check_adapter_surface(mutated, BRIDGE_SOURCE)


def test_comparator_rejects_a_dropped_context_member(tmp_path: Path) -> None:
    mutated = _load_mutated_interfaces(tmp_path, (("\n    dataset_id: str | None", ""),))
    with pytest.raises(AssertionError):
        check_context_agreement(mutated)


def test_vocabulary_check_rejects_a_renamed_schema_enum_value() -> None:
    runtime = _load_active("otdp-runtime.schema.json")
    values = runtime["$defs"]["error"]["properties"]["dispatch_state"]["enum"]
    values[values.index("not_dispatched")] = "never_dispatched"
    with pytest.raises(AssertionError):
        check_vocabularies(runtime)


def _mutated_bridge_source(replacements: tuple[tuple[str, str], ...]) -> str:
    """String surgery on a COPY of the bridge source; the tree is never touched."""
    source = BRIDGE_SOURCE
    for old, new in replacements:
        assert source.count(old) == 1, f"mutation fixture no longer applies: {old!r}"
        source = source.replace(old, new)
    return source


def test_adapter_pin_rejects_an_aliased_adapter_call() -> None:
    """F1: a call through an alias of self._adapter escapes the member pin."""
    aliased = _mutated_bridge_source(
        (
            (
                "result = self._run(self._adapter.execute(envelope, context), context)",
                'alias = self._adapter\n'
                '                self._run(alias.next_event("subscriptions", context), context)\n'
                "                result = self._run(self._adapter.execute(envelope, context), context)",
            ),
        )
    )
    with pytest.raises(AssertionError):
        check_adapter_surface(_sdk_module("benchweave_sdk.interfaces"), aliased)


def test_adapter_pin_rejects_a_starred_call_argument() -> None:
    """F1: a starred argument is an unpinnable shape, not one positional."""
    starred = _mutated_bridge_source(
        (
            (
                "self._adapter.execute(envelope, context)",
                "self._adapter.execute(*envelope_parts, context)",
            ),
        )
    )
    with pytest.raises(AssertionError):
        check_adapter_surface(_sdk_module("benchweave_sdk.interfaces"), starred)


def test_adapter_pin_rejects_a_helper_argument_pass_through() -> None:
    """F1: handing self._adapter to a helper escapes the member pin."""
    passed = _mutated_bridge_source(
        (
            (
                "result = self._run(self._adapter.execute(envelope, context), context)",
                "self._dispatch_via(self._adapter, context)\n"
                "                result = self._run(self._adapter.execute(envelope, context), context)",
            ),
        )
    )
    with pytest.raises(AssertionError):
        check_adapter_surface(_sdk_module("benchweave_sdk.interfaces"), passed)


def test_comparator_rejects_an_adapter_data_member(tmp_path: Path) -> None:
    """F2: a non-function Adapter member is a protocol change, not an invisible extra."""
    mutated = _load_mutated_interfaces(
        tmp_path, (("\n    async def open(", "\n    retries: int\n\n    async def open("),)
    )
    with pytest.raises(AssertionError):
        check_adapter_surface(mutated, BRIDGE_SOURCE)


def test_absent_submodule_fails_under_ci(tmp_path: Path) -> None:
    """An absent submodule under CI fails this module; it never silently skips."""
    isolated = tmp_path / "isolated"
    (isolated / "tests/sdk").mkdir(parents=True)
    shutil.copyfile(Path(__file__), isolated / "tests/sdk/test_adapter_agreement.py")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/sdk/test_adapter_agreement.py"],
        cwd=isolated,
        env={**os.environ, "CI": "true"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, "an absent submodule must fail under CI, not pass"
    combined = result.stdout + result.stderr
    assert "submodules must be checked out recursively" in combined
    assert "skipped" not in combined.lower(), "the CI path must fail, not skip"
