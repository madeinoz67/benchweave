# Issue #225 — Slice 3: management surfaces and identity — design record

**Status:** Design (builder-ready) · **Tracking:** madeinoz67/benchweave#225 (sub-issue of #209, slice 3 of 6)
**Authority superseded where corrected:** `docs/implementation-planning/10-contributor-publishing-design.md` §4 Slice 3 + §3.5 (frozen; never edited — corrections live here, §1). Fixed parameters: PRD `docs/implementation-planning/07-contributor-publishing-prd.md` §9 rulings (Q1–Q21), PLUS the two post-parent owner rulings that landed with slice 1 and bind this slice: **"the registry STATES AND ADVERTISES; the client enforces"** (issue #223 rework — `benchweave-registry/.github/workflows/records.yml` header comment; the replay is an on-demand tool, not a publish-time CI gate) and **"the registry VALIDATES + PUBLISHES + LABELS, never signs"** (`scripts/verify.py` docstring — publisher signatures at package time; no lane signing key in any CI).
**Evidence baseline:** registry `origin/main` @ `21acea1` (local checkout 2 behind — all registry reads are origin bytes); SDK `main` @ `714eab4` (v0.4.1); gateway `main` @ `e8aeadb` (this worktree). Gortex-served bodies cited per path; `git show origin/main:` where the local checkout is stale.

**Verdict: BUILD.** The slice is buildable on proven mechanisms, is smaller than the issue text implies (§1.1), and closes one real defect the slice-1 tree shipped with (§1.2). One pre-build verification step is mandatory (§7 R1).

---

## 1. Evidence-based corrections vs the parent design record

### 1.1 Slice 1 already shipped most of the "identity" half

Verified on registry `origin/main` — the parent design's §4 Slice 3 build list names four things that ALREADY EXIST:

| Parent-design build item | Actual state at `21acea1` | What remains for slice 3 |
|---|---|---|
| "namespace similarity rule with committed vectors" | **Landed.** `lane-rules.json` carries `similarity_rule` (skeleton-plus-edit-distance, confusable map, `max_edit_distance: 2`) with **5 committed test vectors**; reserved namespaces (`benchweave`/`otdp`/`dev`/`stg`) + reserved plugin names. SDK-side enforcement exists at package time (`namespace_reserved:`/`namespace_collision:` refused; `namespace_lookalike:` flagged-not-refused riding the draft — `docs/publishing-guide.md:95-96`, `cli.py` `package_command` printing `artifacts.lookalikes`). | The **vetting-time and records-side** application (§2.4): nothing today enforces namespace rules over committed records or `publishers.json` — only the SDK packaging path does. |
| "publisher vetting records (`publishers.json` + … Q21 declared-not-verified rows)" | **Landed.** `records/publishers.json` + `publishers.schema.json`: vetted identity, namespace, Ed25519 public key + validity window, and `publisher_repo_protections` with `state: "declared-not-verified"` (Q21). | The **machine-citable vetting checklist** (no V-rows exist; `review-checklist.md` v1 is release-review only) and citation enforcement. |
| "transfer-as-re-vetting" record shape | **Seeded.** `records/records.schema.json` `lifecycle.transfer` block already exists: `from_publisher`/`to_publisher`/`consents` (minItems 2)/`vetting_reference` — **no semantic arm enforces any of it** (`scripts/validate_records.py` handles only `op == "publish"`). | The enforcement (§2.5): receiver-vetting resolution, consent naming, coordinator actor, similarity bar. |
| "accountability verify command (CR-54)" | **Landed.** `scripts/verify.py` prints the chain per release — publisher, reviewer, outcome, signature state, closure digest, capability declaration — from a clean clone (its own tests green). | Prove it on the dogfooded release (C6) + extend the chain with the lifecycle event timeline (§2.6). |

The lifecycle `op` enum in `records.schema.json` already enumerates `publish|yank|advisory|unlist|takedown|transfer`. **Slice 3's real build is the SEMANTICS and the CLI family, not the shapes.**

### 1.2 Defect found: the served release tree cannot resolve — status documents never landed

The gateway resolver reads `status.json` AND `status.sig` **unconditionally** per release, verifying both against the origin trust root (`src/benchweave/registry/resolver.py::Resolver._resolve_release`; `LocalDirectorySource.status_bytes`/`status_signature` at resolver.py:100–115; `FileNotFoundError` → `unknown_release`). The registry README claims the served layout is "`manifest.json`, `manifest.sig`, `status.json`, `status.sig`, `payload.zip` — … a clone is a resolvable origin". The committed dogfooded release carries **neither status file** (full `origin/main` tree listing: 4 files under `releases/benchweave-registry/madeinoz67/dps150/0.1.0/`), and `keys/main.pub.pem` — which `scripts/replay_admission.py` loads — is **not committed either**. Consequences, each verified from the bytes:

- A clean clone of the registry repo cannot run the admission replay (no root) and could not resolve the dogfooded release even with one (no status pair).
- `validate_release_status.py` is green **by vacuity** (its own output says so: "no status documents under releases/").
- The publish record's reason field says "…signed, replayed" — the replay that ran at slice-1 landing must have run against maintainer-local state (keys and status bytes) that never committed.

This is exactly the vacancy C3 walks into: **yank semantics cannot be proven on a tree whose baseline release does not carry the document yank flips.** Slice 3 closes it: the status-document discipline becomes a first-class mechanism (§2.3), the dogfooded release's baseline status pair is backfilled as part of the slice (signed by the maintainer's origin key out-of-band, committed as release bytes), and C3's proof harness is fixture-keyed so no arm ever depends on uncommitted key material.

