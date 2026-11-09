# Design record — gateway issue #604 (GW-1): the host admits the dataset-shaped invoke result

Date: 2026-11-09. Carrier: gateway issue #604 (OPEN, verified this session), the
gateway half of SDK issue #589 row D10. This record is the slice's first commit.

Triage: PUBLIC. Mechanisms, invariants and measurements only. The plugin the ruling
was measured against is "a real plugin project"; its vendor, package name and
repository URL appear nowhere here. Fixture names in the arms are invented
(`demo.*`, the existing synthetic invoke fixtures).

Tooling note: the Gortex MCP server was unavailable for this session (checkout
discovery failed; no graph access granted). All reads were `Read`/`grep`/`sed` via
native tools, per the dispatching brief. No daemon started, no tracking changed.

Working-tree note (load-bearing): the primary checkout was 230 files behind
`origin/main` (local `084c5e6c`, origin `b08ee075`) and its `standards/otdp` tree
stopped at 0.2.3. Every line number below was verified in a fresh worktree at
`origin/main` (`b08ee075`), under the repo's `.wt/` scratch root. Paths cited
without a prefix refer to that head.

---

## 0. The ruling, in its own words

The principal ruled on issue #589, comment `2026-11-06T12:24:22Z` — read directly
from the SDK records that quote it verbatim
(`.claude/deep-review/2026-11-06-589-live-bringup-design.md` §4 and
`.claude/deep-review/2026-11-06-589-pr3-dataset-admission-design.md` §0, both read
from the SDK repository's `origin/main` at `56e832cb`; the local submodule mount
is detached at an older release and does not contain them):

> "Ruling: the host admits. The adapter does not publish."

The ruled reasoning, adopted as written (not paraphrased loose): **storage policy
is host policy** (a publish hop inside the adapter is a second authority that
drifts); **the gateway's dispatch-time requirement is a trap** (it fires only at
dispatch, after the gateway accepted a descriptor whose behavior promised
host-admission); **the dataset is already typed by the measurement schema** (a
second explicit publish is ceremony that can disagree with the payload it
accompanies). The plugin side does not change; host-admission is "the standard's
rule, not one plugin's preference".

