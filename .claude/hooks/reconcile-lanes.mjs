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
//
// EGRESS (M3, lane 2): in judgment mode the candidate finding pairs are sent to
// https://api.typesafe.ai. TYPESAFE_DISABLE forces the deterministic-only path.

import { readFileSync, realpathSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { createClient, choiceQuestion } from './lib/typesafe.mjs'

const LINE_WINDOW = 5
const MERGE_CONFIDENCE = 0.6
const MAX_PAIRS = 60 // bounded batch; beyond this the deterministic layer alone answers
const VALID_VERDICTS = ['distinct', 'related', 'same_root'] // R4: off-vocabulary answers are not answers

/** F5: line fields arrive as numbers and as natural LLM emissions ("L17", "120-124").
 * Parse the leading integer when one exists; anything unparseable never pairs —
 * the failure direction is more clusters, never fewer. */
function lineNumber(f) {
  const n = f?.line ?? f?.line_start ?? null
  if (typeof n === 'number' && Number.isFinite(n)) return n
  if (typeof n === 'string') {
    const m = n.match(/\d+/)
    if (m) return Number(m[0])
  }
  return null
}

/** Deterministic candidate pairs: same file, lines within the window. Pure. */
export function sameFilePairs(a, b) {
  const pairs = []
  for (const fa of a) {
    if (!fa.file) continue
    for (const fb of b) {
      if (fb.file !== fa.file) continue
      const la = lineNumber(fa)
      const lb = lineNumber(fb)
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
  const capped = pairs.length === MAX_PAIRS
  if (!pairs.length) {
    // LOW: nothing was judged — a mode keyed on 'model' would read as a semantic pass
    return { ...base, mode: 'none', merged: [], uncertain: [], keptSeparate: [], disclosure: 'no same-file candidate pairs — nothing to reconcile semantically' }
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
      keptSeparate: [],
      disclosure: `semantic same-root pass not run (typesafe: ${r.reason}) — ${pairs.length} candidate pair(s) left unmerged for the row-call table${capped ? `; deterministic pairing reached the ${MAX_PAIRS}-pair cap — excess same-file findings appear single-lane` : ''}`,
    }
  }

  const merged = []
  const uncertain = []
  const keptSeparate = []
  pairs.forEach((p, i) => {
    const a = r.answers[`pair_${i}`]
    const conf = a?.confidence
    // F8 + R4: confidence is [0,1] AND the choice is in the vocabulary, or it is not
    // an answer — an off-vocabulary verdict at high confidence must not buy its way
    // onto keptSeparate (recorded RESOLVED) the way 'banana' at 0.99 did.
    if (
      !a ||
      a.type !== 'choice' ||
      !VALID_VERDICTS.includes(a.choice) ||
      typeof conf !== 'number' ||
      !Number.isFinite(conf) ||
      conf < 0 ||
      conf > 1
    ) {
      uncertain.push({ pair: p, why: 'invalid-answer' })
      return
    }
    if (conf < MERGE_CONFIDENCE) {
      uncertain.push({ pair: p, why: `${a.choice} at confidence ${conf.toFixed(2)} < ${MERGE_CONFIDENCE}` })
    } else if (a.choice === 'same_root') {
      merged.push({ members: [p.a, p.b], confidence: conf })
    } else {
      // A confidently-distinct or confidently-related pair is RESOLVED, not open —
      // `uncertain` is exactly the row-call queue, nothing else.
      keptSeparate.push({ pair: p, verdict: a.choice, confidence: conf })
    }
  })
  return {
    ...base,
    mode: 'model',
    merged,
    uncertain,
    keptSeparate,
    disclosure: `semantic pass ran over ${pairs.length} pair(s); rule in code: same_root at confidence >= ${MERGE_CONFIDENCE} merges${capped ? `; deterministic pairing reached the ${MAX_PAIRS}-pair cap — excess same-file findings appear single-lane` : ''}`,
  }
}

// ---- CLI (guarded: importing for exports must never read files or stdin) ----
// F6: real paths, not as-typed — a symlinked invocation runs the CLI, never a silent no-op.
const isMain = (() => {
  try {
    return realpathSync(fileURLToPath(import.meta.url)) === realpathSync(resolve(process.argv[1] || 'x-not-main'))
  } catch {
    return false
  }
})()
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
    for (const m of result.merged) console.log(`  MERGED  ${m.members.map((x) => x.id || '(no id)').join(' + ')} (confidence ${m.confidence.toFixed(2)})`)
    for (const u of result.uncertain) console.log(`  ROW-CALL ${(u.pair.a.id || '(no id)')} vs ${(u.pair.b.id || '(no id)')} — ${u.why}`)
    for (const f of result.singleLane) console.log(`  SINGLE  [${f.severity}] ${f.id || '(no id)'} ${f.file || '(no file)'}: ${f.summary}`)
  }
}
