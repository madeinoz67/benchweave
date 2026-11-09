# Design: #606 slice 2 — dispatch-bound admission identity (the selection close)

- **Issue:** gateway #606, refute-lane HIGH-1. This is the independent design pass the
  dispatcher commissioned for the mechanism the §11 addendum named; it is written on
  top of, and composes with, the in-flight "close the mint door" slice (candidate B,
  uncommitted in this worktree at design time — read and verified, production diff and
  record both).
- **Tree read and verified:** branch `fix/606-dataset-id-mint` at `ce4a4b44`
  (= `origin/main` `5f4256c1` + `656114f8` + `a2be59f9` + the §11 addendum), plus the
  uncommitted candidate-B diff (`src/benchweave/content/dataset_services.py`
  `mint_payload_id` fallback → typed refusal; both test files; the manifest refresh).
  The local primary checkout lags at `084c5e6c` and was not used.
- **Tier call (design-time, #254):** **TIER 3** — by dispatch (identity on the
  admission path, the same dispatch ground as slice 1), and the record's own §9 table
  self-fires the keyword rule by construction. The code diff's path rules fire none.
  See §9.
- **RED status:** the arms this slice carries (§6) are RED on the candidate-B head by
  trace (§3); the build must capture the runs before any green is claimed. ARM-2c —
  which the dispatch brief named as this slice's RED carrier — is **green on the
  candidate-B head and is NOT this slice's carrier**; §2 states why with the trace.

## 1. What this record decides

The brief asked this pass to verify or replace the builder's named mechanism
(dispatch-bound identity: `request.operation_id` at the bridge, a host-side
current-dispatch record for the member path). The builder has since picked a different
first move — candidate B, closing the mint door — and priced dispatch-binding
(candidate A) as the costlier alternative it "composes on top of if ever taken".

**Verdict, on the evidence:**

1. **Candidate B is sound for what it closes and should land.** The fallback it
   removes is verified dead in `src/` for its stated justification (the routing mint
   only ever names an operation whose state identity has already confirmed exists);
   its only dependents were the exploit and one unit fixture. It closes **id
   introduction**: no controller state can exist under a name the host never
   dispatched.
2. **B alone does not satisfy the branch's own correction of record.** §11's closing
   sentence — "the identity key must stop being a value the adapter can name" — is
   not made true by B. Under B, `admit`'s first line is still
   `operation_id = str(getattr(context, "operation_id", ""))` — an attribute of the
   adapter-held context. B narrows what that name can SELECT (host-minted ids only);
   it does not stop the adapter naming.
3. **This slice is A on top of B.** Not a rival: B is the floor (introduction
   closed, ARM-2c pinned), A is the completion (identity = the live dispatch,
   selection closed). §3 gives the executed-under-B trace that keeps A necessary;
   §2.2 corrects B's cost analysis of A, which this pass found overstated.

### 1.1 Where this pass disagrees with the brief

The brief pre-assigned ARM-2c as this slice's RED carrier ("already RED, so the
pre-commitment is cheap"). ARM-2c is RED on `ce4a4b44` only. Under candidate B its
attack dies at `payload_create` — the mint refusal raises inside `execute`, dispatch
poisons UNKNOWN/PROTOCOL_ERROR, nothing is admitted — every ARM-2c assertion passes
without any dispatch-bound identity. ARM-2c is B's pin, not A's carrier. A's RED
carriers are the selection arms (§6), which are red on B's head and only green under
A. The pre-commitment is therefore not free-riding on an existing RED run; the build
must produce its own.

### 1.2 Where this pass disagrees with candidate B's record

Two corrections, both checkable:

- **A's cost was priced against the wrong shape.** B's record prices A as "one new
  mechanism (no ContextVar exists anywhere in this tree's `src/`)… a seam through
  every direct publish/payload call in the unit harness (~30 call sites)". This
  design's A needs no ContextVar (the bridge is single-dispatch under its lock; a
  plain controller slot suffices — §4) and moves no payload-member call: identity is
  admission's concern, and the payload members keep their current signatures and
  context reads (§5, with the structural reason the residual is inert). The measured
  fixture surface is three named sites (§6.4), not thirty.
