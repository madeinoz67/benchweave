# OTDP profile actions and adapter API 0.1.0

## 1. Controlled extensibility

OTDP 0.1.0 introduces `invoke` as one typed dispatch envelope for versioned class/vendor actions. It is not an arbitrary command endpoint. Every action has a locally admitted input schema, output schema, side-effect/lifecycle contract and tests. The gateway validates the action before invoking the adapter and validates its result afterwards.

The descriptor lists channels, profile IDs, action mappings and contract references. Contract references identify a package-relative file and SHA-256. Paths resolve relative to the host-admitted plugin bundle root, must remain within it after symlink resolution, and cannot identify a URL or executable module. The host resolves schema IDs using only this verified local registry; external `$ref` retrieval is disabled.

The standard catalog is `device-profile-catalog.json`, validated by `device-profile-catalog.schema.json`. Each embedded input/output schema also passes Draft 2020-12 meta-validation. A catalog file hash is not its schema URI: the catalog schema identifies the file's structure, while the descriptor pins the actual catalog contents. The measurement schema is pinned separately.

`required_features` is now an extensible identifier list, but every identifier must be understood by the host before admission. Initial known features are core/0.3.0, adapter/1.1, passive_can/0.3.0, profile_actions/1.0.0, measurement/0.3.0 under the `otdp.` namespace, and the twelve catalog profile IDs. A well-formed unknown identifier is not automatically supported. This replaces v0.2's closed feature enumeration without weakening admission.

Version matching is exact. This revision does not negotiate version ranges or silently choose a similar profile. A future profile revision gets its own ID, schemas, semantic rules and tests. Unknown optional `x-` metadata remains ignorable and cannot change required behaviour.

## 2. Action admission and invocation

The host checks:

1. Profile IDs resolve in the pinned catalog and are listed in required_features; required action membership is complete. An invoke integration also requires otdp.profile_actions/0.1.0 and otdp.measurement/0.1.0.
2. Declared actions belong to an advertised profile and implemented adapter binding.
3. Action input matches the catalog schema, the descriptor's additional input_constraints, actual channels/resources and bench policy.
4. Lifecycle preconditions and current ownership/configuration/acquisition IDs hold.
5. The action's timeout/cancellation/retry/effect declarations are supportable and do not weaken the profile.
6. Successful result matches its catalog schema and semantic postconditions, including dataset rules.

`input_constraints` is an additional JSON Schema, never a replacement for the standard schema. It must itself be meta-validated and use only locally admitted references. It narrows model ranges, modes and capacities. Coupled constraints requiring live state are checked semantically. Empty constraints in structural examples do not establish a real instrument's limits.

The standard action side-effect is a minimum classification. A device may elevate none to state_change, for example a DMM resistance measurement that applies stimulus. It must not downgrade a state-changing action. The umbrella invoke policy is conservative; the gateway evaluates the exact action and current configuration. Profile-aware clients must not mark every invoke read-only because one action is a measurement.

Request:

```json
{"operation_id":"op-1","verb":"invoke","arguments":{"action_id":"otdp.dc_psu.output/1.0.0","input":{"channel":"ch1","enabled":false}}}
```

Successful result:

```json
{"operation_id":"op-1","verb":"invoke","status":"ok","data":{"action_id":"otdp.dc_psu.output/1.0.0","result":{"channel":"ch1","enabled":false,"assurance":"readback"}}}
```

Errors use the existing non-ok operationResult envelope. Result identity, channel, IDs and requested outcome must agree; a schema-valid result for the wrong acquisition is rejected. Unknown outcomes cannot be downgraded to success. A plugin may not replace a forbidden action with a different one that happens to be schema-valid.

Admission verifies catalog integrity and structure, but trust still depends on reviewed provenance. Device-supplied metadata cannot install a catalog, authorise code or add a new transport provider on its own.

## 3. Adapter API changes

API 1.1 retains the factory/open/execute/next_event/close methods from API 1.0. `execute` additionally handles invoke after host validation. The adapter uses `arguments.action_id` to dispatch only its admitted mappings; it does not evaluate arbitrary source code or command templates supplied by the caller.

New scoped host methods are:

```python
class HostServices:
    async def dataset_publish(self, manifest: dict,
                              context: OperationContext) -> dict: ...
    async def dataset_lookup(self, dataset_id: str,
                             context: OperationContext) -> dict: ...
    async def artifact_read(self, artifact_id: str, offset: int, length: int,
                            context: OperationContext) -> bytes: ...
```

