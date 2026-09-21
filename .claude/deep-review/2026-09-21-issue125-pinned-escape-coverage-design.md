# Issue #125 — regression coverage for the pinned check's path-escape arm

Status: design complete, ready to build. Test-only increment; no production
code changes. Branch `test/issue125-pinned-escape-coverage` (at `main`, `4ffa2f9`).
Design feasibility was probed in /tmp (no checkout writes); numbers below are
labeled whose they are. The acceptance rule in §6 is pre-committed for the
builder's on-branch run — commit this record before running it.

## 1. Root cause and premise verification

Issue #125 (verified against the tracker): the devices regression arms pin the
pinned check's **hash-mismatch** arm (parametrize row 1) and the census arm
(row 2); nothing exercises `is_relative_to(OUT)`. The ask is explicit that the
new arm must fail "for the escape reason, not merely the hash reason."

The pinned check, `scripts/architecture/check_devices.py` (descriptors loop,
inside `if "profiles" in d:`):

```python
for c in d["contracts"]:
    path = (OUT / c["path"]).resolve()
    check(
        p.name + " pinned " + c["id"],
        path.is_relative_to(OUT)
        and path.is_file()
        and (hashlib.sha256(path.read_bytes()).hexdigest() == c["sha256"]),
    )
```

with `OUT = (STANDARDS / "otdp" / OTDP_VERSION).resolve()` (resolved-to-resolved
since #126 / `4ffa2f9`, verified at HEAD). Verified properties the design leans on:

- **Conjunct order and short-circuit.** `and` evaluates left to right; a black-box
  observer sees only the combined boolean, so attribution of *which* conjunct
  failed is only possible **by construction**: make the other two conjuncts true
  and the failure deductively belongs to the escape arm.
- **`contracts[].path` is schema-free text.** `otdp-device-descriptor.schema.json`
  constrains it as `{"type": "string", "minLength": 1}` — no pattern, no format.
  `"../escaped-contract.json"` is schema-valid, so the `descriptor structure`
  check stays green (verified against the active 0.2.0 schema).
- **Nothing else consumes `contracts`.** In `check_devices.py` the contracts list
  appears only in the pinned loop; no check scans `standards/otdp/` itself (all
  scans are `OUT.glob(...)` or named `load(...)`s), so a file placed in `otdp/`
  outside the version dir is invisible to every other check.
- **`class-dc_psu.json`** carries `profiles` and `contracts[0] =` the
  profile-catalog contract (`urn:otdp:profile-catalog:0.2.0` →
  `device-profile-catalog.json`, sha256 `dc776ec3…`).

### Live finding: the working tree is NOT clean

The dispatch claimed the broken first draft was reverted. It was not:
`git diff tests/contracts/test_architecture.py` shows 26 uncommitted
insertions — `test_pinned_check_detects_path_escape` with
`escaped = standards / "escaped-contract.json"`. That is the root-caused-broken
shape: `../` from `OUT` (`standards/otdp/<ver>/`) resolves to
`standards/otdp/escaped-contract.json`, **not** `standards/escaped-contract.json`,
so the copied file does not exist at the resolved location, `is_file()` fails,
and the pinned check fails **regardless** of the escape arm — with the arm
neutralized to `True`, `is_file()` keeps the check failed, so the test stays
GREEN (orchestrator-measured this session: junitxml 1 test, 0 failures, arm
off). The test cannot discriminate escape from existence. **Builder step 0 is
to discard this hunk** (`git checkout -- tests/contracts/test_architecture.py`)
before applying §3. Other uncommitted traffic in the checkout (`M packages/sdk`,
untracked evidence files) belongs to other active work — do not touch it.

## 2. Mechanism

A dedicated pytest arm in `tests/contracts/test_architecture.py` that
constructs, on a `tmp_path` copy of the corpus, the **only** corpus state in
which the escape conjunct is the sole failing one:

1. `shutil.copytree` `docs/` and `standards/` to `tmp_path` (established
   discipline — every mutation test in this file works on copies; the real
   corpus is never touched).
2. Derive the active version dir from the manifest via the file's existing
   `_active_report_path().rsplit("/", 1)[0]` — never a literal (the #102 D2
   rule the parametrize rows already follow).
3. Take `class-dc_psu.json`'s `contracts[0]`; **copy its target's bytes
   UNCHANGED** to `version_dir.parent / "escaped-contract.json"` (=
   `standards/otdp/escaped-contract.json` — one level above `OUT`, exactly
   where `../` lands).
4. Pin the geometry with a resolve-equality guard:
   `assert (version_dir / "../escaped-contract.json").resolve() == escaped.resolve()`.
   This is the structural fix for the draft-1 defect class: if the copy target
   and the descriptor's `../` ever drift apart again, the guard fails loudly
   instead of the test silently degrading to non-discriminating.
5. Rewrite `contract["path"] = "../escaped-contract.json"` and re-dump the
   descriptor with `json.dumps(descriptor, indent=2)`.
6. Run the devices suite via the file's `run_checks("devices", docs, standards)`
   and assert **exact list equality**:
   `failures == [f"class-dc_psu.json pinned {contract['id']}"]`.

Why each piece is load-bearing:

- **Bytes unchanged** ⇒ recorded sha256 matches ⇒ the hash conjunct is true.
- **File exists at the resolved location** ⇒ `is_file()` true.
- **Resolved path outside `OUT`** ⇒ `is_relative_to(OUT)` false — the only
  false conjunct. Deductively, the failure *is* the escape arm; this is the
  strongest attribution available black-box, and it is exactly what the issue
  asks ("not merely the hash reason").
- **Exact equality, not substring-any** ⇒ the test also proves there is no
  collateral failure (schema, census, structure). The parametrize rows'
  `any(expected in name ...)` shape would pass for hash reasons too — #125
  explicitly forbids that.

### Dedicated test, not a parametrize row (decision)

The row harness (`test_contract_regressions_are_detected`) is a single
old→new byte replacement plus substring-any assertion; it cannot create a new
file, and its assertion shape is exactly what this arm must not use. Extending
the harness for one row would modify shared machinery and weaken the
assertion. Precedent for multi-step constructions is in-tree and adjacent:
`test_pinned_checks_pass_through_symlinked_standards_alias` (#119 — copytree +
symlink + exact `failures == []`) and
`test_documents_ignores_markdown_links_inside_fenced_code_blocks`. The new test
is the #119 test's sibling: same discipline, inverted expectation (exactly one
named failure). Placement: immediately after the symlink test (the slot the
broken draft currently occupies).

