# Smart Test Gateway — PoC and MVP product requirements

**Version:** 0.2 · **Date:** 10 September 2026  
**Status:** Initial product and delivery proposal for review; implementation has not started.  
**Architecture baseline:** STG 1.5; OTDP 0.3.0; adapter API 1.1; registry/execution 1.0.0; interface 1.1.0; MCP 2026-07-28.

## 1. Product decision

Build one complete, reusable test-bench workflow before broadening device coverage. The **PoC proves software behaviour with simulated devices**. The **MVP delivers a separately qualified low-voltage hardware workflow**, including approved unattended execution. Both demonstrate that a second user can reuse a published integration instead of writing another driver.

The product is a local test gateway with shared device integrations. Its first useful outcome is an operator finding compatible integrations, admitting them to a bench, running an approved test and receiving trustworthy results and recovery information through REST or an AI client using MCP.

| Delivery option | Trade-off | Selection |
|---|---|---|
| Simulator-first complete workflow, then one qualified bench | Early deterministic fault testing; hardware proof remains a distinct gate | Recommended baseline |
| Hardware-first one-device demo | Faster visible instrument control but weak replay/failure evidence and dependency on equipment availability | Do not use as the PoC exit criterion |
| Implement all twelve classes and a public marketplace first | Broad scope delays proof of core value | Deferred |

**Selected hardware:** FNIRSI DPS-150 is the confirmed first instrument. ESP32 is the provisional controller family; exact board/firmware remains to be selected. See the hardware discovery brief for protocol and qualification gates.

## 2. Problem and users

Instrument integrations are repeatedly recreated, tests are tied to scripts and particular benches, and an acknowledgement can be mistaken for a verified result. An AI interface increases convenience but must not change device ownership, operating limits or evidence requirements.

Primary users:

- **Test engineer:** runs repeatable controller tests, evaluates measurements and diagnoses failures.
- **Integration author:** publishes a documented plugin once, with compatibility and evidence that others can evaluate.
- **Bench owner:** admits equipment, qualifies protection and controls unattended use.
- **AI-assisted operator:** discovers capabilities, starts approved procedures and inspects results through the same authorised core.

Stephen is the product decision owner for this proposal. Engineering, registry and bench qualification owners are roles to assign before their respective milestones; names and physical limits are not invented here.

## 3. Demonstration journey

1. A clean gateway discovers a curated registry containing a profile package and two simulated implementations: DC supply and embedded controller.
2. The engineer reviews compatibility, licence, permissions and simulated evidence, then admits exact releases locally.
3. The bench owner selects a versioned simulated fixture/policy and approved procedure. Simulation is visibly identified throughout.
4. The operator starts the procedure through REST, retrieves the same run through MCP and views a concise report.
5. The procedure configures/enables the simulated supply, obtains supply measurements and numeric controller telemetry, evaluates assertions, disables the supply and verifies the modelled final safe condition.
6. A deliberately lost response, stale sample, trip or gateway restart produces the defined outcome without an unintended second run.
7. A second clean installation reuses the same registry packages without modifying plugin source.
8. For the MVP, replace the simulated devices with selected real equipment, perform qualification, then demonstrate the approved unattended procedure.

Controller assertions use a documented numeric telemetry quantity supported by the chosen DUT. The simulator supplies a specified numeric quantity in its protocol fixture. For an ESP32 reference DUT, a small separately versioned telemetry firmware is included in the MVP work package if suitable firmware does not already exist; it supplies numeric uptime in seconds and explicit identity/correlation. It is not an independent protective controller. The plan does not assume a particular real controller exposes supply voltage, uptime or a boot flag. A Boolean boot assertion would require an explicit execution-contract extension or a separately justified supported numeric measurement; do not silently change types to fit the PoC.

## 4. Scope by stage

