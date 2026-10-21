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
import { mkdtempSync, rmSync, writeFileSync, existsSync, chmodSync, symlinkSync } from "node:fs";
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

const gitAt = (args) => spawnSync("git", ["-C", ROOT, ...args], { encoding: "utf8" });

// The gortex arm is reached only for PRIMARY-checkout files (a linked worktree
// exits earlier at the git-dir/common-dir check), so probes target the
// primary: the clone itself, or the owning primary when this suite runs from
// a .wt/ lane.
function primaryToplevel() {
  const commonDirRaw = gitAt(["rev-parse", "--git-common-dir"])?.stdout?.trim();
  assert.ok(commonDirRaw, "git rev-parse --git-common-dir returned nothing");
  return dirname(resolve(ROOT, commonDirRaw));
}

function writeExecutable(file, body) {
  writeFileSync(file, body);
  chmodSync(file, 0o755);
}

// One-shot load belt (the timing lane's gen-1 pattern, applied to the node
// lane): this suite runs every hook-test file in parallel, and a synchronous
// fork under that load can exceed the 500ms per-candidate budget on an
// otherwise-instant stub — the mechanism's correct answer to a timed-out
// candidate is fall-through, so a starved run can yield the opposite verdict
// from a quiet host. Re-measure once on exactly the named load-noise
// signature; the pinned property must hold on the re-measure.
function beltRetry(run, isLoadNoise) {
  const first = run();
  if (!isLoadNoise(first)) return first;
  return run();
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
  const primaryTop = primaryToplevel();
  const probe = join(primaryTop, "README.md");
  const tracked = spawnSync(
    "git",
    ["-C", primaryTop, "ls-files", "--error-unmatch", "--", "README.md"],
    { encoding: "utf8" },
  );
  assert.equal(tracked.status, 0, `probe ${probe} must be tracked for this test to measure the gortex arm`);
  const stubDir = mkdtempSync(join(tmpdir(), "wg-stub-"));
  const stub = join(stubDir, "gortex-stub");
  writeExecutable(stub, "#!/bin/sh\necho \"does not track\"\n");
  try {
    const env = { ...process.env, GORTEX_BIN: stub };
    const payload = JSON.stringify({ tool_input: { file_path: probe } });
    // Load noise here: the allow-stub starved and a later real candidate
    // denied instead — the deny message is that signature.
    const r = beltRetry(
      () => runHookRaw(payload, env),
      (x) => x.status === 2 && /GortexWriteGate/.test(x.stderr || ""),
    );
    assert.equal(r.status, 0, `expected ALLOW with the stub honored; stderr: ${r.stderr}`);
    assert.doesNotMatch(r.stderr || "", /GortexWriteGate/);
  } finally {
    rmSync(stubDir, { recursive: true, force: true });
  }
});

test("F1 (deny pinned): output that is not workspace info is not an answer — a garbage GORTEX_BIN falls through to the next candidate", () => {
  // Decision pinned and why: a wrong binary that merely SUCCEEDS must not
  // satisfy the gate. The shape check (JSON-parseable, or the pre-existing
  // 'does not track' marker) is cheap and both forms are what the real CLI
  // emits — measured 2026-10-21, workspace info is a JSON object with
  // members[].path — so deny stays affordable: garbage falls through instead
  // of silently allowing (pre-fold, /bin/echo and a foreign PATH gortex both
  // allowed a tracked primary file).
  const primaryTop = primaryToplevel();
  const probe = join(primaryTop, "README.md");
  const stubDir = mkdtempSync(join(tmpdir(), "wg-f1-"));
  const pathStub = join(stubDir, "gortex");
  writeExecutable(pathStub, `#!/bin/sh\necho '{"members":[{"name":"stub","path":"${primaryTop}"}]}'\n`);
  try {
    const env = { ...process.env, GORTEX_BIN: "/bin/echo", PATH: `${stubDir}:${process.env.PATH}` };
    const payload = JSON.stringify({ tool_input: { file_path: probe } });
    // Load noise here: every candidate starved inside its 500ms budget, so
    // the walk fail-opened with no gate message — allow-with-no-stderr is
    // that signature.
    const r = beltRetry(
      () => runHookRaw(payload, env),
      (x) => x.status === 0 && !/GortexWriteGate/.test(x.stderr || ""),
    );
    assert.equal(r.status, 2, `expected DENY once the garbage candidate fell through; stderr: ${r.stderr}`);
    assert.match(r.stderr || "", /GortexWriteGate/);
  } finally {
    rmSync(stubDir, { recursive: true, force: true });
  }
});

