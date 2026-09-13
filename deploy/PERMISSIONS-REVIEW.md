# BenchWeave deploy surface — permissions review

> WP08 Task 14. This document is the deliverable the deploy template
> implements: every directive in `deploy/systemd/benchweave.service.template`
> with its threat rationale, the secret posture `serve` enforces, and the
> separation invariants the surface must keep. CI renders the template and
> runs `systemd-analyze verify` over the rendered unit (job `systemd`).

## 1. Scope and threat model

BenchWeave is a **local, single-operator** test-bench gateway: it binds
loopback, serves REST + MCP to the operator's tooling, executes check runs
through instrument/DUT plugins, and admits signed fixture packages from the
committed fixture registry. The systemd surface defends against:

| Attacker class | What they get without this surface |
| --- | --- |
| A compromised plugin / check process running as the service | Root escalation paths (setuid binaries), kernel attack surface, arbitrary file writes |
| Another local user account | Reading the gateway secret from a world-readable env file, racing the data dir, injecting units |
| A tampered fixture / supply-chain artifact | Writes anywhere in the filesystem, network exfiltration channels beyond loopback service sockets |
| Operator error (the realistic one) | Booting a "production" gateway on the repo's public test secret — anyone who reads the public source can then mint admin tokens |

Explicit non-goals: multi-tenant isolation (single operator by design),
remote network exposure (loopback bind is the default and the posture), and
defending the host root from a full sandbox escape (the unit hardens the
blast radius; it is not a VM boundary).

## 2. Deployment layout — three distinct roots

| Root | Path (rendered) | Mode / owner | Writable? |
| --- | --- | --- | --- |
| Data dir | `{{DATA_DIR}}` (e.g. `/var/lib/benchweave`) | `0750 benchweave:benchweave` | **The only writable root** — `state.sqlite` (the whole store, including the DB-backed content plane — there is no separate content directory) with its WAL/hold sidecars, and the registry session's work tree (`registry/`) |
| Credential env file | `{{ENV_FILE}}` (e.g. `/etc/benchweave/benchweave.env`) | `0600 root:benchweave` | Read by the unit at start; edited by the operator |
| Code + fixtures checkout | e.g. `/opt/benchweave` (repo checkout or wheel install) | read-only to `benchweave` | Never — code, the execution lattice, and the fixture registry are inputs, not state |