| Capability | PoC | Hardware MVP |
|---|---|---|
| Local gateway | One Linux host, one bench, one controlling run | Same ownership boundary on the qualified host |
| Device coverage | DC PSU and embedded-controller simulator plugins | FNIRSI DPS-150 plus a provisionally selected ESP32 fixture; required independent evidence source |
| Procedure engine | Full bounded execution 1.0.0 language; unsupported device actions rejected | Same language on the qualified procedure/device set |
| Registry reuse | Curated static registry, exact pins, test trust root, local review, second installation | Controlled shared registry with operational signing/recovery and support ownership |
| Interfaces | Twenty REST operations and seventeen MCP tools, with administrative staging limited to the two-plugin bench | Same interface; exact tested client/authentication matrix |
| Identity | Local test issuer with validated audience/scopes and separate principals | Configured production identity provider and scoped accounts |
| Protection | Faultable simulation; clearly no physical safety claim | Qualified independent protection where required, verified sensing and shutdown |
| Evidence | Durable run/request/events, exact-byte documents, scalar datasets and bounded artefact reads | Retention/recovery validated on the deployment |
| Operator experience | CLI for setup/discovery; concise report; MCP client demonstration | Documented setup, qualification, operation and recovery workflow |
| Installation | Reproducible native Linux service and clean test environment | Qualified native service, updates and backup/restore |

A full graphical dashboard is not required for either initial exit gate. Reports and CLI must make run outcome, final safety, evidence gaps and simulation status unambiguous. Public account registration, community moderation automation and a marketplace website are deferred; the first central repository is curated.

## 5. Prioritised requirements

P0 means required for the named stage; P1 means useful only after those gates pass. Architecture obligations are not waived by their omission from this product summary.

| ID | Priority/stage | Requirement | Observable acceptance |
|---|---|---|---|
| PRD-01 | P0 PoC | Reproducible clean setup with locally pinned contracts/dependencies | A second documented Linux environment builds and runs the demo without editing source |
| PRD-02 | P0 PoC | Discover and reuse compatible packages | Second installation resolves the same digests and runs without creating another implementation |
| PRD-03 | P0 PoC | Authenticated immutable package admission | Tamper, unknown trust, missing dependency, conflict and revoked-package cases reject before activation |
| PRD-04 | P0 PoC | Real plugin ABI through simulated transports | Both plugins use published factory/context/host services; no simulator-only shortcut bypasses policy or dispatch evidence |
| PRD-05 | P0 PoC | One ownership domain and typed admission | Competing starts, stale generations, incompatible bindings and unauthorised principals are rejected |
| PRD-06 | P0 PoC | Bounded approved procedures | All eight step kinds, lexical references, body/protection budgets and invalid predicates behave as specified |
| PRD-07 | P0 PoC | Durable run and request identity | Dropped start response and identical REST/MCP retries yield one run and one intended dispatch occurrence |
| PRD-08 | P0 PoC | Explicit protection and recovery | Trip/cancel/timeout/restart tests preserve uncertainty, never reset the protective deadline or automatically resume |
| PRD-09 | P0 PoC | Trustworthy measurement and final report | Invalid/stale/wrong-unit evidence cannot pass; missing terminal record or unverified safety cannot produce passed |
| PRD-10 | P0 PoC | Interface parity and access scope | REST/MCP vectors and live client tests agree; cross-bench evidence reads and principal spoofing fail |
| PRD-11 | P0 PoC | Registry and network independence during a run | Accepted gateway-owned simulated run finishes within policy through client/registry loss |
| PRD-12 | P0 PoC | Controlled administration | Separate approved change succeeds only at a safe idle boundary; control identity cannot self-approve |
| PRD-13 | P0 MVP | Verified real instrument and DUT support | Commands, firmware, transport, channel mapping and compatibility supported by source and hardware evidence |
| PRD-14 | P0 MVP | Qualified physical operating envelope | Fixture identity, limits, sensing, independent protection and shutdown timing have approved measured evidence |
| PRD-15 | P0 MVP | Approved unattended operation | Normal and applicable fault runs meet the commissioned response bounds without continuous AI/client judgement |
| PRD-16 | P0 MVP | Supportable installation and recovery | Backup/restore, updates, revocation, identity replacement and operator recovery procedures demonstrated |
| PRD-17 | P1 after MVP | Broaden coverage and presentation | Additional device classes or GUI work starts only after a prioritised user need and the initial gates |

