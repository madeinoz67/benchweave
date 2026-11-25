# classref-coverage gate — design record (2026-11-24)

Lane: gateway standards-gap closure. Not the class sweep.

## The defect this closes

`otdp` declares device classes. `plugin-ui-class-reference` gives each declared
class a reference presentation. Nothing structural ties the two lists together:
`select_references` (src/benchweave/presentation/classref.py) is deliberately
fail-open — a profile with no reference is skipped and the plugin renders today's
no-attachment absence. So when `otdp` gains a class, the gap is invisible until a
plugin author hits it, then costs a release round trip.

Measured on the tracked tree at this record's date:

- `standards/otdp/0.2.4/device-profile-catalog.json` declares **12** profiles.
  The lane brief says 13; 13 counts `examples/class-action-vectors.json`, which
  is a vectors file and not a class. Twelve is the number the catalog's own
  `profiles` array carries and the one `device-classes.md` states ("Twelve
  explicitly defined device classes").
- `standards/plugin-ui-class-reference/0.6.0/` carries **8** class references.
- Missing: `embedded_controller`, `switch_matrix`, `spectrum_analyser`, `vna` —
  the same four the brief names.

## Where the rule lives, and why not the alternatives

**Home: `src/benchweave/standards/coverage.py`, composed into the `check` verb.**

| Candidate | Verdict |
|---|---|
| `standards/cross-constraints.json` | **No.** G-4 defines it as a compatibility-window/evidence table: a row names one released version and what it requires of others, and REQUIRES citable evidence a reviewer can locate. Its own note treats a missing row as a deliberate honest negative. A completeness assertion is a total map over a catalogue, carries no pairwise evidence, and is enforced by `dependency.py` at *resolve* time — after the gap has already reached a consumer. Placing it there would also require inventing evidence for a rule that needs none. |
| A new CLI verb | **No.** CI's `gates` job runs `make check-sdk-standards`, which runs `benchweave.standards check` and `matrix --check`. A verb nobody invokes is a rule nobody runs — the known finding this lane is asked to avoid (an enforcement that lives only in a gitignored `.claude/settings.local.json`). |
| `run_check` (inside the module) | **No.** `tests/standards/test_check.py` drives `run_check` over synthetic roots that carry no otdp corpus; folding the rule in would force every synthetic fixture to satisfy it or force a silent skip. Silent skips are the failure mode. |
| **The `check` verb, composed beside `run_check`** | **Yes.** `src/benchweave/standards/__main__.py` is tracked, the CI job invokes it, and composition leaves `run_check`'s SDK-mirror contract intact. Verifiable from the tracked tree: the rule is Python under `src/`, run by a tracked Makefile target, from a tracked CI workflow. |

## The register is the existing sweep plan

`docs/internal/classref-sweep-plan.json` (tracked, not digest-pinned) is a
machine-readable record already read by `scripts/assemble_docs_site.py`, whose
shape validator refuses when the file is absent. It names exactly the four gaps
as slots L18–L21.

The gate treats a row there as the recorded exception. **Why each of the four is
not built yet, in one sentence:** the class sweep delivers one class per
increment, each with its own design record, mockup and fixture lattice, in the
order recorded on 2026-10-14 (`…classref-logic-analyser-design.md`, L11–L21 row:
L18 `embedded_controller`, L19 `switch_matrix`, L20 `spectrum_analyser`,
L21 `vna`); `embedded_controller` is the live "unwritten class" exemplar three
test arms depend on, so batching all four would contradict the recorded order and
break the rotating-exemplar arms by construction.

The rule covers both directions that can lie about a class:

1. every profile in the active OTDP catalogue → a reference, or a sweep-plan slug;
2. every reference → a profile the catalogue declares (a stale reference renders
   for a class that does not exist).

Two shapes are deliberately NOT checked, both because they are the roadmap state
rather than a claim about delivery:

- **a plan row naming a profile otdp has not declared yet.** A plan is a roadmap
  and the docs site renders an unlanded row as
  "planned" — a slot legitimately precedes the class. It opens no silencing
  channel: a row covers only a gap whose slug already matches a declared profile.
- **a slug that is both referenced and planned.** The plan is APPEND-ONLY by
  design — the corpus wins for a slug both carry, so a class landing needs no edit
  to the shared file and parallel sweep lanes never conflict on it. Four surfaces
  teach it: `scripts/assemble_docs_site.py:756-758` (loader note),
  `scripts/assemble_docs_site.py:854-855` (the plan validator's own docstring),
  `docs/adding-a-device-class.md:37` and
  `docs/internal/drift-and-obligations.md:710-711`. This one cost a full round
  trip; see the removed-arm note under Proof.

The failure this prevents: a **new** otdp class with no reference and no plan row
reds `make check-sdk-standards` at the commit that adds it, instead of reaching a
plugin author.

## What the gate does not catch

**Presence and naming, not semantic content.** The gate asserts that a reference
EXISTS for a declared class and that it binds the right `profile_id` in the right
direction. It does not judge whether that reference is any good — its pages,
slots, `expect` block or `cannot_derive` rows. Those are the family schema's job
and the per-class arms' job (`tests/ui_html/test_classref_*`,
`tests/architecture/test_plugin_ui_class_reference_contracts.py`). A later reader
must not round this up to "coverage verified"; there is no such claim anywhere in
G-6 or here, and this paragraph exists so the rounding has somewhere to fail.

The same discipline as G-04's lesson: a gate that prints "passed" for checks it
never ran is worse than no gate, because it manufactures confidence.

## The declaration-surface limit (the logicport gap-audit finding, verified)

Two surfaces let a profile be NAMED outside `device-profile-catalog.json`:

- `standards/otdp/0.2.4/otdp-device-descriptor.schema.json` — `properties.profiles`
  is `{"type":"array","items":{"type":"string","minLength":1}}`; any string is
  declarable (verified at the file, not taken on report).
- `standards/plugin-ui-class-reference/0.6.0/composed-member-declaration.schema.json`
  — `profiles` carries exactly one `vendor_profile` row lifted verbatim from the
  catalogue's profile row.

Neither is a leak in THIS rule, and the distinction is the point: the rule asserts
a total map over the **catalogue's declarations**, not over every string a
consumer may write. The catalogue remains the sole authority for what an `otdp.*`
class IS — `resolve_otdp_contracts` compiles action validators from it, so an
uncatalogued class yields no action surface (`invoke` refuses UNSUPPORTED), and
`select_references` skips the unknown profile. A device claiming a nonexistent
class therefore gains nothing but a false label; it does not gain behaviour or a
rendering.

What the auditor's finding genuinely establishes is a gap on a **different
axis**: no admission check requires a descriptor's `otdp.*` profiles to exist in
the catalogue it pins. That deserves its own increment (an admission-surface
rule with its own design record and tests) and is recorded in G-6 as a stated
limit rather than folded in here, where it would make the coverage rule assert
something it does not check.

## Change class

**No standards version bump, and none is owed.** The batch moves no corpus
bytes:

- the rule is Python under `src/`, not a normative path;
- the register is `docs/internal/`, taxonomy class 10, not
  digest-pinned;
- `standards/GOVERNANCE.md` is prose, not digest-pinned (it carries no
  corpus-manifest row; verified: 369 rows, none matching).

The governing precedent is recorded twice: `dependency_policy` and the
`cross-constraints.json` side table are "governance data in this same family …
moving no corpus rows and needing no repin" (GOVERNANCE, G-3 and G-4). Zero
corpus rows → nothing to repin → no bump to take. Were a future batch to add the
missing references, that batch is **MINOR** under "new normative file within an
existing standard" (standing practice, twice run) and takes the highest change
class the batch contains (#69). One bump per release train, not per gap: gaps
landing in separate trains take separate bumps, which is the train rule working as
designed rather than a violation.

## Proof

Pre-committed acceptance rule: the gate is accepted when

1. it is green on the tracked tree as it stands (8 references + 4 planned slots
   against 12 declared profiles), via `make check-sdk-standards`;
2. it goes RED — a failure line naming the class — when (a) a catalogue profile
   gains no reference and no plan row, (b) a reference names an undeclared
   profile, (c) the sweep plan is absent, each mutated in a scratch copy and
   executed, with the observed result recorded — never predicted. Observed, in
   order: dropping the `vna` plan row gave
   `classref_coverage_missing: otdp.vna/1.0.0 …`; adding an uncatalogued
   `signal_source` class gave the same failure for it; binding a `ghost` profile
   gave `classref_coverage_stale`; deleting the plan gave
   `classref_coverage_plan_absent`; the unmutated scratch was clean;

3. TWO arms were BUILT, EXECUTED and REMOVED, and both removals are findings in
   their own right — recorded because the deletions are what stopped this gate
   becoming an obstacle:

   - `classref_coverage_plan_unknown`, refusing a plan row naming an undeclared
     profile. It fired as designed. Removed: the shape is legitimate — a slot
     names a class before it exists, and the docs site renders exactly that row
     as "planned".
   - `classref_coverage_plan_stale`, refusing a slug that is both referenced and
     planned. Built on a standards-governor MEDIUM that argued a standing row
     would cover a later deletion of the reference, and it fired when executed on
     the real corpus (a `dmm` plan row redded). Removed on that reviewer's own
     follow-up: the plan is APPEND-ONLY by design, taught in four live surfaces
     (`scripts/assemble_docs_site.py:756-758` loader note, `:854-855` the plan
     validator's own docstring, `docs/adding-a-device-class.md:37`,
     `docs/internal/drift-and-obligations.md:710-711`), so a landed class keeping
     its row is the intended state and the corpus decides delivery. The arm also
     reintroduced the shared-file write conflict the append-only rule exists to
     avoid: every sweep increment would have had to edit one shared file.

     The arm did buy one protection, and removing it reopens that case — stated
     here rather than left to inference: if a reference is deleted while its plan
     row stands, the gate is GREEN. The row covers the gap and the loss is visible
     only at that deletion's own review, a review-gated breaking corpus change
     (MINOR at least, copy-never-move, governor lane). A green run must not be read
     as "a class cannot lose its reference without a red".

     The reviewer's LOW (fix gate item 6's wording) presupposed its own cure —
     keep the arm and edit the four surfaces; under the arm-removal cure actually
     taken, that wording would have re-added the arm. The append-only evidence
     decided, not either proposed phrasing, and gate item 6 states the pair is
     valid;

   Both shapes now have a test asserting they are ACCEPTED, so the removals cannot
   creep back;
3. a no-regression arm holds the real tree green after every mutation is undone.
