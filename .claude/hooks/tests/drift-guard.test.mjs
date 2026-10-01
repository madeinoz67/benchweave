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
