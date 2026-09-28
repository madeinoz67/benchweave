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

Series tokens (`--bw-series-1…8`), the dash sequence and the symbol sequence are added
by the plot-series slice (issue #242 slice 3); their absence here is a deferral, not a
gap in this contract's authority.

### §A.1 Colour palette

Schema: `Token | Light | Dark | Use` — 16 rows. The first 14 carry product meaning;
the last 2 are the theme-dependent colour inputs the elevation shadow compositions in
`tokens.css` reference (pinned so that every theme-varying colour in `themes.css` is
contract-pinned).

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
| `reading-tile` | `section` | `data-severity ~ aria-label` | `region` | `bw-reading ~ bw-reading__header ~ bw-reading__severity ~ bw-reading__value ~ bw-reading__quality` | `steady · 2 s` | The tile renders the severity icon and its label, the value with adjacent unit, and a quality line "`{quality} · {freshness}`" (canonical fixture values: quality `steady`, freshness `2 s` — the required-text literal is the canonical line, so it discriminates a renderer that drops or misjoins either side). A reading does not become verified merely because it rendered; do not optimistically copy a requested value into an applied reading. |
| `alert-bubble` | `aside` | `data-severity ~ aria-label=Dismiss` | `status` | `bw-alert-bubble ~ bw-alert-bubble__content` | — | Title renders in a strong element, message in a paragraph, optional source in small. Critical and trip use live region `alert` (§B.1); the dismiss affordance renders only for dismissible severities (§B.1) and carries `aria-label="Dismiss"`. |
| `engineering-plot` | `figure` | `role=img ~ aria-label ~ aria-describedby ~ aria-label=Traces ~ aria-label~=(hidden by presentation preference) ~ data-line ~ data-hidden` | `img` | `bw-plot ~ bw-plot__canvas ~ bw-plot__legend ~ bw-visually-hidden` | `hidden` | The canvas carries `role="img"` with the plot title and a described-by textual chart description. Every trace is listed in a visible legend labelled "Traces"; legend items expose their line form via `data-line` (`solid`/`dashed`) and hidden channels via `data-hidden`, the hidden marker text, and an aria-label ending "(hidden by presentation preference)". Series assignment: issue #242 slice 3. |
| `data-table` | `div` | `scope=col` | `table` | `bw-table-wrap ~ bw-data-table` | — | The table carries a caption naming the data; column headers are `th[scope=col]`; rows keep a stable key. Dense data sits on a recessed surface. |
| `panel` | `section` | `data-surface ~ aria-label` | `region` | `bw-panel ~ bw-panel__header ~ bw-panel__title ~ bw-panel__body` | — | `data-surface` is `raised` for actionable groups and bounded modules, `recessed` for plots, tables, logs and dense data. An optional eyebrow span (`bw-panel__eyebrow`) precedes the title. Structural narrative and example HTML are renderer guidance. |
| `mode-banner` | `section` | `data-bw-mode-banner ~ data-bw-mode ~ aria-label=Presentation mode` | `region` | `bw-mode-banner ~ bw-mode-banner__entry` | `SIMULATED PRESENTATION DATA ~ NO GATEWAY · LOCAL PRESENTATION ONLY ~ NO CONTROLLER LEASE · ACTIONS CANNOT BE AUTHORISED ~ NO POLICY ENGINE · POLICY CHECKS UNAVAILABLE` | Contract §D: persistent, non-dismissible, first element of the page's main region; one entry per active mode in the fixed order of §D.1; absence asserts full-authority presentation. The required-text literals are the four fixed wordings (the enforcement fixture renders all four modes; a page renders only its active modes). |
| `confirm-action` | `div` | `data-bw-confirm` | — | `bw-confirm ~ bw-confirm__step ~ bw-confirm__text` | `the output will be energised ~ 12.5 V ~ PSU-07 output` | Contract §C.1 R-ENERGISE-1: the initial control only stages; the confirm step — a second explicit action — states the effect, the exact value with unit, and the target (the required-text literals are the canonical armed fixture's three elements). For energy-sourcing actions only; an energy-removing action is one action, never confirmed, never gated (R-DEENERGISE-1) and must not use this pattern. |

## §F Icon set

Framework-neutral icon keys keyed by severity or state. Any icon set can bind from the
shape descriptions; the reference binding names the lucide icons the reference renderer
uses today (`ui/src/components/feedback/severity.tsx`). State keys have no icon in the
reference renderer today — they render as text ("Staged", "hidden") or an attribute
(`aria-busy`) — so their binding is open and lands with the safety-behaviours slice's
stories.

### §F.1 Icons

Schema: `Icon key | Class | Shape description | Reference binding` — 9 rows.

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

Icons render with `aria-hidden="true"` when adjacent text supplies the name. Destructive
and protective actions always include a text label; icon-only is not allowed.
