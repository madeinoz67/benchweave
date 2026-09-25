# Disposition audit trail + audited delete-tier disposition (issue #194)

**Date:** 2026-09-25 · **Issue:** [#194](https://github.com/madeinoz67/benchweave/issues/194)
(carries #43 design-of-record deferral row 3, opened at slice-3 merge exactly as the
discipline names it)
**Verdict:** BUILD-minimal — the audit trail plus a delete-only disposition executor with
review/archive blocking. The archival tier is NOT built (deferral D1, the one follow-on
issue). No standards byte moves; no serving-surface operation is added.
**Train surfaces:** `control/retention_policy.py`, `cli/retention.py`, new `cli/dispose.py`
+ `state/dispositions.py`, `state/migrations/`, operator docs/README, tests. Nothing in
`standards/`, the SDK submodule, or gateway capture surfaces (the #176 promotion owns
those).

## 0. Grounding (read before designing — citations from main at `bebf5d9`+)

- `src/benchweave/control/retention_policy.py` — the validated policy object:
  `resolve_origin` (bench class → bench default → global class → global default, naming
  the winning entry), `on_disposition` ∈ {delete, archive, review} as a report label,
  `hold`, `retain_after` ∈ {landing, run_end} (`last_access` refuses at load), the
  exact-byte decode, `MAX_DURATION_S`.
- `src/benchweave/cli/retention.py` — the pure projection. `_disposal_row` emits the full
  matched-rule identity (`matched_selector`/`matched_scope`/`matched_rule`, anchor,
  `disposal_date`, honest statuses `ungoverned|held|anchor_unresolved|scheduled`,
  `overdue`). `retention_from_data_dir` (line 1158) is the at-rest wrapper:
  `StoreHold` → `_refuse_schema_mismatch` (line 1064, the fork-A never-migrate precheck)
  → `Store.open` → `build_retention_report`. The wedge disclosure constant
  `_WEDGE_DISCLOSURE` (line 142) still names the audit-trail slice as future remediation.
- `src/benchweave/state/store.py` — single-writer SQLite (WAL, `synchronous=FULL`),
  caller-supplied timestamps (STO-1), migrations one-`BEGIN IMMEDIATE`-each with the
  refuse-newer guard, `begin_kill_window` (the sanctioned fault-injection window), and
  the guarded-transition precedent `_close_lease`: exact-row `UPDATE ... WHERE state =
  'active'` + rowcount check.
- `src/benchweave/state/migrations/` — registry `MIGRATIONS` tuple
  (`state/migrations/__init__.py`); v5 (`v5_capture_staging.py`) is the additive-migration
  precedent and pins the chain's zero-CHECK, code-enforced-vocabulary discipline.
- `src/benchweave/content/capture_store.py` — the staged writer. `finalise` publishes the
  content-addressed artifact **inside the same transaction** as the staging flip
  ("The artifact row joins this transaction (same connection)") — the direct precedent
  for audit-payload artifacts joining the disposition transaction. `used_bytes` is the
  G3 ledger read (Σ reserved staged + Σ charged finalised per context key). Only the
  abort/sweep paths delete staging rows today; no path deletes a finalised row or an
  evidence row.
- `src/benchweave/content/store.py` — `put_artifact` (content-addressed
  `INSERT OR REPLACE`), `put_evidence` (`ev-` + uuid, `content_ref` carrying the digest):
  the evidence-exactness mechanism this design mirrors for audit records.
- `src/benchweave/cli/atrest.py` + `src/benchweave/state/hold.py` — the at-rest command
  family (setup/backup/restore/verify) and the exclusive sibling-file `flock`; the
  crash-release property; label convention `"retention pid {os.getpid()}"`.
- `src/benchweave/interfaces/operations.py::append_bench_event` — considered and
  rejected as the audit-trail home: bench event streams are **trimmed by design**
  (`trim_stream`, surfaced as `cursor_expired`), so an audit trail riding them would be
  deletable by the very retention machinery it audits. The `changes` table was also
  rejected (bench-scoped admin workflow with generation fences — wrong shape).
- `tests/cli/test_retention.py` — the S3 controls; S3-1 pins "slice 3 writes nothing
  back over all fifteen tables" (the store currently carries exactly fifteen tables).
- `docs/smart-test-gateway-decisions.md` A04 (no silent promotion to autonomous
  execution; bounded, pre-declared authority), A06 (evidence over assertion), A07 (audit
  failure constrains new work). `docs/internal/invariants.md` STO-1..4, CON-1..13.
- `docs/internal/drift-and-obligations.md` — obligations 4 (CLI behavior → operator
  guide CLI reference + README) and the Tier-3/two-lane-adversary standing rule.
- #43 design of record Decision 8 (sequencing invariant; report-first; the wedge
  disclosure) and deferral rows 3, 7, 12, 15, 16.

