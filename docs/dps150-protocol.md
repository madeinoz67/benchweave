# DPS-150 protocol and plugin

The DPS-150 integration is now an independent project at `plugins/fnirsi/dps150/`. Its protocol library, adapter, descriptor, licence, evidence and tests belong to that project, not to the BenchWeave core wheel.

Read `plugins/fnirsi/dps150/README.md` for setup and mock conformance, and `plugins/fnirsi/dps150/docs/protocol-evidence.md` for pinned source evidence, supported commands and limitations. The import package is `benchweave_fnirsi_dps150`; descriptor ID `org.benchweave.fnirsi-dps150` is unchanged.

The [developer guide](device-developer-guide.md#repository-layout-for-device-plugins) defines the manufacturer/model project structure and ownership of custom-device firmware. DPS-150 has no maintained firmware source or flashing implementation. Hardware operation and publication remain separately authorised.
