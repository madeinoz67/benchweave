// Tests for session-preflight.mjs — the SessionStart facts hook.
// Runs the real script against throwaway git repos, so no network and no dependence on this
// checkout's own state.

import { execFileSync, spawnSync } from 'node:child_process'
import { chmodSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
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

function put(dir, relPath, body = 'x') {
  const full = join(dir, relPath)
  mkdirSync(dirname(full), { recursive: true })
  writeFileSync(full, body)
  return full
}

function commit(dir, name) {
  put(dir, `${name}.txt`, name)
  git(dir, 'add', '.')
  git(dir, 'commit', '-q', '-m', name)
  return git(dir, 'rev-parse', 'HEAD')
}

// `env` overrides PATH for the hostile-git arms; everything else inherits.
function run(cwd, env = {}) {
  const res = spawnSync('node', [HOOK], {
    input: JSON.stringify({ session_id: 'preflight', cwd, hook_event_name: 'SessionStart' }),
    encoding: 'utf-8',
    timeout: 40000,
    env: { ...process.env, ...env },
  })
  assert.equal(res.status, 0, `hook must always exit 0 (stderr: ${res.stderr})`)
  if (!res.stdout.trim()) return null
  return JSON.parse(res.stdout).hookSpecificOutput?.additionalContext ?? null
}

// A checkout whose origin is a real local bare repo, so remote-tracking refs exist without
// any network call — the hook reads them and never fetches.
function repoWithRemote() {
  const dir = repo()
  const bare = tempDir('session-preflight-origin-')
  git(bare, 'init', '-q', '--bare')
  git(dir, 'remote', 'add', 'origin', bare)
  return { dir, bare }
}

// A real submodule registration: `.gitmodules` plus a gitlink, which is what
// `git submodule status` reads. A hand-written `.gitmodules` is not the same thing and made an
// earlier arm pass for the wrong reason.
function seed(hasSrc) {
  const dir = repo()
  commit(dir, 'base')
  if (hasSrc) {
    put(dir, 'src/benchweave_sdk/__init__.py', '')
    git(dir, 'add', '.')
    git(dir, 'commit', '-q', '-m', 'src')
  }
  return dir
}

function withSubmodule(hasSrc) {
  const dir = repo()
  commit(dir, 'base')
  execFileSync(
    'git',
    ['-C', dir, '-c', 'protocol.file.allow=always', 'submodule', 'add', '-q', seed(hasSrc), 'packages/sdk'],
    { encoding: 'utf-8' },
  )
  git(dir, 'commit', '-q', '-m', 'add submodule')
  return dir
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
  // The kill line: no fetch runs, so the count's provenance must be stated.
  assert.match(note, /hook does not fetch/)
  assert.match(note, /wrong in either direction/, 'a stale or tombstoned ref must be disclosed')
})

test('a checkout level with origin/main says nothing at all', () => {
  const { dir } = repoWithRemote()
  commit(dir, 'one')
  git(dir, 'push', '-q', 'origin', 'main')
  assert.equal(run(dir), null)
})

test('an uninitialised packages/sdk names the mypy trap, not a code failure', () => {
  const dir = withSubmodule(true)
  git(dir, 'submodule', 'deinit', '-f', 'packages/sdk')

  const note = run(dir)
  assert.ok(note, 'expected a submodule warning, got silence')
  assert.match(note, /packages\/sdk` is not initialized/)
  assert.match(note, /git submodule update --init packages\/sdk/)
  // The quoted mypy line must be the one the tool actually prints.
  assert.match(note, /packages\/sdk\/src: error: Cannot read file/)
})

test('a materialised submodule says nothing', () => {
  assert.equal(run(withSubmodule(true)), null)
})

test('a submodule checked out without its sources is not called uninitialised', () => {
  // The state here is materialised-and-wrong. Telling its owner to run `update --init` is
  // advice that changes nothing, repeated on every session start forever.
  const note = run(withSubmodule(false))
  assert.ok(note, 'expected a warning, got silence')
  assert.doesNotMatch(note, /is not initialized/)
  assert.match(note, /carries no `src\/`/)
  assert.match(note, /git submodule update packages\/sdk`/)
})

