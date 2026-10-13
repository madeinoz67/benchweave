# Design — issue #450: the MCP-surface interface revision

- **Issue:** madeinoz67/benchweave#450 (five rows + one rider, from the published agent-surface
  antipattern catalog, CC BY 4.0)
- **Date:** 2026-10-13
- **Status:** PROPOSED — two forks need the owner's word (§10). Rows 1a/3/4/5 and the rider are
  BUILD; row 1b/2 BUILD as errata; **the class call is corrected against the row-call comment,
  with measured evidence (§2)**.
- **Branch:** `feat/issue450-interface-revision` (design record commit; no corpus bytes touched —
  the standards tripwire holds on this branch).
- **Design-time tier and keyword scans (#254):** stated per slice in §9. Maximum across slices:
  **Tier 3** (the corpus-revision slice; `standards/` path rule and the `sha256` keyword rule
  both fire on its expected diff). Slices 1 and 3 are Tier 2 on the current evidence; the build
  lane re-scans the real diff at commit time and corrects the statement per the rubric if the
  counts move.

---

## 1. The rows, measured against the real corpus and code

Every claim below was verified in the corpus and code at this branch's base
(`1e49e2c5`, origin/main tip).

### Row 1 — agent guidance gap (MED)

**1a (code-side):** `build_mcp` (`src/benchweave/interfaces/mcp.py:102`) constructs
`FastMCP(name="benchweave-gateway", auth=StgTokenVerifier(...))` — no `instructions`
parameter. The SDK standalone server's `build_mcp`
(`packages/sdk/src/benchweave_sdk_server/mcp.py:278`, body at :288-294) passes
`instructions=(...)` and its `host_info` result carries `absent_guarantees`
(`catalogue.py` `_HOST_INFO_RESULT`, lines ~156-160). The SDK posture is the parity
reference and the in-tree precedent (fastmcp 4.0.3 serves `instructions` — proven in the
sibling server, same fastmcp).

**1b (corpus):** all 17 served descriptions are one-line generics served verbatim from the
corpus by CON-3's pin: `mcp.tool(..., description=spec["description"])` (`mcp.py:224`),
and the parity suite pins served `tool.description == vendored description`
(`tests/integration/test_interface_parity.py`, `test_wire_tools_list_exact_set_and_schemas`,
the description-equality arm). The corpus descriptions read
`"STG <op>. Apply interface 0.1.0 authorisation and lifecycle rules."` — checked across all
17 rows of `standards/interface/0.1.0/mcp-tools.json`. The lifecycle sentences the surface
should carry are the contract's own (interface-contract.md:64: "Clients must wait for
terminal evidence before asserting completion"; :62 run_cancel durable/idempotent; :40
observation endpoints never trigger instrument reads).

### Row 2 — annotation drift (LOW): both defects verified in the corpus bytes

Extracted directly from `standards/interface/0.1.0/mcp-tools.json`:

| Tool | Served annotations today | Defect |
|---|---|---|
| `stg_v1_run_find` | `readOnlyHint: true, destructiveHint: true, idempotentHint: true, openWorldHint: false` | ro+destructive contradict each other; and destructive is factually wrong (run_find is a §9 request-id resolution read) |
| `stg_v1_run_check` | `readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false` | `readOnlyHint: false` contradicts the tool body — `run_check` is the advisory preflight: "No reservation, no device I/O" (`operations.py:558-561`); it performs zero writes and runs ungated (`mcp.py` run_check body comment) |

The read-family norm: the corpus's pure reads
(gateway_info, bench_list, bench_get, device_list, device_get, document_get, run_get,
events_get, evidence_get, artifact_read) carry exactly `{readOnlyHint: true,
idempotentHint: true}` with destructive/openWorld keys ABSENT. Both corrected rows join
that family: `{readOnlyHint: true, idempotentHint: true}` — nothing else, no new keys.

### Row 3 — quiet default page (LOW): the D3 residual, measured

The seam's paged ops return a bare tuple with no limit echo:
`Operations.bench_list` returns `(items, next_cursor)`
(`src/benchweave/interfaces/operations.py:374-387`); the REST handler wraps
`{"items", "next_cursor"}` (`rest.py:196-204`); the MCP adapter likewise
(`mcp.py` `_paged`, ~:250-260). Both adapters clamp with the identical formula
`max(1, min(limit, max_page_size))` (mcp.py and rest.py), then the seam re-validates the
clamped value against the corpus input schema. The MCP Python signature defaults
`limit=1` (`mcp.py`, bench_list tool body), fastmcp 4.0.3 does not enforce the pinned
schema's `required` (measured, D3's root, the parity suite's D8 register), so
`bench_list()` with no arguments serves a one-item page that names nothing.

The corpus output schemas are closed: `$defs.bench_list_output.data` requires exactly
`{items, next_cursor}`, `additionalProperties: false`
(`interface.schema.json` `$defs.bench_list_output`; the same shape inline in
`mcp-tools.json` bench_list `outputSchema`). Adding the echo therefore requires the corpus
row; the corpus is the authority (drift obligation 1).

### Row 4 — envelope validation is events-only (LOW-MED): measured

`_validate_event_def` (`tests/integration/test_interface_parity.py:80-86`) validates served
events against `$defs.event` of `interface.schema.json`. No run or lease output envelope is
ever validated against the corpus — the suite compares MCP vs REST full envelopes only, so
a seam-shape fault present on both sides passes (the WP07 lesson CON-5 names). The corpus
already carries the anchors: `$defs.run`, `$defs.lease`, and the per-op `*_output` defs
(`run_start_output`, `run_get_output`, `run_find_output`, `run_cancel_output`,
`run_check_output`, `lease_create_output`, `lease_renew_output`, `lease_release_output`)
— verified by listing `$defs` keys. The mirror is mechanical.

### Row 5 — plugin-authored strings carry no provenance mark (MED): the census

The HTML side autoescapes (`ui.py:124` `autoescape=True`, plus the ui-html package env and
stream templates); the MCP side has nothing. Census of what crosses the MCP surface from
outside the gateway's own authorship:

