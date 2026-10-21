# Name screen for the public repository — design record

Tracker: madeinoz67/benchweave#518 (single issue stream; gateway-only diff)
Date: 2026-10-21 · Branch: `fix/name-screen` (off `origin/main` at `5ff6668b`) ·
Status: PRE-COMMITTED — the acceptance rule in §7 was written and committed before any
measurement in this arc ran.

## 1. Root cause

CLAUDE.md §4 ("This repository is public") forbids naming a real bench, client or
operator in source, tests, comments, design records, commit messages and filenames, and
says getting it right before the commit is the only version that works — git history is
forever. Enforcement today is prose and shape:

- Review rubric G0 (`docs/internal/review-rubric.md`) scans secret literals and private
  paths only, and it is an agent-run instruction, not a command — a reviewer who never
  runs it ships nothing detectable.
- `privacy-screen.mjs` is wired only into measurement-report delivery; it sees
  mechanical shapes (emails, home paths, addresses, serial-like strings), and a plain
  name has none of those shapes.
- No `.pre-commit-config.yaml` exists; the CI map has no content-screen job.

The class that passes every gate today: a real name as plain prose in a fixture, test
name, comment, commit message or filename — no email shape, no path shape, no serial
shape. Nothing mechanical looks at it, and no machine boundary refuses it.

## 2. Mechanism — a two-tier screen whose failure mode is BLOCK

New committed `.claude/hooks/name-screen.mjs`, node stdlib only, exit 0 PASS / 3 BLOCK.

- **Tier P (public, listless):** the privacy screen's deterministic pattern classes
  (email, home path, hex dump, MAC, IPv4, serial-like) plus G0's secret-literal shapes
  (`mk_`, `mdb_`, `gorag_`, `ghp_`, `github_pat_`, `sk-`, Bearer-token forms — matched
  as prefix-plus-tail shapes, not bare prefixes, so the rubric's own prose that names
  the prefixes cannot self-trip the screen), run over content AND filenames. This makes
  G0 machine-run for the first time.
- **Tier L (local list):** plain names at `$BENCHWEAVE_NAME_LIST`, default
  `~/.config/benchweave/name-screen.list` — outside every repository of the family, so
  the list itself can never land in one. One name per line, minimum length 4,
  case-insensitive substring. List absent → the tool prints "public tier only" and
  continues; it is never silent about which tiers ran.

**The screen never prints matched text.** A block cites `file:line` (or the surface
label `filename` with the input ordinal, when the filename itself is the match — a
filename citation would quote the very thing being refused) plus the pattern id or the
list-entry index. A screen whose block message restates the leak is a second leak; this
one structurally cannot quote its own matches.

Names split across lines are missed (substring per line), and blobs over 1 MiB are
scanned only to the first 1 MiB with the truncation announced — both disclosed residuals,
not silent behavior.

## 3. Three wirings

