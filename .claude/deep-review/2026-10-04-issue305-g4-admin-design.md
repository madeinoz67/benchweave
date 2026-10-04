# G4 design — administration: change submit, review, apply (issue #305, PRD 12)

**Verdict: BUILD, one slice.** Triage call: mechanisms, issue numbers and code paths
only — no person, client, bench, serial or install detail — public path as named.

**Evidence baseline:** gateway `origin/main` `b3f1fba` (2026-10-04, fetched this
session; carries merged G3a + G3b — the lease control region, the staging panel, the
fire-time guards, and `ui_staging.py`). Trigger state verified: #304 merged (#390 its
G3b PR); no open PR on the gateway repo touches the planned paths; the sibling repo's
in-flight lanes (I3, #226 registry) touch neither `interfaces/` UI surfaces nor
`ui_routes.py`. All code reads below were taken from the worktree bytes at `b3f1fba`
(design-session note: the gortex daemon served one stale view for this repo during
premise reads — `ui_routes.py` without the G3b rows — caught by content-identity
against `git grep`; every load-bearing fact below is re-verified against the worktree).

## 1. Premise check (verified, not assumed — every load-bearing fact with its anchor)

- **The three change operations are exactly as the PRD names them, and REST-only.**
  `change_submit` (`operations.py:1025`), `change_apply` (`operations.py:1090`),
  `change_get` (`operations.py:1195`); `mcp_tool: null` in all three catalog entries
  (`standards/interface/0.1.0/operation-catalog.json`) — the UI is the second surface
  for this family, after REST.
- **Submit is §9-idempotent; apply is NOT — the two-phase state is apply's replay
  answer.** `change_submit` keys `scoped_request_key(principal, "change_submit",
  request_id)` (`operations.py:1052`) with a body digest over the five-field candidate;
  a replay returns the original change projection, same-key-different-body is
  `conflict` (`test_seam_admin.py:149`). `change_apply` has **no** `accept_request`
  call — its `request_id` rides the dispatch only; a double-apply is answered by the
  state machine (`state != proposed` → `conflict`). The UI's GW-13 duty on apply is
  therefore a fixed form `request_id` plus honest rendering of that conflict — nothing
  else is available, and nothing else is needed (a second apply of an applied change
  is a decided refusal, never a second effect).
- **The independence check is at the seam and only at the seam:**
  `approver.principal == identity.principal` → `forbidden` "approval must be
  authenticated by a principal other than the applier" (`operations.py:1135-1141`).
  The approval is TWO things that must agree (`verify_approval`,
  `operations.py:1201-1272`): a stored, sha-pinned document
  `{change_id, expected_generation, approver_principal, policy_version}` (schema id
  `urn:stg:approval`) and a detached HMAC token (audience `gateway-admin`, scope
  `stg:admin`) naming the same principal. Missing token → `forbidden`
  (`missing_token`); malformed/bad-signature/expired → `unauthenticated`; wrong
  audience/scope → `forbidden`; wrong change+generation binding → `forbidden`.
- **The change projection carries NO approver.** `_change_projection`
  (`operations.py:1494`) is closed at ten fields (`change_id, bench_id, kind,
  target_ref, expected_generation, reason, state, reasons, created_at, updated_at`).
  The approver is knowable only by reading the approval document — which
  `document_get` serves to any `observe` scope (`operations.py:411`, returns `content`
  + original bytes). GW-71's presentation check is therefore *derivable* through the
  interface once the approval digest is known: read the document, compare
  `approver_principal` with the session's principal and the `change_id`/`
  `expected_generation` binding with the change record.
- **`run_find` cannot reconcile a change request.** It keys
  `scoped_request_key(principal, "run_start", request_id)` (`operations.py:744`) —
  change keys are invisible to it. `render_no_response`'s reconcile link
  (`ui_refusals.py:179`) is run-shaped by construction; GW-12's change half needs its
  own reconcile action (§2.5).
- **The seam implements NO inhibition on failed/unknown changes.** The contract says
  "A failed or uncertain application leaves an explicit failed/unknown change record
  and inhibits affected control until reconciled"
  (`standards/interface/0.1.0/interface-contract.md:88`); in the code, nothing outside
  the apply path consults change state (`_assert_run_runnable` at `operations.py:1713`
  never reads the changes table) and the store has **no per-bench change enumeration
  at all** — `get_change` by id only (`store.py:874`). GW-72's rendering is therefore
  presentation-level over records the session can name — the same posture as G3's trip
  predicate (G3 §2.5, G3-D3), with the seam gap filed as an observation (§3).
- **Change states are `proposed → applied | failed | unknown`, all terminal after the
  first decided outcome.** `_record_change_outcome` (`operations.py:1485`) never
  overwrites `applied`; a `failed`/`unknown` change can never re-enter `proposed`, so
  re-apply is structurally impossible and the seam's retry advice is `never` —
  reconciliation is "change_get, then a NEW change if warranted" (the D13
  retry-honesty comment at `operations.py:1174`).
- **The kinds and their target refs.** `CHANGE_KINDS = {package_admission,
  configuration_activation, trip_reset}` (`operations.py:295`). The catalog pins
  `target_ref` to `{id, version, sha256(64-hex)}` for all kinds. Per-kind apply checks:
  `trip_reset` refuses a tripped bench projection (`_apply_trip_reset`,
  `operations.py:1320` — currently always passes, `tripped` hardcoded `False`, the
  disclosed PoC boundary); `configuration_activation` refuses a live lease (`not_idle`)
  and requires a registry session (`_apply_configuration_activation`,
  `operations.py:1337`); `package_admission` requires a registry session
  (`operations.py:1386`). Successful apply bumps the bench generation, refreshes the
  bench row, marks `applied`, emits the kind's event (`_dispatch_change`,
  `operations.py:1274`).
