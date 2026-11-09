// Tests for session-preflight.mjs — the SessionStart facts hook.
// Runs the real script against throwaway git repos, so no network and no dependence on
// this checkout's own state.

import { execFileSync, spawnSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import assert from 'node:assert/strict'

const HOOK = join(import.meta.dirname, '..', 'session-preflight.mjs')

const scratch = []
test.after(() => {
  for (const dir of scratch) rmSync(dir, { recursive: true, force: true })
})

function tempDir(prefix) {
  const dir = mkdtempSync(join(tmpdir(), prefix))
  scratch.push(dir)
  return dir
}

function git(cwd, ...args) {
  return execFileSync('git', ['-C', cwd, ...args], { encoding: 'utf-8' }).trim()
}

function repo() {
  const dir = tempDir('session-preflight-')
  git(dir, 'init', '-q', '-b', 'main')
  git(dir, 'config', 'user.email', 'test@example.com')
  git(dir, 'config', 'user.name', 'Test')
  return dir
}

function commit(dir, name) {
  writeFileSync(join(dir, `${name}.txt`), name)
  git(dir, 'add', '.')
  git(dir, 'commit', '-q', '-m', name)
  return git(dir, 'rev-parse', 'HEAD')
}

function run(cwd) {
  const res = spawnSync('node', [HOOK], {
    input: JSON.stringify({ session_id: 'preflight', cwd, hook_event_name: 'SessionStart' }),
    encoding: 'utf-8',
    timeout: 20000,
  })
  assert.equal(res.status, 0, `hook must always exit 0 (stderr: ${res.stderr})`)
  if (!res.stdout.trim()) return null
  return JSON.parse(res.stdout).hookSpecificOutput?.additionalContext ?? null
}

// A checkout whose origin is a real local bare repo, so `git fetch origin` SUCCEEDS —
// this is the arm that proves the normal path, not just the degrade path.
function repoWithRemote() {
  const dir = repo()
  const bare = tempDir('session-preflight-origin-')
  git(bare, 'init', '-q', '--bare')
  git(dir, 'remote', 'add', 'origin', bare)
  return { dir, bare }
}

test('a checkout behind origin/main warns with the count and both SHAs', () => {
  const { dir } = repoWithRemote()
  const first = commit(dir, 'one')
  git(dir, 'push', '-q', 'origin', 'main')
  const second = commit(dir, 'two')
  git(dir, 'push', '-q', 'origin', 'main')
  git(dir, 'reset', '-q', '--hard', first)

  const note = run(dir)
  assert.ok(note, 'expected a behind-origin warning, got silence')
  assert.match(note, /1 commit behind origin\/main/)
  assert.ok(note.includes(first.slice(0, 7)), `expected HEAD sha ${first.slice(0, 7)} in: ${note}`)
  assert.ok(note.includes(second.slice(0, 7)), `expected origin sha ${second.slice(0, 7)} in: ${note}`)
  assert.doesNotMatch(note, /fetch origin` failed/, 'the fetch succeeded here — no degrade notice')
})

test('a checkout level with origin/main says nothing at all', () => {
  const { dir } = repoWithRemote()
  commit(dir, 'one')
  git(dir, 'push', '-q', 'origin', 'main')
  assert.equal(run(dir), null)
})

test('an uninitialised packages/sdk names the mypy trap, not a code failure', () => {
  const dir = repo()
  commit(dir, 'one')
  writeFileSync(join(dir, '.gitmodules'), '[submodule "packages/sdk"]\n\tpath = packages/sdk\n')
  mkdirSync(join(dir, 'packages', 'sdk'), { recursive: true })

  const note = run(dir)
  assert.ok(note, 'expected a submodule warning, got silence')
  assert.match(note, /packages\/sdk` is not materialized/)
  assert.match(note, /git submodule update --init packages\/sdk/)
})

test('a materialised submodule says nothing', () => {
  const dir = repo()
  commit(dir, 'one')
  writeFileSync(join(dir, '.gitmodules'), '[submodule "packages/sdk"]\n\tpath = packages/sdk\n')
  mkdirSync(join(dir, 'packages', 'sdk', 'src'), { recursive: true })
  assert.equal(run(dir), null)
})

test('a failed fetch still reports the count, and says the fetch failed', () => {
  const dir = repo()
  const first = commit(dir, 'one')
  commit(dir, 'two')
  // A remote-tracking ref without a reachable remote: the fetch must fail, the count must
  // still come from the last-fetched ref.
  git(dir, 'update-ref', 'refs/remotes/origin/main', git(dir, 'rev-parse', 'HEAD'))
  git(dir, 'reset', '-q', '--hard', first)
  git(dir, 'remote', 'add', 'origin', join(dir, 'nowhere.git'))

  const note = run(dir)
  assert.ok(note, 'expected a behind-origin warning, got silence')
  assert.match(note, /1 commit behind origin\/main/)
  assert.match(note, /fetch origin` failed/)
})

test('a path that is not a repository warns about nothing', () => {
  assert.equal(run(tempDir('session-preflight-plain-')), null)
})
