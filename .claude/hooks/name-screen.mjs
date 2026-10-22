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
//   filenames, with a measured allowlist for shapes this repository's own
//   legitimate vocabulary carries (loopback and RFC 5737 documentation
//   addresses, example-domain emails, scp git URLs on known hosting domains,
//   and version-shaped four-part strings — exactly: leading-zero, out-of-range
//   or first-octet-zero quads) — RFC 1918 private ranges stay BLOCKED: a
//   bench's internal addressing is operational specificity, and the fold's
//   tracked-tree sweep pins the test fixtures that carry them.
//   Tier L (local list): plain names at $BENCHWEAVE_NAME_LIST (default
//   ~/.config/benchweave/name-screen.list — OUTSIDE every repo of the family,
//   so the list itself can never land in one). One per line, minimum length
//   4, case-insensitive substring — plus INFLECTION-tolerant matching
//   (spaced entry vs hyphenated/underscored/dotted filename) through a
//   canonical form. A list that exists but cannot be read (directory,
//   permissions) BLOCKS: the operator opted into this tier, and silently
//   dropping it is the worse failure. A list that does not exist announces
//   "public tier only" — never silent.
//
// THE SCREEN NEVER PRINTS MATCHED TEXT. A block cites the pattern id or the
// list-entry index, with file:line or a surface ordinal — and never a path
// that itself carries the name in any inflection.
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
// come from review-rubric G0's literal list. This screen's home class is
// deliberately WIDER than privacy-screen's (windows drive homes, lowercase
// users-dirs and bare tilde-name homes — the fold's F6); keep-in-step means intent, not bytes.
//
// Disclosed residuals (design record §6): names split across lines are
// missed (substring per line); content past the first 1 MiB of a blob is
// missed with the truncation announced; a name absent from the list is
// invisible to every tier.

import { readFileSync, realpathSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const MAX_BYTES = 1048576;
export const MIN_ENTRY = 4;

// ---- tier P: the pattern classes ------------------------------------------------
const LOCAL_CHAR = /[A-Za-z0-9._%+-]/;
const DOMAIN_CHAR = /[A-Za-z0-9.-]/;
const EMAIL_SHAPE = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}$/;

// The measured allowlist (fold F2): shapes the repository's own vocabulary
// carries, so tier P must not block them. Private ranges are NOT here.
const EXAMPLE_DOMAINS = ["example.com", "example.net", "example.org", "example.test", "example.invalid", "example.example", "localhost"];
// The scp-style git URL exemption is HOSTING-scoped (re-fold FOLD-B): only a
// git@ address on a known hosting domain is a remote URL, never a mailbox.
// Any other git@ domain is an ordinary candidate — a client hostname must not
// walk in through the URL exemption.
const HOSTING_DOMAINS = ["github.com", "gitlab.com", "bitbucket.org", "codeberg.org"];

function allowedEmail(candidate) {
  const at = candidate.indexOf("@");
  if (at === -1) return false;
  const local = candidate.slice(0, at);
  const domain = candidate.slice(at + 1).toLowerCase();
  if (local.toLowerCase() === "git") {
    return HOSTING_DOMAINS.some((h) => domain === h || domain.endsWith("." + h));
  }
  return EXAMPLE_DOMAINS.some((d) => domain === d);
}

function allowedIpv4(candidate) {
  const rawParts = candidate.split(".");
  if (rawParts.length !== 4) return true;
  // version-shaped four-part strings (re-fold R2b, reachable branch): the
  // rule is exactly leading-zero, out-of-range or first-octet-zero quads. A
  // leading-zero octet is not a canonical address and reads as version or
  // vector-path data; out-of-range octets and a first octet of zero are the
  // same class. The claim names exactly this mechanism.
  if (rawParts.some((s) => /^0\d/.test(s))) return true;
  const parts = rawParts.map(Number);
  if (parts.some((n) => Number.isNaN(n) || n < 0 || n > 255)) return true;
  const [a, b, c] = parts;
  if (a === 0) return true; // version-shaped / this-network — never a host address in this repo's docs
  if (a === 127) return true; // loopback
  if (a === 192 && b === 0 && c === 2) return true; // RFC 5737 documentation
  if (a === 198 && b === 51 && c === 100) return true;
  if (a === 203 && b === 0 && c === 113) return true;
  return false;
}

