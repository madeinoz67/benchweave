import { test } from 'node:test'
import assert from 'node:assert/strict'
import { sameFilePairs, reconcile } from '../reconcile-lanes.mjs'
import { createClient } from '../lib/typesafe.mjs'

delete process.env.TYPESAFE_API_KEY
delete process.env.TYPESAFE_DISABLE

const laneA = [
  { id: 'A1', severity: 'MEDIUM', file: 'src/benchweave/state/store.py', line: 120, summary: 'write-path race lets a deleted run resurrect' },
  { id: 'A2', severity: 'LOW', file: 'src/benchweave/cli/main.py', line: 40, summary: 'flag help text drifts from behavior' },
]
const laneB = [
  { id: 'B1', severity: 'MEDIUM', file: 'src/benchweave/state/store.py', line: 124, summary: 'concurrent delete+write can resurrect an engram-like row' },
  { id: 'B2', severity: 'NIT', file: 'docs/operator-guide.md', line: 8, summary: 'typo in section header' },
]

test('deterministic layer: same file, nearby lines become candidate pairs; different files never do', () => {
  const pairs = sameFilePairs(laneA, laneB)
  assert.equal(pairs.length, 1)
  assert.equal(pairs[0].a.id, 'A1')
  assert.equal(pairs[0].b.id, 'B1')
})

test('deterministic layer: line distance beyond the window does not pair', () => {
  const far = [{ id: 'B9', file: 'src/benchweave/state/store.py', line: 400, summary: 'x' }]
  assert.equal(sameFilePairs(laneA, far).length, 0)
})

test('unavailable judgment layer: pairs reported, merge not attempted, disclosure present', async () => {
  const r = await reconcile(laneA, laneB, createClient({ disable: true }))
  assert.equal(r.mode, 'fallback')
  assert.equal(r.candidatePairs.length, 1)
  assert.equal(r.merged.length, 0)
  assert.match(r.disclosure, /semantic same-root pass not run/)
  assert.ok(r.singleLane.some((f) => f.id === 'A2'))
  assert.ok(r.singleLane.some((f) => f.id === 'B2'))
})

const clientAnswering = (choice, confidence) => ({
  ask: async ({ questions }) => ({
    ok: true,
    model: 'jev-test',
    answers: Object.fromEntries(
      Object.keys(questions).map((id) => [id, { type: 'choice', choice, probabilities: {}, confidence }])
    ),
  }),
})

test('model path: same_root at adequate confidence merges the pair', async () => {
  const r = await reconcile(laneA, laneB, clientAnswering('same_root', 0.8))
  assert.equal(r.mode, 'model')
  assert.equal(r.merged.length, 1)
  assert.equal(r.merged[0].members.length, 2)
})

test('model path: same_root at low confidence is uncertain, never silently merged', async () => {
  const r = await reconcile(laneA, laneB, clientAnswering('same_root', 0.3))
  assert.equal(r.merged.length, 0)
  assert.equal(r.uncertain.length, 1)
})

test('model path: distinct keeps findings separate and single-lane flags intact', async () => {
  const r = await reconcile(laneA, laneB, clientAnswering('distinct', 0.9))
  assert.equal(r.merged.length, 0)
  assert.equal(r.uncertain.length, 0)
  assert.ok(r.singleLane.some((f) => f.id === 'B2'))
})

test('a failed model call degrades to the deterministic layer with disclosure', async () => {
  const r = await reconcile(laneA, laneB, { ask: async () => ({ ok: false, reason: 'timeout' }) })
  assert.equal(r.mode, 'fallback')
  assert.match(r.disclosure, /timeout/)
  assert.equal(r.candidatePairs.length, 1)
})

test('F5: numeric-string lines parse and pair within the window', () => {
  const A = [{ id: 'A1', file: 'src/x.py', line: 'L120', summary: 'a' }]
  const B = [{ id: 'B1', file: 'src/x.py', line: '120-124', summary: 'b' }]
  assert.equal(sameFilePairs(A, B).length, 1)
})

test('F5: far or unparseable line strings never pair — failure direction is more clusters', async () => {
  const far = [
    { id: 'A1', file: 'src/x.py', line: 'L10', summary: 'a' },
    { id: 'A2', file: 'src/x.py', line: 'near the top', summary: 'a2' },
  ]
  const B = [{ id: 'B1', file: 'src/x.py', line: '8890', summary: 'b' }]
  const r = await reconcile(far, B, createClient({ disable: true }))
  assert.equal(r.candidatePairs.length, 0)
  assert.equal(r.singleLane.length, 3)
})

test('R4: an off-vocabulary choice is invalid-answer, never resolved', async () => {
  const client = {
    ask: async () => ({ ok: true, model: 'm', answers: { pair_0: { type: 'choice', choice: 'banana', probabilities: {}, confidence: 0.99 } } }),
  }
  const r = await reconcile(laneA, laneB, client)
  assert.equal(r.merged.length, 0)
  assert.equal(r.keptSeparate.length, 0, 'banana at 0.99 must not buy its way onto keptSeparate')
  assert.equal(r.uncertain.length, 1)
  assert.match(r.uncertain[0].why, /invalid-answer/)
})

test('R4: same_root at out-of-range confidence never merges', async () => {
  const client = {
    ask: async () => ({ ok: true, model: 'm', answers: { pair_0: { type: 'choice', choice: 'same_root', probabilities: {}, confidence: 7 } } }),
  }
  const r = await reconcile(laneA, laneB, client)
  assert.equal(r.merged.length, 0)
  assert.equal(r.uncertain.length, 1)
  assert.match(r.uncertain[0].why, /invalid-answer/)
})

test('LOW: a no-pairs reconcile reports mode none, not a semantic pass', async () => {
  const r = await reconcile(
    [{ id: 'A1', file: 'a.py', line: 1, summary: 'x' }],
    [{ id: 'B1', file: 'b.py', line: 1, summary: 'y' }],
    createClient({ disable: true })
  )
  assert.equal(r.mode, 'none')
})

test('the question battery is one choice per candidate pair, options named in code', async () => {
  let seen = null
  const client = { ask: async ({ state, questions }) => { seen = { state, questions }; return { ok: true, model: 'm', answers: Object.fromEntries(Object.keys(questions).map((id) => [id, { type: 'choice', choice: 'distinct', probabilities: {}, confidence: 0.9 }])) } } }
  await reconcile(laneA, laneB, client)
  const ids = Object.keys(seen.questions)
  assert.equal(ids.length, 1)
  assert.deepEqual(Object.keys(seen.questions[ids[0]].criteria).sort(), ['distinct', 'related', 'same_root'])
  assert.ok(seen.state.pairs.length === 1)
})
