# Issue #147 increment 3 — gateway admission and grant (slice-level design)

- Date: 2026-09-23
- Status: design (pre-implementation; no code exists for this slice; this record is
  the builder's commit one)
- References: the #147 design of record
  (`.claude/deep-review/2026-09-22-issue147-transport-provider-contracts.md`, SDK-side
  copy is the one carrying the heal-path amendment), gateway issues #147, #155/#157
  (landed slice 1), #166, #167, #169; corpus OTDP 0.2.2 at branch tip `a103a4c`
- Grounding window: **the #147 corpus landing to main has NOT happened.** All
  corpus/branch claims below were read from `origin/feat/147-transport-providers`
  (tip `a103a4c`) and SDK `origin/fix/147-fold-sync` (tip `7fc1848` == SDK main at
  reading time) via `git show`; all gateway-source claims were read from the merged
  main working tree (`baeb179`, which contains PR #157 and PR #164 but not PR #165 —
  a recovery-side fix, orthogonal to every surface here). Claims that depend on
  post-landing state are marked **[post-landing]**.

## Owner summary (BLUF)

**Verdict: BUILD, as one increment (PR C), ordered admission-first.** The gateway
today enforces none of the provider lane (zero `required_features`/`connection_key`
reads in `src/` — re-verified this session), the corpus 0.2.2 text names increment 3
as the moment `security_scope` becomes a boundary, and every mechanism needed is a
proven in-tree pattern (the CON-10 admission mirror, the capture-services permission
gate, the exact-byte decoder). Fork calls: (1) the commissioned settings surface is
realized NOW as gateway-local validated configuration — identity only, endpoints and
secrets stay unrepresentable; (2) the #166 lock↔manifest version gate does NOT belong
in this increment — it already exists main-side and is CI-wired, the SDK-side half is
structurally unbuildable, and PR #169's governance makes the dev-head carve-out moot;
(3) no corpus bytes move. Slice shape: one increment, internally ordered
admission → grant; the split seam is named below as a fallback only.

## 0. Grounding — verified against code and corpus this session

1. **The merged slice-1 gate exists and is the construction precedent.**
   `src/benchweave/content/capture_services.py` (main, PR #157):
   `build_capture_services` re-derives the RAW descriptor by pinned digest (one
   `get_document` — the CON-10 projection drops `integration`, so the raw form is the
   only permission source), reads `adapter_permissions` from
   `src/benchweave/control/documents.py`, and returns the eight-member capture bundle
   or the five-member scoped bundle with **no capture attributes at all** —
   structural absence, not a runtime flag. The streaming sibling
   (`build_stream_services`, `content/stream_services.py:414`) gates `event_sink` the
   same way. The docstring names the governing decisions A11/A17.
2. **The transport injection seam already exists.**
   `ScopedServicesBundle.__init__` takes `transport: Any = None`; `transfer` and
   `close_transport` delegate to the injected provider or raise `NotImplementedError`
   ("no transport is bound to this session's services"). The grant for a provider
   transport is therefore an OBJECT, not a protocol change: the injected transport
   becomes a grammar-guarded adapter over an admitted contract. The bridge's
   `OTDPBridge.__init__` (`host/otdp_bridge.py:5497`) takes `capture`/`stream`
   controllers and `services`; capture/stream flow through controllers, never through
   `self._services` (§0.3 of the #43 record).
3. **The activation gap is live and stays disclosed.** `build_capture_services` and
   `load_otdp_plugin` (`registry/otdp_loading.py:170`) have ZERO production callers —
   `git grep` over `src/` shows only tests (`tests/unit/test_capture_services.py`,
   `tests/integration/test_otdp_loading.py`, `tests/faults/test_capture_forensics.py`,
   `tests/unit/test_otdp_bridge.py`). Issue #167 carries the activation wiring. This
   increment adds enforcement at the seams that exist; it does not close row 9 and
   does not claim to.
4. **The gateway enforces no descriptor-feature surface today.** `git grep` over
   gateway `src/`: zero occurrences of `required_features`, zero of `connection_key`,
   zero of `scoped_transport`. `_check_semantic_mirrors` (`control/documents.py`)
   mirrors S01/S02 only. The #147 record's grounding 9 still holds on merged main.
5. **The corpus 0.2.2 lane is complete on the branch and names this increment.**
   `origin/feat/147-transport-providers:standards/otdp/0.2.2/` carries
   `otdp-transport-provider.schema.json` (normative-listed), the `provider` object on
   `$defs/customTransport`, `examples/reference-provider.json` +
   `examples/reference-hid-meter.json`, and `transport-providers.md`, whose §4 says
   gateway admission (increment 3) "validates every provider document against the
   corpus schema before admitting it, so an out-of-scope value never reaches a grant.
   Until that admission lands, the enum is a corpus promise about what can be
   admitted, not a runtime claim." The manifest's otdp entry is active 0.2.2 stable,
   supersedes 0.2.1; 0.2.1 is frozen at the SDK-released bytes (the heal-path
   amendment).
6. **The SDK conformance half is on the branch and is the agreement target.**
   SDK `src/benchweave_sdk/validation.py` (`7fc1848`): `_check_provider_features`
   (the five census refusals), `_corpus_known_otdp_features` (derived from the
   vendored tree: feature-shaped consts swept from the descriptor schema + catalog
   profile ids), `validate_transport_provider` (schema + grammar-subschema
   meta-validation + kind-string uniqueness + the reserved-seven disjointness + the
   three identity equalities), `verify_provider_pin` (descriptor-relative, strict
   no-follow, bounded read, hash, agreement). The six refusal prefixes are
   STD-4-listed **SDK-side** (`benchweave-sdk/docs/internal/invariants.md:36`) —
   increment 2 amended the SDK's list; main's invariants carry no STD family, so the
   gateway-side prefix set amends **CON-1** here.
7. **The commissioned settings sentence has no realization in-tree.**
   `standards/execution/0.1.0/execution-contract.md:100`: "The connection key
   resolves through administrator-owned transport settings and secret storage; it is
   not an endpoint supplied by the procedure." Verified: no `settings` object in
   `commissioning.schema.json` or `bench.schema.json`; the bench `devices` items
   carry only `{id, generation, descriptor-pin}`. Nothing in gateway source reads any
   connection configuration. This increment realizes the **settings-derived identity
   axis** of that sentence (which contracts are admitted, which connection_key binds
   to which) and leaves the endpoint/secret axis unrepresentable (see §1.2).
8. **The equivalence census is the agreement vehicle.**
   `tests/sdk/test_descriptor_equivalence.py` runs the gateway leg through the REAL
   `admit_documents` over the fixture lattice against the SDK check CLI in-process,
   with the sanctioned gateway-stricter cells named in the module docstring
   (currently one: `issued_map:`). PR A [post-landing] extends it with the provider
   lattice over the 0.2.2 example set; increment 3 adds the gateway admission legs
   and the new sanctioned cells.
9. **The exact-byte decoder is strict UTF-8.** `content/json_document.py` decodes
   `raw.decode("utf-8")` inside the `invalid_json` catch: a UTF-16/BOM provider
   document is refused by the gateway lane (the SDK's bounded reader admits them —
   RedTeam EN-3). That asymmetry is real, one-sided, and gets PINNED as a sanctioned
   census cell rather than "fixed" (§3, metric A).
10. **The #166 gate already exists main-side.**
    `src/benchweave/standards/check.py:112-118` (`_compare_lock`) raises
    `sdk_version_mismatch: <id> manifest <v> vs SDK lock <v>` whenever the SDK lock's
    version disagrees with the freshly exported corpus manifest, and
    `make check-sdk-standards` runs it in the `gates` and `package` CI jobs
    (`.github/workflows/ci.yml:61`, `package.yml:40`; the drift doc's CI map row
    `gates` names it "main standards ↔ SDK lock ↔ vendored tree"). The SDK repo
    cannot host it: its own CI comment (`benchweave-sdk/.github/workflows/ci.yml:55`)
    says the check is "deliberately NOT here: this repository has no standards
    manifest" and defers to the parent. Full recommendation in §5.
11. **PR #169's dev-stage governance settles the dev-head half of #166's clause.**
    `origin/feat/devstage-standards` GOVERNANCE "The dev stage": "The SDK never
    consumes `-dev` bytes: immutability starts at release, and a lock pinned at a
    `-dev` version would have to churn its version per edit or carve an exemption
    into the same-version refusal — neither is sanctioned." A lock at a declared dev
    head is therefore not a legal state under the landing governance — the version
    gate needs no dev carve-out (§5).
12. **Governance roles.** PR #169 [post-landing] adds GOVERNANCE "Roles and
    authority": corpus-byte merges need a single human reviewer other than the author
    (standards-coordinator carve-out aside); the governor lane reviews, it does not
    rule. Increment 3 moves **no corpus bytes** (verified in §4), so the mandatory
    governor lane is not triggered; the PR carries ordinary code review plus the
    repo's code-reviewer with its docs-coverage duty (this record, the CON-1/CON-10
    amendments, the drift-obligation rows).

## 1. Mechanism

Three pieces, each an extension of a named in-tree mechanism. Everything is
deterministic code; nothing depends on agent judgement at run time (A04 is
satisfied by construction — the refusals are structural, the grant is arithmetic on
admitted state).

### 1.1 The admission seam — the CON-10 mirror grows the provider rows

Home: `src/benchweave/control/documents.py`, extending `_project_full_form` /
`admit_documents`.

**(a) The census mirror.** A `_check_provider_mirror(logical, descriptor, admitted)`
sibling of `_check_semantic_mirrors`, mirroring the SDK's `_check_provider_features`
refusal-for-refusal and in the same order: the sanctioned-namespace shape row
(`provider_transport_undeclared:`), the §6.4 placement row (provider requires
adapter mode — run even on schema-refused documents, the S19 posture the SDK's
`validate_descriptor` except-branch establishes), `provider_feature_missing:`, the
orphan `otdp.transport.*` sweep with the SDK's effective-declaration determinization
(declared on the `custom` transport of an adapter-mode integration), and
`unknown_otdp_feature:` closure. The known set is the **two-layer union**:

- layer 1, corpus-known — a gateway mirror of `_corpus_known_otdp_features`,
  derived from the gateway's OWN vendored tree (feature-shaped `const` sweep of the
  vendored descriptor schema + the vendored catalog's profile ids), never
  hand-listed;
- layer 2, host-admitted — the feature ids of the contracts in the operator's
  admitted set (§1.2).

The SDK proves the declaration **well-formed** (layer 1 + declaration consistency);
only the gateway can prove it **admitted** — and the admission proof is the TRIPLE
ROW of (b) below (`_check_provider_admission`: exact id+version+sha256 against the
operator's admitted set), which never consults the union. Layer 2's role is
narrower and different: it extends the KNOWN-FEATURES closure (the
`unknown_otdp_feature:` row) so a feature declared through an admitted contract is
not refused as corpus-unknown — it is not the admission proof, and the census
mirror's union would not catch an unadmitted contract. *(Fold wave D correction,
2026-09-23: the original text attributed admission proof to layer 2; the
commissioned state the triple row checks is what admission means.)* This is the
two-layer model of the record §1.2 / transport-providers §6 made executable, and
it is why the two lanes legitimately disagree on one cell: a well-formed
descriptor pinning a contract the host has not admitted is SDK-clean and
gateway-refused.

**(b) The gateway-only admission row.** New refusal prefix `provider_not_admitted:`
— a gateway-owned prefix in the `issued_map:` tradition (the SDK cannot see
commissioned state, so no offline prefix exists and none is invented offline). It
fires, with typed detail naming the failed axis, when: the declared provider triple
`{id, version, sha256}` is not exactly an admitted triple; the approval block is
expired (checked against a caller-supplied `now_wall` — A04's arithmetic-on-declared-
values posture; "an expired approval is not an admitted contract",
transport-providers §6); or `connection_key` does not resolve to a connection bound
to the SAME admitted contract (the S12-extended row: exact id+version+sha256). A
missing settings document (the closed default) refuses every provider-declaring
descriptor with this prefix — missing requirements block control rather than
defaulting (A02).

**(c) The pin and instance verification.** A `_verify_provider_pin` mirror of the
SDK's `verify_provider_pin`, run at descriptor admission (the S14-family gateway
row): resolve the pin descriptor-relative (the descriptor's own directory —
`admit_documents` holds `descriptor_paths[device_id]`), strict no-follow on symlinks
(the SDK's stricter posture — the record's disclosed divergence now holds on BOTH
sides, knowingly), hash the bytes against the pinned `sha256`
(`provider_contract_hash_mismatch:`), decode through the **exact-byte decoder**
(duplicate keys, non-finite numbers, size, strict UTF-8 — BOM/UTF-16 refuses here
and only here), then validate the document against the vendored
`otdp-transport-provider.schema.json` (resolved manifest-derived, the
`_descriptor_validator` pattern extended with a second normative-name lookup) plus
the mirror checks the SDK performs beyond the schema: grammar-subschema
meta-validation (Draft 2020-12), kind-string uniqueness, disjointness from the
hand-carried reserved-seven frozenset (mirrored with its own spelling test — extends
record deferral 8), and the identity equalities — the three corpus equalities plus
the declaration-agreement pair (`feature_id` AND `id` must equal the descriptor's
declaration: the AR-6 "SDK-added fourth equality" is KEPT gateway-side, decided
knowingly — the pin names the reviewed document, and the gateway is the authority
moment for that name). Refusal prefix `provider_contract_invalid:` /
`provider_contract_missing:` as in the record's table.

**(d) Signature change.** `admit_documents` gains one keyword:
`provider_settings: Path | None = None` — the operator's settings document (§1.2),
validated BEFORE any descriptor is projected (fail-at-startup, the #85 CON-1
amendment posture: `bootstrap.admit_fixture_lattice` passes
`fixtures_dir / "transport-settings.json"` when the optional file exists, `None`
otherwise). The CON-10 projected view does NOT change: transport and provider stay
unprojected; the grant seam re-derives the raw form by digest exactly as
`build_capture_services` already does for permissions.

**Build-time amendment (fold wave B, 2026-09-23): the run path.** The record above
named only bootstrap as the settings carrier; the run factory
(`app._build_run_factory` → `_spool_documents` → `admit_documents`) is the fourth
admission caller and was silently outside the design. Folded: the run spool resolves
a provider-declaring descriptor's pinned contract from the ORIGINAL descriptor's
side (by digest over the fixtures' descriptor family — the bootstrap resolution
pattern), verifies it against the pin, and writes it into the spool at the pinned
relative path (the pin is descriptor-relative and the spooled descriptor lives at a
new filename — without the spooled contract, run admission misattributed
`provider_contract_missing:` to a package that has the file); `_spool_documents`
threads the fixtures' optional `transport-settings.json` as `provider_settings` and
`build_run` supplies `now_wall` from its wall callable. Resolution failures inside
the spool helper return silently — admission then refuses with its own honest
prefix against the spool's true state. The run path and bootstrap apply one
standard; pinned by `tests/integration/test_run_path_provider.py`.

### 1.2 The commissioned settings surface NOW — `transport-settings.json`

**Increment 3 is the moment for the identity axis, and no earlier than it.** The
record's gateway-side rows (known-features growth, S12-extended) are unenforceable
without a concrete carrier for commissioned state, and untestable without one; the
#43 retention-policy precedent (owner call 2) is exactly this shape: gateway-local
validated configuration now, corpus/commissioning promotion on a named trigger
(record deferral 3 keeps its home and trigger — the operator document admitting a
provider instance bench-side stays an execution-standard-queue item, triggered by
the first provider implementation).

The document: an operator-owned, optional `transport-settings.json` in the fixtures
directory (the administrator-configuration locus — `bench.json`,
`commissioning.json` live there), gateway-schema-validated (a schema in gateway
source, NOT corpus — provider instances are deliberately versioned elsewhere),
`additionalProperties: false` throughout:

```json
{
  "config_version": "1",
  "admitted": [
    {
      "id": "urn:otdp:transport-provider:reference-hid:1.0.0",
      "version": "1.0.0",
      "sha256": "<64 hex>",
      "feature_id": "otdp.transport.reference-hid/1.0.0",
      "document": "providers/reference-provider.json"
    }
  ],
  "connections": [
    {"connection_key": "power_meter", "provider_id": "urn:otdp:transport-provider:reference-hid:1.0.0"}
  ]
}
```

- `document` is settings-relative; the gateway decodes those bytes through the
  exact-byte decoder, requires the digest to equal the triple's `sha256`, and
  schema-validates the instance — the operator's admission record and the reviewed
  bytes are one act, deterministically checkable.
- **There is no field that can name an endpoint, path, process, credential, or
  secret — by schema, not by policy.** The surface carries identity only
  (contract triple + connection_key binding). Extension-contract §6's "API 1.1 does
  not grant direct unrestricted SDK/filesystem/network access as a shortcut" stays
  truthful in the only way that survives review drift: the increment-3 surface
  cannot express the thing it must not grant. Endpoint and secret configuration
  arrives with the first runtime implementation through deferral 3's operator
  admission surface, never here.
- Nothing in the execution lattice pins this file (no bench/commissioning pin).
  Disclosed: its authority is the operator's file act plus its internal consistency;
  promotion into the commissioning shape (pinned, expired with the commissioning)
  is deferral 3's. `validation.py` owns the typed refusals (`settings_schema:` /
  `settings_digest_mismatch:` family, machine-matchable like every other
  admission refusal).

