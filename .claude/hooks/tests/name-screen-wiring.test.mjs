// name-screen-wiring.test.mjs — the three wirings of the name screen (issue
// #518; design record §3): the PreToolUse settings entry, the .githooks/
// pre-commit + pre-push pair (installed by `make hooks`) with their chain
// shims, and the CI job's diff pipeline. The 36 pre-committed planted blocks
// are proven HERE through the real hook scripts — an exit 127 from a missing
// script is NOT a block, so every planted case must show "name-screen: BLOCK"
// in the output to count.
//
// CANARY DISCIPLINE: same as name-screen.test.mjs — invented names only, and
// the tier-P shapes are assembled so this file's own bytes stay green.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync, chmodSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..", "..", "..");
const HOOKS = join(ROOT, ".githooks");
const SCREEN = join(ROOT, ".claude", "hooks", "name-screen.mjs");

const PLANTED = [
  "Zorblat", "Quimbrel", "Brindlestack", "Vorpane", "Tessilune", "Grovmark",
  "Palexion", "Dravemont", "Ullquor", "Ostrevan", "Nimbrelfour", "Chalkvane",
];
const TALLY = { wiringBlocked: 0 };

function tmp() {
  return mkdtempSync(join(tmpdir(), "ns-wiring-"));
}

function assertNoLeak(out, needles) {
  for (const n of needles) assert.ok(!out.includes(n), `hook output leaked a canary "${n.slice(0, 4)}…"`);
}

// A temp git repo whose .githooks/ entries forward to the real committed
// scripts (which self-locate the screen). Tests invoke the temp copies the
// way git would (cwd = repo top).
function gitRepo(listPath) {
  const d = tmp();
  mkdirSync(join(d, ".githooks"), { recursive: true });
  for (const h of ["pre-commit", "pre-push", "post-commit", "post-merge"]) {
    writeFileSync(join(d, ".githooks", h), `#!/bin/sh\nexec sh ${JSON.stringify(join(HOOKS, h))} "$@"\n`);
    chmodSync(join(d, ".githooks", h), 0o755);
  }
  const env = { ...process.env, BENCHWEAVE_NAME_LIST: listPath };
  const g = (args) => spawnSync("git", ["-C", d, ...args], { encoding: "utf8", env });
  const hook = (name, input = "") =>
    spawnSync("sh", [join(d, ".githooks", name)], { input, encoding: "utf8", cwd: d, env });
  g(["init", "-q"]);
  g(["config", "user.email", "probe@example.test"]);
  g(["config", "user.name", "probe"]);
  g(["config", "commit.gpgsign", "false"]);
  writeFileSync(join(d, "seed.txt"), "seed\n");
  g(["add", "."]);
  g(["commit", "-q", "-m", "seed"]);
  return { d, g, hook, env };
}

function writeList(d) {
  const p = join(d, "name-screen.list");
  writeFileSync(p, PLANTED.join("\n") + "\n");
  return p;
}

// ---- wiring presence ------------------------------------------------------------

test("settings.json carries the second PreToolUse entry (name-screen --pretooluse)", () => {
  const s = JSON.parse(readFileSync(join(ROOT, ".claude", "settings.json"), "utf8"));
  const pre = s.hooks?.PreToolUse ?? [];
  const entry = pre.find((e) => e.matcher === "Edit|Write|MultiEdit" && e.hooks?.some((h) => /name-screen\.mjs/.test(h.command || "") && /--pretooluse/.test(h.command || "")));
  assert.ok(entry, "no PreToolUse Edit|Write|MultiEdit entry runs name-screen.mjs --pretooluse");
  const gortex = pre.find((e) => e.hooks?.some((h) => /gortex-write-gate/.test(h.command || "")));
  assert.ok(gortex, "the gortex-write-gate entry must survive — name-screen is a SECOND entry, not a replacement");
});

test("ci.yml carries the name-screen job over the added-lines diff", () => {
  const y = readFileSync(join(ROOT, ".github", "workflows", "ci.yml"), "utf8");
  assert.match(y, /^  name-screen:/m, "no name-screen job");
  assert.match(y, /name-screen\.mjs --diff/, "the job does not pipe the diff into the screen");
  assert.match(y, /github\.event_name != 'schedule'/, "the job must guard out of the weekly schedule run");
});

