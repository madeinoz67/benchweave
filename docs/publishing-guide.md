# Publishing a plugin

The contributor path from a finished plugin to a signed, admitted release.
Git-native end to end: a submission is a pull request (PR) against the
[registry repository](https://github.com/madeinoz67/benchweave-registry), and
no service is required at any point.

**Baseline:** registry standard 0.1.2 (the review block inside the signed
manifest). The tools are `benchweave-sdk package` and `benchweave-sdk submit`
(SDK 0.4.0+). The maintainer does the review and signs.

**Admission posture:** the registry repository **states and advertises**.
Each publish record carries the pinned gateway version the release targets
(`gateway_ref`, advertised in the index). The **client enforces at import
time**. Nothing gates admission at publish.

> **WARNING:** An accepted release executes in-process with full gateway
> authority. There is no Python sandbox (CR-52).

## The path

1. **Package** — one command, offline (keyless by default):

   ```
   benchweave-sdk package <plugin-dir> \
     --registry-clone <benchweave-registry checkout> \
     --source-url https://github.com/<you>/<plugin> \
     --revision <40-or-64-hex commit digest> \
     --publisher <your-vetted-publisher-id> \
     --out <dir>
   ```

   Every manifest pin derives from the plugin's own tree. The output is
   byte-reproducible for identical inputs. Nothing is hand-assembled.
   Declare capabilities with `--capability network-egress`, `--capability
   subprocess-or-native-library` or `--capability filesystem-writes`. The
   flags are repeatable. Pass none of them for an explicit none. A
   declaration is always needed. **The publisher signs at package time**:
   use `--publisher-key <your-ed25519.pem>` to apply your signature over
   the manifest. Use `--timestamp-token` (from `benchweave-sdk timestamp
   --tsa-url …`) to attach an RFC 3161 trusted timestamp from a timestamp
   authority (TSA). The signature then stays valid after your key expires
   or is revoked.

2. **Submit** — run `benchweave-sdk submit <dir> --registry-clone <working
   clone>`. The tool writes the artefact set into the registry repository's
   submission layout. It creates the branch. When `gh` is present, the tool
   opens the PR. Otherwise it prints the compare URL.

3. **Review** — the maintainer reviews against the versioned
   [checklist](https://github.com/madeinoz67/benchweave-registry/blob/main/review-checklist.md)
   plus the machine evidence (platform findings at the pinned revision).
   The maintainer records the outcome in the registry repository's
   `records/` tree.

4. **Validate and record** — the registry VALIDATES + PUBLISHES + LABELS,
   and never signs. `scripts/registry/sign_release.py` here is
   validate-and-record. It re-derives the manifest and verifies YOUR
   signature against your recorded public key. It labels the release
   `signed-valid` or `unsigned`. The registry REJECTS a present signature
   that does not verify. With a trusted timestamp, the registry judges
   validity at the time the TSA attested the signature. The review block
   rides inside the recorded manifest. One record attests release and
   review together. Your signed submission bytes ride beside it.

5. **Verify** — anyone, from a clean clone of the registry repository
   alone, runs `uv run python scripts/verify.py`. The script validates
   every record. It verifies every signature and digest. It prints the
   accountability chain (publisher, reviewer, outcome, closure digest,
   capability declaration).

## Required artefacts

A submission is a single generated artefact set. The components are the
same enumeration the packaging tool refuses without, and the one the lane's
records schema needs on review:

```text
adapter-source
build-provenance
capability-declaration
closure-diff
conformance-evidence
dependency-lock
descriptor
licence
payload-inventory
release-manifest
```

## Entry gates (refusal is the default)

Packaging refuses, with a stable machine prefix, when:

| Prefix | Requirement |
|---|---|
| `dev_lineage_refused:` | no dependency resolves through a dev-unsigned origin (dev-prefixed registry id) |
| `source_ref_mutable:` | the source linkage must be a commit digest, never a branch or tag name |
| `capability_declaration_absent:` | the closed three-way capability declaration is needed. All-false is an explicit none |
| `transport_triples_absent:` | a descriptor that declares a transport provider must publish its admitted contract triples |
| `firmware_provenance_absent:` | firmware in the tree needs a vendor attestation. Without it, packaging refuses. WITH an attestation the release publishes with the bytes **vendor-distributed**. The payload-role enum carries no firmware role, so the bytes are never bundled. The attestation is recorded in the submission draft and the publish record. The index advertises it. Enforcement is the client's decision |
| `closure_diff_absent:` | the publish-record draft must carry the dependency closure diff versus the prior release |
| `namespace_reserved:` or `namespace_collision:` | namespace hygiene under the committed lane rules (refused). Collisions are per-author. Your own next version of an existing package routes to the closure diff. It is never a collision. Another author's claim to an existing package id collides. The same device name under a different author's namespace is allowed |
| `namespace_lookalike:` | a name similar to an existing namespace under the committed similarity rule. The tool flags it for review. It does not refuse it. The finding rides the submission draft (`namespace_lookalikes`) and prints at package time, so the reviewer consults it (CR-39) |
| `component_absent:<name>` | a required artefact component is missing from the plugin tree |

## Honest boundaries (read before you rely on any of this)

- **Measurement truth (CR-51).** Run evidence is integrity-pinned but
  content-unverified against an adapter that sends false readings. Digest
  verification establishes byte integrity, never that a reading is true.
  Cross-validation against a second qualified instrument is the named
  detection lane for forgery with plausible readings. It is not built.
  Nothing in the publishing surfaces states or implies otherwise.
- **Execution model (CR-52).** See the WARNING above The path. Every
  accepted review record carries this disclosure verbatim. The maintainer
  was told what the approval grants.
- **Local state (CR-55).** Gateway-local admission state (lock, cache,
  high-water, activation records) is never provenance evidence. Local
  write access to a gateway's work root can disarm rollback with a
  well-formed lower high-water. It can re-point a commissioned closure to
  older origin-served releases. It can forge the unbound approval block.
  The single-writer store hold is the mitigation that is in place. The
  project records tamper-evident state work as a structural need. It is
  not shipped. The publishing lane never accepts gateway-local state as
  provenance.
- **Response reach (NFR-S2/NFR-S3, issue #226).** A published revocation,
  yank or advisory reaches the gateway at the NEXT run-build of a
  commissioned closure. The delay is at most 5 minutes (300 s) after the
  status document is published. This bound covers only
  gateways that are reachable at a next run-build. A gateway that is
  offline since publication, or that runs no builds, is covered by the
  recorded operator-delivery half instead. Its refusal or advisory
  reaches the gateway at its next consult, whenever that happens. Until
  then the bound makes
  no claim. At that run-build, a revoked or yanked release refuses the
  run (`closure_status_revoked` / `closure_status_yanked`). An advisory
  does not refuse the run. It is delivered as a recorded operator notice
  under the gateway's advisories directory. The consult verifies
  every status document against the gateway's trust root. If the origin
  serves no status document, the run-build refuses
  (`closure_status_absent`). It never assumes `published`.
- **What review is not.** Structural validity never establishes trust. A
  correctly-signed release carries no technical backstop against malicious
  intent. Publish-time review owns that residual. A clean platform scan
  never marks a release "verified".
- **Publication never authorizes control.** A published, signed, admitted
  release is data until commissioned locally on a specific bench (REG-3).

## Where things live

| Thing | Home |
|---|---|
| Records, releases, lane rules, checklist, public root | `benchweave-registry` (the registry repository) |
| Packaging and submit tooling | the SDK (`benchweave-sdk package` and `benchweave-sdk submit`) |
| Signing (`sign_release.py`) and this guide | this repository |
| Admission (unchanged) | this repository's registry machinery: what stock admission verifies today is exactly what a published release must satisfy (CR-13) |