### 1.3 The grant — the grammar guard at the component boundary

Home: a new `src/benchweave/content/provider_transport.py` (beside
`capture_services.py` — the content package owns the services-bundle family), plus a
`build_capture_services` extension.

**(a) The permission gate extends by structural absence.**
`build_capture_services` gains `providers: ProviderRegistry | None = None` (the
validated §1.2 object). When the re-derived raw descriptor declares a provider, the
factory:

1. requires `scoped_transport` in `adapter_permissions(raw)` — else the bundle is
   constructed with `transport=None` as today, and `transfer` raises its existing
   `NotImplementedError`; the refusal names the permission. No new permission name
   exists (a provider transfer IS a scoped transport — record §1.3);
2. requires the registry to resolve `connection_key` to a connection bound to the
   descriptor's exact admitted triple — else `transport=None` with the same loud
   refusal shape (the admission seam already refused this descriptor; the gate
   re-checks because the construction seam must not trust its caller — the same
   defense-in-depth `load_otdp_plugin` practices re-hashing entry bytes);
3. constructs the guard and binds it as the bundle's `transport`.

**(b) The guard.** `ProviderTransport` implements exactly the two members
`ScopedServicesBundle` delegates to (`transfer`, `close_transport`):

- `transfer(transaction, context)`: refuse a non-object or kindless transaction;
  refuse a kind not in the admitted contract's grammar ("extends the table, never
  shadows it" — transport-providers §3); validate the transaction against the kind's
  `request_schema` (Draft 2020-12); then delegate to the injected runtime — and when
  no runtime is injected, raise `NotImplementedError` naming the missing runtime and
  the issue lane ("provider implementations are a separate act"). With a runtime
  (tests and, later, real implementations), validate the result against the kind's
  `result_schema` before returning — a misbehaving host-side runtime cannot launder
  a malformed result into the adapter.
