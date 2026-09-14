# Plugin presentation contracts 0.1.0

Plugins can declare optional configuration, readings, dataset and specialised panel pages through a shared host UI. A plugin with no presentation remains usable through its descriptor. This contract and the SDK tools validate presentation candidates; they do not activate attachments in the registry. The SDK additionally bundles a labelled, simulation-only preview renderer (`benchweave-sdk preview-ui`) for local authoring — it displays simulated states, serves loopback only, and never operates hardware or publishes anything.

## Ownership and execution

The gateway owns device connections, acquisition, retained observations, leases, approvals and run state. Pages display gateway state and submit explicit requests through approved procedures. A plot never starts its own device polling loop. Selecting a preset performs no I/O; applying it is a separate operation requiring the normal procedure and approval checks.

A browser disconnect must not terminate a gateway-owned procedure. Interactive manual control remains subject to the gateway's lease expiry and protective transition rules. A UI manifest cannot grant permissions, bypass a lease or declare an operation that the descriptor does not implement.

The current adapter bridge supports identify and scalar read/write. Class-action and waveform fixtures below describe contracts, not newly implemented acquisition support. Dataset views require a host implementation of the corresponding descriptor action and dataset delivery.

## Resource layout

Keep each distributable plugin in `plugins/<vendor>/<device>/`, with the developer SDK in `packages/sdk/`. An external plugin uses the same package layout without depending on the gateway distribution:

```text
plugin-project/
  pyproject.toml
  README.md
  tests/
  src/plugin_package/
    __init__.py
    adapter.py
    protocol.py
    descriptor.json
    vectors.json
    presentation.json
    binding-catalogue.json
    ui/
      manifest.json
      settings/                 # only for implemented configuration actions
        configuration.schema.json
      presets/                  # complete, versioned configuration documents
        documented-configuration.json
      assets/                   # optional presentation resources
```

The default SDK starter remains read-only and has no presentation files. `--with-ui` adds a readings page and catalogue while preserving its descriptor, adapter and protocol bytes. Configuration schemas and presets are added only when the plugin implements those actions. Package all declared resources, include them in the normal payload inventory and update hashes whenever their bytes change.

## Four documents

| Document | Purpose |
| --- | --- |
| `presentation-envelope.schema.json` | Candidate attachment: contract version, descriptor hash, package-relative resource root and manifest path/hash. |
| `ui-manifest.schema.json` | Optional pages, typed bindings, assets, plots and required host features. |
| `binding-catalogue.schema.json` | Host-provided descriptor binding metadata, including action/schema relationships and observation/dataset variables. |
| `configuration-preset.schema.json` | Complete settings, plugin/profile/firmware compatibility, settings schema identity/hash and provenance. |

Each schema has an exact 0.1.0 identifier. Fields are closed except explicitly namespaced manifest extensions. The three smaller schemas refer to shared definitions in the manifest schema; validators resolve them from the local corpus. Canonical runtime copies under `contracts/plugin-ui-v0.1.0/` are byte-identical to these files and pinned by `contracts/manifest.json`. OTDP 0.3.0, adapter API 1.1 and registry 1.0.0 remain unchanged.

IDs within pages, bindings, targets, variables and assets must be unique. A binding identifies a catalogue target and retains its kind. Observation targets identify readable descriptor parameters and compatible units/types. Action targets identify a declared action and the profiles which supply it. Dataset schema identities must appear in the descriptor's admitted contract references.

The catalogue is trusted host metadata, not an authority granted to plugin-supplied UI files. In particular, generic measurement schemas do not determine a particular dataset's variable shapes or units. The host supplies that metadata after admission. The SDK can check an authoring catalogue's structural consistency; it cannot certify its provenance or establish hardware conformance.

## Configuration presets

Presets have explicit identities, revisions, compatible plugin/profile IDs and firmware versions, a settings schema ID and SHA-256 digest, complete settings, and author/revision/evidence provenance. Evidence is labelled `synthetic` or `documented`. Unknown firmware or a firmware mismatch fails preset validation.

