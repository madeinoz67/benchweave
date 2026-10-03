# BenchWeave document taxonomy

> The principal ratified this taxonomy on 2026-09-15. Every document and machine artifact in this
> repository belongs to exactly one class. Every class has exactly one home and one
> validation regime. New material is routed by class, not by habit. Classify by
> mutability and audience. The row then names the home.

| # | Class | Examples | Mutability | Validated by | Home |
|---|-------|----------|------------|--------------|------|
| 1 | Normative machine corpus | schemas, catalogs, vectors, examples | digest-frozen; versioned errata only | devices, registry, execution and interface suites | `standards/<id>/<version>/` |
| 2 | Standards prose companions | `otdp-specification.md`, `execution-contract.md`, `validation-report.md` | versioned with its standard | same suites + link checker | `standards/<id>/<version>/` (whole standard together) |
| 3 | Governance locks | `standards/standards-manifest.json`, `standards/corpus-manifest.json` | row-per-change, CI-gated | manifest gates | `standards/` root |
| 4 | Architecture baseline | `smart-test-gateway-architecture-v1.5.md`, decisions, closure, compatibility | admitted record, near-immutable | closure suite | `docs/` |
| 5 | Acceptance evidence | `acceptance/`, composition reviews | append-only | closure suite | `docs/acceptance/` |
| 6 | Implementation planning | `implementation-planning/` pack | living until close-out | planning suite | `docs/implementation-planning/` |
| 7 | Run / hardware evidence | `evidence/` trees | immutable once landed | provenance stamps | `docs/evidence/` |
| 8 | Guides (plugin author / operator) | device-developer-guide, develop-your-device, dps150-protocol | living | link checker | `docs/` |
| 9 | Plugin-local pinned copies | `plugins/<vendor>/<device>/contracts/` | pinned to a corpus revision | plugin tests | inside the plugin |
| 10 | Working material | `superpowers/`, `internal/`, ISA | ephemeral, local | none | untracked by convention |
| 11 | Public site source | `website/` (static front door), `great-docs.yml`, `index.qmd`, `scripts/assemble_docs_site.py` | living | docs workflow (assembly `verify_tree`: link resolution and the `stamp_residue:` sweep over every copied file); the stamp contract (`tests/contract/test_website_stamps.py`: map derivation, token coverage both directions, per-card agreement, stamped end state, the class-11 literal ban, the `{{` braces pin) | `website/` + root config; build output (`user_guide/`, `standards_pages/`, `great-docs/`, `site/`) gitignored |

A `standards/<id>/<target>-dev/` directory is the staging area of the dev stage for
classes 1–2 (GOVERNANCE "The dev stage"). It has the same homes and the same
validation regime as a released version. Pins, coverage and validate apply
exactly as to a released version. But the directory is repin-mutable while the
head is open. It is never exported, synced or packaged. Promotion copies it to
the released version and removes it.

## Rules

1. **One home per class.** No class ever exists in two places. A second copy of any
   class is a defect, not a convenience. The project retired the pre-2026-09-15
   docs and contracts mirror for exactly this reason.
2. **No new top-level trees.** A new class must fit an existing home or justify a
   taxonomy amendment to this file.
3. **One package root per validation suite.** Each architecture suite validates a
   single package root (`STANDARDS` or `DOCS`). Reads that merely reference the other
   tree use the other injected root but do not widen the suite's scope. The documents
   suite is the declared exception. It walks each tree separately (JSON and schema
   checks over `standards/`, markdown-link checks over each tree) and never merges
   the walks.
4. **Digest locks move with their corpus.** Manifest rows are relative to the manifest's
   directory, so corpus and lock relocate together with no digest changes.
5. **Historical records are not live references.** `source:` provenance fields, the
   compatibility register, planning history and the changelog may name retired paths.
   They are records, not routing.
6. **The public site renders, but it does not copy.** Class 11 is the one class that
   *presents* other classes: the docs site stages classes 2 and 8 (and the changelog)
   at build time into gitignored trees and renders them. Nothing under `website/` or
   the build output is a second home for any document.

Amendments to rule 6:

- 2026-09-16: `website/` was admitted as a top-level tree under rule 2.
- 2026-09-25 (issue #188, invariants CON-13): version stamps render at assembly
  from the standards manifest's active versions. Claim sites in
  `website/index.html` carry `{{stg-*}}` tokens. No three-component version
  literal is allowed anywhere in the class-11 source set (`website/` plus
  `index.qmd`, `tests/contract/test_website_stamps.py`). Two-component prose
  claims remain the named residual.
- 2026-10-02 (issue #224, invariants CON-13 amendment, rewritten to the pivot
  the same day): the plugin catalogue is generated and served from the registry
  repository. The gateway website carries no registry-derived bytes. The pivot
  deleted the mirror, its pin and the generated panel block that the amendment
  first drafted. The registry repository's own Pages pipeline renders the
  catalogue as a deploy-time artifact. The plugins panel is a static teaser
  with one outbound link and zero catalogue-derived data. The class-11 literal
  scan returns to zero exemptions. There is nothing to exempt.
