# Issue #450 fold addendum — the owner's fold-all row call, reconciled against current main

- **Parent record:** `.claude/deep-review/2026-10-13-issue450-interface-revision-design.md`
  (FROZEN — this file never edits its bytes; corrections live here)
- **Issue:** madeinoz67/benchweave#450, owner row-call comment of 2026-10-17T14:54:34Z
  ("Row call: fold all rows, no deferrals")
- **Branch:** `feat/issue450-corpus-revision` at `49b4b65e` (origin/main tip at authoring;
  base verified by `git branch --show-current` this session)
- **Date:** 2026-10-17
- **Gortex:** unavailable for this checkout (daemon admission error, probed once per the
  controller's brief); all file:line cites below are from bytes read this session with
  native tools.

---

## 1. The owner's row call (recorded)

Issue #450 comment, 2026-10-17T14:54:34Z, madeinoz67 — in substance:

- **Fold all, no deferrals.** Rows 1b (17 corpus tool descriptions), 2 (the two annotation
  rows), 3 (effective-limit echo, schema-field route), 5 (`origin` marker on
  `document_get`, schema-visible), and the rider (named x/y keys on capture_series
  points, SDK repo) fold into this one arc.
- Rows 1a and 4 are already merged (PR #455) — confirmed against main this session
  (§2, row PR-1).
- **D1–D5 all fold.** Nothing from the parent record's §6 deferral table is deferred.
- **F4 folds:** the CON-10 device-conformance wire field enters this revision batch.
- **F1:** interface 0.1.0 → 0.1.1 PATCH; the rider is a breaking change in the SDK repo,
  named in the SDK release notes.
- **F2:** the marker is optional and additive; the gateway always populates it; CI
  enforces it.
- **F3:** the MCP paging default stays `limit=1` with the honest echo. (D3's fold is
  thereby satisfied — the review the deferral asked for is this ruling; nothing further
  builds.)
- **F5:** the SDK release notes carry a BREAKING footer.
- **Branch and train:** `feat/issue450-corpus-revision` in its own worktree; PR order —
  the corpus revision, then the SDK leg, then the gateway pointer; if a sibling train
  holds `standards-manifest.json`, this train parks at review-complete and rebases once.
- Each row carries a RED pair and a GREEN rule; the PR holds the evidence.

## 2. Current-state re-verification table

The parent record was verified at base `1e49e2c5`. Main has since advanced to `49b4b65e`
(≈4 days; ~40 merges). Every file:line or version claim the parent record's mechanism
depends on was re-read this session. `git log 1e49e2c5..HEAD -- standards/interface/` is
empty — the interface corpus bytes are UNCHANGED since the parent record, so every
corpus-content discrepancy below is a design-time misread in the parent record, not
corpus motion.

### Holds (verified against current bytes)

| Parent claim | Current status |
|---|---|
| PR-1 (rows 1a+4) lands first | **Shipped**: PR #455 merged 2026-10-13 at `59b2a18c`, in this branch's history. `instructions=` at `src/benchweave/interfaces/mcp.py:147`; the corpus-anchored mirror at `tests/integration/test_interface_parity.py:141` (`_validate_output_def`) and `:167` (`_validate_corpus_output`), manifest-anchored via `active_contract_family` (`:118`, `:154`). The prior branch `fold/issue450-pr1-code-sides` is that PR's branch — fully merged, zero unmerged residue (checked `git merge-base --is-ancestor`). |
| 17 tools, one-line generic descriptions | Holds: 17 rows in `standards/interface/0.1.0/mcp-tools.json`, each `"STG <op>. Apply interface 0.1.0 authorisation and lifecycle rules."` (census this session, all 17 printed) |
| Row 2 defects: `run_find` `{ro:true, destr:true, idem:true, ow:false}`; `run_check` `{ro:false, destr:false, idem:false, ow:false}` | Hold verbatim (census) |
| Zero positional 2-arrays in the four interface machine artifacts | Holds: `"maxItems": 2` and `"minItems": 2` count 0 in each of mcp-tools.json, openapi.json, interface.schema.json, operation-catalog.json — the class correction (parent §2) stands |
| `bench_list_output.data` closed over exactly `{items, next_cursor}`, `additionalProperties: false` | Holds (`interface.schema.json` `$defs.bench_list_output`, oneOf ok-branch; same shape inline in mcp-tools/openapi/catalog) |
| The 14 named `$defs` exist (run/lease `*_output` ×8, `run`, `lease`, `event`, the paged/document outputs) | All present; `$defs` count 50; `origin` absent (to be added) |
| `Operations.bench_list` returns `(items, next_cursor)` | Holds at `src/benchweave/interfaces/operations.py:374-387`; `device_list` same at `:397-415` |
| `events_get` returns a dict | Holds at `operations.py:495-552`: `{events, cursor, stream_id, oldest_sequence, current_sequence}` |
| `document_get` builds `data` at one return | Holds at `operations.py:429-442` (the origin emission site) |
| `run_check` is the ungated advisory preflight; findings are `{field, reason}` | Holds at `operations.py:555+` (findings construction ~`:568-600`) |
| REST handler unwraps the tuple, wraps `{"items","next_cursor"}` | Holds at `src/benchweave/interfaces/rest.py:194-204` (bench_list); same pattern for the paged siblings |
| `_paged` shapes the tuple into the page object | Holds at `src/benchweave/interfaces/mcp.py:206-218`; `events_get` uses `_dispatch` directly (seam already returns a dict) |
| Clamp `max(1, min(limit, max_page_size))` in both adapters | Holds: `mcp.py:288/304/328` (three paged tool bodies, `limit: int = 1` defaults at `:284/:299/:323`) and `rest.py:200` (+ siblings) |
| Content-store document row `(sha256, raw_bytes, content_json, schema_id, stored_at)` | Holds at `src/benchweave/content/store.py:82-85`; `documents_by_schema_suffix` at `:102-103` |
| HTML autoescape | Holds at `src/benchweave/interfaces/ui.py:124` |
| Device projection carries the descriptor ref triple | Holds: `_device_projection` at `operations.py:1606+`, triple in the return ~`:1641-1647`; `_log_device_conformance` call at `:1633`; `device_list` maps rows through the same `_device_projection` (`:410`) — one emission site serves list and get |
| 6 interface machine rows in corpus-manifest | Holds (`corpus-manifest.json` `files`: 6 rows under `interface/`) |
| Derived surfaces move by mechanism, not by hand | Holds: `mcp.py:53` `_VENDORED_PATH`, `src/benchweave/interfaces/validation.py:38-43`, `scripts/architecture/check_interface.py:22-26` — all manifest-derived (read this session) |
| interface-contract.md sentences (observation-only; run_cancel durable/idempotent; wait-for-terminal) | Text holds (read at `standards/interface/0.1.0/interface-contract.md` §4/§5 area; exact line numbers not re-pinned — the sentences are the anchor) |
| Rider sweep set (SDK): catalogue schema row, seam emission, capture tests; plots/analysis/report out | Holds with moved lines (below); the only MCP-served consumer of the wire form is the tool edge itself (`benchweave_sdk_server/mcp.py:138`); report/web consume internal tuples (verified: `report.py:336-338` feeds `decimate_minmax(entry.points, …)`; `web.py:208-211` decimates server-side into x/y arrays — positional pairs never serialize to a client) |
| dependency-policy interface range `>=0.1.0,<0.2.0` | Holds (`standards-manifest.json` `dependency_policy.standards.interface.range`; `retired: ["1.1.0","1.1.1"]`) |

### Drifted — corrections this addendum makes to the parent record

1. **Row-2 "read-family norm" is wrong against the frozen bytes (parent §1/§3.2).** The
   parent record claims the pure reads carry "exactly `{readOnlyHint: true,
   idempotentHint: true}` with destructive/openWorld keys ABSENT". Measured: all ten pure
   reads carry **all four keys** — `{ro:true, destr:false, idem:true, ow:false}` (census
   above). The corpus is frozen since the parent's base, so this was a design-time
   misread. **Correction:** the two corrected rows (row 2) join the ACTUAL family shape —
   `{readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint:
   false}` — not the parent §3.2 two-key snippet. The parent's own rule ("nothing else,
   no new keys… matching the read family's shape") is honored by matching the family as
   it is.
2. **Row-2's defect class extends past the two named rows (D4's fold, measured).**
   `run_cancel` and `lease_release` serve `idempotentHint: false` today while the
   contract's own prose states both are idempotent ("It is durable, idempotent and
   records a reason"; "Lease release is idempotent"). Same defect class as row 2
   (annotation contradicts the contract), opposite direction. §3-D4.
3. **SDK version tier.** Parent §5 sequenced against "SDK 0.11.0 pending; rider rides
   0.12.0". Current: SDK at **0.15.0**, gateway gitlink `fca9c415` = tag `v0.15.0`
   exactly (`.gitmodules` pin agrees). The rider + interface-0.1.1 sync ride the next SDK
   MINOR: **0.16.0**. Re-derived sequencing in §5.
4. **The blocking trains are gone.** Parent §5's collision analysis assumed OTDP 0.2.3
   and plugin-ui 0.3.1 mid-flight. Current manifest: otdp **0.2.3** active (landed),
   plugin-ui **0.4.0**, plugin-ui-preview 0.2.0, registry 0.1.3, execution 0.2.0 — and a
   **seventh standard** now exists (`plugin-ui-class-reference` 0.2.0; the parent
   record's "six standards" census is stale). No open gateway PR touches
   `standards-manifest.json` (zero open gateway PRs at all; the one open SDK PR, #176,
   is CLI-only). **This train is unobstructed**; the park-and-rebase rule stays as the
   contingency.
5. **`bootstrap.py` moved.** Parent cites `bootstrap.py:259` under control/; the module
   is now `src/benchweave/interfaces/bootstrap.py` (the row-5 derivation's
   schema_id-at-admission anchor lives there; re-locate by symbol at build time).
6. **The "15 test files" loader census is wrong twice over.** Current census: 18 files
   under `tests/` carry the `interface/0.1.0` literal. Of those: **14 are corpus loaders**
   (§3-D1 lists them); `test_vendoring.py`'s three mentions are **fake-tree fixtures**
   (tmp_path + monkeypatched roots — they never touch the real corpus and do not move at
   the bump; the parent wrongly classed the file as a loader); `test_train_window.py:270`
   is a synthetic fake-tree fixture (does not move); `test_capture_services.py:22` and
   the parity docstring are comment-only; and **`test_zero_literal_gate.py:181` is an
   active-version equality pin** — `assert active_contract_family("interface") ==
   contract_family("interface/0.1.0")` — which MUST move to 0.1.1 in the sweep and which
   the parent record missed entirely by classing the file as loader/comment-only.
7. **The parent's CLI sweep item for row 3 is moot.** `GatewayClient.bench_list`
   (`src/benchweave/cli/client.py:114`) and `events_get` (`:177`) consume the REST
   response body via `_unwrap` — the seam's tuple never reaches them, and the page dict
   keeps its outer shape. No CLI change is needed for the echo (verified by reading both
   bodies).
8. SDK file:line drift (mechanism unchanged): `_CAPTURE_SERIES_RESULT`
   `catalogue.py` ~530-545 → **`:410-427`** (positional items `:416-424`); `_op_capture_series`
   def still `seam.py:2143`, emission line now **`:2203`**; SDK server `instructions=`
   `mcp.py:278/:288-294` → **`:320`**; `_HOST_INFO_RESULT` ~156-160 → **`:72-75`**;
   `test_capture_lifecycle.py` wire-form sites `:313`/`:320` hold; the parent's ":345 raw
   call" is now the `payload_too_large` refusal arm at ~`:341-350` (verify-in-arc, not an
   assert change).

## 3. Per-item mechanisms for the folded items

### D1 — shared active-contract loader for tests (folded; replaces the literal sweep)

**Mechanism.** No new helper is written. The production helper
`benchweave.vendoring.active_contract_family("interface")` already exists, and the
landed #455 parity suite is the in-tree precedent for using it from tests
(`tests/integration/test_interface_parity.py:118` import, `:154` use — proven in CI).
Each loader file's `Path(__file__)… / "standards" / "interface" / "0.1.0"` construction
is replaced by the helper call.

**Files (the 14-file loader set, regenerated this session):**
`tests/contracts/test_architecture.py:752`; `tests/integration/test_event_recovery.py:853`;
`tests/integration/test_interface_parity.py:121` (the `CONTRACTS` constant the parent
record left for the sweep); `tests/integration/test_mcp_baseline.py:26`;
`tests/integration/test_mcp_fidelity_spike.py:40`;
`tests/integration/test_mcp_tools.py:42,46,141`;
`tests/integration/test_registry_changes.py:35`; `tests/integration/test_takeover.py:53`;
`tests/unit/test_error_model.py:30`; `tests/unit/test_seam_admin.py:36`;
`tests/unit/test_seam_control.py:42`; `tests/unit/test_seam_events.py:19`;
`tests/unit/test_seam_observe.py:23,150`; `tests/unit/test_seam_validation.py:10`.

**Explicitly not swept:** `test_vendoring.py` (fake-tree fixtures — the literal is the
test's subject); `test_train_window.py:270` (synthetic tree); docstring mentions
(opportunistic); `test_zero_literal_gate.py:181` — the active-version pin **moves to
`"interface/0.1.1"` by hand** (it is a tripwire whose subject is the active version; a
derived pin would be vacuous).

**The held property (so the sweep cannot rot).** A small guard test beside
`test_zero_literal_gate.py` asserts that no `.py` under `tests/` builds a corpus-load
path from an `interface/<version>` literal except the registered exemptions (the
fake-tree fixtures, the vendoring lookup keys, the zero-literal pin, docstrings). This
mechanizes D1 the way the zero-literal gate mechanizes its own sweep — the registered-
exemption shape is the in-tree precedent (`scripts/standards/count_version_literals.py`'s
REGISTER).

**RED/GREEN.** RED: plant a `… / "interface" / "0.1.0" / "mcp-tools.json"` load in a
swept file → the guard reds naming the file. GREEN: all 14 loaders resolve via the
helper; `grep -rn 'interface/0\.1\.0' tests/ --include='*.py'` returns exactly the
registered exemptions (the set is regenerable by the guard itself). Kill: if the guard
cannot distinguish a load from a fixture without heavy parsing, the guard is rewritten
as an allowlist of files permitted to carry the literal — not waived.

**Invariant impact:** none new (CON-4's packaged-first resolution; the #455 precedent
proves CI behavior).

### D2 — marker scope widening beyond `document_get`

The parent §1 census named the other crossings; the fold builds two legs and gets the
third by construction:

1. **Device objects.** `_device_projection` (`operations.py:1606+`) gains an `origin`
   sibling of `descriptor`: `{"kind": "plugin", "basis": "admitted-device-ref"}` — a
   constant derivation (every device row IS an admitted descriptor; nothing to
   classify). The `document` sub-object of the twin is OMITTED here: the ref triple is
   the adjacent `descriptor` field, and duplicating it doubles the wire. The `origin`
   def therefore makes `document` optional within `kind: plugin` (the `document_get`
   emission always includes it — CI-enforced; the device emission never does). One
   emission site serves `device_get` and `device_list` (both project through
   `_device_projection`, verified `:410`).
2. **`run_check`.** `data` gains `origin` = the origin twin of the checked binding
   document — the SAME pure derivation as `document_get`, applied to the binding row the
   body already fetched. The provenance question an agent has about a finding is "who
   authored the document these findings quote"; the twin answers it. Findings themselves
   stay `{field, reason}` (the `field` key already names the document path; the `reason`
   string is the gateway's own words — marking it `plugin` would be false).
3. **Future document families:** automatic — the parent §3.4 derivation rules are total;
   a new family serves kinded or as `unclassified-fallback` basis. No build.

**Corpus:** `device` def and `run_check_output` gain optional `origin` (four artifacts,
same edit set as row 5).

**RED/GREEN.** RED: revert the emission — device envelopes lack `origin`, new arms fail.
GREEN: every device envelope (list and get, both transports) carries
`kind:"plugin", basis:"admitted-device-ref"`; `run_check` carries the binding document's
twin; D5 arms prove schema validity. Kill: any device row that cannot serve a constant
twin means an emission path bypasses `_device_projection` — find it, don't special-case.

### D4 — annotation-policy widening

**Corpus motion in 0.1.1 (beyond row 2's two rows, which take the four-key family shape
per §2-correction 1):**

- `run_cancel`: `idempotentHint` false → **true** (contract: "durable, idempotent").
- `lease_release`: `idempotentHint` false → **true** (contract: "Lease release is
  idempotent").
- `lease_create` / `lease_renew`: **stay false**, stated not silently dropped — creation
  is not idempotent, and renew's replay safety is §9 request-layer duplicate suppression,
  not a tool-effect-class claim. `destructiveHint`/`openWorldHint` untouched on every
  other tool.

**Checker rows** (`scripts/architecture/check_interface.py`, after the tools load ~`:148`
— inline `check()` calls are the checker's own idiom):

1. ro-true ⇒ destr-not-true (parent §3.2's row — catches the `run_find` defect class).
2. Closed-shape row: every tool's `annotations` carry exactly
   `{readOnlyHint, destructiveHint, idempotentHint, openWorldHint}` — pins the actual
   four-key family and corrects the parent record's two-key description.
3. Named-pair row: `{run_cancel, lease_release}` carry `idempotentHint: true` — the
   named-specimen precedent is the checker's own `change_apply` self-approval row at
   `:198-200`.

**What the guard does not catch:** idempotency for any tool the contract does not
sentence about — there is no mechanical source in the corpus; the named-pair row is
deliberately exhaustive over contract-stated idempotency (2 tools; denominator: 17).

**RED/GREEN.** RED: flip `run_cancel` back to `idem:false` in the 0.1.1 copy → row 3
reds; flip `run_find` back to `destr:true` → row 1 reds. GREEN: all three rows green with
the four corrected annotation rows (row 2's two + D4's two).

### D5 — paged-output corpus validation

**Mechanism.** The parity suite's own docstring names the gap at
`tests/integration/test_interface_parity.py:150` ("What it does NOT cover: the paged
`*_list`/`events_get` output defs") — the fold closes exactly that. At the paged capture
sites (the EXACT_CASE fixtures `:586/:596/:640` and the live call `:1068` and siblings),
add `_validate_corpus_output("bench_list"|"device_list"|"events_get", envelope)` arms —
the helper #455 landed (`:167`), extended to three more op names. Denominator: 3 paged
ops × both transports.

**The echo's teeth.** `limit` is schema-optional (PATCH pattern), so schema validity
alone cannot prove the echo. The arms additionally assert presence and integer type of
`limit` equal to the clamped requested value on both transports (parent §8 row 3's rule,
unchanged).

**RED/GREEN.** RED: plant a page-shape fault (drop `next_cursor`; serve `limit` as a
string; serve a page without `limit`) → the arms red by name. GREEN: all captured pages
validate against the 0.1.1 `*_output` defs with the echo present. Kill: an arm passing
the planted fault means it reads the wrong def or does not assert presence — re-anchor,
never waive.

### F4 — the CON-10 device-conformance wire field

**The site already exists and says so.** `_device_projection`'s own comment
(`operations.py:1617-1623`): "the wire field lands with the interface lane" — this is
that lane. `_log_device_conformance` (`operations.py:193+`) already calls the one
authority, `classify_descriptor_pin` (`src/benchweave/control/documents.py`; `DescriptorPin`
at `:243` — fields `otdp_version`, `status`, `conformance`, `deprecated`, `note`,
`acknowledgement`).

**Wire shape.** The device object gains optional `conformance`:

```json
{"otdp_version": "<pin>", "status": "served|yanked|nonconforming|retired|unknown|unclassifiable|dev|rc",
 "conformance": "conforming|non-conforming", "deprecated": false, "acknowledged": false}
```

Closed enums only; `note` (free-form VR-37 text) stays server-side — the wire stays
closed (disclosed: an agent needing the refusal detail reads it via the operator log
channel, not the device object).

**Presence rule (the capture-keys posture — CON-10's own amendment precedent):** the
field is present **iff** the descriptor row carries an `otdp_version` pin. Legacy
pre-dialect rows omit it (nothing to classify — `_log_device_conformance`'s R10
precedent). A `StandardsError` from malformed governance bytes omits the field and keeps
the existing log line (the read path never crashes on governance bytes — the helper's
own degradation precedent).

**Emission:** `_device_projection` calls `classify_descriptor_pin` directly (one
authority, both consumers — REG-4's read-not-import pattern is respected;
`classify_descriptor_pin` is gateway code, not an SDK import). One site serves
`device_get` and `device_list`.

**Corpus:** `device` def gains optional `conformance` (new `$defs.conformance`), four
artifacts.

**RED/GREEN.** RED: device_get on a pinned fixture lacks the field → new arm fails.
GREEN: served on every pinned device; `status`/`conformance` pinned per fixture class —
served pin → `{served, conforming}` on the parity lattice's devices; the
yanked/retired/nonconforming cells are pinned at the unit seam with synthesized policy
rows (the in-tree pattern for policy states) **if** the parity lattice carries no
non-served pins — the denominator is stated at build time from the lattice actually
present. Kill: a pinned device serving a class the classifier's Q6 table does not name
means the wire enum lags `DescriptorPin.status` — extend the enum, never truncate.

**Invariant impact:** CON-1's 2026-09-27 amendment sentence ("the wire field lands with
the next interface bump") becomes true; CON-10 gains a dated amendment recording the
wire field and its presence rule; CON-5's amendment (parent §7) extends to name it.

## 4. Revision mechanics for interface 0.1.1 (reconciled against current standards state)

**Copy-never-move.** `standards/interface/0.1.0/` (9 entries: 4 machine JSON artifacts,
2 example fixtures, `interface-contract.md`, `README.md`, `review-scenarios.md`,
`validation-report.md`) is copied wholesale to `standards/interface/0.1.1/`; every edit
lands in the copy; the 0.1.0 dir and its 6 corpus-manifest rows stay digest-frozen. The
6 new rows cite `interface/0.1.0/<path>` as `source`; digests move only through
`uv run python -m benchweave.standards repin` (edit → repin → export; never
hand-spliced).

**The corpus edit set (all inside the copy):**

1. `mcp-tools.json` — 17 descriptions (parent §3.1 template family, version-stamped
   "interface 0.1.1"); **4 annotation rows** (row 2's two in the four-key family shape +
   D4's two); the 3 paged outputSchemas gain optional `limit`; `document_get` outputSchema
   gains optional `origin` (row 5); `device` objects and `run_check` output gain optional
   `origin` (D2); `device` gains optional `conformance` (F4).
2. `interface.schema.json` — the same $defs edits; new defs `origin` (kind/basis closed
   enums, `document` optional within kind=plugin) and `conformance`.
3. `openapi.json` — the same response-schema edits.
4. `operation-catalog.json` — the same per-op `output_schema` rows.
5. `interface-contract.md` — errata: the limit echo, the origin field and its scope, the
   conformance field and its presence rule, the corrected annotation semantics; history
   row "Supersedes interface 0.1.0" + the errata list.
6. `examples/operation-vectors.json` + `examples/mcp-start-exchange.json` — regenerate
   via the checker (byte-pinned by the report check; the `document_get` specimen site
   `check_interface.py:105-108` gains whatever the auto-derivation does not produce for
   `origin`).
7. `validation-report.md` — regenerate (`--write-report`, refuses on red). New checker
   rows move the count → `docs/README.md:20` ("256 … checks") moves with it (obligation
   13; the pin ties README to live).
8. `README.md` — version-reference row if it names the active version;
   `review-scenarios.md` — copied; verify no active-version claims at build.

**Checker additions:** the three D4/row-2 rows (§3-D4).

**Manifests:**

- `standards/standards-manifest.json` — the interface entry: `version: "0.1.1"`,
  `released` date, `supersedes: "0.1.0"`, normative list re-pointed to 0.1.1 paths.
- `dependency_policy.standards.interface.range` slides `>=0.1.0,<0.2.0` →
  `>=0.1.1,<0.2.0`. **G-3/VR-43: a range change is a coordinator decision requiring a
  linked ruling reference in the PR body** — the owner's row-call comment is the ruling;
  the PR body cites it by timestamp.
- `standards/corpus-manifest.json` — 6 new rows via repin.

**Bump window (G-5, which superseded the 24h window on 2026-10-12):** a standard may not
bump while its previous released version's SDK leg is outstanding. Interface 0.1.0's SDK
leg is complete (SDK 0.15.0's lock and vendored tree carry it) — no hold. One bump per
train: this is the one. PATCH class ⇒ no SM-5 migration note (that gate is
MINOR-or-greater).

**The in-arc sweep:**

- D1's 14 loader files ADOPT the helper in this same arc (the fold merges the parent's
  sequenced literal-sweep and refactor into one motion).
- `test_zero_literal_gate.py:181` pin → `"interface/0.1.1"` (hand edit, one line).
- `scripts/standards/docs-literal-baseline.json` + counter — docs ratchet refresh via
  the explicit `--refresh-docs-baseline` (its diff is the review surface; the #444
  motion).
- Docs naming the ACTIVE interface (obligation 18): `docs/README.md:17-21`;
  `docs/project-index.md:23`; `docs/ai-device-reviewer.md:94` + its baseline paragraph;
  `docs/device-developer-guide.md:802` + its Baseline line;
  `docs/smart-test-gateway-architecture-v1.5.md:323/:329` + §21 consolidated baseline;
  `docs/development.md` baseline; `docs/internal/drift-and-obligations.md` rows 1-2
  (obligation 18(h) prose pointers).
- **Not swept (frozen probes — obligation 18(i), copy-never-move keeps them resolving,
  they claim nothing about "active"):** `docs/internal/invariants.md:429`'s
  `interface/0.1.0/interface-contract.md` pin, the parity-tests bullet in
  drift-and-obligations' conventions section, and CLAUDE.md principle 6's reference.
- **No motion (derived; verified this session):** the checker constants, `validation.py`,
  `mcp.py` `_VENDORED_PATH`, `vendoring.active_contract_family`, the website (tokens,
  CON-13), `docs/compatibility-matrix.md` (rendered, CON-12).

**CON-4 window:** `make check-sdk-standards` reds from slice-1 merge until the pointer
PR lands — expected, bounded by §5, disclosed in the PR body.

## 5. Slice and PR stack plan (against the current train state)

Current state: gateway main at `49b4b65e`; zero open gateway PRs (nothing holds
`standards-manifest.json`); SDK at 0.15.0 with one open SDK PR (#176, CLI-only, no
standards surface — merges independently whenever; no interaction with this stack).

- **Slice 0 (this addendum).** Commit on `feat/issue450-corpus-revision`. Docs-only.
- **Slice 1 — the corpus revision PR** (gateway repo; `feat/issue450-corpus-revision` →
  main). **One PR, one batch commit** carrying per-row RED evidence in its message (the
  row-call-fold doctrine), because the corpus motion and the code emissions are atomic —
  CON-3 pins served schemas to the corpus verbatim, and `additionalProperties: false` on
  the page/data/device defs means an emitted-but-undeclared `limit`/`origin`/
  `conformance` is a schema-invalid wire response; they cannot land separately. Contents:
  the 0.1.1 copy + all corpus edits (rows 1b/2/3/5; D2 legs 1-2; D4; F4) + checker rows +
  seam/adapter emissions (the echo at `operations.py` bench_list/device_list/events_get +
  `_paged`/REST handlers pass-through; origin at `document_get`/`_device_projection`/
  `run_check`; conformance at `_device_projection`) + D1 adoption + the D1 guard + the
  zero-literal pin + D5 arms + per-row/per-item RED/GREEN arms + docs sweep + report regen
  + repin + export. Gates: fast lane at the commit; full battery + both tripwires;
  Tier 3 + standards-governor mandatory + two-lane refute.
  - **Split contingency:** if the governor or refute lane requires a smaller diff, the
    test-only motions (D1's helper adoption + guard, D5 arms) can split into a stacked
    PR — the corpus+emission core cannot.
  - **Parking:** no sibling train holds the manifest today. If one opens before merge,
    park at review-complete; rebase once (owner's rule).
- **Slice 2 — the SDK leg** (SDK repo; branch off SDK main). One PR carrying: the rider
  (`catalogue.py:410-427` items schema → `{x, y}` object, required both keys,
  `additionalProperties: false`; `seam.py:2203` emission → `[{"x": x, "y": y} for x, y
  in served]`; test sites `test_capture_lifecycle.py:313/:320` + verify-in-arc
  `:341-350`, `test_capture_catalogue.py`, `test_catalogue.py`, `test_seam.py`,
  `test_mcp.py`) + `make sync-sdk-standards` (vendored tree + lock + compat mirror +
  interface 0.1.1 rows) + the BREAKING release-notes footer naming the point-shape
  change and the old→new mapping (F5; the SA-PREVIEW exit footer is the in-tree
  precedent). SDK PR body notes no SDK-side issue exists by design (single issue stream;
  gateway #450 carries it). Opens after slice 1 merges (the sync leg consumes slice 1's
  export); the rider's code itself is slice-1-independent but batches into the one
  release.
- **Slice 3 — SDK release cut.** After slice 2 merges: `make release-cut
  VERSION=0.16.0` in the SDK repo (#408 order: SDK PRs merge → release cut → pointer
  PR). If another SDK train claims 0.16.0 first, this train takes 0.17.0 — the label
  moves, the class (MINOR, breaking rider on the 0.x line) does not.
- **Slice 4 — the gateway pointer PR.** Gitlink → the released tag + `.gitmodules` `pin`
  in the SAME commit; the regenerated SDK lock, the moved `sdk_compatibility` mirror and
  the re-rendered `docs/compatibility-matrix.md` ride it (obligation 7 version-pairing);
  `make check-sdk-standards` returns green; the `sdk-drift` lane reads the new pin. The
  train closes here; issue #450 closes after this merge (all PRs in both repos merged).
  Tier 3 by the pointer rule.

## 6. Measurable proof — pre-committed acceptance rules

All conformance mechanics; each rule states RED / GREEN / kill. Denominators stated per
row. (Parent §8's rows 1a/4 are closed by #455 and are not restated.)

| Item | RED (mechanism disabled = effect disappears) | GREEN (ships when) | Kill / underpowered |
|---|---|---|---|
| 1b descriptions | Revert the 0.1.1 copy's descriptions to one-liners → served-description arms fail | tools/list serves the 17 template-family descriptions; parity description pin green (17/17) | Pin passing on stale bytes = the pin reads the wrong dir; fix the sweep, not the test |
| 2 + D4 annotations | Revert any of the 4 corrected rows → checker rows 1/3 red; served-annotation arms fail | run_find/run_check serve the four-key family shape; run_cancel/lease_release serve `idem:true`; checker rows 1-3 green (denominator 17 tools) | A checker row that cannot distinguish corrected from defect = rewrite the row, never waive |
| 3 echo | Revert the seam to tuple returns → pages lack `limit` → D5/parity arms fail | bench_list/device_list/events_get carry integer `limit` = the clamped value on BOTH transports, envelope-equal (3/3 ops) | Cross-transport echo divergence = emission leaked to an adapter; fix the site |
| 5 origin (document_get) | Revert the origin emission → descriptor-family document_get lacks `origin` → arm fails | Every document_get success carries schema-valid `origin`; kind pinned per fixture family (descriptor→plugin, lattice→operator, terminal-record→gateway) | A misclassified REAL fixture family = kill; census arms must cover all three kinds before GREEN |
| D2 origin (devices, run_check) | Revert `_device_projection`/`run_check` emissions → arms fail | Every device envelope (list+get, both transports) carries `{plugin, admitted-device-ref}`; run_check carries the binding doc's twin | A device row served without origin = a path bypasses `_device_projection`; find it |
| D1 loader helper | Plant a literal corpus-load path in a swept file → the guard reds naming it | All 14 loaders resolve via `active_contract_family`; the literal census over `tests/` returns exactly the registered exemptions | Guard that passes the plant = the exemption set is too broad; tighten, never delete |
| D5 paged corpus arms | Plant `next_cursor`-drop / string-`limit` / echo-absent in a served page → arms red by name | All captured pages (3 ops × 2 transports) validate against 0.1.1 defs WITH the echo present | Arm passing a planted fault = wrong def or no presence assert; re-anchor |
| F4 conformance | Omit the field on a pinned fixture device → arm fails | Every pinned device serves `conformance`; status/conformance pinned per class over the lattice present (denominator stated at build from the lattice); legacy unpinned rows omit it (pinned) | A class outside the wire enum = extend the enum from `DescriptorPin.status`, never truncate |
| Rider | Serve positional points from a scratch copy → the revised items schema refuses them | Positional refuses / named admits / the enumerated sweep set green (2 src + 3-5 test files, SDK repo) | A post-sweep consumer of the positional wire form found = extend the set with disclosure |
| Train | `git diff origin/main...HEAD -- standards/` empty on slices 0/2-side PRs; non-empty ONLY on slice 1 | Full battery + both tripwires green; check-sdk-standards green at slice 4 | Tripwire red on a non-corpus PR = leaked corpus motion; abort and split |

Effect sizes: binary conformance (present/refused) — no percentage claimed. Denominators:
17 descriptions; 4 annotation rows; 3 paged ops; 8 run/lease envelopes (closed by #455);
1 document_get def + 2 D2 surfaces; 14 loader files; 2 src + 3-5 test files (rider).

## 7. Review tier and Step-1 keyword scans (#254)

- **Slice 0 (this addendum):** path rules — docs-only (Tier 1). Keyword scan over this
  document's own text (docs and code alike). Whole-file counts are self-referential:
  this scan statement itself carries each keyword (the self-fire the rubric's interplay
  rule calls intended), so the stable, honestly-countable figure is the hit count
  OUTSIDE this §7 section: `sha256` 1 (the content-store row cite in §2) and `recovery`
  1 (a test filename inside §3-D1's loader list) — the other six keywords 0 outside §7.
  The rule fires on the whole-diff text regardless of the self-reference:
  **this commit is Tier 3 by the keyword rule** (text-carries-depth — the rubric's
  intended interplay for a docs diff that defines agent-facing surface). The build lane
  re-scans the real diff and corrects per the rubric if counts move.
- **Slice 1 (corpus revision):** **Tier 3** — the path rule fires (touches `standards/`
  including JSON Schema files and both manifests) AND the keyword rule fires (`sha256`
  appears in the corpus/manifest/report diff text; expected count high — pinned
  properties and digest-shaped patterns). Standards-governor mandatory; two-lane refute.
- **Slice 2 (SDK repo):** the SDK repo's own gates apply; the rider diff text carries
  none of the eight keywords (the `{x, y}` object schema and the emission line carry
  none) — Tier-2-equivalent SDK-side; the sync leg is the SDK repo's own standards lane.
- **Slice 4 (pointer PR):** **Tier 3** by the pointer rule (advances the submodule
  gitlink). Keyword scan over the expected diff (gitlink + pin + lock + mirror + matrix):
  all eight keywords 0 (the lock's digest hex strings do not contain the keywords).
- **Maximum across slices: Tier 3.**

## 8. Top risks, each with its falsifier

1. **The four-key family correction is wrong** (maybe the corpus intended the two-key
   form). Falsifier: the census is mechanical and reproducible — all 17 rows carry four
   keys today; the checker's closed-shape row pins whichever shape ships. If the owner
   rules for the two-key minimal form, that is a separate corpus motion with its own
   errata row, not a silent edit here.
2. **The origin/conformance derivations misclassify a real family.** Falsifier: census
   arms over the fixture lattice per kind/class before GREEN (the parent §11.2 pattern);
   over-marking (operator doc carrying a descriptor `$schema` URN → plugin) is the
   conservative direction, disclosed in the schema description.
3. **The seam tuple→dict change breaks an unnoticed internal caller.** Falsifier: the
   caller census (adapters only; the CLI consumes the REST body — verified §2
   correction 7) plus the full battery; any fourth caller the census missed reds in
   slice 1's battery, which is the tripwire doing its job.
4. **D1's helper adoption changes resolution for some test** (packaged-first vs repo
   path). Falsifier: #455's parity suite already loads via the helper in CI — the
   landed precedent; the full battery covers the rest.
5. **The one-PR batch is too large to review honestly.** Mitigation: per-row RED
   evidence in the commit message, governor + refute lanes, and the §5 split
   contingency for the test-only motions. Kill direction: a governor ruling that the
   core must split is impossible under CON-3 atomicity — that ruling would itself be a
   design change requiring the corpus to declare the fields first, i.e. the reverse
   order; surface it to the owner rather than splitting silently.
6. **SDK release-train collision on 0.16.0** (the ui-html pin-bump train or another
   arc). Falsifier: the release-cut is first-come; §5 slice 3 already names the fallback
   (0.17.0, class unchanged).
7. **The docs ratchet blocks on the descriptions naming "0.1.1" in prose.** Measured
   posture: the refresh is an explicit reviewable diff (the #444 motion); one amend, not
   a design risk.

## 9. What this arc still does NOT cover

- **Promoting the standalone catalogue to a normative corpus standard** (F5's rejected
  alternative) — new-standard admission; its own arc if ever wanted.
- **`analysis_view` / report internal positional tuples** — measured NOT wire surfaces
  (`web.py:208-211` decimates server-side into x/y arrays; the report renders SVG
  server-side), so the rider's "last positional surface" claim holds for WIRE surfaces
  (MCP catalogue + REST bodies) with that denominator stated. A future host serializing
  `analysis_view` entries raw would reopen it; named here so the claim's scope is exact.
- **The MCP paging default change** (F3) — ruled KEEP `limit=1`; a friendlier default is
  a different row with its own parity evidence, not deferred by this arc.
- **`openWorldHint` policy** — no contract sentence derives it; D4's boundary is the
  contract-stated idempotency pair plus the two mechanical checker rows. Widening needs
  a corpus sentence first.
- **A parity-lattice device pinned yanked/retired** (F4's class coverage beyond served)
  — carried by unit-seam synthesized policy rows if the lattice lacks one; lattice
  fixture work is future motion, not this arc's blocker (denominator stated at build).
- **The `sdk_compatibility` mirror and lock motion** — slice 4's pairing per obligation
  7; not editable in slice 1 (the lock stays authority; the mirror follows the pointer
  train).
- **The ui-html 0.2.0 release event / D-B5 pin-bump** — a different train; interacts
  only through SDK release ordering (risk 6).
- **Two-component prose version claims** (issue #188 deferral 5) — untouched.
- **Register dispatch for operator-facing docs** — `interface-contract.md` and the
  machine artifacts are the vendored standard (agent-facing); the docs-sweep edits to
  `docs/` operator surfaces dispatch the `document-writer` agent per the CLAUDE.md
  register rule at build time.
