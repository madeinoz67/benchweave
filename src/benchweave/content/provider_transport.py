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
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jsonschema import Draft202012Validator
from referencing.exceptions import Unresolvable

from benchweave.control.documents import adapter_permissions

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
        if kind not in self._grammar:
            raise ValueError(
                f"provider_transaction: kind {kind!r} is not in the admitted "
                "contract's grammar; a provider grammar extends the transfer "
                "table and never shadows it"
            )
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
    raw_descriptor: dict[str, Any], providers: ProviderRegistry | None
) -> Any:
    """The grant gate (design §1.3a): three checks, then the guard.

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
    return ProviderTransport(contract=entry.document)
