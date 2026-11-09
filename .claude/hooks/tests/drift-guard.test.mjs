// Tests for drift-guard.mjs — the path-shaped cross-surface warning hook.
// Runs the real script end-to-end with a private session-id state dir.

import { spawnSync } from 'node:child_process'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
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

test('a crossed-checkout edit still warns, both directions', () => {
  // RED before the fix: rules matched a path computed from the SESSION root, so an edit
  // crossing checkouts of this repo family matched nothing — the path either carried a
  // `.wt/<lane>/` prefix (no rule's prefix matches) or resolved through '..' and returned
  // early. Every rule went silent exactly where the documented working method puts edits,
  // and a silent guard reads like a clean session.
  const session = 'drift-guard-test-crosscheckout-' + process.pid
  // One session per direction: the hook fires each rule at most once per session, so
  // sharing an id would make the second direction silent for the wrong reason.
  const runIn = (suffix, cwd, filePath) =>
    spawnSync('node', [HOOK], {
      input: JSON.stringify({
        session_id: `${session}-${suffix}`,
        cwd,
        tool_input: { file_path: filePath },
      }),
      encoding: 'utf-8',
    })
  const note = (res) =>
    res.stdout.trim()
      ? (JSON.parse(res.stdout).hookSpecificOutput?.additionalContext ?? null)
      : null
  // Direction 1: session anchored in this worktree, edit landing in the primary checkout.
  const fromWorktree = runIn(
    'wt',
    process.cwd(),
    join(process.cwd(), '..', '..', 'src/benchweave/cli/report.py'),
  )
  // Direction 2: session anchored at the repo root, edit landing in this worktree.
  const fromRoot = runIn(
    'root',
    join(process.cwd(), '..', '..'),
    join(process.cwd(), 'src/benchweave/cli/report.py'),
  )
  assert.equal(fromWorktree.status, 0)
  assert.equal(fromRoot.status, 0)
  assert.ok(
    note(fromWorktree)?.includes('Drift 4'),
    `expected the warning when the session is in a worktree and the edit is in the primary, got: ${note(fromWorktree)}`,
  )
  assert.ok(
    note(fromRoot)?.includes('Drift 4'),
    `expected the warning when the session is at the root and the edit is in a worktree, got: ${note(fromRoot)}`,
  )
})

test('a path genuinely outside any repository still stays silent', () => {
  const res = spawnSync('node', [HOOK], {
    input: JSON.stringify({
      session_id: 'drift-guard-test-outside-' + process.pid,
      cwd: process.cwd(),
      tool_input: { file_path: join(tmpdir(), 'not-a-repo', 'file.py') },
    }),
    encoding: 'utf-8',
  })
  assert.equal(res.status, 0)
  assert.equal(res.stdout.trim(), '', 'an out-of-repo edit must produce no warning')
})
