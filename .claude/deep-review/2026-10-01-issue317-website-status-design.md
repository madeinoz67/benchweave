# Issue #317 — bring the website's "Where it stands" current: design record

Status: DESIGN COMPLETE, awaiting the owner's fork calls (§4.3) before build.
Base: `origin/main` @ `33b4c55`. Branch (at build): `feat/issue317-website-status`;
this record is commit 1 of that branch. Triage: PUBLIC placement — the record was checked
against `.claude/deep-review/README.md`'s private list and carries no person, client, bench,
serial, or commercial identifier; every citation is a public path, issue, or PR.

---

## 0. Summary

The "Where it stands" section and two neighboring claim sites on the public site describe the
project as it stood on **2026-09-16** (commit `5693bcf`, "a validated 'Where it stands'").
Since then three things landed that the section does not know about, and one of its claims
became false:

1. **The standards-dependency arc** (#203/#288: multi-version serving, per-pin admission, the
   resolver CLI, dev-head pins, promotion records) — the "dependency-management story" the
   issue names — is entirely absent from "Working now".
2. **The OTDP bridge grew verbs** — capture (`7a12d3d`, 2026-09-22), streaming (the poll
   engine, same window), invoke (`f5cddf1`, 2026-09-26). "the OTDP bridge carries identify
   and scalar read/write **only**" is **false today**.
