# Execution train design (issue #176 — rows A, B, D, G of the #167 deferral table)

**Date:** 2026-09-24 · **Issue:** [#176](https://github.com/madeinoz67/benchweave/issues/176)
**Parent records:** `.claude/deep-review/2026-09-23-issue167-run-engine-activation-design.md`
(the deferral table this train drains: rows A, B, D, G) and, one level up,
`.claude/deep-review/2026-09-21-issue43-capture-streaming-design.md` (the capture/streaming
design of record; Decision 3 is the capture mechanism row A finally makes expressible in a
procedure). **Dev-stage compliance:** `.claude/deep-review/2026-09-23-devstage-standards-design.md`
— amended twice by directive (2026-09-24): first *"use the dev corpus as we move forward
until we need to roll up standards"*, then the model change that resolves fork 1:
*"to continue development we can use the dev corpus, until all is finished, then it will be
promoted."* **The train develops entirely against the dev head; promotion is one pure
release event at train end.** This revision (Amendment 3) also preserves the refute
slate's folds merged at `8aca4d1`/`111d27d` (the literal-site premise correction, the
seven-keys fix, the `_resolve_ref` capture arm, the promotion sweep census).
**Verdict (Amendment 3, promote-at-end):** BUILD all four rows. Increment 1 (the authoring
head) is **MERGED** — PR [#185](https://github.com/madeinoz67/benchweave/pull/185), merge
`8d2f659`: `64e7cb5` (this record) → `4bfbf88` (OPEN `0.2.0-dev`) → `0608490` (author the
capture family) → `8aca4d1`/`111d27d` (refute folds). Next: the gateway runtime surfaces
land on main as **corpus-gated code, exercised green through a new dev-corpus resolution
seam** (§1b — the enabling mechanism, overturning this record's earlier
declined-as-sprawl call by directive); row B is **unparked** (M-B′ measures the mid-capture
shape through a real capture step resolved from the head); rows D+G are independent and
already building; **promotion at train end is a pure release event — literal sweep, version
sweep, report regen, export, SDK sync + pointer, head teardown, ZERO new code.** No
released standards byte moves until that event (verified: `event_sink`/`stream_limits` are
already in the active OTDP 0.2.2 descriptor schema; row G is gateway admission policy).
**Grounding checkout:** main at `2847be6` (post-#185); `standards/execution/0.2.0-dev/` on
main per the merged increment.

## 0. Grounding — checked against code and corpus, not the issue prose

- **The corpus gate row A removed was real, and the head now removes it.**
  `standards/execution/0.1.0/procedure.schema.json` closed `$defs/step` at exactly eight
  oneOf branches (`invoke`, `read`, `write`, `delay`, `sample`, `assert`, `if`,
  `repeat`), every branch `additionalProperties: false`; `$stg_issue` closed at
  `["configuration_id", "acquisition_id"]`. The merged `0.2.0-dev` head carries the capture
  family (step branch, allow-rule branch, prose, examples) per §1a as landed by `0608490`.
  The dispatcher types were never the blocker: `OperationVerb` already carries `capture`
  (#43 Decision 3; the bridge's `supported` map pins the closed argument set
  `{capture_id, format, sample_count, max_bytes}`), and #167 (PR #177, `1211ab3`)
  activated bridge construction in `build_run`.
- **The runtime corpus sites are frozen literals — this is what the seam must move.**
  The gateway's corpus sites are frozen literals, not manifest-derived resolutions:
  `control/documents.py:48` and `control/coordinator.py:81` hardcode
  `contract_family("execution/0.1.0")` (interface and registry follow the same pattern —
  `interfaces/mcp.py:52`, `interfaces/validation.py:37`, `registry/schemas.py:22`), and
  nothing at runtime derives a `-dev` path (devstage §4.2 invisibility table, row
  "Gateway runtime"; that record's F1 verification states it plainly — "nothing at
  runtime can address it" — which the default composition keeps true and the seam opts
  out of explicitly). An earlier draft of this record claimed `vendoring.contract_family`
  resolves only manifest-derived `<id>/<active-version>` paths — false per the refute's
  lane-2 evidence: the resolver (`src/benchweave/vendoring.py:29–34`) takes any
  caller-supplied name and is **packaged-first** (`_PACKAGED_ROOT/contracts/<name>`, else
  the dev-checkout fallback `_REPO_ROOT/standards/<name>`); it is the call sites that pin
  the active version. Two consequences the seam relies on: since the resolver takes any
  name, a manifest-derived dev resolver needs no new path logic — it passes the head's
  version to the existing function; and since the head never exports and the devstage
  wheel exclusion keeps it out of `_vendored/contracts`, `contract_family` can resolve
  the head ONLY in a dev checkout — in an installed wheel the packaged miss falls through
  to a non-existent path and fails loudly.
- **The checker lane is the seam's in-tree precedent.** `corpus_directory` /
  `_corpus_override` / `_declared_dev_head` (`scripts/architecture/_validation_report.py:51–146`):
  default resolves the manifest-active directory; `--corpus <dir>` accepts **exactly the
  manifest-declared dev head** for the standard (resolved through the canonical
  `load_manifest`, so every dev-block shape refusal the loader enforces is the lane's
  refusal too — "same words on both surfaces"), refusing `corpus_override_not_dev_head:`
  on any other path, `<id>_dev_head_absent:` when no head is declared, and
  `corpus_override_write_refused:` for the report combination. It is a view, never a
  mutation. The gateway seam is this pattern's runtime twin — with one difference the
  design must own: a long-running gateway has no argv, so the opt-in channel is a
  composition parameter, not a flag.
- **The executor is a closed kind-switch awaiting one branch — and its reference resolver
  is verb-keyed.** `Executor._execute_step`
  (`src/benchweave/control/executor.py:700–762`) dispatches leaf kinds to `_step_invoke`/
  `_step_read`/`_step_write`/… and terminates `execution_error` on an unknown kind; the
  occurrence ledger, event append, issued-id retention/invalidation
  (`kind in ("invoke", "read", "write")` gate at the ledger write) and replay all wrap
  around that switch. `_operation_id` (`executor.py:589–592`) mints
  `op:{run_id}:{step_id}{.index-suffix}` — the minting precedent #167 Decision 6 names for
  `cap:` ids. `_resolve_ref` (`executor.py:340–373`, called from `resolve_value`:284) is
  verb-keyed and terminal-raises `pointer: results of verb 'capture' are not referable`
  (`executor.py:372`) — while contract §3 (this head) promises `$stg_ref` into a capture
  step's result resolving `/capture_id`, `/artifact_id` and `/sha256` (all required
  captureManifest members in OTDP 0.2.2). The runtime increment adds the resolver arm;
  A-R4's `$stg_ref`-resolution assertion is the pre-committed control that pins it.
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
  (`tests/integration/test_run_activation.py::_mutated_descriptor`:300–312) — the demo
  lattice itself cannot stream. The plugin's `next_event` is the missing piece on the
  fixture side.
- **Row G's root cause, to the line.** `load_otdp_plugin`
  (`src/benchweave/registry/otdp_loading.py:190–193`) verifies the caller-supplied
  `manifest_sha256` against a **canonical re-serialization** of the supplied manifest dict
  (`sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n")`) and keys
  the payload cache at `cache_root / manifest_sha256`. The closure side pins and verifies
  the **served raw bytes**: the resolver pins `manifest_sha256=manifest_doc.sha256`
  (`src/benchweave/registry/resolver.py:318`) and the run-time closure re-verifies
  `served_digest != row.get("manifest_sha256")` (`src/benchweave/interfaces/device_closures.py:198`).
  A manifest whose published bytes are any non-canonical serialization therefore resolves
  cleanly — every raw-pin site agrees with itself — and then refuses at the loader with
  `manifest_hash_mismatch`. The pin lattice (status.json release rows, `package-lock`
  dependencies, `catalogue.json`, the cache directory name, and the loader's check) is keyed
  by ONE digest; it is only coherent when admissible manifest bytes ARE the canonical
  serialization. In-tree fixtures already emit canonical bytes
  (`scripts/registry/build_fixtures.py::_emit_release`:103 pins `_sha(mraw)`), which is why
  the residual has never fired in-tree.
- **Standing rulings that bind the remaining increments:** single human reviewer for corpus
  bytes with the coordinator self-review carve-out (2026-09-23, re-review 2027-03-23);
  governor lane mandatory for any `standards/` touch; deferral rows live in design-record
  tables (amended rule 3); at most ONE follow-on issue per merged PR.

## Decision 1 (row A) — the capture step shape, authored on the dev head

### 1a. The dev head — MERGED (increment 1)

`standards/execution/0.2.0-dev/` is on main (OPEN `4bfbf88`, author `0608490`, refute
folds `8aca4d1`/`111d27d`; PR #185 merge `8d2f659`), carrying per this record's design:

- **`procedure.schema.json`** — the closed capture branch:
  `{id, kind: {"const": "capture"}, role, format ∈ ["waveform_f64le", "raw_binary"],
  sample_count ≥ 1, max_bytes ≥ 1, timeout_ms ≥ 1}` — required all seven keys (id, kind,
  role, format, sample_count, max_bytes, timeout_ms), `additionalProperties: false` — the
  closed §7 argument set minus `capture_id` (host-minted), plus `role` (the procedure-side
  binding every device step carries) and `timeout_ms` (**is** the capture budget —
  Amendment 3 of the #43 record; no new procedure-budget mechanism). `format` closes at
  the OTDP core-lane enum; widening it is a future OTDP-coupled revision, not this train.
  **`$defs/value` untouched** — `$stg_issue` stays closed at two values (see 1c).
- **`safety-policy.schema.json`** — the capture allow-rule branch:
  `{device_id, kind: {"const": "capture"}, format, capture_constraints: {"type": "object"}}`,
  required all four, `additionalProperties: false` (CTL-4's vocabulary for state-changing
  captures).
- **`execution-contract.md`** — §1 language list, §3 kind table + `$stg_ref`-into-manifest
  reference rules (resolving `/capture_id`, `/artifact_id`, `/sha256`), §5 budget
  arithmetic, §7 allow-rule paragraph; companion-line truthfulness fix.
- **`examples/procedure.json` + `examples/safety-policy.json`** — the capture shapes, so
  the `--corpus` lane proves admission end to end. The fixture demo procedure is
  deliberately NOT extended (it must keep running on the demo bench).
- Dev rows cite the 0.1.0 corpus paths as `source`; the `dev` block carries
  `version: "0.2.0-dev"` + `normative` + `opened`; no version sweep in the copy (the
  devstage flow places the sweep at promotion; the annotation guard does not judge dev
  bytes) — substance-only diffs.

### 1b. The dev-corpus resolution seam + the runtime surfaces (the enabling mechanism)

**The overturned call, and why the overturn is sound.** This record's earlier revision
declined a test-reachability seam as sprawl and deferred all gateway code to a
promotion-that-had-no-date. The principal's promote-at-end model makes that posture
incoherent: the entire train develops against the head, so the runtime must be able to
*compose against head bytes* or nothing after increment 1 is testable end to end. The
overturn is by directive, and the design answers the original objection structurally: the
seam is a **named, manifest-derived, opt-in composition parameter with no path-valued
surface and three layers of non-leakage** — not a backdoor.

**The seam, concretely (extending proven mechanisms only):**

1. **`vendoring.py` gains the manifest-derived dev resolver** — the runtime twin of the
   checker lane's `_declared_dev_head`:
   `declared_dev_family(standard_id: str) -> Path` loads the manifest through the canonical
   `load_manifest`, finds the entry, and returns `contract_family(f"{standard_id}/{entry.dev.version}")`
   (the resolver already takes any name — the refute's corrected premise — so this adds
   no path logic, only the manifest derivation). Refusals, mirroring the lane's words on
   both surfaces: the loader's own dev-block shape refusals are inherited verbatim
   (malformed block, non-`<target>-dev` version, target not strictly greater — the
   review-row-6 pattern); `execution_dev_head_absent:` when no head is declared;
   `dev_head_unresolvable:` naming the missed path when the resolved directory does not
   exist (the packaged-context case — **never a silent fallback to active**). There is no
   path parameter anywhere in the resolver: the manifest's declared head is the only thing
   it can return (the accept-exactly-the-declared-head rule, made typal).
2. **The opt-in channel is a keyword-only composition parameter, not a flag, env var, or
   config key.** The composition root (`create_app`, `src/benchweave/interfaces/app.py` —
   the factory that already receives injected objects like `RegistrySession`) gains
   `execution_corpus: CorpusResolution = CorpusResolution.ACTIVE` (keyword-only; the enum
   lives beside the resolver in `vendoring.py` with exactly two members). `ACTIVE` keeps
   the **frozen literal** at the sites — today's
   `contract_family("execution/0.1.0")` behavior, byte-identical production posture (the
   promotion's literal sweep is what moves it; making ACTIVE manifest-derived is a named
   future hardening, §1c). `DEV_HEAD` resolves `declared_dev_family("execution")` **once
   at composition** and threads the resulting directory through the existing injection
   path (`create_app` → `_build_run_factory` → `build_run` → the coordinator; and the
   bootstrap call — `admit_fixture_lattice` — so startup admission resolves the same
   family in the composed app). The builder walks every consumer of the two `_CONTRACTS`
   constants (`relations`/`usages`) and threads accordingly; the constants remain the
   module defaults. If threading through a consumer proves to need a second composition
   path, the increment splits rather than widens the seam. The interface and registry
   literal sites (`interfaces/mcp.py:52`, `interfaces/validation.py:37`,
   `registry/schemas.py:22`) are NOT seam targets — this train's head is execution-only;
   they are named solely as the promotion-sweep census pattern.
3. **Three layers of structural non-leakage (the governor's review target):**
   - **No accidental channel:** the parameter is keyword-only constructor injection — no
     env var reads, no operator-config schema key, no REST/MCP surface can set it; the
     only construction path is code, and no production caller passes it.
   - **Packaged impossibility:** the head never exports and the devstage wheel exclusion
     keeps it out of `_vendored/contracts`, so an installed (wheel-run) gateway physically
     cannot resolve `DEV_HEAD` — it refuses `dev_head_unresolvable:` rather than degrading.
   - **Self-retirement:** promotion deletes the dev block, so from that moment any stray
     `DEV_HEAD` composition refuses `execution_dev_head_absent:` — the seam cannot outlive
     the head, which is what makes the promotion's ZERO-new-code claim safe.
4. **Seam controls (pre-committed):**
   - **S-R1 (default is today, byte-for-byte):** the default composition resolves the
     active family — the sites' resolved paths equal today's literal-derived paths; no
     production behavior changes. RED: default `DEV_HEAD` → the pin fails.
   - **S-R2 (exactly the declared head, self-retiring):** `DEV_HEAD` resolves
     `standards/execution/<entry.dev.version>` through the canonical loader; with the dev
     block removed (the post-promotion shape), composition refuses
     `execution_dev_head_absent:`. RED: silently falling back to active on a missing head.
   - **S-R3 (packaged impossibility):** with the packaged root pointing at a contracts
     tree lacking the head (the wheel shape), `DEV_HEAD` refuses
     `dev_head_unresolvable:`. RED: any fallback.
   - **S-R4 (no arbitrary path):** the seam's public surface exposes no path-valued
     parameter — the enum is the only opt-in (a shape assertion over the factory
     signature; mypy-visible).

**The four runtime surfaces (landing as the next increment, corpus-gated on main):**

- **Projection (CON-10 amendment):** `_project_descriptor`'s total execution view gains the
  capture surface — `capture_formats`, `capture_limits`, and the `artifact_writer`
  permission flag (the grant seam `build_capture_services` already re-derives the RAW
  descriptor by digest; the projection extension is what *admission* reads). Raw document
  stays the pin authority; nothing about the descriptor dialect changes.
- **Semantics (CTL-7 extension):** `_check_step` gains the capture kind — step-ID uniqueness
  and lexical scoping are kind-generic and already cover it; the new checks are the
  admission-time descriptor mirror: role's device declares `artifact_writer` +
  `capture_formats`/`capture_limits` (refusal prefix `capture_undeclared:`), `format` ∈
  declared formats, `sample_count` ≤ `max_samples`, `max_bytes` ≤ `max_bytes`.
  `worst_case_body_ms` counts `timeout_ms` like an invoke timeout.
- **Policy (CTL-4 amendment):** `check_allowed` gains the capture kind — target is the
  `format` (preserving the exact-capability match; a device-wide capture rule was
  considered and declined — it would widen by later descriptor edit), payload is the
  capture request `{format, sample_count, max_bytes}` (invoke's
  payload-must-be-an-object guard applies), constraints key `capture_constraints` with the
  conjunctive evaluate + `vacuous_constraint:` warning parity, refusal prefixes unchanged
  plus `capture_constraint:`.
- **Executor:** `_execute_step` gains `elif kind == "capture": result = self._step_capture(...)`
  — mint `cap:{run_id}:{step_id}{occurrence-suffix}` mirroring `_operation_id` exactly;
  `check_allowed` BEFORE dispatch (CTL-4); dispatch the closed `{capture_id, format,
  sample_count, max_bytes}` through the wrapped plugin under `min(now + timeout_ms,
  body_deadline)`; the step's result is the returned captureManifest. **`_resolve_ref`
  gains the capture arm (refute lane-2, verified):** the resolver is verb-keyed and
  today terminal-raises `pointer: results of verb 'capture' are not referable`
  (`executor.py:372`); the arm makes the landed manifest referable at the §3-promised
  pointers (`/capture_id`, `/artifact_id`, `/sha256`). The minted id is retained in the
  ledger entry's `issued_ids` and **invalidated when the step's operation does not
  succeed** (joining the `("invoke", "read", "write")` gate). Replay/occurrence semantics
  are the ledger's, unchanged.

**The accepted trade, named:** until the promotion event, main carries capture machinery
no production admission can exercise (the default composition resolves 0.1.0, which
refuses capture steps) — corpus-gated dormant code, sanctioned by the promote-at-end
ruling. The seam's non-leakage (S-R1/S-R3, no new channel) is the governor's review
target; the dormancy ends at the promotion event by construction.

**The promotion event (train end — a pure release, ZERO new code):** copy
`standards/execution/0.2.0-dev/` → `standards/execution/0.2.0/` (class rule governs the
promoted version — MINOR recommended, §Governance); version sweep in the promoted copy
(`contract_version` consts, examples' fields, `$id`s per the fork ruling, titles); bump
the execution-corpus literals (`control/documents.py:48`, `control/coordinator.py:81`) in
the same arc — the sweep sites the refute's lane-2 census named (interface's
`interfaces/mcp.py:52` + `interfaces/validation.py:37` and registry's
`registry/schemas.py:22` follow the same pattern at their own promotions); promoted rows
cite the **dev path** as `source` AND the pre-dev 0.1.0 paths as **`lineage`** (the
§13.10 required field; repin refuses a `lineage` naming a `-dev` path); delete the dev
directory and rows; remove the `dev` block (a leftover block fails
`dev_target_not_greater` at load — the structural forgetfulness catch); flip the active
entry; `repin`; regenerate the 0.2.0 validation report via `check_execution.py
--write-report`; `docs/README.md` row; identity block's execution row (CON-8; no repin);
export; SDK sync (SDK push first, pointer second); matrix regen; the M-B′ promotion
re-measure arm (Decision 2). The 24h window is re-verified against HEAD at the event;
MINOR-vs-PATCH and the `$id` convention are ruled at the event.

### 1c. What row A deliberately does not do (each named, each deferred)

- **No `$stg_issue` variant.** `$stg_issue` MINTS fresh ids at marked input fields; the
  capture id is minted by the capture step itself and reaches later steps as part of its
  landed result via `$stg_ref` (e.g. `/capture_id`). If the #146 dataset/invoke train
  wants a fetch action's marked input to receive a capture id, THAT train adds the enum
  variant. Home: this record's deferral table.
- **No stream-subscribe step kind.** Subscriptions are run-owned from commissioned bench
  declarations (#167 Decision 3).
- **No dataset-lane sampling of captures** (#43 row 2 / #146).
- **No capture-capable demo fixture** — see the row-D fork below; the execution controls
  ride harness descriptors (the `_mutated_descriptor` precedent).
- **No ACTIVE-manifest-derived resolution.** The seam's ACTIVE member keeps the frozen
  literals (the refute's corrected premise: the sites, not the resolver, pin the version);
  making active resolution manifest-derived is a named future hardening so a future bump
  cannot rely on the literal sweep alone — deferred (row 8), not this train.

## Decision 2 (row B) — the deadline-aware busy-timeout clamp + the mid-capture measurement (UNPARKED)

The six-point review closed in #167 Decision 7; this train builds it. **Unparked by the
promote-at-end model:** M-B′ no longer waits for a promotion — it measures through a real
capture **step** admitted by a `DEV_HEAD`-composed gateway (the same code paths the
promoted corpus will drive; the seam changes only which directory the schemas load from).

- **New pragma surface:** `Store` gains a guarded busy-timeout window —
  `busy_timeout_window(ms)` (context manager: `PRAGMA busy_timeout=<ms>` on entry, restore
  the `Store.open` default on exit, `try/finally`). The store still reads no clock
  (STO-1 unamended): the remaining-deadline arithmetic happens bridge-side on the injected
  monotonic clock.
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

**The measurement (M-B′):** a real capture **step** — a procedure carrying a `capture`
step, admitted against the head's schemas by the `DEV_HEAD` composition and executed
through the activated composition (the `build_run`-constructed bridge on a capture-capable
harness descriptor). The second writer acquires `BEGIN IMMEDIATE` **after** the G3 gate
passes (mid-capture), so the contended writes are the append and the abort epilogue — the
anchor's 2×-busy shape. Pre-committed reading in §Acceptance. **Promotion-time re-measure
arm (belt-and-braces):** at the promotion event the measurer re-runs M-B′ under the
default (active-0.2.0) composition — same numbers expected; a divergence names a seam
defect (the compositions resolving different schemas), not a capture defect, and is fixed
on the seam before the event closes.

## Decision 3 (row D) — fixture-lattice streaming demo (no standards bytes; building now)

- `fixtures/execution/descriptor-sim-psu.json`: `integration.adapter.permissions` gains
  `"event_sink"`; the descriptor root gains `stream_limits`
  (`{"min_interval_ms": <declared>, "max_subscriptions": <declared>}` — fixture authoring
  choices pinned by the vectors/tests, not commissioned numbers; the demo bench is
  synthetic).
- `plugins/benchweave/sim_psu/` plugin: `next_event` event production honoring the declared
  `min_interval_ms` floor, strictly-increasing per-subscription sequences, terminal `ended`
  semantics (the bridge's event-validation contract; a sim that violates it poisons by
  design and the tests pin the sim honest).
- **Lattice rebuild in lockstep** (obligation 5; the #66 lesson — plugin-source changes
  make the rebuild mandatory): `scripts/registry/build_fixtures.py` regenerates
  `payload.zip`s, `catalogue.json`, status rows and digests; the digest-pinning tests stay
  green.
- Docs: `docs/device-developer-guide.md` demo-lattice mention moves in the same PR
  (obligation 3). No operator-guide motion.

This gives the activated streaming composition a REAL admitted demo device: subscriptions
construct a `StreamController` through the unmutated fixture lattice, telemetry lands as
`event_log` evidence under `run:{run_id}` during delay windows — the #167 R14 shape on the
lattice itself. **Independence, stated:** row D rides active-corpus machinery only
(`event_sink`/`stream_limits` in ACTIVE OTDP 0.2.2; #167 streaming activation merged) —
no dependency on the head, the seam, or the promotion; lands in its own slot.

## Decision 4 (row G) — manifest canonicality refusal at resolution (F4)

The pin lattice is single-digest end to end (status rows, lock dependencies, catalogue,
cache directory, loader check); the loader's canonical re-hash makes that digest discipline
**canonical-bytes** implicitly. The fix makes it explicit at the boundary where manifest
bytes are first decoded and pinned:

- `Resolver._resolve_release` gains a canonicality check: the served bytes must equal
  `json.dumps(parsed, sort_keys=True, separators=(",", ":")) + "\n"` — byte equality, the
  same formula the loader verifies — else refuse with the machine prefix
  `manifest_not_canonical:` naming the package. Raised through the resolver's existing
  typed-refusal shape so admission, bootstrap and the run-time closure all inherit it.
- The loader's check is kept verbatim (defense in depth — it still refuses a tampered dict).
- Publisher-side: one sentence in the device-developer/publishing guide (emit canonical
  JSON — `json.dumps(sort_keys=True, separators=(",", ":")) + "\n"`).
- **Considered and declined:** normalizing at admission (re-encoding served bytes and
  re-pinning breaks the cross-document lattice — status/lock rows pin the published
  digest — which is laundering, not fixing); relaxing the loader's re-hash (removing a
  check to fix a mismatch). The refusal makes the incompatible state unrepresentable.

No corpus byte moves. **Independence, stated:** registry-resolver admission policy,
orthogonal to procedure corpora, the head, the seam, and the promotion.

## Slice order

1. **Increment 1 — row A as the dev head: DONE, MERGED** (PR #185, `8d2f659`; OPEN
   `4bfbf88`, author `0608490`, refute folds `8aca4d1`/`111d27d`).
2. **Increment 2 — the seam + the four runtime surfaces.** `declared_dev_family` +
   `CorpusResolution` + the composition threading (S-R1–S-R4) and the projection,
   semantics, policy, executor (+`_resolve_ref` arm) surfaces, all exercised green through
   the `DEV_HEAD`-composed gateway; A-R3/A-R4/A-R5 run against dev-resolved admission.
   Corpus-gated dormant code on main is the accepted trade (§1b).
3. **Increment 3 — row B (unparked).** The pragma window + controller/bridge clamp +
   epilogue floor + the M-B′/M-C′ measurement pass through the dev-resolved composition
   (bench-measurer lane).
4. **Increment 4 — rows D + G** (building now; independent — may land in any slot).
5. **The promotion event — train end, timed by the standards coordinator** (fork 1
   RESOLVED to promote-at-end; fires when the train is complete or the owner calls it):
   the pure release of §1b — literal sweep, version sweep, `lineage`, teardown, repin,
   report, export, SDK sync + pointer, matrix; window re-verified; MINOR/`$id` ruled; the
   M-B′ re-measure arm run. **ZERO new code by design — the seam self-retires.**

## Precedent (proven in-tree mechanisms every shape extends)

- **The seam:** the checker lane's `corpus_directory`/`_declared_dev_head`
  (`scripts/architecture/_validation_report.py:51–146`) — accept-exactly-the-declared-head,
  canonical-loader resolution with the loader's own refusal words, view-not-mutation. The
  gateway twin changes exactly one thing (a composition parameter instead of argv) and
  adds the typal no-path rule. `contract_family`'s packaged-first discipline
  (`vendoring.py:29–34`) is the packaged-impossibility layer. The composition-root
  injection pattern is `create_app`'s own (RegistrySession et al.; #167 threaded quota
  through the identical path).
- **The dev head:** the devstage record's built mechanism — increment 1 is its first
  production use, now merged.
- **The promotion arc:** #147's OTDP 0.2.2 re-roll and #64's OTDP 0.2.0 train, with the
  devstage §4.4 amendments (dev-path `source`, required `lineage`, teardown) and the
  refute's literal-sweep census.
- **A closed oneOf branch with a policy twin:** the `invoke`/`write` allow-rule pair; the
  capture branch is the third of the same shape.
- **Host-minted occurrence ids:** `_operation_id` and the `$stg_issue`
  mint-retained-invalidated registry — `cap:` ids join both molds.
- **Result references:** `_resolve_ref`/`resolve_value` (`executor.py:340`/`:284`) — the
  manifest lands in scope exactly as invoke results do, via the arm the refute verified
  is missing today.
- **Admission-time descriptor mirrors:** `_check_declared_usage` and the CON-10
  projection's actions+issued surface.
- **The clamp's containment shape:** the writer-originated lock-contention classification
  (`otdp_bridge.py:359–397`) and B15-iii's designated-retry mold.
- **Fixture rebuild lockstep:** #66's PR #72 — row D is that shape again, streaming
  edition.
- **Loud typed refusals with machine prefixes:** every admission fence in
  `control/documents.py` and `registry/*` — `manifest_not_canonical:`,
  `execution_dev_head_absent:`, `dev_head_unresolvable:` join the family.

## Invariant and cross-surface impacts

- **CON-7:** dev rows' first production exercise (merged); the seam adds no row fate.
- **Increment 2's amendments (landing with the surfaces):** CTL-4 (third allow-rule kind,
  `capture_constraint:` prefix), CTL-5 (capture occurrences; failed capture invalidates
  its minted id), CTL-7 (`capture_undeclared:` mirrors; manifest results in lexical
  scope), CON-10 (projection capture surface). CTL-6 unamended, argued: the capture step
  carries literals only (no `input` object, no reference positions —
  `additionalProperties: false` makes a `$stg`-bearing capture step unrepresentable), so
  what the policy checks is what dispatches, trivially.
- **CON-1 note (the seam's honesty):** admission still validates pinned bytes against
  admitted schemas; `DEV_HEAD` changes WHICH corpus directory the family resolves — the
  head's bytes are pinned and validated exactly like active bytes (devstage §4.1), so the
  exact-byte posture is unchanged in kind. The default composition is byte-identical to
  today (S-R1).
- **Row B:** STO-1 unamended, argued (bridge-side deadline arithmetic; the store sets a
  handed-down pragma). `state/` and `control/` touched → `tests/faults/` runs.
- **Row G:** strengthens CON-1's exact-byte posture; no REG invariant moves.
- **Everything else (CTL-1/2/3/8/9, STO-2/3/4, CON-2…12 minus the named, REG-1…4):
  untouched.**
- **Obligations:** increment 2 — the seam is dev-workflow machinery, not operator-visible
  (no operator-guide motion); the device-developer guide's capture-authoring section lands
  with the surfaces (the corpus admits capture steps for dev-corpus authors). Increment 4
  — obligations 3 and 5. The promotion event carries obligations 6/7/8/13 in full. CI
  cost: none new — all controls are plain pytest on the existing `gates` job; the
  measurement pass is run-lane.

## Pre-committed acceptance rule (written before any implementation number exists)

Floor semantics inherit the house rule: every control must (a) pass with the mechanism
present and (b) **fail when only the mechanism commit is reverted** — absence-presence,
watched red then green. No underpowered mode applies to controls; the measurements carry
their own underpowered readings.

**The seam (gates the rest): S-R1–S-R4 as specified in §1b.**

**Row A — corpus (pinned by increment 1; re-asserted because later increments must not
touch head bytes)**

- **A-R1 (corpus admits capture; active does not):** the head's examples validate through
  `check_execution.py --corpus standards/execution/0.2.0-dev`; the SAME documents against
  the frozen active 0.1.0 schemas fail on the capture step. Negative shapes refuse in the
  dev lane: unknown field, missing `timeout_ms`, `format` outside the enum.
- **A-R2 (the head's diff is exactly the capture family):** the head tree against its
  0.1.0 source differs by exactly: +1 step branch, +1 allow-rule branch, the prose
  sections, the example additions — step kinds == eight + `{capture}`; allow-rule kinds ==
  `{invoke, write, capture}`; `$stg_issue` enum unchanged; every pre-existing schema
  branch byte-identical. RED: any other widening fails the assertion.

**Row A — runtime surfaces (against `DEV_HEAD`-composed admission)**

- **A-R3 (admission + policy deny-by-default):** through the `DEV_HEAD`-composed real
  admission path — a capture step on a capture-declaring device admits; on a
  non-capturing device refuses `capture_undeclared:`; with no capture allow rule the
  dispatch is denied `no_matching_rule:` with zero adapter `execute` calls; a
  `capture_constraints` violation refuses `capture_constraint:`. RED: revert the policy
  consult → the dispatch proceeds and the zero-execute assertion fails.
- **A-R4 (execution + identity + scope):** a run through `build_run` (dev-resolved) on a
  capture-capable harness descriptor executes a capture step: step event per occurrence;
  the manifest is the step's result; a later step's `$stg_ref` pointer into it resolves
  through `_resolve_ref` (`/capture_id`, `/artifact_id`, `/sha256` — the refute-verified
  arm); the minted id matches `cap:{run_id}:{step_id}{suffix}` and sits in the ledger's
  `issued_ids`; a failed capture invalidates it; replay answers from the ledger without
  re-dispatch. RED: revert the executor branch → unknown-kind `execution_error`; revert
  the resolver arm → the `pointer:` terminal raise.
- **A-R5 (budget):** `worst_case_body_ms` counts capture timeouts; a procedure whose
  static bound overruns `max_body_ms` on capture timeouts alone refuses admission. RED:
  skip the kind in the walk → the refusal assertion fails.
- **SDK conformance surface (at the promotion event):** `make check-sdk-standards` green
  with lock + vendored tree at 0.2.0.

**Row B (through the dev-resolved composition)**

- **B-R1 (clamp bounds the mid-capture shape):** second writer acquired after the gate,
  with the clamp: the dispatch's wall-stretch lands in the ≤1× `busy_timeout` +
  epilogue-floor class (NOT the 2× anchor); classification `RESOURCE_LIMIT`, session
  survives; staging reclaimed. RED: revert the clamp → the stretch returns to the anchor
  class and the bound assertion fails.
- **B-R2 (leak discipline):** after clamped dispatches on both success and failure paths,
  `PRAGMA busy_timeout` reads the `Store.open` default again (including a dispatch that
  raises between set and restore).
- **B-R3 (sweep exemption):** `sweep_open`/close/`reclaim_orphans` waits are bounded by
  the default, unclamped.
- **M-B′ (pre-committed measurement, the row's headline):** ≥5 trials, mid-capture
  contention, a real capture step through the `DEV_HEAD`-composed activated composition;
  report median and spread of dispatch wall-stretch vs the commissioned step deadline,
  **with the clamp present**; the held-from-start shape (#167 M-B, median 5.199 s) is the
  matched control condition. **Ships if** the clamped median ≤ 1× `busy_timeout` + the
  measured epilogue class with spread ≤ 25%. **Fires arm 3** (Option B evaluation, posted
  to #159 per #167's pre-committed reading) **if** the clamped stretch still exceeds the
  recorded 2×-busy anchor bound by a margin the clamp design cannot remove, or the monitor
  gap during the stretched dispatch breaches the capture-deadline policy bound with no
  clamp-side remediation. **Underpowered if** the mid-capture window cannot be reproduced
  stably (spread > 25% over ≥5 trials) — record underpowered + arm unfired +
  "re-measure with a stable harness", and decide nothing from it. M-B′ never silently
  converts to Option-B evidence. **Promotion re-measure arm:** re-run under the
  active-0.2.0 composition at the event; divergence names a seam defect (fix the seam
  before the event closes).
- **M-C′ (rider):** queued-run delay behind the clamped contended capture — expectation:
  the slice-1/#167-M-C class; a larger delay names an unbounded path, not Option-B
  evidence.

**Row D**

- **D-R1 (the lattice streams):** post-rebuild, the demo bench admits at bootstrap and a
  run on it constructs a `StreamController` for the psu through the unmutated fixture
  lattice; during a delay step telemetry lands as `event_log` evidence under
  `run:{run_id}`. RED: revert the descriptor permission → no stream services construct,
  zero events.
- **D-R2 (sim honesty):** the plugin's event production honors the declared floor and the
  strictly-increasing/terminal-`ended` contract.
- **D-R3 (lockstep):** `build_fixtures.py` regenerates; `test_registry_fixtures` and the
  digest pins stay green — no hand-moved fixture bytes.

**Row G**

- **G-R1 (the residual, made unrepresentable):** a fixture-adjacent manifest re-serialized
  non-canonically refuses at resolution with `manifest_not_canonical:` naming the package.
  RED: revert the check → the closure resolves AND `load_otdp_plugin` refuses
  `manifest_hash_mismatch` — assert that today-shape fails red under the mechanism.
- **G-R2 (no collateral):** every in-tree fixture manifest passes the check.
- **G-R3 (defense in depth kept):** the loader still refuses a tampered manifest dict.

## Governance walk

1. **No bump until the promotion event.** Increments 2–4 touch no `standards/` bytes at
   all; the head is invisible to the train window by construction. At the event: the
   window is re-verified against HEAD (last execution dir 0.1.0 added by the 2026-09-16
   reset — long expired, but the check is restated at the event, not assumed).
2. **Head discipline (standing, from increment 1):** dev rows cite 0.1.0 as `source`;
   edit → repin on any head change (`normative_hash_mismatch` is the honesty gate);
   `--corpus` proofs green; SDK stillness across all head-adjacent commits.
3. **Increment 2's governor review target — the seam's non-leakage:** S-R1/S-R3 green; no
   env/config/wire channel creeps in beside the keyword-only enum; the dormant-code trade
   is the accepted, named posture (§1b); the lane's refusal words and the seam's refusal
   words agree on both surfaces.
4. **The promotion event:** copy-never-move from the dev source; `lineage` to 0.1.0 (the
   §13.10 required field); version sweep + literal sweep (the censused sites); teardown
   with the loader's structural forgetfulness catches; repin; report regen;
   `docs/README.md` row; identity; export; SDK sync + pointer; matrix. MINOR-vs-PATCH and
   the `$id` convention ruled at the event (recommendations below).
5. **Review gate:** governor lane mandatory for any `standards/` touch; corpus bytes +
   rows → single human reviewer with the coordinator self-review carve-out. The
   coordinator times the event (fork 1's resolution).

## Top risks and what falsifies this design

| Risk | Falsifier / disposition |
|---|---|
| **Corpus-gated dormant code on main** (capture machinery no production admission can exercise, increment 2 → promotion) | The named, accepted trade of the promote-at-end ruling; bounded by the event's certainty (train end or owner call); the seam's non-leakage is the governor's target (S-R1/S-R3); falsified by ANY new channel reaching the parameter — kill direction: remove the channel, do not gate it. |
| **The seam leaks into production posture** (an accidental `DEV_HEAD` composition, a new config path) | Structurally: keyword-only injection, no env/config/wire surface, packaged impossibility (the head is never in a wheel), self-retirement at teardown. The review checks no creep; S-R1/S-R3 pin it. |
| **The promotion re-measure diverges** (dev-resolved vs active-resolved numbers differ) | Names a seam defect — the compositions resolve different schemas — fix the seam before the event closes; never tune the measurement to match. |
| **The head rots open past train end** | The trigger is now simple (train complete or owner call) and the event is a pure release; the coordinator's stale-head ruling path exists; the `opened` date stays machine-readable. |
| **Threading the seam needs a second composition path** (a `_CONTRACTS` consumer that cannot take injection) | The increment splits rather than widens the seam (named in §1b); inventing a parallel admission path remains the DON'T-BUILD line. |
| **MINOR vs PATCH contested at the event** | Bytes identical either way; governor rules with the recorded argument (new capability + new consumer obligation; §1's "reviewed language extension" is not errata). |
| **The clamp masks legitimate long waits** | The clamp only shortens waits already doomed to exceed the step deadline (six-point point 4); commissioned `timeout_ms` (A02) remains the lever. |
| **Row D rebuild churn** (many digest moves obscure the real diff) | The builder is the only writer (obligation 5); the reviewer reads the plugin + descriptor diffs; D-R3 pins lockstep. |
| **Row G refuses a real pretty-printed registry** | Disclosed ecosystem constraint with a one-line publisher fix; the alternative (dual digest disciplines) is the F4 bug itself. |
| **M-B′ does not reproduce stably** | Pre-committed underpowered reading; arm unfired; no decision from the run. |
| **Train sprawl** (four rows + a seam + a promotion event) | The brief's rows are the scope; every newly-spawned want lands in the deferral table, not the PRs. |

## Deferrals — every row names its home and reopen trigger

| # | Deferred | Home | Reopen trigger |
|---|---|---|---|
| 1 | **The promotion event** (the pure release: literal + version sweep, `lineage`, teardown, repin, report, export, SDK sync + pointer, matrix; the M-B′ re-measure arm; the MINOR/`$id` rulings; the window re-verification) | This record §1b; the head itself; fork 1 RESOLVED to promote-at-end | **Train complete (all four rows merged) or owner call** — the owner ruling of 2026-09-24: "to continue development we can use the dev corpus, until all is finished, then it will be promoted" |
| 2 | `$stg_issue` gains `capture_id` (fetch-lane input field) | This record §1c | The #146 dataset/invoke train's fetch-action design |
| 3 | Capture-capable demo fixture (sim-psu `artifact_writer` + capture verb + demo-procedure capture step) | This record §1c | First operator-facing demo procedure needing capture, or the #146 train — whichever first |
| 4 | `stream_subscribe` procedure step kind | This record §1c | A procedure author needing procedure-authored subscriptions |
| 5 | Corpus promotion of the manifest-canonicality requirement | This record §Decision 4 | A second publisher surface needing the requirement stated normatively |
| 6 | Aggregate teardown-window deadline (#167 F2 disclosure — unchanged) | #167 record | A commissioned envelope demanding it |
| 7 | Capture format-enum widening beyond the core lane | This record §1a | An OTDP capture-formats revision train |
| 8 | ACTIVE-manifest-derived corpus resolution (retiring the frozen literals at the runtime sites) | This record §1c | The first bump that would otherwise rely on the literal sweep alone, or a CON-10-style unification train |

(#167's rows C, E, F stay closed in that record's table — none is this train's scope.)

## Forks for the maintainer

1. ~~Promotion timing~~ — **RESOLVED 2026-09-24, owner ruling (promote-at-end):** *"to
   continue development we can use the dev corpus, until all is finished, then it will be
   promoted."* The event fires at train completion or owner call; the coordinator times it.
2. **Row A change class at the promotion event** — MINOR (recommended) vs PATCH; governor
   rules at the event with the argument recorded in §Governance 4.
3. **Execution `$id` convention at the event** — track the standard version (recommended,
   `urn:stg:execution:procedure:0.2.0`) vs keep the decoupled `1.0.0` segment (registry
   precedent).
4. **Capture-capable demo fixture now vs deferred** — deferred (recommended; row D stays
   streaming-only per its carrier; harness descriptors carry the execution controls) vs
   extending the same rebuild.
5. **Capture allow-rule target** — `format` exact-match (recommended) vs device-wide
   capture rules (declined; widening-by-descriptor-edit).
6. **Pre-sweep the dev copy's version consts vs leave them to the promotion sweep** —
   leave-to-sweep (recommended; substance-only diffs — as landed in increment 1).
7. **NEW — seam durability after this train:** keep the `CorpusResolution`/
   `declared_dev_family` seam as a permanent dev-workflow surface (recommended — it is
   the gateway twin of the permanent checker lane; the directive's "as we move forward"
   implies future trains develop the same way; it is inert without an open head and
   self-retires at each teardown) vs train-scoped scaffolding torn down at promotion
   (leaves future dev-corpus trains runtime-untestable and re-pays this design).