- **No operator surface mints approvals today.** The seam, REST and MCP expose
  submit/apply/get; the approval document + detached token are constructed out of band
  (tests build them directly against the content store and `identity.issue`
  (`test_seam_admin.py:83-128`); the CLI has no change, approval or admin-token
  command — `cli/commands.py` carries only `ui-login` in that region). This is an
  honest gap in the operator flow, not something the applier's UI can or should close:
  the gateway minting the approval for the applier would defeat the independence the
  two-phase design exists to enforce. Deferred with a home (§3, G4-D3).
- **The G2/G3 substrate this extends** (all at `b3f1fba`): the mounted `/ui` sub-app
  with its four omittable guards (`ui.py`); `SessionStore` side tables under one lock
  with logout/expiry/restart death semantics (`sessions.py:230-316` — held-lease view,
  staged start, pending-cancel marker: the exact shapes a change index copies); the
  route registry `UI_ROUTES` + `route_mapping_violations` where GW-10's one-operation
  rule fires for interface-classified mutating routes and the "complete non-interface
  set" assertion lives in `test_ui_route_mapping.py:108`; the §C.3 row table +
  `render_no_response` (`ui_refusals.py`); `_failure_page`'s page-and-fragment refusal
  rendering (`ui.py:574`); the Python-composed control-region fragment with
  escaped-interpolable helpers (`ui_control.py:274-664`); the bench page composing
  `controls_html` (`ui_templates/bench.j2:13`); the in-fragment scope check
  `record.scopes & TIER_SATISFIES[...]` (`ui_control.py:372`); `bench_get` carrying
  `generation` and the configuration ref (`operations.py:591`,
  `bench.j2:6,10`).
- **§C.2's disabled-reason enum is closed at five keys** (`ui-contract.md` §C.2:
  `capability-absent, device-state, protection-active, invalid-staged-input,
  no-authority`), machine-pinned by the harness — a new key would be a contract change
  and a package bump. G4 needs no new key: permission-absence and self-approval are
  both authority facts and §C.2's own note says `no-authority` "absorbs the reference
  renderer's earlier permission-disabled story state" (`ui-contract.md:209`).
  §B.1's `critical` row (persistent-until-resolved, `alert` region) is the inhibited
  state's persistence class.
- **Drift finding carried into this slice: the G3 CON-5 control amendment never
  landed.** The G3 record §7 proposed it "lands with G3b"; `docs/internal/
  invariants.md` carries only the G2 amendment (zero hits for `ui_control`). G4 folds
  both texts (§7) — one docs row, its own commit.
- **D7's ground truth:** the theme CSS keys on `[data-theme="light|dark"]` with `:root`
  defaulting to light (`packages/ui-html/.../themes.css:1-31`); the live gateway sets
  no attribute anywhere (`base.j2` has no theme hook, `bw-host.js` no toggle) — the
  gateway serves light-only today; both themes exist only in the pattern library and
  the harness. A manual toggle is host-or-package machinery (§3's D7 ruling).

## 2. The mechanism

All administration flows through interface 0.1.0 operations only. New surface: one
module (`src/benchweave/interfaces/ui_admin.py`, registered before the catch-all by
the same `register_*_routes` closure pattern `ui_control.py` set), one session side
table, five route rows, two small templates, two no-response variants. **Zero package
motion, zero seam motion, zero `standards/` motion.**

### 2.1 The session's change index (the one new state home)

`SessionStore` gains `session_id -> {change_id -> ChangeView}` under its existing
lock, mirroring the staged-start shape: `ChangeView = {bench_id, acknowledged: bool}`
— **an index, not a state cache**. It records which changes this session submitted or
attempted to apply; every rendered STATE comes from a fresh `change_get` at render
time, never from the index (the G3 stale-view lesson taken structurally: the failure
class is deleted, not mitigated). Death semantics identical to every other side table
(logout, expiry sweep, restart). Honest boundary, disclosed: changes filed by other
sessions or surfaces are invisible to the index — the bench page shows only this
session's changes, and the change page accepts a manually entered change id (the
G3-D1 selector shape: the interface has no listing operation, and G4 does not invent
one).

