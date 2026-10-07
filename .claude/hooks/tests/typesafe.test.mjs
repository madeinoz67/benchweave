import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createClient, noulQuestion, choiceQuestion, scoreQuestion } from '../lib/typesafe.mjs'

// Hermetic: strip operator environment so key resolution is deterministic in this file.
delete process.env.TYPESAFE_API_KEY
delete process.env.TYPESAFE_DISABLE

const NO_ENV = { envFile: '/nonexistent/typesafe-test.env' }
const okFetch = (body) => async () => ({ ok: true, status: 200, json: async () => body })
const SAMPLE = {
  model: 'jev-test',
  answers: { hazard: { type: 'noul', noul: 0.93 } },
  usage: { input_tokens: 10, output_tokens: 2 },
}

test('disable override short-circuits before any key resolution or network', async () => {
  let called = false
  const c = createClient({ ...NO_ENV, disable: true, fetchImpl: async () => { called = true } })
  const r = await c.ask({ state: 'x', questions: { q: noulQuestion('is it?') } })
  assert.equal(r.ok, false)
  assert.equal(r.reason, 'disabled')
  assert.equal(called, false, 'no network call may happen when disabled')
})

test('missing key reports no-key without touching the network', async () => {
  let called = false
  const c = createClient({ ...NO_ENV, key: '', fetchImpl: async () => { called = true } })
  const r = await c.ask({ state: 'x', questions: { q: noulQuestion('is it?') } })
  assert.equal(r.reason, 'no-key')
  assert.equal(called, false)
})

test('a hanging request resolves to timeout, bounded by the client timeout', async () => {
  const c = createClient({
    ...NO_ENV,
    key: 'k-test',
    timeoutMs: 25,
    // A fetch implementation that ignores the abort signal — the client must bound the
    // await itself (Promise.race), never trust the implementation to honor the signal.
    fetchImpl: () => new Promise(() => {}),
  })
  const r = await c.ask({ state: 'x', questions: { q: noulQuestion('is it?') } })
  assert.equal(r.ok, false)
  assert.equal(r.reason, 'timeout')
})

test('non-2xx maps to http-<status>', async () => {
  const c = createClient({ ...NO_ENV, key: 'k-test', fetchImpl: async () => ({ ok: false, status: 503, json: async () => ({}) }) })
  const r = await c.ask({ state: 'x', questions: { q: noulQuestion('is it?') } })
  assert.equal(r.reason, 'http-503')
})

test('fetch rejection maps to network', async () => {
  const c = createClient({ ...NO_ENV, key: 'k-test', fetchImpl: async () => { throw new Error('ECONNREFUSED') } })
  const r = await c.ask({ state: 'x', questions: { q: noulQuestion('is it?') } })
  assert.equal(r.reason, 'network')
})

test('success returns answers keyed by question id, with no key material anywhere', async () => {
  const c = createClient({ ...NO_ENV, key: 'k-secret-value', fetchImpl: okFetch(SAMPLE) })
  const r = await c.ask({ state: 'report text', questions: { hazard: noulQuestion('hazard?') } })
  assert.equal(r.ok, true)
  assert.equal(r.answers.hazard.noul, 0.93)
  assert.equal(r.model, 'jev-test')
  assert.ok(!JSON.stringify(r).includes('k-secret-value'), 'the key must never appear in a result')
})

test('a 200 whose body lacks the answers map is invalid-response, never a pass', async () => {
  const c = createClient({ ...NO_ENV, key: 'k-test', fetchImpl: okFetch({ model: 'jev-test' }) })
  const r = await c.ask({ state: 'x', questions: { q: noulQuestion('is it?') } })
  assert.equal(r.ok, false)
  assert.equal(r.reason, 'invalid-response')
})

test('question builders match the API contract shapes', () => {
  assert.deepEqual(noulQuestion('present?', { true: 'yes', false: 'no' }), {
    type: 'noul', instructions: 'present?', criteria: { true: 'yes', false: 'no' },
  })
  assert.equal(noulQuestion('present?').criteria, undefined)
  assert.deepEqual(choiceQuestion('pick', { a: 'first', b: 'second' }), {
    type: 'choice', instructions: 'pick', criteria: { a: 'first', b: 'second' },
  })
  assert.deepEqual(scoreQuestion('how much', ['none', 'some', 'all']), {
    type: 'score', instructions: 'how much', criteria: ['none', 'some', 'all'],
  })
})

test('F7: a real-fetch abort (signal-honoring) maps to timeout, not network', async () => {
  const c = createClient({
    ...NO_ENV,
    key: 'k-test',
    timeoutMs: 30,
    fetchImpl: (_url, init) =>
      new Promise((_resolve, reject) => {
        init.signal.addEventListener('abort', () =>
          reject(Object.assign(new Error('This operation was aborted'), { name: 'AbortError' }))
        )
      }),
  })
  const r = await c.ask({ state: 'x', questions: { q: noulQuestion('is it?') } })
  assert.equal(r.reason, 'timeout')
})

test('the bearer key travels in the Authorization header, never in the URL', async () => {
  let seenUrl = null
  let seenHeaders = null
  const c = createClient({
    ...NO_ENV,
    key: 'k-secret-value',
    fetchImpl: async (url, init) => {
      seenUrl = url
      seenHeaders = init.headers
      return { ok: true, status: 200, json: async () => SAMPLE }
    },
  })
  await c.ask({ state: 'x', questions: { hazard: noulQuestion('hazard?') } })
  assert.ok(!String(seenUrl).includes('k-secret-value'))
  assert.equal(seenHeaders.Authorization, 'Bearer k-secret-value')
})