// The ANCHOR RULE (closed by the third refutation): a home-path candidate
// must BEGIN at a token boundary — the preceding character is NOT in
// [A-Za-z0-9_.-] and NOT a slash, or the candidate starts the line. That
// single negative condition replaces any enumeration: it admits every
// punctuation character that can abut a path in prose, and refuses a path
// inside a longer token ("email/home/serial", "docs/Users/index", an
// absolute path nested under another) because the character before it is a
// word character, a dash/dot/underscore, or a slash.
const ANCHOR = String.raw`(?<![A-Za-z0-9_.\-/])`;

const PATTERNS = [
  { id: "home_path", re: new RegExp(`${ANCHOR}\\/(?:Users|home)\\/[A-Za-z0-9_.-]+`, "gi") },
  { id: "win_home", re: new RegExp(`${ANCHOR}[A-Za-z]:[\\\\/](?:Users|home)[\\\\/][A-Za-z0-9_.-]+`, "gi") },
  // tilde homes REQUIRE a path separator (ruled trade, 2026-10-22): a bare
  // tilde token is indistinguishable from this repo's approximation prose
  // ("~seconds", "~2 min"), and approximation prose is far more common than a
  // bare home reference — PR #529 reddened on the bare form. Tilde-slash and
  // tilde-name-slash stay home shapes; a bare tilde token does not match, so
  // a bare ~username reference with no path is MISSED (disclosed residual).
  // A dotted name (~john.doe/x) is also missed: the run excludes dots, the
  // typing-annotation ambiguity is unchanged.
  { id: "tilde_home", re: new RegExp(`${ANCHOR}~(?:\\/|[A-Za-z][A-Za-z0-9_-]{2,}(?![A-Za-z0-9_-])\\/)`, "g") },
  { id: "hex_dump", re: /(?:[0-9a-f]{2} ){8,}/gi },
  { id: "mac", re: /\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\b/gi },
  { id: "ipv4", re: /\b(?:\d{1,3}\.){3}\d{1,3}\b/g, allow: allowedIpv4 },
  // serial tails must carry a digit: "serial attachment" is prose, an id is not
  { id: "serial_like", re: /\b(?:SN|S\/N|serial)[:#= ]+(?=[A-Z0-9-]*\d)[A-Z0-9-]{6,}\b/gi },
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
    const cand = line.slice(s, e);
    if (EMAIL_SHAPE.test(cand) && !allowedEmail(cand)) {
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
        if (!p.allow || !p.allow(m[0])) {
          hits.push({ tier: "P", id: p.id, surface: "content", line: n + 1, col: m.index + 1 });
        }
        if (m.index === p.re.lastIndex) p.re.lastIndex++; // zero-width safety
        if (hits.length > 500) return hits; // pathological input stays bounded
      }
    }
  }
  return hits;
}

// ---- tier L: the local list -------------------------------------------------------

/** Load the name list. Absent -> public tier only, announced. Present but unreadable -> unreadable:true (callers BLOCK). */
export function loadList(env = process.env) {
  const p = env.BENCHWEAVE_NAME_LIST || join(env.HOME || homedir(), ".config", "benchweave", "name-screen.list");
  let raw;
  try {
    raw = readFileSync(p, "utf8");
  } catch (err) {
    let present = false;
    try {
      present = statSync(p) !== undefined;
    } catch {
      present = false;
    }
    if (present) {
      return { present: true, unreadable: true, entries: [], ignored: 0, source: p, note: `name list present but unreadable (${err.code || "error"}) — refusing to screen as listless; fix the file or unset BENCHWEAVE_NAME_LIST` };
    }
    return { present: false, unreadable: false, entries: [], ignored: 0, source: p, note: "public tier only (no name list)" };
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
    entries.push({ value: t, lower: t.toLowerCase(), canon: t.toLowerCase().replace(/[^a-z0-9]+/g, "") });
  }
  return { present: true, unreadable: false, entries, ignored, source: p, note: `public tier + list tier (${entries.length} entries)` };
}