## 1. The problem, evidenced

Slice 3 shipped disposal as a **report row**. The operator surface now discloses the
quota wedge live (`over_ceiling`/`at_ceiling` + time-to-exhaustion), and the disclosure
tells the operator the truth: hold-heavy exhaustion hard-blocks G3 with **no deletion
path** — remediation is manual (raise the ceiling) until disposition is auditable
(`cli/retention.py` `_WEDGE_DISCLOSURE`). No in-tree path deletes a finalised
`capture_staging` row or an `evidence` row; the ledger (`used_bytes`) therefore never
shrinks for finalised data. The wedge is real, visible, and named. This increment is the
audited path that relieves it, exactly as Decision 8's sequencing invariant requires:
audit trail first, then — and only through it — deletion.

## 2. The mechanism

### 2.1 The audit trail: two additive tables (migration v6)

`state/migrations/v6_dispositions.py`, purely additive, `IF NOT EXISTS`, zero CHECKs
(code-enforced vocabulary, the v5 discipline):

```sql
CREATE TABLE IF NOT EXISTS disposition_invocations (
  invocation_id TEXT PRIMARY KEY,      -- 'dsp-inv-' + uuid4 hex
  invoked_at    TEXT NOT NULL,         -- caller-supplied now (STO-1)
  actor         TEXT NOT NULL,         -- the StoreHold label ('dispose pid N')
  policy_path   TEXT NOT NULL,
  policy_sha256 TEXT NOT NULL,         -- digest of the exact governing policy bytes
  bench_filter  TEXT,                  -- NULL = unscoped
  counts_json   TEXT NOT NULL          -- per-outcome counts + bytes reclaimed
)
CREATE TABLE IF NOT EXISTS dispositions (
  disposition_id       TEXT PRIMARY KEY,   -- 'dsp-' + uuid4 hex (contract id shape)
  invocation_id        TEXT NOT NULL,
  row_kind             TEXT NOT NULL,      -- 'capture' | 'evidence'
  target_id            TEXT NOT NULL,      -- capture_id | evidence_id
  context_key          TEXT,
  bench                TEXT,
  data_class           TEXT NOT NULL,
  matched_selector     TEXT,               -- the report row's identity, verbatim
  matched_scope        TEXT NOT NULL,
  matched_rule         TEXT NOT NULL,
  on_disposition       TEXT NOT NULL,      -- 'delete' (only executable tier)
  anchor_kind          TEXT NOT NULL,
  anchor_at            TEXT,
  disposal_date        TEXT NOT NULL,
  bytes                INTEGER NOT NULL,   -- the report row's bytes figure
  deleted_artifact_id  TEXT,               -- HISTORICAL record: digest-bearing id of
  deleted_byte_length  INTEGER,            --   the deleted content (not a live ref)
  decision_artifact_id TEXT NOT NULL,      -- LIVE reference: the audit envelope
  decision_sha256      TEXT NOT NULL,      -- canonical-JSON digest of the envelope
  executed_at          TEXT NOT NULL,
  outcome              TEXT NOT NULL       -- 'deleted'
)
CREATE INDEX IF NOT EXISTS idx_dispositions_target ON dispositions (row_kind, target_id)
```

