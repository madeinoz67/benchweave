# OTDP transport providers 0.2.1

**Status:** Mechanism for non-scoped transports; host admission and provider implementations are separate acts  
**Companions:** `otdp-specification.md` (§6.4, §8.1), `extension-contract.md` (§6), `otdp-transport-provider.schema.json`, `examples/reference-provider.json`

## 1. What a transport provider is

A **transport-provider contract** is a JSON document validated by `otdp-transport-provider.schema.json`. It names the feature the integration requires, the transaction grammar the adapter will speak, the closed security surface the provider may touch, what the host-side implementation needs, and the approval that reviewed it. The schema is structure only: JSON validity grants no authority, exactly as commissioning documents behave.

The document's identity fields must cohere, and every admission point refuses on disagreement: the urn-embedded version equals `version`; the `feature_id`-embedded version equals `version`; and the `feature_id` name segment equals the urn's name segment (`otdp.transport.<name>` ↔ `urn:otdp:transport-provider:<name>`). Three equalities, one identity — a contract whose fields name two different providers or two different revisions is refused at admission with the existing identity-check refusals (the prefix ports with increments 2 and 3).

Provider contracts are host-admitted local documents, deliberately versioned elsewhere — like profile ids and plugin releases, they are not governed standards. The corpus owns the schema and these rules so that descriptor semantics have one authority; each instance gets its authority from a host operator.

`contract_version` is the instance-compatibility axis: it moves exactly when the schema's validation semantics move, and a corpus re-copy that changes nothing semantic keeps the const — old instances stay valid under their admitted contract. The schema's `$id` version is corpus position, not a compatibility promise; only `contract_version` is.

## 2. Declaring one

A descriptor with `transport.type: "custom"` may carry one optional `provider` object:

```json
"provider": {
  "feature_id": "otdp.transport.reference-hid/1.0.0",
  "id": "urn:otdp:transport-provider:reference-hid:1.0.0",
  "path": "reference-provider.json",
  "sha256": "<64-hex digest of the pinned bytes>"
}
```

`feature_id` follows the `required_features` pattern and **must** also appear in `required_features` — a provider the integration does not require, or a required transport feature with no declaring object, is an admission failure (S04). The `otdp.*` feature namespace is corpus-owned: an `otdp.*` identifier that is neither corpus-known (the core lanes and catalog profile ids) nor declared through a transport-provider object is a refusal at every admission point. The sanctioned provider sub-namespace is `otdp.transport.<name>/<semver>` exactly — the contract schema's `feature_id` pattern admits nothing else in `otdp.*`, so a contract claiming `otdp.core/9.9.9` (or any reserved id at a fake version) is refused before any host could mint it as known.

`{id, path, sha256}` is the contract-reference shape: digest-pinned, resolved inside the admitted bundle after symlink resolution, never a URL or executable module. The provider triple resolves **relative to the descriptor's own package root** — the same bundle-root rule extension-contract §1 states for the root `contracts` array governs that array; the provider object names its path descriptor-relative, so a plugin and its pinned contract travel one package. The pin makes "the bytes that were reviewed" deterministic; it grants nothing by itself.

The descriptor schema's version const is exact-matching, not a compatibility claim: a descriptor declaring `otdp_version` 0.2.0 is refused by the 0.2.1 schema's const by construction — the designed exact-matching posture, not a break — while every 0.2.0-valid document keeps its validity under its own pinned version's schema.

When `provider` is absent, `custom` behaves as before: the integration is honestly incomplete for that device. Nothing about a connection key implies a provider.

## 3. The transaction grammar

`transaction_grammar[]` extends the specification's §8.1 transfer table **for this provider only**. Each entry is a `kind` (unique, snake_case) with `request_schema` and `result_schema` as Draft 2020-12 subschemas and a `limits` object for byte and count bounds. The host validates provider transactions against the admitted contract's grammar, never against the generic table, and never against another provider's grammar.

