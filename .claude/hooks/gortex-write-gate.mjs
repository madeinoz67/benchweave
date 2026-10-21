#!/usr/bin/env node
// GortexWriteGate — PreToolUse guard for Edit|Write|MultiEdit.
//
// Denies native file mutation inside a gortex-tracked PRIMARY checkout,
// routing to mcp__gortex__edit per the CLAUDE.md edit-routing card.
// Allowed through: linked worktrees (the overlay caveat row), files with
// no git repo above them, and anything gortex does not track. No-ops
// (exit 0) whenever the gortex CLI, the daemon, or git is unavailable, so
// contributors without gortex are never blocked.
import { execFileSync } from "node:child_process";
import { relative } from "node:path";
import { readFileSync } from "node:fs";

// Resolution order (issue #508): an explicit GORTEX_BIN, then `gortex` on PATH
// (the resolution the `sh("git", …)` call below already relies on), then the
// Homebrew absolute path. First candidate that returns output wins; a
// candidate that cannot execute (or errors) falls through to the next.
const GORTEX_CANDIDATES = [
  process.env.GORTEX_BIN,
  "gortex",
  "/opt/homebrew/bin/gortex",
].filter(Boolean);
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

function gortexInfo(cwd) {
  for (const bin of GORTEX_CANDIDATES) {
    const out = sh(bin, ["call", "workspace", "--arg", "operation=info"], { cwd });
    if (out !== null) return out;
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
const filePath = input?.tool_input?.file_path;
if (!filePath) process.exit(ALLOW);

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
