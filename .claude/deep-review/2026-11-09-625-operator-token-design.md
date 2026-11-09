# Issue #625 — an operator cannot obtain a bearer token from the shipped CLI

**Status:** design, pre-build. **Slice:** one increment (one commit) plus its tests and docs
sweep. **Base:** `origin/main` at `c28b3648`.

## 1. The defect, traced to the line

The issue reports a dead end on the path from `setup` to the read-only UI. Verified on a
clean `main`, reading the code rather than the brief:

1. `benchweave setup --data-dir D` writes a random signing secret to `D/benchweave.env`
   (mode 0600) — `src/benchweave/cli/atrest.py:284`, `_write_credential_file` at
   `atrest.py:164`.
2. `benchweave serve --data-dir D` bridges that file into the process environment through
   the shared validator and allowlist — `src/benchweave/cli/env_file.py`
   (`parse_env_file`, `apply_env_entries`, `serve_env_file_keys`,
   `ENV_FILE_EXCLUDED_KEYS`), called from `src/benchweave/cli/commands.py:856-881` — and
   `app_entry.build()` signs and validates with `BENCHWEAVE_SECRET`
   (`src/benchweave/interfaces/app_entry.py:289`).
3. `benchweave ui-login` requires `--token` (`commands.py:1324-1330`) and exchanges it for
   a single-use login code over the gateway's REST surface
   (`src/benchweave/interfaces/ui.py:654-699`).

Between 2 and 3 there is no shipped command. The only issuer in the tree is
`benchweave.interfaces.identity.issue` (`identity.py:77`), whose docstring calls it a
local **test** token minter and whose only callers are tests and test support
(`tests/interfaces_ui/ui_gateway_support.py:57`, `tests/cli/test_live.py`, and siblings).
The same gap blocks `status`, `demo`, REST clients and MCP clients: all of them take
`--token` or a Bearer header and nothing in the operator surface produces one. Reaching
the UI from a clean checkout required a Python one-liner against `src/`, which is not an
operator surface.

**Correction to the issue's stated mechanism (one point).** The brief says a short token
"silently bounds the browser session". Read literally, `sessions.mint_login_code`
(`src/benchweave/interfaces/sessions.py:470-491`) **refuses**; it does not clamp. With
`--ttl-mins` omitted, `ttl_seconds` defaults to the store's session ceiling
(`sessions.py:472-473`), and then:

```
if now + ttl_seconds > caller.expires_at:
    raise MintRejected("forbidden")
```

so a token shorter than the ceiling makes a no-flag `ui-login` fail with `forbidden`
(403), not silently shorten the session. The *only* silent bound is at exchange time,
`granted_expiry = min(now + session_ttl_s, caller_expires_at)` (`sessions.py:523`), and
that path is reached only when the caller explicitly asked for a `--ttl-mins`. This
correction is load-bearing for the default lifetime decision in §3.4: an 8-hour token
(`==` the ceiling) cannot mint the default session once even a second has elapsed, because
the comparison is `>` at second granularity.

The UI itself is not in scope: the reporter confirmed it renders (all assets 200, bench
page 200 with real data) once a token exists.

## 2. Decision — the shape

Three candidates were weighed.

| Option | Covers the UI | Covers REST/MCP | New credential-printing surface | Failure coupling |
|---|---|---|---|---|
| **A. New `benchweave token`** | yes | yes | one, explicit, offline | none — no gateway call |
| B. `ui-login --data-dir` mints and logs in | yes | no | one | a gateway error after minting leaves an unprinted token |
| C. Nothing new; document the Python one-liner | yes | yes | none | n/a — but it documents an internal, unsupported surface |

**Chosen: A.** Reasons, in the order they decided it:

1. **One issuer, every consumer.** `token` composes with the surface that already exists:
   `--token` / `BENCHWEAVE_TOKEN` on `ui-login`, `status` and `demo`. Option B leaves the
   REST/MCP half of the issue open, so the issue would not be closed.
2. **Failure isolation.** `token` is a pure local computation: read the file, sign, print.
   It cannot fail after producing a credential, and it cannot hold a credential back
   because the network was down. Option B interleaves signing with a network call, and
   then has to decide whether to print a token on a failed login — every answer is worse
   than not coupling them.
