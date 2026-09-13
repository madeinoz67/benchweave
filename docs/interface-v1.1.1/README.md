# Interface corpus errata 1.1.1 (D2)

This directory is a **new, versioned revision** of the admitted interface
corpus — not an edit of `interface-v1.1.0`. The 1.1.0 corpus remains vendored
at `contracts/interface-v1.1.0/` with its bytes frozen; this revision is
vendored byte-identically at `contracts/interface-v1.1.1/` and recorded in
`contracts/manifest.json` as `identity.interface_errata: "1.1.1"`.

## Why the architecture identity stays 1.1.0

`identity.interface` remains `"1.1.0"` because the amendment changes no
architecture semantics: no operation, route, tool, error code, or permission
tier is added, removed, or re-tiered. The errata is a schema-level correction
of one REST request body, tracked as a separate revision so the frozen 1.1.0
corpus stays the auditable baseline and any consumer can pin either revision
by digest.

## The erratum (deviation register D2)

The 1.1.0 catalog's `change_apply` REST body schema declared
`{request_id, expected_generation, approval_ref}` with
`additionalProperties: false` — but the REST adapter forwards
`approver_token` (the detached approval credential, authenticated against the
`gateway-admin` audience independently of the applier's admin identity) from
the apply body into the seam's optional `approver_token` kwarg. Under the
1.1.0 schema a catalog-literal body can therefore never carry the credential
the seam fail-closes on (`forbidden` / `missing_token`): the body that
actually works was, per the schema, invalid.

The 1.1.1 revision admits reality: `change_apply`'s requestBody schema gains
an **optional** `approver_token` string property. It is deliberately NOT
added to `required` — the adapter extracts it with `body.get(...)` and the
seam accepts it as an optional kwarg, so a corpus-literal body without the
token must remain schema-valid (it fails later, and truthfully, at approval
verification). `required` and `additionalProperties: false` are otherwise
untouched.

## Scope

Exactly one schema changed:

- `openapi.json` — `change_apply`'s requestBody schema properties gain
  `approver_token: {"type": "string"}`; nothing else in the document differs
  from 1.1.0 (the whole-document semantic diff is pinned in
  `tests/contract/test_corpus_revision.py`).

Every other file (`mcp-tools.json`, `operation-catalog.json`,
`interface.schema.json`, the examples) is a byte-copy of 1.1.0: adding an
optional property to one REST-only body schema requires no bump inside them
(verified, not assumed — `change_apply` is REST-only, so no MCP tool
inputSchema and no catalog failure-code entry is affected).

## Provenance

- Source of truth: `docs/interface-v1.1.1/` (this directory).
- Vendored byte-identically into `contracts/interface-v1.1.1/`.
- Every vendored file is recorded in `contracts/manifest.json` with its
  sha256 (`shasum -a 256` over the vendored bytes).
- Integrity is pinned by `tests/contract/test_corpus_revision.py`: the
  revision byte-matches its docs sources at the manifest digests, the 1.1.0
  corpus bytes are unchanged versus git HEAD's manifest, and the 1.1.0
  corpus rejects the token-bearing body the 1.1.1 corpus admits.