- `close_transport`: delegate when a runtime is bound; a no-op when not (nothing
  was opened — raising here would poison a session that never had transport).

The guard sits INSIDE the existing transfer envelope — the bridge's dispatch
markers, deadline, cancellation and transmission evidence wrap
`services.transfer`, so every provider transaction inherits them (record §1.3's
"for free" claim, verified against the bridge's dispatch path this session). The
descriptor's `settings.protocol_reference` is review-read metadata; the guard never
consumes it. `security_scope` needs no runtime check: `commissioned_connection` is
the only enum value and the guard has no other capability to exercise — the
boundary is the object's shape.

**(c) What the grant hands the adapter: nothing structurally new.** The adapter
calls the same `HostServices.transfer` with provider-kind transactions; the grammar
— not any implementation — is the contract (record §1.5's three-backend
composition: the gateway guard, a future standalone backend, and the SDK MockHost
all speak the same admitted grammar; MockHost scripts it today with zero SDK
changes).

## 2. Standards impact — none (verified)

Increment 3 moves **zero corpus bytes**: the vendored 0.2.2 descriptor schema, the
provider schema, the examples and the prose all arrive with PR A + the submodule
pointer + `make sync-sdk-standards` [post-landing]; the gateway mirror derives
corpus-known features and the provider schema from the vendored tree by the
manifest, exactly as `_descriptor_validator` does — there is no gateway constant
that could drift. No OTDP bump, no train window, no SDK-tree change, no scaffold
change (provider-less descriptors are untouched by every check above). The SDK's
STD-4 already lists the six prefixes (increment 2); the gateway-side prefix
amendment lands in main's CON-1 (§4). One disclosed prose consequence: 0.2.2
`transport-providers.md` §4's "until that admission lands" clause and §1's "the
prefix ports with increments 2 and 3" are satisfied by this increment — frozen
versioned prose is not edited in place; the refresh rides the next OTDP bump
(deferral 5 below).

## 3. Measurable proof — pre-committed acceptance rule

Written before any fixture named here exists and before any number was looked at.
The record §4's floor extends; its lattice is this design's fixture source.

**Metric A — census agreement (the drift proof).** The provider fixture lattice of
the record §4 metric 1 (12 fixtures: 4 valid, 8 single-fault), plus the in-tree
descriptor corpus, run through the REAL `admit_documents` (with a settings document
admitting the corpus reference provider) against the SDK check lane in-process.
Requirement: 12/12 accept/refuse agreement between the gateway leg and the SDK leg;
every SDK refusal carries its named prefix from the record's table; the two
sanctioned gateway-stricter cells — `provider_not_admitted:` (admission is
gateway-only) and the strict-UTF-8 decode (BOM/UTF-16 provider documents: SDK-clean,
gateway `invalid_json`) — are pinned by name in the census docstring (the CON-10
convention that every asymmetric cell is named). Additionally the derived
corpus-known feature sets (gateway mirror vs SDK `_corpus_known_otdp_features` at
the same vendored version) must be EQUAL — a one-line set comparison test.
- **Ship:** 12/12 + correct prefixes + set equality + both cells named.
- **Kill:** any disagreement, missing/wrong prefix, set inequality, or an unnamed
  asymmetric cell — the increment does not ship as-is; either the mirror or the
  corpus text is wrong; fix before merge. Population, not sample: the 8 are the
  enumerated single-fault permutations.

**Metric B — RED control (the mechanism proof).** Neutralize ONLY the provider
mechanisms (API-preserving no-op bodies in `_check_provider_mirror`,
`_verify_provider_pin`, the settings validator, and the grant gate's three
checks — a raw file revert makes the lattice uncollectable; the re-instrument
clause from the record §4 applies): the 8 invalid fixtures must stop refusing with
their named prefixes, the `provider_not_admitted` arms must pass, and the grant
arms of Metric C must flip as specified; restore, green again. Paste both runs
(collected counts; `no tests ran` is a FAILED check).
- **Ship:** refusals vanish on revert and return on restore.
- **Kill:** refusals surviving the revert mean the measurement tests the wrong
  layer — underpowered/mis-instrumented, not conclusive; re-instrument before any
  conclusion. No ship on a failed RED.

**Metric C — the grant gate (five arms, each with its own RED ablation).**
On the construction seam (`build_capture_services` with `providers=...`):
(1) full grant — provider + `scoped_transport` + admitted + resolved key → guard
bound; out-of-grammar kind refused; schema-violating request refused; well-formed
transaction reaches an injected fake runtime; malformed runtime result refused;
(2) no `scoped_transport` → `transport=None`, transfer raises, and the refusal
names the permission (RED: delete the permission check → this arm fails);
(3) contract not admitted → `transport=None` (RED: delete the triple check);
(4) `connection_key` bound to a DIFFERENT admitted contract → refused (RED: delete
the resolution check — arms 3 and 4 must fail independently);
(5) empty registry → refused. Fixtures use invented names (`watt-link`,
`meter-probe`); corpus `reference-*` examples are reused where the bytes matter.
- **Ship:** all five arms green; each RED ablation flips exactly its arm.
- **Kill:** any arm passing without its mechanism, or any RED ablation that flips
  another arm — the gate is mis-factored; fix before merge.

**Underpowered signal (pre-committed):** if Metrics A–C pass first-try with zero
fixes anywhere in the increment, treat the lattice as too weak — add the multi-fault
compositions (record deferral 6) before shipping. A mechanism this shape should
catch at least the hash, orphan and admission cases distinctly.

## 4. Invariant and drift impacts

- **CON-1 amendment:** descriptor admission gains the provider rows (census mirror,
  pin/instance verification, host-admission row); the machine-matchable refusal set
  gains the six SDK prefixes riding inside the existing family prefixes plus the
  gateway-owned `provider_not_admitted:`; provider documents and the settings
  document decode through the exact-byte decoder. The settings-validator's own
  prefixes (`settings_schema:` / `settings_digest_mismatch:`) join the same list.
- **CON-10 amendment:** the equivalence census extends to the provider lattice; the
  sanctioned gateway-stricter cells grow to three named cells (`issued_map:`,
  `provider_not_admitted:`, strict-UTF-8 decode); the projection itself is
  UNCHANGED (transport/provider stay unprojected; the grant re-derives the raw
  form — the existing permissions precedent).
- **CON-2 untouched:** the provider pin lives inside the descriptor, transitively
  pinned by the bench pin; no new lattice edge.
- **Drift obligations:** obligation 15 (the branch's pairing-constraint row) is
  satisfied on its gateway half — the census named there stays green across the
  pair; new rows for (a) the `transport-settings.json` surface (validated,
  identity-only, promotion trigger = deferral 3) and (b) the gateway's
  hand-carried reserved-seven frozenset spelling test (extends record deferral 8 to
  both sides).
- **CI cost:** no new job. Growth only: the equivalence module's provider lattice,
  a documents-test provider arm set, the settings-validator tests, and the grant
  test module. Runtime cost negligible (schema validators cached as today).

## 5. The #166 gate — recommendation: NOT this increment; mostly already built

The owner asked for a ruling inside this design's scope. The evidence:

1. **The lock↔manifest version-agreement gate exists main-side and is CI-wired.**
   `_compare_lock` refuses `sdk_version_mismatch` on any lock-version vs
   manifest-active-version disagreement, in the `gates` and `package` jobs. It
   fired on this very drift — the #147 record's build-time amendment counts the
   56 failures, `sdk_version_mismatch` among them. #166's "no gate cross-checks
   the version axes" is imprecise: no gate cross-checks them **SDK-side**, because
   the SDK repo has no standards manifest (its CI says so verbatim) — a SDK-side
   gate is structurally unbuildable, not merely missing.
2. **The dev-head clause is settled by PR #169's governance, in the simpler
   direction.** The dev stage never reaches the bundle, lock, or vendored tree;
   a lock pinned at a dev version is unsanctionable. The gate therefore needs NO
   dev carve-out: a lock version that is not the manifest's active version refuses,
   unconditionally. #166's "or an explicitly declared dev/wip stage" alternative is
   moot — implementing it would contradict the landing governance.
3. **The residual #166 gap is temporal, not checkable at this seam.** The window
   the issue actually caught: the SDK released a version whose corpus authority was
   an unmerged branch (the ratified fork-F3 landing order makes the window
   structural). Main-side CI checks the pinned SHA, so it stays green during the
   window; the SDK publishes on its own green. No check living in either repository
   can see "the corpus this version came from is unmerged" at publish time without
   a cross-repo network dependency the SDK deliberately lacks.

**Recommendation:** close #166 item 2 as already-built-with-evidence (the
`sdk_version_mismatch` citation + the PR #169 governance ruling), fold the
residual window disclosure into #166 item 1's reconciliation (which the PR A
landing itself completes — corpus 0.2.2 active == SDK lock 0.2.2), and if the owner
wants the window itself machine-gated, that is a #166-scoped CI-ordering increment
(e.g. allowing `sdk_version_mismatch` only on PRs that move the pointer and the
manifest together) — a workflow file change, neither admission surface nor SDK
tooling. It does not belong in increment 3: wrong invariant family (sync tooling,
not CON-1/CON-10), wrong review lane, and coupling it would hold this increment
hostage to a workflow ruling. **Dev-head interaction with THIS admission surface:
none.** Gateway admission derives the active vendored schema from the vendored
manifest (post-sync); a descriptor whose corpus is at a dev head is unreachable
here by construction — dev bytes never vendor, so the gateway cannot see them.

## 6. Deferrals — each with home and reopen trigger

| # | Deferred | Home | Reopen trigger |
|---|---|---|---|
| 1 | Runtime provider implementations (USB-HID host provider, vendor-SDK bindings, the webcam integration) — record deferral 2 stands; the guard's runtime parameter is the injection point | Per-device gateway issues | First real device commissioned through the lane |
| 2 | Execution-side commissioning shape for provider-backed connections (commissioning-pinned promotion of `transport-settings.json`, secret storage, endpoint configuration) — record deferral 3 stands; the interim carrier is this increment's gateway-local document, identity-only | Execution-standard queue | First provider implementation |
| 3 | `st_nlink` hardlink posture (record §8 PT-1): not added — the settings directory is operator-controlled and the pin's security is the sha256; recorded posture, not an oversight | Gateway tracker (single stream) | The provider document source becomes plugin/caller-supplied rather than operator-file-supplied |
| 4 | Reserved-seven frozenset census fixture (derivation-vectors style) — both checkers hand-carry the set with spelling tests; extends record deferral 8 to both sides | Gateway tracker (single stream) | The §8.1 generic table grows |
| 5 | Corpus prose refresh — 0.2.2 transport-providers §4's "until that admission lands" and §1's prefix-port sentence are satisfied by this increment; frozen prose is not edited in place | Next OTDP bump train | Any semantic OTDP bump |
| 6 | Multi-fault compositions + provider-grammar fuzzing (record deferral 6) | Follow-on | The §3 underpowered signal fires |
| 7 | The #43 row-9 activation gap — production wiring of the whole chain (bridge construction over the worker store) including the provider grant's first production call site. Scope note (fold wave E): the grant gate has NO expiry axis — admission judges approval expiry at admit time against `now_wall`; a gate-side re-check (the gate re-derives the triple the way it re-checks permission and resolution) is #167's FIRST item, landing with the gate's first real caller rather than speculatively now | Issue #167 | First real capture-class or provider-backed plugin |
| 8 | Draft-provenance check for grammar subschemas (dead Draft-07 keywords under 2020-12 — record §8 EN-7) | Gateway tracker (single stream) | A real provider contract authored off-corpus-tooling misses it |

## 7. Top risks — each with its falsifier

1. **The corpus's grant shape strains at the construction seam.** If the guard
   cannot express what the first real provider needs (device enumeration, buffer
   streaming), the transfer-grammar choice cracks (record risk 2). *Falsifier:* the
   first provider implementation needing a non-transfer call shape; then a
   services-surface row (new HostServices methods, adapter_api bump) opens as a
   design row, not a patch.
2. **The settings document grows into a shadow commissioning surface** (scope creep
   eroding deferral 3). *Falsifier:* any request for an endpoint/secret/credential
   field before the first provider implementation — refused and routed to
   deferral 3; the `additionalProperties: false` schema makes the creep
   unrepresentable rather than policy-checked.
3. **Result-schema validation rejects legitimate runtime results** (over-strict
   guard). *Falsifier:* the fake-runtime arms of Metric C failing on well-formed
   results — the fix is the CONTRACT's grammar (a 0.2.x provider-schema revision of
   the example), never a guard-side loosen switch; the reference-hid example
   grammar is the standing control.
