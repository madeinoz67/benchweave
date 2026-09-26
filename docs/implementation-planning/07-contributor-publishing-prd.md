# Contributor Publishing Path — Requirements PRD

**Status:** Draft v0.3 (2026-09-26; v0.2 2026-09-26; v0.1 2026-09-25) · **Author:** Stephen (madeinoz67), standards coordinator · **Tracking issue:** madeinoz67/benchweave#209 (this PRD, the design record and the work all live under it) · **Posted for commentary**

> v0.3 adds §5(l.7) GitHub-native detection and response surfaces (CR-59 to CR-62, Q21), and §5(m) standalone and shared plugins with the kind taxonomy (CR-56 to CR-58, Q20) plus author-sharing user stories — the differentiation and sharing mechanisms for plugins outside the signed-admission path. A decision review of Q1 to Q19 accompanies this draft in the run record; rulings remain with the owner.
> v0.2 added §5(l) malicious-plugin risk and handling: CR-35 to CR-55, NFR-S1 to NFR-S3, Q12 to Q19, and security entry criteria on the increments. Grounded in a 12-agent adversarial run over the real code: four machinery readers, four threat lenses producing a 56-entry threat catalogue, and two independent refute lanes recording 63 verdicts (59 confirmed gap, 2 owner calls, 2 refuted; lane coverage 32 and 31 entries of 56, with the uncovered and truncated entries disclosed at Q19).

## Summary