## 6. Measurable success criteria

The following are **proposed product targets, not measured results or electrical safety thresholds**:

- A prepared engineer can complete the documented clean simulated demo in **30 minutes or less**, excluding dependency download time; record the actual result.
- A second engineer can discover/admit the published integrations and repeat the demo in **30 minutes or less**, with **zero plugin-source changes**.
- **100 consecutive normal simulated runs** produce complete, internally consistent evidence and no duplicate dispatch. Use a fixed seed and retain logs.
- Every applicable fault case in the PoC test matrix has its expected deterministic outcome; **no false passed result** is tolerated.
- On the recorded reference host, metadata reads have **p95 ≤500 ms** and run acceptance has **p95 ≤2 s**, excluding device execution. Use 100 requests with one active run and two observers. Exceeding a product target triggers profiling/scope review, not relaxed protective timing.
- The MVP completes **20 consecutive qualified normal hardware runs** plus every applicable approved fault test. Twenty runs demonstrate repeatability for this release; they are not a statistical reliability certification.
- The product owner accepts the reuse and operator journey; the bench/test-safety owner separately accepts physical and unattended qualification.

## 7. Stage exit gates

**G1 — First working slice:** Verified local contract/content store plus one simulator plugin can produce a typed measurement through scoped host services. This is internal engineering evidence, not the product PoC.

**G2 — PoC exit:** PRD-01 through PRD-12 pass with live software, simulated devices, an independently exercised MCP client, curated authenticated registry and second-installation reuse. Fault results and performance measurements are retained. No claim that all twelve classes are implemented.

**G3 — Supervised hardware gate:** Hardware selection, manuals, firmware, identity, host-provider contracts and physical protection are documented. PRD-13/14 pass before using an energised fixture outside the approved commissioning activity. Simulation approvals cannot authorise hardware.

**G4 — MVP exit:** PRD-15/16 pass, normal/fault hardware evidence and operational procedures are reviewed, and the unattended procedure is specifically qualified. A successful PoC does not automatically open this gate.

## 8. Risks and release controls

| Risk | Delivery response |
|---|---|
| First equipment/protocol information unavailable | Continue simulator PoC; hold hardware tasks at G3 |
| SDK mismatch with MCP 2026-07-28 | Early live interoperability task; pin a verified compatible SDK or write a bounded adapter preserving the selected contract |
| Simulators hide transport ambiguity | Faultable transport boundary, dispatch ledger, process-kill tests and real hardware gate |
| Registry work expands into marketplace development | Static curated publishing/discovery first; preserve the trust/metadata contract |
| Durability/protection timing competes with downloads | Separate quotas, bounded single-writer persistence and failure injection; qualify actual response timing |
| UI or broad class support consumes schedule | CLI/report first; two implemented profiles until G2 |
| Draft planning assumptions mistaken for approval | Gate records bind actual evidence, owner and exact content digests |

## 9. Inputs still needed

The PSU model is now selected: FNIRSI DPS-150. Hardware planning still needs its exact revision/firmware, the ESP32 board and telemetry firmware, available independent measurement/protection hardware, target Linux host and applicable protocol evidence. These inputs select the first qualified integrations; they do not block the simulator work packages.

Before committing dates: assign engineering/QA/bench owners, confirm available effort and review lead times. This PRD deliberately sets dependency gates rather than unsupported calendar promises. The repository name and proposed layout in the plan are planning choices; no source repository has been created.

## 10. Product release decision

Approve the PoC on demonstrated reuse, deterministic recovery and honest evidence. Approve the MVP only after separate physical/unattended qualification. Additional device families, fleets, unrestricted scripts, cloud control and public marketplace operations remain outside this release.
