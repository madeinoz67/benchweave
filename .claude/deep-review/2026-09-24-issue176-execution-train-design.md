# Execution train design (issue #176 — rows A, B, D, G of the #167 deferral table)

**Date:** 2026-09-24 · **Issue:** [#176](https://github.com/madeinoz67/benchweave/issues/176)
**Parent records:** `.claude/deep-review/2026-09-23-issue167-run-engine-activation-design.md`
(the deferral table this train drains: rows A, B, D, G) and, one level up,
`.claude/deep-review/2026-09-21-issue43-capture-streaming-design.md` (the capture/streaming
design of record; Decision 3 is the capture mechanism row A finally makes expressible in a
procedure). **Dev-stage compliance:** `.claude/deep-review/2026-09-23-devstage-standards-design.md`
— this record is written under the principal's amended directive of 2026-09-24 (*"use the
dev corpus as we move forward until we need to roll up standards"*): row A develops in a
**`-dev` head**, not a released-version bump.
**Verdict:** BUILD all four rows. **The train authors on a dev head** — row A opens
`standards/execution/0.2.0-dev/` (the first production use of the `-dev` stage) — **with
promotion as a separate, gated increment** (its own PR, timed by the standards coordinator;
it carries the version roll-up AND the four gateway runtime surfaces). Slicing: increment 1
= the authoring head; the promotion increment (gated) = dev → 0.2.0 + the runtime code;
increment 2 = row B, explicitly after promotion (M-B′ needs a real capture step through the
activated composition); increment 3 = rows D+G, verified independent of row A and its
promotion. No released standards byte moves in the authoring increments: row A touches only
the dev head; rows B/D/G touch no standards at all (verified: `event_sink`/`stream_limits`
are already in the active OTDP 0.2.2 descriptor schema; row G is gateway admission policy).
**Grounding checkout:** main at `3df703d`, clean (two untracked scratch files predate this
design and are untouched).

## 0. Grounding — checked against code and corpus, not the issue prose

- **The corpus gate row A removes is real.** `standards/execution/0.1.0/procedure.schema.json`
  closes `$defs/step` at exactly eight oneOf branches (`invoke`, `read`, `write`, `delay`,
  `sample`, `assert`, `if`, `repeat`), every branch `additionalProperties: false`;
  `$defs/value.$stg_issue` closes at `["configuration_id", "acquisition_id"]`;
  `contract_version` is the const `"0.1.0"`. `safety-policy.schema.json` closes
  `allow_rules` at two kinds (invoke/write). The dispatcher types are NOT the blocker:
  `OperationVerb` already carries `capture` (#43 Decision 3; the bridge's `supported` map
  pins the closed argument set `{capture_id, format, sample_count, max_bytes}`), and #167
  (PR #177, merge `1211ab3`) activated bridge construction in `build_run`. What no run can
  do today is *say* "capture" in a procedure — admission would refuse the step as
  schema-invalid against the active corpus.
- **The dev stage is built and unexercised on main.** GOVERNANCE carries the full dev-stage
  doctrine; the manifest loader/validator/repin extensions, the `--corpus` proof lane, the
  `candidate` marker and the `lineage` field all shipped with the devstage record's
  increment 1 (its §13.7–13.10 post-build rulings confirm). `standards/standards-manifest.json`
  at HEAD carries **no `dev` block on any entry** — row A opens the first production head.
  The stage's own acceptance vehicle was the #147 fold replayed on a scratch branch; this
  train is the first head ever carried by a real PR.
- **The gateway runtime cannot see dev bytes — by construction, and that shapes the
  slicing.** The gateway's corpus sites are frozen literals, not manifest-derived
  resolutions: `control/documents.py:48` and `control/coordinator.py:81` hardcode
  `contract_family("execution/0.1.0")` (interface and registry follow the same pattern —
  `interfaces/mcp.py:52`, `interfaces/validation.py:37`, `registry/schemas.py:22`), and
  nothing at runtime derives a `-dev` path (devstage §4.2 invisibility table, row
  "Gateway runtime"; that record's F1 verification states it plainly — "nothing at
  runtime can address it" — and that is exactly why the runtime surfaces gate on
  promotion). An earlier draft of this record claimed `vendoring.contract_family`
  resolves only manifest-derived `<id>/<active-version>` paths — false per the refute's
  lane-2 evidence: the resolver takes any caller-supplied name; it is the call sites
  that pin the active version. The conclusion stands on the corrected premise — the
  frozen literals cannot address `-dev`. The exported bundle, SDK lock, vendored tree,
  identity block, compatibility matrix, train window and report pins are all equally blind
  to the head. Therefore: while the head is open, the running gateway validates procedures
  against execution **0.1.0** and cannot admit a capture-bearing procedure — the four
  main-side surfaces that execute capture steps (projection, semantics, policy, executor)
  would be production-unreachable code until promotion. The design consequence is taken
  deliberately, not as a concession: **the head carries the bytes now; the gateway code is
  the roll-up's in-arc motion** (§1b stays in this record as the designed, ready shape).
- **The executor is a closed kind-switch awaiting one branch.** `Executor._execute_step`
  (`src/benchweave/control/executor.py:700–762`) dispatches leaf kinds to `_step_invoke`/
  `_step_read`/`_step_write`/… and terminates `execution_error` on an unknown kind; the
  occurrence ledger, event append, issued-id retention/invalidation
  (`kind in ("invoke", "read", "write")` gate at the ledger write) and replay all wrap
  around that switch. `_operation_id` (`executor.py:589–592`) mints
  `op:{run_id}:{step_id}{.index-suffix}` — the minting precedent #167 Decision 6 names for
  `cap:` ids. The module docstring pins the issued-id seam: ids mint once per occurrence
  and are retained in the occurrence-ledger entry under `issued_ids`.
- **Policy is a two-kind matcher awaiting a third.** `check_allowed`
  (`src/benchweave/control/policy.py:60–134`) matches on `device_id` + `kind` + target
  (`action_id` for invoke, `parameter` for write), then validates every matching rule's
  constraints JSON-Schema-conjunctively (`input_constraints`/`value_constraints`, with the
  `vacuous_constraint:` warning and the invoke payload-must-be-an-object guard). Rejections
  carry `no_matching_rule:` / `input_constraint:` / `value_constraint:` (CTL-4).
- **Semantics and budgets are kind-walkers.** `worst_case_body_ms`
  (`src/benchweave/control/semantics.py:44–49`) sums invoke/read/write timeouts and delays
  through `if`/`repeat`; `_check_step` (`semantics.py:175–206`) enforces reference placement
  per kind. Binding's `_check_declared_usage` (`src/benchweave/control/binding.py:154`)
  checks declared actions/parameters against the descriptor projection.
- **Row B's seam.** `busy_timeout=5000` is set exactly once, in `Store.open`
  (`src/benchweave/state/store.py:93`) — there is no mid-run pragma surface today
  (`capture_store.py` has zero `busy_timeout` references). The dispatch deadline discipline
  (step `timeout_ms` clamped to the body deadline — never extended) and the six-point
  closure of the clamp review are #167 Decision 7; the measuring condition for this train:
  the #167 M-B run measured the **held-from-start gate arm only** (median 5.199 s over 5
  trials; the G3 `open_capture` check-and-reserve at `otdp_bridge.py:493` →
  `capture_store.py:150` waiting 1× `busy_timeout`, classified `RESOURCE_LIMIT`/
  `NOT_DISPATCHED` at the F6 arm `otdp_bridge.py:516`). The anchor's **mid-capture 2×-busy
  shape** — a second writer acquiring *after* the gate, so the append's BEGIN and the abort
  epilogue's BEGIN each wait out `busy_timeout` (slice-1 anchor: 10.73 s at the 5 s default,
  `DISPATCHED`) — is unmeasured through the activated composition.
