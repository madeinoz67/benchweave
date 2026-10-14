# Issue #445 — the read verb's per-parameter side effect (design record)

**Date:** 2026-10-12
**Branch:** `feat/issue445-read-side-effect`
**Issue:** madeinoz67/benchweave#445 (`gateway`)
**Verdict:** BUILD — an additive OTDP 0.2.3 declaration surface (a per-parameter
`read_policy.side_effect` with a verb-maximum coherence rule) plus a gateway-code leg
(admission mirrors and the procedure-read refusal that mechanises an execution-contract
rule that is normative today but enforced by nothing). The issue's premise is confirmed
by the code and by the owner-supplied real device plugin's own bytes.
**Review tier (design-time call, rubric #254):** **Tier 3** — the build diff touches
`standards/`, adds JSON Schema content, and touches `src/benchweave/control/documents.py`
(a named Tier-3 path in its own right). The standards-governor mandate applies. Keyword
scan in §11.

---

> **Addendum 2026-10-12 (fold-in).** Frozen-bytes rule: this note records the
> owner-supplied fold-in evidence; the body below is unchanged from
> `feat/issue445-read-side-effect@2205012c`.
>
> - **The decoder-system interoperability record (owner-supplied, 2026-10-12)
> confirms this record's read-surface findings.** The same plugin whose bytes §1
> cites is the record's subject: the verb-wide
> `operations.read.side_effect: "none"` over four multiplexed counter
> parameters, the prose-only disclosure of the mux-select write, and the
> gateway's structural blindness (the CON-10 projection dropping `read_policy`,
> no S-check mirror, the executor's hardcoded non-state-changing assumption)
> are all corroborated — no re-verification of §1/§2 was needed.
> - **The decoder-system resolutions do not reach this contract.** The six-term
> wait alphabet (`h/l/r/f/e` plus `'n'` no-edge) and the grid-fidelity ruling
> (timing-mode RLE as the true uniform grid; the state-mode synthesized grid)
> touch the pdhost/plugin layers' decode and render paths, not the descriptor
> declaration surface this record motions — no schema, specification, or
> gateway-code clause here depends on either resolution.
> - **No corrections to this record's claims.** Unlike the #443 fold-in (whose
> §12 gateway-first claim went stale), nothing in the owner's record
> contradicts §0–§13 of this one; the addendum records confirmations only.


## 0. Summary

