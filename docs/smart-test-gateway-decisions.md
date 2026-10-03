# Smart Test Gateway: Architectural decisions

**Date:** 9 September 2026  
**Status:** Selected decisions in the consolidated v1.5 architectural baseline; implementation and qualification evidence remain required  
**Architecture:** [Smart Test Gateway v1.5](smart-test-gateway-architecture-v1.5.md)

## Purpose

Close architectural ambiguity and do not invent bench-specific requirements. This record explains the choices and their trade-offs. It is not an implementation plan or a commissioning approval.

## A01: Local authority, colocated interfaces

**Selected:** One gateway owns one bench; MCP and REST are colocated entry points to the shared control core.

**Alternatives:** Separate remote MCP from the outset; centralise bench execution in a fleet service.

**Reason:** Local ownership and protection remain independent of central-service availability. Colocation reduces initial deployment burden without removing the future network boundary.

**Consequence:** Every entry point carries caller identity into the same policy checks. Future fleet routing cannot bypass local decisions. Cross-gateway procedures remain outside the initial scope.

## A02: Qualified profiles, not universal electrical assumptions

**Selected:** Architecture mandates a bench envelope, safe transition and qualification evidence. Numeric limits and protective hardware are commissioned for each bench.

**Alternatives:** Adopt one arbitrary low-voltage envelope; attempt unrestricted equipment support through descriptor ranges alone.

**Reason:** Neither low nominal voltage nor an instrument's rating establishes acceptable energy or device-under-test (DUT) safety. A reusable gateway can have strict contracts without assuming every bench has the same hazards.

**Consequence:** Missing requirements block control. Independent protection is required where loss of gateway control could leave a damaging condition. Unattended operation is a confirmed target and an explicitly qualified capability. The initial class is low-voltage embedded controllers. Future mains-powered DUTs require separate qualification. Their support is not inferred from a low-voltage control interface or a descriptor range change. The user's expectation of little stored energy must still be checked per fixture.

## A03: One active controlling procedure

**Selected:** One controlling procedure per bench, with explicit resource ownership and scheduled observations.

**Alternatives:** Concurrent procedures that share instruments. Independent clients that coordinate informally.

**Reason:** The selected scope avoids conflicting physical sequences and keeps initial recovery understandable.

**Consequence:** Parallel test throughput is limited initially. A future concurrency extension must prove resource independence, including shared buses, fixtures and protective dependencies.

## A04: Bounded continuity after client loss

**Selected:** Manual control expires with its lease and starts the approved safe transition. Explicitly approved gateway-owned procedures may finish within their local duration limit without the client.

**Alternatives:** Always terminate on client loss; always continue indefinitely.

**Reason:** A transient client failure need not invalidate a safe local procedure, but it must not leave indefinite authority or energisation.

**Consequence:** Execution mode, duration and disconnect behaviour are declared before the run starts. Gateway-owned execution is the normal mode for the requested unattended procedures. A client cannot silently promote an ordinary operation to autonomous execution. Protection and completion cannot depend on continued AI judgement. Trips and gateway restarts do not automatically resume or re-arm runs.

## A05: Trusted integrations with selective containment

**Selected:** Reviewed, versioned plugins with controlled admission. Fault isolation is added where integration behaviour requires it.

**Alternatives:** Unrestricted plugins in the gateway process; a complete untrusted-plugin platform from the outset.

**Reason:** A restricted trusted-extension model is supportable for the initial scope. If you call an imported class a sandbox, you hide its actual privileges.

**Consequence:** Executable plugin changes are release changes. Descriptor reload remains possible at a validated, safe activation boundary. Plugin trust is a documented assumption. Independent protection must cover relevant failures of gateway code.

## A06: Evidence-aware operation semantics

**Selected:** Persistent operation identity, explicit uncertain outcomes and declared verification requirements.

**Alternatives:** Treat a successful transport write as completed physical work. Retry every timeout automatically.

**Reason:** Physical command execution can succeed even when its acknowledgement is lost. The selected contract preserves that ambiguity. It does not repeat unsafe work. It does not assert success.

**Consequence:** The gateway provides duplicate suppression at its boundary. Exactly-once physical execution is not promised. Recovery reconciles ambiguous outcomes before dependent actions proceed.

## A07: Audit failure constrains new work

**Selected:** Protect audit capacity from captures. Refuse new actions that energise when their intent cannot be recorded. Protective action and the approved active-procedure response continue.

**Alternatives:** Continue all work without evidence; stop all actions, including shutdown, whenever logging fails.

**Reason:** The system retains accountability and does not make evidence storage a dependency of physical protection.

**Consequence:** Retention and capacity are mandatory deployment settings. Central log connectivity is not required for local operation.

## A08: Reference deployment without hardware universality claims

**Selected:** Python reference runtime and a host-native supervised Linux service. Hardware and backend combinations are explicitly qualified.

**Alternatives:** Require containers for every bench; support arbitrary Linux hosts and adapters without a compatibility boundary.

**Reason:** This preserves the original software-only direction and a clear direct-hardware deployment baseline. Packaging does not establish equivalent USB, general-purpose input/output (GPIO) or failure behaviour automatically.

**Consequence:** Containers and other runtimes may be supported after their behaviour is qualified. No hard real-time guarantee follows from runtime or operating-system selection.

## A09: OTDP compatibility is an explicit integration gate

**Selected:** New plugins target the accompanying reconciled OTDP 0.1.0 specification, descriptor and runtime schemas and adapter API 0.1.0. Gateway runtime safety and ownership remain explicit separate contracts.