test('the submodule check still runs when the session starts in a subdirectory', () => {
  // git resolves the repository from a subdirectory; reading `.gitmodules` from the raw cwd
  // does not, so this half of the hook used to go silent while the other half kept working.
  const dir = withSubmodule(true)
  git(dir, 'submodule', 'deinit', '-f', 'packages/sdk')
  put(dir, 'src/benchweave/keep.py', '')

  const note = run(join(dir, 'src/benchweave'))
  assert.ok(note, 'expected the submodule warning from a subdirectory cwd, got silence')
  assert.match(note, /packages\/sdk` is not initialized/)
})

test('a path that merely mentions packages/sdk is not a declaration of it', () => {
  // Substring matching fired on these and then printed a remedy that errored out.
  const viaUrl = repo()
  commit(viaUrl, 'base')
  writeFileSync(
    join(viaUrl, '.gitmodules'),
    '[submodule "other"]\n\tpath = vendor/other\n\turl = https://example.invalid/packages/sdk.git\n',
  )
  assert.equal(run(viaUrl), null)

  const longerName = repo()
  commit(longerName, 'base')
  writeFileSync(
    join(longerName, '.gitmodules'),
    '[submodule "tools"]\n\tpath = vendor/packages/sdk-tools\n\turl = https://example.invalid/sdk-tools.git\n',
  )
  assert.equal(run(longerName), null)
})

test('the hook never fetches', () => {
  // A fetch is a write: it fast-forwards shared origin/* refs and FETCH_HEAD from whichever
  // worktree started the session, and a blackholed origin cost 5.175 s per start.
  const { dir } = repoWithRemote()
  commit(dir, 'one')
  git(dir, 'push', '-q', 'origin', 'main')
  const log = join(tempDir('session-preflight-log-'), 'calls.log')
  writeFileSync(log, '')

  const bin = tempDir('session-preflight-bin-')
  const realGit = execFileSync('sh', ['-c', 'command -v git'], { encoding: 'utf-8' }).trim()
  writeFileSync(join(bin, 'git'), `#!/bin/sh\necho "$@" >> ${log}\nexec ${realGit} "$@"\n`)
  chmodSync(join(bin, 'git'), 0o755)

  run(dir, { PATH: `${bin}:${process.env.PATH}` })
  const calls = execFileSync('cat', [log], { encoding: 'utf-8' })
  assert.doesNotMatch(calls, /\bfetch\b/, `the hook must not fetch; it ran: ${calls}`)
})

test('a wedged git cannot hold the session start open', () => {
  // Only the fetch carried a timeout before, so a git that blocked on anything else held the
  // start until the harness killed it.
  const { dir } = repoWithRemote()
  commit(dir, 'one')
  git(dir, 'push', '-q', 'origin', 'main')

  const bin = tempDir('session-preflight-bin-')
  const realGit = execFileSync('sh', ['-c', 'command -v git'], { encoding: 'utf-8' }).trim()
  writeFileSync(
    join(bin, 'git'),
    `#!/bin/sh\nfor a in "$@"; do if [ "$a" = "rev-list" ]; then sleep 30; fi; done\nexec ${realGit} "$@"\n`,
  )
  chmodSync(join(bin, 'git'), 0o755)

  const started = Date.now()
  run(dir, { PATH: `${bin}:${process.env.PATH}` })
  const elapsed = Date.now() - started
  assert.ok(elapsed < 6000, `bounded git calls expected, took ${elapsed}ms`)
})

test('a path that is not a repository warns about nothing', () => {
  assert.equal(run(tempDir('session-preflight-plain-')), null)
})
