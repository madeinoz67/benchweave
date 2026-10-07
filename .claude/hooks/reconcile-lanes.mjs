#!/usr/bin/env node
// reconcile-lanes.mjs — reconcile two adversary lanes' findings (#420, per #181 R3's
// two-lane refute discipline).
//
// Two layers, one direction of failure:
//   - Deterministic (always): findings in the SAME file within a line window become
//     candidate pairs. Different files never pair. Nothing merges without more.
//   - Judgment layer (when available): one Choice per candidate pair — distinct /
//     related / same_root — batched in a single call. CODE applies the rule:
//     same_root at confidence ≥ 0.6 merges; anything less is listed `uncertain` for
//     the row-call table, never silently merged.
//   - Unavailable: candidate pairs + single-lane findings + an explicit disclosure.
//     The failure direction is MORE clusters, never fewer.
//
// Usage:
//   node .claude/hooks/reconcile-lanes.mjs laneA.json laneB.json [--json]
// Each input is a JSON array of {id?, severity, file?, line?, summary}.

import { readFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'
import { createClient, choiceQuestion } from './lib/typesafe.mjs'

const LINE_WINDOW = 5
const MERGE_CONFIDENCE = 0.6
const MAX_PAIRS = 60 // bounded batch; beyond this the deterministic layer alone answers

/** Deterministic candidate pairs: same file, lines within the window. Pure. */
export function sameFilePairs(a, b) {
  const pairs = []
  for (const fa of a) {
    if (!fa.file) continue
    for (const fb of b) {
      if (fb.file !== fa.file) continue
      const la = fa.line ?? fa.line_start ?? null
      const lb = fb.line ?? fb.line_start ?? null
      if (la === null || lb === null || Math.abs(la - lb) > LINE_WINDOW) continue
      pairs.push({ a: fa, b: fb })
    }
  }
  return pairs.slice(0, MAX_PAIRS)
}

/**
 * @param {Array} laneA findings from adversary lane 1
 * @param {Array} laneB findings from adversary lane 2
 * @param {{ask: Function}} [client] TypeSafe client or test double.
 * @returns {Promise<{mode, candidatePairs, merged, uncertain, singleLane, disclosure}>}
 */
export async function reconcile(laneA, laneB, client) {
  const c = client || createClient()
  const pairs = sameFilePairs(laneA, laneB)

  const paired = new Set()
  for (const p of pairs) {
    paired.add(p.a)
    paired.add(p.b)
  }
  const singleLane = [...laneA.filter((f) => !paired.has(f)), ...laneB.filter((f) => !paired.has(f))]

  const base = { candidatePairs: pairs, singleLane }
  if (!pairs.length) {
    return { ...base, mode: 'model', merged: [], uncertain: [], disclosure: 'no same-file candidate pairs — nothing to reconcile semantically' }
  }

  const questions = {}
  pairs.forEach((p, i) => {
    questions[`pair_${i}`] = choiceQuestion(
      `Are \`pairs[${i}].a\` and \`pairs[${i}].b\` the same underlying defect? Judge the mechanism described, not the wording: two independently-found findings are the same root when fixing one necessarily fixes the other.`,
      {
        distinct: 'Different defects; fixing one leaves the other intact',
        related: 'Touch the same area but different root causes; both need their own fix',
        same_root: 'One underlying defect found twice; fixing it resolves both findings',
      }
    )
  })
  const state = { pairs: pairs.map((p) => ({ a: p.a, b: p.b })) }

  const r = await c.ask({ state, questions })
  if (!r.ok) {
    return {
      ...base,
      mode: 'fallback',
      merged: [],
      uncertain: [],
      disclosure: `semantic same-root pass not run (typesafe: ${r.reason}) — ${pairs.length} candidate pair(s) left unmerged for the row-call table`,
    }
  }

  const merged = []
  const uncertain = []
  const keptSeparate = []
  pairs.forEach((p, i) => {
    const a = r.answers[`pair_${i}`]
    if (!a || a.type !== 'choice' || typeof a.confidence !== 'number') {
      uncertain.push({ pair: p, why: 'invalid-answer' })
      return
    }
    if (a.confidence < MERGE_CONFIDENCE) {
      uncertain.push({ pair: p, why: `${a.choice} at confidence ${a.confidence.toFixed(2)} < ${MERGE_CONFIDENCE}` })
    } else if (a.choice === 'same_root') {
      merged.push({ members: [p.a, p.b], confidence: a.confidence })
    } else {
      // A confidently-distinct or confidently-related pair is RESOLVED, not open —
      // `uncertain` is exactly the row-call queue, nothing else.
      keptSeparate.push({ pair: p, verdict: a.choice, confidence: a.confidence })
    }
  })
  return {
    ...base,
    mode: 'model',
    merged,
    uncertain,
    keptSeparate,
    disclosure: `semantic pass ran over ${pairs.length} pair(s); rule in code: same_root at confidence >= ${MERGE_CONFIDENCE} merges`,
  }
}

// ---- CLI (guarded: importing for exports must never read files or stdin) ----
const isMain = import.meta.url === pathToFileURL(process.argv[1] || '').href
if (isMain) {
  const args = process.argv.slice(2)
  const asJson = args.includes('--json')
  const files = args.filter((a) => !a.startsWith('--'))
  if (files.length !== 2) {
    console.error('usage: node .claude/hooks/reconcile-lanes.mjs laneA.json laneB.json [--json]')
    process.exit(1)
  }
  const load = (p) => JSON.parse(readFileSync(p, 'utf8'))
  const result = await reconcile(load(files[0]), load(files[1]))
  if (asJson) {
    console.log(JSON.stringify(result, null, 2))
  } else {
    console.log(`reconcile-lanes: ${result.merged.length} merged, ${result.uncertain.length} uncertain/kept-separate, ${result.singleLane.length} single-lane (${result.mode})`)
    console.log(`  ${result.disclosure}`)
    for (const m of result.merged) console.log(`  MERGED  ${m.members.map((x) => x.id).join(' + ')} (confidence ${m.confidence.toFixed(2)})`)
    for (const u of result.uncertain) console.log(`  ROW-CALL ${u.pair.a.id} vs ${u.pair.b.id} — ${u.why}`)
    for (const f of result.singleLane) console.log(`  SINGLE  [${f.severity}] ${f.id || ''} ${f.file || '(no file)'}: ${f.summary}`)
  }
}
