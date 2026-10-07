# Issue #422 increment 1 — env-file autoload for `serve`, one standard across both CLIs

**Date:** 2026-10-07
**Issue:** madeinoz67/benchweave#422 (increment 1 of 4: env autoload → supervision/stop-semantics record → lifecycle verbs → doctor/logs)
**Verdict:** BUILD (both surfaces, twin implementations; forks in §11)
**Status:** design record — not yet reviewed, not yet built

---

## 0. Premise correction the code forced (read this first)

The dispatch brief and the issue body describe `<data-dir>/benchweave.env` as "the env
file `setup` writes", parallel to systemd's `EnvironmentFile`. Reading the tree corrects
two load-bearing details:

1. **`benchweave.env` IS the credential file — nothing else.**
   `src/benchweave/cli/atrest.py:88` — `CREDENTIAL_FILE = "benchweave.env"`;
   `_write_credential_file` (atrest.py:164) writes exactly one line,
   `BENCHWEAVE_SECRET=<token_urlsafe>\n`, mode 0600 (Windows: owner-only ACL,
   atrest.py:190). `setup` never writes `BENCHWEAVE_DB`, `BENCHWEAVE_ENV`, host, or
   port into it. The file is deliberately never backed up or restored (atrest.py
   module docstring; `verify`'s `_UNLISTED_OK` tolerates it as live-state).

2. **There are TWO files named `benchweave.env` in the operator story.** The systemd
   unit's `EnvironmentFile={{ENV_FILE}}` (deploy/systemd/benchweave.service.template,
   rendered to `/etc/benchweave/benchweave.env` by the example) is a hand-authored
   deployment file carrying ENV/DB/HOST/PORT/SECRET/UI. The data-dir file is
   setup's secret carrier. Same filename, different files, different writers.

The increment therefore is NOT "serve reads its config file" — it is "**serve
auto-bridges the credential file** (and any operator-added service keys) into the
process environment, set-if-not-set". That is precisely the pain the issue names
(operator-guide.md:176–181, the grep/cut/export dance), and it is all the issue's
increment 1 asks for.

## 1. Root cause, traced

`benchweave serve` (src/benchweave/cli/commands.py:745) calls
`app_entry.build()` (src/benchweave/interfaces/app_entry.py:271 `build`), which reads
`os.environ["BENCHWEAVE_DB"]` (required — the KeyError becomes serve's typed refusal,
commands.py:759-763) plus `BENCHWEAVE_SECRET/ENV/FIXTURES/REGISTRY_DIR/UI` and the
seven quota keys. Nothing between the shell and `build()` ever looks at
`<data-dir>/benchweave.env`, so the secret setup wrote to disk is invisible to serve
unless the operator bridges it (operator-guide.md §3, the `export
BENCHWEAVE_SECRET="$(grep … | cut …)"` line) or the service manager injects a whole
second file (systemd). Verified: no other reader of `CREDENTIAL_FILE` exists besides
`atrest.read_secret` (setup `--show-secret`).

The chicken-and-egg the brief flags is real but already half-solved in-tree:
**`BENCHWEAVE_DATA_DIR` exists today** as the click `envvar` backing `--data-dir` on
every at-rest command (commands.py:81,154,206,233,373,455,571; operator-guide.md:107).
`serve` is the one command outside that family. Extending the existing locator to
serve — rather than inventing a new one — resolves the bootstrap: the data-dir locates
the file; the file never needs to locate itself.

## 2. Mechanism (gateway `benchweave serve`)

### 2.1 Where it hooks

Inside the `serve` command body, BEFORE `app_entry.build()` and AFTER click has parsed
options. NOT inside `build()` and NOT at CLI-group level:

- `build()` stays pure env-in → app-out. The module docstring promises "reading its
  inputs from the environment so a child process can run the real app"; bare
  `uvicorn benchweave.interfaces.app_entry:app` deployments keep that contract.
- Group-level loading would inject env into at-rest commands (`report`, `retention`,
  `dispose` read their own `--data-dir`/env today) — silent behavior change, refused.