- **B without a CTL-13 motion leaves the invariant over-claiming.** B's record §2
  concedes CTL-13's "the adapter cannot choose its dataset id" "remains
  non-structural in the selection sense" — but plans no invariant amendment, leaving
  the bound that matters recorded only in an uncommitted design record. Under this
  repo's claim discipline (rubric G4: a *cannot* needs its structural reason inline,
  in the durable surface), B's merge must either carry that honesty amendment or be
  followed immediately by this slice, whose amendment (§8) supersedes it. If the
  maintainer adopts B's §2 position as final and never takes A, the conditional
  deliverable is B's amendment naming the selection residual as the disclosed
  non-structural bound — stated here so that ruling has a recorded alternative.

## 2. Root cause, restated to cover both halves

Slice 1's §11 already names the conflation: a host-computed VALUE (`ds:{op}`) was
mistaken for a host-chosen KEY. The refute split it into two defects, and the two
candidates each close one:

- **Introduction** (the executed HIGH-1): `mint_payload_id`'s fallback let a member
  call create per-operation state under any name, so "a future operation has no mint"
  was false. B closes it: no state without a host dispatch.
- **Selection** (the surviving half, disclosed in B's §2): during dispatch X, an
  adapter names a PAST, minted-but-unadmitted operation P on the context it passes
  (or rewrites on the live one) and `admit` keys on P. B leaves this fully workable,
  and its M10/M11 bounds are weak in exactly the way B's record concedes: M10 fires
  only when P's action's input schema declares `configuration_id`/`acquisition_id`
  (a permissive-output action has no structural bound), and M11 is satisfiable by the
  thief itself, because `payload_create`/`payload_finalise` under P are legal under B
  (P is minted) and `note_payload_finalised` keys on the same adapter-named
  `context.operation_id` — the thief stages REAL artifacts under P's name and M11
  passes by construction. Inline-value manifests reference nothing and pass trivially.

**Trace of the selection attack on the B head** (why this is not analysis but a
reachable path — the build's RED run executes it): dispatch op-1 (invoke, plain
non-dataset result — op-1 is now minted, unadmitted); dispatch op-2, whose `execute`
rewrites `context.operation_id = "op-1"` (or passes any object carrying it), calls
`payload_create`/`payload_append`/`payload_finalise` under that context (all legal:
op-1 is minted), then either calls `dataset_publish` with a manifest carrying
`ds:op-1`, or returns it as op-2's dataset-shaped result. Both entrances key on the
context's op-1, find op-1's mint, and admit. The run record now attributes op-2's
adapter-authored dataset to op-1.

**Why the residual matters at this repo's own bar:** the issue's severity ruling is
"treat the claim as the defect". CTL-13 and the GW-1 record claim the adapter cannot
choose its dataset id; under B it chooses among the run's minted-unadmitted ids. And
the realistic non-hostile case is a buggy adapter that reuses a retained context
(forbidden by the guide, written by real code anyway): under B that misattributes
silently; under A it refuses loudly. Attribution of evidence to the dispatch that
produced it is the run record's job (A06 posture); a record that launders it is wrong
even with every gate green.

## 3. What A adds over B, stated as one sentence each

- Under B: the adapter cannot make the controller believe an operation exists that
  the host never dispatched.
- Under A: the adapter cannot make admission believe a publish belongs to any
  dispatch other than the one currently executing — which is the dispatch that
  produced it.

## 4. The mechanism (the whole production diff)

Four edits, no new module, no ContextVar, no payload-member motion.

1. **`DatasetAdmission.admit` signature** (`src/benchweave/content/dataset_services.py`):
   `def admit(self, manifest: dict[str, Any], operation_id: str) -> dict[str, Any]`.
   The context parameter drops entirely — identity (`operation_id`) is host-supplied,
   and `_stamp_evidence_quota` takes the same host-supplied id (the stamp's operation
   binding is the same key defect one layer down; the bridge's classifier already
   compares the stamp against the host's `request.operation_id`, so a forged binding
   there only harms the forger — rerouting is consistency, not a closed hole). M10
   and M11 take `operation_id` as parameters already; they inherit the host-supplied
   key by construction. The identity block becomes:
   `state = self._controller.dispatch_state(operation_id)` — unchanged text, now fed
   a host-named key.
2. **The bridge's result gate** (`src/benchweave/host/otdp_bridge.py`, the invoke
   branch of `_convert`): `self._dataset_admission.admit(payload, request.operation_id)`
   — the host-known id is already load-bearing one line up (the envelope correlation
   refuses `result["operation_id"] != request.operation_id`), so this is the same
   authority the gate already trusts.
