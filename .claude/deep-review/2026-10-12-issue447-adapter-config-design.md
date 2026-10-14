# Issue #447 — the adapter configuration surface (design record)

**Date:** 2026-10-12
**Branch:** `feat/issue447-adapter-config`
**Issue:** madeinoz67/benchweave#447 (`gateway`)
**Verdict:** BUILD — an additive OTDP 0.2.3 declaration surface (`integration.adapter.configuration`,
digest-pinned package-relative file references) **folded into the #443 train**, plus a
gateway-code leg (admission mirror, loader inventory resolution, projection row) and a
small prerequisite motion in the registry standard (an inventory role for configuration
assets). The issue's premise is confirmed by the code and by the owner-supplied real
device plugin's own bytes.
**Review tier (design-time call, rubric #254):** **Tier 3** — the build diff touches
`standards/` and JSON Schema files (the path rule fires before any keyword rule), plus
`src/benchweave/control/documents.py` and `src/benchweave/registry/` loading behavior
(each a named Tier-3 path in its own right). The standards-governor mandate applies.
Keyword scan in §11.

---

## 0. Summary

OTDP 0.2.2 gives the adapter object five facts — `entry_point`, `api_version`, `version`,
`dependencies`, `permissions` — all required, `additionalProperties: false`, no
configuration field anywhere in the descriptor. A plugin that needs a host-located
resource (the motivating case: a vendor FPGA bitstream file the host must locate and
verify before the device can be configured) has exactly two places to put it today: an
action input (a free-form string the executor type-checks and nothing more) or a process
environment variable (invisible to the host entirely). Neither is declarative; neither is
visible to the host; neither is digest-checked before plugin code runs.

The fix is the corpus's own file-reference pattern, one more time: an optional
`integration.adapter.configuration` object carrying `files: [{id, path, sha256}]` — the
root `contracts` item shape verbatim, the same shape the 0.2.1 provider object embedded
and the #443 `decoders` field reuses. Files are package-relative, resolve inside the
admitted bundle after symlink resolution, are digest-pinned, and are verified at
admission (gateway mirror + SDK validator) and again at activation (loader inventory).
The host shows the declared configuration through the CON-10 projected view. Static by
construction: the descriptor's bytes are digest-pinned, so "changing" configuration is a
new descriptor version — the ordinary reviewed release path.

Three scoping decisions, argued in §2 and §6: **files only, no free-form scalar map**
(secrets and host-locality cannot be expressed by a file reference; a typed map can
express both); **static, not runtime-settable** (a write surface contradicts the
digest-pinned descriptor model and belongs to the settings/plugin-ui lane if anywhere);
**the environment fallback is not absorbed** — the corpus gains one normative sentence
that descriptor-declared adapter configuration comes from the descriptor, and the env
path remains what it is today: outside the contract, invisible, and the thing being
replaced.

**Train recommendation: fold into #443's OTDP 0.2.3 train** (§4) — the same descriptor
schema file, the same one-bump window, and #443 is held at its evidence gate precisely to
absorb plugin findings of this class. The registry role motion (an inventory role for
configuration assets) is a separate small PATCH sequenced before the gateway-code slice's
fixtures.

## 1. Localization — what exists today

### 1.1 The corpus (`standards/otdp/0.2.2/`)

- `otdp-device-descriptor.schema.json` `$defs.adapter`: `entry_point` (pattern),
  `api_version` (const "1.1"), `version` (semver), `dependencies` (array, exact
  versions), `permissions` (enum of 4) — **required all five**,
  `patternProperties` for `x-` extensions, `additionalProperties: false`. No
  configuration field.
- `$defs.integration`: `mode` (`declarative` | `adapter`), optional `adapter` object;
  the mode conditional **forbids** `adapter` under `declarative` — an adapter-config
  field inside `$defs.adapter` is automatically scoped to plugin-backed devices, no new
  conditional needed.
- Root `contracts`: the `{id, path, sha256}` triple array, `minItems 1` — the
  established shape for descriptor-referenced package files.
- `extension-contract.md` §1 line 7: "Contract references identify a package-relative
  file and SHA-256. Paths resolve relative to the host-admitted plugin bundle root,
  must remain within it after symlink resolution, and cannot identify a URL or
  executable module." §1 line 15: unknown `x-` metadata "remains ignorable and cannot
  change required behaviour" — **the `x-` escape hatch is not a configuration surface**;
  a config fact the host must honor cannot live there.
- `otdp-specification.md` §8 (adapter ABI 1.1): `open(self, descriptor, services,
  context)` — the host hands the adapter the full descriptor dict, so a new descriptor
  field is plugin-visible with zero ABI change. §9: "Secrets are excluded from
  descriptors and logs." §9: "Executable plugin replacement is a reviewed release
  change. No hot reload mutates active parser or mapping state."
- `otdp-specification.md` §10: the S-table runs S01–S19 in 0.2.2. #445's folded design
  takes S20; this motion takes **S21**.
- No corpus text anywhere mentions environment variables as a configuration source
  (checked: zero matches for `environ`/`environment variable` across the 0.2.2 mds).

### 1.2 The gateway (`src/benchweave/`)

- `registry/otdp_loading.py::load_otdp_plugin` (:174) — the activation loader. It
  re-hashes **every** manifest inventory file into a verified `inventory` dict
  (:216–231, `file_hash_mismatch` on any drift, strict no-follow on bundle paths), then
  resolves the descriptor's pinned `contracts` against that inventory (:241,
  `resolve_otdp_contracts` — the issue-#146 seam) before any plugin import. This is the
  exact mechanism an adapter-configuration resolution extends.
- `registry/activation.py::load_plugin` (:61) — the non-OTDP legacy loader; same
  inventory-verification posture. Not touched by this design (the OTDP loader is the
  live path for adapter-mode plugins).
- `control/documents.py::_verify_provider_pin` (:1112) — the descriptor-relative pin
  verification precedent: relative-POSIX path posture (no backslash, no colon, no
  absolute, no `.`/`..`/empty segments), strict symlink no-follow, containment inside
  the descriptor's package root, a bounded read cap, sha256 compare,
  exact-byte decode, then schema + declaration-agreement. Refusals carry typed
  machine-matchable prefixes.
- `control/documents.py::_project_full_form` (:1608) — the CON-10 projection. The view
  carries selected facts (`artifact_writer` is projected from
  `$defs.adapter.properties.permissions` via `adapter_permissions`, :2154) and
  **drops `integration` wholesale** — post-admission consumers see adapter facts only
  through what this function copies in. "Visible to the host" mechanically means: a row
  in this view.
- `control/provider_settings.py` — the operator-owned `transport-settings.json`
  surface: identity-only **by schema, not by policy** ("No field can express an
  endpoint, path target, process, credential or secret"), with endpoint/path
  configuration explicitly deferred to a future operator admission surface. This is the
  corpus's standing decision that host-local values do not live in descriptors — the
  design honors it (§2.2).

### 1.3 The real device plugin (read directly, outside this repo — disclosed)

The owner-supplied plugin's adapter (a real device plugin; a vendor FPGA-tools logic
analyser behind a custom USB transport) implements a `configure_fpga` action whose
first move is (identifiers genericized; the source names the vendor format and its
env constant, elided per the public-repo rule):

```python
path = inputs.get("<vendor-container>_path") or os.environ.get("<VENDOR_ENV_CONSTANT>")
```

— action input first, environment variable fallback; then `open(path, "rb")`, then a
`hashlib.sha256` compare against a hardware-proven digest constant baked into the
plugin refuses. Three facts matter for this design:

1. **The plugin already digest-pins the file** against a hardware-proven constant baked
   into its own code. The trust model the issue asks for (digest verification) already
   exists plugin-side; what is missing is the *declaration* — the host cannot see or
   pre-verify any of it.
2. **The file is host-local today**: the vendor bitstream container exists only in the
   operator's vendor-software extraction directory, outside the plugin package
   (unlicensed vendor bytes are excluded from the plugin's own distribution by rule).
3. The action input is declared in the plugin's descriptor as
   a bare `{type: string}` field under `input_constraints` — a free-form string the
   executor's schema check passes and nothing else validates.

## 2. The shape decision — precedent analysis

Three candidate shapes, judged against the corpus's own model for
"plugin-declared configuration the host must honor":

### 2.1 Candidate A — digest-pinned package-relative file references (CHOSEN)

`integration.adapter.configuration.files` carries `{id, path, sha256}` triples — the
root `contracts` item shape verbatim, the 0.2.1 provider object's embedded shape, and
#443's `decoders` shape. The file ships **inside the admitted plugin package**.

- **Precedent (primary):** the `transport.provider` object (0.2.1, commits `340fda2d`/
  `7946dd9a`) — whose schema description states the resolution contract outright:
  "id/path/sha256 is the contracts item shape verbatim: package-relative, digest-pinned,
  resolved inside the admitted bundle after symlink resolution. The pin names the bytes
  that were reviewed; the host operator's admission of the contract grants authority."
  Also `contracts` itself (root, live in the real plugin: two triples), also the
  loader's inventory verification (`registry` contract §4 path hygiene +
  `file_hash_mismatch`), also `_verify_provider_pin`'s posture rules.
- **Trust story:** zero new trust surface. The file lives inside the bundle admission
  already hash-verifies; the descriptor triple adds the plugin's semantic claim (what
  the file IS) on top of admission's mechanical fact (what bytes it has). Descriptor
  trust inherits to the reference exactly as the issue's constraint anticipates.
