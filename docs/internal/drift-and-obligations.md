# Cross-surface obligations, drift risks, and the CI map

BenchWeave has many surfaces that must stay in sync but mostly *aren't* checked
automatically. This is where "you changed X but didn't update Y" bugs live. A reviewer must
walk this list for any PR that touches a synced surface — the review rubric's G5 gate is
the obligation; this file is the detail behind it.

Obligations marked 🪝 are additionally warned about by `.claude/hooks/drift-guard.mjs`, a
PostToolUse hook that fires when Claude Code edits the triggering path. It is a reminder,
not a gate: it warns once per session, stays quiet if you have already touched the
corresponding surface, and never blocks. The unmarked obligations need judgment or a build,
and remain the reviewer's job.

## "If a PR touches X, it must also do Y"

1. **An MCP tool change** (tool set, parameters, output schema) 🪝 → the vendored corpus is
   the authority: `standards/interface/0.1.0/mcp-tools.json` plus any schema it references.
   The gateway pins tool schemas verbatim to the corpus (invariants CON-3), so a gateway
   change and a corpus change cannot land separately — normative standards changes start
   in this repository and sync out to the SDK. If the operation surface moved,
   `operation-catalog.json` moves too.

2. **An API-visible change** 🪝 → `standards/interface/0.1.0/openapi.json` (and
   `interface.schema.json` when the envelope changes). There is no spec linter in CI —
   field-level drift is the reviewer's eye, not a gate.

3. **Plugin/device-visible behavior** (packaging, loading, policy, lifecycle) →
   `docs/device-developer-guide.md`.

4. **Operator-visible behavior** 🪝 (service, config, CI) → `docs/operator-guide.md` and
   `README.md`. **CLI behavior** (`src/benchweave/cli/`) → the CLI reference in the
   operator docs.

5. **The fixture lattice** 🪝 → all four in lockstep: `fixtures/registry/` ↔
   `scripts/registry/build_fixtures.py` ↔ `catalogue.json` ↔ the digest-pinning tests.
   Fixtures without the builder, or a rebuilt lattice without regenerated digests, is
   silent drift. **CI materialises the fixture signing keys from repo secrets**
   (`main.pem`, `originb.pem`) — any test whose outcome depends on those secrets must
   match the workflow's materialisation, and a workflow change gets a cold full-suite run,
   not a warm local one.

6. **Vendored contract bytes** 🪝 → `standards/corpus-manifest.json` byte-pins move with any
   vendored change, and `make check-sdk-standards` (CI `gates` job) must stay green: it
   refuses drift between the main-repo standards, the SDK lock and the vendored tree.
   Pins move via `uv run python -m benchweave.standards repin` (the loop is
   edit → repin → export); hand-splicing digests is not a path.
   A dev head's rows follow the same loop (dev pins are validated like active
   pins); promotion of a head carries the FULL bump obligation set — this row
   plus 7/8/13 — with the dev directory as the copy source and the block/rows/
   directory teardown as part of the bump (GOVERNANCE "The dev stage").
   The manifest's `sdk_compatibility` mirror moves with the SDK lock's
   `compatibility` block — `standards check` refuses drift
   (`sdk_compatibility_drift`, mirror ↔ lock, and `sdk_version_unanchored`,
   lock ↔ the pinned SDK's pyproject; invariants CON-12) — and `matrix --check` is
   checkout-invariant: it renders committed state only (manifest + mirror +
   `pyproject.toml` `[project.urls]` + `.gitmodules`), so fork and
   uninitialised-submodule checkouts render byte-identical upstream bytes.

7. **The `packages/sdk` pointer** → the submodule commit must **exist and be pushed** to
   the SDK remote before the pointer lands here — CI checks out submodules by SHA, so an
   unpushed commit is invisible there and breaks `gates`. **Version-pairing**: a pointer
   advance that moves the SDK's own version pairs the regenerated SDK lock, the moved
   `sdk_compatibility` mirror, and the re-rendered `docs/compatibility-matrix.md` in the
   same landing — the PR #189 shape (`4d7f6bc`: matrix + pointer + manifest + test in one
   merge, closing #187) and the PR #154 shape (`18009ce`, closing #153: pointer + in-tree
   dependents together) — with `make check-sdk-standards` as the mechanical half: it
   anchors the lock's `compatibility.sdk` to the pinned SDK's own pyproject
   (`sdk_version_unanchored`), so a stale lock reds at pointer-advance time.
   **Renderer freshness**: the `ui`
   job rebuilds the preview renderer (`npm --prefix ui run build:preview`) and fails on any
   diff in the SDK's committed `preview_assets` — a UI change that leaves the committed
   renderer stale ships silently in the wheel.