**Evidence-exactness (the issue's done-means item):** every audit row's full decision
envelope — all identity fields above plus `invocation_id`, `executed_at`, `outcome` — is
serialized with the store's canonical form (`json.dumps(..., sort_keys=True)`) and
content-addressed through the existing `ContentStore.put_artifact` **inside the
disposition transaction** (the `finalise` precedent: the artifact row joins the
transaction). `decision_sha256` must equal both the recomputed canonical digest and the
digest embedded in `decision_artifact_id` (`art-<sha256>`). The trail is therefore
verifiable with the same mechanism that makes evidence verifiable, and
`deleted_artifact_id` preserves the **digest of the deleted bytes** — the forensic
"what was deleted" proof — without retaining the bytes (delete reclaims space; it is not
a backup; disclosed in the guide).

**Historical-record vs live-reference (the one subtle correctness point):**
`deleted_artifact_id` is a record, NOT a reference — artifact garbage collection counts
only live references (`evidence.artifact_id`, `capture_staging.artifact_id`,
`dispositions.decision_artifact_id`). Counting the historical column would keep every
deleted artifact alive forever and defeat reclamation.

**No delete path:** the dispositions tables are history, never deleted — the
`leases`/`changes` precedent (`list_leases`: "leases are history, never deleted"). The
audit trail must not be governed by the policy it audits (self-reference); its growth is
bounded by disposition activity and disclosed (deferral D7).

### 2.2 The executor: one transaction, audit-then-delete, guarded rows

New `state/dispositions.py` — a `DispositionLog` writer class over `Store` (the
`CaptureStagingStore` layering precedent), plus the executor in `cli/dispose.py`. The
command flow, mirroring `retention_from_data_dir` line by line (fold-wave correction:
the policy load is FIRST, before the hold — as built and as `retention_from_data_dir`
itself orders it; the original numbered list here had the hold first, which described
the flow inverted):

1. Policy load through `load_retention_policy` — **imported, never re-implemented**
   (issue constraint (d)). New in this train: `load_retention_policy_with_digest(path)
   -> tuple[RetentionPolicy, str]`, refactoring the existing loader so the digest comes
   from the SAME single `path.read_bytes()` (zero TOCTOU drift by construction); the old
   name delegates. **No policy file ⇒ typed refusal** — disposition never runs
   ungoverned, and explicit configuration is never silently substituted.
2. `StoreHold(db, label=f"dispose pid {os.getpid()}")` — refuses naming the holder while
   a live gateway owns the store (STO-3; disposition runs in a maintenance window).
3. `refuse_schema_mismatch(db)` — promoted from `_refuse_schema_mismatch` to a public
   name in `cli/retention.py` and imported (never duplicated). **Dispose never
   migrates**: a store missing v6 refuses typed with the fork-A wording ("open it once
   with a current gateway (setup/serve/report) to upgrade, then retry"). This is
   deliberately stricter than `report` (which applies pending migrations on open — #43
   record row 15 carries that known family inconsistency).
4. Plan = `build_retention_report(store, policy=..., bench_id=..., now=...)` — the
   report builder itself, so selection, scoping (`_in_scope`'s never-vanish rule),
   resolution semantics, matched-rule identity and honest statuses are the slice-3
   contract with **zero formula drift** (pinned mechanically by acceptance control A9).
   Executable set: rows with `status == "scheduled" AND overdue AND on_disposition ==
   "delete"`. Everything else is counted and disclosed, never executed:
   `review` → `blocked_review`; `archive` → `blocked_archive` (the archival tier does
   not exist — an archive row falling through to delete would be the worst lie this
   command could tell); `held`/`anchor_unresolved`/not-yet-overdue → skipped.
5. **Execution = ONE `BEGIN IMMEDIATE` transaction for the whole invocation** (the
   single-writer discipline; all-or-nothing — a crash disposes nothing and a re-run
   re-plans cleanly, since deleted rows simply vanish from the report):
   insert the invocation row → for each selected row: insert the audit row (envelope
   artifact via `put_artifact` joins the transaction) and issue a **guarded delete**
   (`DELETE FROM evidence WHERE evidence_id = ? AND kind = ? AND stored_at = ?` /
   `DELETE FROM capture_staging WHERE capture_id = ? AND state = 'finalised' AND
   updated_at = ?`; `rowcount != 1` ⇒ ROLLBACK with a typed
   `store changed under the plan` refusal — the `_close_lease` exact-row precedent)
   → collect dropped artifact ids → GC artifacts whose live references are all gone
   (predicate of §2.1) → update nothing else → COMMIT.

   "Auditable before executable" is therefore **structural, not disciplinary**: the audit
   record and the deletion commit in one SQLite transaction, so a committed deletion
   without its audit row is unrepresentable. This is A07's shape applied to disposal:
   if the audit write fails, the action does not happen.

6. Timestamps are caller-supplied end to end (`dispose_from_data_dir(..., now: str)` —
   the CLI passes `now_iso()` exactly as the retention command does; STO-1 unamended,
   no store clock reads, no new sequence authority — uuid ids, the evidence precedent).

### 2.3 The command surface

`benchweave dispose` (separate subcommand — fork F1) with `--data-dir`, `--policy`,
   `--bench`, `--out`/`--json` (the retention flag family) and:

- **Default = plan (dry run): writes nothing** — all seventeen tables byte-identical
  (control A7 extends S3-1's census, regenerated from `sqlite_master`, not the literal
  fifteen). `--execute` is required to dispose (fork F2: a destructive at-rest command
  requires the explicit opt-in; the report remains the plan surface).

Output: the plan/outcome per row with matched-rule identity (the report row fields),
per-outcome counts, bytes reclaimed, the artifact-GC count, and the disclosures —
including the review/archive blocks and the delete-is-irreversible-digest-retained
sentence.

### 2.4 Review-tier blocking and the archival verdict

- `review` rows are **never executed** — the policy is the operator's intent channel, and
  moving a row out of review is a policy edit (a per-row override channel is a new
  authority surface — deferral D4). Blocked rows are counted in the invocation summary.
- `archive` rows are **blocked, never deleted**, with `blocked_archive` counts and a
  disclosure naming the archival tier as unbuilt (D1). This is the honest interim: the
  schema admits archive, the executor refuses to interpret it as delete.

### 2.5 The wedge disclosure motion (issue done-means item 4)

`_WEDGE_DISCLOSURE` in `cli/retention.py` and the operator guide/README retention text
change to: the audited disposition path now exists (`benchweave dispose`) — delete-tier
rules reclaim bytes and G3 ledger when run under the store hold; review- and
archive-tier rows remain blocked (archival tier unbuilt); or raise the ceiling. The
`retention.py` module docstring's sequencing sentence is amended to name `dispose` as
the audited path it was waiting for. Every claim in the new text is scoped to what this
increment ships.

## 3. Root cause / why this shape

The defect this increment closes is absence, not breakage: Decision 8 sequenced
disposition behind an audit trail that did not exist, leaving the disclosed wedge with
no remediation. The design's load-bearing choices each trace to a read fact:
audit-records-as-artifacts (the `finalise` transaction precedent + `put_evidence`'s
digest model), one-transaction-per-invocation atomicity (single-writer + all-or-nothing
crash story), guarded deletes (`_close_lease`), never-migrate (fork A), flock window
(STO-3 at-rest family), report-builder-as-plan (zero drift, constraint (e)), and
blocked archive (a label must never widen into a harder action than it names).

## 4. Minimal first increment — scope and deferrals

**In:** migration v6 (two tables + index); `load_retention_policy_with_digest` refactor;
`refuse_schema_mismatch` promotion; `state/dispositions.py` (transactional writer +
GC predicate); `cli/dispose.py` + command registration (dry-run default, `--execute`);
`_WEDGE_DISCLOSURE` + module-docstring amendment; operator guide (retention section +
CLI reference) and README rows; tests (below); STO-3 amendment + new STO-5 in
`docs/internal/invariants.md`.

**Out — each deferral names its carrier and reopen trigger** (deferrals live in this
record's table per the 2026-09-20 amended rule; one tracker issue maximum):

| # | Deferred | Carrier | Reopen trigger |
|---|---|---|---|
| D1 | Archival tier (offline-storage disposition target, byte-preserving) | The one follow-on issue opened at merge (the #194 bundle already names it a candidate) | The first operator who needs `on_disposition: archive` to actually archive (a policy author with a real offline target), or a wedge case where delete is unacceptable |
| D2 | Serving-surface disposition (MCP/REST operation; gateway-live execution) | This record | An operator needing disposition without a gateway stop — rides the interface-corpus train (CON-3/obligation 1), never this train; coordination note: any standards-side motion belongs to the #176-promotion lane |
| D3 | Operator-facing audit verification (`dispose --verify`) | This record | First operator audit/export request; tests pin the recomputation now (A8) |
| D4 | Per-row override channel (disposing a review-tier row without a policy edit) | This record | Operator friction showing policy-edit-only is unusable — a new authority surface needing its own design |
| D5 | `retain_after: last_access` (store access-time column backfill) | Unchanged: #43 record row 12 | Unchanged: the first policy author needing it |
| D6 | Read-only at-rest opens (structural fix for the precheck→open window) | Unchanged: #43 record row 16 | Unchanged: a real hostile/broken concurrent writer; dispose inherits the disclosed residual and the guarded deletes make the stale-plan case a typed refusal |
| D7 | Audit-trail self-retention (its growth is unbounded by design — the leases/changes history posture) | This record | An operator measurably hit by audit-payload growth at scale; a self-governed audit policy is inherently self-referential and gets its own record |
| D8 | `report`'s migration-on-open alignment with the never-migrate family | Unchanged: #43 record row 15 | Unchanged; dispose chooses the stricter posture and the inconsistency stays row 15's to carry |
| D9 | Gateway-managed scheduling of disposition | This record (operator-side cron/systemd needs nothing from us — the command is the bounded, operator-invoked unit, A04) | An operator wanting gateway-side scheduling → folds into D2's serving-surface train |

## 5. Precedent (extend, don't invent)

| Mechanism | Precedent extended |
|---|---|
| Audit envelope as content-addressed artifact inside the write transaction | `CaptureStagingStore.finalise` — "the artifact row joins this transaction"; `put_evidence`'s artifact + digest-ref model |
| Append-only history tables, no delete path | `leases` ("history, never deleted"), `changes` |
| One `BEGIN IMMEDIATE` transaction, guarded exact-row mutations with rowcount checks | `_close_lease`, `next_lease`, every store write |
| At-rest command wrapper: hold → typed precheck → open → act | `retention_from_data_dir` (the never-migrate arms), `backup`/`restore` (the mutating arms) |
| Plan derived from the existing report model | `build_retention_report` called as-is (constraint (e): import `control/retention_policy.py`; never re-implement — here generalized to the whole row model) |
| Additive migration, code-enforced vocabulary, uuid ids | v5 `capture_staging`, `ev-` evidence ids |
| Caller-injected clock at the CLI boundary | `retention_lib.now_iso()` in `commands.py::retention` |

No new architecture: the only new durable state is two tables whose shapes mirror
existing history tables, and the only new executable path composes three proven ones
(report → guarded transactional writer → at-rest wrapper).

## 6. Invariant and drift impacts

- **New [STO-5]** (proposed wording for `docs/internal/invariants.md`): every disposition
  execution is ONE `BEGIN IMMEDIATE` transaction carrying its complete audit record —
  invocation row, one audit row per disposed governed row (canonical-JSON envelope
  content-addressed through `put_artifact`, digest pinned in the row), the guarded
  deletions, and reference-checked artifact GC (live references: `evidence`,
  `capture_staging`, `dispositions.decision_artifact_id` — historical
  `deleted_artifact_id` is a record, never a reference); a committed deletion without
  its audit row is unrepresentable; `review`- and `archive`-tier rows are never deleted;
  the dispositions tables have no delete path. *Why: Decision 8's sequencing invariant
  and A07 made structural — audit capacity is not a dependent of the action, it is the
  action's transaction.* Pinned by `tests/cli/test_dispose.py` + `tests/faults/`.
- **[STO-3] amendment**: the at-rest family list ("backup, restore") is already stale
  (retention shipped holding the flock) — amend to name the family: backup, restore,
  retention (report, read-only), dispose (write). Evidence: `retention.py:1196`.
- **STO-1** holds (caller-supplied `now` throughout); **STO-2** not extended (uuid ids,
  no new sequence authority); CTL/CON/REG untouched — no corpus byte, no interface
  operation, no SDK surface (CON-3/CON-5 untouched; obligations 1/2/6/7/8 not triggered).
- **Tier 3** (on-disk schema + migration) → the build PR's refute runs **two independent
  adversary lanes** per the standing rule; the migration-sha256/hashlib keyword rule
  will classify it Tier 3 automatically.
- **Obligation 4** (🪝): operator guide CLI reference + retention section, README.
- **Pins that move**: `tests/cli/test_retention.py` S3-1's table census (fifteen →
  seventeen, regenerated from `sqlite_master` rather than the literal);
  `tests/control/test_retention_policy.py` gains the digest-refactor arm; the
  `_WEDGE_DISCLOSURE` string is asserted verbatim somewhere in the slice-3 suite and
  moves with the new text.
- **CI cost**: plain pytest + one faults arm + one bounded scale smoke (~5,000 rows —
  the read-side baseline is 0.67 s at 20,500 rows from the #193 measurement; writes are
  heavier but the smoke stays in-suite). No new jobs.

## 7. Measurable proof — pre-committed acceptance rule

Written before any implementation number exists. Fixture vocabulary is invented (the
`test_retention.py` `_seed` pattern: two benches, terminal + live runs, finalised
captures at three context keys including a byte-identical pair, shared artifacts,
event_log evidence, unattributed keys). Every control must pass with the mechanism
present and **fail when the mechanism commit is reverted** (absence arm) — a control
that stays green under revert does not test the mechanism and must be fixed before
merge. This rule is a floor; review-added controls meet the same standard.

- **A1 (audit atomicity)**: after `--execute`, #audit rows == #deleted governed rows,
  exactly one invocation row, every deleted target has its audit row, and the audit
  envelope digests recompute (triple check of §2.1). Absence arm: revert the audit-insert
  statements → the count assertions go red (deletion-without-audit is what they exist to
  catch). Fault arm (`tests/faults/`, the `begin_kill_window` harness pattern): process
  death mid-transaction leaves NEITHER audit rows NOR deletions after reopen.
- **A2 (review blocks)**: overdue `review` rows present after `--execute`, counted
  `blocked_review`. Absence arm: a change making review executable fails this pin.
- **A3 (archive never deletes)**: overdue `archive` rows present after `--execute`,
  counted `blocked_archive`, disclosed in output. Absence arm: the archive-falls-through-
  to-delete bug is exactly what this pin kills.
- **A4 (ledger relief — the wedge remediation, measured)**: seeded at/over-ceiling
  context key; after `--execute`, `CaptureStagingStore.used_bytes(key)` drops by exactly
  Σ `charged_bytes` of that key's deleted capture rows (denominator: the key's deleted
  finalised rows), and the G3 allowance formula recovers headroom. Absence arm: with
  disposition reverted, no path shrinks the finalised ledger (asserted directly).
- **A5 (GC reference-check)**: an artifact shared by a retained row survives; a fully
  unreferenced artifact is collected exactly once; decision artifacts are never
  collected. Absence arm: removing the reference predicate deletes the shared artifact
  → pin fails.
- **A6 (refusals)**: store missing v6 → typed `retention_store:`-family refusal naming
  the upgrade path; held store → `StoreHeldError` naming the holder; no policy file →
  typed refusal (never a silent no-op); explicit-but-invalid policy → `retention_policy:`
  refusal.
- **A7 (dry-run purity)**: without `--execute`, every table in `sqlite_master`
  byte-identical before/after (S3-1's method, census regenerated).
- **A8 (evidence-exactness + tamper arm)**: recompute over every audit row matches;
  flipping one identity field in a row (or in its artifact bytes) is detected by the
  digest comparison.
- **A9 (plan parity — the import-not-re-implement pin)**: the dry-run plan's rows equal
  `build_retention_report`'s `scheduled ∧ overdue ∧ on_disposition=delete` rows — same
  ids, same matched-rule identity fields. Absence arm: any second derivation in the
  executor shows here as drift.
- **Scale smoke**: 5,000 governed overdue rows across ≥3 context keys via the synthetic
  generator pattern — `--execute` completes with audit rows == deleted == 5,000 exactly
  and bytes reclaimed == Σ row bytes exactly. Wall time is disclosed, not gated (CI
  hardware variance would make a timing gate fluff-friendly).

**SHIP iff** A1–A9 all pass with their absence arms red-under-revert (counts exact,
denominators named above). **KILL if** any structural arm is unachievable — specifically:
single-transaction atomicity cannot be held (it can: one connection, one writer), or the
report's row model cannot drive execution without a second derivation (it can: A9), or
review/archive cannot be blocked without per-row durable state (they can: the policy is
the only intent channel). **UNDERPOWERED, not conclusive, if** only fixture-scale arms
pass and the scale smoke cannot complete in CI for environmental reasons — re-measure on
a quiet host; the count invariants still gate either way.

## 8. Top risks and falsifiers

| Risk | Falsifier / mitigation |
|---|---|
| Deleting evidence weakens run accountability — the audit digest proves what was deleted, not the bytes | Disclosed (delete is irreversible; guide sentence). If an operator needs recoverable disposition, that is D1's archival tier triggering — not a redesign of delete |
| Plan→execute staleness via a non-flock concurrent writer (row-16 residual inherited) | Guarded exact-row deletes make it a typed `store changed under the plan` refusal, never a wrong-row deletion; the structural fix stays row 16/D6. Sharpened (fold wave): the guards cover IDENTITY AND STAMP drift — the row vanishing, its kind/state changing, its landing stamp moving, or the exact-row delete matching ≠1 row — and the GC re-verifies each deleted artifact's bytes against its content address. NON-STAMP figure drift (a row's `bytes`, bench attribution, context key changing between plan and execution) is NOT guarded: the invocation executes on the plan's figures and the audit row records exactly those figures, verbatim — that residual is carried by D6/row 16 with the rest of the non-flock-writer window |
| Audit-payload growth is unbounded | Leases/changes history posture, disclosed; D7's trigger is an operator measurably hit by it |
| `review`/`archive` blocking surprises an operator expecting action | Command output + guide name the blocks and the policy-edit path; A2/A3 pin them; D1/D4 carry the futures |
| The wedge-disclosure text overclaims | Every sentence scoped to shipped behavior (§2.5); review checks it against A2/A3 outcomes |
| Scale: one giant transaction on a huge store | All-or-nothing is chosen deliberately; the smoke bounds the expectation; if a real store shows pathologic WAL growth, splitting into per-key invocations is a D7-adjacent amendment — measured first |

## 9. Forks for the owner

1. **F1 — command shape**: separate `benchweave dispose` subcommand (recommended: keeps
   `retention` in the read-only family posture and the operator guide lists them
   adjacently) vs `benchweave retention --dispose`.
2. **F2 — execution opt-in**: dry-run default + `--execute` (recommended: destructive
   at-rest command, report already the plan surface) vs execute-by-default.
3. **F3 — audit payload home**: content-addressed artifact + digest-pinned row
   (recommended: mirrors the evidence model exactly, keeps rows queryable-thin, gives
   the deleted-content digest a natural home) vs inline JSON + digest column only
   (simpler, equally tamper-evident against inconsistent edits, loses the artifact-model
   symmetry).
4. **F4 — never-migrate posture for dispose**: refuse on behind-schema (recommended:
   fork-A consistency, explicit operator upgrade path) vs migrate-on-open like `report`
   (row 15 shows the family is currently inconsistent either way).

Recommendations are 1/2/3/4 as marked; all four are cheap to reverse before the build
starts and expensive after.

## 10. Fold-wave amendments (2026-09-25, review wave 1)

The three review reports (mechanism critic + two adversary lanes) folded;
what changed, and the disclosures the fold added to the record of truth:

**Mechanisms added by the fold:**

- **GC verifies artifact bytes before deleting them** (critic F1): each
  artifact the GC is about to collect is re-read and re-hashed against
  the content address embedded in its id; a mismatch refuses typed
  (`StoreChangedUnderPlan`) and rolls the whole invocation back — the
  `finalise` mirror: stored bytes are verified, never trusted.
- **The GC's three live-reference columns are indexed inside v6 itself**
  (lane A F2): unindexed, each per-dropped-artifact probe scanned its
  whole table under flock + `BEGIN IMMEDIATE` — quadratic (measured
  4.24x wall per row-doubling on the no-index code: 3.36 s / 14.28 s /
  67.58 s at 5k/10k/20k rows; after the indexes 0.29 s / 0.59 s / 1.33 s
  = 2.01x per doubling, linear). One-time migration cost, measured:
  5.1 ms on a fresh store; 33.9 ms upgrading a v5 store carrying 20k
  capture rows + 20k evidence rows + 20k artifacts.
- **Byte units are decomposed, never summed across meanings** (fold fix
  5): `charged_ledger_bytes` (the G3 reservation-ledger relief — deleted
  capture rows' charged bytes), `artifact_bytes_freed` (what the GC
  physically removed from disk), and `bytes_reclaimed` (the row-bytes
  sum — the disposal-rows method figure, retained and labeled as
  double-counting shared artifacts).
- **The single skipped count splits by the report's status vocabulary**
  (held / anchor_unresolved / ungoverned / not_yet_overdue, plus a
  residual bucket for labels outside the enum), and the REPORT's own
  disclosures ride through the dispose model instead of being dropped.
- **The invocation row lands last in the transaction**, carrying the
  complete `counts_json` (including `artifact_bytes_freed`, knowable
  only after GC) — the transaction is all-or-nothing, so intra-
  transaction ordering does not change durability, and no post-GC
  UPDATE is needed.

**Disclosures (behavior unchanged, now stated where the record is read):**

- `executed_at` is the plan instant: every row of one invocation carries
  the invocation's single caller-supplied `now` (STO-1) — the trail
  asserts no per-row ordering within an invocation. Cross-invocation
  ordering authority does not exist either: ids are uuids (STO-2
  unamended — no sequence), so "which invocation happened first" is read
  from `invoked_at`, not from id order.
- The trail records COMMITTED invocations only. A refused or killed
  invocation leaves no rows anywhere — that is the all-or-nothing
  property working, not an evidence gap; the fault arm pins it.
- Measurement figures carry their denominators: the scale figures above
  are wall-clock times of ONE `--execute` invocation over N synthetic
  finalised captures (distinct artifacts, payloads of 8–11 bytes, three
  context keys) plus the audit-row writes and artifact GC — measured on
  the builder's host, CI hardware will differ; the count invariants gate
  regardless.
- Bench-scoped dispose (`--bench`) deletes unattributed and non-run-keyed
  rows under the filter — the inherited report semantics (`_in_scope`'s
  never-vanish rule keeps them IN scope), so a bench filter is not a
  containment boundary for keys that never mapped to a bench. Named in
  the operator guide's dispose section.

**Record corrections:** §2.2's numbered flow now matches the code (policy
load before the hold — the original list described it inverted); §8's
stale-plan row now names exactly what the guards cover (identity/stamp
drift, rowcount, artifact digests) and what they deliberately do not
(non-stamp figure drift — carried by D6/row 16).