- **Portability:** the file travels with the package — "same results on any host" holds
  by construction. No host paths anywhere.
- **The licensing objection, answered:** the plugin *author's* distribution excludes
  vendor bytes; the *operator's* admitted package is a local, reviewed act, and nothing
  in the corpus prevents an operator packaging a locally-licensed vendor file. The
  author's published package simply omits the triple (and stays on the action-input
  path) until the operator's local build supplies the file — the same
  honestly-incomplete posture as `custom` transport without a provider. The
  cannot-ever-package case is the named deferral D2 (§6), not slice 1.

### 2.2 Candidate B — commissioned host-local binding (connection_key analog)

The descriptor declares the requirement (id + sha256, no path); an operator-owned
settings document binds id → local path; the host resolves and verifies at load — the
`connection_key` → `transport-settings.json` pattern.

- **Rejected for slice 1, kept as D2.** It matches A02's philosophy for host-specific
  *values*, but it requires a new operator settings surface + resolution machinery —
  and the transport lane already ruled (provider_settings.py module docstring) that
  exactly this shape for endpoints/paths "arrives with the first runtime implementation
  through the deferred operator admission surface, never here". Building a parallel
  surface for adapter files ahead of that lane is new architecture (core principle 9)
  without the precedent fit Candidate A already has. If the transport lane's deferred
  operator surface materializes, adapter file bindings should ride it, not duplicate it.

