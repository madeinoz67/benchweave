# BenchWeave Operator Guide

Everything an operator needs to install, run, and care for a BenchWeave
gateway: written from the **shipped** commands. Every `benchweave ...`
line below was verified against the installed CLI's `--help` output and is
copy-pasteable; the automated form of this guide is
`tests/integration/test_clean_install.py`, which drives the exact
setup → demo → report → backup → damage → restore → verify flow against a
wheel-installed `benchweave` binary.

Steps marked **[interactive]** open a Textual view when run on a TTY. They
fall back to plain text (or JSON with `--json`) when piped. The guide's
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
`benchweave/_vendored/`). The fixture lattice is **not** in the wheel. It
is operator-supplied input (`--fixtures` or `BENCHWEAVE_FIXTURES`; see
§4 Demo and §11 Troubleshooting).

### Second-install reuse

A second clean installation reuses the same published packages. It does
not touch plugin source. Install the **same built wheel** into a second
fresh venv. Make sure the vendored plugin trees are byte-identical to the
first install, and to the checkout's `plugins/benchweave/` (the
zero-plugin-source-changes proof). Then repeat the demo from install two
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

An empty `diff` (exit 0, the echo confirms) is the reuse evidence. The
second install resolved the same package bytes as the first. It shipped
the sources verbatim. No plugin source was modified to repeat the demo.

## 2. Setup: the data directory

```sh
benchweave setup --data-dir /var/lib/benchweave
```

Creates `<data-dir>/state.sqlite` (migrations applied as at app boot),
`<data-dir>/content/`, and the 0600 credential file
`<data-dir>/benchweave.env` holding the generated gateway secret. A store
that refuses to open with `refuse_newer_schema:` was written by a NEWER
gateway. Downgrade is refused. Open it with a gateway that knows the
schema. The secret is never printed unless you opt in:

```sh
benchweave setup --data-dir /var/lib/benchweave --show-secret --json
```

On Windows, mode bits do not reach a file's access list, so `setup` does the
equivalent instead. `setup` creates `benchweave.env` in a private staging
directory. It strips inherited entries. It grants the file to the account
running `setup` alone. Only then does it give the file the secret and move
it into place, so no other account can open it at any point. Check it with
`icacls <data-dir>\benchweave.env`, which should list
one entry. Run the gateway under that same account. On a volume with no
access lists (FAT, exFAT) `setup` refuses rather than write a secret it cannot
protect. Only the credential file is restricted. The rest of the data
directory keeps whatever access its location gives it, so choose that
location as you would on Linux.

`--data-dir` can come from `BENCHWEAVE_DATA_DIR` instead of the flag (true
for `setup`, `backup`, `restore`, `report`, and `verify`). Every command
also takes `--json` for the stable machine contract.

### Optional: admitting transport providers (`transport-settings.json`)

A descriptor may declare a transport provider (a pinned, reviewed
provider contract — OTDP 0.2.2 `transport-providers.md`). The gateway
refuses such a descriptor unless the operator has admitted its contract
through an optional `transport-settings.json` placed in the fixtures
directory (beside `bench.json` and `commissioning.json`):

```json
{
  "config_version": "1",
  "admitted": [
    {
      "id": "urn:otdp:transport-provider:reference-hid:1.0.0",
      "version": "1.0.0",
      "sha256": "<64-hex digest of the reviewed contract bytes>",
      "feature_id": "otdp.transport.reference-hid/1.0.0",
      "document": "providers/reference-provider.json"
    }
  ],
  "connections": [
    {"connection_key": "power_meter", "provider_id": "urn:otdp:transport-provider:reference-hid:1.0.0"}
  ]
}
```

