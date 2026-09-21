# BenchWeave Operator Guide

Everything an operator needs to install, run, and care for a BenchWeave
gateway — written from the **shipped** commands. Every `benchweave ...`
line below was verified against the installed CLI's `--help` output and is
copy-pasteable; the automated form of this guide is
`tests/integration/test_clean_install.py`, which drives the exact
setup → demo → report → backup → damage → restore → verify flow against a
wheel-installed `benchweave` binary.

Steps marked **[interactive]** open a Textual view when run on a TTY; they
fall back to plain text (or JSON with `--json`) when piped — the guide's
machine paths are what the test pins.

## 1. Install

From a checkout (development):

```sh
git clone <your-benchweave-checkout>
cd BenchWeave
uv sync                # dev environment (UV_PROJECT_ENVIRONMENT=venv)
uv run benchweave --version
```

From a built wheel (a clean install):

```sh
uv build                                        # dist/benchweave-<version>-py3-none-any.whl
uv venv /opt/benchweave-venv
uv pip install --python /opt/benchweave-venv/bin/python dist/benchweave-*.whl
/opt/benchweave-venv/bin/benchweave --version
```

The wheel is self-contained for the gateway runtime: the vendored contract
corpora and the BenchWeave simulator plugins ship inside it (under
`benchweave/_vendored/`). **The fixture lattice does not** — it is
operator-supplied input (`--fixtures` / `BENCHWEAVE_FIXTURES`; see
§4 Demo and §9 Troubleshooting).

### Second-install reuse

A second clean installation reuses the same published packages without
touching plugin source: install the **same built wheel** into a second
fresh venv, verify the vendored plugin trees are byte-identical to the
first install (and to the checkout's `plugins/benchweave/` — the
zero-plugin-source-changes proof), then repeat the demo from install two
with the same fixtures:

```sh
uv venv /opt/benchweave-venv-two
uv pip install --python /opt/benchweave-venv-two/bin/python dist/benchweave-*.whl
/opt/benchweave-venv-two/bin/benchweave --version

# Resolve SITE_* only after the installs above — earlier, the glob stays literal.
SITE_ONE="$(echo /opt/benchweave-venv/lib/python*/site-packages)"
SITE_TWO="$(echo /opt/benchweave-venv-two/lib/python*/site-packages)"
(cd "$SITE_ONE/benchweave/_vendored/plugins/benchweave" \
    && find . -type f ! -name '*.pyc' -print0 | sort -z | xargs -0 shasum -a 256) > /tmp/plugins-one.sha256
(cd "$SITE_TWO/benchweave/_vendored/plugins/benchweave" \
    && find . -type f ! -name '*.pyc' -print0 | sort -z | xargs -0 shasum -a 256) > /tmp/plugins-two.sha256
diff /tmp/plugins-one.sha256 /tmp/plugins-two.sha256 \
    && echo "install two reuses install one's plugin packages byte-for-byte"

(cd plugins/benchweave \
    && find . -type f ! -name '*.pyc' -print0 | sort -z | xargs -0 shasum -a 256) > /tmp/plugins-repo.sha256
diff /tmp/plugins-one.sha256 /tmp/plugins-repo.sha256 \
    && echo "the shipped trees are the checkout's plugin sources verbatim"

/opt/benchweave-venv-two/bin/benchweave demo \
    --scratch /tmp/demo-two --keep --fixtures /path/to/fixtures/execution --json
```

An empty `diff` (exit 0, the echo confirms) is the reuse evidence: the
second install resolved the same package bytes as the first and shipped
the sources verbatim — no plugin source was modified to repeat the demo.

## 2. Setup — the data directory

```sh
benchweave setup --data-dir /var/lib/benchweave
```

Creates `<data-dir>/state.sqlite` (migrations applied as at app boot),
`<data-dir>/content/`, and the 0600 credential file
`<data-dir>/benchweave.env` holding the generated gateway secret. The
secret is never printed unless you opt in:

```sh
benchweave setup --data-dir /var/lib/benchweave --show-secret --json
```

`--data-dir` can come from `BENCHWEAVE_DATA_DIR` instead of the flag (true
for `setup`, `backup`, `restore`, `report`, and `verify`). Every command
also takes `--json` for the stable machine contract.

