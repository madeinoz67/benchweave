#!/usr/bin/env node
// name-screen.mjs — the public-repo name screen (issue #518).
//
// CLAUDE.md §4 forbids naming a real bench, client or operator anywhere in
// committed content — source, tests, comments, records, commit messages and
// filenames. Until this screen, that rule was enforced by prompt discipline
// alone for the class that has no shape: a plain name as prose. Two tiers,
// one direction of failure — BLOCK:
//
//   Tier P (public, listless): the privacy screen's deterministic pattern
//   classes plus the review rubric G0 secret-literal shapes, over content AND
//   filenames. Secret prefixes are matched as prefix-plus-tail shapes, never
//   bare prefixes, so prose that merely names the prefixes (the rubric's own
//   G0 text) cannot self-trip the screen.
//   Tier L (local list): plain names at $BENCHWEAVE_NAME_LIST (default
//   ~/.config/benchweave/name-screen.list — OUTSIDE every repo of the family,
//   so the list itself can never land in one). One per line, minimum length
//   4, case-insensitive substring. List absent -> "public tier only",
//   announced, never silent.
//
// THE SCREEN NEVER PRINTS MATCHED TEXT. A block cites the pattern id or the
// list-entry index, with file/line or a surface ordinal — a screen whose block
// message restates the leak is a second leak. When the FILENAME is the match,
// the path is not quoted either; it is cited by ordinal.
//
// Usage:
//   node name-screen.mjs [--text]   [file]   # screen text (stdin default)
//   node name-screen.mjs --diff     [file]   # screen a unified diff's ADDED
//                                            # lines and new-file paths
//   node name-screen.mjs --paths    [file]   # screen one path per line
//   node name-screen.mjs --pretooluse        # PreToolUse payload on stdin;
//                                            # exit 2 denies the edit
// Exit codes: 0 PASS, 3 BLOCK (--pretooluse: 0 allow, 2 deny).
//
// Keep-in-step: the tier-P pattern set mirrors privacy-screen.mjs's
// deterministic classes (email, home path, hex dump, MAC, IPv4, serial-like);
// a pattern added there belongs here too, and vice versa. The secret shapes
// come from review-rubric G0's literal list.
//
// Disclosed residuals (design record §6): names split across lines are missed
// (substring per line); content past the first 1 MiB of a blob is missed with
// the truncation announced; a name absent from the list is invisible to every
// tier.

import { readFileSync, realpathSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const MAX_BYTES = 1048576;
export const MIN_ENTRY = 4;

// ---- tier P: the pattern classes ------------------------------------------------
// Mirrors privacy-screen.mjs's PATTERNS + scanEmails (kept in step; see the
// header comment). Secret shapes are prefix + tail of a minimum length, so a
// bare prefix in prose never matches. The bearer tail requires a digit or
// punctuation somewhere in it — pure letter-hyphen runs are ordinary prose.
const LOCAL_CHAR = /[A-Za-z0-9._%+-]/;
const DOMAIN_CHAR = /[A-Za-z0-9.-]/;
const EMAIL_SHAPE = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}$/;