- The issue's scope is serve; autoload is a serve affordance.

### 2.2 Locator resolution (the chicken-and-egg, resolved)

`serve` gains `--data-dir` (`type=click.Path(path_type=Path)`, `envvar="BENCHWEAVE_DATA_DIR"`,
help `_DATA_DIR_HELP`) — the exact in-tree pattern of the seven at-rest commands.
Resolution order, first match wins:

1. `--data-dir` flag (explicit; click already prefers it over its envvar)
2. `BENCHWEAVE_DATA_DIR` process env
3. `BENCHWEAVE_DB` process env → data-dir = `Path(db).parent()` (today's only path;
   legacy, byte-for-byte preserved when no file is present — see 2.6)
4. none → today's typed refusal, message extended to name the two new locators

Conflict rule: if (1) or (2) resolved a data-dir AND `BENCHWEAVE_DB` is set in the
process env and `Path(os.environ["BENCHWEAVE_DB"]).resolve().parent() !=
data_dir.resolve()` → typed refusal `serve_locator_conflict:` naming both paths.
Compare resolved (a relative `--data-dir` must not false-conflict; the
`_integrity_problems` resolve() precedent, atrest.py:498-500).

Derivation: when the locator is (1) or (2) and `BENCHWEAVE_DB` is unset after
autoload, derive `BENCHWEAVE_DB = data_dir / atrest.DB_NAME` (`"state.sqlite"` — the
at-rest layout contract). Guard: if that file does not exist → typed refusal naming
`benchweave setup` (a typo'd data-dir must not silently create a fresh store — see
risk R7 for why the guard does NOT apply to the legacy locator (3)).

### 2.3 Which env keys the file may set — and may NOT

**Allowlist (closed, refused-if-unknown):** the keys the serve surface actually reads
downstream — `BENCHWEAVE_SECRET`, `BENCHWEAVE_ENV`, `BENCHWEAVE_FIXTURES`,
`BENCHWEAVE_REGISTRY_DIR`, `BENCHWEAVE_UI`, and the seven quota keys
(`BENCHWEAVE_MAX_DATASET_BYTES`, `BENCHWEAVE_MAX_EVENT_BATCH`,
`BENCHWEAVE_UI_PANEL_POLL_MS`, `BENCHWEAVE_UI_LOGIN_CODE_TTL_MS`,
`BENCHWEAVE_UI_SESSION_TTL_MS`, `BENCHWEAVE_UI_MAX_BRIDGES_PER_SESSION`,
`BENCHWEAVE_UI_READING_SCAN_ROWS`).

The quota-key subset is DERIVED, not re-spelled: the allowlist imports
`app_entry._QUOTA_ENV_KEYS`'s env column (it is a module-level tuple) so the two
cannot drift silently; the hand-named members are pinned by a test that fails when a
new `BENCHWEAVE_*` read appears in `app_entry`/serve without joining the allowlist or
the documented exclusion set. Scope limit (fold correction, gw2 F4): the inventory
scan sees literal `os.environ.get("...")`/`os.environ["..."]`/`envvar=` spellings
only — an indirectly-read key (a constants idiom routing through a variable) is
invisible to it; the known indirect reads ride the imported quota tuple by
construction, and a NEW indirect read is a review-lane catch, not a scan catch.

**Excluded keys — each refused with a reason in the message if present in the file:**

| Key | Why excluded |
|---|---|
| `BENCHWEAVE_DATA_DIR` | circular — it is a locator; the file is found BY it |
| `BENCHWEAVE_DB` | derived from the data-dir (the dir you point serve at is the store you serve; locator (3) keeps env as the source) |
| `BENCHWEAVE_HOST`, `BENCHWEAVE_PORT` | click reads them via `envvar=` BEFORE the command body runs — a file value could never take effect, which is exactly the silent-no-op this repo refuses (the `BENCHWEAVE_UI` unknown-value posture). Bind comes from flags/process env/systemd's own file. |

