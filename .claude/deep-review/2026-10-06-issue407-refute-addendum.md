# Issue #407 design record — refute-wave addendum (2026-10-06, dated)

The record's bytes are frozen (committed as the branch's first commit);
this dated addendum carries the corrections the refute lane produced.
The record remains the authority for everything it does not contradict.

## A1. The swap is serialized (amends §2.1 "The swap")

`reconfigure_link` holds an asyncio lock across the guard re-check, the
close, the opener and the rebind. The record's guards read the CURRENT
link; without serialization two concurrent switches both pass the
guards and interleave catastrophically (observed classes: one twin
closes the other's freshly minted link; a loser's transport orphaned
with its reader alive forever; a ConnectionError answered while a
healthy link serves — falsifying the documented no-link posture).
Serialized, the loser's swap closes the winner's link through the
normal `old.close()` path and a failure answer genuinely means no link.

## A2. The deadline is re-checked after the opener too (amends §2.1)

The record checked the deadline after the close only. A reopen that
outlives its context now closes the port it opened, publishes the
failed row, and answers `TimeoutError` — never success. A port opened
past its deadline must not silently become the session's link.

## A3. Cancellation publishes (amends §2.1 "Failure posture")

The opener runs under a BaseException handler with an opened-list
cleanup: a cancellation publishes the failed row and closes what the
opener produced before propagating. Disclosed residual (unchanged in
kind from the record's risk 3): a cancel landing while the thread is
still inside a blocked opener cannot reach the produced transport; the
host's own timeout enforcement sits at the same await boundary.

## A4. The F3 owner-fork wording is false for exactly one key (amends §9 F3)

`device_get`'s overlay is additive EXCEPT for `link` itself: an
adapter-reported `identity["link"]` wins, and the host's block fills
the gap only when the adapter did not report one. The record's
"overlay" wording, read literally, clobbered that key.

## A5. Derived baud reads are defaulted (amends §2.1.1)

The session mint always carries the defaulted boot baud and every
derived read goes through the same defaulted getter: a descriptor whose
`transport.settings` omits `baud` is legal (the opener defaults it) and
worked at base. The branch's first cut indexed `settings["baud"]` and
KeyErrored `host_info`, `device_get` and every switch — a regression
the refute lane caught, folded RED-first.

## A6. Link-down serves null (amends §2.1 state block)

`link_state()` serves null whenever the current link is closed — a
live-looking baud with nothing serving it would be a lie (A06). The
schema's null arm covers both "no link configured" and "no link
serving".

## A7. The boot baud validates like the declared list (amends §2.1.1)

Both baud inputs (boot and declared list) validate structurally:
positive non-bool ints, typed refusals (`standalone_serial_boot_baud:`
joins the prefixed refusal family). A bool boot baud would otherwise
admit the set `{1}` silently.

The refute cells live in the SDK repo's
`tests/server/test_reconfigure_folds.py` (nine cells, RED-first; the
RED evidence is quoted in the SDK branch's fold commits).
