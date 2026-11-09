#!/usr/bin/env node
// session-preflight.mjs — SessionStart facts for the two traps only a session start can catch:
// a stale checkout and an unmaterialised SDK submodule. Design
// `.claude/deep-review/2026-11-09-459-release-preflight-design.md` §5 (slice 2 of #459).
//
// Both traps cost real hours the night this was designed: a design pass ran against a primary
// 33 commits behind origin/main (CLAUDE.md §3.1 is discipline only, and it failed twice in one
// night), and a fresh worktree reddened bare mypy with an error that reads like a code failure
// and is not one.
//
// §8 of that design pre-committed a kill line for this slice: "wall time ≥5 s after the
// degrade path engages → drop the fetch step (last-fetched-refs mode) and re-measure". A
// refute pass measured a blackholed origin at 5.175 s, so the fetch is GONE: this hook never
// touches the network. It reads only remote-tracking refs that already exist, which also
// means it no longer mutates the user's repo on every setup — a fetch is a write, and it was
// fast-forwarding shared `origin/*` refs and `FETCH_HEAD` from whichever worktree the session
// happened to start in.
//
// Posture copied from drift-guard: WARNS, never blocks — always exit 0, silent when everything
// holds. Deliberately says nothing about venv or path configuration (owner-machine specifics
// stay out of the repo) and nothing about gortex state.

import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

// Every git call is bounded. Only the fetch used to carry a timeout, so a git that blocked on
// anything else (a stale network mount, a wrapper, an FS lock) held the session start until
// the harness killed it.
const GIT_TIMEOUT_MS = 2000

function git(cwd, args) {
  try {
    const res = spawnSync('git', ['-C', cwd, ...args], {
      encoding: 'utf-8',
      timeout: GIT_TIMEOUT_MS,
    })
    return res.status === 0 ? res.stdout.trim() : null
  } catch {
    return null
  }
}

// `git rev-parse` resolves a session started in `src/benchweave`; reading `.gitmodules` from
// the raw cwd does not. Reading the raw cwd silently disabled the submodule half of this hook
// for any session started in a subdirectory, while the behind-count kept working — so the
// hook looked alive.
function checkoutRoot(cwd) {
  return git(cwd, ['rev-parse', '--show-toplevel']) ?? cwd
}

// The branch's own upstream when it has one (a fork whose canonical remote is `upstream`, or a
// default branch that is not `main`), falling back to `origin/main`. Both spellings were
// hardcoded before, so such a clone was silent forever with no sign the check had not run.
function upstreamRef(root) {
  return (
    git(root, ['rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}']) ?? 'origin/main'
  )
}

function behindUpstream(root) {
  const upstream = upstreamRef(root)
  const count = git(root, ['rev-list', '--count', `HEAD..${upstream}`])
  if (count === null) return null
  const behind = Number(count)
  if (!Number.isFinite(behind) || behind <= 0) return null

  const head = git(root, ['rev-parse', '--short', 'HEAD']) ?? 'unknown'
  const remote = git(root, ['rev-parse', '--short', upstream]) ?? 'unknown'
  return [
    `**[Pre-flight] This checkout is ${behind} commit${behind === 1 ? '' : 's'} behind ${upstream}**`,
    '',
    `HEAD \`${head}\` vs ${upstream} \`${remote}\`, counted against the last-fetched refs — this`,
    'hook does not fetch. Confirm the commit before you assert what the code does and re-verify',
    'any design work done here (CLAUDE.md §3.1). A remote-tracking ref that is itself stale, or',
    'one whose branch was deleted upstream, makes this count wrong in either direction.',
  ].join('\n')
}

// The submodule this checkout registers, matched on its `.gitmodules` PATH entry. Matching the
// file as a substring fired on a URL that merely mentioned the path and on a longer sibling
// name, and the remedy those warnings printed then failed with "pathspec did not match".
const SUBMODULE_PATH = 'packages/sdk'

function declaresSubmodule(root) {
  let text
  try {
    text = readFileSync(join(root, '.gitmodules'), 'utf-8')
  } catch {
    return false
  }
  // git accepts `path = x`, `path=x` and `path = "x"` as the same registration. Requiring the
  // canonical spacing left a hand-edited or tool-generated `.gitmodules` silent — the bad
  // direction for a guard, since the submodule it names is genuinely uninitialised.
  return text.split('\n').some((line) => {
    const match = /^\s*path\s*=\s*(.+)$/.exec(line)
    if (match === null) return false
    return match[1].trim().replace(/^"(.*)"$/, '$1') === SUBMODULE_PATH
  })
}

function submoduleNote(root) {
  if (!declaresSubmodule(root)) return null
  // `git submodule status` is the authority, not the absence of a directory: a leading `-`
  // means registered-but-not-initialised, which is exactly the state `update --init` fixes.
  // A submodule that IS checked out but has no `src/` is a different fault, and telling its
  // owner to run `update --init` is advice that changes nothing while repeating every session.
  const status = git(root, ['submodule', 'status', '--', SUBMODULE_PATH])
  if (status === null) return null
  const line = status.split('\n').find((candidate) => candidate.includes(SUBMODULE_PATH))
  if (line === undefined) return null

  if (line.trim().startsWith('-')) {
    return [
      '**[Pre-flight] `packages/sdk` is not initialized in this checkout**',
      '',
      'Run `git submodule update --init packages/sdk`. Until then bare `uv run mypy` exits 2 with',
      '`packages/sdk/src: error: Cannot read file: No such file or directory`, which reads like a',
      'code failure and is not one — a fresh worktree does not initialize submodules.',
    ].join('\n')
  }
  if (existsSync(join(root, SUBMODULE_PATH, 'src'))) return null

  const sha = line.trim().split(/\s+/)[0] ?? 'unknown'
  return [
    '**[Pre-flight] `packages/sdk` is checked out but carries no `src/`**',
    '',
    `The submodule working tree exists at \`${sha.slice(0, 10)}\` without the sources its pin has, so`,
    'this is a working tree that does not match its pin rather than one that was never',
    'initialized. `git submodule update --init` will change nothing; run',
    `\`git submodule update ${SUBMODULE_PATH}\` and re-check.`,
  ].join('\n')
}

try {
  const input = JSON.parse(await readStdin())
  const cwd = input?.cwd || process.cwd()
  const root = checkoutRoot(cwd)

  const notes = []
  const submodule = submoduleNote(root)
  if (submodule !== null) notes.push(submodule)
  const behind = behindUpstream(root)
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
