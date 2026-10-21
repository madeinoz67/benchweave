// R5 (2026-09-24 retro): the write-gate's own message promises
// "Worktree and branch-new files are exempt" and the CLAUDE.md routing card
// sends branch-new / untracked files to native Write — but the hook denied
// them (no trackedness check). These cases pin both directions.
// Issue #508 pins the gate's fail-open posture: unparseable input allows
// visibly (exit 0 + notice, not an accidental exit 1), missing file_path
// allows, and GORTEX_BIN is the first binary-resolution candidate.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync, existsSync, chmodSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..", "..", "..");
const HOOK = join(ROOT, ".claude", "hooks", "gortex-write-gate.mjs");

function runHookRaw(input, env) {
  return spawnSync(process.execPath, [HOOK], {
    input,
    encoding: "utf8",
    cwd: ROOT,
    ...(env ? { env } : {}),
  });
}

function runHook(filePath) {
  return runHookRaw(JSON.stringify({ tool_input: { file_path: filePath } }));
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

test("unparseable payload: a visible allow, not an accidental exit 1", () => {
  const r = runHookRaw("not-json");
  assert.equal(r.status, 0, `expected ALLOW for unparseable payload; stderr: ${r.stderr}`);
  assert.match(r.stderr || "", /unparseable payload/);
});

test("payload without file_path: allowed", () => {
  const r = runHookRaw(JSON.stringify({ tool_input: {} }));
  assert.equal(r.status, 0, `expected ALLOW for missing file_path; stderr: ${r.stderr}`);
  assert.doesNotMatch(r.stderr || "", /GortexWriteGate/);
});

test("GORTEX_BIN is honored: a 'does not track' stub allows a tracked primary file", () => {
  // The gortex arm is reached only for PRIMARY-checkout files (a linked
  // worktree exits earlier at the git-dir/common-dir check), so the probe
  // targets the primary: the clone itself, or the owning primary when this
  // suite runs from a .wt/ lane.
  const g = (args) => spawnSync("git", ["-C", ROOT, ...args], { encoding: "utf8" });
  const commonDirRaw = g(["rev-parse", "--git-common-dir"])?.stdout?.trim();
  assert.ok(commonDirRaw, "git rev-parse --git-common-dir returned nothing");
  const primaryTop = dirname(resolve(ROOT, commonDirRaw));
  const probe = join(primaryTop, "README.md");
  const tracked = spawnSync(
    "git",
    ["-C", primaryTop, "ls-files", "--error-unmatch", "--", "README.md"],
    { encoding: "utf8" },
  );
  assert.equal(tracked.status, 0, `probe ${probe} must be tracked for this test to measure the gortex arm`);
  const stubDir = mkdtempSync(join(tmpdir(), "wg-stub-"));
  const stub = join(stubDir, "gortex-stub");
  writeFileSync(stub, "#!/bin/sh\necho \"does not track\"\n");
  chmodSync(stub, 0o755);
  try {
    const r = runHookRaw(JSON.stringify({ tool_input: { file_path: probe } }), {
      ...process.env,
      GORTEX_BIN: stub,
    });
    assert.equal(r.status, 0, `expected ALLOW with the stub honored; stderr: ${r.stderr}`);
    assert.doesNotMatch(r.stderr || "", /GortexWriteGate/);
  } finally {
    rmSync(stubDir, { recursive: true, force: true });
  }
});