4. **The two-layer known-features union drifts silently between the checkers.**
   *Falsifier:* Metric A's set-equality arm or an unnamed asymmetric cell appearing
   in the census — every asymmetric cell must be named (CON-10 convention); an
   unnamed cell is a merge blocker.
5. **Enforcement-without-activation looks like protection it is not.** Nothing in
   production constructs these objects yet (grounding 3); a reader could mistake
   admission enforcement for runtime enforcement. *Mitigation:* the record and the
   census docstring state the boundary; the guard's no-runtime refusal names the
   lane. *Falsifier for the disclosure itself:* the first production wiring (#167)
   finding a seam that cannot carry the registry — then this design's §1.3 shape
   was wrong and a follow-up design is owed.

## 8. Owner forks (surfaced, with recommendations)

- **F-166 — the #166 gate home.** Recommendation: not increment 3, not the SDK
  repo; close-as-built with evidence + the PR #169 ruling (§5). Alternative (if the
  owner wants the train window machine-gated): a #166-scoped CI-ordering rule.
- **F-slice — one increment or split.** Recommendation: ONE increment (PR C),
  internally ordered admission (§1.1) before grant (§1.3) — the grant is untestable
  end-to-end without the admission state, and both halves depend on PR A equally,
  so a timing split buys nothing. The fallback seam, if review bandwidth forces it:
  admission half (documents + settings validator + census) lands first, grant half
  (provider_transport + gate extension) follows on the same issue — never the
  reverse order.
- **F-secrets — settings surface scope.** Recommendation: identity-only NOW
  (§1.2); endpoints/secrets via deferral 3's operator admission surface with the
  first runtime. Alternative rejected: carrying endpoint strings in
  `transport-settings.json` from day one — it would put §6's no-direct-access
   sentence one schema-edit away from false, exactly the "unrestricted access by
   another name" the constraint bars.
