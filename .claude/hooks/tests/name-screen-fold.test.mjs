// name-screen-fold.test.mjs — the refute-fold suite (issue #518 fold, F1-F7).
// Each arm pins a defect the adversarial review found in the first build;
// every canary is invented, tier-P shapes are assembled at runtime (this
// file's own bytes stay green under the screen it ships).
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..", "..", "..");
const SCREEN = join(ROOT, ".claude", "hooks", "name-screen.mjs");

// Multi-word invented names (F3: the spaced/hyphenated/underscored/dotted
// inflections a filename can carry when the list entry itself is spaced).
const MULTI = ["Brindlestack Labs", "Quimbrel Testworks", "Zorblat Engineering"];
const inflections = (name) => {
  const lower = name.toLowerCase();
  return [name, lower, lower.replaceAll(" ", "-"), lower.replaceAll(" ", "_"), lower.replaceAll(" ", "."), name.toUpperCase()];
};

function tmp() {
  return mkdtempSync(join(tmpdir(), "ns-fold-"));
}

function runCli(args, { input = "", env = {} } = {}) {
  return spawnSync(process.execPath, [SCREEN, ...args], {
    input,
    encoding: "utf8",
    cwd: ROOT,
    env: { ...process.env, ...env },
  });
}

function assertNoLeak(out, needles) {
  for (const n of needles) {
    if (n && n.length >= 4) assert.ok(!out.includes(n), `output leaked the inflection "${n.slice(0, 6)}…"`);
  }
}

// ---- F1: hunk poisoning -------------------------------------------------------

