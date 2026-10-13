# Issue #446 — invoke binds UI targets to corpus profiles only (design record)

**Date:** 2026-10-12
**Branch:** `feat/issue446-invoke-profile-map`
**Issue:** madeinoz67/benchweave#446 (`gateway`)
**Verdict:** BUILD — as two slices (a code-only parity fix, then the plugin-authored-profile
surface as a plugin-ui PATCH train), with the issue's second relaxation (the class-apparatus
separation) **deferred with a designed sketch and a named reopen trigger** (§6, D1). Two
premise corrections and one latent production defect surfaced by the localization are part
of the result (§1, §2).
**Review tier (design-time call, rubric #254):** **Tier 3** — the slice-2 build diff touches
`standards/` and moves a normative plugin-ui machine row (`src/benchweave/presentation/contracts.py`
is plugin-ui 0.3.0's live code object); the standards-governor mandate applies. Slice 1 is
path-Tier 2 (`src/benchweave/interfaces/`) but its expected diff text carries `sha256`/`hashlib`
in the test arms, so the keyword rule lifts it to the Tier-3 lane; the record's own commit is
docs-only by path and Tier 3 by the same keyword rule. Keyword-scan fixed-point counts in §11.

---

## 0. Summary

A plugin can already declare its own action profile — as a pinned, catalog-shaped contract
document the gateway's load-time resolution **fully accepts today** (verified empirically,
§2.3). What it cannot do is get a UI surface on that profile: the presentation checker's
profile map draws only from the trusted-host corpus document set, so a UI target must bind a
corpus class profile and a corpus action, forcing every presentation-bearing plugin to buy a
corpus class identity it may not want. Separately, the gateway's own device page feeds the
validator a document set so narrow (plugin-ui schemas only) that **every shipped
invoke-kind target is invalid there** — a latent parity defect this localization found and
slice 1 fixes.

The mechanism is small because the checker is already document-set-driven: the profile-map
comprehension unions whatever documents it is given. The fix threads the descriptor's
digest-pinned contract documents into that set at both call sites (SDK `check-ui`/standalone
host; gateway device page), adds one namespace-integrity check (divergent duplicate profile
ids refuse) plus one merge-time guard (a pinned document's embedded `$id` may not shadow a
corpus schema id), and amends the plugin-ui prose. No OTDP machine bytes move in slices 1–2;
the deferred apparatus separation is the only OTDP-schema motion, and it waits for a real
consumer.

## 1. Localization — both constraints, with the code that decides them

### 1.1 Constraint 1 — the profile map

The refusal the issue names is emitted by `_target_findings`, the invoke-branch target
check shared byte-for-byte by the gateway and the SDK's vendored validator:

- `src/benchweave/presentation/contracts.py:388` (`_target_findings`), profile map at
  `:435–451`; SDK vendored copy `src/benchweave_sdk/standards/plugin-ui/contracts.py:435`
  (standalone SDK checkout; the gateway's `packages/sdk` submodule is deinitialized locally
  by directive).
- For a target of kind `configuration`, `procedure` or `dataset`, the check requires:
  `action_id ∈ descriptor.actions`, `"invoke" ∈ descriptor.capabilities`,
  `target.profile_ids ⊆ descriptor.profiles`, **and** every named profile must exist in a
  `documents`-sourced profile map with the action in `required_actions ∪ optional_actions`.
  Failure is one `capability_mismatch` finding, path `targets.<id>`, message
  "Target exceeds descriptor capabilities".

`documents` is `dict(schema_documents)` plus `$id` aliases and per-action
`input_schema`/`output_schema` subschemas (`validate_presentation`, `contracts.py:611`,
document construction at `:640`). **The corpus-only behavior is an artifact of the call
sites' document sets, not a rule inside the checker:**

- **SDK** — `benchweave_sdk/presentation.py:53–65` (`schemas()`) = `contract_documents()`
  (validation.py:126) = every `.json` of every lock-carried standard (OTDP catalog and
  measurement schema included). This is the checker that refused the issue's plugin
  (`benchweave-sdk check-ui`).
- **Gateway** — `src/benchweave/interfaces/ui_presentation.py:71` (`_plugin_ui_schemas`)
  globs only `standards/plugin-ui/<active>/*.schema.json`. Four documents. No OTDP catalog,
  no measurement schema.

**Latent production defect (found by this pass, empirically reproduced):** under the
gateway's document set the profile map is empty and the OTDP measurement urn is
unresolvable, so **every** `dataset`/`configuration`/`procedure` target — including the
in-tree `sim_scope` attachment's own configuration target — composes INVALID on the gateway
device page (`capability_mismatch` + `unresolved_reference`), while the same bytes validate
on the SDK host. That is a parity violation of PRD 11's SW-41 rule ("the same bytes the SDK
host validates with"). `compose_device_presentation` (`ui_presentation.py:168`) is the only
production caller of `presentation.admission.validate_attachment`; nothing pins it with a
dataset/configuration target today (the G2 tests exercise observation targets only), which
is why it has not been seen. `_plugin_ui_schemas` was born in the G2b landing (PR #368,
commit `13faaec9`) and was never revisited — no recorded decision narrows the set.

### 1.2 Constraint 2 — the class apparatus

- `standards/otdp/0.2.2/otdp-device-descriptor.schema.json`, the `invoke` conditional
  (`allOf` index 29; required list at schema lines 2993–2997, feature containment at
  3011–3022): `capabilities ∋ invoke` ⇒ top-level `channels`, `profiles`, `contracts`,
  `actions` all required, `integration.mode = adapter`, `operations.invoke` required, and
  `required_features` must contain **both** `otdp.profile_actions/0.1.0` and
  `otdp.measurement/0.1.0`.
- Prose: `otdp-specification.md:47` and `extension-contract.md:11,21` tie both features to
  class integrations whose profile ids "resolve in the pinned catalog".
- **Nothing in gateway or SDK runtime code consumes `otdp.measurement/0.1.0` as a gate.**
  The census (`control/documents.py:856` gateway mirror; SDK `validation.py:410`) only
  refuses *unknown* `otdp.*` ids; omitting a known one is unchecked. The runtime's actual
  invoke requirements are structural: the pinned contract pair resolves
  (`registry/otdp_contracts.py::resolve_otdp_contracts` — exactly one catalog-schema-valid
  catalog plus the measurement schema, `contract_multi_catalog`/`contract_multi_measurement`
  refusals otherwise), the action resolves in that pinned catalog (bridge gate I3,
  `host/otdp_bridge.py:719` `_invoke_gate`), and a dataset-shaped result must have been
  published (`_convert` + `dataset_services.py::is_dataset_shaped` — the R2
  "publication lie" poison).
- On "returns datasets inline without a dataset service": the corpus's own rule is the
  opposite of inline (`extension-contract.md` §3: "Inline datasets also go through
  `dataset_publish`; small data is not exempt from semantic validation"). What is genuinely
  inline-legal today is a **non-dataset** plain-object result, validated against the pinned
  catalog action's `output_schema`. The legitimate relaxation is therefore not about the
  dataset lane at all — it is about plugins whose actions never produce datasets being
  forced to declare the measurement feature and pin the measurement schema (§6, D1).

### 1.3 What the runtime already admits (the premise correction that shrinks this design)

`resolve_otdp_contracts` validates each pinned document's **shape** (catalog schema) — not
its provenance. A plugin-authored, catalog-shaped profile document pinned in
`descriptor.contracts` resolves today, compiles its actions, and dispatches. Verified
empirically against the real device plugin's own action set, reshaped to catalog form with
`output_schema`/`lifecycle` added: resolution returns a full class surface (five
plugin-authored actions compiled); the plugin's actual free-form profile document (no
`catalog_version`, `profile_id` instead of `profiles[]`, `output_summary` instead of
`output_schema`) refuses at load with `contract_schema: … 'output_schema' is a required
property`. So:

- **OTDP does not forbid plugin-authored profiles.** The pinned-catalog mechanism is the
  intended carrier, and one catalog per descriptor is the load-time limit (the NIT-2
  ambiguity closure).
- **Only the presentation seam is corpus-blind.** The issue's Constraint 1 is a
  presentation-checker + call-site defect, not a standards gap in the binding rule's
  machinery.

A second premise correction: the issue's evidence plugin ships *both* a plugin-authored
profile and a corpus class profile because only the corpus one binds. Under this design its
own profile binds directly and the corpus class surface becomes optional — the acceptance
metric (§9 M-A) is exactly that state, with the corpus duplicate removed.

### 1.4 Prose/enforcement gaps found on the way (disclosed, not silently fixed)

- `extension-contract.md` §2.1 says profile ids are "listed in required_features"; no schema
  or checker enforces it, and the real plugin's descriptor omits them (as does nothing in
  the in-tree corpus examples' enforcement path — the class examples do list them). Enforcing
  it now would refuse the issue's own descriptor — a MINOR-class tightening. Fork F3 (§13).
- The SDK document set carries multiple OTDP versions whose **action** definitions diverged
  (12 actions differ between the carried 0.2.0 and 0.2.2 catalogs; profile rows are
  identical, 12/12). The `documents` construction aliases action schemas by `$id`
  last-wins — a pre-existing residual, not created here. D2 (§6).
- `descriptor.profiles` membership against the pinned catalog (C01/C02 prose) is enforced
  nowhere on the gateway load path — only the presentation check and the census look at
  profiles at all. This design's namespace check (§3.2) partially closes it at the
  presentation seam; full admission-side C01/C02 enforcement is D3.

## 2. Empirical verification performed in this pass (all against the worktree's own code)

Using `src/benchweave/presentation/contracts.py` directly with the real device plugin's
bytes (descriptor, presentation envelope, manifest, binding catalogue, ui assets) and the
real `standards/` corpus:

| Arm | Document set | Target binding | Result |
|---|---|---|---|
| A | SDK-style (full corpus) | as shipped (corpus class profile + corpus fetch action) | **valid** |
| B | SDK-style | rebound to the plugin's vendor profile + its own capture action | **invalid** — `capability_mismatch targets.capture` (Constraint 1 reproduced) |
| C | gateway `_plugin_ui_schemas()` (4 plugin-ui schemas) | as shipped | **invalid** — `capability_mismatch` + `unresolved_reference` (the parity defect, §1.1) |
| D | SDK-style + the plugin's pinned catalog (reshaped to catalog form) merged at the call site | the same rebound as B | **valid** (the mechanism works with zero checker change) |
| E | same as D | action present in `descriptor.actions` but in **no** validated profile | **invalid** — `capability_mismatch` (the negative control holds: binding stays profile-sourced) |
| F | same as D, but the pinned document re-declares a corpus profile id with divergent rows, target binds it | — | **valid** — silent shadowing (the hole §3.2 closes; today's comprehension keeps the last-seen row) |

Also verified: the `sim_scope` in-tree attachment is invalid under the real
`_plugin_ui_schemas()` (arm C shape, production path `ui_read.device_page →
compose_device_presentation`), and catalog-shaped plugin profiles resolve through
`resolve_otdp_contracts` (§1.3). Arms D–F are the design's proof-of-mechanism; the build
lands them as permanent RED→GREEN tests with invented fixture identities.

## 3. The mechanism

### 3.1 Slice 1 — the gateway document-set parity fix (code-only, no standards bytes)

`src/benchweave/interfaces/ui_presentation.py`: `_plugin_ui_schemas` becomes
`_presentation_documents()` — plugin-ui `*.schema.json` (active version, keyed by `$id` as
today) **plus** every `*.json` under every served `standards/otdp/<version>/` directory,
keyed by both a path-shaped key (`otdp/<version>/<file>`, mirroring the SDK's
`contract_documents` keying) and `$id`, with the per-action `input_schema`/`output_schema`
expansion the SDK's `schemas()` already performs. All carried version directories are
served, not just the active one: a descriptor pinning an older carried OTDP version has a
version-suffixed measurement urn (`urn:otdp:measurement:0.2.2` et al.) that must resolve —
matching the SDK host. RED test: `compose_device_presentation` over the `sim_scope`
attachment (admitted documents + descriptor bytes) returns `valid=True` (RED today — arm C);
a companion arm asserts the OTDP catalog is in the served set and that a fabricated
plugin-ui-colliding `$id` still refuses. Tests live beside the existing
`tests/interfaces_ui/test_ui_presentation.py` arms.

### 3.2 Slice 2 — plugin-authored profiles back UI targets (the plugin-ui PATCH train)

**Checker (corpus-owned, moves with the plugin-ui bump).**
`src/benchweave/presentation/contracts.py::_target_findings` — the profile-map
comprehension gains duplicate detection: a profile id declared by two documents in the set
with **divergent rows** yields a new finding `profile_shadow` (path `targets.<id>`,
message naming the id); identical duplicates (the corpus's own multi-version copies —
verified identical, §1.4) remain benign dedup. No new parameter on
`validate_presentation`: the document-set composition stays the caller's contract, now
amended in the prose. The `documents` `$id`-alias loop (`validate_presentation` `:640`)
stays as is — the merge-time guard below keeps pinned `$id`s out of collision with it.

**SDK (repo: benchweave-sdk).**
`benchweave_sdk/presentation.py` — a new helper `pinned_contract_documents(descriptor_raw,
package_root)`: parse the descriptor, enumerate `contracts` entries, read each path
package-relative through the existing bounded symlink-safe `read_file`, refuse on
sha256 disagreement with the pin (CON-1's family discipline; the #443 decoder-declaration
admission posture — digest + schema, no operator commissioning, the asymmetry recorded in
the docstring), validate catalog-shaped entries against the vendored
`device-profile-catalog.schema.json` of the descriptor's pinned OTDP version, and return
them keyed `pinned:<contract id>`. **Merge guard:** a pinned document whose embedded
`$id` (its own or any action schema's) equals a corpus-served `$id` refuses with
`pinned_id_shadow:` — a planted catalog re-declaring the ui-manifest schema id must not
become the schema the envelope validates against (the poisoning vector; RED test arm).
`validate_presentation`/`check_ui` and the standalone host's loader compose
`schemas() | pinned_contract_documents(...)`. The standalone preview host gets the same
composition so authoring-time and preview-time agree.

**Gateway.**
Admission side: the device-admission flow that `put_document`s the descriptor
(`interfaces/bootstrap.py` `content_sha` loop) additionally admits each pinned contract
document (digest-verified from the same package/lattice bytes the registry verified,
schema id `urn:otdp:profile-catalog:<pinned version>` for catalogs / the measurement urn
for measurement schemas) — the store stays the honest intermediary of admitted bytes.
Read side: `compose_device_presentation` parses the descriptor, takes
`contracts[].sha256`, queries the store for rows with those digests, and merges them into
`_presentation_documents()` under `pinned:<id>` keys with the same merge guard. Absent
rows (a descriptor whose pinned documents were never admitted) degrade loudly: the
attachment composes invalid with `unresolved_reference`, never a partial validation —
matching the module's existing honest-unvalidatable posture.

**Prose.**
`standards/plugin-ui/0.3.1/README.md` (copy-never-move from 0.3.0): §"Action targets
identify a declared action and the profiles which supply it" gains the supply rule —
profiles are supplied by the trusted-host corpus **or** by the descriptor's admitted
pinned contract documents; divergent duplicate profile ids refuse (`profile_shadow`); a
pinned document may not shadow a corpus schema id. The catalogue-trust paragraph's "The
catalogue and schema corpus come from the trusted host" is amended to name pinned
contract documents as caller-verified additions. `standards/otdp/0.2.2/extension-contract.md`
(companion prose — **no bump**, GOVERNANCE's prose row): §2 names plugin-authored pinned
catalogs explicitly and states the namespace rule — `otdp.*` profile ids in a
plugin-pinned catalog must reproduce the pinned corpus version's rows exactly (identical
duplicates are benign; divergence refuses), and vendor-namespaced profile ids live outside
`otdp.*` per §1's corpus-owned-namespace rule.

**Authoring consequence (the issue's acceptance).** The plugin folds its profile document
into catalog shape (`catalog_version`/`otdp_version` consts, one `profiles[]` row with
`required_actions`, per-action `input_schema`/`output_schema`/`side_effect`/`lifecycle`),
keeps the measurement-schema pin, and binds its UI targets to its own profile and actions.
A plugin wanting corpus class surface **and** vendor surface in one descriptor copies the
needed corpus rows verbatim into its catalog (the identity rule makes that benign and
drift-checked); two separate catalog documents stay refused (the NIT-2 closure). The
four-document merge is fork F4's deferral.

### 3.3 What does NOT move

- `otdp-device-descriptor.schema.json`, the runtime catalog, the measurement schema, the
  bridge, the loader, `resolve_otdp_contracts` — zero bytes (the runtime already behaves
  as the presentation seam must learn to).
- REST/MCP/openapi/operation-catalog — presentation validation is not an interface
  operation (A13 untouched).
- The `one catalog per descriptor` load-time limit; the invoke gates I1–I5; the dataset
  publication rule.
- `standards/plugin-ui` schemas themselves — no `ui-manifest.schema.json` change: the
  `target` def already carries `profile_ids` as opaque ids; the supply rule is prose +
  checker semantics.

## 4. Minimal first increment

**Slice 1** (one gateway PR): the parity fix + RED test. No train, no standards bytes,
lands immediately.

**Slice 2** (the train, gateway repo first per the 0.2.2-landing shape):
1. `docs(design)` — this record (already committed before any measurement, the
   pre-commitment ordering).
2. `test(presentation)` — RED: arms D/E/F of §2 as permanent fixtures with invented
   identities (`vendor.la34/1.0.0`-form profile id, catalog-shaped pinned document,
   plugin-profile-bound target; the no-profile-action negative; the divergent-shadow
   control; the `$id`-shadow merge guard).
3. `feat(standards)` — plugin-ui 0.3.1: copy-never-move, the contracts.py mechanism
   (`profile_shadow`), README/MIGRATION prose, validation-report regen, manifests in-arc,
   repin (the `plugin-ui/contracts.py` corpus row), export, docs sweeps
   (obligations 3, 13, 18, 20, 21 — the executable-literal sweep covers `SCHEMA_ROOT`).
4. Gateway code: bootstrap admission of pinned documents + `compose_device_presentation`
   wiring + the merge guard.
5. SDK repo (own PRs, the #408 order): vendored sync at 0.3.1, `pinned_contract_documents`
   + `check_ui`/host composition, SDK tests; SDK release cut; gateway pointer PR
   (gitlink + pin in one commit).

## 5. Precedent citations

- **Document-set-driven validation:** the checker's own `documents` construction
  (`contracts.py:640`) — this design changes what callers compose, not the checker's
  contract-shape.
- **Digest-pinned plugin documents at a lighter-than-commissioning posture:** the #443
  decoder-declaration family (`.claude/deep-review/2026-10-12-issue443-decoder-output-contract-design.md`
  §3.2 — "digest + schema + semantic checks, with no operator commissioning step; the
  asymmetry recorded"); the transport-provider `{id, path, sha256}` triple
  (extension-contract §6) for the pin shape; `resolve_otdp_contracts` itself as the
  load-time admission this design mirrors at the presentation seam.
- **Store-mediated admitted bytes:** `compose_device_presentation`'s existing
  `_documents_by_schema_suffix` + digest joins for envelope/manifest/catalogue — the
  pinned-catalog join is the same pattern keyed on `contracts[].sha256`.
- **The corpus-row-copy allowance:** corpus-manifest rows are public and digest-frozen;
  `sim_scope` already vendors the corpus catalog verbatim (`plugins/benchweave/sim_scope`),
  the established shape.
- **Bump-class:** GOVERNANCE's additive-errata PATCH row and `a103a4cf`'s refused-none
  template — plugin-ui 0.3.1 admits new inputs (pinned-document-bearing validations) and
  refuses none: a 0.3.0-valid document set without pinned documents behaves byte-identically
  (identical-duplicate dedup never fires on corpus-only sets; the merge guard fires only on
  inputs corpus-only sets cannot contain). Falsifier stated in advance: any 0.3.0-valid
  presentation that 0.3.1 refuses flips the class to MINOR.

## 6. Deferrals (each with home + reopen trigger)

| # | Deferral | Home | Reopen trigger (observable) |
|---|---|---|---|
| D1 | **The class-apparatus separation (Constraint 2).** Sketch: split the invoke conditional — `invoke ⇒ profiles/contracts/actions/profile_actions` always; `otdp.measurement/0.1.0` required iff a `urn:otdp:measurement:*` contract pin exists (both directions: feature-declared-but-unpinned is a lie); loader accepts catalog-only resolution (controller with the dataset half absent); bridge dataset lane attaches conditionally. | this record §1.2/§6; OTDP schema + prose + `otdp_contracts.py` + `_invoke_gate` | a real pure-action plugin (invoke actions that never produce datasets) arrives on the tracker, or the owner calls for the apparatus slimming; benefits no in-tree plugin today (the issue's own plugin produces datasets and pins the pair) |
| D2 | Cross-version action-schema duplicates in the SDK document set (12 diverged actions across carried 0.2.0/0.2.2; `$id` last-wins) | SDK `schemas()` docstring (disclosed residual) | a check-ui result turns on which carried version's action schema won — a filed repro |
| D3 | Admission-side C01/C02 profile-membership enforcement (descriptor profiles vs pinned catalog rows; §1.4's third gap) | extension-contract §2 checks table | a descriptor claims a profile its pinned catalog does not carry and something consumes the claim — a filed mismatch |
| D4 | Corpus+vendor two-catalog pinning (merge with enforced action-id disjointness) | this record §3.2 (the one-catalog rule stays) | a plugin's copied corpus rows drift-check cost exceeds one bump's patience — a tracker issue from a plugin author maintaining the copy |
| D5 | A UI target kind for non-dataset inline action results (plotting plain invoke outputs) | plugin-ui backlog | a plugin asks to visualize inline results in a dataset page — a tracker issue naming the surface |

## 7. Invariant impacts (A01–A14 walk)

- **A02:** untouched — no numeric envelope; pinned documents are declarations.
- **A04:** untouched — no protective transition, lease or deadline change; nothing here
  needs judgement to stay safe (the shadow checks are mechanical).
- **A05:** plugin trust boundary respected — plugin-authored profile documents enter as
  *data*, digest-pinned and shape-validated, gating presentation binding only; the same
  documents already gated runtime dispatch (the load-time precedent). No plugin-authored
  code or schema becomes authority: the merge guard keeps corpus `$id`s unshadowable, and
  `validate_attachment`'s "successful validation grants no execution authority" stands.
- **A06:** the shadow finding refuses divergence and names the id — no ambiguity laundered.
- **A10:** bounded classes preserved — vendor profiles are not new corpus families; the
  `otdp.*` namespace stays corpus-owned (the namespace rule is the amendment's payload).
- **A12/A13:** untouched; no transport motion — the strongest signal the seam is right.
- **A14:** nothing.
- **CON-1 gains an amendment:** pinned contract documents entering the presentation seam
  follow the exact-byte digest discipline (`pin_absent`/digest-refusal prefixes) — already
  the load-time behavior, now stated for the presentation path (amendment text lands with
  slice 2, evidence: arms D/E/F).
- **CON-7/CON-11/CON-14:** move mechanically with the plugin-ui bump (repin-only row
  motion; report regen; the matrix renders from committed state).
- **REG-4:** the SDK sync keeps the three-way pin green; the `check-sdk-standards` gate
  runs immediately after the export (the 0.2.2 train's own check).
- CTL/STO: untouched. No new invariant beyond the CON-1 amendment: the shadow rule is a
  plugin-ui conformance check carried by the checker and its tests, the S19/M15-as-corpus-
  checks model.

## 8. Cross-surface obligations (drift-and-obligations walk)

3 (device-developer-guide: authoring plugin-authored profiles in catalog shape — new
section), 5 (fixture lattice — new presentation fixtures ride the test tree; no registry
lattice motion), 6 (vendored contract bytes — the plugin-ui row via repin only), 7 (SDK
pointer, the #408 order), 12 (renderer surface — no renderer change; preview host composes
the same set), 13 (plugin-ui validation-report regen), 18 (version-bearing surfaces —
README stamps, MIGRATION), 20 (executable-version-literal gate — `SCHEMA_ROOT` sweeps with
the bump), 21 (dependency-policy block + carried set). CI cost: no new lanes; new tests
ride the existing unit/interfaces suites; the SDK release + pointer PRs are the only
pipeline additions (the established train cost).

## 9. Measurable proof — pre-committed acceptance rule

Metrics fixed before any number is looked at (all are boolean/directional; the effect
sizes are the arms themselves):

- **M-A (the issue's acceptance):** the real device plugin's specimen (anonymized fixture
  identity) — profile document in catalog shape, pinned as the descriptor's contract,
  UI target bound to the vendor profile + the plugin's own capture action —
  `benchweave-sdk check-ui` reports **valid**, with the corpus class profile and the
  corpus class actions **removed** from the descriptor and binding catalogue. RED before
  the fix: arm B (reproduced this pass).
- **M-B (negative control):** a target naming an action that exists in
  `descriptor.actions` but in **no** validated profile (corpus ∪ pinned) still refuses
  `capability_mismatch`. Reproduced this pass (arm E) — it must stay red after the fix.
- **M-C (shadow control):** a pinned document re-declaring a corpus profile id with
  divergent rows refuses `profile_shadow` (RED today: arm F — it validates). Companion:
  the planted-`$id` merge-guard arm refuses `pinned_id_shadow`.
- **M-D (parity/no-regression):** the `sim_scope` attachment composes **valid** on the
  gateway device page (RED today: arm C); every existing presentation test green; a
  corpus-only document set behaves byte-identically to 0.3.0 (no new findings on any
  existing fixture).

**SHIP if** M-A, M-B, M-C, M-D all hold with the mechanism exactly as designed
(call-site composition; divergent-duplicate refusal; no binding beyond validated profiles).

**KILL if** the only way to pass M-A is to weaken M-B (binding must be profile-sourced —
if plugin-profile binding only works by letting targets bind unvalidated actions, the
mechanism is wrong, not the tests); or M-C's refusal cannot distinguish benign
multi-version duplication from shadowing (fires on M-D's corpus-only sets — then the
document-set union is the wrong composition point and the design restarts from a
validator-side pinned parameter); or M-D regresses any existing fixture (the bump flips
MINOR and the regression is a finding, not a fold).

**UNDERPOWERED if** the specimen set is the one plugin — single-specimen risk sits on the
authoring ergonomics (catalog-shape burden: `output_schema` + `lifecycle` per action), not
on the refusal directions (M-B/M-C pin those). Remedy named in advance: author a second
specimen — a configuration-action-only plugin with no dataset surface — before judging
ergonomics; if that specimen needs D1's relaxation to express itself, that is the D1
reopen trigger firing, not a design failure here.

## 10. Top risks, each with its falsifier

1. **Schema-resolution poisoning via pinned documents.** A pinned catalog's embedded
   action-schema `$id`s enter the resolution registry; a colliding `$id` could shadow a
   plugin-ui schema. Mitigated by the merge guard (§3.2); falsified by a planted-`$id`
   arm that gets past it. Residual: colliding `$id`s *within* the pinned set (two pinned
   documents aliasing one id) — covered by the same guard's pairwise form; the arm
   includes it.
2. **The shadow rule over-fires** on legitimate corpus multi-version duplication.
   Falsified by M-D; pre-checked this pass (12/12 profile rows identical across carried
   versions). If a future corpus bump diverges a profile row across carried versions, the
   rule fires honestly — that collision becomes a finding to resolve, not a silent pick.
3. **Store-join drift on the gateway** (admitted pinned documents vs descriptor pins).
   The join is on `contracts[].sha256` against store digests — the same bytes the
   registry verified; a missing row degrades loudly (`unresolved_reference`), never
   partially. Falsified by an arm admitting a descriptor whose pinned rows are absent.
4. **The one-catalog limit taxes mixed-surface plugins** (corpus rows copied verbatim).
   Disclosed (D4); falsified as a maintenance burden only when a real author complains —
   the drift check makes copies safe, not free.
5. **The record's "nothing consumes the measurement feature" claim** is load-bearing for
   D1's framing. Falsified by any runtime consumer appearing (grep `otdp.measurement`
   over `src/` at build time re-derives it; a consumer turns D1's sketch into a
   compatibility analysis first).

## 11. Review tier and the Step-1 keyword scan

**Tier 3** (maximum across slices): slice 2 touches `standards/` and a JSON-Schema-adjacent
normative machine row (the plugin-ui live code object) — path rule; the standards-governor
pass is mandatory; two-lane adversarial refute per the Tier-3 doctrine. Slice 1 is path
Tier 2 (`src/benchweave/interfaces/`) lifted to the Tier-3 lane by keyword hits
(`sha256`, `hashlib`) in its expected test text. This record's own commit is docs-only by
path and Tier 3 by the keyword rule (its text carries `sha256` substantively — the pin
discipline is the mechanism).

**Keyword scan (the eight Step-1 words, word-boundary counts over this record's final
committed text — a fixed point: this section and the tier paragraph above quote the
keyword names themselves, and those self-references are the rubric's intended
self-fire):**
`threading` 1, `asyncio` 1, `subprocess` 1, `sha256` 10, `hashlib` 4, `migrate` 1,
`recovery` 1, `protection` 1. Substantive hits outside the self-references: `sha256`
(the mechanism's own pin discipline — contract pins, digest joins, the merge guard) and
`hashlib` (slice-1's expected test arms). The build lanes re-run the scan over the real
diffs and report actual counts; the tier cannot drop below 3 either way.

## 12. Train recommendation

- **Slice 1:** no train — code-only, lands on its own PR against main, linked to #446.
- **Slice 2:** one plugin-ui PATCH bump (0.3.0 → 0.3.1), its own release train, gateway
  repo first (standards motion + repin + export + code), then the SDK sync/release/pointer
  per the #408 order. **No OTDP machine motion** — the extension-contract prose is a
  companion-doc clarification (GOVERNANCE: no bump), so this train does not touch the
  #443-held OTDP 0.2.3 lane at all. Sibling-lane pre-flight (#181 R2) runs at build time:
  `git fetch origin` + remote-branch check over `standards/plugin-ui/` before the copy
  step, in case #444/#445 carry plugin-ui motions this pass could not see.
- **D1 (when reopened):** an OTDP PATCH that either joins the 0.2.3 train if #443's
  evidence gate is still open when it unblocks (one bump per (standard, train) — batching
  is the rule) or cuts 0.2.4 from the landed 0.2.3 — decided then, on the train state at
  that moment, not now.

## 13. Forks needing the owner's word

- **F1 — namespace-rule carrier:** prose + checker-code enforcement, no OTDP bump
  (recommended — the rule is a presentation-seam conformance check) vs a machine check
  family in the OTDP corpus (stronger, costs an OTDP PATCH and coordination with the
  #443-held window).
- **F2 — profile-ids-in-required_features:** leave the prose unenforced and disclosed
  (recommended — enforcing refuses the issue's own descriptor today, a MINOR-class
  tightening) vs enforce in the SDK checker + gateway mirror now.
- **F3 — one-catalog with corpus-row copying** (recommended, D4 holds the merge
  alternative) vs relaxing `contract_multi_catalog` to corpus+vendor with enforced
  action-id disjointness now.
- **F4 — D1 scheduling:** defer until a pure-action plugin arrives (recommended) vs
  design it into this increment as slice 3 despite no in-tree consumer.

---

*Localization evidence: all file:line anchors verified against this branch's tree on
2026-10-12; the empirical arms (§2) ran against the worktree's own validator with the
standards corpus of this branch. Gortex reads served the gateway repo; the SDK standalone
checkout is outside the daemon's indexed roots and was read natively (disclosed per-path);
the device-plugin tree was read natively as instructed.*

---

## 14. Fold-in addendum (2026-10-13 — slice 2 onto the plugin-ui 0.3.1 train)

1. **Train / one-bump.** Slice 2 lands on the plugin-ui 0.3.1 bump that the
   #444 commissioned-preset train already cut on
   `feat/issue444-commissioned-preset-firmware` (fc6a0d63): the 0.3.1 tree,
   corpus rows, served range and version-literal sweep are done. This rider
   cuts NO second bump — the `profile_shadow` checker semantics, the
   pinned-`$id` merge guard and the prose amendments ride 0.3.1 in place.
   The PATCH class still holds: `profile_shadow` fires only on divergent
   duplicate profile declarations, which a corpus-only 0.3.0-valid document
   set cannot contain (§2 verified the carried catalogs' profile rows
   identical; re-verified 2026-10-13 for `otdp.dc_psu/1.0.0` between the
   carried 0.2.0/0.2.2 catalogs), so the §5 falsifier ("any 0.3.0-valid
   presentation that 0.3.1 refuses flips the class to MINOR") does not trip.

2. **Slice-boundary ruling at build time.** The gateway read-side
   composition (§3.2: "`compose_device_presentation` ... merges them into
   `_presentation_documents()`") requires slice 1's `_presentation_documents()`
   (§3.1), which is parked on `feat/issue446-invoke-profile-map` (967f00f5)
   and absent from the 0.3.1 train tip (fc6a0d63 serves `_plugin_ui_schemas`
   only). The same applies to the SDK leg (`pinned_contract_documents`,
   benchweave-sdk repo). These composition parts are STOPPED here; the
   landing order becomes slice 1 → slice 2. What lands in this arc: the
   `profile_shadow` check, the merge guard as a checker-level seam, and the
   corpus prose.

3. **Deviation (disclosed).** §3.2 places the `$id` merge guard inside the
   SDK helper and the gateway read side. This arc implements the guard as a
   checker-level function `merge_pinned_documents` in the live code object so
   the rule exists at exactly one enforcement point and both composition
   points compose through it when their slices land. Refusal surface:
   `DocumentError` carrying code `pinned_id_shadow` — the design's
   `pinned_id_shadow:` refusal prefix.

4. **`profile_shadow` semantics.** The §3.2 anchor `path targets.<id>` is
   read as: the finding fires for a target that BINDS a divergently-declared
   profile id — the binding is where the last-wins map makes the result
   order-dependent, and a shadowed id no target binds stays unobserved (the
   corpus sets have no divergent duplicates today, so this reading cannot
   over-fire on M-D's no-regression rule). Identical duplicates remain
   benign last-wins dedup, byte-identical to 0.3.0 behavior.

5. **Slate reference.** The train's 0.3.1 evidence record is
   `standards/plugin-ui/0.3.1/validation-report.md` (issue #444); this
   rider appends its own section there in the feat arc.