test("make -n hooks shows the core.hooksPath install and changes nothing", () => {
  const before = spawnSync("git", ["config", "--local", "core.hooksPath"], { encoding: "utf8", cwd: ROOT }).stdout;
  const r = spawnSync("make", ["-n", "hooks"], { encoding: "utf8", cwd: ROOT });
  assert.equal(r.status, 0, `make -n hooks failed: ${r.stderr}`);
  const out = r.stdout;
  assert.match(out, /git config core\.hooksPath \.githooks/, "dry run does not set core.hooksPath");
  assert.match(out, /chmod \+x/, "dry run does not chmod the hooks");
  const after = spawnSync("git", ["config", "--local", "core.hooksPath"], { encoding: "utf8", cwd: ROOT }).stdout;
  assert.equal(after, before, "make -n MUTATED the config — the test itself must stay dry");
});

// ---- git hook surfaces (the pre-committed 36 through the real scripts) ------------

test("pre-commit/pre-push: all 36 planted cases BLOCK through the real hook scripts", () => {
  const d = tmp();
  try {
    const list = writeList(d);
    for (const name of PLANTED) {
      const repo = gitRepo(list);
      try {
        // surface 1 of 3: staged content
        writeFileSync(join(repo.d, "notes.md"), `run history for ${name}\n`);
        repo.g(["add", "notes.md"]);
        let r = repo.hook("pre-commit");
        let out = r.stdout + r.stderr;
        if (r.status !== 0 && /name-screen: BLOCK/.test(out)) TALLY.wiringBlocked++;
        assert.ok(r.status !== 0 && /name-screen: BLOCK/.test(out), `staged content not blocked: ${name.slice(0, 3)}\n${out}`);
        assertNoLeak(out, PLANTED);

        // surface 2 of 3: commit message, screened at the push boundary
        repo.g(["reset", "-q"]);
        writeFileSync(join(repo.d, "clean.md"), "clean\n");
        repo.g(["add", "clean.md"]);
        repo.g(["commit", "-q", "-m", `bench: notes from ${name}`]);
        const head = repo.g(["rev-parse", "HEAD"]).stdout.trim();
        const parent = repo.g(["rev-parse", "HEAD^"]).stdout.trim();
        r = repo.hook("pre-push", `refs/heads/main ${head} refs/heads/main ${parent}\n`);
        out = r.stdout + r.stderr;
        if (r.status !== 0 && /name-screen: BLOCK/.test(out)) TALLY.wiringBlocked++;
        assert.ok(r.status !== 0 && /name-screen: BLOCK/.test(out), `commit message not blocked: ${name.slice(0, 3)}\n${out}`);
        assertNoLeak(out, PLANTED);

        // surface 3 of 3: staged filename
        const probe = join(repo.d, `${name.toLowerCase()}-rig.md`);
        writeFileSync(probe, "clean content\n");
        repo.g(["add", probe]);
        r = repo.hook("pre-commit");
        out = r.stdout + r.stderr;
        if (r.status !== 0 && /name-screen: BLOCK/.test(out)) TALLY.wiringBlocked++;
        assert.ok(r.status !== 0 && /name-screen: BLOCK/.test(out), `filename not blocked: ${name.slice(0, 3)}\n${out}`);
        assert.match(out, /surface=filename/);
        assertNoLeak(out, PLANTED);
      } finally {
        rmSync(repo.d, { recursive: true, force: true });
      }
    }
  } finally {
    rmSync(d, { recursive: true, force: true });
  }
});

test("clean content passes both hooks (no false block on ordinary work)", () => {
  const d = tmp();
  try {
    const list = writeList(d);
    const repo = gitRepo(list);
    try {
      writeFileSync(join(repo.d, "notes.md"), "ordinary notes about a real bench\n");
      repo.g(["add", "notes.md"]);
      let r = repo.hook("pre-commit");
      assert.equal(r.status, 0, `false block on clean staged content\n${r.stdout}${r.stderr}`);

      repo.g(["commit", "-q", "-m", "bench: ordinary work"]);
      const head = repo.g(["rev-parse", "HEAD"]).stdout.trim();
      const parent = repo.g(["rev-parse", "HEAD^"]).stdout.trim();
      r = repo.hook("pre-push", `refs/heads/main ${head} refs/heads/main ${parent}\n`);
      assert.equal(r.status, 0, `false block on clean push\n${r.stdout}${r.stderr}`);

      // a deletion push (local sha all zeros) carries nothing new: skipped
      const zero = "0".repeat(40);
      r = repo.hook("pre-push", `refs/heads/main ${zero} refs/heads/main ${head}\n`);
      assert.equal(r.status, 0, `deletion push not skipped\n${r.stdout}${r.stderr}`);
    } finally {
      rmSync(repo.d, { recursive: true, force: true });
    }
  } finally {
    rmSync(d, { recursive: true, force: true });
  }
});

