# Issue #444 — OTDP presets refuse commissioned-firmware devices (design record)

**Date:** 2026-10-12
**Branch:** `feat/issue444-commissioned-preset-firmware`
**Issue:** madeinoz67/benchweave#444 (`gateway`)
**Verdict:** BUILD — a plugin-ui firmware-gate fix (fork b, policy-aware relaxation),
riding a plugin-ui version bump; **zero OTDP motion**, so no collision with the #443
OTDP 0.2.3 train. The issue's premise is corrected in §1 (the commissioned schema
PERMITS a firmware list; the defect is in the plugin-ui gate, not the OTDP schema).
**Review tier (design-time call, rubric #254):** **Tier 3** — the build diff touches
`standards/` and adds JSON Schema files under a new version directory (the path rule
fires before any keyword rule). The standards-governor mandate applies (any
`standards/` touch). Keyword-scan result in §11.

---

## 0. Summary

A device descriptor under `identity.firmware_policy: "commissioned"` cannot pass the
plugin-ui preset firmware gate — ever, on any surface. The gate
(`validate_preset`, plugin-ui contracts) demands a firmware value that is a member of
`identity.supported_firmware`; a commissioned descriptor carries no such list (the
corpus's own commissioned example has none), so the third conjunct of the gate is
unsatisfiable, and the only escape hatch in the code (`firmware_policy == "any"`) is
unreachable dead code — `firmware_policy` has been the enum
`["listed", "commissioned"]` in **every OTDP version ever in this tree**. Result: the
SDK `check-preset`/`check-ui` refuse, the gateway's presentation composition marks the
whole attachment invalid (the settings/preset UI dies), the standalone authoring path
refuses with "no firmware to judge the preset against", and the standalone apply path
refuses even with the device's established firmware in hand.

The fix is one semantic change in the one vendored gate, plus one small arm in the
SDK-server authoring helper: **the descriptor-side firmware membership applies only
where the descriptor declares a firmware list; under the commissioned policy a missing
firmware value is the honest offline posture (the bench's commissioned record is the
authority, re-gated at apply time against the preset's own declared list).** Because
the gate lives in the digest-pinned live code object (`contracts.py`, byte-identical
in the gateway and the SDK), any byte change is a plugin-ui standards bump — this
design is a standards train whether it wants to be or not (the #62 lesson: normative
entry points are trains in disguise).

## 1. Localization — where the rule lives (this decided everything)

The rule is owned by **plugin-ui**, not OTDP. OTDP owns the *descriptor-side*
vocabulary (`firmware_policy`, `supported_firmware`); plugin-ui owns the *preset
compatibility gate* that consumes both.

### 1.1 The gate

`src/benchweave/presentation/contracts.py:279-293` (`validate_preset`), byte-identical
twin at `packages/sdk/src/benchweave_sdk/standards/plugin-ui/contracts.py:279-293`
(verified identical by `diff` this session; the twin is the SDK's
`_GENERATED.txt`-marked vendored copy):

```python
if (
    firmware is None
    or firmware not in preset["supported_firmware"]
    or (
        identity.get("firmware_policy") != "any"
        and firmware not in identity.get("supported_firmware", [])
    )
):
    findings.append(Finding("incompatible_firmware", "preset.supported_firmware",
        "A known firmware compatible with the descriptor and preset is required"))
```

Diagnostic id `incompatible_firmware` is a plugin-ui code — documented in
`standards/plugin-ui/{0.1.0,0.1.1,0.2.0,0.3.0}/README.md` (the stable-codes
paragraph). The issue's refusal text matches the Finding message verbatim.

### 1.2 The enforcement surfaces (all four refuse a commissioned descriptor today)

| Surface | Site | Firmware source | Refusal mode |
|---|---|---|---|
| SDK `check-preset` | `packages/sdk/.../cli.py:303-333` (`--firmware` required) | author-supplied | gate conjunct 3 (`not in []`) |
| SDK `check-ui` | `cli.py:266-287` + `presentation.py::check_ui` | author-supplied optional | conjunct 1 when omitted, conjunct 3 when supplied |
| Gateway presentation composition | `src/benchweave/interfaces/ui_presentation.py:222-234` → `presentation/admission.py::validate_attachment` → `validate_presentation` → `validate_preset` | `identity.supported_firmware[0]` else `None` | conjunct 1 (`None`) — every preset finding ⇒ attachment invalid ⇒ settings/preset UI dead |
| Standalone server authoring | `packages/sdk/src/benchweave_sdk_server/authoring.py:404-418` (`_preset_firmwares`) + `421-464` (`_validated_preset`) | explicit → session-established → descriptor-declared | empty candidate list ⇒ `AuthoringError("no firmware to judge the preset against...")` |
| Standalone server apply | `benchweave_sdk_server/seam.py:1166-1274` (`_op_preset_apply`) | device-established identity firmware (refuses `not_ready` when absent) | conjunct 3 — even with real established firmware |

### 1.3 What the commissioned policy IS in the corpus

- Schema (`standards/otdp/0.2.2/otdp-device-descriptor.schema.json`, identity def
  ~1986-2050): `firmware_policy` enum `["listed", "commissioned"]`; `supported_firmware`
  is an **unconditionally permitted** property whose *requirement* is conditional — the
  `allOf` requires it only under `listed`. Nothing forbids it under `commissioned`.
- Prose (`standards/otdp/0.2.2/otdp-specification.md:43`): "`listed` requires exact
  supported firmware values. **`commissioned` requires a bench-maintained accepted
  identity/firmware record before control.**"
- Example (`standards/otdp/0.2.2/examples/reference-can.json`): the commissioned
  reference carries **no** `supported_firmware`.
- Every non-commissioned example declares `listed` + a list.

**Premise correction (the issue's claim "the identity schema offers no
`supported_firmware` field under the commissioned policy" is inexact):** the schema
*permits* the field under commissioned; it merely does not *require* it, and the
corpus pattern (example + prose) is that commissioned descriptors carry none. A
commissioned descriptor that adds a list is schema-valid today and would pass the
gate — §2 explains why that workaround is rejected as the fix.

### 1.4 The dead `"any"` arm (root-cause evidence)

`firmware_policy` has been `["listed", "commissioned"]` in every OTDP schema version
in-tree (0.1.1, 0.1.2, 0.2.0, 0.2.2 — verified this session; 0.1.0's identity block
predates the field's current shape). No OTDP-valid descriptor can ever be `"any"`, and
the gate only ever sees OTDP-validated descriptors (the SDK wrapper calls
`validate_descriptor` first; the gateway validates at admission, CON-1/CON-10). The
`!= "any"` arm has been unreachable since it landed (commit `50b28de7`, the original
SDK-aligned presentation contracts). The gate was written for a two-value world
(listed / any) that the corpus never had; **the commissioned policy was simply never
handled** — that omission is the defect.

## 2. The semantic fork — both directions, corpus-grounded

### Fork (a): give the commissioned policy a firmware-statement path

- **(a1) Let commissioned descriptors declare `supported_firmware`** (already
  schema-legal — the zero-motion workaround). Rejected as the fix:
  - It converts the commissioned posture into a behaviourally identical `listed` while
    keeping the label — the descriptor becomes the firmware authority, which is
    exactly what `commissioned` exists to avoid (spec §1.3's sentence above).
  - **A02**: firmware acceptance under commissioned is *bench qualification
    evidence*. A plugin author cannot enumerate which firmware generations a bench's
    commissioned record accepts; a descriptor-side list asserts, as plugin authorship,
    a fact the corpus assigns to the bench.
  - It contradicts the corpus's own commissioned example and prose pattern.
  - It is per-plugin-author burden with an dishonest label, not a mechanism.
- **(a2) A new commissioned firmware-statement shape** (new OTDP identity field, or
  the gate consulting the bench's commissioned record). Rejected: a new OTDP field is
  OTDP motion (colliding with the #443 train — see §5) duplicating what `listed`
  already expresses; consulting the bench record inside `validate_preset` breaks the
  check's by-design offline purity (plugin-ui README: "Success means offline
  compatibility only" — the check takes descriptor/schema/preset bytes and ONE
  caller-supplied firmware string).

### Fork (b): relax the preset rule for commissioned devices — RECOMMENDED

The gate learns the corpus's division of firmware authority:

1. **The preset's own `supported_firmware` list always applies** — whenever a
   firmware value is supplied, it must be a member. The plugin author's applicability
   claim keeps its full force, including at apply time.
2. **The descriptor's list applies only when the descriptor declares one** — under
   `listed` (schema-required) and for any commissioned descriptor that declares one
   (§1.3's permitted shape — early adopters of the a1 workaround keep their check;
   nothing they rely on silently disappears). Under commissioned with no list (the
   corpus pattern), there is no descriptor-side membership to check — the bench's
   commissioned record is the authority.
3. **`firmware is None` is admissible only under `firmware_policy: "commissioned"`** —
   the honest "cannot be decided from the descriptor" posture for offline checks and
   gateway composition. It is NOT admissible under `listed` (unchanged: unknown
   firmware fails). The apply path is unaffected: `seam.py` already refuses `not_ready`
   before the gate when no firmware is established, and with an established firmware
   rule 1 governs.

Grounding, not convenience: what commissioning establishes about firmware is *the
bench's accepted record* (spec §43), not a descriptor-decidable property. A preset
authored against a commissioned descriptor is compatible-by-construction with respect
to the descriptor (the descriptor asserts nothing about firmware); firmware-generation
divergence remains possible and is exactly what the apply-time gate (established
firmware ∈ preset list) catches. The refusal's blast radius today — the entire
settings/preset UI dead on commissioned devices — is the gate asserting an
incompatibility it cannot know (an A06-shape dishonesty, in the refusal direction).

**Falsifier for fork (b)'s premise**: if the corpus prose ever assigned commissioned
descriptors a firmware statement (or a bench record consult inside offline checks),
(b)'s authority division would be wrong. No such text exists in any in-tree OTDP
version (searched; the only commissioned-firmware sentence is §43's).

## 3. The mechanism (file-by-file)

The gate restructure in BOTH byte-identical copies
(`src/benchweave/presentation/contracts.py` and
`packages/sdk/src/benchweave_sdk/standards/plugin-ui/contracts.py`), replacing
lines 279-293 with the three-rule form (semantics of §2, exact code shape is the
builder's; the three refusals keep the same Finding code/path/message so every
consumer — including `seam.py`'s conflict mapping at line 1237 — is unchanged):

```
rule 1: firmware is not None and firmware not in preset["supported_firmware"] -> refuse
rule 2: firmware is None and identity.get("firmware_policy") != "commissioned" -> refuse
rule 3: identity.get("supported_firmware") is a list and firmware not in it -> refuse
        (None counts as not-a-member: a declared list is enforced regardless of policy)
```

The dead `"any"` arm is removed (unreachable per §1.4; no OTDP-valid descriptor can
carry it, and the gate only sees OTDP-validated descriptors — the structural reason
inline, per claim discipline).

Riding the same train:

- **`standards/plugin-ui/0.3.1/`** (recommended class: PATCH — §6): copy-never-move of
  `0.3.0/`; the version sweep (schema `contract_version` consts `0.3.0` → `0.3.1`,
  README codes paragraph unchanged — `incompatible_firmware` remains a code); README
  §preset prose amended: the firmware-gate paragraph gains the commissioned
  qualification (descriptor-side membership applies when the descriptor declares a
  list; a declared list is enforced regardless of policy; under commissioned policy a
  missing firmware value is admitted offline and the apply-time established-firmware
  gate governs); `MIGRATION.md` from-predecessor note; a train `validation-report.md`
  per the plugin-ui convention (hand-committed evidence record, not a suite render —
  CON-11's carve-out).
- **`standards/standards-manifest.json`**: active plugin-ui entry `0.3.0` → `0.3.1`;
  `dependency_policy.standards.plugin-ui.range` slides
  `>=0.3.0,<0.4.0` → `>=0.3.1,<0.4.0` (the one-live-object rule forces the narrow
  slide — the bundle row lists the live `contracts.py` in every carried version's
  rows, so carrying 0.3.0 beside 0.3.1 would serve 0.3.1 code bytes under a 0.3.0
  pin; the F1/#203 policy note sanctions the below-floor range).
- **`standards/corpus-manifest.json`**: rows for the new directory via
  `uv run python -m benchweave.standards repin` (edit → repin → export; no
  hand-spliced digests).
- **In-tree preset re-stamps** (the range slide puts 0.3.0 pins out of the carried
  set; documents are 0.3.1-valid except `contract_version`):
  `plugins/benchweave/sim_scope/src/benchweave_sim_scope/ui/presets/{fast-survey,low-noise-pair}.json`
  (gateway, 2 files) and SDK-side the 2 fixture presets
  (`tests/fixtures/{binary_frames_plugin,setpoint_plugin}/.../presets/steady.json`)
  plus scaffold-expected material if the sweep finds bearers (the 0.3.0 MIGRATION's
  own re-stamp pattern). No in-tree plugin contract locks exist today; if one carries
  a plugin-ui row at build time it relocks in-arc (`standards pin`).
- **`packages/sdk/src/benchweave_sdk_server/authoring.py`**: `_preset_firmwares` /
  `_validated_preset` gain the commissioned arm — when the candidate list is empty
  AND the descriptor's policy is `commissioned`, validate once with
  `firmware=None` instead of raising `AuthoringError` (the gate now decides; the
  error stays for `listed` with no candidates, where it is correct).
- **Tests (both repos)**: new RED-first arms — commissioned admit (None and
  in-preset-list value), the three negative controls of §7, commissioned-with-declared-
  list enforcement (rule 3); existing pins stay green untouched
  (`test_requires_known_compatible_firmware`,
  `test_l1b_incompatible_firmware_refused`,
  `test_preset_firmware_mismatch_refuses_before_any_write` — all listed-policy or
  preset-list-membership refusals, which rules 1-3 keep).
- **Docs**: `docs/device-developer-guide.md` preset/firmware section (obligation 3 —
  plugin-visible behaviour changed); `docs/project-index.md` standards-links sweep
  (obligation 18n) + `--refresh-docs-baseline` (obligation 20's docs ratchet — the
  diff is the review surface). Website stamps and the compatibility matrix are
  derived surfaces (`{{stg-*}}` tokens, `matrix --check`) — no hand motion.
- **Gateway caller code: ZERO changes required.** `compose_device_presentation`
  passes `None` for commissioned descriptors today; under rule 2 that is the admitted
  offline posture, so the settings/preset UI comes alive with no gateway-side code
  motion beyond the vendored gate itself.

Two-repo order (AGENTS.md / #408): SDK PR first (contracts twin + vendored dir +
lock + authoring arm + SDK tests) → merge → SDK release cut (with the lock-anchor
ritual: `standards-lock.json compatibility.sdk` = the release's own pyproject version
BEFORE tagging — the v0.7.0 lesson) → gateway PR carrying bump + repin + re-stamps +
tests + docs + the submodule pointer/pin advance in one commit (the sdk-drift
same-commit rule). `make check-sdk-standards` and `sdk-drift` ride CI as usual.

## 4. Minimal first increment and EXPLICIT deferrals

**Slice 1 (this increment):** everything in §3 — the gate restructure, the plugin-ui
0.3.1 train, the authoring arm, re-stamps, tests, docs, the SDK release + pointer.
One plugin-ui bump, one semantic change, no OTDP bytes.

**Deferrals (each with home + reopen trigger):**

- **D1 — a gateway-side commissioned firmware source at compose time** (passing the
  bench's established/commissioned firmware into presentation composition so
  render-time validation could be firmware-resolved rather than deferred). Home: a
  future `interfaces/` presentation increment. Reopen: the first operator request for
  firmware-specific preset availability in the read-only UI (the deferred posture
  renders all structurally-valid presets; availability is decided at apply).
- **D2 — any commissioned firmware-statement shape** (fork a2). Home: OTDP, only on
  new evidence. Reopen: an owner/corpus request for descriptor-carried firmware
  metadata that is explicitly non-authoritative (display-only), which would need its
  own train.
- **D3 — `check-ui --firmware` convenience resolution for commissioned plugins**
  (e.g. reading a project-local declared value). Home: SDK CLI. Reopen: author
  ergonomics feedback; the `None` posture already validates structurally.
- **D4 — scenario identity display**: `scenarios.py::_identity_fields` renders
  firmware `"unknown"` for descriptors without a list — honest, cosmetic. Reopen:
  scenario-fidelity complaints.
- **D5 — plugin-ui-preview surfaces**: out of scope; the preview quality vocabulary
  is untouched.

## 5. Train recommendation: NO OTDP MOTION — independent train

The fix lives in plugin-ui (the gate) + SDK-server code + gateway vendored bytes. The
OTDP corpus already states the commissioned semantics this design implements (§1.3);
no OTDP schema or prose byte moves. Therefore:

- **Not "join the 0.2.3 train"** — there is nothing to roll onto `feat/issue443-decoder-
  output-contract`; folding a plugin-ui bump into an OTDP train would violate
  "different standards may share a merge only when they are one increment" (they are
  not — #443 is a decoder-output contract, #444 is a preset-compatibility gate).
- **Not "sequence after"** — no ordering constraint exists: disjoint standards, disjoint
  in-tree artifacts (sim descriptors carry `otdp_version`; preset documents carry
  plugin-ui `contract_version`; no artifact carries both in one field), no shared
  schema refs (plugin-ui's preset schema does not $ref OTDP documents).
- **Collision analysis**: the ONE shared file is `standards/standards-manifest.json`
  (active-entries block + dependency policy) — an ordinary MODIFY-vs-MODIFY merge
  resolved in review, the GOVERNANCE head-merge rule's own shape. The merge-result
  stranding class (the #62-era lesson: a bump strands every in-tree artifact declaring
  the old version *in the merge result*) applies per-standard: whichever of #443/#444
  merges second must carry artifacts the other added to main after its fork — for
  #444 that means re-checking any NEW preset documents or plugin-ui pins #443's merge
  result introduced (its scope makes that unlikely; verified against its design
  record — OTDP-only). Pre-flight this session: `git fetch origin` shows no remote
  branches on plugin-ui or #444 paths; no rival design.
- plugin-ui's bump window is clear (last plugin-ui bump was the 0.3.0 digital-lanes
  train, weeks past the 24h floor).

**Standing gates that bind this train:** the standards-byte tripwire (Stephen's word
as a normal permission gate — this design moves `standards/` bytes and needs it); the
dependency-policy range slide is a **coordinator decision requiring a linked ruling
reference in the PR body** (G-3/VR-43); the standards-governor lane is mandatory.

## 6. Precedent

- **The gate itself is the precedent-bearing mechanism** — this extends the existing
  plugin-ui firmware gate's condition set; no new architecture. The closest in-tree
  semantic precedent for policy-aware authority division is OTDP's own §43 sentence
  (the corpus already divides listed/commissioned authority; the gate is brought into
  line with it).
- **plugin-ui 0.1.1 → 0.2.0 (issue #62)**: the prior contracts.py-behaviour bump —
  established that contracts.py byte changes are structurally version-forcing
  (digest-pinned in the SDK lock's normative bundle row; same-version drift refused
  `standards_version_required`) and that the two repo copies move as one train. This
  design is the mirror-image change class: #62 TIGHTENED (valid→invalid ⇒ MINOR,
  governor-confirmed); this LOOSENS with nothing removed or retyped (invalid→valid
  only), mapping to GOVERNANCE's "additive machine errata (backwards-compatible) ⇒
  PATCH" row (the `approver_token` pattern). **Owner-fork:** the standards
  coordinator may rule MINOR — the mechanism is identical either way; only the label,
  the MIGRATION framing and the range slide's exact bounds move. Stated here so the
  ruling is a label call, not a rework.
- **plugin-ui 0.2.0 → 0.3.0 (issue #244)**: the one-live-object / narrow-range-slide
  and re-stamp mechanics this train reuses verbatim (MIGRATION.md of 0.3.0).
- **Decision record**: A02 (commissioned-per-bench — grounds the fork choice);
  A06 (evidence over assertion — the old gate asserted an undecidable incompatibility;
  the new None-posture defers to the apply-time evidence gate); A09 (OTDP as the
  explicit integration gate — no OTDP motion needed because the semantics already
  exist there); A13 (one core contract — one vendored gate behind both repos' surfaces);
  A12 (presets stay versioned, bounded documents with declared applicability).

## 7. Measurable proof and the PRE-COMMITTED acceptance rule

**Pre-fix measurement (RED, run before any production edit):** the real
commissioned-policy consumer's descriptor (owner-supplied, read this session) plus a
preset authored from its writable settings — run ``benchweave-sdk` `check-preset`` (SDK
checkout) with `--firmware <a value the preset lists>`: today it refuses with exactly
`incompatible_firmware` at `preset.supported_firmware` (the issue's quoted finding —
the repro that anchors the whole train). Same shape reproduced synthetically in the
gateway test suite against a commissioned fixture descriptor.

**Metric:** refusal/admission verdict of the vendored gate over the preset corpus ×
policy matrix. The census denominator: all in-tree preset documents (gateway sim_scope
×2, SDK fixtures ×2, scaffold set) + the commissioned fixture matrix (4 arms below) +
the real consumer's descriptor (N=1 operator-facing confirmation — its presets are
still in authoring; the owner's check output is the closing evidence).

**Controls (negative, must still refuse after the fix):**
- C2 listed-policy mismatch: firmware ∉ descriptor list ⇒ `incompatible_firmware`
  (existing pin `test_requires_known_compatible_firmware`).
- C3 commissioned preset-list mismatch: commissioned descriptor, preset declares
  `["1.0"]`, firmware `"2.0"` ⇒ refused by rule 1 (the apply-time gate's force;
  existing pin `test_preset_firmware_mismatch_refuses_before_any_write` shape).
- C4 listed + `firmware=None` ⇒ refused by rule 2 (unknown firmware still fails).

**Acceptance rule (pre-committed before any number is looked at):**
- **SHIP iff**: (i) the commissioned-admit arms are RED pre-fix (the §7 pre-fix
  measurement and the synthetic arm both refuse with the exact finding) and GREEN
  post-fix; (ii) reverting ONLY the gate restructure turns them RED again (G3
  RED-sanity — the test catches the thing); (iii) C2/C3/C4 refuse with code
  `incompatible_firmware`, path `preset.supported_firmware`, unchanged message; (iv)
  the in-tree listed-policy corpus (sim_scope ×2) admits with byte-identical findings
  before and after (widening-only proof); (v) full battery green: fast lane (ruff,
  fresh-cache bare mypy, focused pytest) + full suite + both standards tripwires +
  `make check-sdk-standards` + `matrix --check` + the version-literal zero gate.
- **KILL if**: any of C2/C3/C4 stops refusing; or any previously-valid listed-policy
  document becomes refused anywhere in the census (the change stopped being a
  relaxation — re-scope); or the commissioned-admit arm cannot be made RED by revert
  (the proof is vacuous — fix the test before shipping anything).
- **UNDERPOWERED (not conclusive) if**: the only green evidence is synthetic fixtures
  and neither the real consumer's check output nor its authored preset can be
  produced — the mechanism may still ship on synthetic + corpus evidence, but the
  issue stays open with the closing claim downgraded to "mechanism verified on
  fixtures; operator confirmation pending", and the owner's run remains the reopen
  evidence.

## 8. Invariant and drift impacts

- **A01–A14 walk**: A02 — directly engaged, preserves it (fork (b) keeps firmware
  acceptance as bench evidence; fork (a1) would have violated it — recorded in §2).
  A06 — the None-posture replaces an undecidable refusal with deferral-to-evidence.
  A09 — no OTDP motion; OTDP's existing semantics are the authority being conformed
  to. A12 — preset documents unchanged in shape/semantics of applicability. A13 — one
  gate, one vendored byte-stream, both repos (the sync discipline). A04/A05/A07/A08/
  A10/A11/A14 — untouched (no control path, no lifecycle, no audit, no packaging, no
  registry, no interface-contract change).
- **Invariants file**: no new invariant; no amendment required — CON-4/CON-7/CON-14
  are the mechanics this train RIDES (vendoring drift gate, repin, dependency-policy
  surfaces), not ones it changes.
- **Surfaces that move** (drift-and-obligations): 3 (device-developer-guide),
  6 (vendored bytes/repin loop), 7 (SDK pointer + version-pairing, release-cut
  order), 18n (project-index sweep) + 18's closing clause, 20 (docs baseline refresh;
  the contracts twins stay digest-pinned whole — they move together or not at all),
  21 (dependency-policy block + carried set: manifest ↔ export ↔ SDK lock ↔ vendored
  tree, one arc). Standards-governor lane mandatory. Website/matrix derived.
- **On-disk format/schema**: yes — a new plugin-ui version directory with JSON Schema
  files (Tier 3 by the rubric's own note). No persisted-state migration anywhere.

## 9. Top risks and falsifiers

- **R1 — rendered-but-unappliable presets**: an operator sees a preset that refuses
  at apply (firmware generation mismatch discovered only then). By design (the
  commissioned record is bench-side); the apply refusal is typed (`conflict`, naming
  device and preset firmware). Falsifier of the DESIGN: an owner ruling that
  render-time firmware resolution is required — that opens deferral D1, it does not
  invalidate the gate fix.
- **R2 — rule 3 surprises a future commissioned descriptor that declares an advisory
  list**. Mitigated by README prose ("a declared list is enforced regardless of
  policy"). Falsifier: a corpus example or owner intent showing advisory-list
  semantics under commissioned.
- **R3 — PATCH/MINOR misclassification** (§6 owner-fork). The governor lane reviews;
  the coordinator rules the range with a linked ruling. Cost of either answer is a
  label, not a mechanism.
- **R4 — out-of-tree re-stamp burden**: the range slide puts 0.3.0-pinned presets out
  of the carried set (every plugin-ui bump ever has; the population today is
  pre-release). Falsifier: a released out-of-tree 0.3.0 preset author broken by the
  slide — the MIGRATION note is the migration path.
- **R5 — train interference with #443**: only the shared standards-manifest merge;
  verified disjoint otherwise (§5). Falsifier: #443's branch acquiring preset-bearing
  or plugin-ui-pinning artifacts — checked at rebase time.
- **R6 — SDK release timing**: the gateway PR needs a tagged SDK release carrying the
  sync before the pointer can advance (pin = tag, the sdk-drift law); the lock-anchor
  ritual precedes the tag or the tag is structurally unsatisfiable (v0.7.0 lesson).

## 10. Review tier (design-time call, #254)

**Tier 3.** Trigger: the build diff touches `standards/` (new plugin-ui version
directory, both manifests) and adds JSON Schema files — the path rule fires before
any keyword rule. The standards-governor mandate applies. G6 adversarial refute:
mandatory; the refute's named targets are §7's kill conditions (any
previously-valid document newly refused; any negative control disarmed; the
RED-sanity vacuity case).

## 11. Step-1 keyword scan over the expected diff

Scan over the whole expected build diff (code + tests + standards + docs), keywords
and counts as design-time fixed points over the expected diff shape — the review
re-runs the scan on the real diff and the tier does not depend on it (the path rule
already fires):

- `threading`: 0
- `asyncio`: 0
- `subprocess`: 0
- `sha256`: ≈ 6 — four `corpus-manifest.json` rows for the new directory (one
  `"sha256"` key each) plus ≈ 2 in new test arms asserting digest behaviour; the
  gate restructure itself touches no digest code (the `hashlib.sha256` line at
  contracts.py:295 is context, not diff).
- `hashlib`: 0
- `migrate`: 0 (`MIGRATION.md` filenames and prose do not contain the verb; the
  token is `migration`, which does not contain `migrate` as a substring)
- `recovery`: 0
- `protection`: 0

## 12. Owner forks named by this design

1. **The fork (§2)**: relax (b, recommended) vs a commissioned firmware-statement
   path (a). Argued from the corpus; bless or override.
2. **The bump class (§6)**: PATCH 0.3.1 (recommended, additive-errata row) vs MINOR
   0.4.0 — coordinator ruling, linked ruling reference in the PR body either way (the
   range slide is G-3 territory).
3. **The standards-byte permission gate**: this train moves `standards/` bytes;
   Stephen's word, per the standing tripwire.
