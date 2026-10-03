# Architecture closure register: STG 1.5

**Disposition:** Architectural review and consolidation complete at the explicitly bounded scope. No implementation, live protocol interoperability or physical qualification claim is made. Owner approval to deploy or energise equipment is not inferred from this document.

## Authoritative contract set

| Contract | Version | Disposition |
|---|---|---|
| STG architecture | 1.5 | Local authority, ownership, protection and recovery selected |
| OTDP | 0.3.0 | 12 profiles and 50 typed actions; explicit class and transport exclusions |
| Python adapter API | 1.1 | Scoped plugin lifecycle, transport and dataset interfaces |
| Registry | 1.0.0 | Package metadata, trust, lifecycle and composition rules |
| Execution | 1.0.0 | Bounded sequential procedures, bench, policy and commissioning, and run records |
| External interface | 1.1.0 | 20 REST operations, 17 MCP tools; exact-byte documents and explicit evidence gaps |
| MCP protocol | 2026-07-28 | Selected compatibility baseline; other versions not implicitly supported |

The normative versions listed above define the design baseline kept in this repository. Narrative clarifications in registry and execution keep their schema versions because their structures did not change. Changes to interface structure and semantics receive version 1.1.0. Superseded archives were removed. Mix-and-match contract sets are unsupported.

## Closure evidence

- 16 registry scenarios resolve ownership, reuse, wrappers, mirrors, forks, versions, revocation and shared devices.
- 26 integrated scenarios define the trigger, the required response, the evidence and the recovery, and the acceptance owner.
- The integrated review resolves all 7 cross-contract findings.
- 978 document and schema checks and selected semantic and coverage checks pass. Limits are reported beside each suite.

No known unresolved architectural decision blocks the stated baseline. This is the outcome of this documented review, not a claim that further implementation or independent review cannot uncover defects.

## Before implementation conformance can be claimed

Implement the specified contracts. Then do the applicable OTDP semantic and behavioural checks: C01–C12, M01–M14, P01–P10, B01–B10, I01–I12, registry obligations and integrated scenarios. Record actual results, versions, failure injections and reviewer evidence. Schema validity alone is not enough. Choices of library, hosting and storage may vary only while they preserve these contracts.

## Before bench qualification or unattended use

> **CAUTION:** MISSING DEPLOYMENT VALUES BLOCK THE RELEVANT OPERATION. THE SYNTHETIC EXAMPLES DO NOT SUPPLY THEM.

Supply these items before you energise a bench:

- real device, protocol and firmware facts
- verified identities and wiring
- applicable input and provider contracts
- domain limits for voltage, current, power and energy
- physical protection
- bounds for signal errors and freshness
- response times
- runtime capacity
- named approvals
- qualified fixtures and procedures

Set the policies for registry keys and recovery, offline freshness, and retention.

> **CAUTION:** FUTURE MAINS DUTs (DEVICES UNDER TEST) NEED SEPARATE QUALIFICATION.

## Explicit extensions

These are outside this baseline and do not prevent its closure:

- specialised device classes and more transports
- procedures that are distributed, parallel or general-script
- first-class registry procedure discovery
- advanced dataset analytics
- broader policy expressions
- descriptor-free generic registry libraries
- automatic failover
- older MCP compatibility

Unknown provider/profile IDs must be rejected until a reviewed extension exists.

## Delivery status

Architecture and specification work only. This workstream created no gateway, registry, plugin, controller, procedure engine or deployment. Next substantive work is implementation planning against this baseline, when requested. Commissioning remains separate.