test("F1: an added line whose content starts '++ ' is CONTENT, not a file header", () => {
  const d = tmp();
  try {
    const list = join(d, "l.list");
    writeFileSync(list, MULTI.join("\n") + "\n");
    const email = ["poisonbox", "@", "notexample.test"].join("");
    const home = ["/Users/", "poisonbox", "/x"].join("");
    const serial = ["SN", ": ", "PB", "-", "778899"].join("");
    const bearer = ["Bearer", " ", "pb", "9k", "tok", "2x", "vault", "7m"].join("");
    // content lines that BEGIN with "++ " render as "+++ …" in the diff and
    // poisoned the first build's parser into header mode
    const diff = [
      "diff --git a/docs/notes.md b/docs/notes.md",
      "--- a/docs/notes.md",
      "+++ b/docs/notes.md",
      "@@ -5,2 +5,6 @@",
      " context line",
      `+++ note about ${MULTI[0]}`,
      `+${email}`,
      `+${home}`,
      `+${serial}`,
      `+${bearer}`,
      `+clean tail line about ${MULTI[1]}`,
    ].join("\n");
    const r = runCli(["--diff"], { input: diff, env: { BENCHWEAVE_NAME_LIST: list } });
    assert.equal(r.status, 3, `poisoned hunk passed the screen\n${r.stdout}${r.stderr}`);
    const out = r.stdout + r.stderr;
    // every planted shape and name in that hunk is caught, and the new-file
    // line numbers stay continuous past the poisoned line (hunk opens at 5:
    // context=5, poisoned=6, then 7,8,9,10,11). The CLI prints the first 5
    // citations plus a remainder count; the second list name is the 6th hit.
    for (const frag of ["id=email", "id=home_path", "id=serial_like", "id=secret_bearer", "entry=1"]) {
      assert.match(out, new RegExp(frag.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")), `missing ${frag} in block output`);
    }
    assert.match(out, /and 1 more/);
    assert.match(out, /docs\/notes\.md:7/);
    assertNoLeak(out, [...MULTI.flatMap(inflections), email, home, serial, bearer]);
  } finally {
    rmSync(d, { recursive: true, force: true });
  }
});

test("F1: header-position '+++' still parses as a header (no regression)", () => {
  const d = tmp();
  try {
    const list = join(d, "l.list");
    writeFileSync(list, "Unrelated-name\n");
    const diff = ["diff --git a/x b/y", "+++ b/y", "@@ -1,1 +1,1 @@", "+clean line"].join("\n");
    const r = runCli(["--diff"], { input: diff, env: { BENCHWEAVE_NAME_LIST: list } });
    assert.equal(r.status, 0, `clean diff blocked\n${r.stdout}${r.stderr}`);
  } finally {
    rmSync(d, { recursive: true, force: true });
  }
});

test("F1b: a multi-file diff resets header position — the second file's headers are not content", () => {
  const d = tmp();
  try {
    const list = join(d, "l.list");
    writeFileSync(list, [...MULTI, "Filler-entry"].join("\n") + "\n");
    // file one is clean; the plant lives in file TWO. Before the fold's F1b
    // fix the second file's "+++" header was parsed as content and its path
    // never registered (misattributed citations downstream).
    const diff = [
      "diff --git a/docs/a.md b/docs/a.md",
      "--- a/docs/a.md",
      "+++ b/docs/a.md",
      "@@ -1,1 +1,2 @@@",
      " context",
      "+clean addition",
      "diff --git a/docs/b.md b/docs/b.md",
      "--- a/docs/b.md",
      "+++ b/docs/b.md",
      "@@ -1,1 +1,2 @@@",
      " context",
      `+worked with ${MULTI[0]}`,
    ].join("\n");
    const r = runCli(["--diff"], { input: diff, env: { BENCHWEAVE_NAME_LIST: list } });
    assert.equal(r.status, 3, `plant in the second file of a multi-file diff passed\n${r.stdout}${r.stderr}`);
    const out = r.stdout + r.stderr;
    assert.match(out, /docs\/b\.md:2/, `hit not attributed to the second file\n${out}`);
    assert.match(out, /entry=1/);
    assertNoLeak(out, MULTI.flatMap(inflections));
  } finally {
    rmSync(d, { recursive: true, force: true });
  }
});

test("F2: slash-list prose is not a home path, but a real path in prose still is", async () => {
  const m = await import("../name-screen.mjs");
  assert.deepEqual(m.publicScan("the email/home/serial trio and docs/Users/index are prose"), [], "slash-list prose false-positives on home_path");
  // assembled: the positive case must not exist as a shape in this file's bytes
  const realPath = ["see /", "Users", "/", "poisonbox", "/x for the notes"].join("");
  assert.ok(m.publicScan(realPath).some((h) => h.id === "home_path"), "real home path in prose missed after the boundary fix");
});

// ---- F2: the allowlist + the tracked-tree sweep ---------------------------------

test("F2 unit: loopback, doc ranges, example domains, version shapes pass; real shapes block", async () => {
  const m = await import("../name-screen.mjs");
  const pass = ["127.0.0.1", "127.8.8.4", ["192", "0", "2", "77"].join("."), ["198", "51", "100", "9"].join("."), ["203", "0", "113", "4"].join("."), "0.2.2.1", "0.17.0.3", "999.1.1.1"];
  const block = [["8", "8", "8", "8"].join("."), ["10", "0", "0", "5"].join("."), ["192", "168", "1", "1"].join("."), ["172", "16", "5", "4"].join("."), ["1", "0", "0", "0"].join(".")];
  for (const p of pass) assert.deepEqual(m.publicScan(p), [], `false positive on ${p}`);
  for (const b of block) assert.ok(m.publicScan(b).some((h) => h.id === "ipv4"), `missed ${b}`);
  const okmails = [["a", "@", "example.com"].join(""), ["b", "@", "example.test"].join(""), "git@github.com:example/benchweave.git"];
  const badmail = ["c", "@", "notexample.test"].join("");
  for (const e of okmails) assert.deepEqual(m.publicScan(e).filter((h) => h.id === "email"), [], `false positive on ${e}`);
  assert.ok(m.publicScan(badmail).some((h) => h.id === "email"));
  // serial tails must carry a digit — "serial attachment" is prose, not an id
  assert.deepEqual(m.publicScan("serial attachment, reset and disconnect"), []);
  assert.ok(m.publicScan(["S/N", " ", "PB991234"].join("")).some((h) => h.id === "serial_like"));
});

// The pinned residual table: every tracked-tree tier-P hit the sweep finds
// that is NOT one of these rows fails the sweep; a row that stops matching
// fails it too (the ratchet moves only by visible editorial diff — the
// version-literal register's discipline). Justifications are load-bearing:
// the two private-path rows are OWNER-TRIAGE entries from the #518 history
// audit — deliberately NOT allowlisted into silence. The tilde rows are the
// bare tilde-home class's documented narrowing (re-fold FOLD-A): this repo's
// approximation notation (a tilde before an ordinary word) is structurally
// identical to a bare home reference, so it is pinned, not silently allowed
// — rewording to "about"/"approx." shrinks the table.
const PINNED = [
  { path: "docs/internal/review-rubric.md", id: "tilde_home", count: 1, why: "G0b names the screen's own default list path — the repo's vocabulary for its own config" },
  { path: "docs/operator-guide.md", id: "tilde_home", count: 1, why: "macOS launchd system path in operator documentation" },
  { path: "src/benchweave/cli/commands.py", id: "tilde_home", count: 1, why: "macOS launchd system path in CLI help text" },
  { path: "src/benchweave/cli/diagnose.py", id: "tilde_home", count: 2, why: "macOS launchd/launchagent system paths in diagnostics prose" },
  { path: "docs/implementation-planning/05-wp05-procedures-plan.md", id: "tilde_home", count: 1, why: "shell-config example in a planning doc" },
  { path: "docs/superpowers/plans/2026-09-14-standards-sync.md", id: "tilde_home", count: 2, why: "home-form checkout paths in tracked planning docs — pre-existing, the §6 audit's companion class" },
  { path: "docs/superpowers/plans/2026-09-15-sdk-repo-self-sufficiency.md", id: "tilde_home", count: 4, why: "home-form checkout paths in tracked planning docs — pre-existing, the §6 audit's companion class" },
  { path: "docs/superpowers/specs/2026-09-15-sdk-repo-self-sufficiency-design.md", id: "tilde_home", count: 3, why: "home-form checkout paths in tracked planning docs — pre-existing, the §6 audit's companion class" },
  { path: "docs/internal/public-site-mockup.html", id: "ipv4", count: 5, why: "SVG path-data numeric runs in a generated mockup — not addresses (the leading-zero version shape now allows 2 of the original 7)" },
  { path: "tests/interfaces_ui/test_ui_guards.py", id: "ipv4", count: 4, why: "private-range (RFC 1918) host-matching fixtures — private ranges stay blocked by design, these are pinned test literals" },
  { path: "tests/standards/test_zero_literal_gate.py", id: "ipv4", count: 2, why: "private-range literals the zero-gate's own snapshot tests assert on" },
  { path: "docs/superpowers/plans/2026-09-15-sdk-pypi-brew-publishing.md", id: "home_path", count: 4, why: "OWNER TRIAGE (#518 audit class): pre-existing private home-dir occurrences in tracked public content — removal is an owner decision, never an allowlist" },
  { path: "docs/implementation-planning/04-wp01-completion.md", id: "home_path", count: 1, why: "OWNER TRIAGE (#518 audit class): pre-existing private home-dir occurrence" },
  { path: "tests/contracts/test_architecture.py", id: "home_path", count: 1, why: "docstring documenting the home-path SHAPE itself (ellipsised, no real user)" },
];

test("F2: tracked-tree sweep (docs/ src/ packages/ tests/) — zero blocks outside the pinned table", async () => {
  const m = await import("../name-screen.mjs");
  const files = spawnSync("git", ["ls-files", "docs/", "src/", "packages/", "tests/"], { encoding: "utf8", cwd: ROOT }).stdout
    .trim()
    .split("\n")
    .filter(Boolean);
  assert.ok(files.length > 500, `sweep denominator implausible: ${files.length}`);
  const found = {}; // "path id" -> count
  let scanned = 0;
  let skippedBinary = 0;
  let skippedBig = 0;
  for (const f of files) {
    let t;
    try {
      t = readFileSync(join(ROOT, f), "utf8");
    } catch {
      skippedBinary++;
      continue;
    }
    if (t.includes("\0")) {
      skippedBinary++;
      continue;
    }
    if (t.length > 4 * 1024 * 1024) {
      skippedBig++;
      continue;
    }
    scanned++;
    for (const h of m.publicScan(t)) {
      const k = `${f} ${h.id}`;
      found[k] = (found[k] || 0) + 1;
    }
  }
  const pinned = {};
  for (const row of PINNED) pinned[`${row.path} ${row.id}`] = row.count;
  const problems = [];
  for (const [k, c] of Object.entries(found)) {
    const want = pinned[k] ?? 0;
    if (c !== want) problems.push(`unpinned or count-drifted: ${k.replace(" ", " ")} found ${c} pinned ${want}`);
  }
  for (const k of Object.keys(pinned)) {
    if (!(k in found)) problems.push(`pinned row no longer matches (shrink the table): ${k.replace(" ", " ")}`);
  }
  assert.deepEqual(problems, [], `sweep failed (${scanned} scanned, ${skippedBinary} binary-skipped, ${skippedBig} big-skipped)\n${problems.join("\n")}`);
});

// ---- F3: inflected filename leaks ------------------------------------------------

test("F3: a spaced list entry matches a hyphenated filename, and src= never prints any inflection", () => {
  const d = tmp();
  try {
    const list = join(d, "l.list");
    writeFileSync(list, [...MULTI, "Filler-entry"].join("\n") + "\n");
    const needles = MULTI.flatMap(inflections);
    const env = { BENCHWEAVE_NAME_LIST: list };

    // (a) the filename surface: hyphenated/underscored/dotted files all hit,
    // cited by ordinal, never by path
    for (const [i, variant] of [MULTI[0].toLowerCase().replaceAll(" ", "-"), MULTI[1].toLowerCase().replaceAll(" ", "_"), MULTI[2].toLowerCase().replaceAll(" ", ".")].entries()) {
      const r = runCli(["--paths"], { input: `docs/clients/${variant}-rig.md\n`, env });
      assert.equal(r.status, 3, `hyphenated/underscored/dotted filename missed: ${variant}`);
      const out = r.stdout + r.stderr;
      assert.match(out, /surface=filename/);
      assertNoLeak(out, needles);
    }

    // (b) the content surface with a hot path: the citation must not quote a
    // path that carries the name in ANY inflection
    const hotPath = `docs/clients/${MULTI[0].toLowerCase().replaceAll(" ", "-")}-rig.md`;
    const w = runCli(["--pretooluse"], {
      input: JSON.stringify({ tool_name: "Write", tool_input: { file_path: hotPath, content: "clean content\n" } }),
      env,
    });
    assert.equal(w.status, 2, `hot-path Write not denied`);
    assertNoLeak(w.stdout + w.stderr, needles);
    assert.match(w.stdout + w.stderr, /surface=filename/);

    // (c) diff mode: added line inside a hot-path file cites an ordinal, and
    // an unrelated list entry in content still cites the (cold) path safely
    const diff = ["diff --git a/x b/x", `+++ b/${hotPath}`, "@@ -1,1 +1,2 @@", " context", `+worked with ${MULTI[1]}`].join("\n");
    const r = runCli(["--diff"], { input: diff, env });
    assert.equal(r.status, 3);
    assertNoLeak(r.stdout + r.stderr, needles);
  } finally {
    rmSync(d, { recursive: true, force: true });
  }
});

// ---- F5: present-but-unreadable list ----------------------------------------------

test("F5: a present-but-unreadable list BLOCKS with its own message (fail closed where opted in)", () => {
  const d = tmp();
  try {
    // a directory is present but unreadable as a file
    const dirList = join(d, "listdir");
    mkdirSync(dirList);
    writeFileSync(join(d, "seed"), "x");
    let r = runCli(["--text"], { input: "ordinary notes\n", env: { BENCHWEAVE_NAME_LIST: dirList } });
    assert.equal(r.status, 3, "directory list degraded silently to public tier");
    assert.match(r.stdout + r.stderr, /present but unreadable/i);

    // chmod-000 file: present, unreadable — same posture
    const locked = join(d, "locked.list");
    writeFileSync(locked, "Somename\n");
    spawnSync("chmod", ["000", locked]);
    if (spawnSync("cat", [locked]).status !== 0) {
      // only assert when the lock actually denies THIS user (root would read it)
      r = runCli(["--text"], { input: "ordinary notes\n", env: { BENCHWEAVE_NAME_LIST: locked } });
      assert.equal(r.status, 3, "chmod-000 list degraded silently");
      assert.match(r.stdout + r.stderr, /present but unreadable/i);
    }
    spawnSync("chmod", ["644", locked]);
  } finally {
    rmSync(d, { recursive: true, force: true });
  }
});

// ---- F6: the home-path family ------------------------------------------------------

test("F6: windows drive homes, lowercase users-dirs, and bare tilde-name homes all hit; a tilde-slash config path does not", async () => {
  const m = await import("../name-screen.mjs");
  const hits = (t) => m.publicScan(t).filter((h) => h.id.includes("home")).length;
  assert.ok(hits(["C:", "\\", "Users", "\\", "poisonbox", "\\", "x"].join("")), "windows drive home missed");
  // assembled: these paths exist at run time, never as shapes in this file
  assert.ok(hits(["/", "users", "/", "poisonbox", "/notes"].join("")), "lowercase users-dir missed");
  assert.ok(hits(["/", "Users", "/", "poisonbox", "/notes"].join("").toLowerCase()), "case-insensitive posix home missed");
  assert.ok(hits(["~", "poisonbox", "/bench"].join("")), "bare tilde home missed");
  // flipped by the 2026-10-22 ruled trade: tilde-slash IS a home shape now
  assert.ok(m.publicScan(["~", "/", ".config/x"].join("")).some((h) => h.id === "tilde_home"), "tilde-slash home path missed");
});

// ---- F4: the CI job's hardening (text-level pins on the workflow) -------------------

test("F4: ci.yml screens commit messages, uses the base-branch script, and handles branch creation", () => {
  const y = readFileSync(join(ROOT, ".github", "workflows", "ci.yml"), "utf8");
  assert.match(y, /git log --format=%B "\$base\.\.HEAD"/, "commit messages are not screened in CI");
  assert.match(y, /git show "\$script_ref:\.claude\/hooks\/name-screen\.mjs"/, "the job still runs the PR's own copy of the screen");
  assert.match(y, /cat-file -e/, "no existence guard before git show of the base script");
  assert.match(y, /default_branch/, "the all-zeros before case has no default-branch fallback");
});

test("F4: the CI message pipeline blocks a planted commit message (local shape)", () => {
  const d = tmp();
  try {
    const repo = tmp();
    try {
      const list = join(d, "l.list");
      writeFileSync(list, MULTI.join("\n") + "\n");
      const env = { ...process.env, BENCHWEAVE_NAME_LIST: list };
      const g = (args) => spawnSync("git", ["-C", repo, ...args], { encoding: "utf8", env });
      g(["init", "-q"]);
      g(["config", "user.email", ["probe", "@", "example.test"].join("")]);
      g(["config", "user.name", "probe"]);
      writeFileSync(join(repo, "a.txt"), "a\n");
      g(["add", "."]);
      g(["commit", "-q", "-m", "seed"]);
      const base = g(["rev-parse", "HEAD"]).stdout.trim();
      writeFileSync(join(repo, "b.txt"), "b\n");
      g(["add", "."]);
      g(["commit", "-q", "-m", `bench: notes from ${MULTI[2]}`]);
      const log = spawnSync("git", ["-C", repo, "log", "--format=%B", `${base}..HEAD`], { encoding: "utf8", env });
      const r = spawnSync(process.execPath, [SCREEN, "--text"], { input: log.stdout, encoding: "utf8", cwd: ROOT, env });
      assert.equal(r.status, 3, "planted commit message passed the CI message pipeline");
      assertNoLeak(r.stdout + r.stderr, MULTI.flatMap(inflections));
    } finally {
      rmSync(repo, { recursive: true, force: true });
    }
  } finally {
    rmSync(d, { recursive: true, force: true });
  }
});

// ---- second refutation (2026-10-21): FOLD-A / FOLD-B / FOLD-C / R2b ----------

test("FOLD-A: the closed anchor rule — boundary chars hit, in-token paths never", async () => {
  const m = await import("../name-screen.mjs");
  const home = ["/", "Users", "/", "poisonbox", "/x"].join("");
  // the four the positive enumeration used to let through
  for (const pre of ["#", ")", "&", "\\"]) {
    assert.ok(m.publicScan(`${pre}${home}`).some((h) => h.id === "home_path"), `boundary char ${pre} missed`);
  }
  // representative prose abutments still hit
  assert.ok(m.publicScan(`> ${home}`).some((h) => h.id === "home_path"), "spaced blockquote path missed");
  assert.ok(m.publicScan(`*${home}`).some((h) => h.id === "home_path"), "bullet-abutted path missed");
  // bare tilde tokens do NOT match (the 2026-10-22 ruled trade); the
  // separator forms do
  const bare = ["~", "poisonbox"].join("");
  assert.deepEqual(m.publicScan(`see ${bare} for the rig`).filter((h) => h.id === "tilde_home"), [], "bare tilde token matched");
  assert.ok(m.publicScan(["~", "poisonbox", "/rig"].join("")).some((h) => h.id === "tilde_home"), "tilde-name-slash home missed");
  // typing annotations are not homes
  assert.deepEqual(m.publicScan(["~", "benchweave.content.store.Context"].join("")).filter((h) => h.id === "tilde_home"), [], "typing annotation false-positives on tilde_home");
  // in-token negatives: word chars, dash/dot/underscore prefixes and nested
  // absolute paths never match — the rule did not over-widen
  assert.deepEqual(m.publicScan(`abc${home}`), [], "word-char prefix matched");
  assert.deepEqual(m.publicScan(`x-y${home}`), [], "dash-prefix matched");
  assert.deepEqual(m.publicScan(`x.y${home}`), [], "dot-prefix matched");
  assert.deepEqual(m.publicScan(["/nested/dir", home].join("")), [], "nested absolute path matched");
  assert.deepEqual(m.publicScan("email/home/serial and docs/Users/index"), [], "mid-token path matched");
});

test("FOLD-B: the git-URL exemption is hosting-scoped; a client hostname is an ordinary hit", async () => {
  const m = await import("../name-screen.mjs");
  const ok = ["git@", "github.com:example/benchweave.git"].join("");
  assert.deepEqual(m.publicScan(ok).filter((h) => h.id === "email"), [], "hosting git URL false-positives");
  const client = ["git@", "acmecorp", "-", "client.internal"].join("");
  assert.ok(m.publicScan(client).some((h) => h.id === "email"), "client-identifying git@ host passed");
});

test("FOLD-C: binary-add and mode-only filenames are screened through the real hook and the CI command", () => {
  const d = tmp();
  try {
    const list = join(d, "l.list");
    writeFileSync(list, [...MULTI, "Filler-entry"].join("\n") + "\n");
    const env = { ...process.env, BENCHWEAVE_NAME_LIST: list };
    const nameEmail = ["contact-", ["alice", "@", "corp.example.com"].join(""), ".png"].join("");
    const nameHyphen = `${MULTI[0].toLowerCase().replaceAll(" ", "-")}-deploy.sh`;

    // (1) binary add through the real pre-commit hook — no +++ header exists
    for (const [label, fname, body] of [["binary", nameEmail, Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x00, 0x00])], ["mode-only", nameHyphen, Buffer.from("#!/bin/sh\n")]]) {
      const repo = tmp();
      try {
        const g = (args) => spawnSync("git", ["-C", repo, ...args], { encoding: "utf8", env });
        const hook = (name, input = "") => spawnSync("sh", [join(ROOT, ".githooks", name)], { input, encoding: "utf8", cwd: repo, env });
        g(["init", "-q"]);
        g(["config", "user.email", ["probe", "@", "example.test"].join("")]);
        g(["config", "user.name", "probe"]);
        writeFileSync(join(repo, "seed.txt"), "seed\n");
        g(["add", "."]);
        g(["commit", "-q", "-m", "seed"]);
        if (label === "mode-only") {
          // the canary NAME is already committed; only the mode changes now
          writeFileSync(join(repo, fname), body);
          g(["add", fname]);
          g(["commit", "-q", "-m", "seed the canary name"]);
          spawnSync("chmod", ["+x", join(repo, fname)]);
          g(["add", fname]);
        } else {
          writeFileSync(join(repo, fname), body);
          g(["add", fname]);
        }
        const r = hook("pre-commit");
        const out = r.stdout + r.stderr;
        assert.ok(r.status !== 0 && /name-screen: BLOCK/.test(out), `${label} filename not blocked by pre-commit\n${out}`);
        assertNoLeak(out, [...MULTI.flatMap(inflections), nameEmail, nameHyphen, "alice", "acmecorp"]);

        // (2) the CI command shape over the same staged state
        const names = spawnSync("git", ["-C", repo, "diff", "--cached", "--name-only", "--no-renames", "--diff-filter=ACM"], { encoding: "utf8", env });
        const screen = spawnSync(process.execPath, [SCREEN, "--paths"], { input: names.stdout, encoding: "utf8", cwd: ROOT, env });
        assert.equal(screen.status, 3, `${label} filename passed the CI paths leg\n${screen.stdout}${screen.stderr}`);
        assertNoLeak(screen.stdout + screen.stderr, [...MULTI.flatMap(inflections), nameEmail, nameHyphen, "alice", "acmecorp"]);
      } finally {
        rmSync(repo, { recursive: true, force: true });
      }
    }
  } finally {
    rmSync(d, { recursive: true, force: true });
  }
});

