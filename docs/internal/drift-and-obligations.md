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
   **Frozen preview bundle (G1e, R-5):** the SDK's committed `preview_assets` React
   bundle is FROZEN at its last build (`renderer_version 0.1.2`, inventory at freeze
   commit `085b0ff78e126b5b124b95451d2b08114ae78b71` — recorded at landing):
   shippable, NEVER rebuilt — the toolchain that built it (`ui/`,
   `write-preview-inventory.mjs`, the Node CI lane) is deleted, so no path exists
   that regenerates it. The SDK's `hatch_build` inventory-vs-committed-bytes
   verification REMAINS the integrity check (frozen ≠ rot: byte drift still reds
   the SDK build). Exit: dependency 4a — the PRD 11 standalone host with mock
   transport (SA-PREVIEW, #309) — at which point `preview_assets` is deleted from
   the SDK and `preview-ui` becomes a shim (R-9).

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
   bump on either side surfaces there. Since #217 (slice 3) the census also sweeps
   the SERVED set (both lanes per-pin; the 28-cell matrix stays ACTIVE-version) and
   pins the disclosed 0.1.2 prefix-split cell (SDK `version_not_served:` fold vs the
   gateway's ack gate).

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

12. **The UI/preview renderer surface** (the Python renderer package, the
    pattern library, the ported proofs, and the served wire document) → the
    normative surface for plugin-visible rendering behavior is
    `docs/internal/ui-contract.md` (issue #242: renderer-neutral contract;
    tokens, severity model, safety definitions, component rows); its gates
    are the `benchweave-ui-html` contract harness (`packages/ui-html` — the
    pytest11 collector; pin layer = parse integrity per pinned table, row
    layer = canonical-artifact requirement per parsed row), LIVE in the
    default root-suite run since G1e (`testpaths` carries the contract
    beside `tests/`, enforced by the default-run pin in
    `tests/ui_html/test_harness.py`) — a contract-table edit lands with its
    pins in the same change. `docs/internal/ui-styleguide.md` is
    implementation guidance for the Jinja/HTMX renderer, not the authority.
    The pattern library (static export, docs-site staging at build, the
    browser lane's axe/screenshot set) carries component behaviour beside
    the harness rows; the ported proofs live in `tests/ui_html/` (the
    series-colour proofs, token/CSS pins, threshold constants, lane
    reduction, the staleness predicate) and the composition state-machine
    proofs (`tests/ui_html/test_compositions.py` +
    `test_compositions_mutations.py` — the §B/§C rule rows' transition,
    fire-attempt and refusal drivers) pin the behavioural rules the same
    way. Plugin-visible rendering behavior →
    `docs/device-developer-guide.md` (presentation section, unchanged);
    component behavior → the harness rows + the pattern-library pages (the
    Storybook reference is gone). The wire shape:
    `standards/plugin-ui-preview/<active>/preview-document.schema.json`,
    conformance-tested from the **Python emitter only** (the TS decoder
    half was deleted with `ui/` at G1e). The vendored-asset inventory +
    serve-time verification (UR-10) is the package's
    `benchweave_ui_html.assets.verify_vendored_assets()` plus the host-call
    documentation (a host verifies the inventory before serving the assets;
    the wiring lands with G2 / PRD 11).

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
    the gateway-side members of this set are inside the gated gateway scope
    and the SDK-side members inside the sdk scope, so a literal ADDED in
    either fails the zero gate in CI (#221) — the in-arc sweep remains the
    motion mechanism for the surviving declaration rows;
    (f) `verify_tree`'s frozen-version corpus probe
    (`standards/otdp/0.2.0/otdp-runtime.schema.json`) — copy-never-move keeps
    it permanently resolvable and it claims nothing about "active" (issue
    #188 design deferral 2);
    (g) plugin contract locks — `plugins/fnirsi/dps150/contracts/lock.json`
    declares `otdp_version` (and its corpus `directory`); motion: relock via
    `uv run python -m benchweave.standards pin` in the bump arc, against the
    corpus the bump admits (#216, lock v2: the `standards` rows re-derive
    from corpus rows; the legacy otdp projection — `directory`,
    `otdp_version`, `adapter_api_version`, the file map — moves with the
    resolved otdp row and only with it). Revision motion is explicit
    (#216 fold F4): same-version digest-value motion in the map requires
    `pin --revision <sha>` — the recorded revision must carry the bytes the
    map digests (the revision-scissors invariant; the map itself is an
    allowlist — corpus-rowed ∪ prior-mapped, fold F3). The lock is JSON
    data outside the counter's executable scopes (#221), but the plugin's
    DESCRIPTOR declarations are inside the gated plugins scope as
    registered authored data (the register row names them);
    (h) live authority pointers that name one versioned path as THE
    authority — obligations 1-2 above (`standards/interface/0.1.0/…`) and
    the `drift-guard.mjs` hook advice text that repeats them; motion: those
    obligations' in-arc sweeps (an interface bump re-points them); these
    are PROSE pointers in this doc, inside the docs scope's excluded
    internal set (#221) — their motion stays the in-arc sweep;
    (i) the additional frozen corpus probes — invariants CON-5's
    `interface/0.1.0/interface-contract.md` pin, the parity-tests bullet in
    this file's testing-conventions section, and CLAUDE.md's core-principle
    reference to the same contract; motion: copy-never-move keeps them
    resolving, and they claim nothing about "active" — the same class as
    (f), not swept; this doc's own probe text sits inside the docs scope's
    excluded internal set (#221);
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
    promotion left them stale); mechanically these lines now sit inside the
    docs scope's committed snapshot ratchet (#221 — a NEW literal refuses;
    an edit to an EXISTING literal's count refreshes only via the explicit
    `--refresh-docs-baseline`, whose diff is the review surface — the
    in-arc sweep is still the motion, the ratchet is its tripwire);
    (n) `docs/project-index.md` — the standards-links block names each
    standard's versioned path (found stale at plugin-ui 0.2.0 in the #244
    governor review — a bump WIDENS the stale surface to every standard it
    bumps, so the #244 train staled both plugin-ui and plugin-ui-preview
    lines against GOVERNANCE's in-arc rule; the finding's core was this
    surface's omission from the walked obligations); motion: in-arc sweep
    at EVERY standard the bump touches, with the #221 snapshot refresh
    (`--refresh-docs-baseline`, diff = the review surface) — the ratchet
    pins per-value counts, so an in-place version swap is still a visible
    refresh, never silent.
    Closing clause: a new version-bearing literal anywhere is a defect —
    make it a derived surface or register it here with its motion mechanism.
    Enforcement (issue #221, #203 slice 7): "here" is mechanically the
    counting script's REGISTER (`scripts/standards/count_version_literals.py`,
    zero-mode) — each entry carries a reason and an `expected_sites` count,
    and a new literal inside a registered file fails the gate until the row
    is edited (a visible editorial diff). A literal registered anywhere
    OTHER than that register is an off-register defect, review-visible by
    this clause.
19. **Skills shared with the SDK repo** (`.claude/skills/increment/`,
    `panel/` — the intersection of the two repos' skill dirs) → a change to
    a shared skill's clauses re-syncs the SDK copy's shared clauses in the
    same work: SDK-side copy commit → push → SDK PR, plus the main-side
    skill-file commit (skill copies are independent files in two repos —
    AGENTS.md's submodule discipline governs `packages/sdk` only, and any
    pointer advance rides a train of its own); loop prose that is
    deliberately gateway-specific does not sync (issue #99's design §6).

20. **The executable-version-literal zero gate** (issue #203 slice 1, A4;
    zero-mode since slice 7, issue #221):
    `scripts/standards/count_version_literals.py` is the gate's counter —
    AST-based, reproducible. Slice 1 ran it in ratchet mode (a committed
    12-site ceiling at merge base `403c061`); slice 7 flipped it to
    ZERO-MODE: per scope (gateway / plugins / sdk / docs-ratchet), the
    count of literals OUTSIDE the register is 0 and every register row's
    `expected_sites` holds exactly (authored-data rows pin the literal
    VALUES too — a semantics-changing substitution fails at unchanged
    cardinality; the contracts.py twins stay digest-pinned whole). The
    docs scope is an EXACT-CONTENT bound against the committed snapshot
    (`scripts/standards/docs-literal-baseline.json`): growth AND shrinkage
    refuse, the scanned-file census is checked in-gate, and only an
    explicit `--refresh-docs-baseline` (its diff the review surface) moves
    the bound. It runs in the device-plugins lane (`--scope plugins,docs`)
    and through the pytest suite over the real trees (`test_zero_literal_gate`
    — every scope, plus the sdk scope whenever the submodule is present);
    `make check-sdk-standards` carries the SDK-SYNC lane's own sdk-scope
    gate at the submodule pin (scope-explicit since the #221 fold — a bare
    default-scope invocation refuses `sdk_tree_absent:` in submodule-absent
    worktrees); the SDK repo carries the twin counter and its own CI step.
    A planted literal in any registered scope fails CI (the G2 plant
    branches carry the wire-level proof); a literal inside a REGISTERED
    file fails the row's expectation until the register is edited — a
    visible editorial diff.
    **Assembly clause (issue #269, row 1; residual regenerated by the
    fold wave, row 3):** the matcher folds CONSTANT-ONLY assembly and
    refuses the folded result under `ASM-A`/`ASM-BARE`. The fold
    allowlist is exactly: `Constant`; `JoinedStr` whose `FormattedValue`s
    carry no conversion and no format-spec; `BinOp` `+` (str+str), `*`
    (str×int), `%` (folded string left side); `List`/`Tuple` displays;
    `.join` over one literal list/tuple of str; `.format` with positional
    args only (no kwargs, no format-spec or conversion in the template);
    `.decode()` with no arguments; `chr(i)`/`str(x)` with one argument,
    unshadowed at module level. EVERY OTHER input class is a DOCUMENTED
    MISS, named: format-specs and conversions; `.format` kwargs;
    `%`-with-dict; `decode` with argument(s); conditional-expression
    arms; starred format arguments; `os.path.join` and every other
    stdlib string constructor (D-3); folds bounded out by the caps (fold
    depth > 24, folded length > 4096 — a bounded-out fold is
    indistinguishable from dynamic assembly, the same disclosure); and
    dynamic input — variable, parameter, function result, comprehension,
    data/env/config reads — where catching needs taint tracking,
    deliberately not attempted (D-1). The
    `chr`/`str` shadow prepass sees module-level bindings only (a
    function-local shadow is a named residual). The battery pins BOTH
    sides: `tests/standards/assembly_shapes.py` carries the twelve caught
    shapes, the documented-miss shapes (must pass), and the boundary
    table (24 chained BinOps fold, 25 bounded out; a 4096-char fold is
    caught, 4097 bounded out) — the next evasion probe extends the file.
    **Scripts scope (row 2):** `scripts/` is a fifth gated tree — the adc
    control's two pins DERIVED from the committed policy block
    (`adc_policy_absent:`/`adc_yank_not_unique:`/`adc_yank_is_active:`
    refusals — the yanked == active shape is REFUSED, it would make the
    anti-gaming warning checks vacuous; `adc_policy_unreadable:` wraps
    malformed authorities), the docs site's runtime-schema path DERIVED
    from the active otdp family, and twenty authored fixture/self-test
    values REGISTERED with value pins across seven rows; the counter
    self-exempts (`SCRIPTS_EXCLUDED_FILES`, whole-file — a plant in its
    non-shared region is review-lane-borne, named residual). **Membership
    rules (row 3):** plugins gate any `.py` under `plugins/` with no
    `tests/` component (flat plugins; census 15; a distributed
    `tests`-subpackage stays excluded — named residual), and environments
    are detected BY MARKER AND LAYOUT — a directory is a Python
    environment iff it carries `pyvenv.cfg` AS A FILE and environment
    structure (`bin/` or `lib/python*/`; the layout conjunct is the
    fold-wave truth re-check: a planted marker without layout does NOT
    exempt a tree) (`node_modules`/`site-packages` stay name-based: no
    marker exists, named residual; a deleted marker fails the gate
    loudly, never silently). **Denominator boundary (fold row 13, as
    shrunk):** the gated trees are gateway `src/benchweave/`, the SDK's
    `src/benchweave_sdk/`, in-tree plugins, `docs/` (ratchet), and
    `scripts/`. `tests/` and `.github/` are OUTSIDE the gates (tests
    carry legitimate fixture literals; assembly there equally so) —
    named so the denominators cannot silently move. Per-scope scanned
    censuses are pinned (plugins 15, sdk 19, scripts 17, docs 31; the
    gateway floor 93) — a denominator move is a visible same-commit diff
    (numbers read from the gate's own pins in
    `tests/standards/test_zero_literal_gate.py`, which returns to main's
    bytes with the #224 pivot: the scripts census is 17 again —
    `scripts/website/` held three .py files at the pre-pivot slice and now
    holds zero, the directory itself deleted; the census is stated from
    the gate's own pin, never hand-counted).

21. **The dependency-policy block and the carried set** (issue #215, parent
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
    exports clean). The SDK-side check lane additionally cross-checks the
    lock's OWN rows against the mirrored policy block — a yank-marker flip
    on a lock row, a retired-but-carried row, an out-of-range row or a
    yanked active marker refuses `marker_mirror_drift:` (issue #288 M5), so
    lock-internal drift fails `sync-standards --check` offline, not only at
    the next gateway-side comparison. Range changes are coordinator
    decisions (VR-43) and
    require a linked ruling reference in the PR body
    (`policy_change_unruled:` is DEFERRED as D10 — no gateway workflow reads
    PR bodies today, so no check harness can carry it; the governor lane
    reviews every `standards/` touch meanwhile. This slice's PR amends this
    row's original "landing with slice 2's agreement lane" sentence — the
    owner's merge is the blessing). Slice 2 (#216) adds the resolver
    surface: `standards/cross-constraints.json` (governance data beside the
    two manifests, no corpus rows, root-scoped exemption in repin and the
    baseline walks) ↔ its loader in `src/benchweave/standards/dependency.py`
    ↔ resolve-time pairwise enforcement, with slice 3's bench admission
    consuming the same loader (LANDED, #217: `control/documents.py`
    `_check_cross_constraints`, pairwise per device against the bench's
    execution version, `cross_constraint_violation:`); rows require citable evidence, and the
    package carriers are `contracts/constraints.json` (authored) ↔
    `contracts/lock.json` (generated, verified by `pin --locked` and check's
    `plugin_lock_drift:` lane). The yanked 0.2.1 and the retired identifiers
    enumerated from `ea70c6a5^` are the founding entries. A YANKED entry must
    name a retained in-range version — bytes have to exist for a
    yanked-but-conforming pin to validate against
    (`policy_entry_unresolved:`); a RETIRED entry must name NO retained
    directory and never the active version (`policy_retired_active:` /
    `policy_status_conflict:`) — retired means "used and dead", so a retired
    identifier naming no retained directory is the CORRECT seed state, not a
    refusal (the earlier inversion here is corrected by #215 fold row 10).
    Registration append (issue #288, the fold's own NIT-2 gap class): the
    loader family's bound-shape refusal `constraint_bounds_reversed:` —
    `dependency.py` `parse_interval` and `manifest.py` `_parse_range` refuse
    an equal or inverted bound pair at parse time, naming the pair, in both
    the constraints loader and the policy loader — is registered here,
    closing the gap its loader-family siblings (`cross_constraint_violation:`,
    `policy_entry_unresolved:`, `policy_retired_active:`/`policy_status_conflict:`
    above) never had; and `marker_mirror_drift:` (the SDK-side sentence
    above) is registered with CON-4's stability posture — the prefix has NO
    gateway emitter by design §4's conscious choice (issue #288 M5 is
    SDK-side only; the gateway lane never synthesizes it), so this doc is
    its registration home.

22. **The counter twins** (issue #221, obligation-19 shape): the gateway's
    `scripts/standards/count_version_literals.py` and the SDK repo's
    `scripts/count_version_literals.py` are one definition in two
    repositories — the gateway copy is the authority, the SDK twin scopes
    it to `src/benchweave_sdk/` with the SDK register rows. A change to
    EITHER copy's definition block or register SEMANTICS re-syncs the
    other in the same work (the register ROWS themselves are per-repo
    data and move independently); the SDK PR body notes the sync when it
    rides a definition change. The pairing is the A6 two-sided gate: an
    SDK-only literal fails the SDK lane immediately and the gateway lane
    at the next pointer bump. The shared DEFINITION block is marked in
    both counters (`>>> BEGIN/END SHARED COUNTER REGION`) and pinned
    BYTE-IDENTICAL by the gateway's parity test (issue #269 §4 — the
    digest-identity shape of the contracts.py pin; a one-character
    mutation arm proves detection): SDK-side definition drift fails
    gateway CI at the next pointer bump, with this row remaining the
    human-level sync duty.
23. **The bridge verb set and the CLI command surfaces** (the `supported` dispatch table and
    module docstring in `src/benchweave/host/otdp_bridge.py`; the Click tree under
    `src/benchweave/cli/`; the argparse family in `src/benchweave/standards/__main__.py`) 🪝 →
    a change to any of those sets sweeps every prose surface that names them, in the same
    change. Bridge-status sentences state **remaining scope only, never a verb enumeration**
    — the #317 doctrine (refute F1/F2): a verb list in prose is a set claim with no
    mechanical pin, and a "remaining scope is" sentence is a set claim by complement that
    must be re-derived from the mechanism — the bridge's dispatch table, the services the
    host wires into it, and the open tracker items. The docstring's gap list is a derived
    surface this row also sweeps: it went stale once (#146's dataset-services landing, left
    unmirrored) and its false sentence shipped to two prose mirrors — the #319 refute.
    The surfaces: `website/index.html`'s home-page sentence and `docs/device-developer-guide.md`'s
    status/simulator paragraphs (kept byte-mirrored where both carry the same claim); the CLI
    command sets in `docs/operator-guide.md` §10 (BOTH tables), the website's CLI-reference
    card, and the docs site's generated standards-CLI page — that page regenerates at build
    from `python -m benchweave.standards --help` (`scripts/assemble_docs_site.py`;
    `verify_tree` pins its presence) and `tests/contract/test_docs_site_standards_cli.py`
    pins its verb set, so a verb add/remove reddens the pin: that red is the tripwire doing
    its job, not noise. The dispatch-table/CLI diff is the trigger; docs-only refactors of
    these sentences are not.

24. **The pattern library's package-relative assets** (issue #300 G1d; UR-06/UR-13;
    re-pointed at G1e) → the export reads THREE inputs: the token CSS — the
    package's vendored assets since G1e
    (`packages/ui-html/src/benchweave_ui_html/assets/`, via
    `artifacts.TOKENS_CSS`/`THEMES_CSS`/`GLOBALS_CSS`; byte-pinned by the
    UR-10 inventory, the re-point the G1d design record §1.3 named), the
    contract itself (`docs/internal/ui-contract.md` — the library pages
    derive their §B.1/§C.2/§C.3/§D.1 content from its parsed cells,
    row-as-data), and the staleness predicate — whose semantic reference is
    `packages/ui-html/.../staleness.py` itself since G1e (the React
    `staleness.ts` it was ported from is deleted; documentation-level only
    either way). The export refuses loudly when any input is absent
    (`PatternExportRefused`, pinned by `tests/ui_html/test_patterns.py`),
    so a missing input cannot lose the library silently — it reds. The
    generated tree is NEVER committed: a tracked `patterns/` dir at the
    repository root refuses (the repo-side guard in the same test file),
    and the docs site stages the export at build time.

25. **The pattern library is never served by production** (issue #300 G1d;
    the G2 half the G1d design record §1.3 discloses) → the package ships
    render functions and a static-file writer ONLY — there is no app/ASGI/
    route object to mount, so a production mount is not a code path away.
    Honest limit: this cannot STOP a future host from choosing to serve the
    generated HTML; the enforcement is G2's GW-04 routing test, which must
    pin that no `/ui` path serves the pattern library (the dev posture is
    loopback file:// browsing). This row is the obligation the G2 design
    inherits — a gateway routing test added at G2 must carry that pin or
    this row stays open.

26. **The real UI's component-CSS obligations died with `ui/` and are
    inherited by the G2/G3 host design** (issue #300 G1d fold F2, extended
    at G1e) → the pattern pages inline only the token CSS, so interactive
    controls render at browser-default metrics — some below WCAG 2.2's 24px
    target-size minimum; the PAGE's own inlined CSS carries the minimum as
    a layered pair (globals.css's `button { font: inherit }` at the 16px
    root — measured 24px buttons — plus the chrome rule `.bw-pattern
    button, … { min-height: 24px }` in `pattern-page.j2`), and the browser
    lane's strip machine check proves the pair: one layer stripped stays
    clean, both stripped reds `target-size`. The REAL UI's target sizes
    rode `ui/src/components/**/*.css` — which G1e deleted: the G2/G3 host
    design inherits the obligation that its component CSS (or the host's
    own chrome) provides the minimum, or the real UI regresses what the
    export proves. The G1b reading-tile CSS structure pins
    (`tests/ui_html/test_reading_tile_css_pins.py`, G1b record §1.4) died
    with the same deletion — retired at G1e, per the G1b record's own
    "dies with `ui/` unless re-pointed" ruling, because no live renderer
    consumes that file (the pattern library inlines token CSS only; the
    hosts design their own component CSS). Their substance transfers here
    the same way: the G2/G3 host CSS inherits no-glow on normal/limiting
    readings (§B.2 SR-B2, §B.3 — the limiting block declares no box-shadow)
    and the limiting border being exactly `var(--bw-limiting)`; the HTML
    shape of the reading tile stays enforced by the §E.1/§B.3 harness rows.
    Named here so the deletion cannot lose them silently.

27. **The publishing-lane surfaces** (issue #223 slice 1, design
    `docs/implementation-planning/10-contributor-publishing-design.md`): the
    registry repository of record (`benchweave-registry`) owns the records
    tree, its schema, the lane rules, the checklist and the signed releases —
    its own CI runs the records-validity gate and the admission replay at the
    committed `gateway-ref` pin (the pin advances deliberately per train; the
    drift job warns when gateway main passes it). Cross-repo sync obligations:
    a registry-standard bump repins here then syncs the SDK lock and vendored
    tree via `make sync-sdk-standards` (obligation 6's loop); the artefact
    enumeration is three-way pinned (publishing guide ↔ SDK
    `REQUIRED_COMPONENTS` ↔ records-schema enum) by the registry repo's
    `check_enumeration.py` over the gateway checkout at the pin; the DPS-150
    dogfooded release's records live in the registry repository, never in this
    tree. `scripts/registry/sign_release.py` here is the only lane signer, and
    the lane key never enters any CI (CR-12).

## CI map

| Job | What it catches |
|---|---|
| `gates` | submodules recursive; fixture keys materialised from secrets; `ruff check .`; config-driven `mypy` (bare — explicit path args drop `packages/sdk/src` from the build); `pytest -q -n auto -m "not timing and not browser"` (including the 196 contract-gate items collected from `docs/internal/ui-contract.md` via `testpaths` — live in the default run since G1e — plus the adapter agreement test, which pins the SDK↔gateway protocol mirror and the version triplet — see obligation 8, and the version-literal ZERO gate's pytest module, which runs ALL FIVE scopes (gateway, plugins, sdk, docs, scripts) over the real trees — issue #203 slices 1+7, issue #269); `make check-sdk-standards` (main standards ↔ SDK lock ↔ vendored tree, plus the identity `adapter_api` derivation check, plus the served-set/policy-mirror lanes and the version-literal ZERO gate over the SDK scope only — `--scope sdk`) |
| `timing` | the real-paced set (`-m timing`: the two integration rig files whole, plus the contention and clamp cells in `tests/unit/test_otdp_bridge.py`), serialized on its own fresh VM within ~2 min of boot so its wall-clock bands are measured before any bulk-suite residue (page cache, draining threads, WAL checkpoints); complementary partition with `gates` — union = the full collection, structural by construction from the complementary markers, with the proof at PR time (the builder's collected-id set diff recorded in the PR body per the design's AR-1 — not an automated gate), and serial forever (xdist would reintroduce exactly the competition the split removes; issue #241 slice 1). Does NOT catch: a guarantee of a quiet host — a noisy neighbor can still stretch a band; slice 2's evidence-backed re-bands resolved as HOLD/document-only in that slice (2026-09-28); intra-lane ordering residue — review-fold disclosure: collection order runs the sequential-model battery before the continuity rig, so the rig measures after the lane's own earlier real-paced battery; the fresh-VM claim removes bulk-suite residue from other jobs, not ordering within this one; red-attribution is scoped — a red in the real-paced subset reads as a timing question, but the continuity file's ride-along logic tests can red as logic (the fold disclosure) |
| `systemd` | unit-template render + `systemd-analyze verify` with rehearsed deployment preconditions (see obligation 9) |
| `device-plugins` (`dps150-independent`) | the version-literal zero gate over the plugins + docs scopes BEFORE the plugin project is isolated (obligation 20; completing D8/#233's plugin lane), then the plugin's own offline conformance, quality checks and build from its isolated copy |
| `package` (OS matrix: ubuntu + macos) | installed-wheel/SDK smoke against the built packages; the ui-html member wheel's standalone install proof (issue #302 REL: build + fresh-venv assertions — import from outside the checkout, version equality with `packages/ui-html/pyproject.toml`, the `pytest11` entry point, installed set exactly the package + its two declared runtime deps); `make check-sdk-standards`; the clean-venv ADC conformance control (issue #203 slice 1: the out-of-tree ADC plugin at its pre-restamp commit, `git archive`-installed, the built SDK wheel forced over the checkout pin, network blocked — 26/26 or red); and the derived-variable census selection (`tests/unit/test_derivation.py` + `tests/faults/test_derivation_faults.py`) — the lane where cross-platform binary64 agreement is actually measured (no Windows lane; the design record's risk 4 states the coverage) |

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
- **Real-clock ms bounds live in the timing lane**: a wall-clock bound assert on
  a real clock (pacing bands, precision gates, busy-retry windows) carries the
  `timing` marker and runs serialized in the dedicated CI lane — or the quantity
  moves to an injected clock. `gates` runs `-n auto -m "not timing"`; an unmarked
  real-clock bound will flake in `gates` exactly the way issue #241's sweep
  rows did (marker-rot guard is the deferred D5). Timing-lane band readings that
  can absorb a transient host stall re-measure once through the one-shot cell
  belt (issue #241 slice 3): the reading is untouched, a gen-1 breach re-runs
  the cell once, and a fresh breach reds with both generations rendered —
  systematic looseness still reds; structural asserts and floors never trigger
  a re-roll themselves, but they evaluate whichever generation the belt returns
  — an absorbed gen-1 band breach skips gen-1's floor/structural verdicts,
  except the load-safe x1 floor, which asserts on both generations.
  Issue #241 slice 4's placement ruling adds three standing sentences
  (its design §1.5): a NEW test whose asserted property is purely
  order/budget semantics defaults to the injected clock (TestClock); a
  wall-measured disclosure quantity defaults to the timing lane with an
  in-run-relative ceiling (the D4' pattern — the ceiling references a
  quantity the same run stamped, the deterministic cut/status assert
  beside it, a synthetic band pin on the form); and the sentinel set is
  never skipped or made local-only — the timing lane stays the only
  enforced execution surface for the serialized model's disclosure, and
  the rule the #240 red-lane class was judged by only worked because the
  lane executed. The lane's residual budget is named, not open-ended:
  chronic-starvation exhaustion (a trial's fixed attempt budget exhausts
  on infrastructure sites, the composition rendered in the red) and
  sustained-stretch (three distinct band families breaching in one
  execution) are the tolerated-by-name families — a red without the
  family's signature is not in one.
- **`tests/faults/`** runs for any change touching `state/`, `control/`, or anything
  concurrency-shaped — it is the fault-injection arm of the suite.
- **Platform-conditional expectations key on a runtime capability probe**: probe the
  predicate the src branch actually keys on, assert the property in every branch (never
  a skip), and pin the other platform's shape on POSIX by simulating the primitive's
  absence — never static reasoning alone (issue #207: the dispose directory-fsync probe,
  the fw5 `time.tzset` guard, the Windows-shape simulations).
- **One RED→GREEN slice per commit** — the discipline that keeps every fix provable.
