# Issue #220 — #203 Slice 6: The Execution Per-Document Pin — Design Record

**Status:** Design (builder-ready) · **Tracking issue:** madeinoz67/benchweave#220 (sub-issue of #203) ·
**Parent design:** `docs/implementation-planning/09-standards-dependency-design.md` §4 Slice 6, §3.3 (the
arc record — its acceptance rule F is pre-committed there and is elaborated here, never rewritten) ·
**Evidence baseline:** gateway `main` at `6582651` (in sync with origin; slice 5 = PR #256 `40b9b69`
landed). Branch will be `feat/issue220-execution-pin` off main (per the issue's in-progress note).

---

## 0. Premise verified — and one premise CORRECTED

The arc record's slice-6 text says the execution documents "declare their execution version (an additive
corpus change: an optional `execution_version` field on the bench document is a PATCH-class execution
bump … riding its own train)". Read against the corpus bytes, the first half is already true and the
second half is wrong in the slice's favor:

- **The pin carrier already exists.** `contract_version` is a **required property with a `const`** in
  every one of the five execution schemas, in BOTH served versions — 0.1.0 schemas const `"0.1.0"`,
  0.2.0 schemas const `"0.2.0"` (verified across
  `standards/execution/{0.1.0,0.2.0}/{bench,procedure,safety-policy,run-binding,commissioning}.schema.json`).
  This is exactly the OTDP `otdp_version` const shape the whole #203 arc is built on
  (`standards/otdp/0.2.2/otdp-device-descriptor.schema.json:5`, cited in the arc record §1). Both bench
  schemas are `additionalProperties: false` and neither has an `execution_version` property — a bench
  document carrying a literal `execution_version` key rejects under BOTH corpora today, which is why a
  new field would need a PATCH. `contract_version` needs nothing: it has been in every document since
  0.1.0.
- **Therefore this slice moves no corpus bytes and is NOT blocked on the PATCH train.** The separate
  PATCH train (optional `execution_version`) is not a prerequisite for F1/F2 in any part. Evidence
  further argues the PATCH would be actively harmful if landed as specced: it would create a SECOND
  version field beside the const-enforced `contract_version` in the same closed documents — two
  carriers for one fact, a standing drift hazard the schemas could not refuse (one of them optional).
  That is the other train's question, not this slice's; this record records the evidence (§7 Fork 2).
- **A real 0.1.0-era lattice exists and is recoverable.** The last commit whose fixture lattice carried
  `contract_version: "0.1.0"` is `4743bd4` (the #176 row-D demo-lattice commit; `54a59fa` promoted
  execution 0.2.0 and restamped). `git show 4743bd4:fixtures/execution/*` yields a COMPLETE,
  digest-coherent, really-admitted 0.1.0 lattice — all five execution documents, package-lock, and two
  descriptors whose pins classify cleanly TODAY (both pin `otdp_version: "0.2.2"`, adapter API `1.1` —
  served, conforming, and inside execution 0.2.0's cross-constraint row as well). F1's fixture is
  historical bytes, not a hand-built approximation.
- **The corpus's own 0.1.0 `examples/` are digest-coherent but not a runnable lattice**: binding →
  procedure/bench/policy and commissioning → bench/procedure_refs pins all match the actual example
  bytes (verified by sha256), but the example bench's device pins are placeholders (an all-zeros
  sha256 no descriptor bytes can match). They remain useful as the anti-tolerance arm's raw material
  (§5 F1c).

