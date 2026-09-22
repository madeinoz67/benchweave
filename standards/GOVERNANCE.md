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
may not bump more than once per **48-hour window**, measured between the committer
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
grandfathered by mechanism. The 48-hour floor is a starting figure ratified with this
rule; it is revisited after three windows, not silently.

**Bump mechanics — copy, never move.** A version bump copies the old version
dir to the new version and edits bytes only in the copy; the old dir and its
corpus-manifest rows stay in place, digest-frozen. Moving or in-place-editing a
retained version is a governance violation, not a shortcut. The new version's
rows record the old corpus path as their `source`. Digest pins move only
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
