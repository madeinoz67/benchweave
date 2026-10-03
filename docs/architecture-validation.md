# Architecture validation

Architecture contracts are executable review surfaces. The **gates** job in
GitHub CI validates them on every push and pull request via
`pytest -q -n auto -m "not timing"`, without path filters. No contract,
schema or rejection test carries the `timing` marker. The deselection
never touches this surface. The real-paced set runs in the dedicated
**timing** lane instead. Schema violations, contract drift and failed
rejection cases fail the job. When you enable GitHub branch protection,
configure this job as a required status check. A workflow alone does not
enforce merge rules.

## Run locally

From the project root:

```sh
uv sync --locked --dev
uv run --no-sync pytest tests/contracts -s
```

Run all project tests with `uv run --no-sync pytest`. The architecture suite
uses repository-relative paths and uv-locked `jsonschema` and `referencing`
dependencies. It needs no hardware, credentials or network access after
dependency installation. JSON Schema references resolve from the local baseline.

## Ownership and coverage

The pytest entry point and validation regression tests live in
`tests/contracts/test_architecture.py`. The portable check scripts live in
`scripts/architecture/`. You can also run each script with `uv run python`.

| Script | Checked surfaces |
|---|---|
| `check_devices.py` | Schemas for descriptors, runtime, measurements and the catalog; 12 profiles; 50 action contracts; pinned hashes, vectors, shapes and selected metrology and rejection rules |
| `check_registry.py` | Release metadata, package locks, required evidence, path and version restrictions, and selected metadata semantics |
| `check_execution.py` | Procedure scope and bounds, bench resources, commissioning budgets, linked hashes, uncertainty and terminal safety outcomes |
| `check_interface.py` | 20 REST operations, 17 MCP tools, schema parity, required fields, error and status mappings, resource limits and stored wire and vector agreement |
| `check_closure.py` | Selected dependency graph conflicts, review coverage and cross-contract safety decisions |
| `check_planning.py` | PRD and work-package coverage, release gates, hardware decisions, stored requirement trace and proposed code syntax |
| `check_documents.py` | JSON syntax and duplicate keys, local schema references and portable Markdown file links |

The first five keep the original 978 review checks, plus three checks against
stored interface and composition fixtures. Planning and document-integrity
checks extend that baseline. Pytest prints the current counts and failures.
The five family reports are the active versions of otdp, registry, execution
and interface (`standards/<id>/<version>/validation-report.md`), plus the
closure review (`docs/acceptance/validation-report.md`). The validators
write each family report. `tests/contracts/test_architecture.py` byte-pins
each committed file to a live sorted render. A corpus or check change reruns
that suite's `uv run python scripts/architecture/check_<suite>.py
--write-report` in the same change. Superseded versions' reports and
plugin-ui's train records remain historical evidence. They are never
regenerated.

## Validation safeguards

Eight regression cases mutate temporary copies of the documents. They make
sure that validation rejects:

- a changed pinned contract
- a floating package version
- an unsafe pass outcome
- an altered interface vector
- an altered composition fixture
- an invalid requirement trace
- a broken document link
- an unresolved schema reference

A separate test hashes the complete document tree before and after all
suites. It makes sure that validation does not rewrite fixtures and does
not refresh its own evidence. Git attributes preserve LF line endings for
digest-sensitive documents.

## Limits and maintenance

These are architectural checks, including selected semantic models and text
invariants. They are not any of these:

- a full runtime conformance suite
- an OpenAPI meta-validator
- an MCP interoperability test
- a signature verifier
- a package resolver
- a physical safety qualification

Markdown checks look at local file targets, not heading anchors or
availability of external websites.

When you change a contract, add or update its rejection cases and linked
fixtures in the same change. Review the underlying contract change before
you update the pinned fixture hashes. Keep validators read-only. CI must
report drift, not regenerate expected files to make the check pass. The
author-side exception is the machine-written report family. Each suite's
`uv run python scripts/architecture/check_<suite>.py --write-report` is
its explicit regeneration path. It refuses to write when any check fails.
The suite byte-pins the committed file to a fresh render.