- **Row D's gate is open without a bump.** `event_sink` is in the active OTDP 0.2.2
  descriptor schema's permission vocabulary and `stream_limits` is a schema-admitted,
  conditionally-required descriptor key (`standards/otdp/0.2.2/otdp-specification.md` §7
  line 154: "Streaming descriptors require `stream_limits.min_interval_ms/max_subscriptions`").
  The demo fixture descriptor (`fixtures/execution/descriptor-sim-psu.json`) declares
  `permissions: ["scoped_transport"]` only, no `stream_limits`, no capture keys. Tests
  currently *mutate* fixture descriptors to add these keys
  (`tests/integration/test_run_activation.py::_mutated_descriptor`:300–312 adds
  `artifact_writer` + `event_sink` + `stream_limits`) — the demo lattice itself cannot
  stream. The plugin's `next_event` is the missing piece on the fixture side.
- **Row G's root cause, to the line.** `load_otdp_plugin`
  (`src/benchweave/registry/otdp_loading.py:190–193`) verifies the caller-supplied
  `manifest_sha256` against a **canonical re-serialization** of the supplied manifest dict
  (`sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n")`) and keys
  the payload cache at `cache_root / manifest_sha256`. The closure side pins and verifies
  the **served raw bytes**: the resolver pins `manifest_sha256=manifest_doc.sha256`
  (`src/benchweave/registry/resolver.py:318`) and the run-time closure re-verifies
  `served_digest != row.get("manifest_sha256")` (`src/benchweave/interfaces/device_closures.py:198`).
  A manifest whose published bytes are any non-canonical serialization (pretty-printed,
  different key order) therefore resolves cleanly — every raw-pin site agrees with itself —
  and then refuses at the loader with `manifest_hash_mismatch`, because the loader demands
  raw digest == canonical-form digest. The pin lattice (status.json release rows,
  `package-lock` dependencies, `catalogue.json`, the cache directory name, and the loader's
  check) is keyed by ONE digest; it is only coherent when admissible manifest bytes ARE the
  canonical serialization. In-tree fixtures already emit canonical bytes
  (`scripts/registry/build_fixtures.py::_emit_release`:103 pins `_sha(mraw)`), which is why
  the residual has never fired in-tree.
- **No 2026-09-24 design record contradicts this train** (this is the first); the standing
  rulings that bind it: single human reviewer for corpus bytes with the coordinator
  self-review carve-out (2026-09-23, re-review 2027-03-23); governor lane mandatory for any
  `standards/` touch; deferral rows live in design-record tables, not tracker rows
  (amended rule 3); at most ONE follow-on issue per merged PR.

## Decision 1 (row A) — the capture step shape develops in the dev corpus

### 1a. The dev head: OPEN `standards/execution/0.2.0-dev/` (the train's only standards motion)

Per the devstage record's documented open flow (§4.1 "Dev-open") and GOVERNANCE's dev-stage
section, in one PR (the head's OPEN lifecycle event — the governor lane reviews it; there
is no separate pre-approval):

1. **Copy** `standards/execution/0.1.0/` → `standards/execution/0.2.0-dev/` — the one
   ADD-wholesale; every later edit is a MODIFY on a tracked path (the review artifact the
   stage exists to preserve).
2. **Edit substance in the copy** (and only substance — see the no-sweep note below):
   - **`procedure.schema.json`** — one new oneOf branch in `$defs/step`, closed exactly as
     #167 Decision 6 designed and #43 Decision 3 grounds:

     ```json
     { "id": …, "kind": {"const": "capture"}, "role": …, "format": {"enum": ["waveform_f64le", "raw_binary"]},
       "sample_count": {"type": "integer", "minimum": 1}, "max_bytes": {"type": "integer", "minimum": 1},
       "timeout_ms": {"type": "integer", "minimum": 1} }
     ```

     required all seven keys (id, kind, role, format, sample_count, max_bytes,
     timeout_ms), `additionalProperties: false` — the closed §7 argument set minus
     `capture_id` (host-minted), plus `role` (the procedure-side binding every device step
     carries) and `timeout_ms` (**is** the capture budget — Amendment 3 of the #43 record;
     no new procedure-budget mechanism). `format` closes at the OTDP core-lane enum;
     widening it is a future OTDP-coupled revision, not this train. **`$defs/value` is
     untouched** — the `$stg_issue` enum stays `["configuration_id", "acquisition_id"]`
     (see 1c).
   - **`safety-policy.schema.json`** — one new `allow_rules` oneOf branch:
     `{device_id, kind: {"const": "capture"}, format, capture_constraints: {"type": "object"}}`,
     required all four, `additionalProperties: false`. CTL-4's vocabulary extends because a
     capture arms an acquisition — state-changing ordinary control under §7's
     deny-by-default rule; without this branch no policy could ever admit one.
   - **`execution-contract.md`** — the prose companions: §1's language list gains the
     capture step (it is the "later reviewed language extension" §1 itself sanctions);
     §3's kind table gains the `capture` row (contract: dispatch a single-channel core
     capture on a bound role with a capture-scaled timeout; the manifest lands in scope as
     the step's result); §3's reference rules state that `$stg_ref` into a capture step's
     result addresses the captureManifest; §5's worst-case-bound sentence counts capture
     timeouts like invoke timeouts; §7's allow-rule paragraph extends "exact
     action/parameter" to "exact action/parameter/format" with `capture_constraints`
     intersecting the descriptor's declared capture envelope. The stale companion line
     ("OTDP 0.1.0") is corrected to the active version while the file is open — prose
     truthfulness (the .md is a prose companion, not a corpus row).
   - **`examples/procedure.json` + `examples/safety-policy.json`** — gain the capture
     shapes (a capture step; a matching capture allow rule) so the dev corpus is
     self-demonstrating and the `--corpus` lane proves the admission end to end. The
     **fixture demo procedure is deliberately NOT extended** —
     `fixtures/execution/procedure-voltage-check.json` must keep running on the demo bench,
     whose devices declare no capture support; and until roll-up the active corpus would
     refuse the step anyway.