/** Tier-L scan of content. Hits cite the 1-based entry index — never the entry text. */
export function listScan(text, entries) {
  const hits = [];
  const lines = text.split("\n");
  for (let n = 0; n < lines.length; n++) {
    const lower = lines[n].toLowerCase();
    const canon = lower.replace(/[^a-z0-9]+/g, "");
    for (let e = 0; e < entries.length; e++) {
      const ent = entries[e];
      const entLower = ent.lower ?? String(ent).toLowerCase();
      const entCanon = ent.canon ?? entLower.replace(/[^a-z0-9]+/g, "");
      const raw = lower.indexOf(entLower) !== -1;
      const inflected = !raw && entCanon.length >= MIN_ENTRY && canon.includes(entCanon);
      if (raw || inflected) {
        hits.push({ tier: "L", entry: e + 1, surface: "content", line: n + 1, col: 1, inflected });
        if (hits.length > 500) return hits;
      }
    }
  }
  return hits;
}

// ---- verdict assembly --------------------------------------------------------------

function forcedByList(list) {
  return list.unreadable ? list.note : null;
}

function assemble(hits, list, extraNotes = []) {
  const notes = [list.note, ...extraNotes];
  if (list.ignored) notes.push(`${list.ignored} list entries shorter than ${MIN_ENTRY} ignored`);
  const forced = forcedByList(list);
  const verdict = hits.length || forced ? "BLOCK" : "PASS";
  return { verdict, hits, notes, forced };
}

/** Screen one text blob against both tiers. Verdict + hits + notes. */
export function screenText(text, list) {
  const notes = [];
  let body = text;
  if (text.length > MAX_BYTES) {
    body = text.slice(0, MAX_BYTES);
    notes.push(`input truncated at ${MAX_BYTES} bytes — misses past the cut are possible`);
  }
  const hits = [...publicScan(body), ...listScan(body, list.entries)];
  return assemble(hits, list, notes);
}

/** Screen path strings (one per input line). Filename hits cite the ordinal, never the path. */
export function screenPaths(paths, list) {
  const hits = [];
  paths.forEach((path, i) => {
    for (const h of publicScan(path)) hits.push({ ...h, surface: "filename", ordinal: i + 1 });
    hits.push(...listScan(path, list.entries).map((h) => ({ ...h, surface: "filename", ordinal: i + 1 })));
  });
  return hits;
}

