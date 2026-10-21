# The classref plot-kind mirror leg: emit the reference's plot kind, gateway-side (the render-gate record's D2)

Status: designed 2026-10-21 in `.wt/gate-k9x2` (branch `feat/classref-promotion`, head
`ade5753d`; content-identical to `origin/main` for every path this design touches —
verified `git diff --stat HEAD origin/main` over `presentation/`, `interfaces/ui_presentation.py`,
`contracts.py`, the class-reference corpus, `tests/presentation/`, `tests/ui_html/` is empty).
No build in this slot. This is the follow-on gateway issue the render-gate record
(`2026-10-21-classref-sdk-render-gate-design.md` §2.1, deferral D2) named: the L4 fallback
emits every derived plot as `digital_lanes` regardless of what the reference's page template
declares.

Triage check (`.claude/deep-review/README.md`): public. Invented fixture names only; the
community daq plugin referenced below is already-public provenance named in-tree
(`tests/ui_html/test_classref_daq.py`), cited as provenance per CLAUDE.md §4.

## 1. The defect, traced to the line

`src/benchweave/presentation/classref.py::_assemble_documents` (lines 1136–1450) builds the
derived plot at lines 1370–1412. The loop reads the page template's `plot` spec
(`plot_spec.get("over_slot")` at 1378, `plot_spec.get("group_radix", "hex")` at 1396) but
never reads `plot_spec["kind"]`; the emitted plot hardcodes `"kind": "digital_lanes"`
(line 1401) with `y` = the string-typed channel lanes (`lane_vars`, line 1168:
`{"id", "type": "string", "unit": None, "shape": "vector"}`) and hex `D{first}-D{last}`
lane groups at `_GROUP_SIZE` (lines 1383–1398).

The committed 0.3.0 corpus declares, per class file (verified by reading all eight):

| class | plot template |
|---|---|
| logic_analyser | `digital_lanes` over `capture` (the founding class) |
| dc_psu, dmm, electronic_load, smu | `time_series` over `measure` (`series: numeric_variables`) |
| oscilloscope, daq | `waveform` over `capture` (`series: numeric_variables`) |
| function_generator | no plot (the measurement-free class — unaffected) |

So for six of the seven post-founding classes the fallback serves a plot of the wrong kind,
over variables typed as string vectors, with lane groups the analog kinds' schema bans. The
SDK expander carries the same hardcoded emission
(`packages/sdk/src/benchweave_sdk/classref.py::_finish`, line 1178 — `time_series` and
`waveform` occur zero times in that module), so this is NOT gateway drift from the SDK: the
gateway is today a faithful mirror of a shared defect. The SDK-side widening is designed and
in flight (the render-gate record §3.1 item 2); the SDK's `classref_gate.py::_forbid_findings`
line 299 (`if plot.get("kind") != "digital_lanes": continue`) only SKIPS non-lane plots for a
hint rule — no gate anywhere refuses or diverts these kinds.

## 2. Q1 — Reachability: LIVE on the serve path, not latent

The production chain, every link read in this tree:

1. `src/benchweave/interfaces/ui_read.py:197` — `device_page` calls
   `compose_device_presentation(content, descriptor_raw)`.
2. `src/benchweave/interfaces/ui_presentation.py:464-496` — with NO admitted envelope
   (the no-manifest arm, line 490), it calls `_classref_fallback`.
3. `_classref_fallback` (line 693) — `select_references` finds the class reference for any
   descriptor whose profiles name one of the eight classes (fail-open only for classes with
   NO reference); `derive_attachment` (line 756) runs.
4. `derive_attachment`'s refusal ladder (lines 1475–1558: invalid reference, target version,
   unknown action, unknown slot, required-action absent, slot conflicts) — **none of these
   reads the plot kind**. `validate_reference_document` validates against the family schema,
   whose plot-kind enum is `["digital_lanes", "time_series", "waveform"]` with per-kind
   conditionals (`standards/plugin-ui-class-reference/0.3.0/class-reference.schema.json`
   lines 225–300) — a `time_series`/`waveform` template is schema-VALID.