OTDP 0.2.2 gives a readable parameter a per-parameter read declaration
(`read_policy`: `max_age_ms`, `destructive`) and gives the read verb ONE operation policy
(`operations.read.side_effect: none | state_change`) covering every parameter — with no
rule connecting the two layers. A device whose read of some parameters mutates state (the
issue's multiplexed counter: one read must first write the channel select) therefore
cannot say so: setting the verb to `state_change` over-classifies every other parameter,
setting it to `none` (what the real plugin does) launders a state change as pure
observation. The per-parameter truth vocabulary that exists (`destructive`) names data
consumption, not incidental state change, and is consumed by nothing — the gateway's
projected descriptor view drops `read_policy` entirely, no S-check mirror reads it, and
the executor hardcodes "Core reads are non-state-changing observation: no allow rule
applies" (`executor.py` `_step_read`). The execution contract already ruled state-changing
core reads out of procedures ("excluded from this procedure revision; use an admitted
typed invoke action with an explicit allow rule", execution-contract.md §"allow rules")
— but the ruling is unenforceable because no surface identifies which reads are
state-changing.

The fix is three layers, one increment family:

1. **Declaration** — a new optional `read_policy.side_effect` (`none | state_change`,
   the verb enum verbatim) on readable parameters, plus a root-level schema conditional
   (the coherence rule, new S-check row S20): any readable parameter declaring
   `state_change` forces `operations.read.side_effect: state_change`. The verb policy is
   the MAXIMUM across parameters — the exact dual of the corpus's own write rule ("Write
   operation policy is a minimum across writable parameters; a parameter may demand
   stronger completion, never weaker", specification §10). Conservative
   over-classification at the verb stays legal, one direction only.
2. **Mirrors** — the CON-10 projected view gains the read side-effect facts; the
   refusal is enforced where the execution contract already places it.
3. **Enforcement** — procedure admission refuses a `read` step whose bound device's read
   verb declares `state_change` (typed prefix `state_changing_read:`), mechanising the
   execution contract's existing exclusion. Zero execution-contract bytes move.

Class call: **PATCH-class addition** to the OTDP 0.2.3 train issue #443 is already
building (held at its evidence gate) — with a mechanical dead-shape proof that no
0.2.2-admissible document is refused (§4). Unlike #443's zero-code slice 1, this motion
REQUIRES gateway code: the corpus rule is schema-expressible (both checkers inherit it
per-pin for free), but the procedure refusal and the projection are gateway logic that
exists nowhere today.

## 1. Localization — where the read surface and side_effect live

Corpus (`standards/otdp/0.2.2/`):

- `otdp-device-descriptor.schema.json` `$defs.operationPolicy.properties.side_effect`:
  enum `["none", "state_change"]`, required in every policy.
- Same file `properties.operations.properties.read`: ONE `$defs.operationPolicy` for the
  whole verb (required iff `capabilities` contains `read`, the S01 pairing).
- Same file `$defs.parameter.properties.read_policy`: `{max_age_ms (integer ≥ 0),
  destructive (boolean)}`, both required for `access: ro | rw` (parameter-level
  conditionals). **No `side_effect` at parameter level; no cross-check to
  `operations.read`.**
- `otdp-specification.md` §4: "Readable parameters declare `max_age_ms` and whether
  reading consumes or changes device state." §5: the verb table — `read` takes exactly
  `parameter` (the runtime permits only parameter arguments; confirmed in the plugin
  adapter, which enforces `set(arguments) == {"parameter"}`, and in the executor's
  `OperationRequest.read`). §10 S03: "no hidden writable binding or undeclared
  destructive read"; §10 tail: the write-minimum rule and "Conservative state_change
  classification is allowed".
- The catalog's `side_effect` declarations apply to invoke actions only; `read` is a
  core verb, not a catalog action.
- `standards/execution/0.2.0/execution-contract.md`, the signals paragraph:
  "Destructive reads and stimulus-producing reads require explicit policy/ownership and
  cannot be silently used as passive interlocks." The allow-rules paragraph: "**A core
  read with state-changing behaviour is excluded from this procedure revision; use an
  admitted typed invoke action with an explicit allow rule.** Non-state-changing
  observation is scheduled within ownership and measurement requirements, not through a
  control allow rule."

Gateway (`src/benchweave/`):

- `control/executor.py` `Executor._step_read` (around line 1119): the load-bearing
  comment — "Core reads are non-state-changing observation: no allow rule applies." —
  then `OperationRequest.read(...)` with no policy consultation. Reads are the ONE step
  kind that never reaches `check_allowed`.
- `control/policy.py` `check_allowed` (CTL-4): deny-by-default allow rules for kinds
  `invoke`, `write`, `capture` only. No `read` kind exists.
- `control/documents.py` `_project_full_form` (CON-10): the projected execution view
  keeps `parameters` as a list of NAMES — `read_policy` is dropped before any consumer
  can see it.
- `control/documents.py` `_check_semantic_mirrors`: mirrors S01/S02 only.
- `control/semantics.py` `_check_step`: read steps get the literal-parameter check
  only; no descriptor-policy mirror (contrast the capture kind's `capture_undeclared:`
  mirror, CTL-7).
- Repo-wide: `destructive` has ZERO occurrences under `src/benchweave/`; `side_effect`
  occurs in exactly one file, `registry/otdp_contracts.py` (`CompiledAction.side_effect`
  — the catalog invoke-action compile, consumed by `content/dataset_services.py`).

SDK (`packages/sdk/src/benchweave_sdk/`):

- `validation.py` `validate_descriptor`: mirrors S01/S02/S04/provider/S19. S03's
  destructive clause is not implemented. (The SDK vendors OTDP 0.2.0/0.2.1/0.2.2.)

The owner-supplied real device plugin (adapter-mode, OTDP 0.2.2-pinned; descriptor and
adapter read directly in its own tree, outside this repo):

- `operations.read` = `{timeout_ms: 2500, side_effect: "none", retry: "never",
  cancellable: true, completion: "acknowledged"}` — verb-wide `none`.
- Four multiplexed counter parameters (`frequency_a`–`frequency_d`, `access: ro`,
  `semantic: measurement`), each with `read_policy: {max_age_ms: 0, destructive: false}`
  and a description reading, in part: "The read switches the counter multiplexer: a
  device side effect the verb-wide read policy cannot declare (standards gap, disclosed
  here)." The disclosure is prose-only — exactly as the issue states.
- The adapter's counter read path (`_read_frequency`): sends a C1 write frame to the
  select register, drains the acknowledgement, polls the ready gate, reads the count,
  returns a Reading with `quality: "valid"`. `mark_dispatch_started()` is called before
  dispatch for every read, so even the dispatch-marker evidence does not discriminate a
  mutating read from a pure one.

In-tree census (measured, this worktree): every gateway fixture, in-tree plugin
descriptor (`sim_controller`, `sim_psu`, `sim_scope`) and corpus example descriptor
declares `operations.read.side_effect: "none"` with `destructive: false` on all readable
parameters. Nothing in-tree is refused by anything this design adds.

## 2. Root cause

Not a missing field alone — a missing RULE plus a dropped projection plus a hardcoded
assumption, in a chain:

1. The vocabulary that exists (`read_policy.destructive`) names "consumes or changes"
   device state in §4 prose, but its plain name reads as data destruction. The plugin
   author (disclosing in prose,, `destructive: false` in bytes) is direct evidence the
   community reads it narrowly: a mux select destroys nothing, so `false` felt honest
   even while the description text discloses a write. Redefining a shipped field's
   meaning in prose would silently change what existing descriptors declare (the
   explicit-configuration discipline forbids exactly that).
2. Even a truthful declaration would be inert: the CON-10 projection drops
   `read_policy`; no S-check mirror in either checker reads it; the executor's comment
   bakes the assumption in. The truthfulness hole is therefore structural — there is no
   consumer for the truth even if it were declared.
3. The runtime consequence: the execution contract's exclusion of state-changing core
   reads from procedures is prose. A procedure with a `read` step on a mutating
   parameter admits and executes today, mutating device state with NO allow rule — the
   CTL-4 deny-by-default posture bypassed by assumption, and the run record shows a
   clean observation (A06's "missing declaration reads as a clean answer").

Verified, not assumed: the plugin's bytes (above), the executor's comment (read at
`_step_read`), the projection (read at `_project_full_form`), the mirror inventory
(`_check_semantic_mirrors`, `validate_descriptor`), and the repo-wide zero/one-file
census for `destructive`/`side_effect`.

## 3. The semantic fork

What `side_effect` GATES decides the fork. Today it gates: (a) the execution contract's
prose model — state-changing operations are control, control needs an allow rule, and
state-changing core reads are excluded from procedures; (b) authoring guidance (retry
eligibility, completion claims); (c) catalog invoke-action compilation. It does NOT
currently gate any core-verb machine path — the gap is that it cannot even be EXPRESSED
per-parameter, so none of (a)'s machinery can engage.

**Direction 1 (RECOMMENDED) — per-parameter `read_policy.side_effect` + verb-maximum
coherence + admission mirrors.** A new optional field with the verb enum verbatim; the
coherence rule; the projection; the procedure refusal. Precedented end to end (§7).
The verb-level policy stays the machine-consumed surface (exactly how the write
minimum works: parameters declare demands, the verb policy is the derived bound the
executor's consumers read); the per-parameter field is authoring precision and the
coherence input.

**Direction 2 — a distinct read-with-effect verb class.** Rejected. A new verb touches
the runtime envelope schema, the §5 verb table, the executor's step kinds, the procedure
schema, the 17 vendored-exact MCP tools, REST/openapi, the bridge dispatch table and the
obligation-23 prose sweep — a cross-surface explosion (against A13 minimalism and the
minimal-increment doctrine) for a problem one optional field plus one conditional plus
one refusal solves. The corpus already has the "typed operation with declared
side_effect and an allow rule" shape: invoke actions.

**Direction 3 — invoke-action re-modelling only (no standards motion).** The plugin
could today re-model the muxed reads as descriptor-local actions (the `actions` surface
with per-action `side_effect` exists in the 0.2.2 schema, verified). Rejected as the
PRIMARY fix, kept as the plugin-side complement: (a) it abandons the parameter surface —
samples, predicates and stream subscriptions are parameter-shaped; (b) it leaves the
corpus defect open for every future multiplexed device, with the dishonest default
(`none`) as the path of least resistance; (c) the issue asks for the declaration
surface. After Direction 1 lands, Direction 3 is the plugin's procedure-side remedy
(§6, the follow-on).

**Direction 4 — an implicit-precondition model (the parameter declares the mux
dependency; the runtime elevates the effective policy).** Rejected for minimality: it
invents dependency-topology vocabulary for a fact the side_effect enum already names,
and the elevation lands in the same admission refusal anyway. Named as an owner fork
(F4) in case evidence arrives that consumers need the topology (e.g. scheduling reads
to avoid mux thrash).

**The falsifier held in view:** a descriptor whose read mutates state, once it DECLARES
so, must never validate as `side_effect: none`. Under Direction 1 the amended plugin
descriptor (counter parameters `state_change`) is refused by the schema conditional the
moment `operations.read.side_effect` says `none` — M-B below. What no static rule can
catch is the UNDECLARED lie (the plugin's bytes today, minus the prose): the mechanism
closes the declared-truth hole; catching silent mutation stays conformance-vector and
review territory (S09/S11 evidence). This residual is part of the guard's stated scope,
per the G4 claim discipline.

## 4. The mechanism — file-by-file motion

### 4.1 Standards (OTDP 0.2.3 — riding issue #443's train; this pass touches no
standards bytes)

All edits land in the 0.2.3 copy (copy-never-move; 0.2.2 stays digest-frozen):

1. `otdp-device-descriptor.schema.json`:
   - `$defs.parameter.properties.read_policy.properties.side_effect`: enum
     `["none", "state_change"]`, OPTIONAL (absent means `none`), with a schema
     description carrying the semantics sentence: the class of THIS parameter's read;
     the verb policy must be `state_change` when any readable parameter declares it;
     conservative over-classification at the verb remains legal.
   - A root-level `allOf` conditional: `if` the `parameters` array `contains` an item
     whose `read_policy.side_effect` is `state_change`, `then`
     `operations.read.side_effect` is `state_change`. One direction only — the reverse
     (all parameters `none`, verb `state_change`) stays valid by design.
   - `$defs.parameter.properties.read_policy` description updated to name both fields'
   meanings and the maximum rule.
2. `otdp-specification.md`:
   - §4: extend the readable-parameters sentence — the per-parameter `side_effect`
     declaration, the verb-maximum rule as the write-minimum rule's dual, and the
     one-directionality (over-classification legal, under-classification refused).
   - §10: new check row **S20** (read side-effect coherence), stated as the machine rule
     the schema conditional enforces and the author-facing index entry. S03's existing
     text is untouched.
3. New example `examples/reference-mux-counter.json` (invented names throughout): an
   adapter-mode descriptor, capabilities identify/read/invoke, parameters
   `mux_count_a`/`mux_count_b` (`ro`, `measurement`, `read_policy.side_effect:
   state_change`) and `supply_v` (`ro`, `none`), `operations.read.side_effect:
   state_change`, plus ONE descriptor-local invoke action reading the counter with
   `side_effect: state_change` — demonstrating both halves of the contract: the honest
   declaration AND the corpus's sanctioned procedure-side alternative. A short §12
   entry (the reference-hid-meter brevity pattern: the wire shape sketched, no vendor
   content) and minimal vector rows join it. Without at least one admissible corpus
   document using the field, the vocabulary is dead and the census has no positive arm.
4. `scripts/architecture/check_devices.py`: census arms over the new example plus
   mutation rows (parameter `state_change` + verb `none` refused; verb `state_change`
   with all-none parameters accepted; the local action's policy shape). RED first
   against the pre-mechanism tree (`5af97935` shape).
5. Manifests/report/docs in-arc: standards-manifest + corpus-manifest rows via repin,
   bundle export, validation-report regeneration (obligation 13), docs baseline
   refreshes (obligation 18), `docs/project-index.md` / `docs/README.md` rows, and the
   device-developer-guide's read-policy section (obligation 3 — a published surface;
   the document-writer agent authors that leg under the ASD-STE100 register).

### 4.2 Gateway code (required — the contrast with #443's zero-code slice)

1. `src/benchweave/control/documents.py` `_project_full_form`: the CON-10 view gains
   - `"read_side_effect"`: the verb policy string, present iff `operations.read` is
     (absent ⇒ consumers treat as `none`), and
   - `"state_changing_reads"`: the sorted names of parameters declaring
     `read_policy.side_effect: state_change` (always a list, possibly empty).
   A CON-10 amendment names both, in the amendment style of the capture keys.
2. `src/benchweave/control/semantics.py` `_check_step`, read branch: refuse when the
   bound device's projected `read_side_effect` is `state_change`:
   `state_changing_read: step {sid!r} at {where} reads device {device_id!r} whose read
   operation declares side_effect state_change; the execution contract excludes
   state-changing core reads from procedures — use an admitted typed invoke action
   with an explicit allow rule`. The refusal triggers on the VERB flag (faithful to the
   contract's sentence — an over-classified verb declares state-changing behaviour and
   is excluded equally); the `state_changing_reads` set rides the message for
   precision. The module docstring's prefix family gains `state_changing_read:`. No
   execution-contract or safety-policy bytes move: the rule being mechanised is
   normative today.
3. `src/benchweave/control/executor.py` `_step_read`: comment-only amendment — the
   "no allow rule applies" assumption now names its backstop (admission refuses
   state-changing read verbs; execution sees only non-state-changing core reads). No
   logic change: admission is the seam (the CTL-7 posture — descriptor mirrors at
   admission, not re-checks at dispatch).
4. Tests (RED first):
   - the semantics admission suite: the refusal arm; a no-block control (a `none`-verb
     device's read step admits); an over-classified-verb refusal arm;
   - the projection suite: the view carries the flag and set;
   - `tests/contract/`: 0.2.3 schema-conditional vectors over an invented-name fixture
     (the amended-plugin shape: two `state_change` params, one `none`, verb
     `state_change` validates; verb flipped to `none` refuses; 0.2.2-pinned copy of the
     same shape validates unchanged — per-pin, CON-1/#215).

### 4.3 SDK

`validate_descriptor` needs NO new code for the coherence rule — the schema conditional
is inherited by schema validation per-pin. The SDK leg is the vendored-0.2.3 sync and
release, riding #443's named follow-on train (its D7; the #408 order: SDK PR merges →
release cut → gateway pointer PR). The equivalence census extends to the new corpus when
the SDK tree carries it; the coherence refusal is schema-level on both sides (no new
gateway-stricter cell), and the `state_changing_read:` refusal is gateway-only by
design (procedure admission — the SDK has no procedure surface), like
`capture_undeclared:`.

## 5. Version semantics, governance, train

**Class call: PATCH-class, with a mechanical dead-shape proof.** The refused set of the
new rule is exactly {documents whose `read_policy` carries `side_effect`}. Under 0.2.2's
schema, `read_policy` is `additionalProperties: false` — any document carrying the new
field is ALREADY refused by 0.2.2 (unknown keyword), and any document not carrying it
cannot trip the conditional. Refusals(0.2.3) ∩ admissible(0.2.2) = ∅, proven both ways —
the `a103a4cf` standard, one notch stronger than that commit needed (there the dead
shape was proven by the deeper equality layer; here the closed vocabulary itself is the
proof). No field is retyped, removed, or required. The falsifier stands: if review
exhibits any input 0.2.3 refuses and 0.2.2 admitted, the class flips to MINOR and the
batch rule drags the whole 0.2.3 train with it — that exhibit cannot exist for this
rule, and M-D guards it.

**Train: JOIN #443's OTDP 0.2.3 train as a later slice.** Collision analysis: #443
(building 0.2.3 additive, held at its evidence gate) touches the descriptor schema's
ROOT (`decoders` field), the catalog, new decoder files, measurement-model §6,
device-classes §7, extension-contract; this motion touches `$defs.parameter.read_policy`
+ a root `allOf` entry, specification §4/§10, a new example, and gateway
code #443's slice 1 does not touch (that slice is zero-code; its D6 names admission
mirrors as its own follow-on).
Same version dir, disjoint regions of the shared files except the schema's root object
(low-conflict: one adds a property + one allOf entry). NOT disjoint surfaces ⇒ the
one-bump-per-train rule forbids a parallel 0.2.4; the batch rule wants the fold. #443's
hold is EXPLICITLY waiting for the plugin-implementation findings to fold in — this is
one of them. Sequencing: land after #443's slice on the train branch (stacked), one
0.2.3 dir, one repin, one SDK sync. #444 (commissioned-preset firmware) is designing
now and owns its own train call; nothing here touches its surfaces (preset/firmware
admission), and if #444 later needs OTDP bytes it joins the same 0.2.3 window or waits
per GOVERNANCE.

## 6. Minimal first increment — and the explicit deferrals

Slice 1 (one gateway PR on the train, after #443's slice): the §4.1 standards motion
(1–5) + the §4.2 gateway leg + RED-first tests. Slice 2 (same PR or an immediate
follow-on commit, owner's staging call): the device-developer-guide leg (document-writer
dispatch).

Deferrals, each with home + reopen trigger:

| # | Deferral | Home | Reopen trigger (observable) |
|---|---|---|---|
| D1 | The `destructive ⇒ verb state_change` implication as a MACHINE check (today `destructive: true` + verb `none` is not refused; the implication would refuse hypothetical 0.2.2-admissible shapes and drag the train to MINOR) | this record §3/§4 | the first descriptor in any served corpus, fixture or plugin declares `read_policy.destructive: true` (measured today: zero across all in-tree fixtures, plugins and examples) |
| D2 | The signals clause — refusing a safety-policy signal bound to a state-changing read ("cannot be silently used as passive interlocks", execution-contract signals paragraph): no signal↔descriptor cross-check seam exists at admission today (verified: documents.py carries no signal validation); building that seam is its own increment | this record; the policy-admission seam | the first state-changing-read descriptor is commissioned on a bench whose safety policy binds a signal to one of its parameters — an A04-weight residual, disclosed |
| D3 | Interactive/streaming disclosure: the MCP read tool surfacing the declared class; stream-subscription refusal for state-changing parameters (a streamed state-changing read would mutate at poll cadence) | the interfaces/ui surfaces | the first state-changing-read descriptor reaches an interactive or streaming bench session |
| D4 | Per-parameter read allow rules (`kind: "read"` in `check_allowed`, matching parameter names — the end-state where verb-level over-classification stops costing procedure access to clean parameters) | a future execution-contract revision (its bytes, its own bump) | a device needs clean and mutating reads in the SAME procedure — the real plugin's own shape (its `status` reads are clean, its counter reads mutate); interim remedy: the local invoke action |
| D5 | SDK vendored-0.2.3 sync + release cut + gateway pointer | #443's D7 train (the #408 order) | slice 1 merges |
| D6 | Run-record surfacing of the read class (the execution run-record echoing the declared class for admitted runs) | the D4 execution-contract revision | a consumer files the need (today the run binding's descriptor digest pin carries the honest declaration — the evidence is indirect but exact) |

## 7. Precedent citations

- **The write-minimum rule (primary, in-corpus):** specification §10 — "Write operation
  policy is a minimum across writable parameters; a parameter may demand stronger
  completion, never weaker." S20 is its dual for reads: parameters declare, the verb
  policy is the derived bound, one direction only. The layering (per-parameter
  declaration grain, verb-level machine consumption) is the same.
- **The admission-mirror precedent:** `capture_undeclared:` (`semantics.py`
  `_check_capture_declared`, CTL-7) — an admission-time descriptor mirror refusing a
  procedure step the bound device's declaration does not cover, family-prefixed and
  greppable. `state_changing_read:` is the same shape for the read kind.
- **The projection precedent:** the CON-10 capture keys — conditionally-projected
  declaration facts the admission seam reads; `adapter_permissions` for the
  raw-form-by-digest pattern if a consumer ever needs more than the projection.
- **The schema-conditional precedent:** the parameter-level `allOf` conditionals
  (`read_policy` required iff ro/rw; `write_policy` + `hazard_class` required iff
  wo/rw; the verification pairing) — declaration coherence expressed structurally,
  inherited by every per-pin checker for free.
- **The bump-class precedent:** `a103a4cf` (the refused-none template with the
  dead-shape proof); GOVERNANCE's additive-errata row ("new optional field, nothing
  removed or retyped → PATCH").
- **The escape-route precedent:** the descriptor `actions` surface with per-action
  `side_effect` (0.2.2 schema, verified) + execution-contract's own sentence naming it
  — the plugin-side remedy exists in-tree today.
- **The census/RED precedent:** `5af97935` (RED commit against the pre-mechanism
  tree), the 0.2.1 provider lane's corpus-first-then-mirrors order.

## 8. Invariant impacts (A01–A14 walk)

- **A02 (qualified, not assumed):** no numeric envelope, timeout or threshold is
  introduced or retuned; the motion adds a truthfulness declaration, not a commissioned
  number. Unchanged.
- **A04 (protection independent of AI):** the refusal is admission-time arithmetic over
  declared fields — no judgement in the loop; protective paths are untouched. The
  DEFERRED signals clause (D2) is the disclosed residual on this axis: the
  interlock-on-a-mutating-read hazard stays prose-enforced until that seam exists.
- **A05 (bounded procedures):** the refusal REMOVES an operation from procedures rather
  than adding one; the sanctioned alternative (admitted invoke action under an allow
  rule) is the corpus's existing bounded path. Procedures cannot express a mutating
  read before the run exists — structurally, at admission.
- **A06 (evidence over assertion):** the core win. A mutating read can no longer be
  declared pure observation; the run binding's descriptor pin (digest-exact) carries
  the honest class; a procedure cannot launder a state change as a scheduled
  observation. Residual stated: an UNDECLARED mutating read is not statically
  catchable (conformance vectors and review own that; the dispatch marker does not
  discriminate — verified in the plugin, which marks all reads).
- **A12 (bounded procedures):** unchanged envelope mechanics; one more admission
  refusal with a typed prefix.
- **A13 (one core contract):** one corpus motion; ZERO REST/openapi/MCP motion (the
  read request/result envelopes are unchanged — verified against the §5 table and the
  runtime envelopes); the strongest signal the attachment point is right.
- **A14 / A01–A03, A07–A11:** untouched.
- **CTL-4:** textually unchanged; in spirit this closes a bypass-by-assumption (the one
  step kind that never reached the deny-by-default gate because it was ASSUMED
  non-mutating). No allow-rule kind is added — that is D4.
- **CTL-7:** amendment — the admission-time descriptor mirror family gains the
  `state_changing_read:` row.
- **CON-1:** cited, not changed — per-pin resolution is what leaves every 0.2.2-pinned
  descriptor (including the plugin's, until it amends) admissible unchanged.
- **CON-10:** amendment — the projected view gains `read_side_effect` and
  `state_changing_reads`, in the capture-keys amendment style.
- **CON-2 / CON-11:** the fixture lattice and the validation-report family move
  mechanically with the corpus bump (obligations 5, 13).
- **STO / REG:** untouched. **No new invariant**: the coherence rule is a corpus
  conformance check (S20) carried by the schema conditional and the census — the
  derived_variables precedent (S19/M15 as corpus checks, not invariants) is the model.

## 9. Measurable proof — pre-committed acceptance rule

All metrics fixed before any number is looked at. The plugin-derived shapes use invented
names in this repo's fixtures (`mux_count_a/b`, `supply_v`); the owner's real plugin
descriptor is the out-of-repo corroborations, re-run against it by the owner.

- **M-A Expressiveness (declaration):** the amended shape — two counter parameters with
  `read_policy.side_effect: "state_change"`, one clean parameter `none`, verb
  `state_change` — validates against the 0.2.3 descriptor schema and passes S20.
  Sample: the fixture shape + the `reference-mux-counter` corpus example (2 positive
  documents, 3 and 1 state_change parameters respectively).
- **M-B Coherence refusal (the negative control):** the SAME shape with
  `operations.read.side_effect` reverted to `"none"` is REFUSED by the 0.2.3 schema
  conditional. Both-way dead-shape control: the amended shape is refused by the 0.2.2
  schema (closed vocabulary) — proving the PATCH class claim's premise set is empty.
- **M-C Procedure exclusion enforced (RED-controlled):** a procedure with a `read` step
  bound to the amended descriptor is refused at semantic admission with the
  `state_changing_read:` prefix; with the semantics check neutralised (the one arm
  removed), the SAME procedure admits (RED); a read step over a `none`-verb descriptor
  (the sim-controller fixture) still admits (the no-over-blocking control); a
  procedure reading the clean parameter on the amended (over-classified-verb) descriptor
  is ALSO refused — the disclosed, intended cost.
- **M-D No regression:** every in-tree descriptor, fixture, procedure and corpus example
  validates unchanged (per-pin where pinned); the full battery green; the census green
  with the new arms; `make check-sdk-standards` posture unchanged from #443's train
  shape.

**SHIP if** M-A, M-B, M-C, M-D all hold with exactly the specified refusal prefixes and
the M-C RED control shows admit-when-neutralised.

**KILL if** the amended shape cannot validate without further schema motion
(expressiveness failure — the field shape is wrong); any in-tree artifact refuses
(M-D — also flips the class call per §5); or the conditional proves unexpressible
without refusing valid documents (the schema route abandons for an S-check mirror — a
mechanism swap, not a kill of the design).

**UNDERPOWERED if** only the fixture and one corpus example exercise the field —
genericity rests on n=2 documents from one device family (multiplexed counters). The
widening obligation is named: a second device shape (e.g. a consuming-read parameter,
`destructive: true` + `side_effect: "state_change"`) joins the corpus before D1's
trigger is judged. An underpowered outcome is a finding about the corpus, not a
pass.

## 10. Top risks, each with its falsifier

1. **Over-classification cost.** The verb-max rule means one mutating parameter makes
   the WHOLE read verb procedure-excluded — clean parameters lose procedure reads too
   (the plugin's `status` case). Inherent to the shipped execution-contract exclusion,
   not invented here; the interim remedy is the local invoke action; the end-state is
   D4. Falsified in review if a procedure shape exists that legitimately requires mixed
   clean/mutating reads with no action-shaped alternative — that exhibit accelerates D4
   rather than killing Direction 1.
2. **Train collision with #443.** Same version dir, same schema file (different
   regions), one shared repin window. Falsified by a real merge conflict in the
   descriptor schema root or the standards-manifest arc — mitigated by stacking on the
   train branch and landing after #443's slice.
3. **The undeclared lie survives.** An author who simply omits the field keeps today's
   posture (M-B cannot fire). Not statically catchable; conformance vectors and review
   own it; the design's stated residual (G4 discipline). Falsified only by evidence
   that a machine-detectable signal exists (none found: the dispatch marker does not
   discriminate — verified).
4. **Schema-conditional correctness.** A malformed root conditional could refuse valid
   documents or fire on the wrong shape. M-D's per-pin sweep plus the census mutation
   matrix are the net; the conditional is one `contains` + one `then`, reviewed line by
   line.
5. **The plugin's own follow-on is load-bearing.** The fix only pays off when the owner
   amends the real plugin's descriptor (four parameters + the verb) — until then its
   reads stay dishonest AND procedure-admissible. Out-of-repo by design (hygiene); the
   acceptance rule's out-of-repo corroboration step names it. Falsified if the amended
   plugin descriptor hits a validation wall the fixtures did not predict.

## 11. Review tier and the Step-1 keyword scan

**Tier 3**, three independent path rules: the build diff touches `standards/`; it adds
JSON Schema content; it touches `src/benchweave/control/documents.py` (a named Tier-3
path). The standards-governor pass is mandatory; the two-lane adversarial refute applies
(the standing Tier-3 doctrine).

Keyword scan (the eight Step-1 words, word-boundary counts over the expected diffs):

- *This record's commit (the record file is the only diff; the counts below are the
  fixed-point numbers over the final committed text, this section included — stating
  counts changes them, so these are the numbers the final text actually carries):*
  `threading` 2, `asyncio` 2, `subprocess` 2, `sha256` 3, `hashlib` 2, `migrate` 2,
  `recovery` 2, `protection` 4. Nearly all of these hits are this section itself — the
  listing and the build-diff bullet naming the keywords (the rubric's intended
  self-fire); the one substantive hit outside this section is `protection` in the §8 A04
  heading, and `sha256` has none. The tier is 3 by the path rules regardless; the
  keyword hits ride along as disclosed.
- *The expected slice-1 build diff (0.2.3 corpus motion + examples + validator arms +
  manifests/report/docs sweeps + the gateway leg + tests):* `sha256` ≈ 10–25 (repinned
  manifest rows, census digest arms, the corpus example's provenance shape),
  `hashlib` 0–2 (test digest computations, if any), `threading`/`asyncio`/`subprocess`/
  `migrate`/`recovery` ≈ 0 each, `protection` 0–2 (docstring references to protective
  transition in comment text, if any). The build lane re-runs the scan over the real
  diff and reports actuals; the tier cannot drop below 3 either way.

## 12. Train shape

1. `docs(design)` — this record (first commit; the pre-commitment ordering)
2. `test(standards)` — RED: census/contract arms + the admission-refusal arms against
   the pre-mechanism tree
3. `feat(standards)` — the 0.2.3 additions (§4.1), landing on the train branch AFTER
   #443's slice (stacked; one version dir, one repin, one export, one report regen, the
   docs sweeps)
4. `feat(control)` — the gateway leg (§4.2) + its GREEN
5. Fold waves as review requires; the SDK sync + release + pointer ride the train's
   named follow-on (#443's D7 / this record's D5)

Reviews before open: resident code-reviewer (Tier 3 protocol) + standards-governor
(mandatory) + two independent adversarial lanes. Merge on the full rollup.

## 13. Forks needing the owner's word

- **F1 — field shape:** new `read_policy.side_effect` (recommended — additive, the verb
  enum verbatim, `destructive` keeps its consuming-read meaning untouched) vs
  redefining `destructive` in prose (zero schema motion, but a silent meaning change
  under shipped descriptors — rejected on the explicit-configuration discipline).
- **F2 — refusal trigger:** the verb flag (recommended — faithful to the
  execution-contract sentence; over-classified verbs excluded equally) vs the
  per-parameter set only (narrower, but under-enforces the contract for
  over-classified descriptors).
- **F3 — train:** fold into #443's held 0.2.3 as a later slice (recommended — the batch
  rule, and #443's hold is explicitly awaiting this class of finding) vs sequencing as
  a later window (a second 24h window + a second SDK sync for no governance gain).
- **F4 — implicit-precondition vocabulary** (Direction 4): deferred unless the owner
  sees near-term need for dependency-topology declarations (mux-thrash scheduling);
  reopen trigger would be a filed consumer need.