3. **The controller's current-dispatch record** (`dataset_services.py`,
   `DatasetController`): `begin_dispatch(operation_id)` / `end_dispatch()` around a
   `current_dispatch` property (a plain `str | None` slot; the controller is
   per-bridge — constructed in the per-plugin load path — so no cross-bridge
   sharing exists). The bridge calls `begin_dispatch(request.operation_id)` for every
   verb where the controller is armed, immediately before the dispatch `try` (after
   the gates, after gate I6), and `end_dispatch()` in a `finally` appended to that
   `try` — bracketing `execute`, `_convert`, and the classified-failure epilogues.
   The row-B dispatch clamp (`otdp_bridge.py` invoke/capture `ExitStack` brackets) is
   the in-tree bracket precedent; the SDK's admission-surface ContextVar (its seam
   set around the dispatch, read at admission) is the cross-repo semantic precedent —
   the gateway shape needs no ContextVar because the bridge is single-dispatch (§4.1).
4. **The bundle's `dataset_publish`** (`_InvokeMembers.dataset_publish`): signature
   UNCHANGED `(manifest, context)` (REG-4 pins the member surface); the context's
   role shrinks to what it still legitimately carries (nothing, on this member —
   cancellation checks live on the payload members). The body becomes:
   `operation_id = self._controller.current_dispatch`; `None` raises
   `DatasetServiceRejected("dataset_publish requires the operation the host is "
   "dispatching (no live dispatch: out-of-dispatch publication is refused)")` — the
   arms match `no live dispatch`; otherwise
   `return self._admission.admit(manifest, operation_id)`.

The refusal ordering inside `admit` is untouched (identity → idempotency → schema →
M-checks → routing); a refused admission still persists nothing.

### 4.1 The concurrency bound (consequence b, answered)

The single-slot record is sound because one live dispatch per controller is
structural, not assumed: `dispatch` holds the bridge RLock for its whole body;
same-thread re-entry is refused at `_require_sync` (a running loop is the caller's
execute context); and each bridge owns its controller exclusively (per-plugin
construction). Above the bridge sit A03 (one controlling procedure per bench) and
STO-3 (one coordinator per store). Nothing today detects interleaving — there is
none to detect — so the structural reason is carried in CTL-13's amendment (§8): a
future change that breaks dispatch serialization must revisit that row before the
single-slot record stays credible.

