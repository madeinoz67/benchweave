import { test } from 'node:test'
import assert from 'node:assert/strict'
import { scoreBar } from '../lib/bar-score.mjs'
import { createClient } from '../lib/typesafe.mjs'

// Hermetic operator environment.
delete process.env.TYPESAFE_API_KEY
delete process.env.TYPESAFE_DISABLE

const RECORD = {
  concept: 'rtk pytest summaries',
  content: 'rtk filtered pytest summaries lie: No tests collected on green runs; exit codes survive. Read counts from junitxml attributes.',
  summary: 'one line',
  type: 'fact',
  tags: ['gotcha'],
}

const answersAt = (d, n, s) => ({
  ok: true,
  model: 'jev-test',
  answers: {
    durable: { type: 'score', score: d },
    non_obvious: { type: 'score', score: n },
    self_contained: { type: 'score', score: s },
  },
})

test('unavailable judgment layer: one skip line, advisory contract intact', async () => {
  const out = await scoreBar([RECORD], createClient({ disable: true }))
  assert.match(out, /bar scoring skipped \(typesafe: disabled\)/)
  assert.match(out, /append proceeds/)
})

test('a malformed score answer is a skip, never a fabricated verdict', async () => {
  const bad = { ask: async () => ({ ok: true, model: 'm', answers: { durable: { type: 'score' } } }) }
  const out = await scoreBar([RECORD], bad)
  assert.match(out, /skipped \(typesafe: invalid-answer\)/)
})

test('model path prints per-dimension feedback on the /4 scale', async () => {
  const out = await scoreBar([RECORD], { ask: async () => answersAt(3.5, 2.0, 4.0) })
  assert.match(out, /durable 3\.5\/4/)
  assert.match(out, /non-obvious 2\.0\/4/)
  assert.match(out, /self-contained 4\.0\/4/)
  assert.doesNotMatch(out, /below the bar/)
})

test('a below-bar composite names the protocol, and still does not block anything', async () => {
  const out = await scoreBar([RECORD], { ask: async () => answersAt(0.5, 0.5, 1.0) })
  assert.match(out, /below the bar/)
  assert.match(out, /your call; nothing is blocked/)
})

test('the question battery is three score questions with self-standing levels', async () => {
  let seen = null
  const client = { ask: async ({ questions }) => { seen = questions; return answersAt(2, 2, 2) } }
  await scoreBar([RECORD], client)
  for (const id of ['durable', 'non_obvious', 'self_contained']) {
    assert.equal(seen[id].type, 'score')
    assert.ok(seen[id].criteria.length >= 4, 'levels must describe concrete situations')
  }
})

test('F8: an out-of-domain score is invalid-answer, never a verdict', async () => {
  const neg = {
    ask: async () => ({
      ok: true,
      model: 'm',
      answers: {
        durable: { type: 'score', score: -1 },
        non_obvious: { type: 'score', score: 2 },
        self_contained: { type: 'score', score: 2 },
      },
    }),
  }
  const out = await scoreBar([RECORD], neg)
  assert.match(out, /skipped \(typesafe: invalid-answer\)/)
})

test('the state carries the proposal fields the bar judges, and nothing else', async () => {
  let seen = null
  const client = { ask: async ({ state }) => { seen = state; return answersAt(2, 2, 2) } }
  const rec = { ...RECORD, vault: 'benchweave', importance: 0.9 }
  await scoreBar([rec], client)
  assert.deepEqual(Object.keys(seen[0]).sort(), ['concept', 'content', 'summary'])
})