`dataset_publish` validates a measurement manifest, referenced payloads, M01–M14, ownership and quotas; assigns/validates the host-scoped dataset ID and returns the immutable admitted manifest. The submitted dataset_id is a host-reserved ID derived from the current operation/acquisition; it is not chosen as an arbitrary global path by the adapter. The host provides `context.dataset_id: str | None` for data-producing invoke calls. The manifest must use that ID; a null value forbids publishing a new dataset. An idempotent repeated fetch may return the already published manifest for the acquisition.

`dataset_lookup` returns a validated manifest the current principal is authorised to use. It does not trust a caller-supplied manifest or URL. Upload actions use it to inspect the dataset's variables, shapes, units and quota requirements before reading any payload.

`artifact_read` reads a positive bounded length at a nonnegative offset from an authorised input artifact; it cannot read beyond its recorded length. It requires artifact_reader permission. It cannot access paths or arbitrary artifact IDs. Only upload-capable or other explicitly approved data-consuming integrations receive that permission.

API 1.0 capture writers remain available for simple core captures. For class datasets, API 1.1 additionally provides:

```python
class HostServices:
    async def payload_create(self, encoding: str, byte_limit: int,
                             context: OperationContext) -> str: ...
    async def payload_append(self, artifact_id: str, data: bytes,
                             context: OperationContext) -> None: ...
    async def payload_finalise(self, artifact_id: str,
                               context: OperationContext) -> dict: ...
    async def payload_abort(self, artifact_id: str) -> None: ...
```

These methods require artifact_writer. Create reserves a bounded output artifact belonging to the current operation/acquisition and a recognised encoding. Append enforces that reservation. Finalise computes and returns the artifact object (ID, encoding, byte length, SHA-256); dataset_publish then validates element/shape meaning. Abort is idempotent local cleanup and remains permitted after deadline; no partial unpublished artifact becomes a successful dataset automatically.

All new methods use the existing context deadlines, cancellation, exception classes and scoped ownership model. Publishing/looking up datasets does not grant device I/O permission. Inline datasets also go through dataset_publish; small data is not exempt from semantic validation.

## 4. Required plugin authoring output

For a class-capable plugin, an AI coding agent must additionally deliver:

- Profile IDs and real channel/terminal mappings.
- Exact action bindings with per-device input constraints and source evidence.
- Pinned catalogs/schemas bundled for local resolution.
- Class-specific dataset conversion, including units, axes, uncertainty and timing provenance.
- Configuration/acquisition state handling and failure evidence.
- Action input/output fixtures, mandatory/optional membership tests and applicable C01–C12/M01–M14 checks.

It must not generate an unsupported feature as a placeholder returning success. If the device lacks a required base action, choose a limited profile or report the gap. Standard profiles do not remove the need for the actual device manual and firmware evidence.

## 5. Class checks C01–C12

| ID | Check |
|---|---|
| C01 | Profile/version/hash resolves locally and every required action is implemented |
| C02 | Action belongs to an advertised profile; optional actions/features are consistently declared |
| C03 | Input meets standard schema, additional device constraints and current bench policy |
| C04 | Channel references, roles, terminal groups and ownership are valid |
| C05 | Configuration/acquisition IDs are current and belong to the right device generation |
| C06 | Source configuration is safe; enabling uses verified configuration; disable remains available |
| C07 | Arm/trigger/fetch/abort lifecycle is valid, bounded and does not replay physical work |
| C08 | Returned effective settings/outcomes agree with the request and required assurance |
| C09 | Returned dataset passes M01–M14 and contains the class's required quantities/axes |
| C10 | Upload input is authorised, validated and within device memory/encoding limits |
| C11 | Side-effect/cancellation/retry claims are conservative and supported |
| C12 | Required class failures have deterministic evidence and do not claim hardware qualification from mocks |

## 6. Transport coverage remains explicit

Class contracts are transport-independent. The existing scoped LAN/USBTMC/serial/CAN/I²C/SPI primitives are retained. A device requiring GPIB, USB-HID, arbitrary USB bulk or a vendor SDK still needs a separately reviewed host-provider contract. API 1.1 does not grant direct unrestricted SDK/filesystem/network access as a shortcut. The relevant class may be fully specified while a particular device's transport integration remains unsupported.