The SDK's standalone host already implements the ruled path
(`benchweave_sdk_server/dataset_admission.py` `DatasetAdmission.admit`, and the
seam's result-gate call at `seam.py` — read at SDK `56e832cb`): the dataset-shaped
branch of the invoke result gates calls `admit(payload, dataset_id=…, action_id=…,
invoke_input=…)`, a validation refusal is a typed `invalid_request`, an admission
success publishes a `dataset_admitted` event, and "the invoke result itself is
unchanged: admission is a host side-effect, not a result mutation."

GW-1 is the gateway mirror of that mechanism. The SDK record's D10 disclosure
("the gateway still requires `dataset_publish` until GW-1") retires when this
merges.

## 1. Root cause, verified

The defect: `src/benchweave/host/otdp_bridge.py:1462-1479` at `b08ee075`, the
invoke branch of `_convert`. After the action's catalog output schema validates
(1455-1461), the bridge requires that a dataset-shaped result byte-equal a
manifest THIS operation published through the dataset services during `execute`:

```python
if self._dataset.is_dataset_shaped(payload):
    admitted = self._dataset.admitted_for(request.operation_id)
    if admitted is None or canonical_json(admitted) != canonical_json(payload):
        ...
        raise InvalidInvokeResult(
            "invoke returned a dataset-shaped result that was never "
            "admitted through dataset_publish"
        )
```

`admitted_for` (`content/dataset_services.py:284-291`) returns the manifest only
if the adapter called `dataset_publish` mid-dispatch
(`dataset_services.py:461-564`, `record_admitted` at 293-319). Under the ruling,
an adapter that does the standard thing — returns the dataset-shaped result and
publishes nothing — is refused with `PROTOCOL_ERROR` and its session is poisoned.
The trap fires exactly as the ruling describes: after descriptor acceptance, at
dispatch, for correct behavior.

Pinned today by `tests/unit/test_otdp_bridge.py`:
`test_r2_dataset_shaped_result_without_publication_poisons` (3405 — pins the trap;
asserts `"dataset_publish" in result.error.message`) and
`test_r2_published_dataset_result_passes_the_cross_check` (3715 — the publish-then-
return pair and the post-publish-mutation poison arm).

Verification method: direct code reads at `origin/main` (`b08ee075`) — the bridge
branch, the controller, the publish member, the loader seam (`registry/otdp_loading.py:255-269`),
the app factory (`interfaces/app.py:943-965`), the discriminator
(`otdp_bridge.py:1249-1271`), and the tests. A live suite probe in the scratch
worktree was attempted and abandoned: the shared venv's editable install resolves
`benchweave` to the stale primary checkout rather than the worktree, so the
synthetic contracts resolved the worktree's 0.2.4 corpus under the stale code and
refused with `ActivationRejected` — an environment artifact, disclosed here so the
builder knows the RED demonstration below has not been pre-run and belongs to the
build.

Issue state, checked this session: gateway #604 OPEN (the acceptance rows below
re-read it); gateway #589 OPEN; SDK PR #256 (the record-citation correction) is
OPEN and states it does not change this premise; no open gateway PR touches these
paths (pre-flight per #181 R2: `gh pr list` both repos, only SDK #256).

**There is no gateway-readable host-admission declaration — evidence, as run**
(the refute pass attacks this; every command and its verbatim output is recorded
here; the sweep runs in the scratch worktree at `origin/main`, the SDK commands
in the SDK clone):

Gateway at `b08ee075` — the four-token sweep over `src`, `standards`, `docs`:

```
$ git rev-parse HEAD
b08ee075391a5dacb2735761eaa079b337b49262
$ grep -rn -E "host_admission|hostAdmission|admits_on_result|admitsOnResult" src standards docs | wc -l
       0
```

Gateway at `b08ee075` — the descriptor schema is closed and carries no such key
(a plugin cannot smuggle the declaration in as an extension field):

```
$ python3 -c "
import json
s = json.load(open('standards/otdp/0.2.4/otdp-device-descriptor.schema.json'))
print('top additionalProperties:', s.get('additionalProperties', 'absent'))
print('datasets/admission key present:', any(k in s.get('properties', {}) for k in ('datasets','admission','dataset_admission')))"
top additionalProperties: False
datasets/admission key present: False
```

SDK at `56e832c` — the SDK package ships no `adapter.py`; every match is the
scaffold template or a test fixture, none under the shippable `src/benchweave_sdk`
package:

```
$ git ls-tree -r --name-only 56e832c | grep -i "adapter"
template/.claude/skills/benchweave-adapter-testing/SKILL.md.jinja
template/src/{{ package_name }}/adapter.py.jinja
tests/fixtures/binary_frames_plugin/src/binary_frames_demo/adapter.py
tests/fixtures/classref/readings_adapter.py
tests/fixtures/ftdi_control_plugin/src/ftdi_control_demo/adapter.py
tests/fixtures/replay_hid_plugin/src/replay_hid_demo/adapter.py
tests/fixtures/scaffold_expected/base/.claude/skills/benchweave-adapter-testing/SKILL.md
tests/fixtures/scaffold_expected/base/src/example_plugin/adapter.py
tests/fixtures/scaffold_expected/provider/.claude/skills/benchweave-adapter-testing/SKILL.md
tests/fixtures/scaffold_expected/provider/src/example_plugin/adapter.py
tests/fixtures/scaffold_expected/ui/.claude/skills/benchweave-adapter-testing/SKILL.md
tests/fixtures/scaffold_expected/ui/src/example_plugin/adapter.py
tests/fixtures/setpoint_plugin/src/setpoint_demo/adapter.py
tests/server/fixtures/scripted_invoke_adapter.py
tests/server/fixtures/wavegen_adapter.py
tests/server/test_adapter_failure.py
```

SDK at `56e832c` — the SDK's own `src` carries no host-admission declaration
either (grep exits 1 = no matches):

```
$ git grep -n -E "host_admission|hostAdmission|admits_on_result|admitsOnResult" 56e832c -- src; echo "(exit $?)"
(exit 1)
```

Reading of the evidence: the declaration the #589 records cite at
`adapter.py:1216-1217` is a line range in the measured plugin's own GENERATED
adapter (the scaffold's `adapter.py.jinja` output, living in the plugin author's
project outside both repositories) — an observation of one plugin on one day,
never a surface the gateway can read, and not a surface the SDK exposes either.
SDK PR #256 corrects the three record citations to say exactly this. A plugin
cannot carry the declaration today without a corpus schema change, and no
in-repo code reads one if it did. That is what justifies respecifying the guard
(§2) instead of conditioning it (§3, candidate 1).


## 2. The anti-fabrication property, respecified

The old property ("bridge-side state, never adapter cooperation",
`otdp_bridge.py:1463-1467`): a dataset-shaped result counts only if it byte-equals
a manifest that passed admission through `dataset_publish` during this dispatch.
What that actually guaranteed was **validation-and-persistence provenance**: the
manifest that becomes the run's dataset passed the host's validation
(identity → idempotency → pinned schema → M01-M04 → M10 → M11) and was persisted
through the staged writer (a `art-<sha256>` row, a dataset-kind evidence row,
quota-charged). The trigger sat with the adapter.

The respecified property (this design): **a dataset-shaped result is admitted only
by the host's own admission validation on the result itself — the same pipeline,
unchanged order — and only then persisted; admission failure is the typed
invalid-result refusal and the result never stands as a dataset.** The trigger
moves to the host. What it still guarantees, per manifest that becomes a
run-recorded dataset:

1. it carries a **host-minted id** (`ds:{operation_id}`, gate I6 at
   `otdp_bridge.py:424-440`; the identity check refuses anything else — the
   adapter cannot choose its dataset id);
2. it passed the **pinned measurement schema** and the implemented M-check subset
   (unique ids, dimension agreement, dtype↔encoding, inline finiteness, the
   channels cross-check against the descriptor, M10 correlation to THIS dispatch's
   action/input, M11 scope to payloads THIS operation finalised);
3. it is **byte-persisted** through the staged writer with a sha256 artifact row
   and a dataset-kind evidence row under the run's context key — quota-charged,
   rollback-safe (the wave-2 one-transaction boundary, `dataset_services.py:527-560`);
4. it is **immutable once admitted** (idempotent re-admission returns it;
   a divergent manifest under the same id refuses).

What it stops guaranteeing: **nothing of substance.** The set of manifests that
can become datasets is the same — schema-valid, M-check-passing, host-minted-id
manifests produced by the adapter. Under the old design a fabricated-but-valid
manifest passed by being published; under the new one it passes by being
returned. What is removed is only the requirement that the adapter make the call.

What this guard never caught, in either design (a guard states what it does not
catch): **measurement authenticity.** The adapter is trusted Python — the bridge
says so at `otdp_bridge.py:499-504` ("the stamp separates accidental collision
from origin, it does not prove origin against deliberate hostility") — and
`dataset_publish` never verified that values were real; it validated structure.
A schema-valid manifest of invented values passes both designs. The check proves
validation-and-persistence provenance, not truth of measurement. The issue's
"fabricated dataset-shaped result still refuses" row is therefore read as: a
fabricated result that fails validation refuses (ARM-2/3/3b); a fabricated result
that passes validation is admitted exactly as its published counterpart was
before the ruling.

## 3. The candidates, evaluated

### Candidate 1 — a descriptor-level declaration in the OTDP contract; gate the check on it (the issue's recommendation, option 2)

Rejected on CORRECTNESS grounds that stand independent of cost; the cost is
priced separately below so the two cannot be confused.

**Correctness (decisive on its own):**

- **The gate would perpetuate the trap the ruling removes.** The ruling made
  host-admission the standard, not a per-plugin option. A gated check refuses the
  standard behavior for every plugin whose descriptor lacks the new field — the
  same trap, re-implemented as schema absence. A declaration whose DEFAULT is the
  ruled behavior is not a gate; it is the new design with extra steps.
- **It would condition protection on adapter-supplied metadata.** The issue's own
  open question says the design "must not depend on adapter cooperation at invoke
  time"; a descriptor field read at load is static cooperation, but the deeper
  problem is what the gate protects: under the ruling there is no class of plugin
  for whom publish-required remains correct. The gate protects a distinction the
  standard deleted.

Had these grounds not held — had the declaration marked a behavioral distinction
the standard still recognizes — the descriptor would be the better model and the
cost below would be a price to pay, not an objection. They do hold.

**Delivery cost (real, none of it skippable, and NOT the reason for rejection) —
the four-leg path the SDK session priced (2026-11-09):**

1. the normative content changes in THIS repository's canonical corpus — a new
   field in `otdp-device-descriptor.schema.json`, which under copy-never-move is
   a version increment by definition. **The schema version, named per the
   standing requirement so the export tooling's pin is settled if this candidate
   is ever taken: OTDP 0.2.5** (the copy-never-move successor of 0.2.4, new rows
   citing 0.2.4 paths as `source`, in-arc motion of every in-tree artifact
   pinning corpus bytes — plugin fixture descriptors' `otdp_version` + contract
   URNs, the descriptor digest chains, corpus-derived test literals);
2. the export of the bundle from the canonical corpus;
3. arrival in the SDK through `sync-standards` with that version increment —
   hand-editing the SDK's vendored tree is wrong regardless of quality;
4. SDK support for the field, then an SDK RELEASE, then the gateway pointer PR
   (the #408 order rule). At least one release sits on the critical path.

For scale: the chosen candidate's corpus motion is PROSE-ONLY (4.4) — zero of
these four legs, no release, no pointer motion.

### Candidate 2 — structural verification of the manifest against the returned payload, provenance kept out of the guard

Not an alternative here; it degenerates into the admission core or into a weaker
check. For inline-valued manifests — what an invoke-only plugin returns — the
manifest IS the payload; there is no second artifact to verify against, so
"structural verification against the returned payload" is circular. For
artifact-backed manifests, the binding already exists as M11 (references must
name payloads THIS operation finalised, `dataset_services.py:717-747`). Take the
remaining structure checks (schema + M01-M04 + M10) WITHOUT persistence and you
get strictly less than admission: a result the run treats as a dataset while the
content store holds no artifact row, the evidence ledger holds no dataset row,
and no quota is charged — a laundering path that launders the ambiguity the
evidence discipline exists to prevent (A06). The fabricated manifest that passes
pure structural verification: any schema-valid manifest carrying the host-minted
id — including one whose inline values are invented (see §2) and, without
persistence, one the run's records cannot later produce bytes for. Conclusion:
the structural half of candidate 2 is subsumed by the admission core; the
persistence half is what makes the guard mean anything. Rejected as a standalone
shape; adopted as a component. (Cost note, for completeness: like the chosen
candidate, it lives entirely in this bridge and bumps nothing — its rejection is
the weakness above, not its price.)

### Candidate C (chosen) — the host admits on result: the admission core called from the bridge's result gate

The SDK's shipped standalone shape, mirrored. The validation pipeline and the
persistence routing are unchanged — the existing `dataset_publish` body — moved
onto a callable both the service member and the bridge reach. Nothing new is
invented; the precedent is the mechanism this repository already runs, with its
trigger moved to the ruled side of the adapter boundary.

## 4. The mechanism

### 4.1 Extract the admission core (`src/benchweave/content/dataset_services.py`)

A new module-level class `DatasetAdmission`, constructed by
`build_dataset_services` (which already holds every ingredient — controller,
writer, content, context key, quota, wall, channels):

- fields: `_controller`, `_writer`, `_content`, `_context_key`, `_quota_evidence`,
  `_wall`, `_channels` — moved from the `_InvokeMembers` attribute set;
- method `admit(self, manifest: dict, context: Any) -> dict` — the current
  `dataset_publish` body verbatim, in the same load-bearing order: identity
  (482-493) → idempotency (494-502) → pinned schema (503-510) →
  `_check_m_structural` incl. channels (511) → `_check_m10_correlation` (512) →
  `_check_m11_records` (513) → staged-writer routing + evidence row with the
  quota abort-and-stamp path (514-560) → `note_payload_finalised` +
  `record_admitted` (561-562). Raises `DatasetServiceRejected` (typed, unchanged
  prefixes) or the stamped `EvidenceQuotaExceeded`; both existing channels;
- the M-check helpers and `_DTYPE_ENCODING` move with it (they serve only the
  core);
- `_InvokeMembers.dataset_publish` becomes a delegation:
  `async def dataset_publish(self, manifest, context): return self._admission.admit(manifest, context)`
  — external contract byte-identical (async signature, refusal types, idempotent
  return);
- `build_dataset_services` returns `(bundle, admission)` — signature change; the
  two call sites move in-arc (`interfaces/app.py:959`, the construction test at
  `tests/unit/test_dataset_services.py:766`);
- **removed as dead**: `DatasetController.admitted_for` (sole caller was the
  cross-check — verified by grep) and `DatasetController.dataset_shape_note`
  (sole caller was the refusal note at `otdp_bridge.py:1472`; its property — a
  dataset-shaped result that also fails the pinned schema refuses with the
  validator's own finding — is re-homed STRONGER as ARM-3, which pins the actual
  refusal rather than a note helper). The `dataset_shape_note` controller tests
  retire with the property re-homed; `canonical_json` at `otdp_bridge.py:102`
  goes if grep confirms no other in-repo caller.

### 4.2 The bridge admits (`src/benchweave/host/otdp_bridge.py`)

- constructor kwarg `dataset_admission: Any = None` → `self._dataset_admission`
  (the §0.3 posture: the bridge holds a controller object per lane — capture,
  stream, dataset — and never reaches through `self._services`, whose pinned
  exercised subset stays `{monotonic}`);
- the dataset-shaped branch (1462-1479) becomes:

```python
if self._dataset.is_dataset_shaped(payload):
    # The ruled path (#589 §4 / #604): the host admits the
    # dataset-shaped result itself — identity, idempotency, the
    # pinned schema, the M-checks, then the staged-writer routing
    # and the evidence row. Bridge-side validation, never adapter
    # cooperation; admission failure is the honest invalid-result
    # refusal.
    if self._dataset_admission is None:
        raise InvalidInvokeResult(
            "invoke returned a dataset-shaped result but the dataset "
            "admission lane is not armed"
        )
    try:
        self._dataset_admission.admit(payload, context)
    except DatasetServiceRejected as exc:
        raise InvalidInvokeResult(
            "invoke returned a dataset-shaped result the host "
            f"refused to admit: {exc}"
        ) from exc
```

- `DatasetServiceRejected` joins the existing import from
  `benchweave.content.dataset_services` (73-75).

Failure composition — all existing, tested paths, no new machinery:

- **validation refusal** → `InvalidInvokeResult` → the `except` at 484-491 → R6
  poison with the specific message (the same posture the cross-check refusal has
  today; a plugin returning an invalid dataset-shaped result is a protocol lie);
- **evidence/payload quota during admission** → the stamped
  `EvidenceQuotaExceeded` raised inside `_convert` (inside the same `try` at
  460-483) → the resource-condition handler at 492+ → the C3/R10 discriminator
  (`_capture_originated` 1249-1271: `dataset_evidence_originated(exc,
  operation_id)` binds the bundle stamp to THIS operation; the admission core's
  payload id is minted for this operation and registered live) → the invoke-lane
  branch (537-565): `abort_open` reclaim under the epilogue floor,
  `RESOURCE_LIMIT` refusal, `dispatch_state=dispatched`, **session survives**;
- **the store clamp still brackets the write**: `_convert` is called at 462,
  inside the `with ExitStack() as clamp_stack` whose invoke arm clamps the shared
  staged writer (381-400) — the admission's sqlite writes hit the clamped window
  exactly the adapter's own appends do. `test_invoke_dispatch_brackets_the_store_clamp`
  (3454) stays green unchanged.

The single `_convert` call site (verified: only 462) means no other path needs
the treatment.

### 4.3 The wiring (`registry/otdp_loading.py`, `interfaces/app.py`)

The loader's `dataset_services` factory protocol (loader kwarg, app-supplied,
called at `otdp_loading.py:269`) returns the pair; the loader unpacks and passes
`dataset_admission=` into `OTDPBridge(...)` (298-305) — the same named-kwarg
threading `capture` and `stream` controllers already take. `app.py`'s
`dataset_factory` closure (943-965) unpacks `build_dataset_services`'s new return
and returns both. When no factory is supplied (tests constructing bridges
directly), admission is `None` and a dataset-shaped result refuses honestly
("lane not armed") — the SDK seam's exact posture; a bridge that cannot admit
says so instead of pretending.

### 4.4 The corpus prose amendment (`standards/otdp/0.2.4/extension-contract.md`)

The corpus today teaches the trap: line 85 — "Inline datasets also go through
`dataset_publish`; small data is not exempt from semantic validation" — and the
dataset-services section at 56-85 describes publication as the adapter's path.
The amendment (in place, no version bump — grounds below):

- dataset_publish keeps its paragraph (it stays: upload actions inspecting a
  dataset before payload reads; pre-result publication for fetch cycles;
  idempotent re-admission of a published manifest returned as the result);
- a ruled paragraph: the HOST admits a dataset-shaped invoke result itself,
  through the same validation (identity against the host-minted id, idempotency,
  the pinned schema, the M-checks, artifact routing, the evidence row); an
  adapter that returns a dataset-shaped result need not call `dataset_publish`;
  admission failure is the typed invalid-result refusal;
- the line-85 sentence becomes: inline datasets go through the same admission
  validation; whether the manifest arrives through `dataset_publish` or as the
  invoke result itself, small data is not exempt from semantic validation;
- a dated amendment note (the `invariants.md` amendment pattern) citing the
  ruling and #604.

**Governance call, made explicitly:** in-place prose amendment, NO version bump.
Grounds: `corpus-manifest.json` carries zero `.md` rows (verified — 36 rows for
0.2.4, none prose), so no digest can move; GOVERNANCE's change table treats
companion prose as not digest-pinned ("keep it truthful"); consumers resolve
MACHINE bytes by pin (R-2 multi-version serving), so prose motion breaks no pin;
and a 0.2.5 whose machine files are byte-identical to 0.2.4 would be a phantom
bump — version ladder motion with no consumer-visible machine change — while
churning the full two-repo release pipeline (SDK sync, release, pointer, the #408
order). The standards-governor lane (mandatory for any `standards/` touch) and
the single-human-reviewer rule apply regardless. **Contingency, named:** if the
governor lane rules the normative-prose reversal requires a bump, the same PR
grows the copy step (0.2.4 → 0.2.5 per GOVERNANCE's bump mechanics — a shape this
tree has run repeatedly); the SDK leg then follows per #408. The edit text is
identical either way; only the packaging differs.

### 4.5 Published prose (`docs/device-developer-guide.md`, ASD-STE100 — dispatch the `document-writer` agent)

Line 598 pins the trap in operator-facing prose: "The host refuses a
dataset-shaped `result` that it did not admit through its dataset services, as a
protocol violation from day one. Publish through `dataset_publish` with
`context.dataset_id` rather than inlining." Replaced with the ruled statement:
the host admits a dataset-shaped result itself through the same validation a
`dataset_publish` call runs; an ill-formed dataset-shaped result is refused as a
protocol violation carrying the validator's own finding; `dataset_publish` stays
available for actions that must publish before returning. Line 142 (dataset
identity) keeps the host-mint discipline and notes both entrances validate
against `context.dataset_id`.

### 4.6 Invariants (`docs/internal/invariants.md`)

One NEW row (next free CTL number at build time), the respecified property:

> A dataset-shaped invoke result is admitted only by the host's own admission
> validation on the result — identity against the host-minted id, idempotency,
> the pinned measurement schema, the M-check subset, artifact routing through the
> staged writer, the dataset-kind evidence row — the same pipeline
> `dataset_publish` runs; it is never laundered as a plain result and never
> accepted unvalidated. Admission failure is the typed invalid-result refusal; a
> resource-condition admission failure is the classified lane refusal and the
> session survives. *A dataset enters the run's record only through the host's
> validation and persistence, whichever side of the adapter boundary initiated
> it.*

No existing row changes text: CTL-6/CTL-7 are procedure-side and untouched; STO
rows untouched (the writer is unchanged); REG-4 (adapter agreement) pins
`_Context`, the `self._adapter` call set and envelope key sets — a constructor
kwarg and a result-branch rewrite are none of those (verify at build that
`tests/sdk/test_adapter_agreement.py` needs no edit). A06 strengthens (the
evidence row now covers the ruled path); A13 untouched (no REST/MCP surface
moves — the refusal rides the existing `PROTOCOL_ERROR` message channel; the
interface contract and `mcp-tools.json`/`openapi.json` enumerate no invoke
refusal substrings — verified by grep).

## 5. Minimal first slice

Ships, in one PR:

1. the `DatasetAdmission` extraction + delegation + the two call-site moves
   (4.1);
2. the bridge branch rewrite + ctor kwarg (4.2);
3. the loader/app wiring (4.3);
4. the corpus prose amendment (4.4);
5. the device-developer-guide rows (4.5, document-writer agent);
6. the new invariant row (4.6);
7. the arms below, replacing/re-homing the retired tests.

### Deferrals, each named

- **SDK-side follow-ups** (their own SDK arc, after this merges — they cannot
  precede it): retiring the D10 disclosure (the divergence sentence and the
  `host_info` `dataset_admission.gateway_divergence` block in the SDK's
  `dataset_admission.py`/`seam.py`, which say "until GW-1") and the SDK guide's
  dataset-section prose. Carried by #589's remaining rows; this PR's body notes
  them. No SDK code change is required by the gateway slice — the SDK's
  standalone host already admits on result; only its DISCLOSURE prose ages.
- **A dataset retention/pruning policy** — the PR-3 record's "S4/GW-1's corpus
  question" is NOT taken here. No unbounded growth path is introduced: the
  admission's manifest bytes charge the per-bench dataset byte budget through the
  staged writer exactly as publish does (the budget is the bound). The corpus
  question stays with its S4 carrier.
- **Cross-principal dataset authorization** — the standing deferral, mirrored
  verbatim from the publish path; unchanged.
- **A gateway-side `dataset_admitted` event** (the SDK emits one on its event
  bus) — the gateway's record is the evidence row + artifact row; no event
  surface is added. If the monitor wants a live signal, that is a future slice
  with its own carrier.
- **M11-at-the-bridge beyond ARM-3b** — the M-checks are shared-core and
  unit-pinned on the publish path; one bridge-level M11 arm (3b) proves the
  wiring, a matrix is not built.

## 6. Arms (the test plan; each maps to an acceptance row)

All in `tests/unit/test_otdp_bridge.py` unless named; fixtures are the existing
synthetic invoke set (`_invoke_synthetic_contracts`, `_A_PUBLISHABLE_MANIFEST`,
`_DATASET_SHAPED_RESULT`) with invented `demo.*` names.

- **ARM-1 (the RED arm — the fix):** a valid dataset-shaped result, NO publish
  call. Before: refused, `"dataset_publish"` in the message (pinned today at
  3405). After: `OperationStatus.OK`; the manifest is admitted —
  `controller.admitted_by_dataset_id("ds:op-i")` equals the payload; the writer
  holds one `art-<sha256>` row for the manifest bytes; one dataset-kind evidence
  row exists under the harness context key.
- **ARM-2 (identity):** dataset-shaped result whose `dataset_id` differs from
  `context.dataset_id` → poison carrying "does not carry the host-minted id".
- **ARM-3 (schema):** dataset-shaped result failing the pinned measurement
  schema → poison carrying the validator's `json_path` finding (re-homes the
  `dataset_shape_note` property, stronger: the actual refusal, not a note).
- **ARM-3b (M11 scope):** dataset-shaped result referencing an artifact id this
  operation did not finalise → poison carrying the M11 refusal.
- **ARM-4 (immutability — the preserved property):** adapter publishes A during
  execute, returns A′≠A → poison carrying "already admitted and immutable"
  (re-homes the mutation arm at 3715; the old design refused this too, by match
  failure — the outcome is preserved, the message changes).
- **ARM-5 (idempotent compose):** adapter publishes A and returns A → OK
  (re-homes the passing arm at 3715; pre-ruling plugins stay conformant).
- **ARM-6 (lane not armed):** bridge with the controller but no admission object
  → dataset-shaped result poisons with "admission lane is not armed".
- **ARM-7 (quota, classified):** result-side admission under an exhausted
  dataset/evidence budget → `RESOURCE_LIMIT` failure, message
  "invoke resource condition", `dispatch_state=dispatched`; a subsequent invoke
  dispatch on the same session runs (the session survives).
- **ARM-8 (no overreach):** a plain (non-dataset-shaped) result triggers no
  admission — no admitted manifest, no evidence row, `OK` unchanged (pinned
  partly today at 3294's tail).
- `tests/unit/test_dataset_services.py`: **every existing publish-path test
  passes UNMODIFIED** except the two named mechanical edits (the
  `build_dataset_services` construction-site signature; the retired
  `dataset_shape_note` tests). One new test pins the one-core property: the same
  manifest admits identically through `dataset_publish` and through
  `DatasetAdmission.admit`.

## 7. Review tier and the Step-1 keyword scan (#254)

**Tier 3.** Trigger rules, first-match: the diff touches `standards/` (the
extension-contract.md amendment) — also independently: `src/benchweave/registry/`
loading behavior (`otdp_loading.py`), and the keyword rule (`sha256`, `hashlib`).
The review takes the Tier-3 deep lane plus the mandatory standards-governor pass
(any `standards/` touch).

**Keyword scan, design-time, over the expected diff** (the eight Step-1 words:
`threading`, `asyncio`, `subprocess`, `sha256`, `hashlib`, `migrate`,
`recovery`, `protection`). The expected diff's inventory: the dataset_services
extraction (~100 moved lines containing `hashlib.sha256(blob).hexdigest()` once
and the `"sha256"` dict key once; ~60 new lines of class/docstring), the bridge
branch rewrite (~25 lines, no keywords), the loader/app wiring (~15 lines, none),
the corpus prose (~2 paragraphs; the section's existing "SHA-256" is
uppercase-hyphenated and does not match), the guide rows (~2), the invariants row
(~1; may name the sha256 artifact row once), the arms (~150 lines of test;
manifest fixtures may carry `"sha256"` in artifact dicts). **Design-time counts:
`sha256` ≈ 3-5, `hashlib` ≈ 1, all six others 0 — the moved admission core is the
only carrier.** The counts are the design's estimate over the named inventory;
the review re-derives them over the actual diff, and the builder states the
actual counts in the PR body (#254's rule). Tier is Tier 3 under any of the counts.

## 8. The measurable proof — pre-committed acceptance rule

Written before any number was looked at; the suite has not been run against this
design (the design-pass probe hit the disclosed venv artifact and was abandoned).

**Metric:** the behavior pair of ARM-1's fixture adapter (return-valid-dataset-
shaped, no publish) at two heads — `origin/main` (`b08ee075`) and the slice head —
plus the poison/refusal arms' named substrings. Deterministic fixtures: each arm
is a population of one per head, not a sample; no randomness, no power analysis
beyond the RED leg's reach.

**SHIPS if all of:**

1. at the slice head, ARM-1 yields `OK` with all three admission residues
   present (admitted-by-id record equals the payload; one manifest artifact row;
   one dataset-kind evidence row) — and the RED leg holds: the same test at
   `origin/main` refuses with `"dataset_publish"` in the message (run the new
   test file against the old head, or revert only the branch rewrite and watch
   ARM-1 flip);
2. ARM-2, ARM-3, ARM-3b, ARM-4, ARM-6 each poison carrying its named substring;
3. ARM-5 and ARM-8 are `OK` with no admission residues in ARM-8;
4. ARM-7 is `RESOURCE_LIMIT`, dispatched, and the same session completes a
   further dispatch;
5. `tests/unit/test_dataset_services.py` passes with exactly the two named
   mechanical edits and nothing semantic (count from `--junitxml` `tests`
   attribute, never a filtered summary line); the full battery (fast triple +
   full suite + both standards tripwires) is green at the slice head with
   `UV_PROJECT_ENVIRONMENT=venv`, true exit codes.

**KILLS if any of:**

1. any of ARM-2/3/3b/4/6 fails to poison — the anti-fabrication guard is weaker
   than designed and the slice does not merge (this is the property the whole
   design exists to carry across the ruling);
2. ARM-1 admits a manifest that fails identity or the pinned schema (the gate
   order is wrong — the admission ran after acceptance instead of being the
   acceptance);
3. the publish suite needs semantic edits to pass (the extraction changed the
   publish path's behavior — the one-core premise is false and the design's
   equivalence claim dies with it).

**UNDERPOWERED, not conclusive, if:** the RED leg cannot be demonstrated against
`origin/main` because the pre-fix head cannot arm the admission lane at all. The
sanctioned degradation: neutralize the mechanism (cp-backup the branch, replace
the `admit` call with `pass`) and show ARM-1 flips from OK-with-residues to
clean-pass-without-residues — a valid but weaker RED (it proves the mechanism
produces the residues, not that the old head refused). If even that is
unavailable, the acceptance evidence is insufficient: the arms still must pass,
but the claim "this fixes the trap" goes unproven, the issue stays open, and the
record is amended to say so. Tuning any threshold after seeing a run is the
failure this section exists to prevent; a run that misses SHIP goes to KILL or to
the named degradation, never to re-negotiation.

## 9. Risks, each with its falsifier

1. **The result-side write lengthens the conversion window.** The admission's
   sqlite writes run inside the row-B dispatch clamp (verified by call position:
   `_convert` at 462 sits inside the `ExitStack` whose invoke arm clamps at
   381-400), so the existing disclosed-overshoot semantics cover it. Falsifier:
   a reviewer demonstrates an unclamped path or an overshoot beyond the disclosed
   bound — then the admission call moves formally inside the clamp context at
   build (mechanical; the call position is already correct).
2. **The no-bump prose call is overruled.** Named contingency in 4.4: the same
   PR grows the 0.2.5 copy step; SDK leg follows per #408. Cost is packaging,
   not design.
3. **Poison-on-divergence is too harsh** (publish A, return valid A′≠A: the
   operation poisons the session). Deliberate parity: the old design refused
   this case too (match failure → `InvalidInvokeResult` → poison), and a plugin
   that publishes one manifest while returning another is lying about which
   dataset the result is. Falsifier: a use case where the publish-and-return-
   different shape is legitimate (upload actions publish for inspection and
   return a DIFFERENT dataset as the result — if real, the identity/immutability
   refusal needs a per-operation two-id refinement; none exists in the corpus
   today, and the SDK standalone host has the same refusal).
4. **`is_dataset_shaped` over-capture**: a plain result that happens to carry
   the eleven dataset keys is now admitted (or refused) as a dataset attempt.
   Unchanged detector, and the action's output schema already gates what a
   result may be (a non-fetch action's schema will not ref the dataset def).
   Falsifier: a legitimate non-dataset result shaped exactly like the manifest —
   the remedy is the action's output schema, not the detector.
5. **The harness cannot construct the admission lane cheaply** (the arms depend
   on wiring `DatasetAdmission` beside the controller in `InvokeHarness`). The
   bundle constructor already takes every ingredient (the 3715 test constructs
   `DatasetPayloadBundle` directly); the admission object is the same fields.
   Falsifier: none expected; if the harness fights it, the arms move to the
   dataset-services file with a thin fake bridge context (ids only).

## 10. What the builder runs

- FAST lane every commit; full battery once before push (both standards
  tripwires included — the `standards/` touch makes them load-bearing).
- RED demonstration per §8 before the fix lands in the same commit's message
  (one commit may carry the arms + the fix with RED evidence in the message, per
  the batch rule).
- `tests/sdk/test_adapter_agreement.py` green unmodified (REG-4 unaffected —
  confirm, do not assume).
- The `document-writer` agent for the guide leg; engineering register everywhere
  else (this record, the invariants row, the corpus prose).

---

Sources, first-hand: a scratch worktree at `origin/main` `b08ee075` (every
gateway line number above); the SDK repository at `56e832cb` via git (the two
#589 design records, `dataset_admission.py`, `seam.py`'s result gate); the
corpus bytes at `standards/otdp/0.2.4/`; issue #604 and SDK PR #256 over `gh`;
the ruling's words as quoted in the SDK records (the issue comment itself was not
fetched — the two records agree verbatim and PR #256 does not contest them). The
§1 evidence commands were re-run verbatim 2026-11-09 after the SDK session's
cost/schema-version additions; outputs are recorded as captured, not paraphrased.
