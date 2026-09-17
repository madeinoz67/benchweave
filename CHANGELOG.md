# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Bug Fixes

- Invoke compound-action failures report dispatched state
- Promote jsonschema to runtime dependency
- Exercise boolean continuous conditions
- Recheck sample freshness at predicate evaluation
- Require at least one tag on every memory proposal
- Poll-sliced stable verification and uncertainty-preserving body truth
- Final WP05 fix wave - read/write stg refs, interrupted outcome, product units, freshness honesty
- Resolver identity recheck, pin-conflict guard, review minors (amends Task 5 brief)
- Structural loader containment, record overwrite refusal, atomic writes, review minors (amends Task 7 brief)
- Admission hardening — verify-if-exists cache, persisted high-water, source-level payload cap (WP06 final-fix wave 1)
- Loader exec-time integrity — re-hash entry before import (WP06 final-fix wave 2)
- Builder determinism wave — ZIP_STORED payloads, stale-dir pruning, origin-scoped sha_of, mypy coverage, full-breadth determinism pin (WP06 final-fix wave 3)
- Live format validation (rfc3987 + rfc3339-validator) and the mutable-revision honesty line (WP06 final-fix wave 4)
- Bind served status to its release — status_release_mismatch (unsigned-fix wave 1)
- Dev identity fence on OriginConfig — dev-unsigned reserved for dev- origins (unsigned-fix wave 2)
- Surface-audit wave 1 A — single-source §4 path check, archive_invalid, sys.modules rollback, prune dead map check, schema path pointer
- Surface-audit wave 1 B — loader executes verified bytes, unreadable .sig maps to bad_signature, falsifiable cache asserts, dev-path status-swap pin
- Surface-audit wave 1 C — model dev signatures honestly as bytes | None
- Raw WRITE trip reports DISPATCHED — compound-action honesty (surface-audit wave 2, item 11)
- Input-validation polish — eager deadline parse, scoped release swallow, typed condition-kind fence (surface-audit wave 2, item 13)
- §11 id-sharing exemption is ownership-direction-only; provided-id maps split per kind (surface-audit wave 2, item 14)
- WP07 task 3 follow-up — contract-legal artifact/evidence id shapes (no colons)
- WP07 task 4 — permission tiers are a hierarchy (observe ⊆ control ⊆ admin) + cursor numeric guard
- WP07 task 5 — canonical generation fence + worker-thread store for build_run + join fast path
- WP07 task 8 — adapter limit/length clamping + first live run-through-app test
- WP07 task 8 — clamp floor at 1 (negative/zero limit/length)
- WP07 final fix wave — event_gap/§7, cancel scoping/§6, seam offset floor, MCP write gate, MCP isError + D8-D13 register
- WP07 final — event_gap carries retained watermarks per §7/§10
- Stream_id bench.{id} contract-pattern conformance
- Scope dangling-request sweep to run keys, spare change keys
- D11 artifact offset aligned to the §8 letter — beyond-size fails invalid_request, at-size keeps the zero-byte eof chunk (seam construction site, envelope parity pinned)
- D13 MCP body ceiling — max_json_bytes over tool-call arguments, payload_too_large envelope parity with REST (D6 residual closed)
- D13 internal_error one construction site — correlation_id minted (uuid4 hex16), message text parity across transports, detail rides details
- D13 retry honesty — change_apply unknown-outcome advertises retry never (re-entry is conflict), pinned end to end
- Internal diagnostics off the wire, keyed by correlation_id — details def is closed (D14/D15 registered)
- Client guards for non-JSON and non-object 2xx bodies, read-phase timeout
- Reject scheme-less gateway URLs at the client boundary (T9 carry)
- Restore manifest gate + traceback-free at-rest boundaries
- Operator-close path for the live demo view
- Refuse empty and placeholder production secrets; observability + doc folds
- Audit fix wave — complete denylist, report hold, restore extras gate, setup boundary
- Verify carve-out for the registry work tree
- Assert the CLI contract (--version) instead of the retired bare-call print
- Mint correlation_id on every failure envelope (D14 cheap half)
- Serve the interface-v1.1.1 tools corpus (align with seam validation)
- Check_documents ignores fenced code blocks when scanning links
- Review minors — command count, hostname scrub at retention, parse guard, dotfile skip, junit family pin, index precondition
- Synthetic hostname in scrub test fixture (close-review F-M1; wave completed by controller after agent stall)
- Scaffold a location-independent preview conformance test
- Keep smoke contract sets aligned with the SDK build hook
- Register the preview fixture schema with its docs source
- Run config-driven mypy and type the SDK preview tests
- Enforce preview-server trust boundaries
- Ignore compiled vite config siblings
- Harden generated-project creation
- Polish preview runtime surfaces
- Point the renderer freshness gate into the submodule
- Refuse normative paths colliding in the bundle
- Guard sync target against uncommitted submodule pointers
- Neutralise newlines in matrix cells
- Tolerate trailing telemetry in the commanded reply window (live-device defect)
- Frame-atomic drain window — WP11 W1 straddle hardening + W2 same-field pin
- Ruff-format dps150 session - repair dps150-independent lane (broken by #14)
- Repoint preview wire-schema test at standards/ corpus path
- Re-lock dps150 contracts at the standards tree
- Review fix wave for the id/version tree (PR #21 M-1/M-2)
- Smoke script + adapter API constant follow the 0.1.0 baseline
- Audit straggler sweep — URN ids, catalog version, prose assertions
- Review fix wave 2 — runtime interface version, example teachings, doc truth
- Declare MIT license in pyproject metadata (was Proprietary)
- Key the Pages concurrency group by ref
- Wrap phone-width header onto two rows
- Anchor public-site-assembly ignores to the repo root
- B2 — Failure construction-site guard refuses empty correlation_id
- D14-details — the closed six-key error envelope on every failure
- D4 — every event kind emits the closed document-ref evidence
- Review-fix wave — poison-emit guard, fallback log, hygiene
- Pin the symmetric stray/stamp gates across all three check lanes (#9)

### Documentation

- Correct compatibility record with UF_HIDDEN root cause
- Pin memory vault routing to benchweave, ledger fallback until /mcp approval
- Pin memory vault routing to benchweave, ledger fallback until /mcp approval
- WP05 procedures plan and project ISA (close-of-WP05 state)
- Code-reviewer gates on documentation coverage per change (rule 3b)
- Rule 3b extends to API (OpenAPI lockstep) and MCP (mcp-tools.json) surfaces
- Rule 3b names CLI surface explicitly and reserves the UI clause
- Rule 3b adds fixture/CI/vendoring/security-posture surfaces; reserves deploy and hardware-evidence
- Honesty labels — dev-unsigned auth wording, enforced-not-authenticated sequence (unsigned-fix wave 3)
- Developer guide gains the registry dev loop — unsigned packaging, dev origins, signed production path, status refresh
- Add AI device development guide with firmware path
- Link AI device and firmware development workflows
- Clarify external plugins and Docker gateway lifecycle
- Link SDK workflow and clarify external adapter support
- Align device quickstart with plugin layout
- Show optional plugin feature directory layout
- Disclose report's migration-on-open window; settle missing-evidence render
- Operator guide + clean-install gate (PRD-01 flow)
- D14 correlation_id half CLOSED by WP09 Task 1 (3ebfcb5)
- D14 mint-sites phrasing + HEAD-guard durability note; ledger re-ledgers
- 100-run seeded volume leg — PRD §3 retained evidence
- Second-install reuse runbook — the PRD §3 step-7 operator flow
- Timed operator legs — author-run, wall-clock recorded
- Timed-leg record precision — abort duration, verdict scoping, runbook ordering note
- PRD §6 reference timing + stress tier — both targets pass
- D13 decision landed; G2 deviation registrations
- Fault-matrix harvest + deterministic digest index
- Regenerated tree post-scrub
- G2 gate record
- Close-review honesty — PRD-11 registry-loss row structural, acceptance verdict qualified, index root-refusal disposition
- Define style guide and workbench architecture
- Define contextual alert message classes
- Support declarative custom device compositions
- Publish executable style guide
- Add portable mock-up and design tokens
- Design deterministic UI preview workflow
- Complete local UI preview developer loop
- Align preview documentation with what shipped
- Review findings persist to memory at every severity
- Bind RedTeam and external review outputs to the memory rule
- G2 owner acceptance — ACCEPTED 2026-09-14
- Standards synchronisation design and plan
- Two-repo discipline for the SDK submodule
- SDK guide moves to the SDK repository
- SDK repo self-sufficiency design and plan
- WP10 compatibility record + esp32 selection
- WP10 close reconciliation — plugin status honest, PID boundary, completion companion
- Record links stay in-docs — out-of-tree capture references as code paths (architecture gate)
- WBR fix — README lifecycle honest (adapter performs the handshake); scratch-name cosmetic
- Point SDK consumers at PyPI; simplify dead concurrency expression
- Close-out - PyPI/brew publishing design + implementation plan (landed)
- Record honesty — WP11 W3 ramp wording + W4 adapter-shape note
- Fix errata README's own post-move pointers (review M-1)
- Add Contributor Covenant 3.0 code of conduct
- Add SECURITY, CONTRIBUTING, SUPPORT and issue/PR templates
- Public-site styleguide and mockup for the SDK website
- Public-site styleguide v0.2 — AI instructions, sub-brands, icon set, nav mapping
- Add Built with AI panel crediting models and tooling
- Report via private advisory, not personal email
- Add permanent Discord invite to README, SUPPORT and site (#33)
- D4 + D14-details CLOSED by the interface-errata slice (#16)

### Features

- Validate exact-byte JSON documents
- Vendor admitted architecture contracts with verified manifest
- MCP client spike with local identity issuer
- Durable run lease request and event state
- Publish scoped host ABI as typed OTDP envelopes
- Sim_psu plugin with OVP OCP trip latch over the host ABI
- Sim_controller plugin with numeric uptime telemetry
- Fault matrix protocol fixtures and timeout-after-dispatch rule
- Sim_psu dc_psu class actions over the host ABI
- Strict admission of execution documents with executable fixtures
- Semantic admission with lexical scope and budget bounds
- Role binding resource closure and bench lease
- Safety policy allow rules and continuous conditions
- Eight-kind execution engine with occurrence ledger and body deadline
- Lexical references issued ids and three-valued trustworthy predicates
- Protection engine coordinator and truthful terminal records
- Project muninndb MCP as muninndb-benchweave, distinct from global connection
- Strict vendored-schema loaders; types-jsonschema carry-in
- Deterministic fixture catalogue with signed releases and fault statuses
- Ed25519 authenticity with expiry and sequence rollback rejection
- §10 semantic admission — closure, paths, spdx, conflicts
- Configured-origin resolver with strict routing and authenticated closure
- Admission — lifecycle gates, verified extraction, explicit package lock
- Idle-boundary activation record and cache plugin loader
- WP06 close — vacuous-constraint warning, store single-writer doc, full gates
- Origin-level signature policy — dev-unsigned skips authenticity only
- Publish_dev — unsigned dev packaging and keyless developer loop
- Add mock-qualified FNIRSI DPS-150 protocol and adapter
- WP07 task 1 — fastapi/fastmcp deps + schema-fidelity spike (gateway_info deep-equality proven)
- WP07 task 2 — v2 migration (generations, benches, devices, run_states, changes) + LeaseNotActive
- WP07 task 3 — content-addressed documents/artifacts/evidence + quota-bound retain_evidence
- WP07 task 4 — 14-code error model, observe seam, startup bench admission
- WP07 task 5 — control seam, §9 scoped dedup, run queue/worker, monitor evidence hook
- WP07 task 6 — bench event streams, seven kinds, principal-bound cursors, honest retention
- WP07 task 7 — two-phase admin changes with independently authenticated approvals
- WP07 task 8 — FastAPI app + FastMCP mount, 17 vendored-exact tools, token auth
- WP07 task 9 — 20 REST routers, exact statuses, 14-code error translation
- WP07 task 12 — licence display verdict, FastMCP qualification record, docs currency
- Add SDK-aligned presentation contracts and presets
- D8 seam validation against the vendored corpus
- D9 §5 accept-time busy/binding pre-checks
- D12 commissioned takeover slice + authority_changed emitters
- D13 lease expiry, events index, crash-window reconciliation, hygiene
- D13 lease_renew §6 semantics — duplicate returns same renewal (§9 keys, sweep resolves in leases), late renewal cannot revive an expired row
- D13 §6 lease contention — lease_create rejects live run/live lease (closes the D12 consume→reserve window), fixtures restructured for one-live-lease-per-bench
- D2 interface-v1.1.1 errata (change_apply approver_token), 1.1.0 untouched
- Wire fixture resolver session at bootstrap (unblocks admin change kinds)
- Click command tree + machine output paths
- At-rest setup/verify + WAL-aware backup/restore with daemon-hold
- Live status/demo with ephemeral fresh-install mode
- Textual renderers with plain-text fallback
- Truthful report model + markdown/JSON emitters
- Systemd template + permissions review + CI verify; serve production posture
- Seeded journey volume generator
- PRD target measurement + non-gating stress tier
- Fault-matrix harvest + digest index — evidence group complete
- Establish React and Storybook foundation
- Add Layered Precision themes and surfaces
- Add staged engineering controls
- Add semantic readings and alert bubbles
- Add engineering plots and data tables
- Add operator and admin workbench mock-ups
- Define deterministic preview fixture contract
- Validate preview fixtures and baseline states
- Serve deterministic preview API on loopback
- Add local preview-ui command
- Render SDK preview scenarios through host components
- Pin the preview wire document
- Canonical standards manifest with hash validation
- Deterministic bundle export
- Non-mutating sync check and make targets
- Generated compatibility matrix
- Adopt the SDK repo's sdk-tagged memory ledger (submodule 2b426a1)
- Evidence-backed session layer — handshake frames + telemetry drain
- Session establishment + telemetry drain/route per WP10 design
- Live demo script under the plugin — ramp, telemetry, session-survival flourish
- Git-cliff config, seeded CHANGELOG.md, merge-driven regeneration
- Standards GOVERNANCE.md rulebook + resident standards-governor agent
- Public site — static front door + Great Docs tree on Pages
- Add "Where it came from" — the origin of the project
- "What surprised us" and a validated "Where it stands"
- Align the main site to public-site styleguide v0.2
- Star-on-GitHub header CTA with live count

### Hardware Evidence

- First real-hardware contact — identity, session behaviour, live telemetry
- HW-04 leg 1 — baseline read-back via the shipped session layer (read-only)
- HW-04 leg 2 — voltage setpoint write accepted, no readback path (dispatch-only confirmed)
- HW-04 legs 3/3b/4/6 — setpoint+protection readback proven, both dialects live
- HW-04 leg 5a+5b — output toggle proven; setpoints APPLY (1.00V commanded, 1.0V at terminals incl. ramp sample); restores verified; mid-run crash emergency-restored + re-run clean (codec 260B feed bound honored)
- HW-04 panel observations — principal's screen mirrored remote writes and output state throughout (no divergence)
- Panel observation-3 — V-set display tracks local knob, not remote writes; local control live during PC session
- HW-05 legs 1+2 — session SURVIVES port-close and host process death (answered with no re-handshake both times)
- HW-05 leg 3 — session SURVIVES USB unplug/replug (cold query answered); /dev node name stable across re-enumeration; wake is power-cycle-bound
- Task 6 interim — identify verified end-to-end via adapter stack; read verb unverified (harness request-shape, next session)
- Task 6 complete — identify+reads wire-verified; ADAPTER DEFECT found: trailing telemetry poisons the session (live-only, mock-blind); fix direction recorded
- Fix verified on device — 165/165 clean reads over 60s through the correlated-wire adapter

### Miscellaneous

- Ignore gortex cross-harness shims, checkpoint state, rendered ISA
- Keep ISA local under docs/superpowers (muninndb convention)
- WP08 slice-1 closure chores (flake evidence, stash reconciliation, SDK validation report, lock_path register note)
- WP08 register close-out + vendored-tree guard
- Advance submodule for standards sync
- Sync submodule with SDK repo README and docs commits
- Submodule pointer - superpowers docs stay local
- Submodule pointer - ignore docs/superpowers
- Submodule pointer - standards sync check exit, vocabulary and deprecation reporting
- Submodule pointer - self-contained standards check and SDK CI pipelines
- Submodule pointer - matrix gate note points main-side
- Ignore the export staging directory
- SDK reviewer agent, conventions and MCP wiring (submodule 032e8d8)
- Submodule pointer - reviewer doc census completion
- Submodule pointer - absolute doc links (submodule 49d0bb9)
- Advance sdk pointer to v0.0.2 (0f105a3)
- Advance sdk pointer to bb3159e (tap-bump job)
- Ignore gortex git-hook artifacts (wiki, mermaid exports, docs bundle)
- Remove the retired firmware/esp32_reference placeholder
- Post-consolidation cleanup — retire firmware placeholder, re-lock dps150 contracts (#20)
- Advance SDK pointer — adapter API constant at 0.1.0
- Principal row calls — redate releases to the reset, align acceptance record
- Re-lock dps150 at the 0.1.0 baseline
- Re-lock dps150 at the 0.1.0 baseline (#22)
- Ignore device plugins' local vendored contracts
- Ignore device plugins' local vendored contracts (#23)
- Advance SDK pointer — gortex-artifact ignore guard (main #17 parity)
- Advance benchweave-sdk pointer (CoC + governance docs)
- Advance SDK pointer — docs site + public site merged (PR #4); repoint plugin-sdk stub
- Advance SDK pointer — close-out docs
- Advance SDK pointer — SDK-focused static site
- Advance SDK pointer — docs concurrency fix
- Advance SDK pointer — styleguide v0.2 brand
- Bump packages/sdk to 17d6ecb (star CTA + header wrap)
- Bump packages/sdk to 5da15c7 (gateway links to project website)

### Refactoring

- Keyless builders extracted to registry_common — dev loop loads no cryptography (surface-audit wave 2, item 15)
- Colocate device and simulator projects
- Align CLI with Click Rich and Textual
- Single-source preview constants
- One standards tree — corpus, prose and locks under standards/
- One standards tree (corpus, prose, locks under standards/) (#19)
- Id/version tree — standards/<id>/<version>/ with retention
- Reset every standard to 0.1.0 — the governance starting point
- Id/version tree, full 0.1.0 reset, and governance layer (#21)

### Testing

- WP06 acceptance — reuse, tamper, revocation, rollback, collision
- Pin cache-loaded module identity in run legs (Task 8 review)
- Cover high_water_invalid on malformed persisted state (final-wave review)
- Six-pin test-posture batch closes the WP05 coverage gaps (surface-audit wave 2, item 12)
- WP07 task 2 backfill — device method coverage + has_more/None paths (+ v2 newline)
- WP07 task 3 backfill — sha-mismatch rejection pinned
- WP07 task 10 — REST↔MCP parity suite + tier fix + deviation pins
- WP07 task 10 backfill — wrong-audience + expired token probes + register disclosure
- WP07 task 11 — event-recovery suite, worker poison guard, §144 disconnect+evidence failure
- WP07 task 11 backfill — evidence-gap record survives with refs pinned
- Satisfy strict CI typing for presentation tests
- Pin extra-property wire truth + D8 residual, anchor test corpus path
- _masked_error helper + wrong-typed approver_token 400 pin
- T10 whole-branch minors — served events_get letter, second-boot refusal, autocheckpoint pin
- T11 teardown pin + T12 real events_observed assertion
- PRD journey scaffold — discover/admit/select live
- Run journey REST+MCP+report, admin + stale-generation legs
- Fault legs + second-install reuse — journey complete
- Packaging asserts lock-wheel equality; smoke reads the SDK lock
- Self-contained standards check without a bundle
- Unchanged, clarification and breaking scenarios
- F5-quiet exercises the idempotency path it names
- WP11 carried minors — T1-1/T1-3/T2-6/T2-8/T5-9/T5-10

### Build

- Bundle versioned UI preview renderer
- Mount benchweave-sdk as a submodule at packages/sdk

### Ci

- Fixture signing keys move to repo secrets; public halves stay; add gates workflow
- Gate the UI toolchain and vendored-renderer freshness
- Gate PRs and releases on standards sync
- Gate-only package lane; SDK distribution moves to PyPI
- Push CHANGELOG.md via changelog app token
- Add manual trigger

### Review

- WP11 whole-branch fix wave — both verdicts clean, findings landed

