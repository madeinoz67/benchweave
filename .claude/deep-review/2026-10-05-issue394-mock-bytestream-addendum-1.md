# Addendum 1 — issue #394 design of record: fold corrections

**Date:** 2026-10-05 (post four-lane review battery: resident code-reviewer, adversary lanes 1 and 2, mechanism-critic)
**Record amended:** `2026-10-05-issue394-mock-bytestream.md` (frozen; corrections append here, per the invariants file's own amendment discipline)
**Carrier branch:** `feat/issue394-mock-bytestream` (SDK side, commits `3973ce9`..`e8fdd95` and following)

The review battery's verdict — mechanism core defended; 4 MEDIUM defects + evidence-layer gaps folded — and the controller's three rulings required the following corrections to the record's text. Each carries one sentence of evidence.

**(a) §8's selector-only RED-control prescription was mechanically unsound.** The typed `standalone_vectors_*:` prefixes live in the parse layer (`vectors_script`), not the selector, so neutralizing only the selector leaves families D/B2 green — the canonical control is the full-mechanism revert, which lane 2 executed (11/13 RED, every D cell reddening); the builder's own merge-base run showed the honest mixed shape (5 symptom failures + 8 `capture_root` signature failures, 0 collection errors), and the builder's surgical control (merge-base `mock_exchanges` + selector bodies, parser intact) reproduced the pre-fix `KeyError: 'request'` shape with 12/39 seam-level cells failing.

**(b) §1.3's "inherited ConformanceError" for non-stream kinds is false.** Those kinds hit the shared `_FIELDS` strictness first and refuse `ValueError("not a section 8.1 stream transaction")` IDENTICALLY on backend and mock — the stronger parity property; it stands (pinned by `test_field_sets_are_strict_and_shared_with_the_backend`).

**(c) §1.3 omitted the capture mechanism.** The byte-stream host serves the five capture members through `WriterBackedCaptureServices`, extracted verbatim from `SerialCaptureServices` (one definition, two hosts), with `capture_root` threaded through `mock_plugin_session` the way `serial_plugin_session` threads it — required by §2/§9-A4 but unstated in §1.3's mechanism list.

**(d) The record's literal advance rule looped on all-response-only scripts.** The shipped once-per-advance bound was the right instinct, and this fold's release-once rule supersedes both: `_advance` never recycles; the restore happens in the send path, re-armed only by request-bearing consumption, so a drain returns the captured burst once per cycle and then quiets (lane 1 measured ~268k frames/s of hot spin under the old rule).

**(e) §10's keyword table is corrected.** Actuals: `threading` 2, `sha256` 6, `hashlib` 2, `asyncio` ~29 — the tier is unchanged (Tier 3; the triggering rules were already satisfied).

**(f) Family E's serial leg is a `_ReplyPort` ring**, not the `LoopbackPort` fixture §0 named — functionally the §9 intent (same wire bytes, same take semantics through a real `SerialLink`), and the loopback precedent's shape.

**(g) §1.5's "holds until the operation's own deadline" is false as literal mechanics.** The immediate raise on an unservable receive is deliberate (outcome parity, no timing) and is now guide-disclosed with its consequence: a rehearsal over the mock proves NO `timeout_ms` budget fit — budget-fit evidence is hardware-only (a note the controller posts on gateway #285).

**(h) The minted `_cycle_start` heuristic (LAST repeated request) is replaced by controller ruling 1.** It was structurally broken — any row after the last repeated request is by construction novel, so the derived cycle could never contain a repeating multi-request cycle; `[ID, CH0, CH1]×3` (the reporter's own device class) mismatched on the second sweep blaming a correct adapter. The replacement is minimal-period detection: the shortest suffix-unit that, repeated from the establishment boundary, regenerates the captured tail exactly (compared by `(request, response)` byte pairs, never diagnostic names), with two full units of evidence and a request-bearing row in the unit; mid-unit captures restore ROTATED to the captured phase; no derivable period falls back to `LoopingMockHost`'s head-of-one rule (the guide: capture at least two full poll cycles).

**(i) Default-dialect coercion restored per controller ruling 2.** Lane 1 proved a real compat break: numeric rows (`{"request": 42}`) connected and rehearsed at the merge base through `str()` coercion; the branch had refused them. The `stream_exchange` dialect with ASCII payloads coerces non-string payloads through exactly the merge base's expression; the strict string requirement applies only where decoding needs a string (`send_receive`, or a row overriding its encoding to `hex`).

**(j) The silent-descriptor ceiling is shared per controller ruling 3.** The record said 64 KiB while the mock minted a 128-byte fallback and the serial session used 4096; `transport_ceiling(settings)` is the one resolution both hosts clamp through — the descriptor's declared bound, session fallback 4096 when silent, clamped by the backend's 64 KiB transfer ceiling.

**Mechanism defects folded alongside (each RED-first on the SDK branch):** refuse-before-mutation (critic F2 — the validation ladder: grammar, bounds, payload type, liveness, closed, marker, then state); close-path receive parity (critic F3 = lane 1 F8 — a buffered COMPLETE frame delivers after close, a partial refuses); `assert_complete()` teeth (lane 1 F4 + critic F5 — it read the always-empty exchange deque and certified exhaustion over an un-exhausted script); expired-context ordering (lane 1 F9 — bounds outrank liveness); the G cell's subset assert (lane 2 F2 — equality per the nowrite precedent); `test_e5`'s wall-clock assert dropped (resident L1 — the record's own §1.5 rules timing asserts out).