1. **Authoring time (every clone):** a second PreToolUse `Edit|Write|MultiEdit` entry in
   tracked `.claude/settings.json` — the gortex-write-gate pattern (#508) — running
   `name-screen.mjs --pretooluse`. Deny is exit 2 (the PreToolUse block code); the
   module's CLI contract stays 0/3 and the hook mode is the wiring's own translation,
   the same `--hook` posture `memory-drain.mjs` uses.
2. **Commit/push time (opt-in per clone):** committed `.githooks/pre-commit` and
   `.githooks/pre-push`, installed by `make hooks`, which sets repo-local
   `core.hooksPath=.githooks`. Allocation of the scanned surfaces:
   `pre-commit` → staged added content + staged filenames; `pre-push` → the pushed
   range's added-line diff, every commit message in the range, and the changed
   filenames in the range. The publication boundary is the push; a name in a commit
   message that is never pushed never left the machine. `make hooks` ALSO installs
   chain shims `.githooks/post-commit` and `.githooks/post-merge` that exec the
   global-hooksPath hooks when one is configured — required because the owner machine
   runs gortex's post-commit/post-merge from a global `core.hooksPath`, which a bare
   local override would silence.
3. **CI (the bypassed-hook path):** a `name-screen` job running tier P over the PR
   added-lines diff (`git diff --unified=0 <base>...HEAD | name-screen.mjs --diff`).
   Tier L does not run in CI (deferral D2). The branch that lands this screen is
   itself green under it: the test corpus builds its tier-P canaries by assembly, so
   the suite's own added lines never carry the shapes it refuses.

## 4. Alternatives rejected

- **A committed digest set** (store hashes of the names, match by hashing the diff) —
  a guess-confirmation oracle: hash a guess, compare. It confirms the very names it
  hides, to anyone with the list's hash set and a candidate. Rejected on that ground
  alone.
- **A judgment layer in the gate** (an LLM or service verdict) — the gate's egress
  sends text externally before any verdict exists, and its clean-fallback path wedges
  every offline push. The privacy screen can afford both because it gates one outbound
  document; a commit-time gate cannot.
- **Shape heuristics alone** — they cannot see a class that has no shape. A plain name
  is exactly the shapeless class. Two-tier wins: precise where the list can live
  (tier L), mechanical everywhere (tier P).

## 5. Scope

In scope: `name-screen.mjs` and its tests in `.claude/hooks/tests/`; all three wirings
(the settings entry, `.githooks/` + `make hooks`, the CI job); the G0 amendment naming
the client/bench/operator class and the machine command; a one-line pointer at
CLAUDE.md §4's close; a new drift-and-obligations row plus a CI-map row; an install
step in AGENTS.md.

Known at design time: the `.codex` rubric mirror is untracked local tooling on the
owner machine (0 tracked files — the #254 record's census), so the committed G0
amendment lands in the tracked rubric only and the mirror's refresh is an owner-side
follow-up, not a commit.

### Deferrals

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D1 | SDK and registry repo wiring (their own hooks/jobs/CI) | follow-on issue on the single tracker, filed when this lands | a PR in `benchweave-sdk` or `benchweave-registry` touching hook wiring or their CI files — the first sibling-repo change that should have carried the screen |
| D2 | CI tier L via Actions secret | documentation here | an Actions capability change (GitHub changelog entry) that exposes secrets to fork-PR read-only steps without a new exfiltration surface, or the owner's explicit call to accept same-repo-branch exposure |
| D3 | optional `--semantic` pre-push mode | documentation here | a recorded miss in the tracker where tiers P and L both passed a name a semantic pass would have caught on this repository's diff |
| D4 | scheduled full-history re-scan | documentation here | any history-audit hit outside the screen family's own synthetic-canary class (§7's one-shot audit), or the owner's explicit call |
| D5 | operator-doc mention of `make hooks` | documentation in `docs/operator-guide.md` | the list distribution to all three developers completing (maintainer decision 1) — the moment the list exists out of band, the install step is load-bearing |

## 6. Honest residual

- A list-holder who bypasses their own pre-push (`--no-verify`, or never running
  `make hooks`) can still publish a name. The screen is an accident barrier, not an
  adversary barrier; it is not aimed at a malicious actor inside the trusted ring.
- A name missing from the list is invisible to every tier — tier L is exactly as good
  as its list.
- Names split across lines, and content past the first 1 MiB of a blob, are missed and
  the miss is reported.
- CI runs tier P only; the PR-added-lines screen does not run tier L (D2), so the
  bypassed-hook path is pattern-class only.
- There is no integrity pin on the screen itself: a PR that only neuters
  `name-screen.mjs` carries no name-shaped content, passes the honest base copy's
  screening, and becomes the base for every later PR — human review of a hook diff is
  the only catch (next to the first-landing fallback note in the CI job).
- Letter-only asset tags (a serial with no digit in the tail) pass by design — the
  serial class requires a digit, accepting that narrow miss so "serial attachment"
  prose does not block.

## 7. Pre-committed acceptance rule

Written before any run. Kill conditions are absolute; "close enough" is not a verdict
here, because a screen with a hole or a screen that blocks normal work both get
uninstalled — which is how screens die.

Synthetic corpus: 12 obviously-invented org/bench names planted in a temp list; 24
negatives drawn from real project vocabulary (the project's own name, OTDP, existing
fixture names, the phrase "a real bench"); 8 pattern cases (fake home path, email,
serial-like, and so on). Every canary is invented — a canary that is a real name is
the leak this increment exists to stop.

- With the list present: BLOCK 12/12 planted across all three surfaces (staged
  content, commit message, filename = 36 block cases total). Anything under 36/36
  KILLS.
- PASS 24/24 negatives. Any false block KILLS.
- With the list absent: those 36 must pass tier L while the 8 pattern cases still
  BLOCK 8/8, proving the public tier runs independently rather than going blind.
- RED: removing the list makes the planted names pass — the effect belongs to the
  mechanism, not the test rig.
- "0 cases collected" is INVALID, not a pass (CLAUDE.md §3.3). Only the 8-case arm can
  be underpowered.
- CI RED/GREEN: a branch adding a fixture with a synthetic home path must redden the
  `name-screen` job; without it, green.
- Canary-leak proof: every canary is invented, and the no-matched-text property is
  itself asserted — output carries the entry index, never the planted string.
- One-shot history audit over the full log (tier P, no list — none exists yet): the
  public record carries the COUNT only; any hit's detail goes to
  `.claude/deep-review/private/` exclusively. Expectation: 0 hits. A hit fires D4 plus
  owner escalation rather than killing the mechanism.

## 8. Risks, with falsifiers

- **Hook fatigue / uninstall** — held by the 24/24 zero-false-block bar and sub-100 ms
  runtime (measured on the dev machine at acceptance time and recorded in §10).
- **A local hooksPath override silencing the global gortex hooks** — chain shims
  (§3.2); falsified by a hermetic harness (temp HOME with a global hooksPath) plus the
  owner's own test commit after `make hooks`.
- **Stale list** — the list lives outside the repos; staleness is invisible to the
  screen. Mitigation is process (the maintainer decision-1 distribution), not code;
  named here because "the screen passed" can otherwise be read as "the list is
  current".
- **Substring false positives** — an entry that collides with project vocabulary
  blocks ordinary work; held by the 24/24 bar over the real vocabulary corpus, and by
  the list's documented minimum length 4.
- **The list file itself landing in a repo** — its default path is outside every
  repository of the family, and no wiring reads a repo-relative path.

## 9. Maintainer decisions (not made here; the build blocks on neither)

1. How the list is distributed to the three developers out of band.
2. Whether the one-shot history audit runs before merge — this arc assumes NO list
   exists yet, so the public tier stands alone and every run must behave correctly
   with the list absent.

## 10. Design-time tier call (issue #254)

Tier: **Tier 2** by the default rule (`.github/` and root config are in the Tier-2
set; no Tier-3 path rule or keyword matches). Step-1 keyword scan over the expected
diff (this record, the hook, the hooks, the tests, the CI job, the docs rows):
`threading` 0, `asyncio` 0, `subprocess` 0, `sha256` 0, `hashlib` 0, `migrate` 0,
`recovery` 0, `protection` 0 — 0 hits for all eight. The enumeration in this
paragraph is the scan statement itself (the rubric's intended self-fire); the
expected diff text outside this paragraph is written to carry none of the eight.
The review re-derives the tier independently.

## 11. Run record

Numbers only, per §7. Suite: `.claude/hooks/tests/name-screen.test.mjs` (16
tests) + `name-screen-wiring.test.mjs` (8 tests); every count below is read
from the suites' own tally asserts and the runner's counts (`tests/pass/fail`),
never from a summary line.

- Planted blocks: **36/36** at the CLI surfaces (12 names × content,
  message-shaped text, filename) and **36/36** through the real hook scripts
  (staged content via pre-commit, commit message via pre-push range, staged
  filename via pre-commit — each case asserted to carry "name-screen: BLOCK"
  so a missing script's exit 127 cannot count).
- Negatives: **24/24** pass (no false block on project vocabulary).
- Pattern cases: **8/8** BLOCK with the list absent, 8/8 with it present —
  the public tier runs independently.
- RED arm: with the list removed the same 36 planted cases PASS (36/36) —
  the effect belongs to the list, not the rig. Suite-level RED: the
  acceptance suite against the absent module ran 16 tests / 2 pass / 14
  fail (12 × "Cannot find module"), exit 1; the wiring suite against the
  absent wirings ran 8 tests / 1 pass / 7 fail, exit 1.
- CI arm (the job's exact pipeline, run locally over a temp repo's range):
  planted added line → exit 3; clean range → exit 0. The branch's own
  added-lines diff under the same command: PASS (see below).
- Canary-leak proof: asserted per block case — output carries `id=` or
  `entry=`/`surface=filename ordinal=`, and the suite fails if any planted
  string appears in any output.
- Runtime (dev machine, whole process incl. node startup, best of 4):
  64 KiB blob **70 ms**, 1 MiB blob **85 ms** — under the 100 ms bar.
- **History audit: expectation 0 was wrong.** 2112 commits scanned (tier P,
  no list): 268 hits — 211 content, 57 message; by class (content+message):
  serial_like 91, email 76, ipv4 72, home_path 17, hex_dump 12. Sampled
  characterization: platform noreply/trailer addresses, doc-fixture domains,
  reserved documentation address ranges, fixture serials — intentional
  public content, no sampled person/client/bench identifier; tier P cannot
  distinguish fixture from real by shape, so confirmation is the owner's.
  Detail (citations only, no matched text) is in
  `.claude/deep-review/private/2026-10-21-issue518-audit-hits.txt` with a
  triage note beside it. Hits outside the screen family's own canary class
  fired **D4 + owner escalation**, as pre-committed — the mechanism stands.

### Design vs contact (what the build found)

- **PreToolUse deny needs exit 2**; the CLI contract is 0/3. The wiring is a
  `--pretooluse` mode that translates (deny = 2), the same `--hook` posture
  `memory-drain.mjs` uses — consistent with §3.1's "gortex-write-gate
  pattern", now stated precisely.
- **The `.codex` rubric mirror is untracked local tooling** (0 tracked
  files; the #254 record's census) — the G0/G0b amendment lands in the
  tracked rubric only; refreshing the local mirror is an owner-side
  follow-up, disclosed here instead of a commit that cannot exist.
- **Commit-message screening sits at pre-push, not pre-commit.** The design
  enumerates four surfaces across the two hooks without allocating them;
  the build allocates messages to the push boundary (a never-pushed local
  message has left nothing) and keeps pre-commit to staged content +
  filenames — reading `COMMIT_EDITMSG` at pre-commit time would screen a
  stale file from a previous commit and false-block.
- **The screen's own test corpus needs no exemption.** The suite assembles
  its tier-P shape canaries at runtime, so its committed bytes never carry
  the shapes it refuses — the branch is green under its own CI job with no
  self-exemption list to launder a leak through.

## 12. Fold record (adversarial review, 2026-10-21 — NOT DEFENDED → folded)

Seven findings, all folded. Per-finding RED (against the first build) and
GREEN (against the folded build), from the fold suite's own run counts.

- **F1 hunk poisoning (HIGH).** An added line whose content begins "++ "
  renders as a file-header-shaped line and was parsed as one: the rest of
  that hunk was skipped by both tiers, and the refuter got an email, a home
  path, a serial and a Bearer token through `.githooks/pre-commit`
  verbatim. Fix: header position is real state — a header-shaped line is a
  header only outside a hunk; inside one, a `+` line is content whatever
  follows, and the no-newline marker never counts as a context line. RED:
  the poisoned hunk passed (exit 0) with all four shapes and both list
  names in it. GREEN: 5 hits + "and 1 more", correct new-file line numbers
  past the poisoned line (pins: the exact poisoned shape).
- **F2 tier P blocked the repository's own vocabulary (MED-HIGH).** 157
  loopback occurrences alone; the operator guide instructs a loopback
  bind; example domains, documentation ranges and version-shaped
  four-part strings all blocked. Before: 57 of 674 tracked files in the
  swept roots carried hits (189 total: ipv4 154, serial_like 19, email 10,
  home_path 6; the refuter's whole-tree figure was 122 of 1432). Fix: a
  measured allowlist (loopback, RFC 5737 documentation ranges, example
  domains, version-shaped four-part strings — leading-zero, out-of-range or
  first-octet-zero quads — scp-style git URLs), a digit
  requirement on serial tails ("serial attachment" is prose), and the
  pinned tracked-tree sweep below. After: zero unpinned hits over the same
  674 files; 19 pinned hits in 6 files (both-direction ratchet).
  **Correction to the pre-committed rule, stated as a correction:** the
  §7 "24 negatives" arm was under-powered — it omitted the commonest
  forms in this repository. The negatives bar is now the tracked-tree
  sweep over `docs/`, `src/`, `packages/`, `tests/`: zero blocks outside
  the pinned table, any residual named with its justification. The 24
  invented-word negatives remain only as the tier-L interaction arm.
  The pinned table's two home-path rows are OWNER-TRIAGE (pre-existing
  private-path occurrences in tracked public content, same class as the
  §11 audit) — listed so they cannot be widened away, removed only by an
  owner decision.
- **F3 the block message could quote the leak (MED).** `src=` printed the
  path when the path did not exactly contain the list entry — a spaced
  entry vs a hyphenated filename leaked the name in the citation. Fix:
  inflection-tolerant (canonical) matching for path hits AND for the
  hot-path decision that suppresses `src=`; leak-needle assertions extend
  to spaced/hyphenated/underscored/dotted inflections. RED: the hyphenated
  filename arm's output carried the name. GREEN: every inflection hits the
  filename surface (ordinal citation) and none of them appears in any
  output.
- **F4 publication-boundary gaps (MED).** (a) commit messages screened
  only at pre-push — a `--no-verify` push published them uncaught; the CI
  job now screens `git log --format=%B <base>..HEAD`, and the CI-map row
  says so. (b) branch-creation pushes exited 0 unscreened; the job now
  screens against the default branch, and the one residual (the first push
  of the default branch itself — no base to diff) is disclosed in the
  CI-map row rather than omitted. (c) the job ran the PR's own script —
  a PR could neuter the screen and pass; the script is fetched from the
  BASE side (`git show <base>:…`), with a notice-and-fallback only where
  the base predates the screen's first landing. RED: the workflow text
  lacked all three; GREEN: pinned by text arms plus a local run of the
  message pipeline (exit 3 on a planted message).
- **F5 present-but-unreadable list (LOW-MED).** a directory or unreadable
  file degraded to "no name list", misdescribing an opted-in but broken
  setup. Posture, chosen explicitly: an EXISTING but unreadable list
  BLOCKS (fail closed where the operator opted in); a list that does not
  exist passes on the public tier, announced. RED: a directory list passed
  silently; GREEN: exit 3 with "name list present but unreadable".
- **F6 home class naming (LOW).** the class missed windows drive homes,
  lowercase `/users/`, and a bare tilde-name home. Widened (all three hit now; the tilde
  form requires a trailing separator so typing annotations and
  approximations do not match — measured on this tree's own `~`-prose).
- **F7 audit reproducibility.** The §11 audit ran through a one-shot
  script, not a committed command. The exact invocation, for
  re-derivation of the 268 count: for every commit `C` in
  `git rev-list HEAD` (2112 at the run), diff `C^..C` (empty-tree for
  roots) with `--no-renames --unified=0 --diff-filter=ACM` piped into
  `name-screen.mjs --diff`, and `git log -1 --format=%B C` piped into
  `name-screen.mjs --text`, each with `BENCHWEAVE_NAME_LIST` pointing at
  an absent path (tier P only); any non-zero exit is a hit, recorded with
  its commit sha and citation lines in the private hits file. Author
  headers deliberately excluded (committer identities are public by
  choice).

## 13. Re-fold record (second refutation, 2026-10-21 — all four folded)

- **FOLD-A anchors + bare tilde.** The anchor set was closed and real
  paths abutted by `> * @ ~ ! ? + ] } |` and the map/separators passed;
  bare tilde-name homes (no trailing separator) passed. RED: the anchor pin
  failed on those characters and on the bare tilde form. GREEN: the
  ANCHOR RULE, stated in the code — a home-path candidate must BEGIN at
  a token boundary (start of line, whitespace, or one of the punctuation
  characters above); a path inside a longer token never matches, because
  the character before it is a word character or a slash. The tilde form
  is a maximal name run not continuing as dot-plus-letter (typing
  annotations are not homes); the narrowing this accepts: a dotted
  personal name is indistinguishable from a typing annotation and is
  missed, and the repo's approximation notation (a tilde before an
  ordinary word) is indistinguishable from a bare home reference — 13
  such hits in 8 files are PINNED in the tracked-tree sweep table with
  that justification, never silently allowed. All anchor characters are
  pinned individually in the suite.
- **FOLD-B git@ hosting scope.** The scp-URL exemption keyed on the
  local part alone, so a client hostname walked in as a "git URL". RED:
  a client-identifying git@ host passed. GREEN: the exemption is
  HOSTING-scoped (an explicit hosting-domain allowlist); any other git@
  domain is an ordinary email candidate. Both directions pinned.
- **FOLD-C filename wirings (merge hold).** Binary adds and
  mode-change-only entries carry no file headers, so the diff leg never
  screened their names — the filename claim failed on 2 of 3 wirings.
  RED: a binary add and a mode-only change passed pre-commit and the CI
  command with canary names. GREEN: the diff parser registers the b-side
  path from the `diff --git` line itself (binary/mode entries carry that
  even with no hunk), AND pre-commit + the CI job screen the changed-file
  LIST through the same `--paths` arm the pre-push leg uses. Both cases
  pinned end to end through the real hook and the CI command shape.
- **R2b unreachable claim.** The header claimed "version-shaped
  four-part strings" are allowlisted while the branch keyed only on
  out-of-range groups the regex never yields. RED: the leading-zero
  version shape still blocked. GREEN: the branch is REACHABLE — the
  version rule is exactly leading-zero, out-of-range or first-octet-zero
  quads — and the header claim now names that mechanism. A clean
  routable quad with no leading zeros still blocks (pinned).
- **DISCLOSE-D** landed as the two §6 residual sentences: no integrity
  pin on the screen itself (human review of a hook diff is the only
  catch), and letter-only asset tags pass by design (the serial class
  requires a digit).