No defaults are inserted, and no inheritance or merge is performed. Settings must satisfy the supplied schema. When attached to a configuration binding, settings also satisfy the canonical action input schema and descriptor input constraints. A permissive plugin schema cannot relax those action constraints. There is no approval, execution or credential field in the preset contract.

## Optional plotting and panels

A readings page may have no plots. Time-series plots require numeric scalar variables and a receipt-time axis measured in seconds. Waveform plots require numeric vector axes. Plot bindings must belong to their page and resolve to observation or dataset targets. String or boolean values remain suitable for readings tables but cannot become numeric plots.

Class and custom panels name an exact versioned host panel, such as `vendor-panel/1.0.0`. The validator never imports or executes that panel. An unavailable optional panel is returned in `unavailable_pages`; an unavailable required panel produces `panel_unavailable` and fails validation. Missing required UI features fail with `unsupported_feature`.

## SDK commands

```sh
benchweave-sdk new example --package example_plugin --with-ui
benchweave-sdk check-ui example/src/example_plugin/presentation.json \
  --descriptor example/src/example_plugin/descriptor.json \
  --resources example/src/example_plugin \
  --catalogue example/src/example_plugin/binding-catalogue.json \
  --firmware 1.0.0
benchweave-sdk check-preset configuration.json \
  --descriptor descriptor.json --settings-schema configuration.schema.json \
  --firmware 1.0.0
benchweave-sdk inventory prepared-package
```

`--resources` identifies the package directory; the envelope's `resource_root` is resolved within it. Resource names are portable relative paths. The filesystem reader rejects symlinks, non-regular files and oversized content, including symlinks in parent components. Use canonical directory paths on systems with aliases such as macOS `/var` or `/tmp`. `--feature` and `--panel` can be repeated to describe the target host's supported UI features and panels.

`benchweave_sdk.presentation.validate_preset` and `validate_presentation` expose the same offline checks as the CLI. SDK wheels and self-contained source archives bundle the gateway's pure validator byte-for-byte; installed SDK operation does not import the gateway. The source checkout has a development-only loader for that same file. Neither distribution depends on a third presentation package.

The gateway's `benchweave.presentation.admission.validate_attachment` accepts an already admitted descriptor, resources verified from the exact envelope root, the trusted catalogue and the host's feature/panel sets. It returns compatibility findings and never performs package admission or activation. Registry linkage and runtime rendering are separate integration work; placing files in a folder does not attach a UI.

## Limits and diagnostics

JSON documents are limited to 262,144 bytes and 32 levels of nesting, with strict UTF-8, duplicate-key rejection and finite numbers. Limits also include 64 pages, 256 bindings, targets or assets, 256-character IDs/titles, 16 MiB per resource and 64 MiB for the resource collection. Digests apply to exact original bytes, including whitespace. Schema resolution is offline.

Reports contain stable diagnostic codes and paths rather than settings values. Codes include `invalid_document`, `limit_exceeded`, `invalid_schema`, `digest_mismatch`, `identity_mismatch`, `incompatible_firmware`, `unresolved_reference`, `capability_mismatch`, `invalid_settings`, `invalid_plot`, `unsafe_path`, `unsupported_version`, `unsupported_feature` and `panel_unavailable`. Success means offline compatibility only, not admission or approval to apply settings.

## Executable synthetic examples

The SDK-generated read-only starter and `tests/unit/test_presentation_manifest.py` exercise readings with optional time-series plotting. `tests/unit/test_presentation_specimens.py` constructs a DC supply configuration preset and an oscilloscope waveform from the existing OTDP class fixtures. These fixtures are synthetic contract evidence, not qualified device drivers. `scripts/sdk_smoke.py` builds both distributions, rebuilds wheels from source archives, installs the generated plugin outside the checkout and checks resource hashes and SDK/gateway validator parity on the existing Linux/macOS CI matrix.