The gateway validates the document at startup, before any lattice
admission: `document` names a settings-relative file whose bytes must hash
to the admitted `sha256` and validate as a provider contract. Your
admission record and the reviewed bytes are one act. The surface carries
IDENTITY ONLY: there is no field for an endpoint, path, process,
credential, or secret, by schema rather than by policy. Endpoint and
secret configuration arrives with the first provider implementation
through the execution-standard commissioning shape (deferred; see the
issue #147 increment-3 design record), never through this file. An
approval that has expired (`approval.expires_at` in the contract, judged
at startup) is not an admitted contract. Re-admit the renewed bytes.

Run admission reads this same settings document: each run's spool resolves
a descriptor's pinned provider contract beside it and threads the fixtures
directory's `transport-settings.json` with a fresh wall stamp, so a
provider-declaring lattice executes under the admissions recorded here.
Bootstrap and the run path apply one standard.

## 3. Serve: run the gateway

`serve` composes the gateway from the environment and runs it under
uvicorn in the **foreground** (daemonization belongs to the service
manager; see §9). It reads:

| Variable | Meaning |
|---|---|
| `BENCHWEAVE_DB` | **Required.** Path to the store (`<data-dir>/state.sqlite`). |
| `BENCHWEAVE_SECRET` | The gateway secret (the one `setup` wrote). |
| `BENCHWEAVE_ENV` | `production` arms the secret posture (below). |
| `BENCHWEAVE_HOST` / `BENCHWEAVE_PORT` | Bind address and port (also `--host` and `--port`; loopback + 8125 by default). |
| `BENCHWEAVE_FIXTURES` | Fixture lattice directory (see §4). |
| `BENCHWEAVE_REGISTRY_DIR` | Fixture registry root (default: the repository registry). |
| `BENCHWEAVE_MAX_DATASET_BYTES` | Per-run capture-byte ceiling; **required for adapter-bridge runs** (see below). |
| `BENCHWEAVE_MAX_EVENT_BATCH` | Per-run event-landing batch ceiling; **required for adapter-bridge runs** (see below). |
| `BENCHWEAVE_UI` | Compose the browser UI at `/ui` (default: on; `0`/`false`/`off` disables it — the routes are absent, not stubbed). |
| `BENCHWEAVE_UI_LOGIN_CODE_TTL_MS` | Login-code lifetime (default 60000). |
| `BENCHWEAVE_UI_SESSION_TTL_MS` | Browser-session lifetime ceiling (default 28800000, 8 h). |
| `BENCHWEAVE_UI_MAX_BRIDGES_PER_SESSION` | Live event-stream bridges per browser session (default 4). |

```sh
export BENCHWEAVE_DB=/var/lib/benchweave/state.sqlite
export BENCHWEAVE_ENV=production
export BENCHWEAVE_SECRET="$(grep '^BENCHWEAVE_SECRET=' /var/lib/benchweave/benchweave.env | cut -d= -f2-)"
benchweave serve --host 127.0.0.1 --port 8125
```

**Production secret posture.** With `BENCHWEAVE_ENV=production`, `serve`
*refuses to boot*, before the store is opened and before anything touches
disk, if `BENCHWEAVE_SECRET` is unset, empty or whitespace, or a publicly
known value (the repo's test secret or the deploy example's placeholder).
Generate a real one: `openssl rand -hex 32`.

**Startup admission gate.** Before the gateway serves anything, the
fixture lattice passes the same admission gate that execution and recovery
use. Every document is decoded exactly, validated against the vendored
schemas (each OTDP device descriptor against the schema of its own
`otdp_version` pin) and pin-verified against the bench's digest lattice.
A lattice that fails refuses startup. The process exits with
`Application startup failed` and logs one `startup_admission_rejected:`
line carrying the typed reason (`schema:`, `digest_mismatch:` or
`pin_absent:`, plus the version prefixes below where a pin
misclassifies; an absent pinned file raises a `FileNotFoundError` naming
the device and digest prefix). A refused startup writes nothing to the
store, so a repair (fix the lattice, restart) starts from a
clean inventory. Under systemd the unit then restart-loops (§9). That
log line is the diagnosis surface.

**Version pins, conformance classes, and the operator acknowledgement.**
Admission classifies each device descriptor's `otdp_version` pin against
the gateway's dependency policy before schema validation. A served pin
conforms and validates against its own digest-verified bytes — the pin
does not have to be the corpus's active version. A yanked pin also
conforms; the admission record and the run's evidence stream carry a
deprecation warning naming the derived move-to. A **retained but
out-of-range** pin is **non-conforming**: the gateway can validate it
against its own retained bytes, but loads it only behind a recorded
per-device **operator acknowledgement**. The acknowledgement is a
mapping of device id to the exact OTDP pin it covers: authored in an
optional `operator-acknowledgements.json` beside the lattice documents
(`{"acknowledgements": {"<device-id>": "<otdp-version>"}}`, validated
fail-closed — a malformed file refuses startup by name), threaded to
startup and recovery admission by the shared resolution body. It binds
the pin it names, so an acknowledgement recorded for one version does
not authorise a device later re-pinned to another, and one
acknowledgement cannot cover a bench's other devices. When a
non-conforming device admits, the recorded acknowledgement (stamped
with the admission's time) appears on the admission record, on the
run's evidence stream alongside the pin and its class, and on the
device's stored row (the read surfaces derive from that row: an
acknowledged device does not re-warn on every read). A non-conforming
device is never silently shown as conforming. Without the
acknowledgement, admission refuses with
`operator_ack_required:` (carrying the `standard_nonconforming:`
classification).

The remaining pin classes refuse outright, each with the five inline
fields (standard, pinned version, supported range, derived move-to,
migration-note pointer): `retired_identifier:` (the number was used
once and is never reissued; the refusal names the next minor to
re-target to), `version_unknown:` (this corpus never carried the
version; publish it or fix the pin), and
`cross_constraint_violation:` (the bench's execution version constrains
the OTDP range its devices may pin; a pin outside it refuses naming
both versions and the constraining row's evidence. An operator
acknowledgement authorises the version window, never the execution
runtime interface). A non-conforming pin in the startup lattice without
a matching entry in `operator-acknowledgements.json` is a hard
`startup_admission_rejected:` refusal. With one, it loads flagged, and
withdrawing the file withdraws the authorisation at the next startup.

The execution lattice is itself pinned (issue #220): the bench document's
own `contract_version` selects the vendored execution corpus version all
five documents validate against — the pin's digest-verified bytes, not
the gateway's active version. Its refusals carry the same
machine-matchable vocabulary and the five inline fields:
`version_unknown:`, `retired_identifier:`, and `standard_nonconforming:`
— a non-conforming execution pin refuses outright; no operator
acknowledgement authorises it (an acknowledgement covers an otdp window,
never the execution runtime interface). A lattice that pins a non-active
execution version still validates and loads at startup — the
procedure-author story — and a run request over it is legal (issue #260,
the record lane): the run's terminal record carries and validates at the
LATTICE's own execution version, with an
`implementation_disclosure:` reason naming both versions whenever they
differ. RUNNING is an implemented-dialect fact: every run's device pins
must satisfy the COMPOSITION's cross-constraint row — the same
`cross_constraint_violation:` refusal admission raises, subject rewritten
to "this gateway runs", refused synchronously at run start (typed
`policy_denied`, before any lease is consumed) and authoritatively at the
worker. The synchronous refusal is BEST-EFFORT: it reads the binding,
bench and descriptor documents from the content store, and an UNSTORED
document skips it — that class of start stays asynchronous (202, then
`outcome_unknown` under the worker's poison guard); the worker's floor
over the full admission result is the authority. A composition version
whose standard declares no row asserts no floor — the same per-version
honest negative admission has. A stored run whose binding names a carried
execution dialect other than the active one (an era run) is terminalized
at restart recovery against its OWN version: doc-first (the stored binding
document's const), echo-judged when the doc is absent,
`interrupted`/`unknown` as recovery always prescribed. The echo is judged
three ways: carried → the era record; retired-but-RETAINED → the era
record stamped from the retained bytes (a later retirement never flips an
era run to a composition stamp and never wedges it); everything with no
retained bytes (never carried, a retired identifier, unclassifiable) is
caller data and terminalizes exactly as before. The containment
class is an unresolvable record — a doc/echo
disagreement or an unjudgeable or const-less doc const — left
non-terminal and logged `recovery_execution_version_unresolved:`. RETIRED
vocabulary (an old log
grep finds it here): `execution_version_not_runnable:` was the pre-record-
lane run guard (superseded by the floor + threading above) and
`recovery_execution_version_not_runnable:` was the pre-record-lane era
skip (superseded by era terminalization).

**Adapter-bridge runs and the quota seam.** A run constructs a real OTDP
bridge for a bench device only when the device's descriptor declares
`integration.mode: "adapter"` AND the device's declared `generation`
carries a registry activation record: the admin act that commissioned the
package closure (admission wrote the content-addressed cache and the
package lock; the run resolves through them, digest-pinned). Devices
without a commissioned closure, including the demo lattice's (which
declare the startup-admitted generation), run the committed simulator
plugins instead, disclosed with one `run_device_declarative_fallback:`
log line per device per run. Bridge-constructing runs additionally
**require** the two operator ceilings `BENCHWEAVE_MAX_DATASET_BYTES` and
`BENCHWEAVE_MAX_EVENT_BATCH`. If they are unset, that is a valid, loud
posture: the run refuses with `run_quota_config_absent:` before any
device opens, the worker contains the job, and the run's projection
closes terminal with `outcome_unknown`. No outcome is fabricated.
`max_capture_bytes` and `max_subscriptions` keep built-in defaults until
your bench qualification commissions values (they are not env-configured
today).

### Shutdown drain

On shutdown the gateway stops the run worker, then gives it a bounded
drain: 5 seconds for in-flight and queued runs to finish. Runs that
complete within the bound close normally. The gateway does not wait out
anything still outstanding when the bound expires. It logs one
`run worker did not drain at shutdown` line and exits, and the next
startup's recovery sweep records those runs `interrupted` with safe state
`unknown`: an honest "we do not know how this ended", never a fabricated
outcome.

> **WARNING:** RECOVERY DOES NOT TOUCH THE BENCH. VERIFY THE BENCH'S
> PHYSICAL STATE BEFORE YOU START NEW WORK.

A run whose durable record already says
it completed keeps that record; only its stale queue state is reconciled.
The worker thread is a daemon and the bound is a fixed
grace in the gateway's shutdown path, so an external service manager (§9)
remains the real limit on total shutdown time; plan restarts accordingly
when runs can exceed the grace.

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
ephemeral, `SIMULATION`-labelled simulator gateway on a scratch directory,
never your data directory. It runs the fixture procedure to a terminal
state, and tears down:

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

On a TTY both modes open a live event-fed view **[interactive]**. If you
close it early, the exit is clean. `--timeout` (default 120 s) bounds the
wait for a terminal state.

The demo refuses to compose if a live gateway already holds a store under
its scratch dir (one-coordinator rule — §11).

## 5. Report: run evidence

`report` reads the data directory **at rest** (never a live gateway;
`--gateway` is a documented not-implemented stub that refuses):

```sh
benchweave report --data-dir /tmp/demo --json
benchweave report --data-dir /var/lib/benchweave --out report.md         # markdown to a file
benchweave report --data-dir /var/lib/benchweave --bench sim-bench       # one bench
```

The report lists benches and runs (simulated ones labelled `[SIMULATION]`,
derived from the bench's stored commissioning limitation), every evidence
digest, and, honestly, any evidence whose backing bytes are gone
(`missing_evidence` is never papered over). On a TTY the report opens as a
view **[interactive]**. Like the other at-rest commands, the report takes
the store's exclusive lock for its whole read and refuses (naming the
holder) while a live gateway owns the store.

## 6. Retention: disposal projection (read-only)

`retention` reads the data directory **at rest** and projects, from a
policy file plus the store's own rows, when each capture and evidence row
becomes disposable and how fast storage grows. It is a pure
projection: **it writes nothing back**, no classification stamps, no
cached disposal dates. **It never migrates the store**, and nothing
deletes or archives anything here (`on_disposition` is a report label in
this command; the audited disposition path is the `dispose` command
below).

```sh
benchweave retention --data-dir /var/lib/benchweave --json
benchweave retention --data-dir /var/lib/benchweave --out retention.md
benchweave retention --data-dir /var/lib/benchweave --policy /etc/benchweave/retention-policy.json
benchweave retention --data-dir /var/lib/benchweave --horizon-s 604800
```

**Schema mismatches refuse (they never upgrade).** A store behind the
gateway's schema version, including a *holey* `schema_migrations` (any
applied-migration row missing, not only a lower newest version), or
written by a newer one, refuses with a `retention_store:` message naming
the mismatch. Exit code 1 applies, like every handled refusal. To project a
down-level store, open it once with a current gateway
(`setup`/`serve`/`report` upgrades it) and re-run. (`report` still shares
the old migration-on-open shape; aligning it is a follow-up, deferred in
the design record.)

> **WAL note.** Opening the store folds a crashed writer's hot
> write-ahead log into `state.sqlite` (a SQLite checkpoint on close): the
> report writes no table content (that is pinned), but the file's
> *bytes* can change. The write-back rule is logical-table, not
> byte-forensic; workflows that compare file bytes before and after a
> copy should quiesce the store first (or copy the backup command's verified
> snapshot instead).

The policy file defaults to `<data-dir>/retention-policy.json`; absent
there, every row reports `ungoverned`. A policy file that is present but
invalid refuses, as does an explicitly passed `--policy` that is missing.
The document is validated gateway-side: `duration_s` (integer seconds ≥
1, bounded by the datetime domain ceiling 253402300799), `retain_after`
(`landing` or `run_end`; `last_access` refuses until the store durably
tracks access times), `on_disposition` (`delete`/`archive`/`review`),
`hold: true` (no disposal date), and data-class selectors
`capture:<format>` / `evidence:<kind>` (dots and uppercase admitted —
any class the report can name is governable; the capture lane stays a
closed vocabulary). Resolution: bench class → bench default → global
class → global default — and every row names the **winning** entry
(`matched_selector`, `matched_scope`, `matched_rule`), never a shadowed
rule.

Each disposal row carries its status: `scheduled` (with the computed
`disposal_date`), `held` (no date: the rule keeps the row), `ungoverned`
(no policy matched), or `anchor_unresolved` (no resolvable offset-bearing
anchor: a missing terminal record, a naive or unparseable stamp). The
count of `anchor_unresolved` rows is disclosed. `run_end` anchors on the
run's terminal record `ended_at` (immutable), never the run-state
projection stamp.

The report discloses its own arithmetic, per lane with its basis and
denominator: stored bytes are `SUM(LENGTH(data))` over the artifact table
(content-addressed dedup under-counts); the growth lanes sum **per-row**
artifact lengths / charged bytes (shared artifacts over-count per row);
and the quota wedge forecasts the capture writer's **reservation ledger**
(staged reserved + finalised charged — the figure G3 enforces; the ledger
is not monotone: finalise re-prices and the abort sweep refunds).

**Growth projection.** Per stream and key the wire carries
`observed_bytes`, `observed_span_s`, `n`, `rate_Bps` and
`projected_horizon_bytes`. The rate is extrapolated over one
operator-chosen horizon (`--horizon-s`, default 2592000 s / 30 days,
accepted range 1..253402300799, the datetime-domain ceiling, the same
bound `duration_s` carries). The value is the same for every row, so
projections are comparable. Unestimable streams (single event, zero
span, naive or unparseable stamps) render absence: excluded, counted and
disclosed, never a zero projection. Held classes (every governing rule
is `hold: true`) project the same horizon growth, labelled `held` (they
never empty at disposal time).

**Quota wedge.** Per capture context (per run), used bytes from the
writer's ledger and the time to exhaust `--max-dataset-bytes` (or
`BENCHWEAVE_MAX_DATASET_BYTES` — both knobs validate identically: an
integer ≥ 1, or a typed refusal). States: `forecast` (exhaustion at a
date), `at_ceiling` (G3 refuses new captures now), `over_ceiling`
("over ceiling by N bytes" — never a negative forecast), `zero_growth`
("measured zero growth", n/span shown), `unestimable_rate` (no rate —
never a clean 0), `ceiling_unknown` ("ceiling unknown; projection
omitted"). A forecast whose exhaustion instant falls beyond the datetime
domain keeps `time_to_exhaustion_s` (the honest figure) and renders the
instant absent, disclosed — it never kills other rows' output. A closed
run's row is labeled `run closed` and carries no
exhaustion forecast. Hold-heavy exhaustion hard-blocks new captures — that wedge is
disclosed in the report, and the remediation is now the audited path:
`benchweave dispose --execute` (next section) reclaims overdue
delete-tier rows under the store hold. Review-tier rows remain blocked
there; archive-tier rows move offline when dispose runs with
`--archive-target` (verified content-addressed copies; the store copy is
reclaimed); otherwise raise the ceiling.

Under `--bench`, rows whose run exists on another bench filter out;
unattributed keys (including `run:` keys whose run has no run row)
always stay and are disclosed by count. Like the other at-rest commands,
`retention` takes the store's exclusive lock for its whole read and
refuses (naming the holder) while a live gateway owns the store.

## 7. Dispose: audited delete-tier disposition

`dispose` is the audited path the retention wedge disclosure points at:
it deletes overdue **delete-tier** rows (finalised captures and evidence
rows whose governing policy rule says `on_disposition: delete` and whose
disposal date has passed) **through a complete audit trail** — the plan,
the audit record and the deletion commit in ONE transaction, so a
committed deletion without its audit row cannot happen.

```sh
benchweave dispose --data-dir /var/lib/benchweave                 # dry run (default): writes nothing
benchweave dispose --data-dir /var/lib/benchweave --execute       # dispose through the audit trail
benchweave dispose --data-dir /var/lib/benchweave --policy /etc/benchweave/retention-policy.json --execute
benchweave dispose --data-dir /var/lib/benchweave --bench sim-bench --execute
benchweave dispose --data-dir /var/lib/benchweave --execute --archive-target /mnt/offline/benchweave
benchweave dispose --data-dir /var/lib/benchweave --verify-archive --archive-target /mnt/offline/benchweave
```

> **CAUTION:** DELETE IS IRREVERSIBLE. THE AUDIT ROW RETAINS THE DELETED
> CONTENT'S DIGEST AND BYTE LENGTH, NEVER THE BYTES. ARCHIVAL IS THE
> RECOVERABLE TIER.

**Dry run by default; `--execute` to act.** Without the flag the command
projects the plan (per-row outcome, counts, bytes that would be
reclaimed) and writes nothing — every table stays byte-identical. With
`--execute` the whole invocation commits as one transaction: the
invocation row, one audit row per disposed row (its full decision
envelope content-addressed as an artifact, digest pinned in the row),
the guarded exact-row deletions, and artifact garbage collection that
counts live references only.

**A policy is required.** Disposition never runs ungoverned: with no
policy file at the default location and no `--policy`, the command
refuses typed. Review-tier rows are **blocked** (moving a row out of
review is a policy edit); archive-tier rows execute only with
`--archive-target` — without one they are **blocked and never deleted**
(the output names the missing flag), and the delete-tier rows in the
same invocation still execute. Blocked counts are in the output.

**Never migrates the store.** Like `retention`, a schema mismatch (a
store behind the gateway, holey, or newer) refuses with a
`retention_store:` message naming the mismatch and the upgrade path
(open it once with a current gateway, then retry). A missing v6
disposition-table store refuses the same way.

**Delete is irreversible.** Each audit row retains the deleted
content's digest and byte length (`deleted_artifact_id` /
`deleted_byte_length`), never the bytes — delete reclaims space (the
capture ledger and the G3 allowance recover immediately); it is not a
backup. Archival is the recoverable tier (below). The audit trail
itself (`dispositions` / `disposition_invocations`) is history, never
deleted, and is not governed by the policy it audits.

### The archive tier (`--archive-target`)

`on_disposition: archive` rows become executable when you name an
offline destination directory:

```
<target>/
  objects/<artifact_id>            # the preserved bytes, named by content
                                   #   address (art-<sha256>) — the same id
                                   #   as the in-store artifact had
  manifests/<invocation_id>.json   # canonical JSON: invocation id, actor,
                                   #   policy digest, written_at, resolved
                                   #   destination, objects + lengths, counts
```

**Copy-verify-commit ordering (the crash story).** The offline
filesystem is outside the SQLite transaction, so ordering — not
atomicity — is what makes the move honest. Every distinct archived
object is staged and re-verified at the destination BEFORE the store
transaction opens: temp file → fsync → atomic `os.replace` → re-read
from the destination → re-hash against the content address (a power
loss after COMMIT cannot leave the trail referencing bytes that never
reached the destination platter). A crash may therefore leave the
destination holding MORE bytes than the committed trail references —
**over-preserved, never under-preserved**. Objects whose invocation
never committed are content-addressed and verify-and-skip on re-run;
`--verify-archive` reports the leftovers as orphans. Staging is
STREAMING: objects are placed one payload at a time and every hash
runs in 1 MiB blocks, so the invocation's peak memory is bounded at
one artifact's payload plus block overhead — it does not scale with
the number or total size of archived objects (pinned by a tracemalloc
ceiling over a two-8-MiB-artifact archive).

**Mixed invocations are one transaction.** A plan with both tiers
executes in the ONE transaction: a crash or refusal disposes nothing of
either tier. Re-runs are idempotent (content-addressed objects
verify-and-skip; committed rows cannot be re-selected). A re-run that
selects nothing stages nothing and writes NO manifest — manifests ride
the staging pass and describe the objects it placed; the store's
invocation row is the no-op's record.

**The manifest has no consumer in the tooling.** It is an operator-facing
index: the committed trail row is the commitment record and the
machine-read authority (`--verify-archive` reads the trail, never the
manifest). The asymmetry worth naming: under TOTAL store loss the
manifests are the only surviving index of what was archived — the trail
they summarize is gone with the store — yet nothing in the tooling
consumes them today. Treat them as durable operator documentation, not
as verification input.

**`archive_verified_at` is the plan instant.** It is the caller-supplied
`now` of the invocation (STO-1) — one instant for the whole invocation —
and the destination objects are fsynced and re-read around it, so an
object's file mtime can land before OR after the recorded instant.
mtime-vs-`archive_verified_at` is therefore NOT a valid forensic
ordering signal; the trail's proof is the content address, not
timestamp comparisons.

**Typed refusals** (the `archive_target:` family): an unwritable or
uncreatable target; a target resolving inside the data dir (refused:
`restore` swaps the whole data directory, and an archive inside it
would be destroyed by disaster recovery); a pre-existing destination
object whose bytes do not hash to its content address (never silently
overwritten: overwriting would launder destination corruption into a
fresh "verified" copy).

**The audit columns, record vs reference.** An archived row's audit
envelope carries `archived_artifact_id`, `archived_byte_length`,
`archive_destination`, `archive_verified_at` (the instant the
destination re-read matched — the plan instant, one per invocation);
`deleted_artifact_id` stays NULL and `deleted_byte_length` 0 (nothing
was destroyed). `archived_artifact_id` is a RECORD, never a live
reference — the same grammar as `deleted_artifact_id`: counting it in
the artifact GC would keep every archived artifact in the store forever
and defeat the move. Once no live row references it, the in-store copy
is collected; the offline object is the survivor, and the trail row
plus its decision artifact stay in the store as the finder's index. An
artifact shared with a retained row survives in-store AND exists
offline (sharing is a store concept; the object is the content).
Archived captures relieve the G3 ledger exactly like deleted ones.

**What "archived" does NOT prove: destination health.** The trail
proves the copy was byte-identical at `archive_verified_at`; the medium
can rot or be deleted afterwards. `--verify-archive` re-proves every
archived row's object (present, re-hashed, length matched) and names
drift per object (`absent` / `digest_mismatch` / `length_mismatch`,
exit 1 on any drift); orphans are reported, never deleted. **Verify
reads each row's recorded `archive_destination`**; that column is what
it exists for, so archiving later batches to a second target never
makes earlier rows read as drift. The `--archive-target` flag is only a
fallback for rows that lack a recorded destination (it stays the
store/dispose-time argument). Relocating a destination directory
therefore reads as `absent` at the recorded path: the trail names where
the copy was verified, not where bytes may have been moved since.
Restoring archived bytes back into a store is deferred (design record
D1 — first operator request); the verify arm is its trust basis.

**Ledger relief, in two named units.** Disposing finalised captures
drops their charged bytes from the per-context reservation ledger
(`charged_ledger_bytes`, the figure G3 enforces), so an at/over-ceiling
context recovers headroom exactly when its delete-tier rows go. What the
artifact GC physically removes from disk is reported separately as
`artifact_bytes_freed`: evidence rows sharing one artifact make a plain
row-bytes sum double-count and diverge from physical disk, so the two
units are never summed across meanings (the row-bytes figure is kept as
`bytes_reclaimed`, labelled as the projection sum).

**Bench scope is inherited from the report.** Under `--bench`, rows whose
run exists on another bench are excluded — but unattributed keys and
non-run-prefixed context keys stay in scope by the report's
never-vanish rule. A bench filter is therefore not a containment
boundary for keys that never mapped to a bench; scope your policy
selectors if you need finer containment.

Like the other at-rest commands, `dispose` takes the store's exclusive
lock for its whole run (a maintenance window: stop the gateway first)
and refuses, naming the holder, while a live coordinator owns the store.
Scheduling is operator-side (cron/systemd); the command is the bounded,
operator-invoked unit.

## 8. Backup and restore

```sh
benchweave backup --data-dir /var/lib/benchweave --out /var/backups/benchweave
benchweave verify  --data-dir /var/backups/benchweave/backup-<iso>     # any archive verifies
benchweave restore --archive /var/backups/benchweave/backup-<iso> --data-dir /var/lib/benchweave
benchweave verify  --data-dir /var/lib/benchweave                        # exit 0 iff clean
```

A backup is `backup-<iso>/` holding a self-contained SQLite snapshot
(`sqlite3` backup API; committed WAL frames folded in), a verbatim copy
of `content/`, and `manifest.json` with the sha256 of every file.
`restore` re-verifies **every** manifest digest, refuses any staged file
the manifest does not list (a backup tree is complete; extras are
tampering), and runs a SQLite integrity check on a staged copy *before*
anything in the data directory is touched, then swaps it in. The
previous directory is kept beside it as `<name>.pre-restore-<iso>`.

Both mutating commands refuse (naming the holder) while a live gateway
holds the store. Stop the gateway first (§11).

> **CAUTION:** A BACKUP DOES NOT COPY THE CREDENTIAL FILE, AND A RESTORE
> DOES NOT WRITE IT. `benchweave.env` IS DELIBERATELY NOT BACKED UP: A
> BACKUP COVERS *STATE + CONTENT* ONLY. AFTER A RESTORE (ESPECIALLY ONTO
> A REBUILT MACHINE) RE-CREATE OR RE-PLACE YOUR CREDENTIAL FILE YOURSELF.
> `benchweave setup` on a fresh dir generates one; keep your existing
> secret safe and separate from the backup location. A restored gateway
> re-uses the operator's kept credential.

## 9. systemd deployment

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

## 10. Command reference

Twelve commands — `benchweave --help` is the full surface:

| Command | One-liner | Key flags |
|---|---|---|
| `setup` | Initialize an at-rest data directory | `--data-dir` (req), `--show-secret`, `--json` |
| `serve` | Run the gateway (foreground) | `--host`, `--port` |
| `status` | Gateway identity + bench inventory (live) | `--gateway` (req), `--token` (req), `--json` |
| `ui-login` | Mint a one-use browser login URL (the URL expires in 60 s; the session is at most as wide as the token) | `--gateway-url` (req), `--token` (req), `--scope` (repeatable), `--ttl-mins`, `--json` |
| `demo` | Built-in simulator demonstration | `--gateway`/`--token`, `--scratch`, `--keep`, `--timeout`, `--fixtures`, `--json` |
| `report` | Run evidence from the store at rest | `--data-dir` (req), `--bench`, `--out`, `--json` |
| `retention` | Disposal/growth projection (read-only; never migrates the store) | `--data-dir` (req), `--bench`, `--policy`, `--max-dataset-bytes`, `--horizon-s`, `--out`, `--json` |
| `dispose` | Audited disposition (delete tier; archive tier with `--archive-target`; dry run by default; never migrates the store) | `--data-dir` (req), `--bench`, `--policy`, `--execute`, `--archive-target`, `--verify-archive`, `--out`, `--json` |
| `backup` | Verified snapshot of store + content | `--data-dir` (req), `--out`, `--json` |
| `restore` | Verify an archive and swap it in | `--archive` (req), `--data-dir` (req), `--json` |
| `verify` | Manifest digests + store integrity | `--data-dir` (req), `--json` |
| `evidence` | Generate/index the retained evidence tree (`runs`/`timing`/`faults`/`index`) | `--dest` (req), `--count`, `--seed`, `--timeout`, `--fixtures`, `--json` |

The standards family is a separate argparse tree rather than a `benchweave`
subcommand — `python -m benchweave.standards --help` is its authority (the
operator-facing commands above are the shipped binary; these manage the
vendored standards corpus a checkout carries):

| Subcommand | One-liner |
|---|---|
| `export` | Write the SDK-facing bundle |
| `check` | Verify the pinned SDK against a fresh export |
| `matrix` | Write or verify `docs/compatibility-matrix.md` |
| `versions` | Print main, standard, SDK lock and submodule versions |
| `repin` | Recompute corpus-manifest sha256 rows from the on-disk corpus |
| `list` | Print per-standard range, retained/carried/served sets, yanks, retirements |
| `pin` | Resolve a package's constraints into its `contracts/lock.json` |
| `upgrade` | Move exactly one standard's lock row to a precise version |
| `why` | Explain the current resolution: per standard, the rung that fired |

Exit codes: 0 on success; 1 on any handled refusal (bad usage, unreachable
gateway, rejected token, failed verify); 130 on Ctrl-C.

## 11. Troubleshooting

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

**`run_quota_config_absent: ...`** — a run on an adapter bench (a device
whose declared generation carries an activation record) tried to construct
bridges without the required operator ceilings. Set
`BENCHWEAVE_MAX_DATASET_BYTES` and `BENCHWEAVE_MAX_EVENT_BATCH` in the
gateway's environment and restart. Benches without commissioned adapter
closures never hit this refusal.

**`run_device_declarative_fallback: ...`** — an adapter-mode descriptor
with no commissioned closure for its declared generation ran the committed
simulator plugin instead of a bridge. If this is unexpected, the bench's
device `generation` and the gateway's activation records
(`<data-dir>/registry/activations/<bench>/activation-<n>.json`) drifted
apart. Check which generation the admin act actually activated.

**`archive ... has no manifest.json` / digest mismatches on restore** —
the target is not a `backup-<iso>/` directory, or its contents changed
after the backup. A damaged archive *must* refuse; take a fresh backup.

**Demo timing out** — `run <id> did not reach a terminal state within
120.0s (last state: ...)`: raise `--timeout`, or check the gateway's own
logs in gateway mode.
