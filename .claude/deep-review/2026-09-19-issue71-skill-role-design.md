# Design — issue #71 run: `skill` payload-file role, scaffolded skills, plugin-developer skill, docs

Date: 2026-09-19. Status: slice 1 ACCEPTED as written (team-lead, 2026-09-19);
§9 amended to the run slice map; slice 2 designed in the sibling record
(`2026-09-19-issue71-slice2-agent-native-scaffold-design.md`, §12). Scope per
five maintainer directives delivered mid-design (2026-09-19) plus the
fork-settling correction — provenance in §0.1. This record is drafted in the
SDK repository's deep-review directory and, at PR time, commits on the
main-repository branch (the issue-#64 precedent, main commit `c4e622f`; the
issue-#62 precedent, `f609182`) so the pre-committed acceptance rules provably
predate the measurements.

## 0. Verdict and run scope map

**BUILD** — a sliced run, stacked PR pairs. Slice 1 is a governed registry PATCH
(the original issue, unchanged in mechanism); slice 2 builds the agent-native
scaffold (skills + CLAUDE.md seeding, plugin-developer skill content,
standalone-MCP workflow, golden pins); slice 3 documents it; slices 4–5 are the
folded found-deferral designs (D5, D6), each with its own design pass before
build. The issue's OWN pre-declared deferrals stay deferred (D1/D2, §9).

### 0.1 Directive provenance (all 2026-09-19, from the run owner via the team lead)

1. Found deferrals roll INTO this run (stacked PRs allowed); only the issue's own
   pre-declared deferrals stay out.
2. Scope expansion: developer-scenario skill workflows (documented) + a
   standalone-MCP-server skill workflow; map the docs-only vs machinery fork with
   evidence.
3. `benchweave-sdk new` generates the skill files into every scaffolded plugin
   project; scaffold becomes a required slice; golden impacts planned.
4. The scaffold also seeds a `CLAUDE.md` at the plugin repo root.
5. Skill taxonomy: device/runtime skills vs one plugin-developer skill containing
   firmware-development + adapter-creation + standalone-MCP + an elicitation
   workflow ("asks all the right questions"), with the questions mapped to real
   authoring surfaces.
6. Fork settled: ALL skills live in the scaffolded plugin, full stop — nothing
   ships as an SDK-package skill; the SDK's role is scaffolding + checking +
   documenting. (Supersedes the packaging lean in directive 5.)
7. Team-lead decision on this design: slice 1 accepted unchanged; §9 amended —
   D3–D6 are run slices with their own design passes, not backlog deferrals;
   slice 2 designed next (pipelined while slice 1 parks behind #62).

### 0.2 Slice map

| # | Slice | Design | Lands as |
|---|---|---|---|
| 1 | Registry `skill` role — PATCH 0.1.0→0.1.1 + fixture live-fire (D4 mechanics, §1.3) — **ACCEPTED** | this record §1 | PR pair A (SDK PR merged first, then main PR with pointer) — the #64 shape |
| 2 | Agent-native scaffold: skills + CLAUDE.md seeding, plugin-developer skill content (elicitation, firmware, adapter, standalone-MCP, release), golden pins, SDK 0.0.3 | sibling record `2026-09-19-issue71-slice2-agent-native-scaffold-design.md` (authoritative; supersedes this record's former §2–§5.2 detail where they differ) | Stacked on pair A's SDK main |
| 3 | Developer docs: the skills model, authoring workflow, standalone-MCP shape and its limits | slice-2 sibling is the source; docs get their own light pass | Same stack |
| 4 | D5 — SDK `check-manifest` lane (folded found deferral) | own design pass before build | Stacked, on trigger evidence or maintainer go |
| 5 | D6 — manifest-derived active registry version (ends the §8 literal-sweep class) | own design pass before build | Stacked, or the next registry bump, per its design |

Slice order is load-bearing: the role must exist before the scaffold catalogues
skill files; the docs slice documents slices 1–2; D5/D6 follow their own passes.
The SDK version decision lives with slice 2 (sibling §9: one bump, 0.0.2 → 0.0.3,
at the first output-changing merge).

Naming hygiene for all generated content and both records: invented names only;
the real capture/decode bench device that motivated the device-skill case is
referred to generically and is not named.

## 1. Slice 1 — registry `skill` payload-file role (PATCH 0.1.0 → 0.1.1) [ACCEPTED]

Mechanism accepted as written; verified against the trees at
`/Users/seaton/Documents/src/BenchWeave` (main, post-#64) and
`/Users/seaton/Documents/src/benchweave-sdk` (branch `feat/issue62-plugin-ui-020`,
the in-flight #62 train; read-only).

### 1.1 Premise, verified

- **Enum**: `standards/registry/0.1.0/release-manifest.schema.json`
  `payload.files[].role`, lines 404–417 — ten values. SDK vendored copy
  sha256-pinned by `standards-lock.json`. Standard: `registry`, active 0.1.0
  (`standards/standards-manifest.json`); normative set = the six machine files;
  the prose companions (`registry-specification.md`, `validation-report.md`) are
  corpus-resident but neither normative-listed nor vendored.
- **Role handling is enum-driven everywhere.** SDK source: zero role strings
  outside the vendored tree (`grep build_provenance|dependency_lock|release-manifest`
  → no hits); `packaging.py:31` is deliberately role-agnostic. Gateway: role
  literals only in `activation.py` (`IMPLEMENTATION_ROLE`) and
  `otdp_loading.py:213` (`.py` members must be role `implementation`) — both
  orthogonal to an added role; structure validation is pure schema
  (`src/benchweave/registry/schemas.py`, `RegistryRejected("schema_invalid")`).
- **No SDK lane validates release manifests today** — `check` (OTDP descriptor),
  `check-ui`/`check-preset` (plugin-ui), preview (plugin-ui). The only refusals a
  skill-role manifest can draw today: gateway `schema_invalid`; SDK-side
  `ValueError("Contract validation failed: … 'skill' is not one of […]")` via the
  generic loader. **STD-4: no new refusal path or prefix is introduced.**
- **The SDK's one load-bearing coupling**: `src/benchweave_sdk/validation.py:26–30`
  hardcodes `("registry", "0.1.0")` in the `sets` tuple;
  `contract_documents()` walks it eagerly, and the vendored tree is
  single-active-version, so a stale key breaks every lane at load. The #62 sync
  already moved the plugin-ui entry the same way (SDK `f923179`, 1-line diff).

### 1.2 Corpus change (main-side first — STD-5, TWO-1)

Copy-never-move (GOVERNANCE "Bump mechanics"; OTDP precedents `709de25`, `30a775b`):

1. Copy `standards/registry/0.1.0/` → `standards/registry/0.1.1/` (eight files);
   0.1.0 stays digest-frozen forever.
2. In-copy edits, only in the copy:
   - role enum appends `"skill"` (eleven values); no other schema edit. The
     kind-conditionals (profile forbids implementation/descriptor roles;
     implementation must contain the four mandatory roles; non-implementation
     forbids implementation) are untouched — agent guidance is kind-agnostic
     (explicit non-change; risk R6).
   - `manifest_version`/`status_version`/`lock_version` consts → `"0.1.1"`
     (OTDP precedent: `otdp_version` const moved on the 0.1.2 PATCH — the
     document declares which enum admitted it; document-own version fields never
     move).
   - **`$id`s do NOT move**: registry `$id`s are `urn:stg:registry:<doc>:1.0.0` —
     the trailing number is the architecture-contract edition (the spec's title),
     not the standard version; OTDP/plugin-ui `$id`s embed the standard version
     and therefore moved with their bumps. No cross-`$ref` exists among the
     registry schemas. (Governor confirms at PR time.)
   - `examples/release-manifest.json`: `manifest_version` → `"0.1.1"`; add
     `{"path": "skills/drive-device/SKILL.md", "role": "skill", …}` following the
     zero-placeholder convention.
   - `registry-specification.md` §4: first enumeration of the role list; `skill`:
     an agent-facing skill document in the cross-harness skills format (frontmatter
     `name` + `description`; the `SKILL.md` convention); BenchWeave names the
     format, not the consuming harness; disambiguation from `documentation`
     (human-facing vs machine-discoverable agent guidance; CLAUDE.md-class
     project instructions are `documentation`, not `skill`); multiple skill
     entries permitted. `validation-report.md`: new checks + count.
3. `uv run python -m benchweave.standards repin` (the only digest writer): new
   corpus rows for the six 0.1.1 machine files citing `standards/registry/0.1.0/…`
   sources; `identity.registry` → `"0.1.1"`.
4. `standards/standards-manifest.json`: registry → 0.1.1, `supersedes: "0.1.0"`,
   re-pointed normative paths.
5. Gates: `benchweave.standards check`, architecture validator, `matrix --check`.

**Digit: PATCH.** GOVERNANCE's additive-machine-errata row ("new optional field,
nothing removed or retyped") — an enum member addition removes/retypes nothing;
every 0.1.0-valid document stays valid. #62/#64 were MINOR only because they
tightened. Governor confirms or reclassifies at PR time (cheap either way).

### 1.3 Slice-1 consumers beyond the original design (D4 mechanics — accepted here)

- `scripts/registry/registry_common.py`: `ROLE_BY_SUFFIX` gains
  `"SKILL.md": "skill"` (and `"CLAUDE.md": "documentation"`, needed by slice 2's
  payload story); `_common_members()` (or impl extras) gains a real skill member
  (e.g. `skills/drive-device/SKILL.md` with invented fixture content), so the
  regenerated fixture lattice carries a skill-role file through
  admission/resolver/authenticity tests — the gateway-side live-fire proof of the
  new role, riding the same fixture regen the version sweep already forces. The
  fixture's SKILL.md content stays decoupled from slice 2's scaffold template
  (the fixture proves the ROLE; the template proves the SEEDING — sharing bytes
  would couple two proofs to one edit).
- Lock compatibility notes (hand-set by the sync commit — the sync itself writes
  `notes: None`, `standards_sync.py:251`): registry 0.1.1 admits `skill`
  (additive; 0.1.0 manifests stay valid against the frozen 0.1.0 corpus but must
  re-version for 0.1.1 admission); no SDK behavior change; no SDK version bump in
  this sync.

**SDK delta for slice 1**: `validation.py:28` one line; sync-generated
lock/tree/stamps; notes; new main-side tests (§5.1). No CLI/scaffold/preview
change; SDK version stays 0.0.2 in this sync (f5e05fa precedent + the 2026-09-19
minimum-bump directive; the run's one version decision is slice 2's, sibling §9).

## 2. Slice 2 overview — the agent-native scaffold [detail in the sibling record]

The authoritative slice-2 design is
`.claude/deep-review/2026-09-19-issue71-slice2-agent-native-scaffold-design.md`
(§12). Summary for the run map:

- **Seeding (always-on, in `create_project`'s `contents`)**:
  `src/<package>/skills/{develop-plugin,drive-device}/SKILL.md` (inside the
  package = in the wheel = catalogued under the slice-1 `skill` role; frontmatter
  `name`+`description`, names parameterized by package) and `CLAUDE.md` at the
  project root (parameterized like `TEST`; **uncatalogued dev tooling by
  default** — root files never enter the wheel, and if a publisher ships it the
  spec §4 text added in slice 1 assigns `documentation`, not `skill`).
- **Plugin-developer skill** (`develop-plugin`): elicitation (questions derived
  from the corpus — the sibling's §4 table enumerates the real descriptor
  surfaces: the ten verbs, operationPolicy fields, parameter fields with enums,
  four identity strategies, nine transport variants with settings keys,
  channels/capture/stream surfaces, the twelve OTDP classes, manifest roles and
  evidence levels), firmware workflow, adapter creation against the real Adapter/
  HostServices contract, standalone-MCP workflow, release workflow.
- **Device skill** (`drive-device`): documents driving the synthetic demo and is
  explicitly the template to rewrite — the synthetic-adapter honesty pattern.
- **Standalone-MCP fork: shape (a), workflow-only** — the SDK has zero MCP
  machinery (no MCP dependency; the gateway's interface-standard MCP surface is
  gateway-side), so the skill guides an agent to wrap `create_plugin()` with a
  minimal five-method host + MCP server; shape (b) machinery is slice-adjacent
  but held with a measured trigger (sibling §7).
- **Manifest mechanics (D3)**: the scaffold emits NO manifest surface and keeps
  it that way — the manifest is a release-time publisher record; the scaffold's
  job is knowable role assignment (`inventory` output + the skill's file→role
  table) — sibling §6.
- **Golden**: the **file-set pin** becomes the SRF-1 contract (no byte-golden
  tree exists today — `test_sdk.py:102` is structural and
  `test_presentation_cli.py` scaffolds into tmp dirs); byte-stability and
  content-coverage tests derived from the vendored schemas — sibling §8.
- **SDK version: one bump, 0.0.2 → 0.0.3, at slice 2's release commit** — the
  first output-changing merge is the honest version boundary; flagged as the
  maintainer's call — sibling §9.

## 3. (superseded as a standalone slice — folded into slice 2)

The former "slice 3 — skill content" is absorbed into slice 2 per the team-lead's
tasking (the seeded skills ship WITH working content). The elicitation table,
taxonomy, MCP fork evidence, firmware/release workflows, and content tests live
in the sibling record §2/§4/§7/§8.

## 4. Slice 3 — developer docs

- `user_guide/plugin-sdk.qmd` + docs site: the skills model (two kinds, both
  project-resident), how the scaffold seeds them, the elicitation/authoring
  workflow, the standalone-MCP shape-(a) story and shape-(b) boundary, manifest
  cataloguing (`skill` role; CLAUDE.md as `documentation` if shipped).
- README five-steps: mention the seeded skills where the generated project is
  described (drift obligation 1).
- Docs proof is the docs-site CI build + the G5 review walk — honestly not
  RED-provable; the behavioral proof lives in slices 1–2's tests.

## 5. Proving tests and pre-committed acceptance rules

### 5.1 Slice 1 (accepted as written)

**`tests/sdk/test_registry_contract.py`** (new; first SDK test to consume the
vendored registry contract):
- `test_registry_manifest_skill_role_validates` — in-code manifest (the
  `tests/contract/test_registry_schemas.py:24–73` shape) with a skill entry;
  schema key resolved FROM THE COMMITTED LOCK (the `tests/test_version_constants.py`
  pattern — RED for the right reason pre-sync: it fails on the ENUM against
  whatever version the lock pins, not on a stale hard-coded key);
  `benchweave_sdk.validation.validate` returns cleanly.
- `test_registry_manifest_unknown_role_refused` — role `"workbench_guide"` →
  `Contract validation failed:` + `is not one of`. **The control.**
- `test_registry_standard_version_is_0_1_1` — lock registry version (sweep
  sentinel).

**`tests/contract/test_registry_schemas.py`**:
`test_manifest_skill_role_accepted` (gateway loader round-trip); existing
`schema_invalid` tests are the closed-enum controls. Fixture live-fire: the
regenerated lattice's skill-role file flows through admission/resolver tests.

**`scripts/architecture/check_registry.py`**: example's skill entry rides the
existing positive-fixture check; ONE added negative check (role `"skillx"`
refused); count 63→64; `validation-report.md` + `docs/README.md:14` carry it.

**Acceptance (pre-committed).** SHIP iff: (1) PRE-bump, the two skill-role tests
FAIL with the validator's own `is not one of` text (SDK lane) / `schema_invalid`
(gateway lane) in the evidence; (2) PRE, both unknown-role controls PASS; (3)
POST, all §5.1 tests PASS and the controls STILL PASS (enum closed, exactly one
member added); (4) `sync-standards --check`, `make check-sdk-standards`
(`check` + `matrix --check`), SDK CI, main battery green at both PR heads and the
merge result; fixture regen diff shows only version-string/digest churn plus the
new skill member; (5) the main PR carries the design record before the corpus
bump. KILL if: skill tests pass PRE (enum not closed for the tested path —
instrument broken or premise wrong); any control fails POST (widening beyond one
member); any gate needs changes outside this design's file lists. UNDERPOWERED,
not conclusive, if: the PRE↔POST delta is only the version sentinel — the
`is not one of` RED text never appeared (stale-key instrument; re-run with the
text requirement enforced).

**Correction to the originally proposed instrument** (kept for the record):
"scaffold + SKILL.md manifest entry + `check` clean" proves nothing — no SDK lane
reads release manifests. The honest scaffold-level proof is slice 2's generation
tests plus the end-to-end note: a generated project's `inventory` output lists
the skill files (path/bytes/sha256 — roles are assigned at manifest authoring,
which the plugin-developer skill's release section instructs).

### 5.2 Slice 2 — superseded by the sibling record §8

The slice-2 acceptance rule (file-set pin, byte-stability, frontmatter and
command pins, schema-derived elicitation coverage, KILL/UNDERPOWERED clauses)
lives in the sibling record §8 and is the authoritative version.

## 6. Landing plan and serialization with the in-flight #62 train

**State observed (2026-09-19)**: #62 (plugin-ui 0.1.1→0.2.0) is mid-flight —
main branch `feat/issue62-plugin-ui-020` has design+RED+bump+pointer commits
(`f609182`, `d6b171f`, `e6b177f`, `03a8ba0`); SDK branch carries the pushed sync
(`f923179`, `67dcb69`); main's `packages/sdk` pointer is still `f5e05fa`.

**Serialization**: slice 1 shares #62's sync surfaces (standards-manifest,
corpus-manifest, SDK lock/tree, pointer) and cannot merge independently of it.
**The run parks until #62 lands** (SDK PR then main PR), then executes once from
the post-#62 baselines — no interleaving, no second rebase; if #62's shape
changes in review, re-copy the corpus branch from the new predecessor
(GOVERNANCE).

**Sequence** (the #64 shape: SDK PR #27 merged `e0c09dc`, then main PR #80
merged `64f64a9` containing pointer `1fe3e1a`):

1. Main branch `feat/issue71-skill-role` from post-#62 main. Commit order:
   design record → §5.1 tests, run RED, evidence pasted → corpus bump + full §8
   sweep + fixture regen (skill member included) → tests GREEN; main battery
   green with the acknowledged mid-sequence red on `make check-sdk-standards`
   (the OTDP 0.2.0 message records the same intermediate state).
2. SDK branch `feat/issue71-skill-role` from post-#62 SDK main: `make
   sync-sdk-standards` from the branch export; sync commit (slice-1 SDK delta,
   `f923179`-style message). Push. SDK PR → CI green → **merge**.
3. Main PR: pointer commit to the pushed SDK SHA (TWO-1) → merge on green
   merge-result gates (`make check-sdk-standards`, `uv run pytest tests/sdk
   tests/standards`, raw-run counts).
4. Slice 2 stacks on the merged SDK main — SDK branch
   `feat/issue71-scaffold-skills` (sibling record §10 has the commit plan), SDK
   PR carrying the 0.0.3 bump at its release commit, then one final main pointer
   + merge-result gate. Slice 3 (docs) rides the same stack. Slices 4–5 (D5/D6)
   follow their own design passes. Default is stacked PR pairs so slice 1's
   registry train is not held hostage to content review.

## 7. Invariant impacts

- **STD-1/2/3** (slice 1): maintained mechanically by the sync; content moves
  version-first; the three lanes verify the new tree identically; no lane edits.
- **STD-4**: no new refusal path or prefix anywhere in the run; the new tests PIN
  existing surfaces (`schema_invalid`, `Contract validation failed:`).
- **STD-5 / TWO-1**: normative bytes change main-side first; every SDK commit
  pushed before its pointer.
- **PKG-1/2/3**: no new dependencies (MCP shape (a) chosen partly for this); the
  wheel packages the same tree (templates are inline constants in `scaffold.py`,
  matching house style); `.claude/`-rooted artifacts (these records) reach no
  artifact; renderer untouched.
- **SRF-1** (TOUCHED in slice 2 — the run's biggest interface change): scaffold
  output gains files; the file-set pin (sibling §8) becomes the contract; the
  generated RUNTIME keeps its no-SDK-dependency property (markdown only; test
  extra unchanged).
- **SRF-2**: preview untouched. **SRF-3**: no conformance rule weakens; the run
  ADDS the first registry-contract and scaffold-output pins.
- **Rubric**: slice 1 is Tier 3 (vendored tree + lock + version increment);
  slice 2 is an SRF-1 interface change; standards-governor runs on the main PR;
  code-reviewer walks the G5 obligations (§8) on every pair.

## 8. Stranding and obligations checklist

Slice 1 (grep-derived; the #64 arc needed `dc9955b` for missed docstrings —
re-grep at the merge result):

Main: (1) `standards/registry/0.1.1/*`; (2) `standards-manifest.json`; (3)
`corpus-manifest.json` via repin; (4) `src/benchweave/registry/schemas.py:22`;
(5) `scripts/architecture/check_registry.py:10` + negative check; (6)
`scripts/registry/registry_common.py` version emitters (121, 179) +
`ROLE_BY_SUFFIX` entries + skill member + `build_fixtures.py` regen
(`fixtures/registry/**`, `catalogue.json`); (7) `tests/contract/test_baseline.py:29`
ADMITTED_DIRS **+=** `registry/0.1.1` (0.1.0 stays); (8)
`tests/contract/test_registry_schemas.py` literals 26/146/167/194 + new test;
(9) `tests/contracts/test_architecture.py:89`; (10) `tests/standards/test_repin.py:34`
(sweep-or-justify); (11) `tests/sdk/test_standards_sync.py:119` victim path →
0.1.1 (the bundle carries only active versions); (12) docs active-version paths
(`docs/README.md:13–14` + count cell, `project-index.md:19`,
`device-developer-guide.md`, `smart-test-gateway-architecture-v1.5.md`,
`ai-device-reviewer.md`, `develop-your-device.md`); (13)
`docs/compatibility-matrix.md` re-render. SDK: (14) lock + vendored tree +
stamps; (15) `validation.py:28`; (16) new `tests/sdk/test_registry_contract.py`.

Slice 2: SDK `scaffold.py` (templates + `contents` + AI-GUIDE layout paragraph);
new main-side tests (sibling §8); README five-steps + `user_guide/plugin-sdk.qmd`
+ docs-site content (obligations 1–2, the docs slice); the SDK version bump
(sibling §9). In-flight-PR hazard stands: re-grep `registry/0.1.0` at each merge
result.

## 9. Run slice map and deferral dispositions (amended per the team-lead decision)

Everything found during this task rolls INTO the run as slices with their own
design passes; nothing found goes to the backlog. The only true deferrals are
the issue's own pre-declared ones, and both get follow-up issues filed before
the slice-1 main PR merges (orphan deferrals block merge).

- **Slice 1** — registry `skill` role + D4 mechanics (§1). Design: ACCEPTED.
- **Slice 2** — agent-native scaffold: D3's seeding + skills content + CLAUDE.md
  + MCP shape (a) + golden pins + SDK 0.0.3. Design: the sibling record (§12).
- **Slice 3** — developer docs (README five-steps, user guide, docs site).
  Design: light pass when slice 2's content is final; the sibling is the source.
- **Slice 4 (D5)** — SDK `check-manifest` lane: the SDK's first
  manifest-consuming check surface. Own design pass; currently gated on the
  honest trigger — repeated manifest-authoring defects observed at release time
  in a real plugin project — or a maintainer go. The reason it is a later slice
  and not slice-2 machinery: no slice consumes manifests, and a manifest lane
  forces format decisions D2 defers.
- **Slice 5 (D6)** — manifest-derived active registry version in
  `check_registry.py`/`schemas.py`/`validation.py` (ends the §8 literal-sweep
  class). Own design pass; the natural slot is the NEXT registry bump, so this
  run does not widen regression surface across 16+ files mid-train.
- **D1 (richer `skills` manifest array) and D2 (standardising the skills
  format)** — remain true deferrals, the issue's own; follow-up issues filed
  before the slice-1 main PR merges. D2's boundary is load-bearing three times:
  no check-lane skill-content validation, no prose parsing in the content test,
  no format schema in the scaffold.

## 10. Top risks, each with its falsifier

- **R1 sweep misses** (slice 1) — §8 checklist is grep-derived and re-run at each
  merge result; CI catches code-path misses mechanically.
- **R2 digit or `$id` call wrong** — governor reclassifies at PR time; both
  corrections are pre-merge-cheap by design.
- **R3 `manifest_version` const move strands 0.1.0 manifests** — no real
  publishers exist today (fixtures only; corpus reset 2026-09-16); OTDP set the
  const-moves-on-PATCH precedent. Falsifier: an in-tree manifest that cannot
  re-version mechanically.
- **R4 #62 interleaving** — park-and-rebase (§6); `make sync-sdk-standards`'s own
  refusals enforce the order.
- **R5 stale-schema-key RED** (slice 1 instrument) — the `is not one of` text
  requirement; without it the run is UNDERPOWERED.
- **R6 kind-conditional expectations** (skill forbidden for `kind: profile`?) —
  the issue's "no other schema change" is authority; governor may amend §1.2
  prose + a conditional, decided at review, not smuggled.
- **R7 scaffold interface blast radius** (slice 2): additive-only (no existing
  file renamed or removed), the file-set pin makes future drift loud, the PR
  states the interface change. Falsifier: any existing generated file must
  change bytes beyond the AI-GUIDE layout paragraph (would multiply the diff
  across every downstream repo — escalate before proceeding).
- **R8 skill content invents surfaces** — sibling §4 table + the schema-derived
  test cover omissions; inventions are review-covered (honest limit, sibling §8).
  Falsifier: a reviewer finding a question with no schema/spec referent.
- **R9 CLAUDE.md role ambiguity** — recommendation is `documentation` if shipped,
  uncatalogued by default (sibling §3); governor confirms the slice-1 §4 wording.
- **R10 template non-determinism** (slice 2) — byte-stable regeneration test.
- **R11 the seeded device skill is mistaken for device qualification** — the
  honesty text in the skill itself, mirroring the synthetic adapter's labelling.
- **R12 MCP shape drift** (a harness changes the skills convention) — frontmatter
  kept to the lowest common denominator; format standardisation remains D2.

## 11. CI cost

No new jobs. Existing gates only: SDK CI lane over the grown tree; main
test/contract/standards suites (+10–14 tests, negligible runtime); three sync
lanes; matrix render; docs-site build (the docs slice adds pages). The expensive
part remains human: the §8 sweep walk and the skill-content review (R8).

## 12. Companion records

- **Slice 2 (authoritative)**:
  `.claude/deep-review/2026-09-19-issue71-slice2-agent-native-scaffold-design.md`
  — the agent-native scaffold: seeding, CLAUDE.md, the corpus-derived
  elicitation table, D3's manifest mechanics, the standalone-MCP fork decision
  (shape (a) with shape (b)'s trigger), golden/file-set pins, the pre-committed
  slice-2 acceptance rule, and the SDK 0.0.3 bump assessment. Where this record's
  former §2–§5.2 detail differs, the sibling wins.
- Slice-1 acceptance: §5.1 here (accepted). Slice 4 (D5) and slice 5 (D6)
  designs: pending their own passes before build.