*2026-09-19 annotation:* the active corpus versions are now OTDP 0.1.1 (a byte-errata of 0.1.0) and adapter API 1.1. See the `standards/corpus-manifest.json` identity. The decision text above is the historical record and is unchanged.

*2026-09-19 annotation (later the same day):* the active OTDP corpus version is now 0.1.2. This is an additive derived-variables revision (descriptor `derived_variables[]`, measurement `derivation` marker; M15/S19). Adapter API stays 1.1. Same authority: `standards/corpus-manifest.json` identity.

*2026-09-19 annotation (issue #64):* the active OTDP corpus version is now 0.2.0. This MINOR revision admits `averaging_count` on the oscilloscope configure action (class-bounded [1, 64]). It bounds acquisition `sample_count` at 1e6 across the oscilloscope, logic-analyser and data-acquisition (DAQ) configure inputs and their echoes. This is a tightening. Because of it, descriptors and presets are re-versioned and repinned. Adapter API stays 1.1. Same authority: `standards/corpus-manifest.json` identity.

**Alternatives:** Accept v0.1 structural validation as sufficient; embed gateway policy into optional descriptor extensions.

**Reason:** Review confirmed that v0.1 allows inconsistent capability claims and incomplete mappings. The revised contract separates capabilities from integration mode, tightens validation and specifies the plugin authoring and lifecycle requirements.

**Consequence:** The missing-document dependency is closed. New descriptors require the new contract; v0.1 imports require reviewed migration. An AI coding agent receives complete plugin interface and host-service definitions plus reference vectors. Actual device facts still come from protocol evidence, and implementation conformance remains to be demonstrated when code exists.

## A10: Bounded, composable device classes

**Selected:** 12 versioned device profiles and 50 typed actions, backed by a shared measurement model and locally pinned schemas. A multi-function instrument composes profiles while it retains one physical ownership boundary.

**Reason:** A generic scalar descriptor cannot express acquisition lifecycles, source and sink behaviour, complex data and switching topology sufficiently for consistent plugin authoring.

**Consequence:** Every claimed base action is required; optional features and model limits are explicit. A dataset shape does not imply a supported device class. New families require reviewed profiles and unsupported transports require host-provider contracts. The standard contracts guide an AI coding agent, while actual commands, ranges and hardware evidence remain device-specific.

## A11: Shared registry with local adoption authority

**Selected:** A central searchable catalogue of immutable profile, descriptor and implementation releases, linked to source repositories. Public and private registries and mirrors share one metadata contract. Authenticated distribution uses The Update Framework (TUF); local admission pins the complete dependency closure.

**Reason:** Users can reuse and improve existing integrations while they assess compatibility, provenance, licence, permissions and evidence. A Git-only directory lacks the selected lifecycle and discovery contract. Central bench execution introduces an unnecessary operational dependency.

**Consequence:** Publication and installation do not authorise control. Approved local packages support offline bounded procedures. Updates wait for a safe activation boundary; advisories and revocation are explicit managed state. Registry operations and bench admission have separate accountable owners.

## A12: Bounded procedures and separately commissioned bench policy

**Selected:** Versioned JSON procedures with sequential actions, fixed-count loops, lexical references, scalar assertions and explicit deadlines. Six document schemas separate portable procedures, local wiring and resources, protection policy, commissioning, run binding and outcomes.

**Reason:** This makes admission and failure handling reviewable. It does not let a shared or AI-generated procedure rewrite its operating envelope. Wiring, identities and package versions must match the evidence that qualified them.

**Consequence:** All endings require the approved safe transition. Terminal pass requires verified final safety. General scripts, parallel and distributed workflows and advanced analytics remain extensions. Fixture values and zero external digests are synthetic and do not commission real hardware. The acceptance documents record the integrated architectural review. Interface 0.1.0 supplies the external contract.

## A13: One core contract behind REST and MCP

**Selected:** REST v1 and MCP 2026-07-28 share typed operation/result contracts and durable core run identity. 20 REST operations include three administration operations omitted from the 17-tool MCP surface.

**Reason:** Transport sessions and retries must not determine physical authority or cause duplicate runs. Durable request associations, application leases and event cursors make recovery explicit across both interfaces.

**Consequence:** Older MCP revisions require a separately qualified compatibility adapter. Manual operations use approved procedures. Administration requires independent local approval and safe activation boundary. The interface is specified. Live OAuth and MCP interoperability and whole-system failure behaviour remain unverified.

## A14: Final review corrections and bounded closure

**Selected:** Interface 0.1.0 preserves original document bytes for digest verification and permits terminal evidence gaps only with uncertain or interrupted outcomes. The caller's valid manual lease supplies, rather than conflicts with, manual run authority. Qualification covers body plus protection; repeated trips cannot restart a protective deadline. Registry profile ownership, wrapper compatibility and shared physical-instance ownership are explicit.

**Consequence:** 16 registry composition and 26 integrated scenarios have defined architectural responses and acceptance owners. Implementation and hardware evidence remain required. The baseline is closed at its explicit scope; additional families, providers and workflows require reviewed extensions.

## What remains outside architectural closure

| Item | Required next evidence | Blocks |
|---|---|---|
| First bench's numeric DUT and energy envelope | Low-voltage embedded-controller scope confirmed; numeric limits still supplied during commissioning | Commissioning energised control |
| Safe transition and response times | Bench-specific assessment and validation | Relevant control qualification |
| Unattended operation | Requirement confirmed; fixture and procedure qualification evidence remains necessary | Unattended use |
| Equipment and transport combinations | Compatibility and failure-behaviour evidence | Support claim for that combination |
| OTDP implementation conformance | Execute the delivered structural, semantic and behavioural obligations against future code | Implementation conformance claim |

No implementation work is included in this decision record.