Everything else the arc record scopes for slice 6 checks out against current main: `admit_documents`'s
`contracts` parameter threads a corpus version directory (documents.py:1489, module default
`_CONTRACTS = contract_family("execution/0.2.0")` at documents.py:78); the per-pin descriptor lane
(#217) resolves each descriptor's pin before validation; `_check_cross_constraints` derives the bench's
execution version from the ambient directory name (`execution_version = contracts.name`,
documents.py:1243); execution is served at {0.1.0, 0.2.0} (policy block range `>=0.1.0,<0.3.0`, no
yanks, retired `["1.0.0"]` — `standards/standards-manifest.json`); the wheel ships the whole retained
tree minus `*/<target>-dev/` (the `hatch_build.py` per-unit contribution, `pyproject.toml:70-77`), so
`execution/0.1.0` (12 corpus-manifest rows) is packaged-first like every retained version.

## 1. The mechanism, file by file

### 1.1 `src/benchweave/control/documents.py` — pin routing at admission

**The routing read.** `admit_documents` gains a pre-schema exact-byte read of the bench document —
the `_project_full_form` pre-schema pattern (documents.py:1285-1321, where the descriptor's
`otdp_version` is resolved BEFORE schema validation) applied to the lattice: decode `bench_path`
through `_decode(bench_path, "bench")` (no schema — the exact-byte gates still apply), read
`contract_version`, classify, route. The five existing `_decode(..., contracts)` calls
(documents.py:1529-1541) then validate against the ROUTED directory instead of the threaded one.
The bench document is decoded twice (routing read + validating read); the double read is safe because
the pin's own const re-asserts itself in the validated bytes — if the file changed between the two
reads, the routed schema's `contract_version` const refuses the swapped content. A builder may
restructure to a single read (decode once, validate the decoded content) provided the refusal
prefixes and their order for existing multi-fault fixtures are unchanged; the double read is the
minimal-diff shape.

**The classification core, generalized by standard.** The served-set machinery is already
standard-parameterized — `load_dependency_policy_from_corpus(corpus)` (policy for all standards),
`policy.standards.get(<id>)`, `retained_versions_from_corpus(corpus, standard)`,
`served_versions_from_corpus(policy, corpus, standard)`, `declared_dev_head(corpus, standard)`
(documents.py:60-73 imports; call sites :231, :306, :333, :352). What hardcodes OTDP is the
classification core and its message: `_classify_cached(pin, corpus_text, policy_digest, retained_digest)`
(documents.py:283-365) reads `policy.standards.get(_OTDP)`, and `_vr37_text` (documents.py:220-240)
prints `standard: {_OTDP}` inline. The change: thread a `standard: str` parameter through both
(`_classify_cached`'s lru_cache key gains it — corpus-state tokens are standard-independent, so
without the key an otdp and an execution classification of the same pin string would collide),
generalize `_vr37_text(row, pin, corpus, policy, standard)`. `classify_descriptor_pin`'s public
signature is UNTOUCHED (it passes `standard=_OTDP` internally — its consumer
`Operations._device_projection` and the API view do not move). A new module-internal
`_classify_execution_pin(pin, *, corpus=None) -> DescriptorPin-shaped record` wraps the core with
`standard="execution"`; total over pin values exactly as the descriptor classifier is (malformed →
`unclassifiable`; a dev-shaped label classifies against `declared_dev_head(corpus, "execution")`,
which is None today and refuses as never-carried — total, no crash).

**Routing decisions, per class (the Q6 table applied to the lattice):**

| `contract_version` class | Behavior |
|---|---|
| served or yanked (dev/rc if a head is ever declared) | validate all five documents against `contracts.parent / <pin>`, each schema file digest-verified against its corpus-manifest row at load (the `_validator` cache key `(dir, filename)` already keeps versions apart, documents.py:164-177) |
| retained ∧ out-of-range (`nonconforming`) | REFUSE `standard_nonconforming:` + the five VR-37 fields — **no ack path**; the #217 landing note is the ruling: "an ack authorises the otdp-window load, never the execution runtime interface" (invariants.md CON-1 amendment 2026-09-27) |
| retired (`1.0.0`) | REFUSE `retired_identifier:` (distinct from unknown; the re-target hint wording) + VR-37 |
| never carried (`0.3.0`, `0.2.5`, an undeclared dev label) | REFUSE `version_unknown:` + VR-37 |
| unclassifiable (not `MAJOR.MINOR.PATCH`, absent) | validate against the threaded `contracts` (the ACTIVE/composition posture) so the schema's own const error names it — the OTDP no-pin posture, mirrored (documents.py:1318-1321) |

The refusal vocabulary is #217's, emitted verbatim for a new document class: `retired_identifier:`,
`version_unknown:`, `standard_nonconforming:` with the five VR-37 fields inline
(`standard: execution; pinned: X; supported: >=0.1.0,<0.3.0; move-to: 0.2.0; migration: …`). The
gateway still never emits `version_not_served:` (the SDK lane's fold — documents.py module docstring
:25-36). Mixed-version lattices need no new vocabulary: routing selects one version's schemas and
their consts enforce agreement — a procedure declaring 0.2.0 inside a 0.1.0-routed lattice refuses
`schema: procedure $.contract_version` with the const error naming the disagreement.

**`_check_cross_constraints` threads the pin.** Signature `(contracts: Path, pins)` →
`(execution_version: str, pins)`; the caller passes the ROUTED version label. Today's
`execution_version = contracts.name` (documents.py:1243) is the ambient-directory fact; under the pin
it is the bench's own declared fact. The row lookup is version-keyed and the honest negative stands:
`standards/cross-constraints.json` carries exactly one row (execution 0.2.0 → otdp `>=0.2.0,<0.3.0` +
adapter_api `1.1`, evidence PR #201); a 0.1.0-pinned bench matches no row and constrains nothing it
has no evidence for — the file's own note says the absence is deliberate. `_check_cross_constraints`
already reads rows via `load_cross_constraints_from_corpus(_otdp_corpus())` (the corpus root), so
only the version argument moves.

**`AdmittedDocuments.execution_version: str`.** One new frozen-dataclass field (the routed version
label), consumed by the run guard (§1.2) and the tests. `AdmittedDocuments` is constructed at exactly
one site (documents.py:1707) and never serialized; the addition is contained.

**Digest verification of the routed schemas.** `_validator` reads `contracts / schema_filename`
blindly (the composition seam was trusted). Under routing, resolution goes through a
`_versioned_schema_path(corpus_root, family, version, document_name)` generalization of
`_otdp_versioned_schema_path` (documents.py:505-531) — file-exists check, `corpus_file_unpinned:`
refusal for an unrowed file, `corpus_pin_mismatch:` refusal for a digest disagreement — so a pin's
schema is served from digest-frozen retained bytes exactly as CON-1's amendment requires. The OTDP
helper delegates to the generalized one (one mechanism, two families) or stays as-is with a parallel
execution twin the builder picks by diff weight; either way the refusal prefixes are the existing
corpus vocabulary.

**The composition seam keeps its shape.** `create_app(execution_corpus=ACTIVE|DEV_HEAD)` resolves
`contracts` ONCE (app.py:906-909: `declared_dev_family("execution")` or `_CONTRACTS`) and threads it
through startup, recovery, and run admission. Under routing, the threaded directory is the
composition BASE — `contracts.parent` is `standards/execution/` (or `_vendored/contracts/execution/`
in a wheel) for both ACTIVE and DEV_HEAD resolutions, and the pin selects within the family. A
released pin routes to its own released bytes even under a dev composition — VR-13 applied honestly
(the pin's bytes, not the composition's); a lattice written for the dev head carries the dev const
and routes to the head's directory. No `create_app` change.

### 1.2 `src/benchweave/interfaces/app.py` — the run guard (degrade loudly)

The one reachable dishonesty the mechanism opens: `build_terminal_record` hardcodes
`"contract_version": "0.2.0"` (coordinator.py:171) and validates against `contracts`
(coordinator.py:158) — a terminal record for a 0.1.0-lattice run would carry
`binding.version "0.1.0"` beside `contract_version "0.2.0"`, an internally contradictory evidence
record (A06's laundering class). Runs on a pinned-old lattice are reachable: startup admits the
lattice (that IS F1), and the run path re-admits per run (app.py:698-702). The minimal honest close:
**a guard, not the record lane** — immediately after the run-path `admit_documents` call
(app.py:698-702), refuse when `docs.execution_version != contracts.name`:

```
execution_version_not_runnable: this gateway runs execution@<contracts.name>; the
lattice pins execution@<pin> — validation and inventory load (the procedure-author
story); running needs the record lane (follow-on); move-to: <contracts.name>
```

A new stable prefix, additive per VR-38. The guard fires BEFORE device plans and bridges are built
(app.py:705+). Recovery cannot bypass it: no 0.1.0-lattice run can exist in any store (pre-slice,
such a lattice refused at startup — F1's RED; post-slice, starts are guarded), so recovery
terminalization never touches a pinned-old run. Startup deliberately does NOT guard — F1's surface
is the gateway holding and validating the old lattice; the refusal lands at the run request, loudly,
with the move-to.

### 1.3 Tests and fixtures

- `tests/fixtures/lattice-execution-0.1.0/` (new, test tree): the eight files recovered from
  `4743bd4:fixtures/execution/` byte-frozen (five execution documents at `contract_version "0.1.0"`,
  package-lock, two descriptors pinning otdp 0.2.2). Provenance note in the test module docstring.
- `tests/control/test_execution_pin.py` (new): the F1/F2 arms of §5, including the recovered-lattice
  admission, the anti-tolerance teeth, the cross-constraint threading discriminator, the guard, and
  the no-regression control over `fixtures/execution/` (the 0.2.0 sim lattice, byte-unchanged).
- Existing suites are the no-regression net: `tests/control/` (documents), `tests/unit/`
  (bootstrap admission, operator acknowledgements, seam control), `tests/faults/` (control/ change →
  faults lane per the CI map), `tests/integration/test_procedures.py` (the run path).

### 1.4 `docs/internal/invariants.md` — CON-1 amendment (append)

See §4. One appended amendment lands with the slice PR (doctrine and mechanism together, the #169
pattern).

## 2. Precedents — each verified in current main

| Mechanism reused | Precedent, cited |
|---|---|
| Pre-schema pin resolution (read the pin from raw decoded bytes, classify, then validate against the pin's own bytes) | `_project_full_form` documents.py:1285-1321 (#217, design §3.3) |
| Per-version, digest-verified corpus path resolution with `version_unknown`/`corpus_file_unpinned`/`corpus_pin_mismatch` refusals | `_otdp_versioned_schema_path` documents.py:505-531; `_descriptor_validator(version)` documents.py:459-478 |
| The Q6 classification over a policy row, with the VR-37 message and the lru_cache bound to corpus-state tokens | `_classify_cached` documents.py:283-365; `_vr37_text` documents.py:220-240; `_corpus_state_token` documents.py:243-280 |
| Version-keyed validator cache (ACTIVE and per-pin never share) | `_validator` documents.py:164-177; `_DESCRIPTOR_CACHE` documents.py:180 |
| Standard-parameterized served-set readers | `benchweave.standards.manifest` `load_dependency_policy_from_corpus` / `retained_versions_from_corpus` / `served_versions_from_corpus` / `declared_dev_head` (documents.py imports :64-73) |
| Honest-negative cross-constraint row absence | `standards/cross-constraints.json` note + `tests/standards/test_cross_constraints.py::test_the_retrofit_row_is_exactly_the_evidenced_set` |
| Compose-once, thread-everywhere `contracts` seam | `create_app` app.py:875-921; `bootstrap.admit_fixture_lattice` bootstrap.py:63-144 (the one body startup and recovery share — routing lands inside `admit_documents`, so both inherit it with zero caller changes) |
| Test-built lattices in a target dialect (fixtures with computed pins, flipped-pin arms) | arc record A2/C1 practice; `tests/standards/test_cross_constraints.py::_copy_standards`/`_rewrite` for policy-fixture mutation |
| Historical-byte fixture recovery | the #218 founding promotion record recovered from history (promotion-records.json's coordinator-authorized founding entry) — git-history bytes as evidence, same discipline |

## 3. Minimal first-increment scope and deferrals

**In scope (the increment):** the routing read + classification generalization + routed digest-verified
validation inside `admit_documents`; `_check_cross_constraints` threading the pin;
`AdmittedDocuments.execution_version`; the run guard in app.py; the recovered 0.1.0 test lattice;
the F1/F2 test module; the CON-1 amendment. No standards bytes, no SDK bytes, no interface/wire
bytes, no CLI.

**Deferrals** (each with a home and a reopen trigger, per `.claude/deep-review/README.md`):

| # | Deferred | Home | Reopen trigger |
|---|---|---|---|
| E1 | Terminal-record construction and validation against the pinned version's own run-record schema (`build_terminal_record`'s literal coordinator.py:171 and its `contracts` validation; recovery terminalization) — unblocks RUNS on non-active-pinned lattices and lifts the §1.2 guard | Follow-on issue (the slice PR opens it) | The `execution_version_not_runnable:` guard firing in real operator use, or the owner's explicit call to allow running non-active-pinned lattices (the ask naming the lattice version) |
| E2 | An ack-shaped load for a retained-but-out-of-range EXECUTION pin (refused outright this slice, consistent with #217's "never the execution runtime interface") | Documentation here + the slice PR body | The first retained execution version that sits outside the declared range (a state change visible in `standards-manifest.json`'s execution row vs the retained tree) |
| E3 | Public surface for the execution pin's classification (an API-view derivation or run-event recording of the lattice's execution class, VR-46-style) and a full pin record on `AdmittedDocuments` beyond the version string | Documentation here | The first consumer surface requesting the lattice's execution class (E1's record lane, or an interface bump opening the wire object) |
| E4 | Deriving the module-default `_CONTRACTS` literal from the manifest active entry (documents.py:78) — already the arc's slice-7 lane (§3.7); this slice neither adds nor removes literals (counter at 12, baseline 12, `scripts/standards/count_version_literals.py`) | The #203 slice-7 sub-issue | Slice 7 |

## 4. Invariant, governance, and drift impacts

- **CON-1 — the arc record's claim is WRONG and the slice appends one amendment.** The record (§4
  Slice 6) says "CON-1's amendment text already covers per-document selection; no new amendment."
  Verified against `docs/internal/invariants.md:163-241`: the 2026-09-26 (#215) and 2026-09-27 (#217)
  amendments are descriptor-specific — "the **descriptor's** own `otdp_version` pin selects the
  vendored schema" — and name `_descriptor_validator(version)`, `classify_descriptor_pin`,
  `AdmittedDocuments.pins`. The five execution-contract documents selecting by `contract_version` is
  a different admission-input class; no existing text covers it. The appended amendment (one
  paragraph, evidence line `issue #220, 2026-09-28`): under per-document execution pinning, the bench
  document's own `contract_version` selects the vendored execution corpus version all five documents
  validate against — the pin's digest-verified bytes, never the ambient composition's; the Q6 classes
  and prefixes apply (`version_unknown:` / `retired_identifier:` / `standard_nonconforming:` with the
  five VR-37 fields; a non-conforming execution pin refuses outright — the acknowledgement authorises
  otdp-window loads, never the execution runtime interface); the pairwise cross-constraint check
  reads the bench's pinned version, not the composition directory's name; exact-byte decode, digest
  pins, and every existing prefix unchanged.
- **CON-2 (fixture lattice lockstep):** untouched — `fixtures/execution/` does not move; the new
  0.1.0 lattice lives in the TEST tree (CON-2's lockstep is the registry fixture lattice's, not
  admission tests').
- **CON-4/CON-8/CON-10/CON-12/CON-14:** untouched — no served-set, manifest, projection, matrix, or
  resolver change. CON-10's descriptor projection does not see the execution pin.
- **GOVERNANCE:** no G-item; the policy block, yanks, retirements, and promotion records are
  consumed, not changed.
- **Standards bytes: none move.** `git diff origin/main...HEAD -- standards/` is empty on the slice
  branch (the #203-related exemption is not even needed). The PATCH train is decoupled — see §7
  Fork 2 for the evidence-based recommendation to reconsider it.
- **Surfaces that move:** `control/documents.py` (Tier 3 by rubric), `interfaces/app.py` (one guard),
  the test tree, `docs/internal/invariants.md` (append). MCP tools / REST / openapi / CLI: no motion
  (the new refusal prefixes ride inside `AdmissionRejected` messages, exactly as #217's did — no wire
  enumeration). Operator docs: the refusal vocabulary is documented where #217's is (the module
  docstring + the CON-1 amendment). SDK repo: no motion — the SDK validates descriptors, not
  execution documents (verified: one incidental comment mention at the pin, nothing functional).
- **CI cost:** negligible — one new focused test module (seconds), no new lanes. The ratchet is
  untouched (12 = baseline 12; the coordinator literal stays, made safe by the guard, removed by E1).

**Tier call (Step-1 rules, run on the planned diff):** **Tier 3** — primary rule: "touches
`src/benchweave/control/documents.py` (the run/document schema)". Keyword scan over the expected diff
text: `sha256` PRESENT (digest verification and pin fields in the routing/refusal code); `hashlib`,
`threading`, `asyncio`, `subprocess`, `migrate`, `recovery`, `protection` absent from the new code
(the word "recovery" appears in reasoning/comments only). Second independent adversary lane required
(Tier 3), per the standing two-lane rule. Standards-governor: the diff touches no `standards/` bytes,
no locks, no SDK tree, no version-string literals — the mandate's letter does not fire; given the
diff's SUBJECT is standard-version selection, dispatching the governor anyway is recommended as the
conservative reading (recorded either way in the PR body).

## 5. Measurable proof — acceptance rule F (pre-committed in the arc record) elaborated

The arc record's F1/F2 are quoted verbatim and elaborated with named arms; nothing is rewritten.

> **F1** — "a lattice written for execution 0.1.0 validates UNEDITED while the gateway's active
> execution version is 0.2.0 (RED: today the module literal forces 0.2.0). KILL: any in-tree lattice
> needing edits."
> **F2** — "a lattice declaring an unserved execution version refuses with the VR-37 fields."
> KILL: any in-tree lattice needing edits. CI cost: negligible.

- **F1a (the recovered lattice, RED→GREEN).** Fixture: `tests/fixtures/lattice-execution-0.1.0/`
  (bytes from `4743bd4`). RED, run at the merge base BEFORE the mechanism:
  `admit_documents` over the lattice refuses `schema: bench $.contract_version: '0.1.0' was expected
  '0.2.0'` (the active const — the module literal forcing 0.2.0). GREEN post-mechanism: the lattice
  admits with zero byte edits; `AdmittedDocuments.execution_version == "0.1.0"`; both descriptors
  classify served (otdp 0.2.2). "Unedited" is exact here: historical bytes, digest-frozen, including
  the placeholder-free descriptor pins.
- **F1b (the cross-constraint threading discriminator — design Q4's proof).** A 0.1.0-pinned bench
  with an ACKNOWLEDGED otdp-0.1.2 descriptor (retained, out-of-range → loads behind the recorded
  per-device acknowledgement, the #219 carrier) ADMITS — no 0.1.0 cross-constraint row exists (the
  honest negative). The same acknowledged descriptor on the 0.2.0 sim lattice REFUSES
  `cross_constraint_violation:` (0.1.2 outside `>=0.2.0,<0.3.0`). The first cell is the discriminator:
  under the old ambient-version behavior it would refuse (the 0.2.0 row applied to a 0.1.0 bench) —
  its RED at the merge base is implied by F1a's (the 0.1.0 lattice does not admit at all), and its
  discriminating power is against a routing bug that threads `contracts.name` instead of the pin.
- **F1c (anti-tolerance teeth — routing serves the PIN's bytes, not a tolerant schema).** A procedure
  built from the 0.2.0 corpus's own structural additions — the new closed `oneOf` member with
  required `timeout_ms` (`procedure.schema.json` 0.2.0 adds it; 0.1.0 lacks the branch) — with
  `contract_version` stamped `"0.1.0"` REFUSES under the 0.1.0 pin (oneOf/additionalProperties
  failure from the 0.1.0 bytes). Converse arm: the F1a procedure re-stamped `"0.2.0"` (the const
  field only) validates under 0.2.0 — the 0.1.0 dialect is structurally inside 0.2.0 (verified by
  schema diff: 0.2.0 only ADDS `maximum: 86400000` bounds and new closed branches; nothing removed or
  renamed). Both cells together prove selection-by-pin in both directions. The 0.1.0 corpus examples
  (digest-coherent, placeholder device pins) supply raw 0.1.0-dialect bodies for these arms where
  convenient.
- **F1d (no-regression / the KILL arm).** The in-tree 0.2.0 sim lattice (`fixtures/execution/`)
  admits byte-unchanged; the full existing admission surface (bootstrap admission, operator-ack,
  seam-control, faults, procedures integration) is green. KILL fires if ANY in-tree lattice needs an
  edit to admit.
- **F2a (never carried).** `contract_version: "0.3.0"` → `version_unknown:` naming execution, the
  pinned version, `supported: >=0.1.0,<0.3.0`, `move-to: 0.2.0`, the migration placeholder — all five
  VR-37 fields asserted by test.
- **F2b (retired).** `contract_version: "1.0.0"` → `retired_identifier:` (distinct prefix, "used and
  dead" wording, the next-minor re-target hint) + the five fields.
- **F2c (non-conforming, no current instance — exercised via policy fixture).** A copied-standards
  fixture with the execution range narrowed below 0.1.0 (the `_copy_standards`/`_rewrite` pattern,
  `tests/standards/test_cross_constraints.py`) makes 0.1.0 retained-out-of-range: the lattice REFUSES
  `standard_nonconforming:` + VR-37, and no acknowledgement input changes that (E2's posture pinned).
- **F2d (malformed).** `"0.1"` / absent `contract_version` → the composition schema's own const error
  (`schema:` … was expected '0.2.0') — the no-pin posture, mirrored from OTDP.
- **F3 (guard, elaboration — RED within the slice).** After routing lands and BEFORE the guard, a run
  start over the F1a lattice BUILDS (the run path admits it) — that is the guard test's RED. With the
  guard: the run request refuses `execution_version_not_runnable:` naming both versions and the
  move-to, before any device plan or bridge is constructed. KILL: a 0.1.0-lattice run producing a
  terminal record (contradictory evidence — A06).
- **F4 (ratchet, standing).** `scripts/standards/count_version_literals.py` reports 12 = baseline 12
  at the slice head; a planted literal fails CI (the arc's A4 discipline, unchanged).

Underpowered-measurement rule (pre-committed): F1a/F1b/F1c are each single-cell deterministic tests —
if any RED cell cannot be reproduced at the merge base (F1a's const refusal, F3's unguarded build),
the fixture is wrong, not the mechanism; stop and re-baseline the fixture before building. No
statistical arms exist in this slice; nothing here depends on sample size.

## 6. Top risks — and what an adversary attacks first

1. **Constraint escape via the old pin (the strongest attack).** Pin the bench to 0.1.0 and the 0.2.0
   cross-constraint row (the otdp `>=0.2.0` floor) does not apply — devices below the floor ride the
   bench. TODAY the guard makes the escape moot for execution (the run refuses). The attack reopens
   with E1: if runs on pinned-old lattices are enabled without a floor, a 0.2.0-dialect device runs
   under a bench that never asserted an otdp floor. MITIGATION now: the guard + this risk named as
   E1's DESIGN CONSTRAINT (the record lane must not lift the guard without deciding the floor —
   e.g. the gateway's implemented-dialect minimum as a run-side constraint independent of the pin).
   FALSIFIER: F1b's refusing cell passing with a 0.1.0 bench and an unacked below-floor device…
   note: an unacked below-floor device refuses at the ACK gate (otdp-window), so the escape needs an
   acknowledged device — the ack is the operator's recorded decision; the cross-constraint row is the
   bench's. The design keeps both, per-version.
2. **TOCTOU on the double bench read.** The routing read and the validating read are two reads of one
   path; a concurrent swap between them routes on bytes A and validates bytes B. SELF-DEFENDING: B's
   `contract_version` const must equal the routed version or the routed schema refuses it — the pin
   lives in the validated bytes. FALSIFIER: a test that swaps the bench between reads and gets an
   admission whose routed version differs from the admitted document's const (should be impossible;
   the test proves it).
3. **The examples temptation / fixture laundering.** A builder "greens" F1 by editing the recovered
   bytes (stamping consts) or by validating the examples' placeholder pins away. MITIGATION: the
   fixture is byte-frozen with a provenance note; F1c's teeth arm fails under any tolerant-schema
   implementation; the KILL arm (F1d) catches in-tree edits. FALSIFIER: F1c's stamped-"0.1.0"
   0.2.0-structure procedure validating under the 0.1.0 pin.
4. **Classification-cache collision.** Generalizing `_classify_cached` without adding `standard` to
   the lru_cache key makes an otdp and an execution classification of the same pin string share an
   entry (the corpus-state tokens are standard-independent). MITIGATION: the key gains the standard;
   a test classifying pin "1.0.0" under BOTH standards in one process asserts the distinct rows
   (otdp 1.0.0 is NOT retired — unknown; execution 1.0.0 IS retired). FALSIFIER: that test sharing a
   row.
5. **Composition-seam surprise.** A dev-head composition (when a head is next declared) no longer
   overrides a released pin — a released-pinned lattice validates against its own released bytes even
   under `execution_corpus=DEV_HEAD`. This is VR-13 applied honestly, but a devstage workflow that
   expected the composition to capture old lattices will see behavior change. MITIGATION: this record
   states it; the devstage roll-up policy's gateway surfaces land with the roll-up, which can add a
   composition-pins-override opt-in if the devstage needs it (a fork, not a secret).
   FALSIFIER: none needed today (no declared execution head exists); reopen with the next head
   declaration.
6. **The guard's surface gap.** The guard lives at the run path; any FUTURE admission caller that
   executes physical work must add the same check or laundering moves there. MITIGATION: the prefix
   is grep-able and the CON-1 amendment names the rule ("running is a composition-version fact");
   E1 consolidates. FALSIFIER: a new executor-side admission caller appearing without the guard
   (review catches by the amendment's mention).

## 7. Forks for the maintainer

- **Fork 1 — runs on non-active-pinned lattices (the genuine product fork).** Recommended (designed
  above): the guard — validation and inventory load for old lattices now, runs refuse loudly, E1
  threads the record lane later with the constraint-floor decision attached. Alternative: thread the
  record lane IN this slice (runs work end-to-end; the diff grows into coordinator/recovery record
  semantics and must answer Risk 1's floor question now). The PRD's procedure-author story is
  validation-only ("keep validating", PRD §2 line 77), which the guard satisfies fully.
- **Fork 2 — the PATCH train.** Evidence in §0: the optional `execution_version` field is redundant
  with the const-enforced `contract_version` and would be a two-carrier drift hazard in closed
  documents. Recommendation: reconsider that train's premise before it spends a 24h window (this
  slice proves the story lands with zero corpus motion). Not this slice's call; flagged with the
  evidence.

## 8. DISCLOSED UNVERIFIED

- **The double-read restructure.** Whether the builder keeps the two bench reads (minimal diff) or
  restructures `_decode` to validate already-decoded content — either is conformant; the
  refusal-order pin (existing multi-fault fixtures) is verified only by the focused suite at build
  time, not by this design.
- **CI checkout depth.** The recovered lattice is COMMITTED under `tests/fixtures/` (no
  `git show` at test time), so CI history depth is irrelevant — but the recovery step itself
  (extracting `4743bd4` bytes) was done in THIS checkout; the builder re-verifies the committed
  fixture's digests against the corpus-manifest rows for the execution documents (the descriptors and
  package-lock have no corpus rows — they are operator documents — so the check is over the five
  execution documents only).
- **Wheel-install behavior** is inherited from the #217 OTDP lane's proof (whole retained tree ships
  minus dev dirs; classification reads the packaged manifest before any path resolution). No new
  wheel-install test is added by this slice; if the review panel wants one, it belongs with E1 (the
  first slice that RUNS a pinned lattice end to end).

---

*Design record for issue #220 (#203 slice 6 of 7). No standards bytes move. The arc record's slice-6
premise (a new optional field on its own PATCH train) is corrected by corpus evidence in §0; the
pre-committed acceptance rule F is elaborated, not rewritten. Deferral table §3 follows the
`.claude/deep-review/README.md` contract.*
