import { test } from 'node:test'
import assert from 'node:assert/strict'
import { screen, fallbackScan, verdictFromHazards, THRESHOLDS } from '../privacy-screen.mjs'
import { createClient } from '../lib/typesafe.mjs'

// Hermetic operator environment.
delete process.env.TYPESAFE_API_KEY
delete process.env.TYPESAFE_DISABLE

const disabled = createClient({ disable: true })
const modelAnswers = (p) => ({
  ok: true,
  model: 'jev-test',
  answers: Object.fromEntries(
    ['device_identifier', 'person_or_org', 'bench_or_site', 'protocol_content', 'query_text', 'path_leak'].map((id) => [
      id,
      { type: 'noul', noul: p },
    ])
  ),
})
const CLEAN = 'Measured on a real 400-run bench history. Recovery rate 8/8 runs to a truthful interrupted record; median latency 0.67 s at 20,500 rows.'

test('fail-safe RED arm: clean text with the judgment layer unavailable is REVIEW, never PASS', async () => {
  const r = await screen(CLEAN, disabled)
  assert.equal(r.verdict, 'REVIEW')
  assert.equal(r.mode, 'fallback')
  assert.match(r.reason, /semantic screen not run/)
})

test('deterministic fallback catches the mechanical identifier classes', () => {
  const hits = fallbackScan('contact ops@example.org for the corpus')
  assert.ok(hits.some((h) => h.id === 'email'))
  assert.equal(hits.every((h) => ['email', 'home_path', 'hex_dump', 'mac', 'ipv4', 'serial_like'].includes(h.id)), true)
})

test('fallback: an operator home path is a mechanical leak', () => {
  const hits = fallbackScan('store opened from /Users/someone/src/corpus.db')
  assert.ok(hits.some((h) => h.id === 'home_path'))
})

test('fallback: a hex dump is captured protocol content', () => {
  const hits = fallbackScan('frame: de ad be ef 00 11 22 33 44 55 66 77 88')
  assert.ok(hits.some((h) => idMatches(h, 'hex_dump')))
  function idMatches(h, id) { return h.id === id }
})

test('fallback hits escalate the verdict the same way model probabilities do', async () => {
  const r = await screen('reached out to ops@example.org about bench A', disabled)
  assert.equal(r.verdict, 'BLOCK')
  assert.equal(r.mode, 'fallback')
})

test('model path: probabilities threshold to BLOCK / REVIEW / PASS', () => {
  assert.equal(verdictFromHazards({ device_identifier: 0.93 }).verdict, 'BLOCK')
  assert.equal(verdictFromHazards({ device_identifier: 0.60 }).verdict, 'REVIEW')
  assert.equal(verdictFromHazards({ device_identifier: 0.20 }).verdict, 'PASS')
  assert.equal(THRESHOLDS.block, 0.85)
  assert.equal(THRESHOLDS.review, 0.5)
})

test('model path: BLOCK wins over REVIEW regardless of hazard order', () => {
  const r = verdictFromHazards({ query_text: 0.55, person_or_org: 0.91 })
  assert.equal(r.verdict, 'BLOCK')
  assert.ok(r.blocking.includes('person_or_org'))
})

test('model path on clean text returns PASS with per-hazard probabilities', async () => {
  const client = { ask: async () => modelAnswers(0.02) }
  const r = await screen(CLEAN, client)
  assert.equal(r.verdict, 'PASS')
  assert.equal(r.mode, 'model')
  assert.equal(r.hazards.device_identifier, 0.02)
})

test('a failed model call degrades to the fallback, never to PASS', async () => {
  const client = { ask: async () => ({ ok: false, reason: 'http-503' }) }
  const r = await screen(CLEAN, client)
  assert.equal(r.verdict, 'REVIEW')
  assert.equal(r.mode, 'fallback')
  assert.match(r.reason, /http-503/)
})

test('the question battery covers every hazard the threshold table names', async () => {
  let seen = null
  const client = { ask: async ({ questions }) => { seen = questions; return modelAnswers(0.02) } }
  await screen(CLEAN, client)
  const ids = Object.keys(seen)
  for (const id of ['device_identifier', 'person_or_org', 'bench_or_site', 'protocol_content', 'query_text', 'path_leak']) {
    assert.ok(ids.includes(id), `battery must ask ${id}`)
    assert.equal(seen[id].type, 'noul')
  }
  assert.equal(ids.length, 6)
})

test('F8: an out-of-domain probability is an unavailable screen, never a pass', async () => {
  const ids = ['device_identifier', 'person_or_org', 'bench_or_site', 'protocol_content', 'query_text', 'path_leak']
  const client = {
    ask: async () => ({
      ok: true,
      model: 'm',
      answers: Object.fromEntries(ids.map((id) => [id, { type: 'noul', noul: id === 'person_or_org' ? -5 : 0.02 }])),
    }),
  }
  const r = await screen(CLEAN, client)
  assert.equal(r.mode, 'fallback')
  assert.match(r.reason, /invalid-answer/)
})

test('F2: adversarial no-dot email-shaped input completes fast and yields no email hit', () => {
  const evil = 'a'.repeat(20000) + '@' + 'b'.repeat(20000)
  const t0 = process.hrtime.bigint()
  const hits = fallbackScan(evil)
  const ms = Number(process.hrtime.bigint() - t0) / 1e6
  assert.ok(!hits.some((h) => h.id === 'email'))
  assert.ok(ms < 500, `scan must be near-linear, took ${ms.toFixed(1)}ms`) // 150x headroom; not a CI perf gate, a blowup tripwire
})

test('M1 (lane 2): sentence-final punctuation does not erase an email the old regex caught', () => {
  const hits1 = fallbackScan('Contact the operator at ops@example.com. They replied.')
  assert.ok(hits1.some((h) => h.id === 'email' && h.match === 'ops@example.com'), 'trailing period erased the hit at 3ca9586e')
  const hits2 = fallbackScan('Reach ops@example.com... or ops@example.com- for anything.')
  assert.equal(hits2.filter((h) => h.id === 'email').length, 2, 'dot-runs and hyphens after the domain must trim, not swallow')
})

test('no PASS verdict is reachable with an unavailable judgment layer, even for empty text', async () => {
  const r = await screen('', disabled)
  assert.notEqual(r.verdict, 'PASS')
})
