# Dataset/invoke lane design of record (issue #146)

**Date:** 2026-09-25 · **Issue:** [#146](https://github.com/madeinoz67/benchweave/issues/146)
**Design home lineage:** promoted from deferral row 2 of the #43 record
(`2026-09-21-issue43-capture-streaming-design.md`, Amendment 3).
**Corpus:** `standards/otdp/0.2.2` (spec §14, extension-contract §1–§5,
measurement-model §1/§7, runtime schema `$defs/operationRequest`/`operationResult`,
descriptor schema root `contracts`/`actions`/`capabilities`); execution corpus
`standards/execution/0.2.0` (the `invoke` step kind, present since execution 0.1.0).
**Verdict: BUILD** — as three slices (SDK protocol; gateway invoke dispatch;
gateway dataset services), with the guide obligations riding the gateway slices.
**No standards bump is implicated and none is wanted.** OTDP 0.2.2 already fully
specifies `invoke` and the dataset services; execution 0.2.0 already specifies the
procedure step. Every byte this design moves is host implementation, SDK protocol
surface, or guide prose. The corpus is read-only here, exactly as in #43.

This record is committed before any implementation runs, so the acceptance rule in
§7 is provably pre-committed.
**Amendment 1 (2026-09-25):** mechanism-critique fold — see the Amendment 1
section. **Amendment 2 (2026-09-26):** slice-2 review fold — see the
Amendment 2 section; R16's taxonomy corrected in place, §7 gained R18–R21.

---

## 0. Grounding corrections — checked against code and corpus, not the issue prose

The issue's framing is correct but understates how much of the lane already exists.
Checked against the tree at `main` = `4d8f718`:

- **The executor side of invoke is complete and has been since the activation
  train.** `_step_invoke` (`src/benchweave/control/executor.py:993-1032`) resolves
  input, records `resolved_input_sha256`, checks policy
  (`check_allowed(…, "invoke", action_id, resolved_input)` — the runtime
  `input_constraints` JSON-Schema intersection lives there,
  `control/policy.py:107-116`), builds `OperationRequest(verb=INVOKE,
  arguments={action_id, input})`, and dispatches. `OperationVerb.INVOKE` exists
  (`host/types.py:102`). The result projections (`data.result` for invoke,
  `executor.py:425-432`), `sample` over a `scalar_set` dataset
  (`executor.py:521-609`), and derived-variable appending to dataset-shaped
  results (`_apply_derivation`, `executor.py:1034-1082`, CON-9) are all live.
- **The execution corpus specified the invoke step before this issue existed.**
  Execution 0.1.0 line 34 already carried `invoke | Dispatch an exact OTDP class
  action on a bound role, with a positive timeout and structured input`; 0.2.0
  unchanged. The dormant-branch note at `executor.py:762-765` applies to the
  **capture** kind only (added by the 0.2.0 language extension) — invoke was in
  the initial language.
- **Binding, semantics, and the projection already do their half.** Binding
  refuses `undeclared_action` (`control/binding.py:154-159`); semantics sums
  invoke timeouts into the static body bound (`control/semantics.py:60`) and
  enforces `$stg_issue` placement against the descriptor's issued map
  (`semantics.py:211-233`, validated at `control/documents.py:302-332`); the
  CON-10 projection carries `actions` as `[{action_id, issued?}]`
  (`documents.py:851-863`). Semantic admission also enforces capture-declaration
  mirrors (`_check_capture_declared`) — the precedent an invoke admission mirror
  would extend, if one were needed (§4, D8).
- **The refusal site is exactly one dict lookup.** `OTDPBridge.dispatch` builds
  `supported = {identify, read, write, capture, stream_subscribe,
  stream_unsubscribe}` (`host/otdp_bridge.py`, the `supported.get(request.verb.value)`
  region); `invoke` falls through to
  `reject(UNSUPPORTED, "Bridge supports identify, read, write, capture and stream
  verbs")`. The bridge docstring already names the boundary honestly: "Dataset and
  profile semantics still need a native async host — … and the eventual
  invoke/dataset scheduling, explicitly NOT for capture/stream correctness."
  This design amends that sentence when slice 2 lands (the #43 Decision-1
  precedent for the docstring amendment).
- **The bridge receives the RAW descriptor.** `_BridgePlan(closure, descriptor,
  digest)` is built from `document["content"]` — the raw full form
  (`interfaces/app.py:616-621`), and the bridge's own constructor deep-copies it
  (`OTDPBridge.__init__` — the `self._descriptor = copy.deepcopy(descriptor)`
  line; `load_otdp_plugin` at `registry/otdp_loading.py:249-256` only passes it
  through — Amendment 1 citation fix). Invoke gating can therefore read
  `capabilities`, the `actions` map, and `contracts` directly at the bridge,
  exactly as the capture gate reads `capture_limits`/`capture_formats`.
- **The SDK protocol already reserves the seam.** `OperationContext.dataset_id:
  str | None` is declared in `benchweave_sdk/interfaces.py` and pinned by
  `tests/sdk/test_adapter_agreement.py` (`EXPECTED_CONTEXT_DATA`, and the pin at
  :437-439 asserting `context.dataset_id is None` "no dataset support in the
  synchronous host" — a pin this design consciously moves). The bridge's own
  `_Context` already carries `self.dataset_id = None`.
- **What does NOT exist, and is slice construction:** (a) any resolution of
  `descriptor.contracts` — the pinned catalog is never read, digest-verified, or
  schema-validated anywhere in the gateway today (the C01 leg is unbuilt; the only
  `contracts` hits in `src/` are the gateway's own interface-contract manifest,
  `registry/schemas.py:20`); (b) the bridge's invoke gate and result conversion;
  (c) any `dataset_publish`/`dataset_lookup`/`artifact_read`/`payload_*`
  implementation (zero hits in gateway source); (d) the SDK `DatasetServices`
  protocol; (e) measurement-manifest validation (the `measurement/` package is
  `derivation.py` only — no M-check validator exists, and measurement-model §7
  says plainly these are "author/host conformance obligations, not proof that a
  validator or driver already implements them").

**Consequence for scope:** this is NOT a new lane to be designed from scratch. It
is the last unimplemented verb of a lane whose procedure semantics, policy
intersection, budget arithmetic, projections, and derivation are already shipped
and pinned. The increment is: the bridge's dispatch half, the pinned-contract
resolution it gates on, the dataset services the corpus defines, the SDK protocol
shape, and the guide. Everything else is deferral or already-built.

---

## 1. What the corpus actually mandates (the design's authority)

From extension-contract §1–§3 and the schemas, the obligations that name host
behavior:

1. **Invoke is a typed, admitted envelope — not an arbitrary command endpoint**
   (§1). The gateway "validates the action before invoking the adapter and
   validates its result afterwards."
2. **The six §2 admission checks**: profile/feature resolution (the descriptor
   schema's own `capabilities: [invoke]` conditional already forces
   `channels/profiles/contracts/actions`, adapter mode, and
   `otdp.profile_actions/0.1.0` + `otdp.measurement/0.1.0` in `required_features`
   — schema-enforced at admission today); declared actions belong to an
   advertised profile; input matches the catalog schema ∧ descriptor
   `input_constraints` ∧ bench policy (policy ✅ at the executor; the rest is
   this design); lifecycle/ownership IDs hold (the issued-id machinery ✅);
   timeout/cancellation/retry/effect declarations supportable (✅ structurally:
   deadlines are honored, silent retry is refused by the adapter contract);
   result matches its catalog schema ∧ semantic postconditions including dataset
   rules (this design).
3. **The dataset services shape** (§3): `dataset_publish(manifest, context)`,
   `dataset_lookup(dataset_id, context)`, `artifact_read(artifact_id, offset,
   length, context)`, and `payload_create(encoding, byte_limit, context) ->
   str` / `payload_append(artifact_id, data, context)` /
   `payload_finalise(artifact_id, context) -> dict` /
   `payload_abort(artifact_id)`. The submitted `dataset_id` is host-reserved,
   derived from the current operation/acquisition, provided via
   `context.dataset_id`; the manifest must use it; a null value forbids
   publishing. `payload_*` requires `artifact_writer`; `artifact_read` requires
   `artifact_reader`. Finalise "computes and returns the artifact object (ID,
   encoding, byte length, SHA-256)". "Inline datasets also go through
   dataset_publish; small data is not exempt from semantic validation."
4. **Result honesty** (§2): "Result identity, channel, IDs and requested outcome
   must agree; a schema-valid result for the wrong acquisition is rejected.
   Unknown outcomes cannot be downgraded to success."
5. **The manifest schema** (`otdp-measurement.schema.json` `$defs/dataset`):
   closed 12-field object, `kind` ∈ the nine kinds, `configuration_id`/
   `acquisition_id` nullable strings, variables with required
   `{id, quantity, unit, channel_ids, dtype, dimensions, uncertainty,
   calibration, status}` and either inline `values` or a payload `artifact`
   `{artifact_id, encoding, byte_length, sha256}` (closed, 8-value encoding
   enum).

---

## 2. The mechanism

### 2.1 Pinned-contract resolution — the C01 leg (slice 2's foundation)

**New, named construction** (nothing resolves `contracts` today): at bridge
construction, `load_otdp_plugin` (or a sibling function it calls,
`registry/otdp_loading.py`) resolves each `descriptor.contracts` entry
(`{id, path, sha256}`) against the **already-verified bundle inventory** — the
loader verifies every file's digest at inventory build (`otdp_loading.py:201-218`),
so contract resolution is a lookup + sha256 compare + parse, never a filesystem
trust decision:

- The **action registry**: the contract whose parsed shape satisfies the vendored
  `device-profile-catalog.schema.json` yields `action_id -> {input_schema,
  output_schema, side_effect, lifecycle}` (the catalog's `actions` dict — 50
  standard actions, each embedding Draft 2020-12 input/output schemas with
  `$id`s; `device-profile-catalog.json`). Input/output validators are compiled
  once per bridge construction and cached (the `_descriptor_validator()` lazy
  singleton precedent, `documents.py`). External `$ref` retrieval stays disabled
  (§1) — jsonschema is constructed with `registry=None` semantics as every
  in-tree validator already is. **Resolution probe (Amendment 1, MEDIUM-3;
  family corrected by Amendment 2, adversary F2 + critic M):** structural
  validation alone never resolves embedded references — `Draft202012Validator`
  resolves lazily, so an unresolvable reference passes load and raises at I4,
  escaping `iter_errors` into the generic except as dispatch-time poison —
  inverting this section's earliest-boundary claim. The probe must model the
  RUNTIME validators' resolution exactly, in two dimensions Amendment 1's
  text missed: (a) it walks **`$dynamicRef` as well as `$ref`** (2020-12
  resolves both lazily; a dangling `$dynamicRef` passes a `$ref`-only probe
  and escapes the bridge uncontrolled at first invoke); (b) it **roots each
  reference the way the compiled per-action validator roots it** — the action
  subschema / nearest enclosing `$id`, never the document — a same-document
  relative ref passes a document-rooted probe and raises `PointerToNowhere`
  at dispatch, recording UNKNOWN for a pre-dispatch gate failure, the worst
  outcome class. Any unresolvable reference, either family, is an
  `ActivationRejected` at load (R14, R18, R19).
- The **measurement schema**: the pinned `otdp-measurement.schema.json`
  (identified by its `$id` urn / `$defs/dataset` presence) compiled for
  `dataset_publish`. **Degenerate identification is present-bytes-that-lie**
  (Amendment 2, F4): a pinned document claiming to be the measurement schema
  whose `$defs/dataset` required set has degenerated to empty or absent is a
  HARD load refusal — a validator compiled against it would admit anything,
  so identification is checked, not assumed (R21).
- **Both-or-neither** (the CON-10 capture-keys precedent, `documents.py:864-888`):
  a descriptor whose pinned contracts yield an action registry but no measurement
  schema — or vice versa — constructs **no class controller**: a half-declared
  class surface grants no class surface. `invoke` refuses UNSUPPORTED. The
  refusal is structural, never a runtime flag.
- Any digest mismatch, unparsable JSON, catalog-schema failure, or unresolvable
  `$ref` (the probe above) is an `ActivationRejected` **at load, before any
  dispatch** — M14/C01's "unknown required contracts are rejected, not treated
  as opaque success," enforced at the earliest boundary.
- **Multi-catalog refusal (Amendment 1, NIT-2):** a descriptor pinning more
  than one catalog-shaped contract is REFUSED at resolution — overlapping
  `action_id`s across catalogs would let registry merge order silently pick
  the `input_schema` that gates I4. The precedence question is closed by
  refusal, not resolution, and is disclosed in §6 row 8.
- **Inventory threading (Amendment 1, NIT-1):** the verified inventory is a
  local inside `load_otdp_plugin` — resolution takes it as an explicit
  argument wherever it lands, never a module global or a filesystem re-read.

Precedent extended: the loader's own verified-inventory mechanism (trust), the
vendored-schema validation pattern (shape), the capture both-or-neither posture
(policy). No new trust decision exists in this step — the bytes were already
digest-verified before the adapter module was even imported.

### 2.2 The dataset controller and bundle (the composing object, §0.3 shape)

One new module `src/benchweave/content/dataset_services.py`, the direct sibling
of `capture_services.py` (its `ScopedServicesBundle`/`CaptureController`/
`build_capture_services` triad is the precedent, structure for structure):

**`DatasetServicesBundle(ScopedServicesBundle)`** — the SDK §3 shape, one bundle
per plugin session, constructed by permission:

- `payload_create(encoding, byte_limit, context) -> str`: validates `encoding`
  against the manifest artifact enum and `byte_limit` as an exact-type int
  ≥ 1 ≤ 2^53−1 (the `_exact_int` gate discipline); the **host mints** the
  payload staging id `pay:{operation_id}:{n}` (n = per-session counter; the
  `cap:`/`op:` minting precedent) — the adapter never names staging ids; opens a
  staged writer entry with allowance `min(byte_limit, max_dataset_bytes − used)`
  — and **refuses `not_dispatched` at create when `byte_limit` exceeds that
  allowance** (owner ruling on MEDIUM-1: refuse-at-create, capture's G3 parity
  — never silently reduce; `payload_create` returns `str`, corpus-fixed, so a
  reduced ceiling would be undiscoverable by the adapter; R12). Note the
  **allowance formula differs from captures** by one term: payload bytes
  belong to the dataset budget and are NOT clamped by `max_capture_bytes`. Same
  table, same `staged` state, `format` column carrying the encoding,
  `sample_count` NULL — **no migration** (the `capture_staging` v5 schema's
  columns already admit this; see §5, Tier-3 note).
- `payload_append(artifact_id, data, context)`: the staged writer's append —
  reservation enforcement, incremental sha256, cancellation honored
  (`is_cancelled()` on every append, the §8 rule the writer already applies).
  A payload id from another session is refused (the writer keys on
  `context_key`; R7's isolation control).
- `payload_finalise(artifact_id, context) -> dict`: the writer's publish —
  returns `{artifact_id: "art-<sha256>", encoding, byte_length, sha256}`, all
  host-computed over the real bytes (G4's discipline: adapter-supplied digests
  are not inputs here at all).
- `payload_abort(artifact_id)`: idempotent local cleanup through the writer
  (§3's own words — unlike capture's forensic abort marker, which was a #43
  decision rather than a corpus mandate; payloads follow the corpus text, and
  the difference is disclosed here).
- `dataset_publish(manifest, context) -> dict` — the validation surface:
  1. `manifest` is an object; `manifest.dataset_id == context.dataset_id`,
     non-null — else refusal ("a null value forbids publishing"). The
     host-assigned id is the only publishable identity.
  2. Schema validation against the pinned measurement schema (closed dataset
     def, variables, axes, artifacts).
  3. The **M-check subset this increment implements** (§2.4): M01 structural
     references (unique axis/variable ids; channel references exist in the raw
     descriptor's `channels`), M02 length agreement (inline value counts vs
     dimension products; payload artifact `byte_length` vs the writer's
     published record), M03 encoding/dtype consistency (enum + artifact-record
     cross-check), M04 inline numeric finiteness, M10-id correlation subset
     (manifest `configuration_id`/`acquisition_id` must echo the invoke input's
     corresponding string fields when the action's input schema declares them),
     M11 artifact integrity — **scoped to the operation, not the session**
     (Amendment 1, MEDIUM-4): every referenced payload artifact is one THIS
     operation's writer published and finalised. The per-dispatch state makes
     the operation binding free, and it is required: an artifact finalised
     under a *prior* operation of the same session satisfies session-scoped
     existence while its bytes were acquired under a different acquisition —
     contra §1.4 — so it refuses (R15). Finalise-record cross-check, the
     two-sided-manifest discipline), M14 (already enforced by construction).
  4. Quotas (Amendment 1, HIGH-2): the serialized manifest is ROUTED THROUGH
     THE STAGED WRITER — a staging entry opened at the manifest's byte size and
     finalised within the same publish — so its bytes enter the `used` ledger
     (`Σ reserved staged + Σ charged finalised`, `capture_store.py:267-272`)
     and the published `art-<sha256>` row is the manifest's own storage path
     (one storage path, no migration). The original text's "manifest bytes
     charged to the dataset byte quota" had no mechanism: `used` sums
     `capture_staging` rows only and a bare `put_artifact` is invisible to it,
     so unbounded inline manifests — which need no `artifact_writer` — were
     never byte-refused, and §6 row 10's declination was false as specified;
     it is now true by routing (R11). An evidence row lands (kind `dataset`)
     under the host-minted run context key on the `(context_key, kind)`
     entries dimension — **shared with the run's `retain_evidence` rows AND
     the monitor's per-tick retention, disclosed** (Amendment 1, LOW-3:
     `monitor.retain` is armed at `app.py:403` to retain one kind-`dataset`
     row per monitor tick, so a step-heavy run can fill the dimension before
     any publish — starvation is real, cleanly refused, and the inverse
     degradation is the existing `evidence_gap`; splitting the dimension needs
     distinct evidence kinds, a corpus revision, exactly the #43 erratum's
     posture). Both quota numbers are `max_page_size × 10` by PARALLEL
     DERIVATION (`app.py:516` and `:709`) — slice 3 folds a one-source
     derivation plus a pin so the two cannot drift.
  5. Idempotency/immutability: byte-identical manifest under the same
     `dataset_id` returns the admitted manifest, no new rows ("an idempotent
     repeated fetch may return the already published manifest"); a different
     manifest under a used `dataset_id` is refused (the admitted manifest is
     immutable).
  6. The admitted manifest is recorded in the session's dataset state for the
     bridge's result cross-check, and returned.
- `dataset_lookup(dataset_id, context) -> dict`: returns the validated admitted
  manifest for datasets **this run published** (session state + evidence rows
  under the run context key). Unknown or not-this-run ids refuse. The
  cross-principal authorization model is a deferral (row 2).
- `artifact_read(artifact_id, offset, length, context) -> bytes`: present only
  when the adapter holds `artifact_reader` (structural absence otherwise — the
  §0.3/S15 pattern). Bounded windowed read — with the offset floor REFUSED
  here, never inherited from the seam (Amendment 1, MEDIUM-2): the interface
  seam CLAMPS negative integer offsets to zero (`interfaces/operations.py:
  353-360`, the pinned MCP behavior) and `ContentStore.artifact_chunk` itself
  enforces only length ≥ 1, the 65536 ceiling, and beyond-size refusal — a
  negative offset reaching the store's Python slicing reads the wrong window
  (measured: `offset=-1, length=1` → zero bytes, `eof=False`, a
  non-terminating read loop; `offset=-1, length=MAX` → the last byte). The
  corpus's "nonnegative offset" is a precondition this bundle REFUSES on
  (R13's boundary table), never clamps. Authorization subset: artifacts
  belonging to datasets this run published. Upload-capable consumption beyond
  that is a deferral (row 3).

**`DatasetController`** — the bridge-held facade (control flows here, never
through `self._services`; the pinned exercised subset stays `{monotonic}`):

- holds the compiled action registry + measurement validator (from §2.1);
- `dataset_id` minting and the per-dispatch state (`{operation_id, dataset_id,
  input, open payload ids, admitted manifests}`) the bundle's publish
  correlates against. **The payload-id registry is load-bearing** (Amendment
  1, HIGH-1): the writer's quota stamp binds its token to the *staging id*
  (`pay:{op}:{n}`), the controller is the only component that knows which ids
  an operation opened (it mints them), and the bridge's existing
  `_capture_originated` discriminator returns False whenever `capture_id is
  None` — true for every invoke — so without this registry every
  writer-originated resource condition raised during an invoke dispatch
  poisons the session today. The discriminator's dataset arm is therefore
  `stamp id ∈ this operation's open payload ids` (R10, both directions);
- `gate(request)` — §2.3's pre-dispatch checks;
- `dispatch_clamp` / `epilogue_floor` forwarding to the session's shared staged
  writer (the writer is the one instance per session, shared with the capture
  bundle exactly as `app.py:734-750` shares it today);
- `abort_open(operation_id)` — the failure-path reclaim of still-open payloads
  (the `_abort_contained` precedent, minus the forensic row per §3);
- `sweep_open(reason)` — `plugin_close`'s sweep;
- the C3-style stamp discipline for dataset-originated resource conditions
  (module token + operation binding — a bare or replayed raise keeps the poison
  posture, `capture_services.py:44-58` precedent verbatim in shape).

**`build_dataset_services(...)`** — the permission-gated construction point,
re-deriving the RAW descriptor by pinned digest (the grant-seam precedent,
CON-10's "re-derives the raw form by digest exactly as the permissions precedent
does"):

| Descriptor declares | Bundle | Controller |
|---|---|---|
| invoke capability ∧ catalog+measurement resolved | + `dataset_publish`, `dataset_lookup` | yes |
| ∧ `artifact_writer` | + `payload_create/append/finalise/abort` | (same controller) |
| ∧ `artifact_reader` | + `artifact_read` | (same controller) |
| no invoke capability / unresolved contracts | base five members only | **None** → `invoke` refuses UNSUPPORTED |

`interfaces/app.py`'s activation loop grows one `build_dataset_services(...)` call
and one `dataset=dataset_controller` kwarg at `load_otdp_plugin` (app.py:739-772,
the exact shape of the capture/stream wiring — F1's close-sweep adoption extends
to the dataset controller's sweep).

### 2.3 Bridge invoke dispatch (slice 2)

`supported` grows `"invoke": {"action_id", "input"}` (the runtime schema's own
closed branch). The gate — all refusals clean, typed, `not_dispatched`, zero
adapter calls (the `_capture_gate` discipline):

| Gate | Check | Refusal |
|---|---|---|
| I1 capability | `self._dataset is not None` (controller existence = capability ∧ contracts resolved) | UNSUPPORTED |
| I2 declaration | `action_id` is a string ∧ in the raw descriptor's `actions` map (defense in depth under binding's admission refusal) | INVALID_ARGUMENT |
| I3 catalog | the action resolves in the pinned catalog's registry | INVALID_ARGUMENT (M14 — unknown contract, never opaque success) |
| I4 input shape | `input` is an object ∧ validates against the action's `input_schema` | INVALID_ARGUMENT (validator's message) |
| I5 narrowing | `input` validates against the descriptor action's `input_constraints` (the bridge holds the raw form; the policy-rule intersection already ran at the executor — this is the descriptor's own narrowing, §2 check 3). I5's validators compile from descriptor bytes, so the §2.1 probe's coverage includes the per-action `input_constraints` schemas (R22) | INVALID_ARGUMENT |
| I6 identity | mint `dataset_id = "ds:{operation_id}"`, set on the `_Context` (unique per dispatch: CTL-5 keys re-entry on occurrence ids, and recovered steps never re-dispatch, so no collision from replay) | — |

The **clamp bracket extends to invoke** when the controller exists (the row-B
discipline, `otdp_bridge.py`'s ExitStack region): a fetch action's payload
appends during `execute` hit the same single-writer store a capture's appends
do, and the entry-time-remaining semantics and disclosed overshoot apply
unchanged. The step's `timeout_ms` (already `min(now + timeout_ms,
body_deadline)` at `_dispatch`) is the whole budget — no new procedure-budget
mechanism, exactly as #43 Amendment 3 corrected for captures.

**Result conversion** — `_convert` grows the invoke branch (the
`$defs/operationResult` invoke `data` branch is closed: `{action_id, result}`):

- envelope shape + `action_id` echo == request (uncorrelated otherwise — the
  `_convert` precedent);
- `result` validates against the action's `output_schema`; failure is
  **PROTOCOL_ERROR poison carrying the validator's message** (the `InvalidEvent`
  discipline: the honest invalid class, never generic failed-or-late wording);
- **dataset cross-check**: if `result` is dataset-shaped (satisfies the
  manifest's required keys), the controller must hold an admitted manifest for
  THIS operation whose canonical bytes equal the returned result — a dataset the
  adapter did not publish through `dataset_publish`, or a post-publish
  mutation, is a protocol lie (poison). Non-dataset results (configure/abort
  outputs) pass schema-only. This is the structural enforcement behind §1's
  "inline datasets also go through dataset_publish" — the adapter-correlation
  channel (context) is the honest path, the bridge-side state is the
  enforcement.
- **Slice-3 rider (Amendment 2):** `is_dataset_shaped` consults the compiled
  dataset validator for its refusal text once slice 3 lands it (`kind` ∈ the
  nine kinds) — sharper than the required-keys heuristic, same poison
  posture.

**Failure paths** (Amendment 1, HIGH-1/LOW-2): the dispatch site's first
except tuple extends EXPLICITLY to the dataset lane — the writer raises the
same `CaptureQuotaExceeded`/`OperationalError` classes, but the classification
must be deliberate, not incidental class overlap — and the stamp discriminator
grows the dataset arm: a writer-originated condition whose stamp names one of
THIS operation's open payload ids (the controller's registry, §2.2) classifies
clean `RESOURCE_LIMIT` `dispatched` — session survives, still-open payloads
aborted, A06/A7 posture identical to captures — while a genuine saved
exception replayed from ANOTHER operation's payload (same module token, wrong
binding) keeps the poison posture (R10). The writer's refusal messages and the
bridge's classified-refusal template are parametrized at the writer seam so an
invoke-classified refusal names the payload/dataset lane, never capture prose
(LOW-2, R17). Every other exception keeps the poison posture; `plugin_close`
sweeps open payloads.

**Slice-3 riders (Amendment 2):** (a) capture-STAMPED writer conditions
raised during an invoke keep poisoning even after slice 3's payload registry
exists — the registry knows `pay:` ids, not `cap:` ids, and a capture stamp
bound to an invoke dispatch has no honest binding; the defensible C3
posture, recorded so slice 3 does not "fix" it. (b) The writer seam's
capture-worded exception prose is slice 3's to parametrize — R17's
no-capture-wording pin, extended to the payload lane, is the forcing
function.

### 2.4 What this increment does NOT build (the honest M-check boundary)

Implemented: M01 (structural refs), M02 (length agreement), M03 (encoding/dtype
consistency vs records), M04 (inline finiteness), M10-correlation subset, M11
(artifact integrity), M14 (contract resolution). Deferred with carriers
(§6 rows 1): M05–M09, M12, M13 — the class-semantic checks (quality-status
coherence, class quantity requirements, log references, time/trigger coherence,
multiplexed timing, port-pair rules). These require device-classes quantity data
wired to profiles; the corpus itself frames all of M01–M15 as conformance
obligations, and shipping the structural core first is the same minimal-increment
posture #43 took for capture (G1–G4 then, M-structural now). The guide (§4)
states which M-checks remain author-side obligations.

### 2.5 SDK slice (slice 1)

`benchweave_sdk/interfaces.py` grows `DatasetServices(HostServices, Protocol)`
with the seven §3 members, docstrings faithful to the corpus text (dataset_id
host-reserved; publish validation; artifact_read's permission and bounds), and
the `OperationContext.dataset_id` docstring gains the invoke-minting note. The
module docstring's own sentence — "Profile/dataset extensions must follow the
pinned extension contract" — is the hook this fills. Additive protocol, no
corpus bytes, no `ADAPTER_API_VERSION` motion (the CaptureServices precedent:
capability protocols grow beside the base without an API bump).

---

## 3. Slice map (the run)

| Slice | Repo | Content | Gates |
|---|---|---|---|
| 1 | SDK (`~/Documents/src/benchweave-sdk`) | `DatasetServices` protocol + docstrings; the agreement-test sets it moves ride the pointer | SDK PR first (TWO-1: commit, push, PR — stacked if needed), then main-repo pointer commit |
| 2 | main | §2.1 contract resolution + §2.3 invoke dispatch (gate I1–I6, convert, clamp, sweeps) + app.py wiring + the UNSUPPORTED pin narrowing + guide §4/§7 (invoke half). Datasets-shaped results refuse unpublished from day one (strict posture) | RED-first; `uv run ruff check .`, bare `uv run mypy`, focused pytest + `tests/faults/` |
| 3 | main | §2.2 dataset services (bundle, controller, builder, writer `open_payload` allowance) + publish/lookup/artifact_read + the publish-path controls + guide §7 (dataset half) + adapter-agreement dataset pins + the one-source derivation and pin for the two `max_page_size×10` quota numbers (Amendment 1, LOW-3) | same; E2E per §7 |

One RED→GREEN slice per commit; working branch, PR, double review (resident +
adversary); each merged PR opens at most one follow-on issue. Slices 2 and 3
serialize on main's merge result (the run rules); slice 1 precedes both.

---

## 4. Invariant and cross-surface impacts

- **CTL-6** (invoke input resolution): unchanged — resolution stays at the
  executor seam; the bridge gate validates the *resolved* input (post-CTL-6),
  which is the only place a `$stg_ref`-resolved value can be schema-checked.
- **CTL-8** (monitoring wraps every dispatch): unchanged — invoke is a dispatch
  like read/write; no new engine rhythm, no poll-loop implications.
- **CON-9** (derivation pure post-dispatch): unchanged — `_apply_derivation`
  already handles dataset-shaped invoke results; the admitted manifest flows
  through it identically.
- **CON-10**: **minor amendment** — the projection itself is untouched (binding
  needs only `action_id`+`issued`, both present); the amendment adds one
  sentence to the invariant's grant-seam clause: the dataset seam re-derives the
  raw form by digest for `capabilities`/`actions`/`contracts`/permissions,
  exactly as the permissions and provider precedents do. The census
  (`test_descriptor_equivalence.py`) is untouched — no descriptor-semantics
  check moves.
- **REG-4 / drift row 8** (adapter protocol surface): moves **consciously**.
  `tests/sdk/test_adapter_agreement.py`: `EXPECTED_DATASET_SERVICES` joins the
  SDK-only assertion (`not (EXPECTED_CAPTURE_SERVICES | EXPECTED_DATASET_SERVICES
  & used)` — the bridge never calls dataset members); the
  `context.dataset_id is None` pin (:437-439) flips to verb-conditional ("None
  for non-invoke verbs; host-minted `ds:` opaque for invoke"); the
  mutation test at :684 (dataset_id removal from interfaces) still guards the
  field. CON-8's identity block: **unchanged** (no version bump).
- **STO-1..6**: untouched — **no new migration**. Payload staging reuses the v5
  `capture_staging` table (id column carries `pay:` ids; `format` carries the
  encoding; `sample_count` NULL — the raw_binary captures already open with
  `sample_count=None`, `capture_store.py:186`). The allowance formula differs
  (dataset budget, no capture clamp term) — a new `open_payload` method on the
  writer, disclosed dual-use of two columns in its docstring. **Not Tier 3.**
- **CON-3/CON-5/CON-6** (MCP/REST): untouched — no new operation. Datasets are
  served by the existing `stg_v1_artifact_read` (payloads, manifests) and
  `stg_v1_evidence_get` (evidence rows). Dedicated dataset operations are a
  deferral (row 4), the #43 row-5 precedent.
- **Drift rows moved**: 3 (device-developer-guide §4 package assembly — pinned
  catalogs; §7 publish measurements — dataset services, context.dataset_id,
  author-side M-checks), 8 (above), 7 (SDK pointer, slice 1). Rows 1–2, 4, 9–18:
  untouched.
- **CI cost**: none new — all controls are plain pytest over the existing
  harnesses (`tests/unit/test_otdp_bridge.py` grows an `InvokeAdapter` beside
  `CaptureAdapter`; integration rides the real activation path). No new job.

---

## 5. On-disk format / schema involvement

None. No store migration (§4 STO note), no corpus byte moves, no openapi change,
no interface-contract change. The only schema-adjacent construction — compiling
the pinned catalog's embedded schemas — reads already-verified bytes. This is a
Tier-1/Tier-2 increment in the review rubric's terms (new host behavior + SDK
protocol surface), not Tier 3.

---

## 6. Deferrals — every row carries carrier and reopen trigger

| # | Deferred | Carrier | Reopen trigger |
|---|---|---|---|
| 1 | Class-semantic M-checks (M05–M09, M12, M13) at publish | Follow-on issue at slice-3 merge | First profile whose required-quantity/class-output validation is wanted at the gateway — the device-classes quantity data wiring is its own train |
| 2 | Cross-run / cross-principal `dataset_lookup` authorization (a principal model) | Documentation here | A multi-run workflow needing shared datasets |
| 3 | Upload-capable consumption end-to-end (data-consuming integrations reading foreign artifacts) | Documentation here | First upload-capable profile plugin |
| 4 | Dedicated MCP/REST dataset operations | Documentation here (row-5 precedent) | A caller needing dataset reads outside `stg_v1_evidence_get`/`stg_v1_artifact_read` |
| 5 | Acquisition-scoped dataset identity (dataset_id derived from the acquisition, idempotent re-fetch across operations) | Follow-on issue at slice-3 merge | A profile whose fetch semantics need acquisition-dedup; the issued-id registry is the mechanism home |
| 6 | Standalone (hostless) dataset/payload writer — SDK parity with `StandaloneCaptureWriter` | SDK-side note in slice 1's PR | A plugin-dev need for dataset authoring without the gateway |
| 7 | Demo-lattice class fixture (`fixtures/registry` + builder + catalogue + digests) | Follow-on issue at slice-3 merge | First registry-demo need or first real class plugin admission — the E2E proof (§7) uses a test-local admitted bundle through the real activation path, so the lattice is not load-bearing for this issue |
| 8 | Multi-catalog precedence — overlapping `$id`s AND overlapping `action_id`s across pinned contracts (Amendment 1, NIT-2: slice 2 REFUSES multi-catalog outright, so the precedence question is closed by refusal, not resolution) | Documentation here | A real plugin genuinely needing two simultaneous catalogs — the refusal then converts to a designed precedence rule |
| 9 | Step-timeout vs declared-action-timeout admission mirror (considered, declined: step timeouts are the procedure's bounded authority; the descriptor declaration is admission evidence) | Documentation here | A corpus revision normatively pairing them |
| 10 | Manifest-size ceiling as a commissioned `QuotaLimits` field (declined — and the declination is TRUE by mechanism since Amendment 1's HIGH-2: the manifest routes through the staged writer at publish, so its bytes are in the `used` ledger and the existing `max_dataset_bytes` refuses them; the original text asserted a charge that had no mechanism) | Documentation here | A measured manifest-bloat trace the routed bytes cannot refuse |

---

## 7. Pre-committed acceptance rule

Written before any implementation number exists. All controls must (a) pass with
the mechanism present and (b) **fail when only the mechanism is reverted** — the
reviewer reverts the mechanism commit and watches red, restores and watches
green. A control that stays green under (b) does not test the mechanism and must
be fixed before merge. No underpowered mode applies: if the fixture substrate
cannot express a pinned catalog through the REAL activation path, the E2E is
underpowered and the slice reports that rather than weakening any control.

**Unit/fault controls (each a RED-revertible test):**

- **R1 (bounds before device):** invoke with an undeclared action (I2), a
  catalog-unknown action (I3), a schema-invalid input (I4), and an
  `input_constraints`-violating input (I5) each returns a typed
  `INVALID_ARGUMENT`/`UNSUPPORTED` `not_dispatched` with a spy adapter recording
  **zero** `execute` calls.
- **R2 (host-assigned identity):** a publish whose `manifest.dataset_id ≠
  context.dataset_id`, and a null-context publish, both refuse; an invoke result
  that is dataset-shaped but was never published (or diverges from the admitted
  manifest) poisons `PROTOCOL_ERROR` — the cross-check is bridge-side state, not
  adapter cooperation.
- **R3 (payload integrity, M11):** `payload_finalise` returns host-computed
  `{artifact_id, encoding, byte_length, sha256}`; a manifest whose variable
  artifact fields disagree with the writer's published record is refused at
  publish; appends after terminal are refused; a payload id from another session
  is refused.
- **R4 (quota honesty):** payload bytes charge the dataset allowance
  (`min(byte_limit, max_dataset_bytes − used)` — asserted WITHOUT the
  `max_capture_bytes` clamp term, pinning the formula difference); exhaustion
  mid-invoke is a clean `RESOURCE_LIMIT` `dispatched` with the session alive and
  zero published rows; a forged or replayed quota exception (no stamp / wrong
  operation binding) keeps the poison posture.
- **R5 (failure reclaim):** an adapter that opens payloads then raises leaves
  zero staging rows (epilogue reclaim asserted without adapter cooperation) and
  `plugin_close` sweeps a still-open payload.
- **R6 (result honesty):** a schema-invalid `result` poisons with the
  validator's message (not generic wording); an `action_id` echo mismatch
  poisons; an unknown-outcome envelope is never downgraded (existing envelope
  pins already cover the last — re-asserted through the invoke branch).
- **R7 (permission structure):** without `artifact_reader` the bundle has no
  `artifact_read` attribute (structural absence asserted); without
  `artifact_writer` no `payload_*` members; a descriptor pinning a catalog but
  no measurement schema gets no controller and `invoke` refuses UNSUPPORTED
  (both-or-neither).
- **R8 (immutability/idempotency):** byte-identical re-publish under the same
  dataset id returns the admitted manifest with no new rows; a divergent
  manifest under a used id refuses.
- **R9 (contract resolution honesty):** a bundle whose pinned catalog bytes do
  not hash to the declared sha256 is refused at load (`ActivationRejected`)
  with zero bridges constructed — the C01 leg's own control.

**Amendment 1 additions (R10–R17).** These controls post-date the original
pre-commit — they were added after the mechanism-critic pass, and are held to
the same absence-presence standard; no control above is weakened or narrowed
by them (each extends or adds):

- **R10 (invoke classification, both directions — HIGH-1):** a writer-originated
  quota condition raised through THIS operation's payload classifies clean
  `RESOURCE_LIMIT` `dispatched` with the session alive; a genuine saved
  exception from ANOTHER operation's payload — same module token, wrong
  operation binding — poisons. Reverting the discriminator's dataset arm must
  flip the first direction to poison (the second already poisons today, which
  is the defect).
- **R11 (manifest byte-refusal — HIGH-2):** an inline manifest of N bytes
  against `max_dataset_bytes = N − 1` REFUSES at publish — no
  `artifact_writer` permission involved (inline manifests need no payload
  writers); the refusal exists only because the manifest routes through the
  staged writer.
- **R12 (refuse-at-create — MEDIUM-1, owner-ruled):** `payload_create` with
  `byte_limit` above the remaining allowance refuses `not_dispatched` at
  create (capture G3 parity); the refusal message names the actual allowance;
  no staging row is written.
- **R13 (offset floor boundary table — MEDIUM-2):** `artifact_read` at
  `{(-1, 1), (-1, MAX), (size, 1), (size+1, 1)}` — negative offsets REFUSE
  (never clamp — the seam's clamp is the MCP behavior, not this bundle's);
  EOF and beyond-size semantics match the store's D11 contract.
- **R14 (load-time `$ref` probe — MEDIUM-3):** a digest-matching catalog whose
  embedded schema carries one external/unresolvable `$ref` is refused at LOAD
  (`ActivationRejected`, zero bridges) — R9's companion; without the probe the
  same catalog would pass load and poison at first dispatch instead.
- **R15 (M11 operation binding — MEDIUM-4):** a manifest referencing an
  artifact finalised during a PRIOR operation of the same session refuses at
  publish (session-scoped existence would pass every other check — the control
  exists to fail under exactly that regression).
- **R16 (refusal scope per defect class — LOW-1; taxonomy corrected in place
  by Amendment 2, adversary F5 + governor M — the original text's
  "both-or-neither failures are load-level" was wrong):** an admission-level
  test pins the SCOPE of each refusal against the resolved taxonomy. **HARD
  (load, run-wide) = present bytes that lie:** digest mismatch, unresolvable
  `$ref`/`$dynamicRef` (probe-rooted, R18/R19), degenerate measurement
  identification (R21), multi-catalog (§2.1's structural refusal). **SOFT
  (verb-level UNSUPPORTED, no controller) = absence:** contract pins absent
  from the bundle, `contracts` key absent. The empirical asymmetry the
  implementation confirmed: the real corpus catalog's half-pair refuses at
  LOAD via the probe (its 12 measurement refs dangle), while
  measurement-alone and a synthetic self-contained catalog without the
  measurement pin are the soft arms (R20 pins the latter). Any future
  widening or narrowing of scope trips the pin.
- **R17 (lane-honest refusal prose — LOW-2):** an invoke-classified
  `RESOURCE_LIMIT` refusal's message names the payload/dataset lane — asserted
  to contain no capture-lane wording (the writer-seam parametrization's
  control).

**Amendment 2 additions (R18–R21).** Slice-2 review fold; same standard and
same post-date honesty as R10–R17:

- **R18 (probe rooting — relative refs):** a catalog whose action schema
  carries a same-document RELATIVE `$ref` that the per-action validator roots
  differently than the document → `ActivationRejected` at load. Without the
  rooting fix the probe passes it and dispatch raises `PointerToNowhere`,
  recording UNKNOWN for a pre-dispatch gate failure — the wrong outcome
  class for a gate refusal.
- **R19 (`$dynamicRef` probe):** a catalog with a dangling `$dynamicRef` →
  `ActivationRejected` at load (a `$ref`-only probe passes it; the reference
  escapes the bridge uncontrolled at first invoke).
- **R20 (the catalog-half soft arm — F3):** a synthetic self-contained
  catalog without the measurement pin loads SOFT — `_dataset is None`,
  `invoke` refuses UNSUPPORTED, nothing else refuses. The arm previously had
  no pin; hardening it into a load-level refusal must trip this control.
- **R21 (degenerate measurement identification — F4):** a pinned measurement
  document whose dataset required set is empty or absent →
  `ActivationRejected` at load — present bytes that lie; the
  every-dict-poisons repro dies here.
- **R22 (descriptor constraints probe — in-wave residual):** the load-time
  probe extends to the DESCRIPTOR's per-action `input_constraints` schemas
  (walk `$ref` + `$dynamicRef`, rooted exactly as I5's lazy compile roots
  them): a descriptor action whose `input_constraints` carries an
  unresolvable reference is `ActivationRejected` at bridge construction —
  present bytes that lie, HARD under the corrected R16 taxonomy — while a
  self-contained constraints schema (internal `$defs`) still resolves and
  dispatches.

**E2E measurement (the value demonstration, sim/test substrate — no hardware
claims):** N = 30 procedure runs through the real activation path
(app.py bridge construction, not a hand-built bridge), each
`configure(invoke) → fetch(invoke, payload-backed dataset) → sample → assert`:

- **Ship:** 30/30 runs terminal-complete; 30/30 admitted datasets with one
  evidence row and published artifacts each; 30/30 `sample` assertions resolve
  over the admitted `scalar_set`; 0 unrefused protocol lies across the R1–R8
  mutation battery replayed against the E2E fixture.
- **Kill (functional):** any battery case accepted, or any count below 30/30 on
  a green suite, kills the slice — no partial credit.
- **Kill (measurement-validity):** if the E2E cannot drive the real activation
  path with a pinned catalog (loader-inventory resolution fails in test), the
  measurement is underpowered — report, do not substitute a hand-built bridge
  for the counts.
- **Disclosure measurements (reported, no gate):** publish+validate path p50/p95
  at fixture scale, and per-dispatch gate validation cost, against the
  capture-path measurements already in-tree (the #176 class). These feed risk 3;
  their reopen trigger is a measured deadline-breach or bloat trace (§6 rows 1,
  10), mirroring #43 Decision 5's trigger style — a number invented now would be
  the tuning-this-prevents failure. **Amendment 2 note:** I5's descriptor
  `input_constraints` validators compile lazily on first use per action — the
  FIRST invoke dispatch of each action pays that compile inside the
  clamp+deadline window; the per-dispatch cost measurement reports first-use
  and steady-state separately so the spike is visible, not averaged away.

---

## 8. Top risks and what falsifies this design

| Risk | Falsifier |
|---|---|
| **Contract resolution adds a new admission surface at load — with a run-wide blast radius and a soft/hard inversion, both now named** (Amendment 1, LOW-1): an `ActivationRejected` at load aborts `build_run` RUN-WIDE, so one device's stale digest refuses devices that never dispatch; meanwhile the completeness end is SOFT — an invoke capability with unresolved contracts yields only the verb-level UNSUPPORTED, never a run refusal. Integrity-hard/completeness-soft is the defensible ordering and is KEPT, but as a named decision, not a discovery | R9 + R7's both-or-neither control + R16's refusal-scope admission test pinning the scope per defect class, so any future widening or narrowing trips. If real descriptors in the wild pin only partial contract sets, the both-or-neither posture bites — that's a fork for the owner, disclosed at slice-2 review |
| **The dataset/result cross-check couples the bundle and controller through shared session state** — a state bug could admit an unpublished dataset or poison a honest one | R2's both arms; the RED revert must flip both. The state is per-dispatch keyed on operation id (CTL-5's uniqueness), so replay cannot alias it — asserted in R2 |
| **Validation cost per dispatch** (input schema + output schema + manifest schema + M-subset) inside the step deadline — including the per-action FIRST-use lazy compile of I5's `input_constraints` validators inside the clamp+deadline window (Amendment 2 rider) | The §7 disclosure measurements, first-use and steady-state reported separately; a measured deadline breach at fixture scale reopens the gate-placement decision (admission-time pre-compilation vs dispatch-time) rather than tuning constants |
| **Shared evidence dimension** — dataset rows, the run's `retain_evidence` rows, AND the monitor's per-tick retention are all kind `dataset` on the run key (Amendment 1, LOW-3: the monitor is the loudest competitor — one row per tick, so a step-heavy run can fill the dimension before any publish; refusal is clean and the inverse degradation is the existing `evidence_gap`) | Disclosed (§2.2 step 4); slice 3 folds the one-source derivation + pin for the two `page_size×10` quotas; starvation demonstrated in either direction becomes the corpus-revision fork (distinct evidence kinds), the erratum's own precedent |
| **Invoke dispatches now bracket the store clamp** — a class bridge serializes store access like a capturing one; the entry-time-remaining overshoot disclosure (row B) extends to fetch actions | Inherits the #176 measured posture; no new claim made here beyond the extension, and the clamp bracket's tests extend mechanically |

**Standing disclosures inherited unchanged:** the serial-engine model (#43
Decision 1, Option B's own record `2026-09-23-issue159-…`); trusted-Python
forgery boundary (the C3 docstring's honest limit); the naive-stamp clock
disclosure (execution 0.2.0 line 76) applies to dataset `started_at` exactly as
to capture `started_at`.

---

## 9. Decisions taken in this design (and why, over the alternative)

1. **Bridge-gate schema validation over admission-time-only.** Inputs can carry
   `$stg_ref` directives resolved at dispatch (CTL-6); only the bridge sees the
   resolved value. The alternative — validate at semantic admission — cannot
   see runtime values and would validate only literals, a silent hole.
2. **Host-minted `ds:{operation_id}` over acquisition-derived ids (first
   increment).** The operation id is unique per occurrence and already the
   ledger key; acquisition identity needs the issued-id registry's runtime
   state and is row 5's deferral. The corpus's "may return the already
   published manifest" is permissive, not mandatory.
3. **Reuse the staged writer + `capture_staging` table over a new payload
   table.** Same lifecycle (staged/finalised/aborted), same recovery sweep, same
   clamp/floor machinery; a second table would duplicate the writer's invariants
   (the #43 Amendment-1 lesson: hand-re-deriving invariants is the fragile
   pattern). Dual-use of two columns is disclosed at the writer.
4. **`RESOURCE_LIMIT` classification via the stamp discipline over widening the
   poison exception list.** The C3-as-amended rule (module token + operation
   binding) is the proven discriminator; widening `except` clauses by exception
   type is the exact pattern C3 replaced.
5. **Strict from day one: an unpublished dataset-shaped result poisons in slice
   2, before the services exist in slice 3.** The alternative (accept inline
   datasets unvalidated until slice 3) would ship a lane whose integrity core
   arrives later than its data path — the #43 record's own refusal shape
   ("a lying or truncated capture is refused at finalise, never published").
6. **SDK protocol-only slice over protocol + standalone writer.** The issue
   names the interfaces; the standalone writer is real but separable value
   (row 6), and slice 1 stays reviewable in one sitting.

## 10. What the maintainer must decide (forks)

- **Both-or-neither contract pinning** (risk 1): if real pending plugins pin
  partial contract sets, the structural refusal may be stricter than the
  ecosystem needs. The alternative (a measurement-schema-less invoke lane that
  refuses only `dataset_publish`) weakens M14's edge; this design takes the
  strict side and names the fork.
- **Slice 2/3 split confirmation**: the split ships dispatch-without-datasets
   between the two PRs; if the reviewer prefers one landing (the interlock is
   the strict refusal), the slices merge into one PR at the cost of review size.

## Amendment 1 — mechanism-critique fold (2026-09-25)

A mechanism-critic pass attacked this record after the original pre-commit (2
HIGH, 4 MEDIUM, 3 LOW, 2 NIT; six assumptions attacked and held). Every
finding was verified against source before folding; falsified text is amended
in place, §7 is EXTENDED only (R10–R17, each marked with its origin finding,
held to the same absence-presence standard, with this section as the honest
record that they post-date the original pre-commit), and no existing control
is weakened.

**Changed in place:** §0 (NIT-1 — the raw-descriptor deep-copy is
`OTDPBridge.__init__`, not `load_otdp_plugin`; the verified inventory is a
local that resolution must take as an explicit argument); §2.1 (MEDIUM-3 — the
load-time `$ref` probe, without which structural validation passes
unresolvable references that would poison at I4 instead of refusing at load;
NIT-2 — multi-catalog refusal; NIT-1 — inventory threading); §2.2 (HIGH-1 —
the controller's open-payload-id registry and the discriminator's dataset
arm, without which every writer-originated condition during an invoke poisons;
HIGH-2 — the manifest routes through the staged writer so its bytes enter the
`used` ledger, closing the unbounded-inline-manifest hole and making row 10's
declination true; MEDIUM-1 — refuse-at-create, owner-ruled capture-G3 parity;
MEDIUM-2 — `artifact_read` refuses negative offsets rather than inheriting the
seam's clamp, with the measured wrong-window behaviors recorded; MEDIUM-4 —
M11 scoped to the operation; LOW-3 — the monitor's per-tick retention named as
the shared dimension's real competitor, both quota numbers'
`page_size×10` parallel derivation flagged for a slice-3 one-source pin);
§2.3 (HIGH-1/LOW-2 — the explicit except-tuple extension, the both-direction
classification rule, lane-honest refusal prose); §3 (slice 3 gains the quota
one-source derivation pin); §6 rows 8 and 10; §8 risks 1 and 4 sharpened.

**Owner ruling integrated:** MEDIUM-1 is decided REFUSE-AT-CREATE (capture
parity) — never silently reduce a `payload_create` ceiling.

**Holds — attacked and survived, recorded as confirmed:** `ds:{operation_id}`
minting under replay/recovery (recovery finalizes the interrupted run, the
body never resumes, run ids are never reusable — no collision path);
inventory trust for contract resolution (bytes digest-verified before the
adapter module is imported); abort refunds allowance with no leak and no
double charge; the clamp brackets SQLITE lock waits, not write throughput (a
large `byte_limit` cannot wedge it); evidence-dimension sharing as disclosed;
both-or-neither fidelity to the `documents.py:864-888` precedent.

## Amendment 2 — slice-2 review fold (2026-09-26)

Three review lanes (adversary, critic, governor) ran against the shipped
slice-2 branch; this fold integrates their corrections. Same discipline as
Amendment 1: falsified text corrected in place, §7 extended only (R18–R21),
no existing control weakened, and this section is the honest record that the
additions post-date the original pre-commit.

**Changed in place:** §2.1 (the resolution probe's family corrected —
`$dynamicRef` walked as well as `$ref`, and each reference rooted the way
the compiled per-action validator roots it, never at the document;
degenerate measurement identification named as a HARD present-bytes-that-lie
refusal); R16 (its "both-or-neither failures are load-level" claim was
wrong — the resolved taxonomy is HARD = present bytes that lie, SOFT =
absence, with the empirical asymmetry named: the real corpus catalog's
half-pair refuses at LOAD via the probe because its 12 measurement refs
dangle, while measurement-alone and a synthetic self-contained catalog are
the soft arms); §2.3 (two slice-3 riders recorded beside the failure-path
text and one beside the result-conversion text); §7's disclosure
measurements (the per-action first-use lazy compile of I5's
`input_constraints` validators inside the clamp+deadline window — reported
first-use and steady-state separately); §8 risk 3 (the same note).

**§7 additions:** R18 (probe rooting — a relative-ref catalog refuses at
load), R19 (a dangling `$dynamicRef` refuses at load), R20 (the catalog-half
soft arm pinned — a synthetic self-contained catalog without measurement
loads SOFT with `_dataset is None`), R21 (degenerate measurement
identification refuses at load).

**Slice-3 riders inherited by its brief:** (a) the cross-lane poison posture
(§2.3 — capture-stamped writer conditions during invoke keep poisoning; the
payload registry knows `pay:` ids, not `cap:` ids); (b) the writer seam's
capture-worded exception prose is slice 3's to parametrize, R17's
no-capture-wording pin extended to the payload lane as the forcing
function; (c) `is_dataset_shaped` consults the compiled dataset validator
for sharper refusal text (`kind` ∈ the nine kinds); (d) the first-use
compile disclosure in §7/§8.

**Process note (F1 — provenance only; the fix is code):** the shipped
slice-2 branch carried a false bare-mypy-green claim in the builder's
report. The review battery, not the builder's report, is the gate evidence
of record.

---

*Provenance: grounded against `main` at `4d8f718` (2026-09-25); corpus
`standards/otdp/0.2.2` + `standards/execution/0.2.0`; the #43 record (all three
amendments + erratum) is the governing precedent set. No client, bench, or
person identifiers appear here; fixtures use invented names.*