### 2.3 Candidate C — an options-like typed scalar map

A `parameters`-style declared surface the host materializes and validates (keys, types,
ranges). Rejected: it configures nothing the motivating case needs, and a scalar map is
a secrets channel (`§9` excludes secrets from descriptors) and a host-locality channel
(a portable document carrying host-specific values breaks the same-results clause).
File references carry neither: a digest is not a secret, and a package-relative path has
no host locality. If a genuine non-file, non-host-local scalar need appears, it is D3.

### 2.4 The placement decision

Inside `integration.adapter` (not root): the adapter object is where the host already
reads plugin-execution facts (`adapter_permissions` reads
`$defs.adapter.properties.permissions` from the raw form); the integration mode
conditional scopes the field to adapter-mode descriptors for free; a root field would
need its own conditional and would separate the configuration from its only consumer.
`contracts`/`decoders` are root because catalog actions and the measurement lane consume
them; nothing but the adapter and the host's activation path consume configuration.

## 3. The mechanism

### 3.1 The descriptor surface (OTDP 0.2.3, corpus leg)

`$defs.adapter` gains one optional property:

```json
"configuration": {
  "type": "object",
  "properties": {
    "files": {
      "type": "array",
      "minItems": 1,
      "uniqueItems": true,
      "items": {
        "type": "object",
        "properties": {
          "id":   {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
          "path": {"type": "string", "minLength": 1},
          "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"}
        },
        "required": ["id", "path", "sha256"],
        "additionalProperties": false
      }
    }
  },
  "required": ["files"],
  "additionalProperties": false
}
```

- `id` uses the `connection_key` pattern (corpus snake_case convention). `path` carries
  shape only in-schema; the **posture** (relative POSIX, no `..`/`.`/empty segments, no
  backslash, no colon, strict symlink no-follow, containment) is semantic — S21 plus the
  mirrors, exactly how the provider lane splits schema shape from resolution posture.
- `minItems 1` + `required ["files"]`: a configuration that configures nothing is dead
  weight; an empty `configuration` refuses. This tightens only the new field — nothing
  that validated before can carry it (the dead-shape proof, §4).
