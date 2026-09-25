# Archival tier: offline storage as a disposition target (issue #199)

**Date:** 2026-09-25 · **Issue:** [#199](https://github.com/madeinoz67/benchweave/issues/199)
(carries deferral D1 of the #194 design of record, opened at that slice's merge exactly as
the discipline names it)
**Verdict:** BUILD-minimal — a byte-preserving archive tier over the landed disposition
audit trail: `on_disposition: archive` becomes executable when the operator names an
offline target, via copy-verify-commit ordering that keeps the crash story honest. No
standards byte moves; no serving-surface operation is added.
**Train surfaces:** `cli/dispose.py`, `state/dispositions.py`,
`state/migrations/v7_archive_tier.py` (new), `cli/commands.py` (flags),
`cli/retention.py` (disclosure strings only), operator docs/README, tests. Nothing in
`standards/`, the SDK submodule, or gateway capture surfaces.

## 0. Grounding (read before building — citations from main at `a5fd51d`)

- `.claude/deep-review/2026-09-25-issue194-disposition-design.md` — the parent record.
  Every mechanism below extends one it landed: migration v6 tables, code-enforced
  outcome vocabulary, canonical-JSON envelopes content-addressed through `put_artifact`
  inside the disposition transaction, ONE `BEGIN IMMEDIATE` per invocation, guarded
  exact-row deletes, the three-column live-reference GC predicate
  (`state/dispositions.py::_LIVE_REFERENCE_SQL`), GC byte-verification before collect,
  dry-run default + `--execute`, never-migrate, StoreHold at-rest wrapper,
  caller-supplied timestamps (STO-1).
- `src/benchweave/control/retention_policy.py` — `on_disposition` ∈
  {delete, archive, review} admitted by the schema since slice 3 (line ~100,
  `_rule_properties`); `load_retention_policy_with_digest` (the single-read
  digest loader). **Imported, never re-implemented — and NOT extended**: the policy
  keeps saying *what* happens to a class; the target says *where*, and stays out of the
  policy document (fork F2).
- `src/benchweave/cli/dispose.py` — the executor extended. `_classify` (line ~100)
  routes overdue archive rows to `_ARCHIVE = "blocked_archive"`; the disclosure at
  line ~228 says "the archival tier is not built"; `_IRREVERSIBLE_DISCLOSURE` (line ~84)
  says "recoverable disposition is the archival tier (unbuilt)"; the model carries
  `counts`, `bytes_reclaimed`, `charged_ledger_bytes`, `artifact_bytes_freed`.
  `dispose_from_data_dir` is the wrapper: policy load FIRST, then `StoreHold` →
  `refuse_schema_mismatch` → `Store.open` → plan → execute.
- `src/benchweave/cli/retention.py` — `_WEDGE_DISCLOSURE` (line 150) names
  "the archival tier is unbuilt"; the module docstring's sequencing sentence says
  "every deletion flows through the audit trail's one-transaction executor".
  `build_retention_report`'s row model is the plan authority (A9's zero-drift pin).
- `src/benchweave/state/dispositions.py` — `DispositionLog.execute_invocation`: the
  one-transaction shape; `_ENVELOPE_FIELDS` (19 fields) drives both the writer's
  canonical blob and the A8 recomputation; `_collect_unreferenced` re-hashes artifact
  bytes against their content address before deleting; the invocation row lands last.
- `src/benchweave/state/migrations/__init__.py` — the chain tips at v6;
  `v6_dispositions.py` shows the additive discipline (IF NOT EXISTS, zero CHECKs) AND
  its own widening precedent: v6 **indexed pre-existing tables** (`evidence`,
  `capture_staging`) from a new migration — schema-object addition to an existing table
  was already judged additive when it rewrites no data.
- `src/benchweave/cli/atrest.py` — `backup` is THE external-directory precedent:
  writes `out/backup-<iso>/{state.sqlite, content/, manifest.json}` with
  `_digest_tree` sha256 manifest; "only created under the hold: a refused backup must
  not leave a half-created target directory behind" (review M4 cleanliness); `restore`
  verifies every manifest digest BEFORE touching the data dir. The archive destination
  extends this shape.
- `src/benchweave/state/store.py::begin_kill_window` (line 899) +
  `tests/faults/_dispose_child.py` + `tests/faults/test_disposition_faults.py` — the
  sanctioned kill-window harness (marker-protocol child, kill-mid / kill-after pair).
- `src/benchweave/cli/commands.py` — the `dispose` command registration (line ~719):
  `--data-dir/--bench/--policy/--execute/--out/--json`; the catch family
  (`AtRestError, StoreHeldError, StoreChangedUnderPlan, ValueError, ...`).
- `docs/internal/invariants.md` — STO-1..5 (STO-5 at line 113; STO-3's site list at
  line 99). `docs/internal/drift-and-obligations.md` — obligation 4 (CLI → operator
  guide CLI reference + README) and the Tier-3/two-adversary-lane standing rule.
- `tests/cli/test_dispose.py` — A1–A9 + the fold arms + the scale smoke; the `_seed`
  fixture already carries four archive-tier `event_log` rows
  (`_EXPECTED_COUNTS["blocked_archive"] == 4`) — they become the no-target arm
  unchanged, and the with-target arms are new.
- `docs/operator-guide.md` §7 (lines 407–454) — the dispose section whose
  "archival tier is not built" sentence moves.

## 1. The problem, and the trigger honesty