test("F3: a symlink at an untracked path reaches its target's verdict (realpath before the trackedness lookup)", () => {
  // The linked-worktree row is untouched by this pin: real worktree paths
  // resolve to themselves and keep their exemption (the existing worktree
  // test above still guards that row).
  const primaryTop = primaryToplevel();
  const target = join(primaryTop, "README.md");
  const linkDir = mkdtempSync(join(tmpdir(), "wg-f3-"));
  const link = join(linkDir, "readme-link.md");
  symlinkSync(target, link);
  const stubDir = mkdtempSync(join(tmpdir(), "wg-f3-stub-"));
  const pathStub = join(stubDir, "gortex");
  writeExecutable(pathStub, `#!/bin/sh\necho '{"members":[{"name":"stub","path":"${primaryTop}"}]}'\n`);
  try {
    const env = { ...process.env, PATH: `${stubDir}:${process.env.PATH}` };
    // Load noise here (same signature as F1): every candidate starved inside
    // its 500ms budget and the walk fail-opened silently.
    const belted = (filePath) =>
      beltRetry(
        () => runHookRaw(JSON.stringify({ tool_input: { file_path: filePath } }), env),
        (x) => x.status === 0 && !/GortexWriteGate/.test(x.stderr || ""),
      );
    const viaTarget = belted(target);
    const viaLink = belted(link);
    assert.equal(viaTarget.status, 2, `control: target must DENY; stderr: ${viaTarget.stderr}`);
    assert.equal(viaLink.status, 2, `symlink must reach the target's verdict; stderr: ${viaLink.stderr}`);
    assert.match(viaLink.stderr || "", /GortexWriteGate/);
  } finally {
    rmSync(linkDir, { recursive: true, force: true });
    rmSync(stubDir, { recursive: true, force: true });
  }
});

test("F4: the candidate walk is bounded — a hanging candidate costs its per-candidate budget, not the 5s sh timeout", () => {
  // Budget: 500ms per gortex candidate. Why 500: the refute lane measured a
  // healthy full-hook run at ~0.22s wall, so 500ms per candidate is over 2x
  // the entire healthy run — generous for the real CLI, while bounding the
  // 3-candidate walk at <=1.5s instead of the measured 5.36s (one hanging
  // candidate) / ~10s (two). The git calls keep the 5s sh default: separate
  // constant, separate call sites.
  const primaryTop = primaryToplevel();
  const probe = join(primaryTop, "README.md");
  const stubDir = mkdtempSync(join(tmpdir(), "wg-f4-"));
  writeExecutable(join(stubDir, "hang-gortex-bin"), "#!/bin/sh\nsleep 10\n");
  writeExecutable(join(stubDir, "gortex"), "#!/bin/sh\nsleep 10\n");
  try {
    const measure = () => {
      const t0 = Date.now();
      const r = runHookRaw(JSON.stringify({ tool_input: { file_path: probe } }), {
        ...process.env,
        GORTEX_BIN: join(stubDir, "hang-gortex-bin"),
        PATH: `${stubDir}:${process.env.PATH}`,
      });
      return { r, wallMs: Date.now() - t0 };
    };
    // Load noise here: a wall past the ceiling (the fork pressure itself
    // stretched the non-hanging parts). RED pre-fold measured 10340ms.
    const { r, wallMs } = beltRetry(measure, (m) => m.wallMs >= 2500);
    assert.ok(r.status === 0 || r.status === 2, `verdict should still be reached, got ${r.status}`);
    // Assert ceiling 2500ms = the 1.5s walk cap plus <1s of host-dependent
    // extras measured on the dev machine (the surviving real brew candidate
    // ~0.2-0.6s, the git calls, node boot).
    assert.ok(wallMs < 2500, `candidate walk took ${wallMs}ms; expected < 2500ms with two hanging candidates at 500ms each`);
  } finally {
    rmSync(stubDir, { recursive: true, force: true });
  }
});
