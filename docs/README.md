# Smart Test Gateway — Architecture and device-class contract

**Design baseline:** STG 1.5 · OTDP 0.2.2 · Python adapter API 1.1  
**Scope:** Architecture and plugin-authoring contracts for a qualified embedded-controller bench, including unattended procedures and a separate future mains qualification boundary.

**Status:** Consolidated architecture at the stated scope. Design review is complete; implementation, live interoperability and bench qualification have not been performed.

## Read first

| File | Purpose |
|---|---|
| [Architecture](smart-test-gateway-architecture-v1.5.md) | System responsibilities, protection, ownership, recovery and commissioning |
| [Central registry](../standards/registry/0.1.1/registry-specification.md) | Shared packages, discovery, publication, metadata, trust and offline adoption |
| [Registry checks](../standards/registry/0.1.1/validation-report.md) | 64 passing metadata-contract checks |
| [Procedure and bench contracts](../standards/execution/0.2.0/execution-contract.md) | Bounded execution, wiring/resources, safety policy, commissioning and outcomes |
| [Execution checks](../standards/execution/0.2.0/validation-report.md) | 151 passing document/schema checks; six linked synthetic examples |
| [REST/MCP contract](../standards/interface/0.1.0/interface-contract.md) | Twenty REST operations, seventeen MCP tools, authentication and recovery |
| [OpenAPI](../standards/interface/0.1.0/openapi.json) | REST routes and schema references |
| [MCP tools](../standards/interface/0.1.0/mcp-tools.json) | Input/output schemas for the pinned MCP baseline |
| [Interface checks](../standards/interface/0.1.0/validation-report.md) | 256 document/mapping checks and explicit verification limits |
| [Interface errata 1.1.1](../standards/interface/0.1.0/README.md) | D2 amendment: `change_apply` body admits the optional `approver_token`; 1.1.0 bytes untouched |
| [Closure register](architecture-closure.md) | Review disposition, normative versions and qualification boundaries |
| [Registry composition review](acceptance/registry-composition-review.md) | Sixteen package reuse/compatibility scenarios |
| [Integrated review](acceptance/end-to-end-review.md) | Twenty-six end-to-end cases and resolved cross-contract findings |
| [Decisions](smart-test-gateway-decisions.md) | Selected architectural trade-offs |
| [Device classes](../standards/otdp/0.2.2/device-classes.md) | Twelve class profiles, physical semantics, acquisition lifecycle and explicit exclusions |
| [Core specification](../standards/otdp/0.2.2/otdp-specification.md) | Plugin authoring, runtime and host contracts |
| [Extension contract](../standards/otdp/0.2.2/extension-contract.md) | Typed actions, local schema admission and adapter API 1.1 |
| [Transport providers](../standards/otdp/0.2.2/transport-providers.md) | Provider contracts for non-scoped transports: declaration, review tiers and the grant boundary |
| [Measurement model](../standards/otdp/0.2.2/measurement-model.md) | Units, axes, channels, complex/digital data, timing, calibration and uncertainty |
| [Profile catalog](../standards/otdp/0.2.2/device-profile-catalog.json) | Fifty actions with exact input/output schemas |
| [Validation report](../standards/otdp/0.2.2/validation-report.md) | 616 passing document/schema checks and their limits |

The package also includes descriptor, runtime, measurement, catalog and transport-provider schemas; twelve class descriptor fixtures; fifty action exchange vectors; thirteen dataset examples; and the six reference descriptors (four with protocol vectors, one pinning a provider contract, one an unbacked custom transport). Current normative device contracts are in `otdp/0.2.2/`.

## Device-class coverage

The defined profiles cover DC power supplies, digital multimeters, oscilloscopes, logic analysers, function generators, electronic loads, source-measure units, data acquisition devices, embedded controllers, switch matrices, spectrum analysers and vector network analysers.

Each profile defines its required base actions and optional features. A device may compose profiles. Real model restrictions narrow the standard schemas, and shared hardware remains subject to shared ownership. The class document states required quantities, lifecycle rules and failure evidence.

This is a bounded class baseline, not universal feature coverage. AC power sources, RF conversion/modulation families, cameras, environmental chambers and other specialised devices require additional profiles. GPIB, USB-HID, arbitrary USB bulk and vendor SDKs require separately admitted host-provider contracts (transport-providers.md). Structural fixtures are neither implemented plugins nor qualified instruments.

## Procedure and bench provision

Execution contract 0.2.0 adds six schemas for procedures, benches, safety policies, commissioning, run bindings and run records. Logical roles make a procedure portable across separately qualified fixtures. Bounded control flow, explicit measurement validity and a required verified safe ending support unattended execution. A procedure may capture: the release adds the closed capture step kind (role-bound, with `format`, `sample_count`, `max_bytes` and the capture budget carried by `timeout_ms`) and its capture allow-rule kind, and later steps reference the landed capture manifest through `$stg_ref` (`/capture_id`, `/artifact_id`, `/sha256`). The fixtures are synthetic; no actual bench limits or qualification are supplied.

## Central repository provision

Registry contract 0.1.0 adds immutable release manifests, mutable release status and local dependency locks, each with a schema and synthetic metadata example. Users can share profiles, descriptors and implementations through a public catalogue or private mirror. The gateway retains local admission and offline execution authority. The package defines this architecture; it does not deploy a central service.

## Handoff to an AI coding agent

Supply this entire package together with the instrument's protocol manual, model/firmware details and available reference exchanges:

> Search configured registries for compatible existing integrations first, then reuse, contribute or fork with attribution as appropriate. For a new integration, create an STG device integration targeting OTDP 0.2.2 and adapter API 1.1. Read the core specification, extension contract, applicable device classes, measurement model and schemas. Select supported profiles, declare real channels and device constraints, and implement all claimed actions using verified protocol evidence. For registry publication, also supply the release manifest and evidence required by registry contract 0.1.1. Bundle the pinned local contracts and deliver the descriptor, adapter where required, dependencies, tests and supporting evidence. Apply the specification's semantic/conformance obligations and applicable class/dataset checks. Report missing device facts; do not invent commands or unsupported capabilities. Distinguish mock conformance from live qualification. Do not modify bench safety limits or energise equipment as part of code authoring.

These documents define the interfaces; a gateway host or plugin implementation is not included. Schema validation does not prove lifecycle correctness, protocol truth, hardware compatibility or physical protection.

## Implementation and commissioning evidence still required

Build and exercise the gateway and plugins against these contracts. Supply actual device protocol evidence, model limits and hardware qualification. Commission the bench's voltage/current/power/energy envelope, safe transition, response time and unattended procedures. Future mains-powered fixtures require separate qualification.

From the 0.1.0 baseline forward, superseded versions are retained digest-frozen beside their successors (see `standards/GOVERNANCE.md`); the reset's pre-baseline lineage lives in git.

## Baseline verification

1104 document/schema and selected semantic/coverage checks passed: OTDP 616, registry 64, execution 151, interface 256 and closure 17. These checks are not a complete runtime or hardware conformance suite. These counts record the architecture review baseline; they are not results from the repository CI.