`on_disposition: archive` is admitted by the policy schema, projected by the report,
counted by dispose — and executable by nothing: every overdue archive row is
`blocked_archive`, bytes never move, and the only recoverable-disposition story the
system tells is the disclosure sentence naming this tier as unbuilt. The delete tier
proved the pattern (audit trail → guarded executor → GC); the archive tier is the same
pattern with one genuinely new hard part: **the destination is a filesystem the SQLite
transaction cannot cover**. That hard part is why #194 deferred it, and it is the
load-bearing design question here (§2.2).

**Trigger honesty, stated plainly:** the reopen trigger fired by the owner's explicit
call, not by operator demand — no operator is blocked on `blocked_archive` today. This
design therefore manufactures no operator requirements: the tier is strictly
opt-in (an explicit `--archive-target`; without it, `blocked_archive` remains the honest
status and no bytes move), and its value is measured by the acceptance controls below,
not claimed from operator pull. An operator who never writes an archive policy rule
sees exactly today's behavior.

## 2. The mechanism

### 2.1 Destination shape: a content-addressed directory with a manifest

The offline target is a plain directory the operator names:

```
<target>/
  objects/<artifact_id>            # the preserved bytes, named by content address
                                   #   (art-<sha256>) — same id as the in-store artifact
  manifests/<invocation_id>.json   # canonical JSON (sort_keys): invocation_id, actor,
                                   #   policy_sha256, written_at (caller-supplied now),
                                   #   destination_resolved, objects:
                                   #   [{artifact_id, byte_length}], row counts
```

- **Shared object pool, per-invocation manifests.** Content addressing gives dedup for
  free: re-archiving byte-identical content (across invocations, across stores, after a
  rolled-back attempt) verifies and skips. Each invocation attempt writes its own
  manifest, so manifests are ATTEMPT-scoped, not commitment-scoped — a crashed attempt
  leaves a manifest describing objects that exist and hash-verify; the trail is the
  commitment record (§2.2's over-preservation window, disclosed).
- **Objects are written durably:** temp file in `objects/` (same volume), bytes
  written, `flush` + `os.fsync`, `os.replace` (atomic), and one directory `fsync` after
  the last object, all BEFORE the store transaction begins. Contrast `backup`, which
  does not fsync (`shutil.copytree`) — backup's contract is "a snapshot, verified at
  restore time"; the archive tier's contract is stronger: the committed trail ASSERTS
  preservation, and a power loss after COMMIT must not leave the trail referencing
  bytes that never reached the destination platter.
- **Typed destination refusals** (`archive_target:` prefix, machine-matchable — the
  `retention_store:`/`retention_policy:` family posture): target unwritable or not
  creatable; target resolves INSIDE the data dir (refused — `restore` swaps the whole
  data dir with `os.replace`, and an archive inside it would be destroyed or moved by
  disaster recovery, the exact opposite of preservation; the `hold_path` resolve()
  precedent for path spelling); a pre-existing object whose bytes do NOT hash to its
  content address (destination corrupt or tampered — **never silently overwritten**:
  overwriting would launder destination corruption into a fresh "verified" copy).
- **No destination lock.** Objects are content-addressed and placed via
  temp+`os.replace`, so concurrent writers cannot interleave corruptly; manifests are
  per-invocation-id (uuid) so they cannot collide. Concurrent SAME-store dispose is
  already excluded by `StoreHold`. Disclosed: two different stores archiving to one
  target interleave safely and dedup.

**Configuration (fork F2):** `--archive-target PATH` on `dispose` only. The policy file
is NOT extended — the policy is the operator's *intent* channel (what happens to a
class); the target is *deployment* configuration (where), it belongs to the command
invocation exactly as `--policy` does, and putting it in the policy would churn the
`additionalProperties: false` schema and the validated-config surface for no operator
demand. No env fallback in slice 1 (a write-path knob should be as explicit as
`--policy`; the env convenience can ride later if anyone asks).

### 2.2 The move: copy → verify → ONE transaction (the crash story)

The parent's all-or-nothing property cannot literally cover an external filesystem.
The invariant that replaces it:

> **Over-preserved, never under-preserved.** A crash may leave the destination holding
> MORE bytes than the committed trail references (objects whose invocation never
> committed). The trail never references bytes that were not verified present at the
> destination, by this process, re-read from the destination, before the transaction
> began.

Concretely, `dispose --execute --archive-target T` over a plan that selects both tiers:

**Phase A — pre-stage (no store transaction open):**
1. Resolve + validate `T` (typed refusals of §2.1). Compute the archive rows' DISTINCT
   content artifact set (shared artifacts stage once).
2. For each artifact: if `T/objects/<id>` exists, re-read and re-hash it — equal ⇒
   counted `objects_deduped`; unequal ⇒ typed `archive_target:` refusal, nothing
   disposed. If absent: write temp → fsync → `os.replace` → re-read from the
   destination → re-hash against the content address (the GC's verify-before-collect
   mirror: **destination bytes are verified, never trusted** — the write syscall
   returning is not proof the bytes are there). Record
   `archive_verified_at = now` (caller-supplied, STO-1) per object.
3. Write `T/manifests/<invocation_id>.json`; fsync the directory.
4. `stage_hook(n)` fires per object — TEST SUPPORT (the `mid_transaction_hook`
   precedent) for the Phase-A fault arm.

