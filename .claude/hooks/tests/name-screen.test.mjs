// name-screen.test.mjs — the acceptance corpus for the public-repo name screen
// (issue #518; design: .claude/deep-review/2026-10-21-issue518-name-screen.md,
// whose §7 pre-committed every count asserted at the bottom of this file).
//
// CANARY DISCIPLINE: every canary here is invented, and the tier-P shape canaries
// are ASSEMBLED at runtime (never written as whole literals in this file's bytes),
// so this suite's own added lines stay green under the screen it ships — the
// shapes exist at run time, not in the source bytes. Do not "clean up" an
// assembly into a literal; that reds the name-screen CI job on this very file.
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

// ---- the corpus (invented; see the design record §7) -------------------------

// 12 obviously-invented org/bench names — the tier-L planted set.
export const PLANTED = [
  "Zorblat", "Quimbrel", "Brindlestack", "Vorpane", "Tessilune", "Grovmark",
  "Palexion", "Dravemont", "Ullquor", "Ostrevan", "Nimbrelfour", "Chalkvane",
];

// 24 negatives — real project vocabulary that must never block.
export const NEGATIVES = [
  "BenchWeave", "benchweave", "OTDP", "otdp", "DPS-150", "dps150", "FNIRSI",
  "registry", "corpus", "standards", "gateway", "descriptor", "adapter",
  "transport", "commissioning", "quarantine", "measurement", "evidence",
  "digest", "procedure", "bench", "plugin", "a real bench", "single-writer",
];

// The 8 pattern cases (tier P), assembled. Keys are the pattern ids of §2.
export const PATTERN_CASES = [
  ["home_path", ["/Users/", "zorblat", "/bench/notes.md"].join("")],
  ["email", ["quimbus", "@", "example.test"].join("")],
  ["mac", ["02", "1a", "2b", "3c", "4d", "5e"].join(":")],
  ["ipv4", ["192", "0", "2", "77"].join(".")],
  ["hex_dump", Array.from({ length: 12 }, (_, i) => (i * 7 + 3).toString(16).padStart(2, "0")).join(" ")],
  ["serial_like", ["SN", ": ", "QX", "-", "991234"].join("")],
  ["secret_ghp", ["ghp_", "a1"].join("") + "k".repeat(30)],
  ["secret_bearer", ["Bearer", " ", "tok", "3n", "line", "5x", "vault", "9m"].join("")],
];

// Extra tier-P shapes asserted in unit arms (not part of the 8-case arm).
const EXTRA_SHAPES = [
  ["secret_sk", ["sk", "-"].join("") + "b2".repeat(20)],
  ["secret_mk", ["mk_", "c3"].join("") + "d4".repeat(8)],
  ["secret_mdb", ["mdb_", "e5"].join("") + "f6".repeat(8)],
  ["secret_gorag", ["gorag_", "a7"].join("") + "b8".repeat(8)],
  ["secret_github_pat", ["github_pat_", "9c"].join("") + "8d".repeat(16)],
];

const TALLY = { plantedBlocked: 0, negativesPassed: 0, patternBlocked: 0, plantedPassListless: 0 };

// ---- helpers -----------------------------------------------------------------

function tmp() {
  return mkdtempSync(join(tmpdir(), "name-screen-"));
}

function writeList(dir, names) {
  const p = join(dir, "name-screen.list");
  writeFileSync(p, names.join("\n") + "\n");
  return p;
}

function runCli(args, { input = "", env = {} } = {}) {
  return spawnSync(process.execPath, [SCREEN, ...args], {
    input,
    encoding: "utf8",
    cwd: ROOT,
    env: { ...process.env, ...env },
  });
}

// The canary-leak proof (design §7): a BLOCK must never carry the matched text.
// `needles` are the strings the output must not contain.
function assertNoLeak(out, needles) {
  for (const n of needles) {
    if (n && n.length >= 4) assert.ok(!out.includes(n), `screen output leaked the canary "${n.slice(0, 4)}..."`);
  }
}

// ---- unit arms ----------------------------------------------------------------

test("corpus self-check: no planted name is a substring of any negative", () => {
  for (const p of PLANTED) {
    for (const n of NEGATIVES) {
      const hit = n.toLowerCase().includes(p.toLowerCase()) || p.toLowerCase().includes(n.toLowerCase());
      assert.ok(!hit, `corpus collision between planted "${p.slice(0, 3)}…" and a negative`);
    }
  }
});

