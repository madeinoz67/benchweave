# BenchWeave

BenchWeave is the project name for the Smart Test Gateway architecture work.

This repository carries the BenchWeave implementation for packages WP01 to WP07. It also carries the frozen architecture and PoC and MVP planning documents. Implementation flows from the PRD and delivery plan in this folder, with architecture documents treated as contracts rather than informal notes.

**Current status (updated 2026-09-14):** interface 0.1.0 is live on the gateway side. It has 20 REST routes and 17 MCP tools over FastAPI and FastMCP on one core-operations seam. Parity between REST and MCP is proven. SIGKILL event recovery is proven. The change kinds for registry admission and activation are not reachable without a registry session. OAuth and TLS are out of PoC scope. Both limits are disclosed in the [compatibility record](compatibility.md). The `feature/ui` line adds the workbench style guide for Layered Precision. It also adds the SDK's simulation-only plugin UI preview workflow. The workflow has a bundled renderer, a preview server and a Click, Rich and Textual CLI.

## Start Here

- [PoC MVP PRD](implementation-planning/00-poc-mvp-prd.md)
- [Delivery plan](implementation-planning/01-delivery-plan.md)
- [First slice plan](implementation-planning/03-first-slice-plan.md)
- [Architecture v1.5](smart-test-gateway-architecture-v1.5.md)

## Contract Sets

- [OTDP 0.2.0](../standards/otdp/0.2.0/otdp-specification.md)
- [Registry v0.1.2](../standards/registry/0.1.2/registry-specification.md)
- [Contributor publishing design record](implementation-planning/10-contributor-publishing-design.md)
- [Publishing guide](publishing-guide.md)
- [Execution v0.2.0](../standards/execution/0.2.0/execution-contract.md)
- [Interface v0.1.0](../standards/interface/0.1.0/interface-contract.md)
- [Plugin UI v0.3.0](../standards/plugin-ui/0.3.0/README.md) and [Plugin UI preview v1](../standards/plugin-ui-preview/0.2.0/fixture.schema.json) (fixture and served-document schemas for the simulation-only preview workflow)
- [Acceptance closure](acceptance/end-to-end-review.md)


## Development

Start with [Develop your device with AI](develop-your-device.md) for five-step paths to build a device plugin or custom firmware, with reusable prompts that cover development, testing, review and release preparation. Device plugins integrate existing instruments or custom hardware. Independent plugin repositories and releases are the preferred path for authors.

Use the [AI device reviewer](ai-device-reviewer.md) to assess candidate integrations against the contracts and their evidence.

Start with the [Device developer guide](device-developer-guide.md) for device creation, for hosting on the gateway, and for shared packages. It includes an AI task template and a human review checklist.

The [plugin SDK guide](plugin-sdk.md) documents the plugin developer SDK, maintained in the separate [benchweave-sdk](https://github.com/madeinoz67/benchweave-sdk) repository mounted at `packages/sdk`.

See [Development and CI](development.md) for uv setup, local checks and GitHub workflows.
