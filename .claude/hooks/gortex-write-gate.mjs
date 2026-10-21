#!/usr/bin/env node
// GortexWriteGate — PreToolUse guard for Edit|Write|MultiEdit.
//
// Denies native file mutation inside a gortex-tracked PRIMARY checkout,
// routing to mcp__gortex__edit per the CLAUDE.md edit-routing card.
// Payload paths resolve through symlinks before the trackedness lookup.
// Allowed through: linked worktrees (the overlay caveat row), files with
// no git repo above them, and anything gortex does not track. No-ops
// (exit 0) whenever the gortex CLI, the daemon, or git is unavailable, so
// contributors without gortex are never blocked.
import { execFileSync } from "node:child_process";
import { relative } from "node:path";
import { readFileSync, realpathSync } from "node:fs";

// Resolution order (issue #508): an explicit GORTEX_BIN, then `gortex` on PATH
// (the resolution the `sh("git", …)` call below already relies on), then the
// Homebrew absolute path. The first candidate that returns a
// workspace-info-shaped answer wins; a candidate that cannot execute, errors,
// times out, or prints something that is not workspace info falls through to
// the next (fold F1: a wrong binary that merely succeeds — /bin/echo, a
// foreign PATH gortex — is not an answer).
const GORTEX_CANDIDATES = [
  process.env.GORTEX_BIN,
  "gortex",
  "/opt/homebrew/bin/gortex",
].filter(Boolean);
// Per-candidate budget and overall walk cap (fold F4 + the verdict-stability
// follow-up, both measured 2026-10-21): the deny must survive real load, not
// just idle speed. Measured on the dev machine (10 cores, parallel agent
// lanes): ambient load 34-53 — real daemon call p50 93ms, worst spike 1021ms
// (the load class that flipped verdicts at the first 500ms budget); a fork
// storm at load 67 still spawns an instant stub in <=303ms. Induced 2x-core
// storms push the real call to 3.5s-8s+ — beyond ANY walk cap under the
// pre-#508 single-hang cost, so storm-time deny is unreachable by budget and
// is a disclosed residual, not a tunable. Derivation: 1500ms per candidate
// = 1.5x the worst ambient spike and ~16x ambient p50; 3000ms overall walk
// cap = 43% under the measured 5.26s pre-#508 single-hang cost, and it binds
// only when earlier candidates consumed full slices (all-starved walks
// fail-open regardless). The git calls keep the 5s sh default: separate
// constant, separate call sites.
const GORTEX_CANDIDATE_TIMEOUT_MS = 1500;
const GORTEX_WALK_BUDGET_MS = 3000;
const ALLOW = 0;
const DENY = 2;

function sh(cmd, args, opts) {
  try {
    return execFileSync(cmd, args, {
      encoding: "utf8",
      timeout: 5000,
      stdio: ["ignore", "pipe", "ignore"],
      ...opts,
    });
  } catch {
    return null;
  }
}

// Workspace info, measured 2026-10-21, is a JSON object (members[].path
// naming the tracked checkout); the not-tracked answer carries the marker
// string the verdict arm already keys on. Both checks are cheap; anything
// else is treated as no answer.
function looksLikeWorkspaceInfo(out) {
  if (out.includes("does not track")) return true;
  try {
    JSON.parse(out);
    return true;
  } catch {
    return false;
  }
}

function gortexInfo(cwd) {
  const walkStart = Date.now();
  for (const bin of GORTEX_CANDIDATES) {
    const remaining = GORTEX_WALK_BUDGET_MS - (Date.now() - walkStart);
    if (remaining <= 0) return null;
    const out = sh(bin, ["call", "workspace", "--arg", "operation=info"], {
      cwd,
      timeout: Math.min(GORTEX_CANDIDATE_TIMEOUT_MS, remaining),
    });
    if (out !== null && looksLikeWorkspaceInfo(out)) return out;
  }
  return null;
}

let payload = "";
try {
  payload = readFileSync(0, "utf8");
} catch {
  process.exit(ALLOW);
}

// Unparseable payloads allow: exit 1 would be non-blocking (allow) anyway, but
// with a SyntaxError trace — this makes the fail-open posture deliberate and
// visible instead of accidental. Pinned by write-gate.test.mjs.
let input;
try {
  input = JSON.parse(payload || "{}");
} catch {
  console.error(
    "[GortexWriteGate] unparseable payload — allowing (fail-open by design, pinned by tests)",
  );
  process.exit(ALLOW);
}
let filePath = input?.tool_input?.file_path;
if (!filePath) process.exit(ALLOW);

// Resolve symlinks before every path-based decision (fold F3): a link at an
// untracked path aiming at a tracked file must reach the target's verdict.
// A path that does not resolve (branch-new files, dangling links) keeps its
// literal form — the untracked exemption below still applies. Real worktree
// paths resolve to themselves, so the worktree row is untouched.
try {
  filePath = realpathSync(filePath);
} catch {
  // keep the literal path
}

// The overlay rows: linked worktrees and git internals never take the
// gortex-edit path.
if (filePath.includes("/.claude/worktrees/") || filePath.includes("/.git/")) {
  process.exit(ALLOW);
}

const dir = filePath.replace(/\/[^/]*$/, "");
const toplevel = sh("git", ["-C", dir, "rev-parse", "--show-toplevel"])?.trim();
if (!toplevel) process.exit(ALLOW);

// Branch-new / untracked files are exempt (the routing card's native-Write
// row, and this gate's own message): the gate governs edits to gortex-indexed
// TRACKED source only. Proven by tests/write-gate.test.mjs (R5, 2026-09-24).
const rel = relative(toplevel, filePath);
const tracked = sh("git", ["-C", toplevel, "ls-files", "--error-unmatch", "--", rel]);
if (!tracked) process.exit(ALLOW);

// A linked worktree's git dir lives under the primary's .git/modules tree.
// Both rev-parses run from the toplevel so their renderings are comparable.
const gitDir = sh("git", ["-C", toplevel, "rev-parse", "--git-dir"])?.trim();
const commonDir = sh("git", ["-C", toplevel, "rev-parse", "--git-common-dir"])?.trim();
if (gitDir && commonDir && gitDir !== commonDir) process.exit(ALLOW);

const info = gortexInfo(toplevel);
if (!info || info.includes("does not track")) process.exit(ALLOW);
if (info.includes(`"${toplevel}"`)) {
  console.error(
    `[GortexWriteGate] ${filePath} is inside the gortex-tracked primary checkout ${toplevel}. ` +
      "Route through mcp__gortex__edit (change impact before, detect after) — " +
      "see the CLAUDE.md edit-routing card. Worktree and branch-new files are exempt.",
  );
  process.exit(DENY);
}
process.exit(ALLOW);
