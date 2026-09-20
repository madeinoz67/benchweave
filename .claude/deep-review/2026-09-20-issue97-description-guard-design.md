# Issue #97 side-item — extend the #47 annotation guard to `description`

- Date: 2026-09-20
- Status: design (pre-implementation, `feat/issue97-description-guard`)
- References: issue #97 re-scope comment 5748876078 ("side-items, not churn fixes"); PR #47's guard `test_vendored_schema_titles_match_standard_version` (`tests/standards/test_manifest.py:62-78`)
- Diff class: tests + one small helper refactor; NO `standards/` bytes, NO corpus, NO manifests — Tier ≤2 by the rubric (not "anything under standards/")

## 1. Measurement (the design input)

Every normative `*.schema.json` in `standards-manifest.json` swept for version-like
strings in `title` and `description` against its standard's active version:

- `description` hits: exactly 1 — `standards/otdp/0.2.0/otdp-device-descriptor.schema.json`
  naming `0.2.0`, its own. Zero stale, zero cross-standard.
- The evidence sweep's "21 schema descriptions" (EVIDENCE-annotations-and-versions.md,
  a local-untracked read-only-sweep artifact at the main-checkout root) reconciles
  two ways: 17 are nested tool descriptions inside `interface/0.1.0/mcp-tools.json`,
  excluded by the guard's `*.schema.json` filter; the other 3 are descriptors in
  SUPERSEDED otdp dirs (0.1.0–0.1.2), excluded because the guard reads only the
  active manifest's normative list. The guard-relevant set is the one file above.

So the extension lands on a clean tree: no corpus fix, no bump, no repin.

## 2. Mechanism

Extract the existing loop into `_annotation_offenders(standards_root)` returning the
offender list, with the annotation key parametrized over `("title", "description")`
— same rule verbatim: any `\d+\.\d+\.\d+` in the annotation that is not the entry's
active version is reset residue. Three arms:

1. Real tree: zero offenders on both keys (the existing assertion, now double-keyed).
2. Planted tmp tree, STALE DESCRIPTION with a clean title → refusal names the
   description key (the RED-honesty arm: the pre-change guard reads titles only, so
   this arm fails before the change — the extension is not self-greening).
3. Planted tmp tree, versionless annotations → passes (pins the "no version at all
   is fine" semantics on both keys, the #47 rule's explicit half).

Residual, stated: a future description that legitimately cites ANOTHER standard's
version trips the guard — correct by this guard's rule (annotations name their own
version or none, the ratified #47 semantics); the fix is rewording the prose, not
loosening the guard.

## 3. Proof — pre-committed acceptance

- RED: arms 2-3 fail at the pre-change tree (helper absent; the planted description
  case cannot pass a title-only reader). Watched, quoted.
- GREEN: 3/3 arms + the full `tests/standards/` lane green; ruff clean; strict mypy
  on the test file clean (tests are inside the mypy gate's `files`).
- Kill: if the real tree has a description offender at build time (it did not at
  measurement), the increment STOPS — that is a corpus byte fix, i.e. a PATCH bump
  under the train window, its own arc, not a guard extension.

## 4. DON'T-BUILD

Not triggered: one guard, parametrized over the two annotation keys the corpus
actually carries (`$comment`: zero occurrences, per the evidence sweep — not added
speculatively).