1. **`document_get.data.content`** — the FULL parsed document
   (`operations.py:429-442`). This is the large crossing: descriptor documents are
   plugin-authored in their entirety (display fields, metadata, notes); binding, policy
   and commissioning documents are operator-authored. Served flat, unmarked.
2. **`document_get.data.document.{id, version}`** — identity strings taken from the
   document itself (plugin- or operator-chosen).
3. **`device_get`/`device_list.data.descriptor.{id, version}`** — plugin-chosen strings,
   but already inside a named `descriptor` ref triple carrying `sha256`
   (`operations.py:1605-1644`) — the corpus's ref-triple structure already says
   "descriptor-derived" by construction.
4. **`run_check.data.findings[].reason`** — gateway-template messages that QUOTE
   document-derived values (`operations.py` run_check body: `f"binding names bench
   {named!r}, not {bench_id!r}"`). The `field` key of each finding already names the
   document path the value came from — the pointer exists; the message is the gateway's
   own words.

Everything else is gateway-authored (closed enums, minted ids, watermarks, limits).

The content store's document row is
`(sha256, raw_bytes, content_json, schema_id, stored_at)`
(`content/store.py:82-85`) — there is no entry-provenance column. But two derivable
provenance signals exist without any store migration: the row's `schema_id`
(derived from each document's own `$schema`/`schema_id` at admission,
`bootstrap.py:259`), and the admitted device rows' descriptor refs
(`device.descriptor.sha256`, the CON-10 projection). Row 5 is solvable as a pure
derivation; §3.4 designs it.

### The rider — the positional points form: measured, and NOT interface bytes

- The interface corpus contains **zero** positional two-element arrays:
  `"maxItems": 2` and `"minItems": 2` count 0 across all four machine artifacts
  (`mcp-tools.json`, `openapi.json`, `interface.schema.json`, `operation-catalog.json`).
- The positional form lives in the **SDK repo**, code-carried:
  `_CAPTURE_SERIES_RESULT` defines `"points": {items: {type: array, minItems: 2,
  maxItems: 2}, description: "[x, y] pairs in acquisition order"}` in
  `benchweave-sdk src/benchweave_sdk_server/catalogue.py` (~:530-545), emitted by
  `_op_capture_series` (`seam.py:2143`, the `[[x, y] for x, y in served]` line), pinned by
  test in `tests/server/test_capture_lifecycle.py` (three sites: `point[1]` at :313,
  `raw["points"][0] == [0.0, -9.5]` at :320, the raw call at :345) and the schema rows in
  `test_capture_catalogue.py` / `test_catalogue.py`.
- The catalogue module states its own authority: the closed SW-10 set "defined here as
  data" with nothing "inferred from a Python signature" — a **code-carried contract**,
  pinned against the vendored interface catalog only for the error vocabulary
  (catalogue.py module docstring). The standalone catalogue is NOT a vendored standard;
  there is no standalone-interface standard in `standards/` (six standards: execution,
  interface, otdp, plugin-ui, plugin-ui-preview, registry).
- The gateway consumes none of it: the gateway never serves points, and the standalone
  UI's plots render from a separate data path (the observation ring via
  `plots.plot_host_html`), not from the capture_series wire form. The internal tuple
  consumers (`plots.decimate_minmax`, `analysis.trapezoid_integral`,
  `report.py:337`) consume the pre-wire `list[tuple[float, float]]` and are untouched by
  a wire-shape change.

**Consequence:** the rider cannot class the interface standard. See §2.

---

## 2. The class correction — the record's central finding

The owner's row-call comment classes the rider "MINOR, interface 0.2.0". The comment's
premise — that the capture_series point shape is interface-schema bytes — is measured
wrong: the point shape is code-carried in the SDK repo's standalone catalogue, and the
interface corpus carries zero positional arrays. Under GOVERNANCE's own table (change
class = highest class the batch contains, per standard):

- **Interface corpus rows (1b descriptions, 2 annotations, 3 the limit echo, 5 the origin
  marker — all additive or clarifying):** additive machine errata = **PATCH**
  ("new optional field, nothing removed or retyped" — the table's own precedent row is
  the interface `approver_token` pattern). → **interface 0.1.0 → 0.1.1 PATCH.**
- **The rider:** a refusal of a previously-served wire shape on the standalone host —
  honestly MINOR-class, but of the **standalone host's code-carried catalogue**, whose
  vehicle is the **SDK package semver (0.x line: breaking rides MINOR)**. It moves zero
  interface bytes, so it contributes no class to any standard. → **SDK MINOR release;
  no standards bump for the rider.**
- The marker-shape fork inside row 5 (optional vs conditionally-REQUIRED) decides whether
  the interface class is 0.1.1 or 0.2.0 — §3.4 recommends optional; if the owner rules the
  marker required-when-content-present, the interface bump becomes 0.2.0 and the owner's
  stated class becomes true, just by a different mechanism than the rider.