test("loadList: reads entries, drops short ones and comments", async () => {
  const m = await import("../name-screen.mjs");
  const d = tmp();
  try {
    const p = writeList(d, ["Alpha-one", "# a comment", "", "ok", "valid"]); // "ok" < 4 chars
    const r = m.loadList({ BENCHWEAVE_NAME_LIST: p });
    assert.deepEqual(r.entries.map((e) => e.value), ["Alpha-one", "valid"]);
    assert.equal(r.ignored, 1);
    assert.equal(r.present, true);
  } finally {
    rmSync(d, { recursive: true, force: true });
  }
});

test("loadList: absent list reports public tier only, never silent", async () => {
  const m = await import("../name-screen.mjs");
  const r = m.loadList({ BENCHWEAVE_NAME_LIST: "/definitely/not/here.list" });
  assert.equal(r.present, false);
  assert.deepEqual(r.entries, []);
  assert.match(r.note, /public tier only/i);
});

test("publicScan finds every pattern id with line and column", async () => {
  const m = await import("../name-screen.mjs");
  const lines = ["ordinary prose about a real bench", ...PATTERN_CASES.map(([, v]) => v), ...EXTRA_SHAPES.map(([, v]) => v)];
  const hits = m.publicScan(lines.join("\n"));
  const ids = new Set(hits.map((h) => h.id));
  for (const [id] of [...PATTERN_CASES, ...EXTRA_SHAPES]) {
    assert.ok(ids.has(id), `publicScan missed pattern ${id}`);
  }
  const h = hits.find((x) => x.id === "home_path");
  assert.equal(h.line, 2); // first pattern case sits on line 2
  assert.ok(h.col >= 1);
});

test("listScan cites the entry index and the line, never by name", async () => {
  const m = await import("../name-screen.mjs");
  const values = ["filler-one", "filler-two", PLANTED[3]];
  const entries = values.map((v) => ({ value: v, lower: v.toLowerCase() }));
  const hits = m.listScan(`intro line\nworked with ${values[2]} on the rig\n`, entries);
  assert.equal(hits.length, 1);
  assert.equal(hits[0].entry, 3); // 1-based index into the loaded list
  assert.equal(hits[0].line, 2);
});

test("screenText: listless pass of a planted name (tier P cannot see plain names)", async () => {
  const m = await import("../name-screen.mjs");
  const r = m.screenText(`notes from ${PLANTED[0]} engineering`, []);
  assert.equal(r.verdict, "PASS");
});

// ---- CLI arms ------------------------------------------------------------------

test("CLI text mode: BLOCK exits 3, cites index, carries no canary text", () => {
  const d = tmp();
  try {
    const list = writeList(d, PLANTED);
    const r = runCli(["--text"], {
      input: `the ${PLANTED[5]} run history\n`,
      env: { BENCHWEAVE_NAME_LIST: list },
    });
    assert.equal(r.status, 3, `stderr: ${r.stderr}`);
    assert.match(r.stdout + r.stderr, /BLOCK/);
    assert.match(r.stdout + r.stderr, /entry=6\b/);
    assertNoLeak(r.stdout + r.stderr, PLANTED);
  } finally {
    rmSync(d, { recursive: true, force: true });
  }
});

test("CLI pass with list prints the tier note; without list prints public-tier-only", () => {
  const d = tmp();
  try {
    const list = writeList(d, ["Unrelated-entry"]);
    const withList = runCli(["--text"], { input: "plain project notes\n", env: { BENCHWEAVE_NAME_LIST: list } });
    assert.equal(withList.status, 0);
    assert.doesNotMatch(withList.stdout + withList.stderr, /public tier only/i);
    const noList = runCli(["--text"], { input: "plain project notes\n", env: { BENCHWEAVE_NAME_LIST: "/absent.list" } });
    assert.equal(noList.status, 0);
    assert.match(noList.stdout + noList.stderr, /public tier only/i);
  } finally {
    rmSync(d, { recursive: true, force: true });
  }
});

test("CLI diff mode: added line blocks with path:line; context and removed lines do not", () => {
  const d = tmp();
  try {
    const list = writeList(d, PLANTED);
    const name = PLANTED[7];
    const diff = [
      "diff --git a/docs/notes.md b/docs/notes.md",
      "--- a/docs/notes.md",
      "+++ b/docs/notes.md",
      "@@ -10,2 +10,3 @@",
      " context line stays",
      `-old line mentioning ${name} by name`,
      `+new line mentioning ${name} by name`,
    ].join("\n");
    const r = runCli(["--diff"], { input: diff, env: { BENCHWEAVE_NAME_LIST: list } });
    assert.equal(r.status, 3, `stderr: ${r.stderr}`);
    const out = r.stdout + r.stderr;
    // hunk opens at new-file line 10: context=10, the removed line does not
    // advance the new-file counter, so the added line is new-file line 11
    assert.match(out, /docs\/notes\.md:11/);
    assertNoLeak(out, PLANTED);
  } finally {
    rmSync(d, { recursive: true, force: true });
  }
});

