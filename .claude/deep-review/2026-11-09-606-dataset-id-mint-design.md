# Design: #606 — the dataset admission identity reads the host's mint, not the adapter-held context attribute

- **Issue:** gateway #606 (found by the GW-1 adversary lane, filed with the issue)
- **Tree read and verified:** `origin/main` at `5f4256c1` (the local primary checkout lags at
  `084c5e6c`, pre-GW-1 — every file:line below cites the origin/main blob; the fix branches
  from `origin/main`)
- **Tier call (design-time, #254):** **TIER 3** — by dispatch (identity on the admission
  path); the objective Step-1 rules alone classify the code diff Tier 2, and this record's
  own §8 scan-table labels self-fire the keyword rule by construction. See §8.
- **RED status:** the reachability probe below was run pre-fix on `5f4256c1` and FAILED in
  the direction that proves the hole open. This is not a hypothetical defect.

## 1. Finding, confirmed at source and by a first-hand probe

`DatasetAdmission.admit` (`src/benchweave/content/dataset_services.py:385-415`) takes the
admission identity from the context object:

```python
operation_id = str(getattr(context, "operation_id", ""))    # :402
dataset_id = getattr(context, "dataset_id", None)           # :403
```

`context` is the bridge's `_Context` (`src/benchweave/host/otdp_bridge.py:103-110`), a plain
object whose `dataset_id` attribute is set once by the host at invoke dispatch
(`otdp_bridge.py:431-439`, gate I6, via `mint_dataset_id`) and then handed to the adapter in
`execute` (`otdp_bridge.py:460`). The adapter holds a live reference to a mutable object.
The mint the host performs is *recorded* — `mint_dataset_id` writes
`_operations[operation_id]["dataset_id"]` (`dataset_services.py:176-184`), readable through
`dispatch_state` (`dataset_services.py:144-147`) — but before this fix nothing on the publish
path read that key back. The identity check compared the manifest against the adapter-rewritable
copy, and `record_admitted` (`dataset_services.py:270-296`) filed the manifest under
`manifest["dataset_id"]`, which that check had just forced to equal the context value.

**The adapter chose the key its manifest was filed under.** The refusal message called the
value "the host-minted context.dataset_id" (`dataset_services.py:407-415`) — a claim the code
did not enforce.

**Probe (run by this design, not cited from the issue).** A detached worktree at `5f4256c1`,
one throwaway bridge-level test (since deleted): an adapter that sets
`context.dataset_id = "ds:attacker"` in `execute` and returns a valid dataset-shaped manifest
carrying `"ds:attacker"`; assertions `status is UNKNOWN` and
`admitted_by_dataset_id("ds:attacker") is None`.

Result, read from `--junitxml` (2 tests / 1 failure / 0 errors; exit 1 — the passing test is
the no-rewrite control on the same harness):

```
AssertionError: #606 OPEN: dispatch returned ok (error=None) — the rewritten context id was honored
```

