# 0001. Retry-stable timing belt fixtures

- **Status:** Accepted
- **Issue:** [BenchWeave #241](https://github.com/madeinoz67/benchweave/issues/241)
- **Decision:** Repository owner approved the scope and publication of this ADR.

## Context

In `tests/integration/test_cross_instance_continuity.py`, `_cell` and `_belt_fresh_generation` supply trial indices to `run_trial`. Its retries create a fresh rig and store using an attempt-specific index. The forced-loose pin assigns factors by the order in which instances first reach `ARigAdapter._pace`. A discarded rig that has already paced consumes a factor. The slot-2 discard case documented in #241 reduces the trimmed planned spread from 80 ms to 40 ms under a 50 ms limit. Three historical failures have the matching missing-assertion signature. Their logs omit the vectors needed to identify the trigger.

## Decision

Assign the forced-loose perturbation by generation and logical trial slot at the test fixture seam. Refresh the existing timing census from attempt-level workflow evidence before selecting further stabilization. Keep broader changes contingent on that evidence.

| Option | Consequence |
| --- | --- |
| Census and diagnostics only | Improves attribution and leaves the known allocation defect. |
| Logical slot allocation plus census | Removes retry order from the planted input while retaining the live rig and the existing gate. |
| Broader suite redesign | Expands validation across multiple timing families before the residual problem is known. |

## Contracts and stability boundaries

- Provide a test-local, optional pace factor defaulting to 1.0. Resolve it from the original logical slot before entering the retry loop and pass the same resolved factor through each fresh rig to the adapter pace seam. Both belt generations use the existing five factors independently, with zero-based ladder position derived from the one-based caller index. Keep the existing attempt-specific index for resource isolation.
- Apply the factor to the real pace argument and retain the plan captured by the original pace implementation. Existing callers keep nominal pacing. No public API, schema, configuration, production code or dependency changes.
- Preserve Section 5's plan-domain gate, trim rule, 25% denominator, one fresh belt generation, and structural failure propagation. Preserve the three-attempt budget and typed retry classification. Keep the serialized CI timing lane.
- When a forced-loose pin fails, report generation, logical slot, retained plan vector and ordered retry sites. Record missing or ambiguous evidence explicitly.

## Implementation and acceptance

1. **Census.** Update the existing issue census with a frozen 100-run workflow window, including all available attempts. Record run and attempt IDs, timing job conclusions and distinct failing test IDs. For each timing-fragile test record the band, driving signal, semantics and disposition. Report missing logs and separate workflow, attempt and distinct-test denominators. This task can run in parallel with the fixture change.
2. **Fixture and regression.** Limit edits to `tests/integration/test_cross_instance_continuity.py`. Force a discarded attempt after pace at ladder position 2 in each generation and assert that the discard actually happened, the retained vectors still contain all five plans, and the production test gate reports both generations in breach. Check the regression against the old allocator and require it to fail there. Audit neighboring pins for the allocation assumption and record their dispositions. Demonstrate that neutralizing the range assertion makes the forced-loose pin fail.
3. **CI evidence.** After the fixture change, read three consecutive completed workflow runs with the timing job executed on the stabilized revision. Retain each attempt and classify any residual failure from the nearest observed cause. A skipped job or a green retry does not stand in for its earlier failed attempt.

## Consequences and rollback

The forced-loose pin remains an end-to-end check of the same measurement with reproducible planned inputs across retries. The change cannot eliminate host starvation or attribute historical failures without evidence. Revert the isolated test commit if nominal pacing or retry behavior regresses, and report the known pin exposure. The census remains valid historical evidence. No migration is required.