## 3. Serve — run the gateway

`serve` composes the gateway from the environment and runs it under
uvicorn in the **foreground** (daemonization belongs to the service
manager — §7). It reads:

| Variable | Meaning |
|---|---|
| `BENCHWEAVE_DB` | **Required.** Path to the store (`<data-dir>/state.sqlite`). |
| `BENCHWEAVE_SECRET` | The gateway secret (the one `setup` wrote). |
| `BENCHWEAVE_ENV` | `production` arms the secret posture (below). |
| `BENCHWEAVE_HOST` / `BENCHWEAVE_PORT` | Bind address/port (also `--host`/`--port`; loopback + 8125 by default). |
| `BENCHWEAVE_FIXTURES` | Fixture lattice directory (see §4). |
| `BENCHWEAVE_REGISTRY_DIR` | Fixture registry root (default: the repository registry). |

```sh
export BENCHWEAVE_DB=/var/lib/benchweave/state.sqlite
export BENCHWEAVE_ENV=production
export BENCHWEAVE_SECRET="$(grep '^BENCHWEAVE_SECRET=' /var/lib/benchweave/benchweave.env | cut -d= -f2-)"
benchweave serve --host 127.0.0.1 --port 8125
```

**Production secret posture.** With `BENCHWEAVE_ENV=production`, `serve`
*refuses to boot* — before the store is opened, before anything touches
disk — if `BENCHWEAVE_SECRET` is unset, empty/whitespace, or a publicly
known value (the repo's test secret or the deploy example's placeholder).
Generate a real one: `openssl rand -hex 32`.

**Startup admission gate.** Before the gateway serves anything, the
fixture lattice passes the same admission gate execution and recovery
use: every document is decoded exactly, validated against the vendored
schemas (the OTDP device descriptors included) and pin-verified against
the bench's digest lattice. A lattice that fails refuses startup — the
process exits with `Application startup failed` and logs one
`startup_admission_rejected:` line carrying the typed reason
(`schema:`, `digest_mismatch:` or `pin_absent:`; an absent pinned file
raises a `FileNotFoundError` naming the device and digest prefix).
Nothing is written to the store by a refused startup, so a repair (fix
the lattice, restart) starts from a clean inventory. Under systemd the
unit then restart-loops (§7) and that log line is the diagnosis surface.

For the deployment env file, copy and fill the shipped example:

```sh
sudo cp deploy/systemd/benchweave.env.example /etc/benchweave/benchweave.env
sudo chown root:benchweave /etc/benchweave/benchweave.env
sudo chmod 0600 /etc/benchweave/benchweave.env
# edit /etc/benchweave/benchweave.env: BENCHWEAVE_SECRET=<your real secret>
```

## 4. Status and the demo

`status` speaks to a **live** gateway (observe tier or higher):

```sh
benchweave status --gateway http://127.0.0.1:8125 --token "$TOKEN"          # [interactive] on a TTY
benchweave status --gateway http://127.0.0.1:8125 --token "$TOKEN" --json
```

`--gateway`/`--token` can come from `BENCHWEAVE_GATEWAY`/`BENCHWEAVE_TOKEN`.

`demo` has two modes. **Fresh-install mode** (no `--gateway`) boots an
ephemeral, `SIMULATION`-labelled simulator gateway on a scratch directory —
never your data dir — runs the fixture procedure to a terminal state, and
tears down:

```sh
benchweave demo --fixtures /path/to/fixtures/execution --json
benchweave demo --scratch /tmp/demo --keep --fixtures /path/to/fixtures/execution   # keep the store for 'report'
```

> **Wheel installs must pass `--fixtures`.** The demo's fixture *default*
> resolves relative to the repository checkout (where the lattice lives
> beside its suites). In a wheel install that path does not exist, so the
> demo refuses with `fixture lattice not found at ...` until you pass
> `--fixtures <dir>` (or `BENCHWEAVE_FIXTURES`). The directory must carry
> `run-binding.json` — the repository's `fixtures/execution/` is the
> reference lattice. This is pinned by the clean-install test.

**Gateway mode** drives your *live* gateway instead (control tier token;
never labelled a simulation — the bench may be real hardware):