The dispatch returned **OK** and the manifest was admitted under the adapter-chosen id.
Reachability end to end — dispatch → adapter rewrite → invoke result gate
(`otdp_bridge.py:1461-1479`) → `admit` → `_admitted_by_dataset["ds:attacker"]` — is proven
first-hand. The kill direction ("if the demonstration cannot be made to fail, close #606 as
unreachable") does not fire. The issue additionally demonstrates the cross-operation
consequence (a later operation denied its own dataset id because the thief claimed it first);
this design re-verified the primary path only and cites the issue for that consequence.

## 2. Root cause, and why the existing arm misses

Root cause in one line: the identity term of a host-authoritative check reads a value the
checked party holds and can rewrite (`dataset_services.py:403`), while the authoritative
record the host itself minted sits unread one method call away (`dispatch_state`).

`test_gw1_arm2_foreign_dataset_id_poisons` (`tests/unit/test_otdp_bridge.py:3923-3944`)
plants a foreign id in the manifest and leaves the context honest — the liar-in-the-payload
adversary. The identity check as written catches exactly that. It has no arm for the
liar-in-the-context adversary, which is the one the mechanism actually permits.

Severity framing (issue #606's own honest statement, anchored by decision A05's "plugin trust
is a documented assumption"): the adapter is trusted Python that could already fabricate any
schema-valid manifest, so this is not new privilege. The defect is the **stated guarantee** —
CTL-13 and the GW-1 record §2 item 1 say the adapter cannot choose its id; the code did not
enforce that. A guarantee a reviewer relies on while reasoning about dataset identity is the
asset; under claim discipline (rubric G4) a *cannot* claim without a structural reason is
itself the defect.

## 3. The mechanism (the whole production diff)

One source change in `DatasetAdmission.admit`, `dataset_services.py:402-415`. The identity
value stops coming from the context attribute and starts coming from the controller's mint
record — the exact in-class precedent `_check_m10_correlation` already uses
(`dataset_services.py:616`):

```python
operation_id = str(getattr(context, "operation_id", ""))
state = self._controller.dispatch_state(operation_id)
dataset_id = state["dataset_id"] if state is not None else None
```

- The mismatch refusal (`:411-415`) is **unchanged verbatim** — "does not carry the
  host-minted id" — with `{dataset_id!r}` now rendering the true mint. Both existing message
  pins (`tests/unit/test_otdp_bridge.py:3940`, `tests/unit/test_dataset_services.py:432`)
  survive as written.
- The no-identity refusal (`:406-410`) is reworded, because after the fix the firing
  condition is "no mint for this operation", not "null attribute":

  `dataset_publish requires the host-minted dataset id for this operation (an unminted
  operation forbids publishing)`

  For every real flow this is the same rule the old message named: `context.dataset_id` is
  null exactly when no mint exists (the host mints on every invoke dispatch before `execute`
  and never on a non-invoke one — pinned by `test_i6_invoke_mints_the_host_dataset_id_on_the_context`).
  The only state the rewording changes is a fabricated one: a minted operation whose context
  attribute was nulled by the adapter mid-flight, which now admits (the manifest must still
  carry the mint) instead of refusing. That state is unreachable by a conformant adapter and
  its old refusal was an accident of reading the wrong source.
- The order is untouched and stays load-bearing: identity first, idempotency, schema,
  M-checks, then routing. `dispatch_state` is a read-only dict lookup, so a refused admission
  still reaches no writer call, no evidence row, and no admitted state — a refusal cannot
  have persisted anything.
- Docstring corrections in the same commit, same file: the `DatasetAdmission` class docstring
  (`:345`) and `admit`'s docstring (`:388`) say "identity against the host-minted
  `context.dataset_id` / it must equal `context.dataset_id`" — reworded to name the mint
  record as the source. `mint_dataset_id`'s docstring gains that its record is now the
  admission identity's authority (it was write-only before; this fix is what makes it
  load-bearing).

That is the entire production change. Precedent: no new architecture — the fix reroutes one
lookup to the in-class mechanism (`dispatch_state`) that M10/M11 already trust for the same
operation's state. One completeness note for the refute lane: the only other state-creating
path, `mint_payload_id`'s out-of-dispatch fallback (`dataset_services.py:196-210`), records
the same host-computed `ds:{operation_id}` — so the identity source stays host-chosen on
that path too; there is no state a bundle call can create whose `dataset_id` key the
adapter supplied.

## 4. What this fix deliberately does NOT do

- **No corpus/standards change.** The vendored extension contracts (all OTDP versions,
  `standards/otdp/<v>/extension-contract.md` ~line 62, and 0.2.4's admission paragraph at
  ~line 66) state the rule from the adapter's side: the host *provides* the id via
  `context.dataset_id`; "the manifest must use that ID; a null value forbids publishing a
  new dataset"; the id "is not chosen … by the adapter". None of that names where the host
  reads at check time, and all of it stays observationally true after the fix — more true,
  since "not chosen by the adapter" becomes enforced rather than asserted. No vendored byte
  moves, no repin loop, no standards-governor pass is *required* by the diff; the refute lane
  is invited to challenge this judgment, and the named fallback if it loses is a corpus
  amendment carried by its own slice.
- **No device-developer-guide edit.** Every guide sentence about dataset identity (lines
  142, 598, 772) instructs the conformant developer — carry the id the host minted onto the
  context, never mint your own — and remains correct. The guide never describes the check's
  internal source. Obligation 3 (plugin-visible behavior) is walked and satisfied with zero
  motion, disclosed here.
- **The `operation_id` rewrite residual is named, not fixed.** The adapter can also rewrite
  `context.operation_id`; admission, M10 and M11 all key on it. Analysis: sequential
  dispatch means a *future* operation has no mint when an earlier `execute` runs, so theft of
  a not-yet-dispatched id refuses; a *past* admitted id hits idempotency-or-immutability and
  returns nothing the adapter could not already obtain by `dataset_lookup` this run; a
  *minted-but-unadmitted* past op can be published under only by correlating to that op's
  own acquisition (M10) and its own finalised artifacts (M11). No privilege boundary is
  crossed — it is misattribution among the run's own ids by an adapter that already holds
  the whole lane. Closing it means binding admission to the *dispatch* rather than the
  context (the bridge knows `request.operation_id`); that is a different mechanism with its
  own arms, deferred to a named follow-up if the maintainer wants it. This record's claim is
  exactly: *the current operation's dataset id is host-chosen*, nothing wider.
- **No SDK motion.** The SDK's standalone host already admits on result with its own
  identity source; the gateway's check is gateway-side. `packages/sdk` pointer does not move.

## 5. Arms (RED-first; each maps to §6's rule)

1. **ARM-2b, bridge (the RED demonstration, becomes the pin):** new
   `test_gw1_arm2b_context_rewrite_poisons` in `tests/unit/test_otdp_bridge.py` beside ARM-2.
   Adapter: an `InvokeAdapter` subclass whose `execute` sets `context.dataset_id` to a forged
   value, then returns `_A_PUBLISHABLE_MANIFEST()` rewritten to carry that same forged value —
   the manifest **matches the rewritten context and not the mint**. Assertions, in order:
   `status is UNKNOWN` with `PROTOCOL_ERROR` carrying "does not carry the host-minted id";
   `admitted_by_dataset_id("ds:attacker") is None` (the forged id filed nothing — **the arm's
   reason to exist**: a test asserting only "some refusal happened" would pass while the hole
   stayed open); `admitted_by_dataset_id("ds:op-i") is None` (nothing admitted for the
   operation at all). Pre-fix this arm fails exactly as the §1 probe did (OK + admitted under
   the forged id); the build records that RED run in the commit message.
2. **ARM-2b twin, unit core:** beside R2 in `tests/unit/test_dataset_services.py` —
   `harness.context()` with `dataset_id` rewritten to a forged value plus
   `a_valid_manifest(forged)`; expect `DatasetServiceRejected` matching "does not carry the
   host-minted" and nothing admitted. Also RED pre-fix (the manifest equals the rewritten
   context value, so today it admits). Pins the core independent of bridge wiring, the
   CTL-13 pin set's existing unit-file habit.