## 3. The exact increment

Replace the uncommitted broken hunk with (full body — apply verbatim):

```python
def test_pinned_check_detects_path_escape(tmp_path: Path) -> None:
    """The pinned check's escape arm must fail an escaped contract path (#125).

    The regression rows pin the hash-mismatch and census arms; this dedicated
    arm pins ``is_relative_to(OUT)``. The contract's bytes are copied UNCHANGED
    to one directory above the active version directory, and the descriptor's
    contract path is rewritten to ``../``-reach it, so the recorded sha256
    still matches and the file still exists — by construction the only clause
    that can fail is the escape itself, never the hash or existence. The
    resolve-equality guard pins the geometry: if the copy target and the
    ``../`` resolution ever drift apart (the vacuous shape this test replaced),
    the guard fails loudly rather than passing for the wrong reason.

    Ordinary corpus obligation: class-dc_psu.json must keep a non-empty
    ``contracts`` array and its ``profiles`` key — the construction is generic
    over whichever contract is ``contracts[0]``.
    """
    docs = tmp_path / "docs"
    standards = tmp_path / "standards"
    shutil.copytree(ROOT / "docs", docs)
    shutil.copytree(ROOT / "standards", standards)
    version_dir = standards / _active_report_path().rsplit("/", 1)[0]
    descriptor_path = version_dir / "examples" / "class-dc_psu.json"
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    contract = descriptor["contracts"][0]
    escaped = version_dir.parent / "escaped-contract.json"
    escaped.write_bytes((version_dir / contract["path"]).read_bytes())
    assert (version_dir / "../escaped-contract.json").resolve() == escaped.resolve(), (
        "escape target must be exactly where the descriptor's ../ lands"
    )
    contract["path"] = "../escaped-contract.json"
    descriptor_path.write_text(json.dumps(descriptor, indent=2), encoding="utf-8")
    failures = [name for name, passed in run_checks("devices", docs, standards) if not passed]
    assert failures == [f"class-dc_psu.json pinned {contract['id']}"], failures
```

Delta from the uncommitted draft: the escape target moves from
`standards / "escaped-contract.json"` to `version_dir.parent / …`, the guard
assertion is added, the docstring records the construction and the obligation.
Three substantive lines.

