# Registry composition review — STG 1.5

**Method:** Architectural walkthrough of immutable package graphs and their admission contracts. No registry or package resolver was executed.

## Ownership rules

`provides.profile_ids` names profile definitions owned by a package, while `device_targets.profile_ids` names profiles a device integration implements/consumes. Consuming a profile does not redefine or own it. A profile definition resolves to exactly one admitted definition/digest per logical ID in a lock. Identical copies bundled for offline schema resolution may be deduplicated only after their bytes/digests agree; conflicting definitions under the same ID are rejected.

The selected standard distribution shape is profile package → consumed by an implementation that bundles its model descriptors. An optional separately published descriptor depends on that implementation and uses its admitted factory; the implementation never needs a reverse dependency on every downstream descriptor. Standalone implementations remain device-bearing under the existing manifest schema: they include at least one supported reference/model descriptor. A descriptor-free generic adapter-library package is not a new registry kind in this baseline; ordinary language dependencies cover internal shared libraries with exact locks.

A wrapper descriptor uses its own descriptor ID, declares its exact implementation dependency and must fit that implementation's supported model/firmware/profile/transport contract. It cannot claim new device support solely by referencing a factory. An upstream implementation change invalidates the wrapper's pin until its maintainer releases and qualifies a compatible wrapper revision.

All descriptor selections that resolve to the same physical instrument identity share one host device instance/ownership domain. Two descriptors or profiles do not permit two independent controllers of the same PSU, bus or fixture. Aliases are discovery aids, not independent hardware identities.

## Scenarios and decisions

| ID | Composition | Admission decision |
|---|---|---|
| R01 | One PSU profile package and one PSU implementation containing its descriptor | Admit only the exact profile and implementation releases; the implementation consumes rather than republishes the profile ID |
| R02 | Mixed-signal implementation consumes oscilloscope and logic profiles | Both profiles present, one physical instance, shared acquisition/resource limits enforced |
| R03 | A separate model descriptor depends on an existing compatible implementation | Acyclic forward dependency; wrapper has a distinct descriptor ID and verified compatibility; no reverse dependency required |
| R04 | Wrapper claims firmware not supported by its implementation | Reject compatibility intersection; a schema-valid wrapper is insufficient |
| R05 | Two roots share the same profile package/version/digest | One lock entry; closure deduplicates the shared node |
| R06 | Two roots require different versions/digests of one package | Reject the single-version closure; do not silently prefer latest |
| R07 | Private and public registries contain the same package name | Resolve from configured registry/namespace identity; never public fallback |
| R08 | Private mirror contains an upstream release | Preserve original identity/digest and trust verification; organisational approval is additional evidence |
| R09 | Fork changes implementation while retaining an upstream link | New package ID/release, preserved licence/attribution and independently reviewed permissions; no impersonation of upstream |
| R10 | Two packages define the same profile ID with different bytes | Reject conflicting provider definitions even when package IDs differ |
| R11 | Upgrade adds artifact_reader or a new host provider | New admission/qualification review; active run remains on its old pinned generation |
| R12 | A transitive dependency is revoked | Entire dependent closure ineligible for new starts once known; active run follows the commissioned protective response |
| R13 | Yanked release appears in an old lock | Normal selection excludes it; recorded digest-specific local exception is required for admission; history retained |
| R14 | Dependency cycle or missing dependency | Reject closure before download/activation; never fetch opportunistically during a test |
| R15 | Two descriptors point to one physical instrument | One instrument instance and coordinator ownership; conflicting configurations rejected |
| R16 | Hardware evidence covers one firmware/backend only | Display that evidence scope and narrow compatibility; no inference that another firmware or bench is qualified |

## Review disposition

The three existing package kinds cover the selected reuse scenarios without adding a fourth kind or a dependency cycle. Registry specification §11 records these ownership/compatibility semantics. Registry hosting/API implementation choices remain bounded by the existing logical-operation contract. First-class procedure discovery and descriptor-free generic libraries remain explicit extensions.

The companion graph fixtures/checker exercise simplified exact dependency closure and conflicts. They do not validate real package archives, cryptographic trust, licences, devices or complete registry conformance.