3. **R2 null arm, fixture updated:** `test_r2_identity_refusals`'s second arm
   (`test_dataset_services.py:438-441`) today nulls the attribute on a minted operation.
   After the fix that fixture describes an irrelevant attribute; the arm becomes a context
   for an operation with **no mint** (`SimpleNamespace(operation_id="op-unminted", …)` with
   a manifest carrying `ds:op-unminted`), expecting the reworded refusal, pin
   "unminted operation forbids publishing". The mismatch arm above it is untouched.
4. **W2 quota fixture, one line:** `test_w2_publish_evidence_quota_refusal_charges_nothing`
   (`test_dataset_services.py:883-886`) publishes under `op-b`, which the harness never
   minted. After the fix that publish refuses on identity before reaching the quota path, so
   the test mints `op-b` first (`harness.controller.mint_dataset_id("op-b", …)`). The test's
   subject (quota refusal charges nothing) is unchanged.
5. **Unchanged and must stay green without edits:** ARM-1 (result-side admission), ARM-2
   (foreign manifest id), ARM-4/ARM-5 (immutability, publish-then-return), the I6 mint test,
   the one-core identity test, R2's mismatch arm, R8 idempotency, the R7/W5 read-allowlist
   rows, the publishing-adapter OK path at `:3767-3791`.

## 6. Pre-committed acceptance rule (written before any post-fix run)

- **Metric:** binary, over the enumerated set: {ARM-2b bridge, ARM-2b unit} must be RED on
  the pre-fix head and GREEN after; the §5.5 pin set must stay green with no edits beyond
  the two named fixture updates; full battery once, cold, counts read from `--junitxml`
  attributes or exit codes, never an output-filter summary.
- **Effect size / sample size:** one RED run and one GREEN run of the two new arms; one cold
  full battery at the slice head (n=1 each; these are deterministic unit tests, not
  statistics — repetition is not the evidence, direction is).
