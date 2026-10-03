# Smart Test Gateway: Architecture and device-class contract

**Design baseline:** STG 1.5 · OTDP 0.2.2 · Python adapter API 1.1  
**Scope:** The architecture and the contracts for plugin authors for a qualified embedded-controller bench, including unattended procedures and a separate future mains qualification boundary.

**Status:** Consolidated architecture at the stated scope. Design review is complete. Implementation, live interoperability and bench qualification were not done.

## Read first

| File | Purpose |
|---|---|
| [Architecture](smart-test-gateway-architecture-v1.5.md) | System responsibilities, protection, ownership, recovery and commissioning |
| [Central registry](../standards/registry/0.1.2/registry-specification.md) | Shared packages, discovery, publication, metadata, trust and offline adoption |
| [Registry checks](../standards/registry/0.1.2/validation-report.md) | 68 metadata-contract checks that pass |
| [Procedure and bench contracts](../standards/execution/0.2.0/execution-contract.md) | Bounded execution, wiring and resources, safety policy, commissioning and outcomes |
| [Execution checks](../standards/execution/0.2.0/validation-report.md) | 151 document and schema checks that pass; 6 linked synthetic examples |
| [REST/MCP contract](../standards/interface/0.1.0/interface-contract.md) | 20 REST operations, 17 MCP (Model Context Protocol) tools, authentication and recovery |
| [OpenAPI](../standards/interface/0.1.0/openapi.json) | REST routes and schema references |
| [MCP tools](../standards/interface/0.1.0/mcp-tools.json) | Input and output schemas for the pinned MCP baseline |
| [Interface checks](../standards/interface/0.1.0/validation-report.md) | 256 document and mapping checks and explicit verification limits |
| [Interface errata 1.1.1](../standards/interface/0.1.0/README.md) | D2 amendment: `change_apply` body admits the optional `approver_token`; 1.1.0 bytes untouched |
| [Closure register](architecture-closure.md) | Review disposition, normative versions and qualification boundaries |
| [Registry composition review](acceptance/registry-composition-review.md) | 16 package reuse and compatibility scenarios |
| [Integrated review](acceptance/end-to-end-review.md) | 26 end-to-end cases and resolved cross-contract findings |
| [Decisions](smart-test-gateway-decisions.md) | Selected architectural trade-offs |
| [Device classes](../standards/otdp/0.2.2/device-classes.md) | 12 class profiles, physical semantics, acquisition lifecycle and explicit exclusions |
| [Core specification](../standards/otdp/0.2.2/otdp-specification.md) | Plugin authoring, runtime and host contracts |
| [Extension contract](../standards/otdp/0.2.2/extension-contract.md) | Typed actions, local schema admission and adapter API 1.1 |
| [Transport providers](../standards/otdp/0.2.2/transport-providers.md) | Provider contracts for non-scoped transports: declaration, review tiers and the grant boundary |
| [Measurement model](../standards/otdp/0.2.2/measurement-model.md) | Units, axes, channels, complex and digital data, timing, calibration and uncertainty |
| [Profile catalog](../standards/otdp/0.2.2/device-profile-catalog.json) | 50 actions with exact input and output schemas |
| [Validation report](../standards/otdp/0.2.2/validation-report.md) | 616 document and schema checks that pass, and their limits |

The package also includes these artefact types:

- descriptor, runtime, measurement, catalog and transport-provider schemas
- 12 class descriptor fixtures
- 50 action exchange vectors
- 13 dataset examples
- 6 reference descriptors

Of the 6 reference descriptors, 4 have protocol vectors. 1 descriptor pins a provider contract. 1 descriptor uses an unbacked custom transport. Current normative device contracts are in `otdp/0.2.2/`.

## Device-class coverage

The defined class profiles cover these device classes:

- DC power supplies
- digital multimeters
- oscilloscopes
- logic analysers
- function generators
- electronic loads
- source-measure units
- data acquisition devices
- embedded controllers
- switch matrices
- spectrum analysers
- vector network analysers

Each class profile defines its required base actions and optional features. A device may compose class profiles. Real model restrictions narrow the standard schemas, and shared hardware remains subject to shared ownership. The class profile states required quantities, lifecycle rules and failure evidence.

This is a bounded class baseline, not universal feature coverage. AC power sources, radio-frequency (RF) conversion and modulation families, cameras, environmental chambers and other specialised devices need more class profiles. GPIB, USB-HID, arbitrary USB bulk and vendor SDKs (software development kits) need separately admitted host-provider contracts (transport-providers.md). Structural fixtures are neither implemented plugins nor qualified instruments.

## Procedure and bench provision

Execution contract 0.2.0 adds 6 schemas for procedures, benches, safety policies, commissioning, run bindings and run records. Logical roles make a procedure portable across separately qualified fixtures. Bounded control flow, explicit measurement validity and a required verified safe end support unattended execution.

A procedure may capture data. For this, the release adds the closed capture step kind and its capture allow-rule kind. The step kind is role-bound. It carries `format`, `sample_count` and `max_bytes`, and holds the capture budget in `timeout_ms`. Later steps reference the landed capture manifest through `$stg_ref` (`/capture_id`, `/artifact_id`, `/sha256`).

The fixtures are synthetic. The package supplies no actual bench limits or qualification.

## Central registry provision

Registry contract 0.1.0 adds immutable release manifests, mutable release status and local dependency locks, each with a schema and synthetic metadata example. Users can share profiles, descriptors and implementations through a public catalogue or private mirror. The gateway retains local admission and offline execution authority. The package defines this architecture. It does not deploy a central registry.

## Handoff to an AI coding agent

Supply this entire package together with the instrument's protocol manual, model and firmware details, and available reference exchanges:

> **WARNING:** DO NOT ENERGISE EQUIPMENT WHEN YOU AUTHOR CODE. DO NOT MODIFY BENCH SAFETY LIMITS.
>
> 1. Search configured registries first for compatible existing integrations. Then reuse, contribute or fork with attribution.
> 2. For a new integration, create an STG device integration for OTDP 0.2.2 and adapter API 1.1.
> 3. Read these documents: the core specification, the extension contract, the applicable device classes, the measurement model and the schemas.
> 4. Select supported class profiles. Declare real channels and device constraints. Implement all claimed actions with verified protocol evidence.
> 5. For registry publication, also supply the release manifest and the evidence required by registry contract 0.1.1.
> 6. Bundle the pinned local contracts. Then deliver the descriptor, the adapter where it is needed, the dependencies, the tests and the evidence.
> 7. Apply the semantic and conformance obligations of the specification and the applicable class and dataset checks.
> 8. Report missing device facts. Do not invent commands or unsupported capabilities.
> 9. Distinguish mock conformance from live qualification.

These documents define the interfaces. This package does not include a gateway host or plugin implementation. Schema validation does not prove lifecycle correctness, protocol truth, hardware compatibility or physical protection.

## Implementation and commissioning evidence still required

Build and exercise the gateway and plugins against these contracts. Supply actual device protocol evidence, model limits and hardware qualification. Commission the voltage, current, power and energy envelope of the bench. Also commission its safe transition, its response time and its unattended procedures. Future mains-powered fixtures need separate qualification.

From the 0.1.0 baseline forward, the corpus retains superseded versions digest-frozen beside their successors (see `standards/GOVERNANCE.md`). The reset's pre-baseline lineage lives in git.

## Baseline verification

1104 document and schema checks and selected semantic and coverage checks passed: OTDP 616, registry 64, execution 151, interface 256 and closure 17. These checks are not a complete runtime or hardware conformance suite. These counts record the architecture review baseline. They are not results from the repository CI (continuous integration).