test("push-range added-line diff blocks (the CI pipeline's exact shape)", () => {
  const d = tmp();
  try {
    const list = writeList(d);
    const repo = gitRepo(list);
    try {
      const clean = repo.g(["rev-parse", "HEAD"]).stdout.trim();
      writeFileSync(join(repo.d, "later.md"), `worked with ${PLANTED[4]}\n`);
      repo.g(["add", "later.md"]);
      repo.g(["commit", "-q", "-m", "later"]);
      const tip = repo.g(["rev-parse", "HEAD"]).stdout.trim();
      // exactly the pipeline the CI job runs (design §3.3)
      const diff = spawnSync("git", ["-C", repo.d, "diff", "--no-renames", "--unified=0", "--diff-filter=ACM", `${clean}...${tip}`], { encoding: "utf8", env: repo.env });
      const screen = spawnSync(process.execPath, [SCREEN, "--diff"], { input: diff.stdout, encoding: "utf8", cwd: ROOT, env: repo.env });
      assert.equal(screen.status, 3, `planted added line did not block\n${screen.stdout}${screen.stderr}`);
      assertNoLeak(screen.stdout + screen.stderr, PLANTED);
      // and the GREEN half: the same pipeline over the clean range passes
      const cleanDiff = spawnSync("git", ["-C", repo.d, "diff", "--no-renames", "--unified=0", "--diff-filter=ACM", `${clean}...${clean}`], { encoding: "utf8", env: repo.env });
      const pass = spawnSync(process.execPath, [SCREEN, "--diff"], { input: cleanDiff.stdout, encoding: "utf8", cwd: ROOT, env: repo.env });
      assert.equal(pass.status, 0, `clean diff blocked\n${pass.stdout}${pass.stderr}`);
    } finally {
      rmSync(repo.d, { recursive: true, force: true });
    }
  } finally {
    rmSync(d, { recursive: true, force: true });
  }
});

// ---- chain shims ------------------------------------------------------------------

test("chain shims forward post-commit/post-merge to a global hooksPath (hermetic HOME)", () => {
  const home = tmp();
  const repo = tmp();
  try {
    const globalHooks = join(home, "githooks");
    mkdirSync(globalHooks, { recursive: true });
    for (const h of ["post-commit", "post-merge"]) {
      writeFileSync(join(globalHooks, h), `#!/bin/sh\necho "${h}-ran" >> "${join(home, "marker")}"\n`);
      chmodSync(join(globalHooks, h), 0o755);
    }
    // EVERY git call here runs under the overridden HOME — a stray call that
    // resolves the real HOME would read or write the operator's own global
    // config, which this suite must never touch.
    const env = { ...process.env, HOME: home };
    const g = (args) => spawnSync("git", ["-C", repo, ...args], { encoding: "utf8", env });
    g(["init", "-q"]);
    g(["config", "--global", "--add", "core.hooksPath", globalHooks]); // scoped by HOME override
    let r = spawnSync("sh", [join(HOOKS, "post-commit")], { encoding: "utf8", cwd: repo, env });
    assert.equal(r.status, 0, `shim failed: ${r.stderr}`);
    r = spawnSync("sh", [join(HOOKS, "post-merge")], { encoding: "utf8", cwd: repo, env });
    assert.equal(r.status, 0, `shim failed: ${r.stderr}`);
    const marker = readFileSync(join(home, "marker"), "utf8");
    assert.match(marker, /post-commit-ran/);
    assert.match(marker, /post-merge-ran/);

    // no global hooksPath configured -> the shim exits 0 and runs nothing
    const bareHome = tmp();
    try {
      const env2 = { ...process.env, HOME: bareHome };
      const r2 = spawnSync("sh", [join(HOOKS, "post-commit")], { encoding: "utf8", cwd: repo, env: env2 });
      assert.equal(r2.status, 0, `shim must exit 0 without a global hooksPath: ${r2.stderr}`);
    } finally {
      rmSync(bareHome, { recursive: true, force: true });
    }
  } finally {
    rmSync(home, { recursive: true, force: true });
    rmSync(repo, { recursive: true, force: true });
  }
});

test("wiring tally — 36/36 through the hooks (a zero is INVALID, not a pass)", () => {
  assert.equal(TALLY.wiringBlocked, 36, `wiring-level planted blocks: ${TALLY.wiringBlocked}/36 — under 36 kills (design §7)`);
});