3. **The UI direction was ruled** — PRD 12 (#295, ruled 2026-10-01): the gateway's first
   operator web UI will be **server-rendered (HTMX)** and **retire the React reference
   tree**. "Then a basic operator UI on the component library that exists today" points at
   the component library being retired.

Two further stale sites ride along: the hero status badge ("architecture baseline and Python
scaffold") and the Docs panel's CLI-reference card (its hand-written command list is missing
`retention` and `dispose`; the real tree has 11 commands).

**The increment**: four single-line rewrites in `website/index.html` — nothing else. No new
stamps, no mechanism, no standards bytes. The D4 scope question resolves to **closure stands**
(§4). Three deferrals file as sub-issues of #317 (§9), the meatiest being a defect pattern
this audit surfaced: the same hand-written bridge-verb sentence drifted stale on **three
surfaces at once** with no pin to the dispatch table that regenerates the verb set.

**DON'T-BUILD verdicts are recorded** for the optional refinements found on the way (§9.4):
they are real but not worth the diff.

---

## 1. Root cause: why the section aged (and why one claim is false, not merely old)

Hand-written public prose has **no mechanical pin** to machine state. The version badges are
pinned (CON-13: `{{stg-*}}` tokens, manifest-derived at assembly, bidirectional fail-closed
coverage, literal ban over the class-11 set — `scripts/assemble_docs_site.py:321-379`,
`tests/contract/test_website_stamps.py`). The *prose* around them is pinned only by review —
which is exactly why the badges still show plugin-ui 0.3.0 / preview 0.2.0 correctly while the
sentences beside them describe September 16.

The false claim has a sharper root cause. The bridge's supported-verb **set** is named in
prose on three surfaces, none of which regenerates from the mechanism that defines the set —
the dispatch table at `src/benchweave/host/otdp_bridge.py:340-353`:

| Surface | Text | Verdict today |
|---|---|---|
| `website/index.html:316` | "the OTDP bridge carries identify and scalar read/write only" | FALSE — fixed by this increment |
| `docs/device-developer-guide.md:17` | "OTDPBridge support … identify, scalar read and scalar write. … Profile actions, capture/streaming … are not provided by this bridge" | FALSE — deferred, sub-issue (§9.1) |
| `standards/plugin-ui/0.3.0/README.md` ("Ownership and execution") | "The current adapter bridge supports identify and scalar read/write" | STALE-in-released-bytes — deferred, sub-issue (§9.2) |

The dispatch table reads: `identify`, `read`, `write`, `capture`, `stream_subscribe`,
`stream_unsubscribe`, `invoke` (`otdp_bridge.py:340-353`); the module docstring
(`otdp_bridge.py:1-30`) states the same with the gates (capture is `artifact_writer`-gated,
streaming is `event_sink`-gated) and names what genuinely remains: "Dataset
publishing/lookup and the payload services still need the dataset-services slice; profile
scheduling still needs a native async host." G4's rule — a set named in prose is regenerable
from a mechanism — was violated three times by three authors over four days. This is the
defect *pattern* the sub-issue in §9.3 carries; this record's website fix deliberately does
**not** re-enumerate the verbs (§3 explains why that is also what keeps the fixed site from
contradicting the two stale surfaces).

---

## 2. The claim-site census (staleness review)

Census scope: every hand-written claim site in `website/index.html` (the only prose file in
`website/`; `assets/` is styles, nav JS, and the logo — no claims). The live site was fetched
and matches the in-repo source byte-for-byte modulo stamp resolution, so this census covers
both. Token claim sites (badges, deep links) are listed for completeness; they are
machine-pinned and green.

| # | Site | Claim | Truth check (source) | Verdict |
|---|---|---|---|---|
| 1 | `:64` hero badge | "Status: architecture baseline and Python scaffold" | The PoC is through its acceptance gate (WP09 complete, `tests/integration/test_poc_acceptance.py`; §3 evidence map row W1) | **STALE → FIX** |
| 2 | `:67` hero sub | The one-line promise (plugins, typed profiles, bounded procedures, ownership, evidence, safe endings) | Matches the architecture's promise (AGENTS.md §1) | CURRENT |
| 3 | `:266-273` origin | History narrative; "Everything on this site says what has been built and what hasn't" | History; the discipline commitment is the site's own charter | CURRENT |
| 4 | `:280-285` surprised card 1 | A plugin needs no BenchWeave runtime; DPS-150 builds/tests unchanged outside the checkout; has driven the real supply; a standalone MCP host can control a device; the gateway owns the safety model | `plugins/fnirsi/dps150/pyproject.toml` `dependencies = []`; `docs/devices/dps150/compatibility-record.md` (live-verified captures, committed fixtures); descriptor: read-only, no DC PSU profile | CURRENT |
| 5 | `:287-291` surprised card 2 | Firmware path: shared session instruction, stage prompts, `firmware/` beside toolchain and compatibility record; prompts authorise software only | `docs/develop-your-device.md:199-203` (five-step path, shared session instruction) | CURRENT |
| 6 | `:294-297` AI callout | Five-step paths; development/testing/review/release prompts; AI device reviewer checks against contracts | `docs/develop-your-device.md` path structure; `docs/ai-device-reviewer.md` exists | CURRENT |
| 7 | `:302-303` plan lede | Four commitments; "The first PoC is simulator-first; the planned hardware MVP targets the FNIRSI DPS-150, with ESP32 as the provisional controller family" | Matches PRD/delivery plan; PoC done, hardware MVP still planned | CURRENT (tense nit, §9.4) |
| 8 | `:304-309` plan cards | Connect / Share / Coordinate / Expose | Architectural commitments (also cited as promises by `docs/implementation-planning/07-contributor-publishing-prd.md:20`) | CURRENT |
| 9 | `:315` Working now — 6 claims | PoC through acceptance gate; kill-recovery; admission + protection; 20 REST routes + 17 MCP tools; operator CLI; SDK scaffold + release-CI build/drive; DPS-150 (3 claims) | **All reconcile** (see §3 evidence map W1–W8) — but the section is **incomplete**: the dependency-management story is absent | **INCOMPLETE → REWRITE (extend)** |
| 10 | `:316` Next — 5 claims | Registry gateway side done ✓; registry service + device-install absent ✓; bridge "identify and scalar read/write **only**" ✗; "basic operator UI on the component library that exists today" ✗; hardware qualification + unattended commissioned ✓ | Rows N1–N7 in §3: two claims false or superseded | **STALE → REWRITE** |
| 11 | `:323-324` standards intro | Independently versioned, digest-frozen, validated in CI; SDK vendors same bytes | Corpus manifest digests; `make sync-sdk-standards` | CURRENT |
| 12 | `:328-364` six spec cards | Badge tokens + descriptions | Tokens match the manifest (otdp 0.2.2, registry 0.1.1, execution 0.2.0, interface 0.1.0, plugin-ui 0.3.0, preview 0.2.0 — verified against `standards/standards-manifest.json` and the live page's rendered badges); descriptions spot-verified against each corpus dir's contents | CURRENT (plugin-ui card understates 0.3.0 scope — nit, §9.4) |
| 13 | `:372` governance note | GOVERNANCE, manifest, corpus manifest, standards index | Files exist; index renders | CURRENT |
| 14 | `:378-380` docs intro | Great Docs; unversioned until first tag; every page links back | `refuse_if_tagged` + `add_site_home_link` in the assembler | CURRENT |
| 15 | `:383-397` guide cards | Labels + blurbs | Spot-verified against the guides | CURRENT |
| 16 | `:389` CLI-reference card | "`setup`, `serve`, `status`, `verify`, `demo`, `report`, `backup`, `restore`, `evidence`" | Real tree (`benchweave --help`): 11 commands — **`retention` and `dispose` missing** | **STALE → FIX** |
| 17 | `:399-410` reference + devices cards | Standards index; git-cliff changelog; DPS-150 protocol/compat; ESP32; agent skill; llms.txt | All exist; `write_llms_txt` in the assembler | CURRENT |
| 18 | `:412-418` SDK intro + tagline | Own repo/site/CI/release; submodule at `packages/sdk`; Python 3.13+; scaffold, validate, mock, preview | SDK commands at the pinned tree: `new`, `check`, `check-ui`, `check-preset`, `inventory`, `sync-standards`, `preview-ui`; "mock" = `MockContext`/`MockHost` (`benchweave_sdk/testing.py`), "scaffold" = `scaffold.py`/`new`, "validate" = the conformance checks, "preview" = `preview-ui` | CURRENT (capability words, not verb names) |
| 19 | `:419` SDK code block | `benchweave-sdk new plugins/acme/model100 --package benchweave_acme_model100` | `new` exists; invented name | CURRENT |
| 20 | `:428-466` Built with | Which model did which job; open tooling | The owner's own credit record — not machine-verifiable, no three-component literals (GLM-5.3 is outside the semver pattern), **untouched by this increment** | OUT OF AUDIT |

Census result: **20 claim-site rows; 3 STALE (1, 10, 16), 1 INCOMPLETE (9), 16 CURRENT/OUT.**

---

## 3. The proposed text (exact) + evidence map

Four single-line rewrites. **Constraint: line count preserved** — no inserted or deleted
lines in `website/index.html`, because two committed records cite line numbers in this file:
`docs/implementation-planning/10-contributor-publishing-design.md:19` cites
`website/index.html:316` (quoting the registry sentence this design keeps verbatim), and
`.claude/deep-review/2026-09-29-issue233-register-design.md` §2 cites `website/index.html:330-357`
(the spec cards). Single-line rewrites keep both resolving.

### 3.1 Line 64 — hero status badge

```diff
-          <div class="status-line"><span class="status-dot"></span> Status: architecture baseline and Python scaffold</div>
+          <div class="status-line"><span class="status-dot"></span> Status: simulator-first PoC through its acceptance gate</div>
```

### 3.2 Line 315 — Working now (kept claims unchanged; the dependency story inserted)

```diff
-        <p><strong>Working now.</strong> The simulator-first PoC is through its acceptance gate: durable run and lease state with kill-recovery, procedure admission and protection, 20 REST routes and 17 MCP tools on one core-operations seam, and an operator CLI. The SDK scaffolds an independent plugin project and release CI builds one outside the checkout and drives it through the gateway on mock transport. The DPS-150 plugin — hand-written, zero runtime dependencies — has driven the real supply; it is read-only and claims no PSU profile yet.</p>
+        <p><strong>Working now.</strong> The simulator-first PoC is through its acceptance gate: durable run and lease state with kill-recovery, procedure admission and protection, 20 REST routes and 17 MCP tools on one core-operations seam, and an operator CLI. Standards now behave like dependencies: plugins pin the standard versions they admit against, admission checks those pins, and a resolver lists, pins, upgrades and explains what a pin resolves to. Released versions serve side by side, development heads pin by name, and every promotion from a head to a released version is recorded. The SDK scaffolds an independent plugin project and release CI builds one outside the checkout and drives it through the gateway on mock transport. The DPS-150 plugin — hand-written, zero runtime dependencies — has driven the real supply; it is read-only and claims no PSU profile yet.</p>
```

### 3.3 Line 316 — Next (bridge claim corrected to remaining-scope; UI claim replaced by the
ruled direction; registry sentence kept **verbatim** — it is cited)

```diff
-        <p><strong>Next.</strong> Gateway and devices talking through the registry: the gateway side of the registry contract is done (signed catalogue, admission with a content-addressed cache, activation, an unsigned dev loop) but the registry service and a device-install command do not exist, and the OTDP bridge carries identify and scalar read/write only. Then a basic operator UI on the component library that exists today. Hardware qualification and unattended bench operation remain separate, commissioned work.</p>
+        <p><strong>Next.</strong> Gateway and devices talking through the registry: the gateway side of the registry contract is done (signed catalogue, admission with a content-addressed cache, activation, an unsigned dev loop) but the registry service and a device-install command do not exist. The OTDP bridge's remaining scope is dataset publishing and lookup, and profile scheduling on a native async host. The gateway's first operator web UI will be server-rendered, with the React reference renderer retired in a gated cutover. Hardware qualification and unattended bench operation remain separate, commissioned work.</p>
```

### 3.4 Line 389 — CLI-reference card (list completed to the real tree)

```diff
-        <a class="doc-card" href="docs/reference/cli/"><h3>CLI reference</h3><p>The <code>benchweave</code> command tree — <code>setup</code>, <code>serve</code>, <code>status</code>, <code>verify</code>, <code>demo</code>, <code>report</code>, <code>backup</code>, <code>restore</code>, <code>evidence</code> — generated from <code>--help</code>.</p></a>
+        <a class="doc-card" href="docs/reference/cli/"><h3>CLI reference</h3><p>The <code>benchweave</code> command tree — <code>setup</code>, <code>serve</code>, <code>status</code>, <code>verify</code>, <code>demo</code>, <code>report</code>, <code>evidence</code>, <code>retention</code>, <code>dispose</code>, <code>backup</code>, <code>restore</code> — generated from <code>--help</code>.</p></a>
```

### 3.5 Evidence map — every claim in the shipped lines and its source

Working now (W):

| Row | Claim | Source |
|---|---|---|
| W1 | PoC through its acceptance gate | WP09 complete (delivery plan WP09; `tests/integration/test_poc_acceptance.py`); PRD §7 stage exit gates |
| W2 | Durable run/lease state with kill-recovery | `src/benchweave/state/` store + `tests/faults/` recovery battery |
| W3 | Procedure admission and protection | `src/benchweave/control/` admission/executor/safe-transition; A03/A12 |
| W4 | 20 REST routes, 17 MCP tools, one seam | `standards/interface/0.1.0/openapi.json` = 20 paths (20 method-routes); `operation-catalog.json` = 20 operations; `mcp-tools.json` = 17 tools (3 admin ops have no MCP twin); A13 |
| W5 | Operator CLI | `benchweave --help`: 11 commands |
| W6 | Plugins pin the standard versions they admit against; admission checks those pins | `plugins/fnirsi/dps150/contracts/{constraints.json,lock.json}` (range + pin); per-pin gateway admission (#217 / PR #245) |
| W7 | Resolver lists, pins, upgrades, explains | `python -m benchweave.standards` family `list/pin/upgrade/why` (#216 / PR #234–#236 lane; on-site table in `docs/operator-guide.md` — the generated CLI reference gap is #291, cited not re-filed) |
| W8 | Released versions serve side by side | Multi-version serving (#215 / PR #234); preview 0.1.1 + 0.2.0 both served today (register §2 point 4) |
| W9 | Development heads pin by name | Dev-head pins (#218 / PR #252): content-addressed, `dev_head_unresolvable:` by name |
| W10 | Every promotion from a head to a released version is recorded | Promotion records (#218 / PR #252): three gates + D4 squash-landing property |
| W11 | SDK scaffolds an independent plugin project | `benchweave-sdk new` (scaffold.py); `scripts/sdk_smoke.py` builds wheel-installed external projects |
| W12 | Release CI builds one outside the checkout and drives it through the gateway on mock transport | `.github/workflows/package.yml:50` runs `scripts/sdk_smoke.py` ("Build sdists and wheels; test installed SDK and external adapter"; MockHost drive; gateway/SDK validator agreement asserted) |
| W13 | DPS-150: hand-written, zero runtime deps, driven the real supply, read-only, no PSU profile | `pyproject.toml` `dependencies = []`; `docs/devices/dps150/compatibility-record.md` (live-verified captures); descriptor: "read-only … no DC PSU profile or hardware qualification" |

Next (N):

| Row | Claim | Source |
|---|---|---|
| N1 | Registry gateway side done (signed catalogue, content-addressed cache admission, activation, unsigned dev loop) | `src/benchweave/registry/{authenticity,admission,activation,resolver}.py`; `dev-unsigned` signature policy (`resolver.py:125-144`); corroborated by `docs/device-developer-guide.md:15` |
| N2 | "the registry service and a device-install command do not exist" — **kept verbatim**; load-bearing citation | TRUE (no service; no install command in the CLI tree); cited by `docs/implementation-planning/10-contributor-publishing-design.md:19`; the publishing path is tracked as #209 → #223–#228 |
| N3 | Bridge remaining scope: dataset publishing and lookup | `otdp_bridge.py:340-353` dispatch table has no dataset verbs; docstring "Dataset publishing/lookup … still need the dataset-services slice" |
| N4 | …and profile scheduling on a native async host | Docstring "profile scheduling still needs a native async host"; #159 open |
| N5 | First operator web UI will be server-rendered | PRD 12 (#295), ruled 2026-10-01: "server-rendered HTMX renderer"; G-slices #297–#305 open |
| N6 | React reference renderer retired in a gated cutover | PRD 12: "retires React as the reference renderer in one gated cutover"; G1e #301 |
| N7 | Hardware qualification and unattended bench operation remain separate, commissioned work | A02 (commissioned per bench, never assumed); tracked shape now #316 (endurance authorization) + #307 (lease ruling) |

Hero (H1): "simulator-first PoC through its acceptance gate" — same source as W1.
CLI card (C1): 11 commands — `benchweave --help`.

**Acceptance census N = 23 claim rows** (W1–W13, N1–N7, H1, C1).

Two wording notes, disclosed: (a) W12 keeps the site's existing "through the gateway on mock
transport" phrasing — the smoke drives the external adapter over the gateway's host interface
via `MockHost` and asserts gateway/SDK validator agreement; substantively true, and the
sentence's job is "not on real hardware". (b) N2's "device-install command" has no tracker
issue by that name — the gap is real and documented (`docs/device-developer-guide.md:15,17`,
`docs/develop-your-device.md:197`) and the registry arc's design treats it as the discovery
gap; the phrase is kept because it is TRUE and cited.

---

## 4. The D4 scope question — disposition: **closure stands; nothing to build**

The issue frames two options: (a) fold a served-set/range line into this update (new derived
stamps + assembly stamping + test rows + CON-13 extension), or (b) re-defer with a recorded
disposition. The record found a third state: **D4 is already CLOSED**, not deferred. The
#233 register (`.claude/deep-review/2026-09-29-issue233-register-design.md` §2, "D4 — website
range/served-set stamps · CLOSE at PR #275's landing, evidence pre-committed here") closed it
on six structural points: (1) every version claim on the site is a token derived from the
manifest — the site claims no ranges or served sets anywhere; (2) coverage is bidirectional
and fail-closed; (3) stamped deep links are verified in CI assembly; (4) multi-serving stages
automatically; (5) the ranges' real consumer is the machine-rendered, CI-gated compatibility
matrix (CON-12); (6) the demonstrated control — PR #275 (the plugin-ui 0.3.0 / preview 0.2.0
range move, containing `b9ea484`, the exact range change the issue's reopen trigger names)
touched **zero website bytes** and its Build Docs lane was green.

### 4.1 What the trigger firing means here

The trigger ("the first range change after slice 1 lands") was not a promise to do work; it
was the **test of the closure's premise**. It fired, and the premise held: the first real
range change flowed through the website machinery in CI with no website work. Re-opening D4
now — option (a) — would add the one shape the closure identified as drift-capable (a
range/served-set claim site on a surface whose only mechanical pin is version-derived),
require a CON-13 amendment (invariant motion → standards-governor), new assembly derivation,
test rows, and a drift row-18 update, to duplicate on the site what the compatibility matrix
already publishes from the same authorities. No new evidence supports it. **Rejected.**

### 4.2 What this increment actually adds (and why it is not a D4 reopen)

The proposed W8–W10 prose describes the dependency-management **capability** ("released
versions serve side by side, development heads pin by name, promotions recorded") with **no
range values and no served-set membership**. A range change is not an input these claims
consume — they cannot drift on a bump, only if the capability itself is removed (the ordinary
aging of hand-written claims, review-caught under G4, the same disclosed class as CON-13's
deferral-5 two-component claims). Verified on the proposed text: no three-component literal,
no version enumeration, no served-set membership claim. **The website remains a version-only
consumer after this change.**

### 4.3 Owner fork flagged (not decided silently)

If the owner reads D4's "served-set claim site" as covering capability prose about serving,
the conservative alternative is to cut the clause "Released versions serve side by side,
development heads pin by name" — the sentence survives without it (W6/W7/W10 carry the
dependency story alone). **Default: keep.** Second micro-fork: if the owner wants served-set
*visibility* on the site (e.g. "the corpus serves N versions of each standard"), that is a
deliberate D4 reopen with a named new claim site and its own Tier-3 mechanism increment —
out of scope here either way.

---

## 5. Mechanism needs: NONE

- No new tokens, assembly changes, or test rows. The existing pins' scope is positional, not
  content-based: the literal ban sweeps the whole class-11 set (`website/**` + `index.qmd`),
  the token coverage is bidirectional over the file, and the assembly residue guard sweeps
  every copied file for `{{` — the new prose is covered by all three with zero changes.
- The proposed text was **run through the real scanners** (scratch copy, 2026-10-01,
  base `33b4c55`): literal ban = zero hits; stray-brace scan = zero; token set byte-identical
  (14 occurrences, unchanged); T4 spec-card agreement green; line count 471 -> 471; the
  pristine-tree baseline suite green at **19 tests / 0 failures / 0 errors** (junitxml —
  never the filtered summary line).
- **Control that fluff cannot pass** (the RED demonstration for "the pin covers the new
  text"): on a scratch copy, plant `9.9.9` inside the new Working-now sentence —
  `tests/contract/test_website_stamps.py::test_source_carries_no_version_literals` must fail
  naming it; remove it, green. This is a demonstration on a copy, not a committed change
  (prose-only edits skip behavior-test additions per the increment doctrine).
- CI cost: zero new lanes. The existing Build Docs lane is the rendered-page verifier.

---

## 6. Review tier + Step-1 keyword scan (design-time call, #254)

**Tier: 3.** Path-rule-alone would say Tier 1 (web copy only — nothing under `src/`,
`scripts/`, `tests/`, `ui/`, `.github/`, root config, or `standards/`). The keyword rule
fires first (first-match wins): the expected diff text carries `recovery` and `protection`
because the rewritten Working-now paragraph **keeps** the true claims "kill-recovery" and
"procedure admission and protection" in both its − and + lines. The rubric's interplay clause
is explicit that docs-only diffs carrying a protection-related key take the Tier-3 lane; this
record takes that as intended — the site's protective claims deserve the depth.

**Scan** (run over the exact expected diff text — the four changed lines, − and + alike, as
constructed in §3; counts are of case-sensitive substring occurrences):

| Keyword | Count | Keyword | Count |
|---|---|---|---|
| `recovery` | **2** | `sha256` | 0 |
| `protection` | **2** | `hashlib` | 0 |
| `threading` | 0 | `migrate` | 0 |
| `asyncio` | 0 | `subprocess` | 0 |

("native async host" does not contain `asyncio`; verified by the scan run.) Scope note: the
scan covers the expected **implementation** diff. This design record, committed as commit 1
of the branch, quotes the same claims by design and would add counts if scanned itself; the
tier is 3 under either scope, so the call is scanner-independent. The review re-derives
independently per #254.

**Standards-governor mandate (#69): does not fire** — the diff touches no `standards/` bytes,
no plugin contract locks, no SDK vendored tree, and no standard-version strings (the prose is
token-free and literal-free by construction). The standing tripwire still runs and is
reported at push: `git diff origin/main...HEAD -- standards/` is empty, and no
version-string touches.

---

## 7. Pre-committed acceptance rule

Written before any review pass or measurement ran. This increment has no statistical effect
to measure; the honest metric is claim accuracy with zero tolerance, plus the existing
machine pins.

- **Metric**: unreconciled-claim count — shipped claim rows (§3.5's census, N = 23) that
  cannot be tied to their named source, or whose source contradicts them, at review time.
- **Sample size**: N = 23 rows (the full census of claims in the four shipped lines; the
  wider 20-row site census in §2 documents the untouched rows).
- **Effect size**: zero tolerance — 23/23 must reconcile. A claim whose source cannot be
  opened or checked is NOT reconciled.
- **SHIP direction** (all must hold):
  1. 23/23 census rows reconcile (the reviewer re-derives independently; each row's source
     named in §3.5).
  2. `tests/contract/test_website_stamps.py` green on the new text (includes the literal ban
     and token coverage); planted-literal control demonstrated per §5.
  3. Assembly verification clean (Build Docs lane, or local `assemble_docs_site.py --dest`):
     no stamp residue, all `docs/…` links resolve.
  4. Rendered-page check: the assembled (or live, post-merge) page contains the new
     "Standards now behave like dependencies" sentence with tokens resolved — fetch
     verification suffices (the section is static text; no new interactivity to exercise).
  5. Line count of `website/index.html` unchanged (the `:316` and `:330-357` citations in two
     committed records keep resolving).
  6. Standards tripwire reported empty.
- **KILL direction** (any one kills): a shipped claim without a reconciling source (kill —
  cut or reword before landing, never land an unverifiable claim); a three-component literal
  in the class-11 set (CON-13 red); the rendered page missing or differing from the source
  text; any `standards/` motion in the diff; a line-count change in `website/index.html`.
- **UNDERPOWERED (not conclusive)**: if a row's source cannot be opened at review time
  (tracker unreachable, file moved), the row is UNVERIFIABLE → the claim is **cut**, and the
  result recorded as "measurement underpowered" — the honest-negative rule: cut beats assert.
  Under no reading is an unopenable source treated as confirmation.

---

## 8. Invariant, drift and surface impacts

- **No invariant changes or amendments.** CON-13 and CON-12 are exercised, not touched. No
  CTL/STO/CON/REG motion.
- **No on-disk format or schema** — Tier 3 by keyword only, not by persisted-format rule.
- **Version-bearing surfaces**: no new version-bearing claim site (no literals, no new
  tokens); drift row 18's inventory is unchanged. The two-component claim "Python 3.13+"
  (deferral 5 class) is untouched.
- **Cross-surface effects, disclosed**:
  - `docs/implementation-planning/10-contributor-publishing-design.md:19` cites
    `website/index.html:316` quoting "the registry service and a device-install command do
    not exist" — the sentence is kept **verbatim** and the line count preserved, so the
    citation resolves and its quote remains accurate. (Had the reword been heavier, that
    live planning doc would need a rider — avoided by design.)
  - After this lands, the site no longer asserts a bridge verb list, so it does **not**
    contradict the two still-stale surfaces (§1's table) — deliberately. The contradiction
    those two surfaces carry against the code is pre-existing and carried by §9.1/§9.2.
  - `docs/device-developer-guide.md:15`'s "a Python scaffold" era-phrase now differs from the
    hero badge; that guide line rides with §9.1's sub-issue.
- **SDK repo**: untouched. **Operator docs / device-developer guide**: untouched here (§9.1).
  **MCP tools / REST / openapi**: untouched. **Fixture lattice**: untouched.
- **CI cost**: none beyond existing lanes; the fast lane runs per commit (docs-only commits
  included, #247 doctrine), the full battery once before push.

---

## 9. Deferrals (file as sub-issues of #317) and DON'T-BUILD rows

### 9.1 D-A — device-developer-guide stale bridge/status claims (DEFER → sub-issue)
`docs/device-developer-guide.md:17` claims the bridge supports "identify, scalar read and
scalar write" and that "capture/streaming … are not provided by this bridge" — falsified by
`otdp_bridge.py:340-353` (capture landed `7a12d3d` 2026-09-22, invoke `f5cddf1` 2026-09-26).
`:15`'s "a Python scaffold" era-phrase rides along. **Carrier**: the guide's status lines.
**Reopen trigger**: the next edit to `docs/device-developer-guide.md` on any lane, or the
next change to the bridge's supported-verb set — whichever fires first. **Why deferred**: the
issue's scope is the website; the guide is a separate surface with its own review lane, and
bundling it would break the one-surface-per-increment shape.

### 9.2 D-B — plugin-ui 0.3.0 released prose understates the bridge (DEFER → sub-issue)
`standards/plugin-ui/0.3.0/README.md` ("Ownership and execution"): "The current adapter
bridge supports identify and scalar read/write." Stale in **digest-frozen released bytes** —
fixing requires a governed version bump (copy-never-move) or a coordinator errata ruling, not
an in-place edit. **Carrier**: the next plugin-ui standards train (or the standards
coordinator's errata call). **Reopen trigger**: the next plugin-ui corpus train opening.

### 9.3 D-C — the hand-written bridge-verb list drift pattern (DEFER → sub-issue)
The defect pattern of §1: one verb-set, three prose surfaces, zero pins to the dispatch
table that regenerates it — G4's "a set named in prose is regenerable from a mechanism"
violated three times in four days. Candidate cures (not decided here): a drift-obligation row
naming the three prose sites with the dispatch table as authority, or a generated scope line.
**Carrier**: `docs/internal/drift-and-obligations.md` (a future mechanism increment).
**Reopen trigger**: the next change to `OTDPBridge`'s supported-verb set — the exact event
this pattern has already missed twice.

### 9.4 DON'T-BUILD rows (optional refinements, deliberately not taken)
- `:303` tense polish ("The first PoC **is** simulator-first" → "was") — true either way; not
  worth diff noise.
- plugin-ui spec-card description ("bindings, presets and envelopes") could name 0.3.0's
  plots/panels — mild understatement, not false; the badge already carries the version.
- Adding the Textual TUI to "an operator CLI" — true but marginal; the CLI claim stands.
- Count-bearing stamps (operations/tools) for "20 REST routes / 17 MCP tools" — correct today
  against interface 0.1.0's corpus; a count-stamp mechanism is a D4-class extension rejected
  in §4. The counts are re-checked at the next interface bump by review.

### 9.5 Cited, not re-filed
#291 (generated CLI reference cannot see the `benchweave.standards` family) already carries
the resolver-verbs discoverability gap; the operator guide's on-site table (landed with the
#288 fold) is the on-site source backing W7.

---

## 10. Top risks, each with its falsifier

- **R1 — The new prose ages the same way.** Hand-written claims have no mechanical pin; W4's
  counts and N5/N6's plan claims are the most perishable. *Falsifier*: the next interface or
  PRD-12 ruling change; the census table + §7 rule make the re-check mechanical, and D-C
  carries the pattern cure for the worst offender. Standing residual, disclosed.
- **R2 — The builder violates the line-count constraint** (inserts lines, breaking the `:316`
  and `:330-357` citations in committed records). *Falsifier*: `git diff --stat` showing a
  line-count change in `website/index.html`; acceptance rule §7.5 refuses it.
- **R3 — A reviewer reads the tier call as inflated.** The record states Tier 3 with the
  keyword counts and the counterfactual; if the review's scanner scopes differently the tier
  is still 3 under the implementation diff alone (the keywords sit in the changed lines), so
  the call is scanner-independent.
- **R4 — The dependency-story prose overstates what shipped.** Three of seven #203 slices
  remained after #218; W6–W10 name only capabilities that merged (each row's PR cited).
  *Falsifier*: any W-row whose cited PR/issue does not carry the capability — kill row, cut
  claim.
- **R5 — The kept registry sentence ("device-install command") is read as a commitment with
  no tracker.** It is a TRUE gap statement (no such command exists) kept verbatim for a
  citation; §3.5's note discloses that its carrier is the registry arc's design, not an issue
  by that name. If the owner prefers, a rider on #209 naming install-on-bench closes the
  naming gap — flagged, not blocking.

---

## 11. What this record does not do

No production code, no standards bytes, no tests, no mechanism. The build agent's slice is
exactly §3's four line rewrites on `feat/issue317-website-status` (this record as commit 1,
the prose edit as commit 2 with the fast lane per commit and the full battery before push),
the three deferral sub-issues of §9.1–9.3 filed on this tracker, and the §4.3 forks surfaced
to the owner before or at review — the §4.3 default (keep the capability clause) applies
unless the owner says otherwise.
