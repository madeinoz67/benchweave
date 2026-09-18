# Adapter API version: identity-block declaration + cross-repo protocol agreement (issue #44)

Status: proposed · Date: 2026-09-18 · Evidence base: working tree at `main` = `bbd1b38`
(clean; `packages/sdk` initialized at gitlink `908a1f6` = "vendor otdp 0.1.1"). All file
claims below were read from that tree this session. SDK standalone checkout
(`~/Documents/src/benchweave-sdk`, HEAD `b4c9045`) was consulted as a second source and is
one commit BEHIND the pinned submodule — every claim attributed to "the pinned SDK" was
verified in `packages/sdk`, not the standalone copy.

## 0. Root cause, established

The adapter API version ("1.1") has exactly one machine authority: the vendored OTDP
descriptor schema's `$defs.adapter.properties.api_version` `const`. Verified present and
equal in both retained trees:

- `standards/otdp/0.1.0/otdp-device-descriptor.schema.json` → `{"const": "1.1"}`
- `standards/otdp/0.1.1/otdp-device-descriptor.schema.json` → `{"const": "1.1"}`

Nothing else is machine-checked:

1. **The corpus-manifest identity block is decorative.** `manifest.py:_corpus_pins`
   (src/benchweave/standards/manifest.py:71-76) reads only the `files` rows;
   `load_manifest` reads `standards/standards-manifest.json` (a different file);
   `export.py:export_bundle` writes `bundle-manifest.json` with only
   `bundle_version`/`exported_from`/`standards`; `check.py` and the SDK's
   `standards_sync.py:_load_bundle` parse none of `identity`. An unknown or wrong
   `identity.*` key passes every gate today.
