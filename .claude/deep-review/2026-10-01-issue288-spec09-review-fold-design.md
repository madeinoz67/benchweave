# Issue #288 — fold the spec-09 RedTeam findings: design record

**Status:** Design (builder-ready) · **Tracking issue:** madeinoz67/benchweave#288 ·
**Reviewed arc:** `docs/implementation-planning/09-standards-dependency-design.md`
(slices #215–#221, follow-on #233) · **Evidence baseline:** gateway `main` at `7125c34`
(detached worktree verified clean and identical); SDK read at pinned gitlink `085b0ff`
through the SDK checkout's object store. Every finding site below was re-verified at this
SHA before design; every measured number carries its denominator and says whose
measurement it is (this pass's measurements are labeled DESIGN-MEASURED).

**Design-time tier call (#254).** **Tier 3**, by three independent rules: (a) the diff
touches `standards/GOVERNANCE.md` (one file under `standards/` — LOW 3); (b) the expected
diff text carries Step-1 keywords — see the scan below; (c) the fold advances the
`packages/sdk` submodule pointer (SDK slice lands first). The refute slate per the owner's
rules: two independent adversary lanes + standards-governor + mechanism-critic (the sweep
rule in M1 and the move-to rule in M4 are digest/derivation rules, so the critic attends).

**Keyword scan (Step 1, over the expected diff text of ALL slices, docs and code
alike — DESIGN-ESTIMATED counts from the site inventory below; the builder re-runs the
scan over the real diff at review and the review re-derives it):** `sha256` ≈ 28
(promotion.py digest-pairing code and tests, export.py, SDK served.py docstrings);
`hashlib` ≈ 8 (import lines and digest-map builds); `subprocess` ≈ 6 (promotion.py's
history-walk helpers, mirroring the module's existing calls); `migrate`/`migration` ≈ 12
(VR-37 text and docstrings touched by the M4 consolidation and the stale-slice-5 NIT);
`threading` 0; `asyncio` 0; `recovery` 0; `protection` 0. First match wins: Tier 3.

**Standards-byte check — FLAGGED.** This fold moves **zero corpus bytes and zero
governance-data bytes** (`standards-manifest.json`, `corpus-manifest.json`,
`promotion-records.json`, `cross-constraints.json` untouched; no version directories move;
no version-string changes anywhere in `standards/`). **One file under `standards/` does
move: `standards/GOVERNANCE.md` (LOW 3's two missing promotion-flow steps).** That is
governance prose, not corpus bytes, but it trips the path-based push tripwire
(`git diff origin/main...HEAD -- standards/`), so it needs the owner's explicit word as a
normal permission gate. It is designed as its own single-file commit (gateway commit G5)
so the owner can approve or veto exactly that motion; the veto fallback is a #288
sub-issue (payload in §9). Everything else in the fold lives in `src/`, `tests/`, `docs/`,
`.claude/deep-review/`, and the SDK repo.

---

## 1. Per-finding verdicts

### M1 — promotion sweep substring laundering — **BUILD**

**Root cause, verified.** `src/benchweave/standards/promotion.py::_line_offends`
admits any changed line via `any(token in line for token in tokens)` — a fast-admit that
requires no counterpart on the opposite side of the diff. Three attacks execute: a
semantic edit on a token-bearing line (the counterpart exists but differs in more than
version strings — the identity rule would refuse it, the token rule admits it first);
comment injection (an appended line carrying `0.2.0` — no counterpart at all); and a
real-to-real digest swap (the digest rule checks set membership, not assignment —
`_sweep_check` builds `dev_digests`/`promoted_digests` as flat sets). The existing RED arm
(`tests/standards/test_promotion.py::test_d3_planted_non_version_edit_refuses_sweep_violation`)
plants a token-free wording change only, so the token-riding class is untested.

**DESIGN-MEASURED controls (this pass, over the REAL founding-record diff — execution
0.2.0, dev_edit_sha `53d700d1…` vs `standards/execution/0.2.0/` at `7125c34`):**
30 changed lines across 7 files (schema files 4 lines each, `execution-contract.md` 2);
**0 lines rely on the token fast-admit** (every token-bearing line also passes the
identity rule); 19 lines admit by the identity re-stamp rule alone; 9 removed/added pairs
(18 lines) carry exactly one bare sha256 each — cross-file document digests
(`examples/bench.json`'s digest re-stamped inside `commissioning.json` and
`run-binding.json`) — and **all 9 pairs satisfy same-relative-path assignment**
(digest-of-P@dev → digest-of-P@promoted). Re-running `_line_offends` with the token rule
deleted over the real diff: **0 offending lines** — the founding record stays green.

**Mechanism.** Two changes to `_line_offends`/`_sweep_check`, generalizing rules the
founding record already proved:

1. **Delete the token fast-admit.** Every legitimate version-transition line (const,
   `$id`, title, description, path segments) has its opposite counterpart and admits
   under the existing identity re-stamp rule (`_VERSIONISH.sub("", line) in
   stripped_opposite`) because the transition tokens (`<target>-dev`, target, pre-dev)
   are all version-shaped and already stripped by `_VERSIONISH`. A changed line that
   merely *contains* a token now refuses unless its version-stripped residual matches the
   opposite side. The `tokens` list stays (it feeds the refusal message's remediation
   text) but no longer admits anything by itself.
2. **Digest re-stamp pairing.** `_sweep_check` already walks both trees; it additionally
   builds path→digest maps (`dev_map`, `prom_map`) beside the existing digest sets, and
   `_line_offends`' digest rule gains assignment: within one hunk, the i-th removed line
   pairs with the i-th added line (difflib emits substitutions as adjacent runs); when
   both sides of a pair carry digests, every digest must still be a known digest of the
   right tree AND the paths they name must agree —
   `{dev_map⁻¹(d) for d in removed-digests} == {prom_map⁻¹(d) for d in added-digests}`.
   A swapped digest names a different file's path and refuses
   `promotion_sweep_violation:` quoting both digests. Unpaired digest-bearing lines
   (an append with no counterpart) keep membership-only admission — **disclosed residual**:
   a *new* line whose only payload is one real digest still admits; it is visible as an
   added line in the promotion PR, which is the review surface, and cannot launder an
   *edit* of an existing line (those always pair).
   **REFUTE-SLATE DISCLOSURE (2026-10-01, mech-F9, folded with the slate's
   digest-lane overhaul):** the digest→path map is one-to-many when two
   files in one tree have IDENTICAL content — the path-set then names both
   and a re-stamp between same-content files admits. Measured at fold
   time: zero duplicate-content files within any single one of the 18
   retained version directories (the corpus's 254 duplicate-content
   groups are CROSS-version copies under copy-never-move — different
   trees, never one tree's map); unreachable today, disclosed.

**Precedent.** The identity re-stamp rule (`_VERSIONISH` residual equality) and the F6
digest-membership fold (`test_a_re_stamp_line_carrying_a_fake_digest_refuses`) are the
in-tree mechanisms being generalized; this is tightening two existing rules, not new
architecture.

**Acceptance (pre-committed).** RED arms, all currently green (the attacks execute):
`test_m1_semantic_edit_on_a_token_bearing_line_refuses` (edit the descriptor
`description` text beside a version mention, counterpart present);
`test_m1_token_riding_comment_injection_refuses` (append
`# 0.4.0 NOTE: reviewers, skip the safety envelope check below` to a prose file in the
promoted tree); `test_m1_real_to_real_digest_swap_refuses` (swap the two `sha256` values
between the cross-referencing example fields — both digests real members of
`promoted_digests`). GREEN controls, all currently green and must stay green:
`test_the_founded_real_tree_validates` (the real diff — DESIGN-MEASURED 0 offending
post-fix), `test_the_honest_record_passes_all_gates` (the fixture sweep),
`test_d3_planted_non_version_edit_refuses_sweep_violation` (the token-free plant).
**Kill direction:** if the founding-record control goes red post-fix, the deletion
over-tightened — do not widen the token list back; investigate which real line class the
identity rule misses and admit it by a rule with evidence (the founding diff's classes
are enumerated above). If any of the three attacks still passes, the fold failed — no
partial ship.

### M2 — self-declared promotion-record trigger — **BUILD**

**Root cause, verified.** `validate_promotion_records` builds `dev_sourced` exclusively
from `_DEV_SOURCE.match(row["source"])` — the promotion's own self-declared citation. A
promotion whose corpus rows cite the RELEASED predecessor (the organic bump's shape)
skips the record, digest, and sweep gates entirely.

**DESIGN-MEASURED control (this pass, over real `main` history at `7125c34`):** for all
18 retained version directories, the commit that introduced each path was located and
that commit's parent's manifest inspected: **exactly 1 introduction had a parent
declaring the standard's dev head — execution 0.2.0 (parent declared `0.2.0-dev`), which
carries its record; the other 17 show no dev head in the introducing parent.** The
history-derived trigger is therefore exact on today's tree: zero false-refuses, and the
single true positive is the recorded promotion.

**Mechanism.** A second, non-self-declared derivation of the no-record trigger, from the
object store (the module's own `_git_show`/`ls-tree` precedent and `check.py`'s
pyproject@pin git-show posture — no new state, no new fields, no new file). For every
retained (standard, version) with no promotion record: locate the first commit touching
`standards/<id>/<version>/` (`git log --format=%H --reverse -- <path>`, first line); read
that commit's parent's `standards/standards-manifest.json` through the object store; if
the parent declares a dev head for that standard whose version equals
`<version>-dev` (strict match — an organic bump landing while an unrelated head is open
does not fire), the landing was a promotion: refuse the existing
`promotion_record_absent:` prefix with the history evidence inline (the parent sha and
the head label it declared). Edge behavior: a root-commit introduction is organic (no
parent); a retained directory whose introducing commit cannot be found in an existing git
root refuses loudly (`promotion_history_unavailable:` — the D4 disclosed-limit posture:
the gate fails loudly on amputated history, never silently passes); the current
`-dev`-source trigger stays as the immediate, current-tree derivation (both triggers,
one prefix).

**Disclosed residual (not closable by tree state):** a dev head that never landed on
`main` (opened, edited, and squash-landed entirely from a branch) leaves no main-history
evidence — bytes-wise that landing IS an organic bump. GOVERNANCE's flow (OPEN is a PR
adding the block to main; EDITs are PRs) plus the mandatory governor lane on every
`standards/` touch are the process gate for that shape; the founding record demonstrates
the sanctioned flow keeps the head main-visible (its introducing parent declared it).

**Precedent.** The landing-sha/dev-edit-sha object-store reads in the same module; the
`_pinned_sdk_package_version` git-show read in `check.py`.

**Acceptance (pre-committed).** RED arm (currently green — the executed bypass):
`test_m2_laundered_source_promotion_requires_a_record` — fixture variant with the head
opened and committed ON MAIN (the sanctioned flow), the landing's rows citing the
RELEASED predecessor as `source`, no record → `promotion_record_absent:` naming the
history evidence. GREEN controls:
`test_m2_organic_bump_citing_predecessor_stays_green` (the successor-version arm — rows
cite the released predecessor, no head ever, no record → clean);
`test_m2_on_main_head_with_honest_record_stays_green`; the real-tree control
`test_the_founded_real_tree_validates` (17 organic stay organic). **Kill direction:** any
false-refuse of an organic bump on the real tree or the successor arm kills the trigger
design (fall back to the disclosed-residual posture and a sub-issue — do not tune the
match loose; a loose match re-opens false refusals, the worse failure).

### M3 — SDK lock-row shape crash — **BUILD (SDK slice)**

**Root cause, verified.** SDK `src/benchweave_sdk/served.py::lock_rows` (~:68) validates
only that `id`/`version` are strings; `_move_to`'s comprehensions call `_tuple(version)`
unguarded over served rows (~:156-161), so one corrupted row version (`"0.2.2"` →
`"0.2.x"`) crashes classification with a bare `ValueError` — one lane over from the F2
fix that made malformed *pins* typed refusals. `standards_sync.py::_version_sort_key`
(:640) has the same exposure over lock rows on the sync path.

**Mechanism.** Shape-validate at the module's one load point: `lock_rows()` refuses
`lock_invalid:` (the existing prefix, naming the row) when a row version does not
fullmatch the canonical-numeral grammar
`(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)` — the grammar `RANGE_PATTERN` already
enforces per-segment gateway-side (`manifest.py:49-52`) and the promotion-records schema
enforces on targets (`promotion.py:88-90`). The grammar constant lives in `served.py`
(the module whose docstring already claims to be "the one reader every consumer shares")
and `standards_sync.py` reuses it in `_read_lock_file`'s row validation so the sync lane
cannot crash on the same row. `_tuple_or_none` keeps guarding pins (external input).

**Acceptance.** RED: `test_lock_row_non_canonical_version_refuses_typed` (plant
`"0.2.x"` and `"0.02.1"` rows — the first crashed with ValueError at `085b0ff`
(reproduced by the review lane), the second is LOW 4's leading-zero twin);
`test_sync_check_refuses_malformed_row_version` (the sync lane). GREEN: the real lock
stays clean; `classify_pin` over a valid lock unchanged. **Kill:** any new traceback path
over lock bytes.

### M4 — five-copy move-to, none ≥pin — **BUILD (consolidation + labeled fallback)**

**Root cause, verified.** Five sites derive the move-to independently:
`dependency.py:396` (`_move_to`), `documents.py:288` (`_vr37_text`) and `documents.py:419`
(`_classify_cached`'s yanked arm), `matrix.py:275`, SDK `served.py::_move_to`. All five
produce `max(served)` numerically (the SDK carries a ≥pin filter, but
`max(candidates≥pin) == max(served)` whenever the filter is nonempty — the filter is
vacuous). `documents.py:277-280`'s docstring presents this as an equivalence *proof*;
the design §3.3 rule ("highest served non-yanked version ≥ pin") is undefined exactly
where the code invents its fallback (pin above every served version → recommends
max(served), an unlabelled downgrade).

**Decision — the honest rule, both halves.** The design's ≥pin rule is implemented
*where it is defined*, and the degenerate case gets an explicit label instead of a
silent fallback: move-to is always `max(served)` (fallback: the range's lower bound when
nothing is served, labeled as guidance the way the SDK's retired branch already labels
F-E-10's fallback), and when the yanked pin is ABOVE every served version the warning
names the downgrade explicitly. Rationale: when a yanked pin tops the range, the newest
healthy served version IS the actionable remediation (the pin's bytes are yanked;
nothing newer is servable); suppressing it in favor of "no move-to exists" helps
nobody — but recommending a downgrade while claiming an upgrade path is the dishonesty
the lane caught. This is option (i) and option (ii) reconciled: numerically the
implemented rule stands (no behavior change in any currently reachable state), the
docstring's false "proof" becomes a *definition with its disclosed degenerate case*, and
the design §3.3 sentence is superseded by annotation in THIS record (design records are
frozen history; GOVERNANCE carries no move-to phrasing — verified — so no governance
motion rides M4).

**Mechanism.** One canonical pure derivation in `dependency.py`:

```python
@dataclass(frozen=True)
class MoveTo:
    version: str
    downgrade: bool          # True iff version orders below the pin
    guidance_only: bool      # True iff nothing is served (version is row.lower)

def derive_move_to(row: StandardPolicy, served: Iterable[str], pin: str) -> MoveTo
```

(version-ordered by `version_tuple`; `downgrade` compares tuples; `guidance_only` when
`served` is empty). The three gateway call sites pass their locally-derived served sets
(`served_versions` for dependency/matrix, `served_versions_from_corpus` for documents —
the corpus sources differ by design and stay per-surface; only the derivation
consolidates). Warning formatters append ` (a downgrade — no served version is newer)`
when `downgrade`, and label the empty-served fallback as guidance. The SDK re-implements
the ~10-line pure function (two-repo split; no import) — pinned to the gateway's format
by tests in both repos asserting the same literal expected strings (the existing
"pinned text-equal by test" posture `documents._vr37_text` already documents), plus a
gateway `tests/sdk/` arm running the SDK's derivation in-process at the new pin over the
degenerate fixture (the census harness pattern) once the pointer advances.

**Acceptance.** RED-ish (structure): `test_move_to_one_derivation_five_surfaces` —
table over {pin below all served; yanked pin above all served; served empty; yanked pin
mid-set}: the dependency warning, the documents note, the matrix yank cell, and (SDK-side
twin test) the SDK classification agree on both the version and the downgrade marking
(pinned as literal expected strings in both repos). New behavior arm:
`test_yanked_pin_above_served_set_warns_of_downgrade` (gateway + SDK twins). GREEN
controls: every existing move-to text test unchanged (the degenerate state is unreachable
on the real corpus — no current fixture has it, which is exactly why the five copies
could drift silently). **Kill:** any of the four table states disagreeing across
surfaces, or any existing move-to text changing (that would be a behavior change this
fold explicitly does not make).

### M5 — SDK marker/mirror cross-check — **BUILD (SDK slice)**

**Root cause, verified.** `standards_sync.py::_verify_self_consistency` →
`_verify_state` → `_verify_tree` verifies lock rows ↔ vendored bytes ↔ stamps only; it
never reads the `dependency_policy` mirror living in the same lock file. A yank-marker
flip in a lock row passes `sync-standards --check` green while the gateway's
`served_set_drift:` refuses the identical plant (A6 holds for row-level plants only).

**Mechanism.** Extend `_verify_state` (after `_verify_tree`) with an internal-consistency
pass over the lock alone, offline (no bundle, no gateway checkout): for each standard id
in the lock's rows, read the mirrored policy row and refuse `marker_mirror_drift:`
(a new machine-matchable prefix, same vocabulary family as `policy_mirror_drift:`/
`served_set_drift:`) when (a) a row's `yanked` flag disagrees with membership of
(id, version) in the mirror's yanked set — both directions; (b) a row's (id, version) is
named in the mirror's `retired` list (retired bytes must not be carried); (c) a row's
version falls outside the mirror's declared range (a narrowed range that did not drop its
rows) — range membership via a minimal interval parse reusing M3's canonical grammar and
`tuple` comparison (the gateway's `RANGE_PATTERN` grammar, re-implemented SDK-side the
way the counter twins split); (d) the active-marked row is yanked or out of range
(exactly-one-active stays `served.active_version`'s own refusal). The mirror-absent
shape keeps `served.py`'s existing `policy_mirror_absent:` posture.

**Acceptance.** RED (the drift lane's executed green-passing plant):
`test_yank_marker_flip_refuses_check` (flip `"yanked": true→false` on the otdp 0.2.1 row
in a temp checkout's lock → `--check` red, naming the row and the mirror's yanked set);
`test_retired_carried_row_refuses`; `test_out_of_range_row_refuses`. GREEN: the real
lock + tree checks clean; gateway-side check behavior byte-unchanged (no gateway file in
this slice beyond the pointer). **Kill:** either repo green with a marker plant.

### LOW verdicts

| # | Finding | Verdict / mechanism |
|---|---|---|
| 1 | §3.5 removal-point dissolution | **BUILD (records)** — one sentence here: design §3.5's "deprecation warnings name the removal point (the range's next lower bound after narrowing)" dissolved; the landed posture (move-to naming, M4's consolidated rule) is strictly more actionable and is the superseding definition. Annotation lands in the CON-14 amendment (`docs/internal/invariants.md`), which this fold already touches. |
| 2 | Ruling-artifact wording drift | **BUILD (records)** — the design §2 carrier says "gain the dated amendments in §5"; GOVERNANCE's lift says "in `docs/internal/invariants.md`", and the lines were rewrapped. Annotate in the same CON-14 amendment: the verbatim claim holds modulo rewrap + that one phrase; both texts are frozen history, the annotation is the disclosure. No GOVERNANCE edit. |
| 3 | GOVERNANCE promotion step-list omits record-append + landing_sha-fill | **BUILD (GOVERNANCE, the flagged standards-path commit G5)** — two clauses appended to the promotion paragraph (`standards/GOVERNANCE.md:197-210`): "append the promotion record (dev_edit_sha, dev_tree_digest via `dev_tree_digest_at`) in the promotion PR; fill `landing_sha` by the immediate post-landing append". Veto fallback: #288 sub-issue (§9). |
| 4 | Canonical numerals on policy status keys | **BUILD** — `_dependency_policy_from`'s key checks (`manifest.py:533/:567/:587`) move from `VERSION_PATTERN` (`\d+.\d+.\d+`, leading zeros pass) to a canonical-numeral pattern sharing `RANGE_PATTERN`'s segment grammar; `"0.02.1"` then refuses `dependency_policy_invalid:` at LOAD on the admission path too, agreeing with `validate_dependency_policy`'s export-time refusal. RED: plant a leading-zero yanked key in a temp corpus → admission path refuses (today it silently un-yanks). |
| 5 | `upgrade_lock` skips `_dev_head_state` | **BUILD** — one line: call `_dev_head_state(root, resolution)` in `upgrade_lock` after `resolve_package`, mirroring `pin_lock` (`dependency.py:1971`) and the check lane (`check.py:155`). RED: a dev-row package whose head moved, upgraded on a different standard — today re-locks green; after, refuses `dev_pin_drift:`. |
| 6 | `export_bundle` read-once | **BUILD** — thread the validated document: `export_bundle` reads `standards-manifest.json` bytes ONCE; `load_dependency_policy` gains a bytes-accepting internal (the root/corpus wrappers keep their signatures) and the verbatim block handed to `_policy_document` comes from those same bytes (the `Resolution` threading precedent at `dependency.py:992-1001` — no re-read window between validate and embed). RED: monkeypatched second read returning different bytes → detected/refused rather than silently embedded (assert the embedded block equals the validated one). **REFUTE-SLATE CORRECTION (2026-10-01, mech-F8/adv1-F6): the "bytes ONCE" claim overstated — the POLICY lane reads once (the embedded block comes from the validated bytes), but the FILE is read twice in total (the manifest lane's own load, then the policy read). The torn-window residual this leaves is disclosed: a concurrent write between those two reads is NOT caught at export — it is caught downstream by the SDK-side marker mirror (M5) and the gateway's `served_set_drift:` lane.** |
| 7 | Reversed/equal interval bounds parse clean | **BUILD** — `parse_interval` (`dependency.py:347-368`) refuses `constraint_bounds_reversed:` (equal or lower ≥ upper) at parse time, both in the constraints loader and `_parse_range` (manifest-side keys share the check via the loader family). RED: `">=0.3.0,<0.3.0"` and `">=0.4.0,<0.3.0"` refuse named (today: parse, then "no served version inside"). |
| 8 | validation-report regeneration content-unverified | **DON'T-BUILD (covered)** — the sweep sanctions the file's ADDITION; its CONTENT is verified by the existing family pin (`test_validation_report_matches_live_run` + tamper arms, obligation 13): a promotion landing makes its target the active version, whose committed report is byte-compared to a fresh live render in every CI run. A content-wrong regeneration reds the landing PR's own gates. Residual: none reachable (a promoted-but-never-active version is not the promotion flow — promotion IS the active bump, GOVERNANCE :197). |

### NIT dispositions (folded where the file is touched; none merits its own review surface)

1. "7 identifiers" prose slip (design §3.1's retired enumeration says 7; the enumeration
   lists 6 across 5 standards) — annotated here (frozen record, not edited).
2. Obligation-19 cross-references — the obligations file's rows read 19, 21, 20, 22 in
   file order (21's block sits between); G5's docs commit reorders the two blocks (no
   renumbering — numbers are cited elsewhere) and audits the two "obligation-19"-shaped
   references (`drift-and-obligations.md:414/:440`) while there.
3. CON-14 carries no inline date on the original row — the fold's CON-14 amendment
   carries its date and names the omission.
4. Design §3.1's `policy_change_unruled:` promise has no inline deferral note —
   obligation 21 already records it as D10; noted here (this record is the design-side
   pointer).
5. VR-37 field-five placeholder differs gateway ("migration guidance pending") vs SDK
   (the longer `MIGRATION_NOTE_PENDING`) — **accepted as-is, disclosed**: the SDK text
   names the mirror because it stands alone at plugin-author sites; aligning would churn
   pinned texts for no reader's benefit.
6. Stale "until slice 5" docstrings (`dependency.py:57`, `dependency.py:2001`) and
   `documents.py:559`'s "persistence and stamping land with slice 5" (slice 5 landed,
   #219) — corrected in the M4/LOW commits that already touch those files.
7. SDK `_move_to` docstring vs behavior — superseded by M4's new derivation + docstring.
8. Process-cached `lock_rows()` in editable checkouts (SDK) — fold into the SDK slice:
   key the cache on the lock file's `(mtime_ns, size)` so an in-process lock change is
   seen; RED arm edits the lock between two reads in a temp checkout.
9. Digest-reposition sibling of the disclosed identity false-accept — the M1 docstring
   gains the paired-digest disclosure sentence (a cross-file digest reposition now
   refuses by path mismatch; an unpaired real-digest append remains admitted, named).

### DOCS verdicts

- **(a) dev-head pinning how-to — BUILD.** Extend the existing four-class taxonomy
  section (`docs/device-developer-guide.md:167-206`) with the authoring story sourced
  from GOVERNANCE G-1 + design §3.6: opt-in authoring in
  `contracts/constraints.json`, `pin --opt-in <ID>=<LABEL>@<SHA>` (note the real flag
  spelling — verify against `__main__.py` at build time), digest-break semantics (the
  label is mutable, the pin is not; `dev_pin_drift:`), wheel refusal
  (`dev_head_unresolvable:` posture), one-head-per-standard.
- **(b) stale OTDP-0.2.0 guidance — BUILD.** `docs/device-developer-guide.md:123/:233/:658`
  and the `../standards/otdp/0.2.0/…` link family (the guide's corpus links point at
  0.2.0 while 0.2.2 is active and served — links resolve under copy-never-move but the
  guidance steers authors one version back); `docs/develop-your-device.md:7` (the review
  lane's `docs/devices/` prefix was itself stale — the file lives at `docs/`);
  architecture doc `:17/:271/:279`. Rewording targets "a served version (0.2.2 active;
  0.2.0 remains served)" and links re-pointed at the active corpus paths. **These are
  docs-scope literal edits: the commit MUST regenerate
  `scripts/standards/docs-literal-baseline.json` via `--refresh-docs-baseline`, and that
  refresh diff is the review surface (obligation 18m/20).**
- **(c) SDK doc surfaces — BUILD (SDK slice).** `user_guide/plugin-sdk.qmd` gains a
  per-pin validation / served-set / lock section including `version_not_served:` and the
  yanked-pin warning with the M4 downgrade label; README gains the per-pin validation
  bullet; `index.qmd:3`'s "SDK 0.1.0" claim (pyproject says 0.4.0) drops the self-version
  (prose defers to the machine source — the SDK's own counter does not gate `index.qmd`,
  verified, so no ratchet rides).
- **(d) site CLI reference blind to the argparse family — SPLIT.** The in-repo half
  lands now: `docs/operator-guide.md`'s CLI reference (obligation 4's named surface —
  verified today to carry NO standards-family coverage) gains a compact
  `python -m benchweave.standards` table (export/check/matrix/versions/repin/list/pin/
  upgrade/why, one line each, `--help` as the authority). The SITE page
  (`reference/cli/index.html`, generated from the Click tree) structurally cannot see
  the argparse family — extending that generator is its own slice with its own drift
  surface, **deferred as a #288 sub-issue (§9)**.

---

## 2. Slice and commit structure (SDK-first two-repo order)

**SDK repo, branch `feat/issue288-spec09-review-fold`** (one PR, stacked if any sibling
is in flight):
- **S1:** M3 + M5 + NIT-8 (`served.py`, `standards_sync.py`, tests) — the SDK lock
  integrity slice. One reviewable increment; per-finding RED evidence in the message.
- **S2:** M4-SDK + DOCS-c (`served.py` derivation + `user_guide/plugin-sdk.qmd`,
  `README.md`, `index.qmd`, tests).

**Gateway repo, branch `feat/issue288-spec09-review-fold`:**
- **G1:** this design record (the branch's first commit).
- **G2:** M1 + M2 (`promotion.py`, `tests/standards/test_promotion.py`) — the promotion
  trust boundary, one slice.
- **G3:** M4 gateway (`dependency.py` `derive_move_to` + `documents.py` ×2 +
  `matrix.py` + docstring proof→definition + the stale-slice-5 docstrings riding the
  touched files + tests incl. the five-surface table).
- **G4:** LOW batch (4/5/6/7: `manifest.py` numerals, `dependency.py` `upgrade_lock` +
  `parse_interval`, `export.py` read-once) — ONE commit, per-row RED evidence in the
  message (the fold-wave pattern), plus `documents.py:559`'s stale comment.
- **G5:** GOVERNANCE step-list (LOW 3) — the flagged single-file `standards/` commit.
- **G6:** docs (DOCS-a/b/d-in-repo + `docs/internal/invariants.md` amendments [CON-7
  sweep/trigger, CON-14 move-to/date/dissolution/verbatim-drift] +
  `drift-and-obligations.md` [obligation 21's SDK-side marker-check sentence; NIT-2
  reorder]) + the `--refresh-docs-baseline` regeneration.
- **G7:** SDK submodule pointer advance (after the SDK PR merges).

Gates per CLAUDE.md #247: fast lane every commit (bare ruff, fresh-cache bare mypy,
focused pytest + `tests/standards/`), full battery once before push; SDK PR opens at S1
push time, not at end-of-run (AGENTS.md).

## 3. Pre-committed acceptance rules (summary table)

| Rule | Metric | Ship | Kill | Underpowered |
|---|---|---|---|---|
| M1 | 3 executed attacks refuse; 3 GREEN controls stay green (real-tree control = 0 offending lines, DESIGN-MEASURED pre-fix over 30 changed lines) | all 6 | any attack passes, or founding control reds | n/a (deterministic fixtures) |
| M2 | laundered-source arm refuses; organic-successor + honest-record + real-tree (17 organic / 1 recorded, DESIGN-MEASURED) stay green | all 4 | any organic false-refuse | n/a |
| M3 | malformed row versions refuse typed on both SDK load paths; real lock clean | 3 arms green, 2 RED proven | any traceback over lock bytes | n/a |
| M4 | four-state table agrees across 4+1 surfaces (literal expected strings both repos); all existing move-to texts byte-unchanged | table + controls | any surface disagreement or any existing text change | n/a |
| M5 | marker flip / retired-carried / out-of-range refuse SDK-side; clean lock green; gateway unchanged | 4 arms | either repo green with a marker plant | n/a |
| LOWs | one RED arm each (4/5/6/7); LOW 8 DON'T-BUILD by coverage argument | arms green pre-merge | any arm that passes both ways | n/a |

All RED proofs run before the fix lands on its branch (G3-sanity: revert the production
line in place, show the new test red, restore, show green; collected counts read from
junitxml, never a filtered summary).

## 4. Invariant impacts

- **CON-7 amendment** (in G6): the promotion sweep's line rules tightened (token
  fast-admit deleted — admission is identity-residual equality, verified digest
  re-stamps with same-path pairing, or the sanctioned regeneration) and the no-record
  trigger gains its object-store derivation alongside the `-dev` citation. Append with
  evidence; original text untouched.
- **CON-14 amendment** (in G6): the move-to derivation is ONE canonical pure function
  (`derive_move_to`) consumed by every gateway surface, re-implemented SDK-side and
  pinned by twin tests; the design §3.5 removal-point sentence is recorded as dissolved
  by the landed move-to posture (LOW 1); the ruling-carrier verbatim claim carries the
  rewrap + "§5"→invariants-path annotation (LOW 2); the row's missing inline date noted.
- **No CON row weakens.** CON-12 (matrix purity — `matrix.py:275` changes its
  derivation input handling only, committed-state reads unchanged), CON-4 (the SDK-side
  check gains arms; prefixes stable), CON-10/CON-1 untouched. No new invariant row is
  needed — the folds tighten existing mechanisms.
- **GOVERNANCE:** LOW 3's two clauses (G5, flagged).

## 5. Top risks — and what an adversary attacks first

1. **M1 over-tightening a future legitimate sweep.** A future promotion whose diff
   contains a line class the founding record did not exercise (e.g. a multi-digest line,
   or a legitimately unpaired digest change) reds the sweep. FALSIFIER: the fixture
   green-spine + real-tree controls in the same suite; the refusal message names the
   line, so a new class surfaces as a named refusal, not a silent pass.
2. **M2 history cost/fragility in shallow contexts.** `git log` per retained dir; a
   shallow clone refuses `promotion_history_unavailable:` (loud, by design — same
   posture as the founding record's own object-store reads). FALSIFIER: CI runs full
   clones today (the founding-record test already requires main ancestors).
3. **M4's label text becoming a pinned cross-repo contract.** The literal expected
   strings in both repos must move together if the wording ever changes. Mitigation: the
   twin tests ARE the contract; a wording change is a two-repo change by construction
   (the counter-twins posture).
4. **M5's range parser drifting from the gateway's.** A third grammar copy. Mitigation:
   the canonical-numeral constant is shared SDK-side (M3) and the gateway grammar is
   pinned by its own tests; a drift surfaces as marker_mirror_drift false-refusals on
   the next sync — loud, not silent.
5. **The GOVERNANCE commit tripping the tripwire unnoticed.** It is designed as G5,
   single-file, named in the PR body as the fold's only `standards/` motion; the push
   tripwire firing there is the expected, owner-gated event.
6. **Adversary's first move:** promote a real head with rows citing the released
   predecessor (M2's history trigger must catch it — the on-main-head RED arm); or edit
   a schema line that mentions a version (M1's identity rule must refuse — the semantic
   RED arm); or swap two real digests inside one example file (M1 pairing must refuse).

## 6. CI cost

No new lanes. ~20 new gateway tests + ~10 SDK tests, seconds-scale; the M2 history walk
adds ~17 fast git-log subprocess calls inside existing suite tests (DESIGN
estimate; MEASURED at fold time: ~34 history-walk subprocesses per
real-tree validate — 1 rev-parse, 17 introducing-commit logs, 16
parent-manifest reads, plus the shallow probe the refute slate added —
inside ~75 total subprocess calls and ~0.8s wall for the whole
validate including the founding-record sweep); the docs-baseline
refresh is a generated artifact regenerated in G6.

## 7. What this fold defers (sub-issue payloads — the owner's no-silent-deferral rule)

| Deferred | Sub-issue body must carry |
|---|---|
| Site CLI reference for the argparse `benchweave.standards` family (generator extension or hand-written derived page + its own drift obligation row) | **Carrier:** `scripts/assemble_docs_site.py`'s `reference/cli` page + this record §DOCS-d; the in-repo operator-guide table (G6) is the landed half. **Reopen trigger:** the next docs-site work session, or the owner's call to surface the family publicly. |
| GOVERNANCE step-list clauses, IF the owner vetoes G5 | **Carrier:** this record §LOW-3 + `standards/GOVERNANCE.md:197-210`. **Reopen trigger:** the owner's word on the `standards/` prose motion. |

## 8. Disclosed unverified

- The `pin --opt-in` flag spelling in DOCS-a is quoted from the design §3.6 and the M2
  site inventory; the builder verifies against `standards/__main__.py`'s argparse
  definitions before writing the guide text.
- The docstring-count estimates in the keyword scan are design-time estimates over the
  expected diff inventory; the review re-runs the scan over the real diff.
- SDK-side test-file names are new (the SDK repo's existing served/sync test modules are
  the homes; exact file boundaries confirmed at build time).

---

*Design record for issue #288. Commit 1 of `feat/issue288-spec09-review-fold`. The
reviewed arc's design record (`docs/implementation-planning/09-…`) is frozen history;
every supersession here is by annotation, never in-place edit.*