3. **Author the dev corpus rows** citing the corresponding `standards/execution/0.1.0/...`
   paths as `source` (coverage fails closed on any unpinned `standards/**/*.json`; the
   examples are normative-listed and carry rows; the .md needs none).
4. **Add the `dev` block** to the execution entry: `version: "0.2.0-dev"` (target strictly
   greater than the active 0.1.0 — the loader enforces), the dev `normative` path list, and
   the `opened` date (the machine-readable head age the governor reads on every
   `standards/` touch). The optional `candidate` marker stays unset while authoring
   continues; setting it is the coordinator's believed-ready declaration when the roll-up
   decision is taken.
5. **`repin`** (dev rows are repin-mutable; validate treats dev pins exactly like active
   pins — a later dev edit without repin fails `normative_hash_mismatch` naming the dev
   path).

**No version sweep in the dev copy** — a deliberate reading of the stage's own flow: the
devstage record lists the sweep under *promotion* (§4.4 step 2), and the annotation guard
does not judge dev bytes ("stale version strings inside the dev copy are not judged until
promotion makes them active, at which point a forgotten sweep **fires**"). The dev copy
keeps its 0.1.0-era `contract_version` consts and `$id`s — internally consistent, validated
green by the `--corpus` lane — and the sweep moves them in the promoted copy. This keeps
the head's diffs substance-only (named micro-fork below if the owner prefers pre-swept
bytes).

**Proof lane:** `uv run python scripts/architecture/check_execution.py --corpus
standards/execution/0.2.0-dev` — the sanctioned pre-promotion census (read-only for SDK
state; never combined with `--write-report`; cross-standard reads stay manifest-active —
harmless here, the capture verbs live in active OTDP 0.2.2 already). No validation report
is written for dev bytes; reports are a released-version property.

**What the head costs and buys (the dev-stage trade, applied):** no consumer gate sees the
bytes (SDK stillness, identity, matrix, window, reports all green by construction — the
invisibility arms below prove it); the review artifact is MODIFY diffs after the one copy;
and the capture shape is authored, validated and reviewable now, while the release ledger
waits for the roll-up trigger.

### 1b. The gateway code motion — designed here, lands at ROLL-UP (promotion-coupled by construction)

The gateway runtime resolves only manifest-active corpus paths (§0), so these surfaces are
production-unreachable while the head is open; landing them now would be dead code behind
an unreachable path, and testing them would require inventing a test seam that promotion
makes unnecessary (declined — sprawl). They are designed to the line here so the roll-up
increment walks this section verbatim:

- **Projection (CON-10 amendment):** `_project_descriptor`'s total execution view gains the
  capture surface — `capture_formats`, `capture_limits`, and the `artifact_writer`
  permission flag (the grant seam `build_capture_services` already re-derives the RAW
  descriptor by digest; the projection extension is what *admission* reads). Raw document
  stays the pin authority; nothing about the descriptor dialect changes.
