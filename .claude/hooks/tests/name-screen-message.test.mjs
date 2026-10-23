// name-screen-message.test.mjs — the message-surface discipline suite (issue #527).
//
// The #527 residual: the CI message screen (and pre-push) refused prose that
// DESCRIBES the rule, because a describing sentence quotes a shape and the
// screen cannot tell a placeholder name from a real one. The ruled closure
// (design record §16): documentation and messages describing the screen must
// not write the shapes — describe them in words, or assemble them in code —
// and the refusal itself teaches that discipline at the point of friction.
// These arms pin the ruling from both sides: the discipline is taught, the
// words-only way through passes, and every genuine catch still fires.
//
// DIFF DISCIPLINE (design record §15): every shape in this suite is assembled
// at runtime — no line of this file carries a contiguous home shape, so the
// branch stays green under the base screen that judges its added lines.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..", "..", "..");
const SCREEN = join(ROOT, ".claude", "hooks", "name-screen.mjs");

// The two fragments the refusal must carry for home-family hits: the
// epistemic limit stated plainly, and the remedy.
const LIMIT = /cannot tell a placeholder from a real home path by shape/;
const REMEDY = /describe it in words/;

// The issue's self-fire sentence, assembled (its two matched classes are
// pinned by id below — home_path and tilde_home, both surface=content).
const ISSUE_SENTENCE = [
  "The rule refuses a home path such as ",
  "~", "/name or ", "/", "Users", "/", "name.",
].join("");
// The commonest REAL self-fire: a message quoting the screen's own default
// list path. A placeholder-name allowance cannot fix this one — the path
// component after the tilde separator is fixed vocabulary, not a name.
const DEFAULT_PATH_QUOTE = [
  "Docs: point operators at the default list path ",
  "~", "/", ".config/benchweave/name-screen.list.",
].join("");
// The way through: the same rule described entirely in words.
const WORDS_ONLY =
  "The screen refuses a real home path in committed content: a tilde home reference, a Users-dir path, or a drive-letter home. Describe the shape in words; never quote it.";
// Genuine catches — realistic invented usernames from the suite family's own
// vocabulary (Quimbrel/Zorblat, the fold suite's invented set).
const REAL_USERS_HOME = ["see ", "/", "Users", "/", "quimbrel", "/bench.md"].join("");
const REAL_TILDE_HOME = ["notes under ", "~", "zorblat", "/bench"].join("");
const REAL_WIN_HOME = ["logs at ", "C:", "\\", "Users", "\\", "zorblat", "\\x"].join("");
// serial_like's separator class is [:#= ]+ — the tail follows a colon here
const SERIAL_SHAPE = ["tag ", "SN", ": ", "ZBL", "772201", " recorded"].join("");

// Never created: every tier-P arm runs listless by construction, so the
// operator's real list (if one exists) cannot nondeterministically fire.
const ABSENT = join(tmpdir(), "ns-msg-absent.list");

function runCli(input, env = {}) {
  return spawnSync(process.execPath, [SCREEN, "--text"], {
    input,
    encoding: "utf8",
    cwd: ROOT,
    env: { ...process.env, BENCHWEAVE_NAME_LIST: ABSENT, ...env },
  });
}

test("the #527 sentence: BLOCK names both classes AND teaches the discipline", () => {
  const r = runCli(ISSUE_SENTENCE + "\n");
  assert.equal(r.status, 3, "a message quoting the shapes must stay refused");
  const out = r.stdout + r.stderr;
  assert.match(out, /id=home_path/, "home_path citation missing");
  assert.match(out, /id=tilde_home/, "tilde_home citation missing");
  assert.match(out, LIMIT, "the refusal does not state the epistemic limit");
  assert.match(out, REMEDY, "the refusal does not teach the describe-in-words remedy");
  // and it never quotes the matched shapes back
  for (const shape of [["~", "/name"].join(""), ["/", "Users", "/", "name."].join("")]) {
    assert.ok(!out.includes(shape), "block output quoted a matched shape");
  }
});

test("a message quoting the screen's default list path: BLOCK with the discipline", () => {
  const r = runCli(DEFAULT_PATH_QUOTE + "\n");
  assert.equal(r.status, 3, "the default-list-path quote must stay refused");
  const out = r.stdout + r.stderr;
  assert.match(out, /id=tilde_home/);
  assert.match(out, LIMIT, "no epistemic limit on the default-path self-fire");
  assert.match(out, REMEDY, "no remedy on the default-path self-fire");
});

test("the way through: a message that describes the rule in words passes", () => {
  const r = runCli(WORDS_ONLY + "\n");
  assert.equal(r.status, 0, "words-only describing prose must pass");
  assert.match(r.stdout + r.stderr, /name-screen: PASS/);
});

test("genuine catches still fire and name the class: real homes in a message BLOCK", () => {
  for (const [text, id] of [
    [REAL_USERS_HOME, "home_path"],
    [REAL_TILDE_HOME, "tilde_home"],
    [REAL_WIN_HOME, "win_home"],
  ]) {
    const r = runCli(text + "\n");
    assert.equal(r.status, 3, `real home path in a message passed (id=${id})`);
    const out = r.stdout + r.stderr;
    assert.match(out, new RegExp(`id=${id}`), `citation missing id=${id}`);
    assert.match(out, /surface=content line=1/, `citation must carry the line for id=${id}`);
    assert.match(out, LIMIT, `home-family hit (id=${id}) must carry the guidance`);
  }
});

test("the discipline note is scoped to the home family: a serial hit blocks WITHOUT it", () => {
  const r = runCli(SERIAL_SHAPE + "\n");
  assert.equal(r.status, 3, "a serial shape in a message passed");
  const out = r.stdout + r.stderr;
  assert.match(out, /id=serial_like/);
  assert.doesNotMatch(out, LIMIT, "the home-family note fired for a non-home class");
});

test("a real client name in a message still BLOCKs by entry index (tier L unchanged)", () => {
  const d = mkdtempSync(join(tmpdir(), "ns-msg-"));
  try {
    const list = join(d, "l.list");
    writeFileSync(list, "Quimbrel Testworks\n");
    const r = runCli("bench notes from Quimbrel Testworks\n", { BENCHWEAVE_NAME_LIST: list });
    assert.equal(r.status, 3, "a listed client name in a message passed");
    const out = r.stdout + r.stderr;
    assert.match(out, /tier=L entry=1/);
    assert.ok(!out.includes("Quimbrel"), "output quoted the listed name");
    assert.doesNotMatch(out, LIMIT, "the home-family note fired for a tier-L name hit");
  } finally {
    rmSync(d, { recursive: true, force: true });
  }
});

test("the screen's own bytes pass its own public scan (it ships its own discipline)", async () => {
  const m = await import("../name-screen.mjs");
  assert.deepEqual(
    m.publicScan(readFileSync(SCREEN, "utf8")),
    [],
    "the screen's own source carries a shape its own tier P refuses",
  );
});

test("the refusal's own output passes the screen (the guidance carries no shape)", async () => {
  const m = await import("../name-screen.mjs");
  const r = runCli(ISSUE_SENTENCE + "\n");
  assert.equal(r.status, 3);
  assert.deepEqual(
    m.publicScan(r.stdout + r.stderr),
    [],
    "blocked output carries a shape the screen itself would refuse",
  );
});
