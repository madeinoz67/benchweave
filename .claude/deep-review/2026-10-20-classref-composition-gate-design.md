# The cross-class composition gate (gateway issue #500)

Status: designed 2026-10-20, built on `feat/classref-composition-gate`
(base `a7dc70fc`, the L17 tip). Owner directive 2026-10-19: every device
class must compose with every other device class — a core requirement of
the family, not a property of one batch.

## 1. The gap

A descriptor's `profiles` is an array (`minItems: 1`, `uniqueItems`,
no maximum). The gateway merges the selected references per parent §3.8:
`select_references` sorts the claimed profiles bytewise, skips profiles
without a corpus reference, and `_merge_references` composes the sorted
list — the first reference keeps bare slot and page ids, every later one
prefixes them with its profile slug
(`profile_id.split("/")[0].replace(".", "-")` + `-`).

Each class reference is authored in isolation, and no existing gate
composes two classes. A class whose identifiers collide with another
class's *prefixed* identifiers therefore lands clean: the family schema
admits the colliding literal (`^[A-Za-z0-9][A-Za-z0-9._:/-]*$`), the
per-class gates never merge, and the merge itself is collision-blind —
`merged["slots"][key] = slot` overwrites silently, and duplicate page
ids append silently. The defect appears only when a device claims two
classes, which no test or bench does today.

## 2. The gate

One instrument, extended, not forked: the composition arm lives in
`tests/ui_html/classref_census.py` (the family's shared instrument since
L12 — no second census), and the gate is
`tests/ui_html/test_classref_composition.py`.

Mechanism, all through the real code path:

1. **Discovery** — `family_profile_ids(corpus)` walks the ACTIVE family
   version's `class-*.json` files (the same glob and the same
   `profile_id` acceptance `_find_reference` applies). The pair set
   derives from the CURRENT family, never a frozen list — the flip-target
   rotation rule; a ninth class widens the gate automatically.
2. **Selection + merge** — `compose_pair(corpus, (a, b))` builds the
   synthetic descriptor `{"profiles": [a, b]}`, runs the real
   `select_references`, asserts both references were selected, and the
   real `_merge_references` over the sorted list (`merge_selected` is
   the seam both the pair gate and the refusal arms use — selection for
   corpus classes, direct sorted documents for synthetic ones, which the
   corpus cannot carry without a standards bump).