- Spec prose: `otdp-specification.md` §8 gains a short "adapter configuration"
  paragraph: the declaration semantics (package-relative, digest-pinned, verified at
  admission and activation, visible in the host's projected view), the resolution
  contract for the adapter (resolve `path` against its own package root — the directory
  the host verified inside the cache; no host service hands over a path, no ABI
  change), and the normative sentence: **adapter configuration for descriptor-declared
  settings comes from the descriptor; the adapter does not source them from action
  inputs or process environment variables.** Mechanically this sentence is
  authoring/review surface, like the rest of the ABI prose — the host cannot statically
  prove a reviewed plugin never reads its environment; the declared surface is what the
  host can see, and that is the issue's ask.
- §10 gains **S21**: "Adapter configuration files are unique by id and path,
  package-relative, resolve inside the admitted bundle after symlink resolution, are
  digest-pinned against their sha256, and are present in the admitted manifest
  inventory."
- `extension-contract.md` §1's file-reference paragraph extends by one sentence to name
  adapter configuration files as a third carrier of the triple discipline (contracts,
  provider, configuration).
- Examples: one 0.2.3 example descriptor gains a `configuration.files` entry pointing at
  an invented binary fixture (invented name, real sha256 of the fixture bytes — e.g.
  `assets/fixture-fpga-image.bin`), plus census mutation rows (§3.4).

### 3.2 The gateway admission mirror (code leg, `control/documents.py`)

`_verify_adapter_configuration(logical, descriptor, descriptor_path)` — a structural
sibling of `_verify_provider_pin` with two deliberate differences:

- **No exact-byte decode**: a configuration file is opaque bytes (a bitstream is not a
  JSON document). The verify stops at posture + containment + read-cap + sha256. This is
  the inventory posture, not the document posture — stated in the function docstring so
  the CON-1 family boundary is explicit.
- **Inventory agreement** where the provider lane had declaration-agreement: at the
  fixtures-lattice admission the triple's sha256 must equal the pinned manifest
  inventory digest for the same path when the lattice carries the package (the
  double-pin drift check, Risk 2).

Refusals, typed and machine-matchable, riding the existing family style:
`adapter_config_invalid:` (shape/posture), `adapter_config_missing:` (absent,
unresolvable, symlink-crossing, oversized), `adapter_config_hash_mismatch:` (digest),
`adapter_config_inventory_conflict:` (double-pin drift). Called from
`admit_documents` beside `_verify_provider_pin` (:2095 region) — total on a present
`configuration`, no-op on absence (the `adapter_permissions` posture: a malformed shape
grants nothing and refuses loudly).

### 3.3 The loader resolution (code leg, `registry/otdp_loading.py`)

`load_otdp_plugin` gains, beside the `resolve_otdp_contracts` call (:241): for each
configuration triple, the `path` must name an entry in the **verified inventory** and
the triple's `sha256` must equal that entry's pinned digest — refuse
`adapter_config_not_in_bundle:` / `adapter_config_hash_mismatch:` **before any plugin
import** (the #146 posture: integrity failures never reach the import machinery). The
adapter then reads `descriptor["integration"]["adapter"]["configuration"]` from its
`open()` argument and resolves `path` against its own package root. No `HostServices`
addition — the plugin reading its own verified bundle is the standing trust model
(review at admission, not sandboxing at runtime), and an ABI file-read service would be
new surface for zero security gain.

### 3.4 The projection row (code leg, `control/documents.py`)

`_project_full_form` gains, in the `artifact_writer` style:

```python
view["adapter_configuration"] = {
    "files": [
        {"id": ..., "path": ..., "sha256": ...},   # the declared triples, verbatim
    ]
}
```

— present only when the descriptor declares it; a malformed shape projects nothing (no
fact is granted by a malformed shape). The **wire** device object stays contract-closed:
the REST/MCP field lands with the next interface bump, exactly the disclosure style the
#217 pin-class lane used (derive server-side now, move the wire later). "The host cannot
show this setting" is closed at the projection — every gateway-side consumer (UI,
operator tooling) reads the view.

### 3.5 The registry prerequisite (registry 0.1.3, small standards motion)

The release-manifest inventory's `role` enum (registry 0.1.2
`release-manifest.schema.json`, `payload.files.items.role`) is
`profile | descriptor | implementation | schema | test | documentation | licence | sbom |
build_provenance | dependency_lock | skill` — **no role describes an opaque configuration
asset**, and `role` is required on every inventory file. A package honestly carrying a
bitstream cannot declare it. The motion: registry 0.1.3 adds `"configuration"` to the
enum plus one prose sentence in the registry contract. Purely additive PATCH (no
previously-valid manifest refused). Sequenced **before** the gateway-code slice, whose
fixture lattice needs it; the OTDP corpus leg does not.

### 3.6 The SDK leg (benchweave-sdk repo, follows the #408 order)

`benchweave_sdk.validate_descriptor` inherits the 0.2.3 schema per-pin for free. The
semantic mirror (`verify_adapter_configuration`, the `verify_provider_pin` shape:
posture + digest + no-follow against the package on disk) is the plugin-authoring lane's
catch, so `benchweave-sdk check` refuses a broken triple before the gateway ever sees
it. Rides the train's single SDK release cut.

### 3.7 What does NOT move

- `otdp-runtime.schema.json`, the operation catalog, `openapi.json`, `mcp-tools.json` —
  no transport motion (A13: the projection is internal; the wire defers).
- The adapter ABI signatures — `open(descriptor, services, context)` already carries the
  declaration.
- `registry/activation.py` (the legacy loader) — the OTDP loader is the live path.
- `transport-settings.json` and `provider_settings.py` — untouched; Candidate B's
  machinery is explicitly not built.
- Every 0.2.2 byte (copy-never-move; the old dir stays digest-frozen).

