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

## Change classes and their bumps

| Change | Bump | Notes |
|---|---|---|
| Prose clarification (companion docs) | none | Prose is not digest-pinned; keep it truthful |
| Additive machine errata (backwards-compatible) | PATCH of that standard | The interface `approver_token` pattern: new optional field, nothing removed or retyped |
| Breaking machine change | MINOR at least | Old version retained frozen; `supersedes` recorded |
| New standard | admission | Review + `status: stable`; new tree dir at its first version |
| Deprecation | none (status) | Status change only; the version stays, digest-frozen |
| Deletion of a version | never | Retired corpora live in git history, not the tree |

**Bump mechanics — copy, never move.** A version bump copies the old version
dir to the new version and edits bytes only in the copy; the old dir and its
corpus-manifest rows stay in place, digest-frozen. Moving or in-place-editing a
retained version is a governance violation, not a shortcut. The new version's
rows record the old corpus path as their `source`.

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
   escapes the manifest, nothing listed is missing)
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
