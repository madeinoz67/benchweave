# Design: `benchweave.standards repin` — recompute corpus-manifest sha256 rows — plus the Makefile venv pin

**Date:** 2026-09-18 · **Issue:** #46 · **Base:** `main` @ `7bcdc17`
**Triage:** public — mechanism and tests only; no person, client, bench or install
identifiers. (One code path is quoted from `Makefile`/`ci.yml`; both are committed
public files.)

---

## 1. Problem and verified root cause

`standards/corpus-manifest.json` byte-pins 78 rows (measured 2026-09-18 on `7bcdc17`)
against the on-disk corpus, and drift-and-obligations §6 obligates the pins to move with
every vendored change — but **no in-tree code path ever writes those pins**:

- `src/benchweave/standards/manifest.py:53-67` — `validate_manifest` only *reads* pins
  (`_corpus_pins`, line 71) and compares (`normative_hash_mismatch` on drift).
- `src/benchweave/standards/export.py:18-40` — `export_bundle` *validates first*
  (line 21) then recomputes digests itself from bytes (line 59) into the **bundle**
  manifest. It refuses to run while pins are stale; it never repairs them.
- `src/benchweave/standards/check.py` — read-only against the lock and vendored tree.
- The #45/#47 run updated pins by hand (recompute `shasum -a 256`, splice the digest
  string into the manifest) — the loop's only existing write path is a hand-edit.

Corroborating evidence that the hole is real, not hypothetical: the committed drift
reminder `.claude/hooks/drift-guard.mjs` (obligation 6, `vendored-standards-drift`)
instructs *"Re-export and re-sync rather than hand-editing pins"* — but re-export does
not write pins, so as the code stands the message prescribes a mechanical path that does
not exist. The governor runbook (`.claude/agents/standards-governor.md`, duty 5) orders
"corpus digests recomputed" with no tool named.

Related wart (same issue): `Makefile` pins `UV_PROJECT_ENVIRONMENT=venv` only on the
SDK-sync line (line 12). Lines 11, 13, 14, 15 (`sync-sdk-standards`) and lines 20, 21
(`check-sdk-standards`) run bare `uv run`, so any invocation from a shell without the
variable exported — a clean shell, CI, an agent session — creates and uses a stray
`.venv/` at the repo root, violating the repo's non-dot-venv convention
(`.gitignore` lines 6-7 cover both; only `venv/` is intended).

## 2. What the corpus manifest actually is (measured on `7bcdc17`)

Structure: `{"identity": {...}, "files": [{path, source, sha256}, ...]}`.

- **78 rows**, every row exactly the keys `{path, source, sha256}`; 0 duplicate paths;
  rows are grouped (not globally path-sorted) — insertion order is load-bearing.
- **104 files** on disk under `standards/`; the 26 unpinned ones are exactly the 24
  prose companions (`.md`) plus the two manifests themselves — i.e. **machine file ==
  `*.json` under `standards/` minus the two manifests**, which is precisely
  `tests/contract/test_baseline.py:62-67` (`_contract_files`) and enforced as coverage
  by `test_manifest_lists_every_contract_file` (line 84).
- **Serialization is a proved fixed point**: the current 17,761 bytes are byte-identical
  to `json.dumps(json.loads(raw), indent=2) + "\n"` (verified by round-trip on
  2026-09-18; also 0 non-ASCII bytes, so `ensure_ascii` fidelity is total). Note this
  is **not** `canonical_json` (`export.py:14-15`, sorted+compact) — that formatter is
  for the bundle manifest only. Reusing it here would reflow the file.