- **Semantics (CTL-7 extension):** `_check_step` gains the capture kind — step-ID uniqueness
  and lexical scoping are kind-generic and already cover it; the new checks are the
  admission-time descriptor mirror ("validated twice… during admission wherever values are
  known"): role's device declares `artifact_writer` + `capture_formats`/`capture_limits`
  (refusal prefix `capture_undeclared:`), `format` ∈ declared formats, `sample_count` ≤
  `max_samples`, `max_bytes` ≤ `max_bytes`. `worst_case_body_ms` counts `timeout_ms` like an
  invoke timeout.
- **Policy (CTL-4 amendment):** `check_allowed` gains the capture kind — target is the
  `format` (preserving the exact-capability match: every rule names the exact thing
  allowed; a device-wide capture rule was considered and declined — it would widen by
  later descriptor edit), payload is the capture request `{format, sample_count,
  max_bytes}` (invoke's payload-must-be-an-object guard applies), constraints key
  `capture_constraints` with the conjunctive evaluate + `vacuous_constraint:` warning
  parity, refusal prefixes unchanged plus `capture_constraint:` for the failing-constraint
  case.
- **Executor:** `_execute_step` gains `elif kind == "capture": result = self._step_capture(...)`
  — mint `cap:{run_id}:{step_id}{occurrence-suffix}` mirroring `_operation_id` exactly;
  `check_allowed` BEFORE dispatch (CTL-4: every state-changing dispatch); dispatch the
  closed `{capture_id, format, sample_count, max_bytes}` through the wrapped plugin under
  `min(now + timeout_ms, body_deadline)`; the step's result is the returned captureManifest;
  the minted id is retained in the ledger entry's `issued_ids` and **invalidated when the
  step's operation does not succeed** (joining the `("invoke", "read", "write")` gate).
  Replay/occurrence semantics are the ledger's, unchanged. **`_resolve_ref` gains the
  capture arm (refute lane-2, verified):** the resolver (`executor.py:340–373`) is
  verb-keyed and terminal-raises `pointer: results of verb 'capture' are not referable`
  (`executor.py:372`) — while contract §3 (this head) promises `$stg_ref` into a capture
  step's result resolving `/capture_id`, `/artifact_id` and `/sha256` (all required
  captureManifest members in OTDP 0.2.2). The roll-up adds the resolver arm; A-R4's
  $stg_ref-resolution arm is the pre-committed control that pins it.

**The promotion increment (gated — its own PR, timed by the standards coordinator's
call, fork 1 below), in full:** copy
`standards/execution/0.2.0-dev/` → `standards/execution/0.2.0/` (the class rule governs the
promoted version — MINOR recommended on record below); version sweep in the promoted copy
(`contract_version` consts, examples' fields, `$id`s per the fork ruling, titles); author
promoted rows citing the **dev path** as `source` AND the pre-dev active 0.1.0 paths as
**`lineage`** (the §13.10 required field; repin refuses a `lineage` naming a `-dev` path —
the dev edge is what `source` carries); delete the dev directory and rows; remove the
`dev` block (a leftover block fails `dev_target_not_greater` at load — the structural
forgetfulness catch); flip the active entry; bump the execution-corpus literals
(`control/documents.py:48`, `control/coordinator.py:81`) in the same arc — the sweep
sites the refute's lane-2 census named (interface's `interfaces/mcp.py:52` +
`interfaces/validation.py:37` and registry's `registry/schemas.py:22` follow the same
pattern at their own promotions); `repin`; regenerate the 0.2.0 validation
report via `check_execution.py --write-report`; `docs/README.md` row; identity block's
execution row (CON-8; no repin); export; SDK sync (SDK commit/push FIRST, main-repo pointer
second); matrix regen; **and the four code surfaces above land in the same arc with
their controls (A-R3–A-R5 below), RED-first** — the code motion is part of the bump, not a
follow-up.

### 1c. What row A deliberately does NOT do (each named, each deferred)

- **No `$stg_issue` variant.** `$stg_issue` MINTS fresh ids at marked input fields; the
  capture id is minted by the capture step itself and reaches later steps as part of its
  landed result via `$stg_ref` (e.g. `/capture_id`) — the reference machinery that exists.
  If the #146 dataset/invoke train wants a fetch action's marked input to receive a capture
  id, THAT train adds the enum variant (one branch, one semantics review). Home: this
  record's deferral table.
- **No stream-subscribe step kind.** Subscriptions are run-owned from commissioned bench
  declarations (#167 Decision 3) — procedure-authored subscribes were already ruled
  same-train-if-ever-wanted and nothing since demands them.
- **No dataset-lane sampling of captures** (#43 row 2 / #146).
- **No capture-capable demo fixture** — see the row-D fork below; row A's execution proof
  rides harness descriptors at roll-up (the `_mutated_descriptor` precedent), which is
  exactly how #167 proved activation on surfaces the fixtures don't carry.
- **No gateway code before promotion** (§1b's argument — reachability, not reluctance).

## Decision 2 (row B) — the deadline-aware busy-timeout clamp + the mid-capture measurement

The six-point review closed in #167 Decision 7; this train builds it. The clamp is
capture-DISPATCH machinery (bridge/store) and its test controls (B-R1–B-R3) are
promotion-independent — but the increment lands **after the promotion increment** by an
explicit dependency: M-B′, its head measurement, must drive a real capture **step** through
the activated composition, and admission refuses capture steps on the active 0.1.0 schema
(nothing at runtime addresses a dev head). Mechanism:

- **New pragma surface:** `Store` gains a guarded busy-timeout window —
  `busy_timeout_window(ms)` (context manager: `PRAGMA busy_timeout=<ms>` on entry, restore
  the `Store.open` default on exit, `try/finally` — the leak-discipline point). The store
  still reads no clock (STO-1 unamended): the remaining-deadline arithmetic happens
  bridge-side on the injected monotonic clock; the store only sets what it is handed.
- **The seam:** the `CaptureController` (the run-owned host object the bridge already
  receives as `capture=`) forwards the window to the `CaptureStagingStore` it owns, which
  wraps the worker's `Store`. The bridge brackets every **capture dispatch** (gate region →
  adapter execute → appends/finalise) with `capture.dispatch_clamp(deadline_ns)` computing
  `clamp_ms = min(default_busy_timeout_ms, remaining_deadline_ms)` at entry. One worker
  thread + the per-bridge `RLock` means no interleaved user of that connection exists
  mid-dispatch (re-entrancy point).
- **Epilogue budget:** the abort epilogue (failure/timeout path, where the dispatch
  deadline may be spent) runs under its OWN bounded floor — `min(lifecycle-class constant,
  default_busy_timeout)` — so a clamped-out dispatch still reclaims staging rows instead of
  failing instantly and leaking them; `sweep_open`, `plugin_close`, and the startup
  `reclaim_orphans` stay unclamped (sweep-exemption point; B15-iii retry mold).
- **Classification honesty:** unchanged — a clamped-out BEGIN is the same
  `sqlite3.OperationalError` the writer's stamping discipline routes to the non-poisoning
  `RESOURCE_LIMIT` class (`otdp_bridge.py:359–397`,
  `test_writer_originated_lock_contention_is_resource_limit`).

**The measurement (M-B′, the row's reason to ride this train):** a real capture **step**
— a procedure carrying a `capture` step, admitted against the promoted active schema and
executed through the activated composition (the `build_run`-constructed bridge on a
capture-capable harness descriptor). This is the dependency stated above: before promotion,
admission refuses the step (active 0.1.0 schema) and no procedure-driven capture exists to
measure. The second writer acquires `BEGIN IMMEDIATE` **after** the G3 gate passes
(mid-capture), so the contended writes are the append and the abort epilogue — the anchor's
2×-busy shape. Pre-committed reading in §Acceptance.

## Decision 3 (row D) — fixture-lattice streaming demo (no standards bytes; unchanged by the amended directive)

- `fixtures/execution/descriptor-sim-psu.json`: `integration.adapter.permissions` gains
  `"event_sink"`; the descriptor root gains `stream_limits`
  (`{"min_interval_ms": <declared>, "max_subscriptions": <declared>}` — values are fixture
  authoring choices pinned by the vectors/tests, not commissioned numbers; the demo bench is
  synthetic).
- `plugins/benchweave/sim_psu/` plugin: implements event production — `next_event` over the
  subscribed parameters honoring the declared `min_interval_ms` floor, strictly-increasing
  per-subscription sequences, terminal `ended` semantics (the bridge's event-validation
  contract; a sim that violates it poisons by design and the tests pin the sim honest).
- **Lattice rebuild in lockstep** (obligation 5; the #66 lesson — plugin-source changes
  make the rebuild mandatory): `scripts/registry/build_fixtures.py` regenerates
  `payload.zip`s, `catalogue.json`, status rows and digests; the digest-pinning tests stay
  green. The bench fixture's commissioned signal declarations (`poll_ms`) are unchanged —
  they already drive the #167 subscription set; what changes is that the psu can now honor
  a subscription with real events.
- Docs: `docs/device-developer-guide.md` streaming section already documents the contract;
  the demo-lattice mention moves in the same PR (obligation 3). Operator-visible? No service
  or config change — no operator-guide motion.

This gives the activated streaming composition a REAL admitted demo device: subscriptions
construct a `StreamController` through the unmutated fixture lattice, telemetry lands as
`event_log` evidence under `run:{run_id}` during delay windows — the #167 R14 shape on the
lattice itself instead of a test-mutated descriptor.

**Honest negative (critic wave D6):** the fixture is pull-paced and structurally lossless;
`gap` is unproducible and the host's sequence-jump machinery is undriven — a gap-capable
fixture is deferred (deferral table; trigger: the first real instrument requiring gap
semantics).

## Decision 4 (row G) — manifest canonicality refusal at resolution (F4)

The pin lattice is single-digest end to end (status rows, lock dependencies, catalogue,
cache directory, loader check); the loader's canonical re-hash makes that digest discipline
**canonical-bytes** implicitly. The fix makes it explicit at the boundary where manifest
bytes are first decoded and pinned:

- `Resolver._resolve_release` (where `manifest_doc` and its `sha256` become the pin) gains a
  canonicality check: the served bytes must equal
  `json.dumps(parsed, sort_keys=True, separators=(",", ":")) + "\n"` — byte equality, the
  same formula the loader verifies — else refuse with the machine reason
  `manifest_not_canonical` naming the package (rendered
  `manifest_not_canonical (detail)` at the resolver exception; the admission surface wraps
  reason-only — `registry refused: manifest_not_canonical` — so the package detail stops at
  the wrap, whose detail propagation is a deferral row). Inheritance, stated exactly:
  admission's resolve path refuses (it calls the resolver); bootstrap only *constructs* the
  `Resolver`, resolving nothing; and the run-time closure path
  (`commissioned_device_closure`) reads served bytes WITHOUT the resolver check — so a
  pre-row-G lock over non-canonical bytes still resolves there (its pin matches the served
  bytes) and surfaces the misleading `manifest_hash_mismatch` at `load_otdp_plugin`. That
  upgrade-only residual is named, not laundered: the run-time canonicality gate is a
  deferral row (trigger: the first pre-row-G lock hit in upgrade or support).
- The loader's check is kept verbatim (defense in depth — it still refuses a tampered dict).
- Publisher-side: the in-tree builders already emit canonical bytes; the publishing path
  gains one sentence in the device-developer/publishing guide (emit canonical JSON — the
  one-line `json.dumps(sort_keys=True, separators=(",", ":")) + "\n"`).
- **Considered and declined:** normalizing at admission (re-encoding served bytes and
  re-pinning) — it breaks the cross-document lattice (status/lock rows pin the published
  digest; a re-written admitted copy disagrees with every row naming it), which is
  laundering, not fixing. Also declined: relaxing the loader to skip its re-hash — removing
  a check to fix a mismatch. The refusal is the honest direction: it makes the incompatible
  state unrepresentable instead of tolerated-then-lost.

No corpus byte moves: the registry schemas express structure, not serialization; the
requirement lands as gateway admission policy with a machine-matchable refusal (disclosed
residual: a third-party registry publishing pretty-printed manifests is refused until its
publisher canonicalizes — one line, named in the guide; corpus promotion of the requirement
is a deferral row, not this train).

## Slice order and the first increment

The authoring increment, then the gated promotion increment, then rows B and D+G — one
branch each off `origin/main`, PRs opened as each clears (no stacking needed — only the
promotion increment touches the SDK pointer):

1. **Increment 1 — row A as the dev head (the train's reason and its only standards
   motion).** The OPEN PR: copy, substance edits, examples, dev rows citing 0.1.0 as
   `source`, the `dev` block with `opened`, repin, `--corpus` lane green, invisibility arms
   green. **No SDK motion, no report regen, no gateway code, no identity/matrix/export
   motion — none apply to dev bytes; the PR is green on dev-lane proofs alone.** One
   RED→GREEN slice per commit; gates before each.
2. **The promotion increment — gated on the standards coordinator's timing call (the
   principal holds the role; fork 1 frames the call).** Its own PR, whenever fired: §1b's
   full promotion arc (copy from the dev source, `lineage`, sweep, teardown, repin, report,
   export, SDK sync + pointer, matrix) **and the four runtime surfaces with A-R3–A-R5
   RED-first in the same PR**. Until it fires, the capture shape is authored, validated and
   reviewable in the head while the running gateway is unchanged — admission still refuses
   capture steps, and that refusal is fork 1's operational trigger signal.
3. **Increment 2 — row B (explicitly after promotion).** The pragma window +
   controller/bridge clamp + epilogue floor + the M-B′/M-C′ measurement pass
   (bench-measurer lane). Dependency, stated: M-B′ measures a capture step through the
   activated composition, which requires the promoted active schema (Decision 2).
4. **Increment 3 — rows D + G (verified independent of row A and its promotion).** Row D
   rides active-corpus machinery only — `event_sink`/`stream_limits` are in the ACTIVE
   OTDP 0.2.2 descriptor schema and the #167 streaming activation is merged — so the demo
   lattice streams regardless of the head's state. Row G is registry-resolver admission
   policy, orthogonal to procedure corpora. The two share one PR (registry-adjacent, small)
   and may land in any slot relative to increments 1–2 and the promotion.

## Precedent (proven in-tree mechanisms every shape extends)

- **The dev head itself:** the devstage record's built mechanism (its increment 1 landed on
  main) — the open flow, the repin/validate extensions, the `--corpus` lane, the `lineage`
  field are all shipped machinery this train is the first to use in production. The stage's
  acceptance vehicle (#147 fold replay on a scratch branch) is the precedent for every
  control shape below.
- **The roll-up arc:** #147's OTDP 0.2.2 re-roll and #64's OTDP 0.2.0 train (copy → edit in
  copy → repin → report regen → export → SDK sync → pointer) — with the devstage §4.4
  amendments (dev-path `source`, required `lineage`, teardown).
- **A closed oneOf branch with a policy twin:** the `invoke`/`write` allow-rule pair and
  their `check_allowed` branches; the capture branch is the third of the same shape.
- **Host-minted occurrence ids:** `_operation_id` (`executor.py:589`) and the
  `$stg_issue` mint-retained-invalidated registry in the occurrence ledger — `cap:` ids join
  both molds.
- **Admission-time descriptor mirrors:** `_check_declared_usage` (binding) and the CON-10
  projection's actions+issued surface — the capture surface joins the projection the same
  way; the G2 gate remains the dispatch-time half (validated twice, per §3).
- **The clamp's containment shape:** the writer-originated lock-contention classification
  (`otdp_bridge.py:359–397`) and B15-iii's designated-retry mold for the epilogue — the
  clamp changes only the wait bound, not any classification path.
- **Fixture rebuild lockstep:** #66's PR #72 (plugin doctrine flip + lattice rebuild in one
  motion) — row D is that shape again, streaming edition.
- **Loud typed refusals with machine prefixes:** every admission fence in
  `control/documents.py` and `registry/*` — the `manifest_not_canonical` reason joins the
  family (rendered `manifest_not_canonical (detail)` at the exception, reason-only behind
  the admission wrap).

## Invariant and cross-surface impacts

- **CON-7 (already amended by the devstage record):** dev rows are the third row fate —
  this train is that amendment's first exercise; no further invariant text moves for the
  head itself.
- **At roll-up (pre-committed, not yet):** CTL-4 amendment (third allow-rule kind,
  `capture_constraint:` prefix), CTL-5 amendment (capture occurrences; failed capture
  invalidates its minted id), CTL-7 amendment (`capture_undeclared:` mirrors; manifest
  results in lexical scope), CON-10 amendment (projection capture surface). CTL-6 needs no
  amendment — argued: the capture step carries literals only (no `input` object, no
  reference positions — `additionalProperties: false` makes a `$stg`-bearing capture step
  unrepresentable), so what the policy checks is what dispatches, trivially.
- **Row B:** STO-1 unamended, argued — the clamp's deadline arithmetic is bridge-side on
  injected clocks; the store's new method only sets a handed-down pragma. `state/` and
  `control/` are touched → `tests/faults/` runs per the testing conventions.
- **Row G:** strengthens CON-1's exact-byte posture (pinned manifest bytes are now also
  required to be the canonical ones, disclosed loudly); no REG invariant moves (REG-3's
  admission authority is the enforcement site, extended not weakened).