**Fixture/credential separation (the gate invariant):** the EnvironmentFile
root and the fixtures root are DISTINCT trees. The env file
(`benchweave.env.example`) carries **no fixtures path coupling** — no
`BENCHWEAVE_FIXTURES` key at all — so credentials can never silently point
at (or be written under) the fixture tree, and a fixture-tree compromise
yields no credential material. Fixtures resolve from the deployment
checkout by default (`app_entry`'s repo-rooted default), overridable by the
operator's own env choice if a deployment ever needs it.

The registry session wired into `serve` honours the same invariant from the
other side: its work root (admission cache, package lock, activation
records) is derived from the DB's parent — i.e. it lives **under the data
dir**, not beside the fixtures, so `ReadWritePaths={{DATA_DIR}}` remains
the single writable root and the read-only fixture registry stays
read-only.

## 3. The nine — each directive and its threat rationale

The unit's mandated hardening set (controller ruling 1), in template order:

1. **`User=benchweave` / `Group=benchweave`** (with `Type=simple`, below) —
   a dedicated system user with no home, no shell, no other files on the
   host. Anything the gateway or a plugin it runs is tricked into doing
   executes as this unprivileged identity, not as the operator's login
   account and never as root. Creating it:
   `sudo useradd --system --no-create-home --shell /usr/sbin/nologin benchweave`.
2. **`NoNewPrivileges=true`** — kills the setuid/setgid escape hatch:
   even if a compromised process execs `/usr/bin/su`, `sudo`, `mount`, or
   any other setuid binary, the kernel refuses to grant the privilege
   bump. This is the cheapest high-value directive in the file.
3. **`ProtectSystem=strict`** — the entire filesystem hierarchy is mounted
   read-only for the service (`/usr`, `/etc`, `/boot`, …). A compromised
   process cannot tamper with binaries, unit files, or the fixture
   checkout, which also makes the signed-registry trust meaningful: the
   things admission verifies are the things served.
4. **`ReadWritePaths={{DATA_DIR}}`** — the single, explicit carve-out from
   (3): the data dir only. Every mutable artifact the gateway legitimately
   produces — the store (which carries the DB-backed content plane inside
   it), its WAL and hold marker, and the registry work tree — is designed
   to live under it (see §2). Anything attempting to write elsewhere fails
   at the VFS layer.
5. **`PrivateTmp=true`** — the service gets its own `/tmp` and `/var/tmp`
   namespaces. No symlink races or eavesdropping between the gateway and
   any other local user sharing the host's real `/tmp`; no
   temp-file-based cross-service interference.
6. **`CapabilityBoundingSet=`** (empty) — the process may hold **no**
   Linux capabilities at all, including ambient ones an unprivileged user
   would normally inherit. Even a kernel bug in a capability check has
   nothing to work with; combined with (2) there is no path to regaining
   privilege.
7. **`MemoryDenyWriteExecute=true`** — memory pages may be writable or
   executable, never both. Injected shellcode in a memory-corruption
   attack (a plugin loading hostile firmware blobs is the plausible vector)
   cannot execute. CPython 3.13 does not W+X in normal operation (no
   default JIT); this is revisited if a future CPython enables one.
8. **`EnvironmentFile={{ENV_FILE}}`** — all runtime configuration,
   including the gateway secret, enters through exactly one 0600 file the
   operator owns (see §5). No secrets in the unit file itself (units are
   commonly world-readable in `/etc`), none on the command line (visible
   in `ps`), none baked into the image.
9. **`ExecStart=/usr/bin/python3 -m benchweave serve`** — the foreground
   serve command. `serve` composes `app_entry.build()` (env → store →
   gateway, with the production secret-posture refusal inside) and runs
   uvicorn in the **foreground** — `uvicorn.run` blocks until the service
   stops. The unit is `Type=simple` precisely because serve never
   daemonizes: systemd owns the lifecycle (start ordering, restart, stop
   signal), and the process it forks IS the gateway.

`Type=simple` + `Restart=on-failure` / `RestartSec=2` complete the
lifecycle: systemd considers the unit started immediately at fork (correct
for a foreground process), supervises it, and restarts a crashed gateway
after a beat — the same recovery posture the event-recovery suites pin at
the application layer.

## 4. Additional sandboxing (beyond the nine)

Same reasoning, second tier — each closes a kernel-attack or
cross-service channel that the nine leave open:

- `ProtectHome=true` — `/root` and `/home` are inaccessible; the service
  has no business in operator homes.
- `PrivateDevices=true` — no real device nodes beyond pseudo-devices; a
  plugin cannot reach the host's disks or USB devices. (BenchWeave talks
  to instruments over its plugins' own configured transports, not by
  grabbing `/dev`.)
- `ProtectKernelTunables` / `ProtectKernelModules` / `ProtectKernelLogs` /
  `ProtectControlGroups` / `ProtectClock` / `ProtectHostname` — the six
  kernel-interface fences: no `/proc/sys` writes, no module loads, no
  kernel-log access, no cgroup tampering, no clock changes (which would
  also subvert lease expiry), no hostname changes.
- `RestrictNamespaces=true` — may not create user/mount/net/pid
  namespaces; no namespace-based escape or cloaking.
- `RestrictRealtime=true` / `RestrictSUIDSGID=true` — no realtime
  scheduling (a DoS channel) and no creating setuid files (a persistence
  channel) — the latter is belt-and-braces under `ProtectSystem=strict`.
- `LockPersonality=true` — no switching execution domain (blocks
  exotic-ABI kernel-interface attacks).