3. **The credential handing-out site is the same in both options** — one call to
   `identity.issue` in one CLI command. The "one more place that hands out a credential"
   cost is not paid twice; what A adds is a second *consumer* of the same primitive.
4. **Precedent.** The tree already has a deliberately credential-printing command:
   `setup --show-secret` (`commands.py:98-159`), whose contract is pinned by
   `tests/cli/test_atrest.py:211-240`. A second explicit printer with the mirror contract
   is a smaller change than making an existing network command conditionally offline.

**Precedent extended, named:** `identity.issue` (the pure signer) +
`cli/env_file.py`'s bridge (the single reader of the credential file) +
`setup --show-secret`'s printed-credential contract + `ui-login`'s
"plain mode prints exactly one machine-usable line" output shape (`commands.py:1376-1380`).
No new architecture: the command is an adapter that composes four proven in-tree pieces.
`identity.py` is **not modified** — the signer already takes exactly the inputs needed.

## 3. The mechanism

### 3.1 New command (in `src/benchweave/cli/commands.py`, beside `ui-login`)

```
benchweave token --data-dir D [--scope S ...] [--ttl-mins N] [--json]
```

- `--data-dir` : required, `click.Path(path_type=Path)`, `envvar="BENCHWEAVE_DATA_DIR"`,
  `help=_DATA_DIR_HELP` — the same option shape as `setup` (`commands.py:89-97`).
- `--scope` : repeatable; default `stg:observe` (the read-only floor, §3.4). Each value is
  checked against `TIER_SATISFIES["observe"]` (`src/benchweave/interfaces/operations.py:66-70`)
  — the seam's own scope set, imported rather than re-spelled.
- `--ttl-mins` : `click.IntRange(min=1)`, default `None` → `_TOKEN_DEFAULT_TTL_S` (§3.4).
- `--json` : the stable machine contract; routed through `cli/output.emit` like every
  other command (`_set_json`, `commands.py:70-74`).

Plain (no `--json`) mode prints **exactly the token and a newline to stdout** — the
`ui-login` shape, so `$(benchweave token --data-dir D)` yields a bare credential. One
stderr line carries the human context (principal, scopes, ISO expiry). When the effective
secret came from the process environment rather than the file, a second stderr line says
so (§3.3) — that is the surprising case and it is exactly the one that produces a token
the local gateway will reject.

`--json` payload (additive-only machine contract):

```
{"audience": "stg", "expires_at": <unix int>, "principal": "operator",
 "scopes": ["stg:observe"], "secret_source": "env-file"|"process-environment",
 "token": "<the credential>"}
```

No `secret` key, ever.

### 3.2 The secret bridge — reuse, one reader

The command performs **no new file parsing**. It calls a helper extracted from `serve`'s
existing block, added to `src/benchweave/cli/env_file.py`:

```python
def bridge_env_file(path: Path) -> list[str]:
    """Parse the file, refuse a set-but-empty process shadow, apply
    set-if-not-set into os.environ; return the applied key names."""
    entries = parse_env_file(path, serve_env_file_keys(), excluded=ENV_FILE_EXCLUDED_KEYS)
    for _lineno, key, _value in entries:
        current = os.environ.get(key)
        if current is not None and not current.strip():
            raise EnvFileError(
                f"{ENV_FILE_REFUSAL_PREFIX} {path}: {key} is set but empty in the"
                " process environment and shadows the value this file"
                " carries — unset it or set it to a real value")
    return apply_env_entries(entries)
```

The strings are moved **verbatim** from `commands.py:857-875`, so `serve`'s behaviour and
its pinned messages are unchanged; `serve` then becomes `bridge_env_file(env_path)` plus its
existing "loaded … (set …)" stderr line. Key names only, never values — the existing
contract.

