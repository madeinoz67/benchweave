#!/usr/bin/env node
// drift-guard.mjs — mechanical enforcement for the cross-surface obligations in
// docs/internal/drift-and-obligations.md.
//
// That document lists twelve "if a PR touches X, it must also do Y" obligations and is
// honest that most of them have no automated check. This hook covers the ones that are
// purely path-shaped, so they stop depending on a reviewer remembering. The rest need
// judgment (or a build) and stay manual — see the doc.
//
// Every rule WARNS, never blocks. Each fires at most once per session, and stays silent if
// the session already touched the surface it would ask about. Add a rule by appending to
// RULES — nothing else here is rule-specific.

import { appendFileSync, existsSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, relative, sep } from 'node:path'

const LATTICE = (p) =>
  p.startsWith('fixtures/registry/') || p.startsWith('scripts/registry/') || p === 'catalogue.json'

const RULES = [
  {
    // Obligation 1 — the vendored corpus is the authority for MCP tool schemas.
    id: 'mcp-corpus-drift',
    triggers: (p) =>
      p === 'src/benchweave/interfaces/mcp.py' || p === 'src/benchweave/interfaces/operations.py',
    satisfies: (p) => p.startsWith('standards/interface/'),
    message: [
      '**[Drift 1] MCP tool code was edited — does the vendored corpus still match?**',
      '',
      'Tool `parameters`/`output_schema` are pinned verbatim to the vendored corpus; signature',
      'inference must never define the wire schema. If a tool changed shape:',
      '',
      '1. Update `standards/interface/0.1.0/mcp-tools.json` (and `operation-catalog.json` if',
      '   operations moved) — normative changes start in this repo and sync to the SDK',
      '2. `make check-sdk-standards` must stay green',
    ],
  },
  {
    // Obligation 2 — REST vs the vendored OpenAPI spec. No spec linter runs in CI.
    id: 'api-spec-drift',
    triggers: (p) => p === 'src/benchweave/interfaces/rest.py',
    satisfies: (p) => p.startsWith('standards/interface/'),
    message: [
      '**[Drift 2] `src/benchweave/interfaces/rest.py` was edited — does `openapi.json` still match?**',
      '',
      'There is no spec linter in CI, so field-level drift is on you. If a route or response',
      'shape changed, update `standards/interface/0.1.0/openapi.json` (and',
      '`interface.schema.json` if the envelope moved).',
    ],
  },
  {
    // Obligation 4 — CLI behavior vs the CLI reference in the operator docs.
    id: 'cli-docs-drift',
    triggers: (p) => p.startsWith('src/benchweave/cli/'),
    satisfies: (p) => p === 'docs/operator-guide.md' || p === 'README.md',
    message: [
      '**[Drift 4] CLI code was edited — does the CLI reference still match?**',
      '',
      'A command, flag, or output shape that changed needs its entry in the CLI reference in',
      '`docs/operator-guide.md` (and `README.md` for the headline flows). Absence of the',
      'update is the finding, even when the diff touches no `docs/`.',
    ],
  },
  {
    // Obligation 5 — the fixture digest lattice moves in four-way lockstep. Deliberately
    // NOT self-satisfying: satisfaction is recorded before triggers are consulted, so a
    // rule whose satisfies() overlaps its triggers() would never fire at all. The
    // once-per-session `fired` marker provides the quieting — first lattice touch warns,
    // the rest of the session stays silent.
    id: 'fixture-lattice-drift',
    triggers: LATTICE,
    satisfies: () => false,
    message: [
      '**[Drift 5] The fixture lattice was touched — all four parts must move together.**',
      '',
      '`fixtures/registry/` <-> `scripts/registry/build_fixtures.py` <-> `catalogue.json` <->',
      'the digest-pinning tests. Fixtures without the builder, or a rebuilt lattice without',
      'regenerated digests, is silent drift. CI materialises the signing keys from repo',
      'secrets (`main.pem`, `originb.pem`) — any secret-dependent test must match that',
      'materialisation.',
    ],
  },
  {
    // Obligation 6 — vendored contract bytes vs the manifest byte-pins.
    id: 'vendored-standards-drift',
    triggers: (p) =>
      p.startsWith('standards/') &&
      p !== 'standards/corpus-manifest.json' &&
      p !== 'standards/standards-manifest.json',
    satisfies: (p) => p === 'standards/corpus-manifest.json',
    message: [
      '**[Drift 6] Vendored contract bytes were touched — do the manifest pins still match?**',
      '',
      '`standards/corpus-manifest.json` byte-pins move with any vendored change, and',
      '`make check-sdk-standards` refuses drift between the main-repo standards, the SDK lock',
      'and the vendored tree. Run `uv run python -m benchweave.standards repin` to recompute',
      'the pins (edit → repin → export), then `make sync-sdk-standards` to re-sync — never',
      'hand-splice digests.',
    ],
  },
  {
    // Obligation 8 — the adapter protocol mirror moves SDK↔gateway↔corpus together.
    id: 'adapter-protocol-drift',
    triggers: (p) =>
      p === 'src/benchweave/host/otdp_bridge.py' ||
      p === 'packages/sdk/src/benchweave_sdk/interfaces.py' ||
      p.endsWith('otdp-device-descriptor.schema.json'),
    satisfies: (p) =>
      p === 'tests/sdk/test_adapter_agreement.py' || p === 'standards/corpus-manifest.json',
    message: [
      '**[Drift 8] The adapter protocol surface was touched — three parties move together.**',
      '',
      'The gateway hand-mirrors the SDK protocol (`otdp_bridge` ↔ `benchweave_sdk.interfaces`)',
      'and the adapter API version is declared in the corpus identity block with its authority',
      'in the descriptor schema `$defs.adapter.api_version` const. A change to any party needs',
      'the agreement test expectations and `identity.adapter_api` reviewed in the same change;',
      '`make check-sdk-standards` and `uv run pytest tests/sdk` must stay green.',
    ],
  },
  {
    // Obligation 9 — systemd templates have a complementary test guard.
    id: 'systemd-template-drift',
    triggers: (p) => p.startsWith('deploy/systemd/'),
    satisfies: (p) => p.startsWith('tests/cli/'),
    message: [
      '**[Drift 9] A systemd template was edited — the complementary test guard matters.**',
      '',
      'The CI `systemd` job renders and `systemd-analyze verify`s the template, but the',
      '`{{`-absence assertion in `tests/cli/test_serve.py` catches placeholder misses the',
      'verifier tolerates. Do not simplify that test away — the two catch complementary',
      'failure modes.',
    ],
  },
  {
    // Obligation 10 — a dependency change means the lock moves in the same commit.
    id: 'dependency-lock-drift',
    triggers: (p) => p === 'pyproject.toml',
    satisfies: (p) => p === 'uv.lock',
    message: [
      '**[Drift 10] `pyproject.toml` was edited — does `uv.lock` move in the same commit?**',
      '',
      'A dependency add/remove/re-pin travels with its lock, and with CI when it changes',
      'what CI must install or materialise. Purely local config (tool settings, paths) can',
      'ignore this.',
    ],
  },
]

