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

## Measuring on a real bench

Several records may report measurements taken against a real bench, its run history, or a
real device corpus. Refer to it as "a real bench" and keep protocol examples generic — the
measurement is the point, and the corpus it ran on is not yours to publish.
