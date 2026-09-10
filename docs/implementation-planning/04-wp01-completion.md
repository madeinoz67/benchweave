# WP01 Completion — Environment Lock, Namespace Re-Baseline, Next Task Expansion

> Records the state the first slice landed against (2026-09-10), reconciles the
> planning pack with the repository that now exists, and expands the next WP01
> task. Companion to `03-first-slice-plan.md`; the PRD and delivery plan remain
> the controlling scope.

## Environment lock (recorded, not aspirational)

Locked by `uv.lock` (committed) and verified on the development machine:

| Component | Exact version |
|---|---|
| Python | CPython 3.13.13 (macOS aarch64) |
| uv | 0.11.16 (135a36367, 2026-05-21) |
| pytest | 9.1.1 |
| mypy (strict) | 2.3.1 |
| ruff | 0.16.6 |
| jsonschema | 4.26.0 (Draft 2020-12 via `referencing`) |
| referencing | 0.37.0 |
| rpds-py | 2026.6.3 |
| attrs | 26.1.0 |
| hatchling | build backend per `uv.lock` |

Operational gotcha observed twice on 2026-09-10: the uv editable install can
rot (site-packages retains `_editable_impl_benchweave.pth` +
`benchweave-0.1.0.dist-info` but `import benchweave` fails, and plain
`uv sync` does not heal it). Heal: `rm -rf .venv && uv sync`. Cheap first aid
to try before the wipe: `uv sync --reinstall-package benchweave`.

## Namespace re-baseline — stg → benchweave

The planning pack was authored against a *proposed* repository
(`smart-test-gateway`, Python namespace `stg`). The repository that exists is
**BenchWeave** with namespace `benchweave`. Mapping, authoritative for all
future task execution:

| Plan says | Reality in this repo |
|---|---|
| `src/stg/content/json_document.py` | `src/benchweave/content/json_document.py` (shipped, commit `47d0150`) |
| `PYTHONPATH=src python -m pytest ...` | `uv run pytest ...` (editable install; never PYTHONPATH games) |
| `smart-test-gateway` repository root | `/Users/seaton/Documents/src/BenchWeave` |
| future-repository file specs (`contracts/`, `tests/contract/`) | same paths, this repo (`contracts/` and `tests/contract/test_baseline.py` shipped) |

**Schema `$id`s are NOT renamed.** The `otdp`, `registry`, `execution` and
`interface` schema identities are protocol-family names pinned by the
architecture closure (STG 1.5), exactly like `MCP 2026-07-28` is a protocol
name independent of any implementation repository. BenchWeave implements the
STG contract family; it does not rename it.

## Vendored contracts (WP01 "vendored contracts" outcome)

`contracts/` holds the admitted corpus byte-identical to
`docs/{otdp-v0.3.0,registry-v1.0.0,execution-v1.0.0,interface-v1.1.0}` — 48
JSON files plus `contracts/manifest.json` (per-file SHA-256 + closure
identity). Obsolete interface 1.0.0 is intentionally absent.
`tests/contract/test_baseline.py` verifies: manifest completeness, hash
fidelity against both `contracts/` and the `docs/` sources, strict JSON
discipline, Draft 2020-12 reference resolution (mirroring
`scripts/architecture/check_documents.py` semantics, including the
mcp-tools per-tool roots and the operation-catalog shared `$defs` splice),
obsolete-version absence, and tamper detection (a flipped byte must fail).

## Expanded next WP01 task — schema identity and reference admission

Build on `benchweave.content.json_document` (byte integrity, shipped) the
admission layer that decides whether a *validated* document may enter the
system as a contract:

1. **Local schema-ID validation** — every admitted document carrying `$id`
   must use an `https:` absolute URI whose authority belongs to the admitted
   contract families; unknown authorities are rejected
   (`unknown_schema_authority`).
2. **Cross-document reference admission** — every external `$ref` must resolve
   within the vendored corpus registry; references outside the corpus
   (including the vendored `docs/` copies it must stay byte-equal to) are
   rejected (`unresolvable_reference`).
3. **Cycle rejection** — reference chains that revisit a document cycle are
   rejected (`reference_cycle`), not recursed into.
4. **Remote fetch ban** — resolution NEVER performs network I/O; there is no
   code path that turns a `$ref` into a download (`remote_ref_forbidden` is
   raised structurally: the resolver is built only from local resources).
5. Failure taxonomy follows `DocumentRejected` (same exception family as the
   decoder), each distinct reason machine-matchable.

Test shape: table-driven over `contracts/` fixtures plus crafted rejections
(unknown authority, dangling ref, cyclic pair, remote-scheme ref). RED first.

## Persistence and content-store constraints (definition required before disk-backed admission)

Before any module connects `load_document` to a disk-backed content store,
these constraints are binding on the design (tests must pin the implemented
boundary, not assume the pure function is a store):

- **Atomic admission**: a document is either fully present (bytes + digest +
  metadata) or fully absent; there is no observable intermediate state after a
  crash at any point (write-temp + atomic rename, fsync before rename).
- **Immutability**: admitted bytes never change in place; supersession writes
  a new entry and atomically repoints the index (the vendoring tests already
  model this: manifest + byte-identity).
- **Quotas**: a per-store byte ceiling and per-document `max_bytes` are
  enforced BEFORE any write is attempted (`store_quota_exceeded`), so a
  hostile document cannot fill the disk as a side effect of admission.
- **No implicit I/O**: importing the store module opens nothing; opening the
  store is explicit and fails closed (`store_unavailable`).
- The decoder stays pure: the store consumes `JsonDocument`; it does not
  re-parse bytes.

## Sequencing

With WP01 complete, WP02 (MCP/client risk spike) and WP03 (durable state)
may proceed per the delivery plan's dependency graph; hardware discovery
(WP10) remains parallel and evidence-gated.