// A broken guard must never break the session: everything below is best-effort and always
// exits 0.
try {
  const input = JSON.parse(await readStdin())
  const filePath = input?.tool_input?.file_path
  if (!filePath) process.exit(0)

  const root = process.env.CLAUDE_PROJECT_DIR || input.cwd || process.cwd()
  const rel = relative(root, filePath).split(sep).join('/')
  // Edits outside the repo are not our business.
  if (!rel || rel.startsWith('..')) process.exit(0)

  const stateDir = join(tmpdir(), 'benchweave-drift-guard', String(input.session_id || 'nosession'))
  mkdirSync(stateDir, { recursive: true })

  const notes = []
  for (const rule of RULES) {
    const satisfied = join(stateDir, `${rule.id}.satisfied`)
    const fired = join(stateDir, `${rule.id}.fired`)

    // Record satisfaction first, so an edit that both satisfies and triggers in the same
    // session resolves in favor of staying quiet.
    if (rule.satisfies(rel)) {
      appendFileSync(satisfied, `${rel}\n`)
      continue
    }
    if (!rule.triggers(rel)) continue
    if (existsSync(satisfied) || existsSync(fired)) continue

    appendFileSync(fired, `${rel}\n`)
    notes.push(rule.message.join('\n'))
  }

  if (notes.length) {
    process.stdout.write(
      JSON.stringify({
        hookSpecificOutput: {
          hookEventName: 'PostToolUse',
          additionalContext: notes.join('\n\n---\n\n'),
        },
      })
    )
  }
} catch {
  // Swallow. A guard that fails closed would be worse than one that misses a warning.
}
process.exit(0)

async function readStdin() {
  const chunks = []
  for await (const chunk of process.stdin) chunks.push(chunk)
  return Buffer.concat(chunks).toString('utf-8') || '{}'
}