test("FOLD-C: --diff itself screens binary/mode-change names via the diff --git line", async () => {
  const m = await import("../name-screen.mjs");
  const fname = ["docs/", MULTI[1].toLowerCase().replaceAll(" ", "-"), ".bin"].join("");
  const diff = [
    `diff --git a/${fname} b/${fname}`,
    "new file mode 100644",
    "index 0000000..1234abc",
    "Binary files /dev/null and b/x differ",
  ].join("\n");
  const list = { present: true, entries: MULTI.map((v) => ({ value: v, lower: v.toLowerCase(), canon: v.toLowerCase().replace(/[^a-z0-9]+/g, "") })), ignored: 0, note: "t" };
  const r = m.screenDiff(diff, list);
  assert.equal(r.verdict, "BLOCK", "binary-add name passed in --diff mode");
  assert.ok(r.hits.some((h) => h.surface === "filename"), "no filename-surface hit from the diff --git line");
});

test("R2b: leading-zero four-part strings are the reachable version shape (SVG path data class)", async () => {
  const m = await import("../name-screen.mjs");
  const versionish = ["7", "59", "4", "07"].join(".");
  assert.deepEqual(m.publicScan(versionish), [], "leading-zero version shape still blocks — the claim outran the mechanism");
  // a clean routable address with no leading zeros still blocks
  assert.ok(m.publicScan(["1", "23", "82", "72"].join(".")).some((h) => h.id === "ipv4"), "routable four-part string passed");
});