Commits: (1) this design record; (2) the test,
`test(contracts): pin the pinned check's path-escape arm (#125)`. Conventional
format, `(#125)` suffix, no attribution. PR links issue #125 (single issue
stream — gateway tracker; no SDK-side issue exists or is needed: no SDK file
changes).

## 4. Precedent

- `test_pinned_checks_pass_through_symlinked_standards_alias` — dedicated
  pinned-check-mechanics test, tmp corpus, exact-equality assertion, docstring
  carrying the why. Extended, not replaced.
- The parametrize comment block — in-file documentation of corpus obligations
  ("ordinary corpus obligation" phrasing) reused in the new docstring.
- The RED-sanity-check protocol (repo CLAUDE.md §3.3) — this increment's
  acceptance control is that protocol applied to a coverage arm: the
  "fix" is the escape conjunct; disabling it must flip the test.

## 5. Invariant and drift impacts

- **No production code changes.** `scripts/architecture/check_devices.py` is
  untouched in every committed byte; the pinned check is not weakened. The
  arm-neutralized variant exists only inside the acceptance protocol (§6) and
  is restored and verified restored.
- **Real corpus untouched.** All mutations live in pytest `tmp_path` copies;
  `test_validation_is_read_only` continues to pin read-only-ness on its own
  tmp copy. The committed `validation-report.md` is a function of the check
  set over the real tree — unaffected; `test_validation_report_matches_live_run`
  guards that and must stay green unchanged.
- **No standards bytes move.** No vendored tree, no lock, no manifest, no SDK
  surface — review Tier is the ordinary test lane, not Tier 3. The
  `packages/sdk` submodule pointer is not advanced (no SDK change exists to
  point at).
- **New obligation created:** the in-file corpus dependency on
  `class-dc_psu.json` (non-empty `contracts`, `profiles` present), documented
  in the test docstring per the row-2 precedent. Failure mode is loud
  (`KeyError`/`IndexError`), never a silent pass.
- **CI cost:** +1 test in `tests/contracts/` ≈ one docs+standards copytree plus
  one devices-suite run on the tmp tree — the same cost class as the #119
  symlink test and the tampering rows (seconds). No new job; no doc surfaces
  move; no drift-and-obligations entries triggered (test-only change).

## 6. Measurable proof — pre-committed acceptance rule

Written before the builder's on-branch measurement. (Design-stage feasibility
was probed by the designer in /tmp — disclosed in §7 — and does not substitute
for this run.)

**Metric:** the new test's power to discriminate the escape arm, measured by an
arm-neutralization control. The patch site is unambiguous:
`path.is_relative_to(OUT)` occurs exactly once in `check_devices.py`
(verified); replace it with `True`.

**Protocol (in order):**

1. Commit this design record on the working branch first (provability of
   pre-commitment).
2. Discard the uncommitted broken hunk; confirm `git status` shows no
   unintended changes beyond the known unrelated traffic; apply §3.
3. **GREEN (arm on):** `UV_PROJECT_ENVIRONMENT=venv uv run pytest
   tests/contracts/test_architecture.py -q` → collected count includes
   `test_pinned_check_detects_path_escape`; 0 failed. Read counts from the raw
   run / `--junitxml` attributes, never an output-filter summary line.
4. **RED (arm off):** patch `scripts/architecture/check_devices.py`
   (`path.is_relative_to(OUT)` → `True`); re-run the same command → **exactly
   one** failing test, `test_pinned_check_detects_path_escape`, with an
   assertion diff showing the failures list empty (`[]` on the actual side).
   No other test in the file may change outcome.
5. **Restore:** `git checkout -- scripts/architecture/check_devices.py`;
   re-run step 3 → 0 failed.
6. **Full battery:** `uv run ruff check .`; bare `uv run mypy`; full
   `uv run pytest -q` → 0 failed, collected == main baseline + 1 (baseline
   1391 per the orchestrator's prior full run — re-read the fresh raw count on
   main if in doubt).
7. Three consecutive clean re-runs of steps 3–5 (flake check; `tmp_path` and
   resolve() platform variance). Reviewer re-running steps 4–5 at review time
   is cheap and expected.

**SHIP iff:** 3 GREEN, 4 exactly-one-failure-shaped-as-specified, 5 GREEN, 6
0-failed with baseline+1 collected, 7 no flakes.

**KILL iff:**
- Step 4 leaves the new test passing (non-discriminating — the draft-1 defect;
  the construction has regressed to vacuous), or
