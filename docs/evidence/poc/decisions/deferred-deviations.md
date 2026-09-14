# Deferred deviation registrations — the interface-errata slice (WP09)

**Two deviations are accepted for the G2 claim with resolution
deferred to a dedicated future interface-errata slice.** Both are
client-visible payload reshapes: collapsing either inside an
acceptance work package would change every envelope or event clients
see as a side effect, when the pre-release window (contract §12: no
compatibility claim, no deployed clients) belongs to a slice that
owns the interface surface deliberately. Registered 2026-09-14, WP09
Task 10; the evidence tree's index binds this record's digest
(Task 11) and the G2 gate record names both registrations (Task 12).

## D4 — event-evidence reshape (the legacy free-form family)

**State at registration.** The seam emits free-form evidence dicts
while the contract's `evidence` def is a closed
`{id, version, sha256}` document ref. The D12 exception reconciled
the first kind (`authority_changed` emits the closed ref exactly —
the takeover pins the binding document, the release the commissioned
bench configuration); the legacy free-form family remains, pinned
per-family by
`test_interface_parity.py::test_event_evidence_shape_deviation`. The
def's `stream_id` violation was fixed separately in WP08
(`bench.{bench_id}` dot-form, `5173d61`).

**Registration.** ACCEPTED G2 DEVIATION; resolution deferred to the
interface-errata slice.

**Rationale.** Reshaping emitted event evidence is a client-visible
change to every event on the wire — each event kind's payload would
be recast as the closed document ref at once, so consumers keyed to
the free-form shapes (tests, SDK renderings, any early scripts) all
move together. That is an interface-version decision — which kinds
carry which document refs, and whether the closed def itself grows —
and it deserves a slice that designs the mapping kind-by-kind against
the corpus instead of inheriting whatever an acceptance package had
time to reshape. Pre-release, with no deployed clients, is exactly
the window in which to do it deliberately; deferring costs nothing
but calendar.

## D14 (details half) — the six-key error `details` envelope

**State at registration.** The rendered error envelope serves
`details: {}` on every failure while the vendored `$defs/error`
requires the six closed keys (findings, current_revision, stream_id,
oldest_sequence, current_sequence, retry_after_ms); only run_check's
findings ride it today, free-form. The correlation_id half is CLOSED
(WP09 Task 1, `3ebfcb5` — every envelope mints a real id); the
`details` half is pinned as the rendered (not contract) shape by
`tests/unit/test_error_model.py::test_failure_body_is_the_rendered_error_envelope`.

**Registration.** ACCEPTED G2 DEVIATION; resolution deferred to the
interface-errata slice (the same slice as D4).

**Rationale.** Populating six closed keys on every failure envelope
reshapes every error response on both transports at once — every
failure site must decide what its findings/revision/stream/sequence
values are, which is contract semantics, not rendering polish. Doing
it piecemeal inside an acceptance package would land half-populated
keys (worse than an honest `{}`) or block the G2 close on a
whole-envelope audit; the errata slice owns the envelope surface
deliberately, alongside D4's event payloads, in the same
interface-version decision.

## Ledgered, not errata-bound: D15 / D16

D15 (the `lease_create` §9 replay-peek asymmetry) and D16 (the
session-wide admission-lock identity) are **not** interface errata —
D15 is a corpus-permitted behavioral asymmetry, D16 an internal
design question with no wire divergence — so neither is registered
here. Both stay ledgered as accepted G2 deviations and take their
registration in the G2 gate record
(`docs/evidence/poc/g2-gate-record.md`, Task 12).
