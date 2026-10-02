# Publishing a plugin

The contributor path from a finished plugin to a signed, admitted release.
Git-native end to end: a submission is a pull request against the
[registry repository](https://github.com/madeinoz67/benchweave-registry), and
no service is required at any point.

**Baseline:** registry standard 0.1.2 (the review block inside the signed
manifest). The tools: `benchweave-sdk package` and `benchweave-sdk submit`
(SDK 0.4.0+), review and signing maintainer-side.

**Admission posture:** the registry repository **states and advertises** —
each publish record carries the pinned gateway version the release targets
(`gateway_ref`, advertised in the index) — and the **client enforces at
import time**; nothing gates admission at publish.

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

   Every manifest pin derives from the plugin's own tree; the output is
   byte-reproducible for identical inputs; nothing is hand-assembled. Declare
   capabilities with `--capability network-egress` / `--capability
   subprocess-or-native-library` / `--capability filesystem-writes` (repeatable;
   pass none of them for an explicit none — a declaration is always required).
   **The publisher signs at package time**: `--publisher-key <your-ed25519.pem>`
   applies your signature over the manifest, and `--timestamp-token` (from
   `benchweave-sdk timestamp --tsa-url …`) attaches an RFC 3161 trusted
   timestamp so the signature stays valid after your key expires or is revoked.

2. **Submit** — `benchweave-sdk submit <dir> --registry-clone <working clone>`
   writes the artefact set into the registry repository's submission layout,
   creates the branch, and opens the PR via `gh` when present (otherwise it
   prints the compare URL).

3. **Review** — the maintainer reviews against the versioned
   [checklist](https://github.com/madeinoz67/benchweave-registry/blob/main/review-checklist.md)
   plus the machine evidence (platform findings at the pinned revision), and
   records the outcome in the registry repository's `records/` tree.

4. **Validate and record** — the registry VALIDATES + PUBLISHES + LABELS,
   never signs (`scripts/registry/sign_release.py` here is validate-and-record):
   it re-derives the manifest, verifies YOUR signature against your recorded
   public key, and labels the release `signed-valid` or `unsigned`. A present
   signature that does not verify is REJECTED. With a trusted timestamp,
   validity is judged at the TSA-attested signing time. The review block rides
   inside the recorded manifest (one record attests release and review
   together); your signed submission bytes ride beside it.

5. **Verify** — anyone, from a clean clone of the registry repository alone:
   `uv run python scripts/verify.py` validates every record, verifies every
   signature and digest, and prints the accountability chain (publisher,
   reviewer, outcome, closure digest, capability declaration).

## Required artefacts

A submission is a single generated artefact set. The components — the same
enumeration the packaging tool refuses without, and the lane's records schema
requires on review:

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
| `capability_declaration_absent:` | the closed three-way capability declaration is required; all-false is an explicit none |
| `transport_triples_absent:` | a descriptor declaring a transport provider must publish its admitted contract triples |
| `firmware_provenance_absent:` | firmware in the tree requires a vendor attestation — without it, packaging refuses. WITH an attestation the release publishes with the bytes **vendor-distributed** (never bundled; the payload-role enum carries no firmware role) and the attestation recorded in the submission draft and the publish record, advertised in the index — enforcement is the client's decision |
| `closure_diff_absent:` | the publish-record draft must carry the dependency closure diff versus the prior release |
| `namespace_reserved:` / `namespace_collision:` | namespace hygiene under the committed lane rules (refused). Collisions are per-author: your own next version of an existing package routes to the closure diff, never a collision; another author's claim to an existing package id collides; the same device name under a different author's namespace is allowed |
| `namespace_lookalike:` | a name similar to an existing namespace under the committed similarity rule — **flagged for review**, not refused: the finding rides the submission draft (`namespace_lookalikes`) and prints at package time, so the reviewer consults it (CR-39) |
| `component_absent:<name>` | a required artefact component is missing from the plugin tree |

## Honest boundaries (read before relying on any of this)

- **Measurement truth (CR-51).** Run evidence is integrity-pinned but
  content-unverified against a lying adapter: digest verification establishes
  byte integrity, never that a reading is true. Cross-validation against a
  second qualified instrument is the named detection lane for plausible-reading
  forgery; it is not built. Nothing in the publishing surfaces states or
  implies otherwise.
- **Execution model (CR-52).** An accepted release executes in-process with
  full gateway authority; there is no Python sandbox. Every accepted review
  record carries this disclosure verbatim — the approver was told what the
  approval grants.
- **Local state (CR-55).** Gateway-local admission state (lock, cache,
  high-water, activation records) is never provenance evidence. Local write
  access to a gateway's work root can disarm rollback with a well-formed lower
  high-water, re-point a commissioned closure to older origin-served releases,
  and forge the unbound approval block; the single-writer store hold is the
  standing mitigation, and tamper-evident state work is recorded as a
  structural need, not shipped. The publishing lane never accepts
  gateway-local state as provenance.
- **What review is not.** Structural validity never establishes trust. A
  correctly-signed release carries no technical backstop against malicious
  intent; publish-time review owns that residual, and a clean platform scan
  never marks a release "verified".
- **Publication never authorizes control.** A published, signed, admitted
  release is data until commissioned locally on a specific bench (REG-3).

## Where things live

| Thing | Home |
|---|---|
| Records, releases, lane rules, checklist, public root | `benchweave-registry` (the repository of record) |
| Packaging and submit tooling | the SDK (`benchweave-sdk package` / `submit`) |
| Signing (`sign_release.py`) and this guide | this repository |
| Admission (unchanged) | this repository's registry machinery — what stock admission verifies today is exactly what a published release must satisfy (CR-13) |
