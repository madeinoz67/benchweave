// R5 (2026-09-24 retro): the write-gate's own message promises
// "Worktree and branch-new files are exempt" and the CLAUDE.md routing card
// sends branch-new / untracked files to native Write — but the hook denied
// them (no trackedness check). These cases pin both directions.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..", "..", "..");
const HOOK = join(ROOT, ".claude", "hooks", "gortex-write-gate.mjs");

function runHook(filePath) {
  return spawnSync(process.execPath, [HOOK], {
    input: JSON.stringify({ tool_input: { file_path: filePath } }),
    encoding: "utf8",
    cwd: ROOT,
  });
}

test("branch-new (untracked) file is exempt: native Write allowed", () => {
  const probe = join(ROOT, ".claude", "hooks", "tests", `.write-gate-probe-${process.pid}.txt`);
  assert.equal(existsSync(probe), false);
  writeFileSync(probe, "probe");
  try {
    const r = runHook(probe);
    assert.equal(r.status, 0, `expected ALLOW for untracked ${probe}; stderr: ${r.stderr}`);
    assert.doesNotMatch(r.stderr || "", /GortexWriteGate/);
  } finally {
    rmSync(probe, { force: true });
  }
});

test("tracked source: denied in the primary checkout, allowed in a linked worktree", () => {
  const tracked = join(ROOT, ".claude", "hooks", "gortex-write-gate.mjs");
  const r = runHook(tracked);
  // The gate exempts linked worktrees by design (git-dir differs from common dir —
  // the routing card's overlay row). Pin BOTH directions so the suite is honest in
  // a .wt/ lane AND in the primary/CI clone, instead of failing environmentally.
  const g = (args) => spawnSync("git", ["-C", ROOT, ...args], { encoding: "utf8" });
  const gitDir = g(["rev-parse", "--git-dir"])?.stdout?.trim();
  const commonDir = g(["rev-parse", "--git-common-dir"])?.stdout?.trim();
  const isLinkedWorktree = Boolean(gitDir && commonDir && gitDir !== commonDir);
  if (isLinkedWorktree) {
    assert.equal(r.status, 0, "expected ALLOW for a tracked file inside a linked worktree");
    assert.doesNotMatch(r.stderr || "", /GortexWriteGate/);
  } else {
    assert.notEqual(r.status, 0, "expected DENY for a tracked file in the gortex-tracked checkout");
    assert.match(r.stderr || "", /GortexWriteGate/);
  }
});

test("files outside the repo are allowed", () => {
  const outside = join(mkdtempSync(join(tmpdir(), "wg-")), "x.md");
  writeFileSync(outside, "x");
  try {
    const r = runHook(outside);
    assert.equal(r.status, 0, `expected ALLOW outside the repo; stderr: ${r.stderr}`);
  } finally {
    rmSync(dirname(outside), { recursive: true, force: true });
  }
});