/** A path carries an entry or pattern in any inflection (canonical form). */
function pathIsHot(path, list) {
  return screenPaths([path], list).length > 0;
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
  const registerPath = (p) => {
    const prior = seenPaths.indexOf(p);
    if (prior === -1) {
      seenPaths.push(p);
      const ordinal = seenPaths.length;
      for (const h of publicScan(p)) hits.push({ ...h, surface: "filename", ordinal });
      hits.push(...listScan(p, list.entries).map((h) => ({ ...h, surface: "filename", ordinal })));
    }
    pathHot = pathIsHot(p, list);
  };
  for (const line of body.split("\n")) {
    // F1: a header-shaped line is a header ONLY at header position. Inside a
    // hunk an added line whose CONTENT begins "++ " also renders as "+++ …" —
    // treating it as a header skipped the rest of the hunk (the fold's
    // poisoning). "diff --git" ends the previous file's hunks wherever it
    // appears — a multi-file diff otherwise parses the next file's headers as
    // content and misattributes every hit after it (the fold's F1b).
    // FOLD-C: the diff --git line also REGISTERS the b-side path — binary
    // adds and mode-change-only entries carry no "+++" header at all, and
    // their names are exactly the surface this mode claims to screen.
    if (line.startsWith("diff ")) {
      inHunk = false;
      path = null;
      const mm = line.match(/^diff --git .* b\/(.+)$/);
      if (mm) {
        path = mm[1].replace(/^"|"$/g, "");
        registerPath(path);
      }
      continue;
    }
    if (!inHunk && (line.startsWith("--- ") || line.startsWith("+++ "))) {
      if (line.startsWith("+++ ")) {
        path = line.slice(4).replace(/^b\//, "").replace(/\t.*$/, "");
        if (path === "/dev/null") {
          path = null;
          continue;
        }
        registerPath(path);
      }
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
      hits.push(...listScan(t, list.entries).map((h) => ({ ...h, src: pathHot ? undefined : path, line: newLine })));
      newLine++;
    } else if (line.startsWith("-")) {
      // removed content leaves the tree — not screened
    } else if (!line.startsWith("\\")) {
      newLine++; // context line; the "\ No newline" marker is not one
    }
  }
  return assemble(hits, list, notes);
}

// ---- citation rendering (the no-matched-text contract) -------------------------------

function cite(h) {
  if (h.surface === "filename") {
    // Never quote the path here: for a filename hit the path IS the match.
    return `tier=${h.tier} ${h.tier === "P" ? `id=${h.id}` : `entry=${h.entry}`} surface=filename ordinal=${h.ordinal}`;
  }
  const where = h.src !== undefined ? ` src=${h.src}:${h.line}` : ` line=${h.line}`;
  const col = h.col !== undefined ? ` col=${h.col}` : "";
  return `tier=${h.tier} ${h.tier === "P" ? `id=${h.id}` : `entry=${h.entry}`} surface=content${where}${col}`;
}

function report(result) {
  const lines = [];
  if (result.verdict === "BLOCK") {
    lines.push(`name-screen: BLOCK (${result.hits.length} hit(s)) — refused under the never-name rule (CLAUDE.md §4, issue #518): use an invented name or "a real bench"; the matched text is deliberately not shown`);
    if (result.forced) {
      lines.push(`  ${result.forced}`);
    } else {
      for (const h of result.hits.slice(0, 5)) lines.push(`  ${cite(h)}`);
      if (result.hits.length > 5) lines.push(`  … and ${result.hits.length - 5} more`);
    }
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
  // The payload path is the tool call's ABSOLUTE machine path — under the
  // operator's home directory in every normal checkout, so screening it as
  // the filename surface denied EVERY edit (the 2026-10-22 regression:
  // tier P's home class matched the machine prefix, exit 2 on clean
  // content). The screened path is the REPO-RELATIVE path when the payload
  // path is inside this repository (hook cwd is the project dir); a path
  // outside the repository skips the path surface entirely — content is
  // still screened there, the machine path is not content.
  let relPath = null;
  if (typeof ti.file_path === "string" && ti.file_path !== "") {
    if (isAbsolute(ti.file_path)) {
      const rootDir = process.env.CLAUDE_PROJECT_DIR || process.cwd();
      const rel = relative(rootDir, ti.file_path);
      relPath = rel !== "" && !rel.startsWith("..") && !isAbsolute(rel) ? rel : null;
    } else {
      relPath = ti.file_path;
    }
  }
  // F3: a path that carries the name in ANY inflection is hot — content
  // citations must not quote it either.
  const fnHits = relPath !== null ? screenPaths([relPath], list) : [];
  const src = relPath !== null && fnHits.length === 0 ? relPath : undefined;
  for (const t of texts) {
    const body = t.length > MAX_BYTES ? t.slice(0, MAX_BYTES) : t;
    for (const h of publicScan(body)) hits.push({ ...h, src });
    hits.push(...listScan(body, list.entries).map((h) => ({ ...h, src })));
  }
  hits.push(...fnHits);
  return assemble(hits, list);
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
    result = assemble(screenPaths(paths, list), list);
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