### 1.3 Post-parent rulings that reshape the slice

1. **On-demand replay (owner, #223 rework).** The parent design's Q10 framing ("authoritative admission replay runs in repo-of-record CI") is superseded: records CI runs validity only; `replay_admission.py` is the client-side verification tool. C3's replay half is therefore an **on-demand proof with pasted evidence in the PR body**, not a new CI job. The registry repo's pytest arm carries the same construction **skip-guarded on a gateway checkout being available** (`skipif` naming the path) so CI stays negligible and the ruling holds.
2. **Publisher-signs / registry-labels.** The parent's §3.2 maintainer-origin-signing narrative is reworked: the publisher signs at package time (`--publisher-key`); `sign_release.py` (gateway) remains the maintainer's validate-and-record tool. Slice 3's status-signing follows the same shape: a **local key argument to a maintainer-run command**, never a CI-held key (§2.3).
3. **"Gateway repo: nothing" holds** — with one disclosed consequence: `docs/publishing-guide.md` (gateway-owned) documents the packaging refusal prefixes; the `registry` family's documentation home is the **SDK's own docs site + the registry README**, not the gateway guide (deferral D-S3c names the trigger should the owner want the guide extended).

### 1.4 Signature-topology ambiguity on the real tree (pre-build verification, not a design input)

One `manifest.sig` serves two inconsistent readings: `verify.py` verifies it against the **publisher key over `submission-manifest.json`** (0.1.1 bytes, no review block); the resolver verifies it against the **origin root over `manifest.json`** (0.1.2 bytes, review block inserted). One Ed25519 signature cannot verify over both byte sets — at most one reading is true of the committed tree, and **no CI step exercises either** (records CI never runs `verify.py`'s release check or the replay). This design does not assume an answer: §7 R1 makes "run both tools on the current clone" a mandatory pre-build step whose outcome selects the backfill's signing recipe; every C-arm proof is fixture-keyed and immune. The C6 arm (verify on the dogfooded release) is conditional on this resolution and the resolution is IN scope (whichever tool misreads gets fixed in this slice).

---

## 2. The mechanism

Two repos. **Registry repo** (`benchweave-registry`): record semantics, validity-gate arms, the index generator's unlist arm, the vetting checklist, the backfill, the replay's fixture mode. **SDK repo** (`benchweave-sdk`): the `registry` CLI family. Gateway: nothing.

### 2.1 The CLI family (SDK; Direction module `src/benchweave_sdk/registry_ops.py` + a `registry` Click group in `cli.py`)

Seven commands — the issue's five plus `status` (CR-31's contributor surface, named in the parent §3.5) plus one correction add (`publish-status`, §1.2's durable fix; the family the parent design assumed publish had already written). Every command takes `--registry-clone` (the `package`/`submit` precedent); all are offline and git-native.

| Command | Actor | What it does (record mutations in **bold**) | Keyed? |
|---|---|---|---|
| `registry queue` | maintainer | Derives every submission's stage (7 stages, §2.2) from open PRs + committed records; PR state via `gh pr list --json` when present, else `--pr-state <fixture>`; without either, degrades loudly (`stage_partial: pr_state_unavailable` — names which stages are under-derived). Read-only. | no |
| `registry status [--publisher P] [--plugin X]` | contributor | Publisher-scoped exact submission sets + per-release lifecycle event timeline from records alone (CR-31). Read-only. | no |
| `registry publish-status <publisher>/<plugin>@<version>` | maintainer | Writes the release's **baseline status document** (sequence 1, lifecycle `published`, schema-complete per `standards/registry/0.1.1/release-status.schema.json` — all 11 required keys) + signs it (`--origin-key`, a local PEM path; the `sign_manifest_bytes` helper family over canonical status bytes). Closes §1.2 durably. | yes |
| `registry yank <p>/<x>@<v> --reason …` | maintainer | Reads the current status (absent → `yank_status_absent:` naming `publish-status`), writes sequence+1 lifecycle `yanked` preserving advisories/support fields, re-signs, **appends the lifecycle yank record** (actor/reason/timestamp). | yes |
| `registry advise <p>/<x>@<v> --id … --severity … --summary … --url …` | maintainer | Status rewrite with `advisories[]` appended (lifecycle stays `published` — an advisory is not a yank), sequence+1, re-sign, **appends the lifecycle advisory record** carrying the advisory block. | yes |
| `registry unlist <p>/<x>@<v> --reason …` | maintainer | **Appends the lifecycle unlist record only** — no status change; the release stays resolvable and admissible (CR-32/E4 semantics); the catalogue drops the row (§2.4). | no |
| `registry withdraw <p>/<x>@<v> --reason …` | contributor | Pre-acceptance only: **appends the lifecycle withdraw record**; refuses if a publish record exists (`withdraw_after_publication:` — post-signing withdrawal is advisory or unlist, CR-32). | no |
| `registry transfer <p>/<x>@<v> --to <publisher> --consent-from … --consent-to … --vetting-ref …` | maintainer (coordinator) | **Appends the lifecycle transfer record**: both consents naming from/to publishers, `vetting_reference` citing the receiver's vetting (publishers.json entry + V-rows). Future releases of the plugin publish under the receiver's namespace; existing release paths are immutable history. | no |

Key discipline: **keyed commands take the key as a local file argument, run maintainer-side, and the key never enters either repository or any CI** (CR-12; the `--publisher-key` posture extended). All record writes are **append-only new files** (`records/lifecycle/<publisher>/<plugin>/<version>/<seq>-<op>.json`, the existing naming); no command deletes or rewrites any file — C4's no-erasure proof pins exactly this (§5).

### 2.2 Queue-stage derivation (CR-27) — the committed-first truth table

Stage per submission key `(publisher, plugin, version)`, precedence most-advanced-first, from main-tree records + PR state:

1. `published` — a lifecycle `publish` record exists on main.
2. `withdrawn` — a lifecycle `withdraw` record exists, or the PR is closed-unmerged with no publish record.
3. `signed` — no publish record; a review record with outcome `accepted` exists AND the PR tree carries `manifest.sig` (PR-state arm).
4. `accepted` — a committed review record with outcome `accepted`, no publish record.
5. `changes requested` — latest review record outcome `changes-requested` (PR-state arm: a PR review requesting changes).
6. `in review` — open PR with maintainer review activity, no committed record (PR-state arm).
7. `submitted` — open PR, nothing else.

The PRD's "derivable from the repository of record alone" is read (with the parent §3.5, stated checkably) as **the GitHub repository including its PRs**; the records-only fallback reports the coarse stage with the loud `stage_partial:` disclosure. The hand-derived truth table + the fixture records tree (all 7 stages across 2 publishers × 4 submissions — C1's and C4's fixtures share one tree) **commit before any queue code** (§5 C1 ordering). Fork F1 flags the `signed`-stage reading (§8) — post-rework, the publisher signs at package time, so "signed" as a distinct pre-publication stage is a judgment; the default chosen is the PR-carries-signature-artifacts reading because it is the only one that keeps the stage list's seven members distinct under the reworked flow.

### 2.3 The status-document discipline (the §1.2 fix, generalized)

Baseline (`publish-status`) → yank (sequence+1, `yanked`) → advisory (sequence+1, advisories append) — one monotone sequence per release, every rewrite signed by the origin key, mirroring exactly what the resolver enforces (`check_status` sequence/expiry gates + `_gate_lifecycle`'s `yanked`/`revoked` refusals at `admission.py:151`). CI cross-checks the pairing (§2.4): a yank record whose release's status is not `yanked` refuses, and a `yanked` status with no yank record refuses — record and served state cannot diverge silently.

### 2.4 Registry-repo validity-gate arms (extend `scripts/validate_records.py`; the slice-1 gate is the precedent)

- **Namespace arm (records-side CR-15/16/39):** every record's publisher must be a vetted `publishers.json` entry (`publisher_unvetted:`); a publish record colliding with another publisher's package refuses (`namespace_collision:`); reserved lists refuse (`namespace_reserved:`).
- **Per-op lifecycle shapes (schema 1.1.0, §2.5) + pair checks:** `yank_status_absent:`/`status_yank_unrecorded:` (§2.3); `advisory_status_absent:` (the advisory block must appear in the served status's `advisories[]`); `withdraw_after_publication:`.
- **Transfer arm (CR-17/Q9):** `vetting_reference` must resolve to a vetted `publishers.json` entry for `to_publisher` (`transfer_receiver_unvetted:` / `transfer_vetting_unresolved:`); consents must name both publishers; the record's actor is the coordinator (CR-61's ruleset enforces the approval — the record does not re-implement it).
- **Vetting citations:** every `publishers.json` entry carries a required `vetting` block (`checklist_id: "vetting-checklist"`, version, cited V-rows, `vetted_by`); unresolved row citations refuse (`vetting_row_unknown:`). The existing `madeinoz67` entry is re-vetted and backfilled in the same commit (it is the project's own entry — honest re-vetting, not fabrication).
- **Generator unlist arm (`scripts/generate_index.py`):** a release with an unlist record drops from the index at regeneration — the same row-drop reading as the yank arm (fail-closed doctrine intact: out-of-enum status still refuses; unlist is record-driven, status stays `published`).

### 2.5 Records schema motion (lane-owned, additive; registry-standard bytes untouched)

`records/records.schema.json` `record_version` const `"1.0.0"` → **enum `["1.0.0","1.1.0"]`** — the in-tree registry-0.1.2 enum-arm precedent applied to the lane's own schema; existing records stay valid. 1.1.0 adds: `withdraw` to the op enum; per-op `if/then` required blocks (yank → `release_manifest_sha256` + `status_sequence`; advisory → advisory block; transfer → the transfer block, now required for the op). `publishers.schema.json` gains the required `vetting` block (schema version const 1 → 2 — two entries' worth of data, restamped in the same commit; publishers.json is lane data, not standards; copy-never-move does not bind). **No `standards/` byte moves in any repo** (tripwire `git diff origin/main...HEAD -- standards/` empty gateway-side; the registry repo vendors read-only).

### 2.6 C6 chain extension

`verify.py`'s chain output gains the release's lifecycle event timeline (ops, actors, timestamps from records) beside the existing publisher/reviewer/outcome/signature/closure/capabilities line — one field, sourced from already-validated records. The incident exercise is then exactly: clean clone → `uv run python scripts/verify.py`.

---

## 3. Minimal first increment and deferrals

**In:** the seven commands (§2.1) with their refusal batteries; schema 1.1.0 + publishers schema v2 + `vetting-checklist.md` v1 (V-01…V-06: identity↔namespace, reserved lists, similarity rule vs existing namespaces with vectors cited, Q21 declared-not-verified protections, key recording + validity, transfer re-vetting); the four validity-gate arms (§2.4); the generator unlist arm; the dogfooded release's baseline status backfill (+ the §1.4 topology resolution it depends on); the fixture trees, PR-state fixture, and the two hand-derived truth tables (queue stages; namespace/vetting vectors) committed FIRST; `replay_admission.py --origin-root/--fixture` mode (point the on-demand tool at a fixture root); README sections; SDK docs-site CLI reference rows; SDK MINOR bump 0.4.1 → 0.5.0 (new commands; no gateway-consumed surface moves, so **no submodule pointer advance** — disclosed, obligation 7 untouched).

**Explicit deferrals (each names carrier + reopen trigger):**

| # | Deferred | Carrier | Reopen trigger |
|---|---|---|---|
| D-S3a | `registry publish` wrapper (validate-and-record as one command; today gateway `sign_release.py` + the hand-written publish record) | This record §2.1 + registry README publishing-path section | The next dogfooded submission, or slice 5 wanting the family complete |
| D-S3b | GHSA channel automation (CR-62) — manual publication documented in the checklist | The advisory checklist row citing the manual step | The first security-class incident exercise (slice 4's lane) or owner call |
| D-S3c | Gateway `docs/publishing-guide.md` lifecycle sections (docs-only gateway motion; keeps "gateway: nothing" byte-true) | This record §1.3 | Owner word or the next gateway docs train |
| D-S3d | CR-40's signed fingerprint list beyond the committed public root | Slice 6's lane (this record's F2 commits the raw PEM now) | Slice 6 |
| D-S3e | PR-state caching/refresh for `queue` beyond the single-shot `gh` read | D3's central-service PRD (parent §6) | D3's own PRD |

Parent §6 D3/D5/D7 remain carried by the parent record (not re-deferred). D8 blocks slices 4–6 acceptance only — not this slice (Q19's ruling).

---

## 4. Invariant impacts

- **REG-5 amendment (this slice's row, quoted as it would land in `docs/internal/invariants.md`):**
  > Amendment (2026-10-⟨land⟩, issue #225 slice 3): the namespace/lifecycle clauses are true now — lifecycle records are per-op shape-enforced (a yank record requires its release's served status document to carry lifecycle `yanked` at a sequence greater than every prior, signed by the origin key, and vice versa; an advisory record requires the advisory in the served status's `advisories[]`; an unlist record removes the catalogue row and touches no status document — the release stays admissible; a withdraw record is pre-acceptance only), namespace assignment is restricted to vetted publishers under the committed similarity rule (records-CI refuses unvetted publishers, collisions and reserved names; vetting citations must resolve), transfer requires both consents plus a receiver vetting reference resolving to a vetted publisher held to the CR-35/39 bar (silent reassignment unrepresentable), and no operation erases a signed release from history (append-only records; git history is the floor).
- **REG-1:** untouched (plugin lifecycle unchanged). **CON-13:** untouched (no gateway website bytes; the registry repo carries no literal gate by its own recorded stance). **CR-13:** untouched — no gateway `src/` byte moves; admission is consumed read-only by the on-demand replay, exactly as CR-29 intends (`_gate_lifecycle` refuses `yanked` today; this slice proves it, not changes it). **CR-13/Q12 restated** in each keyed command's docstring (the lane compensates process-side, never admission-side).
- **On-disk formats/schema (Tier-3 inventory):** `records/records.schema.json` 1.1.0 (enum-arm additive), `records/publishers.schema.json` v2, `vetting-checklist.md` v1, the status-document write discipline (bytes shaped by the already-vendored `release-status.schema.json` — no new authority). All additive, versioned, readable-and-refusing.
- **Surfaces:** MCP/REST/openapi/CLI-gateway — none. SDK CLI + its docs site; registry repo README + CI steps inside the existing `validity` job; operator docs — none (contributor tooling). Fixture lattice — untouched (fixtures live in the registry repo's own `tests/`, runtime-keyed).

---

## 5. Acceptance rule C — pre-committed proof plan (both kill directions per arm)

Ordering discipline (slice-2's C1 ancestry precedent, `bd93b1a` ≺ `33f38e8`): **fixture trees + PR-state fixture + both truth tables commit FIRST**, before any command or gate code; the PR body proves it with `git merge-base --is-ancestor`. Fixture names invented (`northwind-instruments`, `harborline-systems` families — the slice-2 fixture namespace).

- **C1 queue (CR-27).** Fixture: one records tree with all 7 stages across 2 publishers × 4 submissions + a PR-state fixture (open/closed PRs, review activity, carried files). Truth table: hand-derived per submission × {full mode, records-only mode} — committed first. SHIP = `registry queue` matches every cell (full mode via `--pr-state`; the live-gh path is smoke-tested manually, pasted). KILL = any stage mis-derived in either mode. Underpowered clause: a harness failure (missing fixture, malformed PR-state) blocks; only a wrong stage kills.
- **C2 lifecycle records (CR-28/NFR-3).** yank + advisory + unlist on one fixture package, then: fresh `git clone` of the result → `validate_records` green, `verify` green, `queue` derives the post-op state, and each op's record is present with actor/reason/timestamp. SHIP = all three reconstructable from the clone alone. KILL = any op leaving no reconstructable record.
- **C3 yank semantics (CR-29/S5).** Two halves. **(a) Replay:** a runtime-keyed fixture origin (Ed25519 keypair generated in-test; `LocalDirectorySource` over a tmp release tree — the `test_registry_reuse.py` construction) with status lifecycle `yanked` → the pinned gateway's `Resolver`+`admit` (via `replay_admission.py --fixture`) raises `AdmissionRejected("yanked")`; control arm: identical bytes, lifecycle `published` → admits. RED-sanity: flipping the fixture status back to `published` flips the arm green (the discriminator is the lifecycle, nothing else). **(b) Catalogue:** regenerate the index over the yanked fixture → row gone; advisory fixture → row carries the advisory; unlist record → row gone; `deprecated` → row stays (boundary matrix extended from slice 2's 11-value table with the record-driven arms). SHIP = both halves. KILL = either half failing. The replay run over the REAL backfilled dogfooded release is pasted in the PR body (on-demand, per the ruling).
- **C4 contributor side (CR-31/32).** `registry status --publisher P` returns exactly P's submissions with correct stages on the 2×4 fixture (exact-set equality, both publishers, disjointness pinned). `withdraw` on a pre-acceptance fixture works and the queue shows `withdrawn`; `withdraw` on a published fixture refuses `withdraw_after_publication:`. No-erasure proof: (i) command census test pins the Click group's command set exactly (a `delete`/`remove` cannot appear silently); (ii) an append-only tree-diff test snapshots the clone before/after every op and asserts **additions only**. SHIP = exact sets + the refusal + both no-erasure arms. KILL = any erasure path existing (any command mutating or deleting existing files, or the census drifting).
- **C5 namespace/transfer (CR-15/16/17/39).** Records-side: collision fixture (publisher B claims A's package) → `namespace_collision:`; reserved (`otdp-tools` publisher; a reserved plugin name) → `namespace_reserved:`; unvetted publisher → `publisher_unvetted:`; lookalike namespace in `publishers.json` (`benchwave-labs` vs `benchweave`) → refused at vetting CI under the committed rule (the 5 committed vectors run as the rule's pin in BOTH repos — the twin-test discipline against the same `lane-rules.json` data). SDK-side: the existing package-time trio re-pinned by CLI-level arms. Transfer: fixture without `vetting_reference` → `transfer_receiver_unvetted:`; with it (receiver vetted, consents naming both) → record lands with both consents; receiver unvetted → refuses. SHIP = every fixture refused/flagged as expected. KILL = any fixture passing that should refuse.
- **C6 accountability (CR-54).** Clean clone → `uv run python scripts/verify.py`: the dogfooded DPS-150 release's chain prints publisher, reviewer, signed approval (signature state), closure digest, capability declaration, and the new lifecycle timeline — with no gateway-local state, no PR thread, no service. Conditional on §1.4's resolution landing (if `verify.py`'s signature reading is the wrong one, the fix is in this slice). SHIP = every element present from the clone alone. KILL = any element needing gateway-local state.

**Anti-gaming:** every refusal arm's control (the mutant restored) must pass; `no tests ran` is a FAILED check; counts read from junitxml/exit codes, never filtered summaries.

**CI cost:** negligible — the validity job grows four static arms + two truth-table runners (sub-second to seconds); SDK grows unit tests (seconds); no new CI jobs; the replay stays on-demand (ruling).

---

## 6. Tier and keyword scan (design-time call, #254)

**Tier 3.** Triggering rules: (i) the diff touches **JSON Schema files** (`records/records.schema.json`, `records/publishers.schema.json`); (ii) the diff text carries the keywords `sha256` and `subprocess`. The gateway repo's expected diff is EMPTY (the tier is carried by the sibling-repo PRs, which cite #225 in the single issue stream; the gateway-side commit is this design record alone — docs-only, Tier 1 by itself, but the slice's build PRs take Tier 3).

Keyword scan over the EXPECTED diff text (both repos' build diffs + this record; counts are design-time estimates over the drafted content — the builder re-runs the scan at review per the rubric's re-derivation): `sha256` ≈ 34 (schema patterns ×8, validity-gate digest checks ×6, status binding pins ×4, truth-table/fixture prose ×8, SDK ops ×6, README/docs ×2); `subprocess` ≈ 4 (the `gh` invocation in `queue`/`status` mirroring `submit_command`, + tests); `hashlib` ≈ 3 (signing/status helpers); `threading` 0; `asyncio` 0; `migrate` 0; `recovery` 0; `protection` 0. No dependency changes; no submodule pointer advance.

---

## 7. Top risks — each with its falsifier

1. **Signature-topology ambiguity on the real tree (§1.4).** Falsifier/pre-build step: run `scripts/verify.py` and `scripts/replay_admission.py --gateway <pin-checkout>` on the current clone; whichever fails names the binding defect; the owner confirms the intended binding; the backfill signs to THAT reading and the loser tool is fixed in-slice. The design is falsified only if BOTH readings fail for reasons beyond the binding (then §1.2's remediation re-scopes).
2. **Queue's PR dependence.** `gh` absence or PR-shape drift mis-derives stages. Mitigated: `--pr-state` fixture drives all CI proof; the live path degrades loudly. Falsifier: a live-run mismatch on a real PR — the disclosure line is the contract.
3. **Two similarity-rule implementations** (SDK package-time; registry vetting CI) drift apart. Mitigated: both pinned against the same committed vectors (twin tests). Residual disclosed: algorithm drift beyond the vectors is review-borne until a shared-package train (D3-class) exists.
4. **Schema enum churn vs old clones.** Records valid at 1.1.0 refuse under a 1.0.0-only validator at an old commit — accepted (forward motion, same shape as any schema bump); the enum arm keeps today's records valid forever.
5. **Unlist/yank polarity confusion.** An unlisted release must remain ADMISSIBLE (status untouched) while dropping from the catalogue — the easiest arm to get wrong. Falsifier: C3(b)'s boundary matrix includes unlist-record × status-enum cells; a cell that drops the row by flipping status fails the arm.

---

## 8. Forks for the owner (defaults chosen are defensible; each may be overridden)

- **F1 — the `signed` stage's post-rework meaning.** DEFAULT: PR-carries-signature-artifacts (keeps 7 distinct stages). Alternative: collapse `signed` into `accepted` (6 stages — contradicts the PRD's user story list).
- **F2 — commit the origin public root (`keys/main.pub.pem`) now.** DEFAULT: yes (a public key; makes the replay + verify clone-runnable; CR-40's SIGNED fingerprint list still rides slice 6). Disclosed interaction: CR-59's custom secret-scanning pattern must target private-key PEM shapes only — `publishers.json` already commits a public PEM, so the shape distinction is established. Alternative: wait for slice 6 (leaves §1.2's clone-runnability half-open).
- **F3 — the dogfooded release's baseline status backfill rides this slice.** DEFAULT: in-slice (makes the README's layout claim true; C3's real-tree replay needs it). Alternative: defer to slice 6 (C3 stays fixture-only — weaker than the issue's S5 wording).
- **F4 — records schema versioning shape.** DEFAULT: `record_version` enum arm `["1.0.0","1.1.0"]` (the registry-0.1.2 precedent). Alternative: bump-and-restamp (2 records — cheaper now, loses the old-valid property).

## 9. Disclosed unverified

- The §1.4 signature binding is UNRESOLVED by this record by design (R1's pre-build step resolves it); no arm's fixture proof depends on it.
- Keyword counts in §6 are estimates over drafted text, not a scan of a real diff; the builder's review re-derives them (the rubric's own rule).
- The live-`gh` queue path is smoke-tested manually (pasted), not CI-pinned — the fixture path is the pinned one.
- SDK `main` beyond `714eab4` and registry `origin/main` beyond `21acea1` were not re-verified for sibling-train motion after this writing; the builder re-runs the #181 R2 pre-flight (fetch, branch list, sibling PRs) at merge base.