**The stale-caller disclosure** (verified fact, not conjecture): `asyncio.Runner`
reuses one loop across `run()` calls, so a task the adapter created inside dispatch X
can run during dispatch Y, and an OS thread holding the bundle can call members at
any time. Under A: such a caller reads the CURRENT record (Y) and its manifest must
carry `ds:Y` — an id that never crosses dispatch boundaries (each envelope is
visible only to its own execute) — so an id-ignorant stale caller refuses on the
identity mismatch. The residual is a stale caller that LEARNS the live id by other
means; the tightening that would refuse stale callers outright (binding the member
entrance to the live context object's identity, `context is live_context`) is named
and NOT taken — the manifest-must-carry-the-live-mint check already bounds every
caller that cannot name the id, and the remainder is trusted-Python territory
(A05's documented boundary). Disclosed here so the refute lane can challenge the
ruling.

## 5. What this slice deliberately does not do

- **No payload-member motion.** `payload_create`/`append`/`finalise`/`abort` keep
  their context-derived operation naming. Structural reason this is inert: admission
  never reads a key it was not handed host-side (both entrances), and B bounds state
  creation to host-minted ids; the worst a hostile adapter can now do is stage
  artifacts and consume session quota under a PAST minted op's name — quota it could
  consume under its own name identically. A buggy adapter mislabelling payload
  bookkeeping is a disclosure, not an admission defect. Binding the payload members
  to the current dispatch (with the out-of-dispatch refusal extended to them) is
  deferral D2.
- **No corpus or standards motion.** The extension contracts tie publication and
  payload staging to "the current operation/acquisition" — the corpus already speaks
  in exactly the terms A enforces. No vendored byte moves; no governance pass.
- **No device-developer-guide edit.** Every published sentence stays true: the guide
  already instructs "Do not … retain contexts for later use" and describes
  `dataset_publish` as the mid-execute entrance ("actions that must publish before
  they return"). Obligation 3 walked, zero motion, disclosed.
- **No `dataset_lookup` change.** Lookup by explicit id over this run's admitted set
  is its documented behavior; identity binding does not apply to reads.

## 6. Arms

1. **ARM-2d, bridge — the selection carrier (RED on the B head):** beside ARM-2c in
   `tests/unit/test_otdp_bridge.py`. A two-invoke adapter: op-1 returns a plain
   (non-dataset) result; op-2's `execute` rewrites `context.operation_id` to op-1's
   id and returns a valid manifest carrying `ds:op-1`. Assertions, in order:
   `status is UNKNOWN` with `PROTOCOL_ERROR` carrying "does not carry the
   host-minted id"; `admitted_by_dataset_id("ds:op-1") is None` (nothing filed under
   the stolen id); `admitted_by_dataset_id("ds:op-2") is None` (nothing admitted for
   the dispatch at all). RED on B's head exactly as §2's trace (dispatch returns OK
   with the manifest admitted under `ds:op-1`).
2. **Unit member-path selection twin (RED on the B head):** in
   `tests/unit/test_dataset_services.py` — harness brackets dispatch `op-a`;
   `dataset_publish(a_valid_manifest("ds:op-b"), harness.context("op-b"))` where
   `op-b` is minted-but-unadmitted: expect `DatasetServiceRejected` matching "does
   not carry the host-minted", nothing admitted under either id. Pins the member
   entrance independent of bridge wiring; RED on B's head (admits under `ds:op-b`
   today).
3. **The dispatch-transition arm — consequence (c)'s own arm, not a footnote
   (RED on the B head):** same harness: with the bracket open (`begin_dispatch`
   called), an honest publish admits (the positive control that sanctioned
   mid-execute publication survives); after `end_dispatch()`, the same publish with
   the same honest context refuses matching `no live dispatch`, and nothing further
   is admitted. RED on B's head at the second phase (out-of-dispatch publish with a
   context naming a minted op admits today).
4. **Fixture updates, named (consequence d):** the harness gains an `enter(op)`
   helper over `begin_dispatch`, called for `op-a` in `__init__` beside the existing
   mint; the one op-switching publish arm (`test_w2_publish_evidence_quota…`, op-b)
   and the one-core arm's direct `admit` call (mechanical: context argument →
   `"op-b"`) move with it. The payload-only arms (op-x/op-y, op-prior) do not move —
   no payload member reads the record. Surveyed against every direct
   publish/admit site in the file: three named sites, not thirty.