**Phase B — the ONE `BEGIN IMMEDIATE` transaction (STO-5's shape, two tiers):**
invocation row plan → for each selected row (delete-tier AND archive-tier): audit
envelope artifact via `put_artifact` joins the transaction + audit row + guarded
exact-row delete (`_current_row` unchanged) → for archive-tier rows also the §2.3
columns → GC of artifacts whose live references are all gone (predicate unchanged) →
invocation row lands LAST carrying complete `counts_json` → COMMIT.

**Crash windows, each with its story:**
- *Crash in Phase A:* store untouched (no transaction was open); the destination may
  carry orphan objects and a manifest. Orphans are content-addressed and verifiable —
  benign over-preservation. Re-run: Phase A dedups (verify + skip), Phase B executes.
- *Crash in Phase B:* SQLite rolls back — no audit rows, no deletions, GC undone; the
  store is exactly as it was; the destination still carries its verified objects
  (over-preservation again). Re-run completes idempotently.
- *Crash after COMMIT:* complete — trail rows present, governed rows gone, objects
  durable (fsynced pre-BEGIN).
- *Refusal in Phase B* (guarded delete mismatch, GC hash mismatch): whole invocation
  rolls back; destination orphans remain, disclosed; re-run re-plans against the fresh
  store state.

**Re-run idempotency is structural, not disciplinary:** the governed rows vanish from
the report once disposed (a committed archive row cannot be re-selected), and
uncommitted attempts leave nothing in the store to double-execute; destination objects
are name-addressed by content, so re-staging cannot duplicate or corrupt.

What is deliberately NOT claimed: post-commit destination HEALTH. The offline medium
can rot or be deleted after the fact; the trail proves the copy was byte-identical at
`archive_verified_at`, and `--verify-archive` (§2.5) re-proves it on demand. That is
the honest boundary between "archived, verified" and "restorable" (§2.5).

### 2.3 Audit semantics: outcome `archived`, migration v7, two-shape envelopes

- **New outcome value `'archived'`** in the code-enforced vocabulary
  (`state/dispositions.py::_OUTCOME_DELETED` gains a sibling; zero CHECKs, the chain's
  discipline).
- **Migration `v7_archive_tier.py` — additive `ALTER TABLE dispositions ADD COLUMN` ×4**
  (all nullable, NULL on delete-tier rows):

```sql
ALTER TABLE dispositions ADD COLUMN archived_artifact_id TEXT;   -- RECORD, never a live
                                                                 -- reference (see GC below)
ALTER TABLE dispositions ADD COLUMN archived_byte_length INTEGER;
ALTER TABLE dispositions ADD COLUMN archive_destination TEXT;    -- resolved target at
                                                                 -- archive time
ALTER TABLE dispositions ADD COLUMN archive_verified_at TEXT;    -- STO-1 instant the
                                                                 -- destination re-read matched
```

  ADD COLUMN rewrites no data and adds no constraint — additive in exactly the sense
  v6's index-creation on pre-existing tables already established (v6's own docstring
  widened "additive" to cover schema-object addition without data motion). No new
  table, no new index (the archived columns are never probed by the GC; the verify arm
  scans `outcome='archived'` at the same cost class as the report's full-table reads —
  disclosed, and cheap to index later if a real store shows otherwise).
- **The deleted-content digest question gets its different answer.** For a delete-tier
  row, `deleted_artifact_id` is the forensic digest of bytes that no longer exist —
  digest is all that remains. For an archived row, the bytes REMAIN (offline), and
  `archived_artifact_id` is the *binding*: the content address that the destination
  object was re-read and re-hashed against, pre-commit. Same column grammar (an
  `art-<sha256>` id), opposite epistemics: delete records what was lost; archive
  records where the survivor is and proves it matched. `deleted_artifact_id` stays
  NULL and `deleted_byte_length` 0 on archived rows (nothing was destroyed); the
  guide's column table says so.
- **Envelope two-shape rule.** `_ENVELOPE_FIELDS` (19 fields) is unchanged for
  delete-tier rows — their canonical blobs are byte-identical in shape to v6's, so
  existing recomputation and history are untouched. An archived row's envelope carries
  the 19 base fields PLUS `archived_artifact_id`, `archived_byte_length`,
  `archive_destination`, `archive_verified_at`. The rule is deterministic and
  symmetric: *archive fields are present iff `outcome == 'archived'`*. Writer and A8
  recomputation share one builder, so the shapes cannot drift; pinned by tests on both
  shapes plus a tamper arm on each archive column.
- The invocation row's `counts_json` gains `archived` (row count),
  `archive_objects_placed`, `archive_objects_deduped`, `archive_bytes_copied` (bytes
  physically written this invocation — the disk-write unit; NOT the row-bytes sum,
  which double-counts shared artifacts — the parent's units discipline extended to the
  copy side).

### 2.4 Ledger and GC: archive relieves exactly like delete

- **G3 ledger:** the capture row is deleted by the same guarded delete, so
  `used_bytes` (Σ charged over finalised rows per key) drops by exactly the archived
  capture rows' charged bytes — the identical mechanism, zero new code; pinned by an
  A4-shaped control with archive rows.
- **In-store artifact:** after the governed rows are deleted, the GC counts live
  references (`evidence.artifact_id`, `capture_staging.artifact_id`,
  `dispositions.decision_artifact_id`) — the predicate is UNCHANGED. The archived
  content artifact's in-store copy is collected once unreferenced: `archived_artifact_id`
  is a **record, never a live reference**, for the same structural reason the parent
  gave for `deleted_artifact_id` — counting it would keep every archived artifact in
  the store forever and defeat the move. The offline object is now the only copy
  (when unshared); the trail row + its decision artifact stay in the store as the
  finder's index. An artifact shared with a retained row survives in-store AND exists
  offline — correct, disclosed (sharing is a store concept; the object is the content).