5. `_assemble_documents` line 1401 emits the hardcoded kind; the derived manifest then
   PASSES `validate_attachment`, because the gateway validator's `digital_lanes` branch
   (`src/benchweave/presentation/contracts.py::_plot_findings`, lines 500–540) requires
   exactly what the lie emits: string/vector y variables over a dataset target. The wrong
   kind launders through validation by construction.

Live proof already in the suite: `tests/ui_html/test_classref_smu.py::
test_the_sweep_absence_holds_over_the_committed_pair` derives the committed SMU pair
(time_series reference) successfully today and asserts the derived layout carries exactly
one plot — green on `main`, never checking the kind. A community daq plugin is already
shipped against this surface (already-public provenance, `tests/ui_html/test_classref_daq.py`),
so no-envelope devices of the numeric classes are a real serving case, not a fixture
curiosity.

**Falsifier for this verdict:** serve any SMU/daq-profile descriptor with no admitted
envelope and observe the device page — if the result is NOT a `valid=True, derived=True`
`PresentationState` carrying a `digital_lanes` plot (i.e. a typed `classref_*` finding or
the honest absence renders instead), the path is gated somewhere I missed and the severity
drops to latent. Mechanically: any gate between `device_page` and line 1401 that reads
`plot_spec["kind"]` — the ladder at 1475–1558 and the family schema are the only candidates
and neither does (both read in full this session).

## 3. Q2 — Fix shape: emit the true kind (mirror the SDK widening), do not refuse

The admission doctrine's asymmetry — hard-fail when PRESENT bytes assert something false,
soft-degrade on absence — condemns the OUTPUT, not the input: the derived manifest's present
bytes assert `digital_lanes`, which is false for a `time_series` reference. Two truthful
arms exist; the doctrine picks between them by asking what the bytes CAN honestly say.

**Refusal is the wrong arm.** The numeric kinds are representable end to end in this tree,
without touching the corpus or the host:

- the manifest schema admits all three kinds
  (`standards/plugin-ui/0.4.0/ui-manifest.schema.json` `$defs.plot`, enum lines 183–190);
- the gateway validator already has the per-kind rules — `time_series`/`waveform` axes must
  be `number|integer` with shape `scalar`/`vector` respectively, and `time_series`'s x must
  carry `axis_role: "receipt_time"` and unit `s` (`contracts.py::_plot_findings` lines
  508–528);
- the derivation's inputs carry everything needed — the descriptor's resolved channels and
  their declared quantities (the SMU example: 2 channels x 3 quantities = 6 scalar
  variables; the daq example: analogue_input channels x voltage);
- the corpus itself AUTHORS the expectation of the true emission (the numeric classes'
  `expect.components` count `engineering-plot: 1`).

Refusing would also contradict the committed-pair arms: seven `tests/ui_html/test_classref_*.py`
suites assert successful derivation over numeric references today (the SMU one explicitly
documents "NO REFUSAL: the derivation over the committed pair succeeds"). A refusal arm
reddens all of them — editing them to expect refusal is weakening existing assertions,
prohibited for this slice. **Falsifier for the refusal arm:** any committed numeric pair
whose derivation the refusal would have to break — `test_the_sweep_absence_holds_over_the_
committed_pair` is the named instance.

**Emission is the right arm — but only as the SDK's mirror, behind the SDK widening.** The
gateway derivation is read-not-import (REG-4 posture) and deliberately byte-mirrors the SDK
expander, pinned by the B8 fixtures (`tests/presentation/test_classref_derive.py::
TestParityB8`; the fixtures are generated FROM the SDK expander at the submodule pin).
Emitting numeric kinds gateway-first would (a) leave the numeric emission unpinnable — no
SDK expander at the 0.17.0 pin can generate the fixture — and (b) make the two derivations
actively DISAGREE on the same pair (SDK `derive-ui` still saying `digital_lanes`), which is
the cross-host inconsistency the project's one-line promise forbids. The render-gate record's
SDK leg (§3.1 item 2) designs the expander-side emission-by-kind; this leg mirrors it.