```sh
benchweave demo --gateway http://127.0.0.1:8125 --token "$TOKEN" \
    --fixtures /path/to/fixtures/execution --json
```

On a TTY both modes open a live event-fed view **[interactive]**; closing
it early is a clean exit. `--timeout` (default 120 s) bounds the wait for
a terminal state.

The demo refuses to compose if a live gateway already holds a store under
its scratch dir (one-coordinator rule — §9).

## 5. Report — run evidence

`report` reads the data directory **at rest** (never a live gateway;
`--gateway` is a documented not-implemented stub that refuses):

```sh
benchweave report --data-dir /tmp/demo --json
benchweave report --data-dir /var/lib/benchweave --out report.md         # markdown to a file
benchweave report --data-dir /var/lib/benchweave --bench sim-bench       # one bench
```

The report lists benches and runs (simulated ones labelled `[SIMULATION]`,
derived from the bench's stored commissioning limitation), every evidence
digest, and — honestly — any evidence whose backing bytes are gone
(`missing_evidence` is never papered over). On a TTY the report opens as a
view **[interactive]**. Like the other at-rest commands, the report takes
the store's exclusive lock for its whole read and refuses (naming the
holder) while a live gateway owns the store.

## 6. Backup and restore

```sh
benchweave backup --data-dir /var/lib/benchweave --out /var/backups/benchweave
benchweave verify  --data-dir /var/backups/benchweave/backup-<iso>     # any archive verifies
benchweave restore --archive /var/backups/benchweave/backup-<iso> --data-dir /var/lib/benchweave
benchweave verify  --data-dir /var/lib/benchweave                        # exit 0 iff clean
```

A backup is `backup-<iso>/` holding a self-contained SQLite snapshot
(`sqlite3` backup API — committed WAL frames folded in), a verbatim copy
of `content/`, and `manifest.json` with the sha256 of every file.
`restore` re-verifies **every** manifest digest, refuses any staged file
the manifest does not list (a backup tree is complete — extras are
tampering), and runs a SQLite integrity check on a staged copy *before*
anything in the data dir is touched, then swaps it in; your previous
directory is kept beside it as `<name>.pre-restore-<iso>`.

Both mutating commands refuse (naming the holder) while a live gateway
holds the store — stop the gateway first (§9).

> **Credentials are deliberately NOT backed up.** `benchweave.env` is
> never copied into a backup and never written by a restore: a backup
> covers *state + content* only. After restoring (especially onto a
> rebuilt machine) re-create or re-place your credential file yourself —
> `benchweave setup` on a fresh dir generates one; keep your existing
> secret safe and separate from the backup location. A restored gateway
> re-uses the operator's kept credential.

## 7. systemd deployment

The shipped unit template is `deploy/systemd/benchweave.service.template`:
the **nine hardening directives** from `deploy/PERMISSIONS-REVIEW.md` §3
(`Type=simple`, a dedicated `benchweave` user, `NoNewPrivileges`,
`ProtectSystem=strict` with a single `ReadWritePaths` data dir,
`PrivateTmp`, an empty `CapabilityBoundingSet`, `MemoryDenyWriteExecute`,
`EnvironmentFile`) plus additional §4 sandboxing. Render the two
placeholders and install:

```sh
sed -e 's|{{DATA_DIR}}|/var/lib/benchweave|g' \
    -e 's|{{ENV_FILE}}|/etc/benchweave/benchweave.env|g' \
    deploy/systemd/benchweave.service.template | sudo tee /etc/systemd/system/benchweave.service
sudo systemctl daemon-reload
sudo systemctl enable --now benchweave
journalctl -u benchweave -f
```

Preconditions the rendered unit assumes (and CI rehearses):
`useradd --system benchweave`, `/var/lib/benchweave/` (the one writable
root), and the filled `/etc/benchweave/benchweave.env`.

Every directive's threat rationale lives in
**`deploy/PERMISSIONS-REVIEW.md`** — read it before changing the unit.

> **macOS boundary.** Development happens on macOS, where neither systemd
> nor `systemd-analyze` exists. The unit's *syntax* gate is CI: the
> `systemd` job in `.github/workflows/ci.yml` renders the template and
> runs `systemd-analyze verify` on ubuntu-latest (plus a pytest assertion
> that no `{{...}}` placeholder survives rendering). Local macOS checks
> cover rendering only; behavioural verification of the unit happens on
> Linux.