- **Governance split of rows** (the crux, resolved below): 54 rows are the
  `standards/`-prefixed normative paths declared by `standards/standards-manifest.json`
  (otdp@0.1.1: 24, registry@0.1.0: 6, execution@0.1.0: 12, interface@0.1.0: 6,
  plugin-ui@0.1.0: 4, plugin-ui-preview@0.1.0: 2; the plugin-ui entry's fifth normative
  path, `src/benchweave/presentation/contracts.py`, is not a `standards/` file and
  carries no pin — `manifest.py:68`). The remaining **24 rows are the superseded
  `otdp/0.1.0/` tree** — GOVERNANCE.md "Bump mechanics — copy, never move": *"the old
  dir and its corpus-manifest rows stay in place, digest-frozen."*

### Governance resolution: which rows are regenerable

- **Regenerable** ⇔ the row's `path` appears in the current standards-manifest
  normative list (with the `standards/` prefix stripped). Structural rule, no
  string-prefix heuristics: `load_manifest(root)` is the same authority
  `validate_manifest` already uses.
- **Frozen** ⇔ every other row (today: exactly `otdp/0.1.0/**`). The command
  recomputes these too but only to **verify** — a mismatch is refused, never written.
  Structural reason: recomputing a frozen pin would launder an in-place edit of a
  retained version — which GOVERNANCE.md calls "a governance violation, not a
  shortcut" — into a clean manifest. The command must be unable to commit that
  laundering, not merely discouraged.
- The rule also degrades conservatively for the pinned-but-not-normative corner (a
  machine file inside a *current* version dir that standards-manifest forgot to list):
  such a row classifies frozen, so editing its bytes is refused until the manifest gap
  is fixed — the failure points at the real defect (the missing normative entry).

What `repin` does **not** and cannot enforce: change-class/bump discipline. After
`repin`, the main-repo hash signal is clear by construction; the same-version
byte-change signal survives cross-repo in the SDK lock
(`check.py:116-119` `content_drift_without_version`) until an explicit
`make sync-sdk-standards`, and the governor review remains the process authority.
`repin` shifts no authority anywhere; it deletes a manual digest-splice step.

## 3. Mechanism

**Module** `src/benchweave/standards/repin.py`, one public function, mirroring the
export/check module shape:

```python
def repin_manifest(root: Path) -> list[str]:
    """Recompute corpus-manifest sha256 rows from the on-disk corpus.

    Existing rows only: row creation/deletion and `source` provenance stay
    hand-authored under governance review. Superseded-version rows are verified,
    never rewritten. Fails closed before any write; writes only when a digest
    actually changed. Returns the paths whose pins changed.
    """
```

Algorithm (all refusals raise `StandardsError` — reused from `manifest.py` — with
machine-matchable prefixes, before any write):

1. **Strict-load** `standards/corpus-manifest.json` (reject duplicate JSON keys and
   non-finite constants, the same `object_pairs_hook`/`parse_constant` trick as
   `tests/contract/test_baseline.py:33-49`) → `corpus_manifest_invalid: <detail>`.
   Structural reason: plain `json.loads` would let a duplicate-key manifest load, and
   the load-modify-dump write would silently drop the duplicate — a reflow beyond the
   digest being repinned. Absent file → `corpus_manifest_absent` (unlike
   `_corpus_pins`, which silently tolerates absence; a pin command with no rows to
   pin is a hard error).
