# Security Policy

BenchWeave is **pre-1.0** software maintained by a single person. This policy is
written to be honest about that rather than to promise more than it can deliver.

## Reporting a vulnerability

**Please report privately, not in a public issue.**

Use GitHub's private vulnerability reporting:
[**Report a vulnerability**](https://github.com/madeinoz67/benchweave/security/advisories/new).
It creates a private advisory only you and the maintainer can see, and it handles
coordinated disclosure and CVE requests if it gets that far.

If you can, include:

- The version or commit you tested (`benchweave --version`)
- Which surface is affected — the gateway process, the plugin API it exposes to
  plugins, a device plugin, the CLI, or the packaged UI
- What an attacker gains, and what access they need to start (loopback reach? an
  observe-tier token? a control-tier token?)
- The smallest reproduction you can manage

Reports are acknowledged and worked on a **best-effort** basis. No response time is
promised that cannot be honored. If something is being actively exploited, say so in
the report and it will be treated accordingly.

Please give a reasonable chance to ship a fix before disclosing publicly. Credit in
the advisory is gladly given — say how you want to be credited, or that you would
rather not be.

## Scope

**Supported version: the latest release.** BenchWeave is pre-1.0 and fixes are not
backported to older tags.

In scope — anything that lets someone exceed a boundary the gateway is supposed to
enforce:

- The plugin API the gateway exposes to plugins — a plugin reaching host
  capabilities it was not granted
- Token tier confusion — an observe-tier bearer token reaching control-tier
  operations, or a token reaching beyond its tier
- Corruption or loss of bench state or run evidence (the store, the content
  store, backup/restore)
- Untrusted input — recorded sessions, fixture or binding documents, plugin
  descriptors — leading to code execution in the gateway process
- Secrets or tokens leaking through logs, errors, API responses, or reports
- The control plane when the gateway is bound beyond loopback

Out of scope:

- **What a plugin the operator chose to install does on its own host.** Plugins
  are code you deliberately install, like any Python package; the API boundary
  they run inside is in scope, the behavior of software you chose to run is not.
- Anything that requires an attacker to already have filesystem or OS-level
  access to the host — BenchWeave is local-first, single-operator software and
  does not defend against a compromised machine.
- Missing TLS or hardening headers. The gateway binds to loopback
  (`127.0.0.1:8125`) by default and ships no TLS. If you rebind it or put it
  behind a reverse proxy, transport security is yours to provide.
- Denial of service through sheer volume against an instance you control.
- Findings from automated scanners with no demonstrated impact.

## Known weaknesses

BenchWeave is pre-1.0 and has rough edges already known about; some are tracked
as public issues. If you find something already tracked, a comment on that issue
is more useful than a new report — but if you think it is more severe than it was
rated, say so privately. Re-rating severity beats defending it.
