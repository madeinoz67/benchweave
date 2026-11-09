#!/usr/bin/env node
// session-preflight.mjs — SessionStart facts for the two traps only a session start can
// catch: a stale checkout and an unmaterialised SDK submodule. Design
// `.claude/deep-review/2026-11-09-459-release-preflight-design.md` §5 (slice 2 of #459).
//
// Both traps cost real hours the night this was designed: a design pass ran against a
// primary 33 commits behind origin/main (CLAUDE.md §3.1 is discipline only, and it failed
// twice in one night), and a fresh worktree reddened bare mypy with "Cannot read file
// packages/sdk/src", which reads like a code failure and is not one.
//
// Posture copied from drift-guard: WARNS, never blocks — always exit 0, silent when
// everything holds. Deliberately says nothing about venv or path configuration
// (owner-machine specifics stay out of the repo) and nothing about gortex state.

import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

const FETCH_TIMEOUT_MS = 5000

function git(cwd, args, timeout) {
  try {
    return spawnSync('git', ['-C', cwd, ...args], {
      encoding: 'utf-8',
      ...(timeout ? { timeout } : {}),
    })
  } catch {
    return null
  }
}

// F3 — the submodule trap. Only fires when this checkout actually declares the submodule
// and its sources are absent, so a repository without one stays silent.
function submoduleUnmaterialised(cwd) {
  try {
    if (!readFileSync(join(cwd, '.gitmodules'), 'utf-8').includes('packages/sdk')) return false
  } catch {
    return false
  }
  return !existsSync(join(cwd, 'packages', 'sdk', 'src'))
}

// F2 — the stale-checkout trap. Best-effort by design: the fetch is capped and its failure
// degrades to counting against the last-fetched ref, disclosed in the warning rather than
// swallowed. A checkout with no origin/main at all says nothing.
function behindOrigin(cwd) {
  const fetch = git(cwd, ['fetch', 'origin'], FETCH_TIMEOUT_MS)
  const fetched = fetch !== null && fetch.status === 0

  const count = git(cwd, ['rev-list', '--count', 'HEAD..origin/main'])
  if (count === null || count.status !== 0) return null
  const behind = Number(count.stdout.trim())
  if (!Number.isFinite(behind) || behind <= 0) return null

  const head = git(cwd, ['rev-parse', '--short', 'HEAD'])
  const origin = git(cwd, ['rev-parse', '--short', 'origin/main'])
  const headSha = head?.status === 0 ? head.stdout.trim() : 'unknown'
  const originSha = origin?.status === 0 ? origin.stdout.trim() : 'unknown'

  const lines = [
    `**[Pre-flight] This checkout is ${behind} commit${behind === 1 ? '' : 's'} behind origin/main**`,
    '',
    `HEAD \`${headSha}\` vs origin/main \`${originSha}\`. Confirm the commit before you assert`,
    'what the code does, and re-verify any design work done on this tree (CLAUDE.md §3.1).',
  ]
  if (!fetched) {
    lines.push(
      '',
      '`git fetch origin` failed here, so this count is against the last-fetched refs and may',
      'understate the gap.',
    )
  }
  return lines.join('\n')
}

try {
  const input = JSON.parse(await readStdin())
  const cwd = input?.cwd || process.cwd()

  const notes = []
  if (submoduleUnmaterialised(cwd)) {
    notes.push(
      [
        '**[Pre-flight] `packages/sdk` is not materialized in this checkout**',
        '',
        'Run `git submodule update --init packages/sdk`. Until then bare `uv run mypy` exits 2',
        "with \"Cannot read file packages/sdk/src\", which reads like a code failure and is not",
        'one — a fresh worktree does not initialise submodules.',
      ].join('\n'),
    )
  }
  const behind = behindOrigin(cwd)
  if (behind !== null) notes.push(behind)

  if (notes.length) {
    process.stdout.write(
      JSON.stringify({
        hookSpecificOutput: {
          hookEventName: 'SessionStart',
          additionalContext: notes.join('\n\n---\n\n'),
        },
      }),
    )
  }
} catch {
  // Swallow. A session that cannot start is worse than a missed nudge.
}
process.exit(0)

async function readStdin() {
  const chunks = []
  for await (const chunk of process.stdin) chunks.push(chunk)
  return Buffer.concat(chunks).toString('utf-8') || '{}'
}