- **Ship if:** pre-fix run of ARM-2b fails with `status ok` + admitted-under-forged (the §1
  probe's signature), post-fix run green, battery green, ruff + fresh-cache bare mypy green.
- **Kill (fix wrong):** any §5.5 pin fails for a reason the two named fixture updates do not
  honestly cover — the fix narrowed a ruled behavior (the #604 host-admits-on-result ruling
  included); do not patch the test to force green, kill the slice and redesign.
- **Kill (hole unreachable):** pre-fix ARM-2b *passes* — the rewrite never reaches `admit`.
  Already disproven by the §1 probe on `5f4256c1`; listed because it was pre-committed as a
  live direction, and a build that cannot reproduce the RED must stop and say so.
- **Underpowered, not conclusive:** the RED run fails for an unrelated reason (0 collected /
  exit 5, harness wiring error) — a broken probe is void evidence; fix the probe and rerun
  before any decision. Likewise a battery run whose counts came from a filtered summary line
  is void, not green.

## 7. Invariant and drift impacts

- **CTL-13 (`docs/internal/invariants.md:232`)** gains a dated amendment, nothing else:
  *Amendment (2026-11-09, gateway issue #606): the identity term is enforced against the
  controller's mint record for the operation (`dispatch_state(operation_id)["dataset_id"]`),
  never the `context.dataset_id` attribute the adapter holds and can rewrite; the mint record
  is the admission identity's only source, and a manifest matching a rewritten context
  attribute but not the mint refuses.* No other row moves: no writer, state, schema, or
  transport surface changes. REG-4 (`_Context`'s pinned surface) is untouched — the
  attribute stays, the host still sets it, only the check's source moves.
- **The GW-1 record (`.claude/deep-review/2026-11-09-604-gw1-dataset-admission.md` §2 item 1)
  is frozen history and is NOT retrofitted** (rubric #254's own clause). Its "the adapter
  cannot choose its dataset id" claim was false at its head; this record is the correction of
  record, and the CTL-13 amendment carries the durable truth.
- **Obligations walked (`docs/internal/drift-and-obligations.md`):** 1/2 no (no MCP tool, no
  API surface — the refusal rides the existing `DatasetServiceRejected` → `PROTOCOL_ERROR`
  message channel, which the contract bytes do not enumerate, per the GW-1 record's verified
  grep); 3 satisfied with zero motion (§4); 8 no (adapter protocol *shape* unchanged — same
  members, same envelopes, one internal check source); 23 no (no verb set, docstring gap
  list, or CLI motion); 5/6/7 no fixture-lattice, vendored-byte, or submodule motion.
- **On-disk formats/schemas:** none. Tier 3 is taken by dispatch and by the record's own
  keyword-table labels, not by a format-surface rule.
- **CI cost:** no new lane, no workflow change, no dependency. Two new unit tests, two small
  fixture edits, one lookup reroute. The Tier-3 cost is the mandatory refute lane plus one
  cold full battery — review depth, not pipeline.

## 8. Tier and keyword scan (#254, design-time)

**TIER 3.** The dispatch takes the deep lane for identity on the admission path. The
objective Step-1 rules, applied to the expected diff (this record, the
`dataset_services.py` change, both test files, the invariants amendment): no path rule
fires (no `contracts/`, `standards/`, persisted-format surface, `registry/`, fixture
lattice, dependency, or submodule motion), and the keyword scan over that diff text
**excluding this §8 table's own row labels** measures, by `grep -c` per keyword:
`threading` 0, `asyncio` 0, `subprocess` 0, `sha256` 0, `hashlib` 0, `migrate` 0,
`recovery` 0, `protection` 0. The code diff alone is Tier 2 by the rules. This table's own
labels carry all eight keywords once each by construction — the rubric's intended self-fire
— so the record's diff is Tier 3 by the letter as well as by dispatch. The review re-derives
the tier independently per #254; both derivations are stated here so neither is discovered
late.

## 9. Deferrals, each named

- The `operation_id`-rewrite binding (admission keyed to the dispatch, not the context) —
  §4's residual, a named follow-up if wanted.
- A corpus amendment naming the check's internal source — only if the refute lane overturns
  §4's no-motion judgment.
- Cross-principal dataset authorization — the standing deferral, untouched.
- The W2 fixture's `op-b` mint is a fixture repair, not a deferral; it rides this slice.

## 10. What this record does not cover

- The cross-operation theft sequence (issue #606's D1/D2) was not re-run by this design; the
  primary path was (§1). The D1/D2 output is cited from the issue, whose author ran it on
  both heads.
- The SDK's standalone host identity source was read about (GW-1 record §deferrals), not
  re-verified file-by-file here; the fix touches no SDK code, and if the SDK's host has the
  same context-attribute shape, that is a separate finding for its own tracker row on the
  gateway issue stream.
- Nothing here changes capture-lane identity (capture ids are host-minted through a
  different controller); no claim is made about it.
