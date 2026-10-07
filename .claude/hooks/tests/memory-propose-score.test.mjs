import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const HOOK = resolve(HERE, '..', 'memory-propose.mjs')

const RECORD = {
  concept: 'scoring integration probe',
  content: 'a self-contained probe record long enough to clear the forty-character content floor',
  summary: 'one line',
  type: 'fact',
  tags: ['probe'],
  source: 'test',
}

function runHook(extraEnv) {
  const dir = mkdtempSync(join(tmpdir(), 'mp-score-'))
  const r = spawnSync(process.execPath, [HOOK], {
    input: JSON.stringify(RECORD),
    encoding: 'utf8',
    env: {
      ...process.env,
      TYPESAFE_DISABLE: '1', // force the designed fallback path
      TYPESAFE_ENV_FILE: '/nonexistent/mp-score.env',
      MUNINN_LEDGER_ROOT: dir,
      MUNINN_PROPOSAL_VAULT: 'probe-vault',
      ...extraEnv,
    },
  })
  return { r, dir }
}

test('--check implies --no-score: pure validation makes no judgment call and pays no linger', () => {
  const dir = mkdtempSync(join(tmpdir(), 'mp-checkscore-'))
  try {
    const r = spawnSync(process.execPath, [HOOK, '--check'], {
      input: JSON.stringify(RECORD),
      encoding: 'utf8',
      env: {
        ...process.env,
        TYPESAFE_ENV_FILE: '/nonexistent/mp-score.env',
        MUNINN_LEDGER_ROOT: dir,
        MUNINN_PROPOSAL_VAULT: 'probe-vault',
        // No TYPESAFE_DISABLE: --check itself must suppress scoring.
      },
    })
    assert.equal(r.status, 0, r.stderr)
    assert.match(r.stdout, /--check, nothing appended/)
    assert.doesNotMatch(r.stdout, /bar sco/)
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
})

const findLedger = (dir) => {
  const walk = (d) =>
    readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(join(d, e.name)) : [join(d, e.name)]))
  return walk(dir).find((p) => p.endsWith('memory-proposals.jsonl'))
}

test('judgment layer disabled: skip line, append proceeds — the producer never loses a finding to advice', () => {
  const { r, dir } = runHook()
  try {
    assert.equal(r.status, 0, r.stderr)
    assert.match(r.stdout, /bar scoring skipped \(typesafe: disabled\)/)
    assert.match(r.stdout, /appended 1 proposal/)
    const ledger = findLedger(dir)
    assert.ok(ledger, 'ledger file must exist under the override root')
    assert.equal(readFileSync(ledger, 'utf8').trim().split('\n').length, 1)
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
})

test('--no-score opts out cleanly: no scoring line, append unchanged', () => {
  const { r, dir } = runHook({})
  const r2 = (() => {
    const dir2 = mkdtempSync(join(tmpdir(), 'mp-noscore-'))
    const rr = spawnSync(process.execPath, [HOOK, '--no-score'], {
      input: JSON.stringify(RECORD),
      encoding: 'utf8',
      env: {
        ...process.env,
        TYPESAFE_DISABLE: '1',
        TYPESAFE_ENV_FILE: '/nonexistent/mp-score.env',
        MUNINN_LEDGER_ROOT: dir2,
        MUNINN_PROPOSAL_VAULT: 'probe-vault',
      },
    })
    return { rr, dir2 }
  })()
  try {
    assert.equal(r2.rr.status, 0, r2.rr.stderr)
    assert.doesNotMatch(r2.rr.stdout, /bar scoring/)
    assert.match(r2.rr.stdout, /appended 1 proposal/)
    // The first (scoring-enabled) run also survived, for symmetry.
    assert.equal(r.status, 0)
  } finally {
    rmSync(r2.dir2, { recursive: true, force: true })
    rmSync(dir, { recursive: true, force: true })
  }
})
