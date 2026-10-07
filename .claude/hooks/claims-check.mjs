#!/usr/bin/env node
// claims-check.mjs — claim-discipline sweep for design records and PR bodies (#420;
// review rubric G4: a set named in prose is regenerable from a mechanism;
// *cannot/never* needs the structural reason inline).
//
// Two layers, one direction of failure:
//   - Deterministic (always): sentences carrying normative markers are extracted;
//     citation presence is detected mechanically (file:line, issue/PR refs, backticked
//     paths). A normative claim with no citation anywhere in its sentence is flagged
//     `no-citation`. This layer cannot clear anything — it only flags.
//   - Judgment layer (when available): one Noul per CITED claim — does the surrounding
//     passage state the structural reason inline (the mechanism that makes the claim
//     true)? p < 0.5 flags `reason-missing`. The threshold lives in code.
//   - Unavailable: deterministic flags + an explicit disclosure. Failure direction is
//     toward flagged, never auto-cleared.
//
// Usage:
//   node .claude/hooks/claims-check.mjs design.md        # or stdin
//   node .claude/hooks/claims-check.mjs --json design.md
// Exit codes: 0 = no flags, 2 = flags found.
//
// EGRESS (M3, lane 2): in judgment mode the claim passages are sent to
// https://api.typesafe.ai. TYPESAFE_DISABLE forces the deterministic-only path.

import { readFileSync, realpathSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { createClient, noulQuestion } from './lib/typesafe.mjs'

const REASON_PRESENT = 0.5
const MAX_CLAIMS = 40 // bounded semantic batch

// Normative markers — the G4 vocabulary. Ordinary narration does not match.
// F9b: evasion phrasings ("unable to", "ruled out", "by construction") are in the list;
// the list remains a defined vocabulary and every disclosure says so — a guard states
// what it does not catch.
const NORMATIVE = /\b(?:cannot|can never|never|must always|always|only|every|all|no [a-z-]+ (?:can|may|will|way to)|guarantee[d]?|impossible|unable to|ruled out|by construction|ensure[sd]?(?: that)? no)\b/i

// Citation shapes: file:line, file, issue/PR refs, backticked paths.
const CITATION =
  /(?:`[^`\n]+`|\b[\w./-]+\.(?:py|md|json|toml|ya?ml|ts|mjs|go)(?::\d+(?:-\d+)?)?\b|\b(?:issue\s+|PR\s+)?#\d+\b|\bA\d{2}\b|\bG\d\b)/

/** Split text into sentence-ish claim units with their surrounding paragraph as passage. */
export function extractClaims(text) {
  const claims = []
  const paragraphs = text.split(/\n\s*\n/)
  for (const para of paragraphs) {
    // Code fences are not claims.
    if (/^\s*```/.test(para)) continue
    const sentences = para
      .replace(/\n/g, ' ')
      .split(/(?<=[.!?])\s+/)
      .map((s) => s.trim())
      .filter(Boolean)
    for (const s of sentences) {
      if (NORMATIVE.test(s)) claims.push({ text: s, passage: para.replace(/\n/g, ' ').trim() })
    }
  }
  return claims
}

/** Mechanical citation presence for one extracted claim. Pure. */
export function hasCitation(claim) {
  return CITATION.test(claim.text)
}

/**
 * @param {string} text the document
 * @param {{ask: Function}} [client] TypeSafe client or test double.
 */
export async function checkClaims(text, client) {
  const c = client || createClient()
  const all = extractClaims(text)
  for (const cl of all) cl.cited = hasCitation(cl)

  const flagged = all.filter((cl) => !cl.cited).map((cl) => ({ ...cl, why: 'no-citation' }))
  const base = { claimsTotal: all.length, flagged }

  const semantic = all.filter((cl) => cl.cited).slice(0, MAX_CLAIMS)
  const overflow = all.filter((cl) => cl.cited).length - semantic.length

  if (!semantic.length) {
    return {
      ...base,
      mode: 'none',
      reasonFlags: [],
      unjudged: 0,
      disclosure: `no cited claims to judge; the marker vocabulary is a defined list — normative claims worded outside it are invisible to the deterministic layer${overflow > 0 ? `; ${overflow} claim(s) beyond the semantic batch cap` : ''}`,
    }
  }

  const questions = {}
  semantic.forEach((cl, i) => {
    questions[`claim_${i}`] = noulQuestion(
      `Does \`claims[${i}].passage\` state the STRUCTURAL REASON inline — the mechanism that makes \`claims[${i}].text\` true (who writes these bytes, what enforces the invariant, why the path cannot be taken) — rather than merely asserting or restating the claim?`,
      {
        true: 'The passage names the mechanism: the reader could re-derive the claim from it',
        false: 'The passage asserts the claim, cites a location, or gestures at authority without the mechanism',
      }
    )
  })

  const r = await c.ask({ state: { claims: semantic }, questions })
  if (!r.ok) {
    return {
      ...base,
      mode: 'fallback',
      reasonFlags: [],
      // F9a: cited-but-unjudged claims are a disclosure, not a clean pass — the exit
      // contract treats them like flags.
      unjudged: semantic.length,
      disclosure: `structural-reason pass not run (typesafe: ${r.reason}) — ${semantic.length} cited claim(s) stand unjudged; only citation absence is flagged; the marker vocabulary is a defined list — claims worded outside it are invisible to the deterministic layer${overflow > 0 ? `; ${overflow} claim(s) beyond the semantic batch cap` : ''}`,
    }
  }

  const reasonFlags = []
  semantic.forEach((cl, i) => {
    const a = r.answers[`claim_${i}`]
    // F8: a probability is [0,1] or it is not an answer.
    const p = a?.noul
    if (typeof p !== 'number' || !Number.isFinite(p) || p < 0 || p > 1) {
      reasonFlags.push({ ...cl, why: 'reason-missing', note: 'invalid-answer' })
      return
    }
    if (p < REASON_PRESENT) reasonFlags.push({ ...cl, why: 'reason-missing', p })
  })

  return {
    ...base,
    mode: 'model',
    flagged: [...flagged, ...reasonFlags.map((f) => ({ text: f.text, passage: f.passage, why: f.why }))],
    reasonFlags,
    unjudged: overflow,
    disclosure: `semantic pass over ${semantic.length} cited claim(s); rule in code: reason-present probability < ${REASON_PRESENT} flags; the marker vocabulary is a defined list — claims worded outside it are invisible to the deterministic layer${overflow > 0 ? `; ${overflow} claim(s) beyond the semantic batch cap` : ''}`,
  }
}

// ---- CLI (guarded: importing for exports must never read stdin) ----
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
  const file = args.find((a) => !a.startsWith('--'))
  const text = file ? readFileSync(file, 'utf8') : readFileSync(0, 'utf8')

  const result = await checkClaims(text)
  if (asJson) {
    console.log(JSON.stringify(result, null, 2))
  } else {
    console.log(`claims-check: ${result.flagged.length} flagged of ${result.claimsTotal} normative claim(s) (${result.mode})`)
    console.log(`  ${result.disclosure}`)
    for (const f of result.flagged) console.log(`  [${f.why}] ${f.text.slice(0, 120)}`)
  }
  process.exit(result.flagged.length || result.unjudged ? 2 : 0)
}