test("CLI diff mode: a new file whose NAME is the match blocks without quoting the path", () => {
  const d = tmp();
  try {
    const list = writeList(d, PLANTED);
    const name = PLANTED[9].toLowerCase();
    const diff = [
      "diff --git a/clients/x.md b/clients/x.md",
      "+++ b/clients/x.md",
      "@@ -0,0 +1 @@",
      "+innocent content line",
    ].join("\n");
    // The filename leg comes from --paths style input; emulate the push leg:
    const paths = runCli(["--paths"], { input: `clients/${name}-rig.md\n`, env: { BENCHWEAVE_NAME_LIST: list } });
    assert.equal(paths.status, 3, `stderr: ${paths.stderr}`);
    const out = paths.stdout + paths.stderr;
    assert.match(out, /surface=filename/);
    assert.match(out, /ordinal=1/);
    assertNoLeak(out, PLANTED);
  } finally {
    rmSync(d, { recursive: true, force: true });
  }
});

test("CLI --pretooluse: Write/Edit/MultiEdit payloads deny with exit 2 and no text", () => {
  const d = tmp();
  try {
    const list = writeList(d, PLANTED);
    const env = { BENCHWEAVE_NAME_LIST: list };
    const name = PLANTED[2];

    const w = runCli(["--pretooluse"], {
      input: JSON.stringify({ tool_name: "Write", tool_input: { file_path: "docs/log.md", content: `notes on ${name}\n` } }),
      env,
    });
    assert.equal(w.status, 2, `stderr: ${w.stderr}`);

    const e = runCli(["--pretooluse"], {
      input: JSON.stringify({ tool_name: "Edit", tool_input: { file_path: "docs/log.md", old_string: "x", new_string: `client ${name}` } }),
      env,
    });
    assert.equal(e.status, 2, `stderr: ${e.stderr}`);

    const me = runCli(["--pretooluse"], {
      input: JSON.stringify({ tool_name: "MultiEdit", tool_input: { file_path: "docs/log.md", edits: [{ old_string: "x", new_string: `ok` }, { old_string: "y", new_string: `${name} rig` }] } }),
      env,
    });
    assert.equal(me.status, 2, `stderr: ${me.stderr}`);
    assertNoLeak(w.stdout + w.stderr + e.stdout + e.stderr + me.stdout + me.stderr, PLANTED);

    // the FILENAME surface: the path itself is the match — the message must not quote it
    const fn = runCli(["--pretooluse"], {
      input: JSON.stringify({ tool_name: "Write", tool_input: { file_path: `docs/${name.toLowerCase()}-notes.md`, content: "clean\n" } }),
      env,
    });
    assert.equal(fn.status, 2, `stderr: ${fn.stderr}`);
    assertNoLeak(fn.stdout + fn.stderr, PLANTED);
    assert.match(fn.stdout + fn.stderr, /surface=filename/);

    const ok = runCli(["--pretooluse"], {
      input: JSON.stringify({ tool_name: "Write", tool_input: { file_path: "docs/clean.md", content: "ordinary notes about a real bench\n" } }),
      env,
    });
    assert.equal(ok.status, 0, `stderr: ${ok.stderr}`);
  } finally {
    rmSync(d, { recursive: true, force: true });
  }
});

test("oversize input is truncated and announced, and scanning stays linear", async () => {
  const m = await import("../name-screen.mjs");
  const chunk = "ordinary project vocabulary about a real bench and an adapter\n";
  const big = chunk.repeat(Math.ceil((m.MAX_BYTES + chunk.length) / chunk.length));
  const t0 = Date.now();
  const r = m.screenText(big, m.loadList({ BENCHWEAVE_NAME_LIST: "/absent.list" }));
  const ms = Date.now() - t0;
  assert.match(r.notes.join("\n"), /truncated/i);
  // Structural anti-quadratic bound, not a wall-clock band: ~1 MiB must scan in
  // well under a second per tier on any CI-grade host (measured locally in the
  // run record; this assert only catches complexity regressions).
  assert.ok(ms < 5000, `screen of ~1 MiB took ${ms}ms — quadratic scan?`);
  assert.equal(r.verdict, "PASS");
});

// ---- surface arms (CLI level; the git-hook wiring arms live in the wiring suite) --

