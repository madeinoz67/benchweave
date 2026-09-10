# Architecture validation

Architecture contracts are executable review surfaces. The **Architecture
contracts** job in GitHub CI validates them on every push and pull request,
without path filters. Schema violations, contract drift and failed rejection
cases fail the job. Configure this job as a required status check when enabling
GitHub branch protection; adding a workflow alone does not enforce merge rules.

## Run locally

From the project root:

```sh
uv sync --locked --dev
uv run --no-sync pytest tests/contracts -s
```

Run all project tests with `uv run --no-sync pytest`. The architecture suite
uses repository-relative paths and uv-locked `jsonschema` and `referencing`
dependencies. It requires no hardware, credentials or network access after
dependency installation. JSON Schema references resolve from the local baseline.

## Ownership and coverage

The pytest entry point and validation regression tests live in
`tests/contracts/test_architecture.py`. The portable check scripts live in
`scripts/architecture/`; each can also be run with `uv run python`.

| Script | Checked surfaces |
|---|---|
| `check_devices.py` | Descriptor/runtime/measurement/catalog schemas, twelve profiles, fifty action contracts, pinned hashes, vectors, shapes and selected metrology/rejection rules |
| `check_registry.py` | Release metadata, package locks, required evidence, path/version restrictions and selected metadata semantics |
| `check_execution.py` | Procedure scope/bounds, bench resources, commissioning budgets, linked hashes, uncertainty and terminal safety outcomes |
| `check_interface.py` | Twenty REST operations, seventeen MCP tools, schema parity, required fields, error/status mappings, resource limits and stored wire/vector agreement |
| `check_closure.py` | Selected dependency graph conflicts, review coverage and cross-contract safety decisions |
| `check_planning.py` | PRD/work-package coverage, release gates, hardware decisions, stored requirement trace and proposed code syntax |
| `check_documents.py` | JSON syntax/duplicate keys, local schema references and portable Markdown file links |

The first five retain the original 978 review checks, plus three checks against
stored interface/composition fixtures. Planning and document-integrity checks
extend that baseline. Current counts and failures are printed by pytest; counts
in existing validation reports remain historical review evidence.

## Validation safeguards

Eight regression cases mutate temporary copies of the documents to verify that
validation rejects a changed pinned contract, floating package version, unsafe
pass outcome, altered interface vector, altered composition fixture, invalid
requirement trace, broken document link and unresolved schema reference.
A separate test hashes the complete document tree before and after all suites
to ensure validation neither rewrites fixtures nor refreshes its own evidence.
Git attributes preserve LF line endings for digest-sensitive documents.

## Limits and maintenance

These are architectural checks, including selected semantic models and text
invariants. They are not a full runtime conformance suite, OpenAPI meta-validator,
MCP interoperability test, signature verifier, package resolver or physical
safety qualification. Markdown checks verify local file targets, not heading
anchors or availability of external websites.

When changing a contract, add or update its rejection cases and linked fixtures
in the same change. Update pinned fixture hashes only after reviewing the
underlying contract change. Keep validators read-only; CI must report drift
rather than regenerate expected files to make the check pass.