### 2.2 The admin region on the bench page (GW-70's submit half)

The bench page gains an **administration region** below the control region —
server-rendered at page render (not inside the polled controls fragment: change state
is not live data and does not deserve the poll budget; the region re-renders as the
response of its own POSTs, htmx-swapped into place, `responseHandling` already
configured for the fragment-vs-page refusal shapes). Composition:

- **Submit form** (admin sessions): `kind` select over `CHANGE_KINDS`; `target_ref`
  as three fields (`id`, `version`, `sha256` — 64-hex pattern-validated at render,
  the seam validates authoritatively); `expected_generation` prefilled from the
  `bench_get` the page already made; `reason` (min length 1); the server-minted fixed
  `request_id` (`"ui-" + uuid4().hex[:12]`, pattern-legal — the GW-13 rule; resubmit
  after any refusal reuses it, so §9 makes the retry return the original change).
  For `trip_reset` the target prefills from the bench's own configuration ref
  (`bench_get.configuration`); for the registry kinds it is manual entry (no
  enumeration exists — §3 G4-D5).
- **Non-admin sessions** (observe or control scope): every control in the region
  renders disabled with §C.2 `no-authority` (the absorbing key, the G2
  observe-no-control precedent); a forged/direct POST reaches the seam and its
  `forbidden` row renders through `_failure_page` — the honest authority answer, no
  UI gate pretends to be the authority.
- **This session's changes** (from the index, state freshly read): a row per change —
  id, kind, state, a link to the review page.
- **The inhibited-state alert** (§2.4).

`POST /ui/benches/{bench_id}/changes` → `change_submit(identity, request_id,
bench_id, kind, target_ref, expected_generation, reason)`. Success renders the region
with the new change's review link and the two-phase statement (US8: the page says the
change **needs independent approval** and names who can give it — a principal other
than any applier). Refusals render through their §C.3 rows; a `conflict` on resubmit
with a different body is shown as the stale-view answer it is.

### 2.3 The review page and the apply flow (GW-70's review/apply halves, GW-71)

`GET /ui/changes/{change_id}` → `change_get` (the route row also names `document_get`
— read pages compose their reads, the bench-page precedent). The page renders the
full ten-field record — the explicit failed/unknown record GW-72's first half demands
is this page with `state=failed|unknown` and `reasons[0]` shown verbatim. For
`state=proposed` and an admin session, the apply workspace renders as a three-step
flow — the staging panel's load→check→fire shape, one gate earlier:

1. **Load the approval** — `POST /ui/changes/{change_id}/approval` (session-layer;
   composes `document_get(sha256)`, no seam write — the staging trio's registry
   classification). The operator pastes the approval digest (and its `id`/`version`,
   which the catalog requires in `approval_ref`); the handler reads the document,
   records `{sha256, id, version, approver_principal, binds}` in the change view, and
   re-renders the workspace showing what the approval actually says: bound change,
   generation, **approver principal**, policy version — with a link to the existing
   document page (`/ui/documents/{sha256}`) for the full view. An unstored digest
   renders the seam's own `not_found` row wording (the honest answer to a digest the
   gateway does not hold).
2. **GW-71's presentation check, at offer time** — with a loaded approval that binds
   the change: if `approver_principal == session.principal`, the apply control is
   **not offered**: it renders disabled with `data-bw-disabled-reason="no-authority"`
   and visible text naming the rule (independent approval — a principal other than
   the applier must have authenticated the approval; the gateway refuses self-approval
   and the UI does not offer what the gateway would refuse). If the approval does not
   bind (`change_id` or `expected_generation` mismatch): not offered, with the
   non-binding reason shown. Only a binding approval naming a different principal
   offers the apply control.