- Step 3 fails the new test (the mutation trips more than the pinned check —
  schema drift or a collateral check), or
- Any *other* test changes outcome between the step-3 and step-4 runs
  (cross-contamination).

**UNDERPOWERED (inconclusive, not a verdict) iff:** the neutralization patch
matches more than one site (ambiguous arm), or counts cannot be read from raw
output/junitxml — fix the harness and re-run the protocol unchanged. Tuning
the rule after seeing a number is the failure this section exists to prevent.
This is a deterministic logic gate, not an estimate: no effect size or
statistical sample applies; the signal is binary and both directions are
specified above.

## 7. Design-stage feasibility probe (designer's measurement, /tmp only)

A scratch script replicated §3's construction on a tmp corpus and ran the real
`check_devices.py` (arm on) and a `/tmp` copy with the arm neutralized (arm
off). No file in the checkout was written. Results (designer's measurement,
2026-09-21):

- contract[0] id: `urn:otdp:profile-catalog:0.2.0`
- geometry guard holds: True
- ARM-ON failures: `['class-dc_psu.json pinned urn:otdp:profile-catalog:0.2.0']`
  (exactly one; no collateral — schema, census, structure all green)
- ARM-OFF failures: `[]`
- Exit 0.

This is evidence the mechanism works as designed; §6 remains the acceptance
run of record because it executes on the committed branch after this document.

## 8. Top risks and falsifiers

1. **Re-vacuation drift (the draft-1 defect class).** The escape target
   drifting from where `../` resolves makes the test pass for the wrong
   reason. *Falsified by:* the resolve-equality guard (fails loudly on drift)
   plus the step-4 control at build and review time. Only removing both the
   guard and moving the target revives it — a two-edit mistake the control
   still catches.
2. **Exact-equality over-pinning.** A future devices-suite check that also
   inspects contract paths adds a second failure and breaks this test.
   *Accepted deliberately:* the failure is loud and cheap to update, and the
   substring-any alternative is the shape #125 explicitly rejects. This is
   over-pinning in the service of the issue's own wording.
3. **Corpus evolution.** `class-dc_psu.json` losing `contracts`/`profiles`, or
   removal of the file, errors the test loudly (`KeyError`, `IndexError`,
   `FileNotFoundError`) — an ordinary corpus obligation documented in the
   docstring, mirroring the row-2 byte-pattern precedent. The construction is
   generic over whichever contract is `contracts[0]`; reordering is harmless.
4. **Shared checkout.** The broken draft sits uncommitted in the working tree
   right now (§1), and unrelated uncommitted traffic is present. *Mitigation:*
   builder step 0 discards the hunk by exact path and verifies `git status`
   before and after; nothing else is touched.
5. **`json.dumps` reformat side effects.** The re-dump (indent=2, no trailing
   newline, `ensure_ascii`) changes descriptor bytes in the tmp tree only; no
   devices-suite check byte-compares descriptors (verified by reading the
   script, and empirically — the arm-on probe produced exactly one failure).
   If a future check pins descriptor bytes, this test's exact-equality
   assertion surfaces it immediately.
6. **Windows lane.** No local Windows execution; CI's windows leg is the
   evidence lane (standing rule). `Path.resolve()`/`is_relative_to` semantics
   with `..` are the platform-sensitive surface; the geometry guard makes any
   drift loud there rather than silent.

## 9. Deferrals (explicit)

- **`is_file`-arm coverage** (missing contract file at an in-OUT path) — not
  asked for by #125; would be a separate trivial row if ever wanted.
- **Per-conjunct failure naming in `check_devices.py`** — would make this
  attribution self-evident and would have exposed draft-1's vacuity
  immediately, but it changes production check names and therefore the
  validation-report bytes (regeneration, report-count obligations in
  docs/README.md) — a production increment, out of scope here. Named as the
  natural follow-up if diagnosability is ever wanted.
- **Additional escape shapes** (`../../`, absolute paths, symlinked escape) —
  one canonical `../` escape pins the arm; more shapes add corpus-coupled rows
  with no additional discriminating power.
- **Row-harness extension** — rejected rather than deferred (§2): the mechanism
  does not fit and the assertion shape it enforces is wrong for this arm.

## 10. DON'T-BUILD evaluation

Not applicable. The premise verified (coverage gap is real; the arm is
currently unpinned), the mechanism is measured to discriminate in both
directions (§7), the precedent is in-tree and adjacent, and the increment is
three substantive lines plus a guard. Build.
