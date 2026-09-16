# Security Policy

## Supported versions

Only the latest release and the `main` branch receive security fixes.

## Reporting a vulnerability

**Do not open a public GitHub issue for a security problem.**

Email **[seaton@strobotics.com.au](mailto:seaton@strobotics.com.au)** with:

- the affected component (gateway, device plugin, plugin API, SDK, or UI),
- steps to reproduce or a proof of concept,
- the impact you believe it has.

You should receive an acknowledgment, typically within 72 hours. Fixes are coordinated with you before disclosure; credit in the advisory is yours if you want it.

## Scope

BenchWeave is a local-first test-bench gateway: the gateway process, the plugin
API it exposes to plugins, the SDK, and the packaged UI are all in scope.
Issues in dependencies should be reported upstream, but a working exploit
chain through BenchWeave counts.

Please do not run automated scanning, load testing, or denial-of-service
techniques against any publicly hosted BenchWeave infrastructure; this project
is self-hosted, so a repro on your own instance is all that is needed.