3. **Apply** — `POST /ui/changes/{change_id}/apply` → `change_apply(identity,
   request_id, change_id, expected_generation, approval_ref, approver_token)`. The
   form carries the approver's detached token (pasted; a field that is never rendered
   back — no echo in any response byte, pinned by an arm). `expected_generation` and
   the `approval_ref` come from the change view and the loaded approval — server-side
   truth, not editable fields. **Fire-time re-evaluation** (the G3 armed-confirm
   rule, copied): the handler re-reads the approval document fresh (content-addressed
   and immutable — no TOCTOU by construction) and re-checks binding and
   non-self-approval; on violation it refuses **pre-send** (no `change_apply` call —
   spy-asserted) rendering the same refusal shape. The seam's checks stay
   authoritative; this guard only stops the UI from sending what it can already see
   the gateway will refuse (GW-71's own sentence).
4. **Success (US9)** — the apply response is the change projection (`state=applied`);
   the handler re-reads `bench_get` and renders the generation increment
   ("generation N → N+1") beside the applied record.

### 2.4 GW-72: the failed/unknown record and the inhibited state

`change_apply`'s failure modes are the wire's own vocabulary and the UI renders them
without invention: decided refusals carry the §C.3 row (the seam has already recorded
`failed` with the refusal message as the reason); the undecided crash carries
`unavailable` (retry `never`) with the change recorded `unknown`. After any
seam-answered refusal from the apply path, the handler re-reads `change_get` and
records the change in the session index — the state rendered is the record's, never
inferred from the refusal. **Pre-send UI refusals (GW-71's guard, form validation)
record nothing** — the seam never judged, so no outcome exists to present.

The inhibited-control state, presentation-level and disclosed as such (§1: the seam
implements no inhibition):

- **The alert** — while any indexed change for the bench reads `failed` or `unknown`
  from a fresh `change_get` and is unacknowledged, the bench page's admin region (and
  the change page) renders a §B.1 `critical` alert-bubble — persistent-until-resolved,
  `alert` region — naming the change id, the state, `reasons[0]` verbatim, linking
  the change page, and stating the reconciliation route in the contract's own terms:
  read the record, then file a NEW change if warranted; never re-apply this one.
- **The disable** — while that condition holds, the region's apply controls (on any
  proposed change of that bench) render disabled with `no-authority`, the alert
  naming the blocking change. **Submit stays enabled** — filing a new change is the
  contract's own reconciliation path; disabling it would block the correction route.
  Run controls are NOT disabled by this state: the wire carries no fact tying a
  failed administrative change to run authority, and the UI does not invent one
  (§9 R1 prices the alternative).
- **Reconciliation** — `POST /ui/changes/{change_id}/acknowledgements`
  (session-layer, no seam call): the operator, having read the record, marks it
  acknowledged; the alert clears and the disables lift. The gateway record never
  changes — there is no operation to mark a change reconciled, and the
  acknowledgement is per-session presentation (a fresh session re-sees the alert over
  the same terminal record: honest, disclosed, §9 R4).

### 2.5 GW-12's change halves (the no-response variants)

`render_no_response(request_id)` stays byte-identical (its wording is suite-pinned);
two additive variants in `ui_refusals.py` compose the same §C.3 row with the
change-honest reconcile action:

- **Submit** — `render_no_response_change_submit(request_id)`: reconcile = resubmit
  the identical form. §9 makes this safe by construction (same principal, same
  operation key, same body digest → the original change returns; a different body →
  `conflict`). The run_find link would be a lie here (§1: change keys are invisible
  to it).
- **Apply** — `render_no_response_change_apply(change_id)`: reconcile = the change
  page link (`change_get` shows the outcome the apply left behind — proposed, applied,
  failed or unknown). No retry action: the seam's advice is `never` (D13).