**Falsifier for the emission arm:** the SDK widened expander cannot produce a manifest-valid
analog plot for a committed class — e.g. a committed example's (channel x quantity) count
exceeds the schema's analog `y` ceiling of 16 (`$defs.plot` allOf, analog branch:
`y maxItems 16`, and `lane_groups`/`decoder_lanes` BANNED), or a field the derivation must
carry is banned. Committed counts as read this session: SMU 6, daq 6 (voltage traces) —
all under 16; if any committed class exceeds it, the corpus itself is underivable and the
slice escalates to the owner (a corpus edit is a KILL condition for this slice, per the
dispatch constraints).

## 4. Q3 — What the numeric kinds need from the host: nothing

The gateway device page's plot rendering is kind-blind structural skeleton
(`ui_presentation.py::_lane_skeleton`, lines 1132–1161): one `data-bw-lane-kind="channel"`
row per y name, group/decoder rows when present, plus the honest "no plotted data" note.
An analog plot (y = numeric variable ids, no groups, no decoder lanes) renders through it
today — fewer rows, same partial. The wrong kind is also surfaced as text in
`plot_summaries` (line 613–617, `f"{plot.get('kind', 'plot')}: ..."`) and in the raw
`plots` dicts on `PresentationPage` (line 638) — both simply become true. The
data-carrying figure rendering (real samples through `benchweave_ui_html.partials.
render_plot`) lives SDK-host-side, which already declares `plots.time-series`,
`plots.waveform`, `plots.digital-lanes`
(`packages/sdk/src/benchweave_sdk_server/presentation.py` line 59 sqq.); the gateway host
declares NO named features (`SUPPORTED_FEATURES` is the empty frozenset, line 98) and the
derived manifest names none — plot kinds are not features, so no `unsupported_feature`
interaction exists. **No host change, no ui-html change, no corpus change.**

## 5. The mechanism (the minimal first increment)

One gateway commit/PR, landing AFTER the SDK widening's release cut, per the #408 order:

1. **Emission by kind** in `_assemble_documents` (lines 1370–1412):
   - `plot_kind = str(plot_spec.get("kind", "digital_lanes"))`.
   - `digital_lanes`: today's body VERBATIM — byte-identical output for the founding class
     (the four committed fixtures f1/f2/f1-da/f5-trio must not move by one byte).
   - `time_series` / `waveform`: emit over the same capture binding —
     `{kind, binding_id: capture_binding_id, x: "t", y: [<numeric variable ids>],
     channel_hints: [{variable_id, visible: true} ...]}` — with NO `lane_groups` and NO
     `decoder_lanes` (the manifest schema's analog branch bans both; a decoder-carrying
     numeric descriptor keeps its decode binding/target, the lanes simply do not ride the
     analog plot — a disclosed residual, recorded in the module docstring).
   - The capture target's variable list becomes slot-aware: when the page template plotting
     over the capture slot declares an analog kind, the target's variables are
     `[x_analog, *numeric_vars]` — `x_analog` = `{id: "t", type: "number", unit: "s",
     shape: "scalar"|"vector", axis_role: "receipt_time" (time_series) | "x" (waveform)}`;
     `numeric_vars` = one variable per (channel, quantity) of the plot's over-slot-resolved
     channels, `type: "number"`, shape `scalar` (time_series) / `vector` (waveform). The
     decode target keeps today's lane-shaped variables (decode datasets are digital event
     logs).
   - **The variable-ID convention for (channel, quantity) pairs is READ FROM the widened
     SDK expander at the new pin** (build step 0: read `packages/sdk/src/benchweave_sdk/
     classref.py::_finish` at v0.18.0) — this design deliberately does not invent one; the
     B8 parity fixture makes any divergence mechanically visible.
   - Analog `y` ceiling: if the SDK leg ships an over-16 arm, mirror it; if it does not,
     the gateway refuses typed (`classref_series_ceiling`, the `classref_lane_ceiling`
     shape) rather than emitting a manifest the schema would refuse diffusely — the
     established precedent for a gateway fail-closed arm the SDK lacks is the non-object
     decoder-document arm at `classref.py:1216-1220`, documented inline.
