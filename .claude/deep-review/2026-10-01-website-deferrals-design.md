# The website deferrals — #319 + #321 + #291 (+ the #320 ruling): design record

Status: DESIGN COMPLETE. Base: `origin/main` @ `bb995c4` (worktree `.wt/f319-design-906`,
detached at tip). Branch at build: `feat/website-deferrals`; this record is commit 1 of that
branch. One PR, main repo only — no SDK bytes, no submodule motion, no `standards/` bytes.
Triage: PUBLIC placement — checked against `.claude/deep-review/README.md`'s private list;
no person, client, bench, serial, or commercial identifier; every citation is a public path,
issue, PR, or commit.

Parent record: `.claude/deep-review/2026-10-01-issue317-website-status-design.md` (§9 filed
these deferrals; §12's refute corrections F1/F2 are load-bearing here and are adopted, not
re-litigated).

---

## 0. Summary and verdicts

| Payload | Verdict | Shape |
|---|---|---|
| #319 — device-developer-guide stale bridge/status claims | **BUILD** | A claim-reconciliation sweep of the guide: **4 stale sites corrected + 1 tense disclosure**, mirroring the website's refute-corrected remaining-scope sentence verbatim. Docs-only. |
| #321 — the verb-list drift pattern's cure | **BUILD** | Obligation **row 23** in `docs/internal/drift-and-obligations.md` + a matching `drift-guard.mjs` rule + one hook test. The "generated scope line everywhere" alternative is rejected on cost (§3.2). |
| #291 — docs-site CLI reference cannot see `benchweave.standards` | **BUILD** | The assembly **generates a staged user-guide page** from `python -m benchweave.standards --help` at build time (generated beats hand-written); a test pins the verb set bidirectionally. |
| #320 — plugin-ui 0.3.0 released README prose | **DON'T-BUILD this round** | Released standards bytes are digest-frozen (copy-never-move); the corrected prose rides the next plugin-ui bump's new version directory. Ruling recorded here + posted to the issue; no design, no diff. |