2. **The adapter protocol is hand-mirrored with no cross-repo check.** The mirror is
   `_Context` + the adapter-call/envelope validation in `src/benchweave/host/otdp_bridge.py`
   (NOT `host/plugin.py`/`host/services.py` — those are the internal host ABI; they share
   only a class name with the SDK surface). The SDK side is
   `packages/sdk/src/benchweave_sdk/interfaces.py`. The only current agreement check is the
   release smoke (`scripts/sdk_smoke.py:101-102` asserts the installed SDK's constants).
3. **The drift is live, not hypothetical.** Measured at HEAD with gates green:
   `docs/device-developer-guide.md:13` says "OTDP 0.1.0 · adapter API 0.1.0",
   `:17` says "async adapter API 0.1.0", `docs/ai-device-reviewer.md:64` says
   "adapter API 0.1.0" — the 2026-09-16 reset swept the adapter version in prose while the
   schema const stayed 1.1, and the OTDP errata (0.1.0→0.1.1, released 2026-09-18) left the
   same lines stale. No gate fired. The SDK-side reset sweep incident (SDK PR #20) is the
   same defect class on the other repo.

So the increment: declare the version where the corpus already declares non-standard
versions, derive-check the declaration against the schema const, and pin the protocol
mirror three-way in CI. Build, don't NOT-build — but build exactly this and nothing more.

## 1. Mechanism

### Leg 1 — identity declaration + derivation check (version authority)

1. `standards/corpus-manifest.json` → `identity` gains `"adapter_api": "1.1"`, following
   the existing non-standard precedent `"mcp": "2026-07-28"` (GOVERNANCE.md "Deliberately
   versioned elsewhere"). The descriptor schema const stays the single authority: the
   manifest value is a *declaration that is verified*, never trusted (mirrors the SDK-side
   derivation-test direction from SDK PR #20, main-side).
2. `src/benchweave/standards/manifest.py` gains:
   - `load_identity(root) -> dict[str, str]` — reads `identity` from corpus-manifest.json
     (fail-closed on missing/`non-dict` with a `StandardsError`);
   - `validate_identity(manifest, root) -> None` — raises `StandardsError` with
     machine-matchable prefixes:
     - `identity_adapter_api_absent:` the key must exist (absence is a failure, not a
       default — this is what turns "tolerated" into "checked");
     - `identity_otdp_descriptor_missing:` the active otdp entry's normative list does not
       name `otdp-device-descriptor.schema.json` (fail-closed before any read);
     - `identity_adapter_api_mismatch:` `identity["adapter_api"]` !=
       `const` at `$defs.adapter.properties.api_version` of
       `standards/otdp/<active-version>/otdp-device-descriptor.schema.json`, where
       active-version comes from the otdp `StandardEntry` of `standards-manifest.json`.
       The const must exist and be a `str` (structural guard, fail-closed).
3. Wiring — one call site: `export.py:export_bundle` calls `validate_identity` right after
   `validate_manifest` (export.py:20-21), inside the existing validate-before-write
   contract. This rides, with zero CI change: `make check-sdk-standards` (CI `gates` job,
   via `benchweave.standards check` → `run_check` → `export_bundle`), `make
   sync-sdk-standards` steps 2-3, and any bare `export`.
4. Sync-time visibility: `check.py:version_lines` gains one line
   `adapter api {value}` (from `load_identity`) after the standard lines —
   `benchweave.standards versions` is the last step of `sync-sdk-standards`, so the
   declared adapter API prints at every sync.
5. `standards/GOVERNANCE.md` "Deliberately versioned elsewhere" gains: *the adapter API
   version — declared in the corpus-manifest identity block, authority is the descriptor
   schema's `$defs.adapter.api_version` const; identity-block edits move no corpus rows
   and need no repin.*

Consequence of the wiring (important, and simpler than the issue assumed): the identity
block is NOT part of the exported bundle (export.py writes only `standards` rows), so this
manifest edit produces **no SDK diff — no lock update, no submodule pointer commit, no
two-repo dance in this increment**. Two-repo discipline is satisfied vacuously. Verified:
`_load_bundle` (standards_sync.py:93-109) reads only `bundle_version` + `standards`.

### Leg 2 — cross-repo protocol agreement test (`tests/sdk/test_adapter_agreement.py`, new)

**Import discipline** (extends the existing pattern at `tests/sdk/test_sdk.py:9-16`):

- `SDK_SRC = ROOT / "packages" / "sdk" / "src"`. If absent: `pytest.fail` when `CI` is set
  (CI always checks out submodules recursively — ci.yml:14), else `pytest.skip` with a
  reason naming `git submodule update --init packages/sdk`.
- `sys.path.insert(0, str(SDK_SRC))`, then import `benchweave_sdk.interfaces` and **assert
  provenance**: `Path(interfaces.__file__).is_relative_to(SDK_SRC)`. This guard is not
  optional — measured this session, the main venv carries
  `_editable_impl_benchweave_sdk.pth` → `~/Documents/src/benchweave-sdk/src` (an editable
  install of the STANDALONE checkout, which is stale relative to the pinned submodule).
  A bare `import benchweave_sdk` here resolves to the wrong tree; `sys.path.insert(0)`
  wins only when the submodule path exists, and the provenance assertion makes the source
  unambiguous either way. (The existing `test_sdk.py` lacks this guard — see Deferrals.)

**Comparison structure — three-way, expected ↔ SDK ↔ gateway.** Each comparison pins an
expected literal in the test and requires BOTH sides to equal it. This is the anti-tautology
property: any mover (SDK protocol change, gateway mirror change, or stale expectation)
fails, and a new SDK member breaks `SDK ≠ expected` even when the gateway is unchanged,
forcing a conscious allowlist update rather than silent narrowing.

1. **Context.** SDK `OperationContext` protocol members (data: `operation_id`,
   `dataset_id`, `deadline_monotonic`; methods: `is_cancelled` sync 0-arg,
   `mark_dispatch_started` async 0-arg) vs `benchweave.host.otdp_bridge._Context`.
   Compare member-name sets, and per method: arity, keyword-only-ness, coroutine-ness
   (`inspect.signature` + `inspect.iscoroutinefunction`).
2. **Adapter call surface.** Mechanically extract what the bridge actually calls: AST-walk
   `otdp_bridge.py` for `Attribute` nodes on `self._adapter` → the set (today
   `{"open", "execute", "close"}`) is asserted equal to the extracted set, and each member
   must exist on the SDK `Adapter` protocol with matching arity/kwonly/awaitability;
   request/execute/close signatures compared parameter-name-exact. The full SDK `Adapter`
   member set must equal expected ∪ documented gaps (below) — so an SDK-side
   `next_event` removal (or addition) fails the test, not just a gateway change.
3. **Envelopes and vocabularies, against the corpus (the machine authority).** The runtime
   schema — NOT the SDK docstrings — states the envelope shapes; compare the bridge's
   enforced literals to the ACTIVE tree (`standards/otdp/<active>/otdp-runtime.schema.json`):
   - request keys `{"operation_id","verb","arguments"}` == `$defs.operationRequest.required`
     (verified equal today, plus `additionalProperties: false` in the schema);
   - success keys `{"operation_id","verb","status","data"}` ==
     `operationResult.properties` − `error`; error-path keys == properties − `data`
     (matches the schema's ok→data / else→error conditional structure);
   - error object keys `{"code","message","dispatch_state"}` == `$defs.error.required`;
   - vocabulary equality, gateway StrEnum value-sets (src/benchweave/host/types.py) ==
     schema enums: `ErrorCode` (10) ↔ `$defs.error.properties.code.enum`,
     `DispatchState` (3) ↔ `dispatch_state.enum`, `OperationStatus` (4) ↔
     `operationResult.properties.status.enum`, `OperationVerb` (10) ↔ `operationRequest.
     properties.verb.enum`. All four verified equal today.
4. **Version triplet.** `benchweave_sdk.ADAPTER_API_VERSION` (from the pinned submodule
   import) == corpus `identity.adapter_api` == active descriptor schema `const`. This is
   the cross-repo version agreement the release smoke currently holds alone; the smoke
   stays as the installed-distribution check at release.

**Documented-gap allowlist** (each row: asserted present on the SDK side, asserted absent
or unused gateway-side, one-line reason — so a future SDK change to any gapped member
breaks the allowlist's own presence assertion and forces review):

- `Adapter.next_event` — declared by the SDK protocol, never called by the bridge
  (identify/read/write only; otdp_bridge.py module docstring).
- `HostServices.transfer/utc_now/record_evidence/close_transport` — the gateway exercises
  only the monotonic-clock subset; the bridge's structural requirement is exactly
  `callable(getattr(services, "monotonic", None))` (otdp_bridge.py:72-73). No gateway-side
  implementation of the full SDK `HostServices` exists anywhere in `src/benchweave`.
- `CaptureServices` (`artifact_append/finalise/abort`) — SDK-only surface.
- `_Context.dataset_id` — pinned present on both sides; always `None` from the bridge.
- **Extension-key delta (pre-existing, now pinned):** the runtime schema permits
  `^x-…` extension keys in the error object (`patternProperties`), while the bridge's
  closed-set check `set(error) != {"code","message","dispatch_state"}` (otdp_bridge.py:248)
  rejects schema-legal extensions. Recorded as intentional gateway strictness; if either
  side changes, this row surfaces it.

## 2. Minimal first increment — and what it defers

**In scope (one PR, main-repo side only):**

| File | Change |
|---|---|
| `standards/corpus-manifest.json` | `identity.adapter_api: "1.1"` (one line) |
| `src/benchweave/standards/manifest.py` | `load_identity` + `validate_identity` |
| `src/benchweave/standards/export.py` | one `validate_identity` call |
| `src/benchweave/standards/check.py` | one `adapter api` line in `version_lines` |
| `tests/standards/test_manifest.py` (or sibling) | RED-pinned tmp-root tests for the three prefixes |
| `tests/sdk/test_adapter_agreement.py` | new, as §1 Leg 2 |
| `standards/GOVERNANCE.md` | "Deliberately versioned elsewhere" entry |
| `docs/internal/invariants.md` | CON-8 + REG-4 amendments (§4) |
| `docs/internal/drift-and-obligations.md` | new obligation row + CI-map note |
| `docs/device-developer-guide.md:13,17`, `docs/ai-device-reviewer.md:64` | baseline-line corrections to machine truth (prose defers to machine sources — this is the measured live drift, §0.3) |

No SDK-repo commit, no lock change, no pointer bump, no CI workflow change, no repin
(identity is not a `files` row; corpus-manifest.json is not self-pinned).

**Explicitly DEFERRED:**

1. Promotion to a seventh corpus standard carrying a canonical importable Python contract
   (the issue's recorded trigger: when the adapter surface stabilizes). This increment
   records the trigger in GOVERNANCE; it does not build it.
2. SDK-side `@runtime_checkable` on the Protocols (isinstance sugar; manual inspect
   comparison is sufficient and stricter — runtime_checkable does not check signatures).
3. Migrating `tests/sdk/test_sdk.py` to the provenance-pinned loader. Live latent issue,
   out of scope: with a deinitialized submodule its `find_spec` resolves the editable
   standalone install, so those tests silently run against an uncontrolled tree locally
   (CI is unaffected — no editable install there). File as an issue; fix separately.
4. Making `scripts/sdk_smoke.py` derive its expected constants from the corpus manifest
   instead of literals (same derivation principle, release-time surface).
5. Deciding whether the bridge should accept schema-legal `^x-` error extensions — this
   increment documents the delta, does not change bridge behavior.
6. The OTDP 0.1.1 prose sweep beyond the two baseline lines named above (e.g.
   `docs/smart-test-gateway-decisions.md:93` says "adapter API 0.1.0" inside a historical
   decision record — maintainers should decide annotate-vs-edit; not this increment).
7. `HostServices`-subset narrowing: implementing `transfer`/evidence services gateway-side
   is new host capability, not agreement checking.

## 3. Precedent

- `tests/sdk/test_sdk.py:9-16` — the `sys.path.insert(0, packages/sdk/src)` SDK-import
  pattern this test extends (plus the provenance guard it lacked).
- SDK `tests/test_version_constants.py` (PR #20) — derive-expected-values-from-the-corpus;
  Leg 1 is the same discipline, main-side, wired into the export gate rather than a test.
- `src/benchweave/standards/export.py:18-27` — validate-before-any-write; the wiring point.
- `tests/standards/test_manifest.py:61-80` — the tmp-root copy-and-corrupt RED pattern for
  manifest validation failures (reused for the identity prefixes).
- `standards/GOVERNANCE.md` "Deliberately versioned elsewhere" — the `"mcp": "2026-07-28"`
  identity-block precedent for a declared non-standard version.
- mypy `files` already includes `packages/sdk/src` (pyproject.toml) — the initialized
  submodule is already the dev-gate norm; the new test adds no new environment assumption
  beyond what bare `uv run mypy` already requires.

## 4. Invariant and drift impacts

- **New CON-8 (proposed):** the corpus identity block's `adapter_api` is derived-checked
  against the active OTDP descriptor schema's `$defs.adapter.api_version` const at every
  export/check; absence fails (`identity_adapter_api_absent`). *Without it the identity
  block stays decorative and the next reset sweep re-creates the PR-20 incident main-side.*
- **New REG-4 (proposed):** the gateway's OTDP adapter mirror (`_Context`, the bridge's
  adapter call set, envelope key-sets, and the four vocabularies) is pinned three-way
  (expected ↔ SDK protocol ↔ gateway code) by `tests/sdk/test_adapter_agreement.py` in
  every CI run; documented gaps are allowlisted with reasons and their own presence
  assertions. *The hand-mirror is otherwise checked only at release smoke.*
- GOVERNANCE.md: amendment to "Deliberately versioned elsewhere" only — **no standard
  version bump, no corpus rows move** (copy-never-move untouched; CON-7/repin untouched).
- `docs/internal/drift-and-obligations.md`: new row — "the adapter protocol surface
  (SDK `interfaces.py` ↔ `host/otdp_bridge.py`) or the descriptor schema const changes →
  the agreement test and `identity.adapter_api` move in the same change" (🪝-eligible on
  both paths); CI-map `gates` row gains the agreement test under `pytest -q`.
- On-disk format/schema? `corpus-manifest.json` gains one non-pinned identity key; bundle
  format, lock format and all standard bytes are unchanged — Tier-3 exposure is nil, but
  the review should confirm no row digests moved (`git diff standards/corpus-manifest.json`
  must touch only `identity`).
- Surfaces: MCP tools/REST/CLI/operator docs — untouched except the two baseline-line
  corrections (operator/device doc prose). Device-developer guide moves per obligation 3.

## 5. Measurable proof — pre-committed acceptance rule

Written before any test run. This increment's effect is deterministic, so the rule is
stated in pass/fail terms with RED demonstrations, not sample sizes.

**Baseline (measured, at HEAD `bbd1b38` with all gates green):** version disagreement
between the schema const, the SDK constant, and prose is caught only by the release smoke
(`sdk_smoke.py:101-102`), at release time; protocol-shape drift is caught by nothing
in-tree. Three doc surfaces currently carry a wrong adapter API version and one also a
stale OTDP version (§0.3).

**After (the claim):** every `gates` CI run (push) catches (a) manifest↔schema↔SDK-constant
version drift, (b) protocol member/signature drift either repo, (c) envelope/vocabulary
drift between bridge and corpus schema.

**RED demonstrations (must be shown failing before the fix, per repo discipline):**

- R1: a tmp-root corpus with `identity.adapter_api` absent → `identity_adapter_api_absent`;
  set to `"1.0"` → `identity_adapter_api_mismatch`. (tmp-root pattern; the real tree is
  never mutated.)
- R2: run the comparator against a mutated COPY of `interfaces.py` (rename
  `mark_dispatch_started`; add a keyword-only arg to `execute`; drop `dataset_id`) — each
  mutation must fail its own comparison. This proves the comparator detects drift rather
  than re-asserting the gateway against itself.
- R3: a scratch copy of the runtime schema with one `dispatch_state` enum value renamed →
  vocabulary comparison fails.
- R4 (honesty of the skip): with the submodule absent and `CI=true`, the agreement test
  FAILS (not skips).

**Ship rule:** all four RED classes fail as designed AND the pristine tree passes with the
submodule initialized (`uv run pytest tests/sdk tests/standards` green, `make
check-sdk-standards` green).

**Kill directions:**

- *Kill:* any RED class passes → the check is tautological or the skip dishonest; fix
  before shipping, do not weaken the expectation literals to make it pass.
- *Kill:* the pristine run fails → the gateway and pinned SDK have ALREADY drifted; that
  is a surfaced finding to resolve on its merits (possibly a real SDK fix), never a reason
  to delete the test.
- *Underpowered rather than conclusive:* not applicable — deterministic structural checks,
  no sampling; if a mutation class "cannot be constructed" (e.g. the comparator cannot see
  the member at all), that IS the kill condition above.

**CI cost:** zero new jobs/minutes of substance — one JSON load in an existing gate, one
test module in the existing `pytest -q`.

## 6. Top risks, each with its falsifier

1. **Structure ≠ semantics.** The test pins names/arity/awaitability/key-sets, not
   behavior — a signature-compatible semantic change (e.g. redefining the deadline's clock
   units in the SDK docs) passes. Falsifier/migration: this is precisely the recorded
   promotion trigger (§2.1); until then the expected-set pinning is the honest boundary.
   The design says what it does not catch, inline (rubric G4).
2. **The editable-install shadow** (measured, §1 Leg 2): a future refactor that drops the
   provenance assertion re-opens silent testing against the stale standalone tree locally.
   Falsifier: R4 + provenance assertion; the guard fails loudly.
3. **Exception-vs-failure-line shape:** identity errors raise `StandardsError` out of
   `export_bundle` inside `run_check` (printed as `standards check error: …`, exit 1)
   rather than joining `run_check`'s failure-line list. Cosmetic inconsistency; consistent
   with `load_manifest`/`validate_manifest` raises. If review prefers lines, the change is
   confined to `run_check`.
4. **Manifest hand-edit confusion:** contributors may fear an identity edit needs `repin`.
   GOVERNANCE's new entry states it does not; `git diff` touching only `identity` is the
   review check.
5. **Allowlist rot:** the gap rows are the part of the test most likely to be "updated to
   green" under pressure. Mitigated structurally: each gap's own presence assertion
   (e.g. `next_event` must still exist SDK-side) turns silent narrowing into a visible
   diff in the expected sets.

## 7. Verification-basis note

Evidence gathered by direct file reads at `main` = `bbd1b38` (clean tree) and the pinned
submodule at `908a1f6`; the SDK standalone checkout was used only as a contrast source and
is stale (`b4c9045`, vendored corpus at otdp 0.1.0) — nothing in this design depends on it.
Gortex graph tools were unavailable in the authoring session (subagent without bound MCP
functions); all citations are file-and-line from the working tree.
