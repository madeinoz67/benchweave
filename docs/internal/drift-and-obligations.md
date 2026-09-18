# Cross-surface obligations, drift risks, and the CI map

BenchWeave has many surfaces that must stay in sync but mostly *aren't* checked
automatically. This is where "you changed X but didn't update Y" bugs live. A reviewer must
walk this list for any PR that touches a synced surface — the review rubric's G5 gate is
the obligation; this file is the detail behind it.

Obligations marked 🪝 are additionally warned about by `.claude/hooks/drift-guard.mjs`, a
PostToolUse hook that fires when Claude Code edits the triggering path. It is a reminder,
not a gate: it warns once per session, stays quiet if you have already touched the
corresponding surface, and never blocks. The unmarked obligations need judgment or a build,
and remain the reviewer's job.

## "If a PR touches X, it must also do Y"

1. **An MCP tool change** (tool set, parameters, output schema) 🪝 → the vendored corpus is
   the authority: `standards/interface/0.1.0/mcp-tools.json` plus any schema it references.
   The gateway pins tool schemas verbatim to the corpus (invariants CON-3), so a gateway
   change and a corpus change cannot land separately — normative standards changes start
   in this repository and sync out to the SDK. If the operation surface moved,
   `operation-catalog.json` moves too.

2. **An API-visible change** 🪝 → `standards/interface/0.1.0/openapi.json` (and
   `interface.schema.json` when the envelope changes). There is no spec linter in CI —
   field-level drift is the reviewer's eye, not a gate.

3. **Plugin/device-visible behavior** (packaging, loading, policy, lifecycle) →
   `docs/device-developer-guide.md`.

4. **Operator-visible behavior** 🪝 (service, config, CI) → `docs/operator-guide.md` and
   `README.md`. **CLI behavior** (`src/benchweave/cli/`) → the CLI reference in the
   operator docs.

5. **The fixture lattice** 🪝 → all four in lockstep: `fixtures/registry/` ↔
   `scripts/registry/build_fixtures.py` ↔ `catalogue.json` ↔ the digest-pinning tests.
   Fixtures without the builder, or a rebuilt lattice without regenerated digests, is
   silent drift. **CI materialises the fixture signing keys from repo secrets**
   (`main.pem`, `originb.pem`) — any test whose outcome depends on those secrets must
   match the workflow's materialisation, and a workflow change gets a cold full-suite run,
   not a warm local one.

6. **Vendored contract bytes** 🪝 → `standards/corpus-manifest.json` byte-pins move with any
   vendored change, and `make check-sdk-standards` (CI `gates` job) must stay green: it
   refuses drift between the main-repo standards, the SDK lock and the vendored tree.
   Pins move via `uv run python -m benchweave.standards repin` (the loop is
   edit → repin → export); hand-splicing digests is not a path.

7. **The `packages/sdk` pointer** → the submodule commit must **exist and be pushed** to
   the SDK remote before the pointer lands here — CI checks out submodules by SHA, so an
   unpushed commit is invisible there and breaks `gates`. **Renderer freshness**: the `ui`
   job rebuilds the preview renderer (`npm --prefix ui run build:preview`) and fails on any
   diff in the SDK's committed `preview_assets` — a UI change that leaves the committed
   renderer stale ships silently in the wheel.

8. **The adapter protocol surface** 🪝 (the SDK protocol
   `packages/sdk/src/benchweave_sdk/interfaces.py` ↔ the gateway mirror
   `src/benchweave/host/otdp_bridge.py` ↔ the descriptor schema's
   `$defs.adapter.api_version` const; `standards/standards-manifest.json` selects the
   active versions the identity block derives from, and
   `packages/sdk/src/benchweave_sdk/__init__.py` carries the SDK-side
   `ADAPTER_API_VERSION` constant) → the full bump touch-set moves in the same change:
   the agreement test (`tests/sdk/test_adapter_agreement.py`), the corpus identity
   declaration (`standards/corpus-manifest.json` `identity.*`), the manifest
   versions when a standard bumps, the descriptor schema const, both SDK files, and
   the orphan identity literal in `tests/contract/test_baseline.py`
   (`test_manifest_identity_pins_admitted_versions`). `make check-sdk-standards`
   carries the identity-vs-schema/manifest derivation checks; the agreement test
   carries the protocol shape (invariants CON-8/REG-4).

9. **`deploy/systemd/` templates** 🪝 → the `systemd` CI job renders the template and
   `systemd-analyze verify`s it against rehearsed preconditions (dedicated user, one
   writable data dir, env file). The `{{`-absence assertion in `tests/cli/test_serve.py`
   catches placeholder misses that `systemd-analyze verify` tolerates — the CI job's own
   comment says do not simplify that test away; the two catch complementary failure modes.

10. **A dependency change** 🪝 → `pyproject.toml` and `uv.lock` together, CI in the same
    change when the dependency changes what CI must install or materialise.

11. **Key/secret handling** → the security-posture docs must track the real key paths and
    secret names (the reviewer's G0 secret scan catches leaks; this catches drift between
    the posture text and the posture).

12. **Reserved for later stages** — the UI/console surface gets its doc home named here
    when that stage lands; hardware-evidence docs get theirs at WP10+ commissioning. Add
    the row at the moment the surface arrives, not after the first drift bug.

## CI map

| Job | What it catches |
|---|---|
| `gates` | submodules recursive; fixture keys materialised from secrets; `ruff check .`; config-driven `mypy` (bare — explicit path args drop `packages/sdk/src` from the build); `pytest -q` (including the adapter agreement test, which pins the SDK↔gateway protocol mirror and the version triplet — see obligation 8); `make check-sdk-standards` (main standards ↔ SDK lock ↔ vendored tree, plus the identity `adapter_api` derivation check) |
| `ui` | `npm ci` + typecheck + lint + unit tests + Storybook build; the renderer freshness gate (see obligation 7); `npm audit --audit-level=high` |
| `systemd` | unit-template render + `systemd-analyze verify` with rehearsed deployment preconditions (see obligation 9) |

What CI does **not** catch: every numbered obligation above that names a doc, a guide, or
a cross-repo push — those are the reviewer's, which is why G5 exists in the rubric.

## Testing conventions worth upholding

- **RED-sanity verification**: a bug-fix test must be shown to fail without the fix. `no
  tests ran` is a FAILED RED check — pytest exits 5 when it collects nothing; look for the
  collected count. Read counts from `--junitxml` attributes or exit codes, never from an
  output-filter summary (the rtk filter can print "No tests collected" over a green run).
- **Claim discipline**: a set named in prose is regenerated by a test from a mechanism; a
  guard states what it does not catch; *cannot/never* means structurally unrepresentable
  and says why inline, otherwise *is refused unless* plus the residual.
- **Parity tests are not contract tests**: transport parity (REST vs MCP) proves only
  symmetry — pin behavior against the frozen
  `standards/interface/0.1.0/interface-contract.md` (invariants CON-5). The WP07 lesson:
  a wrong failure code was test-pinned in three suites before the whole-branch review
  caught it.
- **`tests/faults/`** runs for any change touching `state/`, `control/`, or anything
  concurrency-shaped — it is the fault-injection arm of the suite.
- **One RED→GREEN slice per commit** — the discipline that keeps every fix provable.
