"""The staged-append capture writer (issue #43 slice 1, Decision 3).

Slice-1 scaffold (RED collection stub): the module lands before its first
behaviour commit so the capture-writer tests collect against a parent
commit that has no implementation yet. The implemented surface, landing in
this slice:

- ``CaptureStagingStore`` — open/append/finalise/abort/reclaim_orphans/
  used_bytes over the v5 capture-staging tables, on the store's single
  writer connection under the caller-held write gate; ``open_capture``
  check-then-reserves under BEGIN IMMEDIATE with the record's G3 allowance
  formula; ``finalise`` is one explicit transaction (artifact insert →
  staging flip → chunk deletes) with a streaming digest cross-check;
  ``abort`` is a single-transaction delete; the crash-recovery sweep is two
  transactions (mark staged→aborted, then delete) so the mark alone refunds
  the quota ledger.
- ``CaptureQuotaExceeded`` / ``CaptureFinaliseRejected`` live in
  ``benchweave.host.types`` (the gateway exception vocabulary); this module
  raises writer-stamped instances of them.
"""