2. **The numeric parity fixture** (e.g. tag `f6-smu`): descriptor + the three committed
   triple documents, generated by running the WIDENED SDK expander in the submodule over
   (descriptor x `class-smu.json`) and canonical-serializing — the same generation-once
   flow the four existing fixtures used (module docstring, lines 14–22). `TestParityB8`'s
   tag tuple gains the tag; `test_triples_validate_through_validate_attachment`'s tag list
   gains it too.
3. **The RED arms** in `tests/presentation/test_classref_derive.py` (the module that owns
   `derive_attachment`), new class `TestPlotKindEmission`:
   - `test_a_time_series_reference_derives_the_time_series_plot` — over the committed SMU
     pair (the OTDP example's bytes, corpus selection, no new fixture needed): the derived
     manifest's `output` page carries exactly one plot, `kind == "time_series"`, no
     `lane_groups` key, `y` == the six (channel, quantity) ids per the SDK convention, and
     the capture target's x variable carries `axis_role == "receipt_time"`, unit `s`,
     shape `scalar`. **REDS today** (the kind is `digital_lanes`); greens after.
   - `test_a_waveform_reference_derives_the_waveform_plot` — the same shape over the
     committed daq pair (`kind == "waveform"`, vector shapes). REDS today.
   - The family is discovered by walking the ACTIVE family's `class-*.json` (the census
     instrument's `family_profile_ids` pattern) — a ninth class joins the arms by itself.
4. **Serve-path plumbing: no new arm.** `_compose_page_rows`/`_lane_skeleton` are shared
   code paths already pinned by the derived-marker and skeleton arms in
   `tests/interfaces_ui/test_ui_presentation.py`; the derivation-level arms are the slice's
   proof. DEFERRED: a serve-path arm composing an SMU-shaped no-envelope device end to end.

**Deferrals (explicit):** (a) composed devices — the second reference's plot template keeps
its unprefixed `over_slot` after `_merge_references`, so a non-first class's plot is SKIPPED
today (the `continue` at line 1382); this slice changes nothing there (single-reference
numeric emission only) and the composition hazards ride the composition record's own
deferral table; (b) the serve-path arm above; (c) render polish of analog rows in the
lane-kind vocabulary (`data-bw-lane-kind="channel"` semantics for a numeric series) — a
ui-contract question, not this slice; (d) the D3 UI-GUIDE row (the render-gate record's).

## 6. Precedent

No new architecture. Every piece extends a proven in-tree mechanism: the per-kind validator
rules (`_plot_findings` — the fix's correctness oracle, already shipped); the
`classref_lane_ceiling` typed-refusal shape (the analog ceiling arm mirrors it); the
gateway-fail-closed-arm-the-SDK-lacks precedent (`classref.py:1216-1220`); the
fixture-generated-from-the-SDK flow (B8's four fixtures); the SDK-mirror landing order
(#408: SDK merge -> release cut -> gateway pointer, the same motion every SDK capability
bump takes). The alternative — a gateway-invented refusal or a gateway-first emission — is
refused in §3 on the doctrine and the mirror discipline respectively.

## 7. Invariant and drift impacts

- **CON-5** (the L4 amendment row, `docs/internal/invariants.md` around line 497): the fix stays
  inside the read-time-composition frame (no store write, no control authority, derived
  marker unchanged). An AMENDMENT is warranted, appended with evidence: the derived plot's
  kind follows the reference's page-template plot kind — the founding-class emission
  hardcoded `digital_lanes` until the 0.3.0 vocabulary; the mirror leg emits
  `time_series`/`waveform` per the reference, byte-pinned to the SDK expander at the pin.
  No CTL/STO row is touched; REG-4 is the adapter mirror (interfaces), not this — the
  classref mirror's pin is B8 at test level. No new invariant.
- **Surfaces that move:** `src/benchweave/presentation/classref.py` (emission + docstring
  mirror-pin note), `tests/presentation/test_classref_derive.py`, new files under
  `tests/presentation/classref_fixtures/` (NOT the Tier-3 `fixtures/registry/` lattice),
  the `packages/sdk` gitlink + `.gitmodules` pin (SAME commit — `sdk-drift` reds otherwise).
  No `standards/` byte moves; no host/ui-html byte moves; MCP/REST/CLI surfaces untouched.
- **Obligations walked:** #408 order (SDK merge -> `make release-cut VERSION=0.18.0` ->
  gateway pointer); `make check-sdk-standards` on the pointer PR; `sdk-drift` green with
  pin == the released tag; the standards-governor pass (rubric #69 — mandatory on any
  pointer-advancing diff); the release-time pairing walk reads the `::warning::`
  annotation until the window closes. The gateway issue is filed on this tracker at build
  time (the render-gate record's D2 trigger), and this PR closes it.
- **CI cost:** the derivation arms add ~2 focused tests plus one parity tuple member —
  sub-second in the existing presentation lane. No new job.

## 8. Tier statement (Step 1, rule #254)

**Recommended shape — ONE gateway PR carrying pointer + mirror: Tier 3**, first match on
"advances the `packages/sdk` submodule pointer" (the keyword rule needs no reaching; the
path rules alone do not — `src/benchweave/presentation/` is not a Tier-3 path). If instead
the pointer lands as its own PR (stacked), the mirror-only diff is Tier 2 (production code
under `src/`, none of the eight keywords in its added lines) and the pointer PR carries the
Tier 3. The standards-governor mandate rides the pointer diff either way.

Keyword scan over the expected diff text (design-time, this record plus the expected code
half; the build leg re-runs the scan over the actual committed diff and the review
re-derives the tier): scanned 2026-10-21 — this record carries ZERO occurrences of all
eight Step-1 keywords (threading 0, asyncio 0, subprocess 0, sha256 0, hashlib 0,
migrate 0, recovery 0, protection 0 — the paragraph you are reading self-fires exactly
these eight, intended and counted as the design's own statement, not as diff content);
the expected CODE half (the emission branch, the arms, the generated fixtures, the
pointer commit) carries all eight zero times by design — the emission region (lines
1370–1412) contains no digest call (the digest computations sit at lines 1293/1417/1423,
outside the edit hunks), and the new test arms assert document structure, not digests.

## 9. Pre-committed acceptance rule (written before any arm ran)

Metric: the derived plot kind over the committed corpus pairs, and byte parity against the
widened SDK expander at the v0.18.0 pin. Sample: the whole active family, discovered by
walking the family's `class-*.json` — never a literal list (a ninth class widens the sample
by itself). Six numeric classes + the founding class at this writing.

**SHIPS if all five hold:**
1. RED -> GREEN: both new committed-pair arms RED on the pre-fix tree (kind is
   `digital_lanes`) and GREEN after the emission branch, shown by the G3 procedure
   (revert only the production branch; the arms must fail with the kind assertion).
2. Parity: for the numeric fixture tag, the gateway triple equals the SDK expander's output
   at the pin byte for byte (TestParityB8 extended); the four existing fixtures remain
   byte-identical (the founding class's emission is untouched).
3. Every numeric class's committed pair derives successfully with a kind-true plot AND
   passes the unchanged `validate_attachment` (valid=true) — the composition never sees a
   derivation the validator rejects.
4. The existing suites are green UNCHANGED — `tests/ui_html/test_classref_*.py` (all eight
   classes), `tests/presentation/`, `tests/interfaces_ui/test_ui_presentation.py`: no
   assertion weakened, no fixture edited, no corpus byte moved.
5. `sdk-drift` green with the pin naming the released tag, gitlink + pin in the same commit.

**KILLS if any of:**
- (a) a clean arm cannot go green without editing a corpus byte or weakening an existing
  assertion — the expander cannot derive what the reference authors; owner escalation,
  not a test to tune;
- (b) any committed numeric pair's (channel x quantity) count exceeds the schema's analog
  ceiling (16) — the committed corpus itself is underivable; corpus motion is outside this
  slice's permissions by dispatch;
- (c) parity cannot be reached — the gateway triple diverges from the SDK's on any numeric
  pair after mirroring; the mirror is the design, a divergence is a fix-before-merge.

**UNDERPOWERED, not conclusive:** an arm fails only on host-render grounds (the skeleton's
lane-kind vocabulary for analog rows, theme polish) — that is a discovered render-polish
finding, recorded and deferred (§5c), never a tuning input to this rule; the derivation
evidence stands on its own. Same ruling if the SDK leg's convention makes a test's expected
ids need re-deriving from the pin (fix the expectation from the SDK bytes, re-run, then
judge — the fixture is the oracle, not the test's first draft).

## 10. Top risks, each with what would falsify the design

1. **The SDK widening does not land (killed or re-scoped).** This leg cannot merge — the
   numeric fixture is ungeneratable at 0.17.0 and a gateway-first emission inverts the
   mirror (§3). Falsifier: the SDK leg's own acceptance kill. Mitigation: the defect stays
   a disclosed residual (the render-gate record's D2 + this record); the interim-refusal
   question goes to the owner with this record's §3 cost analysis attached (refusal reddens
   seven committed-pair suites).
2. **The SDK leg's variable-ID convention or plot fields diverge from anything the gateway
   can produce deterministically.** Falsifier: acceptance kill (c). Mitigation: the
   convention is READ from the pin at build step 0 and pinned by the fixture; the gateway
   invents nothing.
3. **Composed devices regress.** A two-class descriptor mixes kinds; the merged-pages plot
   loop must not apply the analog variable typing to the founding class's capture target.
   Falsifier: the composition derivation arms (the composed-pair derivations in
   `test_classref_composition.py`'s orbit and the F5-trio parity fixture). Mitigation:
   variable typing is per-slot, resolved through the plot template that names the slot;
   the f1/f2/f1-da/f5-trio byte-identity requirement (acceptance 2) is the guard.
4. **Analog `y` overflow on real descriptors** (>16 scalar variables). Falsifier: a
   descriptor with 17+ (channel x quantity) pairs derives. Mitigation: the typed
   `classref_series_ceiling` refusal (§5.1) — honest and typed, the lane-ceiling shape.
5. **Severity misjudged as latent.** Falsifier: §2's serve-path probe — run it; if the
   wrong page does not render, this record's severity claim is wrong and the record is
   corrected, not defended.

## 11. Recommendation

**BUILD — as the mirror leg paired to the SDK widening, not standalone.** The defect is
live on the serve path (§2), the honest fix is emission (§3), the host needs nothing (§4),
and no existing assertion, corpus byte, or SDK byte moves gateway-side (§5, §9.4). The one
structural dependency is order: the SDK widening must merge and cut 0.18.0 first; this leg
then lands as the gateway pointer PR carrying the mirror, the numeric fixture, and the RED
arms. If the SDK leg is killed, this leg waits with it — an interim gateway-only refusal
is designed-against here on the committed-pair cost (§3), and that trade-off is the owner's
call, not a default.