- **GC byte-verification before collect applies unchanged** — and gains a
  destination-side twin in Phase A (verify-on-place), so both ends of the move verify
  bytes against content addresses.

### 2.5 Restorability: what "restorable" proves, in this slice

- **Shipped:** `benchweave dispose --verify-archive --archive-target T` (read-only,
  at-rest, holds the store like every read): for every `outcome='archived'` row, the
  object at `T/objects/<archived_artifact_id>` is present, re-hashes to its content
  address, and matches `archived_byte_length`; destination objects no trail row
  references are reported as **orphans** (the disclosed over-preservation window:
  crashed attempts, superseded runs) — reported, never deleted (deleting destination
  files is a new authority; deferral D2). Drift is named per object
  (`absent` / `digest_mismatch` / `length_mismatch`), machine-matchable output, exit
  non-zero on any drift.
- **Deferred (D1):** restore proper — putting archived bytes back into a store as
  evidence/artifacts. Trigger: the first operator restore request. The verify arm is
  restore's trust basis: a restore command will re-hash objects against trail rows
  before re-landing them, exactly as `restore` verifies a backup's manifest before
  touching the data dir.

### 2.6 Command surface and the dry run

- **Extend `dispose`** (the brief's recommended direction; it already blocks archive
  rows): `--archive-target PATH`, `--verify-archive` (mode flag; with it the command
  verifies and exits — never executes). Dry-run default preserved, and **extended to
  the destination**: without `--execute` the command writes nothing to the store AND
  nothing to the target — no objects, no manifests (AR6 snapshots both trees). The dry
  run reports the would-be archive outcomes, the resolved target, and the
  dedup/placeholder figure ("objects to place are known at execution").
- **Mixed invocations are one transaction.** A policy that mixes delete and archive
  tiers in one plan executes both in the ONE `BEGIN IMMEDIATE` window (Phase A staged
  archive objects first). A crash disposes nothing of either tier — STO-5's
  all-or-nothing, now spanning two tiers.
- **No target configured ⇒ archive rows stay `blocked_archive`** with a sharpened
  disclosure ("no --archive-target configured; pass one to archive overdue archive-tier
  rows"), and delete-tier rows in the same invocation still execute (fork F3 — the
  review-tier blocking precedent: the policy is the intent channel; the executor does
  what it can do honestly and counts what it cannot). The existing A3 pin and
  `_EXPECTED_COUNTS` remain valid verbatim as the no-target arm.

### 2.7 Disclosure and docs motion

- `cli/retention.py::_WEDGE_DISCLOSURE`: "…review-tier rows remain blocked;
  archive-tier rows move offline when dispose runs with --archive-target (verified
  content-addressed copies; the store copy is reclaimed); otherwise raise the ceiling."
  Every sentence scoped to shipped behavior.
- `cli/dispose.py`: the blocked-archive disclosure (line ~228) and
  `_IRREVERSIBLE_DISCLOSURE` (line ~84 — "recoverable disposition is the archival tier
  (unbuilt)" must change: delete stays irreversible; archive is now the recoverable
  tier, verified at copy time, restore deferred). The module docstring's archive
  paragraph rewrites.
- `cli/retention.py` module docstring: "every deletion flows through the audit trail's
  one-transaction executor" → "every deletion and archival move does".
- `docs/operator-guide.md` §7 gains the archive-tier subsection (target layout diagram,
  the over-preservation window, fsync posture, verify arm, column table with the
  record-vs-reference grammar) and the CLI reference rows; README rows move; the
  commands.py `dispose` help text gains the two flags.

## 3. Root cause / why this shape

The gap is absence by deferral, not defect: #194 sequenced audit-before-executable and
deliberately shipped `archive` as blocked because an archive target "is its own design"
(issue body). The load-bearing choices here each trace to a read fact: the
destination-with-manifest extends `backup`/`restore` (digest-manifested external trees,
verify-before-touch, M4 target cleanliness); copy-verify-commit extends the GC's
verify-before-collect and `finalise`'s cross-check (stored bytes are verified, never
trusted) to the write side of a move; one-transaction-two-tiers is STO-5's existing
shape with a second outcome; ADD COLUMN is additive by v6's own index-creation
precedent; the record-never-reference grammar for `archived_artifact_id` is the
parent's `deleted_artifact_id` reasoning verbatim; no-target-blocks is the review-tier
precedent; and the flags-only surface keeps the policy schema untouched because no
operator asked it to move.

## 4. Minimal first increment — scope and deferrals

**In:** `--archive-target` + `--verify-archive` on `dispose` (commands.py flags,
dispose model/renderer); Phase A stager (objects + manifest + fsync + typed
`archive_target:` refusals incl. data-dir containment and corrupt-preexisting-object);
migration v7 (4 nullable columns); `DispositionLog` archive path (outcome `'archived'`,
two-shape envelope builder, counts extension); GC unchanged (predicate verified
unmoved); the verify arm; disclosure/docs motion; STO-5 amendment + new STO-6;
tests (AR1–AR9 + fault arms + scale smoke). **NOT in the policy loader** (imported
untouched), `standards/`, the SDK, or any interface surface.

**Deferrals — record-carried (per the 2026-09-20 amended rule; NO follow-on tracker
issue is filed at merge: every trigger below is demand-shaped, and dormant tracker rows
are what the rule retired):**