5. **Unchanged and must stay green without edits:** everything B's §5.4 set carries
   (ARM-1..ARM-8, ARM-2b, ARM-2c, the mint-door pin, I6, R2/R2b, R8, W2, quota,
   read-allowlist, publishing-adapter OK, R15, the capture-evidence policy pair) —
   ARM-2c green on the B head is itself a pin that A must not disturb (A's identity
   refusal fires where B's mint refusal fired; same observable).

## 7. Pre-committed acceptance rule (written before any post-fix run)

- **Metric:** binary, over the enumerated set {ARM-2d, the member-selection twin,
  the dispatch-transition arm}: RED on the candidate-B head, GREEN at this slice's
  head; the §6.5 pin set green with no edits beyond the three named fixture updates;
  one cold full battery at the slice head, counts read from `--junitxml` attributes
  or true exit codes, never a filtered summary line.
- **Effect size / sample size:** one RED run and one GREEN run per arm (n=1 each;
  deterministic unit tests — direction is the evidence, repetition is not).
- **Ship if:** the pre-fix RED runs fail with the B-head signatures (ARM-2d and the
  twin: dispatch OK / no refusal raised with the manifest admitted under the stolen
  id; the transition arm: `DID NOT RAISE` at the post-`end_dispatch` phase);
  post-fix all three green; battery, bare `ruff`, fresh-cache bare `mypy` green;
  `tests/win_core_manifest.json` refreshed through the script's own path moving
  exactly the two totals this slice adds (`test_otdp_bridge.py` 150→151 with ARM-2d
  on top of B's landed head, `test_dataset_services.py` 33→35 with the two unit
  arms) and nothing else.
- **Kill (mechanism wrong):** any selection arm still admits post-fix — the identity
  is still reachable from the context — stop, do not patch the arm. Any §6.5 pin
  fails for a reason the three fixture updates do not honestly cover — a ruled
  behavior was narrowed (the #604 host-admits-on-result ruling included) — kill the
  slice and redesign.
- **Kill (slice unnecessary):** if the maintainer adopts B's §2 position — the
  within-run selection residual accepted as final — this slice does not build; the
  recorded alternative is B's CTL-13 honesty amendment (§1.2). A build that starts
  after that ruling has voided its own premise.
- **Underpowered, not conclusive:** a RED run with zero collected / exit 5, or a
  count read from a filtered summary — void evidence; fix the probe and rerun before
  any decision. A GREEN claimed without the RED captured on the B head first is
  void for the arms this slice carries.

## 8. Invariant and drift impacts

- **CTL-13 gains its second dated amendment** (the amendment text, forward-only):

  *Amendment (2026-11-09, gateway issue #606 HIGH-1, second): the first amendment
  bound the identity VALUE to the mint record and left the KEY on the adapter-held
  context; the mint-door close (payload staging under an operation the host never
  dispatched refuses, no state created) made the key space host-authored, and this
  amendment makes the KEY itself host-supplied: `admit` takes the operation id as a
  host-side argument — the bridge's result gate passes `request.operation_id` (the
  dispatch the host performed), the bundle's `dataset_publish` reads the
  controller's host-side current-dispatch record (set in `dispatch` where gate I6
  mints, cleared in the dispatch's `finally`) — and no attribute of the
  adapter-held context is an identity input, for value or key. The adapter may
  neither introduce an id (the closed mint door) nor select among this run's minted
  ids (the dispatch binding): admission attributes a manifest to exactly the
  dispatch that produced it. The single-slot current-dispatch record is sound
  because one bridge serializes dispatches under its lock with same-thread
  re-entry refused at the running-loop guard, and each bridge owns its controller
  exclusively; a change that breaks dispatch serialization must revisit this row.
  Disclosed ruled change: `dataset_publish` outside a live dispatch (retained
  bundle, post-return, open or close time) refuses — the developer guide already
  forbids retaining contexts, and the corpus ties publication to the current
  operation. M10/M11 inherit the host-supplied key by construction. Pinned by the
  selection and dispatch-transition arms beside ARM-2c.*

- **REG-4 untouched:** `dataset_publish`'s signature is unchanged; `_Context`'s
  attributes stay and the host still sets them (the agreement test's documented
  `dataset_id` gap stands).
- **Obligations walked:** 1/2 no (no MCP tool, no API surface — the new refusal
  rides the existing `DatasetServiceRejected` → `PROTOCOL_ERROR` channel, which the
  contract bytes do not enumerate, per slice 1's verified grep). 3 satisfied with
  zero motion (§5). 8 no (member surface identical; one internal identity source).
  23 no. 5/6/7 no (no fixture-lattice, vendored-byte, or submodule motion). The
  windows ratchet row: the two per-file totals move through the manifest script's
  own refresh path, and `tests/contract/test_win_core_partition.py` green at the
  slice head is part of the battery — the count motion is disclosed here, not
  discovered at CI.
- **On-disk formats/schemas:** none (the manifest json is a CI count registry, not a
  product format; Tier 3 is taken by dispatch and the record's own scan table).
- **CI cost:** no new lane, workflow, or dependency. Three tests, four production
  edits, three fixture sites, one invariant amendment, one count-registry refresh.
  The Tier-3 cost is the mandatory refute lane plus one cold battery.

## 9. Tier and keyword scan (#254, design-time)

**TIER 3.** By dispatch: identity on the admission path (the same ground as slice 1).
The expected diff's path rules fire no Tier-3 rule (no `contracts/`, `standards/`,
persisted-format surface, `registry/`, fixture lattice, dependency, or submodule
motion). Keyword scan — run by `grep -c` over this record's saved text (the dominant
diff component; the production and test diffs are authored to carry none of the
eight — no new imports, no token-bearing identifiers), counts as measured at commit
time: `threading` 1, `asyncio` 3, `subprocess` 1, `sha256` 1, `hashlib` 1,
`migrate` 1, `recovery` 1, `protection` 1 — ten hits, nine of them this §9 passage's
own keyword tokens (the rubric's intended self-fire; the labels are the only
occurrences of seven of the eight), and the one hit outside this passage is
`asyncio` at §4.1's loop-reuse disclosure, a deliberate, load-bearing naming of the
runner mechanism the concurrency bound rests on. The review re-derives both
derivations independently; a disagreement between the record's counts and the diff
is a review finding, and this record is not retro-edited to resolve it.

## 10. The six consequences, resolved

- **(a) The out-of-dispatch mint fallback.** Ruled by B, already in-flight: staging
  under an unminted operation refuses and creates no state — the "staged but
  never-admissible" option is moot because nothing is staged. This slice's remaining
  surface is the publish-side twin: `dataset_publish` outside a live dispatch
  refuses (`no live dispatch`), pinned by the transition arm. Payload members keep
  context-derived naming (§5, structural reason inline); extending the refusal to
  them is D2.
- **(b) Concurrency.** §4.1: the bound is the bridge lock + the running-loop re-entry
  guard + per-bridge controller ownership; the CTL-13 amendment carries the
  structural reason and the revisit trigger. Nothing detects interleaving because
  none is representable today.
- **(c) The disclosed behavior change.** Adopted with its own arm (the transition
  arm's second phase), not a footnote: the guide already forbids retained contexts;
  the corpus already ties publication to the current operation; the guide walk is
  zero-motion because no published sentence becomes false.
- **(d) Fixtures.** §6.4: the `enter(op)` seam; three named sites. The W2 op-b arm
  becomes an enter-dispatch fixture as the brief anticipated.
- **(e) The SDK.** What transfers: the principle — identity host-supplied at both
  entrances — and the specific finding that the SDK's explicit member path
  (`dataset_admission.py`, `getattr(context, …)` for both value and key) has the
  same two-defect split; its inline path is already clean by capture-before, which
  is A's semantic arrived at through record authorship. What does not transfer: the
  gateway's bridge/`request.operation_id` plumbing (the SDK seam constructs its own
  contexts) and the plain-slot record (the SDK already has the ContextVar bracket
  its seam sets around the dispatch — its fix binds at that bracket). The SDK half
  stays open on #606 (`Refs`, not `Closes`), and its slice re-derives the two-candidate
  split against its own seam rather than importing this shape blind — per the SDK
  session's own correction in the issue.
- **(f) CTL-13.** §8: the second dated amendment — value AND key host-side, with the
  serialization reason and the disclosed refusal change inline.

## 11. Deferrals, named

- **D1 (conditional, maintainer's call):** if A is ruled unnecessary, B's CTL-13
  honesty amendment naming the selection residual becomes the deliverable (§1.2,
  §7 kill direction).
- **D2:** payload-member dispatch binding (extend the live-dispatch requirement to
  `payload_create`), with its own RED demonstration and fixture walk.
- **D3:** the member-entrance object-identity tightening (`context is live_context`)
  — §4.1 names it and why it is not taken.
- **D4:** the SDK standalone host's explicit member path — the open half of #606.
- **D5:** cross-principal dataset authorization — the standing deferral, untouched.

## 12. What this record does not cover — completeness, with structural reasons

- **The payload lane's operation labelling** stays adapter-named (D2). Not open for
  admission: admission reads only host-named keys (both entrances, this slice) and
  only host-created state (B); a mislabelled payload key is unreachable from
  admission by construction, not by testing.
- **A stale caller that learns the live dispatch's id** (§4.1) can publish under it
  mid-dispatch from outside that dispatch's own execute. Structural reason it is
  open: the member entrance deliberately does not authenticate the caller (the
  protocol has no handle to authenticate with); the bound is that the id never
  crosses dispatch boundaries, so learning it requires a channel this design does
  not provide. D3 is the close if that line is judged to matter.
- **The capture lane** carries the same attribute shape in its abort-stamp
  (`getattr(context, "operation_id")`) — observed, same-class, and NOT claimed
  here: the stamp is a discriminator input, not an admission key, and the writer
  keys captures by the gate-minted capture id the adapter merely echoes. A finding
  for its own row if the refute lane disagrees with that bound.
- **Nothing here asserts anything about measurement authenticity** — CTL-13's
  founding disclosure stands: a schema-valid manifest of invented values passes both
  entrances. Identity binding attributes; it does not verify.

## 13. Top risks, each with its falsifier

1. **A legitimate out-of-dispatch publish exists that this pass missed.** Falsifier:
   any §6.5 pin failing post-fix for a reason the three fixture updates do not
   cover — the acceptance rule's kill direction fires. Searches performed: `admit`
   has one `src/` caller (the result gate); `dataset_publish`'s production callers
   are adapter code mid-execute (the bridge suite's publishing-adapter arms); the
   corpus ties publication to the current operation.
2. **The single-slot record is wrong under some interleaving this pass did not
   find.** Falsifier: any demonstration of two overlapping dispatches on one bridge
   — the lock, the loop guard, and per-plugin controller construction each forbid
   one; a demonstration breaks all three analyses at once and CTL-13's amendment
   names the revisit.
3. **The selection residual is judged acceptable, making this slice gold-plating.**
   Falsifier: the maintainer's ruling (D1). The record is written so that ruling is
   cheap to take — B stands alone with its honesty amendment.
4. **The fixture seam (`enter(op)`) masks a real behavior** — a test that brackets
   the dispatch differently from the bridge does. Falsifier: ARM-2d and the bridge
   publishing-adapter arms pin the real dispatch path; the seam exists only for
   unit arms that were already calling the core directly.

## 14. Addendum (2026-11-09, post-dispatch): the ruling — B plus the honesty amendment; this slice deferred with its design in place

The maintainer ruled on the fork §1.2 and §7 named: **candidate B lands, with the
CTL-13 honesty amendment made mandatory for its merge** (the introduction-sense vs
selection-sense bound, M10/M11's actual limits inline — the amendment text this
record's §1.2 drafted); **this slice does not build now.** The ruling's stated
ground: two mechanisms in one slice, in a slice already refuted once, is how a third
attempt happens. B closes the demonstrated exploit at a door with no legitimate
traffic; the selection residual stays named, bounded, and carried. §7's "Kill (slice
unnecessary)" direction fired by ruling before any build ran — no RED was captured
for this slice's arms and none is claimed by this record.

Two provenance corrections, dated, so the record preserves events as they happened:

- **The ARM-2c carrier assignment was the dispatcher's error, not the builder's and
  not this record's.** §1.1 identified the assignment as wrong on the evidence; the
  assignment itself came from the dispatch brief ("already RED, so the pre-commitment
  is cheap"), and its author has since acknowledged the error. The analysis stands;
  the error is not the builder's and not inherited from this record.
- **This record is the follow-up slice's design, and its evidence has a stated
  shelf.** The §2 trace was derived against candidate B's working-tree diff as read
  at design time (the header quotes the form). The follow-up build must re-verify
  the trace and re-capture its arms' RED on the actually-landed B head before
  building, and re-affirm the premise §7 names — a build starting after this ruling
  has voided its premise unless it re-derives it against the landed head.
