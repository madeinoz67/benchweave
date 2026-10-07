#!/usr/bin/env node
// privacy-screen.mjs — the outbound privacy gate for measurement reports (issue #420).
//
// The bench-measurer privacy contract says aggregates only: never DUT identifiers,
// operator/client names, bench names, captured protocol content, or query text.
// Until now that rule was enforced by prompt discipline alone. This tool makes the
// report itself pass a gate before it is delivered.
//
// Two layers, one direction of failure:
//   - Judgment layer (TypeSafe System One, one batched call): a Noul per hazard over
//     the report text. Code owns the threshold table — the model never decides policy.
//   - Fallback (judgment layer unavailable, TYPESAFE_DISABLE, timeout, any error):
//     a deterministic pattern screen for the mechanical identifier classes, and — this
//     is the whole design — a CLEAN fallback result is still REVIEW ("semantic screen
//     not run"), never PASS. No PASS verdict is reachable by defaulting through an
//     error path. Failing toward human eyes is the only allowed direction.
//
// Usage:
//   node .claude/hooks/privacy-screen.mjs report.md        # or stdin
//   node .claude/hooks/privacy-screen.mjs --json report.md
// Exit codes: 0 = PASS, 2 = REVIEW, 3 = BLOCK. Verdict, mode, and per-hazard detail
// print to stdout; nothing is written anywhere else.

import { readFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'
import { createClient, noulQuestion } from './lib/typesafe.mjs'

export const THRESHOLDS = { block: 0.85, review: 0.5 }

// One Noul per hazard. The classes are the bench-measurer contract verbatim; keep the
// two lists in step or the threshold table silently stops covering a hazard.
const HAZARDS = [
  {
    id: 'device_identifier',
    ask: 'Does this text contain a device identifier: a DUT serial number, asset tag, or a device model tied to a specific unit?',
    fallback: null,
  },
  {
    id: 'person_or_org',
    ask: 'Does this text name a person, operator, client, colleague, company, or employer — directly or by an identifier unique to them?',
    fallback: null,
  },
  {
    id: 'bench_or_site',
    ask: 'Does this text name a specific bench, laboratory, site, facility, or installation, as opposed to the generic "a real bench"?',
    fallback: null,
  },
  {
    id: 'protocol_content',
    ask: 'Does this text reproduce captured protocol content: raw frames, hex dumps, request/response bytes, or captured command transcripts?',
    fallback: null,
  },
  {
    id: 'query_text',
    ask: 'Does this text reproduce a raw query, search string, or document content from the measured corpus?',
    fallback: null,
  },
  {
    id: 'path_leak',
    ask: 'Does this text contain a filesystem path that identifies an operator machine, user account, or organization (a home directory or similar)?',
    fallback: null,
  },
]

// The deterministic classes the fallback CAN see. Mechanical, low-false-positive
// patterns only — anything needing semantics stays the judgment layer's job, and its
// absence is why a clean fallback is REVIEW.
const PATTERNS = [
  { id: 'email', re: /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, hazard: 'person_or_org', cls: 'block' },
  { id: 'home_path', re: /\/(?:Users|home)\/[A-Za-z0-9_.-]+/g, hazard: 'path_leak', cls: 'block' },
  { id: 'hex_dump', re: /(?:[0-9a-f]{2} ){8,}/gi, hazard: 'protocol_content', cls: 'block' },
  { id: 'mac', re: /\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\b/gi, hazard: 'device_identifier', cls: 'block' },
  { id: 'ipv4', re: /\b(?:\d{1,3}\.){3}\d{1,3}\b/g, hazard: 'bench_or_site', cls: 'block' },
  { id: 'serial_like', re: /\b(?:SN|S\/N|serial)[:#= ]+([A-Z0-9-]{6,})\b/gi, hazard: 'device_identifier', cls: 'review' },
]

/** Deterministic pattern scan. Returns [{id, hazard, cls, match}] — the classes it can see. */
export function fallbackScan(text) {
  const hits = []
  for (const p of PATTERNS) {
    p.re.lastIndex = 0
    let m
    while ((m = p.re.exec(text)) !== null) {
      hits.push({ id: p.id, hazard: p.hazard, cls: p.cls, match: m[0].slice(0, 80) })
      if (hits.length > 200) return hits // pathological input stays bounded
    }
  }
  return hits
}

/** Apply the threshold table to per-hazard probabilities. Policy lives here, in code. */
export function verdictFromHazards(probs) {
  const blocking = []
  const reviewing = []
  for (const [id, p] of Object.entries(probs)) {
    if (p >= THRESHOLDS.block) blocking.push(id)
    else if (p >= THRESHOLDS.review) reviewing.push(id)
  }
  const verdict = blocking.length ? 'BLOCK' : reviewing.length ? 'REVIEW' : 'PASS'
  return { verdict, blocking, reviewing }
}

/**
 * Screen report text. `client` is a TypeSafe client (createClient()) or any object
 * with a compatible ask(); tests inject fakes. Returns:
 *   { verdict: PASS|REVIEW|BLOCK, mode: model|fallback, hazards?, hits?, reason? }
 */
export async function screen(text, client) {
  const c = client || createClient()
  const questions = {}
  for (const h of HAZARDS) questions[h.id] = noulQuestion(h.ask)

  const r = await c.ask({ state: text, questions })
  if (r.ok) {
    const probs = {}
    for (const h of HAZARDS) {
      const a = r.answers[h.id]
      probs[h.id] = typeof a?.noul === 'number' ? a.noul : NaN
    }
    // A malformed answer for any hazard is an unavailable screen, not a clean one.
    if (Object.values(probs).some((p) => !Number.isFinite(p))) {
      return fallbackResult(text, 'invalid-answer')
    }
    const v = verdictFromHazards(probs)
    return { verdict: v.verdict, mode: 'model', hazards: probs, blocking: v.blocking, reviewing: v.reviewing }
  }
  return fallbackResult(text, r.reason)
}

function fallbackResult(text, reason) {
  const hits = fallbackScan(text)
  if (hits.some((h) => h.cls === 'block')) {
    return { verdict: 'BLOCK', mode: 'fallback', hits, reason: `judgment layer unavailable (${reason}); deterministic screen found mechanical identifiers` }
  }
  if (hits.length) {
    return { verdict: 'REVIEW', mode: 'fallback', hits, reason: `judgment layer unavailable (${reason}); deterministic screen found review-class matches` }
  }
  // The load-bearing line: clean deterministic + no semantic screen = human eyes.
  return {
    verdict: 'REVIEW',
    mode: 'fallback',
    hits: [],
    reason: `semantic screen not run (judgment layer unavailable: ${reason}) — human confirmation required`,
  }
}

// ---- CLI (guarded: importing this module for its exports must never read stdin) ----
const isMain = import.meta.url === pathToFileURL(process.argv[1] || '').href
if (isMain) {
  const args = process.argv.slice(2)
  const asJson = args.includes('--json')
  const file = args.find((a) => !a.startsWith('--'))
  const text = file ? readFileSync(file, 'utf8') : readFileSync(0, 'utf8')

  const result = await screen(text)
  if (asJson) {
    console.log(JSON.stringify(result, null, 2))
  } else {
    console.log(`privacy-screen: ${result.verdict} (${result.mode})`)
    if (result.reason) console.log(`  ${result.reason}`)
    for (const h of result.hits || []) console.log(`  [${h.cls}] ${h.id}: ${h.match}`)
    if (result.hazards) for (const [id, p] of Object.entries(result.hazards)) console.log(`  ${id}: ${p.toFixed(2)}`)
    if (result.blocking?.length) console.log(`  blocking: ${result.blocking.join(', ')}`)
    if (result.reviewing?.length) console.log(`  review: ${result.reviewing.join(', ')}`)
    process.exit(result.verdict === 'BLOCK' ? 3 : result.verdict === 'REVIEW' ? 2 : 0)
  }
}

