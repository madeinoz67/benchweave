// Fold-wave tests for the #420 adversary findings (F1-F9). Each names its row.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const HOOKS = resolve(HERE, '..') // tests → .claude/hooks
const PRIVACY = join(HOOKS, 'privacy-screen.mjs')
const CLAIMS = join(HOOKS, 'claims-check.mjs')
const PROPOSE = join(HOOKS, 'memory-propose.mjs')

const LEAKY = 'We measured on the Kemerton lab bench (SN KEM-4417). Dave emailed dave@example.com the store from /Users/dave/corpus.db.'
const CLEAN = 'Measured on a real 400-run bench history. Recovery improved from 0/8 to 8/8 truthful interrupted records.'
const NO_KEY = { TYPESAFE_DISABLE: '1', TYPESAFE_ENV_FILE: '/nonexistent/fold.env' }

const run = (tool, args, env, input = '') =>
  spawnSync(process.execPath, [tool, ...args], { input, encoding: 'utf8', env: { ...process.env, ...env } })

// F1 HIGH: --json must exit by verdict, both branches.
test('F1: privacy-screen --json BLOCK exits 3, clean-disabled REVIEW exits 2', () => {
  const b = run(PRIVACY, ['--json'], NO_KEY, LEAKY)
  assert.equal(b.status, 3, `BLOCK must exit 3 even in --json mode; stdout: ${b.stdout}; stderr: ${b.stderr}`)
  const parsed = JSON.parse(b.stdout)
  assert.equal(parsed.verdict, 'BLOCK')

  const tmp = mkdtempSync(join(tmpdir(), 'f1-'))
  try {
    const clean = join(tmp, 'clean.md')
    writeFileSync(clean, CLEAN)
    const p = run(PRIVACY, ['--json', clean], NO_KEY)
    assert.equal(p.status, 2, 'clean text with the judgment layer disabled is REVIEW (fail-safe), never PASS')
    assert.equal(JSON.parse(p.stdout).verdict, 'REVIEW')
  } finally {
    rmSync(tmp, { recursive: true, force: true })
  }
})

// F6 MEDIUM: a symlinked CLI invocation must behave exactly like a direct one.
test('F6: symlinked privacy-screen runs (not a silent exit-0 no-op)', () => {
  const tmp = mkdtempSync(join(tmpdir(), 'f6-'))
  try {
    const report = join(tmp, 'r.md')
    writeFileSync(report, LEAKY)
    const link = join(tmp, 'screen-link.mjs')
    symlinkSync(PRIVACY, link)
    const r = spawnSync(process.execPath, [link, '--json', report], { encoding: 'utf8', env: { ...process.env, ...NO_KEY } })
    assert.notEqual(r.stdout, '', 'a symlinked run must produce output')
    assert.equal(r.status, 3)
    assert.equal(JSON.parse(r.stdout).verdict, 'BLOCK')
  } finally {
    rmSync(tmp, { recursive: true, force: true })
  }
})

// F9a: claims-check fallback with cited-but-unjudged claims cannot exit clean.
test('F9a: claims-check fallback exits 2 when cited claims went unjudged', () => {
  const tmp = mkdtempSync(join(tmpdir(), 'f9-'))
  try {
    const doc = join(tmp, 'doc.md')
    writeFileSync(doc, 'The store cannot lose a committed run (`state/store.py:412`).\n')
    const r = run(CLAIMS, [doc], NO_KEY)
    assert.equal(r.status, 2, 'unjudged cited claims are a disclosure, not a clean pass')
    assert.match(r.stdout, /structural-reason pass not run/)
  } finally {
    rmSync(tmp, { recursive: true, force: true })
  }
})

// M2 (lane 2): the F4 arm above pins the env-file out of range, so the guard itself is
// not its discriminator. THIS test leaves a real key reachable and a dead endpoint —
// only the NODE_TEST_CONTEXT guard can produce no-key. Pre-guard code returns 'network'.
test('M2: the hermeticity guard itself is the discriminator — key reachable, still no live call', () => {
  const tmp = mkdtempSync(join(tmpdir(), 'm2-'))
  try {
    const envDir = join(tmp, 'env')
    mkdirSync(envDir)
    writeFileSync(join(envDir, 'ts.env'), 'TYPESAFE_API_KEY=k-live-fixture\n')
    const rec = { concept: 'guard discriminator probe', content: 'a probe record long enough to clear the forty-character content floor for validation', summary: 's', type: 'fact', tags: ['probe'], source: 'test' }
    const r = spawnSync(process.execPath, [PROPOSE], {
      input: JSON.stringify(rec),
      encoding: 'utf8',
      env: {
        ...process.env,
        TYPESAFE_ENV_FILE: join(envDir, 'ts.env'), // a REAL key file, in range
        TYPESAFE_ENDPOINT: 'http://127.0.0.1:9/', // dead port: a resolved key would surface as network, fast
        MUNINN_LEDGER_ROOT: tmp,
        MUNINN_PROPOSAL_VAULT: 'probe',
      },
    })
    assert.equal(r.status, 0, r.stderr)
    assert.match(r.stdout, /bar scoring skipped \(typesafe: no-key\)/, 'the guard must suppress the key file; network would mean it resolved')
    assert.doesNotMatch(r.stdout, /bar feedback \(advisory/)
  } finally {
    rmSync(tmp, { recursive: true, force: true })
  }
})

// F4: a node:test-spawned memory-propose never reaches the operator's key, with or
// without an explicit disable in the spawning test.
test('F4: hooks spawned from node:test are hermetic — no operator key, no live call', () => {
  const tmp = mkdtempSync(join(tmpdir(), 'f4-'))
  try {
    const rec = { concept: 'hermeticity probe', content: 'a probe record long enough to clear the forty-character content floor for validation', summary: 's', type: 'fact', tags: ['probe'], source: 'test' }
    const r = spawnSync(process.execPath, [PROPOSE], {
      input: JSON.stringify(rec),
      encoding: 'utf8',
      // Deliberately NO TYPESAFE_DISABLE: the NODE_TEST_CONTEXT inherited from this
      // test process must keep the hook off the operator's key file on its own.
      env: { ...process.env, TYPESAFE_ENV_FILE: '/nonexistent/f4.env', MUNINN_LEDGER_ROOT: tmp, MUNINN_PROPOSAL_VAULT: 'probe' },
    })
    assert.equal(r.status, 0, r.stderr)
    assert.match(r.stdout, /bar scoring skipped \(typesafe: (no-key|disabled)\)/)
    assert.doesNotMatch(r.stdout, /bar feedback \(advisory/)
  } finally {
    rmSync(tmp, { recursive: true, force: true })
  }
})
