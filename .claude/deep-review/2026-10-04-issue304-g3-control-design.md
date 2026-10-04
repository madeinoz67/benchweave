# G3 design — control: leases, staged inputs, runs, energy confirmation, expiry guards (issue #304, PRD 12)

**Verdict: BUILD, two slices.** Triage call: mechanisms, issue numbers and code paths
only — no person, client, bench, serial or install detail — public path as named.

**Evidence baseline:** gateway `origin/main` `1e5865c` (2026-10-04, fetched this session;
includes #375/#376/#377/#378 — #369 reading tiles, #367 normative seam, **#316
endurance-authz**, #191 capture limits — and #373/#374). Trigger state verified: #303
merged (G2 complete), #306 CLOSED (DEP7: the bound is `max_body_ms` read via
`document_get`), #307 CLOSED (6-hour manual lease default ruled; **the code change has
NOT landed — `app_entry.py:103` still reads `max_lease_ms: 600000`; #307's closing
comment assigns it to "G3 (#304) or a standalone one-line increment" — G3 carries it**).
No open PRs on either repo; no remote branch touches the planned paths ahead of this
design (pre-flight rule #181 R2 walked).

## 1. Premise check (verified, not assumed — every load-bearing fact with its anchor)

- **The interface has NO lease read and the lease wire object omits the holder.** The
  20-operation catalog is 12 read + 8 mutating; no lease read exists
  (`standards/interface/0.1.0/operation-catalog.json`, enumerated this session).
  `_lease_projection` is closed at five fields — `{lease_id, bench_id, sequence,
  expires_at, state}` — with the docstring "the holder is deliberately not exposed"
  (`src/benchweave/interfaces/operations.py`, `_lease_projection`). The ONLY way a
  client learns lease state is the `lease_create`/`lease_renew` **response**.
- **`bench_get` carries a lease-adjacent fact, but only one:** `_bench_projection`
  returns `busy = self._live_lease(bench_id) is not None` — "some live lease exists",
  never whose (`operations.py`, `_bench_projection`). `tripped` is **hardcoded `False`**
  — `docs/compatibility.md` discloses this ("no live trip source in the PoC"), and
  `trip_reset`'s own gate reads that always-False flag.
- **A trip IS on the wire, as an event.** The worker appends a `trip` bench event iff
  the durable terminal record's outcome is `tripped`
  (`src/benchweave/interfaces/worker.py:251`, `_emit_completion`); `trip` is in
  `Operations.EVENT_KINDS`. An applied `trip_reset` emits `bench_changed` carrying the
  change's `target_ref` as evidence (`_dispatch_change` / `_apply_trip_reset`) — the
  change kind itself is NOT on the event wire, so a reset's `bench_changed` is not
  distinguishable from a configuration activation's. This underdetermination is dealt
  with in §2.4.
- **Manual-mode starts require a lease at the seam; gateway-owned starts require the
  commissioned unattended grant.** CTL-10 / `_check_unattended_grant`
  (`src/benchweave/control/documents.py:1474`): `procedure.mode ∈ {manual,
  gateway_owned}` (`procedure.schema.json`); `manual` + no presented lease → typed
  `policy_denied` `manual_lease_required:`; `gateway_owned` requires
  `commissioning.modes` to carry `"unattended"` with a passing `unattended`-category
  evidence row. **A presented lease is validated and CONSUMED at accept**
  (`_assert_bench_acceptable` → `store.consume_lease`) — the manual lease does not
  survive the start; the run then holds its own budget (STO-4).
- **GW-56's bound chain (DEP7, #306 verified):** binding (client-held `{id, version,
  sha256}`) → `document_get` → the binding's `procedure` pin → `document_get` →
  `content.max_body_ms` + `max_protection_ms` (both required, 1–86,400,000 ms;
  `procedure.schema.json`). `run_check`'s output does NOT carry it (`{valid,
  generation, findings}` closed). The PRD's §7(f)/§11 name `max_duration_ms` — #306's
  terminology note already corrects this (`max_duration_ms` is the safety policy's
  safe-transition field); this design uses the verified names.
- **The interface's run inputs carry no parameter values.** `run_start` takes exactly
  `{bench_id, request_id, binding_ref, expected_generation, lease_id}` and `run_check`
  `{bench_id, binding_ref}` (catalog input schemas, `additionalProperties: false`).
  "Staged inputs" at the gateway UI therefore means the *binding selection* (plus the
  session-held lease and the minted request id) — there are no numeric parameter
  inputs to stage; those live inside admitted documents. `request_id` must match
  `^[a-z][a-z0-9_.-]*$`.
- **§9 dedup already makes double-submit safe at the seam:** `run_start` keys
  `principal + "run_start" + request_id`, replays return the original run without
  re-enqueue, same-key-different-binding is `conflict`, and refusals precede the key
  write (no tombstone for a refused start) — `operations.py::run_start`. GW-13's UI
  half is a FIXED request id per staging cycle; the seam does the rest.
- **`lease_create`/`lease_renew` carry no duration ceiling anywhere**: the catalog
  schema caps `duration_ms` at 2^53 and the seam passes it straight to
  `_iso_plus_ms` (operations.py:861/971) — `max_lease_ms` is *published*
  (`gateway_info.limits`) but not enforced on `duration_ms`. Observed seam fact,
  disclosed in §9; the UI's picker bounds itself by the published limit and GW-95's
  session bound regardless.
- **The G2 substrate this extends** (all landed, read this session): the mounted `/ui`
  sub-app with its four omittable guards (`ui.py`); `SessionStore` with server-side
  records, bridge registry, lazy expiry sweep (`sessions.py`); the route registry
  `UI_ROUTES` + `route_mapping_violations` where GW-10's one-operation rule fires only
  for `classification == "interface"` mutating routes (`ui_routes.py`); the §C.3 row
  table + `render_no_response(request_id)` whose reconcile LINK already exists
  (`ui_refusals.py`); read pages incl. the run page and `/ui/requests/{id}` reconcile
  view (`ui_read.py`); the SSE bridge with server-held cursor and HWM dedupe
  (`ui_stream.py`); page templates (`ui_templates/*.j2`) with the `mode_banner` slot
  wired but always `None` today ("the wire carries no lease-holder or policy-engine
  fact" — `ui_read.py::_strip`).
- **The package already carries every component G3 composes**: `ConfirmActionData`
  with `guard_reason`/`guard_label` for the armed fire-time rule, `ButtonData` with
  `disabled_reason`/`disabled_label` for §C.2, `ModeBannerData` with the `no-lease`
  key, `render_disabled_label` (`packages/ui-html/src/benchweave_ui_html/{data,
  partials}.py`). **Zero package motion expected.**
- **GW-44's mechanism is settled by ruling**: warn when remaining ≤ max(20% of
  duration, 2 min); critical when remaining ≤ max(5%, 30 s) — the floor guarantees a
  minimum reaction window (PRD §9 Q2), and #307's closing ruling works the 6-hour
  consequence: warn at 72 min, critical at 18 min, "floors inert at this duration by
  design; they continue to protect short-lease configurations only". A lease at or
  under 2 minutes carries the warning from creation — #307's own noted noise shape,
  accepted there.
- **G2's deferral table (D-rows) triage**: **D1** (session-expiry warnings, GW-44's
  session half) and **D2** (GW-13 request-id wiring, GW-12's mutating-form
  no-response half, GW-55's cancel wording) name "G3 (#304)" as home — **carried
  here**. **D3** (chart hydration) is #310's. **D7** (theme toggle) was parked
  "G3's UX polish rows" by convenience of ordering, but it is in neither #304's scope
  nor the PRD's G3 requirement set (GW-40–44/50–57/95) nor the exit gate — **re-deferred**,
  home: the G4 (#305) design record or an owner-called standalone UX slice (§3).
  D4/D5/D6/D8/D9 unchanged.

## 2. The mechanism

All control flows through interface 0.1.0 operations only. New surface: one module
(`src/benchweave/interfaces/ui_control.py`), extending the exact G2 shapes — the
rest.py three-step translation with the Identity source swapped, registered on the UI
router before its catch-all, rows added to `UI_ROUTES`.

### 2.1 The session-side control state (the one new state home)

`SessionStore` gains two side tables under its existing lock, mirroring the bridge
registry's shape (server-side session state; killed by logout, expiry sweep and
gateway restart exactly like sessions themselves):

- **Held-lease view** — `session_id -> {bench_id -> HeldLease}` where `HeldLease` is
  the lease projection returned by THIS session's `lease_create`/`lease_renew` call
  plus the `duration_ms` the session requested (GW-44's percentage base). This is the
  answer to §1's first premise fact: the interface exposes lease state only through
  mutating responses, so the session retains the response it caused. Holder display
  (GW-40): the panel renders the session's own principal — correct by construction
  because the seam mints `holder = identity.principal` and renews holder-only; a bench
  whose live lease this session did not create renders "held by another caller" from
  the `busy` fact, with no identity (the wire's own posture — the holder is
  deliberately not exposed).
- **Staging record** — `session_id -> {bench_id -> StagedStart}` where `StagedStart =
  {request_id, binding_ref, check: {valid, generation, findings} | None, armed: bool}`.
  The request id is minted once per staging cycle (`"ui-" + uuid4().hex[:12]`,
  pattern-legal), fixed across check/arm/confirm and across post-refusal retries
  (§1: a refused start writes no §9 tombstone, so reuse is safe), cleared when a start
  commits.

Both are presentation state of gateway responses the session itself caused — not
authority. Every mutating POST re-validates at the seam; a stale held-lease view fails
at the seam exactly as it would for any REST client (the seam is the authority; the
views only decide what the page renders).

**Disclosed boundary (the honest negative):** a lease created by the SAME principal
through another surface (REST/MCP/another browser session) is invisible to this
session's view — the page shows `no-lease` and disables the energy-sourcing controls.
Conservative direction only (it disables; it never enables what the seam would
refuse); the take-lease control stays enabled and the seam's `conflict` refusal
speaks honestly if another lease is live.

### 2.2 Lease controls (GW-40–44, GW-95, D1)

The bench page gains a **control region** (a raised panel) rendering, from the seam:

- **Take lease** — `POST /ui/benches/{bench_id}/leases` → `lease_create`. The form
  offers `duration_ms`, bounded at render by `min(gateway_info.limits.max_lease_ms,
  session_remaining_ms)`; **GW-95**: when every legal duration would outlive the
  session (i.e. `session_remaining <` the minimum the form offers), the control
  renders disabled with the session expiry stated (wall time) and the clearing action
  ("run `benchweave ui-login` for a longer session"), and the handler refuses the POST
  pre-send when `now + duration_ms > session.expires_at` (a forged/direct POST cannot
  reach the seam with an outliving lease). `expected_generation` comes from the
  `bench_get` the page already made.
- **Renew** — `POST /ui/leases/{lease_id}/renewals` → `lease_renew` with the held
  view's current `sequence`. Same GW-95 bound. GW-41/GW-57: nothing renews in the
  background, ever; the bridge's `lease_changed` events only add rows to the live
  event list.
- **Release** — `POST /ui/leases/{lease_id}/release` → `lease_release`.
- **The lease facts row (GW-40)** — holder (per §2.1), `expires_at`, and remaining
  time, all from the held view; the state renders `expired` when the stored
  `expires_at` has passed — the same read-time arithmetic the seam's `_live_lease`
  oracle applies (the stored stamp is the oracle; the UI computes remaining from the
  gateway's own expiry field, never infers more).
- **GW-44 warnings** — a pure, injected-clock predicate
  `expiry_warning(remaining_ms, duration_ms) -> None | "warning" | "critical"` with
  `warn_at = max(duration_ms // 5, 120_000)` and `critical_at =
  max(duration_ms // 20, 30_000)` (20% / 5%; Q2's max() semantics per §1). Rendered
  per §B.1 (warning: persistent-until-acknowledged-or-resolved; critical:
  persistent-until-resolved, `alert` region). The warning names what is lost — for a
  held lease: "manual work on this bench will be ended by the safe transition" — and
  carries the renew action (GW-44's own required content). **D1 (the session half):**
  the same predicate over the session's remaining time and granted duration
  (`SessionRecord` gains a `duration_s` field recorded at exchange), rendered in the
  shell on every page: names what is lost (the session ends; leases held by it cannot
  be renewed afterwards — GW-95's rationale) and the clearing action (`ui-login`).
- **`no-lease` mode entry + `no-authority` disabling (GW-42)** — the bench and device
  pages populate the `mode_banner` slot (G2 wired the slot; `ui_read._strip` gains a
  bench-scoped mode computation) with the §D.1 `no-lease` entry iff the session holds
  no lease view for that bench. Controls that require lease authority — in G3a the
  renew/release controls' absence is the no-lease shape; from G3b the staging,
  check and energy-sourcing start controls — render disabled with §C.2
  `no-authority` ("No lease or policy authority"). Take-lease is never disabled by
  `no-authority` (it is the path OUT; the seam refuses `conflict` honestly when
  another lease is live). Observe-scope sessions: every mutating control renders
  disabled with `no-authority` — §C.2's own note says the key "absorbs the reference
  renderer's earlier permission-disabled story state"; G2's observe-no-control pin
  stays green by construction.

### 2.3 Live refresh of the control region

The control region is one server-rendered fragment — `GET
/ui/benches/{bench_id}/controls` (`bench_get` + the events tail + the session views) —
composed into the bench page at first render and re-fetched by htmx polling with a
**server-chosen cadence per render**: the limits knob `ui_panel_poll_ms` (default
30 000) normally, `ui_panel_poll_ms // 6` inside warning, `ui_panel_poll_ms // 30`
inside critical. This is how GW-44's escalation appears without any client-side
threshold inference: every rendered byte of the warning is server-computed at the
current clock; the poll only decides WHEN a re-render happens (a read; NFR-O1 holds —
no device-affecting operation on any refresh). The SSE bridge is untouched —
`lease_changed`/`run_changed` rows keep landing in the live-events list it already
serves.

### 2.4 Runs: staging, check, energy confirmation, cancel (GW-50–57, D2)

The control region's second panel is the **staging panel** (labelled *staged*, the
§F `staged` state mark):

- **Staging (GW-50)** — the staged input is the binding selection. Discovery is
  honest to the interface: the panel offers bindings the bench's own event history
  pins (`authority_changed` evidence rows carry `{id, version, sha256}` of binding
  documents) plus manual digest entry; the interface has no binding enumeration and
  G3 does not invent one (raising that is an upstream note, §3). Selecting or
  changing the staged binding is a **session-layer action** (`POST
  /ui/benches/{bench_id}/staging`) — it calls no seam operation and updates the
  staging record; **any change clears the recorded check** (GW-51).
- **Check (GW-51)** — `POST /ui/benches/{bench_id}/run-checks` → `run_check` with the
  staged `binding_ref`; the result (valid, findings, and the returned `generation`)
  is recorded in the staging record. The start control is disabled with §C.2
  `invalid-staged-input` until a check has returned for the CURRENT staged set, and
  the start handler refuses pre-send when no check is on record.
- **Energy classification (GW-52)** — a pure function of the procedure document
  (read through the DEP7 chain: staged binding → `document_get` → procedure pin →
  `document_get`): **energy-sourcing iff any `invoke` step's input carries
  `"enabled": true`** — R-ENERGISE-1's "enabling an output" clause, mechanically
  derivable from admitted documents. The "changing a setpoint of a currently
  energised output" clause is NOT derivable from documents (it needs live device
  state) and is disclosed as uncovered at the run-start granularity (§9 R3). A
  procedure with no enable-true steps (including explicit `enabled: false`) is the
  de-energising class.
- **Confirm (GW-52, §E.1 `confirm-action`)** — an energy-sourcing start is two
  actions: **Arm** (`POST /ui/benches/{bench_id}/staging/arm`, session-layer —
  renders the armed `ConfirmActionData`) then **Confirm** (`POST
  /ui/benches/{bench_id}/run-starts` → `run_start`). The armed text composes from the
  documents: effect ("the output will be energised"), values (the enable step's
  sibling configure inputs — e.g. `voltage_v: 5` → "5 V"), target (device + channel
  from the binding's `bindings[]` role mapping). Unit derivation precedence, stated:
  (1) a same-named `sample` step's declared `unit`; (2) the descriptor parameter's
  unit via the bench-document chain; (3) the field-name SI suffix (`_v`, `_a`, `_ms`)
  as the documented last resort. **Fire-time guards (GW-52/54, R-PROTECT-1):** the
  Confirm handler re-evaluates, server-side, from fresh reads — trip state (§2.5),
  the held-lease view's liveness, the staging record's armed state and check — and
  refuses WITHOUT calling the seam when a guard has arrived, re-rendering the armed
  state with the guard (`protection-active` when a trip is active; the combined
  trip-and-no-authority state presents `protection-active` per the §E.1 Notes). No
  auto-disarm; Cancel (a session-layer `POST .../staging/disarm`) stays enabled; a
  departing guard re-enables on the next render. The gateway's own start checks stay
  authoritative — this guard never substitutes for them (GW-56's own sentence).
- **GW-56 (DEP7 chain)** — at arm and again at fire time, for a `manual`-mode
  procedure: read `max_body_ms + max_protection_ms` via `document_get`; remaining
  attention = `min(lease_remaining_ms, session_remaining_ms)`; when the bound
  exceeds it, the start is refused pre-send (no seam call) rendering the bound, BOTH
  remaining times, and the clearing actions (renew the lease / `ui-login` for a
  longer session); when the binding's commissioning carries the unattended grant
  (`modes` contains `"unattended"` + a passing evidence row — same document read),
  the refusal names gateway-owned mode as the route. Note for the record: with the
  lease consumed at accept (§1), the lease leg of this guard is about the operator's
  *declared attention window*, not the run's own budget (the run holds its own after
  takeover, STO-4) — the PRD's rule is implemented as written.
- **Start (de-energising class)** — one action, never confirmed, never gated by
  `no-authority`/`protection-active` in the presentation (GW-53, R-DEENERGISE-1):
  the same `run-starts` route without the arm step. Without a lease the seam's own
  `manual_lease_required:` refusal renders through its §C.3 row — the honest
  authority answer, not a UI gate.
- **Cancel (GW-53/55, D2)** — `POST /ui/runs/{run_id}/cancellations` → `run_cancel`
  (request id minted at render, reason from the form, min length 1). Ungated: the
  control renders enabled with no lease and during a trip (§6 enforces owner-or-admin
  at the seam, which "does not require an unexpired controlling lease" — its own
  clause). After a cancel POST, the run page renders "cancel requested" (recorded in
  the session's staging-side state as a pending-cancel marker) **until `run_get`
  reports a terminal state** — the marker is presentation of the operator's own
  action; the state itself is always `run_get`'s.
- **Double-submit + no-response (GW-12/13, D2)** — every mutating form carries the
  staging record's fixed `request_id`; the seam's §9 machinery makes a double-click
  or resubmission return the same run (§1). A mutating handler's non-`OperationFailure`
  failure (transport-shaped; an in-process adapter cannot honestly produce one — it
  is induced at the boundary in tests, the G2 §7-F posture) renders
  `render_no_response(request_id)` — sent status UNKNOWN plus the reconcile link to
  `/ui/requests/{request_id}`, which `run_find`s with the same id.

### 2.5 The trip predicate (GW-43/54's wire-honest core)

`trip_active(events) -> bool` is a pure function over the bench's event rows the
adapter can read: scanning newest → oldest, **protection-active iff the newest
trip-lifecycle event is a `trip`** (a `bench_changed` — the only wire shadow an
applied trip_reset has — clears it). Disclosed boundaries, stated in the module
contract and §9: (a) the gateway's own bench projection hardcodes `tripped=False`
(compatibility.md's disclosed PoC boundary) — this predicate consumes the gateway's
own `trip` events, the only live trip signal the wire carries, and §C.1's row is a
*presentation-level* safety rule by the contract's own scope sentence; (b) an
admin-applied configuration activation after a trip also emits `bench_changed` and
therefore also clears the marker — the closed event def has no channel for the change
kind; (c) retention may have dropped an old trip past the window — no verdict, not
protection-active. The gateway's start checks stay authoritative and today carry no
trip gate; making the seam refuse starts on an unreset trip is an interface-side
observation this record files, not a UI change (§9 R2).

### 2.6 The #307 carry (one line, its own commit)

`max_lease_ms: 600000 → 21_600_000` at `app_entry.py:103` and
`cli/demo.py:70` — the ruled 6-hour manual default, published per gateway via
`gateway_info`. The exit gate's "floors confirmed against the commissioned lease
limits" reads, per #307's closing ruling, as: floors sanity-checked against the
deployed `max_lease_ms` — at 6 h the percentages dominate (72 min / 18 min) and the
floors are inert (§6's acceptance K pins the pair).

## 3. Slice split, deferrals, and what is deliberately NOT here

| Slice | Scope | Exit-gate clauses it carries |
|---|---|---|
| **G3a** leases + expiry guards | §2.1's held-lease view, §2.2 whole, §2.3, the `no-lease` mode entry, `SessionRecord.duration_s`, `ui_panel_poll_ms` + env + systemd row, §2.6's one-line default flip | "lease create/renew refused when it would outlive the session"; "warning thresholds tested at both floors and both percentages"; "floors confirmed against the commissioned lease limits" |
| **G3b** runs, staging, energy, cancel | §2.1's staging record, §2.4 whole, §2.5, the `no-authority`/`protection-active` disabling of the run controls (GW-42's full statement becomes true here), D2's halves | "Double-submit starts one run"; "`no-response` reconciles via `run_find`"; "confirm states effect, values and target, and refuses at fire time when a trip arrives while armed"; "cancel and output-off are ungated with no lease and during a trip"; "manual start refused when the bound exceeds remaining lease or session time"; "dependency 7 resolved" |

Stacked (`base` = predecessor), merge bottom-up. Rationale for two, not three: the
energy-safety core (classification → arm → fire-time guards) and the start/cancel flow
are one mechanism — shipping a start control without its confirm (GW-52) would put a
temporarily §C.1-non-conforming surface on main between merges, which is worse than a
larger G3b. If the builder finds G3b heavy, the split is intra-PR commits (one
RED→GREEN per commit), not more PRs.

**Deferrals (each with its home):**

| id | deferred | home |
|---|---|---|
| G3-D1 | Binding enumeration for the staging selector (the interface has no list; today's selector is event-history refs + manual digest entry) | an interface issue raised upstream (tracker row on #304's exit note); reopen when the catalog gains a listing operation |
| G3-D2 | R-ENERGISE-1's "setpoint of a currently-energised output" clause at run granularity (needs live device state; not derivable from documents) | this record §9 R3; reopen when a sample-bearing observation read exists (the #369 carrier) |
| G3-D3 | A seam-side trip gate on `run_start` (today the seam accepts starts after an unreset trip; the UI guard is presentation-only) | tracker observation filed with this design; an interface/execution-standard question, not a UI one |
| G3-D4 | Cross-surface lease visibility (a lease taken via REST/MCP by the same principal is invisible to the browser session's held-lease view — conservative disable) | this record §2.1's disclosure; an interface lease-read operation would be the reopen trigger |
| G3-D5 | D7's manual theme override (re-deferred from G2's table — out of #304's scope and exit gate) | G4 (#305) design record, or an owner-called standalone UX slice |
| G3-D6 | Enforcement of `max_lease_ms` on `duration_ms` at the seam (published but unchecked today, §1) | tracker observation; a seam change, deliberately not smuggled into a UI increment |

## 4. Precedent (principle 9 — extend, don't invent)

| Piece | Proven mechanism extended |
|---|---|
| Control routes as one-operation translations over the seam | `ui_read.py`'s eight read pages (same closures, same `_failure_page`); `rest.py`'s three-step translation |
| Server-side session state beyond the identity record | the bridge registry in `SessionStore` (`sessions.py` — same lock, same death semantics: logout/expiry/restart) |
| Route registry + GW-10 checker; session-layer classification for non-interface state actions | `ui_routes.py::UI_ROUTES` + `route_mapping_violations` (the "complete non-interface set" assertion grows with the staging trio — disclosed, §8) |
| The no-response render + reconcile link | `ui_refusals.render_no_response` (G2b) — G3 wires it into the mutating handlers |
| The armed confirm with fire-time guard | the package's `ConfirmActionData(guard_reason, guard_label)` + the G1 proofs' guard-while-armed behaviour (already pinned in `tests/ui_html/` compositions) — G3 composes it host-side, the package does not move |
| Disabled reasons / mode banner / staged labels | `ButtonData`, `render_disabled_label`, `ModeBannerData`, §F `staged` — all existing |
| Server-chosen poll cadence on a fragment route | htmx polling on server-rendered attributes (the bridge's `data-bw-stream-*` / `data-*` composition precedent, minus the SSE channel) |
| Document-chain reads (binding → procedure/commissioning) | `run_check`'s own pin-walking and `_assert_run_runnable`'s digest-addressed resolution — the UI reads the same digests through `document_get`, never the store |
| Env-driven limits, fail-loud parse | `app_entry._LIMITS` / `_QUOTA_ENV_KEYS` (the `ui_*` G2a row is the direct precedent) |

**New architecture introduced: none.** The two session side tables are the smallest
mechanism satisfying GW-40/50 given §1's wire facts (no lease read; mutating responses
are the only lease surface), and they die with the session exactly as CON-15's store
does.

## 5. Root cause / why this shape

G2 proved the adapter pattern (session → seam → render) over reads. G3's real problem
is that the control half's *facts* are asymmetric on this wire: lease state exists only
in mutating responses, trip state only in events, run inputs only as document refs.
The design's load-bearing decision is therefore to keep every derived state server-side
and response-sourced (the held-lease view, the staging record) rather than client-side
or store-read — so every rendered byte is either a seam answer, a session-retained seam
answer, or a pure function over seam answers (`trip_active`, `expiry_warning`, the
energy classifier), and the seam's own authority checks are never bypassed, only
preceded by honest presentation guards. The one thing G3 must NOT do is invent a UI
route that reads the store for control facts — that is CON-5's line, and the §1 facts
make it unnecessary.

## 6. Measurable proof — pre-committed acceptance rule

Deterministic gates; counts from `--junitxml` attributes or TRUE exit codes;
`UV_PROJECT_ENVIRONMENT=venv` on every invocation; fast lane per commit, cold full
battery + both standards tripwires before each push. Test lattices are authored
in-test (temp fixture dirs through the bootstrap admission path) — **no `fixtures/`
motion, no digest-lattice obligation** — with three procedure shapes: manual +
enable-true (energy-sourcing), manual + explicit `enabled: false` (de-energising),
gateway_owned + commissioned unattended grant.

**A. GW-95 (G3a).** Injected clock. (A1) A duration that would outlive the session:
control disabled with the session expiry stated and the clearing action present;
direct POST refused pre-send — assert **no seam `lease_create` call** (spy) and the
rendered refusal. (A2) Renewal past the session bound: same. (A3) Boundary: a
duration ending exactly at session expiry is allowed (the post-sends and the seam
answers). **RED control:** delete the handler's bound → A1's no-call assertion fails.
SHIP iff A1–A3 hold.

**B. GW-44 thresholds (G3a).** The pure predicate, parametrised: at duration 6 h —
warn at 72 min remaining, critical at 18 min (percentages; floors inert); at 60 s —
warn from creation (floor dominates: max(12 s, 120 s) = 120 s ≥ duration), critical
from 30 s; at exactly 10 min — warn and floor coincide at 120 s (the #307-noted
coincidence); at 20 min — percentage (4 min) beats floor; at 2 min 1 s — floor (120 s)
beats percentage (24.02 s), the Q2 rationale's own case. Both severities render with
their §B.1 persistence classes; the lease warning names the safe-transition loss and
carries the renew action; the session warning (D1) names the login clearing action.
**RED control:** neutralize the floors (percentage-only) → the 60 s / 2 min 1 s arms
fail; neutralize the percentages → the 6 h arm fails (both directions prove the
mechanism discriminates). SHIP iff every arm holds.

**C. Floors vs the commissioned limit (G3a).** With §2.6 landed: the booted test
gateway's `gateway_info.limits.max_lease_ms == 21_600_000`; at that duration the B
arms show the floors inert (the sanity check #307's exit reading names). The default
flip commit's own arm: `app_entry._LIMITS` and `cli/demo.DEFAULT_LIMITS` both carry
21600000. SHIP iff both hold.

**D. Lease lifecycle (G3a).** Take → panel shows expiry/remaining/holder-as-principal;
a second take on the same bench renders the seam's `conflict` row (GW-11, no
softening); renew advances sequence in the held view; release clears it; the
`no-lease` banner entry is present before take and absent after (bench AND device
pages); observe sessions render every lease control disabled with `no-authority` and
the G2 observe-no-control pin stays green; expiry (injected clock past `expires_at`)
renders the expired state and re-fires GW-42's `no-lease` posture. **RED control:**
remove the mode computation → the banner-absence assertions fail. SHIP iff all hold.

**E. Double-submit (G3b).** Arm → two identical Confirm POSTs (same cookie, same
`request_id`): exactly one run exists in the store (count via the test gateway's
store), both responses carry the same `run_id`, the second is the §9 replay. A
resubmitted form after a `no-response` induction reuses the id (assert the POSTed
body). **RED control:** mint the request id per POST instead of per staging cycle →
the one-run assertion fails (two runs). SHIP iff both hold.

**F. No-response action half (G3b).** Boundary induction: a seam double raising
`RuntimeError` (no interface answer) on `run_start` → the response renders the
§C.3 `no-response` row, sent status `UNKNOWN`, and the reconcile link naming the
form's exact `request_id`; the link resolves to `/ui/requests/{id}` (G2b's view).
Labelled induced-not-emitted (the G2 §7-F honesty rule). **RED control:** remove the
handler's no-response path → a bare 500 renders and the row assertion fails. SHIP iff
it holds.

**G. Fire-time refusal, trip-while-armed (G3b).** Real induction where the harness
allows it: run the tripping procedure (monitoring-wrapper shape, WP05's own fixture
pattern) to terminal `tripped` so the `trip` event lands on the bench stream; belt
arm: a planted `trip` event row. Then Arm → trip → Confirm POST: assert **no seam
`run_start` call**, the armed state re-rendered with `data-bw-disabled-reason=
"protection-active"` and its visible label, no auto-disarm, Cancel enabled. Also:
combined trip + no-authority presents `protection-active` (§E.1's rule). **RED
control:** delete the fire-time guard → the no-call assertion fails (the seam call
happens). SHIP iff both inductions hold.

**H. Confirm content (G3b).** The armed fragment states the effect, the exact values
with units, and the target — composed from the documents (the fixture's
"5 V" / device+channel), asserted against the §E.1 armed-text shape ("`effect`:
`value unit` to `target`. Confirm to proceed."). A de-energising start renders NO
confirm pattern (one action). SHIP iff both hold.

**I. Ungated cancel and output-off (G3b).** With no session lease AND with trip
active: the cancel control renders enabled; a cancel POST reaches the seam
(owner session) and the run page renders "cancel requested" until `run_get` reports
terminal (injected-clock/worker-paced). The de-energising start renders enabled under
both states; without a lease its POST reaches the seam and the `policy_denied`
`manual_lease_required:` refusal renders through its own row (the UI did not gate
it). **RED control:** plant a `no-authority` disable on either control → the
enabled assertions fail. SHIP iff all hold.

**J. GW-56 (G3b).** Injected clock. Manual procedure, bound `max_body_ms +
max_protection_ms` > lease remaining (session longer): the Confirm POST is refused
pre-send — no seam call — rendering the bound, BOTH remaining times, and both
clearing actions. Session-shorter leg: same with the session the shorter one.
Boundary: bound exactly equal to the shorter remainder is allowed (post sends; the
seam decides). With the commissioned-grant lattice, the refusal names gateway-owned
mode. Gateway-owned + grant + no lease: the start is NOT refused by this guard
(lease_id null; the seam's grant gate decides). **RED control:** delete the guard →
the no-call assertions fail. SHIP iff every arm holds.

**K. Route mapping (G3a+b).** The mounted enumeration matches `UI_ROUTES` exactly:
six new interface rows (one mutating operation each), the staging
arm/disarm/stage trio + the controls fragment GET in the non-interface set, the
"complete non-interface set" assertion grown to name them. Planted-route arms
re-proven. SHIP iff violations == ∅ on the real app and non-empty on both plants.

**L. Browser lane.** The G2 lane's pattern extended: the bench page with the control
region (both lease states, armed confirm, both disabled reasons) and the run page
with cancel — axe WCAG 2.2 AA in both themes; the planted-violation control applies;
obligation 26's CSS pins (24 px targets) assert on the new controls. SHIP iff clean.

**Ship it if** A–L all hold on the implementing run with outputs recorded and each
slice's battery is green before its push. **Kill it if** any RED control stays green
(the tests police nothing), any pre-send guard lets a seam call through where the
design says no-call (E/F/G/J), or the double-submit arm ever yields two runs.
**Underpowered, not conclusive:** Playwright/browser-environment failures (fix and
re-run; no verdict before a clean lane run); Windows-leg flakes (evidence posture,
record on #207); the trip harness's real-induction arm may fall back to the planted
event only if the wrapper shape proves unavailable in the test lattice — disclosed in
the PR body, never silent.

## 7. Invariant and drift impact

- **CTL/STO/REG: untouched.** No `control/`, `state/` or `registry/` bytes move; G3
  adds no protective behaviour — its fire-time guards are presentation (§C.1's own
  scope), and the seam's checks are unchanged and remain authoritative. A04 is
  honoured structurally: nothing in G3 needs an AI or a live client; the dead-man's
  switch is untouched (no background renewal — there is no renewal code at all
  outside the operator's POST; no session extension; no retry of an expired renewal
  — the seam already refuses late renewal and the UI renders the row).
- **CON-5 amendment (proposed, lands with G3b):** the G2 UI-adapter amendment gains:
  *the `/ui` control routes are one-operation translations over the same seam
  (GW-10's fixed eight; six in G3); session-side staging and held-lease state are
  presentation of this session's own seam responses — never an authority source, with
  every mutating POST re-validated by the seam; energy-removing actions render
  ungated and unconfirmed (§C.1 R-DEENERGISE-1), and the armed confirm re-evaluates
  its guards server-side at fire time (R-PROTECT-1) — `src/benchweave/interfaces/
  ui_control.py`.*
- **CON-15: unchanged in substance** — the new side tables are not identity facts;
  they inherit the store's death semantics (logout/expiry/restart) by construction.
- **On-disk formats/schemas: none.** No `standards/` bytes, no store schema, no
  package motion (ui-html untouched — G3 composes existing partials; if a review
  lane finds a package gap, that is a finding, not a silent bump). `uv.lock` does not
  move. The standards tripwires run before every push of both slices.
- **Obligations:** 4 (operator-guide + README: the control surface — taking/renewing/
  releasing leases, the 6-hour default, staging and check, the confirm step, cancel;
  ASD-STE via the `document-writer` agent for the operator-facing legs); 9 (the
  systemd env example gains `BENCHWEAVE_UI_PANEL_POLL_MS`); 12 (no motion — the row
  is walked and its no-motion stated); 23 (no new CLI — `ui-login`'s rows already
  landed with G2a); the drift-guard hook reminders fire as usual.
- **CI cost:** `gates` grows the two `tests/interfaces_ui/` suites (no new markers);
  `browser` grows the control-region pages (the lane stays serialized); `windows`
  inherits by selection (evidence posture); `timing` untouched (no real-clock bounds
  — all clocks injected); `package` unaffected (no packaging change).

## 8. Review tier (Step-1, rubric #254) and keyword scan

**Tier 3 — maximum across both slices**, by the keyword rule first (the diff text
carries `protection` and `sha256` by construction), independently re-inforced by the
path rules' spirit (a new network-served mutating surface over the control seam).
Consequences: the two-lane adversarial refute per slice and the cold full battery.
The standards-governor mandate does NOT fire: no `standards/` bytes, no vendored
tree, no version strings (the 6-hour figure is a gateway limit default, not a
standards version).

Keyword scan over the expected diff text (new `ui_control.py`, `sessions.py` and
`ui_read.py` additions, `ui_routes.py` rows, `app_entry.py`/`cli/demo.py` one-liners,
new/changed `ui_templates/*.j2`, new `tests/interfaces_ui/` suites, operator-guide +
README + systemd rows, and this record — docs and code alike; estimates re-derived
over the real diff at each review):

| keyword | expected count | where |
|---|---|---|
| `protection` | ~30 | trip/protection-active wiring + tests (~18), record + docs (~12) |
| `sha256` | ~12 | binding refs and armed-text digests in code/tests (~8), record (~4) |
| `hashlib` | ~2 | tests (staging-set digests), if used; 0 acceptable |
| `threading` | ~1 | record prose only (the sessions lock context) |
| `asyncio` | 0 | — (the bridge is untouched) |
| `subprocess` | 0 | — |
| `migrate` | 0 | — |
| `recovery` | ~2 | record prose only |

## 9. Top risks, each with its falsifier

- **R1 — the trip predicate errs clear.** A configuration activation after a trip
  emits `bench_changed` and clears protection-active while a physical trip persists
  (§2.5b); the seam itself has no trip gate, so the presentation guard is the only
  one. Falsifier/mitigation: the predicate's unit matrix pins the exact class;
  G3-D3 files the seam gap; until an interface change names resets on the wire, the
  disclosure stands. If the owner judges the err-clear direction intolerable, the
  fallback (protection-active persists until ANY admin change is observed *and* a
  page-level note says why) is one predicate line — an owner fork, not a redesign.
- **R2 — the held-lease view goes stale and the page lies.** Another surface
  renews/releases the session's lease; the view's sequence/expiry lag. Mitigation:
  every POST carries the view's `sequence` — the seam's `conflict` (stale sequence)
  or `not_found` (released/expired) refusal renders honestly, and the failure path
  clears the view; the poll fragment re-derives remaining from the stored expiry.
  Falsifier: an acceptance arm where a seam refusal must clear the stale view (D's
  conflict arm).
- **R3 — the energy classifier under-covers.** The enable-true rule misses a
  setpoint-raise on an already-energised output (G3-D2) and any energising action an
  author encodes without `enabled: true`. Mitigation: disclosed; the confirm is
  additive friction whose absence never widens seam authority (the seam's checks are
  unchanged); the classifier errs toward MORE confirmation only by rule change, not
  silently.
- **R4 — the staging selector's UX is thin** (event-history refs + digest entry).
  Accepted: the interface has no enumeration, and inventing a UI-private list route
  would breach the PRD's own headline 4. Falsifier for the deferral: an operator
  unable to reach a binding through any G3 surface — then the interface issue
  (G3-D1) becomes blocking.
- **R5 — the poll fragment adds load.** N sessions × one GET per 30 s (5 s/1 s
  inside warnings) — bounded reads, D13's disclosed single-loop posture, far under
  the bridge's own per-tick cost. Falsifier: the lane's load arm showing material
  movement (then the knob, not the code, is the fix).
- **R6 — the 6-hour default flip breaks suite assumptions.** Tests asserting
  600000 or leasing behaviour at 10 min. Mitigation: the flip is its own commit
  (§2.6) with the fast lane; any broken arm is fixed in the same commit, and the
  boundary tests re-derive from `gateway_info` rather than literals.

## 10. Maintainer decisions (forks, not blockers)

- **F1 (R1):** accept the trip predicate's err-clear-on-admin-change boundary as
  disclosed, or take the always-persist fallback until the wire can name resets.
- **F2:** the staging selector's shape (event-history + manual digest) — acceptable
  for G3, or fund the interface listing operation first (G3-D1).
- **F3:** `ui_panel_poll_ms` default 30 000 and the ÷6/÷30 escalation tiers —
  service knob defaults, owner-tunable; objection means different numbers, not a
  different mechanism.
