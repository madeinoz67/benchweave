# Architecture closure register — STG 1.5

**Disposition:** Architectural review and consolidation complete at the explicitly bounded scope. No implementation, live protocol interoperability or physical qualification claim is made. Owner approval to deploy or energise equipment is not inferred from this document.

## Authoritative contract set

| Contract | Version | Disposition |
|---|---|---|
| STG architecture | 1.5 | Local authority, ownership, protection and recovery selected |
| OTDP | 0.3.0 | Twelve profiles / fifty typed actions; explicit class/transport exclusions |
| Python adapter API | 1.1 | Scoped plugin lifecycle, transport and dataset interfaces |
| Registry | 1.0.0 | Package metadata, trust, lifecycle and composition rules |
| Execution | 1.0.0 | Bounded sequential procedures, bench/policy/commissioning and run records |
| External interface | 1.1.0 | Twenty REST operations, seventeen MCP tools; exact-byte documents and explicit evidence gaps |
| MCP protocol | 2026-07-28 | Selected compatibility baseline; other versions not implicitly supported |

The normative versions listed above define the design baseline retained in this repository. Narrative clarifications in registry/execution retain their schema versions because their structures did not change. Interface structural/semantic changes receive version 1.1.0. Superseded archives have been removed; mix-and-match contract sets are unsupported.

## Closure evidence

- Sixteen registry scenarios resolve ownership, reuse, wrappers, mirrors, forks, versions, revocation and shared devices.
- Twenty-six integrated scenarios define trigger, required response, evidence/recovery and acceptance owner.
- Seven cross-contract findings are explicitly resolved in the integrated review.
- 978 document/schema and selected semantic/coverage checks pass, with limits reported beside each suite.

There is no known unresolved architectural decision blocking the stated baseline. This is the outcome of this documented review, not a claim that further implementation or independent review cannot uncover defects.

## Before implementation conformance can be claimed

Implement the specified contracts and execute the applicable OTDP semantic/behavioural checks, C01–C12, M01–M14, P01–P10, B01–B10, I01–I12, registry obligations and integrated scenarios. Record actual results, versions, failure injections and reviewer evidence. Schema validity alone is insufficient. Library/hosting/storage choices may vary only while preserving these contracts.

## Before bench qualification or unattended use

Supply real device/protocol/firmware facts, verified identities/wiring, applicable input/provider contracts, domain voltage/current/power/energy limits, physical protection, signal error/freshness bounds, response times, runtime capacity, named approvals and qualified fixtures/procedures. Set registry key/recovery, offline freshness and retention policies. Missing deployment values block the relevant operation; the synthetic examples do not supply them. Future mains DUTs require separate qualification.

## Explicit extensions

Specialised device classes and additional transports; distributed/parallel or general-script procedures; first-class registry procedure discovery; advanced dataset analytics; broader policy expressions; descriptor-free generic registry libraries; automatic failover; older MCP compatibility. These are outside this baseline and do not prevent its closure. Unknown provider/profile IDs must be rejected until a reviewed extension exists.

## Delivery status

Architecture and specification work only. No gateway, registry, plugin, controller, procedure engine or deployment was created. Next substantive work is implementation planning against this baseline, when requested; commissioning remains separate.