3. **Refusal** — `composition_findings` re-derives each reference's
   emitted identifiers with the merge's own transform (bare for the
   first, `{slug}-` prefixed for later ones) and refuses any identifier
   the composed document would carry twice, with attribution (the two
   profiles that emit it). Four identifier kinds:
   - **slot keys** (the composed document's binding namespace — the
     control handles the manifest's pages bind);
   - **page template ids**;
   - **authored layout page ids**;
   - **`expect.controls` action URNs** (a control's identity — two
     classes claiming one URN is a duplicate control identifier
     regardless of prefixing).

   One pair per unordered class pair: C(n,2) compositions of the active
   family, plus the coverage assertion (pair count exact, every class
   paired, discovery count at least the eight that exist today).

## 3. The RED demonstration

The gate must fail in both directions, and a colliding document must be
shown to pass every existing gate first (the issue's premise):

- **Premise arm** — the deliberately colliding class (a copy of a real
  reference, retitled, one slot renamed to the colliding literal) is
  schema-valid (`validate_reference_document` passes) and the real merge
  accepts it SILENTLY: the merged slot count shrinks — the overwrite the
  issue exists to refuse, demonstrated on today's code.
- **Direction 1 (new class collides with an existing one)** — synthetic
  `otdp.composed_probe/1.0.0` (bytewise before the target) authors a
  slot, a page id and a layout page id in the target's prefixed
  namespace; the pair composition returns all three findings.
- **Direction 2 (existing class edited so a new one collides)** — the
  EXISTING class's slot is renamed into a new class's prefixed
  namespace; the new class's own ids are plain; the pair composition
  refuses, attributing the collision to the edited side.
- **Sort-order arm** — the same collision fires whichever side sorts
  first; the merge order never decides the refusal (the M7 principle at
  the identifier level).
- **URN arm** — two classes claiming one action URN in
  `expect.controls` refuse as a duplicate control identifier.
- **Specificity arm** — a clean synthetic class (plain ids, empty
  controls) composes with EVERY existing class with zero findings: the
  gate refuses collisions, not new classes.

The RED-sanity proof: the refusal arms are run once against a
neutralized detector (findings forced empty — the pre-gate world) and
shown to FAIL, then against the real detector. A gate that has never
refused anything is a claim, not a guard.

The target class is derived at run time (the first family class with a
`capture` slot — `otdp.daq` today) and the sort geometry is asserted,
not assumed — the arms re-derive from the current family, never from
this record (the flip-target rotation trap).

## 4. Scoped out, measured, reported

Measured over all 28 pairs of the current eight-class family (the probe
script's output is preserved in the lane report):

- **Slot keys, page ids, layout page ids: clean across all 28 pairs.**
  The prefixing does its job on the spaces it covers. The gate lands
  green.
- **Authored layout control slugs are NOT prefixed by the merge.**
  `arm`/`abort`/`trigger` are authored by daq, logic_analyser and
  oscilloscope; `measure` by dc_psu, dmm, electronic_load and smu — 10
  of 28 pairs carry duplicate authored control slugs in the composed
  document, and `_urn_for_binding` (both derivations,
  `src/benchweave/presentation/classref.py` and
  `benchweave_sdk/classref.py`) resolves terminal slugs GLOBALLY over
  the plan, so a composed derivation attaches one class's staging fields
  to the other class's button. Latent today — the shared actions' input
  schemas are identical (`acquisition_id`, `configuration_id`,
  `max_duration_ms`), so the wrong resolution emits identical bytes —
  and it becomes visible corruption the moment one class's
  shared-terminal action diverges in fields. Out of this slice: gating
  it would red six landed classes on a reading the owner has not ruled
  on; the fix (page-scoped resolution, or prefixing authored children —
  both derivations, SDK sync) is production motion this lane is
  forbidden to make. Reported for the owner's call.
- **Every pair composes two channels-kind slots; `_resolve_channels`
  takes the first** (`next(...)`), so the second class's channel lanes
  never render in a composed device. A derivation rule, not an
  identifier collision; the founding record does not address two
  capture classes composed. Reported.
- **`expect.components` merges by overwrite** — component count
  expectations from later classes clobber earlier ones (`panel`,
  `mode-banner`, `data-table` shared by all eight). Harmless while the
  SDK gate renders one class at a time; reported.

## 5. Normative surfaces

- The family README (`standards/plugin-ui-class-reference/0.3.0/`)
  gains a normative section stating the requirement: compose with every
  other class; never author an identifier in another class's prefixed
  namespace (`otdp-<class>-…`); the gate enforces it for every pair.
  The README is not corpus-pinned (the manifest pins the two schemas
  and the eight class files only) — no repin rides this slice.
- The device-authoring instructions (issue #499) must carry the
  requirement for human and AI authors. #499's page does not exist yet
  at this slice; recorded in the lane report for the docs leg, per the
  dispatch — not invented here.

## 6. Acceptance rules (pre-committed)

1. Every unordered pair of the active family's classes composes through
   the real `select_references` + `_merge_references` with zero
   identifier findings — on THIS base: 8 classes, 28 pairs, stated by
   assertion not literal.
2. A deliberately colliding class passes `validate_reference_document`
   and is silently accepted by the bare merge (premise), and is REFUSED
   by `composition_findings` with attribution, from the new-class side
   (direction 1) and the edited-existing side (direction 2), and under
   either sort order.
3. A clean synthetic class composes with all existing classes with zero
   findings (specificity).
4. The refusal arms fail against a neutralized detector (RED-sanity).
5. FAST lane green; full battery green except exactly the four known
   `tests/standards/test_check.py` served-set window failures, which
   clear at the batch promotion and are not weakened.

## 7. Tier statement (Step 1, rule #254)

**Tier 3.** The diff touches `standards/` (the family README) — first
match on the path rule; the standards-governor pass is owed at review
time regardless of tier. Keyword scan over the actual committed diff
(design record, census extension, test module, README — the whole
diff, docs and code alike):

- `threading` 1 · `asyncio` 1 · `subprocess` 1 · `sha256` 1 ·
  `hashlib` 1 · `migrate` 1 · `recovery` 1 · `protection` 1 — every
  occurrence is THIS section's own enumeration line (the Step-1
  self-fire the rubric states as intended: "the diff carries the
  keywords by construction"). The code, test and README surfaces of
  the diff carry all eight keywords **0** times (measured with the
  design record excluded).

The tier is path-derived and would stand unchanged at zero keyword
hits; the self-fire adds nothing material.