Unknown key (anything else): typed refusal naming the key and pointing at the
allowlist. A typo'd `BENCHWEAVE_SECREET` must refuse, not silently do nothing.

No bench-safety envelope is file-settable — the allowlist is service/identity
configuration only, the same class boundary `_LIMITS` already draws (A02: hazards are
commissioned per bench, never ambient config).

### 2.4 Parse rules (the standard, shared verbatim with the SDK)

- Lines are `KEY=VALUE`. The first `=` separates; the value may contain `=`.
- Blank lines and lines whose first non-space character is `#` are skipped.
  No inline comments (a mid-line `#` is value content).
- KEY must match `[A-Za-z_][A-Za-z0-9_]*` and be allowlisted.
- VALUE: strip one layer of matching single or double quotes (systemd
  `EnvironmentFile` compatibility for operators copying shell-export lines); no
  escape sequences, no variable expansion, no command substitution — ever.
- Encoding: strict UTF-8 via `Path.read_text` (universal newlines handle CRLF — a
  Windows-edited file must not grow a `\r` into the secret). A BOM corrupts the first
  key into an invalid key name and refuses (consistent with the exact-byte decoder's
  BOM refusal posture, CON-1's provider-doc precedent).
- Fold R1: a value whose first character is a space/tab after the `=`
  refuses (`KEY= "v"` / `KEY= v` are the `KEY = value` typo class wearing a
  different mask). NOT systemd-style trimming — trimming would re-open the
  silent-corruption class.
- Fold R3: any C0 control character (0x00-0x1F) in a value refuses,
  validated before any `os.environ` write — allowlist value domains
  (paths, urlsafe tokens, ints, enums) never carry controls.
- Fold R4: lines split on `\r\n` / `\r` / `\n` ONLY (reading with
  `newline=""`); U+2028/NEL are not line ends here and stay in the value
  verbatim (`str.splitlines()` would truncate on them).
- Fold R5: parse + validate the WHOLE file, then apply — a refused file
  leaves zero `os.environ` residue (two-phase; `parse_env_file` +
  `apply_env_entries`, with `load_env_file` the composed §2.7 contract).
- Fold R9: a duplicate key in one file refuses naming the key and both
  line numbers — an editing mistake must not silently keep the old value.
- Malformed anything (no `=`, bad KEY chars, unknown KEY, mismatched quotes,
  set-but-empty value `KEY=`) → **fail loud**: typed refusal, prefix `env_file:`,
  naming path, line number, key (when parseable) and the problem class — never the
  raw line (a refusal that echoes the line echoes the secret). Serve exits non-zero;
  `build()` is never called; nothing touches disk.
- Set-but-empty refusal follows the SDK's own in-tree precedent
  (`benchweave_sdk_server/binding.py:275`, `benchweave_sdk/capture.py:84`: whitespace-
  only env values refuse rather than fall back) and kills the trailing-`=` typo class
  the production posture already guards (app_entry `_require_production_secret`
  docstring).

### 2.5 Precedence (the standard's one-line contract)

**Explicit process environment always wins.** Each allowlisted key is applied with
`os.environ.setdefault(key, value)` — set-if-not-set. Consequences, stated for the
record:

- systemd deployments are unchanged by construction: the unit's `EnvironmentFile`
  injects into the process environment before Python starts, so every systemd-set key
  beats the data-dir file. New capability, not a conflict: a systemd env file that
  OMITS `BENCHWEAVE_SECRET` now gets setup's secret from the data-dir file
  automatically (documented in operator-guide §9 as one sentence).
- Foreground operators: `benchweave serve --data-dir /var/lib/benchweave` boots with
  DB derived and secret bridged; `BENCHWEAVE_ENV=production` may be exported or added
  to the file (it is allowlisted).

### 2.6 File presence, permissions, logging

- Missing file: one stderr note (`benchweave: no env file at <path> — nothing loaded
  from it`) whenever a data-dir locator resolved, then proceed. On the legacy locator
  (3) with no file in the DB's parent, behavior is byte-identical to today (no note
  needed — nothing new was promised; the note fires only where the operator named a
  data-dir).
