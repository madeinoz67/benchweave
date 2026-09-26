# Design records

One document per increment, written before the code. The `increment` skill
(`.claude/skills/increment/`) requires one for any non-trivial change: the mechanism, the
minimal first-increment scope with explicit deferrals, invariant impacts, the measurable
proof, and the top risks.

These are committed deliberately. A design whose pre-committed acceptance rule was written
BEFORE any number was looked at is only provably so if the document exists in git history
before the measurement ran — that provability is the point of this directory. If you want
to know why BenchWeave is shaped the way it is, `docs/smart-test-gateway-decisions.md` has
the summary and these have the working.

## The triage rule — read before adding a file here

This directory is **public**. `private/` is gitignored.

A design record goes in `private/` if it contains any of:

- **A real person's name** — contributors, colleagues, clients, investors. Test fixtures may
  use invented names; use obviously-invented ones.
- **Client or employer data** — bench identifiers tied to a customer, DUT serials, anything
  naming who the hardware or data belongs to.
- **Commercial terms** — pricing, rates, discounts, contract values, cost structure.
- **Competitive or go-to-market strategy** — positioning, moat analysis, pointed claims about
  other vendors.
- **Operational specifics of someone's bench** — hosts, ports, key material, device paths,
  deployment details particular to one install.

Everything else — mechanisms, measurements, invariants, prior art, negative results,
adversarial findings — belongs in public. Honest negative results are first-class here; a
killed idea is a real result and worth publishing.

**Default new work to `private/` and promote it deliberately.** Promotion is a review;
demotion after the fact is a leak, and git remembers.

## The deferral-row contract (issue #99)

The `increment` skill's Land step requires every deferral to cite its home and carry a
reopen trigger. Both terms are defined here; the skill references this section and does
not restate it.

**Reopen trigger — well-formed when:** it names an observable event (or a decidable
state) on a surface a third party can inspect, so a GO/CLOSE pass can answer "has it
fired?" by looking at that surface, not by asking the deferrer what they meant.
Observable: an admission or publication arriving; a corpus train opening; a measured
trace or repeated log line; a harness or corpus convention changing; a second run
exhibiting a named failure; the owner's explicit call on a named channel — an
owner-fired trigger is legitimate and must be disclosed as such (the #199 precedent:
"the reopen trigger fired by the owner's explicit call, not by operator demand").
Not observable, refused: "when it becomes important", "if needed", "when we have time".

Weak → strong, from the records: "a profile whose fetch semantics need acquisition
dedup" (#146 §6 row 5 as written — "need" is judgement, no inspection procedure)
sharpens to "an admitted or dogfood-published profile declaring an acquisition-lifecycle
fetch family whose procedure shape re-fetches the same acquisition across steps — a
real procedure that today would double-publish under two `ds:` ids" (#231 §3.3). The
strong form is the maturity the contract points at: it additionally names its **nearest
plausible carrier** — the arriving work or train most likely to carry the reopen (#231
§5's table shape). Naming the carrier is recommended, not required.

**Deferral table row — required semantics (four):**

1. **identifier** — a stable row id; later GO/CLOSE passes and follow-on records cite
   rows by it (#231's lineage cites "#146 rows 1, 5 and 7" — a table without ids cannot
   be cited).
2. **deferred** — the bounded thing deferred.
3. **home** — where this deferral lives under the skill's rule: "follow-on issue #N" or
   "documentation here". The column may be labelled Home or Carrier (both in active
   use); a rationale column ("Why") does not satisfy it. A home uniform across all rows
   may be carried once in a sentence above the table instead of a column (#133's
   preamble does this).
4. **reopen trigger** — well-formed per the definition above.

Extra columns are free. A prose list is an acceptable rendering when every item carries
all four semantics. The contract governs records written after it lands; committed
records are frozen history and are never retrofitted.

## Measuring on a real bench

Several records may report measurements taken against a real bench, its run history, or a
real device corpus. Refer to it as "a real bench" and keep protocol examples generic — the
measurement is the point, and the corpus it ran on is not yours to publish.
