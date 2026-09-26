# Start here — PoC/MVP product and implementation planning

**Product first:** [PoC/MVP PRD](00-poc-mvp-prd.md)

The confirmed first instrument is **FNIRSI DPS-150**. **ESP32** is the provisional controller family; exact board/firmware is still a hardware gate. Prove the workflow in simulation, then qualify one real fixture for unattended use.

| Read order | Document | Purpose |
|---|---|---|
| 1 | [PoC/MVP PRD](00-poc-mvp-prd.md) | User value, scope, requirements, success criteria and stage gates |
| 2 | [Delivery plan](01-delivery-plan.md) | Twelve ordered work packages, proposed repository boundaries and requirement traceability |
| 3 | [Hardware discovery](02-hardware-discovery.md) | DPS-150 evidence, reuse candidates, profile compatibility and provisional ESP32 fixture |
| 4 | [First implementation slice](03-first-slice-plan.md) | Concrete proposed code/test task for exact-byte document integrity |
| 5 | [Planning review](planning-review.md) | Coverage/link/syntax checks and limits of this planning work |

Other lane planning: [Contributor publishing path PRD (issue #209)](07-contributor-publishing-prd.md) — requirements for the third-party plugin publishing lane (Draft v0.3, ruled 2026-09-26). Also: [Standards dependency management PRD (issue #203)](08-standards-dependency-management-prd.md) — requirements for standards version pinning and dependency management (Draft v0.2, ruled by proceed-direction 2026-09-26).

Design records: [standards dependency management](09-standards-dependency-design.md) (slices #215-#221) and [contributor publishing](10-contributor-publishing-design.md) (slices filed under #209).

The [STG 1.5 architecture](../smart-test-gateway-architecture-v1.5.md) remains the technical contract. This planning pack does not alter its qualification boundaries or constitute an implemented PoC. The first slice is expanded; following packages are expanded into code-level tasks as their dependency gates are resolved.

The BenchWeave repository now contains a Python scaffold and CI workflows. Functional plugins, firmware and services remain to be implemented. Product targets are proposed acceptance criteria, not measured results. Hardware operations require their own commissioning setup and evidence.
