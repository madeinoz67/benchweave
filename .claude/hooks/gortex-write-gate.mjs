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
// Per-candidate budget (fold F4): a healthy full-hook run measured ~0.22s
// wall (refute lane, 2026-10-21), so 500ms per candidate is over 2x the
// entire healthy run — generous for the real CLI while bounding the
// 3-candidate walk at <=1.5s (measured pre-fold: one hanging candidate
// 5.36s, two ~10.3s). The git calls below keep the 5s sh default: separate
// constant, separate call sites.
const GORTEX_CANDIDATE_TIMEOUT_MS = 500;
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
  for (const bin of GORTEX_CANDIDATES) {
    const out = sh(bin, ["call", "workspace", "--arg", "operation=info"], {
      cwd,
      timeout: GORTEX_CANDIDATE_TIMEOUT_MS,
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
