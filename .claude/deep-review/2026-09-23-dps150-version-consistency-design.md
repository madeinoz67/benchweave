# dps150 version consistency across three consumers — slice-level design

- Date: 2026-09-23
- Status: design (pre-implementation; this record is the builder's commit one)
- References: CON-10 (`docs/internal/invariants.md`), `standards/GOVERNANCE.md`
  ("Bump mechanics — copy, never move"), gateway issue #147 (the landing that
  surfaced this), `tests/sdk/test_descriptor_equivalence.py`, `.github/workflows/device-plugins.yml`
- Grounding window: main at `89e6b86` (dps150 `otdp_version` 0.2.0, reverted by
  `dfff55b`); pinned SDK submodule `6121c96` (vendors `standards/otdp/0.2.2/`
  only). All behavior claims below were reproduced in a worktree cut from
  `origin/main` with the submodule at its pinned SHA — the shared checkout was
  NOT used, because its submodule working tree sat at `909150c` (vendor
  `0.1.0`), which would have produced evidence about the wrong checker.

## Owner summary (BLUF)

**Verdict: BUILD — restore the 0.2.2 stamp cascade half that `dfff55b` undid,
and complete the half `b99b47b` left out (the evidence lock).** The three
consumers are not three opinions: two independent mechanisms *force* a single
consistent triangle, and the tree is currently outside it. `dfff55b`'s stated
premise is contradicted by the diff it sits next to — `b99b47b` did NOT leave
dps150 untouched; it stamped the descriptor 0.2.0 → 0.2.1 and left only the
*lock* at 0.2.0, which is precisely the half-sweep that put the
`device-plugins` lane red from `b99b47b` onward.

## 1. The forced triangle (verified, not inferred)

Three version facts about dps150, and the mechanism that equates them:

| Fact | Where | Enforced by |
|---|---|---|
| `descriptor["otdp_version"]` | `plugins/fnirsi/dps150/src/benchweave_fnirsi_dps150/descriptor.json` + `descriptor.py` | — |
| `lock["otdp_version"]` / `lock["directory"]` | `plugins/fnirsi/dps150/contracts/lock.json` | `test_descriptor_schema_and_package_evidence` validates the descriptor against `contracts/<dir>/otdp-device-descriptor.schema.json`, whose `properties.otdp_version` is `{"const": "<that version>"}` |
| active OTDP version | `standards/standards-manifest.json` otdp entry | CON-10: gateway `_descriptor_validator` resolves the **active** descriptor schema; `benchweave-sdk check` validates against its vendored tree |

Equations the tree already commits to:

- **descriptor == lock**, because the dps150 lane validates the descriptor
  against the lock's schema and that schema pins `otdp_version` by `const`.
  This is not policy — it is what `jsonschema` does with the document.
- **descriptor == active**, because CON-10 is "One descriptor dialect,
  projected": gateway admission and `benchweave-sdk check` both resolve the
  active schema, and the equivalence census pins the two gates equivalent.

Therefore **lock == descriptor == active**. There is no degree of freedom here;
a tree outside the triangle is broken by construction, in at least one lane.

## 2. What the state machine actually was (the historical puzzle, resolved)

The brief held that dps150 sat at `0.2.0` "through the entire 0.2.1 era" with
the equivalence arm green. The commits say otherwise — `git show` the
`otdp_version` line at each of the four relevant commits:

| commit | descriptor `otdp_version` | lock | active | equivalence | `device-plugins` |
|---|---|---|---|---|---|
| `5346599` | 0.2.0 | 0.2.0 | 0.2.0 | green | green |
| `b99b47b` | **0.2.1** | 0.2.0 | 0.2.1 | green | **red** |
| `7d08055` | **0.2.2** | 0.2.0 | 0.2.2 | green | **red** |
| `dfff55b` | **0.2.0** (revert) | 0.2.0 | 0.2.2 | **red** | green |

`b99b47b`'s own message is explicit about the split it chose: *"Stamped 0.2.0
-> 0.2.1: … dps150 descriptor.json + descriptor.py … The dps150
contracts/lock.json stays at 0.2.0 by design."* The descriptor half was
stamped; the lock half was not. `test_adapter.py` already carried
`SCHEMAS = ROOT / "contracts/otdp-0.2.0"` and
`test_descriptor_schema_and_package_evidence` at `5346599` — unchanged through
`b99b47b` — so that lane was red at the 0.2.1 and 0.2.2 stamps.

That redness was missed, not absent: `dfff55b`'s own process note discloses
*"both merges went in on incomplete check verification (watch tail, not the
rollup)"*. The only state in which both lanes were green is `5346599`, where
all three facts were 0.2.0.

**So the equivalence arm was never green with a stale dps150 stamp.** It went
green each time the descriptor was stamped to the active version. Replicating
"what made it green then" is therefore the stamp cascade — not version-matched
schema resolution.

## 3. The resolution weighed

**(a) Re-pin dps150 to 0.2.2** — descriptor + evidence lock + certification
story. *Chosen.*

**(b) Version-matched schema resolution** — the checker resolves the
descriptor's declared version against the retained corpus. *Rejected.*

Why (b) loses, on evidence rather than taste:

1. **CON-10 exists to forbid exactly this.** Its italic close is the failure
   mode (b) recreates: *"Two gates built against two notions of 'a descriptor'
   with no shared authority is how zero of four in-tree descriptors were both
   check-clean and admissible (#63 §1); one dialect plus a projection is the
   structural fix."* Teaching the two gates to resolve *different* schemas for
   the same document re-opens #63's fork.
2. **The SDK leg is structurally unbuildable under (b).** The pinned SDK
   (`6121c96`) vendors `src/benchweave_sdk/standards/otdp/0.2.2/` **only** —
   version-first single-version vendoring, confirmed by `git ls-tree`. Its
   `validate_descriptor` hardcodes `otdp/0.2.2/otdp-device-descriptor.schema.json`.
   Resolving a declared `0.2.0` needs 0.2.0 schema bytes the SDK does not and
   will not carry. The gateway's retained multi-version tree is the
   `copy, never move` half of GOVERNANCE; the SDK's single-version tree is the
   same one-dialect policy expressed on its side.
3. **The green history is evidence against (b).** §2 shows the 0.2.1-era green
   arrived via `b99b47b`'s stamp, not via version-matched resolution. The
   mechanism (`_descriptor_validator`, introduced `3e605e8`) has derived the
   active schema from the manifest since inception — its body is byte-identical
   to today's.

One refinement to the framing in the brief: (a) does **not** kill the retained
0.2.0 corpus. `copy, never move` keeps `standards/otdp/0.2.0/` digest-frozen in
the tree and `test_dps150_lock` keeps verifying the lock against whatever
corpus the lock names. What moves is the plugin's *certification pin*, because
the plugin itself moved dialects. Re-certifying at 0.2.2 is honest only because
the tests re-run against 0.2.2 bytes — which is what re-pinning the lock makes
happen (`fetch_contracts.py` and `conftest.py` both derive their destination
from `lock["directory"]`, version-agnostic).

## 4. The slice

1. `descriptor.json` + `descriptor.py`: `otdp_version` → `0.2.2` (restores
   `7d08055`'s two lines exactly).
2. `contracts/lock.json`: re-pin `directory` → `standards/otdp/0.2.2`,
   `otdp_version` → `0.2.2`, `revision` → `a103a4cf21d817a2e1b4f5ddbc749c56aceea801`
   (the commit that froze the 0.2.2 bytes; verified ancestor of `origin/main`,
   digests byte-match the working tree), `sha256` → the 0.2.2 tree's eight
   digests (computed from file bytes, not hand-typed).
3. `tests/test_adapter.py`: `SCHEMAS` derives from `lock["directory"]` instead
   of the hardcoded `contracts/otdp-0.2.0` literal — the stale-cite class
   `dfff55b` already fixed in `scripts/sdk_smoke.py` for the same reason.
   Module docstring names the locked corpus rather than a version literal.
4. New parent-side guard `tests/contract/test_plugin_descriptor_dialect.py`
   stating the triangle directly, so both halves surface in the `ci` gates
   rollup (this episode's process failure was one red lane in a *separate*
   workflow that nobody's rollup showed).

## 5. Pre-committed acceptance rule

The change is accepted iff, in one run:

- `tests/sdk/test_descriptor_equivalence.py` is **62 passed, 0 failed** (the
  three failures named in the report — `clean-dps150`,
  `issued-map-unknown-action-dps150`, `test_clean_cells_project_the_execution_view`
  — all gone), and
- `cd plugins/fnirsi/dps150 && UV_PROJECT_ENVIRONMENT=venv uv run pytest tests/`
  is **247 passed, 0 failed**, and
- the new guard is red on the pre-fix tree and green on the post-fix tree, and
- `uv run ruff check .`, bare `uv run mypy`, and `uv run pytest -q` are clean.

## 6. What this does NOT do

- It does not make the stamp cascade mechanical. The cascade remains a
  hand-walked obligation in `docs/internal/drift-and-obligations.md`; the new
  guard names one cell of it.
- It does not teach the gateway to admit non-active dialects. A plugin
  certified at a superseded version remains inadmissible under CON-10 — that is
  the invariant, and this slice does not reopen it.
- It does not cover `fixtures/execution/descriptor-sim-*.json`; those move
  with the digest lattice (bench → commissioning → run-binding), pinned by the
  bootstrap suite, and are untouched here.
- `descriptor_version` stays `0.2.0`. It is the plugin's own descriptor
  document revision (CON-10's projection surfaces it as `version`), not an
  OTDP dialect tag; `b99b47b` and `7d08055` both left it alone.
- **Deferred, pre-existing, not caused by this diff:** `docs/device-developer-guide.md`
  still carries the 0.2.2 train's unstated drift — the baseline line and the
  authoring checklist instruct `Use OTDP 0.2.0` (line ~121), and four corpus
  links point at `../standards/otdp/0.2.0/` (lines ~31, ~117). Under CON-10 a
  0.2.0 descriptor is refused by both gates, so that instruction would
  reproduce this failure for the next device author. The links are not broken
  (`copy, never move` retains the tree); they are superseded. Fixing them is a
  version-literal sweep belonging to the 0.2.2 train's obligation-3 walk, and
  folding it here would make this PR's cause non-single. Also unstated there:
  the triangle in §1 — the guide documents the contracts-lock pattern but never
  says the lock's corpus, the descriptor's `otdp_version` and the active version
  are one version. Both findings are reported, not fixed.