## 8. Command reference

Eight commands — `benchweave --help` is the full surface:

| Command | One-liner | Key flags |
|---|---|---|
| `setup` | Initialize an at-rest data directory | `--data-dir` (req), `--show-secret`, `--json` |
| `serve` | Run the gateway (foreground) | `--host`, `--port` |
| `status` | Gateway identity + bench inventory (live) | `--gateway` (req), `--token` (req), `--json` |
| `demo` | Built-in simulator demonstration | `--gateway`/`--token`, `--scratch`, `--keep`, `--timeout`, `--fixtures`, `--json` |
| `report` | Run evidence from the store at rest | `--data-dir` (req), `--bench`, `--out`, `--json` |
| `backup` | Verified snapshot of store + content | `--data-dir` (req), `--out`, `--json` |
| `restore` | Verify an archive and swap it in | `--archive` (req), `--data-dir` (req), `--json` |
| `verify` | Manifest digests + store integrity | `--data-dir` (req), `--json` |

Exit codes: 0 on success; 1 on any handled refusal (bad usage, unreachable
gateway, rejected token, failed verify); 130 on Ctrl-C.

## 9. Troubleshooting

**A mutating command refuses, naming a holder** — e.g.
`refusing: a live gateway holds /var/lib/benchweave/state.sqlite` or
`store held by gateway gw-...`. One coordinator owns a store at a time:
stop the serving gateway (`sudo systemctl stop benchweave`) before
`backup`, `restore`, or pointing the demo's scratch at a held tree. The OS
releases the hold if the process died; a wedged gate self-clears on
process death.

**`startup_admission_rejected: ...` / `Application startup failed`** —
the fixture lattice failed the startup admission gate: a document is
schema-invalid (`schema:`), a digest pin disagrees with the bytes it
names (`digest_mismatch:`), a required pin or descriptor is missing
(`pin_absent:`), or a pinned file is absent from the lattice (a
`FileNotFoundError` naming the device and digest prefix). The gateway
refuses to boot and writes nothing to the store — the empty inventory is
by design, not data loss. Fix the lattice so every pinned document
agrees byte-for-byte with its pins and restart. The same damaged lattice
also logs `recovery_skipped` on any gateway that did boot before the
gate was wired; after repair those runs recover on the next restart.

**`fixture lattice not found at ...`** — the demo (or a gateway in
fresh-install posture) could not resolve the fixture lattice. Pass
`--fixtures <dir>` pointing at a directory carrying `run-binding.json`
(the repository's `fixtures/execution/`), or set `BENCHWEAVE_FIXTURES`.
Wheel installs have no repository default — the flag is required there.
The same variable feeds `serve`.

**`refusing to boot: BENCHWEAVE_ENV=production with an unusable
BENCHWEAVE_SECRET ...`** — production posture refuses an unset, empty, or
publicly-known secret (including the deploy example's placeholder). Set a
real secret in the env file (`openssl rand -hex 32`) and keep the file 0600.

**`missing required environment variable 'BENCHWEAVE_DB'`** — `serve`
composes from the environment; export `BENCHWEAVE_DB` (plus
`BENCHWEAVE_SECRET`/`BENCHWEAVE_FIXTURES`/`BENCHWEAVE_HOST`/`BENCHWEAVE_PORT`
as your deployment configures them), or use the env file from §3.

**`not_ready` registry posture** — on boot, stderr may say
`no fixture registry root — the registry admin change kinds stay not_ready
(fail-closed)`. The gateway runs, but the two registry change kinds are
unavailable: no `fixtures/registry/keys/main.pub.pem` trust root was found
(default resolved from the repository; wheel deployments point
`BENCHWEAVE_REGISTRY_DIR` at a copied registry root). This is the
documented fail-closed posture, not a crash.

**`archive ... has no manifest.json` / digest mismatches on restore** —
the target is not a `backup-<iso>/` directory, or its contents changed
after the backup. A damaged archive *must* refuse; take a fresh backup.

**Demo timing out** — `run <id> did not reach a terminal state within
120.0s (last state: ...)`: raise `--timeout`, or check the gateway's own
logs in gateway mode.
