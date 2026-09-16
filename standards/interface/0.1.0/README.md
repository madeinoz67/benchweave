# Interface contract 0.1.0

This directory is the interface standard at version 0.1.0: the REST/OpenAPI
surface, the MCP tool set, the operation catalog, and the shared envelope
schema, with their exchange examples. Its bytes are pinned row-by-row by
`standards/corpus-manifest.json`; governance lives in
`standards/standards-manifest.json` and `standards/GOVERNANCE.md`.

## History

Version 0.1.0 is the governance starting point (the 2026-09-16 reset). The
pre-reset lineage — interface 1.1.0 and its 1.1.1 errata (the optional
`approver_token` on `change_apply`'s body, carried in `openapi.json`) — lives
in git history and in the corpus manifest's `source` provenance fields. The
errata semantics are part of these bytes; there is no separate revision.
