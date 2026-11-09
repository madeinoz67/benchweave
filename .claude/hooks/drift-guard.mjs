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

import { appendFileSync, existsSync, mkdirSync, readFileSync, realpathSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { tmpdir } from 'node:os'
import { basename, dirname, join, relative, resolve, sep } from 'node:path'

// Git is bounded twice: a per-call timeout, and a budget for the WHOLE edit. A per-call bound
// alone is not a bound — the walk below makes several calls, so N x timeout is what the user
// actually waits, and this is a PostToolUse hook that runs on every edit. Declared above the
// work below rather than beside its users: this file runs its top-level block before reaching
// the helper functions, so a `const` down there sits in the temporal dead zone on first use,
// and because every git helper swallows its own failures that reads as "no repository".
const GIT_TIMEOUT_MS = 1000
const GIT_BUDGET_MS = 3000
const gitDeadline = Date.now() + GIT_BUDGET_MS

const LATTICE = (p) =>
  p.startsWith('fixtures/registry/') || p.startsWith('scripts/registry/') || p === 'catalogue.json'

// Obligation 32 — the win_core ratchet's pinned-file set, keyed on the manifest itself rather
// than a guessed path pattern: `docs/internal/ui-contract.md` is pinned, an unrelated docs edit
// is not. A missing or unreadable manifest degrades to an empty set (a broken guard must not
// break the session); the check's own failure to run is `--check`'s to report, not this hook's.
//
// Read from the checkout that holds the EDITED file, cached per root. It used to be read once
// from the hook's own checkout, which is the wrong manifest whenever the two differ — and a
// lane worktree differing from the primary is what a lane is for, since a count-moving change
// refreshes the manifest in the lane. Both directions were measured: a key the lane removed
// left a genuinely manifested primary edit silent, and a key the lane added fired on a file
// the primary does not pin.
const WINCORE_CACHE = new Map()

function winCoreFiles(root) {
  const cached = WINCORE_CACHE.get(root)
  if (cached !== undefined) return cached
  let files
  try {
    const manifest = readFileSync(join(root, 'tests', 'win_core_manifest.json'), 'utf-8')
    files = new Set(Object.keys(JSON.parse(manifest).files ?? {}))
  } catch {
    files = new Set()
  }
  WINCORE_CACHE.set(root, files)
  return files
}

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
      p === 'packages/sdk/src/benchweave_sdk/__init__.py' ||
      p === 'standards/standards-manifest.json' ||
      p.endsWith('otdp-device-descriptor.schema.json'),
    satisfies: (p) =>
      p === 'tests/sdk/test_adapter_agreement.py' || p === 'standards/corpus-manifest.json',
    message: [
      '**[Drift 8] The adapter protocol surface was touched — three parties move together.**',
      '',
      'The gateway hand-mirrors the SDK protocol (`otdp_bridge` ↔ `benchweave_sdk.interfaces`)',
      'and the adapter API version is declared in the corpus identity block with its authority',
      'in the descriptor schema `$defs.adapter.api_version` const, while',
      '`standards/standards-manifest.json` selects the active versions the identity block',
      'derives from and `packages/sdk/src/benchweave_sdk/__init__.py` carries the SDK-side',
      'version constant. A change to any party needs the agreement test expectations and',
      '`identity.adapter_api` reviewed in the same change (and',
      '`tests/contract/test_baseline.py` re-pinned when identity versions move);',
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
  {
    // Obligation 23 — verb/command-set prose drifts with the mechanism that defines the set.
    id: 'verb-set-docs-drift',
    triggers: (p) =>
      p === 'src/benchweave/host/otdp_bridge.py' ||
      p.startsWith('src/benchweave/cli/') ||
      p === 'src/benchweave/standards/__main__.py',
    satisfies: (p) =>
      p === 'docs/device-developer-guide.md' ||
      p === 'docs/operator-guide.md' ||
      p === 'website/index.html' ||
      p.startsWith('tests/contract/'),
    message: [
      '**[Drift 23] A verb/command-set mechanism was edited — does every prose surface that names the set still match?**',
      '',
      'The bridge dispatch table (`otdp_bridge.py`) and both CLI trees (`src/benchweave/cli/`,',
      '`src/benchweave/standards/__main__.py`) are the authorities for sets that prose names on',
      'the website home page, the device-developer guide, operator-guide §10, and the generated',
      'standards-CLI page. Bridge-status prose states remaining scope only (re-derived from the',
      'mechanism: dispatch table, wired services, open tracker — the docstring is a derived',
      'surface this rule also sweeps) — never a verb enumeration. The site page regenerates; the',
      'tables and the verb pin (`tests/contract/test_docs_site_standards_cli.py`) sweep in the',
      'same change.',
    ],
  },
  {
    // Obligation 32 — the win_core ratchet. Count motion needs a same-commit refresh, and
    // until this rule existed the obligation lived only in the CI-map TABLE row, which the
    // numbered walk and this hook both read past. Four motions landed that way in one night;
    // three were discovered by a red --check at the end of a battery.
    id: 'win-core-manifest-motion',
    triggers: (p, context) => context.winCore.has(p),
    satisfies: (p) => p === 'tests/win_core_manifest.json',
    message: [
      '**[Drift 32] A win_core-manifested file was edited — did its collected count move?**',
      '',
      '`tests/win_core_manifest.json` pins per-file (total, core) counts; ANY motion (a new or',
      'removed test, a docs contract row) refuses `--check` until refreshed:',
      '  `uv run python scripts/ci/win_core_manifest.py --refresh`  (~6 s)',
      '',
      'Commit the refresh diff WITH the count-moving change — the diff is the review surface,',
      'which is why the manifest is not self-updating.',
    ],
  },
]

// A broken guard must never break the session: everything below is best-effort and always
// exits 0.
try {
  const input = JSON.parse(await readStdin())
  const filePath = input?.tool_input?.file_path
  if (!filePath) process.exit(0)

  // Rules match against the root of the edited file's own checkout within THIS repo family,
  // not the session's. They differ whenever an edit crosses checkouts, which is the
  // documented way work happens here: a lane worktree edited from a session anchored at the
  // primary (the computed path carried a `.wt/<lane>/` prefix, so no rule's prefix matched),
  // or the primary edited from a worktree-anchored session (the path resolved through `..`
  // and returned early). Either way every rule went silent, and a silent guard reads exactly
  // like a clean session.
  //
  // The root must be scoped to the family, not merely to "some repository". Two shapes break
  // the naive version, and both were measured: resolving inside the SDK submodule strips the
  // `packages/sdk/` prefix that Drift 8's literals need (so the routine two-commit SDK
  // workflow went silent), while resolving in an unrelated repository makes its identically
  // named paths fire BenchWeave obligations that are none of its business.
  const sessionRoot = process.env.CLAUDE_PROJECT_DIR || input.cwd || process.cwd()
  const root = familyRoot(sessionRoot, filePath) ?? sessionRoot
  const rel = relative(root, realpathOr(filePath)).split(sep).join('/')
  // Edits outside the repo are not our business.
  if (!rel || rel.startsWith('..')) process.exit(0)

  const stateDir = join(tmpdir(), 'benchweave-drift-guard', String(input.session_id || 'nosession'))
  mkdirSync(stateDir, { recursive: true })

  // Rules are path-shaped except obligation 32, which needs the edited file's checkout to know
  // which manifest applies. One context object, computed once, passed to every trigger.
  const context = { root, winCore: winCoreFiles(root) }

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
    if (!rule.triggers(rel, context)) continue
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

// Best-effort git, warn-never-block: a missing git, an unknown directory, a timeout or any
// non-zero exit all mean "no answer" and the caller degrades.
function gitOut(dir, args) {
  const remaining = gitDeadline - Date.now()
  if (remaining <= 0) return null
  try {
    const res = spawnSync('git', ['-C', dir, ...args], {
      encoding: 'utf-8',
      timeout: Math.min(GIT_TIMEOUT_MS, remaining),
    })
    if (res.status !== 0) return null
    return res.stdout.trim() || null
  } catch {
    return null
  }
}

// Logical and physical spellings of the same path must compare equal, or a session anchored
// through a symlink (macOS `/tmp`, `$TMPDIR`) resolves one side against the other and silently
// computes a `..` path. Canonicalises the nearest EXISTING ancestor and appends the rest
// lexically: a plain realpath fails on a path whose leaf does not exist yet, and falling back
// to the logical spelling would reintroduce the very mismatch this resolves. The same walk
// also resolves a symlinked FILE, not just a symlinked directory.
function realpathOr(p) {
  const absolute = resolve(p)
  const tail = []
  let head = absolute
  for (let depth = 0; depth < 64; depth += 1) {
    try {
      return join(realpathSync(head), ...tail.slice().reverse())
    } catch {
      const parent = dirname(head)
      if (parent === head) return absolute
      tail.push(basename(head))
      head = parent
    }
  }
  return absolute
}

// The OUTERMOST checkout of the session's superproject chain. A session anchored inside the
// nested checkout is ordinary here — AGENTS.md's two-commit workflow starts with "commit
// inside the submodule first", so a lane opened with `cd packages/sdk` is the documented
// path. Anchoring the family to that checkout would scope every rule to the submodule and
// silence Drift 8 in exactly the direction this fix exists to keep alive.
function outermostCheckout(dir) {
  let current = dir
  for (let depth = 0; depth < 8; depth += 1) {
    const top = gitOut(current, ['rev-parse', '--show-toplevel'])
    if (top === null) break
    current = realpathOr(top)
    const superproject = gitOut(current, ['rev-parse', '--show-superproject-working-tree'])
    if (superproject === null) break
    current = realpathOr(superproject)
  }
  return current
}

// Worktrees of one repository share a common git dir; unrelated clones and nested repos do
// not. That is the family identity, and it is what tells a sibling worktree (same family)
// from a foreign repository that happens to contain identically named files.
function gitCommonDir(dir) {
  const p = gitOut(dir, ['rev-parse', '--git-common-dir'])
  return p === null ? null : realpathOr(resolve(dir, p))
}

// The edited file's checkout root, but only when that checkout belongs to the session's repo
// family. Walks up from the file so a checkout nested inside the family (the SDK submodule)
// resolves to its superproject — which restores the `packages/sdk/…` prefix the rules match
// on — while a foreign repository finds no family ancestor and yields null, leaving the
// caller's session root in place (and the file out of scope).
function familyRoot(sessionRoot, filePath) {
  const family = gitCommonDir(outermostCheckout(sessionRoot))
  if (family === null) return null
  let dir = realpathOr(dirname(filePath))
  for (let depth = 0; depth < 8; depth += 1) {
    const top = gitOut(dir, ['rev-parse', '--show-toplevel'])
    // git searches upward itself, so null here means no ancestor is a repository at all —
    // there is nothing further to walk and walking anyway costs one spawn per ancestor.
    if (top === null) return null
    const topReal = realpathOr(top)
    if (gitCommonDir(topReal) === family) return topReal
    const parent = dirname(topReal)
    if (parent === topReal) return null
    dir = parent
  }
  return null
}

async function readStdin() {
  const chunks = []
  for await (const chunk of process.stdin) chunks.push(chunk)
  return Buffer.concat(chunks).toString('utf-8') || '{}'
}
