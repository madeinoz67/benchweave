import { test } from 'node:test'
import assert from 'node:assert/strict'
import { extractClaims, hasCitation, checkClaims } from '../claims-check.mjs'
import { createClient } from '../lib/typesafe.mjs'

delete process.env.TYPESAFE_API_KEY
delete process.env.TYPESAFE_DISABLE

const DOC = `# Design record

The store cannot lose a committed run (see \`state/store.py:412\` — the write is
fsynced before the ack is sent).

This can never happen in practice.

Every writer goes through the coordinator, so duplicates are impossible.

Sometimes the cache is warm.
`

test('deterministic layer: normative sentences are extracted, ordinary ones are not', () => {
  const claims = extractClaims(DOC)
  const texts = claims.map((c) => c.text)
  assert.ok(texts.some((t) => t.includes('cannot lose a committed run')))
  assert.ok(texts.some((t) => t.includes('can never happen')))
  assert.ok(texts.some((t) => t.includes('duplicates are impossible')))
  assert.ok(!texts.some((t) => t.includes('Sometimes the cache is warm')))
})

test('deterministic layer: a file:line reference counts as a citation; bare assertion does not', () => {
  const claims = extractClaims(DOC)
  const cited = claims.find((c) => c.text.includes('cannot lose a committed run'))
  const bare = claims.find((c) => c.text.includes('can never happen'))
  assert.equal(hasCitation(cited), true)
  assert.equal(hasCitation(bare), false)
})

test('unavailable judgment layer: bare normative claims flagged, disclosure present, nothing auto-cleared', async () => {
  const r = await checkClaims(DOC, createClient({ disable: true }))
  assert.equal(r.mode, 'fallback')
  assert.match(r.disclosure, /structural-reason pass not run/)
  assert.ok(r.flagged.some((c) => c.text.includes('can never happen') && c.why === 'no-citation'))
  assert.ok(r.flagged.some((c) => c.text.includes('duplicates are impossible') && c.why === 'no-citation'))
  const cited = r.flagged.filter((c) => c.why === 'reason-missing')
  assert.equal(cited.length, 0, 'fallback cannot manufacture a reason-missing verdict — it can only flag citation absence')
})

const noulAt = (p) => ({
  ask: async ({ questions }) => ({
    ok: true,
    model: 'jev-test',
    answers: Object.fromEntries(Object.keys(questions).map((id) => [id, { type: 'noul', noul: p }])),
  }),
})

test('model path: a cited claim whose passage lacks the structural reason is flagged', async () => {
  const r = await checkClaims(DOC, noulAt(0.15))
  assert.equal(r.mode, 'model')
  assert.ok(r.flagged.some((c) => c.why === 'reason-missing' && c.text.includes('cannot lose a committed run')))
})

test('model path: a cited claim with the reason inline passes clean', async () => {
  const r = await checkClaims(DOC, noulAt(0.92))
  assert.equal(r.flagged.filter((c) => c.why === 'reason-missing').length, 0)
  assert.ok(r.flagged.some((c) => c.why === 'no-citation'), 'no-citation flags are deterministic and stand regardless')
})

test('the judgment question references the claim and its passage by backticked paths', async () => {
  let seen = null
  const client = { ask: async ({ state, questions }) => { seen = { state, questions }; return { ok: true, model: 'm', answers: Object.fromEntries(Object.keys(questions).map((id) => [id, { type: 'noul', noul: 0.9 }])) } } }
  await checkClaims(DOC, client)
  const cited = seen.state.claims.filter((c) => c.cited)
  assert.ok(cited.length >= 1)
  assert.ok(Object.keys(seen.questions).length === cited.length, 'one noul per cited claim')
  assert.match(Object.values(seen.questions)[0].instructions, /claims\[\d+\]\.passage/)
})

test('F9b: evasion-shaped normative wording is extracted and the vocabulary blind spot disclosed', async () => {
  const doc = 'The store is unable to lose a committed run. Duplication is ruled out by construction.\n'
  const claims = extractClaims(doc)
  assert.ok(claims.length >= 2, 'evasion phrasings must still be extracted as claims')
  const r = await checkClaims(doc, createClient({ disable: true }))
  assert.match(r.disclosure, /marker vocabulary is a defined list/)
})

test('R5: an out-of-domain noul in the semantic pass is flagged, never silently cleared', async () => {
  const doc = 'The store cannot lose a committed run (`state/store.py:412`).\n'
  const client = { ask: async () => ({ ok: true, model: 'm', answers: { claim_0: { type: 'noul', noul: -5 } } }) }
  const r = await checkClaims(doc, client)
  assert.ok(r.reasonFlags.some((f) => f.note === 'invalid-answer'), 'the malformed arm needs test teeth in this file too')
})

test('LOW: claims-check with nothing to judge reports mode none', async () => {
  const r = await checkClaims('Sometimes the cache is warm.', createClient({ disable: true }))
  assert.equal(r.mode, 'none')
})

test('claims beyond the batch cap are disclosed, not silently dropped', async () => {
  const big = Array.from({ length: 50 }, (_, i) => `Rule ${i}: this can never happen anywhere (\`src/x${i}.py:10\`).\n\n`).join('')
  const r = await checkClaims(big, createClient({ disable: true }))
  assert.ok(r.claimsTotal > 40)
  assert.match(r.disclosure, /10 claim\(s\) beyond the semantic batch cap/)
})