## 4. Version semantics, class, and the train call

**Class: PATCH (OTDP 0.2.2 → 0.2.3; registry 0.1.2 → 0.1.3).** Refused-none template
(the `a103a4cf` shape, argued the same way #443 and #445 argued it):

- The field is optional; `additionalProperties: false` on `$defs.adapter` *gains* a
  property. No 0.2.2-valid descriptor is refused by 0.2.3 — the dead-shape proof's
  forward direction.
- The tightening inside the new field (`required files`, `minItems 1`, unique items)
  refuses only documents that use a field no 0.2.2 document can carry — the backward
  direction.
- The registry enum extension adds a value; no previously-valid manifest is refused.
- **Falsifier, stated in advance:** any input admissible under 0.2.2 (or registry 0.1.2)
  that the new version refuses flips the class to MINOR.

**Train recommendation: FOLD into #443's held 0.2.3 train**, sequenced after its corpus
slice. The collision analysis:

| File | #443 (train, held) | #445 (folded) | #447 (this motion) |
|---|---|---|---|
| `standards/otdp/0.2.3/otdp-device-descriptor.schema.json` | root `decoders` | `read_policy.side_effect` + S20 conditional | `$defs.adapter.properties.configuration` |
| `otdp-specification.md` | §7 named extension | §4/§5/§10 | §8 configuration paragraph, §10 S21 |
| `extension-contract.md` | cross-reference | — | §1 triple-discipline sentence |
| `control/documents.py` | deferred (its D6) | read-side-effect mirrors | `_verify_adapter_configuration` + projection row |
| `registry/otdp_loading.py` | — | — | inventory resolution |
| `standards/registry/0.1.3/…` | — | — | role enum (prerequisite) |
| SDK repo | sync (its D7) | — | `verify_adapter_configuration` mirror |

Different regions of the shared schema file; disjoint prose sections; one shared
manifest/docs sweep. Two bumps of OTDP for three motions sharing one schema file would
pay the window, the sweep, and the SDK release twice for nothing — the one-bump rule
exists for exactly this. And #443 is **held at its evidence gate to absorb plugin
findings** (owner directive: wait for the remainder of the real-plugin implementation
findings, and fold them in); #447 is one of those findings. Sequencing: #443's build
branch is ahead; this motion's corpus bytes stack on the train tip after it; the
gateway-code legs land after the corpus; one SDK release cut at train close.

Independence was considered and rejected: a separate 0.2.4 doubles the sweep cost and
re-collides with the train's held state. Sequencing *after* the whole train (0.2.4) has
no advantage over folding — the files collide either way, and the fold pays once.

## 5. Minimal first increment — scope

Three PR-sized slices (the fold means slice 1 lands on the #443 train tip):

1. **Slice 1 — corpus (OTDP 0.2.3 rider):** copy-never-move + version sweep + §3.1
   (schema field, §8 paragraph + normative sentence, S21, extension-contract sentence),
   example descriptor + invented binary fixture + census mutation rows in
   `scripts/architecture/check_devices.py`, validation-report regeneration,
   manifests in-arc, docs sweeps (obligations 6/13/18; the device-developer-guide gains
   the configuration section — obligation 3). Zero gateway source.
2. **Slice 2 — registry 0.1.3:** the role enum + registry-contract sentence + its own
   manifest/docs sweep. Small, independent PATCH.
3. **Slice 3 — gateway + SDK legs:** `_verify_adapter_configuration`
   (+`admit_documents` wiring), the loader inventory resolution, the projection row,
   fixture-lattice packages carrying a configuration file with the new role
   (obligation 5's four-way lockstep), RED-first tests per §9; the SDK mirror PR →
   release cut → pointer PR (the #408 order).

## 6. Deferrals (each with home + reopen trigger)

| # | Deferral | Home | Reopen trigger (observable) |
|---|---|---|---|
| D1 | **Wire/UI surface** (REST/MCP device field, console rendering) | the interface contract (next bump) + plugin-ui lane | an operator or client names the projected config in a UI request — a tracker issue asking to see it on a wire |
| D2 | **Commissioned host-local file binding** (Candidate B — id+digest in descriptor, operator settings resolve the path) | the transport lane's deferred operator admission surface (`provider_settings.py` docstring names it) | a plugin whose resource cannot legally or practically ship in any admitted package — a filed case where repackaging is ruled out |
| D3 | **Non-file scalar configuration** (typed options-like values) | this record §2.3 | a real plugin need that is neither a file nor host-local — a tracker issue naming the value and why a file does not carry it |
| D4 | **Runtime-settable configuration / write surface** | the settings/preset lane (#444 family) | an operator requests live editing of adapter config — which by construction means a new descriptor version; the request itself is the trigger to design that flow |
| D5 | **HostServices config-read API** (host-mediated file access instead of plugin-reads-own-bundle) | this record §3.3 | a sandboxing/isolation requirement for adapter file access — a security review finding that plugin filesystem reads must be scoped |
| D6 | **A drift-and-obligations row for the adapter-configuration lane** (mirroring row 15's shape) | `docs/internal/drift-and-obligations.md` | slice 3 merges — the row lands with the code it tracks |

## 7. Precedent citations

- **The file-reference triple (primary):** root `contracts` (extension-contract.md §1
  line 7 — package-relative, SHA-256, contained, no URL/executable); the 0.2.1 provider
  object embedding the triple verbatim (`340fda2d` mechanism, `7946dd9a` prose); #443's
  `decoders` field reusing it in this same train. This design is that shape one more
  time, attached to the adapter object.
- **The verification machinery:** `_verify_provider_pin` (posture, no-follow,
  containment, cap, digest, typed prefixes) and `load_otdp_plugin`'s inventory
  verification + the #146 contracts-resolution seam (`resolve_otdp_contracts`).
- **The projection precedent:** `artifact_writer` — an adapter fact projected into the
  CON-10 view with the no-fact-from-malformed-shape posture (`adapter_permissions`
  docstring).
- **The secrets posture:** `provider_settings.py`'s identity-only-by-schema rule —
  mirrored here by files-only-no-scalars (a shape that cannot express the thing it must
  not carry).
- **The honestly-incomplete posture:** `custom` transport without `provider` — the
  author's package omitting the triple stays admissible on the legacy action-input
  path.
- **The consumer:** the real device plugin (§1.3) — its configure action's
  input-then-env path resolution and its plugin-side digest constant are the exact
  behavior being declarativized.

## 8. Invariant impacts (A01–A14 walk)

- **A02 (qualified, not assumed):** untouched — no numeric envelope, timeout or
  threshold moves; the digest is plugin-declared reviewed data, not a commissioned
  value. The host-local-values boundary (the transport-settings ruling) is honored:
  descriptors gain no host locality.
- **A04 (protection independent of AI):** untouched — no protective transition, lease,
  or deadline change; nothing in the mechanism requires judgement to stay safe (a
  missing or wrong file refuses before plugin code runs).
- **A06 (evidence over assertion):** the pin is evidence — admission and activation
  verify bytes against digests; a mismatch refuses with a typed prefix; nothing
  asserts the file is right without hashing it.
- **A07 (audit failure constrains):** refusals carry machine-matchable prefixes riding
  the existing admission-refusal vocabulary; no evidence-storage dependency is added.
- **A12 (bounded procedures):** untouched — configuration is admission-time state, not
  procedure steps.
- **A13 (one core contract):** no transport motion; the projection is internal and the
  wire defers (§3.4) — the same attachment discipline #443 used.
- **A14:** nothing.
- **CON-1 family:** amendment-shaped clarification, not a change: configuration files
  are hash-verified opaque bytes (the inventory posture), not exact-byte-decoded
  documents — the seam is named in the mirror's docstring. Exact-byte decode and digest
  pins for every *document* unchanged.
- **CON-10 (projection):** gains `adapter_configuration` in slice 3 — the
  `artifact_writer` amendment style.
- **REG family:** the OTDP loader gains a refusal class (`adapter_config_*`) with the
  exec-time-integrity posture (verify before import); the registry standard gains an
  inventory role. No new invariant needed: the file-resolution rule is a corpus
  conformance check (S21) carried by the census, the SDK checker, and the mirrors — the
  derived_variables precedent (S19/M15 as corpus checks) is the model.

## 9. Measurable proof — pre-committed acceptance rule

**Metrics (fixed before any number is looked at):**

- **M-A Declarative validity:** a 0.2.3-pinned descriptor carrying
  `integration.adapter.configuration.files = [{id, path, sha256}]` with the file
  present at the pinned digest in its package (i) validates under
  `benchweave_sdk.validate_descriptor`, (ii) admits through gateway
  `_project_full_form` with zero refusals, and (iii) yields a projected view whose
  `adapter_configuration.files` equals the declared triple. Sample: one fixture package
  plus the real plugin's rebuilt package. **RED side:** the same descriptor bytes
  against the pre-change tree refuse with the schema error naming
  `integration.adapter` (`additionalProperties`) — collected refusal, not absence of a
  test.
- **M-B Digest negative control (the kill control):** the same package with the
  referenced file's bytes altered refuses at the loader with
  `adapter_config_hash_mismatch:` **before any plugin import**, and at the SDK
  validator with its mirror prefix. **RED side:** pre-change, the altered package
  loads cleanly — the field does not exist, nothing checks it — demonstrating the
  mechanism is load-bearing, not decorative.
- **M-C Posture negatives:** `../escape.bin`, an absolute path, a colon-bearing path,
  and a symlinked target each refuse `adapter_config_invalid:`/`adapter_config_missing:`;
  a duplicate id and a duplicate path refuse (S21); an inventory/descriptor double-pin
  drift (descriptor pins X, manifest pins Y) refuses
  `adapter_config_inventory_conflict:` rather than resolving silently.
- **M-D No-regression:** the full census + devices suite green; every 0.2.2 example
  byte unchanged; a 0.2.2-pinned descriptor and a 0.2.3 descriptor both validate
  per-pin; every existing fixture package admits unchanged (the dead-shape proof's
  executable form).
- **M-E The real plugin (owner-domain evidence):** the real device plugin's package,
  rebuilt locally with the vendor bitstream at `assets/` and the descriptor carrying
  the triple (its own hardware-proven digest constant), passes `benchweave-sdk check`
  and gateway admission, and the projected device view names the file — where today
  the same setting is an action input plus an environment fallback the host cannot
  see. Runs in the plugin's repo, not this one; the in-repo fixture stands in for CI.

**SHIP if** M-A, M-B, M-D all hold on the fixture package, and M-C refuses every
planted shape.

**KILL if** M-A's descriptor refuses on the post-change tree (mechanism broken);
M-B does not refuse (the pin is decorative — an unenforced digest is worse than none,
do not ship); M-D refuses any previously-admissible package (class flips to MINOR and
the motion re-scopes); or M-C accepts any planted shape.

**UNDERPOWERED if** M-E cannot run (hardware or packaging absent): M-A–M-D still decide
ship/no-ship for the corpus and gateway legs — M-E is recorded as open evidence, not a
silent pass. If only ONE negative control shape were planted (e.g. digest-only), the
validation claim would be underpowered by construction; the rule requires all of M-C's
shapes or an explicit record of which were skipped and why.

## 10. Top risks, each with its falsifier

1. **Two standards, one train** — the registry role motion widens the blast radius.
   Falsified if registry 0.1.3's sweep misses a surface (its own tripwires red);
   mitigated by it being a one-value enum extension with the 0.1.2 sweep as template,
   sequenced before the fixtures that need it.
2. **Double-pin drift** — descriptor triple and manifest inventory pin the same file
   independently; a careless packaging tool lets them disagree. Mitigated by M-C's
   `adapter_config_inventory_conflict:` arm (drift refuses loudly); falsified if any
   path resolves with disagreeing pins.
3. **Bundling pressure on licensing** — an operator reads the design as license to
   redistribute vendor bytes. Mitigated by the record's posture (packaging is the
   operator's local reviewed act; the author's package may omit the triple and stay on
   the legacy path); D2 is the honest home for the cannot-package case. Falsified if
   review finds the corpus *requiring* packaging — it does not.
4. **Secrets laundering via file content** — a referenced file could BE a credential
   store; the host cannot semantically know a binary is not. Disclosed residual: the
   control is admission review (the whole trusted-plugin model), plus the bounded read
   cap; the shape at least carries no secret *in the descriptor*. Falsified only by a
   review-policy gap, not by this mechanism.
5. **The env fallback survives** — plugins keep reading environment variables and the
   corpus sentence is unenforceable prose. Honest residual: the ABI is authoring/review
   surface, like all of §8; the declared surface is fully checked, the undeclared one
   is the plugin author's reviewed behavior. Falsified if a conformance test claims to
   catch env reads — none does, and none is claimed.
6. **Fold-collision merge cost** — three riders on one schema file invites rebase
   churn on the held train. Mitigated by disjoint regions (§4 table) and
   stack-don't-rebase discipline; falsified if the train's builder reports textual
   conflicts in another rider's region.

## 11. Review tier and the Step-1 keyword scan

**Tier 3**, path rules: the build diff touches `standards/` (both bumps), adds JSON
Schema content, touches `src/benchweave/control/documents.py` and
`src/benchweave/registry/` loading behavior. The standards-governor pass is mandatory;
two-lane adversarial refute applies (Tier-3 doctrine). Slice 1 alone is Tier 3 by the
standards path rule; the maximum tier across slices is 3 and every slice's expected
diff is covered by the counts below.

**Keyword scan (the eight Step-1 words) over the expected diffs:**

- *This record's commit (the record file itself; word-boundary counts over the final
  committed text — stating counts changes them, so these are fixed-point numbers):*
  `threading` 2, `asyncio` 2, `subprocess` 2, `sha256` 19, `hashlib` 4,
  `migrate` 2, `recovery` 2, `protection` 3. Every one of these hits is one of: this
  section's own two namings of the word list, the A04 heading in §8, or the mechanism
  text's digest vocabulary; the tier is 3 by the path rule regardless; the keyword
  hits ride along as disclosed.
- *The expected build diffs:* slice 1 (corpus): `sha256` ≈ 10–20 (schema pattern,
  S21, example triple, census arms, manifest rows), `hashlib` ≈ 1–2 (fixture digest
  computation), others ≈ 0. Slice 3 (code): `sha256` ≈ 15–30 (mirror + loader refusal
  messages and test assertions), `hashlib` ≈ 3–5 (documents.py, otdp_loading.py,
  tests), others ≈ 0 — no threading/asyncio/subprocess/migrate/recovery/protection
  content is introduced. The build lane re-runs the scan over each real diff and
  reports actual counts; the tier cannot drop below 3 either way.

## 12. Train shape

- **Slice 1** stacks on the #443 train tip (its build branch is ahead): record-first
  commit there or on this branch cherry-picked per the train owner's call; RED census
  commit; the corpus rider commit (copy + sweep + mechanism + examples + manifests +
  report + docs); fold waves batched per the one-bump rule.
- **Slice 2** (registry 0.1.3): standalone PR, linked to #447, lands any time before
  slice 3's fixtures.
- **Slice 3**: gateway PR (mirror + loader + projection + fixtures + RED-first tests)
  after the 0.2.3 corpus merges; SDK PR (`verify_adapter_configuration`) → SDK release
  cut → gateway pointer PR, the #408 order, riding the train's single cut.
- Reviews before open on every slice: resident code-reviewer (Tier-3 protocol) +
  standards-governor (mandatory on both bumps) + two independent adversarial lanes.
  Merge on the full rollup.

## 13. Forks needing the owner's word

- **F1 — the packaging posture:** this design serves the real plugin by having the
  operator's local package build include the vendor bitstream (recommended — zero new
  trust surface, the proven pattern) vs building Candidate B's commissioned host-local
  binding now (serves the unpackageable case directly, but duplicates the transport
  lane's deferred operator surface ahead of its own lane). If the owner rules the
  bitstream may never enter ANY admitted package, slice 1 shrinks to the declaration
  schema and D2 becomes the main motion.
- **F2 — the registry role name:** `configuration` (recommended — names the function)
  vs `asset` (broader, vaguer) vs reusing an existing role (rejected as dishonest
  inventory metadata).
- **F3 — bump class signalling:** PATCH per the refused-none template (recommended;
  same call as #443/#445) vs MINOR 0.3.0 for signalling — an owner preference to
  record in the PR body, per the #443 F3 precedent.
- **F4 — the normative env sentence:** include the "adapter does not source
  descriptor-declared settings from action inputs or process environment" sentence in
  §8 (recommended — it is the issue's actual complaint, made normative) vs leaving
  plugin behavior unnamed (the corpus's current silence).

---

## 14. Fold-in addendum (2026-10-13, the 0.2.3 train build lane)

The record's §4 fold recommendation is EXECUTED: this surface rides the held OTDP
0.2.3 train per the one-bump rule, sequenced after #443's corpus slice and #445's
read-side-effect rider, stacked on the train tip `99601ada`. The registry rider
(§3.5) is enumerated per the owner's fork calls: **F2 = `configuration`** (the
role name), **F3 = PATCH for both motions** (OTDP 0.2.2 → 0.2.3 already on the
train; registry 0.1.2 → 0.1.3 in this slice), **F1 = the operator's local package
carries the vendor file** (Candidate B stays deferred as D2), **F4 = the
normative env sentence is included**.

Scope notes recorded at fold time:

- The owner's separate decoder-system record and the grid-fidelity resolution
  touch the pdhost/plugin layers, not this descriptor contract — no byte of this
  surface moves for them.
- §12's train shape named "Slice 2 standalone PR" for the registry rider; the
  build lane lands it as the train's fourth commit (same branch, one arc) — the
  sequencing constraint §5 states (registry lands before fixtures consume the
  role) still holds, and the fold's one-bump discipline subsumes the standalone-PR
  framing.
- §3.2/§3.3 name the loader's digest disagreement `adapter_config_hash_mismatch:`
  while M-C names the same condition `adapter_config_inventory_conflict:`. The
  build resolves the overlap by fire point: the admission mirror (§3.2's family)
  refuses bytes-vs-triple drift as `adapter_config_hash_mismatch:`; the loader
  (§3.3's seam) resolves triples against the manifest-verified inventory, where
  the same disagreement is by construction the descriptor-vs-manifest double-pin
  drift and refuses `adapter_config_inventory_conflict:`. Both fire before any
  plugin import or as an admission refusal; no mismatch shape resolves silently.
  This addendum is the pre-committed record of that reading.
