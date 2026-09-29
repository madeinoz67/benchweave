# BenchWeave UI renderer-neutral component contract

**Status:** Normative — this document defines the contract (issue #242)

**Authority chain:** this contract is the normative, renderer-neutral definition of
BenchWeave presentation behaviour. [`ui-styleguide.md`](ui-styleguide.md) is
implementation guidance — how the reference React/Storybook renderer implements this
contract. [`ui-styleguide-workbench-design.md`](ui-styleguide-workbench-design.md) is the
historical design rationale. Where the three disagree, this contract wins.

A host renderer built from this document alone must present BenchWeave device and
gateway state such that checks and controls mean the same thing on every host.

## Authoring rule (normative)

Every machine-pinned table below is a pipe table with a fixed column schema. The
enforcement tests (`ui/src/contract-coverage.test.ts`, `ui/src/contract-enforcement.test.ts`)
parse these tables; a table that does not parse — missing heading, missing table, wrong
header cells, wrong row count where stated — is a **pin failure, not a silent skip**.
Editing this document means editing its pins in the same change.

Cell micro-syntax for §E (component contracts): items within an attribute, role,
class-hook or required-text cell are separated by ` ~ `. An attribute item is one of

- `name` — the attribute must be present somewhere in the rendered component;
- `name=value` — the attribute must be present with exactly that value;
- `name~=substring` — the attribute must be present and its value contain `substring`.

A `name=value` value must not contain a quote or a backslash: the enforcement test interpolates it into an attribute selector, so those characters are excluded by this authoring rule, not by code.

A role item names an implicit or explicit ARIA role that `getByRole` must find. A
class-hook item is a class name some rendered element must carry. A required-text item
is a literal substring the rendered text content must contain. Conditional elements and
value enumerations live in the Notes column, which is prose.

## §A Tokens

Tokens are CSS custom properties. `ui/src/styles/tokens.css` and `ui/src/styles/themes.css`
are their executable mirror: every value pinned here must equal the value parsed from
those files, in both themes, in both directions (a change to either requires the other
to change in the same commit). Components must not hard-code a colour or shadow that
conveys product meaning; theme changes luminance and contrast, not meaning.

The plot-series tokens (`--bw-series-1…8`), the dash sequence and the symbol sequence
land with the plot-series slice (issue #242 slice 3); their values carry the computed
proofs in `ui/src/series-colors.test.ts` (contrast, severity non-confusion under dual
CVD models, adjacency — thresholds pre-committed in the design record §6).

### §A.1 Colour palette

Schema: `Token | Light | Dark | Use` — 25 rows. The first 15 carry product meaning
(including `--bw-limiting`, the reading-state border/label token carrying the computed
non-confusion proofs of §B.3); the next 8 are the plot-series slots (§E.2 — set-derived
trace assignment); the last 2 are the theme-dependent colour inputs the elevation
shadow compositions in `tokens.css` reference (pinned so that every theme-varying
colour in `themes.css` is contract-pinned).

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `--bw-canvas` | `#e4ebef` | `#19252c` | Application background |
| `--bw-surface` | `#f5f8f9` | `#26363f` | Raised panel and control face |
| `--bw-surface-recessed` | `#dce5ea` | `#101a20` | Plots, tables, logs and wells |
| `--bw-text` | `#17242c` | `#eef5f7` | Primary text and values |
| `--bw-text-muted` | `#5b6a73` | `#aebbc2` | Labels, metadata and secondary text |
| `--bw-border` | `#c3cfd5` | `#40515b` | Neutral boundaries and dividers |
| `--bw-accent` | `#0b7181` | `#42cee2` | Selected state and primary action |
| `--bw-accent-contrast` | `#ffffff` | `#07161a` | Text/icons on accent |
| `--bw-focus` | `#087f8c` | `#59d9eb` | Keyboard focus ring only |
| `--bw-advisory` | `#2476b8` | `#62aee8` | Informative state requiring awareness |
| `--bw-warning` | `#a96608` | `#ffb342` | Attention required |
| `--bw-critical` | `#b63830` | `#ff6d63` | Immediate operator action |
| `--bw-trip` | `#a92858` | `#ff5d91` | Protective trip and inhibited control |
| `--bw-success` | `#177158` | `#67d8b2` | Confirmed successful outcome |
| `--bw-limiting` | `#274076` | `#5f9500` | Limiting reading-state border and label (§B.3); non-confusion proofs vs the six severity hues AND the neutral severity's `--bw-text-muted` rendering, plus `--bw-border` (pinned) |
| `--bw-series-1` | `#253421` | `#00744a` | Plot series slot 1 (§E.2; set-derived assignment) |
| `--bw-series-2` | `#8e7588` | `#e3d7ff` | Plot series slot 2 (§E.2; set-derived assignment) |
| `--bw-series-3` | `#2f3300` | `#567200` | Plot series slot 3 (§E.2; set-derived assignment) |
| `--bw-series-4` | `#00379d` | `#805e71` | Plot series slot 4 (§E.2; set-derived assignment) |
| `--bw-series-5` | `#7e002d` | `#007df3` | Plot series slot 5 (§E.2; set-derived assignment) |
| `--bw-series-6` | `#746084` | `#ae686e` | Plot series slot 6 (§E.2; set-derived assignment) |
| `--bw-series-7` | `#5a1538` | `#755d9a` | Plot series slot 7 (§E.2; set-derived assignment) |
| `--bw-series-8` | `#183058` | `#7d8f00` | Plot series slot 8 (§E.2; set-derived assignment) |
| `--bw-shadow-dark` | `#b9c5cc` | `#0c1317` | Dark component of elevation shadows |
| `--bw-shadow-light` | `#ffffff` | `#354852` | Light component of elevation shadows |

Severity colours are not general decoration. Normal state uses neutral surfaces; success
is reserved for a confirmed transition or outcome. Severity hues are legal in plots only
for elements that carry that severity meaning (today: the threshold mark line).

### §A.2 Spacing and layout

Schema: `Token | Value | Typical use` — 6 rows. The base unit is `0.25rem`.

| Token | Value | Typical use |
| --- | --- | --- |
| `--bw-space-1` | `0.25rem` | Tight label/value separation |
| `--bw-space-2` | `0.5rem` | Icon gaps and compact rows |
| `--bw-space-3` | `0.75rem` | Control groups and alert padding |
| `--bw-space-4` | `1rem` | Standard component padding |
| `--bw-space-5` | `1.5rem` | Panel and page-section gaps |
| `--bw-space-6` | `2rem` | Major composition separation |

### §A.3 Radius

Schema: `Token | Value | Use` — 2 rows.

| Token | Value | Use |
| --- | --- | --- |
| `--bw-radius-control` | `0.5rem` | Buttons, fields, bubbles and compact controls |
| `--bw-radius-panel` | `0.875rem` | Panels, cards and instrument groups |

### §A.4 Typography fonts

Schema: `Token | Value | Use` — 2 rows. Typography roles (page title, reading, metadata
sizes) are renderer guidance in `ui-styleguide.md`; the two font stacks are contract
tokens. Numeric readings, timestamps, identifiers and source evidence use the data font
with tabular numerals.

| Token | Value | Use |
| --- | --- | --- |
| `--bw-font-ui` | `Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif` | Interface text |
| `--bw-font-data` | `"SFMono-Regular", Consolas, "Liberation Mono", monospace` | Readings, timestamps, identifiers, evidence |

## §B States and severity model

### §B.1 Severities

Schema: `Severity key | Meaning | Dismissal class | Live region` — 6 rows. Severity keys
are the closed enum; renderers use severity names, icons, labels and messages — never
colour or glow alone.

| Severity key | Meaning | Dismissal class | Live region |
| --- | --- | --- | --- |
| `neutral` | Context or helper detail | `dismissible` | `status` |
| `success` | Confirmed completion with no continuing risk | `dismissible` | `status` |
| `advisory` | Non-urgent evidence or state note | `dismissible` | `status` |
| `warning` | Attention required | `persistent-until-acknowledged-or-resolved` | `status` |
| `critical` | Immediate operator action | `persistent-until-resolved` | `alert` |
| `trip` | Protective action and inhibited control | `non-dismissible-while-active` | `alert` |

### §B.2 State rules

Schema: `Rule id | Requirement` — 3 rows.

| Rule id | Requirement |
| --- | --- |
| `SR-B1` | A state message may appear inline, anchored to its source, inside a panel, or as a global banner. A transient toast is limited to neutral, success and advisory confirmations; warning, critical and trip information must remain present in the affected context. |
| `SR-B2` | Glow is an additional cue only: advisory through trip may use localised glow around the affected reading or message; normal and success readings do not glow. Every abnormal state also carries an icon, an explicit label, a border and text. |
| `SR-B3` | Dismissing a message is not acknowledgement of the underlying gateway or device condition; acknowledgement is modelled as a separately labelled, authorised request. |

### §B.3 Reading states

Schema: `State key | Meaning | Rendering | Announcement` — 1 row.

| State key | Meaning | Rendering | Announcement |
| --- | --- | --- | --- |
| `limiting` | A limit, not the set-point, is constraining the value (constant-current operation; a channel near full scale). Significant, not abnormal. | Icon + visible label `Limiting` + border in `--bw-limiting`, on the affected reading. No glow (SR-B2 reserves glow for advisory–trip SEVERITIES). Never dismissible while active; never rendered via the alert-bubble pattern; never enters a live region `alert`. Composes with any severity (both render; the severity keeps its glow rights). | Entry announces once via a `status` live region, coalesced; exit is silent. |

`limiting` is NOT a severity key (§B.1 unchanged), NOT a disabled reason (§C.2
unchanged), and MUST NOT be counted, aggregated or announced as an alert anywhere a
host summarises alerts. Border allocation: when `limiting` composes with a severity,
the state takes the border (`--bw-limiting`) and the severity keeps its glow rights —
both render, neither displaces the other. Distinct from `protection-active`: a limiting reading is
operating normally inside its envelope; `protection-active` is a control-disabled
reason tied to a protective trip.

### §B.4 Staleness

Schema: `Rule id | Requirement` — 4 rows. The staleness window is the polled
parameter's `max_age_ms` (`otdp-device-descriptor.schema.json` — cited from the
corpus, not restated). Clock anchor (OTDP spec §100): `freshness_ms` is the
age at assembly on the acquisition stream's monotonic-derived time — wall-clock
steps must not un-stale a reading.

| Rule id | Requirement |
| --- | --- |
| `ST-1` | The staleness cadence is the POLLED parameter's `max_age_ms` — the descriptor's own read-acceptance window, host-supplied configuration from the descriptor/profile, never invented, never a renderer default. For a streaming observation `stream_limits.min_interval_ms` is a rate CAP (OTDP spec §158): silence is healthy, so a stream-cadence source supplies NO cadence and renders NO staleness verdict — the missed-data signal is the gap event, never silence-inference. |
| `ST-2` | A reading is stale iff `freshness_ms > max_age_ms` (strictly greater; equality is not stale — the boundary is the descriptor's own disavowal line). `max_age_ms: 0` is valid semantics: fresh-acquisition-only, everything ≥ 1 ms is stale. The predicate is a pure function of the wire's `freshness_ms` and the commissioned window; garbage inputs (non-finite or negative age, non-finite or negative window) render no verdict. |
| `ST-3` | No known cadence (the descriptor/profile supplies none for that binding) ⇒ NO staleness verdict renders — the reading renders without a stale marker, which asserts freshness NOWHERE. `freshness_ms: null` renders `Unavailable` (existing behaviour) and is not stale. A device-declared quality string renders verbatim in the quality slot and is never overwritten or augmented by the computed verdict — two channels, never laundered into one. |
| `ST-4` | A stale reading renders dimmed (muted text treatment) and carries `data-bw-stale="true"` plus the visible marker `stale` appended to the quality line; it renders at reduced prominence, never at normal reading prominence. The fresh→stale transition announces once via a `status` live region, coalesced. A stale reading never renders without its marker (the OTDP §5 rule that stale readings cannot satisfy verification, at the presentation boundary). |

## §C Safety rules (definition rows)

These rows define presentation-level safety behaviour. Their enforcement in the
reference renderer lands with the safety-behaviours slice (issue #242 slice 2); the
definitions are normative now.

### §C.1 Safety rules

Schema: `Rule id | Requirement` — 3 rows.

| Rule id | Requirement |
| --- | --- |
| `R-ENERGISE-1` | An action is energy-sourcing iff it closes a path for energy to reach the DUT: enabling an output, or changing a setpoint of a currently-energised output. An energy-sourcing action requires a confirmation step whose text states (i) the effect — the output will be energised, (ii) the exact values to be applied, with value and unit, and (iii) the target — which output or channel. The initial control only stages intent; the confirm is a second explicit action. |
| `R-DEENERGISE-1` | An energy-removing action (output off) is one action, never confirmed, never gated. Nothing in the presentation may stand between the operator and de-energising (decision A04). |
| `R-PROTECT-1` | Energy-sourcing actions are disabled with reason `protection-active` while a protective trip is active. |

### §C.2 Disabled-reason enum

Schema: `Key | Required label text | Parameter` — 5 rows. A disabled control carries
`data-bw-disabled-reason="<key>"`, and the required label text renders visibly beside the
control (`data-bw-disabled-label`), not aria-only. `no-authority` absorbs the reference
renderer's earlier permission-disabled story state.

| Key | Required label text | Parameter |
| --- | --- | --- |
| `capability-absent` | `Not available on this device` | — |
| `device-state` | `Device must be {state}` | the blocking state (canonical example: `idle`) |
| `protection-active` | `Protection trip active` | — |
| `invalid-staged-input` | `Staged value is invalid` | — |
| `no-authority` | `No lease or policy authority` | — |

### §C.3 Refusal mapping

Schema: `Code | Severity | What happened | Sent status | Operator action` — 15 rows: the
14 error codes of interface 0.1.0 (`standards/interface/0.1.0/interface-contract.md` is
the authority; adding a code there is a standards change and out of scope here) plus one
no-response row for transport failure or timeout with no interface answer at all.

For every interface error code the sent status is **NO** — an error response means the
operation was not accepted and nothing was dispatched. For the no-response row it is
**UNKNOWN — the request may have been sent** (decision A06): the operator must not retry
blindly and reconciles via run identity and duplicate suppression.

Claim-discipline note: the "nothing was sent" claim is only as strong as interface 0.1.0's
error semantics; a future code that can mean "accepted then failed" must not join this
table without a distinct sent status. `not_found` wording must not leak existence — the
interface contract defines not_found as also the scope-invisibility answer, so the
rendered message says "unavailable to this caller", never "does not exist".

| Code | Severity | What happened | Sent status | Operator action |
| --- | --- | --- | --- | --- |
| `invalid_request` | `warning` | The request was not accepted: it failed validation. | `NO` | Correct the staged input and submit it again. |
| `unauthenticated` | `warning` | The request was not accepted: the caller is not authenticated. | `NO` | Authenticate and submit again. |
| `forbidden` | `warning` | The request was not accepted: the caller lacks the required permission. | `NO` | Have an operator with the required authority act, or request the role. |
| `not_found` | `advisory` | The addressed resource is unavailable to this caller. | `NO` | Check the identifier and the caller's scope; do not infer existence from the answer. |
| `conflict` | `warning` | The request was not accepted: the addressed revision or state has moved on. | `NO` | Re-read current state and re-stage the request. |
| `policy_denied` | `warning` | The request was not accepted: policy refuses this action. | `NO` | Request a policy change or an authorised path; do not retry unchanged. |
| `not_ready` | `advisory` | The request was not accepted: the target is not ready for this action. | `NO` | Wait for readiness and submit again. |
| `gone` | `advisory` | The request was not accepted: the addressed resource is gone. | `NO` | Refresh the view and address a current resource. |
| `cursor_expired` | `advisory` | The listing cursor expired or its snapshot was superseded. | `NO` | Restart the listing and deduplicate by stable resource identity. |
| `event_gap` | `warning` | Retention overtook the event cursor; events are missing from the stream. | `NO` | Re-read the affected snapshots from a new cursor; do not skip the gap. |
| `payload_too_large` | `warning` | The request was not accepted: its payload exceeds the limit. | `NO` | Reduce the payload and submit again. |
| `rate_limited` | `advisory` | The request was not accepted: the rate limit was hit. | `NO` | Wait the advertised interval and submit again. |
| `unavailable` | `critical` | The gateway is unavailable. | `NO` | Restore or await the gateway; treat observation and protection visibility as degraded. |
| `internal_error` | `warning` | The request was not accepted: an internal error occurred. | `NO` | Retry from known state or contact the operator; the correlation ID links diagnostics. |
| `no-response` | `critical` | No interface answer arrived (transport failure or timeout). | `UNKNOWN` | Do not retry blindly; reconcile via run identity and duplicate suppression before acting again. |

Severity defaults for `not_ready` and `unavailable` are owner-decision defaults (design
record §10): severity may go up, not down, without an owner ruling.

## §D Mode banner

A persistent, non-dismissible banner on every page, first element of the page's main
region. One entry per active mode, in the fixed order of the table below. The banner
element carries `data-bw-mode-banner`; each entry carries `data-bw-mode="<mode>"`; the
region is labelled "Presentation mode". Tone is advisory. Absence of the banner asserts
full-authority presentation.

### §D.1 Modes

Schema: `Mode | Fixed wording | Fires when` — 4 rows. The `simulated` wording is pinned
by existing SDK console, TUI and test output and must not drift.

| Mode | Fixed wording | Fires when |
| --- | --- | --- |
| `simulated` | `SIMULATED PRESENTATION DATA` | presentation data is simulated or preview |
| `no-gateway` | `NO GATEWAY · LOCAL PRESENTATION ONLY` | the host presents without a gateway behind it |
| `no-lease` | `NO CONTROLLER LEASE · ACTIONS CANNOT BE AUTHORISED` | no bench authority exists behind actions |
| `no-policy` | `NO POLICY ENGINE · POLICY CHECKS UNAVAILABLE` | no policy engine is configured |

The device-level `SIMULATED` badge (device fixture state) is a different question and
stays a device badge; unification is deferred (design record row D4).

## §E Per-component contracts

One row per component. Enforced rows are pinned by `ui/src/contract-enforcement.test.ts`
against the reference renderer's canonical rendering; a row whose component has no
enforcement fixture fails that test (rows cannot appear without implementations).
`engineering-plot` gains its series-assignment sub-rows with the plot-series slice
(issue #242 slice 3).

### §E.1 Components

Schema: `Component | Root element | Required attributes | Required roles | Required class hooks | Required text | Notes` — 10 rows.

| Component | Root element | Required attributes | Required roles | Required class hooks | Required text | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `button` | `button` | `data-variant ~ aria-busy` | `button` | `bw-button` | — | Variants: primary, secondary, tertiary, destructive, protective. Destructive and protective actions always include a text label; icon-only is not allowed. Slice 2 adds `data-bw-disabled-reason` and the visible disabled label. |
| `numeric-input` | `div` | `type=number ~ min ~ max ~ step ~ aria-describedby ~ for` | — | `bw-numeric ~ bw-numeric__label ~ bw-numeric__field ~ bw-numeric__unit ~ bw-numeric__help` | `Staged value; use Apply to request the change` | The input is labelled by `label[for]`; bounds and step are exposed on the input; the help text states the value is staged. Applying a value must state that authority, policy and device verification still apply. |
| `rotary-control` | `div` | `type=button ~ aria-label ~ aria-valuemin ~ aria-valuemax ~ aria-valuenow ~ aria-valuetext~=staged` | `slider` | `bw-rotary ~ bw-rotary__knob ~ bw-rotary__value ~ bw-rotary__state` | `Staged` | A rotary control is always paired with a precise numeric field and an explicit Apply action; it stages intent and emits no device command while dragged. `aria-valuetext` reads "`{value} {unit}`, staged". |
| `reading-tile` | `section` | `data-severity ~ aria-label ~ data-bw-reading-state` | `region` | `bw-reading ~ bw-reading__header ~ bw-reading__severity ~ bw-reading__value ~ bw-reading__set ~ bw-reading__state ~ bw-reading__quality` | `steady · 2 s` | The tile renders the severity icon and its label, the value with adjacent unit, and a quality line "`{quality} · {freshness}`" (canonical fixture values: quality `steady`, freshness `2 s` — the required-text literal is the canonical line, so it discriminates a renderer that drops or misjoins either side). A reading does not become verified merely because it rendered; do not optimistically copy a requested value into an applied reading. With a reading state (§B.3): `data-bw-reading-state="<key>"` on the section, the state icon and its visible label in `bw-reading__state`. With gateway-observed set evidence (§E.3): `Set {value} {unit}` adjacent in `bw-reading__set` with `data-bw-reading-role="set"`. When stale (§B.4): dimmed with `data-bw-stale="true"` and the `stale` marker appended to the quality line — the enforcement fixture renders the canonical tile WITH the state and set evidence (the mode-banner all-modes precedent). |
| `alert-bubble` | `aside` | `data-severity ~ aria-label=Dismiss` | `status` | `bw-alert-bubble ~ bw-alert-bubble__content` | — | Title renders in a strong element, message in a paragraph, optional source in small. Critical and trip use live region `alert` (§B.1); the dismiss affordance renders only for dismissible severities (§B.1) and carries `aria-label="Dismiss"`. |
| `engineering-plot` | `figure` | `role=img ~ aria-label ~ aria-describedby ~ aria-label=Traces ~ aria-label~=(hidden by presentation preference) ~ data-line ~ data-bw-series-slot ~ data-hidden` | `img` | `bw-plot ~ bw-plot__canvas ~ bw-plot__legend ~ bw-visually-hidden` | `hidden` | The canvas carries `role="img"` with the plot title and a described-by textual chart description. Every trace is listed in a visible legend labelled "Traces"; legend items expose their line form via `data-line` (`solid`/`dashed` — the resolved dash, not a display position), their series slot via `data-bw-series-slot` (§E.2.1: `((i mod 8) + 1)`, wrapping at 8), and hidden channels via `data-hidden`, the hidden marker text, and an aria-label ending "(hidden by presentation preference)". Series assignment: §E.2. |
| `data-table` | `div` | `scope=col` | `table` | `bw-table-wrap ~ bw-data-table` | — | The table carries a caption naming the data; column headers are `th[scope=col]`; rows keep a stable key. Dense data sits on a recessed surface. |
| `panel` | `section` | `data-surface ~ aria-label` | `region` | `bw-panel ~ bw-panel__header ~ bw-panel__title ~ bw-panel__body` | — | `data-surface` is `raised` for actionable groups and bounded modules, `recessed` for plots, tables, logs and dense data. An optional eyebrow span (`bw-panel__eyebrow`) precedes the title. Structural narrative and example HTML are renderer guidance. |
| `mode-banner` | `section` | `data-bw-mode-banner ~ data-bw-mode ~ aria-label=Presentation mode` | `region` | `bw-mode-banner ~ bw-mode-banner__entry` | `SIMULATED PRESENTATION DATA ~ NO GATEWAY · LOCAL PRESENTATION ONLY ~ NO CONTROLLER LEASE · ACTIONS CANNOT BE AUTHORISED ~ NO POLICY ENGINE · POLICY CHECKS UNAVAILABLE` | Contract §D: persistent, non-dismissible, first element of the page's main region; one entry per active mode in the fixed order of §D.1; absence asserts full-authority presentation. The required-text literals are the four fixed wordings (the enforcement fixture renders all four modes; a page renders only its active modes). |
| `confirm-action` | `div` | `data-bw-confirm=armed ~ aria-expanded` | — | `bw-confirm ~ bw-confirm__step ~ bw-confirm__text` | `the output will be energised ~ 12.5 V ~ PSU-07 output ~ Confirm to proceed. ~ Confirm: Energise output ~ Cancel` | Contract §C.1 R-ENERGISE-1: the initial control only stages; the confirm step — a second explicit action — states the effect, the exact value with unit (non-optional — a confirm that cannot state the values it will apply is not conforming), and the target. The armed text joins as "`effect`: `value unit` to `target`. Confirm to proceed."; the second action is labelled "Confirm: `label`" and the dismissal "Cancel"; the initial control carries `aria-expanded` and the root's `data-bw-confirm` is `armed` or `idle`. **The guard holds at fire time**: `disabled`/`disabledReason` apply to the armed Confirm button as well as the initial control — a guard arriving while armed (protective trip, lost authority) disables the dispatch with its required visible reason, and the combined trip-plus-no-authority state presents `protection-active` (the trip is the present blocker). The staged intent is never silently discarded: no auto-disarm, Cancel stays enabled, and a departing guard re-enables the confirm. For energy-sourcing actions only; an energy-removing action is one action, never confirmed, never gated (R-DEENERGISE-1) and must not use this pattern. |

### §E.2 Series assignment (`engineering-plot` sub-rows)

Series assignment is a pure function of the plot's declared channel id set (plugin-ui
`$defs/plot` `y`, `maxItems: 16` — cited from the standard, never restated as our
number): the declared ids are sorted bytewise (UTF-8 byte order) and slot `i` (0-based)
takes the colour, dash and symbol below. Display order never enters the assignment;
hiding or reordering display restyles nothing; adding or removing a declared id
re-derives the plot's slots (the set changed). Uniqueness at the ceiling: the 16
declared ids produce 16 distinct (colour, dash) pairs and 16 distinct (symbol, dash)
pairs — the second is the monochrome/dash-only reproduction arm (8 symbols × 2 dashes
with no colour at all). A 17th declared id would collide with slot 8's pair; it is
refused by the wire schema (the ceiling), not by the renderer.

Legend disclosure: each legend row carries `data-bw-series-slot="((i mod 8) + 1)"` and
`data-line` naming its resolved dash.

**Waveform residual (disclosed):** symbols render on `time_series` plots only;
in `waveform` plots identity is carried by colour and dash alone, so the
same-dash census below (all 28 token pairs per theme ≥ 8 ΔE00) is the
load-bearing separation for waveforms. Whether symbols should render in
waveforms is an owner fork, not part of this contract.

#### §E.2.0 Pass-2 composition (channel_hints)

Schema: `Hint | Effect` — 4 rows. These rows are NORMATIVE on top of the slot
assignment: a contract-only host must paint identically to the reference
renderer (the concrete divergence case: an accent hint on a channel that slot
assignment alone would paint `--bw-series-6`).

| Hint | Effect |
| --- | --- |
| `color_role: "accent"` | The hinted channel is repainted `--bw-series-1` (the plot's emphasis role — the binding of the accent hint), overriding its slot colour. Exactly one emphasis colour renders per plot: pass-1 slot 1 (the first bytewise slot among visible traces) is the FIRST claim, so an accent hint on any other trace loses silently to it — no cascade, slot 1 keeps its default. Among visible traces hinting accent, the earliest in trace order wins; the others revert to their slot colours. |
| `color_role: "muted"` | The hinted channel is repainted `--bw-text-muted`, releasing its emphasis claim — but only when the theme resolves the muted token; a token-less muted hint falls back to the trace's slot colour (which still claims if it is slot 1). |
| `visible: false` | The channel is not drawn, but its SLOT never moves: styles are resolved over the full declared set before visibility filters, so hiding a channel never restyles its siblings. A hidden trace releases its emphasis claim and neither claims nor starves. |
| (no hint) | The channel keeps its §E.2.1 slot colour, dash and symbol. |

#### §E.2.1 Slot mapping

Schema: `Slot i | Colour | Dash | Symbol` — 16 rows. Slot `i` is 0-based; the
series and symbol NAMES are 1-based (`series-1` = slot 0). The ceiling is
plugin-ui `y.maxItems: 16` WITH `uniqueItems: true` (ids are unique on the
wire), cited from the standard. A 17th declared id is refused by the wire
schema, not the renderer; the formula would map it (i=16) onto the same
(colour, dash) pair as i=8.

| Slot i | Colour | Dash | Symbol |
| --- | --- | --- | --- |
| 0 | `--bw-series-1` | `dash-1` | `symbol-1` |
| 1 | `--bw-series-2` | `dash-1` | `symbol-2` |
| 2 | `--bw-series-3` | `dash-1` | `symbol-3` |
| 3 | `--bw-series-4` | `dash-1` | `symbol-4` |
| 4 | `--bw-series-5` | `dash-1` | `symbol-5` |
| 5 | `--bw-series-6` | `dash-1` | `symbol-6` |
| 6 | `--bw-series-7` | `dash-1` | `symbol-7` |
| 7 | `--bw-series-8` | `dash-1` | `symbol-8` |
| 8 | `--bw-series-1` | `dash-2` | `symbol-1` |
| 9 | `--bw-series-2` | `dash-2` | `symbol-2` |
| 10 | `--bw-series-3` | `dash-2` | `symbol-3` |
| 11 | `--bw-series-4` | `dash-2` | `symbol-4` |
| 12 | `--bw-series-5` | `dash-2` | `symbol-5` |
| 13 | `--bw-series-6` | `dash-2` | `symbol-6` |
| 14 | `--bw-series-7` | `dash-2` | `symbol-7` |
| 15 | `--bw-series-8` | `dash-2` | `symbol-8` |

The colour values are the §A.1 series tokens (`--bw-series-1…8`, per theme), carrying
the computed proofs of `ui/src/series-colors.test.ts`.

#### §E.2.2 Sequences

Schema: `Key | Shape description | Reference binding` — 10 rows (2 dash, 8 symbol).

| Key | Shape description | Reference binding |
| --- | --- | --- |
| `dash-1` | Solid line — no gaps | ECharts `solid` |
| `dash-2` | Fixed dash pattern — equal on/off segments (the reference binding draws 4 px on, 4 px off at the default stroke width) | ECharts `dashed` |
| `symbol-1` | Filled circle | `circle` |
| `symbol-2` | Filled square | `rect` |
| `symbol-3` | Filled upward triangle | `triangle` |
| `symbol-4` | Filled diamond | `diamond` |
| `symbol-5` | Filled teardrop (pin) | `pin` |
| `symbol-6` | Filled arrowhead | `arrow` |
| `symbol-7` | Filled plus (cross of two bars) | custom SVG path |
| `symbol-8` | Filled saltire (diagonal cross of two bars) | custom SVG path |

The reference binding is implementation guidance (the ECharts marker names the
reference renderer uses; where the chart library lacks a shape the binding is a custom
SVG path). Any icon set can bind from the shape descriptions.

### §E.3 Setpoint presentation (reading-tile sub-rows)

Schema: `Role | Placement | Required labelling | Never` — 3 rows. The host derives role
eligibility from the descriptor's parameter semantic roles (OTDP spec §4:
`measurement`/`setpoint`/`state`/`configuration` — cited from the corpus, not
restated): an observation bound to a `setpoint`-role parameter supplies the `set`
role; a `measurement`-role parameter supplies `measured`.

| Role | Placement | Required labelling | Never |
| --- | --- | --- | --- |
| `measured` | The tile's primary value position (`bw-reading__value`) | — | Never sourced from a requested or staged value; a reading does not become verified because it rendered |
| `set` | Adjacent to the measured value, in the same tile (`bw-reading__set`), carrying `data-bw-reading-role="set"` | `Set {value} {unit}` — visible text, data font | Never derived from a staged input; renders only from gateway-observed device state (a setpoint-parameter read or a verified write's reported effective value) |
| `staged` | Only in the staging input (`numeric-input` / `rotary-control` rows already carry the `Staged` required text) | `Staged` (existing pins) | Never rendered inside a reading tile; never copied into the `measured` or `set` role |

## §F Icon set

Framework-neutral icon keys keyed by severity or state. Any icon set can bind from the
shape descriptions; the reference binding names the lucide icons the reference renderer
uses today (`ui/src/components/feedback/severity.tsx`). State keys have no icon in the
reference renderer today — they render as text ("Staged", "hidden") or an attribute
(`aria-busy`) — so their binding is open and lands with the safety-behaviours slice's
stories.

### §F.1 Icons

Schema: `Icon key | Class | Shape description | Reference binding` — 10 rows.

| Icon key | Class | Shape description | Reference binding |
| --- | --- | --- | --- |
| `neutral` | `severity` | Circle containing a question mark | `CircleHelp` |
| `success` | `severity` | Circle containing a check mark | `CheckCircle2` |
| `advisory` | `severity` | Circle containing a lowercase information letter i | `Info` |
| `warning` | `severity` | Triangle containing an exclamation mark | `TriangleAlert` |
| `critical` | `severity` | Circle containing an exclamation mark | `AlertCircle` |
| `trip` | `severity` | Shield containing an exclamation mark | `ShieldAlert` |
| `busy` | `state` | Circular arc with an arrowhead, suggesting rotation | `none today` |
| `hidden` | `state` | Eye shape crossed by a diagonal slash | `none today` |
| `staged` | `state` | Half-filled circle marking a value not yet applied | `none today` |
| `limiting` | `state` | Vertical arrow rising to meet a horizontal ceiling bar | `ArrowUpToLine` |

Icons render with `aria-hidden="true"` when adjacent text supplies the name. Destructive
and protective actions always include a text label; icon-only is not allowed.