The registry machinery works from our side: origin-signed releases, trust root, sequence high-water admission, package locks, authenticity checks. The SDK gets an author to a finished, validated plugin. What's missing is everything between those two points, and the surfaces around that gap: where submitted plugins become discoverable (the public website and search) and how both sides manage the relationship (maintainer review, signing and advisories on one side; contributor status, ownership and withdrawal on the other). This PRD covers the requirements for that whole lane, scoped to #209. It also settles what any home for the lane — in-tree or a standalone repository — must satisfy. It states what must be true and how we will know. It does not say how to build it; anywhere a shape is sketched to make a requirement testable it is marked "Direction (non-binding)". A central registry service is explicitly out of the first cut: git-native first, per the issue's direction and Architecture v1.5 §18 ("Source repositories support contributions; signed releases support reproducible adoption"). v0.2 adds the malicious-plugin treatment (§5(l)): where the trust boundary actually sits (admitted plugin code runs in-process with the gateway's full authority), the classes of malicious plugin, a prevention/detection/response mechanisms map, and the requirements that make the lane's handling story true.

Evidence baseline: citations verified against the tree as indexed 2026-09-25; §5(l) machinery citations additionally audited 2026-09-26 by the threat run's two independent refute lanes (repo-relative paths throughout). Numbers must be re-measured at each increment's merge base.

## 1. Problem and evidence

1. **The gap is the path, not the machinery.** Admission exists and is strict (`src/benchweave/registry/admission.py` — `admit`, the persisted sequence high-water map, `_gate_lifecycle` carrying revocation/yanked; `src/benchweave/registry/resolver.py` — the resolver's high-water fence). The SDK scaffolds and validates. There is no submission command, no publisher onboarding (namespace governance, distribution keys, review workflow) and no contributor-facing publishing documentation.

2. **ADC-class friction, measured on a real submission.** The ADC plugin (parkview/benchweave#4) has been restamped twice and hand-moved across OTDP versions because admission is a manual owner-side operation — the same evidence trail #203 carries.

3. **Discovery is docs-shaped, not catalogue-shaped.** The public website (`website/index.html`) serves five panels (Home, Standards, Docs, SDK, Built with) and honestly states "the registry service and a device-install command do not exist", while the plan card promises "Profiles and implementations through a central registry". There is no plugin catalogue and no search — a consumer cannot find what has been published without already knowing where it lives.

4. **No publisher model in tooling.** The registry contract already names the model — "central discovery, publisher ownership, immutable releases, compatibility metadata, licence/provenance, test evidence, maintenance status, advisories and private mirrors" (`docs/smart-test-gateway-architecture-v1.5.md:301`) — but a source-tree search for publish/namespace concepts returns no code hits (measured 2026-09-25). Nothing operationalises publisher ownership.

5. **Management has exactly one shape today: the owner, by hand.** Review outcomes live in human memory and PR threads; yank/advisory exist only as admission lifecycle gates with no process, records or public surface wrapped around them.

6. **The project is multi-contributor.** Since 2026-09-23 this is a multi-developer project; a submission process sized for one owner's inbox will not hold.

7. **A malicious plugin has no dedicated handling story (v0.2).** The trust chain verifies bytes, never intent ("structural validity never establishes trust", `src/benchweave/registry/schemas.py`), admitted plugin code runs in-process with the gateway's full authority (the tree concedes "Adapters are trusted Python, not sandboxed", `src/benchweave/host/otdp_bridge.py`), and a published yank cannot reach an already-admitted gateway (run-build reads no status, `src/benchweave/interfaces/device_closures.py`). The lane therefore needs requirements for what it prevents, what it detects, and how response actually reaches commissioned gateways — §5(l).

## 2. Goals, non-goals and success measures

**Goals**

- **G1** — a documented, tooled path from a finished plugin in its own repository to a signed, admitted release, with no hand-restamping.
- **G2** — admitted plugins are discoverable: a catalogue on the public surface, with search.
- **G3** — management works from both points of view: maintainer (queue, review, sign, list, advise, yank) and contributor/consumer (submit, track status, own, withdraw, adopt).
- **G4** — whichever home the lane gets (in-tree or standalone repository) satisfies the home-requirements in §5(k).
- **G5 (v0.2)** — a malicious plugin is handled by named mechanisms: prevented where prevention exists, detected where detection exists, responded to with reach — and the residual risk is stated, not papered over (§5(l)).

**Non-goals**

- The central registry **service** (later, explicitly; git-native first).
- Version pinning and supported ranges — owned by **#203**. This PRD fixes only where version declaration lives in a submission and defers its semantics there entirely.
- The gateway operator console — owned by **#210**. Catalogue management here is not gateway administration.
- Any change to admission semantics or the trust model. The gateway verification path is a consumer of this lane, not a modification target (CR-13). Where §5(l) threats genuinely want an admission-semantics change, they surface as owner calls (Q12, Q13) instead of assuming one.
- Runtime sandboxing of plugin code as a built mechanism (the structural fork is Q16; the lane's requirements are disclosure, evaluation posture and qualification evidence).
- Hardware commissioning or bench qualification.

**Success measures** (each falsifiable)

- **S1** — a plugin of the ADC class goes repository to signed admitted release with zero hand-edits to its stamps; the release manifest is generated, not typed.
- **S2** — an independent reader can enumerate the required submission artefacts from the published docs alone, without asking anyone.
- **S3** — every published release has a durable review record (who, which checklist, when, outcome) recoverable from the repository of record alone.
- **S4** — searching the catalogue for a known admitted plugin finds it; searching for a non-existent one returns empty; a yanked one is flagged or gone within one records refresh.
- **S5** — a maintainer lifecycle action (advisory, yank, unlist) reaches both the catalogue and the next stock-gateway admission without a redeploy.
- **S6 (v0.2)** — a security exercise against a published release produces the full accountability chain (CR-54) and demonstrates response reach within the NFR-S2 bound (CR-53); unpublish-without-reach does not count.

## 3. Actors and user stories

**Actors:** contributor (plugin author, external); maintainer/admin (today me; later delegated reviewers); consumer (operator or developer adopting plugins); gateway (verifier at admission — unchanged); coding agent (acting for any of the above — the develop-your-device lanes already train agents on the build side).

**Contributor (submission POV)**

- As a contributor, I package a finished plugin and its conformance evidence in one command, so nothing is hand-assembled.
- As a contributor, I open a submission and see its stage: submitted / in review / changes requested / accepted / signed / published / withdrawn.
- As a contributor, I know the namespace rules before naming my plugin, and can see whether a name is taken.
- As a contributor, I withdraw a pre-acceptance submission or request an ownership transfer.

**Maintainer (admin POV)**

- As maintainer, I review against a written checklist plus the machine evidence, not vibes.
- As maintainer, I sign accepted releases with the key I custody; contributors never hold signing keys.
- As maintainer, I record an advisory, yank or unlist with a reason and see it propagate.
- As maintainer, I see the queue, the history and who owns what, in one place.

**Consumer (user POV)**

- As a consumer, I browse and search admitted plugins by name, publisher, device class/capability and standard version.
- As a consumer, I see provenance per entry: publisher, immutable release id, compatibility, licence, test evidence, maintenance status, advisories.
- As a consumer, I get adoption guidance (where the release lives, how to verify it) with no service to run.
- As a consumer, I can tell admitted releases from dev-unsigned experiments at a glance.

**Author sharing (standalone plugins) (v0.3)**

- As an author, I can share a standalone plugin in the repository with a clear community-shared, unverified tag, so others can find and try it without waiting for admission.
- As an author, my shared entry keeps my publisher identity and a pinned source ref, so users know exactly what they get and who to ask.
- As a consumer, I can tell at a glance which entries are admitted releases, which are author-shared, and which are in-tree fixtures — the tag never implies verification.
- As a consumer, I can filter search by kind so shared plugins don't drown out admitted ones.
- As an admin, I can unlist a shared listing on a recorded request without touching any admitted release.
- As an author, I understand sharing is not the admission path: only review and signing make a plugin available.

## 4. Current state

What exists (citations from the tree as indexed 2026-09-25):

- **Admission machinery** — `src/benchweave/registry/`: `admission.py` (`admit`; persisted high-water `high-water.json`; `_gate_lifecycle` carrying revocation/yanked), `resolver.py` (origin resolve; the resolver's high-water fence refuses a revisit). Trust root, Ed25519 origin-signed releases, package locks, authenticity checks all in place.
- **Dev loop** — a dev origin runs `signature_policy="dev-unsigned"` with a `dev-` registry id and no trust root (`docs/device-developer-guide.md`); unsigned skips authenticity only — schema, identity, digests, status expiry, high-water and lifecycle gates all still run.
- **SDK, standalone** — `benchweave-sdk` lives in its own repository with its own site, CI and release cycle, mounted at `packages/sdk`; it scaffolds an independent plugin project and its release CI builds one outside the checkout. It is also the existing precedent for the standalone-repository shape.
- **Docs** — `docs/device-developer-guide.md` (device creation, "the AI task template and human review checklist"), `docs/operator-guide.md`, the develop-your-device AI lanes and the AI device reviewer role. The build side is documented; the **publishing** side is not.
- **Public website** — `website/index.html`, five panels, manifest-derived version stamps (the #188 discipline, guarded by `tests/contract/test_website_stamps.py`). No plugin catalogue, no search.
- **In-tree plugins** — proof vehicles under `plugins/` (DPS-150 and the sim set); project fixtures, not published third-party releases.

What does not exist: a submission command; a packaging format for submissions; publisher onboarding (namespace, keys, review workflow); contributor publishing docs; any catalogue or search of plugins; management surfaces for either side; durable review-outcome records. v0.2 additionally records (from the §5(l) audit): no trust-root fingerprint verification at provisioning, no key rotation or revocation channel, no runtime sandbox, no status re-read after admission, and no capability or transport declarations anywhere in the publishing surfaces.

## 5. Functional requirements

Acceptance tests are one-line falsifiers. CR-19 and CR-34 cross-reference #203 and the home decision respectively.

### (a) Submission artefacts and packaging

- **CR-1** — A submission is a single generated artefact set: release manifest, descriptor(s), adapter source reference, conformance evidence, licence/provenance declaration. *Accept:* a submission missing any component is refused with the missing component named.
- **CR-2** — The packaging format is machine-checkable (schema-validated) and generated by tooling, never hand-assembled. *Accept:* the ADC-class case (S1) packages with zero hand-edits.
- **CR-3** — The release manifest binds identity: plugin id, version, declared standard versions (CR-18), source repo and revision, payload digests. *Accept:* every manifest field traces to a repo revision and a digest.
- **CR-4** — Conformance evidence is reproducible. *Accept:* two independent runs against the same revision agree; divergence is a refusal, not a pass.

### (b) Submission tooling

- **CR-5** — An author-side command packages and pre-checks a submission offline, reusing admission's own checks where possible. *Accept:* a deliberately broken package is caught pre-submission by the same class of check admission would apply (RED-provable: break the package, the tool refuses).
- **CR-6** — The submission channel is git-native: a PR against the repository of record, no service required. *Accept:* a full submit-to-accepted cycle completes with only git and review tooling.
- **CR-7** — Tooling lives where authors already are: the SDK CLI surface. *Accept:* an author who scaffolded with the SDK never leaves that toolchain to submit. (Placement confirmed by Q10.)

### (c) Review workflow

- **CR-8** — Review runs against a written checklist (extending the existing human review checklist) plus the machine evidence; the outcome references both. *Accept:* no accepted release exists without a recorded checklist outcome.
- **CR-9** — The outcome is durable and lives with the repository of record, not only PR threads. *Accept:* S3.
- **CR-10** — Every changes-requested state cites at least one failed requirement or checklist row. *Accept:* a changes-requested record with no cited failure is invalid and CI-refused.
- **CR-11** — Re-review triggers when the reviewed revision changes. *Accept:* a signed release can only reference a revision whose review record matches its digest.

### (d) Signing and trust

- **CR-12** — The maintainer signs accepted releases; signing keys stay maintainer-custodied and are never distributed to contributors. *Accept:* no contributor-held credential can produce a signature admission accepts.
- **CR-13** — Gateway verification is unchanged: what stock admission verifies today (origin signature, sequence high-water, lifecycle, digests) is exactly what a published release must satisfy. *Accept:* an accepted release admits through unmodified admission. Any design that requires admission changes fails this PRD.
- **CR-14** — The signature covers the exact artefact set reviewed. *Accept:* any post-review byte change invalidates the signature.

### (e) Naming and namespace

- **CR-15** — Publisher ownership is first-class: every published plugin names its publisher, and publishers own their namespace. *Accept:* two publishers cannot be conflated in manifest or catalogue.
- **CR-16** — Namespace rules are documented before the first submission and machine-checkable (reserved prefixes including `dev-`, collision refusal). *Accept:* a colliding or reserved name is refused at packaging time.
- **CR-17** — Ownership transfer is an explicit, recorded operation. *Accept:* transfer produces an auditable record; silent reassignment is impossible.

### (f) Version declaration (boundary with #203)

- **CR-18** — A submission declares the standard versions it was built on, at the location this lane fixes (manifest field), with semantics exactly as #203 settles them. *Accept:* one declaration mechanism exists — if #203 moves the semantics, this lane follows; a second mechanism is a defect.
- **CR-19** — The catalogue surfaces each plugin's declared versions without re-derivation. *Accept:* version-declaration data renders in catalogue rows straight from the manifest.

### (g) Catalogue on the public website

- **CR-20** — Admitted plugins are a first-class public surface (a Plugins panel or page set on the site), each row carrying the registry contract's metadata: publisher, immutable release id, compatibility, licence/provenance, test-evidence link, maintenance status, advisories. *Accept:* every published release appears with all seven fields rendered or explicitly "none".
- **CR-21** — The catalogue is generated from records, never hand-edited — the same manifest-derived stamp discipline the site already enforces (#188). *Accept:* a records change without catalogue regeneration fails CI (extend the guard class of `tests/contract/test_website_stamps.py`).
- **CR-22** — Pre-admission submissions never appear as available. *Accept:* the default catalogue view shows accepted+signed releases only; in-flight submissions are visible only in management views.
- **CR-23** — The site's honesty rule holds on the new surface. *Accept:* the panel states what is built and what is not; no "registry service" claims appear while none exists.

### (h) Search

- **CR-24** — Search covers name, publisher, device class/capability, standard version and status. *Accept:* each dimension returns correct filtered results on a fixture catalogue of at least 10 rows.
- **CR-25** — Search reflects the records of record; no stale rows survive a yank or unlist. *Accept:* the S5 catalogue half.
- **CR-26** — Search requires no service (static generated index is acceptable; a hosted search service is not required). *Accept:* catalogue search functions from a clean static deploy.

### (i) Management — admin (maintainer) side

- **CR-27** — The maintainer sees the submission queue and each submission's stage from one place. *Accept:* queue state is derivable from the repository of record alone.
- **CR-28** — Publish, unlist, advise and yank are each a recorded operation carrying actor, reason and timestamp. *Accept:* every lifecycle change is reconstructable from the record (NFR-3).
- **CR-29** — Yank/advisory semantics reuse the existing admission lifecycle gates (revocation/yanked); the catalogue reflects them and stock gateways already enforce them. *Accept:* a yanked release fails admission on an unmodified gateway and is flagged or removed in the catalogue within one records refresh.
- **CR-30** — Admin management is CLI/records-first; a bespoke UI is not required (gateway-side console needs belong to #210). *Accept:* every operation in CR-27/28 completes without bespoke UI.

### (j) Management — contributor and consumer side

- **CR-31** — A contributor can see all their submissions and plugins with each one's stage, without maintainer mediation. *Accept:* status is queryable by publisher from the records.
- **CR-32** — A contributor withdraws pre-acceptance submissions; accepted releases are immutable — withdrawal after signing means advisory or unlist, never deletion. *Accept:* no operation erases a signed release from history.
- **CR-33** — Consumer-facing management is read-only: adoption guidance, verification steps, status. *Accept:* the consumer surface exposes no write path.

### (k) Home of the lane — the standalone repository question

The issue commits to git-native flow and a central service later. The structural question this PRD must answer is where the lane's **records and surfaces** live. Requirements any home must satisfy:

- **CR-34** — Home-requirements: public visibility; PR-native contribution and review; durable records recoverable from git alone; catalogue generated from records; no coupling to gateway runtime code; mirrors or exports possible (the registry contract already names private mirrors). *Accept:* a clean-room clone of the home repository is sufficient to regenerate the catalogue and verify every published release's digests.

Options considered:

1. **In-tree** (gateway repo: `website/` + records + tooling). One CI, existing stamp discipline. But every third-party submission lands on the gateway's review load, mixed in with control-path work — wrong traffic shape for a hot repo.
2. **Standalone catalogue/registry repository** (e.g. `benchweave-registry`): records plus catalogue data only; community PRs never touch the gateway; mirrors are trivial; matches §18's "source repositories support contributions; signed releases support reproducible adoption". Cost: a third repo and cross-repo coordination — though we already run the SDK split well.
3. **Hybrid**: packaging/submit tooling in the **SDK** repo (where authors already are, CR-7); records and catalogue data in a standalone registry repo; the website (gateway-owned) renders the catalogue from a generated index.

**Recommendation: option 3**, with option 2 as fallback if cross-repo rendering proves awkward. Tooling beside the SDK matches CR-7; records beside nothing-but-records matches CR-34 and keeps third-party traffic out of the gateway; the site keeps its home and its stamp discipline. Whichever option the design record picks must satisfy CR-34's falsifier.

### (l) Malicious-plugin risk and handling (v0.2)

#### (l.1) Threat model — where the trust boundary actually sits

Plugin code executes in-process in the gateway interpreter, on a per-run worker thread, with the gateway process's full native authority: same OS identity, same filesystem and network reach, same interpreter state. The tree concedes this directly — "Adapters are trusted Python, not sandboxed" (`src/benchweave/host/otdp_bridge.py`) and "an integrity boundary for trusted plugins, not a Python sandbox" (`src/benchweave/registry/otdp_loading.py`). A hostile admitted adapter can read the gateway secret from process memory or environment, read and write the store file directly to forge evidence rows, and mutate `sys.modules`/`sys.meta_path` to hijack later loads; nothing in-process blocks any of this.

What actually bounds a plugin is four layers, and which layer is which matters:

1. **Which bytes run.** The registry chain (resolve → admit → activate → load) authenticates provenance (Ed25519 against the origin root), enforces lifecycle and budgets, digest-verifies extraction, and re-hashes bytes at exec time. Every gate verifies *integrity of bytes*; none analyzes *intent of code* ("structural validity never establishes trust", `src/benchweave/registry/schemas.py`). Plugin code first executes at run-build; activation itself is file I/O only.
2. **A cooperative import fence.** Bundle imports resolve only from the verified in-memory inventory; externals are refused unless top-level stdlib. The standard library is allowed wholesale: `subprocess`, `socket`, `ctypes`, `sqlite3`, `os` are all importable. The fence is anti-accident and anti-dependency-bloat, not anti-exfiltration.
3. **Scoped HostServices.** The only sanctioned I/O channel (quota'd evidence retention, permission-gated capture, grammar-guarded transport) — a cooperative convention the adapter can simply ignore.
4. **The systemd deploy unit.** The only OS-level containment, and only under that deployment: unprivileged user, read-only filesystem except the data dir, PrivateDevices, MemoryDenyWriteExecute, no capabilities. It "hardens the blast radius; it is not a VM boundary" — a full escape still reads the data dir and the in-process secret. Dev, test, and Docker postures run plugins with the operator's own authority.

**Classes of malicious plugin** (from the adversarial investigation; both independent refute lanes confirmed each unless noted):

- **M1 — malicious-but-authentic release.** Correctly signed by a trusted publisher or origin key holder; passes every gate. Variants: a hostile dependency closure riding digest pinning (the pin defends transit drift and mix-and-match, never signer intent); an implementation re-expressing a descriptor id it does not honor (the single direction-fixed ownership exemption in closure checking verifies edge shape, not behavioural correspondence); typosquat / namespace confusion (strict routing and one-owner-per-id catch routing errors and dual ownership, not similarity).
- **M2 — authenticity-authority compromise.** Origin Ed25519 key compromise (single verify key per origin, PoC scope: no rotation, thresholds, or key revocation — `src/benchweave/registry/authenticity.py`); trust-root swap (the verify key is loaded from a filesystem PEM with no out-of-band check — `src/benchweave/interfaces/bootstrap.py`); a dev-unsigned origin added by custom code (no production config surface constructs origins; the default session is fail-closed with one signed origin, but the dev loop is a documented workflow).
- **M3 — local-state compromise.** Write access to gateway work_root: a well-formed lower high-water file silently disarms the rollback gate (only malformed files refuse); a forged lock plus digest-consistent cache re-points a commissioned closure to any older release the origin still serves; the approval block in the lock is an unbound plain record citing a hardcoded policy id. Scope precision: arbitrary *new* bytes additionally require the origin to serve them — the pin binds to origin-served bytes.
- **M4 — runtime authority abuse by admitted code.** The in-process abuses above, plus stdlib weaponization (process spawn, outbound connections, native-library load — no third-party dependency needed); unrestricted outbound addresses in the deployed posture (address families fenced, addresses deliberately not); blocking or spinning adapters that deadlines detect but cannot interrupt (in-process, cooperative asyncio), holding the protective path hostage — `_verify` honestly returns SAFE_UNKNOWN on budget exhaustion, never a false verified, but honesty is not actuation; weaker loader legs (the legacy `load_plugin` executes verified bytes with no import fence — no production caller today, exposure is the documented dev loop and tests; the sim-fixture lane runs bare importlib with zero checks, supply-chain-scoped); hostile firmware blobs where the plugin is the carrier and the separately-authorised flash ceremony is the trigger.
- **M5 — measurement and evidence lies.** A realistic fabricated reading passes every plausibility check (freshness, future-stamp, effective-age, Quality.VALID all operate on adapter-self-reported data; the adapter is the only in-process reading source, so in-process corroboration does not exist and cannot fully exist). Sanctioned-channel evidence is integrity-pinned but content-unverified: host-computed digests and quotas mean adapter-supplied values cannot override the record — not that readings are true. Manifest conformance `evidence[]` blocks are self-attestation whose referenced reports are plugin-authored bytes.
- **M6 — response failure.** A revocation or yank published after admission cannot reach commissioned runs: run-build re-verifies manifest digests against the admitted lock but reads no status (`src/benchweave/interfaces/device_closures.py`), so a yanked release keeps executing until someone manually re-resolves and re-admits. Unpublish without reach is not containment.
- **M7 — transport-lane abuse (latent until issue #167).** A descriptor declaring a transport provider will drive scoped instrument transports once the activation lane wires; nothing constructs a provider transport in production today (`ProviderTransport.transfer` raises `NotImplementedError` without an injected runtime, `src/benchweave/content/provider_transport.py`, "Nothing in production constructs these objects yet"), so prevention today is that the lane is unbound. Requirements: publish-time contract-triple declaration and a pre-committed `scoped_transport` tier rule (CR-49), with the ordering call at Q15.

**Considered and refuted** (recorded so they are not re-litigated): *descriptor envelope override* — refuted by both lanes: the numeric safety envelope is commissioned bench-side from qualification evidence (A02/A03; no code consumes descriptor rating fields — a repo-wide search at the audited revision finds zero consumers), so a lying descriptor deceives the operator at commissioning but cannot widen a commissioned envelope; the surviving residue (self-declared matching metadata, firmware-compatibility claims, and the registry spec section 10 semantic admission checks that remain unimplemented locally) is folded into CR-37 and Q12. *"Operator config accepts a dev origin"* — refuted: no production config surface constructs origins (the corrected posture question is Q17).

#### (l.2) Mechanisms map

| Class | Prevention (today) | Detection (today) | Response (today) |
|---|---|---|---|
| **M1** malicious-but-authentic | Byte-integrity chain only: Ed25519 authenticity, lifecycle/revocation gates, budgets, digest-verified extraction, exec-time re-hash. Intent analyzed by nothing. Procedural only: recorded principal approval (unbound — see M3). | Platform detection at review time (v0.3): code scanning, dependency review, secret scanning (CR-59/CR-60) narrow the vulnerability- and dependency-shaped variants; intent still unanalyzed. Import fence and session poisoning catch accidents and protocol lies, not intent. | Yank/revocation, admission-time only (see M6); GHSA escalation channel (CR-62). |
| **M2** authenticity-authority compromise | Single Ed25519 verify key per origin (PoC scope: no rotation, thresholds, key revocation). Trust root loaded from a filesystem PEM, no out-of-band check. Default session fail-closed (one signed origin; a dev origin requires custom code). | None — a swapped root makes every downstream signature check attacker-controlled. | None distinct from per-release yank. |
| **M3** local-state compromise | Malformed state refuses loudly (`high_water_invalid`); cache re-verified against lock pins. A *well-formed* rewrite passes: lowered high-water disarms rollback; forged lock + digest-consistent cache re-points closures to older origin-served releases. Single-writer store hold is the documented mitigation. | None for well-formed forgeries. | None. |
| **M4** runtime authority abuse | Which-bytes gates + cooperative fence + scoped services; the systemd unit (unprivileged user, read-only FS except data dir, PrivateDevices, MemoryDenyWriteExecute) is the only OS containment — deployment-conditional, blast-radius hardening, not a VM boundary. Stdlib imports pass the fence; outbound addresses unrestricted (families fenced only); no CPU/memory kill lane. | MemoryDenyWriteExecute blocks new W+X mappings only; nothing detects well-formed abuse. | Process restart outside the unit; nothing in-process. |
| **M5** measurement/evidence lies | Plausibility checks (freshness, future stamps, effective age, Quality.VALID) catch lazy lies only. Host-computed digests/quotas pin record integrity, not content truth. | Cross-validation named, not built; in-process corroboration of a realistic lie does not exist and cannot fully exist (the adapter is the only reading source). | None. |
| **M6** response failure | — | Revocation publishes fine at the origin. | Run-build verifies manifest digests but reads no status; a yanked release runs until a manual re-resolve. |
| **M7** transport-lane abuse (latent) | Unbound in production: `ProviderTransport.transfer` raises `NotImplementedError` without an injected runtime; `build_run` passes no transport/providers. | None needed while unbound. | n/a until #167; CR-49 pre-commits the control point. |

#### (l.3) Handling story

Prevention of intent-side risk lives **upstream of admission, in the publishing process** — not because the gateway is careless, but because admission is byte-integrity by design and this PRD does not change admission semantics (CR-13). A correctly-signed malicious release therefore has no technical backstop in the gateway; the lane's compensating controls are publisher vetting with dev-provenance refusal (CR-35), immutable source linkage (CR-36), closure-level review (CR-38), namespace hygiene (CR-39), signed approvals (CR-42), capability declaration (CR-45), transport declaration (CR-49), and firmware provenance (CR-50), with the review chain producible on demand (CR-54). Trust-root distribution and key lifecycle (CR-40, CR-41) close the M2 path where a swapped PEM currently defines "authenticated".

Detection happens at two moments only. At review: the closure diff, the unverified-content marking, and the execution-model disclosure (CR-37, CR-52) put the self-attested and authority-granting facts in front of the accountable reviewer. In the field: capability mismatches surface only under the isolated evaluation posture for untrusted publishers (CR-46), and measurement lies are detectable only by cross-validation against a second qualified instrument — named as the detection lane and scoped honestly (CR-51), because in-process corroboration cannot exist. Loader parity and sim-lane separation (CR-43, CR-44) close the two weaker execution legs so published code never runs with less containment than the OTDP path.

Response must actually reach running gateways: signing and lifecycle exist today, but yank-without-reach is unpublish, not containment — CR-53 makes reach the requirement and leaves the mechanism shape to an owner call (Q14). Where a requirement below binds what an operator must be shown, it binds the **decision record's data**; the console that renders it is issue #210's surface, and version-declaration semantics stay with issue #203. None of these requirements alter what gateway admission verifies; the two places a threat genuinely wants that (intent verification, capability enforcement) are surfaced as owner-call open questions (Q12, Q13) instead. And one structural need is recorded rather than solved: a plugin-independent safe-state path (hardware watchdog or gateway-direct protective lane) so verified safe endings never depend on hostile code being responsive — CR-48 qualifies the publishable control but concedes the boundary (the asyncio deadline detects but cannot interrupt a blocking adapter, `src/benchweave/host/otdp_bridge.py`), so the protective-lane fork rides Q16.

#### (l.4) Requirements

**CR-35 — Publisher identity and dev-provenance refusal.** The publishing lane binds every published release to a vetted publisher identity and refuses submissions whose lineage resolves only through a dev-unsigned origin (dev-prefixed registry id, no trust root); no dev registry id appears in the published index.
*Accept:* a dev-unsigned-lineage submission is refused at publish with a named error, and the published index contains zero dev-prefixed registry ids.

**CR-36 — Immutable source linkage.** Every publish record carries a resolved immutable source ref (commit digest) for the release; gateway admission denies only the four-name mutable set {main, master, HEAD, latest}, so publish-time must refuse what admission lets through.
*Accept:* a submission whose source linkage is a moving branch or tag name outside the four-name admission denylist is refused at publish even though it passes gateway admission today.

**CR-37 — Self-attested content marked unverified; digests authoritative.** Wherever manifest self-declaration appears in a publishing or approval surface — conformance `evidence[]`, version and dependency labels, provenance labels, descriptor matching metadata — it is marked unverified, and the release digest is identified as the authoritative identity (version semantics: issue #203; console rendering: issue #210).
*Accept:* an approval decision record for a release whose only conformance evidence is manifest self-attestation carries an explicit unverified marker, and no publishing surface renders self-attested content as verified.

**CR-38 — Closure-level review artifact.** Publish-time review covers the whole dependency closure: the publish record enumerates dependencies added or changed versus the prior release of the same package, and the reviewer sign-off names the closure digest it covered.
*Accept:* a submission whose dependency set differs from the prior published release yields a publish record enumerating the additions and changes, and a sign-off naming a different closure digest than the one published fails the audit check.

**CR-39 — Namespace hygiene.** Namespace assignment is restricted to verified publishers under a recorded similarity rule that flags or refuses lookalike requests against existing namespaces.
*Accept:* a namespace request similar to an existing namespace under the recorded rule is flagged or refused at publish, and the approval decision input names the verified publisher behind the namespace, not only the package id.

**CR-40 — Trust-root distribution with out-of-band verification.** Origin and publisher verify keys reach gateways through a verifiable channel (a signed fingerprint list published with the index), and provisioning checks the installed root's fingerprint against that list before the root is trusted.
*Accept:* a gateway provisioned with a root whose fingerprint is absent from the signed list refuses origin verification with a named error, instead of loading whatever PEM sits at `registry_dir/keys/main.pub.pem` unchecked as it does today.

**CR-41 — Key lifecycle.** The lane supports rotating and revoking an origin or publisher verify key, announced through the CR-40 channel, as a channel distinct from per-release yank.
*Accept:* after a recorded rotation and stated cutover, a release signed only by the retired key fails signature verification against the updated root set, and a key can be revoked without unpublishing each affected release individually.

**CR-42 — Signed approvals carried in the index.** The publish-side approval is signed by the approving principal or publisher key and published bound to the release digest, making gateway-local approval assertions cross-checkable.
*Accept:* each index record carries a verifiable approval signature over the release digest, and a gateway-local approval block that disagrees with or lacks the published approval is surfaced as drift at the next index consultation — today the lock's Approval is an unbound plain record citing a hardcoded policy id.

**CR-43 — Loader parity for published packages.** A registry-published package resolves only through the OTDP loader leg (bundle import fence, exec-time digest re-verification); the legacy leg, which executes verified bytes with no import filter, refuses package-sourced plugins.
*Accept:* loading a registry-published package through the legacy leg (`src/benchweave/registry/activation.py` `load_plugin`) refuses with a named error, and no shipped path resolves published packages without the import fence.

**CR-44 — Sim-lane structural separation.** The sim-fixture lane accepts only the fixed in-tree fixture set, and registry packages are structurally excluded from it.
*Accept:* a guard test fails if the sim lane (`src/benchweave/interfaces/app.py` `_load_sim_plugin`, today bare importlib with no verification) can load anything outside the fixed in-tree fixture map.

**CR-45 — Declared capabilities at publish.** Every published release carries a capability declaration — network egress, subprocess or native-library use, filesystem writes beyond evidence retention — in its publish record and index entry, displayed in the approval decision input; enforcement at gateway admission or deploy is explicitly out of scope here (Q13 — enforcement would change admission semantics, which CR-13 forbids for this PRD).
*Accept:* a submission without a capability declaration is refused at publish, and the approval decision input for a release declaring egress shows that declaration.

**CR-46 — Isolated evaluation posture.** Trial or evaluation of a plugin from an untrusted or newly-verified publisher runs only under an enforced isolation posture at least equivalent to the deployed unit's hardening — never with the operator's own authority — and the untrusted-trial flow refuses to start without it.
*Accept:* invoking the documented trial flow for an untrusted-publisher plugin without the isolation mechanism refuses with a named error, and the publishing documentation states the deployment requirement as part of the support contract.

**CR-47 — Egress decision recorded.** The deploy set's deliberate omission of an address allowlist (only address families are fenced) is re-decided against plugin egress: either an allowlist ships once the lane can name legitimate endpoints, or the accepted risk is recorded with a rationale that addresses outbound plugin traffic — the standing rationale (loopback bind plus the family fence) constrains bind surfaces, not outbound connections.
*Accept:* the permissions record either documents an address allowlist with its endpoint-list source, or records the accepted risk explicitly covering plugin-originated outbound connections; the unqualified current rationale is not left standing.

**CR-48 — Protective-path responsiveness evidence.** Qualification of a published instrument plugin includes measured dispatch and verify responsiveness under load; a plugin that blocks its bridge runner beyond the protective budget during qualification does not qualify (in-process, the asyncio deadline detects but cannot interrupt a blocking adapter, so qualification evidence is the publishable control).
*Accept:* a published instrument plugin's qualification record contains measured responsiveness under load, and a qualification run with an adapter blocking beyond budget records a failure, not a pass.

**CR-49 — Transport declaration pre-commitment.** A release whose descriptor declares a transport provider publishes the admitted contract triples it intends to drive, and publish refuses the declaration-less case; the rule for which publishers may hold `scoped_transport` exists before the transport lane first activates in the gateway (issue #167 carries the activation wiring — nothing constructs a provider transport in production today).
*Accept:* a transport-declaring submission without named admitted contract triples refuses at publish, and the scoped_transport tier rule is recorded in the lane rules at the moment the transport lane activates rather than retrofitted after it.

**CR-50 — Firmware provenance.** A plugin bundling firmware carries vendor-signed provenance pinned against a vendor manifest, not the publisher's own signature alone; the separately-authorised flash decision surface displays whether firmware provenance is vendor-verified (installing plugin software does not flash device firmware — the plugin is the carrier, the authorisation ceremony is the trigger).
*Accept:* a submission bundling `firmware/` without vendor attestation refuses at publish with a named error, and an operator-facing flash decision shows the firmware provenance state.

**CR-51 — Measurement-truth scope stated.** The published documentation states plainly that run evidence is integrity-pinned but content-unverified against a lying adapter, and names cross-validation against a second qualified instrument as the detection lane for plausible-reading forgery.
*Accept:* the boundary statement and the cross-validation lane are findable in the same documentation set that claims evidence-exactness, so no reader is left with the impression that digest verification establishes measurement truth.

**CR-52 — Execution-model disclosure at approval.** The approval decision input for any published executable states the execution model plainly — in-process execution with full gateway authority, no Python sandbox — so the recorded approval shows the approver was told what the approval grants.
*Accept:* an approval decision record for a published release includes the execution-model disclosure, and an approval recorded without it fails the audit check.

**CR-53 — Response reach.** A revocation or security advisory published after admission reaches commissioned gateways within a stated, testable time bound: the next run-build or commissioning attempt for a closure containing the affected release either refuses or delivers a recorded operator advisory (the mechanism shape is an owner call — Q14; the reach is the requirement).
*Accept:* publishing a revocation for an admitted-and-activated release produces, within the stated bound, a refusal or a recorded advisory at the gateway — today run-build verifies manifest digests but reads no status, so a yanked release keeps executing until a manual re-resolve.

**CR-54 — Accountability record on demand.** For every published release the lane can produce the full review chain on demand: publisher identity, reviewer identity, signed approval, closure digest covered, and capability declaration.
*Accept:* an incident exercise against a published release produces that chain from the lane's own records, without reconstructing it from gateway-local state.

**CR-55 — Local-state trust boundary decided and recorded.** The posture for gateway-local admission state (lock, cache, high-water, activation records) is decided: either local write access to work_root is explicitly out of threat model with the single-writer store hold named as the mitigation and hardening guidance published, or tamper-evident state work is scheduled; the publishing lane never accepts gateway-local state as provenance evidence.
*Accept:* the decision record exists and states the precise local-writer capabilities (disarm rollback with a well-formed lower high-water; re-point a commissioned closure to any older origin-served release; forge the unbound approval block), which today are documented nowhere an operator would find them.

#### (l.5) NFR additions (extend section 6)

- **NFR-S1 — Honesty of protection claims.** No publishing-lane surface states or implies sandboxing, intent verification, or measurement-truth verification for plugin code. *Accept:* a docs-and-surface audit at review time finds no unqualified "sandbox", "verified", or "trusted" claim adjacent to plugin execution or evidence.
- **NFR-S2 — Response bound stated and testable.** The CR-53 reach bound is stated with its denominator — which gateway states it covers (reachable; offline since publication) — and an exercise demonstrates it. *Accept:* the bound's statement names the covered gateway states, and the exercise result is recorded against it.
- **NFR-S3 — No unbounded run-path cost.** Whatever mechanism implements CR-53 adds bounded, measured cost to run-build or commissioning. *Accept:* the design record for the chosen mechanism carries a measured cost figure at commissioning with its measurement conditions. Direction (non-binding): a cached status read with a staleness bound.

#### (l.6) Residual risk (honest — not solved)

Three residuals remain open by design and must not be read as solved. (1) **Operator commissioning per A02 stays load-bearing:** numeric safety envelopes are commissioned bench-side from qualification evidence, and nothing in the gateway consumes descriptor rating fields (the refuted envelope-override threat proved exactly this — a repo-wide search at the audited revision finds zero consumers). That is the defense, and it is also the residual: a descriptor that lies about device class or firmware compatibility deceives the operator at commissioning, not the envelope machinery — review and qualification are the only controls, and they are human. (2) **Deployment isolation is conditional and bounded:** the systemd unit is the only OS-level containment, applies only to that deployment, is explicitly not a VM boundary, and a full escape still reads the data dir and the in-process secret. Dev, test, and Docker postures give plugins the operator's own authority, and outbound addresses remain unrestricted in the deployed posture today (families fenced, addresses not). A plugin-independent safe-state path (hardware watchdog or gateway-direct protective lane) is a recorded structural need (M4/T-A11), not a shipped mechanism. (3) **Insider trust:** the origin key holder and every vetted publisher sit inside the trust boundary — a correctly-signed malicious release has no technical backstop, and the tree's own no-sandbox concession (in-process token forgery, direct store writes, `sys.modules` hijack all reachable) is accountability-bound, not fixed; publish-time review owns that residual. Local write access to gateway work_root can still disarm rollback and re-point commissioned closures to older origin-served releases — this lane's mitigation is refusing to treat gateway-local state as provenance, not protecting the files. And measurement truth stays outside in-process verification: a realistic fabricated reading passes every plausibility check because the adapter is the only reading source; cross-validation against a second qualified instrument is named as the detection lane, not built.

#### (l.7) GitHub-native detection and response surfaces (v0.3)

Platform-native mechanisms on the lane's repositories, free on public repos, standard and supportable, become the review-time detection floor, the machine-evidence feed for CR-8/CR-38, and the escalation channel for CR-53. None of them analyzes intent: this group narrows M1's vulnerability-shaped and dependency-shaped variants only, and amends the §5(l.2) mechanisms map (M1 detection becomes "platform detection at review time; intent still unanalyzed"). Nothing here changes what gateway admission verifies (CR-13), and no surface may render a clean scan as "verified" (NFR-S1). CR numbering continues from §5(m).

**CR-59 — Platform detection baseline on every lane repository.** Every repository of the lane — whichever home §5(k) picks, plus the SDK repository — carries code scanning (CodeQL default setup, Python), secret scanning with push protection (plus a custom pattern for the trust-root PEM shape), a committed `dependabot.yml`, and the dependency-review action as a required status check on submission PRs.
*Accept:* a fixture submission carrying a CodeQL-detectable defect or an advisory-flagged dependency cannot merge, and pushing a PEM-shaped fixture key to a lane repository is refused. (Baseline absent today: verified 2026-09-26 — no code-scanning config or `dependabot.yml` in either repository.)

**CR-60 — Platform findings as named review evidence.** The CR-8 checklist and the CR-38 closure review record the platform findings consulted at the CR-36-pinned revision — code-scanning results, dependency-review diff, secret-scanning state — as machine evidence. Findings are advisory to the accountable reviewer; the identified-reviewer requirement is unchanged.
*Accept:* a review record naming no scanning findings consulted at the pinned revision is invalid under the same CI check that enforces CR-10.

**CR-61 — Records-branch ruleset.** The repository of record's records/default branch enforces required approvals, required status checks (including the CR-10 record-validity check), linear history, and no force pushes or direct pushes.
*Accept:* a direct push or an unapproved merge to the records branch is refused — NFR-3's reconstructability becomes enforced, not conventional.

**CR-62 — Advisory channel for security-class incidents.** A malicious plugin or exploitable published release publishes a GitHub Security Advisory on the repository of record, in addition to the CR-28 record and catalogue row. Recorded as presentation and intake only: gateway reach stays with CR-53 (Q14), and the lane's advisory policy covers malicious plugins that the gateway `SECURITY.md` scopes out.
*Accept:* a fixture yanked-for-security release carries an advisory discoverable from the repository, and the lane documentation states the reach boundary.

### (m) Standalone and shared plugins — differentiation (v0.3)

The catalogue will hold more than admitted releases: in-tree proof fixtures, and standalone plugins authors share directly from their own repositories — not yet admitted, maybe never. Differentiation is a first-class, machine-checkable property of every record, not a prose convention, and the repository of record doubles as the author-sharing mechanism.

- **CR-56 — Plugin kind taxonomy and tagging.** Every records entry and catalogue row carries a machine-checkable kind tag generated from the record (never hand-typed on the surface, per CR-21): at minimum `admitted-release`, `in-tree-fixture`, `community-shared`, with provenance flags carried alongside (for example `dev-unsigned` lineage). *Accept:* a records entry without a kind is refused at write time, and every catalogue row renders its kind.
- **CR-57 — Author-shared listing semantics.** The repository of record may carry author-shared standalone plugins as a sharing mechanism: each shared entry carries at least publisher identity, a pinned immutable source ref, licence, declared compatibility, and an explicit unverified marker (CR-37 class). A shared entry never appears in the default available view and is never rendered as admitted (CR-22 holds); sharing is not an admission path, and admission remains the only route to available status. *Accept:* a shared listing renders with kind `community-shared` and the unverified marker in every view, is excluded from the default available listing, and a consumer can reach its pinned source ref and publisher identity in one step.
- **CR-58 — Kind as a search and filter dimension.** The kind tag is a first-class search dimension (extends CR-24) and consumers can filter to or exclude shared plugins. *Accept:* searching with kind=`community-shared` returns exactly the shared set on a fixture catalogue, and kinds are never mixed in a view without the tag showing.

Cross-references: a shared plugin is untrusted by definition, so the isolated evaluation posture (CR-46) applies to it by default; NFR-S1 forbids any surface implying shared means verified; unlisting a shared listing is a recorded admin operation (CR-28 class). The §5(l) threat classes apply to shared plugins in full — the kind tag is the differentiation and honesty mechanism, not a trust reduction.

## 6. Non-functional requirements

- **NFR-1** Public-repo hygiene: no real bench names, client identifiers or local-machine artifacts anywhere in submissions, records or catalogue content (the standing corpus rule).
- **NFR-2** Single-maintainer operable today (the burden is a checklist and a signature), multi-contributor-ready tomorrow (roles delegate without redesign).
- **NFR-3** Auditability: every transition — submit, review, sign, publish, advise, yank — is reconstructable from git history.
- **NFR-4** Availability independence: the path works with no running service (git plus a static catalogue).
- **NFR-5** CI economy: records and catalogue checks stay static-analysis class (manifest, digest, stamp guards).
- **NFR-6** Agent legibility: the path is drivable by AI coding agents; the develop-your-device lanes can grow a "publish your plugin" stage.
- **NFR-7** Privacy: a submitter is a GitHub identity and a publisher name; nothing more is collected.
- **Security additions (v0.2):** NFR-S1 (honesty of protection claims), NFR-S2 (response bound stated and testable) and NFR-S3 (no unbounded run-path cost) are defined in §5(l.5) and bind group (l) and every increment that touches it.

## 7. Open questions for commentary

1. **Home of the lane.** Recommend hybrid (option 3 above). Does that hold, or do we want standalone-everything (option 2) or in-tree (option 1)?
2. **Signing scope.** Release signature only, or countersigned review? Recommend: one signature, with the checklist outcome as fields **inside** the signed manifest — the signature attests release and review together.
3. **Namespace scheme.** Recommend `publisher/plugin` in the manifest id, reserving `dev-` and in-tree fixture names. Device-class-rooted namespaces are the alternative.
4. **Where the review record lives.** Recommend a committed `records/` directory in the home repo (PR discussion plus committed outcome). CR-9's falsifier wants git recoverability; PR threads alone do not give it.
5. **Catalogue scope.** Recommend published third-party releases only; in-tree proof plugins stay on their docs pages. Or do the fixtures appear as a separate "reference plugins" group? And is author-sharing of standalone plugins sanctioned in the repository of record at all (CR-57), with what takedown path (Q20)?
6. **AI device reviewer as a gate.** Recommend advisory-only at first, mandated as a pre-check once its false-positive rate is measured on real submissions.
7. **Search depth.** Recommend static client-side search over a generated index for the first cut (CR-26).
8. **Advisory distribution.** Recommend the catalogue as the single public advisory point; gateways already consume status files, so the catalogue is presentation, not mechanism.
9. **Ownership transfer.** Recommend allowing publisher-to-publisher transfer with both parties' recorded consent (CR-17).
10. **Submit command placement.** Recommend the SDK CLI (`benchweave-sdk submit/…` shape, name open) — authors are already there (CR-7).
11. **Version declaration.** Recommend this lane fixes the *location* (manifest field) and #203 owns the *semantics* entirely (CR-18). If #203 later relocates the declaration, this lane follows.

**v0.2 additions (from §5(l))**

12. **CR-13 tension (owner call).** Several confirmed threats — the signed-malicious-release class (M1), the implementation-re-expresses-a-descriptor-id exemption in closure checking, and the registry spec section 10 semantic admission checks ("provided IDs match actual profile/descriptor contents") that remain unimplemented locally — can only be closed by changing what admission verifies, from bytes to semantics. Hold the CR-13 line and rely on this group's publishing-process controls, or schedule an admission-semantics change as its own effort?
13. **CR-13 tension, milder (owner call).** CR-45 declares adapter capabilities at publish. Enforcing those declarations at gateway admission or deploy policy would change admission semantics. Where does enforcement land — deploy unit policy, an admission gate (own effort), or evaluation-only — and in which effort?
14. **Response-reach shape for CR-53 (owner call).** Run-build lifecycle re-read, forced re-admission on advisory, or operator notification with recorded delivery — which mechanism, and what time bound per NFR-S2 (stated with its denominator: which gateway states the bound covers)?
15. **Transport lane ordering for CR-49 / issue #167 (owner call).** Pre-commit the scoped_transport control point — publish-time contract declaration plus publisher tiering — before the activation lane wires, or let the lane land untiered and retrofit afterwards, accepting the retrofit cost? (The refute lanes split on this: one graded the threat confirmed as-is, the other an explicit owner fork; the lane itself is unbound in production today, so the threat is latent either way.)
16. **Isolation end-state and the protective lane (owner call).** Is per-plugin process or interpreter isolation — the structural fix for the M4 runtime-authority class — in scope for any near-term increment, or accepted as residual behind the systemd deploy unit and publishing accountability? The same fork covers a plugin-independent safe-state path (hardware watchdog or gateway-direct protective lane) so verified safe endings never depend on hostile code being responsive (M4/T-A11), and a tamper-evident evidence chain (a MAC keyed outside plugin reach). Direction (non-binding): tier published third-party plugins toward isolated workers; all three ride one structural decision.
17. **Dev-origin production posture (owner call).** Adding a dev-unsigned origin today requires custom code — no config surface accepts origins, and the default session is fail-closed on one signed origin. Should a production-mode gateway nonetheless structurally refuse dev-unsigned origins (mode flag), or does the documented dev-loop guidance (keep dev roots local and disposable) carry this alone?
18. **Egress allowlist authority for CR-47 (owner call).** Once the lane can name legitimate endpoints, who owns the address allowlist — publisher capability declaration, origin policy, or operator deploy config?
19. **Re-issue needed before (l) is complete.** One threat-catalogue entry reached both refute lanes truncated before its gap and impact text, and both lanes declined to verdict a fragment. The three status gates it references — expiry, future-time tolerance, and the sequence high-water — are verified real machinery. The full entry must be re-issued and verdicted before group (l)'s requirements are treated as complete against it. (Refute coverage for the record: lane 1 recorded 32 verdicts, lane 2 recorded 31, against a 56-entry catalogue; 59 confirmed gap, 2 owner calls, 2 refuted.)

20. **Author-sharing moderation (owner call, v0.3).** If CR-57's `community-shared` listing is sanctioned: is it open-listing (any vetted publisher may share, takedown on recorded request) or curated (each shared entry gets a light-touch check first)? Recommend open-listing with recorded takedown — the kind tag and CR-46 carry the risk, and curation implies an availability promise the lane cannot keep. Who can request a takedown (anyone, or the publisher only), and is there a response expectation?

21. **Publisher-repository posture (owner call, v0.3).** A publisher's own repository cannot be mechanically verified from the repository of record. Are publisher-side protections (push protection, their own code scanning, advisories) required as CR-39 vetting-checklist declarations, recommended-but-unrecorded, or ignored? Recommend: declared in the CR-39 checklist and rendered declared-not-verified (CR-37 class) — enforcement claims would be dishonest.

## 8. Suggested increments

1. **The ADC-friction remover** (the issue's named first increment): contributor publishing docs + packaging/submit tooling (SDK-side) + the owner review checklist + committed review records. No website change, no service. *Acceptance:* S1, S2 and S3 hold on a real plugin of the ADC class, **and** the submission pipeline carries its §5(l) entry criteria as gates: dev-provenance refusal (CR-35), immutable source refs (CR-36), capability declaration (CR-45), firmware provenance (CR-50), transport declaration (CR-49), and the closure-diff review artifact (CR-38). A pipeline that admits dev-unsigned lineage, moving source refs, or declaration-less releases does not satisfy the increment even if the index and signing work.
2. **Catalogue + search on the public website**: records-derived plugin surface + static search, with the stamp guard extended. *Acceptance:* S4 plus the CR-20/21/24 falsifiers on a fixture catalogue.
3. **Management surfaces**: admin queue and lifecycle operations as records/CLI (CR-27 to CR-30), contributor status (CR-31, CR-32). *Acceptance:* S5 — and the incident-response half exits on CR-53's bounded reach with NFR-S2's stated bound and its denominator; unpublish-without-reach no longer closes it. Publisher identity/vetting (CR-39 to CR-42) and the accountability chain (CR-54) ride whichever sub-increment owns namespace, identity and records.
4. **(Conditional) home migration**, only if the design record picks option 2 or 3: move records and the catalogue data source; tooling stays SDK-side. *Acceptance:* CR-34 holds on the new home.
5. **Execution posture (new, warranted by §5(l))**: loader parity (CR-43), sim-lane separation (CR-44), the isolated evaluation posture (CR-46), the egress decision (CR-47), protective-path responsiveness evidence (CR-48), and the boundary-documentation requirements (CR-51, CR-52, CR-55). These bind the gateway/plugin contract the publishing lane depends on, not the lane's own surfaces, so forcing them into a publishing increment would blur its review. *Acceptance:* each CR's falsifier holds. If the owner holds the line at four increments, these land as named deferrals with owners inside existing increments, and the (l.6) residual note carries them explicitly. The cheap documentation-boundary requirements (CR-51, CR-52, CR-55) should ride whichever increment ships first.

**Relationship to #203:** CR-18 and CR-19 are the only version-declaration touchpoints; the design record must cross-reference #203's PRD so pin semantics do not diverge. **Relationship to #210:** the gateway operator console is out of scope here; CR-30's admin surface is catalogue/registry management, not gateway administration, and where CR-37/CR-52 bind what an approver must be shown, they bind the decision record's data — #210 owns any console that renders it.
