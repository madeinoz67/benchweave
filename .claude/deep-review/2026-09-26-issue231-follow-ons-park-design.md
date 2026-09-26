# Dataset/invoke follow-ons (issue #231) — per-row dispositions

**Date:** 2026-09-26 · **Issue:** [#231](https://github.com/madeinoz67/benchweave/issues/231)
**Lineage:** the consolidated follow-on home for deferral rows 1, 5 and 7 of the
#146 record (`.claude/deep-review/2026-09-25-issue146-invoke-dataset-design.md`,
§6 + Amendments 1–3). That record's deferral table is the authority; this document
is the per-row disposition the tracker issue was opened to receive.
**Tree:** `main` @ `9ad0301` (post-#230-merge; slice 2 + slice 3 of #146 landed).
**Verdict: PARK all three rows — no BUILD slice in this increment.**
Row 1 PARK-trigger-not-fired (and bump-gated for its class-data-dependent half);
Row 5 PARK-trigger-not-fired; Row 7 PARK-trigger-not-fired with the fixture-key
blocker verified to hold mechanically on a contributor machine.

This is a recorded-negative outcome, not an empty one: each row carries (a) the
evidence its reopen trigger has not fired, (b) a mechanism sketch grounded in the
shipped #146 code so a future build starts without re-deriving it, and (c) a
pre-committed acceptance rule for the first slice WHEN the trigger fires. Nothing
here re-opens a decision the #146 record closed; two of its premises are SHARPENED
by inspection (§2.3, §4.2) and recorded as amendments-to-understanding, not edits
to that record.

**Constraint honored:** the principal's no-standards-bump directive for this run.
No row requires corpus motion to park; the one row whose build would require it
(row 1's M06/M13 half) is parked twice over (§2.4). Zero bytes under `standards/`
move, no contract locks, no version strings, no repin.

---

## 0. Grounding — what was read, not assumed

- The #146 record in full (all amendments), `docs/smart-test-gateway-decisions.md`
  (A01–A14), `docs/internal/invariants.md` (CTL/STO/CON/REG), 
  `docs/internal/drift-and-obligations.md`.
- The shipped slice-3 code: `src/benchweave/content/dataset_services.py` (the
  controller, `mint_dataset_id`, the publish path with its M-subset),
  `src/benchweave/registry/otdp_contracts.py` (resolution + the soft/hard arms).
- The corpus: `standards/otdp/0.2.2/measurement-model.md` (§7's M01–M15 table),
  `standards/otdp/0.2.2/device-profile-catalog.schema.json`,
  `standards/otdp/0.2.2/extension-contract.md:62-64`.
- The trigger landscape: the open tracker (issues #92–#95, #203, #207, #209–#210,
  #215–#228), the in-tree plugins (`plugins/fnirsi/dps150/…/descriptor.json`,
  `plugins/benchweave/sim_psu/…/plugin.py:142`, sim_scope), the fixture lattice
  (`fixtures/registry/`, `scripts/registry/build_fixtures.py`,
  `scripts/registry/registry_common.py`, `scripts/registry/publish_dev.py`,
  `tests/contract/test_registry_fixtures.py`, `.github/workflows/ci.yml:22-37`),
  and `tests/integration/test_demo_lattice_streaming.py`.
- Pre-flight (already done before this design, not repeated): no open PRs on
  either repo; #146 s2/s3 merged at `9ad0301`; no prior #231 run state in the
  benchweave vault.

---

## 1. The hard constraint — where the guide lives, and per-row bump exposure

**Ruling: the device-developer guide is host-side documentation, not corpus
bytes.** Evidence:

- A file search for `device-developer-guide` over the whole tree returns exactly
  one file: `docs/device-developer-guide.md`. Nothing under `standards/` renders
  or mirrors it.
- `docs/internal/drift-and-obligations.md` obligation 3 maps plugin-visible
  behavior → `docs/device-developer-guide.md` as a docs surface, distinct from
  the corpus obligations (1, 2, 6).
- Obligation 18(k) treats the guide's `../standards/otdp/<version>/` *links* as
  version-bearing pointers swept in-arc at bumps — pointers into the corpus,
  never corpus bytes themselves.

Therefore guide prose edits are legal without a standards bump (this is also how
#146 moved "guide prose" with no bump). Per-row exposure under the directive:

| Row | Corpus bytes? | Contract locks / version strings? | Guide edits needed to park/build? | Exposure |
|---|---|---|---|---|
| 1 | **Yes for M06/M13** — the quantity substrate does not exist in the closed catalog schema (§2.3); adding it is a corpus revision | Yes (catalog schema + catalog JSON re-version) | None to park (guide:394 already names the checks author-side) | **Bump-gated** for the class-data half; host-only for the manifest-internal subset |
| 5 | No — the corpus at `extension-contract.md:64` already says "derived from the current operation/acquisition" and makes re-fetch idempotency permissive ("may return") | No | Guide lines 130/292/392 document `ds:{operation_id}`; a build would edit them — legal (docs/) | **None** |
| 7 | No — `fixtures/` + `scripts/` + `plugins/` + tests; CON-2 lockstep moves as fixture lattice, not corpus | No | None to park | **None** |

---

## 2. Row 1 — class-semantic M-checks at publish (M05–M09, M12, M13)

### 2.1 Has the trigger fired? No.

Recorded trigger: *"first profile whose required-quantity or class-output
validation is wanted at the gateway."* Reading of the tree at `9ad0301`:

- **No admitted class plugin wants it.** The only admitted real plugin,
  DPS-150, declares `capabilities: ["identify", "read"]` — no invoke, no
  profiles, no contracts (`plugins/fnirsi/dps150/src/benchweave_fnirsi_dps150/descriptor.json`,
  `capabilities` block; its own description: "no DC PSU profile or hardware
  qualification"). It cannot produce datasets through the invoke lane at all.
- **The invoke-capable plugins in-tree are sims** (`sim_psu` routes
  `OperationVerb.INVOKE` at `plugins/benchweave/sim_psu/src/benchweave_sim_psu/plugin.py:142`;
  sim_scope likewise) — test/demo fixtures whose manifests are authored to pass
  the implemented subset. Nothing in their tests or vectors asks the gateway to
  verify class semantics.
- **No open issue asks for it.** The device-plugin proposals (#92 DHO-924S, #93
  RD6024, #94 DM858, #95 webcam) are pre-admission proposals; the registry arc
  (#223–#228) is records/publishing; the dependency arc (#215–#221) is version
  pinning. The recorded premise that "the device-classes quantity data wiring is
  its own train" remains true: no such train exists in the tracker.
- **The honest boundary is already documented and current**: 
  `docs/device-developer-guide.md:394` names M05–M09, M12, M13 as author-side
  obligations, with M14 (load-time) and M15 (derivation path) located elsewhere —
  the #230 merge's guide rider (`ad10045`) refreshed exactly this paragraph.

### 2.2 Mechanism if built (grounded, for whoever reopens)

The insertion point exists and is proven: `dataset_publish`'s validation ladder
in `src/benchweave/content/dataset_services.py` (`_check_m_structural` →
`_check_m10_correlation` → `_check_m11_records`) — a `_check_m_class_semantic`
would slot after `_check_m10_correlation`, reading the same controller state
(`dispatch_state(operation_id)` already carries the action and resolved input).
The corpus definitions it would implement are `measurement-model.md` §7's rows
M05–M09/M12/M13, with §3–§5 prose as the coherence rules.

### 2.3 Structural finding (sharpening the recorded premise)

The recorded blocker says these checks "require device-classes quantity data
wired to profiles." Inspection makes it precise — and splits the family:

- **The machine-readable substrate for M06/M13 does not exist.** The pinned
  catalog schema (`standards/otdp/0.2.2/device-profile-catalog.schema.json`) is
  closed (`additionalProperties: false` everywhere) and defines each profile as
  exactly `{id, title, channel_roles, required_actions, optional_actions}` —
  **no quantities, no units, no required class outputs**. A text search for
  `required_outputs` returns zero hits tree-wide. The quantity/unit pairs of
  `measurement-model.md` §4 and the twelve profiles' output expectations are
  prose, not machine data. `ResolvedOtdpContracts`
  (`src/benchweave/registry/otdp_contracts.py`) consequently compiles only
  action input/output validators — there is nothing class-semantic to compile.
  Building M06/M13 therefore requires EITHER a corpus revision adding quantity
  data to the catalog (a standards bump) OR a host-side hand-carried table of
  corpus prose — the pattern obligation 17 tolerates only under duress, with
  both-side spelling tests, and calls known debt.
- **A manifest-internal subset does not need class data.** M08 (uncertainty/
  calibration coherence: known ⇒ nonnegative value present; applied ⇒ reference
  + method; unknown is not a zero value) and the internal halves of M05
  (valid ⇒ no nulls; partial ⇒ available-and-unavailable unless the reason says
  otherwise) and M09 (host timestamps only with `timestamp_source: host`;
  unknown trigger time is not zero) are checkable from the manifest alone, the
  way M04 is today. The #146 record's "class-semantic" label overstates this
  subset's dependence. This does NOT reopen the boundary — no caller wants
  these checks either, and shipping them unasked would be the forced-busy slice
  the triage doctrine forbids — but the reopen trigger should be understood as
  firing for these checks on "first dataset consumer that wants internal
  coherence verified," not only on profile wiring.

### 2.4 Verdict

**PARK-trigger-not-fired**, with a second, independent bar for the class-data
half: under this run's no-bump directive (and, structurally, behind #203's
dependency train for any catalog revision), M06/M13 are bump-gated even if a
caller appeared. What would fire it: admission (or a submitted-and-reviewed
publication, per the #223 dogfood shape) of an invoke-capable class plugin
whose conformance story requires the gateway — not just the author — to verify
quantity/class-output coherence; or, for the internal subset only, a dataset
consumer that needs M05/M08/M09 coherence as a gateway guarantee.

---

## 3. Row 5 — acquisition-scoped dataset identity

### 3.1 Has the trigger fired? No.

Recorded trigger: *"a profile whose fetch semantics need acquisition dedup."*

- The mint today is per-dispatch: `DatasetController.mint_dataset_id`
  (`src/benchweave/content/dataset_services.py:169-186`) mints
  `ds:{operation_id}` and keys `_operations`/`_admitted_by_dataset` on it. The
  #146 E2E (`tests/integration/test_issue146_e2e.py`) ran
  configure → fetch → sample — one publish per fetch operation, one acquisition
  per fetch. No caller re-fetches the same acquisition across operations.
- The corpus makes the current posture legal: `extension-contract.md:64` — the
  dataset_id is "derived from the current operation/acquisition" (disjunction),
  and "an idempotent repeated fetch **may** return the already published
  manifest" (permissive, not mandatory). Per-operation derivation is
  conformant; the #146 record's decision 2 already ruled it the first-increment
  choice.
- No profile at the gateway defines fetch semantics that dedup: the dc_psu
  `measure` action is direct-lifecycle in the demo fixture; no admitted plugin
  carries an acquisition-lifecycle fetch family. (The catalog's
  `lifecycle: acquisition` actions exist in the corpus, but nothing admitted
  exercises them through the gateway.)

### 3.2 Mechanism if built (grounded)

The pieces exist and are named correctly by the record ("the issued-id registry
is the mechanism home"):

- `$stg_issue` resolution happens at the executor BEFORE dispatch —
  `_resolve_issue` (`src/benchweave/control/executor.py:502-517`) mints
  `{field}-{run_id}-{step_id}{suffix}` and retains it in the occurrence
  ledger's `issued_ids` (CTL-5's mint-retain-invalidate mold). The bridge
  therefore receives the acquisition identity as an already-resolved plain
  string inside the invoke input.
- The publish path already special-cases those fields: `_check_m10_correlation`
  keys on `configuration_id`/`acquisition_id` when the action's pinned input
  schema declares them. A `ds:acq:{acquisition_id}` derivation would read the
  same place, and the idempotency machinery (`admitted_by_dataset_id` +
  byte-identical republish) already returns the admitted manifest without new
  rows.
- **The hole that makes parking correct rather than merely convenient:** under
  acquisition-scoped identity, a re-fetch that acquired MORE data produces a
  divergent manifest under a used id — and the admitted manifest is immutable,
  so it refuses. Dedup across operations is only meaningful once a profile
  defines what a divergent re-fetch MEANS (append? supersede? refuse-with-
  detail?). That semantic does not exist anywhere in the corpus or the tree;
  building the id scheme ahead of it would be inventing policy — the exact
  failure mode A02/A12 guard against.

### 3.3 Verdict

**PARK-trigger-not-fired.** No corpus motion, no guide motion needed to park.
What would fire it: an admitted (or dogfood-published) profile declaring an
acquisition-lifecycle fetch family whose procedure shape re-fetches the same
acquisition across steps — i.e., a real procedure that today would either
double-publish under two `ds:` ids or need the author to work around it. Guide
lines 130/292/392 (the `ds:{operation_id}` documentation) move in that build —
legal, docs-side.

---

## 4. Row 7 — demo-lattice class fixture

### 4.1 Current state (verified, not assumed)

The committed demo lattice is one half of a class fixture, and the missing half
is precisely the deferred row:

- The demo descriptor IS class-shaped: `fixtures/execution/descriptor-sim-psu.json`
  declares `capabilities [… "invoke"]`, `profiles: ["otdp.dc_psu/1.0.0"]`,
  channels with quantities, three `otdp.dc_psu.*` actions, and a `contracts`
  block pinning the corpus pair (`device-profile-catalog.json` +
  `otdp-measurement.schema.json` at 0.2.2 with sha256s).
- The sim adapter implements invoke (`plugin.py:142`).
- The signed-lattice builder does NOT ship the pinned contract bytes:
  `build_fixtures.py`'s implementation members are `_common_members() +
  _impl_extras() + _plugin_members(plugin_dir)` — and `_plugin_members` reads
  only `__init__.py`, `plugin.py`, `adapter.py`. No contract files are emitted.
- Consequence (the mechanism, not a guess): at activation, the pinned contract
  paths are absent from the verified inventory, so `resolve_otdp_contracts`
  takes the soft arm and returns `None` — no `DatasetController`, `invoke`
  refuses UNSUPPORTED at gate I1. The `otdp_contracts.py` module docstring
  states this verbatim: *"The committed demo lattice loads under exactly this
  arm: its descriptor pins the corpus pair, its historical payload predates
  contract shipping, and no demo run invokes."* The demo-lattice streaming test
  corroborates: its harness authors a write-kind policy because the committed
  lattice cannot drive invoke (`tests/integration/test_demo_lattice_streaming.py`,
  module docstring composition notes).
- The keyless half ALREADY landed with #146: `registry_common.ROLE_BY_SUFFIX`
  carries `"device-profile-catalog.json": "schema"` and
  `"otdp-measurement.schema.json": "schema"`, and `publish_dev._contract_members`
  ships them from plugin source at the pinned bundle-root paths — which is how
  the #146 E2E admitted a class-capable bundle through the real activation path
  without the signed lattice.

So the row-7 build is: copy the two corpus contract files into the sim_psu
plugin source, extend `build_fixtures.py` to emit them (mirroring
`_contract_members`), regenerate the lattice, and move the CON-2 lockstep
(catalogue + digest-pinning tests). The regeneration is the gated step.

### 4.2 The blocker — verified mechanically

- `build_fixtures._load_key` reads `fixtures/registry/keys/main.pem` /
  `originb.pem` (PRIVATE keys). The committed tree carries only
  `main.pub.pem` / `originb.pub.pem`.
- CI materialises the private keys from repo secrets
  (`BENCHWEAVE_FIXTURE_KEY_MAIN` / `BENCHWEAVE_FIXTURE_KEY_ORIGINB`) at
  `.github/workflows/ci.yml:22-37`; fork PRs receive empty secrets and simply
  lack them.
- The builder-parity tests are `@requires_signing_keys` — skipif, never fail,
  precisely because a contributor clone cannot sign
  (`tests/contract/test_registry_fixtures.py:22-29`).
- No workflow regenerates-and-commits the lattice. (A CI-commit precedent
  exists in-tree — `changelog.yml` regenerates the changelog with `[skip ci]`
  — but nothing similar exists for fixtures, and inventing one is a fork, not
  a default.)

The blocker holds on inspection: lattice regeneration is impossible on this
machine, exactly as the issue records. It is a machine-access blocker, not a
mechanism blocker — the design records three clearance options in §6.

### 4.3 Has the trigger fired? No.

- **No real class plugin admission.** DPS-150 is identify/read (§2.1); the
  device proposals (#92–#95) are unadmitted proposals; the external ADC plugin
  named in #203/#223 is a serial scalar board, not an invoke-class plugin.
- **No registry-demo need requiring it.** The registry arc's demo fixture is
  "a ≥10-row synthetic catalogue (CR-24's own denominator) with all dimensions
  represented" (`docs/implementation-planning/10-contributor-publishing-design.md:146`)
  — records-level rows for search dimensions, in the registry repo slice 1
  creates; its acceptance B1 needs no runnable class plugin payload in the
  gateway's signed lattice. The DPS-150 dogfood in #223 is a real submission of
  a non-class plugin.

### 4.4 Verdict

**PARK-trigger-not-fired, with the key-access blocker confirmed as the second
gate.** Not BLOCKED-in-principle: the mechanism is fully specified by in-tree
precedent (publish_dev's contract members + the builder's emit pattern), and
key access has three clearance paths (§6). What would fire it: (a) the first
real invoke-capable class plugin submission through the #223 publishing path —
whose replay/dogfood would want a committed class-capable lattice to test
against; or (b) any demo/website need that must RUN a class plugin (not merely
list one) from committed fixtures.

---

## 5. Sharpened fire conditions (the tripwires, testable)

| Row | Fires when (observable event) | Nearest plausible carrier |
|---|---|---|
| 1 (class-data half) | An invoke-capable class plugin's admission/publication whose conformance story requires gateway-side quantity/class-output verification — or a corpus train that adds quantity data to the catalog schema | #92/#94 proposals maturing; the #203 train touching the catalog |
| 1 (internal subset) | A dataset consumer that needs M05/M08/M09 manifest-internal coherence as a gateway guarantee rather than an author obligation | A UI/reporting surface over admitted manifests |
| 5 | A profile with acquisition-lifecycle fetch semantics whose procedures re-fetch one acquisition across steps | An oscilloscope-class plugin admission (#92) |
| 7 | A real class plugin submission through the publishing path, or a demo that must RUN a class plugin from committed fixtures | #223's dogfood closing step; a later website demo |

---

## 6. Maintainer forks (decide when a trigger fires, not now)

1. **Row 1 quantity substrate:** corpus revision (catalog schema gains quantity
   data — a bump, riding #203's train) vs host-side hand-carried table with
   both-side spelling tests (obligation-17 posture, disclosed debt). The design
   position: corpus revision is the honest path; the hand-carried table is what
   the closed schema exists to avoid.
2. **Row 5 divergent-refetch semantics:** append, supersede, or refuse-with-
   detail — a profile-shape decision that must be made by the profile that
   fires the trigger, not by this gateway unilaterally.
3. **Row 7 key clearance:** (a) principal-local regeneration (the secrets'
   originals exist wherever they were minted); (b) a CI workflow that runs the
   builder and uploads `fixtures/registry/` as a workflow artifact, which the
   contributor downloads and commits — lightest, no new push permissions, cold
   full-suite per obligation 5; (c) a changelog.yml-precedent commit-back
   workflow — heaviest, new push machinery. The design position: (b), when
   needed.

---

## 7. Pre-committed acceptance rules for the reopening slices

Written now, before any implementation number exists, in the #146 §7 style. They
bind whoever opens the first slice of each row; a reopening that cannot meet its
rule reports that honestly rather than weakening it.

- **Row 1 (either half):** every new M-check ships as a RED-revertible publish-
  path control in the `tests/unit/test_dataset_services.py` battery shape —
  a manifest that violates exactly the new check refuses with the check named
  (`M0x:` prefix, matching the implemented subset's message grammar), and
  reverting only the check's commit turns that control red while the
  implemented-subset controls stay green. A control that passes with the check
  reverted does not test it. For the class-data half, an additional load-level
  control pins that the quantity substrate is READ from the pinned catalog
  (mutate the catalog's quantity row → the check's verdict flips), so the
  hand-mirror drift class cannot arise silently.
- **Row 5:** two arms, both RED-revertible: (1) two invoke dispatches whose
  resolved inputs carry the SAME issued acquisition id publish under ONE
  dataset id — the second byte-identical publish returns the admitted manifest
  with zero new evidence rows and zero new staged bytes; (2) the corpus
  decision the trigger carries (append/supersede/refuse) is pinned in both
  directions — a divergent re-fetch does exactly what the profile text says,
  and no other outcome class appears. The `ds:{operation_id}` pin
  (`test_i6_invoke_mints_the_host_dataset_id_on_the_context`) moves in the same
  change, never after.
- **Row 7:** the committed lattice itself becomes the E2E substrate — a run
  through the real activation path over the COMMITTED catalogue (the
  `test_demo_lattice_streaming.py::_demo_session` shape, no dev publish, no
  test-local bundle) drives `configure → fetch → sample` on the psu and passes.
  RED arm: revert only the builder's contract-member emission, rebuild (in CI,
  where the keys materialise), and the run refuses UNSUPPORTED at I1 — the
  soft-arm pin. Builder parity stays byte-exact (`test_builder_is_deterministic`)
  and the catalogue/digest lockstep moves in the same commit (CON-2).

**Kill direction common to all three:** if a reopening slice cannot express its
control through the real mechanisms named above (the committed lattice, the
pinned catalog, the publish path), it reports the measurement as underpowered
and stops — no hand-built substitute counts.

---

## 8. Risks of parking (what could bite, each with its tripwire)

| Risk | Tripwire / mitigation |
|---|---|
| The author-side M-boundary is silently relied on by future dataset consumers who assume gateway verification | The guide's explicit sentence (guide:394, "the gateway does not verify them for you") is the contract; §5's internal-subset fire condition watches for the first consumer |
| `ds:{operation_id}` becomes load-bearing in external tooling, making the acquisition-scoped migration breaking later | Guide lines 130/292/392 already document the mint as host-internal ("never choose dataset ids"); the corpus never promised stability of the scheme to adapters — the manifest correlation channel is `context.dataset_id`, not the string's shape |
| The demo lattice's inability to invoke is rediscovered expensively by a future demo run | `otdp_contracts.py`'s module docstring states it verbatim; §4.1 here records the full chain with citations |
| Row 7's builder change lands WITHOUT regeneration (builder and lattice diverge) | `test_builder_is_deterministic` runs in CI where keys exist and would red on divergence; locally it skips — the §7 row-7 rule requires the lockstep in one commit |

## 9. Invariant and drift impacts

None. No code, corpus, fixture, or doc bytes move in this increment beyond this
record. No invariant gains an amendment; the two sharpenings in §2.3 and §4.1
live here as observations on the #146 record's premises, flagged for whoever
reopens those rows. CI cost: zero.

---

*Provenance: grounded against `main` @ `9ad0301` (2026-09-26); corpus
`standards/otdp/0.2.2`; the #146 record (all amendments) is the governing
precedent set. No client, bench, or person identifiers; fixture and plugin names
are the repository's own public in-tree names.*
