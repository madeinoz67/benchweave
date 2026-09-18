# BenchWeave

BenchWeave is the project name for the Smart Test Gateway architecture work.

This repository carries the BenchWeave implementation (packages WP01–WP07) alongside the frozen architecture and PoC/MVP planning documents. Implementation flows from the PRD and delivery plan in this folder, with architecture documents treated as contracts rather than informal notes.

**Current status (updated 2026-09-14):** the gateway side of interface 0.1.0 is live — 20 REST routes + 17 MCP tools over FastAPI/FastMCP on one core-operations seam, REST↔MCP parity and SIGKILL event recovery proven; registry admission/activation change kinds are not reachable without a registry session, and OAuth/TLS are out of PoC scope — both disclosed in the [compatibility record](compatibility.md). The `feature/ui` line adds the Layered Precision workbench style guide and the SDK's simulation-only plugin UI preview workflow (bundled renderer, preview server, Click/Rich/Textual CLI).

## Start Here

- [PoC MVP PRD](implementation-planning/00-poc-mvp-prd.md)
- [Delivery plan](implementation-planning/01-delivery-plan.md)
- [First slice plan](implementation-planning/03-first-slice-plan.md)
- [Architecture v1.5](smart-test-gateway-architecture-v1.5.md)

## Contract Sets

- [OTDP v0.1.0](../standards/otdp/0.1.1/otdp-specification.md)
- [Registry v0.1.0](../standards/registry/0.1.0/registry-specification.md)
- [Execution v0.1.0](../standards/execution/0.1.0/execution-contract.md)
- [Interface v0.1.0](../standards/interface/0.1.0/interface-contract.md)
- [Plugin UI v0.1.0](../standards/plugin-ui/0.1.0/README.md) and [Plugin UI preview v1](../standards/plugin-ui-preview/0.1.0/fixture.schema.json) (fixture and served-document schemas for the simulation-only preview workflow)
- [Acceptance closure](acceptance/end-to-end-review.md)


## Development

Start with [Develop your device with AI](develop-your-device.md) for five-step paths to build a device plugin or custom firmware, with reusable prompts covering development, testing, review and release preparation. Device plugins integrate existing instruments or custom hardware; independent plugin repositories and releases are the preferred authoring path.

Use the [AI device reviewer](ai-device-reviewer.md) to assess candidate integrations against the contracts and their evidence.

Start with the [Device developer guide](device-developer-guide.md) for device creation, gateway hosting and shared packages, including an AI task template and human review checklist.

The [plugin SDK guide](plugin-sdk.md) documents the offline plugin authoring SDK, maintained in the separate [benchweave-sdk](https://github.com/madeinoz67/benchweave-sdk) repository mounted at `packages/sdk`.

See [Development and CI](development.md) for uv setup, local checks and GitHub workflows.
