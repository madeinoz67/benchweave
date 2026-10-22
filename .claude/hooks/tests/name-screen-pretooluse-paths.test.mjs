// name-screen-pretooluse-paths.test.mjs — the shipped-regression pins
// (2026-10-22). The --pretooluse filename surface screened the payload's
// ABSOLUTE path, which sits under the operator's home directory in every
// normal checkout — so tier P's home_path class matched the machine prefix
// and every Edit/Write carrying a file_path was denied (reproduced on main:
// clean in-repo payload, exit 2, id=home_path surface=filename ordinal=1).
// The fix: pretooluse derives the REPO-RELATIVE path when the payload path is
// inside this repository, and skips the path surface entirely when it is not.
// Canaries invented; tier-P shapes assembled at runtime as always.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..", "..", "..");
const SCREEN = join(ROOT, ".claude", "hooks", "name-screen.mjs");

// the machine-prefix shape the bug keyed on — assembled, never literal here
const HOME_PREFIX = ["/", "Users", "/", "poisonbox", "/src/BenchWeave"].join("");

function runHook(payload, env = {}) {
  return spawnSync(process.execPath, [SCREEN, "--pretooluse"], {
    input: JSON.stringify(payload),
    encoding: "utf8",
    cwd: ROOT,
    env: { ...process.env, ...env },
  });
}

test("(a) absolute IN-REPO path + clean content -> ALLOW (the shipped regression)", () => {
  const r = runHook({ tool_name: "Write", tool_input: { file_path: HOME_PREFIX + "/docs/ordinary-note.md", content: "ordinary content about a real bench\n" } });
  assert.equal(r.status, 0, `denied clean in-repo payload:\n${r.stdout}${r.stderr}`);
});

test("(b) absolute in-repo path + content carrying a home path -> BLOCK (content surface unchanged)", () => {
  const leak = ["see /", "Users", "/", "poisonbox", "/x for notes"].join("");
  const r = runHook({ tool_name: "Write", tool_input: { file_path: HOME_PREFIX + "/docs/ordinary-note.md", content: leak + "\n" } });
  assert.equal(r.status, 2, `leaking content allowed\n${r.stdout}${r.stderr}`);
  assert.match(r.stdout + r.stderr, /id=home_path/);
});

test("(c) repo-RELATIVE filename shaped like a leak -> BLOCK (filename surface kept, on relative names)", () => {
  const d = mkdtempSync(join(tmpdir(), "ns-pp-"));
  try {
    const list = join(d, "l.list");
    writeFileSync(list, "Quimbrel Testworks\n");
    const emailName = ["contact-", ["alice", "@", "corp.example.com"].join(""), ".md"].join("");
    const byName = runHook({ tool_name: "Write", tool_input: { file_path: "docs/" + emailName, content: "clean\n" } }, { BENCHWEAVE_NAME_LIST: list });
    assert.equal(byName.status, 2, "repo-relative listed-name filename allowed");
    assert.match(byName.stdout + byName.stderr, /surface=filename/);
    const byShape = runHook({ tool_name: "Write", tool_input: { file_path: "docs/" + emailName, content: "clean\n" } });
    assert.equal(byShape.status, 2, "repo-relative email-shaped filename allowed");
  } finally {
    rmSync(d, { recursive: true, force: true });
  }
});

test("(d) OUTSIDE-repo path + clean content -> ALLOW (path surface skipped, content still screened)", () => {
  const outside = ["/", "Users", "/", "poisonbox", "/scratch/elsewhere.md"].join("");
  const clean = runHook({ tool_name: "Write", tool_input: { file_path: outside, content: "ordinary notes\n" } });
  assert.equal(clean.status, 0, `denied clean outside-repo payload:\n${clean.stdout}${clean.stderr}`);
  const leak = ["see /", "Users", "/", "poisonbox", "/x"].join("");
  const dirty = runHook({ tool_name: "Write", tool_input: { file_path: outside, content: leak + "\n" } });
  assert.equal(dirty.status, 2, "content surface lost for outside-repo paths");
});

// ---- second defect (2026-10-22): tilde approximation prose ---------------------
// PR #529 reddened the name-screen CI job on the sentence "subprocess-driven,
// ~seconds" — the bare tilde-name class matched ordinary approximation prose,
// which this repository writes constantly. Ruled trade: a bare tilde token is
// indistinguishable from approximation prose and approximation prose is far
// more common here, so the class REQUIRES a path separator — tilde-slash and
// tilde-name-slash stay home shapes; a bare tilde token does not match. The
// consequence is disclosed in the record addendum: a bare ~username reference
// with no path is now missed.
test("tilde trade: approximation prose allows; separator forms block", async () => {
  const m = await import("../name-screen.mjs");
  const tildes = (s) => m.publicScan(s).filter((h) => h.id === "tilde_home").length;
  for (const prose of [["~", "seconds"].join(""), ["~", "approx"].join("")]) {
    assert.equal(tildes(`fast, ${prose} per module`), 0, `approximation prose blocked: ${prose}`);
  }
  for (const prose of ["~5 min", "~10ms", "~2 min"]) {
    assert.equal(tildes(prose), 0, `approximation prose blocked: ${prose}`);
  }
  // separator forms are home shapes (assembled where shape-like)
  assert.ok(tildes(["~", "/.config/x"].join("")), "tilde-slash home path missed");
  assert.ok(tildes(["~", "poisonbox", "/reports"].join("")), "tilde-name-slash home path missed");
  const homes = (s) => m.publicScan(s).filter((h) => h.id.includes("home")).length;
  assert.ok(homes(["see /", "Users", "/", "poisonbox", "/x"].join("")) > 0, "posix home path missed");
  assert.ok(homes(["under /", "home/", "poisonbox", "/x"].join("")) > 0, "home-dir path missed");
  // the ruled-out form: bare tilde token, no separator anywhere after it
  assert.equal(tildes(["see ~", "poisonbox", " for the rig"].join("")), 0, "bare tilde token still matches — the trade was not taken");
});
