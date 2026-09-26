# Standards Versioning and Dependency Management: Requirements PRD

**Status:** Draft v0.2 · **Owner:** platima (contributor), for Stephen (madeinoz67) as standards coordinator · **Tracking issue:** madeinoz67/benchweave#203 (this PRD, the design record and the work all live under it)

## Summary

Stephen, this is the requirements document you asked for on how BenchWeave versions its standards and pins them per device. It follows your model of treating standards like Python libraries under uv. A device is developed on a set version of each standard and stays pinned to it until someone upgrades it on purpose. The gateway supports a declared range for each standard and flags plugins outside that range as non-conforming. Standards move through three stages: dev, RC and released. Code names a standard generically and never by a version literal, and the dependency manager resolves the pin. Today each SDK release vendors one version per standard and admission accepts exactly one OTDP version, so every OTDP bump forces every plugin to restamp. A plugin outside the tree can't move in the same change, so it breaks. This document says what must be true and how we will know. It does not say how to build it. Anywhere I had to sketch a shape to make a requirement testable, it is marked "Direction (non-binding)". My three soft roll-forward mechanisms are candidates, not givens.

Evidence baseline: gateway citations are at `ef969af` (main before #201). SDK citations are from `git show 1b2cc74:<path>` (SDK upstream main before the v0.3.0 tag). Since then, gateway PR #201 has merged (7f3c155), SDK PR #54 has merged (d55c1ca), `v0.3.0` is tagged and gateway #202 paired with it. Numbers below must be re-measured at each increment's merge base.

## 1. Problem and evidence

1. **Exact-match admission.** Gateway admission validates each descriptor against the one active OTDP schema (`src/benchweave/control/documents.py:143-190`, called at `:828`), and that schema's `otdp_version` is a `const` (`standards/otdp/0.2.2/otdp-device-descriptor.schema.json:4-6`). The SDK hard-codes `otdp/0.2.2` at five sites (`validation.py:46,166,188,439,909`). The `const` turns every PATCH into a forced restamp. GOVERNANCE sanctions that restamp as in-arc motion (`standards/GOVERNANCE.md:52-54`), but it sits uneasily with the change-class row "Additive machine errata (backwards-compatible)" (`:38`), and plugins outside the tree cannot move in-arc.
2. **SDK releases vendor one version.** Each SDK tag carries one version per standard: v0.0.1 and v0.0.2 carry pre-reset OTDP 0.3.0, v0.0.3 to v0.1.0 carry 0.2.0, and v0.2.0 carries 0.2.2. A sync replaces the whole vendored tree (SDK `src/benchweave_sdk/standards_sync.py:594-664`). At de132a2 the ADC plugin (parkview/benchweave PR #4) declared `otdp_version` 0.2.0, its `pyproject.toml:47` floor was `>=0.1.0`, and its `uv.lock:158-159` pinned SDK 0.1.0. Run unmodified against SDK v0.2.0, and again against the 0.3.0 release branch (7c56a3e), it scored 23/26. Two tests failed with "'0.2.2' was expected" and one with `unknown_contract_schema: otdp/0.2.0/otdp-runtime.schema.json`. PR #4 was then restamped by hand (2d8dccf: five descriptor values plus the pyproject and the lock). This was its second forced restamp after 963a3aa (0.1.0 to 0.2.0, 2026-09-21).
3. **Restamp churn.** DPS-150 moved 0.2.0 → 0.2.1 → 0.2.2 → 0.2.0 → 0.2.2 in about 24 hours, with lanes red in between (b99b47b, 7d08055, dfff55b, 7722b99; PR #174). The 0.2.1 sweep alone touched 50 files (b99b47b). The 7722b99 message says the sweep "missed plugins/". Under the `const`, a fold of three rewordings became a 39-file, +21,274-line PATCH copy (commit 587f716, see `.claude/deep-review/2026-09-23-devstage-standards-design.md:129-133`). #171 as merged touched 134 files (+43,712).
4. **Drift between repositories.** #166: the SDK vendored OTDP 0.2.1 while the corpus authority said 0.2.0. #187: `compatibility.sdk` stayed at 0.1.0 after the SDK advanced. Both classes now have gateway-side gates: `sdk_version_mismatch` (`src/benchweave/standards/check.py`, which fired on #166 according to the owner's comment there) and `_compare_anchor` (#195, 333859f). Two gaps remain. The SDK cannot check agreement offline (the #166 ruling), and nothing checks agreement of ranges or served sets. Separately, SDK main briefly vendored execution 0.2.0 at SDK version 0.2.0 (SDK 8346b01). The 0.3.0 MINOR bump closed that, justified in PR #54 by the served-set change. That is precedent done by hand, with no gate.
5. **Hard-coded versions.** Hand counts at the baseline:

| Location | Executable literals | Examples |
|---|---|---|
| Gateway `src/` (ef969af, before #201) | 13 | `execution/0.1.0` (`control/coordinator.py:88`, `control/documents.py:48`), `interface/0.1.0` (`interfaces/mcp.py:52`, `interfaces/validation.py:37`), `registry/0.1.1` (`registry/schemas.py:22`), plugin-ui `!= "0.2.0"` (`presentation/contracts.py:247,358`) |
| SDK `src/` (1b2cc74) | 17 | `__init__.py:12` (`OTDP_VERSION`), `:13` (`ADAPTER_API_VERSION`); `validation.py:46,47,48,166,188,439,909`; `scaffold.py:530,578` (`required_features`); `presentation.py:515,692,700,706`; `fixtures.py:44,54` |
| Plugins | not counted | `plugins/fnirsi/dps150/src/benchweave_fnirsi_dps150/descriptor.py` (`otdp_version`, changed in all four churn commits) |
| Gateway comments and docstrings | about 23 lines | some already stale: `host/types.py:1,4` (OTDP 0.2.0), `registry/schemas.py:2` ("1.0.0") |

#201 swept the execution literals by hand across 5 source files, 5 fixtures, 8 docs and about 9 tests. The gateway row is therefore already stale at main, which is one more reason the count has to come from a committed script. Obligation 18's closing clause (`docs/internal/drift-and-obligations.md:224-225`) reads: "a new version-bearing literal anywhere is a defect", and it goes on to require making it "a derived surface or register it here with its motion mechanism". The `src/` literals above are neither derived nor registered. #97's closing comment already routed the SDK literals as a future row. The codebase is still small, so this can be cleared now.

6. **Governance history.** #97 (2026-09-20) withdrew "Range pins, a resolver, lock formats, a mutable `-dev` stage, forward-compat tolerance". The mutable `-dev` stage was later reopened by owner ruling (#168/#169), so reopening has a sanctioned path. The rest stays withdrawn: the -dev record at `:377` says "Not in scope, ever". PR #174 rejected version-matched schema resolution, in part because the SDK leg was "structurally unbuildable". PR #59 (plugin-ui 0.1.1) says cross-version tolerance is not claimed. `standards/otdp/0.2.2/extension-contract.md:15` says "Version matching is exact", and that text is frozen normative prose in every retained OTDP version. GOVERNANCE `:137-140` says the SDK never consumes `-dev` bytes. This PRD asks you to reopen several of these rulings (VR-47).

## 2. Goals, non-goals and success measures

**Goals**
- G1. A device stays on the standard versions it was developed on until it is deliberately upgraded, one standard at a time.
- G2. The gateway and SDK serve a declared range of released versions per standard. Anything outside that range is visibly non-conforming or refused.
- G3. Dev, RC and released stages exist, with semver ordering, retained released history, and a git-sha audit trail for dev work.
- G4. No standard version literal appears in executable code. Code names a standard, and resolution supplies the version.
- G5. Rolling forward is soft.

**Non-goals**
- Designing the resolver, lock format or CLI. That belongs in the design record.
- Approximate tolerance of versions the gateway does not retain. Support means serving retained versions exactly.
- Changing any released standard's bytes, or relaxing copy-never-move.
- Publishing standards to an external index.

**Success measures**

| ID | Measure | Baseline | Target |
|---|---|---|---|
| SM-1 | ADC suite at de132a2, unmodified, against the newest SDK | 23/26 | 26/26 |
| SM-2 | Executable version literals outside the resolver (gateway, SDK, plugins) | 13 + 17 + not counted (hand count, to be re-measured with a committed script) | 0, gated |
| SM-3 | Plugins forced to restamp by a release when their pins stayed in range | every plugin, at every OTDP bump | 0 |
| SM-4 | Version refusals naming pinned version, supported range and move-to version | 0 | 100% |
| SM-5 | MINOR releases with a migration note from their predecessor | none. OTDP has a generic "Migration from 0.1" section (`otdp-specification.md:306`) and no note per predecessor | 100% from adoption |

## 3. Actors and user stories

**Standards maintainer (coordinator)**
- I need to open a dev head, and later an RC, on one standard without disturbing released consumers.
- I need promotion to record the git sha of the dev work it rolls up, so the audit trail survives deletion of the dev directory.
- I need to declare each standard's supported range in one place, so the gateway, SDK, matrix and docs cannot disagree.

**SDK maintainer**
- I need an SDK release to never strand a plugin whose pins are in range.
- I need a changed served set to be visible in the SDK's version or metadata, so one version never covers two sets (SDK 8346b01).

**Gateway**
- I need to validate each plugin against the exact retained version it pins, so devices on different pins can share one bench.
- I need to classify each plugin as conforming, non-conforming or refused, and record that classification.

**Device author (in-tree and out-of-tree)**
- I need to pin my device to the versions I developed on, so a newer standard does not break me until I choose to move.
- As a contributor outside the tree (the ADC case), I need gateway and SDK releases to leave my plugin passing, because I cannot move in-arc.
- I need to upgrade one standard at a time, with one command and a migration note.
- I need to opt into a dev or RC standard explicitly, and run it next to released plugins on my bench.

**Procedure or bench-document author** (execution)
- I need my procedures to keep validating against the execution version they were written for when the gateway's active execution version advances.

**API or MCP client** (interface)
- I need to know which interface version the gateway speaks, and I need a named refusal rather than a schema dump when it changes.

**Bench operator**
- I need to see when a device is non-conforming and what may not work, so I do not trust partial results without knowing it.

**CI**
- I need a lock of exact versions and digests, and a mode that fails on drift, so builds are reproducible.

## 4. Current state

| Area | Today | Evidence |
|---|---|---|
| Released history | Kept digest-frozen. Deleted only by a reset-class event (the 2026-09-16 reset did delete versions) | `standards/GOVERNANCE.md:238-242,248-249` |
| Active pointer | One manifest entry per id (`standards_entry_duplicate`) | `src/benchweave/standards/manifest.py:117-121` |
| Export | One entry per id. Dev heads are never exported | `src/benchweave/standards/export.py:34,53-75` |
| SDK lock | One row per id. `released` and `supersedes` are dropped at sync | SDK `src/benchweave_sdk/standards_sync.py:603-638` |
| Admission | OTDP from the active schema. Execution, interface and registry from `src/` literals. plugin-ui is a literal inside corpus-owned code | `documents.py:143-190`; section 1 table |
| Dev stage | At most one `<target>-dev` head per standard. RC is an advisory `candidate` flag, and a separate RC directory was rejected. The SDK never consumes `-dev` bytes | `GOVERNANCE.md:123-167`, `:137-140` |
| Dev at runtime | `CorpusResolution.DEV_HEAD`: execution only, code only, not available from a wheel | gateway `src/benchweave/.../vendoring.py:31-47`, `src/benchweave/interfaces/app.py:841-864` |
| Bump window | One pure-semver directory per standard per 24 h (#164) | `GOVERNANCE.md:55-74` |
| Declared compatibility | Registry `compatibility.otdp_versions[]`, `adapter_api_versions[]` and `migration_notes_path` exist, but no code reads them | `standards/registry/0.1.1/release-manifest.schema.json:120-190` |
| Per-plugin lock | Only DPS-150 has one: `repository, revision, directory, otdp_version, adapter_api_version, sha256`. It is already a resolved-pin record. A dialect test forces lock == descriptor == active | `plugins/fnirsi/dps150/contracts/lock.json`; `tests/contract/test_plugin_descriptor_dialect.py:61-76` |
| Dev audit trail | Promoted execution 0.2.0 prose (#201) has no sha, only `source` and `lineage` rows. Sha citations appear ad hoc elsewhere (`standards/plugin-ui/0.2.0/validation-report.md:71`). No promotion records one systematically | #201 diff |
| Errors | A raw jsonschema `const` dump or `unknown_contract_schema: <path>`. Neither names a fix | reproduced; SDK `validation.py:124-125` |
| Matrix | One global SDK value and notes string (`src/benchweave/standards/matrix.py:44-47,67-68`). There is already a deprecation cell ("migration guidance pending", `:87-91`) | |
| Release gating | The 8-row SDK release matrix checks stamps only | SDK `docs/internal/release-review-matrix.md:10-19` |

## 5. Functional requirements

RFC 2119 keywords apply. "Standard" means otdp, execution, interface, registry, plugin-ui or plugin-ui-preview. The adapter API version is included wherever it is pinned alongside OTDP.

### (a) Declaring and pinning

- **VR-1 (MUST)** A plugin declares an exact version for each standard it uses. *Why:* this is the device's pin. *Accept:* a machine read of every in-tree and contributor plugin yields an exact version per standard.
- **VR-2 (MUST)** A plugin's pin does not change when a newer version is published, the SDK is released or the gateway's active pointer moves, unless the pin leaves the supported range. *Accept:* publishing a version and cutting an SDK release changes no plugin file or lock, and every plugin still passes its checks.
- **VR-3 (MUST)** The requirement (what a plugin accepts) is kept separate from the resolved pin (what it validated against). *Why:* `otdp_version` is currently both. *Accept:* a plugin can declare a constraint wider than its pin, and only the pin determines what is validated.
- **VR-4 (SHOULD)** Reuse existing carriers (registry `compatibility.*`, `migration_notes_path`, the DPS-150 lock shape) or record why not. *Accept:* the design record addresses each one.
- **VR-5 (MUST)** The design record states which standards are pinned per plugin (Direction (non-binding): otdp, plugin-ui, adapter API) and which are gateway-wide or pinned per document (execution, interface, registry). *Accept:* the design record has a table covering each standard.

### (b) Stages: dev, RC, released

- **VR-6 (MUST)** Stages order by semver pre-release precedence: `X.Y.Z-dev` < `X.Y.Z-rc.N` < `X.Y.Z`. *Why:* this matches semver §11 and PEP 440. *Accept:* a committed ordering test covers dev, rc.1, rc.2 and the release.
- **VR-7 (MUST)** Every released version stays retained, immutable and referenceable by id and version. The only exception is a reset-class event (`GOVERNANCE.md:238-242`). *Accept:* the copy-never-move and closed-world guards still pass, and each retained version resolves by name and version.
- **VR-8 (MUST)** Dev heads are not kept after promotion. The released artefact records the git sha of the final dev state. *Why:* this is the audit trail you described. #201's prose carries no sha, so this is new. *Accept:* in a fresh clone, every promoted version's sha passes `git merge-base --is-ancestor <sha> main`, and a test fails any promotion that omits it.
- **VR-9 (MUST)** Every surface that shows a version (lock, matrix, errors, admission record) distinguishes dev, RC and released. *Accept:* each surface shows the stage.
- **VR-10 (SHOULD)** An RC pin is reproducible: its bytes stay frozen while pinned. *Accept:* two resolutions of the same RC pin give identical digests (see Q4).
- **VR-11 (SHOULD, pending Q9)** A version number is never reused for different content, including across resets. *Why:* the eMeet C960 branch declares OTDP 0.3.0, which exists only under pre-reset numbering (SDK v0.0.1/v0.0.2 vendored `otdp-v0.3.0`; reset precedent at `GOVERNANCE.md:248-249`). *Accept:* resolution refuses a retired identifier with a named error.

### (c) Supported range and non-conforming plugins

- **VR-12 (MUST)** The gateway declares a supported range per standard with explicit bounds (for example `>=0.2.0,<0.3.0`). *Accept:* the range is stored in one committed place and read by both the gateway and the SDK.
- **VR-13 (MUST)** A plugin pinned to a retained, in-range version is validated against that exact version and classified **conforming**. *Why:* serving retained versions exactly is not the tolerance PR #59 disclaimed. *Accept:* two plugins pinned to different in-range versions are both admitted in one gateway process, each against its own schema bodies (see control C2).
- **VR-14 (MUST)** A plugin pinned to a retained but out-of-range version is classified **non-conforming** and is never silently treated as conforming. *Accept:* an OTDP 0.1.2 fixture is classified non-conforming.
- **VR-15 (MUST)** A plugin pinned to a version the gateway does not retain (newer and unknown, or a retired identifier) is **refused**, with an error that names what is supported. *Divergence from your direction:* you said out-of-range plugins are flagged and some functions may work. I propose refusal here only because the gateway has no schema to check against. Q6 puts that to you. *Accept:* a 0.3.0 fixture is refused with the VR-37 error.
- **VR-16 (MUST)** Non-conforming status is shown at admission, in the API and UI view of the device, and in every run record that uses it. *Accept:* all three surfaces show it for the VR-14 fixture.
- **VR-17 (MUST)** The permitted behaviour of a non-conforming plugin is defined before the feature ships. Direction (non-binding) candidates: full operation with flagged results, read-only, or only operations whose schemas are unchanged between the pin and the range. *Accept:* the design record picks one, and a test shows one permitted and one refused operation.
- **VR-18 (SHOULD)** A non-conforming plugin loads only after an operator acknowledgement that is recorded. *Accept:* without it admission refuses. With it, the acknowledgement appears in the record.
- **VR-19 (MUST)** A change to the supported range never alters a run in progress. The next admission applies the new classification, and stored run records keep the classification they had. *Accept:* a fixture narrows the range mid-run and the run record is unchanged.
- **VR-20 (MUST)** A gateway can admit a plugin pinned to a dev head, identified by content (VR-29), next to plugins pinned to released versions on one bench, with the dev stage shown per VR-9. *Why:* "dev and prod side by side". This needs the VR-47 ruling. *Accept:* on one bench, a dev-pinned plugin and a released-pinned plugin are both admitted, each against its own bytes.

### (d) No hard-coded versions

- **VR-21 (MUST)** Executable code in the gateway, the SDK and plugins refers to a standard only by generic name. Versions come from resolution. A plugin's own pin declaration is data, not a literal. *Why:* hand sweeps miss sites (#201; 7722b99 "missed plugins/"). *Accept:* SM-2 reaches 0.
- **VR-22 (MUST)** A committed gate counts literals with a committed script and fails CI on any new literal outside the resolver and its declared data files. *Accept:* a planted literal fails the gate, and removing it passes. Until SM-2 reaches 0, the gate MAY run in ratchet mode, where the count cannot rise.
- **VR-23 (MUST)** Code that needs a specific version gets it from the plugin's pin through the resolver. *Accept:* the VR-13 test passes with no version literal in admission code.
- **VR-24 (SHOULD)** Comments, docstrings and user docs render versions from the lock or name none. *Accept:* a docs gate, extending the site hygiene pin (`drift-and-obligations.md:188-194`), covers `docs/`, `user_guide/` and plugin READMEs.
- **VR-25 (SHOULD)** Corpus-owned code (`presentation/contracts.py`, digest-pinned inside plugin-ui) follows VR-21, or the exception is recorded. *Accept:* the design record states the treatment.

### (e) Resolution, lock and inter-standard constraints

- **VR-26 (MUST)** Resolution turns declared constraints into a lock that fixes each standard's exact version and content digests. *Why:* exactness underpins the digest rules. *Accept:* resolving the same inputs twice gives byte-identical locks. Direction (non-binding): `id + version + sha256` per file.
- **VR-27 (MUST)** Resolution prefers the versions already locked and moves one standard only on an explicit upgrade, leaving the others untouched. *Why:* uv `--upgrade-package` and cargo `update -p --precise` behave this way. *Accept:* upgrading `otdp` leaves every other row byte-identical.
- **VR-28 (MUST)** Pre-releases are excluded unless explicitly requested, per standard. *Why:* uv, PEP 440, Cargo and npm all do this. *Accept:* with a dev head open and no opt-in, the released version resolves. An opt-in for one standard affects only that standard.
- **VR-29 (MUST)** A dev pin records content identity (git sha and digests), not only the `-dev` label. *Why:* the label is mutable, and `standards_version_required` must hold. uv git sources and Go pseudo-versions solve the same problem. This conflicts with `GOVERNANCE.md:137-140` and needs VR-47. *Accept:* editing the dev head makes a locked check of a consumer pinned to it fail.
- **VR-30 (MUST)** CI can verify, with no network, that the lock satisfies the declared constraints, and fails on drift. *Accept:* a hand-edited constraint fails CI. Direction (non-binding): a `--locked` mode.
- **VR-31 (MUST)** A released standard declares its constraints on other standards and on the adapter API as data. Resolution refuses a lock that combines conflicting standards, with a named error. *Why:* without this, "resolution" just reads pins. For example, execution 0.2.0 states that it preserves the OTDP 0.2.0 and adapter API 1.1 runtime interfaces (#201). *Accept:* a fixture that pairs an execution version with an OTDP pin outside execution's declared range is refused.

### (f) SDK releases stop forcing the newest standard

- **VR-32 (MUST)** A plugin can validate offline against any released version inside the supported range, whatever SDK version it uses. *Why:* under PKG-1 the SDK cannot reach the gateway checkout, so served versions must be available locally. *Accept:* SM-1, with the network disabled. Direction (non-binding), two options for the design record to weigh: bundle every in-range version in the wheel, or distribute standards as independently versioned artefacts resolved into the plugin's lock, which is closer to "referenced like a Python library". Either needs the manifest and export to carry several retained versions per id (today `manifest.py:117-121`, `export.py:34`), which PR #174 point 2 found unbuildable.
- **VR-33 (MUST)** Upgrading the SDK never changes which standard version a plugin validates against. *Accept:* bumping only the SDK in a fixture plugin leaves its validated versions and results unchanged.
- **VR-34 (SHOULD)** The scaffold writes a constraint and a lock rather than an exact `benchweave-sdk==` pin (`scaffold.py:663-675`). *Accept:* a scaffolded plugin survives an SDK minor release with no edits.

### (g) Upgrade and soft roll-forward

My three mechanisms are candidates. Recommended degrees for early days:

| Candidate | Recommended degree now | Other options | Cost |
|---|---|---|---|
| Support window | MUST cover at least the previous released version of each standard | N-1 minor; N releases; date-based (Kubernetes 4a, RFC 8594 Sunset) | multi-version serving, SDK/gateway equivalence across served versions, larger artefact |
| Clear error | MUST (VR-37) | deprecation warnings before removal | new refusal prefixes (the prefixes are an API) |
| Migration note | MUST for MINOR, SHOULD for PATCH | a machine-readable from→to record | per-release authoring |

- **VR-35 (SHOULD, until Q3 fixes the unit)** A supported version is deprecated for at least one window before it leaves the range, with a warning during the window. *Accept:* once Q3 is answered, a version that is deprecated but in range is admitted with a warning that states the removal point.
- **VR-36 (MUST for MINOR, SHOULD for PATCH)** Each release has a migration note from its predecessor, covering plugin-facing changes and the mechanical steps, and it is walked in the release-review matrix. *Accept:* SM-5, checked by a gate. This absorbs the old release-matrix row.
- **VR-36a (SHOULD)** Upgrading one standard in a plugin, including restamping contract URNs and digests, is one step whose result validates. *Why:* the ADC restamp 2d8dccf was five mechanical values. *Accept:* applied to the ADC at de132a2, SDK `check` then passes.

### (h) Errors and diagnostics

- **VR-37 (MUST)** Every version refusal or non-conforming classification names the standard, the pinned version, the supported range, the nearest move-to version and the migration note. *Accept:* SM-4, checked against the three ADC failures and the VR-14/VR-15 fixtures.
- **VR-38 (MUST)** Version refusals use new, stable prefixes. The existing prefixes keep their meaning. *Accept:* existing prefix tests are unchanged, and the new prefixes are listed in the invariants.
- **VR-39 (MUST)** An offline resolve that lacks a pinned version's bytes fails with a named error and makes no network call. *Accept:* a fixture with the cache removed produces that error.
- **VR-40 (MAY)** A "why" query explains which constraint selected each locked version.

### (i) Governance fit

- **VR-41 (MUST)** The 24-hour window keeps limiting released versions, and how RCs count is recorded. *Accept:* `test_train_window.py` passes, with a new RC case.
- **VR-42 (MUST)** One dev head per standard, and gateway-first flow through export, stay in force. *Accept:* the existing guards pass.
- **VR-43 (MUST)** A range change is a coordinator decision. *Accept:* a gate refuses a change to the range file that lacks a linked ruling reference.
- **VR-44 (SHOULD)** A version can be withdrawn (yanked): it still resolves for an existing lock, a new resolution refuses it, and a named warning is shown. *Why:* the #171 case. *Accept:* a yanked fixture behaves both ways.

### (j) Certification and evidence

- **VR-45 (MUST)** Evidence locks and certification stamps move only when that plugin's pin moves. *Why:* PR #174's "stamp and evidence lock move together" was forced on every bump. *Accept:* the dialect test (`test_plugin_descriptor_dialect.py:61-76`) becomes a within-range test, and DPS-150 passes while the active version advances past it.
- **VR-46 (MUST)** Run evidence records each device's validated versions and conformance class. *Accept:* a mixed-version bench's run record shows both.

### (k) Tooling and rulings

- **VR-47 (MUST)** Before design, an owner ruling covers five points. (1) It reopens #97's withdrawn range pins, resolver, lock format and tolerance items, noting the -dev record `:377` "Not in scope, ever". (2) It amends CON-10 and addresses PR #174 point 2. (3) It rules on `GOVERNANCE.md:137-140`, the rule that the SDK never consumes `-dev` bytes. (4) It says whether `standards/otdp/0.2.2/extension-contract.md:15` ("Version matching is exact") is out of scope for gateway ranges or is superseded in the next OTDP version, since released copies cannot change. (5) It says how PR #59 reads under "serve retained versions exactly". *Accept:* the ruling is linked from #203.
- **VR-48 (MUST)** Authors and CI can list available and supported versions, pin, upgrade one standard to a precise target, and check constraint against lock against range. *Accept:* each capability has a fixture test. Direction (non-binding): `list`, `pin`, `upgrade`, `check` commands.
- **VR-49 (MUST)** An upgrade that fetches does so only from the gateway's published history, with digests verified against the gateway's standards manifest. *Accept:* a fetched file whose digest does not match is refused.

### (l) CI and drift gates

- **VR-50 (MUST)** One source of truth for ranges and served sets feeds the gateway, the SDK, the matrix and the docs. *Why:* the gateway gates `sdk_version_mismatch` and `_compare_anchor` cover single values, not ranges. *Accept:* a mismatch planted in each consumer fails a gate.
- **VR-51 (MUST)** The SDK checks agreement without a gateway checkout. *Why:* the #166 ruling. *Accept:* SDK CI catches a planted version or digest disagreement offline.
- **VR-52 (MAY)** The matrix renders one row per retained version, showing stage, range membership, deprecation and migration note, extending the existing cell (`matrix.py:87-91`).

## 6. Non-functional requirements

- **NFR-1 Offline.** Resolution, validation and checks run from local bytes. Only an explicit upgrade fetches (VR-49). *Accept:* the suite passes with the network disabled.
- **NFR-2 Determinism.** The same inputs give byte-identical locks, bundles, matrices and stamps (CON-12, CON-13). *Accept:* a second run produces no diff.
- **NFR-3 Integrity.** Exact bytes are decoded and their digest verified before schema validation, for every served version (CON-1, A14). *Accept:* a flipped byte is refused.
- **NFR-4 Performance.** No measurable regression on today's single-version admission. *Accept:* measured before and after on the same bench.
- **NFR-5 Backward compatibility.** Every descriptor valid today (in-tree at 0.2.2, the ADC at 2d8dccf) and the ADC de132a2 snapshot at 0.2.0 validate unedited once the range covers them.
- **NFR-6 Layouts.** Resolution by name works in the wheel and in the repo checkout (`vendoring.py:50-55`). *Accept:* tests run in both.

## 7. Open questions for the maintainer

1. **Naming.** You joked "SUV", I suggested "benchver". What should the tool and the lock file be called?
2. **Tracker.** #203 now serves as the dependency-management tracker #97 promised. Can you confirm?
3. **Range bounds.** Inclusive lower bound and exclusive upper bound with 0.x caret semantics (`^0.2` = `>=0.2.0,<0.3.0`)? Is the window measured in minors, releases or days?
4. **RC.** Should an RC be an immutable `X.Y.Z-rc.N` directory (overturning `GOVERNANCE.md:163-167`) or a frozen dev snapshot pinned by sha? Does it count against the 24 h window?
5. **Where the requirement lives.** In the descriptor (relaxing the `const`, or adding a field), in registry `compatibility.*`, or in a plugin lock file?
6. **Unretained and out-of-range versions.** Should a newer unknown version be refused (VR-15), or flagged non-conforming and run with only what the gateway can validate? Which VR-17 option do you want? Should acknowledgement be per bench or per device?
7. **Git sha.** The prose you remembered: plugin-ui validation reports cite shas ad hoc, and #201 carries none. Is VR-8 the right fix?
8. **SDK versioning.** Should a change to the served set bump SDK MINOR, as in 0.3.0? Or should the SDK declare its served ranges explicitly and keep its own semver, or stop serving standards if they become separate artefacts (VR-32)?
9. **Pre-reset identifiers.** Retire or reserve OTDP 0.3.0 and the others, so the eMeet branch re-targets?
10. **Is 0.2.1 in range?** #171 re-rolled 0.2.2 as a PATCH of it. Should 0.2.1 be withdrawn?
11. **Bench constraints.** Must mixed OTDP pins on one bench satisfy the bench's execution constraint (VR-31)?
12. **Adapter API and `required_features`.** Same scheme, or versioned independently?

## 8. Suggested increments

Each increment's PR goes against a sub-issue of #203. Each merged PR opens exactly one follow-on issue that lists its deferrals.

**Increment 1 (SDK only).** Prerequisite: the VR-47 ruling. Scope: VR-12 for OTDP only (range stored in one committed place and read by the SDK, with the matrix deferred), VR-13 and VR-15 on the SDK side, VR-32 and VR-33, VR-37 and VR-38, and VR-22 in ratchet mode. Retained in-range versions are 0.2.0 and 0.2.2. 0.2.1 is left out until Q10 is answered.

**Increment 2 (gateway).** VR-13 and VR-15 in admission, and extending the SDK/gateway equivalence census (`tests/sdk/test_descriptor_equivalence.py`) across both served versions, so the SDK never accepts what the gateway refuses.

**Increment 3.** VR-21 to SM-2 = 0 in the gateway, the SDK and plugins.

Deferred to #203: non-conforming flagging (VR-14, VR-16 to VR-19), dev/RC pins, inter-standard constraints and matrix rework.

**Pre-committed acceptance control (increment 1):**
- **C1, positive, not gameable.** The ADC suite at de132a2, run unmodified, scores 26/26 against the increment's SDK build. Before building, the exact command is committed (Direction (non-binding): install the ADC checkout from `git archive de132a2` plus the SDK build into a clean venv, then `pytest tests/adc/test_adapter_conformance.py`), together with its baseline output: 23/26 against v0.2.0 and v0.3.0, with the three named failures. C1 runs that same command. The ADC repository must not change.
- **C2, per-version content specificity.** The design record names, before building, a schema element that differs between 0.2.0 and 0.2.2 (candidate: `otdp-transport-provider.schema.json`, present only in 0.2.2). A document using that element is accepted when pinned to 0.2.2 and refused when pinned to 0.2.0, and a reverse case is covered as well. The `const` alone cannot pass this control.
- **C3, negative (interim).** A 0.3.0 descriptor is refused, and the error names the pinned version, the range and a move-to version. 0.1.2 is refused only until VR-14 lands, at which point it becomes non-conforming.
- **C4, literal ratchet.** The committed script, re-measured at the merge base, reports a count no higher than the baseline, and a planted literal fails CI.
- **C5, no regression.** In-tree descriptors pass unedited, and the existing refusal-prefix tests are unchanged.

Increment 1 is done only when C1 to C5 pass on the merge result. The refute pass should start with C2.
## Coordinator review and rulings: Draft v0.2

BLUF: this is good work, and the evidence checks out almost line for line. I've reviewed it end to end and I'm answering the twelve open questions below plus the VR-47 ruling points, so you can shape the design record from a settled base. Findings to fold into a Draft v0.3 are at the end. The non-goals stand: copy-never-move holds, approximate tolerance stays disclaimed.

Where my first pass weighed an alternative and rejected it, the rejected option is named in one line so the record shows the reasoning.

### The twelve answers

**Q1 Naming.** The tool is `benchver` — your suggestion, and the right one. Mine was a joke. Lock files get no new names: plugins keep `contracts/lock.json`, the SDK keeps `standards-lock.json`. Both names already carry weight and a third lock filename is just more surface. Preference-only call; I'll swap the tool name if something clearly better turns up, nothing in the design depends on it.

**Q2 Tracker.** Confirmed. #203 is the dependency-management tracker #97 promised — its close comment left those findings for me to raise, and this is the issue that raised them. The PRD, these rulings, the design record and every increment sub-issue hang off this one. Before the first increment sub-issue files I'll sweep the retired SDK tracker for dependency stragglers. Checked just now: its one open item is a capture-writer item already tracked here (#206), so the sweep is empty today.

**Q3 Range bounds and support window.** Inclusive lower, exclusive upper, 0.x caret semantics: `^0.2` means `>=0.2.0,<0.3.0`. The support-window floor is measured in **released versions**, not days and not minor lines: a declared range covers at least the two most recent released versions of each standard. The 24-hour train floor (#164) stays the only clock. Alternative considered and rejected: "previous minor" as the floor — on today's corpus that drags OTDP's 0.1.x line into range on day one and contradicts your own C3. Also: promote the 7g "MUST cover at least the previous released version" into a numbered requirement; right now it's a homeless MUST living in a candidate table.

**Q4 RC.** No RC directory — the 2026-09-23 ruling stands. An RC is the advisory `candidate` flag on the dev head, and an RC pin is that head frozen by content: git sha plus per-file digests. RCs don't count against the 24-hour window because no RC directory exists to count; promotion is the only bump event. VR-6's accept gets amended: the ordering test covers dev < release and the identifier namespace refuses rc.N shapes. RC is a boolean, never an identifier — a comparator for identifiers no surface may issue would just invite someone to mint them.

**Q5 Where the requirement lives.** Three carriers, three jobs:

1. `otdp_version` in the descriptor stays the device's exact pin. The const stays; validation selects the schema of the pinned version, which turns the const from the churn source into the exactness engine.
2. The plugin's accepted range (the requirement) is authored data in `contracts/constraints.json`, a sibling of the lock. Not inside the lock: your own VR-26 makes constraints the input to resolution, and a fresh plugin has no lock yet — and the DPS-150 lock is a generated evidence record, not an authored file. Not registry `compatibility.*`: that belongs to registry release manifests.
3. The resolved pin stays in generated `contracts/lock.json` (exact versions and digests).

Authority chain: the constraint feeds resolution, resolution writes the lock, validation uses the lock's exact version. Before finalising shapes, check the registry standard — it already ships a package-lock schema and the gateway already has a resolver-to-lock writer we should extend rather than reinvent.

**Q6 Unretained and out-of-range.** Two classes, two answers. A version we don't retain (newer and unknown, or a retired identifier) is **refused** — VR-15 stands as written; there are no bytes to validate against, and "run it on what we can guess" is the opposite of how we work. A retained but out-of-range version is **non-conforming**: full operation with flagged results, validated exactly against its own pin's bytes, shown on every surface VR-16 names, and loaded only after a recorded per-device operator acknowledgement (owned by the admission record; per-device, so one ack can't blanket a bench full of unknown pairings). The permitted-behaviour definition carries a protective-path invariance clause and its fixture: it must never weaken the protective path, run evidence, or cross-host results. For increment 1's interim, retained-out-of-range refusals use stable named prefixes that flip to the non-conforming class when VR-14 lands — an added class, never a meaning change.

**Q7 Git sha.** VR-8 is the right fix, with one correction: the recorded sha is the promotion's **landing commit on main** — the commit the squash or merge created. Your accept as written can't pass on this repo: squash landings are our practice (PR #196 folded eight commits into one), and a branch tip is never an ancestor of main. The final dev-head edit sha rides along as optional provenance. Forward-only; digest-frozen rows untouched.

**Q8 SDK versioning.** The SDK keeps serving standards from the wheel, bundling every in-range retained version. That's the smaller mechanism by a wide margin, the gateway wheel already ships all retained released versions, and the external-index non-goal stands — so "stop serving" is off the table. Bump classes split, and a gate asserts the class matches the change (a new release-review matrix row): **PATCH** when the served set grows inside the declared range (invisible to pinned plugins once VR-33 holds); **MINOR** when the declared range changes. Read against that split the 0.3.0 precedent makes sense — "MINOR on feature weight: the vendored corpus moved" was a range-class change. The SDK declares its served set and range in its own lock, mirrored from the gateway's one committed authority through the export bundle (PKG-1: the SDK never reads the gateway checkout; the range travels via committed artifacts). Alternative rejected: blanket MINOR on any served-set change.

**Q9 Pre-reset identifiers.** **Retired**, permanently, recorded in an identifier registry kept outside the corpus where a reset can't delete it. The seed is the pre-reset identifiers minus any the live tree legitimately re-owns — plugin-ui 0.1.0 stays off the list, because the post-reset tree retains a live 0.1.0 and the live version owns that number. Resolution refuses a retired identifier with a named error pointing at the re-target. For numbering: OTDP's next MINOR skips 0.3.0 and goes to 0.4.0. Those numbers shipped in real wheels, so the honest record is "used and dead", not "held".

**Q10 Is 0.2.1 in range.** It stays: retained, in range, served. The served set becomes "all retained in-range versions", which for increment 1 is 0.2.0, 0.2.1 and 0.2.2. That closes the gap the increment-1 served set as written leaves (0.2.1 is retained and inside your own example range) without inventing a fourth classification. Withdrawing it would also misread a governance win as a defect: copy-never-move forced 0.2.2 into existence precisely because 0.2.1 was frozen. Yank (VR-44) gets designed whole when a genuinely defective version appears, recorded as a deferral. Alternative if you'd rather exercise yank now: withdraw 0.2.1 in increment 1 — but that pulls a yanked classification plus VR-13 and VR-19 amendments into increment 1's scope, and that's how we'd get yank wrong under deadline pressure.

**Q11 Bench constraints.** Yes. Every device pin on a bench must sit inside the bench execution version's declared cross-standard constraints or the combination is refused with a named error — but the binding is **pairwise, not uniform**: device A on 0.2.0 and device B on 0.2.2 share a bench as long as both sit inside the execution contract's declared range. The constraint rows are committed side-table data beside the corpus: frozen bytes can't gain rows, so one row per released version, coordinator-governed — and already-released versions get retrofitted rows at adoption (execution 0.2.0's row cites #201's stated interface preservation) so VR-31's fixture is buildable on day one, not someday.

**Q12 Adapter API and required_features.** Same scheme as the standards: pinned alongside OTDP, resolved from the pinned OTDP version's own bytes, riding the OTDP row in the lock. Not a seventh standard — GOVERNANCE's promotion trigger hasn't fired. `required_features` stay exact-match per-identifier as the extension contract rules them. One wording amendment rides the motion below: "Deliberately versioned elsewhere" anchors the authority to the active schema's const; under multi-version admission that must read the **pinned** version's const.

### The VR-47 ruling

This reopens items closed "Not in scope, ever", so I'm recording it as a supersession on new evidence rather than dressing it up as a triggered reopen: the out-of-tree breakage axis (the ADC case) post-dates both closures.

1. **Reopened:** range pins, the resolver, lock formats. **Stay withdrawn:** forward-compat tolerance and external indexes — your own non-goals, unchanged.
2. **CON-10 is amended, and PR #174 is superseded on both its grounds together.** The amendment keeps what CON-10 protects — one shared authority, the retained corpus and manifest — and drops what it doesn't need: the singularity of the active pointer. A descriptor validates against exactly one OTDP version, its pin, resolved from the retained corpus, digest-verified. Multi-version serving answers the single-version-tree ground; wheel-bundling answers "structurally unbuildable". The amendment lands as an append riding the increment PR with the equivalence-census and dialect-guard rewrites; the one-entry-per-id manifest shape is undisturbed.
3. **GOVERNANCE "the SDK never consumes -dev bytes" is replaced, not reinterpreted.** Consumers may pin a dev head under three conditions: explicit per-plugin opt-in; the lock row records content identity (sha plus per-file digests); every coupled guard keeps its force (window promise, wheel exclusion, promotion deletes dev bytes).
4. **"Version matching is exact" gets both halves.** It is out of scope for gateway ranges — a range never fuzzy-matches; each plugin validates against exactly one retained version's bytes under its own const — and it is superseded with a one-line clarification in the next OTDP version copy. For the record: that sentence is tier-2 prose with no corpus-manifest rows, so the freeze on it is governance, not digest.
5. **PR #59 stands unchanged.** Per-plugin exactness is the same guarantee #59 recorded, relocated from one global gate to N per-pin gates. Nothing is tolerated: out-of-range is non-conforming, unretained is refused.

Two points the five-point list missed, folded in: RC directories stay rejected (with the Q4 VR-6 fix), and the Withdrawal change-class row is deferred with VR-44 (per Q10) instead of landing early. All governance and invariant text changes consolidate into **one amendment appendix in the design record**, ratified once: the 137-140 replacement, the "deliberately versioned elsewhere" active-to-pinned wording, the CON-10 append, and the Withdrawal row when yank is designed. Range changes remain coordinator decisions (VR-43).

### Findings to fold into Draft v0.3

The evidence in the document is in good shape. I had the citations checked against both baselines and they hold almost line for line: the admission path, the version const, the GOVERNANCE anchors including the 24-hour floor, the frozen "version matching is exact" sentence in every retained OTDP copy, and the thirteen-literal gateway count all verified. What needs fixing:

**One critical.** The increment-1 served set of {0.2.0, 0.2.2} leaves 0.2.1 retained, inside your own example range, and unserved — the VR-13/14/15 taxonomy has no bucket for that state. The Q10 answer closes it.

**High.**

- C1's "not gameable" label isn't earned yet: a dispatch table hard-coding exactly {0.2.0, 0.2.2} passes C1, C2 and C4 while failing interval semantics for any future version. Give C1 a third in-range version fixture (0.2.1 answers that), and make the committed command explicitly bypass the ADC checkout's own uv.lock SDK pin, or it tests SDK 0.1.0 by accident.
- VR-1, VR-3 and VR-26 together leave two authorities for the validated version; the Q5 authority chain fixes the wording.
- The out-of-range story contradicts itself across VR-2, VR-14, VR-18 and SM-3; the Q6 taxonomy fixes it.
- VR-8's accept can't pass under squash landings; Q7 amends it.
- C3's interim 0.1.2 refusal breaks the final taxonomy and VR-38's prefix stability; the Q6 interim rule fixes it.
- VR-6 and VR-10 assume rc.N identifiers exist as pinnable forms; Q4 fixes that.
- "Increment 1 (SDK only)" is wrong: under PKG-1 the SDK can't read the gateway checkout and still vendors one version per standard, so offline multi-version validation needs a gateway export change. Label increment 1 a two-repo landing (SDK PR, gateway export PR, submodule pointer commit).
- The registry standard already ships lifecycle machinery (yanked, revoked, deprecated, support state) and a package-lock schema, and the gateway already has a resolver-to-lock writer. Extend those; don't invent parallel mechanisms.

**Medium, worth fixing while you're in there.** Increments 2 and 3 have no pre-committed acceptance controls (increment 2 is the riskiest slice). Goal G3 has no success measure. The literal-counting domain needs to name tests and scripts (there's already an executable corpus literal in `tests/faults/`). VR-50's consumer list omits the website stamps surface. Runtime SDK/gateway range skew needs a rule. Three accept clauses (VR-9, VR-38, VR-19) are too weak to fail. NFR-4 needs a numeric threshold. And a CI-budget line is owed given four new gates plus the clean-venv control.

**Numbers to re-measure at the merge base** (you already say this; the specifics): the gateway literal count at main is still thirteen sites — #201 re-versioned values but removed nothing — comment and docstring lines number about 28, not 23, and #201 touched 10 tests, not "about 9". One attribution note: the 23/26 ADC figure is your reported run; wherever it gets repeated it should say so.

### Next

Fold the above into Draft v0.3 and the design record can take shape from the amended PRD with the rulings above as its boundary. Open increment 1 as a sub-issue of #203 once v0.3 lands — it's still the right first slice (kill the ADC-class break, start on the literal debt) and per the finding above it opens as a two-repo increment. Happy to review the design record whenever it's ready.