2. **Row-shape validation**: every row's key set exactly `{path, source, sha256}`,
   all values strings → `pin_row_invalid: <index>`; `path` must be a relative
   POSIX path with no `..` segment and no absolute/`PureWindowsPath` shape →
   `pin_path_escape: <path>` (the digest loop reads `root/"standards"/path`; a
   traversal row would hash files outside the corpus). Duplicate `path` values →
   `duplicate_pin_row: <path>` (note: `_corpus_pins` collapses duplicates silently
   today — `manifest.py:76` — so this refusal is stricter than the validator the
   issue cites; the issue's "duplicate paths" posture is honored, and
   `validate_manifest`'s tolerance is unchanged in this increment).
3. **Coverage, both directions** (same machine-file definition as `test_baseline`:
   `standards/rglob("*.json")` minus the two manifest files):
   - disk file with no row → `corpus_file_unpinned: <path>` (bump flow: author the
     new rows first — `repin` cannot invent `source` provenance, which GOVERNANCE
     defines as reset-import vs supersession-copy semantics);
   - row whose file is absent → `pinned_file_absent: <path>`.
4. **Classify** via `load_manifest(root)`: normative `standards/`-relative set =
   regenerable; also, any normative `standards/` path with no row →
   `normative_not_in_corpus_manifest: <relative>` (same vocabulary as
   `validate_manifest`; author the row first).
5. **Recompute all digests.** Frozen row whose recomputed digest ≠ pinned →
   `frozen_row_changed: <path>` (restore the bytes or do a proper bump; `repin`
   refuses to paper over it). Regenerable rows take the new digest.
6. **No-op short-circuit:** if no digest changed, return `[]` **without writing**
   (bytes and mtime untouched).
7. **Write byte-identically**: `json.dumps(document, indent=2) + "\n"` (insertion
   order preserved by the loads/dumps round-trip; ASCII-only content today and the
   fixed-point proof above) to a `.tmp` sibling, `os.chmod` it to the original's
   mode, then `os.replace` (atomic; mirrors export's staged-replace discipline at
   `export.py:28-39` for a single file).
8. **Post-write self-check**: `validate_manifest(load_manifest(root), root)` — after
   `repin` it must pass; a raise here is a `repin` bug failing loudly, not a repaired
   state.

**CLI** — one subparser in `src/benchweave/standards/__main__.py`, matching the
existing surface (`export|check|matrix|versions`):

```
sub.add_parser("repin", help="recompute corpus-manifest sha256 rows from the on-disk corpus")
```

dispatch mirrors `check`'s error handling (`__main__.py:29-46`): `StandardsError` →
`standards repin error: <exc>` on stderr, exit 1; success prints
`re-pinned <n> row(s): <paths>` or `corpus manifest already current`, exit 0.

**Name:** `repin`, not `pin` — the command refuses to create rows, and the name must
not imply it does. The loop phrase becomes **edit → repin → export**.

### Makefile fix

```make
sync-sdk-standards: export UV_PROJECT_ENVIRONMENT := venv
check-sdk-standards: export UV_PROJECT_ENVIRONMENT := venv
```

and drop the now-redundant inline prefix on the SDK line (line 12). Notes:

- `:=` (not `?=`) deliberately: the Makefile becomes the one source of truth and the
  targets' behavior is structurally independent of the caller's shell. `?=` would let
  an ambient `.venv` value silently reintroduce the wart.
- Line 12 behavior is preserved exactly: a relative `UV_PROJECT_ENVIRONMENT` is
  resolved by uv against the `--project` dir, so the SDK still gets
  `packages/sdk/venv` as it does with today's inline pin.
- **CI consequence, disclosed:** neither `ci.yml` nor `package.yml` sets the variable.
  `package.yml` is neutral (its `make check-sdk-standards` at line 37 runs before any
  `uv sync`, so exactly one env is built either way — just named `venv/` instead of
  `.venv/` afterwards). `ci.yml`'s `gates` job runs `uv sync` + lint/test on `.venv`
  (lines 30-41) and then the make target on `venv/` — one extra full env build in
  that one job. Both dirs are gitignored; uv's setup-uv cache is content-keyed, not
  path-keyed, so no cache-hit change. Collapsing `ci.yml` to the same convention is
  deferred (§5).

## 4. Precedent (principle 9 — extend, don't invent)

- **CLI surface**: the `benchweave.standards` subparsers — `repin` is the fifth
  subcommand, same dispatch/error idioms as `matrix` (write mode with a `--check`
  verifier — here `check` already exists as the verifier, which is why `repin` has no
  `--check` flag of its own).
- **Fail-closed vocabulary + `StandardsError`**: `manifest.py` (`normative_not_in_corpus_manifest`,
  `normative_hash_mismatch`), `check.py` failure lines.
- **"Validate everything, then write once, never partially"**: `export_bundle`'s
  documented contract (`export.py:19`) and its staged replace; `test_export.py:99-100`
  pins "no partial output / no staging left behind" — the same assertion shape pins
  `repin`'s write-or-refuse.
- **Strict JSON loading**: `tests/contract/test_baseline.py:33-49` — moved into the
  package for this one load, unchanged in the test.
- **Test idioms**: `tests/standards/test_manifest.py:68-80` (tmp copy, corrupt one
  thing, assert the refusal), `test_export.py:63-100` (broken repo, refuse, no
  partial output), `test_check.py:34-35` (`_prefixes` set asserts),
  `test_export.py:103-119` (subprocess CLI test).

No new architecture: one module over two existing manifests and one existing digest
function pattern (`hashlib.sha256(path.read_bytes()).hexdigest()`, `manifest.py:61`).

## 5. Minimal first increment — and explicit deferrals

**In scope (one RED→GREEN slice plus carried docs):**

1. `src/benchweave/standards/repin.py` + `__main__.py` subcommand (as above).
2. `tests/standards/test_repin.py` (§7 enumerates the tests).
3. Makefile env pin (3-line diff) — same commit is acceptable; it is mechanically
   independent, so two commits are cleaner if the builder prefers.
4. Committed docs that currently describe the loop, updated to name it:
   `standards/GOVERNANCE.md` (gates list + bump runbook step 2),
   `docs/internal/drift-and-obligations.md` §6, `.claude/hooks/drift-guard.mjs`
   obligation-6 message (replacing the non-existent "re-export" advice),
   `.claude/agents/standards-governor.md` duty 5 + bump runbook,
   `docs/internal/invariants.md` (CON-7, §6).
5. No SDK-repo changes, no submodule pointer movement (the SDK lock at
   `packages/sdk/standards-lock.json` is bundle-derived — verified: it never
   references `corpus-manifest.json`; `check.py` compares it against a fresh
   `export_bundle`, and `export` recomputes digests from bytes, `export.py:59`, so
   the SDK side observes nothing about who wrote the pins).

**Deferred, explicitly:**

- Row creation/deletion and `source` provenance synthesis — refuses instead; a
  machine cannot know reset-import vs supersession-copy provenance (GOVERNANCE "never
  a path that did not produce the bytes").
- `identity`-block sync from `standards-manifest` versions — a separate drift surface
  (pinned by `test_baseline.py:103-110` literals today).
- Moving coverage/duplicate checks into `validate_manifest` itself (would change
  export/check failure surfaces; today they live in `test_baseline`).
- `--dry-run` (the no-op path already writes nothing; `check` is the verifier).
- Aligning `ci.yml`'s bare `uv sync`/`uv run` lines to `UV_PROJECT_ENVIRONMENT=venv`
  (would collapse the `gates` job to one env; disclosed cost until then).
- Any Makefile restructure beyond the env pin; `ruff format`/lint config for the new
  module follows repo defaults.

## 6. Invariant and cross-surface impacts

- **New [CON-7]** (append to `docs/internal/invariants.md`):
  *Corpus-manifest sha256 rows are machine-rewritten only by
  `benchweave.standards repin`, which rewrites existing rows' digests, never rows
  themselves (`path`/`source` byte-preserved, byte-identical formatter), refuses
  structural surprises fail-closed before any write, and verifies-but-never-rewrites
  superseded-version rows — `src/benchweave/standards/repin.py`, pinned by
  `tests/standards/test_repin.py`.* Why: without it, the next contributor's fastest
  path is another hand-splice, and the frozen-row guarantee lives only in prose.
- **CON-4** (vendored-tree drift gate): unchanged — `make check-sdk-standards` still
  runs `export`→`validate_manifest` first, so a stale pin still fails the gate;
  `repin` is upstream of it, not part of it.
- **CON-2** (fixture lattice): untouched — different manifest, different mechanism.
- **CTL/STO/REG**: untouched — no control, store, or plugin surface moves.
- **On-disk format/schema**: none changes — the entire point is a byte-identical
  writer (fixed-point proof §2). Not a Tier-3 (format/schema) change; the review
  rubric's format-change obligations do not trigger.
- **Obligations walked** (drift-and-obligations): §1/§2 (no corpus bytes change in
  this increment), §6 (this is the fix; prose updated), §7 (no UI change, no
  submodule move), §9 (no dependency change). Operator-guide/README: the existing
  `benchweave.standards` subcommands are not documented there today, so adding one
  creates no new doc obligation there; the standards-flow docs listed in §5 are the
  surfaces that do name the loop.
- **CI cost**: ~10 new fast unit tests in `tests/standards/` (tmp-path copies of
  `standards/` only, no subprocess except one CLI test); no new job; one extra uv
  env build in the `gates` job from the Makefile pin (§3).

## 7. Measurable proof — tests, control, and the pre-committed acceptance rule

**RED shape (today, on `7bcdc17`):**

- `uv run python -m benchweave.standards repin` → argparse `invalid choice: 'repin'`,
  exit 2 (CLI surface absent).
- `from benchweave.standards.repin import repin_manifest` → `ModuleNotFoundError`.
- Makefile wart: `env -u UV_PROJECT_ENVIRONMENT make check-sdk-standards` → target
  succeeds but leaves a stray `.venv/` at the repo root (uv's default project
  environment when the variable is unset). Builder must clean it up afterward — it
  is gitignored, not invisible.

**Discriminating tests** (`tests/standards/test_repin.py`; each builds a tmp repo by
copying the real `standards/` tree, mirroring `test_manifest.py:68-80`):

1. `test_repin_round_trip_is_byte_identical` — no-op on the real tree:
   `repin_manifest(ROOT) == []` and the manifest bytes are unchanged (this is the
   formatter control: load-modify-dump with zero modifications writes nothing).
2. `test_repin_updates_exactly_the_edited_row` — flip a byte in one regenerable file
   (e.g. `registry/0.1.0/examples/package-lock.json`); run; assert (a) the returned
   list is exactly that path, (b) the manifest byte-diff is exactly one changed line
   containing exactly the new 64-hex digest, (c) parsed before/after: row order, all
   `path`/`source` values, all other digests, and the `identity` block are equal.
3. `test_repin_matches_the_hand_splice` — the matched control: reproduce the #45
   incumbent method in-test (recompute the digest, string-replace the old digest in
   the raw bytes) and assert `repin`'s output is byte-identical to it.
4. `test_repin_refuses_frozen_row_edit` — flip a byte in `otdp/0.1.0/<any file>`;
   `StandardsError` matching `frozen_row_changed`; manifest bytes untouched.
5. `test_repin_refuses_unpinned_machine_file` — drop `stray.json` into
   `standards/otdp/0.1.1/examples/` → `corpus_file_unpinned`; no write.
6. `test_repin_refuses_pinned_file_absent` — delete one pinned file →
   `pinned_file_absent`; no write.
7. `test_repin_refuses_duplicate_rows` — duplicate a row in the manifest text →
   `duplicate_pin_row`; no write.
8. `test_repin_refuses_normative_row_missing` — add a file and list it in
   `standards-manifest.json` normative without a corpus row →
   `normative_not_in_corpus_manifest`; no write (the bump-flow ordering guard).
9. `test_repin_refuses_duplicate_key_manifest` — hand-corrupt the manifest with a
   duplicate `"sha256"` key → `corpus_manifest_invalid`; no write.
10. `test_cli_repin_runs` — subprocess `-m benchweave.standards repin` on the real
    tree, exit 0, prints `already current` (mirrors `test_export.py:103-119`).
11. RED-sanity control for the mechanism's necessity: after flipping a regenerable
    file's bytes **without** repinning, `validate_manifest` raises
    `normative_hash_mismatch` (this is the "disable the mechanism, the effect
    disappears" check — repin is the only in-tree writer, so removing it must
    re-expose the failure).

**PRE-COMMITTED acceptance rule** (written before any post-fix measurement):

- Metric/effect size: on a tmp copy of the real corpus with exactly one regenerable
  file's bytes changed, `repin` must change **exactly 1 of 78 rows** — one line of
  the manifest diff, 64 hex chars — with every other byte of the 17,761-byte file
  identical (sample: the full manifest, i.e. 78/78 rows compared, not a spot check);
  the no-op run must leave the file byte- and mtime-identical; all six refusal cases
  (tests 4-9) must exit with their exact prefix and leave the manifest byte-identical.
- Ship if: all 11 tests GREEN from the RED states above, `make check-sdk-standards`
  still green on the real tree, and the Makefile acceptance (below) passes.
- **Kill** if: the no-op or single-edit byte-diff shows any reflow beyond the one
  digest (key order, indent, trailing newline, dropped keys) — the formatter claim is
  falsified; or a frozen-row edit is rewritten rather than refused — the governance
  scoping is falsified; or the hand-splice control (test 3) differs by any byte.
- **Underpowered, not conclusive** if: any test cannot be made to fail pre-fix (RED
  unprovable) or passes with `repin_manifest` stubbed to return `[]` — then the test
  measures nothing and must be sharpened before any ship decision.

**Makefile acceptance:** in the real checkout, record
`find . -maxdepth 1 -name ".venv"` (expected: absent), run
`env -u UV_PROJECT_ENVIRONMENT make check-sdk-standards`, re-run the find — must
still be absent, target exit 0. RED: the same steps on the pre-fix Makefile produce
`.venv/` (then `rm -rf .venv`). `sync-sdk-standards` is verified by inspection of the
recipe lines (running it would re-init and dirty the SDK submodule working tree —
the two-repo discipline forbids that in this checkout), plus one `make -n` render
showing the exported variable on every `uv run` line.

## 8. Top risks and falsifiers

1. **Formatter drift via exotic manifest content** (e.g. a future hand-added `source`
   with non-ASCII): `ensure_ascii` would re-escape it on the next repin, a reflow
   beyond the digest. Falsifier/mitigation: tests 1-3 pin byte-identity on the real
   tree and against the incumbent splice; residual is bounded to repin runs that
   change a digest (a no-op repin never writes).
2. **Governance laundering perception** — `repin` clears the main-repo hash signal on
   same-version byte edits. Structural mitigation: the SDK lock gate
   (`content_drift_without_version`) still fires until an explicit sync, and sync
   still refuses a dirty submodule (`Makefile` lines 6-10); process mitigation:
   governor review. Falsifier: if a reviewer can show a same-version byte change
   reaching the SDK with no gate ever firing, the increment's honesty claim fails.
3. **CI double-env in `gates`** from the Makefile pin. Bounded: one extra uv sync in
   one job; falsifier: if `gates` runtime regresses beyond ~1 minute on the PR run,
   pull the deferred `ci.yml` alignment into this increment.
4. **`:=` overrides an operator's deliberate ambient env** — intentional (one source
   of truth); an operator needing a different env now edits the Makefile. If this
   breaks a documented workflow, that's the falsifier; none is documented today.
5. **Name/API regret** (`repin` vs `pin`): the issue left the name TBD; the refusal
   to create rows is encoded in the name. Falsifier: user confusion in review —
   rename is a one-line cost before merge.

## 9. Open for the maintainer

- Subcommand name sign-off (`repin` proposed; `pin` rejected for implying row
  creation).
- Whether the `ci.yml` venv alignment (deferred) should ride this PR as a fourth
  commit or land separately.
- Whether `duplicate_pin_row`/coverage refusals should also be retrofitted into
   `validate_manifest` in a later increment (this design keeps the validator's
   behavior unchanged).