Every admission point meta-validates each grammar subschema (`request_schema` and `result_schema`) against Draft 2020-12 before the contract is admitted; a subschema that fails meta-validation — a misspelled `type`, an unknown keyword where Draft 2020-12 forbids one — refuses the contract with `provider_contract_invalid:`. The implementers are the SDK's `validate_transport_provider` (increment 2) and gateway admission (increment 3); the corpus suite meta-validates its own examples the same way.

Grammar kind uniqueness means **kind-string** uniqueness across `transaction_grammar`: two entries with different `limits` but the same `kind` are a duplicate, not two kinds. The schema's `uniqueItems` only refuses byte-identical entries, so the string-level rule is this row's — admission (increments 2 and 3) enforces it, refusing with `provider_contract_invalid:`.

Extension is additive and disjoint: a provider grammar introduces **new** kinds and never shadows a generic one. The §8.1 kinds — `stream_send`, `stream_receive`, `stream_exchange`, `can_receive`, `can_send`, `i2c_transfer`, `spi_transfer` — are reserved by the generic table; a provider contract whose grammar reuses one is refused, so "extends the table" can never mean "overrides an entry".

`limits` keys are provider-defined and review-read: they state what the reviewer understood the implementation to bound. Actual byte-bound enforcement is `transfer`'s own, not `limits`' — a `limits` entry neither widens nor narrows what the transport layer enforces.

Grammar subschemas type the transaction dict's JSON-representable fields. `data` fields are bytes at the adapter ABI (§8.1) and base64 text in contract documents and offline checks. Provider transactions are `HostServices.transfer` calls on the commissioned connection: they inherit transfer's deadline, cancellation, byte-bounds and evidence enforcement unconditionally, and remain governed by the `scoped_transport` permission; they reject unspecified fields and carry no host/path/credential fields when the grammar is authored that way — a contract's own schemas decide its transaction shape, and that authorship is review surface (§4), not a schema guarantee. No new permission name exists for providers because a provider transfer *is* a scoped transport.

## 4. The security surface

`security_scope` is a closed enum, and it is the **only** closed field: this revision admits `commissioned_connection` alone, and no scope value can express a filesystem path, process spawning or an unrestricted network endpoint. That is the whole machine-checkable claim, and it names exactly that boundary — `host_requirements` text, native-library names, privilege strings and grammar subschemas remain free-form review surface, and a hostile contract can still carry a path or a privilege string inside them; review catches those, the schema does not. "No direct unrestricted SDK/filesystem/network access" (extension-contract §6) is therefore admissible as precisely "the scope is `commissioned_connection`", and as nothing wider.

The scope is a boundary only once an instance has been validated against this schema: gateway admission (increment 3) validates every provider document against the corpus schema before admitting it, so an out-of-scope value never reaches a grant. Until that admission lands, the enum is a corpus promise about what can be admitted, not a runtime claim.

## 5. Host requirements

`host_requirements` is the reviewed statement of what the host-side implementation needs: native library names with exact versions and any privilege claims. This is where a vendor SDK lives — **host-side, named and reviewed**. The plugin never imports it: plugin code runs under the admitted-import rule (stdlib only), so a vendor SDK cannot be plugin payload. This is why the lane is *host-provider*, not plugin-provider.

## 6. Review and admission — two tiers, both named

The **mechanism** — this schema, these rules, the descriptor object — is corpus content and moves under standards governance (drift gates, family suites, validation reports). Each **provider contract instance** is admitted by the host operator as a commissioning-class act: the document's `approval` block (`approved_by`, `approved_at`, `expires_at`, `evidence[]` in the commissioning evidence shape) records the review; the host's admission record grants authority. A descriptor pinning a contract the host has not admitted is an admission failure — unknown required features fail admission, and device-supplied metadata cannot add a transport provider on its own. An expired approval is not an admitted contract.

## 7. The offline boundary

Offline checks (the SDK lane) can prove a provider declaration **well-formed and self-consistent**: the schema shape, the feature-id agreement, the pin resolving inside the package to bytes that hash to `sha256`, and the pinned document passing the contract schema. Only the gateway can prove the **grant**: that `connection_key` resolves to a connection backed by the same admitted contract (exact id, version and digest), and that live transactions match the admitted grammar within `security_scope`. Commissioned state and the provider runtime live there. An offline pass is not an admission claim.
