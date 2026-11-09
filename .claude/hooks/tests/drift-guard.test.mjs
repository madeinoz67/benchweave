// Tests for drift-guard.mjs — the path-shaped cross-surface warning hook.
// Runs the real script end-to-end with a private session-id state dir.

import { execFileSync, spawnSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import test from 'node:test'
import assert from 'node:assert/strict'

const HOOK = join(import.meta.dirname, '..', 'drift-guard.mjs')
const SESSION = 'drift-guard-test-' + process.pid

function run(tool, relPath) {
  const res = spawnSync('node', [HOOK], {
    input: JSON.stringify({
      session_id: SESSION,
      cwd: process.cwd(),
      tool_input: { file_path: join(process.cwd(), relPath) },
    }),
    encoding: 'utf-8',
  })
  assert.equal(res.status, 0, `hook must always exit 0 (stderr: ${res.stderr})`)
  if (!res.stdout.trim()) return null
  const parsed = JSON.parse(res.stdout)
  return parsed.hookSpecificOutput?.additionalContext ?? null
}

test.after(() => {
  rmSync(join(tmpdir(), 'benchweave-drift-guard', SESSION), { recursive: true, force: true })
})

test('a trigger path warns once, then stays quiet for the session', () => {
  const first = run('Write', 'src/benchweave/cli/report.py')
  assert.ok(first?.includes('Drift 4'), `expected the CLI-docs warning, got: ${first}`)
  const second = run('Write', 'src/benchweave/cli/render.py')
  assert.equal(second, null, 'the same rule must not fire twice in one session')
})

test('touching the corresponding surface first silences the rule', () => {
  const session = 'drift-guard-test-satisfy-' + process.pid
  const res = spawnSync('node', [HOOK], {
    input: JSON.stringify({
      session_id: session,
      cwd: process.cwd(),
      tool_input: { file_path: join(process.cwd(), 'standards/interface/0.1.0/openapi.json') },
    }),
    encoding: 'utf-8',
  })
  assert.equal(res.status, 0)
  const then = spawnSync('node', [HOOK], {
    input: JSON.stringify({
      session_id: session,
      cwd: process.cwd(),
      tool_input: { file_path: join(process.cwd(), 'src/benchweave/interfaces/rest.py') },
    }),
    encoding: 'utf-8',
  })
  assert.equal(res.status, 0)
  assert.equal(then.stdout.trim(), '', 'satisfaction recorded first must quiet the trigger')
  rmSync(join(tmpdir(), 'benchweave-drift-guard', session), { recursive: true, force: true })
})

test('the fixture lattice quiets itself once a second lattice path is touched', () => {
  const session = 'drift-guard-test-lattice-' + process.pid
  const call = (rel) => {
    const r = spawnSync('node', [HOOK], {
      input: JSON.stringify({
        session_id: session,
        cwd: process.cwd(),
        tool_input: { file_path: join(process.cwd(), rel) },
      }),
      encoding: 'utf-8',
    })
    assert.equal(r.status, 0)
    return r.stdout.trim() ? JSON.parse(r.stdout).hookSpecificOutput?.additionalContext : null
  }
  const first = call('fixtures/registry/origin-main/x.json')
  assert.ok(first?.includes('Drift 5'), `expected the lattice warning, got: ${first}`)
  const second = call('catalogue.json')
  assert.equal(second, null, 'the lattice rule satisfies itself — a second lattice edit is quiet')
  rmSync(join(tmpdir(), 'benchweave-drift-guard', session), { recursive: true, force: true })
})

test('a path outside the repo produces no warning', () => {
  const out = run('Write', '/tmp/somewhere-else/entirely.py')
  assert.equal(out, null)
})

test('verb-set drift: all three trigger shapes fire Drift 23; a pre-touched surface quiets it', () => {
  const call = (session, rel) => {
    const r = spawnSync('node', [HOOK], {
      input: JSON.stringify({
        session_id: session,
        cwd: process.cwd(),
        tool_input: { file_path: join(process.cwd(), rel) },
      }),
      encoding: 'utf-8',
    })
    assert.equal(r.status, 0)
    return r.stdout.trim() ? JSON.parse(r.stdout).hookSpecificOutput?.additionalContext : null
  }
  const cleanup = (session) =>
    rmSync(join(tmpdir(), 'benchweave-drift-guard', session), { recursive: true, force: true })

  // Each trigger shape fires Drift 23 in a fresh session (a fired rule stays
  // quiet for the rest of its session, so the shapes cannot share one).
  for (const [index, trigger] of [
    'src/benchweave/host/otdp_bridge.py',
    'src/benchweave/cli/report.py',
    'src/benchweave/standards/__main__.py',
  ].entries()) {
    const session = `drift-guard-test-verbset-${process.pid}-${index}`
    const note = call(session, trigger)
    assert.ok(note?.includes('Drift 23'), `expected the verb-set warning for ${trigger}, got: ${note}`)
    cleanup(session)
  }

  // Satisfaction recorded before the trigger keeps the rule quiet (satisfy-first).
  const quietSession = 'drift-guard-test-verbset-satisfy-' + process.pid
  assert.equal(call(quietSession, 'docs/operator-guide.md'), null)
  assert.equal(
    call(quietSession, 'src/benchweave/standards/__main__.py'),
    null,
    'satisfaction recorded first must quiet the verb-set trigger'
  )
  cleanup(quietSession)

  // A NON-trigger path stays silent (refute fold F7): the rule must not
  // over-fire on source outside its three trigger shapes.
  const silentSession = 'drift-guard-test-verbset-silent-' + process.pid
  assert.equal(
    call(silentSession, 'src/benchweave/content/store.py'),
    null,
    'no rule may fire for a path outside every trigger set'
  )
  cleanup(silentSession)
})

test('a win_core-manifested file warns Drift 32; an unmanifested one does not', () => {
  // RED on main tonight: the ratchet's obligation lives in a CI-map TABLE row, so
  // nothing told a session that editing a manifested file moves its pinned count.
  // Four motions landed this way; three were discovered by a red --check at the end.
  const session = 'drift-guard-test-wincore-' + process.pid
  const runIn = (relPath) => {
    const res = spawnSync('node', [HOOK], {
      input: JSON.stringify({
        session_id: session,
        cwd: process.cwd(),
        tool_input: { file_path: join(process.cwd(), relPath) },
      }),
      encoding: 'utf-8',
    })
    assert.equal(res.status, 0, `hook must always exit 0 (stderr: ${res.stderr})`)
    if (!res.stdout.trim()) return null
    return JSON.parse(res.stdout).hookSpecificOutput?.additionalContext ?? null
  }
  const fired = runIn('tests/unit/test_dataset_services.py')
  assert.ok(fired?.includes('Drift 32'), `expected the win_core warning, got: ${fired}`)
  assert.ok(
    fired.includes('win_core_manifest.py --refresh'),
    'the warning must name the refresh command, since the refresh diff is the review surface',
  )
  assert.equal(runIn('tests/unit/test_otdp_bridge.py'), null, 'once per session')
  assert.equal(
    runIn('README.md'),
    null,
    'a file the manifest does not pin must not trigger the ratchet warning',
  )
})

// --- Cross-checkout resolution (#617, family-scoped per the #618 refute findings) ---------
//
// Every arm builds its own repository family, so the suite asserts a PROPERTY rather than
// the author's topology. The first version of this arm hardcoded `../..` as the primary
// checkout: it passed only inside a `.wt/` worktree and failed in a standalone clone, and it
// could not see the submodule or foreign-repo shapes by construction.

const scratchDirs = []
const sessionIds = []

function tempDir(prefix) {
  const dir = mkdtempSync(join(tmpdir(), prefix))
  scratchDirs.push(dir)
  return dir
}

function initRepo(dir) {
  mkdirSync(dir, { recursive: true })
  execFileSync('git', ['-C', dir, 'init', '-q', '-b', 'main'], { encoding: 'utf-8' })
  execFileSync('git', ['-C', dir, 'config', 'user.email', 't@example.com'])
  execFileSync('git', ['-C', dir, 'config', 'user.name', 'T'])
  writeFileSync(join(dir, 'seed.txt'), 'seed')
  execFileSync('git', ['-C', dir, 'add', '.'])
  execFileSync('git', ['-C', dir, 'commit', '-q', '-m', 'seed'])
}

// A family: a primary checkout, a linked worktree of it, and a checkout nested inside it.
// The nested repo reproduces the SDK submodule's shape — its own toplevel, with the family
// root above it — without needing submodule protocol config.
function family() {
  const root = tempDir('drift-family-')
  initRepo(root)
  const wt = tempDir('drift-family-wt-')
  execFileSync('git', ['-C', root, 'worktree', 'add', '-q', '--detach', wt])
  const sub = join(root, 'packages', 'sdk')
  initRepo(sub)
  return { root, wt, sub }
}

// A real edit lands in an existing directory, so the fixtures create the parents and the
// file itself. Realpath resolution needs something on disk to resolve through.
function put(dir, relPath, body = 'x') {
  const full = join(dir, relPath)
  mkdirSync(dirname(full), { recursive: true })
  writeFileSync(full, body)
  return full
}

function runAt(suffix, cwd, filePath) {
  const session = `drift-guard-fam-${suffix}-${process.pid}`
  sessionIds.push(session)
  const res = spawnSync('node', [HOOK], {
    input: JSON.stringify({ session_id: session, cwd, tool_input: { file_path: filePath } }),
    encoding: 'utf-8',
  })
  assert.equal(res.status, 0, `hook must always exit 0 (stderr: ${res.stderr})`)
  if (!res.stdout.trim()) return null
  return JSON.parse(res.stdout).hookSpecificOutput?.additionalContext ?? null
}

test.after(() => {
  for (const id of sessionIds) {
    rmSync(join(tmpdir(), 'benchweave-drift-guard', id), { recursive: true, force: true })
  }
  for (const dir of scratchDirs) rmSync(dir, { recursive: true, force: true })
})

test('an edit crossing checkouts of the family warns in both directions', () => {
  // RED before #617: rules matched a path computed from the SESSION root, so an edit
  // crossing checkouts matched nothing — it either carried a `.wt/<lane>/` prefix or
  // resolved through `..` and returned early.
  const { root, wt } = family()
  const fromWorktree = runAt('wt', wt, put(root, 'src/benchweave/cli/report.py'))
  const fromRoot = runAt('root', root, put(wt, 'src/benchweave/cli/report.py'))
  assert.ok(fromWorktree?.includes('Drift 4'), `worktree session, primary edit: ${fromWorktree}`)
  assert.ok(fromRoot?.includes('Drift 4'), `primary session, worktree edit: ${fromRoot}`)
})

test('an edit inside the nested checkout keeps the family-relative path', () => {
  // RED on the #617 tip: resolving at the nested repo's own toplevel strips the
  // `packages/sdk/` prefix that Drift 8's literals require, so the routine two-commit SDK
  // workflow — the obligation's whole point — went silent.
  const { root, sub } = family()
  const note = runAt('sub', root, put(sub, 'src/benchweave_sdk/interfaces.py'))
  assert.ok(note?.includes('Drift 8'), `expected the adapter-protocol warning, got: ${note}`)
})

test('an edit in an unrelated repository warns about nothing', () => {
  // RED on the #617 tip: the mechanism matched ANY repository's relative path, so a foreign
  // repo's identically named files drew this project's obligations.
  const { root } = family()
  const foreign = tempDir('drift-foreign-')
  initRepo(foreign)
  assert.equal(runAt('foreign', root, put(foreign, 'src/benchweave/cli/report.py')), null)
  assert.equal(runAt('foreign-pyproject', root, put(foreign, 'pyproject.toml')), null)
})

test('a symlinked spelling of a family checkout still warns', () => {
  // git reports the PHYSICAL toplevel while the caller holds a logical path; comparing the
  // two without realpath yields a `..` path and silently skips every rule. macOS `/tmp` and
  // `$TMPDIR` are exactly this shape.
  const { root } = family()
  put(root, 'src/benchweave/cli/report.py')
  const link = join(tempDir('drift-link-'), 'linked')
  symlinkSync(root, link)
  const note = runAt('symlink', link, join(link, 'src/benchweave/cli/report.py'))
  assert.ok(note?.includes('Drift 4'), `expected the CLI warning through a symlink, got: ${note}`)
})

test('a path genuinely outside any repository still stays silent', () => {
  const { root } = family()
  assert.equal(runAt('outside', root, join(tmpdir(), 'not-a-repo', 'file.py')), null)
})
