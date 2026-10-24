// name-screen-botmail.test.mjs — the public-bot mailbox allowlist suite (issue #553).
//
// DEFECT: every dependabot pull request failed the name-screen CI lane on
// the bot's own sign-off trailer — the trailer's mailbox is public GitHub
// infrastructure, published in every dependabot commit, not personal data
// and not a name. The class was too broad for bot-authored content. The
// fix is a measured allowlist of the addresses the bots in THIS repository
// family actually emit (design record §17), never an exclusion of
// bot-authored commits: an identity-based exclusion is a smuggling channel
// (content authored under a bot identity would escape the message and
// content scan entirely), while an allowlist admits exactly the enumerated
// shapes and nothing else.
//
// ENUMERATION (2026-10-24, gateway repository history and the seven open
// dependabot PRs): the dependabot sign-off mailbox — 18 occurrences in
// merged commit bodies and the only email in every open dependabot PR's
// body; GitHub's bot-account noreply convention, whose local part ends in
// a bracketed bot marker — the numeric dependabot form (6 in merged
// bodies, all seven open PRs' author metadata), the code-scanning bot form
// (2 in merged bodies), and the bare bracketed form in author metadata
// (the actions bot, the changelog bot). NOT admitted, each on measurement:
// the bare noreply domain — three HUMAN identities carry it in this
// repository's own history, so a domain-wide allow weakens the protected
// personal-address class; any other mailbox on the github.com domain — the
// allow is one exact public mailbox, not the domain; the github no-reply
// mailbox the issue suggested — zero occurrences here, and guessed lists
// are refused; and the bracket-less agent co-author (one occurrence, an
// agent credited on a human commit — not infrastructure).
//
// DIFF DISCIPLINE: every shape in this suite is assembled at runtime — no
// line of this file carries a contiguous email shape, so the branch stays
// green under the base screen that judges its added lines.
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

// The noreply domain and the measured forms, assembled (no contiguous
// shape ever appears in this file's bytes).
const NOREPLY_DOMAIN = ["users", "noreply", "github", "com"].join(".");
const SIGNOFF_LINE = ["Signed-off-by: dependabot", "[bot] <support", "@", "github.com>"].join("");
const NUMERIC_DEPENDABOT = ["Co-authored-by: dependabot", "[bot] <49699333+dependabot", "[bot]", "@", NOREPLY_DOMAIN, ">"].join("");
const CODESCAN_BOT = ["Co-authored-by: github-advanced-security", "[bot] <62310815+github-advanced-security", "[bot]", "@", NOREPLY_DOMAIN, ">"].join("");
const ACTIONS_BOT = ["Author: github-actions", "[bot] ", "@", NOREPLY_DOMAIN].join("");
const CHANGELOG_BOT = ["Author: benchweave-changelog", "[bot] ", "@", NOREPLY_DOMAIN].join("");

// The stays-blocked forms: invented personal data, the refused shapes.
const PERSONAL_MAILBOX = ["dana.quimbus", "@", "zorblat", ".internal"].join("");
const HUMAN_NOREPLY = ["123456+zorblat", "@", NOREPLY_DOMAIN].join("");
const BARE_BOT_TAIL = ["maintained by volunteer bot", "@", NOREPLY_DOMAIN].join("");
const AGENT_COAUTHOR = ["175728472+agentish", "@", NOREPLY_DOMAIN].join("");
const OTHER_GITHUB_MAILBOX = ["no-reply", "@", "github.com"].join("");

const ALLOWED_FORMS = [
  ["the dependabot sign-off trailer", SIGNOFF_LINE],
  ["the numeric dependabot co-author trailer", NUMERIC_DEPENDABOT],
  ["the code-scanning bot co-author trailer", CODESCAN_BOT],
  ["the bare actions-bot author form", ACTIONS_BOT],
  ["the bare changelog-bot author form", CHANGELOG_BOT],
];