- Permissions: POSIX — refuse if `(st.st_mode & 0o077) != 0` (group/other
  any access; fold R2 corrected the mask from 0o177, which wrongly counted
  the owner-execute bit — a 0700 file is owner-only and loads) with
  `env_file:` naming the octal mode. Residual, disclosed: bits above 0o777
  (setuid/setgid/sticky) are unexamined. The file carries a live secret; ssh's
  posture, not a warning. Windows (`sys.platform == "win32"`): no mode check (mode
  bits do not reach the ACL; setup enforces owner-only at write time) — W1 residual,
  CI-corroborated on the Windows leg.
- Logging: exactly one stderr line on success —
  `benchweave: loaded <path> (set BENCHWEAVE_SECRET, …)` — key NAMES only, never
  values; keys already present in the environment are OMITTED from the line
  (the applied-keys-only choice, pinned by A14: the line names key NAMES and
  the path, and never the secret value).

### 2.7 New module (gateway)

`src/benchweave/cli/env_file.py`:

```python
ENV_FILE_REFUSAL_PREFIX = "env_file:"

class EnvFileError(RuntimeError): ...          # message carries the prefix

def load_env_file(path: Path, allowed: frozenset[str]) -> list[str]:
    """Parse per §2.4, apply set-if-not-set into os.environ, return applied key names.
    Refuses per §2.4/§2.6 (malformed / unknown key / empty value / bad perms)."""

def serve_env_file_keys() -> frozenset[str]:  # allowlist; quota keys imported from app_entry
```

`serve` imports `CREDENTIAL_FILE` from `atrest` (no second spelling of the filename)
and calls the loader before `build()`. `setup`'s writer is NOT changed: the file
remains the secret-only credential file; operators may hand-add allowlisted service
keys (documented), which is the autoload's whole point.

## 3. Mechanism (SDK `benchweave_sdk_server serve`)

