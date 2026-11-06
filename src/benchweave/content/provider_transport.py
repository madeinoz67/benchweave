"""The provider grant: a grammar guard over an admitted contract.

Issue #147 increment 3, design §1.3. The grant is an OBJECT, not a
protocol change: ``ScopedServicesBundle`` already delegates ``transfer``
and ``close_transport`` to an injected transport, so the provider grant is
a grammar-guarded adapter over an ADMITTED contract bound at that seam.
The adapter calls the same ``HostServices.transfer`` with provider-kind
transactions; the grammar — not any implementation — is the contract (the
three-backend composition: this guard, a future standalone backend, and
the SDK MockHost all speak the same admitted grammar).

The guard sits INSIDE the existing transfer envelope — the bridge's
dispatch markers, deadline, cancellation and transmission evidence wrap
``services.transfer``, so every provider transaction inherits them. The
descriptor's ``settings.protocol_reference`` is review-read metadata; the
guard never consumes it. ``security_scope`` needs no runtime check:
``commissioned_connection`` is the only enum value and the guard has no
other capability to exercise — the boundary is the object's shape.

Nothing in production constructs these objects yet (issue #167 carries the
activation wiring): this seam enforces admission and grammar at the
component boundary the composing services define, and is READY for row 9's
wiring rather than blocked by it.

Issue #568 completes the grant (design §1.2/§2.2): with a runtime factory
supplied, the construction resolves the commissioned endpoint, checks the
runtime's op table against the admitted grammar's every op (BEFORE the
device opens), opens the device, and injects the runtime behind the guard.
The guard's kind gate also widened to the corpus's own composition (§0.6:
the gateway serves BOTH transaction families on a provider connection):
the generic §8.1 kinds forward to the runtime's own ladder — a provider
grammar EXTENDS the transfer table, so the table's kinds are always in the
effective grammar — while unknown kinds refuse exactly as before.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jsonschema import Draft202012Validator
from referencing.exceptions import Unresolvable

from benchweave.content.provider_runtime import grammar_op_consts
from benchweave.control.documents import _RESERVED_TRANSFER_KINDS, adapter_permissions

if TYPE_CHECKING:
    from benchweave.control.provider_settings import ProviderRegistry

#: The one permission that governs a provider transfer — a provider
#: transfer IS a scoped transport (record §1.3; no new permission name).
SCOPED_TRANSPORT = "scoped_transport"


class ProviderTransport:
    """The grammar guard: exactly the two members the bundle delegates to.

    Transactions are validated against the admitted contract's grammar
    BEFORE any delegation — kind membership first ("extends the table,
    never shadows it"), then the kind's ``request_schema`` over the
    transaction PAYLOAD (the transaction minus the ``kind`` selector: the
    corpus's own reference grammar types the fields with
    ``additionalProperties: false`` and no ``kind`` property, so the
    selector is not payload — whole-dict validation would refuse every
    corpus-grammar transaction). With a runtime injected, the result is
    validated against the kind's ``result_schema`` before it returns — a
    misbehaving host-side runtime cannot launder a malformed result into
    the adapter. Without a runtime the guard refuses loudly, naming the
    lane: provider implementations are a separate act (design deferral 1),
    and the grammar is enforced regardless.
    """

    def __init__(self, *, contract: dict[str, Any], runtime: Any = None) -> None:
        self._grammar: dict[str, dict[str, Any]] = {
            str(entry["kind"]): entry
            for entry in contract["transaction_grammar"]
        }
        self._runtime = runtime
        self._validators: dict[tuple[str, str], Any] = {}

    def _schema_validator(self, kind: str, field: str) -> Any:
        key = (kind, field)
        validator = self._validators.get(key)
        if validator is None:
            validator = Draft202012Validator(self._grammar[kind][field])
            self._validators[key] = validator
        return validator

    def _first_error(self, kind: str, field: str, document: Any) -> Any:
        """The first schema error over ``document``, or None — with an
        UNEVALUABLE grammar converted to the transaction discipline's
        ValueError, never a crash. Admission refuses ``$ref``-bearing
        grammars, so every admitted contract evaluates; this arm exists
        because the guard is directly constructible (tests, and later the
        runtime-injection seam), and a RecursionError or an unresolvable
        reference there would escape the ValueError contract transfer
        documents (fold wave C)."""
        try:
            return next(
                iter(self._schema_validator(kind, field).iter_errors(document)),
                None,
            )
        except (RecursionError, Unresolvable) as exc:
            raise ValueError(
                f"provider_transaction: the grammar for {kind}.{field} could "
                f"not be evaluated ({type(exc).__name__}); grammar subschemas "
                "are inline Draft 2020-12 and references are refused at "
                "admission"
            ) from exc

    async def transfer(
        self, transaction: dict[str, Any], context: Any
    ) -> dict[str, Any]:
        """One provider transaction, grammar-guarded, through the runtime."""
        if not isinstance(transaction, dict) or not isinstance(
            transaction.get("kind"), str
        ):
            raise ValueError(
                "provider_transaction: a provider transaction is an object "
                "carrying a 'kind' string"
            )
        kind = transaction["kind"]
        if kind not in self._grammar and kind not in _RESERVED_TRANSFER_KINDS:
            raise ValueError(
                f"provider_transaction: kind {kind!r} is not in the admitted "
                "contract's grammar; a provider grammar extends the transfer "
                "table and never shadows it"
            )
        if kind not in self._grammar:
            # A generic §8.1 kind (issue #568, §0.6): the grammar EXTENDS the
            # transfer table, so the table's kinds are in the effective
            # grammar by construction — the runtime's own §8.1 ladder
            # validates them (strict field sets, bounds); the unserved
            # reserved kinds refuse there, typed.
            if self._runtime is None:
                raise NotImplementedError(
                    f"transfer: no provider runtime is injected for kind "
                    f"{kind!r} — provider implementations are a separate act "
                    "(the issue #147 implementation lane); the admitted "
                    "grammar is enforced regardless"
                )
            result = self._runtime.transfer(transaction, context)
            if hasattr(result, "__await__"):
                generic: dict[str, Any] = await result
            else:
                generic = result
            return generic
        payload = {key: value for key, value in transaction.items() if key != "kind"}
        error = self._first_error(kind, "request_schema", payload)
        if error is not None:
            raise ValueError(
                f"provider_transaction: {kind} request violates the admitted "
                f"grammar at {error.json_path}: {error.message}"
            )
        if self._runtime is None:
            raise NotImplementedError(
                f"transfer: no provider runtime is injected for kind {kind!r} — "
                "provider implementations are a separate act (the issue #147 "
                "implementation lane); the admitted grammar is enforced "
                "regardless"
            )
        result = self._runtime.transfer(transaction, context)
        if hasattr(result, "__await__"):
            outcome: dict[str, Any] = await result
        else:
            outcome = result
        error = self._first_error(kind, "result_schema", outcome)
        if error is not None:
            raise ValueError(
                f"provider_transaction: the runtime's {kind} result violates "
                f"the admitted grammar at {error.json_path}: {error.message}"
            )
        return outcome

    def attach_runtime_evidence(self, record: Any) -> None:
        """Bind the session bundle's ``record_evidence`` to the injected
        runtime's intent-first ladder (a no-op without a runtime that takes
        one — the tests' doubles bind their own)."""
        attach = getattr(self._runtime, "attach_evidence", None)
        if attach is not None:
            attach(record)

    async def close_transport(self, context: Any) -> None:
        """Close through the runtime; a no-op without one (nothing was
        opened — raising here would poison a session that never had
        transport)."""
        if self._runtime is None:
            return
        closer = self._runtime.close_transport
        result = closer(context)
        if hasattr(result, "__await__"):
            await result


class _TransportRefusal:
    """A bound refusal: ``transfer`` raises the failed check's
    ``NotImplementedError``; ``close_transport`` is a no-op.

    The structural absence of a usable transport with a loud, named
    refusal — the same refusal shape the unbound bundle practices, carried
    by an object so the refusal can name the exact failed check
    (permission, admission, resolution) instead of the generic
    no-transport message.
    """

    def __init__(self, message: str) -> None:
        self._message = message

    async def transfer(
        self, transaction: dict[str, Any], context: Any
    ) -> dict[str, Any]:
        raise NotImplementedError(self._message)

    async def close_transport(self, context: Any) -> None:
        return None


def declares_provider(raw_descriptor: object) -> bool:
    """Whether a RAW full-form descriptor declares a transport provider."""
    if not isinstance(raw_descriptor, dict):
        return False
    transport = raw_descriptor.get("transport")
    return isinstance(transport, dict) and isinstance(
        transport.get("provider"), dict
    )


def provider_transport_for(
    raw_descriptor: dict[str, Any],
    providers: ProviderRegistry | None,
    *,
    endpoints: Any = None,
    runtime_factory: Any = None,
) -> Any:
    """The grant gate: the landed three checks, then the runtime grant
    (issue #568, design §1.2/§2.2).

    Returns a bound :class:`ProviderTransport` when every check holds,
    else a :class:`_TransportRefusal` naming the failed check. The
    construction seam must not trust its caller — admission already
    refused these shapes; the gate re-checks (the same defense-in-depth
    ``load_otdp_plugin`` practices re-hashing entry bytes). Checks, in
    order:

    1. the permission: ``scoped_transport`` in the RAW descriptor's
       adapter permissions (no new permission name exists);
    2. the admission: the declared triple (id, urn-embedded version,
       sha256) is exactly an admitted triple — an empty registry is this
       check's degenerate state (no admitted triple exists to match);
    3. the resolution: ``connection_key`` resolves to a connection bound
       to the SAME admitted contract (S12-extended).

    With ``endpoints`` supplied, the commissioned-identity legs join:

    4. the endpoint: the connection key resolves to exactly one
       commissioned USB identity (``provider_grant_endpoint_absent:``; the
       conflict re-check — ``provider_grant_endpoint_conflict:`` — is the
       construction gate's defense-in-depth over the connections
       document's own load-time refusal);
    5. the runtime: ``runtime_factory(contract, identity)`` constructs the
       runtime UNOPENED, the table-vs-grammar check demands the runtime's
       dispatch table cover every op the grammar discriminates
       (``provider_runtime_op_unsupported:`` BEFORE the device opens), and
       only then does the device open. ``runtime_factory=None`` keeps
       today's posture: the guard constructs with no runtime and the first
       transfer raises ``NotImplementedError`` (the B0 control's shape).
    """
    permissions = adapter_permissions(raw_descriptor)
    if SCOPED_TRANSPORT not in permissions:
        return _TransportRefusal(
            "transfer: the descriptor declares a transport provider but the "
            "adapter lacks the scoped_transport permission — no provider "
            "transport is granted (a provider transfer IS a scoped transport)"
        )
    transport = raw_descriptor.get("transport")
    provider = transport.get("provider") if isinstance(transport, dict) else None
    if not isinstance(provider, dict):
        return _TransportRefusal(
            "transfer: the descriptor declares no usable transport provider "
            "object — no provider transport is granted"
        )
    provider_id = provider.get("id")
    urn_parts = str(provider_id).split(":") if isinstance(provider_id, str) else []
    declared_version = urn_parts[4] if len(urn_parts) == 5 else None
    entry = (
        providers.find(provider_id, declared_version, provider.get("sha256"))
        if providers is not None
        else None
    )
    if entry is None:
        if providers is None or not providers.admitted:
            detail = "no provider contracts are admitted at all"
        else:
            detail = (
                f"the declared provider triple {provider_id}@{declared_version} "
                "is not admitted"
            )
        return _TransportRefusal(
            f"transfer: {detail} — no provider transport is granted"
        )
    key = transport.get("connection_key") if isinstance(transport, dict) else None
    bound = providers.resolve_connection(key) if providers is not None else None
    if bound is None or (bound.id, bound.version, bound.sha256) != (
        provider_id,
        declared_version,
        provider.get("sha256"),
    ):
        detail = (
            f"connection key {key!r} does not resolve to a connection bound to "
            f"the declared admitted contract {provider_id}@{declared_version}"
            if bound is None
            else f"connection key {key!r} is bound to a different admitted "
            f"contract ({bound.id})"
        )
        return _TransportRefusal(f"transfer: {detail} — no provider transport is granted")
    runtime: Any = None
    if endpoints is not None:
        identity = endpoints.resolve(key)
        if identity is None:
            # The worker-layer grant refusals RAISE (design §1.4 step 3: a
            # refusal fails the run build with the typed reason — the
            # poison-guard shape), unlike the landed 1-3 bound refusals.
            raise ValueError(
                f"provider_grant_endpoint_absent: connection key {key!r} "
                "resolves to no commissioned USB identity in the "
                "provider-connections document — no provider transport is "
                "granted (the closed default, A02)"
            )
        rivals = endpoints.keys_on(identity)
        if len(rivals) > 1:
            raise ValueError(
                f"provider_grant_endpoint_conflict: connection keys "
                f"{sorted(rivals)} share one commissioned USB identity — a USB "
                "interface is single-client; no provider transport is granted"
            )
        if runtime_factory is not None:
            runtime = runtime_factory(entry.document, identity)
            _check_table_covers_grammar(entry.document, runtime)
            runtime.open()
    return ProviderTransport(contract=entry.document, runtime=runtime)


def _check_table_covers_grammar(contract: dict[str, Any], runtime: Any) -> None:
    """The table-vs-grammar check (design §2.2.3): every op the admitted
    grammar's request schema discriminates must be in the runtime's
    dispatch table, and every grammar kind must discriminate ops at all —
    an un-runnable procedure refuses the GRANT, before the device opens
    (the honest #260 posture; a version-skew belt against a newer pinned
    contract this runtime predates)."""
    from benchweave.content.provider_runtime import _OPS

    for kind, ops in grammar_op_consts(contract).items():
        if not ops:
            raise ValueError(
                f"provider_runtime_op_unsupported: the admitted grammar kind "
                f"{kind!r} discriminates no op this runtime's table "
                f"dispatches ({sorted(_OPS)}) — the grant refuses rather than "
                "serving a kind it cannot run"
            )
        for op in sorted(ops):
            if op not in _OPS:
                raise ValueError(
                    f"provider_runtime_op_unsupported: the admitted grammar "
                    f"kind {kind!r} discriminates op {op!r}, which this "
                    "runtime's dispatch table does not carry (the pinned "
                    "contract may be newer than the runtime) — the grant "
                    "refuses rather than failing mid-run"
                )
