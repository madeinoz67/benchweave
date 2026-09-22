# OTDP transport providers 0.2.1

**Status:** Mechanism for non-scoped transports; host admission and provider implementations are separate acts  
**Companions:** `otdp-specification.md` (§6.4, §8.1), `extension-contract.md` (§6), `otdp-transport-provider.schema.json`, `examples/reference-provider.json`

## 1. What a transport provider is

A **transport-provider contract** is a JSON document validated by `otdp-transport-provider.schema.json`. It names the feature the integration requires, the transaction grammar the adapter will speak, the closed security surface the provider may touch, what the host-side implementation needs, and the approval that reviewed it. The schema is structure only: JSON validity grants no authority, exactly as commissioning documents behave.

Provider contracts are host-admitted local documents, deliberately versioned elsewhere — like profile ids and plugin releases, they are not governed standards. The corpus owns the schema and these rules so that descriptor semantics have one authority; each instance gets its authority from a host operator.

## 2. Declaring one

A descriptor with `transport.type: "custom"` may carry one optional `provider` object:

```json
"provider": {
  "feature_id": "otdp.transport.reference_hid/1.0.0",
  "id": "urn:otdp:transport-provider:reference-hid:1.0.0",
  "path": "reference-provider.json",
  "sha256": "4a7f53b4313f6279f003737a756151516033ed1573cffd5c14b00ddfa0b3dc79"
}
```

`feature_id` follows the `required_features` pattern and **must** also appear in `required_features` — a provider the integration does not require, or a required transport feature with no declaring object, is an admission failure (S04). `{id, path, sha256}` is the contract-reference shape: package-relative, digest-pinned, resolved inside the admitted bundle after symlink resolution, never a URL or executable module. The pin makes "the bytes that were reviewed" deterministic; it grants nothing by itself.

When `provider` is absent, `custom` behaves as before: the integration is honestly incomplete for that device. Nothing about a connection key implies a provider.

## 3. The transaction grammar

`transaction_grammar[]` extends the specification's §8.1 transfer table **for this provider only**. Each entry is a `kind` (unique, snake_case) with `request_schema` and `result_schema` as Draft 2020-12 subschemas and a `limits` object for byte and count bounds. The host validates provider transactions against the admitted contract's grammar, never against the generic table, and never against another provider's grammar.

Grammar subschemas type the transaction dict's JSON-representable fields. `data` fields are bytes at the adapter ABI (§8.1) and base64 text in contract documents and offline checks. Provider transactions are `HostServices.transfer` calls on the commissioned connection: they reject unspecified fields, carry no host/path/credential fields, inherit transfer's deadline, cancellation, byte-bounds and evidence enforcement, and remain governed by the `scoped_transport` permission. No new permission name exists for providers because a provider transfer *is* a scoped transport.

## 4. The security surface

`security_scope` is a closed enum. This revision admits `commissioned_connection` only: the provider surface may touch the one commissioned connection the descriptor's `connection_key` resolves to. Filesystem paths, process spawning and unrestricted network endpoints are unrepresentable in the schema — not discouraged, unrepresentable — which makes "no direct unrestricted SDK/filesystem/network access" (extension-contract §6) a machine-checkable property of every admitted contract rather than an aspiration.

## 5. Host requirements

`host_requirements` is the reviewed statement of what the host-side implementation needs: native library names with exact versions and any privilege claims. This is where a vendor SDK lives — **host-side, named and reviewed**. The plugin never imports it: plugin code runs under the admitted-import rule (stdlib only), so a vendor SDK cannot be plugin payload. This is why the lane is *host-provider*, not plugin-provider.

## 6. Review and admission — two tiers, both named

The **mechanism** — this schema, these rules, the descriptor object — is corpus content and moves under standards governance (drift gates, family suites, validation reports). Each **provider contract instance** is admitted by the host operator as a commissioning-class act: the document's `approval` block (`approved_by`, `approved_at`, `expires_at`, `evidence[]` in the commissioning evidence shape) records the review; the host's admission record grants authority. A descriptor pinning a contract the host has not admitted is an admission failure — unknown required features fail admission, and device-supplied metadata cannot add a transport provider on its own. An expired approval is not an admitted contract.

## 7. The offline boundary

Offline checks (the SDK lane) can prove a provider declaration **well-formed and self-consistent**: the schema shape, the feature-id agreement, the pin resolving inside the package to bytes that hash to `sha256`, and the pinned document passing the contract schema. Only the gateway can prove the **grant**: that `connection_key` resolves to a connection backed by the same admitted contract (exact id, version and digest), and that live transactions match the admitted grammar within `security_scope`. Commissioned state and the provider runtime live there. An offline pass is not an admission claim.