| # | Deferred | Carrier | Reopen trigger |
|---|---|---|---|
| D1 | Restore command (archived bytes back into a store) | This record | First operator restore request; `--verify-archive` is its trust basis |
| D2 | Destination orphan reclamation (over-preservation accumulation is unbounded by design) | This record | An operator measurably hit by orphan growth (the parent's D7 analog) |
| D3 | Target topology in policy / per-bench targets / env fallback | This record | A policy author needing target configuration to travel with policy |
| D4 | Non-directory targets (tape, object storage) — the destination is a local directory | This record | An operator with a real remote target; the filesystem boundary is the abstraction seam |
| D5 | Serving-surface disposition (MCP/REST; gateway-live archival) | Parent record D2, unchanged | Unchanged — rides the interface-corpus train, never this one |
| D6 | Read-only at-rest opens (precheck→open window) | Parent record D6 / #43 row 16, unchanged | Unchanged — archive inherits the residual; guarded deletes keep the stale-plan case typed |
| D7 | Gateway-managed scheduling | Parent record D9, unchanged | Unchanged — the command stays the bounded, operator-invoked unit (A04) |

## 5. Precedent (extend, don't invent)

| Mechanism | Precedent extended |
|---|---|
| External directory + sha256 manifest, verify-before-trust | `atrest.backup`/`restore` (`_digest_tree`, manifest gate, M4 no-partial-target) |
| Durable place: temp → fsync → `os.replace` | `restore`'s staged `os.replace` swap; `hold_path`'s resolve() for path-spelling safety |
| Verify bytes against content address before acting on them | `_collect_unreferenced`'s re-hash-before-delete; `finalise`'s streaming digest cross-check |
| One `BEGIN IMMEDIATE` invocation, envelope-in-transaction, guarded deletes, invocation-row-last | `DispositionLog.execute_invocation` — extended, not restructured |
| Additive schema-object addition to an existing table | v6's indexes on `evidence`/`capture_staging`; ADD COLUMN rewrites no data |
| Record-vs-reference column grammar | `deleted_artifact_id` ("a record, never a reference") — same reasoning, archived twin |
| Blocked tier counted, never widened | review-tier blocking (`blocked_review`) + the residual `skipped` bucket |
| Test-support hooks + kill-window harness | `mid_transaction_hook` / `begin_kill_window` / `_dispose_child.py` markers |
| Caller-injected clock at the CLI boundary | `now_iso()` through `dispose_from_data_dir` — extended to `archive_verified_at` |

No new architecture: the only new durable state is four nullable columns on an existing
history table; the only new executable path composes proven ones (report plan →
digest-manifested file staging → the existing transactional writer → the existing GC).

## 6. Invariant and drift impacts

- **[STO-5] amendment**: the outcome vocabulary gains `'archived'`; an archived row's
  envelope carries the four archive fields iff its outcome is `'archived'`;
  `archived_artifact_id` is a record, never a live reference. Everything else
  (one transaction, envelope-in-transaction, guarded deletes, reference-checked GC,
  no delete path on the trail) is restated verbatim.
- **New [STO-6]** (proposed wording): an archival disposition stages every archived
  object at the destination and re-verifies it against its content address — re-read
  from the destination, fsynced — BEFORE the store transaction opens; a crash may
  leave the destination over-preserved (verified objects no committed trail row
  references), never the trail referencing bytes not verified present at the
  destination by the executing process; re-runs are idempotent (content-addressed
  objects verify-and-skip; committed rows cannot be re-selected). *Why: the offline
  filesystem is outside the SQLite transaction, so ordering — not atomicity — is what
  makes the move's crash story honest; A06's evidence-over-assertion applied to a
  filesystem claim.* Pinned by `tests/cli/test_dispose.py` + `tests/faults/`.
- **STO-3**: no amendment — `--verify-archive` rides dispose's existing hold site; the
  site list stays regenerable from `grep StoreHold( src/`.
- **STO-1** holds (`archive_verified_at` and manifest `written_at` are the
  caller-supplied `now`; no clock reads — note the verified-at instant is the plan
  instant, not a per-object measurement, disclosed like `executed_at`); **STO-2**
  unamended (uuid invocation/disposition ids; manifest names derive from them).
- **Tier 3** (on-disk schema + migration v7) → the build PR's refute runs **two
  independent adversary lanes** (the standing rule; the migration keyword
  classification fires automatically).
- **Obligation 4** (🪝): operator guide §7 + CLI reference, README.
- **Pins that move**: `test_dispose.py` gains the with-target arms (the no-target arms
  and `_EXPECTED_COUNTS` stay valid verbatim); the `_WEDGE_DISCLOSURE` and
  `_IRREVERSIBLE_DISCLOSURE` string pins move with the new text;
  `test_retention.py`'s docstring/pin sweep for the disclosure; `test_commands.py`
  unchanged (no new command).
- **CI cost**: no new jobs — plain pytest additions, one faults file extension (a
  Phase-A kill mode on the `_dispose_child.py` pattern), one bounded scale smoke
  mirroring the parent's (5,000 rows). The per-object fsync makes the archive smoke
  the slower of the two; wall time disclosed, not gated (CI hardware variance).

## 7. Measurable proof — pre-committed acceptance rule

Written before any implementation number exists. Fixture vocabulary invented
(`test_dispose.py::_seed` extended: its four archive-tier `event_log` rows plus new
archive-tier captures with shared artifacts; targets under `tmp_path`, never inside the
data dir). Every control passes with the mechanism present and FAILS when the mechanism
commit is reverted (absence arm) — a control that stays green under revert does not
test the mechanism. This rule is a floor; review-added controls meet the same standard.

- **AR1 (archive executes through the trail)**: target + overdue archive rows +
  `--execute`: audit rows with `outcome='archived'` == archived governed rows exactly
  (denominator: the plan's archive rows); every governed row gone; every archived row's
  object present at `objects/<archived_artifact_id>`, re-hash == content address,
  length == `archived_byte_length`; one invocation row. Absence arm: revert the Phase-A
  stager ⇒ typed refusal, zero dispositions, destination untouched.
- **AR2 (no-target still blocks)**: overdue archive rows, no `--archive-target`,
  `--execute`: rows SURVIVE, counted `blocked_archive`, disclosure names the missing
  target; delete-tier rows in the same invocation still execute. Absence arm: a change
  making archive executable without a target fails this pin (the old A3 semantics,
  preserved as the no-target arm).
- **AR3 (never delete-without-copy)**: a pre-existing destination object with WRONG
  bytes under a needed content address ⇒ typed `archive_target:` refusal, whole
  invocation rolled back (store tables byte-identical, governed rows present,
  destination unmodified beyond the pre-existing file). Absence arm: removing the
  pre-existing-object hash check silently overwrites ⇒ pin fails.
- **AR4 (ledger + GC)**: seeded key with archived captures: `used_bytes` drops by
  exactly Σ charged bytes of archived capture rows (denominator: that key's archived
  finalised rows); an unshared archived artifact's in-store row is collected; an
  artifact shared with a retained row survives in-store AND exists offline; decision
  artifacts never collected. Absence arm: any GC predicate change that counts
  `archived_artifact_id` as live keeps the in-store copy ⇒ the collected-count
  assertion fails.
- **AR5 (the crash story — `tests/faults/`, `begin_kill_window` pattern + a new
  Phase-A child mode)**: (a) kill mid-Phase-A (per-object marker): store byte-identical
  (no audit rows, no deletions), destination carries whole objects only
  (temp-orphan tolerated, disclosed); re-run completes with final state == one clean
  run (dedup skip counted). (b) kill inside Phase B: store rolls back completely;
  destination retains verified objects; re-run completes. (c) kill after COMMIT:
  complete; `--verify-archive` clean. Absence arm: revert the ordering (stage after
  BEGIN) ⇒ arm (a) can observe a committed trail row whose object placement was
  interrupted — the pin's state assertions go red.
- **AR6 (dry-run purity, both trees)**: dry run WITH a target: every store table
  byte-identical AND the destination tree unchanged (snapshot before/after — no
  objects, no manifests). Absence arm: Phase A running in dry-run mode fails the
  destination snapshot.
- **AR7 (verify arm)**: clean destination ⇒ every archived row verified, zero drift;
  flip one object byte ⇒ named `digest_mismatch`; delete one object ⇒ named `absent`;
  plant an orphan object ⇒ reported as orphan, NOT deleted, exit 0 (orphan is not
  drift). Absence arm: a verify that trusts `archived_byte_length` without re-hashing
  passes the flipped byte ⇒ pin fails.
- **AR8 (envelope exactness, both shapes)**: recomputation over delete rows matches
  v6's shape byte-for-byte (19 fields); over archive rows matches the 23-field shape;
  tampering any archive column (row or artifact bytes) is detected. Absence arm:
  removing the two-shape rule from either writer or recompute fails the shape/count
  assertions.
- **AR9 (plan parity successor)**: the dry-run plan's archive-outcome rows ==
  `build_retention_report`'s `scheduled ∧ overdue ∧ on_disposition=archive` rows —
  same ids, same matched-rule identity. Absence arm: any second derivation in the
  executor shows as drift.
- **Scale smoke**: 5,000 overdue archive rows across ≥3 context keys (the parent's
  synthetic generator; distinct artifacts, 8–11 byte payloads): `--execute` completes
  with audit rows == archived == 5,000 exactly, objects == distinct artifacts exactly,
  and an immediate RE-RUN is a full no-op (0 selected rows, 0 objects placed — the
  idempotency claim measured, not asserted). Wall time disclosed (fsync-bound), never
  gated.

**SHIP iff** AR1–AR9 all pass with absence arms red-under-revert (counts exact,
denominators named). **KILL if** any structural arm is unachievable — specifically:
the copy-verify ordering cannot be made refusal-clean (it can: it is ordinary file I/O
+ hashing with typed failures), destination idempotency cannot be made deterministic
(it can: content addressing), or the two-shape envelope cannot be pinned without
touching v6 history (it can: the builder is shared and delete rows keep the 19-field
shape). **UNDERPOWERED, not conclusive, if** the fault arms cannot kill reliably
inside the Phase-A window on CI hardware — widen the per-object marker protocol and
re-run on a quiet host; the count invariants gate either way.

## 8. Top risks and falsifiers

| Risk | Falsifier / mitigation |
|---|---|
| The trail asserts preservation the destination later betrays (media rot, operator deletion post-commit) | Disclosed boundary (§2.2): the trail proves the copy at `archive_verified_at`; `--verify-archive` re-proves on demand; D1's restore re-verifies before re-landing. If an operator needs continuous destination health, that is D2/D4 territory — measured demand, not speculation |
| Power loss between destination fsync and COMMIT leaves orphans; between COMMIT and… nothing (ordering forbids it) | AR5's three windows pin the state machine; the orphan disclosure names the window in the guide |
| A shared artifact archived from one row, still referenced by another ⇒ two copies, operator confusion | Disclosed (sharing is a store concept); AR4's shared-survival arm pins the behavior |
| Per-object fsync cost at scale | The smoke measures it; if a real store shows pathologic cost, batching fsyncs (fdatasync, one dir sync) is an amendment with its own measurement — not pre-optimized here |
| The ADD COLUMN choice ages badly if archive rows need richer per-object state | The verify arm and envelope tolerate the four columns; anything richer (per-object verification history) is D2's train — a new table then, joined by disposition_id |
| `blocked_archive`-without-target surprises an operator expecting motion | The disclosure names the missing flag in the output AND the guide; AR2 pins the count; the no-target behavior is byte-identical to today's |
| Wedge-disclosure text overclaims the tier | Every sentence scoped to shipped behavior (§2.7); review walks it against AR2/AR7 outcomes — the parent's §2.5 discipline |
| Destination on the same filesystem as the store: "offline" is then a lie of placement | Not policed in slice 1 (an operator may legitimately stage before rotation); the data-dir CONTAINMENT refusal covers the structurally wrong case (restore swap); same-fs-but-outside is disclosed as the operator's positioning choice |

## 9. Forks for the owner

1. **F1 — destination layout**: shared `objects/` pool + per-invocation manifests
   (recommended: content-addressed dedup makes re-runs and shared artifacts free;
   extends the backup manifest precedent) vs per-invocation `archive-<iso>/` bundles
   (backup-literal, no dedup, simpler visual isolation).
2. **F2 — target configuration**: `--archive-target` flag only (recommended: the
   policy stays the intent channel; write-path config as explicit as `--policy`; zero
   policy-schema churn) vs a policy-file field (target topology travels with policy;
   schema + validation motion, and deployment config embedded in intent documents).
3. **F3 — no-target behavior**: block with counts and proceed with delete-tier rows
   (recommended: the review-tier precedent; mixed invocations stay useful; behavior
   byte-identical to today for archive rows) vs a typed refusal of the whole invocation
   (stricter, but punishes delete-tier rows for an archive-config gap).
4. **F4 — restore scope**: verification-only now, restore deferred on the first
   operator request (recommended: verify is restore's trust basis; no demand exists —
   the trigger honesty section cuts both ways) vs a restore command in this increment
   (scope growth against zero demand).

Recommendations 1/2/3/4 as marked; all four are cheap to reverse before the build
starts and expensive after.

## 11. Review fold — the fix wave (2026-09-25)

Three refute lanes reviewed the built increment; the owner folded six MEDIUM
findings and six LOW/NIT rows into one wave. Every fix landed RED-first, one
commit per fix, gates after every commit. This section is the disposition
record (the #194 precedent's fold shape); it also records the deviations the
build commits disclosed, and corrects two of this record's own claims that
did not survive contact with the code as built.

### 11.1 MEDIUM findings (all FIXED)

| # | Finding | Disposition |
|---|---|---|
| F-1 | FSYNC CHAIN (critic#1 + laneB#1, converged): `target/` and its parent were never fsynced after `mkdir(parents=True)` — only `objects/`, the manifest file, and `manifests/` were. An unfsynced new directory entry can vanish with its subtree on power loss, orphaning the objects the committed trail references. | FIXED: `_resolve_archive_target(create=True)` fsyncs the leaf directories, every ancestor mkdir had to create, and the parent. Pinned by an os.fsync/os.open spy over a real first invocation (RED: target and parent absent from the fsynced set). |
| F-2 | LAUNDERED DURABILITY ERRORS (critic#2): `_fsync_dir` swallowed every OSError — an EIO on the durability path committed anyway. | FIXED: PermissionError on the open stays the documented Windows no-op; every other failure on open or fsync propagates as a typed `archive_target:` refusal. Pinned by an injected EIO at the objects-dir fsync (RED: DID NOT RAISE; the invocation committed). |
| F-3 | VERIFY READ ONE FLAG (critic#3): verify scanned every archived row against the single passed `--archive-target` while `archive_destination` was write-only — a second target made every earlier row read as drift. | FIXED: verify resolves each row's RECORDED `archive_destination` (the column existed for this); the flag is only a fallback for rows lacking one. Relocation reads as `absent` at the recorded path. The `--verify-archive requires --archive-target` mode refusal was removed (verify-without-flag is the honest default). Pinned by a two-target + relocation test (RED: the old typed refusal fired). |
| F-4 | NON-STREAMING STAGER (laneB#2, measured 4×34MB → 168MB peak): the stager materialized Σ payloads. | FIXED: streaming — ids first, then one payload at a time (fetch, place, release), all hashing in 1 MiB blocks (`_hash_file`); the same invocation's GC path also stopped double-copying and pinning fetch tuples across iterations (its phase peak alone was 16MB on two 8MB artifacts). Pinned by a tracemalloc ceiling (12MB) over a two-8MB-artifact archive (RED: 27.8MB); the one-time policy-schema compile is warmed outside the measured window so the ceiling isolates the per-payload bound. Guide discloses the bound. |
| F-5 | NULL-ARTIFACT ROWS ARCHIVED TO NOTHING (laneA F1): an evidence row with `artifact_id=None` was destroyed with no offline copy and verify passed it silently. | FIXED: typed refusal when an archive-tier plan row references no artifact — before anything is staged; the verify arm COUNTS binding-less rows as skipped with `clean=False`, naming them. Pinned by the lane's `put_evidence(kind, ref, None)` repro plus a rogue SQL-inserted archived row (RED: DID NOT RAISE; the row was destroyed). |
| F-6 | BINDING READ PRE-TRANSACTION (laneA F2): the archive binding came from a pre-Phase-A read while the delete tier binds in-transaction — a rogue non-flock writer repointing a row's artifact between Phase A and B committed a trail row over never-verified bytes while the GC destroyed the real content. | FIXED in two halves: the stager returns the per-row bindings AS READ AT ENTRY (the bindings whose bytes were staged) and the envelope records THOSE — the previous post-staging re-read could itself observe the rogue repoint; and `execute_invocation`'s archived branch reconciles the binding against the single in-transaction `_current_row` read, refusing typed (`StoreChangedUnderPlan`) on mismatch. Pinned by the lane's stage_hook(0) repoint repro (RED: DID NOT RAISE; both artifacts and the governed row survive the refusal). |

### 11.2 LOW/NIT rows (owner fold; all addressed)

| # | Row | Disposition |
|---|---|---|
| R1 | Empty/`.` `--archive-target` silently archived into the CWD. | FIXED: typed refusal (a target normalizing to `Path('.')`); an operator naming the CWD on purpose can pass an absolute path. RED: the lane's repro exited 0. |
| R2 | Symlinked destination objects were followed (hash-correct links deduped) in the stager AND verify; an object appearing between the two passes was `os.replace`d unchecked. | FIXED: `_verify_preexisting` is the one discipline for any existing entry — symlink refuses typed (hash-correct or not), wrong bytes refuse typed — used by pass 1 AND pass 2's late-appearing branch; verify refuses symlinked objects typed too. RED: both lane repros DID NOT RAISE. |
| R3 | The 23-field envelope shape had no freeze rule. | PINNED (no production change — the freeze was already structural): appending a dummy 24th field makes the writer's blob construction fail loudly (KeyError — the field-set tuple and the envelope construction must move together), and a drifted row written any other way fails A8's independent recomputation. RULE: a future v8 must version or migrate the shape, never silently append. |
| R4 | The manifest's no-consumer status was implicit. | DOCS: the guide states it explicitly — the trail row is the commitment record and the machine-read authority; the manifest is an operator-facing index; under total store loss it is the only surviving index, and that asymmetry is named. The zero-object-re-run-writes-no-manifest behavior is documented, not just a test message. |
| R6 | `archive_verified_at` vs mtime confusion risk. | DOCS: the guide discloses that `archive_verified_at` is the invocation's plan instant (one caller-supplied `now`) and object mtimes can land on either side of it — mtime-vs-verified_at is not a valid forensic ordering signal. |
| R7 | `--verify-archive --json --out <file>` ignored `--out`. | FIXED: the verify branch writes through the same `_write_out` path (json and markdown), writing the file even on drift — the report is the evidence, the exit code is the verdict. RED: the report file was never written. |

### 11.3 Build deviations, recorded properly (previously only in commit messages)

1. **Two-pass stager** (§2.2 described a single per-artifact loop): AR3's
   pre-committed "destination unmodified beyond the pre-existing file" forces
   verifying all pre-existing destination objects BEFORE placing any. R2 later
   extended pass 2 with the same discipline for late-appearing entries.
2. **Zero-object re-runs write no manifest**: manifests ride the staging pass
   and describe the objects it placed; the store's invocation row is the
   no-op's record (documented in the guide since R4).
3. **Both-tier byte figures**: `bytes_reclaimed` and `charged_ledger_bytes`
   cover delete AND archive rows — §2.4's "archive relieves exactly like
   delete" made total. No-archive fixtures are unchanged (the archive sums are
   zero).
4. **`length_mismatch` scope**: it can only fire alone via trail tampering
   over intact bytes — content addressing makes object-side length-only drift
   unrepresentable (digest precedence in the verify arm).
5. **Model honesty on no-op re-runs**: an executed invocation WITH a target
   reports measured copy figures (zeros), never the dry-run `None`
   placeholder — the idempotency claim is measured (caught by the scale
   smoke's re-run arm: `assert None == 0`).

### 11.4 Corrections to this record's own claims (laneA F3)

§2.6 and §6 claim the no-target arm stays "byte-identical to today" and that
"`_EXPECTED_COUNTS` remain[s] valid verbatim". As built, both are false in a
narrow, additive sense and are corrected here:

- the model's outcome vocabulary gained `archived` (an additive count key —
  `_EXPECTED_COUNTS` gained `"archived": 0`, without which the dict-equality
  pin could not hold); with no target every count VALUE is unchanged, and the
  four `blocked_archive` fixture rows still survive, counted, disclosed;
- the invocation row's `counts_json` gained four keys on EVERY invocation,
  including delete-only ones (`archived`, `archive_objects_placed`,
  `archive_objects_deduped`, `archive_bytes_copied` — zeros when nothing was
  archived). Delete-only envelopes and audit-row SHAPES are untouched
  (two-shape rule); the counts extension is additive JSON, not a shape change.

The honest statement: the no-target BEHAVIOR (rows survive, counted,
disclosed; delete tier proceeds; nothing written anywhere) is byte-identical;
the no-target OUTPUT is additive-superset, not byte-identical.

### 11.5 Post-wave state

All six MEDIUM findings and all six LOW/NIT rows fixed or pinned; gates green
after every commit (ruff, bare mypy, focused pytest + tests/faults); the
acceptance controls from §7 all still pass with their absence arms. Scale
smoke (5,000 archive rows, streaming stager): wall time disclosed in the
final report, never gated.