test("surface arms: with the list, all 36 planted cases BLOCK (12 names x 3 surfaces)", () => {
  const d = tmp();
  try {
    const list = writeList(d, PLANTED);
    const env = { BENCHWEAVE_NAME_LIST: list };
    for (const name of PLANTED) {
      // surface 1: content
      let r = runCli(["--text"], { input: `run history for ${name}\n`, env });
      let out = r.stdout + r.stderr;
      if (r.status === 3 && /BLOCK/.test(out)) TALLY.plantedBlocked++;
      assert.equal(r.status, 3, `content case passed: ${name.slice(0, 3)}\n${out}`);
      assert.match(out, /BLOCK/);
      assertNoLeak(out, PLANTED);

      // surface 2: commit-message-shaped text (subject + body, as pre-push feeds it)
      r = runCli(["--text"], { input: `bench: notes from ${name}\n\nBody line.\n`, env });
      out = r.stdout + r.stderr;
      if (r.status === 3 && /BLOCK/.test(out)) TALLY.plantedBlocked++;
      assert.equal(r.status, 3, `message case passed: ${name.slice(0, 3)}\n${out}`);
      assertNoLeak(out, PLANTED);

      // surface 3: filename
      r = runCli(["--paths"], { input: `clients/${name.toLowerCase()}-rig.md\n`, env });
      out = r.stdout + r.stderr;
      if (r.status === 3 && /BLOCK/.test(out)) TALLY.plantedBlocked++;
      assert.equal(r.status, 3, `filename case passed: ${name.slice(0, 3)}\n${out}`);
      assert.match(out, /surface=filename/);
      assertNoLeak(out, PLANTED);
    }
  } finally {
    rmSync(d, { recursive: true, force: true });
  }
});

test("surface arms: 24 negatives pass (no false block on project vocabulary)", () => {
  const d = tmp();
  try {
    const list = writeList(d, PLANTED);
    for (const neg of NEGATIVES) {
      const r = runCli(["--text"], { input: `the ${neg} adapter ran on a real bench\n`, env: { BENCHWEAVE_NAME_LIST: list } });
      if (r.status === 0) TALLY.negativesPassed++;
      assert.equal(r.status, 0, `false block on project vocabulary: "${neg}"\n${r.stdout}${r.stderr}`);
    }
  } finally {
    rmSync(d, { recursive: true, force: true });
  }
});

test("surface arms: list absent — the 36 planted cases PASS (RED arm) while the 8 pattern cases still BLOCK", () => {
  const absent = "/definitely/absent/name-screen.list";
  const env = { BENCHWEAVE_NAME_LIST: absent };
  // 36 planted cases, listless: 12 names x (content, message text, filename)
  for (const name of PLANTED) {
    for (const text of [`run history for ${name}`, `bench: notes from ${name}`]) {
      const r = runCli(["--text"], { input: `${text}\n`, env });
      if (r.status === 0) TALLY.plantedPassListless++;
      assert.equal(r.status, 0, `listless planted name blocked (tier P overreach): ${name.slice(0, 3)}\n${r.stdout}${r.stderr}`);
    }
    const paths = runCli(["--paths"], { input: `${name.toLowerCase()}-rig.md\n`, env });
    if (paths.status === 0) TALLY.plantedPassListless++;
    assert.equal(paths.status, 0, `listless filename blocked (tier P overreach): ${name.slice(0, 3)}`);
  }
  // the 8 pattern cases, listless: still BLOCK 8/8
  for (const [id, value] of PATTERN_CASES) {
    const r = runCli(["--text"], { input: `prefix ${value} suffix\n`, env });
    if (r.status === 3) TALLY.patternBlocked++;
    assert.equal(r.status, 3, `pattern case ${id} did not block without the list`);
  }
  // and with the list present they block too (the full-strength run)
  const d = tmp();
  try {
    const list = writeList(d, PLANTED);
    for (const [id, value] of PATTERN_CASES) {
      const r = runCli(["--text"], { input: `prefix ${value} suffix\n`, env: { BENCHWEAVE_NAME_LIST: list } });
      assert.equal(r.status, 3, `pattern case ${id} did not block with the list`);
    }
  } finally {
    rmSync(d, { recursive: true, force: true });
  }
});

test("acceptance tally — the pre-committed counts (a zero here is INVALID, not a pass)", () => {
  assert.equal(TALLY.plantedBlocked, 36, `planted block cases: ${TALLY.plantedBlocked}/36 — under 36 kills (design §7)`);
  assert.equal(TALLY.negativesPassed, 24, `negatives passed: ${TALLY.negativesPassed}/24 — any false block kills`);
  assert.equal(TALLY.patternBlocked, 8, `pattern blocks listless: ${TALLY.patternBlocked}/8`);
  assert.equal(TALLY.plantedPassListless, 36, `listless planted passes (RED arm): ${TALLY.plantedPassListless}/36`);
});
