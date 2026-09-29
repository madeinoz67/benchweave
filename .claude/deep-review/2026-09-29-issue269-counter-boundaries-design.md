# Issue #269 — Slice 7 follow-on: the Counter's Named Boundaries — AST Assembly Detection, scripts/ Scope, Flat-Plugin and venv-Name Scope Rules — Design Record

**Status:** Design (builder-ready) · **Tracking issue:** madeinoz67/benchweave#269 (the #221/#203-slice-7 follow-on, all three rows opened by the owner's call) ·
**Parent design:** `.claude/deep-review/2026-09-28-issue221-zero-literal-design.md` (§1.3 the scopes/register, §3 the deferral discipline, §5 the G-arms this record's H-arms extend) ·
**Evidence baseline:** gateway `origin/main` at `8a2cca1` (post-#270/#271; the #221 zero-literal gate and its fold wave `68e2f3c` live) · SDK pinned at gitlink `d698b44` (measured via `git show` at the pin — the standalone SDK checkout sits on a sibling lane's branch; never read it working-tree). The #260 build is live in `.wt/` worktrees; nothing there was read.

---

## 0. Premises verified — and two corrected by measurement

1. **The 12-shape evasion battery is reconstructible and arithmetically consistent with the
   recorded evidence.** The fold commit (`68e2f3c`, row 7) and issue #269 record "9 of 12
   adversarial shapes pass" but the original enumeration was session artifact, never
   committed. I rebuilt a 12-shape battery from the docstring's named classes (concat,
   concat-chain, f-string-from-ints, f-string-mixed, `%`-tuple, `%`-single, bytes+decode,
   join-fragments, join-path, chr-assembly, `.format`, plain-constant control) and ran it
   against the live counter in a scratch tree: **exactly 3 of 12 are caught today** — the
   three shapes that leave a complete string `Constant` in the AST (`"execution/%s" %
   "0.2.0"`, `"/".join(["execution", "0.2.0"])`, and the plain constant) — and **9 pass**,
   matching the recorded 9/12. The battery is committed by this design as the spec
   (acceptance H1); the reconstruction's honesty rests on the arithmetic match, stated
   here rather than invented provenance.
2. **The scripts/ scope is a 23-site disposition, not a two-pin derivation.** Issue #269
   (written by the fold) names only `adc_conformance_control.py`'s `YANKED_PIN`/`MOVE_TO`
   because obligation 20 names only those as live OTDP literals. Measured with the
   counter's own committed definition over `scripts/**/*.py` (minus the counter itself) at
   `8a2cca1`: **23 sites across 8 files** — the two adc pins, one Pattern-A active-corpus
   path in `assemble_docs_site.py:527`, and 20 authored fixture/self-test values
   (`architecture/check_closure.py` ×4, `check_devices.py` ×1, `check_interface.py` ×1,
   `registry/build_fixtures.py` ×4, `registry/publish_dev.py` ×1,
   `registry/registry_common.py` ×7, `sdk_smoke.py` ×2). The ledger and dispositions are
   §2. The issue's framing understated the row; this record corrects it the way the slice-7
   record corrected the SDK hand counts.
3. **The stray dps150 venv is GONE from main.** `plugins/fnirsi/dps150/venv/` (14 sites,
   19 files at the slice-7 measurement base `6582651`) does not exist at `8a2cca1` — and it
   never carried `pyvenv.cfg` in git anyway (it was a committed partial venv). Row 3's
   venv-name half is therefore about the RULE, not current bytes: no environment directory
   exists in any gated tree today, so the marker-rule redesign changes no current census.
4. **The flat-plugin gap is real but vacant.** Widening the plugins rule to "any `.py`
   outside `tests/` and environment components" admits exactly two files today
   (`plugins/fnirsi/dps150/scripts/demo.py`, `fetch_contracts.py`) — both carry zero
   literals under both the textual and the fold definition. Census 13 → 15, zero register
   motion.
5. **MOVE_TO is structurally the manifest's active entry.** The warning's move-to is
   `_move_to` = "highest served (¬yanked) version ≥ the pin" (`served.py:144-160`), and a
   yanked pin is by design in-interval and ≤ active (`manifest.py:56-67`, YankRecord's own
   docstring) — so move-to == the active version whenever the policy shape holds. This
   lets the adc control DERIVE both pins as direct policy reads (the unique yanked entry;
   the active entry) with no re-implementation of the served-set rule. The theorem's
   failure mode is a loud control failure (§2.1), which is the redesign trigger, not a
   silent wrong assertion.
6. **`scripts/` is not stdlib-only today.** `assemble_docs_site.py:69` already imports
   `from benchweave.standards.manifest import load_manifest, load_sdk_compatibility` — so
   its derivation rides the proven loaders directly. Only the adc control is stdlib-only
   BY DESIGN (clean-venv control), and its derivation is a direct JSON read of the
   committed policy block (§2.1).

## 1. Row 1 — the AST assembly pass (constant-folding, both counters)

### 1.1 The mechanism

A conservative **constant-folding evaluator** over the already-parsed AST, added to
`count_sites` in both counters. For every expression node of a foldable kind that is not
itself a plain `Constant`, attempt to evaluate it from literals only; if the folded value
is a `str` matching `PATTERN_A` or `PATTERN_BARE`, emit a site with pattern `ASM-A` /
`ASM-BARE`. The two existing patterns are UNCHANGED — the fold pass feeds the same
matchers; it widens what reaches them, not what they mean.

The foldable kinds (the allowlist — everything else is unfoldable, no guess):

- `ast.JoinedStr` (f-string): each `Constant` part verbatim; each `FormattedValue` with no
  conversion and no format-spec folds its inner expression and stringifies (`int` →
  `"2"`).
- `ast.BinOp`: `Add` on two folded `str`; `Mult` (`str`×`int`, `int`×`str`, Python's own
  semantics — closes repetition composition); `Mod` with a folded `str` left side — the
  operation is APPLIED with Python's own `%` on the folded operands, never re-implemented.
- `ast.Call`:
  - attribute calls on folded constants: `sep.join(seq)` where `sep` folds to `str` and
    `seq` folds to a `list`/`tuple` of `str` (literal `ast.List`/`ast.Tuple` elts only —
    comprehensions and generators are unfoldable); `fmt.format(*folded_args)` (Python's
    own `str.format`, kwargs unfoldable → skip); `b"...".decode()` with no args.
  - name calls `chr(i)` / `str(x)` on foldable arguments — ONLY when the module does not
    shadow the name (a prepass collects module-level defs/assignments/imports of `chr`/
    `str`; shadowed ⇒ unfoldable — a local `def chr` must not be folded as the builtin).
- `ast.List` folds to `list`, **`ast.Tuple` folds to `tuple`** — load-bearing: `%` accepts
  only a real tuple, so folding tuples to lists silently unfolds every `%`-tuple shape
  (shape S5 — found by the design-time probe, §1.3).

Every fold attempt runs under `try/except Exception` ⇒ any raise (bad format, wrong types,
`chr` out of range) is **unfoldable, never an error**: the evaluator's failures are honest
misses, not gate failures. Bounds: fold depth ≤ 24, folded-string length ≤ 4096 —
pathological inputs unfold. No `eval`, no execution: the evaluator applies Python's own
string operations to already-folded constant values and nothing else.

**Dedup:** a folded match nested inside another folded match (by `lineno/col_offset/
end_lineno/end_col_offset` containment) is dropped — the OUTER assembled expression is the
reported site. Inner plain `Constant` fragments that independently match (the join-path
shape's `"0.2.0"` element) still report as ordinary `A`/`BARE` sites via the existing
textual walk — a shape can contribute both; both are honest sites in the same file.

**Scoping:** the fold pass runs over EXACTLY the existing executable scopes — gateway,
plugins, sdk, and the new scripts scope (§2) — the same denominator as the textual pass.
`tests/` (fixture literals are legitimate test data; assembly there equally so) and the
docs prose scope stay outside, by the existing named boundary. The register machinery is
UNCHANGED: assembly sites are ordinary sites; a registered file's `expected_sites` counts
them; file-level rows with `expected_sites` + `expected_values` remain the only exemption
granularity (per-expression exemptions are new machinery — rejected; the file-level row is
the proven anti-laundering shape, and a new assembly literal in a registered file already
fails until the row is edited).

**The rewritten does-not-catch sentence (pre-committed, lands in both docstrings):** the
matcher folds CONSTANT-ONLY assembly — concatenation, f-strings, `%`-formatting,
`.format`, `str.join` over literal sequences, `chr`/`str` over literals, `bytes.decode`,
and string repetition — and refuses the folded result under the same two patterns.
Assembly with ANY non-literal input — a variable, parameter, function result,
comprehension, or a value read from data, environment, or configuration — remains
invisible: catching that needs taint tracking, still deliberately not attempted (the
follow-on row). `os.path.join` and other stdlib string constructors are outside the fold
allowlist (named residual, deferral D-3).

### 1.2 False-positive posture — measured, not assumed

A design-time probe implementing exactly §1.1 ran over the four trees at the evidence
baseline: **0 assembly hits in 93 gateway files, 15 plugins files (the widened scope),
18 SDK files at the pin, and 16 scripts files.** The gate lands with ZERO register
additions for assembly. The false-positive storm the row feared (error-message
construction, benign joins) does not exist at head — version-shaped strings assembled from
constants are already absent from the gated trees because slice 7 removed the literals
their assembly would have used.

### 1.3 The 12-shape battery (committed as the spec)

`tests/standards/assembly_shapes.py` (scratch-written by the test into a scratch tree,
same shape as the existing scratch arms) carries the twelve shapes of §0.1. Measured this
session with the live counter and the probe:

| # | Shape | Live counter today | With the fold pass |
|---|---|---|---|
| S1 | `"execution/0." + "2.0"` | passes | `ASM-A` |
| S2 | concat chain | passes | `ASM-A` |
| S3 | `f"0.{2}.{0}"` | passes | `ASM-BARE` |
| S4 | `f"execution/{0}.{2}.{0}"` | passes | `ASM-A` |
| S5 | `"0.%d.%d" % (2, 0)` | passes | `ASM-BARE` |
| S6 | `"execution/%s" % "0.2.0"` | caught (inner `BARE` constant) | both sites |
| S7 | `b"execution/0.2.0".decode()` | passes | `ASM-A` |
| S8 | `".".join(["0","2","0"])` | passes | `ASM-BARE` |
| S9 | `"/".join(["execution", "0.2.0"])` | caught (inner `BARE` constant) | both sites |
| S10 | `chr(48) + ".2.0"` | passes | `ASM-BARE` |
| S11 | `"{}/{}.{}.{}".format("execution",0,2,0)` | passes | `ASM-A` |
| S12 | plain `"0.2.0"` constant | caught (`BARE`) | unchanged |

Nine passing today matches the fold's recorded "9 of 12" exactly. The battery is
henceforth the committed spec for the class — the next evasion probe extends the file, not
a session's memory.

## 2. Row 2 — the scripts/ scope: three derivations, twenty registrations

### 2.1 The three derivable sites

**`scripts/adc_conformance_control.py` (2 sites) — DERIVE, both pins, direct policy reads.**
The pins are policy facts with a committed machine authority, not authored test data: the
yank policy block (`standards/standards-manifest.json` → `dependency_policy.standards.otdp`
.yanked — exactly one entry today: `0.2.1`) and the active entry (`.standards[]` id=otdp →
`0.2.2`; the move-to by §0.5's theorem). Registering them would leave a hand-swept copy of
a policy fact — the exact defect class this arc exists to remove (`88b64f1`, the recorded
sweep miss; VR-21's own "hand sweeps miss sites" line). Mechanism, stdlib-only (the control
must not depend on the checkout environment):

```python
def _otdp_policy_facts() -> tuple[str, str]:
    """(yanked_pin, move_to) from the committed policy block — the authority
    the built wheel's lock mirrors (make check-sdk-standards refuses drift)."""
    manifest = json.loads((REPO_ROOT / "standards" / "standards-manifest.json").read_text(encoding="utf-8"))
    entry = next((s for s in manifest["standards"] if s.get("id") == "otdp"), None)
    if entry is None:
        raise SystemExit("adc_policy_absent: no otdp entry in the standards manifest")
    policy = manifest["dependency_policy"]["standards"].get("otdp", {})
    yanked = sorted(policy.get("yanked", {}))
    if len(yanked) != 1:
        raise SystemExit(f"adc_yank_not_unique: the control's anti-gaming arm needs exactly "
                         f"one yanked otdp version, found {yanked}")
    return yanked[0], str(entry["version"])

YANKED_PIN, MOVE_TO = _otdp_policy_facts()   # replaces the two literals at :55-56
```

Use sites (`:223-226`, `:253-255`, `:267`) are unchanged — the names keep their values,
now derived. Refusal prefixes follow the script's existing `adc_control_failed:` discipline
(`adc_policy_absent:`, `adc_yank_not_unique:`). The anti-gaming arm then always plants the
CURRENT yanked version — the recorded motion mechanism ("both flip with the yank policy
block") becomes mechanical instead of remembered. Tautology boundary, named: the control
asserts OBSERVED warning content (from the built wheel + external plugin) against the
AUTHORITY read (the checkout manifest) — different objects; the residual is consistent
corruption of manifest AND lock together, which `make check-sdk-standards`'s sync lane owns.

**`scripts/assemble_docs_site.py:527` (1 Pattern-A site) — DERIVE via the proven loaders.**
The file list gains `f"standards/otdp/{active_version_from_corpus(corpus_root(), 'otdp')}/otdp-runtime.schema.json"`
(one import addition beside the existing `load_manifest` import at `:69`). The site should
render the ACTIVE runtime schema — that is what the derivation means; a future otdp bump
moves the copied file with the manifest, no sweep. The runtime call is unfoldable to the
counter (a function call, not a literal) — no literal, no assembly site.

### 2.2 The twenty authored sites — REGISTER with value pins

All twenty are fixture or self-test data — the same register semantics as the SDK
`scaffold.py` row ("authored example-template fields that are not standards references")
and the dps150 descriptor row. Rows (file → expected_sites, expected_values):

| File | n | values | the authored data |
|---|---|---|---|
| `scripts/architecture/check_closure.py` | 4 | `1.0.0`×4 | the synthetic closure-graph fixture versions |
| `scripts/architecture/check_devices.py` | 1 | `2.0.0` | the synthetic identity-disagreement probe |
| `scripts/architecture/check_interface.py` | 1 | `0.1.0` | synthetic clientInfo version in a self-test payload |
| `scripts/registry/build_fixtures.py` | 4 | `1.0.0`×4 | the fixture packages' release version + dir names |
| `scripts/registry/publish_dev.py` | 1 | `0.0.0` | the dev-iteration default sentinel |
| `scripts/registry/registry_common.py` | 7 | `0.1.0`×2, `0.1.1`×2, `1.0.0`×3 | fixture document formats, compat lists, package version |
| `scripts/sdk_smoke.py` | 2 | `1.0.0`×2 | synthetic descriptor firmware (the scaffold row's own class) |

Deeper derivation of the fixture document-format fields (`manifest_version`/`status_version`
from the registry schema consts — the proven `lock_version()` pattern) is deferral D-2:
it changes emitted fixture bytes on every bump and the lattice's motion is already governed
by its rebuild flow; registering with value pins makes drift loud today at minimal cost.

### 2.3 The scope itself

- `ALL_SCOPES` gains `scripts`; `--scope all` covers five scopes. `scope_tree("scripts")`
  = `("scripts/**/*.py", repo root)` with the environment filter applied.
- **The counter exempts ITSELF by a named constant** —
  `SCRIPTS_EXCLUDED_FILES = ("scripts/standards/count_version_literals.py",)` with the
  reason beside it: the register's `expected_values` tuples ARE the gate's own data and
  are literals by construction (the same class as the docs snapshot JSON, which no AST
  scope scans). The twin's file is likewise self-exempted in the SDK repo. Line-scoped
  exemption was rejected — new machinery for a file whose every edit is already an
  editorial re-baseline by the docstring's own rule.
- Census: **16 files scanned** (17 `.py` minus the self-exempted counter), pinned exactly
  in the census test.
- CI: no new lanes. The pytest module runs the scripts scope explicitly; `make
  check-sdk-standards` (`--scope sdk`) and the device-plugins step (`--scope
  plugins,docs`) are unchanged — scripts is the `gates` lane's subject. The submodule-
  absent local invocation becomes `--scope gateway,plugins,docs,scripts`.

## 3. Row 3 — the two scope-membership rules

### 3.1 Flat plugins: drop the src/ requirement, keep the two exclusions

The plugins membership rule (`_in_scope`, currently `"src" in parts and "tests" not in
parts` at `count_version_literals.py:260-266`) becomes: **any `.py` under `plugins/` with
no `tests/` component and no environment component.** A plugin's code is gated wherever it
lays out its package; the fold's row-8 finding (a `tests/src/` shape is a test tree however
laid out) keeps the `tests/` exclusion unchanged. Measured effect at head: 13 → **15 files**
(the two dps150 script files), zero new sites. The twin has no plugins scope — no motion
there. Residual, named: a plugin shipping a `tests` subpackage inside its distributed
package tree is excluded — same residual as today, unchanged by this row.

### 3.2 Environments by marker, not by name

`ENVIRONMENT_COMPONENTS` (the name set `venv/.venv/node_modules/site-packages`, applied at
`:244-246` and in the twin at `:153`) is replaced by a marker rule with a named name-
residual:

- A directory is a **Python environment iff it contains `pyvenv.cfg`** (the marker every
  `venv`/`virtualenv`/`uv venv` writes). Project code in a directory merely NAMED `venv`
  or `.venv` is now SCANNED — the collision case the row names, closed.
- `node_modules` and `site-packages` stay name-based: no marker file exists for either,
  and the names are convention-owned by npm and pip's layout — a real package so named is
  unrepresentable in practice. **Named residual**, not a silent one.
- Implementation: a memoized per-directory predicate (one `stat` per directory under a
  scan root, cached) replacing the free string-set test. Cost at current scale: negligible
  (tens of directories; the probe walk over all trees is sub-second). The census pins
  catch any accidental scope change.

Measured effect at head: none — no environment directory exists in any gated tree (§0.3),
so every census is unchanged. The rule is dormant-but-honest: it binds the day an
environment reappears. Direction of failure stays loud: an environment whose marker was
deleted scans as third-party bytes and its literals FAIL the gate (disposition = a named
path exclusion) — never a silent pass.

## 4. Twin parity — structural this time (a digest-pinned shared region)

Investigated and rejected: riding the counter definition on the vendored standards tree
(`src/benchweave_sdk/standards/`) — a category error that would make governance tooling
into corpus bytes, its motion gated by standards bumps (the wrong axis entirely); and
cross-repo imports — the SDK repo does not contain the gateway, and the gateway counter
must run in submodule-absent worktrees for the non-sdk scopes.

The structural answer extends the PROVEN mechanism — the twin-identity digest pin
(`tests/sdk/test_presentation_packaging.py:70-75`, byte-pinning the two `contracts.py`
copies): both counters gain explicit region markers around their shared definition
(`STANDARD_IDS`, `PATTERN_A`, `PATTERN_BARE`, the environment predicate, `_docstring_ids`,
the fold evaluator and its helper — all pure stdlib, free-standing), and a gateway-side
test (skipping when the submodule is absent, the sdk-scope's own condition) asserts the
two marked regions are BYTE-IDENTICAL. The non-shared machinery (the gateway's scopes/
docs-ratchet register dict vs the twin's flat register; `_pin_standard_ids` manifest-vs-
lock) stays outside the markers. SDK-side definition drift then fails gateway CI at the
next pointer bump — the A6 cadence the two-sided posture already accepts — instead of
relying on the obligation-22 doc row alone (which stays, for the human-level sync duty).
RED at base: the markers do not exist, so the parity test fails with marker-absent — that
is its RED.

## 5. Minimal first-increment scope and deferrals

**In scope (three commits on one gateway branch + the SDK twin PR, RED-first per row):**
the fold evaluator + battery + does-not-catch rewrite in BOTH counters (commit 1); the
scripts scope + three derivations + seven register rows + census pins (commit 2); the two
membership rules + census updates 13→15 + the shared-region markers and parity test
(commit 3). Tests extend `tests/standards/test_zero_literal_gate.py` (+ the battery
module) and the SDK's `tests/test_zero_literal_gate.py`. Docs:
`docs/internal/drift-and-obligations.md` obligation 20 (the assembly/scripts/rule clauses
replace the "review-lane duty" sentence) and obligation 22 (the parity pin); the counter
docstrings. No standards/ bytes move in either repo (the derivations READ the manifest;
the tripwire `git diff origin/main...HEAD -- standards/` stays empty — the #203 hold
window is closed, the check still runs and is still reported). Two-repo shape per
AGENTS.md: SDK PR first (twin fold + rules + markers), then the gateway PR with the
pointer; the work is complete only when both merge.

**Deferrals** (each with a home and a reopen trigger):

| # | Deferred | Home | Reopen trigger |
|---|---|---|---|
| D-1 | Dynamic/runtime assembly (taint tracking: variables, parameters, function results, env/data reads, comprehensions) | The rewritten does-not-catch sentence + obligation 20 | A review catching a shipped dynamically-assembled literal, or the owner's call |
| D-2 | Fixture-field derivation in `scripts/registry/` (schema-const derivation of `manifest_version`/`status_version`, the `lock_version()` pattern) | §2.2's register rows | The next registry fixture rebuild arc, or the owner's call |
| D-3 | Wider fold allowlist (`os.path.join`, textwrap, `%`-dict, format-specs) | The does-not-catch sentence's residual list | A probe shape using one caught in review |
| D-4 | The SDK repo's own scripts/ scope (the twin gates `src/benchweave_sdk/` only) | The twin's denominator-boundary docstring | The next addition to the SDK repo's scripts/ |
| D-5 | node_modules/site-packages name-residual (no marker exists) | §3.2's named residual | A real collision reaching review |

## 6. Invariant, governance, and drift impacts

- **No new invariants.md row, no amendment.** The gate is obligation 20's domain, not a
  CON/CTL/STO/REG row; the counter's docstring carries its own definition-change rule.
  CON-1/2/4/8/9/10/12/14 untouched (no served-set, manifest, projection, matrix, or
  resolver change; nothing under `standards/` moves).
- **Obligation 20** gains: the assembly clause (constant-only assembly is CAUGHT; the
  does-not-catch class is dynamic-only now), the scripts scope (five gated trees; the
  denominator boundary shrinks to `tests/` and `.github/`), and the membership-rule
  clauses. **Obligation 22** gains the shared-region parity pin. **CI map**: the `gates`
  row's scope list grows `scripts`; `device-plugins` unchanged.
- **Surfaces that move:** `scripts/standards/count_version_literals.py`,
  `scripts/adc_conformance_control.py`, `scripts/assemble_docs_site.py`,
  `tests/standards/test_zero_literal_gate.py`, `tests/standards/assembly_shapes.py` (new),
  `docs/internal/drift-and-obligations.md`, this record; SDK repo:
  `scripts/count_version_literals.py`, `tests/test_zero_literal_gate.py`; the submodule
  pointer commit. MCP/REST/CLI/wire: nothing (no tool, endpoint, or CLI flag changes — the
  counter's `--scope` gains a value; the adc script's interface is unchanged).
- **On-disk formats/schemas: none.** The register lives in-script; the docs snapshot is
  untouched; no state, store, or migration surface.
- **CI cost:** no new lanes; the counter's runtime grows by the fold pass (sub-second at
  current scale — measured via the probe over all four trees); ~15-20 new focused test
  arms in two existing modules.

**Tier call (Step-1 rules + the #254 design-time keyword scan, run on the expected diff
text):** **Tier 3.** Path rules: the diff advances the `packages/sdk` submodule pointer
(explicit Tier-3 rule). Keyword scan over the expected added text (the three counter/
script files, the two test modules + battery file, the twin, the drift-doc clauses, this
record): `sha256` PRESENT (~4-6 — the parity test's `hashlib.sha256` calls and the
register/record prose citing digest pinning); `hashlib` PRESENT (~2-3 — the parity
test's import and calls); `subprocess` 0-2 (the new arms reuse the existing
`_scratch_run` helper; context bleed only — the tier does not hinge on it);
`threading`/`asyncio`/`migrate`/`recovery`/`protection` ABSENT from all added text (no
concurrency, migration, or protection surface is touched, and the prose avoids them).
First-match-wins ⇒ Tier 3; the mandatory second adversarial lane applies (standing
two-lane rule).
**Standards-governor: FIRES by clause four** ("standard-version strings"): the diff's
subject is the matcher over standard-version strings, and the scripts register rows + the
adc derivation carry literal standard-version values; the first three clauses do not fire
(no `standards/` corpus bytes, no plugin contract lock, the SDK vendored tree untouched).
Dispatch it — a governance review that never ran is a skipped gate.

## 7. Measurable proof — acceptance rule H (pre-committed, extending G's discipline)

**SHIP directions and KILL directions, fixed before any number is looked at post-build:**

- **H1 (the battery).** The committed 12-shape module in a scratch tree: the folded
  counter refuses the file, and every shape contributes at least one violation line (11
  `ASM-*` sites + the S12/S6/S9 textual sites). SHIP: 12/12 refused. KILL: any shape
  passing under the folded counter. **RED at base (mandatory, captured verbatim in the
  commit message): exactly 9 of the 12 pass against the live counter** — if the base run
  shows a different pass count, the battery fixture is wrong (the underpowered rule:
  fix the fixture before building, do not tune the mechanism to the fixture).
- **H2 (clean head + reproducibility).** All five scopes read `0 outside register` at the
  slice head; `--json` byte-identical across two consecutive runs per scope. SHIP: 5×0 +
  n=2 identical. KILL: any scope >0 (a real finding — disposition it, do not widen the
  register silently); any two runs differing (fix the script before trusting it — A4's
  discipline).
- **H3 (the scripts ledger).** The 23 sites are accounted: 3 derived (the literals absent
  at head — provable by the counter's own `--json` over the scripts scope), 20 registered
  in 7 rows whose `expected_sites` and `expected_values` hold exactly. Plant arm: `_PLANT
  = "9.9.9"` in a scratch copy of `scripts/sdk_smoke.py` refuses. Derivation arms: a
  scratch manifest with zero yanked entries ⇒ `adc_yank_not_unique:` non-zero exit; with
  the otdp entry removed ⇒ `adc_policy_absent:`; the docs-site derived path equals the
  real manifest's active otdp family (unit assertion against the committed manifest).
  SHIP: all arms green, RED at base for the plant (scripts unscanned today). KILL: any
  scripts site outside the register; any derivation arm passing at a corrupted scratch
  authority.
- **H4 (the membership rules).** Plugins census pinned at **15** with `demo.py`/
  `fetch_contracts.py` inside; a literal planted in a scratch flat plugin
  (`plugins/<invented>/mod.py`, no `src/`) refuses (RED at base: passes — invisible
  today); a literal planted in a scratch directory NAMED `venv` without `pyvenv.cfg`
  refuses (RED at base: passes); the same plant inside a scratch marker-carrying
  directory (`pyvenv.cfg` present) is excluded and the census is unchanged. SHIP: all
  four arms. KILL: any arm inverted.
- **H5 (twin parity).** The shared-region markers exist in both counters; the regions are
  byte-identical over the real trees; a one-character mutation of the twin's region in a
  scratch copy fails the parity test; the twin refuses an assembled plant in a scratch
  SDK src tree. SHIP: all arms. KILL: the mutation passing; the twin accepting an
  assembled literal the gateway refuses on the same tree state (the G-risk-2 falsifier).

**Underpowered-measurement rule (pre-committed):** every arm is a deterministic
single-cell check; the only n>1 requirement is H2's byte-identical double run. If a RED
arm cannot be reproduced at the merge base, the fixture or scope definition is wrong, not
the mechanism — stop and re-baseline before building. No statistical arms exist.

## 8. Top risks — and what an adversary attacks first

1. **Future benign assembly false-positives** (an error message assembling a
   version-looking string from constants). MITIGATION: measured 0 at head over 142 files;
   a future hit is a LOUD failure demanding a derivation or a reviewed register edit —
   the register's teeth, working. FALSIFIER: a head where multiple legitimate sites force
   register edits — evidence the patterns are over-broad; revisit with the evidence, not
   by widening exemptions.
2. **The self-exemption as a laundering hole** (a literal planted in the counter file
   outside the register data). MITIGATION: every counter edit is an editorial re-baseline
   by the docstring's own rule; the shared region is digest-pinned against the twin
   (H5). RESIDUAL: a plant in the gateway counter's non-shared region is self-exempt and
   parity-invisible — named here; the review lane carries it (the same posture the
   definition-change rule already takes).
3. **The move-to == active theorem breaks** (a future policy shape where the warning's
   move-to is not the active entry — e.g. yanking the active version without a
   successor). MITIGATION: the control FAILS loudly (the observed warning names something
   other than the derived expectation) and the refusal prefixes carry the diagnosis;
   redesign is the trigger, not a patch. FALSIFIER: a policy state where the control
   passes while the warning names a non-active version — none constructible today.
4. **Fold-evaluator semantics bugs.** A wrong fold toward a hit is a loud, reviewable
   failure; a wrong fold toward a miss joins the does-not-catch class. MITIGATION: the
   battery pins the twelve shapes; the Tuple-folds-to-tuple rule is load-bearing and
   battery-pinned (S5). FALSIFIER: any battery shape regressing.
5. **Marker-rule blind spots** (an environment whose `pyvenv.cfg` was deleted scans as
   code). MITIGATION: that direction FAILS LOUD on the environment's own literals and is
   dispositioned by a named path exclusion — never a silent pass. FALSIFIER: a third-party
   tree passing the gate silently — excluded by construction (its literals would count).
6. **Scope churn** (the plugins census 13→15 colliding with a parallel lane touching the
   plugin tree). MITIGATION: the census pin is updated in the same commit with the
   ratchet-discipline message the existing test already instructs; the #260 record lane
   touches no plugin bytes. FALSIFIER: a merge-order conflict on the pin — resolved by
   re-measuring, never by loosening the pin.

## 9. Forks for the maintainer

- **Fork 1 — scripts fixture fields: register (recommended) vs derive from schema consts.**
  Registering 20 authored values with value pins is minimal and loud; deriving the
  registry fixture fields changes emitted lattice bytes on every bump (D-2). Recommended:
  register now, derive at the next fixture-rebuild arc if the owner prefers.
- **Fork 2 — the adc MOVE_TO route: the active-entry read (recommended) vs re-implementing
  the highest-served rule vs importing the gateway package.** Re-implementation is drift
  bait; importing couples a clean-venv control to the checkout environment. The
  active-entry read is a direct authority read whose equivalence is a stated theorem with
  a loud failure mode. Recommended: the active-entry read.
- **Fork 3 — self-exemption breadth: whole file (recommended) vs line-scoped.** Line-scoped
  is new machinery for marginal closure; the whole-file exemption with the named residual
  (risk 2) matches the docs-snapshot precedent (gate metadata is never scanned).

## 10. DISCLOSED UNVERIFIED

- **The exact original 12 refute shapes** were session artifact; this battery is a
  reconstruction whose honesty rests on the 9/3 arithmetic match (§0.1) — stated, not
  claimed as the original list.
- **The census pins after build** (scripts 16, plugins 15) are design-time measurements at
  `8a2cca1`; the builder re-measures at its merge base and updates the pins in the same
  commit if a parallel lane moved a tree (the pins' own instructed discipline).
- **The adc control's end-to-end run** under the derived pins needs network/git/uv and is
  not exercised by the unit arms; the derivation arms cover the policy reads, and the
  next real control run (its own lane) proves the pair end-to-end — the refusal prefixes
  make a wrong derivation stop the control before any test runs.
- **`str.format` folding breadth**: kwargs, format-specs and conversions are unfolded
  (S11 covers the positional form); a `%`-with-dict is unfolded (no dict folding). Both
  are D-3 residuals, named in the does-not-catch sentence.

---

*Design record for issue #269 (the #221 slice-7 follow-on). All three rows BUILD — the
premises were corrected by measurement (scripts is 23 sites, not 2; the venv row binds a
dormant rule; the battery's arithmetic matches the recorded 9/12), the mechanisms extend
the committed counter in both repos, and acceptance H is pre-committed with both kill
directions. No standards bytes move in either repository.*