Read the real code (standalone checkout main, native Read — the repo is outside the
gortex workspace): `serve` (src/benchweave_sdk_server/cli.py:337) has no data-dir, no
setup, no credential file. Its only env reads are `BENCHWEAVE_STANDALONE_BINDINGS`
(binding.py:275 — set-but-empty refused) and `BENCHWEAVE_CAPTURE_DIR`
(benchweave_sdk/capture.py:84 — same), both resolved INSIDE the command body
(argument > environment > default — Decision 9's precedence family), i.e. AFTER a
loader at the top of the serve body would run. No click-pre-read trap exists here.

**Standard applied, divergence recorded:**

- Same parse rules (§2.4, verbatim), same precedence (flag > process env > file,
  set-if-not-set), same `env_file:` refusal prefix, same 0600-or-refuse posture, same
  key-names-only logging. Twin implementation `src/benchweave_sdk_server/env_file.py`
  + twin tests asserting the SAME literal expected strings in both repos — the
  established cross-repo pattern (CON-14's `derive_move_to` amendment, 2026-10-01).
- **Divergence (recorded reason): the locator is an explicit `--env-file <path>`
  flag, not data-dir auto-discovery.** The SDK surface has no setup step, no data
  directory, and no canonical file — inventing an auto-discovered location would be
  new architecture with no consumer, violating the extend-precedent rule. The flag is
  opt-in; without it, zero filesystem reads change (arm S6).
- SDK allowlist (closed): `BENCHWEAVE_STANDALONE_BINDINGS`, `BENCHWEAVE_CAPTURE_DIR`.
  Anything else (including `BENCHWEAVE_DB`) refuses as unknown — the SDK serve has no
  store, and the refusal teaches that.
- Scope: `serve` only. `mcp` reads the same bindings env key but is deferred (named
  in §4).

## 4. Minimal first increment — and what it DEFERS

This slice ships: gateway serve `--data-dir` locator + `<data-dir>/benchweave.env`
autoload + closed allowlist + `env_file:`/`serve_locator_conflict:` refusals + docs
motion; SDK serve `--env-file` + twin loader + twin tests + docs motion.

DEFERRED (each named, none silent):

- increment 2's record (supervision model, stop semantics, serve-surface declaration
  — this record's §3 divergence input feeds it)
- `start/stop/restart/status`, pidfiles, `service install` (increment 3)
- `doctor`, `logs` (increment 4); no env-continity doctor arm here
- `mcp` subcommand env-file support (SDK)
- extending autoload to any non-serve gateway command
- setup writing more than the secret into the file (config-vs-credential separation
  kept; revisit only with an operator-demand record)
- a `--env-file` flag on the GATEWAY serve (one canonical file exists; a second
  config-file path is a new surface — refused here, recorded)
- touching `deploy/systemd/` bytes (precedence makes it unnecessary; the interplay is
  documented in operator-guide §9 prose instead)
- new invariant IDs for the CLI env layer — the twin tests carry the contract;
  increment 2's serve-surface record decides whether "explicit env always wins"
  graduates into `docs/internal/invariants.md`
- Windows ACL verification of the loaded file (W1: land, let the Windows CI leg
  corroborate the skip path)
- increment 2's record must pin "stderr prose is not an interface" (critic
  Q5): the loaded/note stderr lines are human-facing; `doctor` re-derives
  state from inputs, never parses stderr

## 5. Precedent (what this extends, none of it invented)

1. `--data-dir` + `envvar="BENCHWEAVE_DATA_DIR"` — the seven at-rest commands'
   existing pattern (commands.py:81 ff.); serve joins the family.
2. `atrest.CREDENTIAL_FILE` / `_write_credential_file` / 0600-and-fsync / Windows
   owner-only-ACL — the file's existing writer and posture; the loader reads what
   setup writes and imports the constant.
3. Set-but-empty env refusal — `benchweave_sdk_server/binding.py:275`,
   `benchweave_sdk/capture.py:84`.
4. Machine-matchable refusal prefixes (`no_matching_rule:`, `pin_absent:`, …) — the
   CTL-4 family style; `env_file:` joins the vocabulary.
5. Closed-world key sets with refusal on the unknown — `BENCHWEAVE_UI`'s
   present-but-unknown-value boot refusal (app_entry `_ui_enabled_from_env`).
6. Twin-repo mechanism with twin literal tests — `derive_move_to` (CON-14 amendment,
   2026-10-01).
7. Lazy env-pure `build()` — preserved untouched (test_serve.py's M3 lazy-import pin
   stays green unchanged).

## 6. Invariant and drift impacts

Walked against `docs/internal/invariants.md` (live code checked, not asserted):

- **CTL-1..9:** no `control/` path touched; autoload completes before `build()`
  composes anything. The protective path, executor, coordinator are untouched. PASS
  by path, verified by the diff's file list.
- **STO-1/2:** no store code. **STO-3:** the one-coordinator flock is acquired at app
  boot inside the composition (and by at-rest commands); autoload runs before, holds
  nothing, changes no holder semantics. **STO-4/5/6:** untouched.
- **CON-1..15:** no `contracts/`, no `standards/` bytes, no manifests, no openapi or
  mcp-tools motion. CON-5/A13 parity: REST and MCP both mount behind `build()`; the
  CLI env layer feeds build's inputs identically for both transports — it is not a
  transport and moves no parity surface. The standards-involvement tripwire
  (`git diff origin/main...HEAD -- standards/` empty) stays green.
- **A07 (audit failure constrains new work):** no audit-path change; autoload happens
  pre-composition and cannot affect audit refusals.
- **A02:** no numeric bench envelope becomes env-file-settable — the allowlist is
  service/identity config only (§2.3).
- **At-rest/live split:** the credential file stays never-backed-up, never-restored
  operator state; autoload only READS it. `verify`/`backup`/`restore` semantics
  unchanged (`_UNLISTED_OK` already tolerates the filename).
- **Drift obligations moved:** obligation 4 (operator-visible behavior →
  `docs/operator-guide.md` §2 sentence + §3 rewrite + §10 serve row; README swept for
  the export dance — none found in README.md today) and a NEW row for
  `docs/internal/drift-and-obligations.md`: *the serve env-file allowlist ↔
  app_entry/serve env-read inventory coupling* (a new serve-readable env key must
  join `serve_env_file_keys()` or the documented exclusion set; pinned by the
  inventory test in §7). Obligation 9 (`deploy/systemd/`) deliberately NOT moved —
  no template bytes change; the CI systemd rehearsal is unaffected.
- **CI cost:** no new jobs, no workflow edits. ~14 gateway + ~6 SDK test additions;
  fast lane + full battery per #247; xdist absorbs it.

## 7. Measurable proof — pre-committed acceptance rule

**RED control (the fluff-proof part):** neutralize the mechanism — bypass the
autoload call at its ONE call site in serve (and the SDK's one call site) — and the
autoload arms must go RED. The arms below assert on the environment `build()`
actually received (monkeypatched `app_entry.build` capturing an `os.environ` snapshot;
uvicorn stubbed via `sys.modules` for success arms; CliRunner throughout; the E2E arm
uses the file's existing real-subprocess pattern).

Gateway arms (new `tests/cli/test_env_file.py` + extensions to `tests/cli/test_serve.py`):

| # | Arm |
|---|---|
| A1 | setup-created data dir (real `atrest.setup`), file carries a runtime-generated `BENCHWEAVE_SECRET` + `BENCHWEAVE_ENV=production`; process env scrubbed of `BENCHWEAVE_*`; `serve --data-dir` → build called with the FILE's secret and `BENCHWEAVE_DB=<dir>/state.sqlite` |
| A2 | same + `BENCHWEAVE_SECRET` also in process env → process value wins (≠ file value) |
| A3 | legacy locator: only `BENCHWEAVE_DB` set, file in its parent → secret autoloaded |
| A3b | legacy locator, NO file in parent → build called, default-secret posture (today's bytes) |
| A4 | no DB, no data-dir → typed refusal naming `BENCHWEAVE_DB` AND the new locators |
| A5 | malformed line (`BENCHWEAVE_SECRET` no `=`) → `env_file:` refusal, build never called |
| A6 | unknown key `BENCHWEAVE_NOT_A_THING=1` → refusal naming the key |
| A7 | file sets `BENCHWEAVE_DB` → refusal (derived key) |
| A8 | file sets `BENCHWEAVE_PORT` → refusal (listener key, click pre-read) |
| A9 | `--data-dir X` + `BENCHWEAVE_DB=Y/state.sqlite` (X≠Y) → `serve_locator_conflict:` naming both |
| A10 | `--data-dir` with no `state.sqlite` → refusal naming setup; no store file created |
| A11 | file chmod 0644 → `env_file:` refusal naming the mode (skipif win32) |
| A12 | quoted value + CRLF file → unquoted value, no `\r` (use a non-SECRET key's value — see builder note) |
| A13 | `BENCHWEAVE_SECRET=` (empty) → `env_file:` refusal |
| A14 | A1's stderr contains the key NAME and the path, NOT the secret value |
| E2E | real subprocess, only `BENCHWEAVE_DATA_DIR` set, production, file secret → `/v1` 200 with a token minted from the FILE's secret (the live-serve pattern, test_serve.py:328) |

SDK arms (new `tests/server/test_env_file.py` + serve wiring arms in the server CLI
test module): S1 `--env-file` sets `BENCHWEAVE_CAPTURE_DIR` (seam resolves the file's
value) · S2 process env wins · S3 `BENCHWEAVE_DB` in an SDK env file refuses as
unknown · S4 malformed line refuses with the same prefix · S5 perms refusal twin ·
S6 no flag → no file reads, behavior unchanged.

**Acceptance rule (pre-committed, before any code exists):** all 14 gateway arms +
E2E + 6 SDK arms pass (fold correction, gw1 F7b: the arithmetic is 21 arms —
15 gateway lettered arms counting A3b, + E2E, + 6 SDK arms = 22 collected
arm count; the original "21" undercounted the lettered set), counts read from `--junitxml` attributes or exit codes (never
an output-filter summary). RED control: with the autoload call bypassed at exactly
one call site per repo, A1+A3+E2E (gateway) and S1 (SDK) must FAIL with typed
failures; restored, all pass. SHIP = 21/21 green + 4/4 control arms red-then-green,
both repos' fast lane and full battery green. KILL = any arm failing after one
fluke re-run, or any control arm staying green while bypassed (the arm does not test
the mechanism — redesign the arms, do not merge). UNDERPOWERED = E2E cannot run
locally (port/subprocess sandbox): it may ride the Linux CI leg only, the rule
degrades to 20/21 with that disclosed on the PR — not silently dropped.

Builder notes (trap avoidance, both load-bearing):
- Env-file fixture lines must be UNQUOTED for the secret key. The repo's denylist pin
  (`test_known_public_secrets_covers_every_repo_secret_literal`,
  tests/cli/test_serve.py:230) greps the tracked tree for `SECRET *= *b?"…"` — a
  quoted `BENCHWEAVE_SECRET='x'` fixture line would enroll `x` in the public-secret
  inventory and redden the pin. Quote-stripping arms use a non-SECRET key.
- Generate test secrets at runtime (`secrets.token_urlsafe`), as the live test
  already does.

## 8. Review tier + Step-1 keyword scan (#254)

**Tier 3** for the gateway PR. Trigger, from the rubric's objective rules: the
diff TEXT contains `subprocess` — the E2E arm adds real `subprocess.Popen` usage
lines to tests/cli/test_serve.py (the import already exists in that file), and this
record — which rides the branch as commit one per convention — itself names the word
below. Tier 3 buys the two-lane adversary (standing rule, 2026-09-24 retro R3). The
SDK PR in isolation is Tier 2 (new module + tests + README under `src/`/`tests/`, no
keyword, no Tier-3 path); the train's maximum tier is Tier 3 and this scan covers the
gateway expected diff (code + tests + operator-guide + this record), with the SDK
diff scanned separately.

Keyword legend (numbered so this table does not perturb its own counts):
1=`threading` 2=`asyncio` 3=`subprocess` 4=`sha256` 5=`hashlib` 6=`migrate`
7=`recovery` 8=`protection`.

Scan result, MEASURED over this record at design time
(`grep -oiw <kw> <record> | wc -l`, the single legend occurrence excluded):
1: 0 · 2: 0 · 3: 8 · 4: 0 · 5: 0 · 6: 0 · 7: 0 · 8: 0. Expected CODE diff
(tests/cli/test_serve.py E2E arm): 3: ~2 added lines (`subprocess.Popen`,
`subprocess.TimeoutExpired`); every other keyword 0 across the whole expected
diff — the operator-guide §3 rewrite was written to avoid words 6/7/8 and no
CTL/invariant citation needed them. SDK expected diff: all eight 0.
First-match-wins: keyword 3 fires → Tier 3.

G0 secrets: fixtures carry runtime-generated or obviously-fake unquoted values; no
`mk_`/`gorag_`/`ghp_`/`sk-`/`Bearer ` literals; no private paths beyond repo-relative
ones already public.

## 9. Top risks, each with its falsifier

- **R1 Secrets leak into logs or refusal text.** Falsifier: A14 + the §2.4 rule that
  refusals never echo the raw line. An adversary arm greps the FULL captured output
  of every refusal arm for the file's sentinel value.
- **R2 Silently masking a missing var.** The absent-file note + set-but-empty
  refusal + unknown-key refusal close the quiet paths; production posture still
  refuses a bad secret downstream. Falsifier: A5/A6/A13 + the E2E.
- **SDK/gateway drift.** Twin literal tests + this record's §2.4 as the spec text
  increment 2 re-cites. Falsifier: a twin test that pins the same refusal STRINGS in
  both repos.
- **systemd double-injection surprise.** Process env wins by construction (§2.5); the
  only new behavior is a systemd file that omits the SECRET gaining the data-dir one.
  Falsifier: A2's precedence arm + the §9 guide sentence.
- **Windows path/perm behavior.** Perms check skipped (W1, CI-corroborated);
  universal newlines handle CRLF (A12); relative `--data-dir` resolved (A9's
  resolve() comparison). Falsifier: the Windows CI leg green post-merge.
- **Hand-extended service keys live in a never-backed-up file (fold row,
  gw2 F1).** The credential file is deliberately excluded from backups; an
  operator who hand-adds allowlisted service keys (quota ceilings,
  `BENCHWEAVE_ENV=production`) loses them across a restore. Consequences:
  quota keys vanish → runs that required them refuse loudly at
  `build_run` (the R16 refusal — loud, not silent); `BENCHWEAVE_ENV`
  absent → the gateway silently boots in development posture. The restore
  story already requires re-placing the secret; hand-added keys follow it.
  Falsifier: none in this increment — increment 2's record owns the
  doctor surface that re-derives and reports this.
- **R7 Fresh-store-on-typo.** The exists-guard fires only on the NEW locators; the
  legacy `BENCHWEAVE_DB` path keeps today's create-on-typo behavior because
  integration suites boot fresh stores via `build()` against chosen DB paths —
  changing that is NOT this increment (disclosed, not hidden). Falsifier: A10 vs
  A3b.
- **Allowlist drift (a future env key not added).** Inventory-derived quota keys +
  the drift-doc row + the pinned inventory test. Falsifier: the inventory test
  planted-key arm (add a fake read, test reds).

## 10. Landing shape and test files

Two feature PRs, both referencing #422 (single issue stream; no SDK-side issue by
design):

1. **SDK PR** (repo `benchweave-sdk`, branch off main): twin loader + `--env-file` +
   tests + README §"The server extra" motion. Merges first.
2. **Gateway PR** (this repo): `cli/env_file.py` + serve `--data-dir`/autoload +
   tests + operator-guide §2/§3/§9/§10 + drift-doc row. **No submodule pointer
   motion** — the gateway consumes no SDK bytes (twin tests assert literals in both
   repos independently; REG-4 read-not-import). The pin advance rides the next SDK
   release train (issue #408's order rule governs when a release is cut); a trailing
   pin is green-with-annotation by design.

Test files created/extended: `tests/cli/test_env_file.py` (new),
`tests/cli/test_serve.py` (extended: A1–A4, E2E, builder notes), SDK
`tests/server/test_env_file.py` (new) + the server CLI test module (S-arms).
Docs legs route through the `document-writer` agent for the operator-guide §3
rewrite and the SDK README paragraph (published operator-facing prose, ASD-STE100
register).

## 11. Forks needing the owner's call before build

- **Fork 1 — serve `--data-dir` flag (recommended) vs env-only locator.** The flag
  matches the at-rest pattern and makes the guide's story uniform; env-only
  (`BENCHWEAVE_DATA_DIR` alone) is one option declaration smaller but leaves the
  flag family asymmetric. Recommend: ship the flag.
- **Fork 2 — SDK half now (recommended) vs defer.** The issue's directive says one
  standard for both CLIs; the twin implementation (~80 lines + tests) satisfies it
  cheaply. Deferring is defensible only if the owner reads "standard" as
  spec-for-now (increment 2's record would then own the SDK adoption). Recommend:
  ship both halves.
- **Fork 3 — E2E subprocess arm (recommended) vs in-process-only.** Including it
  makes the diff Tier 3 (two-lane adversary); excluding it keeps Tier 2. The E2E is
  the arm that proves the operator story end-to-end; recommend accepting Tier 3.
