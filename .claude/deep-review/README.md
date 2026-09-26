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

Normative status of the weak form: a trigger whose subject is inspectable but whose
firing predicate is the deferrer's judgement ("a profile whose fetch semantics need
acquisition dedup", #146 §6 row 5 as written — the subject, an admitted profile, is
inspectable; "need" is judgement) is **conforming and weak**. Refused is the trigger
that names no thing to be seen at all: "when it becomes important", "if needed",
"when we have time", "when telemetry shows it matters" (telemetry is a surface, but
"matters" names no thing on it). The discriminator: a well-formed trigger names the
observable thing that would be seen — an arrival, a declaration, a trace, a log
line, a repeated failure; judgement about a named thing is weak, absence of the
thing is refusal. An owner-fired trigger is well-formed when it names the thing
asked for — the ask is the event, and its object makes it decidable ("the owner
asks for published retrospectives" fires when that ask arrives; bare "when the
owner asks", with no object, is refused). Naming the channel the call arrives on
(or stating that none is predetermined) is the recommended strong form, not a
well-formedness requirement.

Weak sharpens to strong by naming the thing and the inspection procedure: #146 row 5
becomes "an admitted or dogfood-published profile declaring an acquisition-lifecycle
fetch family whose procedure shape re-fetches the same acquisition across steps — a
real procedure that today would double-publish under two `ds:` ids" (#231 §3.3). The
strong form additionally names its **nearest plausible carrier** — the arriving work
or train most likely to carry the reopen (#231 §5's table shape); naming the carrier
is recommended, not required.

**Deferral table row — required semantics (four):**

1. **identifier** — a stable row id; later GO/CLOSE passes and follow-on records cite
   rows by it (#231's lineage cites "#146 rows 1, 5 and 7" — a table without ids cannot
   be cited).
2. **deferred** — the bounded thing deferred.
3. **home** — where this deferral lives under the skill's rule: "follow-on issue #N" or
   "documentation here". These two strings are exemplars of the two legal homes, not
   an exhaustive value format: a home value designates which of the two it is, in
   whatever words name its place ("SDK-side note in slice 1's PR" designates
   documentation); a carriage sentence, being deixis-prone, must use the vocabulary
   outright. The column may be labelled Home or Carrier (both in active
   use); a rationale column ("Why") does not satisfy it. A home uniform across all
   rows may be carried once in a sentence adjacent to the table (above or below)
   instead of a column — and the sentence must designate the home in this rule's own
   vocabulary ("documentation …" / "follow-on issue #N"), not imply it by deixis:
   #133's "(documentation deferrals; no scheduled carrier)" counts; #67's "every
   deferral lives here" does not.
4. **reopen trigger** — well-formed per the definition above.

Vocabulary: "carrier" bears two senses in-tree — the nearest plausible carrier of a
trigger is the future work that would carry the reopen (a train, an admission); a
"Carrier" column header in a deferral table is a label for the home. They never both
bind one use: in a deferral table the Carrier column is the home; a carrier-worded
column in another shape (a fire-condition table like #231 §5's) carries the
future-train sense.

Extra columns are free. A prose list is an acceptable rendering when every item carries
all four semantics. The contract governs records written after it lands; committed
records are frozen history and are never retrofitted.

## Measuring on a real bench

Several records may report measurements taken against a real bench, its run history, or a
real device corpus. Refer to it as "a real bench" and keep protocol examples generic — the
measurement is the point, and the corpus it ran on is not yours to publish.
