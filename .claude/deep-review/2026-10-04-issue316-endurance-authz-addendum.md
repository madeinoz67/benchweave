# Issue #316 — endurance-authz design record: fold-wave addendum

**Date:** 2026-10-04
**Amends:** `2026-10-03-issue316-endurance-authz-design.md` (frozen — this addendum
corrects it; the record's bytes do not move)
**Origin:** the two post-push refute lanes' fold wave (no authorization bypass found on
any attack; every seam-skip shape refuses authoritatively at the worker).

## A1 — §2.2 correction: the seam's skip family is the floor's WHOLE family

The record's §2.2 names only "an unstored procedure/commissioning document" as what the
seam does not decide. The gate lives inside `_assert_run_runnable` AFTER the #260 floor's
own early returns, so the skip family is the floor's entire one: an **unstored bench pin,
an unstored descriptor pin, an unstored procedure or an unstored commissioning document**
each skips the seam's whole pre-check, the grant included — even when the procedure and
commissioning ARE stored and the grant is absent (lane-repro'd: grant-absent lattice +
binding whose bench sha256 names nothing stored → the POST 202-accepts; the worker
refuses → `outcome_unknown`; no bypass — the wire layer alone says accepted). CTL-10 and
the operator-guide row now name the full family; the record's §2.2 wording was wrong on
this point, understating the disclosed skip surface.

## A2 — §2.2 addition: the seam does not evaluate the grant's SCOPE

The seam reads `modes`/evidence/`expires_at` from the pinned commissioning but performs
no `procedure_refs` containment — that is the worker pin lattice's (`pin_absent:`).
A second stored procedure + binding under a grant whose `procedure_refs` lacks it
seam-accepts and worker-refuses (lane-repro'd). A lease presented on such a start is
consumed for a doomed run — the same disclosed shape as the unstored-binding path.
Disclosed in CTL-10 and the operator-guide row.

## A3 — §6 wording: the window boundary is "cannot exceed" (equality admits)

The helper implements `now + max_body + max_protection > expires_at` — strict — so a
window ending EXACTLY at `expires_at` admits. The record's §6 CTL-10 draft ("must fit
inside") and the operator-guide's first wording ("must end before") both overstated the
boundary by one instant. The contract's own clause (execution-contract.md:131, "the full
body plus protective budget cannot exceed the valid qualification interval") is what is
implemented; both docs now say that.

## A4 — fold-wave code corrections (beyond the record)

- **NIT-1:** the datetime COMPARISONS (not just construction) now ride the fail-closed
  typed clause — a naive `expires_at` against an aware `now_wall` previously raised a
  raw `TypeError` at the comparison (unreachable in production: admission's
  FormatChecker enforces offset date-times in both dialects and every production
  `now_wall` is Z-stamped). The window leg gained its own clause for the
  `OverflowError` class (execution 0.1.0 caps neither budget field; a schema-valid
  huge budget overflowed `timedelta` construction). Prefix mapping unchanged from the
  slice's deviation-4: the check that needed the value owns the refusal
  (`qualification_expired:` / `qualification_window_exceeded:` with cannot-be-compared
  wording).
- **LOW-2:** two pin arms now drive the REAL `RunWorker` thread wired to the real
  `_build_run_factory` — (i) manual+lease through `run_start` → the worker reads
  `lease_present` from the seam-created run row's `authority` → completed `passed`;
  (ii) the marginal window across skewed clocks (seam equality admits; worker +1 s
  overshoots) → seam 202 → worker `AdmissionRejected` inside the thread → terminal
  projection, no terminal record (`outcome_unknown`), the typed reason on the poison
  log line. Both were lane-probe-verified true before the pins existed.
