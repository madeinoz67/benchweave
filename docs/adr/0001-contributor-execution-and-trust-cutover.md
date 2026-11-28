# 0001. Separate contributor execution restrictions from trust cutover

- **Status:** Accepted
- **Issue:** #228
- **Deciders:** Architect proposed the staged approach. The repository owner approved publishing the ADR.
- **Acceptance dependency:** #647 remains open and gates final Slice 6 acceptance.

## Context

Slice 6 of #209 covers CR-40, CR-41, CR-43, CR-44, CR-46 through CR-48, and Q17. The contributor publishing design §4 specifies acceptance F1 through F8.

- `registry/activation.py:load_plugin` takes a cache root, manifest, manifest digest and keyword-only entry path. It checks the implementation inventory and rehashes the entry bytes before execution.
- `interfaces/app.py:_load_sim_plugin` constructs the module path from a name and imports the file. The run factory passes the simulation plan name.
- `interfaces/bootstrap.py:build_registry_session` loads the PEM with `registry/authenticity.py:load_trust_root` before building the resolver. The current load reads the PEM directly. This observation comes from code inspection.

Source paths above are relative to `src/benchweave/`.

## Decision

Ship execution restrictions and qualification first. Stage the production trust cutover across the gateway and registry, using a separately provisioned verifier for the signed fingerprint list. Gateway deployment owns provisioning of the public verifier and registry release operations owns signing and publication. Assign accountable operators before cutover.

| Option | Consequence |
|---|---|
| Staged execution and trust changes | Independently reviewable execution controls and qualification. The registry and gateway still coordinate the trust cutover. |
| Single coordinated release | One operational window couples loader changes, qualification and trust rollback. |

## Contracts and acceptance

| Task | Boundary and proposed contract | Acceptance evidence |
|---|---|---|
| E1 | `registry/activation.py:load_plugin` keeps its signature. Require admitted development lineage before legacy execution and return `legacy_leg_refuses_published` for published packages. The OTDP loader remains the published execution path. | F1. A published fixture is refused before execution. The documented dev publish-to-load loop succeeds. |
| E2 | `interfaces/app.py:_load_sim_plugin` resolves only fixed in-tree fixtures by registered name. Refuse unregistered names before import with a distinct reason. | F2. A package-sourced fixture is refused and a registered sim fixture loads. |
| E3 | The untrusted trial entry point verifies the effective service hardening at launch. Require the deployed unit's unprivileged identity, read-only filesystem posture and executable-memory restrictions. Report missing protections and refuse execution. | F3. Refusal without required protections and successful run in the protected rehearsal environment. |
| E4 | The deploy permissions record documents plugin-originated outbound traffic as accepted risk while legitimate endpoints are being identified. Operator deploy configuration owns the eventual allowlist under Q18. | F7. Record names the affected traffic, the accepted risk and the allowlist owner and discovery input. |
| E5 | Instrument qualification records require measured dispatch and verification latency under a documented load and protective timing budget. Missing or late measurements fail qualification for new records. Historical records retain their disclosed evidence. | F8. A healthy fixture records the measurements. An over-budget fixture records failure. |
| T1 | Registry publication emits signed, versioned key metadata alongside the index. Scope fingerprints and lifecycle entries to the origin and key role. Verify metadata against an independently provisioned verifier before accepting a registry key. Require monotonic authenticated updates and distinguish verification failure from missing or inactive keys. | F4. A provisioned key absent from approved metadata is refused with a named reason. A listed active key verifies successfully. |
| T2 | Gateway origin verification applies the active key set and recorded cutover. A single authenticated lifecycle record revokes a key across its releases while preserving per-release lifecycle and release history. | F5. Active-key verification succeeds, retired-key-only verification fails after cutover and key revocation takes effect through one record. |
| T3 | Production session construction and origin resolution enforce the production refusal of unsigned development origins. Preserve explicit development mode and document its local trust-root workflow. | F6. Production refuses dev-unsigned origins before use and explicit development mode retains the workflow. |

E1, E2 and E4 can proceed in parallel with separate file ownership. Coordinate E3 and E5 if they share trial entry points. Agree the metadata contract with both repositories before implementing T1. T2 depends on T1. Coordinate T3 with the trust cutover and run the development workflow across E1 and T3.

## Stability boundaries

Keep CR-13 admission semantics and registry standard bytes stable. Preserve entry integrity checks, the OTDP fence and per-release yank. Document the REG-1 amendment and Q16 residuals, including per-plugin isolation, tamper-evident evidence and a plugin-independent safe-state path. Existing unit hardening and qualification evidence describe the interim posture.

## Rollout and rollback

Stage signed metadata and independently provision the verifier before requiring the new policy in production. Rehearse with controlled fixtures and confirm positive and negative acceptance cases before cutover. Keep execution restrictions staged independently. After cutover, recover trust through a newly authenticated forward update that preserves retirements and revocations. If current authenticated policy cannot be restored, suspend affected origin use pending recovery.

Track all eight acceptance checks in implementation review. Keep final acceptance open until #647 records the Q19 re-issue and verdict, then reconcile any resulting requirements with this ADR.