- `SystemCallArchitectures=native` — no 32-bit-compat syscalls (a classic
  kernel-bypass surface).
- `RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6` — the service may
  only open local and IP sockets; exotic families (netlink, packet, raw)
  that would let a compromised process reconfigure the host network are
  refused at syscall level.

Deliberately **omitted**, with reasons: `SystemCallFilter=` (a wrong
allowlist bricks a runtime that legitimately makes broad syscalls —
verifiable syntax is not verifiable behavior; revisit only with a tested
profile), `IPAddressAllow/Deny=` (loopback bind + the AF fence already
constrain the surface; cgroup-bpf filtering adds runtime risk for no
marginal gain at this posture), and socket activation (the gateway's
identity/bench surface has no per-socket credentialing need).

## 5. Secret posture

- **Refusal, not warning.** With `BENCHWEAVE_ENV=production`,
  `app_entry.build()` raises before opening the store if
  `BENCHWEAVE_SECRET` is unset, empty/whitespace (a trailing-`=` typo in
  the env file), or equals a publicly known value — the repo's default
  test secret (`wp07-task-eleven-secret`) or the deploy example's own
  placeholder (`__GENERATE_AND_STORE_A_REAL_RANDOM_SECRET__`); both are
  readable by anyone with the public source, so on either anyone can mint
  admin tokens. `benchweave serve` surfaces it as a clean CLI error and
  exits non-zero; systemd's `Restart=on-failure` will retry it, which is
  correct: a misconfigured deploy should stay loudly down, not boot
  quietly weak. Default posture (no `BENCHWEAVE_ENV`) is unchanged — the
  integration suites boot on the test secret.
- **One 0600 file.** The secret reaches the gateway only via
  `{{ENV_FILE}}`: copy the example, `chown root:benchweave`, `chmod 0600`,
  and fill it with an operator-generated value (`openssl rand -hex 32`).
  The example carries placeholders only; the filled copy is never
  committed, and `benchweave backup` deliberately excludes the credential
  file from snapshots (the at-rest posture since WP08 Task 10).
- **Enforced at the repo, not by convention.** `tests/cli/test_serve.py`
  greps all of `deploy/` for secret-shaped keys with non-placeholder
  values and for high-entropy blobs; CI's render+verify job and the test
  suite both fail if a real secret ever lands in the tree.

## 6. CI verification (`.github/workflows/ci.yml`, job `systemd`)

On every push/PR, an `ubuntu-latest` job: (1) fails loudly
(`::error::` + non-zero exit) if `command -v systemd-analyze` is absent —
a missing verifier is a skip that must never pass silently; (2) rehearses
the deployment preconditions (the `benchweave` system user, the data dir,
the env file path); (3) renders the template's `{{DATA_DIR}}`/`{{ENV_FILE}}`
placeholders with `sed`, exactly as the header documents; and (4) runs
`systemd-analyze verify` over the rendered unit so a directive typo,
an unrenderable placeholder, or a broken `ExecStart` shape fails the build
before it reaches an operator.

Note on `ExecStart`: it names `/usr/bin/python3 -m benchweave serve`, i.e.
the deployment must make `benchweave` importable by the system
interpreter (or an operator edits the interpreter path to their venv's
python — the argument list does not change). The verify job checks the
executable exists and the unit parses; import availability is a
deployment-install step, not a unit property.

## 7. Residual risks (accepted, with reasons)

- The template hardens a systemd/Linux deployment; other supervisors need
  their own equivalent surface (the review is the spec).
- A full sandbox escape as `benchweave` still reads the data dir and the
  in-process secret — that blast radius is why the secret file is 0600 and
  rotated by re-issuing tokens after any suspected compromise.
- `MemoryDenyWriteExecute` and a future CPython JIT (off by default in
  3.13) are in tension; the directive is revisited if the runtime changes.
- The verifier proves syntax and executable existence, not runtime
  behavior under the sandbox; the first install on a real host should
  smoke-boot the gateway and run `benchweave status` against it.
