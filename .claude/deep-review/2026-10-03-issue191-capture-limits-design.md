# Issue #191 — `capture_limits` class bound (the `max_samples`/`max_bytes` ceiling question) — design record

- **Date:** 2026-10-03 · **Base:** `origin/main` `c183db4` · **Register:** engineering (internal record, not ASD-STE100)
- **Verdict:** **DEFER** — the class-bound question has an empty evidence denominator today, the harm it
  guards against is already contained by a commissioned, A02-aligned mechanism, and the only
  corpus-defensible number available now has no runtime consumer. The deferral rows (§8) carry
  sharpened, observable reopen triggers. Owner override forks are named in §9.
- **Standards touch (this increment):** **none**. No `standards/` bytes and no version strings move in
  this record's commit. The deferred train (§10) would touch them; that is stated, not done.

## 1. The question, restated precisely

`capture_limits.max_samples` and `capture_limits.max_bytes` in the OTDP 0.2.2 device-descriptor
schema are `{"type": "integer", "minimum": 1}` with no `maximum`
(`standards/otdp/0.2.2/otdp-device-descriptor.schema.json:194-214`). A device may therefore declare
`max_samples = 2**53-1` — or, because JSON Schema `integer` is unbounded above and Python parses
arbitrary-precision ints, `2**60` — and the declaration is schema-valid. The issue asks: is a
device-class ceiling (mirroring issue #64's `sample_count` 1e6 / `averaging_count` 64 bounds)
warranted, enforced where — admission vs runtime — with what evidenced number; or should the
unbounded state stand with an explicit rationale on record?

## 2. The capture path as it stands (verified map)

Every number below was read on `c183db4`; anchors are `file:symbol/line` at that commit.

1. **Procedure document** — the capture step carries `sample_count` and `max_bytes` as literals,
   each `{"type": "integer", "minimum": 1}`, no maximum
   (`standards/execution/0.2.0/procedure.schema.json`, `$defs.step` capture branch; the SDK's
   vendored copy is byte-identical at `packages/sdk/src/benchweave_sdk/standards/execution/0.2.0/`).
   Capture steps admit no reference positions (CTL-7's closed branch) — the values are reviewable
   literals in the admitted document.
2. **Admission** — `src/benchweave/control/semantics.py::_check_capture_declared` (CTL-7 mirror,
   :237-313): the bound device must declare `artifact_writer` + `capture_formats` +
   `capture_limits`; the step's `format` must be declared; `sample_count ≤ max_samples`;
   `max_bytes ≤ max_bytes`. Six `capture_undeclared:` refusal sites. **No absolute bound and no
   quota awareness** — the mirror compares request literals against the device's declaration only.
3. **Executor** — `src/benchweave/control/executor.py::_step_capture` (:1170-1207): builds
   `{capture_id, format, sample_count, max_bytes}` from the step literals, consults the capture
   allow-rule (`check_allowed`, deny-by-default), clamps the deadline, dispatches.
4. **Bridge gate, pre-dispatch** — `src/benchweave/host/otdp_bridge.py::OTDPBridge._capture_gate`
   (:585-717): request `sample_count`/`max_bytes` must be exact-type ints in **[1, 2^53−1]** (the
   `_INT_MAX` gate — the issue's named ceiling); waveform arithmetic `count×8 ≤ byte_cap`; the
   descriptor's limits are type-validated (int ≥ 1) and the request compared against them; then
   `open_capture` runs **inside the gate region — zero adapter calls on any refusal**.
5. **The staging store's quota — the effective byte ceiling** —
   `src/benchweave/content/capture_store.py::CaptureStagingStore.open_capture` (:194-279): refuses
   when `max_bytes > min(max_capture_bytes, max_dataset_bytes − used)`, atomically under
   `BEGIN IMMEDIATE`, raising `CaptureQuotaExceeded` → the bridge maps it to
   `RESOURCE_LIMIT / NOT_DISPATCHED`. `append` enforces the reservation mid-flight; the dataset
   ceiling accumulates across captures in the context. `max_capture_bytes` defaults to 16 MiB and
   `max_dataset_bytes` is **required** at every construction site
   (`src/benchweave/host/services.py::QuotaLimits`, :19-47 — "fork-3 HINT defaults … commissioned
   values come from bench qualification (A02)"; wired per-run at
   `src/benchweave/interfaces/app.py::_run_quota_limits`, :519-543). The quota formula is pinned by
   `tests/unit/test_capture_store.py` (module docstring states it; e.g.
   `test_open_is_capped_by_mc_never_by_mc_minus_used`, `test_open_refuses_a_context_already_over_the_dataset_ceiling`).

**Where the bound is enforced today, then:** bytes — at the run's commissioned quota envelope,
pre-dispatch, typed, honest (A06-compliant: refused, not silently truncated); samples — on the
`waveform_f64le` lane, transitively (count×8 ≤ max_bytes ≤ quota, so ≤ 2 Msamples at the 16 MiB
default); on `raw_binary`, `sample_count` drives no allocation anywhere in the walked path (the
manifest's `byte_length`/`sha256` are host-computed over delivered bytes; delivered bytes are
bounded by the reservation).

## 3. What an unbounded declaration can and cannot do (the containment argument)

A descriptor declaring `max_samples`/`max_bytes` at or beyond 2^53−1:

- **causes no allocation and no device work by itself** — the declaration is only ever *compared
  against*. Every byte the host stages is sized by the request's `max_bytes`, which the quota
  bounds regardless of the declaration.
- **cannot push a request past the quota** — a request the declaration admits still faces
  `open_capture`'s allowance; the refusal is `RESOURCE_LIMIT / NOT_DISPATCHED` from the gate
  region with zero adapter calls and zero forensic rows.
- **can admit a procedure that will predictably fail at dispatch** — the real seam the issue
  names. A capture step whose `max_bytes` exceeds the run's `max_capture_bytes` passes admission
  (the mirror never sees the quota), then at execution the body terminates
  `BODY_EXECUTION_ERROR` at that step (`executor.py::_dispatch` NOT_DISPATCHED branch, :1240-1250);
  every body ending takes the approved safe transition (A12). **The observable cost is an aborted
  run plus one protective pass — an availability cost, not a hazard.**
- **can claim a capacity the numeric interface cannot express** — §4 of the OTDP specification:
  values outside −(2^53−1)..2^53−1 "are unsupported by this revision's numeric interface", and
  semantic check S02 makes the interoperable range an authoring requirement. Today that rule is
  prose only for these two fields: the schema has no `maximum`, the gateway's S02 mirror checks
  only parameter-bounds ordering (`src/benchweave/control/documents.py::_check_semantic_mirrors`,
  :758-812 — it never touches `capture_limits`), the SDK checker is census-pinned equivalent to
  that mirror, and the bridge validates the declaration only as int ≥ 1. A `2**60` declaration is
  schema-valid, mirror-clean, and admitted. **Runtime effect: none** — every legal request
  (≤ 2^53−1) passes anyway; the declaration has no consumer above the range.

## 4. The evidence census (the denominator a class bound would need)

In-tree descriptor-shaped sites at `c183db4`: **23** — 4 plugin descriptors
(`plugins/benchweave/{sim_controller,sim_psu,sim_scope}/…`, `plugins/fnirsi/dps150/…`) and 19
documents under `standards/otdp/0.2.2/examples/`. **Capture-bearing: exactly 1** — the synthetic
`examples/reference-capture.json`, declaring `{max_samples: 1024, max_bytes: 8192}`, whose §12
values the specification itself scopes: "Values and limits here belong to these examples only;
they are not the user's bench limits." The device-profile catalog (the class-action home where
#64's bounds live) contains **zero** capture mentions — capture is a per-descriptor integration
declaration (spec §7: "These are device integration capacities, not bench safety limits"), not a
class action.

## 5. Applying the #64 discipline to this question

The #64 record (`.claude/deep-review/2026-09-19-issue64-catalog-averaging-samplecap-design.md`)
fixed the evidence rule for corpus bounds, in its own words: "corpus bounds carry the largest
value the in-tree evidence supports. Widening for a real instrument later is another reviewed
revision", and "Writing normative semantics for classes with no exercising plugin or lane is
speculative standardization — the exact thing A10 warns against." #64's numbers had real
denominators: sim_scope's authored envelope (`[1, 64]` averaging; `1_000_000` samples, "32 MB of
float64 across four channels") and a **live defect** motivating the train (refute F1: a
lane-passing preset with huge `sample_count` OOMs fetch; the honest residual was a pinned test
asserting lane 1 exits 0 on a 1e12 preset).

#191 has neither: the denominator is one synthetic example whose values the spec disclaims as
bench-relevant, and there is no runtime defect — the quota contains the harm (#64's gap let a
huge request *reach* fetch and OOM; here a huge request is refused pre-dispatch with zero device
calls). A class ceiling invented now (1024? 8192? 16 MiB?) would be exactly the unevidenced
number #64 refuses, and would bind every future capture class to a synthetic example's shape.

## 6. Why the §4 interoperable bound is not worth a train today

The one number that *is* evidenced today is `9007199254740991` (2^53−1) — spec-derived, not
bench-tuned. Adding `"maximum": 9007199254740991` to the two descriptor fields would follow an
established corpus idiom: the interface corpus uses that literal pervasively
(`standards/interface/0.1.0/interface.schema.json`, `mcp-tools.json` — 100+ sites). Two reasons
it still does not justify a train now:

1. **The asymmetry with the interface corpus is justified by transport, not drift.** The
   interface's integers cross JSON-RPC/HTTP client boundaries where 2^53 is a real interop
   cliff, so the bound belongs in the schema those clients validate against. The descriptor's
   `capture_limits` is consumed by the gateway's exact-byte decoder and Python comparisons
   only; it never crosses a client numeric boundary. The request side — the values that *do*
   get bound into SQLite — is already range-bounded in code at the consumer
   (`_capture_gate`'s A5 comment names this: "the spec §4 interoperable bound, which keeps the
   sqlite bind structurally safe"). The bound already lives where the risk lives.
2. **Zero runtime teeth, full train cost.** A tightening is a MINOR-class bump by #64's
   precedent (0.2.2 → 0.3.0), which drags: the copy-never-move corpus dir + manifest rows, the
   SDK vendored sync (two commits, stacked PRs, `make sync-sdk-standards`), cross-constraints,
   the descriptor-validator's version prefixes, the equivalence census extension, repins, the
   bump-window rule, and the standards-governor pass. That cost bought real interop in #64
   (a demonstrated OOM class); here it buys schema symmetry on a field with no
   beyond-range consumer. A rider without a defect is motion the governance discipline exists
   to prevent; if the train opens for another reason, this two-line edit is a legitimate
   agenda item for it (§10 bundles it).

## 7. Verdict

**DEFER.** Concretely:

- **No class ceiling is derivable today** — the denominator is one spec-disclaimed synthetic
  example (#64 rule; A02's "never a constant tuned on one bench" extends to "never a constant
  tuned on one example").
- **The unbounded declaration is contained** — bytes by the commissioned run quota pre-dispatch;
  waveform samples transitively; `raw_binary`'s `sample_count` allocates nothing. The residual
  is an admission/runtime seam whose worst case is an aborted run plus the approved safe
  transition — availability, not protection.
- **The spec's own semantic rules already cover the authoring duty** (§4 range, S02, S16
  "captures obey format/sample/byte/time bounds"); what is missing structurally (schema
  `maximum`, mirror range clause) is named below with its trigger, so the future train starts
  from this analysis rather than rediscovering it.

This is also the outcome the issue pre-armed: its own trigger ("the first multi-class capture
corpus, or a governance class-bound pass — whichever first") has **not fired** — the OTDP corpus
has not moved since the issue was filed (`git log --since=2026-09-24 -- standards/otdp/` is
empty; 0.2.1/0.2.2 were the transport-provider trains), no class-bound pass has opened, and the
in-tree capture census is unchanged (§4).

## 8. Deferral table

Home for all rows: **follow-on issue #191** (it stays open as the carrier; this record is its
analysis of record). Row ids are stable for future citation.

| id | deferred | home | reopen trigger (observable; inspection named) |
|---|---|---|---|
| D-191-1 | The evidenced ceiling on `capture_limits.max_samples`/`max_bytes` — schema `maximum` at the largest in-tree authored envelope (the #64 rule), plus the runtime-schema request mirrors and the census cells (§10 sketch) | follow-on issue #191 | A capture-bearing device descriptor is admitted in-tree — inspection: a `plugins/*/src/*/descriptor.json` whose parsed JSON carries `capture_limits` (census at `c183db4`: 0 of 4); **or** a second capture-bearing document lands under `standards/otdp/<v>/examples/` (census: 1 of 19, `reference-capture.json` only); **or** a governance class-bound corpus train opens; **or** the owner's explicit call on the tracker. Nearest plausible carrier: the first real capture-capable plugin integration (the sim_scope-to-#64 shape — its authored envelope becomes the denominator). |
| D-191-2 | The admission-time per-capture-ceiling mirror — `_check_capture_declared` (or its caller) additionally refusing a capture step whose `max_bytes` exceeds the run's configured `max_capture_bytes` (the `min()` term admission *can* see; the `max_dataset_bytes − used` term stays runtime-only by nature) | follow-on issue #191 | A real run's evidence trail shows a capture step refused `RESOURCE_LIMIT / NOT_DISPATCHED` with the `allowance … exceeded` message (the bridge-gate refusal of an *admitted* procedure) — inspection: run event log / `capture_staging` absence with the typed error on a capture step. Fixtures do not fire this; the seam must become load-bearing in a real run. |
| D-191-3 | The S02-mirror range clause — gateway `_check_semantic_mirrors` and the SDK checker both refusing `capture_limits` values above 2^53−1 (code-only, no corpus bytes; makes gateway+SDK deliberately stricter than the vendored schema, a sanctioned census posture that must be named as a cell) | follow-on issue #191 | Bundled with D-191-1's train (same trigger), **or** standalone on: a descriptor declaring `capture_limits` above 2^53−1 observed in any registry admission attempt, in-tree fixture, or published package — inspection: the declaration census over admitted descriptors/fixtures. |

## 9. Owner forks (available overrides; not taken)

1. **Build the §4-range structural bound now** (0.3.0 train, two schema lines + mirrors + census)
   for interface-corpus symmetry — rejected here per §6 (no runtime consumer; full train cost),
   but it is a legitimate governance-taste call the owner can make.
2. **Close #191 as unbounded-by-decision** (the issue's other named outcome) — rejected here:
   the trigger conditions are cheap to hold, the first real capture plugin makes an evidenced
   number derivable, and closing would strand this analysis off the tracker. Recommended only
   if the owner judges capture-bearing plugins unlikely for the foreseeable horizon.

## 10. The trigger-fired train, pre-designed (so it starts designed, not rediscovered)

When D-191-1 fires, the increment is the #64 shape applied to the descriptor surface:

- **Mechanism:** `"maximum": <N>` on both `capture_limits` fields in the new OTDP version's
  descriptor schema (copy-never-move from 0.2.2; manifest rows cite the old corpus path as
  `source`), where **N = the largest in-tree authored capture envelope at train time** (the
  admitted plugin's declared `max_samples`/`max_bytes`, mirroring how #64 took sim_scope's
  1e6/64 — never an invented headroom number). Same `maximum` on the runtime schema's capture
  request arguments and the `captureManifest.sample_count` echo (the #64 "output mirrors bounded
  too" rule — a device echoing above the bound is malformed evidence). The S02-mirror range
  clause (D-191-3) and, if the corpus moves to a schema-`maximum` form, the gateway/SDK mirrors
  ride the same train.
- **Where enforced:** all three layers the path already has — schema (structural), S02 mirrors
  (gateway + SDK, census-pinned equivalent), and the existing bridge gate stays as the
  defense-in-depth backstop.
- **Acceptance (pre-committed now):** RED — a descriptor declaring above N is refused by the new
  schema in both checkers (exit nonzero; the #64 `test_settings_envelope_census_top_level`
  pattern: the mutation-matrix cell `("capture_limits.max_samples", N+1, True)` flips from
  lane-exit-0 to lane-refusal), and a procedure capture step above N is refused at *admission*
  with `capture_undeclared:` (it already would be, via the declaration comparison, once the
  declaration itself is bounded — the schema tightening is what makes the refusal reachable
  rather than satisfiable-by-absurd-declaration). GREEN after the train. Control: the
  reference-capture example (1024/8192) must stay admitted — the mutation arm's matched
  in-bounds twin.
- **Tier when built:** Tier 3 (standards/ + JSON Schema + registry-adjacent; standards-governor
  mandatory) — stated here so the future record inherits it.

## 11. Invariant and drift impacts

- **No invariant changes, no amendments.** CTL-7's scope is untouched (this record moves no
  code). The containment fact this record relies on — the quota formula — is already pinned by
  `tests/unit/test_capture_store.py`; it does not need a new invariant row to stay true, and a
  DEFER must not mint invariants for deferred machinery.
- **Drift obligations:** none bind this commit (docs-only record under `.claude/deep-review/`).
  For the record's *content*: obligation 6 (vendored contract bytes move with any standards
  change) and 7 (SDK pointer) are the load-bearing rows for the D-191-1 train, named in §10.
- **Surfaces:** none move now. The D-191-1 train's surface set is named in §6.2/§10 (corpus,
  SDK vendored copy, manifests, cross-constraints, validator prefixes, census, repins).
- **CI cost:** none beyond the standing battery; this branch adds one markdown file.

## 12. Review tier and the Step-1 keyword scan (rubric #254)

This slice's diff = this new file (docs-only). Path rules put a docs-only diff at Tier 1, **but
the Step-1 keyword rule is text-based and first-match-wins**: the record's diff text carries
protective-behaviour prose, so the scan decides.

Scan domain and method, disclosed: a text report cannot contain its own keyword counts without
perturbing them, so the scan domain is **this record's text excluding this §12**; the whole-diff
scanning the rubric asks for is obtained by adding this section, in which every one of the eight
keywords appears at least once by construction (they are named below). Counts over the scan
domain, mechanically at commit time:

- `threading` 0 · `asyncio` 0 · `subprocess` 0 · `sha256` 1 · `hashlib` 0 · `migrate` 0 ·
  `recovery` 0 · `protection` 1
- Where they live: `sha256` — §3, naming the capture manifest's host-computed digest field;
  `protection` — §3, "availability, not protection". No other keyword occurs in §1–§11, §13–§14.

**Tier: 3** (trigger: the keyword rule — `sha256` and `protection` appear substantively in the
diff text, and the whole-diff count is ≥1 for all eight by the report's own construction; the
deep lane is bought by what the text carries, and the standards-adjacent subject matter agrees).
Consequence: this record's review takes the Tier-3 lane — G6 adversarial second pass — and,
since no `standards/` bytes move, the standards-governor mandate does **not** fire for this
commit (it fires for the §10 train).

## 13. Pre-committed acceptance rule for this record (written before any count was final)

The deferral is the deliverable, so the acceptance rule governs the record's own verifiability
— the properties a later GO/CLOSE pass or governance review can check mechanically:

- **A1 — citation resolvability.** Every `file:symbol` anchor in §2–§3 resolves on `c183db4`
  (denominator: all anchors in those sections). **Ship:** 100% resolve. **Kill:** any anchor
  that does not resolve to the named symbol/line ±5 means the containment map is factually
  broken — fix before merge, and re-walk the path (a wrong map invalidates the DEFER rationale).
- **A2 — deferral-table contract conformance (#99).** Each of D-191-1/2/3 carries identifier,
  deferred thing, home, and an observable reopen trigger naming its inspection (denominator: 3
  rows). **Ship:** 3/3 conform. **Kill:** any row whose trigger names no inspectable surface
  ("when it matters", "if needed") is a contract violation — rewrite the trigger, not the
  verdict.
- **A3 — census regenerability.** The §4 census (23 sites / 1 capture-bearing / 0 plugin
  declarations) regenerates from a fresh checkout by the inspection named in D-191-1's trigger.
  **Ship:** numbers match exactly. **Kill/underpowered:** if the census script and the record
  disagree, the record is wrong and the denominator claim collapses — but note the DEFER
  *strengthens* as the capture-bearing count falls and *weakens* only when a count ≥ 1 plugin
  declaration appears, which is itself D-191-1's trigger firing. A disagreement that shows more
  capture-bearing plugins means the deferral trigger has fired, not that the measurement was
  underpowered — route to the §10 train.
- Sample size and effect size: not applicable in the statistical sense — each metric is a
  exhaustive check over a named finite set (all anchors, all rows, all 23 sites), so there is no
  underpowered middle outcome for A1/A2; A3's middle outcome is defined above.

## 14. Top risks, each with its falsifier

1. **The containment map missed an allocation sized by the declaration.** If any code path
   allocates or pre-extends by the *declared* `max_bytes`/`max_samples` (rather than the
   request), the DEFER's core argument collapses and D-191-1 becomes a live-defect train.
   Falsifier: walk `open_payload`/`append`/`finalise` and the dataset-services lane for any use
   of the descriptor's `capture_limits` values as sizes — the walked path used only the request
   and the reservation; the payload/dataset lane (`dataset_services.py`) has its own budget and
   deliberately no `max_capture_bytes` clamp, but was surveyed, not line-audited, here. Re-audit
   at trigger time (§10's train inherits this as a first task).
2. **A legitimate capture device appears whose real captures exceed the 16 MiB HINT default and
   the operator has not commissioned `max_capture_bytes`.** Symptom: healthy captures refused at
   the gate. This is the A02 commissioning posture working as designed (defaults are hints), and
   the operator guide already carries the knob (`docs/operator-guide.md` names
   `max_capture_bytes`); the risk is operational silence, not incorrectness. Falsifier: a run
   event trail showing `allowance … exceeded` on captures the device's own envelope admits —
   that observation also fires D-191-2's trigger.
3. **The deferral rots — trigger never fires, analysis forgotten.** Mitigations: #191 stays open
   as carrier; the triggers name third-party-inspectable surfaces (census, run event trail);
   GO/CLOSE passes re-cite row ids per the #99 contract. Residual, named honestly: no drift-hook
   reminder covers trigger conditions — the retrospective cadence and the tracker are the
   backstop. Falsifier: a GO/CLOSE pass that cannot answer "has D-191-1 fired?" from the named
   inspections means the trigger was written wrong — fix the row then.
4. **The sharpened D-191-1 trigger is *too* eager** — a trivial/synthetic second example (not a
   real device) would fire it without producing a defensible denominator. Guard: the trigger's
   strong form prefers the plugin-admission arm; a train opened on the examples-arm alone must
   justify its number against #64's "largest in-tree evidence" rule or defer again. The owner's
   call at train time.
