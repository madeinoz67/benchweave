# BenchWeave document taxonomy

> Ratified 2026-09-15 by the principal. Every document and machine artifact in this
> repository belongs to exactly one class; every class has exactly one home and one
> validation regime. New material is routed by class, not by habit: classify by
> mutability and audience, and the row names the home.

| # | Class | Examples | Mutability | Validated by | Home |
|---|-------|----------|------------|--------------|------|
| 1 | Normative machine corpus | schemas, catalogs, vectors, examples | digest-frozen; versioned errata only | devices / registry / execution / interface suites | `standards/<id>/<version>/` |
| 2 | Standards prose companions | `otdp-specification.md`, `execution-contract.md`, `validation-report.md` | versioned with its standard | same suites + link checker | `standards/<id>/<version>/` (whole standard together) |
| 3 | Governance locks | `standards/standards-manifest.json`, `standards/corpus-manifest.json` | row-per-change, CI-gated | manifest gates | `standards/` root |
| 4 | Architecture baseline | `smart-test-gateway-architecture-v1.5.md`, decisions, closure, compatibility | admitted record, near-immutable | closure suite | `docs/` |
| 5 | Acceptance evidence | `acceptance/`, composition reviews | append-only | closure suite | `docs/acceptance/` |
| 6 | Implementation planning | `implementation-planning/` pack | living until close-out | planning suite | `docs/implementation-planning/` |
| 7 | Run / hardware evidence | `evidence/` trees | immutable once landed | provenance stamps | `docs/evidence/` |
| 8 | Guides (plugin author / operator) | device-developer-guide, develop-your-device, dps150-protocol | living | link checker | `docs/` |
| 9 | Plugin-local pinned copies | `plugins/<vendor>/<device>/contracts/` | pinned to a corpus revision | plugin tests | inside the plugin |
| 10 | Working material | `superpowers/`, `internal/`, ISA | ephemeral, local | none | untracked by convention |
| 11 | Public site source | `website/` (static front door), `great-docs.yml`, `index.qmd`, `scripts/assemble_docs_site.py` | living | docs workflow (assembly `verify_tree`) | `website/` + root config; build output (`user_guide/`, `standards_pages/`, `great-docs/`, `site/`) gitignored |

A `standards/<id>/<target>-dev/` directory is the dev stage's staging state of
classes 1–2 (GOVERNANCE "The dev stage"): same homes, same validation regime
— pins, coverage and validate apply exactly as to a released version — but
repin-mutable while the head is open and never exported, synced or packaged;
promotion copies it to the released version and removes it.

## Rules

1. **One home per class.** No class ever exists in two places; a second copy of any
   class is a defect, not a convenience (the pre-2026-09-15 docs/contracts mirror was
   retired for exactly this reason).
2. **No new top-level trees.** A new class must fit an existing home or justify a
   taxonomy amendment to this file.
3. **One package root per validation suite.** Each architecture suite validates a
   single package root (`STANDARDS` or `DOCS`); reads that merely reference the other
   tree use the other injected root but do not widen the suite's scope. The documents
   suite is the declared exception: it walks each tree separately (JSON/schema checks
   over `standards/`, markdown-link checks over each tree) and never merges the walks.
4. **Digest locks move with their corpus.** Manifest rows are relative to the manifest's
   directory, so corpus and lock relocate together without touching digests.
5. **Historical records are not live references.** `source:` provenance fields, the
   compatibility register, planning history and the changelog may name retired paths;
   they are records, not routing.
6. **The public site renders, it does not copy.** Class 11 is the one class that
   *presents* other classes: the docs site stages classes 2 and 8 (and the changelog)
   at build time into gitignored trees and renders them; nothing under `website/` or
   the build output is a second home for any document. Amendment 2026-09-16 admitting
   `website/` as a top-level tree under rule 2.