8. **The adapter protocol surface** 🪝 (the SDK protocol
   `packages/sdk/src/benchweave_sdk/interfaces.py` ↔ the gateway mirror
   `src/benchweave/host/otdp_bridge.py` ↔ the descriptor schema's
   `$defs.adapter.api_version` const; `standards/standards-manifest.json` selects the
   active versions the identity block derives from, and
   `packages/sdk/src/benchweave_sdk/__init__.py` carries the SDK-side
   `ADAPTER_API_VERSION` constant) → the full bump touch-set moves in the same change:
   the agreement test (`tests/sdk/test_adapter_agreement.py`), the corpus identity
   declaration (`standards/corpus-manifest.json` `identity.*`), the manifest
   versions when a standard bumps, the descriptor schema const, both SDK files, and
   the orphan identity literal in `tests/contract/test_baseline.py`
   (`test_manifest_identity_pins_admitted_versions`). `make check-sdk-standards`
   carries the identity-vs-schema/manifest derivation checks; the agreement test
   carries the protocol shape (invariants CON-8/REG-4). The SDK-tree mirror family
   has a second gate: the descriptor-semantics census
   (`tests/sdk/test_descriptor_equivalence.py`) pins the gateway's S01/S02 mirrors
   equivalent to the SDK checker over the in-tree corpus (CON-10) — a semantics
   bump on either side surfaces there.

9. **`deploy/systemd/` templates** 🪝 → the `systemd` CI job renders the template and
   `systemd-analyze verify`s it against rehearsed preconditions (dedicated user, one
   writable data dir, env file). The `{{`-absence assertion in `tests/cli/test_serve.py`
   catches placeholder misses that `systemd-analyze verify` tolerates — the CI job's own
   comment says do not simplify that test away; the two catch complementary failure modes.

10. **A dependency change** 🪝 → `pyproject.toml` and `uv.lock` together, CI in the same
    change when the dependency changes what CI must install or materialise.

11. **Key/secret handling** → the security-posture docs must track the real key paths and
    secret names (the reviewer's G0 secret scan catches leaks; this catches drift between
    the posture text and the posture).

12. **The UI/preview renderer surface** (ui components + compositions, the SDK
    preview stack, and the served wire document) → plugin-visible rendering
    behavior: `docs/device-developer-guide.md` (presentation section);
    component behavior: the ui component tests and Storybook stories; the
    wire shape: `standards/plugin-ui-preview/<active>/preview-document.schema.json`,
    conformance-tested from both the Python emitter and the TS decoder. The
    renderer freshness gate (obligation 7) carries the committed
    `preview_assets` half.

13. **The machine-written validation-report family** → a change to a family suite's
    corpus or checks reruns that suite's writer in the same change:
    `uv run python scripts/architecture/check_<suite>.py --write-report` for
    devices/registry/execution/interface (reports land in the manifest-active version
    dirs) and closure (its corpus is the `docs/acceptance` review set — content changes
    there rerun its writer into `docs/acceptance/validation-report.md`); the
    `docs/README.md` rows linking the four standards-tree reports move with the counts.
    The pin tests (`test_validation_report_matches_live_run` and the tamper arms in
    `tests/contracts/test_architecture.py`) are the mechanical half — they byte-compare
    each committed report to a fresh sorted render of a live run and tie the README
    counts to the live counts (invariants CON-11). Superseded versions' reports are
    frozen historical evidence and are not regenerated; plugin-ui's reports are train
    records, not family members.