- **Everything else (CTL-1/2/3/8/9, STO-2/3/4, CON-1…12 minus the named, REG-1…4):
  untouched.**
- **Obligations walked, per increment:** increment 1 — obligation 6 (the edit → repin loop;
  dev rows; NO export/sync motion — the loop's dev-stage note); no obligation 13 (no
  report), no obligation 7 (no pointer), no obligation 8 (no adapter surface). Increment 3
  — obligations 3 (device-developer guide, rows D and G) and 5 (fixture lattice lockstep).
  The roll-up carries obligations 6/7/8/13 in full plus the guide motions for capture
  authoring. CI cost: none new anywhere — all controls are plain pytest on the existing
  `gates` job; the measurement pass is run-lane, not CI.

## Pre-committed acceptance rule (written before any implementation number exists)

Floor semantics inherit the house rule: every control must (a) pass with the mechanism
present and (b) **fail when only the mechanism commit is reverted** — absence-presence,
watched red then green. A control that stays green under (b) does not test the mechanism and
is fixed before merge. No underpowered mode applies to controls; the measurements carry
their own underpowered readings.

**Row A — dev-head increment (now)**

- **A-R1 (the dev corpus admits capture; the active corpus does not):** the dev examples
  (with capture steps) validate against the dev schemas through
  `check_execution.py --corpus standards/execution/0.2.0-dev` — green; the SAME documents
  validated against the frozen active 0.1.0 schemas fail on the capture step (the
  differential run is the control — it must fail there). Negative shapes refuse in the dev
  lane: unknown field on the capture branch, missing `timeout_ms`, `format` outside the
  enum.