Re-verified at this base (not assumed from #317): `src/benchweave/host/otdp_bridge.py` is
**unchanged** between #317's base (`33b4c55`) and this base (`bb995c4`) — `git log 33b4c55..HEAD
-- src/benchweave/host/otdp_bridge.py` is empty — so the dispatch table (`otdp_bridge.py:339-347`:
identify, read, write, capture, stream_subscribe, stream_unsubscribe, invoke) and the module
docstring's gap list (`otdp_bridge.py:16-20`: dataset publishing/lookup **and the payload
services** still need the dataset-services slice; profile scheduling still needs a native async
host) are the same authorities #317's refute corrected against. The website's landed sentence
(`website/index.html:316`, verified in this tree) reads exactly: *"The OTDP bridge's remaining
scope is dataset publishing and lookup with its payload services, and profile scheduling on a
native async host."* The guide will mirror it **verbatim**.

---

## 1. Payload #319 — the guide's claim-reconciliation sweep

### 1.1 Root cause (established, not assumed)

The same defect #317 root-caused, on the guide's copy: the bridge's supported-verb set was named
in hand-written prose with no mechanical pin to the dispatch table that defines it. The guide's
`:17` sentence went false twice (capture `7a12d3d` 2026-09-22, invoke `f5cddf1` 2026-09-26) with
no signal. The #317 refute proved two things this design adopts as doctrine (record §12):

- **F1**: a "remaining scope is …" sentence is an exhaustive set claim — it must name the
  mechanism's **full** gap list (three gaps, not two), or it ships a false claim by omission.
- **F2**: dropping a verb enumeration does not avoid contradiction; the remaining-scope
  sentence **entails** the complement (capture, streaming and invoke work today), so until the
  guide is fixed, the deployed site's home page and its own staged guide page
  (`docs/user-guide/device-developer-guide.html`) contradict each other in one deployment.

The sweep also found stale sites #317's website census did not carry (it censused the website,
not the guide): two more sentences still describe the bridge as invoke-less, and one section
describes the not-yet-landed dataset publish services in present tense while §5 of the same
guide says they have not shipped.

### 1.2 The sweep census (scope: the guide's status/verb-bearing claim rows)

| # | Site (this base) | Claim | Source checked | Verdict |
|---|---|---|---|---|
| 1 | `:13` Baseline line | architecture 1.5 · OTDP 0.2.2 · adapter API 1.1 · registry 0.1.1 · execution 0.2.0 · interface 0.1.0 | `standards/standards-manifest.json` actives; #221 docs ratchet pins the line | CURRENT |
| 2 | `:15` "Current status" | "…a Python scaffold…" understates the PoC state | WP09 acceptance gate, `tests/integration/test_poc_acceptance.py` (#317 W1/H1) | **STALE → FIX (a)** |
| 3 | `:17` "External plugin runtime status" | "…for identify, scalar read and scalar write. … Profile actions, capture/streaming and automatic activation … are not provided by this bridge." | `otdp_bridge.py:339-347` (7 verbs), docstring `:16-20`; invoke landed `f5cddf1`; run-driven activation records (guide §5) | **STALE → FIX (b)** |
| 4 | `:88` "There is no public registry service yet" | registry service absent | corroborated as N2 in #317's census; no service exists | CURRENT |
| 5 | `:98` §3 integration-model table | declarative SCPI/UART/CAN cannot express class invoke, capture, streaming — adapter required | corpus declarative model (otdp spec §5/§7); no declarative invoke/capture lane exists | CURRENT |
| 6 | `:113` §4 simulator paragraph | "The current public bridge still lacks their profile actions" | bridge HAS invoke (`f5cddf1`); the **sim's bridge-leg adapter** does not — `plugins/benchweave/sim_psu/src/benchweave_sim_psu/adapter.py:95-113` (identify/read/write/stream; catch-all `UNSUPPORTED`) | **STALE → FIX (c)** — false at bridge level; re-attribute to the adapter |
| 7 | `:125-134` checklist spot rows (versions; dataset permissions; dataset identity) | served set; `artifact_writer` "grants the payload services"; host mints `pay:` ids | contract-shape prose of the vendored spec; permission wiring is schema-level | CURRENT-as-contract, disclosed by edit (e); no edit |
| 8 | `:139-150` full-form admission + `x-stg-issued-inputs` | per-pin validation, projection | CON-10 amendments (#217 slice 3) | CURRENT |
| 9 | `:166-203` OTDP version pins + dev-head pins | Q6 classes, content-addressed dev pins | CON-1/CON-14 amendments (#215-#219) | CURRENT |
| 10 | `:425` §5 invoke gating | gates before device; `ds:{operation_id}` minted; dataset-shaped result refused day one | issue #146 lane; `otdp_bridge.py` invoke clamp `:386-399` | CURRENT |
| 11 | `:429-433` §5 capture | permission gate, budget clamp, abort epilogue | issue #176 rows B/D; docstring `:28-49` | CURRENT |
| 12 | `:449-457` §5 streaming + event honesty | `event_sink` gate, poll rhythm, landing | issue #167 lane | CURRENT |
| 13 | `:459` §5 demo-lattice parenthetical | "(write/read + capture — … neither runnable over a bridge that carries no invoke, the deferred lane)" | bridge carries invoke (false atom); the **committed adapter** implements identify/read/write/stream, not invoke (`adapter.py:95-113`); the "(write/read + capture)" verb list itself must be reconciled against the committed demo fixture at build time (§1.3-d) | **STALE → FIX (d)** |
| 14 | `:461-477` §5 run-driven streams | run engine owns subscriptions | issue #167 lane | CURRENT |
| 15 | `:525-529` §7 dataset publish/payload prose | "The publish contract. `dataset_publish` validates …" — present tense | `payload_create`/`dataset_publish` appear **only in docs/** (zero hits in `src/`); bridge docstring names the dataset-services slice as pending; the guide's own `:425` says "until the dataset publish services ship" | **TENSE CONTRADICTION → FIX (e)**: one disclosure clause; the paragraph stays (it is the contract's shape) |
| 16 | §10 dev loop | publish_dev, dev-unsigned policy | registry lanes (`resolver.py` dev-unsigned) | CURRENT |
| 17 | §11 AI task template | "Target: a served OTDP version (0.2.2 active; 0.2.0 remains served)" | served set | CURRENT |
| 18 | §12 review/acceptance | handoff discipline | — | CURRENT |

**Census result: N = 18 rows; 4 STALE (2, 3, 6, 13) + 1 tense-disclosure (15) = 5 edits; 13
CURRENT/CURRENT-as-contract.** The census is the increment's scope: a NEW stale site found at
build time outside these rows gets a verdict row and, if it is not verb/status-class, a
follow-up issue — never an in-flight rewrite (risk R1).

### 1.3 The edits (exact, except (d) which is prescribed-and-reconciled)

**(a) `:15`** — single-phrase edit:

```diff
- ...provides architecture contracts, synthetic fixtures, a Python scaffold, architecture CI, and the
+ ...provides architecture contracts, synthetic fixtures, a simulator-first PoC through its acceptance
+   gate, architecture CI, and the
```

(Wrap to the guide's existing line width at build; the phrase swap is the whole edit. Source:
WP09 / `tests/integration/test_poc_acceptance.py`, the same evidence row as #317's H1.)

**(b) `:17`** — the core fix. S1 loses the verb enumeration (pointer to §5 instead, where the
permission gates live at `:425-457`); S3 becomes the website's corrected sentence **verbatim**
(so the same-deployment consistency check in §1.4 is a byte comparison):

```diff
- The new `load_otdp_plugin` loader and `OTDPBridge` support no-argument factories and async
- adapter API 1.1 for identify, scalar read and scalar write. They verify cached inventory and
- isolate package versions, while the caller supplies admitted scoped services and a matching
- monotonic clock. Profile actions, capture/streaming and automatic activation through a live
- gateway are not provided by this bridge.
+ The new `load_otdp_plugin` loader and `OTDPBridge` support no-argument factories and async
+ adapter API 1.1; the verbs the bridge dispatches and their permission gates are covered in
+ §5. They verify cached inventory and isolate package versions, while the caller supplies
+ admitted scoped services and a matching monotonic clock. The OTDP bridge's remaining scope
+ is dataset publishing and lookup with its payload services, and profile scheduling on a
+ native async host.
```

Three deliberate omissions, each sourced: the verb enumeration (drifts — the #317 doctrine);
"automatic activation through a live gateway" as a not-provided claim (the run composes bridges
through registry activation records — guide §5 `:463-466`; the claim died with the false
triad it rode in); any re-statement of the permission gates (§5 already carries them at
`:431`, `:451`, `:425` — one home per fact, doc-taxonomy rule 1).

**(c) `:113`** — re-attribute the gap from the bridge to the adapter:

```diff
- The current public bridge still lacks their profile actions, and the synchronous cores still
- require `benchweave==0.1.0`.
+ The bridge-leg adapter does not implement their profile actions or capture, and the
+ synchronous cores still require `benchweave==0.1.0`.
```

(Source: `adapter.py:95-113` — identify/read/write/stream implemented, everything else
`UNSUPPORTED`. This is a plugin-capability statement whose mechanical source is the plugin's
own adapter + descriptor, not the bridge's set; it is not row 23's enumeration class.)

**(d) `:459` demo-lattice parenthetical — prescribed, reconciled at build.** Two atoms are
false today ("a bridge that carries no invoke"; possibly the "(write/read + capture)" list —
the adapter implements stream, not capture). The builder reconciles against the committed demo
fixture (the procedure and policy under `fixtures/execution/`) plus `adapter.py:95-113`, then
rewrites the parenthetical attributing the deferred lane to the **committed adapter**
(expected shape: "…neither runnable over the committed bridge-leg adapter, which implements
identify/read/write and the stream verbs but not invoke (the deferred lane)"), correcting the
verb list to what the committed demo actually drives. Every atom of the shipped wording must
cite its source in the commit message — the same census discipline as the other rows.

**(e) `:527`** — one disclosure clause at the head of the publish-contract paragraph; the
contract prose stays (it describes the vendored contract's shape, which is the guide's
charter):

```diff
- **The publish contract.** `dataset_publish` validates the manifest against...
+ **The publish contract** (these services are the pending dataset-services slice — the bridge
+ docstring names it as remaining scope; until it lands, §5's day-one refusal is the behavior
+ that ships). `dataset_publish` validates the manifest against...
```

**Not edited, with reasons on record:** `:131-132` (checklist rows — contract-shape authoring
guidance, disclosed by (e)); `:13` (baseline — current, ratchet-pinned); every CURRENT row.

**Docs-literal baseline (#221):** none of the five edits adds or removes a three-component
literal — the `benchweave==0.1.0` clause at `:113` is kept verbatim — so
`scripts/standards/docs-literal-baseline.json` must NOT move. A refresh diff appearing at gate
time is a KILL signal (§1.4), not a routine update.

### 1.4 Pre-committed acceptance rule (#319)

Written before any measurement. No statistical effect; the honest metric is claim accuracy at
zero tolerance.

- **Metric**: unreconciled-claim count over the §1.2 census.
- **Sample size**: N = 18 rows (the full census of the guide's status/verb-bearing claims).
- **Effect size**: zero tolerance — 18/18 reconcile post-edit; a claim whose source cannot be
  opened is NOT reconciled.
- **SHIP** (all must hold):
  1. 18/18 census rows reconcile (reviewer re-derives independently; each row's source named).
  2. The `:17` remaining-scope sentence is **byte-identical** to `website/index.html:316`'s
     sentence (modulo the trailing period context) — checked by grep on both files.
  3. **The F2 contradiction is dead**: post-merge (CI docs lane, or a local
     `uv run python scripts/assemble_docs_site.py --dest /tmp/site-preview`), the assembled
     tree contains the identical sentence on the home page and on
     `docs/user-guide/device-developer-guide.html`. Pre-change this check FAILS (the two pages
     contradict) — that red is the control that fluff cannot pass; run it on the pre-change
     tree once, then on the branch.
  4. No bridge-verb enumeration survives in any STATUS sentence the sweep touches (§5's
     detailed lanes are exempt — they document each lane's contract, not the set).
  5. `docs-literal-baseline.json` unchanged; the version-literal gates green.
  6. Standards tripwire empty (`git diff origin/main...HEAD -- standards/` — nothing in this
     slice touches it).
- **KILL** (any one kills): a shipped claim without a reconciling source (cut or reword, never
  land); a verb enumeration reintroduced in a status sentence; unexpected baseline motion; the
  assembled-site consistency check failing post-merge.
- **UNDERPOWERED**: a source that cannot be opened at review time → the claim is **cut** and
  the row recorded as unverifiable — cut beats assert. Edit (d) specifically: if the demo
  fixture cannot be reconciled confidently, ship (d) as the adapter-attribution rewrite ONLY
  (the atom that is certainly false) and file the verb-list question as a follow-up issue.

---

## 2. Payload #321 — the drift-pattern cure: obligation row 23

### 2.1 The two candidates, costed

**(a) An obligations row (+ its hook warning).** Cost: one row in
`docs/internal/drift-and-obligations.md`, one rule in `.claude/hooks/drift-guard.mjs` (a pure
data addition to `RULES` — the hook's own header says "Add a rule by appending to RULES"),
one test in `.claude/hooks/tests/drift-guard.test.mjs` (the file already runs the real hook
end-to-end per path). Precedent: obligations 4 and 8 are exactly this shape (a path-triggered
docs-review duty; obligation 8 already warns on `otdp_bridge.py` for the protocol mirror —
row 23 warns for the verb-set sweep; two rules may fire on one path, each once, by design).
The row is **not itself a hand-written list that drifts**: it names surfaces, mechanisms and
trigger paths — the file's own idiom — never the verb/command contents.

**(b) A generated scope line for high-churn surfaces.** Cost: a generation/stamping pipeline
per prose surface (CON-13-class machinery — tokens, derivation, coverage tests — per sentence),
for a defect class that currently touches three sentences. The generated shape pays where a
whole surface regenerates: that is precisely payload #291 (the site's standards-CLI page,
generated from `--help`), which this same PR ships. Rejected for the prose surfaces on cost;
the row carries them.

**Verdict: (a), plus #291 as the one place (b) is worth building.** The issue's own doctrine —
the cure must not itself be a hand-written list that drifts — is satisfied by the row naming
*where lists live and what regenerates*, not by the row carrying a list.

### 2.2 The row (exact text, appended as obligation 23 after row 22)

> 23. **The bridge verb set and the CLI command surfaces** (the `supported` dispatch table and
>     module docstring in `src/benchweave/host/otdp_bridge.py`; the Click tree under
>     `src/benchweave/cli/`; the argparse family in `src/benchweave/standards/__main__.py`) 🪝 →
>     a change to any of those sets sweeps every prose surface that names them, in the same
>     change. Bridge-status sentences state **remaining scope only, never a verb enumeration**
>     — the #317 doctrine (refute F1/F2): a verb list in prose is a set claim with no
>     mechanical pin, and a "remaining scope is" sentence is a set claim by complement that
>     must be checked against the bridge docstring's FULL gap list (`otdp_bridge.py:16-20`).
>     The surfaces: `website/index.html`'s home-page sentence and `docs/device-developer-guide.md`'s
>     status/simulator paragraphs (kept byte-mirrored where both carry the same claim); the CLI
>     command sets in `docs/operator-guide.md` §10 (BOTH tables), the website's CLI-reference
>     card, and the docs site's generated standards-CLI page — that page regenerates at build
>     from `python -m benchweave.standards --help` (`scripts/assemble_docs_site.py`;
>     `verify_tree` pins its presence) and `tests/contract/test_docs_site_standards_cli.py`
>     pins its verb set, so a verb add/remove reddens the pin: that red is the tripwire doing
>     its job, not noise. The dispatch-table/CLI diff is the trigger; docs-only refactors of
>     these sentences are not.

### 2.3 The hook rule (exact shape)

Appended to `RULES` in `.claude/hooks/drift-guard.mjs`:

```js
{
  // Obligation 23 — verb/command-set prose drifts with the mechanism that defines the set.
  id: 'verb-set-docs-drift',
  triggers: (p) =>
    p === 'src/benchweave/host/otdp_bridge.py' ||
    p.startsWith('src/benchweave/cli/') ||
    p === 'src/benchweave/standards/__main__.py',
  satisfies: (p) =>
    p === 'docs/device-developer-guide.md' ||
    p === 'docs/operator-guide.md' ||
    p === 'website/index.html' ||
    p.startsWith('tests/contract/'),
  message: [
    '**[Drift 23] A verb/command-set mechanism was edited — does every prose surface that names the set still match?**',
    '',
    'The bridge dispatch table (`otdp_bridge.py`) and both CLI trees (`src/benchweave/cli/`,',
    '`src/benchweave/standards/__main__.py`) are the authorities for sets that prose names on',
    'the website home page, the device-developer guide, operator-guide §10, and the generated',
    'standards-CLI page. Bridge-status prose states remaining scope only (against the docstring',
    'FULL gap list) — never a verb enumeration. The site page regenerates; the tables and the',
    'verb pin (`tests/contract/test_docs_site_standards_cli.py`) sweep in the same change.',
  ],
}
```

(`otdp_bridge.py` then triggers both rule 8 and rule 23 — intended: different duties, each
fires once per session.)

**Hook test**: one new case in `drift-guard.test.mjs` — `src/benchweave/standards/__main__.py`
fires "Drift 23"; pre-touching `docs/operator-guide.md` in the same session quiets it (the
existing satisfy-first pattern).

### 2.4 Pre-committed acceptance rule (#321)

- **Metric**: row 23's trigger set, mechanically checked — every named path exists in the tree
  at review time, and the row/hook fire on the incident class they claim to cover.
- **SHIP** (all must hold):
  1. Row 23 lands with the 🪝 marker; every path string it names resolves in the tree.
  2. The hook rule fires on all three trigger shapes and quiets on the satisfy shapes (the new
     test, green).
  3. **The incident replay control**: `git show 7a12d3d --stat` (the capture landing that
     started this) touches `src/benchweave/host/otdp_bridge.py` — row 23's trigger set contains
     that path, so the incident class is covered. Same check for a `src/benchweave/cli/` diff
     (any recent CLI commit) and a `standards/__main__.py` diff (the resolver verbs' landings).
  4. The row itself carries NO verb or command enumeration (the cure must not be the disease);
     grep the row for the known verb names — zero.
- **KILL**: a named trigger path that does not exist (dead row); the row/hook enumerating
  verbs; the replay control finding an incident-shaped diff that touches no trigger path.
- **UNDERPOWERED**: n/a — structural checks. **Disclosed residual** (a guard states what it
  does not catch): the row is review-borne, not a gate — a verb-set change whose author
  ignores the warning lands with stale prose unless the #291 pin or a reviewer catches it; the
  mechanical halves are exactly the #291 pin (CLI family) and the acceptance-control mirror
  check (bridge sentence). The bridge verb set itself has no test pin — the deferred lint (§6)
  is that escalation.

---

## 3. Payload #291 — the docs-site standards-CLI page, generated from `--help`

### 3.1 Root cause

The site's CLI reference renders from the Click tree (`great-docs.yml` `cli.module:
benchweave.cli.commands`); the resolver family is an argparse sibling (`python -m
benchweave.standards`, `src/benchweave/standards/__main__.py:1-253` — export/check/matrix/
versions/repin/list/pin/upgrade/why) that Click introspection cannot see. The in-repo half
landed with the #288 fold (`docs/operator-guide.md:747-762`, both tables); the public site
half is this payload. A hand-written site page would be the exact shape #321 exists to kill —
disfavavored by the issue and by doctrine.

### 3.2 Mechanism — a generated, staged user-guide page

Extend the assembly's **staging** mechanism (the proven path: every user-guide page is
build-time staged; the site's own docs say so):

1. **`scripts/assemble_docs_site.py`**:
   - `run()` gains an optional `env: dict[str, str] | None = None` passed to `subprocess.run`
     (the only edit to an existing line).
   - `capture_standards_help() -> str` — `run([sys.executable, "-m", "benchweave.standards",
     "--help"], cwd=REPO, env={**os.environ, "COLUMNS": "100"})`; refuses empty stdout
     (`standards_cli_capture_failed:`). `COLUMNS` is pinned so argparse wrapping is
     deterministic (a width-varying capture would make the pin flaky).
   - `render_standards_cli_page(help_text: str) -> str` — PURE. Parses the argparse help's
     subcommand block (the `{export,check,...}` choices plus each verb's one-liner) into a
     verb table; **refuses an unparsable capture** (`standards_cli_help_unparsed:`) — the
     renderer can never ship an empty or silently-shrunk page. Emits the page: H1, frontmatter
     (`title:` + `source: generated from python -m benchweave.standards --help at build
     time`), an intro paragraph (separate argparse tree; operator-guide §10 is the in-repo
     quick reference), the derived verb table, and the verbatim `--help` output in a fenced
     block.
   - `GENERATED_PAGES: dict[str, str] = {"standards-cli.md": "user-guide/standards-cli.html"}`,
     merged into `site_paths()` (drives `verify_tree` — the page's absence fails assembly).
   - `main()` calls `write_standards_cli_page(staging)` immediately after
     `stage_pages(USER_GUIDE, ...)` — the file exists in `user_guide/` before
     `great-docs build`.
2. **`great-docs.yml`**: the "Guides" section gains `- standards-cli.md`.
3. Free by construction: theme/navbar/search (Great Docs renders it), the `.md` twin and
   therefore `llms.txt`/`llms-full.txt` (`write_llms_txt` picks it up), and the
   `verify_tree` required-path assertion. No `website/` byte moves (no CON-13 surface, no
   line-count exposure).

**Alternatives rejected**: post-build HTML injection into `reference/cli/` (hand-built HTML
against tool-generated markup — fragile, no md twin, and `add_site_home_link`/`fix_root_doc_links`
are the only sanctioned repair shapes); extending `great-docs`' `cli:` config (the section
introspects a Click module — argparse is invisible by construction, which is the issue's
premise); importing and introspecting the parser in-process (requires a production refactor of
`__main__.py` to expose the parser — production code motion for a docs need, and the captured
`--help` is the honest artifact anyway).

### 3.3 The test (RED-first) — `tests/contract/test_docs_site_standards_cli.py`

Follows the `_assembler()` importlib pattern of `tests/contract/test_website_stamps.py`:

- **T1 (the pin, bidirectional)**: `render_standards_cli_page(capture_standards_help())`
  carries every verb of the PINNED set (the 9 verbs + short one-liner fragments — fragments,
  not full lines, so wrapping can't flake the pin) plus the provenance marker. Adding or
  removing a verb anywhere reddens T1 — the deliberate tripwire (row 23 says so).
- **T2 (fail-closed)**: `render("")` and `render("<garbage>")` refuse with
  `standards_cli_help_unparsed:`.
- **T3 (wiring)**: `site_paths()` carries the generated mapping; `great-docs.yml` lists the
  staged name; `main`'s call order is pinned by the assembly's own CI run (the docs lane) —
  T3 checks the two in-tree facts.
- **T5 (silent-shrink discriminator)**: a doctored capture with one verb deleted still RENDERS
  (8 verbs parse fine — T2 does not fire) and T1's pin comparison FAILS — proving the pin, not
  the parser, is what catches silent shrinkage. (T2 and T5 together are the pair; either alone
  proves the wrong thing.)
- **RED-sanity (G3)**: on the pre-change tree the file fails at import (missing assembler
  attributes) with a collected count > 0 — `no tests ran` is a FAILED check. Revert the
  `scripts/` diff only → still red (AttributeError); restore → green.

### 3.4 Pre-committed acceptance rule (#291)

- **Metric**: generated-page fidelity — every real verb of the family renders on the page the
  site ships, and the page cannot exist in a silently-degraded state.
- **Sample size**: the full verb set, N = 9 (the pinned set; the pin is the spec).
- **SHIP** (all must hold):
  1. RED shown pre-change (collected > 0, failing on the missing attribute); green post-change.
  2. T1/T2/T3/T5 green on the branch; `uv run ruff check .` and fresh-cache bare `uv run mypy`
     clean (the assembler is strict-typed; new functions fully annotated).
  3. The CI docs lane green — the page exists at `docs/user-guide/standards-cli.html` in the
     artifact, `llms.txt` indexes it, no link regressions (`verify_tree` whole).
  4. The scripts-scope version-literal count unchanged (the generator adds no literals).
  5. The page's ONLY verb literals live in the TEST pin — the generator derives from the
     captured help (grep the generator for verb names: zero).
- **KILL**: any pinned verb absent from a page that passed assembly; the page missing from a
  tree `verify_tree` passed (wiring hole); a hand-written verb list inside the generator; the
  docs lane red.
- **UNDERPOWERED**: if a review environment cannot run the live capture (no synced env), the
  renderer may be exercised on a recorded capture — but then the CI docs lane is the ONLY
  live-capture evidence and the review says so; it may not claim local-capture proof.

---

## 4. Payload #320 — DON'T-BUILD this round (ruling recorded)

`standards/plugin-ui/0.3.0/README.md` carries pre-multi-serving bridge prose in **released,
digest-frozen bytes**. Principle 13 (`standards/GOVERNANCE.md`, copy-never-move): the old
version dir and its corpus-manifest rows stay digest-frozen; an in-place edit is not a path,
and a same-version byte swap is refused by the sync machinery. The corrected prose rides the
next plugin-ui bump's new version directory, whose rows cite the current corpus path as
`source` — exactly the deferral's own carrier and reopen trigger. **No design, no diff, no
mechanism.** The outcome posts to issue #320 as a comment (the design-outcome rule); the issue
stays open on its existing trigger (the next plugin-ui version bump) unless the owner closes
it. Nothing in this PR touches `standards/`.

---

## 5. Slice and commit structure

Branch `feat/website-deferrals`, ONE PR against `main`, body linking #319 + #321 + #291
(closing) and #320 (ruling referenced). No SDK PR (zero `packages/sdk` motion — the two-repo
discipline is not engaged).

| Commit | Slice | Content | Lane |
|---|---|---|---|
| 1 | this record | `.claude/deep-review/2026-10-01-website-deferrals-design.md` | fast lane |
| 2 | #319 | the five guide edits + the census table with per-row sources in the commit message | fast lane (docs-only still runs it — #247) |
| 3 | #321 | drift row 23 + `drift-guard.mjs` rule + hook test | fast lane + `node --test .claude/hooks/tests/*.test.mjs` |
| 4 | #291 | assembler generator + `run()` env param + `great-docs.yml` + the test file | fast lane; **RED→GREEN in-commit evidence** |

Full battery + both standards tripwires once, immediately before push. The CI docs lane is the
rendered-page verifier for slices 2 and 4 (it builds the site on the PR).

---

## 6. Deferrals

Home for all rows: **documentation here** (this record); no scheduled carrier issue unless the
owner files one. Per the deferral-row contract:

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D-1 | Per-verb detail pages for the standards family (flag-level `--help` per subcommand on the site) | documentation here | the first flag addition to any standards verb, or the first user report asking flag-level detail of the site page |
| D-2 | A website Docs-panel link from the CLI card to the generated page (discoverability beyond the sidebar/llms.txt) | documentation here | the next website prose pass, or a discoverability report |
| D-3 | A mechanical verb-enumeration lint over status prose (negative-pattern guard; the bridge set has no test pin — row 23's disclosed residual) | documentation here | the next observed verb-list drift (also #321's issue-level trigger — the lint is the escalation, the row is the cure) |
| D-4 | Folding the generated page into great-docs' own reference section | documentation here | a great-docs release naming argparse/multi-CLI reference support |
| D-5 | plugin-ui 0.3.0 README prose | follow-on: the existing issue #320 (its own carrier) | the next plugin-ui version bump (the issue's own trigger) |

---

## 7. Review tier and Step-1 keyword scan (design-time call, #254)

Scans run over each slice's constructed expected diff (the ± text of §1.3, §2.2-2.3, §3.2-3.3
as it will land), case-sensitive substring counts over the eight rubric keywords. The review
re-derives both per #254; the tier below is the pre-commitment.

**Slice 2 (#319) — TIER 1** (docs `*.md` only; no path rule and no keyword rule fires).
Scan of the five edits' ± text: `threading` 0, `asyncio` 0, `subprocess` 0, `sha256` 0,
`hashlib` 0, `migrate` 0, `recovery` 0, `protection` 0. ("native async host" does not contain
`asyncio`; the removed `:17`/`:113` lines carry no keyword — verified against the exact
current text.) Note for the reviewer: #317 took Tier 3 because ITS lines carried
"kill-recovery"/"protection"; these lines do not — the call is scanner-verified, not
inherited.

**Slice 3 (#321) — TIER 2** (default rule: the `.claude/hooks/*.mjs` code is neither docs-only
nor under a Tier-2-listed path, so the default Tier 2 applies; no keyword fires).
Scan of the row + rule + test text: all eight keywords 0.

**Slice 4 (#291) — TIER 3** (the keyword rule fires: the `run()` env-param edit rewrites the
line carrying `subprocess.run`, so the diff text contains `subprocess` — expected count 2 (the
− and + of that one line); possibly 3-4 if the docstring mentions it). Path rules alone would
say Tier 2 (`scripts/` + root config + `tests/`). G6 (independent second reviewer) is
mandatory at this tier; per the standing two-lane Tier-3 doctrine the refute runs two
independent adversary lanes. The tier is 3 for any count ≥ 1 — deliberately NOT worded around
the keyword (reusing `run()` is the right mechanism regardless; inlining `subprocess.run`
elsewhere would only add counts).

**Maximum tier across slices: 3 (slice 4).** Each slice's scan covers its own expected
implementation diff; this record, committed as commit 1, quotes the same terms and would add
counts if scanned itself — immaterial, the max is 3 already (scanner-independent, #317's
precedent).

**Standards-governor mandate (#69): does not fire** — no `standards/` bytes, no plugin
contract locks, no SDK vendored tree, no standard-version strings (the guide edits move no
literal; #320's ruling touches nothing). Standing tripwire reported empty at push.

---

## 8. Invariant, drift and surface impacts

- **No CTL/STO/CON/REG motion or amendments.** CON-13 is exercised, untouched — zero
  `website/` bytes move in this PR (the #319 mirror is on the guide side), so no stamp, token,
  or line-count exposure. CON-4/CON-7 untouched (no corpus motion).
- **Drift-and-obligations**: row 23 ADDED (this PR's own payload); row 18's inventory
  unchanged (no new version-bearing claim site — the guide edits introduce no literal; #291's
  generated page carries `--help` text, which contains no semver literal).
- **Surfaces moved**: `docs/device-developer-guide.md`, `docs/internal/drift-and-obligations.md`,
  `scripts/assemble_docs_site.py`, `great-docs.yml`, `.claude/hooks/drift-guard.mjs`,
  `.claude/hooks/tests/drift-guard.test.mjs`, new `tests/contract/test_docs_site_standards_cli.py`,
  this record. **Not moved**: MCP tools, REST/openapi, CLI code, standards bytes, SDK,
  fixture lattice, `website/`, `pyproject.toml`/`uv.lock`.
- **No on-disk format or schema** is created or changed (the staged page is build output,
  gitignored like the rest of `user_guide/`).
- **CI cost**: zero new lanes/jobs. The docs lane builds the generator on every PR (one extra
  `python -m` subprocess, sub-second); `gates` runs the new test file; the hooks test joins
  the existing node suite. Nothing balloons.

---

## 9. Collision findings (pre-flight)

- **Open PRs #325/#326** (web-UI G-slices): no file overlap with any surface of this design
  (checked both PRs' file lists — zero matches on `docs/`, `scripts/`, `website/`,
  `great-docs.yml`, `.claude/hooks/`).
- **Pushed branch `docs/issue99-deferral-terms`**: overlaps ONLY on
  `docs/internal/drift-and-obligations.md` (+8 there vs this PR's append of row 23). Evidence
  gathered at pre-flight: the branch's +8 lines are **verbatim-identical to main's already
  landed obligation 19** ("Skills shared with the SDK repo"), its README +72 matches main's
  landed "deferral-row contract (issue #99)" section, and its `SKILL.md` +5 matches main's
  reference — the branch looks like a **stale re-push of content that landed on main via
  another SHA**, with a submodule-pointer bump that may or may not be live work. It is NOT
  treated as a serializer here: this PR's hunk appends after row 22 (a disjoint region), so
  even a simultaneous landing merges cleanly or resolves trivially. **Flagged for the
  maintainer**: confirm whether that branch is superseded before giving it review time. If it
  turns out live and lands first, this PR rebases — row 23's append point moves, nothing else.

---

## 10. Top risks, each with its falsifier

- **R1 — The sweep scope-creeps at build time** (a 19th stale site appears mid-build).
  *Falsifier/handling*: the census IS the scope; a new row gets a verdict, and anything not
  verb/status-class goes to a follow-up issue. The KILL rule bars landing unreconciled claims.
- **R2 — The mirrored sentence drifts again** (two hand-written copies of one claim — the
  guide's and the website's). *Falsifier*: acceptance §1.4-SHIP-3's byte-compare, then row 23's
  review duty; the durable mechanical cure (D-3 lint) is deferred with its trigger. Standing
  residual, disclosed.
- **R3 — The generated page breaks the build** (a listed-but-missing staged file, or a great-docs
  hard-fail on it). *Falsifier*: the generator runs before the build in `main()`; `verify_tree`
  refuses its absence; the CI docs lane is the end-to-end proof at PR time. A red lane at PR
  time is the falsifier catching it, not a ship-blocker class.
- **R4 — Argparse help output varies by environment** (terminal width → wrapping → flaky pin).
  *Falsifier*: `COLUMNS=100` pinned in the capture env; the pin asserts verb names +
  short fragments, never full lines. A local run with a different COLUMNS still produces the
  same captured bytes.
- **R5 — Double-firing hook noise** (`otdp_bridge.py` triggers rules 8 and 23). *Intended*:
  different duties, each once per session (separate state files); disclosed in §2.3.
- **R6 — The tier call is contested at review** (slice 4's `subprocess` count differs from the
  constructed diff). *Falsifier*: the tier is 3 for any count ≥ 1 and 2 only at exactly 0 —
  the record states both sides; the review re-derives per #254 and the max stays 3 unless the
  implementation somehow avoids the word entirely, in which case Tier 2 + G6-not-required is
  the honest re-derivation.

---

## 11. What this record does not do

No production code under `src/` (the #291 mechanism lives in `scripts/` + config + tests). No
`standards/` bytes, no SDK bytes, no `website/` bytes, no invariants text, no new tooling or
dependencies. The build agent's slices are exactly §1.3's five guide edits, §2.2-2.3's row +
rule + test, and §3.2-3.3's generator + config + test file, in the commit order of §5, each
with its fast lane and the full battery before push. The #320 ruling posts to its issue and
touches nothing.

---

## 12. Dated corrections — 2026-10-01, the two-lane refute fold

Both refute lanes converged on a KILL/HIGH the census could not see: **this record's own
authority was stale.** Corrections below are dated, not retro-edited; the census re-derives
from the mechanism where corrected.

- **§0's re-verification proved UNCHANGED, not TRUE.** "`otdp_bridge.py` is unchanged
  between #317's base and this base, so the … docstring's gap list … are the same
  authorities" — the docstring was indeed byte-unchanged, but its content had gone stale
  2026-09-26 13:32–13:55 (issue #146 slice 3 + riders, commits `f2fa4b5`..`1792594`, all
  ancestors of this base): `src/benchweave/content/dataset_services.py` implements
  `dataset_publish`/`payload_create`/`dataset_lookup`/`artifact_read`, wired through
  `app.py`'s `dataset_factory` → `build_dataset_services` into `load_otdp_plugin`
  (`app.py:806-856`); the bridge's own code carries the landed services
  (`self._dataset` at the invoke clamp and the dataset-shape cross-check); issue #146 is
  CLOSED and the E2E is green (36/36, `tests/integration/test_issue146_e2e.py`). An
  unchanged authority is not thereby a true one — the check needed content re-derivation,
  not byte comparison.
- **Census row 15's source claim was FALSE.** "`payload_create`/`dataset_publish` appear
  only in docs/ (zero hits in `src/`)" — the real count is 38 hits across 7 `src/` files
  (`dataset_services.py` 29, `otdp_bridge.py` 1, `app.py` 1, `mcp.py` 2, `operations.py` 2,
  `rest.py` 2, `otdp_contracts.py` 1); REST and MCP carry the services as well. The claim
  was inherited from the design's census, not re-run at build — the builder's miss, named.
- **Census row 10's CURRENT verdict was wrong.** `:425` carried "until the dataset publish
  services ship, and when they do" — a false premise since 2026-09-26 (the services had
  shipped four days before this record's base). Row 10's source check read the invoke
  gating's mechanics but not its tense.
- **§1.3 edit (e) was therefore WRONG and is REVERTED**: the original present-tense §7
  publish-contract paragraph was true (the services ship); the added "pending
  dataset-services slice … until it lands" disclosure shipped a false claim. `:425`'s
  wait-clause is swept the same way.
- **The truth repair (this fold, one commit set on the same branch):** the bridge
  docstring's gap list is rewritten FROM the mechanism (dispatch table — still the 7 verbs,
  the dataset lane rides the composing services, not dispatch; the services wiring above;
  the open tracker: #159 "native async host" OPEN — nothing else of the old list remains);
  `website/index.html`'s sentence becomes "The OTDP bridge's remaining scope is profile
  scheduling on a native async host."; the guide mirrors it byte-identically (the §1.4
  byte-compare control re-run on the corrected pair); row 23 no longer pins the docstring
  as authority — the mechanism is the authority and the docstring a derived surface the
  row also sweeps (it went stale once and its false sentence reached two prose mirrors).
- **§3.3's RED-sanity wording corrected** (refute lane 2 F3): "the file fails at import" —
  wrong; the module imports and the failure is at CALL time (AttributeError inside the
  test body), which is what makes the collected-count requirement meaningful.
- **Census re-derivation consequence:** rows 3, 10 and 15 change verdict or content (3's
  mirrored sentence now carries the corrected claim; 10 EDITED — the `:425` sweep; 15
  REVERTED-to-true); the other 15 rows' verdicts stand re-checked against their named
  mechanisms. One further site found and left, with its verdict: `otdp_bridge.py:390`'s
  comment "payload appends once the dataset services land" reads as future tense but sits
  under the `self._dataset is not None` guard, under which "once … land" can read as "when
  attached" — ambiguous rather than clearly false; not edited (R1), flagged for the
  maintainer.