14. **An agent tool-grant change** (`.claude/agents/*.md` `tools:`/`disallowedTools:`
    frontmatter) → re-extract every sibling agent's frontmatter and diff the effective
    grant sets, so any exception is visible against the standing posture; document the
    exception in the agent's own file (prose, not frontmatter alone — the frontmatter
    says what is granted, the prose says what enforces it); name the reference set
    (issue #74's deliberate exclusions) in the commit message; keep the frontmatter
    serialization consistent across the seven files (comma-separated scalar lists, not
    JSON arrays). Second surface arrival here in as many days (#110, then #112) — the
    row lands per obligation 12's own principle.

15. **The transport-provider lane** (OTDP 0.2.2's provider declaration: corpus schema
    and prose in this repository, offline conformance in `packages/sdk`, gateway
    admission/grant landed increment 3 — gateway issue #147's implementation lane) → the
    increment-2/3 pairing constraint (the #147 design record's AR-6 route): an SDK
    provider sync proves the descriptor lane only — the gateway's admission seam is a
    separate increment, and a corpus change that lands after the SDK synced CANNOT
    re-vendor same-version (`standards_version_required` refuses it; measured on the
    #147 fold) — the heal is a version-incrementing PATCH after the bump-window floor,
    never a same-version byte swap; `tests/sdk/test_descriptor_equivalence.py`
    is the agreement surface that must stay green across the pair. The designed carrier
    of the constraint is the SDK lock's `compatibility.notes` field, filled on the
    SDK's `fix/147-fold-sync` train (the sync writer now preserves the field
    verbatim — SDK STD-6, gateway #170 — so a fill no longer needs to ride a
    sync commit; hand-edit remains the only writer).

16. **The `transport-settings.json` surface** (issue #147 increment 3:
    `src/benchweave/control/provider_settings.py`, consumed by
    `admit_documents`/bootstrap and the `build_capture_services` grant gate) → the
    schema is gateway source, NOT corpus (provider instances are deliberately versioned
    elsewhere); it stays IDENTITY-ONLY by schema, not policy — `additionalProperties:
    false` throughout and every string pattern-constrained except the settings-relative
    document name, which carries the package-relative path rules. Any request for an
    endpoint/secret/credential field is refused and routed to the deferred
    execution-standard commissioning shape (the increment-3 design record's deferral 2;
    reopen trigger: the first provider implementation) — an endpoint field would put
    extension-contract §6's no-direct-access sentence one schema-edit away from false.
    Promotion into the commissioning shape (pinned, expiring with the commissioning) is
    the same deferred row's.

17. **The hand-carried reserved-seven transfer kinds** (the gateway mirror's
    `_RESERVED_TRANSFER_KINDS` in `src/benchweave/control/documents.py`; the SDK's
    twin in `packages/sdk/src/benchweave_sdk/validation.py`) → both frozensets are
    prose-carried (the vendored runtime schema does not enumerate transaction kinds,
    transport-providers §3 does) and each side carries its own spelling test
    (`tests/control/test_documents_provider.py`;
    `packages/sdk/tests/test_transport_providers.py`) pinned from the corpus text — a
    silent shrink of either set fails its own lane. Extends the #147 record's
    deferral-8 posture to both sides; the derivation-vectors-style census fixture
    (one corpus document feeding both checkers) stays the deferred fix shape when the
    §8.1 generic table grows.

18. **The version-bearing-surface inventory** (issue #188's requested row;
    invariants CON-13) → every surface that declares a corpus or SDK version,
    and its motion mechanism under a bump:
    (a) `standards/standards-manifest.json` — the authority; it moves with the
    bump itself;
    (b) `docs/compatibility-matrix.md` — derived; `matrix --check` (CON-12);
    (c) `docs/README.md` validation-report rows — derived paths; the family
    pin tests catch a forgotten row (obligation 13);
    (d) the website version stamps — derived at assembly with ZERO bump
    motion: `website/index.html` carries `{{stg-*}}` tokens at its claim
    sites, the hygiene pin (`tests/contract/test_website_stamps.py`) refuses
    a three-component literal anywhere in the class-11 source set (the
    `website/` tree plus `index.qmd`), and a NEW claim-site gets a token plus
    map coverage, never a literal (CON-13; two-component prose claims remain
    outside the pattern — issue #188 design deferral 5);
    (e) the adapter-identity touch-set — hand-carried, in-arc (obligation 8);
    (f) `verify_tree`'s frozen-version corpus probe
    (`standards/otdp/0.2.0/otdp-runtime.schema.json`) — copy-never-move keeps
    it permanently resolvable and it claims nothing about "active" (issue
    #188 design deferral 2);
    (g) plugin contract locks — `plugins/fnirsi/dps150/contracts/lock.json`
    declares `otdp_version` (and its corpus `directory`); motion: relock in
    the bump arc, against the corpus the bump admits;
    (h) live authority pointers that name one versioned path as THE
    authority — obligations 1-2 above (`standards/interface/0.1.0/…`) and
    the `drift-guard.mjs` hook advice text that repeats them; motion: those
    obligations' in-arc sweeps (an interface bump re-points them);
    (i) the additional frozen corpus probes — invariants CON-5's
    `interface/0.1.0/interface-contract.md` pin, the parity-tests bullet in
    this file's testing-conventions section, and CLAUDE.md's core-principle
    reference to the same contract; motion: copy-never-move keeps them
    resolving, and they claim nothing about "active" — the same class as
    (f), not swept;
    (j) `index.qmd` prose — three-component literals are refused by the
    hygiene pin (see (d)); the residual two-component claim (`Architecture
    v1.5` link text) moves by in-arc sweep (design deferral 5);
    (k) guide and test-docstring corpus pointers — the remaining
    `../standards/otdp/<version>/` links in `docs/device-developer-guide.md`
    (the descriptor-checklist pair was re-pointed at the active 0.2.2 in the
    #188 fold) and `tests/contract/test_dps150_lock.py`'s docstring naming
    the locked directory; motion: in-arc sweep;
    (l) corpus-manifest row paths — every `standards/corpus-manifest.json`
    row's `path`/`source` names a versioned directory; motion: obligation 6 /
    CON-7 (rows move with the bump's corpus edit, digests via `repin`).
    (m) the docs baseline lines — the multi-standard version sentences in
    `docs/device-developer-guide.md` (the **Baseline:** line),
    `docs/ai-device-reviewer.md` (the review-baseline paragraph),
    `docs/development.md` (Documentation baseline) and
    `docs/smart-test-gateway-architecture-v1.5.md` (§21 Consolidated baseline):
    prose version claims naming OTDP/registry/execution/interface versions;
    motion: in-arc sweep at the bump of ANY standard a line names (the #176
    final fold swept all four to execution 0.2.0 / OTDP 0.2.2 after the
    promotion left them stale); no mechanical gate covers them today — the
    hygiene pin's class-11 source set does not include `docs/` (deferral 5's
    shape).
    Closing clause: a new version-bearing literal anywhere is a defect —
    make it a derived surface or register it here with its motion mechanism.
19. **Skills shared with the SDK repo** (`.claude/skills/increment/`,
    `panel/` — the intersection of the two repos' skill dirs) → a change to
    a shared skill's clauses re-syncs the SDK copy's shared clauses in the
    same work: SDK-side copy commit → push → SDK PR, plus the main-side
    skill-file commit (skill copies are independent files in two repos —
    AGENTS.md's submodule discipline governs `packages/sdk` only, and any
    pointer advance rides a train of its own); loop prose that is
    deliberately gateway-specific does not sync (issue #99's design §6).

19. **The dependency-policy block and the carried set** (issue #215, parent
    #203 slice 1): `standards/standards-manifest.json`'s `dependency_policy`
    block is the one committed authority for per-standard ranges, yanks and
    retired identifiers. If a PR touches it, all four surfaces move together
    in one arc: the manifest block ↔ the exported bundle
    (`dependency_policy` rides verbatim; one entry per CARRIED (id, version)
    — yanked versions ride marked) ↔ the SDK lock's carried rows and mirrored
    block ↔ the SDK's vendored tree (`make sync-sdk-standards`; land lock +
    pointer together). Drift refuses by name (`served_set_drift:`,
    `policy_mirror_drift:` in `benchweave.standards check`); the SDK-side
    load path carries the discipline inward — every served document is
    digest-checked against its lock row (`vendored_digest_mismatch:`,
    issue #215 fix F1); and the gateway-side export/check path compares
    every carried version's corpus rows against their corpus pins
    (`corpus_pin_mismatch:`, #215 fold-wave F-B — superseded versions are
    digest-frozen, and a tampered non-active carried version no longer
    exports clean). Range changes are coordinator decisions (VR-43) and
    require a linked ruling reference in the PR body
    (`policy_change_unruled:` is the drift-check lane's refusal, landing with
    slice 2's agreement lane). The yanked 0.2.1 and the retired identifiers
    enumerated from `ea70c6a5^` are the founding entries. A YANKED entry must
    name a retained in-range version — bytes have to exist for a
    yanked-but-conforming pin to validate against
    (`policy_entry_unresolved:`); a RETIRED entry must name NO retained
    directory and never the active version (`policy_retired_active:` /
    `policy_status_conflict:`) — retired means "used and dead", so a retired
    identifier naming no retained directory is the CORRECT seed state, not a
    refusal (the earlier inversion here is corrected by #215 fold row 10).
20. **The executable-version-literal ratchet** (issue #203 slice 1, A4):
    `scripts/standards/count_version_literals.py` is the gate's counter —
    AST-based, reproducible, baseline committed in the script (12 sites at
    merge base `403c061`). It runs in `make check-sdk-standards`; the count
    cannot rise (a planted literal fails CI — proven in the slice record).
    Removing a literal lowers the count and may re-baseline DOWN by editorial
    decision recorded in the script; the register (`DECLARED_FILES`) names the
    D2 exception (plugin-ui corpus-owned code) that slice 7's zero-mode
    consumes.

## CI map

| Job | What it catches |
|---|---|
| `gates` | submodules recursive; fixture keys materialised from secrets; `ruff check .`; config-driven `mypy` (bare — explicit path args drop `packages/sdk/src` from the build); `pytest -q` (including the adapter agreement test, which pins the SDK↔gateway protocol mirror and the version triplet — see obligation 8); `make check-sdk-standards` (main standards ↔ SDK lock ↔ vendored tree, plus the identity `adapter_api` derivation check, plus the served-set/policy-mirror lanes and the executable-version-literal ratchet — issue #203 slice 1) |
| `ui` | `npm ci` + typecheck + lint + unit tests + Storybook build; the renderer freshness gate (see obligation 7); `npm audit --audit-level=high` |
| `systemd` | unit-template render + `systemd-analyze verify` with rehearsed deployment preconditions (see obligation 9) |
| `package` (OS matrix: ubuntu + macos) | installed-wheel/SDK smoke against the built packages; `make check-sdk-standards`; the clean-venv ADC conformance control (issue #203 slice 1: the out-of-tree ADC plugin at its pre-restamp commit, `git archive`-installed, the built SDK wheel forced over the checkout pin, network blocked — 26/26 or red); and the derived-variable census selection (`tests/unit/test_derivation.py` + `tests/faults/test_derivation_faults.py`) — the lane where cross-platform binary64 agreement is actually measured (no Windows lane; the design record's risk 4 states the coverage) |

What CI does **not** catch: every numbered obligation above that names a doc, a guide, or
a cross-repo push — those are the reviewer's, which is why G5 exists in the rubric.

## Testing conventions worth upholding

- **RED-sanity verification**: a bug-fix test must be shown to fail without the fix. `no
  tests ran` is a FAILED RED check — pytest exits 5 when it collects nothing; look for the
  collected count. Read counts from `--junitxml` attributes or exit codes, never from an
  output-filter summary (the rtk filter can print "No tests collected" over a green run).
- **Claim discipline**: a set named in prose is regenerated by a test from a mechanism; a
  guard states what it does not catch; *cannot/never* means structurally unrepresentable
  and says why inline, otherwise *is refused unless* plus the residual.
- **Parity tests are not contract tests**: transport parity (REST vs MCP) proves only
  symmetry — pin behavior against the frozen
  `standards/interface/0.1.0/interface-contract.md` (invariants CON-5). The WP07 lesson:
  a wrong failure code was test-pinned in three suites before the whole-branch review
  caught it.
- **`tests/faults/`** runs for any change touching `state/`, `control/`, or anything
  concurrency-shaped — it is the fault-injection arm of the suite.
- **One RED→GREEN slice per commit** — the discipline that keeps every fix provable.