- **A-R2 (the diff is exactly the capture family — the shape argument, mechanical):** the
  dev tree against its 0.1.0 source differs by exactly: +1 step branch (`capture`), +1
  allow-rule branch (`capture`), the prose sections, the example additions — step kinds ==
  the 0.1.0 eight + `{capture}`; allow-rule kinds == `{invoke, write, capture}`;
  `$stg_issue` enum == `["configuration_id", "acquisition_id"]` (unchanged); every
  pre-existing schema branch byte-identical to 0.1.0. RED: any other widening fails the
  assertion. *This is the control that proves the corpus admits capture steps without
  widening anything else.*
- **A-R3′ (dev-stage discipline, the stage's own arms applied):** SDK stillness — across
  all head commits, `git diff packages/sdk` is empty and `make check-sdk-standards` exits 0
  (the invisibility tripwire); a dev byte edited without repin makes
  `python -m benchweave.standards check` exit 1 naming the dev path
  (`normative_hash_mismatch`); removing the `dev` block while the directory/rows remain
  fails coverage/load (the devstage record's own forgetfulness arms, replayed on this head).
  RED for each: the corresponding violation must be shown refused.

**Row A — promotion increment (gated; pre-committed now so that PR inherits them)**

- **A-R3 (admission + policy deny-by-default):** through the real admission path — a
  capture step on a capture-declaring device admits; on a non-capturing device refuses
  `capture_undeclared:`; with no capture allow rule the dispatch is denied
  `no_matching_rule:` with zero adapter `execute` calls; a `capture_constraints` violation
  refuses `capture_constraint:`. RED: revert the policy consult → the dispatch proceeds and
  the zero-execute assertion fails.
- **A-R4 (execution + identity + scope):** a run through `build_run` on a capture-capable
  harness descriptor executes a capture step: step event per occurrence; the manifest is the
  step's result; a later step's `$stg_ref` pointer into it resolves; the minted id matches
  `cap:{run_id}:{step_id}{suffix}` and sits in the ledger's `issued_ids`; a failed capture
  invalidates it; replay answers from the ledger without re-dispatch. RED: revert the
  executor branch → unknown-kind `execution_error`.
- **A-R5 (budget):** `worst_case_body_ms` counts capture timeouts; a procedure whose static
  bound overruns `max_body_ms` on capture timeouts alone refuses admission. RED: skip the
  kind in the walk → the refusal assertion fails.
- **SDK conformance surface:** `make check-sdk-standards` green with lock + vendored tree at
  the promoted version (the round-trip is the conformance pin; no SDK code interprets
  procedure schemas today — verified at build; if any SDK-side execution-schema test exists
  it moves in the same SDK PR).

**Row B (lands after the promotion increment; controls are promotion-independent, the
measurement is not)**

- **B-R1 (clamp bounds the mid-capture shape):** second writer acquired after the gate, with
  the clamp: the dispatch's wall-stretch lands in the ≤1× `busy_timeout` + epilogue-floor
  class (NOT the 2× anchor); classification `RESOURCE_LIMIT`, session survives; staging
  reclaimed. RED: revert the clamp → the stretch returns to the anchor class (≥2× minus
  jitter) and the bound assertion fails.
- **B-R2 (leak discipline):** after clamped dispatches on both success and failure paths,
  `PRAGMA busy_timeout` reads the `Store.open` default again (including a dispatch that
  raises between set and restore).
- **B-R3 (sweep exemption):** `sweep_open`/close/`reclaim_orphans` waits are bounded by the
  default, unclamped.
- **M-B′ (pre-committed measurement, the row's headline):** ≥5 trials, mid-capture
  contention, through the activated composition (capture-step-driven, per Decision 2 —
  post-promotion); report
  median and spread of dispatch wall-stretch vs the commissioned step deadline, **with the
  clamp present**; the held-from-start shape (#167 M-B, median 5.199 s) is the matched
  control condition. **Ships if** the clamped median ≤ 1× `busy_timeout` + the measured
  epilogue class with spread ≤ 25%. **Fires arm 3** (Option B evaluation, posted to #159
  per #167's pre-committed reading) **if** the clamped stretch still exceeds the recorded
  2×-busy anchor bound by a margin the clamp design cannot remove, or the monitor gap
  during the stretched dispatch breaches the capture-deadline policy bound with no
  clamp-side remediation. **Underpowered if** the mid-capture window cannot be reproduced
  stably (spread > 25% over ≥5 trials) — record underpowered + arm unfired + "re-measure
  with a stable harness", and decide nothing from it. M-B′ never silently converts to Option-B evidence.
- **M-C′ (rider):** queued-run delay behind the clamped contended capture — expectation: the
  slice-1/#167-M-C class; a larger delay names an unbounded path, not Option-B evidence.

**Row D (unchanged)**

- **D-R1 (the lattice streams):** post-rebuild, the demo bench admits at bootstrap and a run
  on it constructs a `StreamController` for the psu through the unmutated fixture lattice;
  during a delay step telemetry lands as `event_log` evidence under `run:{run_id}`. RED:
  revert the descriptor permission → no stream services construct, zero events.
- **D-R2 (sim honesty):** the plugin's event production honors the declared floor and the
  strictly-increasing/terminal-`ended` contract (a pinned test drives the sim's emission
  logic; the bridge's validators remain the authority the sim must not trip).
- **D-R3 (lockstep):** `build_fixtures.py` regenerates; `test_registry_fixtures` and the
  digest pins stay green — no hand-moved fixture bytes.

**Row G (unchanged)**

- **G-R1 (the residual, made unrepresentable):** a fixture-adjacent manifest re-serialized
  non-canonically (same content, different bytes) refuses at resolution with the reason
  `manifest_not_canonical` — the exception names the package
  (`manifest_not_canonical (…)`); the admission surface shows reason-only
  (`registry refused: manifest_not_canonical`). RED (the control exercising the real
  residual): revert the check → the closure resolves AND `load_otdp_plugin` refuses
  `manifest_hash_mismatch` — assert that today-shape fails red under the mechanism.
- **G-R2 (no collateral):** every in-tree fixture manifest passes the check — no fixture
  bytes move.
- **G-R3 (defense in depth kept):** the loader still refuses a tampered manifest dict whose
  canonical hash disagrees with the supplied digest.

## Governance walk (dev-corpus discipline; what the standards-governor lane reviews)

1. **No bump, no window arithmetic.** No pure-semver version directory is added anywhere in
   the train (`0.2.0-dev` fails the collector's `_VERSION_PATH` regex by design); the train
   window stays green by construction. The bump window, copy-never-move, report regen,
   export/sync and identity/matrix motions all attach to the **roll-up** and are restated
   there (§1b) — at roll-up time the window arithmetic is: last execution version dir
   (0.1.0) added by reset commit `ea70c6a` 2026-09-16T09:47:21+08:00, so the 24 h floor is
   long expired whenever the trigger fires (re-verified against HEAD at that time).
2. **Head-shape rules (enforced at load):** one head per entry (execution has none — clean
   OPEN); `version: "0.2.0-dev"` with target strictly greater than active 0.1.0; every dev
   `normative` path under `standards/execution/0.2.0-dev/`; active entry stays pure semver.
3. **Row discipline:** dev rows cite the 0.1.0 corpus paths as `source`; coverage fails
   closed on unpinned dev JSON; the edit → repin loop on every subsequent edit
   (`normative_hash_mismatch` is the honesty gate); row creation/deletion stays
   hand-authored under governance review.
4. **Proof lane:** `--corpus standards/execution/0.2.0-dev` green; never with
   `--write-report`; cross-standard reads stay manifest-active.
5. **Invisibility (the governor's checklist, from the devstage §4.2 table):** SDK lock and
   pointer byte-still across all head commits (`make check-sdk-standards` green); identity
   block, compatibility matrix, annotation guard, train window and report pins all
   unaffected; the wheel exclusion (shipped with the stage) keeps `-dev/` out of packaged
   contracts — the pre-flight `unzip -l dist/*.whl | grep -- '-dev/'` check returns empty.
6. **Review gate:** governor lane mandatory (any `standards/` touch — this is an OPEN
   lifecycle event, the first real one); corpus bytes + corpus-manifest rows → single human
   reviewer with the coordinator self-review carve-out (2026-09-23 ruling; re-review
   2027-03-23). The head's `opened` date is the machine-readable age the governor reads.
7. **Class and `$id` rulings (pre-committed recommendations, decided at roll-up):** the
   head's target `0.2.0` names intent; the class rule governs the promoted version —
   **MINOR recommended** (new accepted document capability carrying a new executor
   obligation; §1's own "reviewed language extension" language is not errata; in-tree
   precedent: OTDP 0.2.0 shipped MINOR for strictly less). A PATCH reading (purely additive
   machine errata) exists and is the governor's call at promotion — the bytes are identical
   either way. **`$id` convention:** recommend tracking the standard version at promotion
   (`urn:stg:execution:procedure:0.2.0`, otdp-style) so two corpus versions admitting
   different document sets never share a schema identity; registry's decoupled precedent
   (`urn:stg:registry:package-lock:1.0.0` unchanged across 0.1.0→0.1.1) is the
   counter-example the governor weighs.

## Top risks and what falsifies this design

| Risk | Falsifier / disposition |
|---|---|
| **The head rots open** (the stage's own risk 3 — and this is the first real head) | The `opened` date is machine-readable and the governor reads it on every `standards/` touch; the roll-up trigger set below is operational (a refused capture-procedure admission is the firing signal); the coordinator's stale-head ruling path exists if needed. |
| **First production use of the stage hits an unforeseen gate** | The stage's own acceptance (#147 scratch replay) proved the invisibility arms; this train reruns them as A-R3′ on a real head — any gate that turns on the head is exactly the devstage record's kill condition (kill the separate-head shape, do not patch symptoms). |
| **The designed-but-unbuilt gateway code drifts before roll-up** (§1b waits in this record) | The roll-up increment walks §1b verbatim; any divergence between the record and the landing code is review-flagged (the record is the design of record for those surfaces); the #46/#6-lineage pattern of record-first development is the precedent. |
| **MINOR vs PATCH contested at roll-up** | Bytes identical either way; the version label is the governor's call with the class argument recorded in §Governance 7; a PATCH ruling forces a re-copy from the same dev source — mechanical. |
| **The projection extension reads as dialect creep** (CON-10 was hard-won — roll-up risk) | The extension carries only what semantics must read at admission (formats, limits, permission flag) — the same shape as actions+issued; the raw document remains the authority and the grant seam still re-derives it by digest. |
| **The clamp masks legitimate long waits** | The clamp only shortens waits already doomed to exceed the step deadline (six-point point 4); commissioned `timeout_ms` (A02) remains the operator's lever and the clamp honors it via `min(…, remaining)`. |
| **Row D rebuild churn** (many digest moves obscure the real diff) | The builder is the only writer (obligation 5); the reviewer reads the plugin + descriptor diffs and treats the regenerated pins as mechanical; D-R3 pins lockstep. |
| **D-R1 is wall-clock sensitive under CPU load** | 1 of 27 load runs landed `outcome_unknown` honestly (no `signal_invalid`, no subscribe refusal; the §5 mapping minted at coordinator.py:107–108 / documented at executor.py:49) — disposition: accepted flake, disclosed in the test docstring; the N×-under-load CI lane is deferred (deferral table, trigger: a second under-load D-R1 flake). |
| **Row G refuses a real pretty-printed registry** | Disclosed ecosystem constraint with a one-line publisher fix, named in the guide; the alternative (dual digest disciplines) is the F4 bug itself. Corpus promotion is a deferral row. |
| **M-B′ does not reproduce stably** | Pre-committed underpowered reading; arm unfired; no decision from the run. |
| **Row B's landing is coupled to the promotion's timing** (coordinator-gated, no committed date) | Deliberate per the reshaping — fork 1 makes the timing an explicit owner call; the clamp's design and controls are complete in this record and land with the increment whenever promotion fires; if promotion is deferred indefinitely, row B and the deferral row 1 share the trigger (they fire together). |
| **Train sprawl** (four rows, three PRs, one issue, one deferred roll-up) | The brief's rows are the scope; every newly-spawned want lands in the deferral table below, not the PRs. |

## Deferrals — every row names its home and reopen trigger

| # | Deferred | Home | Reopen trigger |
|---|---|---|---|
| 1 | **The promotion increment (gated): dev promotion (execution 0.2.0) + §1b's four gateway surfaces + A-R3–A-R5 controls + the full bump-arc obligations** | This record §1b + the head itself (`0.2.0-dev`, `candidate` set when decided) | **"Need to roll up" = the first consumer requiring digest-pinned released bytes, operationally:** (a) the first attempt to admit a capture-bearing procedure through the gateway (the active corpus refuses it — that refusal is the trigger firing), i.e. the first real capture-class plugin commissioning; (b) an SDK vendor-sync or release train requiring the execution standard to move; (c) the principal's explicit call. Whichever first. At roll-up: copy-never-move from the dev source, `lineage` to 0.1.0, sweep, teardown, repin, report, export, sync, pointer, matrix — and the 24 h window re-verified against HEAD. |
| 2 | `$stg_issue` gains `capture_id` (fetch-lane input field) | This record §1c | The #146 dataset/invoke train's fetch-action design |
| 3 | Capture-capable demo fixture (sim-psu `artifact_writer` + capture verb + demo-procedure capture step) | This record §1c | First operator-facing demo procedure needing capture, or the #146 train — whichever first |
| 4 | `stream_subscribe` procedure step kind | This record §1c | A procedure author needing procedure-authored subscriptions (none demands it) |
| 5 | Corpus promotion of the manifest-canonicality requirement (registry prose/schema-adjacent surface) | This record §Decision 4 | A second publisher surface needing the requirement stated normatively |
| 6 | Aggregate teardown-window deadline (#167 F2 disclosure — unchanged, restated for the train) | #167 record | A commissioned envelope demanding it |
| 7 | Capture format-enum widening beyond the core lane | This record §1a | An OTDP capture-formats revision train |
| 8 | Run-time canonicality gate in `commissioned_device_closure` — close the upgrade-only residual (a pre-row-G lock over non-canonical bytes still resolves and surfaces the misleading `manifest_hash_mismatch` at `load_otdp_plugin`) | This record §Decision 4 | The first pre-row-G lock hit in upgrade or support |
| 9 | Shared canonical-formula helper extraction behind the resolver's inline check and the loader's re-hash (the gF2 agreement pin guards divergence meanwhile) | This record §Decision 4 + `tests/contract/test_registry_resolver.py::test_canonical_form_agreement_pin` | The next intentional edit at resolver.py:276 or otdp_loading.py:192 |
| 10 | G-R2 collateral-guard set derived from `catalogue.json` (today: a hardcoded glob and count of 6) | `tests/contract/test_registry_resolver.py::test_every_in_tree_fixture_manifest_is_canonical` | The first non-benchweave fixture path |
| 11 | Admission-wrap detail propagation (`registry refused: {reason}` drops the `manifest_not_canonical (detail)` package name) | This record §Decision 4 + `docs/device-developer-guide.md` §10 | The next admission-error-surface change |
| 12 | CI N×-under-load D-R1 lane (repeat the demo-lattice control under CPU load) | This record §Top risks + `tests/integration/test_demo_lattice_streaming.py` (D-R1 docstring) | The second under-load D-R1 flake |
| 13 | Bundle-loader `importlib.import_module` bypass (already ledgered as a gotcha) | Memory vault gotcha ledger (restated here per amended rule 3) | The first untrusted bundle admission |
| 14 | critic-D1: `stream_completed` → `stream_budget_exhausted` rename + pin + census | This record (critic wave D) | The next adapter/fixture-authoring touch, or row B's fixture work |
| 15 | critic-D2: durable terminal marker on clean `mark_closed` | This record (critic wave D) | The next `stream_services` touch (the mid-budget run-end test rides it) |
| 16 | critic-D3: durable record for subscribe-refusal | This record (critic wave D) | The next `stream_services` touch |
| 17 | critic-D4: adapter refuses duplicate `subscription_id` | This record (critic wave D) | The next adapter touch |
| 18 | Gap-capable streaming fixture (the committed fixture is pull-paced and structurally lossless; `gap` unproducible — disclosure folded into §Decision 3) | This record §Decision 3 (critic wave D) | The first real instrument requiring gap semantics |

(#167's rows C, E, F stay closed in that record's table — none is this train's scope.)

## Forks for the maintainer

1. **Promotion timing (the directive's own call — "until we need to roll up")** — author
   now and promote when the train's runtime value is wanted (recommended as written: the
   first refused capture-procedure admission is the crisp operational signal that the value
   is wanted), vs promote immediately after authoring (burns the window/batch now, ships
   runtime capture sooner). The principal holds the coordinator role; either posture is a
   deliberate call, not a default.
2. **Row A change class at roll-up** — MINOR (recommended) vs PATCH; governor rules then,
   with the argument recorded in §Governance 7.
3. **Execution `$id` convention at roll-up** — track the standard version (recommended,
   `urn:stg:execution:procedure:0.2.0`) vs keep the decoupled `1.0.0` segment (registry
   precedent).
4. **Capture-capable demo fixture now vs deferred** — deferred (recommended; row D stays
   streaming-only per its carrier; harness descriptors carry row A's execution proof at
   roll-up) vs extending the same rebuild (one lattice rebuild either way, but a doubled
   sim surface).
5. **Capture allow-rule target** — `format` exact-match (recommended) vs device-wide capture
   rules (declined above; widening-by-descriptor-edit).
6. **Pre-sweep the dev copy's version consts vs leave them to the promotion sweep** —
   leave-to-sweep (recommended; substance-only diffs, the stage's own flow lists the sweep
   under promotion) vs pre-swept dev bytes so the head reads as its target (costs mechanical
   churn in every dev diff and duplicates the promotion step).