**Why 0.2.0-for-the-rider cannot stand as stated:** GOVERNANCE's class table derives the
class from the highest class the standard's batch contains. A batch in which no
interface-corpus row refuses anything previously-valid is PATCH, whatever the changelog
hopes. Classing it 0.2.0 would repeat the exact error the GOVERNANCE trap memory
documents (classing from the briefing's shorthand instead of the bytes) — and it would
falsely signal breaking to every consumer of the dependency-policy range. The
dependency-policy slide is `>=0.1.0,<0.2.0` → `>=0.1.1,<0.2.0`; a 0.2.0 slide would also
re-open the retired-1.1.x interaction for no machine reason.

**What survives from the row call untouched:** the rider is TAKEN; in-tree consumers
change inside the arc; the marker is schema-visible; row 3 is the schema-field route
(optional, always populated, parity-pinned); rows 1b/2 are errata. Only the class
derivation and its version number move, and §10 asks the owner to confirm.

---

## 3. Per-row mechanisms (file-by-file)

### 3.1 Row 1b — descriptions (corpus bytes; revision slice)

**Where the bytes live:** `standards/interface/0.1.0/mcp-tools.json`, each tool's
`description` — edited only in the new version's copy (copy-never-move, §4). CON-3's pin
serves them verbatim; the parity suite's wire pin re-proves serving after the bump with
zero `mcp.py` changes.

**The template family (how the 17 stay consistent):** every description is rewritten from
one three-part template, in one editorial pass, in one commit:

1. **Role line** (per tool): the existing one-liner's verb + object, tightened.
2. **One shared posture sentence**, identical bytes on all 17:
   `"Apply interface 0.1.1 authorization and lifecycle rules."` — version-stamped so a
   served description names the interface it enforces (derived surfaces like
   `gateway_info` already carry the derived version; the description stamp is corpus-side
   and moves at the next bump by construction).
3. **Lifecycle sentences, by class:**
   - The five mutating/async tools (run_start, run_cancel, lease_create, lease_renew,
     lease_release) gain: acceptance vs completion ("Acceptance is not completion; poll
     run_get (or resolve run_find) to a terminal state before asserting the result."),
     plus the outcome sentence: "A terminal run may carry outcome_unknown: the final
     record is missing; wait for terminal evidence, never assume passed." (run_start and
     run_cancel get the full pair; the lease trio gets the accept/poll pair — leases have
     no outcome).
   - The read family gains the observation sentence: "Observation only: this read never
     triggers an instrument action or takes ownership." (contract :40).
   - `gateway_info` additionally names the advertised limits and interface version
     (it already serves both).

Consistency is enforced by (a) the single-pass template, (b) the interface checker gaining
one mechanical row (§4), (c) the parity suite's existing description pin. The text is
written in the register the corpus already uses (second person, imperative, no marketing).

### 3.2 Row 2 — the two annotation rows (corpus bytes; revision slice)

In the 0.1.1 copy of `mcp-tools.json`:

```json
"stg_v1_run_find":   {"annotations": {"readOnlyHint": true, "idempotentHint": true}}
"stg_v1_run_check":  {"annotations": {"readOnlyHint": true, "idempotentHint": true}}
```

Why each hint: readOnlyHint true — neither tool writes (run_check's body and docstring
are the evidence); idempotentHint true — repeat calls have no additional effect (same
class as every other read in the corpus); destructiveHint/openWorldHint stay ABSENT,
matching the read family's shape. The mcp.py docstring that calls run_check read-only
(`mcp.py` run_check body) becomes TRUE on the wire instead of contradicting it.

**Machine check:** `scripts/architecture/check_interface.py` gains one check row —
`"no read-only tool declares destructiveHint true"`: for every tool with
`annotations.readOnlyHint == true`, `annotations.destructiveHint` is not `true`. One
table-driven loop over the 17; the validation report regenerates with the corpus anyway.
This keeps the contradiction class out of future corpus revisions by mechanism, not
memory.

### 3.3 Row 3 — the effective-limit echo (schema field route; the owner's call, kept)

**Field name:** `limit`. **Placement:** inside each paged output's `data` object, as a
sibling of `items`/`next_cursor` (bench_list, device_list) and of
`events`/`cursor`/watermarks (events_get). **Schema:** property added, NOT added to
`required` — the GOVERNANCE PATCH pattern verbatim (the `approver_token` row). **Always
populated:** the seam emits it on every successful paged call.

**Mechanism (one seam, both transports — A13):** the echo is emitted where the effective
value is already known and singular. Both adapters clamp BEFORE the seam, so the seam's
`limit` parameter IS the effective limit. `Operations.bench_list` /
`Operations.device_list` change their return from `(items, next_cursor)` to
`({"items": [...], "next_cursor": ..., "limit": limit})`, and
`Operations.events_get` adds `"limit": limit` to its existing dict return. The two
adapters' `_paged`/handlers stop constructing the page object and pass the seam's dict
through. One emission site per operation, shared by both transports — the parity suite's
full-envelope equality then pins cross-transport identity automatically.

Callers to sweep in-arc: the two adapters (`mcp.py` `_paged` + the three tool bodies;
`rest.py` bench_list/device_list/events_get handlers), the CLI client's paged methods
(`cli/client.py` GatewayClient.bench_list and siblings — unwrap the dict instead of the
tuple), and any internal callers (grep `operations.bench_list(` — the parity fixture's
`Operations` use goes through transports, not directly).

**Type:** integer, minimum 1 (a clamped value; the corpus input schema already bounds
`limit` at 1000 and the adapters clamp to `max_page_size`).

**The quiet default itself — the fork, resolved as a recommendation:** the MCP Python
signature's `limit=1` default stays. Changing the default to `max_page_size` would change
how much an unargued call serves (a real behavior change outside this issue's rows), and
the echo makes the misread impossible instead: an agent that reads a one-item page SEES
`"limit": 1` beside it. If the owner wants a friendlier default, that is a separate
row with its own parity evidence — recommended DEFER.

### 3.4 Row 5 — the provenance marker (THE design fork, argued)

**The requirement (owner's call):** the marker must be schema-visible — a consumer of the
schema can see it; a marker only the code knows repeats row 3's disease. It must be
machine-checkable, testable, and name what refuses.

**Shape A (per-value inline annotation):** annotate each plugin-authored string
in place. Rejected: strings inside `content` are arbitrary plugin JSON — you cannot
annotate "in place" without retyping `content` from `object` to a wrapper (breaking) or
duplicating every string path (unbounded); and per-value annotations of a
pass-through object are a new sub-language the corpus would have to define. Cost without
closure.

**Shape B (envelope-level quarantine):** plugin-authored strings MOVE into a quarantined
sub-object (envelope-level provenance class). Rejected for this increment: retyping
served results (breaking = MINOR at minimum), all for a distinction the corpus already
expresses better — the ref triple. Quarantine is the right shape for EXECUTABLE content
reaching an interpreter; these are descriptive strings read by an agent. The HTML side's
autoescape analogy is instructive: autoescape does not relocate plugin text, it renders
it inert in the consumer's frame. The MCP consumer's frame is the schema-visible
provenance twin, not relocation.

**Shape C (value-prefix convention):** prefix plugin strings in-band. Rejected: a value
convention is exactly the code-only marker the owner's constraint forbids — invisible to
the schema, unverifiable without the convention document, and it corrupts the bytes
(digest-verifiable documents would serve altered content, violating
"reserialising content is not a valid substitute" contract clause,
interface-contract.md:38).

**Shape A′ (RECOMMENDED): the document-scope provenance twin, additive-optional.**

`document_get`'s `data` object gains one optional sibling:

```json
"origin": {
  "kind": "plugin" | "operator" | "gateway",
  "basis": "descriptor-schema-id" | "admitted-device-ref"
         | "execution-doc-schema-id" | "gateway-family-schema-id"
         | "unclassified-fallback",
  "document": {"id": "...", "version": "...", "sha256": "..."}   // when kind=plugin
}
```

- **`kind`** — who authored the document's content. Three values, closed enum. The
  gateway-authored families (terminal records, approval records) are their own kind: an
  agent must be able to distinguish the gateway's own words from operator documents too.
- **`basis`** — the derivation rule that produced the classification, named on the wire.
  This is the honesty field: it tells the consumer HOW the gateway knows, so the
  consumer can weigh it (G4 claim discipline — the guard states what it does not catch).
- **`document`** — for plugin content, the descriptor's ref triple, joining the marker
  to the corpus's own provenance currency (the digest-pinned document family). The
  device rows already carry exactly this ref (`operations.py:1636-1641`); the marker
  reuses the structure, not a new convention.

**Derivation (pure function of stored state — no store migration):**

1. `kind = "gateway"` iff the row's `schema_id` matches a gateway-authored family
   (terminal-record / approval schema identities — the same schema-suffix derivation
   `documents_by_schema_suffix` already performs, `content/store.py:103`).
2. `kind = "plugin"` iff the row's `sha256` equals an admitted device row's
   `descriptor.sha256` (the CON-10 projection join) OR its `schema_id` resolves to the
   vendored OTDP descriptor schema identity (manifest-derived URN, never a literal).
3. `kind = "operator"` otherwise (the lattice families).

The ordered rules are total over the served set, so every document serves with a
`kind`. `unclassified-fallback` exists as the honest residual `basis` value for a future
family that lands before its rule does: it still carries its `kind` (the rules are
total), so nothing serves unkinded, and the refusal clause below covers marker-absence
and marker-shape — an unclassified basis is served loudly, never silently.

**What refuses (the named refusals):**

- **Marker missing** — the gateway's own emission check: `document_get` serves
  `origin` on every success; the seam constructs it in the same return statement that
  builds `data`. If the derivation helper cannot produce a row (its inputs are always
  present — schema_id is NOT NULL), that is an internal_error, same class as any seam
  crash. There is no silent marker-less success path: the field is built unconditionally
  by the one emission site.
- **Marker wrong (shape)** — the revised corpus `document_get_output` def validates the
  origin object (closed enum, required keys per kind — conditional requires inside the
  def). A malformed marker is a schema-invalid response, which the row-4 mirror
  (extended, §3.6) catches in CI, and which the checker's vectors exercise (the
  document_get specimen gains an origin block, §4).
- **Client-side refusal** is NOT the design's refusal surface: the schema field is
  optional-additive, so an old client sees a new field and ignores it. The refusal the
  design commits to is CI-side (row 4's mirror validates served envelopes) plus the
  emission-site construction. This is the honest statement of what optional-additive
  buys: visibility, not enforcement. Enforcement-when-present (a required-conditional
  origin) is the variant that would class the bump MINOR — flagged in §2 and §10.

**Scope discipline:** the marker lands on `document_get` ONLY in this increment. The
other crossings (document identity strings, the descriptor ref triple, run_check
findings) are either already ref-structured or already path-named; extending the marker
there is the deferred row (§6, D2) with its trigger.

**What the marker does to existing served results:** additive-optional — existing
consumers see one new field on document_get responses; nothing is removed or retyped;
the parity suite's document_get case compares full envelopes on both transports and both
grow the field together (one seam emission).

**Parity impact:** the suite's document_get EXACT_CASE row passes unchanged structurally
— both transports now carry origin; the new arms validate origin's presence + schema
validity per kind, and the RED proof (§8) shows the marker's absence on today's wire.

**Why A′ fits the corpus's own precedents:** it extends (a) the ref-triple document
family (provenance as content-addressed identity), (b) the D4 closed-envelope discipline
(closed kind enum, conditional requires, additionalProperties discipline), and (c) the
derived-not-stated posture (the basis field names a manifest-derived rule, never a
hardcoded schema URN). No new architecture: a pure seam derivation, one additive
schema field, one emission site.

### 3.5 The rider — named x/y on capture_series points (SDK slice)

**The new point shape:** `"points": [{"x": <number>, "y": <number>}, ...]`.

- Schema (`catalogue.py::_CAPTURE_SERIES_RESULT`): items becomes
  `{"type": "object", "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
  "required": ["x", "y"], "additionalProperties": false}`.
- Emission (`seam.py::_op_capture_series`): the wire conversion becomes
  `[{"x": x, "y": y} for x, y in served]`. Internal tuples unchanged (plots/analysis/
  report untouched — measured).
- **The positional form's refusal:** the revised items schema refuses positional pairs
  (a 2-element array fails `type: object`). The decimation and raw-serving paths, the
  `max_points` bounds, and the `payload_too_large` ceiling all unchanged.
- **In-arc consumer sweep set (enumerated, complete):**
  1. `src/benchweave_sdk_server/catalogue.py` — the result schema row.
  2. `src/benchweave_sdk_server/seam.py` — the emission line.
  3. `tests/server/test_capture_lifecycle.py` — the three wire-form sites (:313, :320,
     :345).
  4. `tests/server/test_capture_catalogue.py` — the result-schema validation rows.
  5. `tests/server/test_catalogue.py` — the capture_series row pin.
  6. `tests/server/test_seam.py` — its capture_series site reads status/decimation, not
     the point shape; verify-in-arc, change only if the assert touches points.
  7. `tests/server/test_mcp.py` — the capture tool tests: verify-in-arc.
  8. `src/benchweave_sdk_server/{plots,analysis,report}.py` — VERIFIED OUT (internal
     tuples; the web plot path uses the observation ring, not the series wire form).
  9. The gateway repo — VERIFIED OUT (zero positional arrays corpus- or code-side).
- **Supersedes recording:** the standalone catalogue being code-carried, supersedes is
  recorded the way code-carried contracts do it: the SDK release notes carry a BREAKING
  footer naming the point-shape change and the old→new mapping (the #444/preview-exit
  release-notes BREAKING footer is the in-tree precedent), and the catalogue module
  docstring names the superseded form. If the owner instead wants the points shape to
  become normative corpus bytes (a standalone-interface standard), that is a NEW
  standard (admission class), out of scope — named in §10.
- **Class:** SDK MINOR (breaking wire-shape on a 0.x package). Rides SDK 0.12.0 with the
  interface-0.1.1 sync (§5).

### 3.6 Row 1a — server instructions (code-side; precedes the revision)

`build_mcp` (`src/benchweave/interfaces/mcp.py`) adds the `instructions` parameter to the
FastMCP constructor — a constant string inside build_mcp, exactly the SDK server's inline
posture. Draft text (final wording at build time, STE-adjacent, short):

> BenchWeave test-bench gateway. Run lifecycle: run_start accepts a run; poll run_get
> (or resolve run_find) to a terminal state before asserting the result. A terminal run
> may carry outcome_unknown — the final record is missing; treat it as unresolved, never
> as passed. Leases, generation fences and the protective transition are enforced by the
> gateway regardless of client behavior. gateway_info serves the advertised limits and
> the interface version this server enforces.

Content decisions: states the accept/poll-to-terminal model (row 1's gap), the
outcome_unknown semantics (A06 on the surface), names that protection is gateway-side
(A04 — a client cannot veto the protective transition, and the instructions SAY so).
No absent_guarantees port: the gateway PROVIDES the guarantees the standalone host
absent-guardians; its honesty block is `gateway_info`'s existing limits/version body.
That asymmetry is deliberate and stated here so the build lane does not "fix" it.

Test: the MCP initialize response carries the instructions; RED proof (§8).

### 3.7 Row 4 — run/lease envelope validation mirror (code-side; precedes the revision)

In `tests/integration/test_interface_parity.py`, generalize `_validate_event_def` into
`_validate_output_def(op_name, envelope)` (same Draft202012Validator over
`interface.schema.json` `$defs[<op>_output]`), and:

1. Add `_validate_corpus_output(op_name, envelope)` arms to every run/lease envelope
   the suite already captures: run_start (replay), run_get, run_find, run_cancel,
   run_check, lease_create, lease_renew, lease_release (+replay). Anchor the schema load
   to `active_contract_family("interface")` (the vendoring helper), NOT the hardcoded
   `standards/interface/0.1.0` CONTRACTS constant — the validator then survives the bump
   without edits and cannot lag the active corpus (the derived-not-stated discipline;
   the hardcoded constant remains for the other constants in the file and moves in the
   revision sweep).
2. The RED proof is the honest hole-then-catch: plant a shape fault in a served run
   envelope (monkeypatch the seam projection to drop `revision`) — under the CURRENT
   suite it passes both transports (the hole, measured as the issue says); with the
   mirror, the planted fault is caught by name.

---

## 4. Revision mechanics (slice 2 — the corpus train)

**Copy-never-move:** `standards/interface/0.1.1/` is created by copying
`standards/interface/0.1.0/` wholesale; every edit lands only in the copy; the 0.1.0 dir
and its corpus-manifest rows stay digest-frozen; the 0.1.1 rows record
`source: interface/0.1.0/<path>` (the existing 6 interface rows'
`source: docs/interface-v1.1.1/...` shows the chain shape).

**The corpus edit set (all inside the 0.1.1 copy):**

1. `mcp-tools.json` — 17 descriptions (template family §3.1); 2 annotation rows (§3.2);
   the paged outputSchemas gain `limit` (§3.3); the document_get outputSchema gains
   `origin` (§3.4).
2. `interface.schema.json` — the same $defs edits (bench_list_output, device_list_output,
   events_get_output, document_get_output) + the new `origin` def.
3. `openapi.json` — the same response-schema edits (REST side).
4. `operation-catalog.json` — the same per-op output_schema rows.
5. `interface-contract.md` — prose errata: the page-limit echo, the origin field, the
   corrected annotation semantics; history row "Supersedes interface 0.1.0" + the errata
   list.
6. `examples/operation-vectors.json` + `examples/mcp-start-exchange.json` — regenerate
   via the checker (`check_interface.py` rewrites both; byte-pinned by the report check).
7. `validation-report.md` — regenerate: `uv run python
   scripts/architecture/check_interface.py --write-report` (obligation 13; the checker
   must be green before the writer runs — the writer refuses on a failing run).
8. `README.md` (corpus dir) — version-reference row if it names the active version.
9. **New checker row** (§3.2): the read-only/destructive annotation-consistency loop, so
   the report pins annotation sanity going forward.

**The consistency mechanism is the checker itself:** its per-op MCP/REST input+output
parity checks and its stored-fixture byte-comparisons refuse a four-artifact edit that
missed a file. This is the corpus's own machine-enforced coherence — the reason the
revision is low-risk despite touching four JSON artifacts.

**The in-arc sweep (the "every in-tree artifact declaring the old version moves in-arc"
rule):**

- `standards/standards-manifest.json` — interface active → 0.1.1; dependency_policy
  range slides `>=0.1.0,<0.2.0` → `>=0.1.1,<0.2.0`.
- `standards/corpus-manifest.json` — six new rows citing `interface/0.1.0/...` as
  source, digests via the repin loop (never hand-spliced).
- `scripts/standards/docs-literal-baseline.json` + the counter — the docs ratchet
  refreshes with an explicit reviewable diff (the #444 train's identical motion;
  `test_zero_literal_gate.py`'s TestDocsRatchet is the mechanical half).
- **Test path literals (15 files measured):** every test LOADING corpus bytes from the
  `interface/0.1.0` path re-points to the active dir in-arc
  (test_interface_parity, test_mcp_baseline, test_mcp_fidelity_spike, test_mcp_tools,
  test_event_recovery, test_takeover, test_registry_changes, test_seam_{admin,control,
  events,observe,validation}, test_error_model, test_vendoring, test_capture_services,
  test_architecture, test_zero_literal_gate — the loader set; comment-only mentions move
  opportunistically, not by obligation). NOTE: row 4's new validator (§3.7) is written
  manifest-derived from the start, so it does NOT join this list.
- Docs naming the active contract: `docs/internal/drift-and-obligations.md` rows 1-2,
  `docs/internal/invariants.md` CON-5 path + the new amendment (§7), `docs/README.md`
  report-count rows, `docs/device-developer-guide.md` (where it names the active
  interface), `docs/internal/ui-contract.md` (where it names the active contract;
  historical mentions stay historical).
- Derived surfaces needing NO edit (verified): `mcp.py` `_VENDORED_PATH`,
  `validation.py` `VENDORED_CORPUS_ROOT`/`VENDORED_INTERFACE_VERSION` +
  `gateway_info`'s version field, `vendoring.active_contract_family` — all
  manifest-derived; the checker's `INTERFACE_VERSION`/`CONTRACT_DIR` likewise.

**Repin loop:** edit → `uv run python -m benchweave.standards repin` → export;
`make check-sdk-standards` goes RED until the SDK sync leg lands (CON-4) — the train
closes only when it is green again (§5).

**Bump-window:** the interface standard's previous bump was its admission — no window
runs; the 24-hour window is per standard and untouched by the concurrent otdp/plugin-ui
trains.

---

## 5. Train-sequencing recommendation (the collision analysis)

Three standards trains are live (local branches, none merged): OTDP 0.2.3
(`build/issue443-4731` + `fold/issue445-read-side-effect`, #447/#448 queued), plugin-ui
0.3.1 (`feat/issue444-commissioned-preset-firmware`, mid-refute-slate, SDK 0.11.0
release pending), and this interface train. Collision surfaces: the shared
`standards-manifest.json` (each train edits the active-version + range rows of ITS
standard — textual conflicts, rebase cost, no rule violation; the 24h window is per
standard so no window violation is even possible), the shared SDK release cadence (the
rider and the interface sync both need an SDK release), and the gateway pointer PR
(`packages/sdk` gitlink + `.gitmodules` pin move in one commit, per the #408 order).

**Recommended order:**

1. **OTDP 0.2.3 lands first** (owner-directed: "the trains hold first").
2. **plugin-ui 0.3.1 lands** (refute slate concludes) and **SDK 0.11.0 cuts** — its
   release, its train, unbatched.
3. **This train, as three PRs:**
   - **PR-1 (code-side, can open immediately — no standards motion):** rows 1a + 4
     (§3.6, §3.7). Tier 2. Lands on main before the corpus train opens; zero interaction
     with the other trains.
   - **PR-2 (the corpus revision):** §4. Tier 3 + standards-governor. Opens after OTDP
     and plugin-ui have merged, so its standards-manifest edits rebaze on the settled
     file rather than colliding mid-flight. If a train slips, PR-2 WAITS (the owner's
     row-call already said the trains hold first); PR-1 does not wait.
   - **PR-3 (the SDK leg, in the SDK repo, after SDK 0.11.0 cuts):** the interface-0.1.1
     sync (`make sync-sdk-standards` → vendored tree + lock + compat mirror) AND the
     rider (§3.5) ride ONE SDK release — **0.12.0** — per one-release-per-train-window.
     Then the gateway pointer PR (gitlink + pin, one commit) closes the train and turns
     `make check-sdk-standards` green again.

**Why the SDK leg queues behind 0.11.0 rather than batching into it:** 0.11.0 is the
#444 train's release, mid-refute; folding this train's bytes into it would put unrelated
motion into a release whose notes and review scope are already owned by another train,
and any #444 refute fold would re-open this train's bytes. Queue behind; batch the two
motions that ARE ours (rider + interface sync) into one release. The rider is not blocked
on PR-2's merge (different repo), but its release must follow 0.11.0; PR-3 branches off
SDK main after the 0.11.0 tag.

**Failure modes if the order is violated:** a same-window standards-manifest collision
(rebase cost, double-review); an SDK release carrying another train's unpublished bytes
(release-notes laundering); a pointer PR landing before the SDK tag exists (the sdk-drift
lane reds, correctly).

---

## 6. Slices, order, and explicit deferrals

**Slice 1 — rows 1a + 4 (PR-1, gateway repo, Tier 2).** One commit each or one commit;
RED evidence per row. No corpus motion.

**Slice 2 — the corpus revision (PR-2, gateway repo, Tier 3 + governor).** One commit
carrying the revision + sweep + repin (a batch commit with per-row RED evidence in the
message, per the fast-lane doctrine). Gates: full battery + both standards tripwires.

**Slice 3 — the SDK leg (PR-3, SDK repo, then the gateway pointer PR, Tier 3 by the
pointer rule).** The rider + the interface-0.1.1 sync; SDK 0.12.0; pointer PR.

**Deferrals (each with home + trigger):**

- **D1 — the test-path-literal derivation refactor.** Home: the 15-file loader sweep
  becomes a shared helper (`benchweave.vendoring.active_contract_family` in tests) so
  future bumps move zero test literals. Trigger: the NEXT interface bump (this one
  carries the literal sweep; folding the refactor in would double the diff and blur the
  errata review). Why deferred: minimal increment; the refactor is pure de-drift with no
  row-450 behavior.
- **D2 — marker scope widening** (origin on device_list/device_get descriptor refs,
  run_check findings, and any future document families). Home: a follow-up row on #450's
  residue. Trigger: the first served field proven to mislead an agent despite the
  document_get marker (or the first new plugin-authored document family).
- **D3 — the paged-default review** (should MCP's limit=1 default change). Trigger: the
  owner's fork ruling (§10 F3); home: a row on the tracker.
- **D4 — annotation-policy widening** (idempotent/openWorld policy beyond the two
  corrected rows, e.g. lease tools' idempotentHint semantics under §9 replay). Trigger:
  a future corpus revision; home: the checker row's extension.
- **D5 — the paged-output corpus validation.** Row 4's mirror covers run/lease envelopes
  (the issue's scope). Extending `*_output` validation to the paged pages is natural and
  cheap — DEFERRED only to keep slice-1's diff honest to the issue's named surface; it
  lands with D1's helper or the next parity-suite touch. Trigger: next parity-suite
  touch, no later than the next interface bump.

---

## 7. Invariant impacts (A01-A14, CTL/STO/CON/REG)

- **CON-3 (vendored-exact MCP tools):** unchanged in rule; the corpus moves under it.
  The amendment records the errata class + the new checker row.
- **CON-4 (vendored trees, check-sdk-standards):** the train's SDK leg exists to keep it
  true; the red-until-pointer window is bounded by the sequencing in §5.
- **CON-5 / A13 (one core contract behind REST and MCP):** STRENGTHENED — the limit echo
  and the origin marker are emitted at one seam site; row 4's mirror re-anchors parity
  to the corpus, not the sibling transport (the WP07 lesson, applied). Amendment text:
  "Run and lease output envelopes validate against the corpus *_output defs; served
  pages name their effective limit; document_get names content origin."
- **CON-10:** the device-conformance wire field the VR-16 comment promised "lands with
  the interface lane" — THIS is that lane. Owner fork (§10 F4): fold the additive
  optional conformance field into this revision batch (bump-minimization, one bump per
  standard per train) or defer to the next interface window with an explicit
  re-promise. The design RECOMMENDS folding it (it is additive-optional, the same class,
  and the promise is already in the invariants doc) — but it is the owner's call since
  it widens the batch beyond #450's rows.
- **CON-11 (validation-report family):** the report regenerates in the same change;
  docs/README.md counts move.
- **A06 (evidence-aware semantics):** row 1a/1b state outcome_unknown ON the surface —
  the ambiguity is now advertised where agents read.
- **A04:** row 1a's instructions name the gateway-side protective transition.
- **A02:** untouched (no numeric envelope moves; the limit echo states an existing clamp,
  it does not retune one).
- **CTL/STO/REG:** untouched — no control-path, persisted-format, or registry motion.
  The content store row shape is NOT extended (the origin derivation is pure over
  existing columns).

---

## 8. Measurable proof — pre-committed acceptance rules (written before any number)

All checks are deterministic CI mechanics (this is conformance engineering, not
statistics): each row's rule is a RED→GREEN pair plus the full battery; no sampling
applies and none is claimed. Each rule states what ships, what kills, and what reads as
underpowered.

| Row | RED (mechanism disabled = the effect disappears) | GREEN (ships when) | Kill / underpowered read |
|---|---|---|---|
| 1a | Comment out the `instructions=` argument; the initialize-response assertion fails | Served instructions carry the accept/poll + outcome_unknown sentences; `pytest tests/integration/test_mcp_tools.py -k instructions` green | If fastmcp refuses the param (it does not — SDK-server precedent), the design is wrong: STOP, re-design the disclosure surface |
| 1b | Revert the corpus copy's descriptions to one-liners; the served-description arms fail | tools/list serves the 17 template-family descriptions; parity description pin green | Underpowered = the wire pin passes with stale bytes: means the pin reads the wrong corpus dir — fix the sweep, not the test |
| 2 | Same revert; the served-annotation arms fail (today's run_find serves ro+destr:true) | run_find + run_check serve `{ro:true, idem:true}`; the checker's new annotation row green | If the checker row cannot distinguish the corrected rows from the defect pattern, the check is rewritten, not waived |
| 3 | Revert the seam echo (tuple returns); `bench_list` responses lack `limit` → arms fail | bench_list, device_list, events_get responses carry integer `limit` equal to the clamped requested value, on BOTH transports, envelope-equal | If the echo differs cross-transport, the emission leaked to an adapter — the design's one-seam rule is violated; fix the site, not the test |
| 4 | Plant a dropped `revision` in a served run envelope; CURRENT suite passes it (the measured hole); the mirror catches it | All captured run/lease envelopes validate against `*_output` defs; the planted-fault arm named | A mirror that passes the planted fault = the mirror reads the wrong def; kill and re-anchor |
| 5 | Revert the origin emission; descriptor-family document_get returns no origin → arm fails | document_get carries schema-valid `origin` on every success; kind derivation pinned per family (descriptor → plugin; lattice → operator; terminal-record → gateway); malformed-origin emission is schema-refused | The derivation rule misclassifying a REAL family in the fixture lattice = kill; the census arms must cover all three kinds before GREEN |
| Rider | Serve positional points from a scratch copy; the revised items schema refuses them; emission serves named keys | Positional refuses / named admits / the enumerated sweep set all green in-arc (5 test files + 2 src files) | Any in-tree consumer of the positional wire form found post-sweep = the sweep set was wrong; extend and re-prove, disclosure in the PR |
| Train | `git diff origin/main...HEAD -- standards/` empty on PR-1/PR-3; non-empty ONLY in the revision PR | Full battery + both tripwires green; check-sdk-standards green at train close | Tripwire red on a non-corpus PR = the corpus motion leaked; abort and split |

**Per-row effect sizes:** binary conformance (field present/refused) — a percentage is
not meaningful and is not claimed. Denominators: 17 descriptions, 2 annotation rows,
3 paged ops, 8 run/lease envelopes, 1 output def, 8 in-arc sweep files (rider).

---

## 9. Review tier + Step-1 keyword scans (#254)

Per-slice, over each slice's EXPECTED diff (docs and code alike); the build lane
re-scans the real diff and corrects per the rubric if counts move.

- **Slice 1** (mcp.py + test_interface_parity.py): expected Tier 2 — no Tier-3 path rule
  fires (`src/benchweave/interfaces/mcp.py` is production code under `src/`, tests under
  `tests/`; no contracts/, no standards/, no schema files, no dependency motion). Keyword
  scan over expected diff text: `threading` 0 · `asyncio` 0 new (the import exists; the
  diff touches neither) · `subprocess` 0 · `sha256` 0 · `hashlib` 0 · `migrate` 0 ·
  `recovery` 0 · `protection` 0 (the instructions text says "protective transition" —
  WAIT: "protective" does not contain the keyword `protection`; counted 0, disclosed).
  If the wording changes to contain `protection`, the slice re-classes Tier 3 by the
  keyword rule — the rubric's text-carries-depth rule, intended.
- **Slice 2** (corpus + sweep): **Tier 3**, triggered by BOTH the path rule (touches
  `standards/` including `interface.schema.json` — a JSON Schema file) and the keyword
  rule (the corpus schemas' diff text carries `sha256` — property names and patterns —
  expected count high; the schema defs' `additionalProperties` diffs carry none of the
  other seven). Two-lane refute per the standing order + standards-governor mandatory
  (#69) + the release-review walk if the SDK lock's version strings move.
- **Slice 3** (SDK repo): SDK-side gates; the gateway-side pointer PR is **Tier 3** by
  the pointer rule (advances the submodule pointer). Keyword scan over the pointer diff:
  all eight keywords 0 (a gitlink + pin edit carries none). The SDK-side rider diff:
  expected Tier 2-equivalent under the SDK repo's own gates; its text carries none of
  the eight (`sha256` appears only in unrelated existing lines outside the diff).
- **Maximum across slices: Tier 3.**

---

## 10. Forks needing the owner's word

- **F1 — the class correction.** This record recommends **interface 0.1.1 PATCH** (rows
  additive) + the rider classed at the SDK (MINOR release), correcting the row call's
  "interface 0.2.0 MINOR" on measured evidence: zero positional arrays in the interface
  corpus; the points schema is code-carried in the SDK repo. If the owner holds 0.2.0,
  the mechanism that makes it honest is the marker-required variant (F2), not the rider.
- **F2 — marker optional vs conditionally-required.** A′-optional (recommended): nothing
  refuses old-shaped responses; the gateway always populates; CI enforces. A′-required:
  a response with content but no origin becomes non-conforming (tightening = MINOR =
  interface 0.2.0, matching the row call's class); costs every client a required-field
  migration for a marker. The design ships optional unless overruled.
- **F3 — the MCP paging default.** Keep `limit=1` + the honest echo (recommended) vs a
  friendlier default (a behavior change wanting its own parity evidence).
- **F4 — fold CON-10's promised device-conformance wire field into this batch?** The
  invariants doc twice promises it to "the interface lane"; folding it is
  bump-minimization. Recommended: fold. It widens the batch beyond #450's rows, so it
  is the owner's call, and it is additive-optional (class-neutral).
- **F5 — supersedes recording for the rider.** Release-notes BREAKING footer + catalogue
  docstring (recommended, the code-carried way) vs promoting the standalone catalogue
  into a normative corpus standard (new-standard admission, much larger arc).

---

## 11. Top risks, each with its falsifier

1. **The class call is wrong** (0.1.1 when it should be 0.2.0). Falsifier: one measured
   counterexample — a previously-valid interface-corpus response shape that the revision
   refuses. Search executed: the only refusal in the batch is the rider's, and it is not
   an interface shape. If the marker goes required (F2), the record's own text flags the
   re-class.
2. **The origin derivation misclassifies a real family.** Falsifier: the fixture
   lattice's families (descriptor/lattice/terminal-record/approval) are all classified
   by census arms before GREEN; a family the rules cannot classify serves
   `unclassified-fallback` basis and the PR cannot close until it is named. The honest
   residual: an operator-authored document crafted to carry a descriptor `$schema` URN
   over-marks as plugin — conservative direction for the agent (over-marking is safe),
   disclosed in the schema description.
3. **fastmcp serves instructions differently than the SDK server's usage suggests.**
   Falsifier: the row-1a RED test; the SDK server's live usage is the in-tree proof the
   same fastmcp serves it.
4. **The four-artifact corpus edit misses a file.** Falsifier: the interface checker's
   own parity checks + the byte-pinned fixtures + the report regen — the exact mechanism
   that exists for this. The #444 train ran the same loop with zero residual.
5. **Train collision.** Falsifier: PR-2's rebase onto a moved standards-manifest; the
   sequencing (§5) keeps PR-2 off the file until the other trains merge; PR-1 is
   collision-free by construction.
6. **The rider's sweep set is incomplete** (an in-tree consumer of the positional wire
   form outside the enumerated nine). Fulsifier: the sweep rule is mechanical (grep the
   wire-form literals in both repos); the pre-committed rider check re-runs it at
   commit time; a late find extends the set with disclosure, not silence.
7. **The zero-literal docs ratchet blocks the PR** (the corpus descriptions naming
   "0.1.1" in prose scans). Mitigation measured: the ratchet refreshes by explicit
   reviewable diff (the #444 motion); the risk is one commit-amend, not a design risk.

---

## 12. What this record does NOT decide

- Final description wording (build lane, from the §3.1 template; STE register for any
  operator-facing prose moved into published docs).
- The exact origin schema description text (corpus copy).
- Whether plugin-ui 0.3.1's refute slate concludes before or after this train's PR-2
  opens (§5's rule: it waits).
- The SDK release notes' final BREAKING text for the rider (F5's shape, build lane).