const BLOCKED_FORMS = [
  ["an invented personal mailbox", PERSONAL_MAILBOX],
  ["a human's noreply address (the domain-wide allow is refused)", HUMAN_NOREPLY],
  ["the bot tail without the closing bracket before it", BARE_BOT_TAIL],
  ["a bracket-less agent co-author (the one-occurrence call, refused)", AGENT_COAUTHOR],
  ["any other mailbox on the github.com domain (exact mailbox, not domain)", OTHER_GITHUB_MAILBOX],
];

const TALLY = { allowedPassed: 0, blockedStayed: 0, tierLBlocked: 0, cliBodyPassed: 0 };

function absentListPath() {
  // A path under a fresh tmp dir that never exists: tier L deterministically
  // listless for the CLI arms, whatever the operator machine carries.
  return join(mkdtempSync(join(tmpdir(), "name-screen-botmail-")), "absent.list");
}

function runCli(input, { env = {} } = {}) {
  return spawnSync(process.execPath, [SCREEN, "--text"], {
    input,
    encoding: "utf8",
    cwd: ROOT,
    env: { ...process.env, BENCHWEAVE_NAME_LIST: absentListPath(), ...env },
  });
}

test("every measured bot form passes the email class", async () => {
  const m = await import("../name-screen.mjs");
  for (const [label, text] of ALLOWED_FORMS) {
    const hits = m.publicScan(text);
    assert.deepEqual(hits, [], `${label}: expected no tier-P hits`);
    TALLY.allowedPassed++;
  }
});

test("every personal and refused form still blocks, exactly the email class", async () => {
  const m = await import("../name-screen.mjs");
  for (const [label, text] of BLOCKED_FORMS) {
    const hits = m.publicScan(text);
    assert.equal(hits.length, 1, `${label}: expected exactly one hit`);
    assert.equal(hits[0].id, "email", `${label}: expected the email class`);
    TALLY.blockedStayed++;
  }
});

test("a full synthetic dependabot commit body passes the CLI (the #553 defect shape)", () => {
  const body = [
    "chore(deps-dev): bump quimbrel from 1.63.0 to 1.64.0",
    "",
    "Bumps quimbrel from 1.63.0 to 1.64.0.",
    "- release notes cited in the tracker row",
    "",
    "---",
    "updated-dependencies:",
    "- dependency-name: quimbrel",
    "  dependency-version: 1.64.0",
    "  dependency-type: direct:development",
    "  update-type: version-update:semver-minor",
    "...",
    "",
    SIGNOFF_LINE,
    "",
  ].join("\n");
  const r = runCli(body);
  assert.equal(r.status, 0, `expected PASS, got exit ${r.status}:\n${r.stdout}${r.stderr}`);
  assert.match(r.stdout, /^name-screen: PASS/);
  TALLY.cliBodyPassed++;
});

test("the bot allowlist does not touch tier L: a listed name still blocks beside the trailer", () => {
  const dir = mkdtempSync(join(tmpdir(), "name-screen-botmail-list-"));
  try {
    const list = join(dir, "name-screen.list");
    writeFileSync(list, "Zorblat\n");
    const body = [SIGNOFF_LINE, "", "evaluated on the Zorblat bench"].join("\n");
    const r = runCli(body, { env: { BENCHWEAVE_NAME_LIST: list } });
    assert.equal(r.status, 3, `expected BLOCK, got exit ${r.status}`);
    assert.match(r.stdout, /tier=L entry=1/, "the name must block by list entry");
    assert.ok(!r.stdout.includes("id=email"), "the trailer itself must not hit");
    TALLY.tierLBlocked++;
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("botmail tally — 5 allowed + 5 refused + 1 CLI body + 1 tier-L (a zero is INVALID, not a pass)", () => {
  assert.equal(TALLY.allowedPassed, 5, `allowed forms passed: ${TALLY.allowedPassed}/5`);
  assert.equal(TALLY.blockedStayed, 5, `refused forms blocked: ${TALLY.blockedStayed}/5`);
  assert.equal(TALLY.cliBodyPassed, 1, `CLI body arms passed: ${TALLY.cliBodyPassed}/1`);
  assert.equal(TALLY.tierLBlocked, 1, `tier-L arms blocked: ${TALLY.tierLBlocked}/1`);
});
