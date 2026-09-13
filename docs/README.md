# Smart Test Gateway — Architecture and device-class contract

**Design baseline:** STG 1.5 · OTDP 0.3.0 · Python adapter API 1.1  
**Scope:** Architecture and plugin-authoring contracts for a qualified embedded-controller bench, including unattended procedures and a separate future mains qualification boundary.

**Status:** Consolidated architecture at the stated scope. Design review is complete; implementation, live interoperability and bench qualification have not been performed.

## Read first

| File | Purpose |
|---|---|
| [Architecture](smart-test-gateway-architecture-v1.5.md) | System responsibilities, protection, ownership, recovery and commissioning |
| [Central registry](registry-v1.0.0/registry-specification.md) | Shared packages, discovery, publication, metadata, trust and offline adoption |
| [Registry checks](registry-v1.0.0/validation-report.md) | 63 passing metadata-contract checks |
| [Procedure and bench contracts](execution-v1.0.0/execution-contract.md) | Bounded execution, wiring/resources, safety policy, commissioning and outcomes |
| [Execution checks](execution-v1.0.0/validation-report.md) | 150 passing document/schema checks; six linked synthetic examples |
| [REST/MCP contract](interface-v1.1.0/interface-contract.md) | Twenty REST operations, seventeen MCP tools, authentication and recovery |
| [OpenAPI](interface-v1.1.0/openapi.json) | REST routes and schema references |
| [MCP tools](interface-v1.1.0/mcp-tools.json) | Input/output schemas for the pinned MCP baseline |
| [Interface checks](interface-v1.1.0/validation-report.md) | 254 document/mapping checks and explicit verification limits |
| [Interface errata 1.1.1](interface-v1.1.1/README.md) | D2 amendment: `change_apply` body admits the optional `approver_token`; 1.1.0 bytes untouched |
| [Closure register](architecture-closure.md) | Review disposition, normative versions and qualification boundaries |
| [Registry composition review](acceptance/registry-composition-review.md) | Sixteen package reuse/compatibility scenarios |
| [Integrated review](acceptance/end-to-end-review.md) | Twenty-six end-to-end cases and resolved cross-contract findings |
| [Decisions](smart-test-gateway-decisions.md) | Selected architectural trade-offs |
| [Device classes](otdp-v0.3.0/device-classes.md) | Twelve class profiles, physical semantics, acquisition lifecycle and explicit exclusions |
| [Core specification](otdp-v0.3.0/otdp-specification.md) | Plugin authoring, runtime and host contracts |
| [Extension contract](otdp-v0.3.0/extension-contract.md) | Typed actions, local schema admission and adapter API 1.1 |
| [Measurement model](otdp-v0.3.0/measurement-model.md) | Units, axes, channels, complex/digital data, timing, calibration and uncertainty |
| [Profile catalog](otdp-v0.3.0/device-profile-catalog.json) | Fifty actions with exact input/output schemas |
| [Validation report](otdp-v0.3.0/validation-report.md) | 495 passing document/schema checks and their limits |

The package also includes descriptor, runtime, measurement and catalog schemas; twelve class descriptor fixtures; fifty action exchange vectors; thirteen dataset examples; and the four migrated core reference descriptors and their protocol vectors. Current normative device contracts are in `otdp-v0.3.0/`.

## Device-class coverage

The defined profiles cover DC power supplies, digital multimeters, oscilloscopes, logic analysers, function generators, electronic loads, source-measure units, data acquisition devices, embedded controllers, switch matrices, spectrum analysers and vector network analysers.

Each profile defines its required base actions and optional features. A device may compose profiles. Real model restrictions narrow the standard schemas, and shared hardware remains subject to shared ownership. The class document states required quantities, lifecycle rules and failure evidence.

This is a bounded class baseline, not universal feature coverage. AC power sources, RF conversion/modulation families, cameras, environmental chambers and other specialised devices require additional profiles. GPIB, USB-HID, arbitrary USB bulk and vendor SDKs require separately admitted host-provider contracts. Structural fixtures are neither implemented plugins nor qualified instruments.

## Procedure and bench provision

Execution contract 1.0.0 adds six schemas for procedures, benches, safety policies, commissioning, run bindings and run records. Logical roles make a procedure portable across separately qualified fixtures. Bounded control flow, explicit measurement validity and a required verified safe ending support unattended execution. The fixtures are synthetic; no actual bench limits or qualification are supplied.

## Central repository provision

Registry contract 1.0.0 adds immutable release manifests, mutable release status and local dependency locks, each with a schema and synthetic metadata example. Users can share profiles, descriptors and implementations through a public catalogue or private mirror. The gateway retains local admission and offline execution authority. The package defines this architecture; it does not deploy a central service.

## Handoff to an AI coding agent

Supply this entire package together with the instrument's protocol manual, model/firmware details and available reference exchanges:

> Search configured registries for compatible existing integrations first, then reuse, contribute or fork with attribution as appropriate. For a new integration, create an STG device integration targeting OTDP 0.3.0 and adapter API 1.1. Read the core specification, extension contract, applicable device classes, measurement model and schemas. Select supported profiles, declare real channels and device constraints, and implement all claimed actions using verified protocol evidence. For registry publication, also supply the release manifest and evidence required by registry contract 1.0.0. Bundle the pinned local contracts and deliver the descriptor, adapter where required, dependencies, tests and supporting evidence. Apply the specification's semantic/conformance obligations and applicable class/dataset checks. Report missing device facts; do not invent commands or unsupported capabilities. Distinguish mock conformance from live qualification. Do not modify bench safety limits or energise equipment as part of code authoring.

These documents define the interfaces; a gateway host or plugin implementation is not included. Schema validation does not prove lifecycle correctness, protocol truth, hardware compatibility or physical protection.

## Implementation and commissioning evidence still required

Build and exercise the gateway and plugins against these contracts. Supply actual device protocol evidence, model limits and hardware qualification. Commission the bench's voltage/current/power/energy envelope, safe transition, response time and unattended procedures. Future mains-powered fixtures require separate qualification.

Only the current contract set is retained in this repository; superseded documents and ZIP copies have been removed.

## Baseline verification

978 document/schema and selected semantic/coverage checks passed: OTDP 495, registry 63, execution 150, interface 254 and closure 16. These checks are not a complete runtime or hardware conformance suite. These counts record the architecture review baseline; they are not results from the repository CI.