**Which keys are readable: exactly `serve_env_file_keys()`** — `BENCHWEAVE_SECRET`,
`BENCHWEAVE_ENV`, `BENCHWEAVE_FIXTURES`, `BENCHWEAVE_REGISTRY_DIR`, `BENCHWEAVE_UI`
(`env_file.py:31-37`) plus the derived quota keys (`env_file.py:261-267`). Using the serve
allowlist rather than a two-key set is deliberate: an operator hand-extends
`benchweave.env` with service keys for `serve` (the documented #422 posture), so a
narrower allowlist would refuse a file that `serve` accepts. `BENCHWEAVE_DATA_DIR`,
`BENCHWEAVE_DB`, `BENCHWEAVE_HOST`, `BENCHWEAVE_PORT` stay excluded with their documented
reasons (`env_file.py:41-55`).

Behaviour when the file is not usable, each with the existing typed envelope:

| Condition | Result |
|---|---|
| file absent | `token: <D> is not a BenchWeave data directory (no <path>) — run benchweave setup --data-dir <D>` (this also covers "a directory that is not a BenchWeave data dir"; `setup` writes the store and the file together, and the file is the marker the command needs) |
| unreadable (`EACCES`, I/O) | `env_file: <path>: cannot read it: <error>` |
| not UTF-8 | `env_file: <path>: not valid UTF-8: <error>` |
| group/other access on POSIX | `env_file: <path>: mode 644 allows group or other access … (chmod 0600)` |
| a key not on the allowlist | `env_file: <path>: line N: <KEY> is not allowlisted …` |
| an excluded key (`BENCHWEAVE_DB=…`) | `env_file: <path>: line N: BENCHWEAVE_DB may not come from the env file — …` |
| duplicate / empty value / mismatched quotes / leading whitespace | the matching `env_file:` refusal |
| no `BENCHWEAVE_SECRET` in file **and** none in the process environment | `token: no BENCHWEAVE_SECRET in <path> and none in the process environment — restore the secret line, or run benchweave setup in a fresh data directory` |
| `BENCHWEAVE_SECRET` present but blank after `strip()` | the same refusal as above (an empty key would sign forgeable tokens; §8 item 3) |

Malformed-line refusals never echo the line, so no refusal path can print the secret —
the loader's existing contract (`env_file.py:1-18`), inherited unchanged.

### 3.3 Effective secret and source

`bridge_env_file` applies set-if-not-set, so the effective secret is
`os.environ["BENCHWEAVE_SECRET"]` after the bridge: an explicit process value wins, exactly
as it does for `serve`. `secret_source` (JSON) and the stderr note (plain) report which one
was used, because a stray exported `BENCHWEAVE_SECRET` from an old deploy silently produces
a token the data-dir gateway rejects with `bad_signature`.

### 3.4 Defaults — principal, audience, scopes, expiry

- **Audience: `"stg"`, hardcoded.** No composition path overrides it: `create_app`
  (`app.py:1050-1064`) takes no audience parameter, and the three sub-builders default to
  `"stg"` (`rest.py:55`, `ui.py:471`, `mcp.py`). A `--audience` flag would be decoration on
  a value the shipped gateway cannot change. The end-to-end arm (§6, A1/A2) reds if the
  gateway default ever moves away from the CLI constant.
- **Principal: `"operator"`, fixed, no flag.** The token carries no production identity
  claim (`identity.py:1-8`); no authorization decision reads `principal` — permissions read
  `scopes` (`operations.py:96-100`). Cursors are principal-bound but a forged cursor buys
  nothing (`operations.py:71-79`), so a shared principal label has no security effect. A
  `--principal` flag is deferred: it adds a place to write a real name into a token without
  changing any decision.
- **Scopes: `stg:observe` by default — the least privilege that still reaches the UI.**
  Every route the read-only UI calls requires the observe tier: the index page calls
  `gateway_info` and `bench_list` (`ui.py:628-631`), both `require_permission(identity,
  "observe")` (`operations.py:576` onward). `stg:observe` therefore reaches every UI page
  and nothing that mutates, takes a lease, or administers. Widening is an explicit
  repeatable flag, and only the three seam scopes are accepted.
- **Expiry: 12 h by default (`_TOKEN_DEFAULT_TTL_S = 12 * 3600`), `--ttl-mins` to change.**
  The bound that forces this number: `ui-login` with no `--ttl-mins` asks for the store's
  session ceiling (8 h default, `app_entry.py:112`), and `mint_login_code` refuses when
  `now + ceiling > token.expires_at`. An 8 h token therefore fails the no-flag path on any
  run that crosses a second boundary; 12 h leaves 4 h of slack for the documented
  two-command sequence. A pinning test asserts
  `_TOKEN_DEFAULT_TTL_S > app_entry._LIMITS["ui_session_ttl_ms"] // 1000`, so raising the
  ceiling reds rather than silently re-opening the trap.
  No maximum is imposed. Justification: anyone who can read the 0600 file can already mint
  an arbitrary token with the same primitive, so a long-lived token grants no capability a
  file reader lacks; the token is only *more* dangerous than the secret for someone who
  holds a leaked token but not the file, and that is the residual disclosed in §9.

### 3.5 Production posture

The command applies the same gate the gateway applies at boot: a lazy
`from benchweave.interfaces.app_entry import _require_production_secret` and a call with the
effective secret, wrapped so a `RuntimeError` becomes `token: <message>` and exit 1. After
`bridge_env_file`, a `BENCHWEAVE_ENV=production` carried by the file is in the process
environment too, so the file's posture is honoured, not only the shell's.

Why reuse the private gate rather than reimplement: the inventory of publicly-known secrets
is pinned by `tests/cli/test_serve.py:250`
(`test_known_public_secrets_covers_every_repo_secret_literal`), which greps the tree; a copy
in the CLI would be exactly the drift that test exists to prevent. Cost:
`serve_env_file_keys()` already imports `benchweave.interfaces.app_entry` for
`_QUOTA_ENV_KEYS` (`env_file.py:261-267`), so the app module is already loaded by the time
`token` needs the gate — the lazy import adds no new import graph. Disclosed wart: the
wrapped message begins "refusing to boot", which reads oddly under a `token:` prefix; the
alternative (a light `secret_posture` module) is deferred, not rejected.

Why apply it at all: the command must never print a credential that the gateway it names
would refuse to serve. If the gateway is in production posture, its secret already passed
this gate, so the same file mints a usable token; if the gateway is not running, a token
from a publicly-known secret is a misleading artifact rather than a capability.

### 3.6 What the command does not touch

No `StoreHold`, no `Store.open`, no write of any kind (`token` imports neither
`benchweave.state.hold` nor `benchweave.state.store`), and it has no migration or recovery
path: the command reads one file, signs in memory, and exits. Issuance therefore cannot
block a live bench, cannot race the single-writer rule, and cannot appear on the protective
path — the A04/A07 obligations are untouched by construction, and §6 arm A8 pins the
no-write property.

## 4. Invariants and drift

### 4.1 Invariants

- **CON-15 gains an amendment** (`docs/internal/invariants.md:1201-1209`). The mechanism it
  states does not change: sessions remain server-side, cookie-mapped, at-most-as-wide
  projections, and widening is still refused at the mint. What changes is that the *caller*
  `Identity` now has a shipped issuer, so the row should name it and the bound it carries:
  the CLI signs with the effective `BENCHWEAVE_SECRET` resolved by the serve env-file
  bridge, and a session minted from a CLI token can never outlive that token (refusal when
  the ceiling would, `min(…)` at exchange).
- **New invariant CON-16 — CLI credential issuance.** Three properties, each pinned:
  (a) one reader — the CLI resolves the signing secret only through
  `cli/env_file.bridge_env_file`, never a second parser; (b) the signing secret never
  appears in stdout, stderr, the JSON contract, a URL, or a refusal message; (c) the
  default grant is `stg:observe` and widening requires an explicit flag. Pinning tests:
  `tests/cli/test_token_cmd.py` (§6). Without (a) a hand-rolled reader would skip the
  owner-only mode check; without (b) the command becomes a secret-exfiltration surface;
  without (c) the path of least resistance hands out admin.
- **No CTL / STO / REG change.** No control path, no persistence, no registry behavior.

### 4.2 Drift surfaces that must move with this diff

| Surface | Motion |
|---|---|
| `docs/operator-guide.md` "The browser UI" (§7, ~line 301) | add the token step before `ui-login` — the gap was invisible until walked by hand |
| `docs/operator-guide.md` §10 command reference (~line 1325) | "Eighteen commands" → nineteen; add the `token` row |
| `website/index.html` CLI-reference card (~line 417) | add `<code>token</code>` to the enumerated command set |
| `docs/internal/invariants.md` | CON-15 amendment + CON-16 (above) |
| `tests/win_core_manifest.json` | new row for `tests/cli/test_token_cmd.py` via `scripts/ci/win_core_manifest.py --refresh`, then `--check` (obligation 32 ratchet) |
| `src/benchweave/cli/commands.py` module docstring (line 3-7) | the command list gains `token` |

Explicitly **not** moving, with the reason:

- **No MCP tool / REST / openapi / interface-schema change** — the transport surface is
  untouched (invariant CON-5 unaffected).
- **No env-file allowlist change** (obligation 29): `token` reads only
  `BENCHWEAVE_SECRET` and `BENCHWEAVE_ENV`, both already allowlisted, so the SDK twin
  (`benchweave_sdk_server/env_file.py`) needs no motion and no release.
- **No fixture lattice, no vendored standards, no `standards/` bytes** — no version bump,
  no `corpus-manifest` repin, no standards-governor dispatch.
- **No `packages/sdk` pointer** — nothing in the SDK changes.
- **No on-disk format or schema change** (the file already exists; nothing is written).
- **README** carries no command list (`grep -n "ui-login" README.md` → 0 hits), so
  obligation 4's README half is satisfied by inspection.
- **The docs site's `reference/cli` page** regenerates from `benchweave --help` at build
  (`scripts/assemble_docs_site.py`; the website card's own text says so) — no committed
  edit, no `standards-cli` page motion (that page is the standards argparse tree).

Operator-facing prose (guide + website) is ASD-STE100 register: dispatch the
`document-writer` agent for that leg; engineering text (this record, invariants, tracker)
stays in the engineering register.

**CI cost:** no new lane and no new job. The `gates` lane re-runs the suite; the new test
module boots one real uvicorn thread (module-scoped, reused by A1 and A2 — the
`tests/cli/test_ui_login_cmd.py` cost shape, reusing that module's `boot`/`stop` helpers).
The `windows` lane gains nothing (row pinned at `core 0`; the platform-sensitive validator
already runs there with 25 core tests in `tests/cli/test_env_file.py`). The Tier-3 refute
(§8) is a review pass, not CI.

## 5. Tier call (#254) and the Step-1 keyword scan

**Tier: 3.** Rule that triggers it: Step 1's keyword rule — one keyword occurrence, in this
record's substantive text (§3.6: the command "has no migration or recovery path"). Step 1
is first-match-wins and text-based by design, so a record whose prose carries a
protection-adjacent key takes the deep lane even where the sentence negates the property;
the code, test and docs lines carry none of the eight. The path rules alone would place the
diff at Tier 2 (`src/`, `tests/`, docs); the maximum across the scans is 3, so the Tier-3
lane and its mandatory independent refute (`docs/internal/review-rubric.md` G6) apply.

**Disclosure, because the tier call should be auditable:** the lane was bought by a sentence
in this document, not by the diff's mechanism. Step 1 has no rule that elevates credential
issuance on its own; the same change with that sentence worded differently would land Tier
2. The effect is welcome here — a credential-issuance surface is exactly where a second
independent pass pays for itself — but it is a real process artefact and goes to the ledger
as a finding, not as a workaround. No text was reworded to move the tier in either
direction: the sentence states a property the change genuinely has.

### 5.1 Expected diff

1. `src/benchweave/cli/env_file.py` — `bridge_env_file` helper (verbatim move of the
   existing serve block + set-but-empty guard).
2. `src/benchweave/cli/commands.py` — serve block replaced by the helper; imports pruned;
   docstring command list; the `token` command (~45 lines); `time`/`datetime` imports.
3. `tests/cli/test_token_cmd.py` — new (arms A1–A10), reusing
   `tests/interfaces_ui/ui_gateway_support.py`'s `boot`/`stop`.
4. `tests/win_core_manifest.json` — one row, machine-refreshed.
5. `docs/operator-guide.md` — the step + the command-table row + the count.
6. `website/index.html` — one `<code>token</code>` in the CLI card.
7. `docs/internal/invariants.md` — CON-15 amendment + CON-16.
8. `.claude/deep-review/2026-11-09-625-operator-token-design.md` — this record.

### 5.2 Scan result

Measured with `grep -o -i -w` (case-insensitive, word-bounded) over the whole expected diff
text, for the rubric's eight keywords. Two scans: (a) this record's body **with §5
excluded** — the reporting section necessarily names every keyword, so it is excluded
rather than double-counted (re-run with the same exclusion to reproduce); (b) the intended
code, test and docs lines, pasted into one file.

| Keyword | (a) this record, excl. §5 | (b) code/test/docs diff |
|---|---|---|
| `threading` | 0 | 0 |
| `asyncio` | 0 | 0 |
| `subprocess` | 0 | 0 |
| `sha256` | 0 | 0 |
| `hashlib` | 0 | 0 |
| `migrate` | 0 | 0 |
| `recovery` | 1 | 0 |
| `protection` | 0 | 0 |

**Result: 1 occurrence in (a) (`recovery`, §3.6), 0 in (b).** The keyword rule fires;
Tier 3. The code names no digest (it calls `identity.issue`), starts no thread (the test
reuses the existing boot helper), runs no subprocess, and carries no migration path; the
mechanism is not protective work — the words are the proxy, as Step 1 says they are.

## 6. Measurable proof and the pre-committed acceptance rule

Written before any code exists. All arms are **deterministic**: each outcome is binary (exit
code 0 vs non-zero; substring present vs absent; HTTP 200 vs 401/403), so the sample size is
N = 1 per arm and there is no statistical power question. The only way an arm can be
"underpowered" is if it cannot fail — which is why every positive arm ships a RED twin or a
positive control, named below.

### 6.1 Arms

**A1 — the token is real (REST round trip).**
`setup` a fresh data dir; read its secret with `atrest.read_secret`; boot the real
composition (`create_app` with that secret, the real wall clock, the test limits table) on a
uvicorn thread; run `token --data-dir D`; `GET /v1` with `Authorization: Bearer <stdout>` →
**200**. *RED twin:* the same GET with a token minted from a different secret → **401**.
(The twin proves the arm depends on the secret bridge rather than accepting any well-formed
token.)

**A2 — the issue's operator path, end to end (UI).**
`token --data-dir D` → `ui-login --gateway-url <base> --token <stdout>` → exit **0**; the
printed URL exchanges (303) and the resulting session record has
`scopes == {"stg:observe"}` and `expires_at <= <token expires_at>`.

**A3 — the signing secret never printed.**
Capture `token` and `token --json`: the raw secret string from `atrest.read_secret(D)` does
not appear in stdout or stderr; the JSON has no `secret` key and does have `token`.
*Positive control:* the same absence assertion applied to `setup --show-secret`'s output
**raises** — i.e. the detector can see a printed secret, so A3 is not a check that always
passes.

**A4 — least privilege by default.**
A default token satisfies `require_permission(..., "observe")` and fails
`require_permission(..., "control")` / `"admin"` (unit-level, using the seam's own
functions). *Control:* `--scope stg:control` widens (the flag is not inert).

**A5 — the default lifetime makes the documented path work.**
With the default token, `ui-login` with no `--ttl-mins` exits 0 (A2). *RED twin:* with
`--ttl-mins 5`, the identical `ui-login` invocation exits non-zero carrying `forbidden`.
(The twin proves the failure is the expiry bound and that the default matters — this is the
arm that catches the §1 correction.)

**A6 — expiry is what the payload claims.**
`token --ttl-mins 1`: `identity.validate(..., now=expires_at)` raises `expired`;
`identity.validate(..., now=expires_at - 1)` succeeds; the JSON `expires_at` is within ±2 s
of mint-second + 60.

**A7 — the default is pinned above the session ceiling.**
`assert _TOKEN_DEFAULT_TTL_S > app_entry._LIMITS["ui_session_ttl_ms"] // 1000`. A drift
guard: raising the gateway ceiling without raising the default reds here instead of at an
operator's terminal.

**A8 — issuance writes nothing.**
`sorted(p.name for p in D.iterdir())` is identical before and after `token`, and no
`-wal`/`-shm`/`.hold` file appears. Pins §3.6.

**A9 — failure envelopes (table-driven).**
(a) no env file → `token:` prefix, non-zero; (b) env file mode 0640/0644 → `env_file:`
naming `chmod 0600`, non-zero; (c) env file with `BENCHWEAVE_DB=x` → `env_file:` naming the
exclusion; (d) `--scope stg:root` → `token: unknown scope`, non-zero; (e) `--ttl-mins 0` →
click usage error (exit 2); (f) `BENCHWEAVE_SECRET=""` in the process env with a valid data
dir → `env_file:` non-zero. *RED twin for (f):* with the variable unset, the same data dir
succeeds — proving the refusal is about the blank value, not the fixture.

**A10 — no value echoed on a malformed file.**
An env file containing `BENCHWEAVE_SECRET <the-real-secret>` (no `=`) plus the real
`BENCHWEAVE_SECRET=` line → the refusal carries `env_file:` and **no part of the secret**.

### 6.2 Acceptance rule (pre-committed)

- **Ships** when A1–A10 all pass, every RED twin fails as specified, the Tier-3 refute (§8)
  reports no blocking finding, and the full gates battery is green (ruff, fresh-cache bare
  mypy, full suite, `win_core_manifest --check`).
- **Killed** if any of:
  - A1 or A2 cannot pass against a real composed gateway using only the data-dir file (the
    gateway's effective secret is not reproducible from the operator surface → the premise
    is wrong, return DON'T-BUILD);
  - A3's positive control does not raise (the leak detector is blind, so "never printed" is
    unproven);
  - A9(f)'s RED twin fails — i.e. a blank effective secret can reach the signer (a token
    anyone can forge must never be printed);
  - A5's RED twin succeeds — i.e. a 5-minute token can mint the default session (the
    expiry bound is not enforced and §3.4's reasoning is void).
- **Inconclusive, not conclusive** if A1 can only be run against a harness that injects the
  secret directly instead of through `bridge_env_file`: that would not test the bridge, so
  the arm must be re-pointed at the bridge before the rule is applied.
- **Rework, not silence,** if the `bridge_env_file` extraction reds an existing `serve`
  test on message drift — the fix is the message, not the test.

## 7. What this increment DEFERS

- `ui-login --data-dir` (option B) — unnecessary once `token` exists; the composition
  `$(benchweave token …)` already works.
- `--principal` — no authorization decision reads it (§3.4).
- Token revocation / listing / a token file — tokens are stateless HMAC; rotation of the
  secret is the only revocation and already has no command. Out of scope.
- `benchweave secret rotate`.
- A maximum `--ttl-mins` (§3.4's structural argument, risk R4).
- `--audience` (no shipped composition can change it).
- A machine pin on the operator guide's command count (obligation 23's human sweep stands;
  trigger for adding one: a third command-set prose surface goes stale).
- The `secret_posture` module extraction (§3.5's disclosed wart).
- Any change to REST/MCP auth, scopes, sessions, or the UI.
- Windows-core selection of the new test file beyond its `core 0` row.

## 8. Attack list — what the Tier-3 refute must attack

Tier 3 makes G6 mandatory: a second, independent reviewer runs this list. Each item states
the design's claim, so the pass falsifies rather than re-derives.

1. **Does `token` widen who can mint?** Try to obtain a token without read access to the
   env file: process-env shadow with a foreign secret, a symlinked `benchweave.env`, a
   directory where `is_file()` is true but `stat()`/`open()` differ, a file made readable
   between the two calls. The design's claim is that the file's filesystem permissions
   remain the gate — falsify it.
2. **Can the secret reach an output stream?** Any refusal message, traceback, `--json`
   payload, stderr note, or the `secret_source` field.
3. **Is the blank-secret refusal reachable and ordered correctly?** Every combination of
   {file has key, file lacks key} × {process env unset, blank, whitespace, set} ×
   {production, default} — assert none of them signs with an empty key. The
   file-lacks-key × blank-process-env combination is the hole found at design time
   (§3.2's `strip()` guard); look for a sibling.
4. **Is `secret_source` truthful?** Can it say `env-file` when the process value won, or
   the reverse?
5. **Is the audience constant safe to hardcode?** Prove no composition path can set a
   different audience (`create_app` and the three sub-builders), or show that A1 goes red
   when it does.
6. **Scope handling:** `--scope` repeated, duplicated, empty string, whitespace, a value
   with `|` or a space (the payload delimiter, `identity.py:55-74`), and a scope set that
   `TIER_SATISFIES` does not know.
7. **The `token:` prefix family** — collision with the existing refusal vocabulary
   (`env_file:`, `serve_locator:`, `serve_locator_conflict:`, `no_matching_rule:`), and
   whether any consumer parses stderr.
8. **Behaviour parity of the `bridge_env_file` extraction** — the serve refusals and the
   "loaded … (set …)" line must be byte-identical; run `tests/cli/test_serve.py` and
   `tests/cli/test_env_file.py` unchanged.
9. **The second-granularity boundary** in §3.4: a token minted and used in the same second
   at exactly the ceiling passes; +1 s fails. Confirm the default has slack, not luck.
10. **Windows:** the owner-only check returns early on win32 (`env_file.py:100-108`); does
    `token` inherit a Windows gap (a file readable under a foreign ACL)? State the residual,
    do not paper over it.
11. **Does any arm pass vacuously?** In particular A3 (the leak detector) and A4 (the
    permission check) — check the controls bite.
12. **Machine contract:** is putting the credential in a `--json` payload acceptable, given
    automation may log it? (Residual; the plain path exists for interactive use.)

## 9. Top risks, each with its falsifier

**R1 — the process environment shadows the file and the operator mints a token the local
gateway rejects.** Falsifier: A1 with `BENCHWEAVE_SECRET` exported to a foreign value yields
a 401, and the command's stderr names `process-environment`. Residual: the token is still
printed; the operator must read the note.

**R2 — a tuned `BENCHWEAVE_UI_SESSION_TTL_MS` above 12 h re-opens the `ui-login` refusal.**
Falsifier: set the knob to 16 h and observe the no-flag `ui-login` fail. Mitigation:
documented escape hatch (`--ttl-mins`), and A7 pins only the *default* ceiling. Not fixed in
this increment because reading the effective knob would duplicate `_limits_from_env`'s
parsing (deferred).

**R3 — the credential lands somewhere durable.** The token goes to stdout; `> file`
inherits the shell umask, and an interactive paste lands in shell history. Falsifier: none
machine-measurable; the guide's `export BENCHWEAVE_TOKEN="$(…)"` form is the mitigation.
Residual accepted (the same exposure `setup --show-secret` has).

**R4 — a long-lived bearer.** `--ttl-mins 1000000` mints an effectively permanent observe
token. Falsifier: the structural argument in §3.4 — the secret already grants unlimited
minting to anyone who can read it. Residual accepted; the default is 12 h and the grant is
observe-only.

**R5 — the extraction changes `serve`.** Falsifier: the existing `serve`/`env_file` suites
run unchanged; any message delta is a rework, not a test edit (§6.2).

**R6 — the posture import makes `token` fragile on a minimal install.** Falsifier: run the
command in the repo venv with no extra groups (`uv run benchweave token …`); `fastapi` and
`fastmcp` are hard dependencies (`pyproject.toml:30-41`), and
`serve_env_file_keys()` already imports `app_entry` on every env-file parse, so no new
dependency edge exists. If a real minimal-install failure appears, extract
`secret_posture` (§3.5 deferral triggers).

## 10. Falsifying this whole design

Return **DON'T-BUILD** if any of these is shown:

- A shipped path already produces a bearer token and the reporter missed it (search the
  Click tree for every command that can emit a token — today only `ui-login`, which
  consumes one).
- The secret the gateway uses is not reproducible from `--data-dir` alone (for example a
  deployment that sets `BENCHWEAVE_SECRET` from a service manager and points `--data-dir`
  at a file with a *different* secret): then a token command must take a secret source the
  operator names, which is a different (and larger) design. The stderr `secret_source` note
  is the diagnostic for this case, not a fix for it.
- The value cannot be measured: rejected — every arm above is deterministic and each has a
  twin that can fail.