const PATTERNS = [
  { id: "home_path", re: /\/(?:Users|home)\/[A-Za-z0-9_.-]+/g },
  { id: "hex_dump", re: /(?:[0-9a-f]{2} ){8,}/gi },
  { id: "mac", re: /\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\b/gi },
  { id: "ipv4", re: /\b(?:\d{1,3}\.){3}\d{1,3}\b/g },
  { id: "serial_like", re: /\b(?:SN|S\/N|serial)[:#= ]+[A-Z0-9-]{6,}\b/gi },
  { id: "secret_ghp", re: /\bghp_[A-Za-z0-9]{30,}/g },
  { id: "secret_github_pat", re: /\bgithub_pat_[A-Za-z0-9_]{30,}/g },
  { id: "secret_sk", re: /\bsk-[A-Za-z0-9_-]{32,}/g },
  { id: "secret_mk", re: /\bmk_[A-Za-z0-9]{16,}/g },
  { id: "secret_mdb", re: /\bmdb_[A-Za-z0-9]{16,}/g },
  { id: "secret_gorag", re: /\bgorag_[A-Za-z0-9]{16,}/g },
  { id: "secret_bearer", re: /\bBearer[ \t]+(?=[A-Za-z0-9._~+/=-]*[0-9._~+/=])[A-Za-z0-9._~+/=-]{16,}/g },
];

function scanEmailsLine(line, lineNo, hits) {
  // Linear per-line walk, bounded spans — the privacy-screen F2 shape (no
  // nested quantifiers over adversarial input).
  let i = 0;
  while (i < line.length && hits.length < 50) {
    const at = line.indexOf("@", i);
    if (at === -1) return;
    let s = at;
    while (s > 0 && at - s < 64 && LOCAL_CHAR.test(line[s - 1])) s--;
    let e = at + 1;
    while (e < line.length && e - at - 1 < 255 && DOMAIN_CHAR.test(line[e])) e++;
    while (e > at + 1 && (line[e - 1] === "." || line[e - 1] === "-")) e--;
    if (EMAIL_SHAPE.test(line.slice(s, e))) {
      hits.push({ tier: "P", id: "email", surface: "content", line: lineNo, col: s + 1 });
      return;
    }
    i = at + 1;
  }
}

/** Tier-P scan of a (possibly multi-line) text. Returns hits [{tier,id,line,col}]. */
export function publicScan(text) {
  const hits = [];
  const lines = text.split("\n");
  for (let n = 0; n < lines.length; n++) {
    const line = lines[n];
    scanEmailsLine(line, n + 1, hits);
    for (const p of PATTERNS) {
      p.re.lastIndex = 0;
      let m;
      while ((m = p.re.exec(line)) !== null) {
        hits.push({ tier: "P", id: p.id, surface: "content", line: n + 1, col: m.index + 1 });
        if (m.index === p.re.lastIndex) p.re.lastIndex++; // zero-width safety
        if (hits.length > 500) return hits; // pathological input stays bounded
      }
    }
  }
  return hits;
}

// ---- tier L: the local list -------------------------------------------------------

/** Load the name list. Absent/unreadable -> present:false, entries:[], note announcing it. */
export function loadList(env = process.env) {
  const p = env.BENCHWEAVE_NAME_LIST || join(env.HOME || homedir(), ".config", "benchweave", "name-screen.list");
  let raw;
  try {
    raw = readFileSync(p, "utf8");
  } catch {
    return { present: false, entries: [], ignored: 0, source: p, note: "public tier only (no name list)" };
  }
  const entries = [];
  let ignored = 0;
  for (const line of raw.split(/\r?\n/)) {
    const t = line.trim();
    if (!t || t.startsWith("#")) continue;
    if (t.length < MIN_ENTRY) {
      ignored++;
      continue;
    }
    entries.push({ value: t, lower: t.toLowerCase() });
  }
  return { present: true, entries, ignored, source: p, note: `public tier + list tier (${entries.length} entries)` };
}

/** Tier-L scan. Hits cite the 1-based entry index — never the entry text. */
export function listScan(text, entries) {
  const hits = [];
  const lines = text.split("\n");
  for (let n = 0; n < lines.length; n++) {
    const lower = lines[n].toLowerCase();
    for (let e = 0; e < entries.length; e++) {
      const col = lower.indexOf(entries[e].lower);
      if (col !== -1) {
        hits.push({ tier: "L", entry: e + 1, surface: "content", line: n + 1, col: col + 1 });
        if (hits.length > 500) return hits;
      }
    }
  }
  return hits;
}

// ---- verdict assembly --------------------------------------------------------------

/** Screen one text blob against both tiers. Verdict + hits + notes. */
export function screenText(text, list) {
  const notes = [];
  let body = text;
  if (text.length > MAX_BYTES) {
    body = text.slice(0, MAX_BYTES);
    notes.push(`input truncated at ${MAX_BYTES} bytes — misses past the cut are possible`);
  }
  const hits = [...publicScan(body), ...listScan(body, list.entries)];
  notes.push(list.note);
  if (list.ignored) notes.push(`${list.ignored} list entries shorter than ${MIN_ENTRY} ignored`);
  return { verdict: hits.length ? "BLOCK" : "PASS", hits, notes };
}

/** Screen path strings (one per input line). Filename hits cite the ordinal, never the path. */
export function screenPaths(paths, list) {
  const hits = [];
  const ordinal = (i) => i + 1;
  paths.forEach((path, i) => {
    for (const h of publicScan(path)) hits.push({ ...h, surface: "filename", ordinal: ordinal(i) });
    for (const h of listScan(path, list.entries)) hits.push({ ...h, surface: "filename", ordinal: ordinal(i) });
  });
  return hits;
}

// ---- diff mode ---------------------------------------------------------------------

/** Screen a unified diff: ADDED lines (with new-file line numbers) and new-file paths. */
export function screenDiff(diffText, list) {
  const hits = [];
  const notes = [];
  let body = diffText;
  if (diffText.length > MAX_BYTES) {
    body = diffText.slice(0, MAX_BYTES);
    notes.push(`diff truncated at ${MAX_BYTES} bytes — misses past the cut are possible`);
  }
  const seenPaths = [];
  let path = null;
  let pathHot = false;
  let newLine = 0;
  let inHunk = false;
  for (const line of body.split("\n")) {
    if (line.startsWith("diff ")) {
      inHunk = false;
      continue;
    }
    if (line.startsWith("+++ ")) {
      inHunk = false;
      path = line.slice(4).replace(/^b\//, "").replace(/\t.*$/, "");
      if (path === "/dev/null") {
        path = null;
        continue;
      }
      seenPaths.push(path);
      // The path itself is a surface: a new file whose NAME carries the plant.
      const pathIdx = seenPaths.length - 1;
      for (const h of publicScan(path)) hits.push({ ...h, surface: "filename", ordinal: pathIdx + 1 });
      for (const h of listScan(path, list.entries)) hits.push({ ...h, surface: "filename", ordinal: pathIdx + 1 });
      pathHot = hits.some((h) => h.surface === "filename");
      continue;
    }
    const at = line.match(/^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
    if (at) {
      newLine = parseInt(at[1], 10);
      inHunk = true;
      continue;
    }
    if (!inHunk) continue;
    if (line.startsWith("+")) {
      const t = line.slice(1);
      for (const h of publicScan(t)) hits.push({ ...h, src: pathHot ? undefined : path, line: newLine });
      for (const h of listScan(t, list.entries)) hits.push({ ...h, src: pathHot ? undefined : path, line: newLine });
      newLine++;
    } else if (line.startsWith("-")) {
      // removed content leaves the tree — not screened
    } else if (!line.startsWith("\\")) {
      newLine++; // context line; the "\ No newline" marker is not one
    }
  }
  notes.push(list.note);
  if (list.ignored) notes.push(`${list.ignored} list entries shorter than ${MIN_ENTRY} ignored`);
  return { verdict: hits.length ? "BLOCK" : "PASS", hits, notes };
}

// ---- citation rendering (the no-matched-text contract) -------------------------------

function cite(h) {
  const where = h.src !== undefined ? ` src=${h.src}:${h.line}` : h.line !== undefined && h.surface === "content" ? ` line=${h.line}` : "";
  const col = h.col !== undefined ? ` col=${h.col}` : "";
  if (h.surface === "filename") {
    // Never quote the path here: for a filename hit the path IS the match.
    return `tier=${h.tier} ${h.tier === "P" ? `id=${h.id}` : `entry=${h.entry}`} surface=filename ordinal=${h.ordinal}`;
  }
  return `tier=${h.tier} ${h.tier === "P" ? `id=${h.id}` : `entry=${h.entry}`} surface=content${where}${col}`;
}

function report(result) {
  const lines = [];
  if (result.verdict === "BLOCK") {
    lines.push(`name-screen: BLOCK (${result.hits.length} hit(s)) — refused under the never-name rule (CLAUDE.md §4, issue #518): use an invented name or "a real bench"; the matched text is deliberately not shown`);
    lines.push(`  ${cite(result.hits[0])}`);
  } else {
    lines.push("name-screen: PASS");
  }
  lines.push(...result.notes.map((n) => `name-screen: note: ${n}`));
  return lines.join("\n");
}

// ---- PreToolUse payload -------------------------------------------------------------

function screenPayload(input, list) {
  const ti = input?.tool_input || {};
  const hits = [];
  const texts = [];
  if (typeof ti.content === "string") texts.push(ti.content);
  if (typeof ti.new_string === "string") texts.push(ti.new_string);
  for (const e of Array.isArray(ti.edits) ? ti.edits : []) {
    if (typeof e?.new_string === "string") texts.push(e.new_string);
  }
  const hasPath = typeof ti.file_path === "string";
  // If the path itself is a hit, content citations must not quote it either.
  const fnHits = hasPath ? screenPaths([ti.file_path], list) : [];
  const pathHot = fnHits.length > 0;
  const src = hasPath && !pathHot ? ti.file_path : undefined;
  for (const t of texts) {
    const body = t.length > MAX_BYTES ? t.slice(0, MAX_BYTES) : t;
    for (const h of publicScan(body)) hits.push({ ...h, src });
    for (const h of listScan(body, list.entries)) hits.push({ ...h, src });
  }
  hits.push(...fnHits);
  const notes = [list.note];
  return { verdict: hits.length ? "BLOCK" : "PASS", hits, notes };
}

// ---- CLI (guarded: importing this module for its exports must never read stdin) -----

const isMain = (() => {
  try {
    return realpathSync(fileURLToPath(import.meta.url)) === realpathSync(resolve(process.argv[1] || "x-not-main"));
  } catch {
    return false;
  }
})();

if (isMain) {
  const args = process.argv.slice(2);
  const mode = args.includes("--pretooluse") ? "pretooluse" : args.includes("--diff") ? "diff" : args.includes("--paths") ? "paths" : "text";
  const file = args.find((a) => !a.startsWith("--"));
  const readInput = () => (file ? readFileSync(file, "utf8") : readFileSync(0, "utf8"));

  const list = loadList();

  let result;
  let exit = 0;
  if (mode === "pretooluse") {
    let input;
    try {
      input = JSON.parse(readInput() || "{}");
    } catch {
      input = {}; // unparseable payload: allow, visibly (the write-gate posture)
    }
    result = screenPayload(input, list);
    exit = result.verdict === "BLOCK" ? 2 : 0;
  } else if (mode === "diff") {
    result = screenDiff(readInput(), list);
    exit = result.verdict === "BLOCK" ? 3 : 0;
  } else if (mode === "paths") {
    const paths = readInput()
      .split(/\r?\n/)
      .filter((l) => l.trim() !== "");
    const hits = screenPaths(paths, list);
    result = { verdict: hits.length ? "BLOCK" : "PASS", hits, notes: [list.note] };
    exit = result.verdict === "BLOCK" ? 3 : 0;
  } else {
    result = screenText(readInput(), list);
    exit = result.verdict === "BLOCK" ? 3 : 0;
  }

  const out = report(result);
  if (mode === "pretooluse") console.error(out);
  else console.log(out);
  process.exit(exit);
}
