# Standards governance

> The rulebook for how standards change in BenchWeave. Enforced in review by the
> standards-governor agent (`.claude/agents/standards-governor.md`); the drift
> gates in `benchweave.standards` are its mechanical half. Ratified 2026-09-16,
> founded by the version reset to the 0.1.0 baseline (prior ad-hoc version
> history lives in git before that date).

## Identity and homes

A standard is `<id>` + semver (`MAJOR.MINOR.PATCH`), living at
`standards/<id>/<version>/` — machine corpus and prose companions together
(see `docs/doc-taxonomy.md` for the full placement taxonomy). Two locks
declare and pin it:

- `standards/standards-manifest.json` — governance: which versions are current,
  their status, and the normative path set
- `standards/corpus-manifest.json` — byte truth: one sha256 per machine file,
  rows relative to `standards/`

Repo identity lives in committed data outside the corpus: the compatibility
matrix's Sources cell renders `pyproject.toml` `[project.urls] Repository`
and the `.gitmodules` submodule URL, while `standards-manifest.json`'s
top-level `sdk_compatibility` block mirrors the `compatibility` block of
the SDK lock at the pinned gitlink commit — equality-enforced by
`benchweave.standards check` wherever the submodule working tree sits at
that pin; a moved working tree is refused by name, never mirrored from (the
lock stays the authority); none of these are digest-pinned, so they move no
corpus rows and need no repin (issue #158).
The lock's `sdk` field names the pinned SDK's own version (issue #187 fork
(a)), and `benchweave.standards check` anchors it to the pinned pyproject.

## Change classes and their bumps

| Change | Bump | Notes |
|---|---|---|
| Prose clarification (companion docs) | none | Prose is not digest-pinned; keep it truthful |
| Additive machine errata (backwards-compatible) | PATCH of that standard | The interface `approver_token` pattern: new optional field, nothing removed or retyped |
| Breaking machine change | MINOR at least | Old version retained frozen; `supersedes` recorded |
| New standard | admission | Review + `status: stable`; new tree dir at its first version |
| Deprecation | none (status) | Status change only; the version stays, digest-frozen |
| Deletion of a version | never | Retired corpora live in git history, not the tree |

**Bump minimization (#69).** One bump per (standard, release train). A *release
train* is one merge window of a run: PRs opened concurrently against the same
`origin/main`. Queued changes
to the SAME standard that share a train batch into a single bump (one copy step from
the current active version, one repin); **a batch's bump follows the highest change
class it contains** (errata batched with a breaking change bumps MINOR). Never stack a bump on an unmerged bump — if the
predecessor merges first, re-copy from the new predecessor. Different standards may
share a merge only when they are one increment. CI tests the merge result, so every
in-tree artifact declaring the old version moves in-arc (in the same change/PR) with the bump —
the in-tree motion is part of the bump, not a follow-up.

**Bump window (#97).** The train rule is prescriptive, not descriptive: a standard
may not bump more than once per **24-hour window**, measured between the committer
timestamps of the commits that added each new version directory. A queued change to a
standard still inside its window WAITS — it batches into the next bump of that standard
(the highest-class rule above already governs what the batch becomes). The window is
per standard: bumping otdp does not open or close a window for registry. Exempt: a
standard's first version (admission), and a reset-class commit — identified by a
shape heuristic (one commit adding version directories for three or more standards,
the 2026-09-16 signature), not by the Resets section's full definition; the known
residual is that a coordinated multi-standard increment of that same shape also
escapes the window, accepted because resets are executive-rare. Enforced
mechanically by `benchweave.standards.train_window` in the standards suite; the clock
self-anchors at that module's own arrival commit, so history before the rule is
grandfathered by mechanism. The floor was ratified at 48 hours as a starting figure and
revisited once, not silently: 2026-09-23, explicit owner ruling after one window ran —
the observed cost was latency (a queued fold-after-release waited 34 hours for its
train), not churn. The floor is 24 hours. The window prices the release ledger only:
pre-release authoring accumulated on a dev head is not a bump and waits for nothing
(see **The dev stage** below) — the floor still bounds everything consumers see, and
no longer bounds the edit.

**Bump mechanics — copy, never move.** A version bump copies the old version
dir to the new version and edits bytes only in the copy; the old dir and its
corpus-manifest rows stay in place, digest-frozen. Moving or in-place-editing a
retained version is a governance violation, not a shortcut. The new version's
rows record the old corpus path as their `source`. A dev-stage promotion adds
one more edge: its rows also record the pre-dev active version's
corresponding paths as `lineage` — the dev path named by `source` is a
deleted staging directory and cannot carry the retention chain alone. Both
edges are walked by the derived corpus-dir guard
(`tests/contract/test_baseline.py`), with the same historical-terminal rule
for `-dev` segments; `repin` accepts the optional `lineage` field on rows
and refuses one naming a `-dev` path (that edge is what `source` carries) —
ordinary supersession keeps both trees justified side by side, dev
promotions included. Digest pins move only
through `uv run python -m benchweave.standards repin` — the loop is
edit → repin → export, never a hand-spliced digest. A bump carrying corpus
bytes for any standard with a machine-written validation report (otdp,
registry, execution, interface) regenerates that version's report via its
writer (`check_<suite>.py --write-report`, which refuses on a failing run).
The four standards-tree family scripts derive their corpus directory from
`standards-manifest.json`'s active entry for their standard — devices names
it `OUT`, the siblings name it `CONTRACT_DIR` — and the pin test's report
paths and mutation fixtures derive the same way (#102 D2, generalized to
the family by D1: each script reads the manifest and refuses loudly
without it), so a bump makes no hand-moves on those. Report titles are
version-free constants needing no derivation (`# Registry contract
verification`, `# Procedure and bench contract verification`, …) —
devices' alone embeds its derived version (`# OTDP {version}
specification verification`). Closure's report is docs-rooted
(`CONTRACT_DIR = DOCS / "acceptance"` — no version directory to derive);
its CROSS-standard contract reads are manifest-derived like the rest. The
`docs/README.md` rows linking the reports remain
conventional moves; a FORGOTTEN row is caught mechanically by the pin's
exactly-once link assert (a stale row left beside the new one is not —
copy-never-move keeps the old target resolving). With the version moved,
the pin fails on the copied stale report until the regen runs.

## The dev stage (`-dev`)

A standard may carry at most one dev head: an optional `dev` block on its
standards-manifest entry naming a version (`<target>-dev`, the target strictly
greater than the active version), the date the head was opened (the
machine-readable stale-head age), and a normative path set under
`standards/<id>/<target>-dev/`. The dev directory is staging, not a version:
it is created by a copy of the active version (its corpus rows cite the active
path as `source`), edited in place across any number of changes — each edit
follows the edit → repin loop, and validate treats dev pins exactly like
active pins — and it never appears in the exported bundle, the SDK lock, the
vendored tree, the compatibility matrix, the identity block, or the public
docs site (the site assembly skips `-dev` directories on the packaging-side
lexical rule — both the page staging and the corpus copy beside it). The
SDK never consumes `-dev` bytes: immutability starts at release, and a lock
pinned at a
`-dev` version would have to churn its version per edit or carve an exemption
into the same-version refusal — neither is sanctioned.

The head is train-shared state: one head per standard, carried on the train's
working branch, owned by no author, named for the target version — no author
suffix, because authorship already lives in git history and PR review.
Contributors edit it through the ordinary PR flow; two authors' overlapping
edits are ordinary MODIFY-vs-MODIFY merges resolved in review. A second
concurrent head is refused by the one-optional-field shape, not by
convention. Before opening or editing a head, a contributor re-reads the
manifest's `dev` block — the machine-readable shared-state token;
`python -m benchweave.standards versions` lists open heads — and rebases on
the head-carrying branch.

Head lifecycle. OPEN is a PR adding the block, the directory and its rows;
the standards-governor lane (mandatory for any `standards/` touch) is the
gate — there is no separate pre-approval. EDIT is a PR to the head-carrying
branch. CLOSE is either promotion (below) or abandonment: the standards
coordinator deletes the directory, its rows and the block through the same
PR flow; an orphaned head (author unavailable) closes as an abandonment. A
stale head (open, idle, target still open) is a coordinator ruling, not a
gate — the block's `opened` date keeps its age machine-readable so the
governor review sees it on every `standards/` touch, and a clock on
authoring is exactly the conflation this stage removes. The standards
coordinator may declare a head a release candidate (the optional boolean
`candidate` field on the dev block, owner ruling 2026-09-23): the
declaration is advisory and machine-readable — it changes no enforcement,
testing runs through the `--corpus` lane regardless, and a release
candidate as a separate released directory stays rejected.

The dev-proof lane: each standards-tree family script (devices, registry,
execution, interface) accepts `--corpus <dir>`, which points its census at
the manifest-declared dev head for that script's standard — dev bytes are
proven in place, before promotion, through the same checker lane that
validates releases. The override accepts exactly the declared head
(anything else refuses), never combines with `--write-report` (the
machine-written reports are a property of released versions; a dev run is a
check, not a report), and is read-only for the SDK's lock, vendored tree
and pointer. Without the flag, every script resolves the manifest-active
tree exactly as before. Cross-standard reads stay manifest-active
regardless of the override.

The bump window does not see the head — the collector counts pure-semver
version directories only, and the active entry's version must be pure semver
(`standards_entry_version_invalid` on anything else), so the window cannot be
dodged by suffixing a release directory. Promotion is the bump event, and it
is a bump in every existing respect: copy the dev directory to the released
version (its corpus rows cite the dev path as `source` and the pre-dev active
version's corresponding paths as `lineage` — a dev promotion severs the
copy-never-move chain the bump flow would otherwise carry: the promoted
bytes' direct producer is the dev directory, which teardown deletes by
design, so the predecessor edge is named separately rather than left to git
history), apply the version sweep,
delete the dev directory and its rows, remove the `dev` block, repin,
regenerate the validation report, export and sync — under the change-class
rules with the batch being everything the head accumulated; the head's
version names the intended target, the class rule governs the promoted
version. Immutability starts at release: a version directory with no `-dev`
suffix is frozen exactly as before.

An emergency patch on a standard with an open head never opens a second
head. Two sanctioned paths, named by the standards coordinator: strip and
promote — revert the head's unfinished items out (cheap MODIFY reverts) and
promote the remainder early under a recorded window exception — or a
priority claim, where the emergency claims the head and the paused work
re-lands after promotion.

## Roles and authority

Rulings are recorded artifacts, never comments or habits:

- **Contributor** — any developer; opens and edits heads through PRs, bound
  by the governor lane and single-reviewer review.
- **Reviewer** — a single human reviewer other than the author, required for
  any merge touching corpus bytes or corpus-manifest rows (owner ruling
  2026-09-23: single reviewer, not an additional second human — until
  further notice; re-review by 2027-03-23, the rule carrying its own review
  trigger the same way the bump floor does — and restorable to a
  second-human requirement by a future owner ruling, the same recorded
  mechanism that set it). One carve-out: the standards
  coordinator may be the author and the reviewer of their own corpus-byte
  merges; non-coordinator contributors always need a human reviewer who is
  not the author. Self-merge by anyone else remains indefensible for
  normative bytes; the rule exists before the first multi-author head, not
  after the first bad merge.
- **Standards coordinator** — promotes batches (the timing and batching
  call), rules window exceptions and emergency early-promotions, closes
  stale and orphaned heads. The owner holds the role as ratified;
  delegating it is itself a GOVERNANCE amendment, never a comment or a
  habit.

A window exception or early promotion is written into the promotion PR body
and carries the standing #97 reopen obligation for contested firings (three
windows; any contested firing). Floor changes: the coordinator proposes, the
owner ratifies, in GOVERNANCE. Mechanical gates judge everything judgeable;
humans decide exactly the timing, batching and exception calls, and those
decisions live in reviewable records. Nothing here vests authority in an
agent: the governor lane reviews, it does not rule.

## Retention

Superseded versions stay digest-frozen forever. A version is retired by
deleting its directory AND its corpus-manifest rows only as part of a reset
class event (see below); ordinary supersession keeps both trees side by side.
The obsolete-version guard in `tests/contract/test_baseline.py` refuses any
corpus the manifest does not admit.

## Resets

A reset re-baselines every standard to a chosen version label in one versioned
act (founding precedent: the 2026-09-16 0.1.0 reset). Resets are rare and
executive decisions; they must reset every surface together — governance
versions, tree dirs, and version strings inside the normative bytes — following
the cascade order in the governor's runbook. History is preserved by git and
by the `source` provenance fields in the corpus manifest: reset-imported rows
name the upstream authoring path, and supersession-copied rows name the
corpus path they were copied from (per Bump mechanics above) — never a path
that did not produce the bytes.

## Gates (mechanical, all must be green)

1. Drift gates: normative bytes changing without a version bump is refused
   (`normative_hash_mismatch`, `content_drift_without_version`)
2. Coverage: corpus-manifest rows == machine files on disk (nothing vendored
   escapes the manifest, nothing listed is missing; both directions are
   enforced fail-closed by `benchweave.standards repin`, the only mechanical
   pin writer)
3. Architecture validator suites for the touched standard(s)
4. SDK round-trip: `make check-sdk-standards` (manifest, bundle, lock and
   vendored tree agree)
5. Compatibility matrix matches a fresh render (`matrix --check`)

## Direction

Standards changes land main-side first, flow outward via the exported bundle,
and are consumed by revision-pinned locks (SDK vendored tree; plugin contract
locks). Never SDK-first, never consumer-side edits to corpus bytes.

## Deliberately versioned elsewhere (not governed here)

Sub-capability ids (`otdp:dc_psu:*` profiles, `otdp.*/*/` action ids),
registry fixture package versions, plugin release versions, the architecture
document edition (STG 1.5), and the MCP date. These carry their own versions;
only the six standards above are governed by this file.

The adapter API version is declared in the corpus-manifest identity block
(`identity.adapter_api`); its authority is the active OTDP descriptor schema's
`$defs.adapter.properties.api_version` const, and `validate_identity` fails
closed on absence or disagreement at every export/check. Identity-block edits
move no corpus rows and need no repin. Promotion trigger: when the adapter
surface stabilizes, this becomes a seventh corpus standard carrying a canonical
importable Python contract; until then the declaration plus the three-way
agreement test (`tests/sdk/test_adapter_agreement.py`) is the honest boundary —
it pins names, arity, keyword-only-ness, coroutine-ness and key/enum sets, not
semantics.