Both fire only on non-`OperationFailure` failures of the seam call — an in-process
adapter cannot honestly produce one; the suite induces it at the boundary (the
G2 §7-F posture, G3's F-arm precedent).

### 2.6 Route set (GW-10's registry)

| path | method | operations | classification |
|---|---|---|---|
| `/benches/{bench_id}/changes` | POST | `change_submit` | interface (mutating, one op) |
| `/changes/{change_id}` | GET | `change_get`, `document_get` | interface |
| `/changes/{change_id}/apply` | POST | `change_apply` | interface (mutating, one op) |
| `/changes/{change_id}/approval` | POST | — | session (composes a `document_get` read; the staging trio's shape) |
| `/changes/{change_id}/acknowledgements` | POST | — | session (no seam call) |

`UI_ROUTES` grows the five rows; the mounted-enumeration suite and the "complete
non-interface set" assertion (`test_ui_route_mapping.py:108`) grow with them; the
planted-route arms re-prove the checker. The mutating vocabulary stays exactly
GW-10's eight — G4 mounts the last two.

## 3. Slice plan, deferrals, and the D7 ruling

**One slice (G4), intra-PR commits** (RED→GREEN each, the G3 record's own heavy-slice
rule): (1) the change index + its suite; (2) submit + review page + the submit
no-response variant + route rows; (3) approval load + apply + the GW-71 guards; (4)
the GW-72 alert + acknowledge + the apply no-response variant; (5) the browser lane +
docs + the CON-5 fold. Why not two PRs: submit-without-apply would ship a review page
whose only actionable answer is "come back later" — a temporarily dishonest
workspace; the whole flow is one mechanism of comparable size to one G3 slice.

**Deferrals (each with its home):**

| id | deferred | home |
|---|---|---|
| G4-D1 | The seam-side inhibition the contract names (§1: nothing refuses runs or applies on a bench with a failed/unknown change) — GW-72's rendering is presentation-only | tracker observation filed with this design (the G3-D3 shape); an interface/execution-standards question, reopened when the seam grows a gate |
| G4-D2 | Per-bench change enumeration (no listing operation exists; discovery is the session index + manual change-id entry) | an interface issue raised upstream (G3-D1's twin); the reopen trigger is a listing operation in the catalog |
| G4-D3 | An approval-minting CLI for the approver (today approvals are constructed out of band; the gateway must not mint the applier's approval, but an approver-side helper holding the issuer secret is legitimate) | owner fork (§10 F2) — a CLI increment, carrying obligations 4 and 22 (the counter-twins row), deliberately not smuggled into a UI slice |
| G4-D4 | Target-ref discovery for the registry kinds (manual `{id, version, sha256}` entry; no package enumeration on the change path) | rides G4-D2's interface issue; the staging selector's event-history pattern is NOT reused here because `authority_changed` evidence pins bindings, not packages |
| G4-D5 | **D7, the manual theme toggle — re-deferred, third and final convenience deferral refused: this record pins a trigger.** Grounds: no GW row and no exit-gate clause names it; the live gateway's light-only rendering is the status quo both PRD hosts share; a toggle is package-or-cookie machinery (`bw-host.js` or a server-read preference cookie + a `data-theme` hook in `base.j2`) — a different review surface (package/CSP/a11y lane) welded onto an administration slice for zero G4 value | a standalone UX issue the builder files at G4 landing; trigger = the first operator request for dark rendering on a live host, or PRD 11's standalone host adding its own toggle — whichever comes first lands the shared mechanism in the package once and both hosts take it |

## 4. Precedent (principle 9 — extend, don't invent)

| Piece | Proven mechanism extended |
|---|---|
| Admin routes as one-operation translations over the seam | `ui_control.py`'s lease/run routes (same closures, same `_failure_page`, same fragment responses) |
| Session side table with index semantics | the staged-start record (`sessions.py:269`) — minus its cached check result: G4 caches nothing state-shaped (§2.1) |
| Load→check→fire with a pre-send guard | the staging panel's stage/arm/confirm trio (`ui_staging.py`); the fire-time re-read is the armed-confirm guard rule (`ui_control.py:632`) |
| Refusal rendering, page and fragment | `_failure_page` (`ui.py:574`) and the §C.3 row table (`ui_refusals.py`) — untouched, reused |
| The no-response render with a tailored reconcile | `render_no_response` (`ui_refusals.py:179`) — additive variants only |
| Route registry + non-interface set | `UI_ROUTES` + `route_mapping_violations` + the planted arms (`ui_routes.py`, `test_ui_route_mapping.py`) |
| Read page composing multiple reads | the bench page's three-op row (`ui_routes.py`) |
| Disabled-with-reason for permission absence | the observe-tier treatment + §C.2's `no-authority` absorbing note |
| Server-minted fixed request id on a mutating form | the staging cycle's `request_id` (GW-13's G3b landing) |
| Committed design record as the acceptance pre-commitment | this file (`.claude/deep-review/README.md` convention) |

**New architecture introduced: none.** The change index is the smallest mechanism
satisfying GW-72's persistence given §1's wire facts (no enumeration, no reconciled
flag on the record); it dies with the session exactly as CON-15's store does.

## 5. Root cause / why this shape

G2 proved the adapter over reads; G3 proved it over control with response-sourced
session views and pre-send guards. G4's real problem is that the administration
flow's *trust structure* lives entirely in the approval pair (document + token) that
the applier supplies — the wire carries no approver anywhere else (§1). The design's
load-bearing decision is therefore to make the approval **visible before it is
spent**: the UI reads the approval document through the interface and renders what
it binds and to whom, so GW-71's "not offered" is a fact the operator can see
(approver principal displayed), not a refusal that arrives after a paste-and-pray
POST — and the fire-time re-read keeps the check honest against whatever is actually
in the store at send time. Everything else is the G3 pattern applied verbatim: seam
authoritative, session state presentation-only, every refusal its own row, ambiguity
kept ambiguous (an `unknown` change renders as unknown, with the record's own words).

## 6. Measurable proof — pre-committed acceptance rule

Deterministic gates; counts from `--junitxml` attributes or TRUE exit codes;
`UV_PROJECT_ENVIRONMENT=venv` on every invocation; fast lane per commit, cold full
battery + both standards tripwires before push. Test lattices authored in-test
(temp fixture dirs through the bootstrap admission path) plus `test_seam_admin.py`'s
approval-construction helpers (`_put_approval` lifted to the shared UI support
module) — **no `fixtures/` motion, no digest-lattice obligation**.

**A. Submit + review (GW-70).** Admin session submits a `trip_reset` (target
prefilled from the bench configuration; generation from `bench_get`): the response
region renders the change record (`state=proposed`), its review link, and the
independent-approval statement; the store holds **exactly one** change row. Resubmit
the same form (double-click shape): the same `change_id` returns, still one row (§9).
Same `request_id`, different body: the `conflict` row renders (GW-11, no softening).
Review page renders all ten projection fields. RED control: mint the request id per
POST → the one-row assertion fails (two rows). Non-admin session: every admin control
disabled with `no-authority`; a forged POST renders the seam's `forbidden` row.
SHIP iff all arms hold.

**B. Self-approval not offered (GW-71 — exit-gate clause 1).** With a stored
approval that binds the change and names the SESSION's own principal: the
approval-load response displays the approver principal, and the apply control
renders disabled `data-bw-disabled-reason="no-authority"` with the independence
text; a direct forged apply POST is refused **pre-send** — spy asserts **no
`change_apply` call** — rendering the same refusal. With a binding approval naming a
different principal: the apply control is offered and the seam path is exercised
end-to-end (the seam's own independence check re-proven by the existing seam suite;
an arm where a second principal's session applies successfully — generation bump
rendered, US9). With a non-binding approval (wrong change id, wrong generation):
not offered, the non-binding reason shown, and a forged POST also refused pre-send.
RED control: delete the fire-time re-check → the no-call assertions fail. SHIP iff
every arm holds.

**C. Failed apply renders the inhibited state until reconciled (GW-72 — exit-gate
clause 2).** (C1) Decided failure: a `configuration_activation` on a bench holding a
live lease (valid approval, different principal) → the seam refuses `not_ready`, the
change records `failed`; the change page renders the explicit record with
`reasons[0]` verbatim; the bench admin region renders the §B.1 `critical`
persistent alert naming the change; the region's apply controls render disabled
`no-authority`; submit stays enabled. Acknowledge → the alert clears, the disables
lift. Page reload before acknowledgement → the alert persists (server-side session).
(C2) Unknown: a seam double raising inside the dispatch (the suite's induced-crash
posture) → the `unavailable` row renders, the change reads `unknown`, the same
alert/disable/acknowledge arms hold, and the rendered guidance names the contract's
route (a NEW change if warranted; never re-apply). (C3) State sourcing: mutate the
store row's state between renders — the rendered state follows `change_get`, never
the index (the index-caches-nothing rule). RED control: remove the alert computation
→ the alert-absence assertions fail; remove the disable → the disabled assertions
fail. SHIP iff C1–C3 hold.

**D. The no-response variants (GW-12's change halves).** Induced non-`OperationFailure`
on the submit call: the §C.3 `no-response` row, sent status `UNKNOWN`, reconcile
action = resubmit-the-same-form (and NOT the run_find link — asserted by its
absence); performing that resubmit returns the original change (A's §9 arm reused).
Same induction on the apply call: the row plus the change-page link; no retry
action. The approver-token field appears in no response byte (grep the rendered
fragments). RED control: remove a handler's no-response path → a bare 500 renders
and the row assertion fails. SHIP iff both halves hold.

**E. Route mapping.** Mounted enumeration == `UI_ROUTES` exactly: five new rows
(the two mutating rows one operation each, inside GW-10's eight), the non-interface
set assertion grown to name the approval and acknowledgement routes, planted-route
arms re-proven (violations == ∅ on the real app, non-empty on both plants).

**F. Browser lane.** The bench admin region (admin and non-admin sessions) and the
change page (proposed with a loaded approval, self-approval, failed, unknown) — axe
WCAG 2.2 AA in both themes; obligation 26's CSS pins (24 px targets) on the new
controls; the planted-violation control applies. SHIP iff clean.

**G. Obligations and the CON-5 fold.** Operator guide gains the administration
section (submit, the approval pair's out-of-band reality, apply, the failed/unknown
posture — ASD-STE via the `document-writer` agent); README's UI section gains the
admin flow row; `invariants.md` CON-5 gains the G4 amendment text alongside the
unlanded G3 control amendment (§7); obligations 4, 12 (walked, no motion — no
package bytes), 23 (no new CLI) checked and their no-motion stated.

**Ship it if** A–G all hold on the implementing run with outputs recorded and the
battery green before push. **Kill it if** any RED control stays green (the tests
police nothing), any pre-send guard lets a `change_apply` call through where the
design says no-call (B), the double-submit arm ever yields two change rows (A), or
self-approval is ever offered (B). **Underpowered, not conclusive:**
browser-environment failures (fix and re-run; no verdict before a clean lane run);
Windows-leg flakes (evidence posture, record on #207); the induced-crash arm may
fall back to the seam-double shape only (disclosed in the PR body, never silent).

## 7. Invariant and drift impact

- **CTL/STO/REG: untouched.** No `control/`, `state/` or `registry/` bytes move; no
  seam behavior changes; the §C.2/§B.1 vocabulary used is the closed existing set.
  A04 honoured structurally: nothing in G4 needs an AI or a live client, and the
  independence architecture is preserved verbatim — the UI cannot mint, soften or
  substitute an approval (GW-71 is presentation-only and the seam re-judges every
  apply; §1's `verify_approval` ordering is unchanged).
- **CON-5 amendment (proposed, lands with G4 — folding the unlanded G3 text):** the
  G2 UI-adapter amendment gains: *the `/ui` control and administration routes are
  one-operation translations over the same seam (GW-10's fixed eight — G3 mounted
  six, G4 the last two); session-side staging, held-lease and change-index state are
  presentation of this session's own seam responses and never an authority source,
  with every mutating POST re-validated by the seam; energy-removing actions render
  ungated and unconfirmed (§C.1 R-DEENERGISE-1); the armed confirm and the
  administrative apply re-evaluate their guards server-side at fire time
  (R-PROTECT-1; GW-71) — `src/benchweave/interfaces/ui_control.py`,
  `src/benchweave/interfaces/ui_admin.py`.*
- **CON-15: unchanged in substance** — the change index is not an identity fact; it
  inherits the store's death semantics by construction.
- **On-disk formats/schemas: none.** No `standards/` bytes (the operations are used
  as catalogued — `approval_ref`'s `{id, version, sha256}` shape included), no store
  schema, no package motion (G4 composes existing partials: `panel`, `button`,
  `alert-bubble`, the refusal partial, `data-table`, `render_disabled_label`), no
  dependency motion, `uv.lock` untouched. Both standards tripwires run before push.
- **Obligations:** 4 (operator guide + README — the administration section, STE
  register); 8 (the adapter-identity touch-set — `ui_admin.py` joins it,
  hand-carried); 9 (no new env knob — no systemd motion); 12 (walked, no motion);
  22 (no CLI change — G4-D3 defers the approver CLI rather than triggering it); 23
  (no new CLI); 26 (the browser lane's CSS pins assert on the new controls).
- **CI cost:** `gates` grows one `tests/interfaces_ui/test_ui_admin*.py` suite (no
  new markers); `browser` grows the two admin surfaces (lane stays serialized);
  `windows` inherits by selection; `timing` untouched (no real-clock bounds);
  `package` unaffected.

## 8. Review tier (Step-1, rubric #254) and keyword scan

**Tier 3** — by the keyword rule first: the diff text carries `sha256` by
construction (approval and target refs are digest-keyed end to end). No
standards-governor trigger: no `standards/` bytes, no vendored tree, no version
strings. Consequences: the two-lane adversarial refute and the cold full battery.

Keyword scan over the expected diff text (new `ui_admin.py`, `sessions.py` and
`ui_routes.py` additions, new `change.j2` + admin-region markup, `ui_refusals.py`
variants, new `tests/interfaces_ui/test_ui_admin*.py`, operator-guide + README +
invariants rows, and this record — docs and code alike; estimates re-derived over
the real diff at review):

| keyword | expected count | where |
|---|---|---|
| `sha256` | ~90 | approval/target digest fields, attributes and validation in code (~30), tests minting approval docs and refs (~40), record + docs (~20) |
| `hashlib` | ~4 | tests hashing approval bodies (the `_put_approval` lift); 0 acceptable in prod code |
| `protection` | ~4 | record prose only (§C.1/§C.2 discussion); 0 in code |
| `threading` | ~1 | record prose (the sessions-lock context); 0 in code |
| `asyncio` | 0 | — |
| `subprocess` | 0 | — |
| `migrate` | 0 | — |
| `recovery` | ~2 | record prose only |

## 9. Top risks, each with its falsifier

- **R1 — the "inhibited control" reading.** This design renders the explicit record
  + a critical persistent alert + apply-disable-until-acknowledged, and deliberately
  does NOT disable run controls (no wire fact ties a failed admin change to run
  authority; inventing one exceeds presentation). Falsifier: the owner reading the
  contract's "inhibits affected control" more broadly — the fork is one predicate
  line (extend the disable set) or one deletion (notice-only), not a redesign.
- **R2 — the approval-paste UX is the flow's weakest link.** A detached token pasted
  into a form on a loopback single-operator gateway (the deploy posture); the field
  never echoes, the form is CSRF-guarded, and the token is a local-test-issuer
  credential. Falsifier: an owner judgment that browser handling of approver tokens
  is unacceptable before an identity provider exists (F1's trigger) — then the apply
  workspace moves out of the browser and G4 shrinks to submit + review + the
  failed/unknown record (GW-72 fully, GW-71 vacuously honest).
- **R3 — cross-session invisibility.** Another session's changes are absent from
  the index; the bench admin region understates gateway truth. Mitigation: manual
  change-id entry reaches any change; conservative direction only (it never offers
  what the seam would refuse). Falsifier: an operator unable to reach a change
  through any G4 surface — then G4-D2's interface issue becomes blocking.
- **R4 — the acknowledgement is per-session.** A fresh session re-sees the alert
  over the same terminal record; the gateway state never changes. Honest (no
  reconciled-flag operation exists), disclosed here and in the operator guide.
  Falsifier: owner wants a durable reconciliation mark — that is an interface
  change (G4-D2's issue carries it), not a UI patch.
- **R5 — `trip_reset`'s target semantics are loose.** The catalog pins the shape,
  not the meaning; the prefill (bench configuration ref) is a convention. The seam
  ignores the value beyond event evidence. Mitigation: schema-validated, event
  evidence shown on the record; disclosed. Falsifier: a standards decision that
  pins per-kind target semantics — a catalog change, not a UI one.
- **R6 — apply has no §9 replay.** A double-apply is answered by the two-phase
  `conflict`, not a duplicate return; the UI renders that row without softening.
  Mitigation: A/E arms pin the one-effect property (the dispatch is unreachable
  twice through the state machine); the fixed request id still satisfies GW-13's
  form rule. Falsifier: an interface decision to give apply §9 semantics — the UI
  needs zero changes (the form already carries the id).

## 10. Maintainer decisions (forks, not blockers)

- **F1 (R1):** the inhibited-control breadth — alert + apply-disable (this design),
  notice-only, or the wider disable including run controls.
- **F2 (G4-D3):** fund the approver-side approval-minting CLI now (an operator
  convenience with real obligations — 4 and 22) or leave approvals out-of-band as
  today.
- **F3 (G4-D5/D7):** accept the theme toggle's trigger-pinned re-deferral (standalone
  UX issue; first operator request or the standalone host's own toggle lands the
  shared mechanism), or call the UX slice now.

## Addendum (2026-10-04, the two-lane refute fold): §1's terminality sentence corrected

§1's bullet — "`_record_change_outcome` (operations.py:1485) never overwrites
`applied`; a `failed`/`unknown` change can never re-enter `proposed`, so
re-apply is structurally impossible" — was true as written and incomplete as
read. The recorder's guard was `state != "applied"`: a re-apply attempt on an
`unknown` change reclassified it to `failed` with the two-phase conflict
message, erasing the crash evidence, and a re-apply on a `failed` change
replaced its audit reasons — the `reasons[0]` GW-72's alert renders. That is
the seam pre-dating this slice; §1 cited the guard as terminality proof for a
property it did not have. "Structurally impossible" described re-entering
`proposed`, never the record's immutability.

The fold: the recorder writes only over a change still `proposed` — every
terminal state (`applied`, `failed`, `unknown`) is non-overwritable, and a
re-apply's `conflict` reaches the caller with the record, and its reasons,
exactly as the first outcome left them (A06: the undecided record IS the
evidence). Pinned at the seam in `test_seam_admin.py`
(`test_reapply_on_unknown_keeps_the_unknown_record`, and the failed-record
reasons arm that followed it).
