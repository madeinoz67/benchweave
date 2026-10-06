# Issue #385 design — the device-addition surface: bind `connection_key` to a physical endpoint

**Issue:** #385 (I3: device-addition surface — bind `connection_key` to a physical
endpoint (instance-keyed, 1..N devices)) · **Label:** `sdk` · **Umbrella:** #285 (PRD-11
I3) · **Record:** 2026-10-06, a re-design — the previous pass (record 8444216) and its
branch were swept with the record unrecoverable; two owner-adopted forks survive from it
and are carried forward as binding input (F-385-1, F-385-2, restated in §1).

**Verdict: BUILD, one minimal slice** (the mechanism + the operator pick + the
binding-pending serve + the discovery-row gap closure), with six named deferrals. The
binding state lives in **a new operator-owned document, not in `transport-settings.json`**
— the #147 F-secrets ruling and its risk-2 falsifier already closed the "endpoint field in
transport-settings.json" path, and named the home this increment builds: *the deferred
operator admission surface* (§3.2). This record is frozen bytes; corrections land as dated
addenda at the section open.

**Public-record note.** Mock paths, candidate serials and device names below are invented
(`Acme`/`WidgetLab` fixtures, `/dev/cu.usbserial-A`-style mock paths). No real bench, no
real device serial, no install-specific topology is named. Every device-behaviour claim
about real hardware is labelled speculative; the one open hardware fact (§0.5) is
unmeasured and the design supports both outcomes without claiming which is real.

---

## 0. State established from the code, not assumption

Anchors verified this session against `0adf2d86` (gateway main) and the pinned
`packages/sdk` tree, via the graph's file reads.

### 0.1 The gap is exactly two lines of row construction, and a schema

`benchweave_sdk_server/serial.py:1364` `_device_row` builds each discovery row as
`{id, manufacturer, model, transport, connection_key}` — **the enumerated port name is
computed and thrown away** (`_port_name(port)` at `serial.py:1251` is used only for the
probe call and the no-re-probe comparison). The row's `id` is `plugin.device_id`
(`session.py:121`), which is the descriptor's `transport.connection_key` — so N confirmed
candidates produce N rows that are indistinguishable by id and carry no endpoint.

Measured this session (a RED spike over the live module, run from `packages/sdk`):

```
SPIKE discover row keys today: ['connection_key', 'id', 'manufacturer', 'model', 'transport']
SPIKE _DEVICE_SUMMARY properties: ['connection_key', 'id', 'manufacturer', 'model', 'transport']
SPIKE row has port? False | has usb_serial? False
```

The schema half: `catalogue.py:122` `_DEVICE_SUMMARY` is
`additionalProperties: false` over those five keys — the discover result *cannot* carry an
endpoint today, by schema, the same way `transport-settings.json` cannot. **This is the
discovery-endpoint gap the issue names**, and it is why the operator cannot bind: there is
no endpoint in any surface to pick *from*.

### 0.2 Today's only endpoint source is a process-start CLI flag

`cli.py:120-125`: `serve --transport serial` without `--device` exits 2 with
`standalone_transport_serial_device_required: --transport serial requires --device <path>`.
The flag is wired through `cli.py:144` (`serial_device_path=device`) and captured
construed-time by the seam (`seam.py:180` `self._serial_device_path`). Nothing persists a
pick. The issue's question — *which physical device does `connection_key: "adc_board"`
refer to?* — is answered only by whoever typed the flag, for one process lifetime.

### 0.3 Discovery already does the hard part, and already throws away instance identity

`discover_serial_devices` (`serial.py:1376`): enumerate (`_pyserial_enumerate`,
`serial.py:1206` — `list_ports.comports()`), filter by the descriptor's declared USB hint
(`usb_identity_filter`, `serial.py:1221` — the `x-standalone-usb-vid`/`x-standalone-usb-pid`
extension keys under `transport.settings`; #386 closed the wording that the descriptor's
`serialTransport` carries no standard vid/pid), then confirm each survivor by an IDENTIFY
probe (`_confirm_by_identify`, `serial.py:1288`) that refuses a foreign or silent answer.
The probe's answer is the candidate's identity — and the port object's `serial_number`
(the USB bridge's serial, when the chip reports one) is never read. The three things the
issue asks discovery to enumerate — **port path, USB serial number if the chip reports one,
IDENTIFY probe result** — are two-thirds available and entirely undelivered.

### 0.4 The one-contract seam means the pick needs no UI-private path

`seam.py` header: *"The operations seam: the only mutation path, shared by REST, HTML and
MCP. A13's one-contract rule applied to standalone: every surface is an adapter over
`StandaloneSeam.call`."* The catalogue (`catalogue.py:490+`, "the closed SW-10 catalogue")
feeds the REST adapter (`web.py:134` `_add_rest_routes`, one route per op) and the MCP
tools (`mcp.py` — one `bws_v1_<op>` tool per implemented row, schemas pinned from the
catalogue verbatim). A new catalogue row is automatically an operation on every surface;
the UI's own routes (`web.py:244` `POST /discover`, `web.py:630` `POST
/devices/{device_id}/connect`) call `seam.call` like everything else. The write path for
the pick is therefore *a catalogue operation*, not a UI endpoint — the brief's "no UI-private
operations" requirement falls out of the existing mechanism.

The PRD's own alignment rows back the shape: PRD-11 §5 names "interface 0.1.0: operation
catalogue, OpenAPI, 17 MCP tools `stg_v1_*`, error codes" as the upstream standard the host
aligns with, and Q4 ruled the host's namespace to `bws_v1_*` (own prefix, interface-0.1.0
shapes where semantics match) so an agent cannot assume gateway guarantees from familiar
names (`mcp.py:1-8`). SW-11 pins the error vocabulary (`invalid_request`, `not_found`,
`conflict`, `not_ready`, `unavailable`, `internal_error` + `correlation_id`; `policy_denied`
and `forbidden` are never emitted — there is no policy engine). SW-34 pins the originating
surface as host-supplied dispatch knowledge; SW-54 pins operator attribution (local OS
user) on capture metadata — both reused verbatim for the pick record (§1.4).

### 0.5 The open hardware fact, and the two forks the design must carry

Issue #385 states it plainly: **unmeasured whether common CH343G-class USB-UART bridges
report distinct USB serial numbers**. Distinct → the serial is an instance key that
survives port re-enumeration. Blank or duplicate → only the port path plus the operator's
pick distinguishes instances. #387 records the companion limit: IDENTIFY_RSP carries no
unique board ID, so protocol-level self-identification is unavailable today. The design
therefore carries **both** outcomes (§1.5) and measures both on mock fixtures (§6); the
real measurement is deferred (D-385-3) and no hardware claim is made.

### 0.6 The #407 interlock — what the negotiated link already owns

#407 merged `reconfigure_link` + live link state on both sides. `serial_plugin_session`
(`serial.py:1143`) mints a **fresh link + services per connection** (the M1 fold: "a
reconnect starts a new conversation over a new link, and a faulted link never serves a
second conversation"), and each mint builds the `LinkReconfigurator` (`serial.py:1125`)
with `device_path=device_path` (`serial.py:1178-1184`) — the same path the opener used.
The reconfigure law (#407's own words, `serial.py:14-28`): a baud change is a **line
reset** — one bounded attempt, `close_transport` then reopen *the same path*; a closed
session refuses `standalone_serial_reconfigure_closed`; the `_reconfigure_lock`
(`serial.py:692`) serialises reconfigure against close so a swap can never orphan a
transport.

Consequences for the binding, which this design adopts as the interlock contract:

1. **The binding resolves once, at mint.** The mint hands one resolved path to both the
   opener and the reconfigurator — so a reconfigure reopens *the resolved endpoint* and
   never consults the binding. The negotiated link owns the live port between
   reconfigures; the binding is not consulted while a link lives.
2. **A rebind cannot re-point a live link.** `device_bind`/`device_unbind` refuse typed
   `conflict` while a session is connected (§1.4) — the operator disconnects first. The
   new binding takes effect at the next mint (next connect), which is also what makes
   F-385-2's serve-then-bind-then-connect flow work without a restart.
3. **The mint-time resolve is the house's own late-bound shape** — the factory already
   reads `session.link_event_publisher` at mint time ("the late-bound shape, the `cli.py`
   factory docstring", `serial.py:1183`); resolving the endpoint the same way is an
   extension, not a new mechanism.

### 0.7 What the binding must NOT do (F-385-1, carried forward)

The descriptor's sentence stands untouched: *"Addresses/paths/credentials are not granted
by this descriptor."* The binding is an operator-owned **routing layer** — it selects which
physical endpoint an already-admitted plugin's `connection_key` routes to. It grants no
capability: the plugin's operation set stays exactly the descriptor's declared set, the
binding document is never read by the adapter (the adapter sees only `HostServices`; the
host reads the document), and no field of the descriptor, the bench schema, or
`transport-settings.json` changes. Structural, not policy: the binding document lives
outside the plugin project (a plugin cannot ship one), its schema is endpoint-shaped only
as *routing* data, and the capability axis (what the device may be asked to do) has no field
in it.

---

## 1. Mechanism

### 1.1 Where binding state lives — a new operator-owned document

**Decision: a separate operator-owned `device-bindings.json`, NOT an extension of
`transport-settings.json`.**

- **Precedent (extended, not invented):** `src/benchweave/control/provider_settings.py` —
  the issue #147 increment-3 construction: *"an operator-owned, optional
  `transport-settings.json` in the fixtures directory (the administrator-configuration
  locus), validated against a schema in gateway source — NOT corpus"*; exact-byte decode
  through `benchweave.content.json_document.load_document`; `additionalProperties: false`
  throughout; typed machine-matchable refusals (`settings_schema:` /
  `settings_digest_mismatch:`); internal-consistency refusals (duplicate admission, a key
  bound twice, a binding naming an unadmitted provider).
- **Why not extend that file:** the same record's owner fork **F-secrets** ruled
  identity-only *now* and rejected "carrying endpoint strings in `transport-settings.json`
  from day one — it would put §6's no-direct-access sentence one schema-edit away from
  false", with risk 2's falsifier: *"any request for an endpoint/secret/credential field
  before the first provider implementation — refused and routed to deferral 3"*. Deferral
  3's home is literally *"the deferred operator admission surface"*. This increment is that
  surface beginning to exist — standalone-host scoped. `transport-settings.json` stays
  byte-identical (a falsifier check: the slice's diff must not touch
  `control/provider_settings.py` or its schema dict).
- **Why not the plugin project:** F-385-1 — not a descriptor change; plugin projects are
  distributable ("a plugin from anywhere") and may be installed read-only; endpoint data in
  plugin content is exactly what the descriptor's sentence forbids.
- **Why not the capture library's SQLite index** (`library.py:48` `captures`, rebuildable
  from the capture root, "never the only copy of anything"): a binding is an operator
  decision that is **not** rebuildable — it must survive as a document, and the capture root
  itself refuses unlisted files (`capture.py:12`: inventory verification "refuses unlisted
  files"), so evidence is not a config locus.

**Locus and resolution** (mirroring `capture_root`'s own precedence, `capture.py:62-110` —
explicit argument over environment over working-directory default, refuse-loud on a blank
env value):

```
--device-bindings <path>   >   $BENCHWEAVE_DEVICE_BINDINGS   >   device-bindings.json under the working directory
```

One document per bench (the operator's bench configuration), holding N rows (one per
device instance / `connection_key`). The serve banner prints the resolved path beside the
capture root (the disclosure the flag path never had). The document is **optional** —
absent means every connection key is binding-pending.

**Document shape** (the schema is a dict in `device_bindings.py` source, the
`TRANSPORT_SETTINGS_SCHEMA` precedent — NOT a corpus/JSON-Schema file, and therefore not a
standards surface):

```json
{
  "config_version": "1",
  "bindings": [
    {
      "connection_key": "adc_board",
      "endpoint": {
        "port": "/dev/cu.usbserial-A",
        "usb_serial": "W12345",              // omitted or null when the chip reports none
        "serial": "SIM001",                  // IDENTIFY_RSP serial — evidence, not identity (§0.5/#387)
        "firmware": "1.0.0",                 // IDENTIFY_RSP firmware — evidence (changes across upgrades)
        "manufacturer": "Acme",
        "model": "demo"
      },
      "bound_at": "2026-10-06T02:00:00Z",
      "operator": "<local OS user>",
      "surface": "ui"                        // ui | rest | mcp — host-supplied (SW-34)
    }
  ]
}
```

- `connection_key` pattern `^[a-z][a-z0-9_]*$` (the descriptor schema's own
  `customTransport.connection_key` pattern); **unique** — a key bound twice refuses
  `bindings_schema:` (the `provider_settings` invariant, verbatim: "a connection key bound
  twice refuses").
- Decoded through `load_document` (duplicate keys, non-finite numbers, size cap, strict
  UTF-8) with a computed digest — CON-1's discipline; there is no external pin, so the
  digest is computed and passed as the expected digest exactly as
  `load_transport_settings` does for the settings file itself.
- **Write path:** `device_bind` writes atomically (temp file + `os.rename`, the
  `StandaloneCaptureWriter` finalise precedent, `capture.py:358`) and rewrites only the one
  row (read-modify-write over the document). Concurrent binds inside one process cannot
  interleave the read and the rename: the bind handler is synchronous file I/O with no
  await between read and rename on the single event loop — the structural reason, not a
  lock. Two *processes* sharing one document can lose an update (disclosed residual,
  D-385-5; the `library.py:200` `_acquire_lock` file-lock precedent is the named carrier).
- **Hand-edits are first-class** (the `provider_settings` "operator's file act" posture):
  a hand-written row that schema-validates is a binding. The mint re-reads the document
  (§1.3), so hand-edits are live without a restart.

**Typed refusal family** (the machine-matchable surface, STD-4's discipline — "the prefixes
are an API even though they live in error text"):

| Prefix | Raised by | Meaning |
|---|---|---|
| `bindings_schema:` | the store load | decode / schema / internal-consistency failure |
| `bindings_io:` | the store write | the atomic write failed (never a silent drop) |
| `binding_pick_unscanned:` | `device_bind` | the pick names no candidate from the host's last scan |
| `binding_source_conflict:` | seam construction | `--device` and the store row name different endpoints |
| `binding_instance_absent:` | the mint resolve | the bound instance is not in the current enumeration |
| `binding_mismatch:` | `device_connect` | the connected identity disagrees with the record's fingerprint |
| `standalone_binding_pending:` | the device ops | no binding yet — not_ready, pages still render |

### 1.2 Discovery enumeration flow (the gap closure)

`discover_serial_devices` rows gain the instance identity the issue names. The probe and
the USB-hint filter are unchanged; the row construction stops discarding what it already
computed:

- `_device_row` takes the port object alongside the identify answer and emits
  `port` (the enumerated name, `_port_name`), `usb_serial` (the port object's
  `serial_number` when the chip reports one, else null), `serial` and `firmware` (the
  IDENTIFY answer's fields, null when the firmware reports none). `manufacturer`/`model`
  stay as they are (they are the probe answer's identity fields).
- `catalogue.py:122` `_DEVICE_SUMMARY` gains `port` (**required**, `["string","null"]` —
  the mock arm's row carries `port: null`, honestly "no physical endpoint") and
  `usb_serial` / `serial` / `firmware` (`["string","null"]`, declared-not-required — the
  `_IDENTITY_RESULT.link` precedent at `catalogue.py:135-147`). The serial discover path
  always emits all four (§6 arm A4 pins this mechanically).
- **Claim discipline on the row's identity fields:** `usb_serial` is the only *instance*
  candidate (when the chip reports a distinct one); `serial` is the IDENTIFY_RSP serial and
  is **not** instance identity (#387) — it is recorded evidence and shown on the pick
  screen; `manufacturer`/`model` are class identity (VID/PID + IDENTIFY signature are
  class, never instance — the issue's constraint).

**Considered and rejected:** making the row's `id` the port path (an "instance id").
Rejected because every device operation keys on the host's one session device id
(`session.py:121` `device_id` = `connection_key`; `_op_device_connect`/`_op_device_get`
refuse `arguments["device_id"] != self._session.device_id` with `not_found`) — foreign ids
in discover rows would break the closed op contract. The endpoint is the instance
discriminator; the device id is the host's one session. The binding record is
"instance-keyed" in the sense the issue needs: it keys the *instance* (the picked endpoint
identity) under the connection_key, never the class.

### 1.3 The resolve path for sessions (bind-then-route)

The resolve lives at **mint** (per connection), not at session construction:

```
endpoint := (the --device flag, if given)  else  resolve_binding(document, connection_key)
```

`resolve_binding` re-reads the bindings document (the file is the source of truth; no
in-memory copy can drift) and applies one rule that carries both serial-outcome forks
(§0.5):

1. The record's `usb_serial` is non-empty **and exactly one** enumerated port reports it
   → that port. **Serial-keyed** — survives port re-enumeration (fork A).
2. The record's `usb_serial` is non-empty and **zero** ports report it → the instance is
   gone: `binding_instance_absent` → binding-pending. **Never fall back to the path** — a
   path fallback would open a *different* device, which is exactly the swap hazard.
3. The record's `usb_serial` is non-empty and **≥2** ports report it (duplicate serials) →
   **path-keyed** on the record's `port`; the duplicate-serial swap is a disclosed residual
   (what the guard does not catch, §7.2).
4. The record has no `usb_serial` → **path-keyed** on the record's `port` (fork B).
5. The path-keyed port is not enumerated → `binding_instance_absent` → binding-pending.

The mint hands the resolved path to **both** `opener(path, boot_settings)` and
`LinkReconfigurator(device_path=path, …)` — the §0.6 interlock. The mint also reports the
resolved endpoint on the session (`PluginSession.endpoint`), which becomes the no-re-probe
clause's match key: `seam.py:445` currently matches the construction-time
`self._serial_device_path` (flag-coupled, #389's wiring); it matches the session's own
minted endpoint instead. Byte-equality stays (alias spellings are D-385-2 / #392).

**Connect-time identity verification** (the bound path only): after `session.connect()`,
the seam compares `session.identity` against the record's fingerprint — `manufacturer` and
`model` always; `usb_serial` when the record carries one. `serial` and `firmware` are
**not** compared (the firmware field changes across upgrades; the IDENTIFY serial is not
unique per #387). A mismatch closes the session and fails typed `binding_mismatch` → the
device page shows the reason; no silent wrong-device session. This also closes, on the
bound path, the asymmetry a prior review recorded (the connected scan row serving
`session.identity` UNVERIFIED while probe rows are descriptor-verified) — the flag path
keeps today's unverified posture, disclosed.

**What this verify does not catch** (stated, per claim discipline): two instances with
identical class identity and blank/duplicate `usb_serial` swapped across paths; a
misbehaving adapter that byte-echoes the expected fingerprint (the scaffold reference
byte-pins its reply) — the binding is operator trust and routing, not a security boundary.

### 1.4 The operator-pick write path

Two new catalogue operations (closed set; ops outside the catalogue are `invalid_request`):

| Op | Input | Result | Notes |
|---|---|---|---|
| `device_bind` | `{device_id, port}` | the binding projection | the pick names a **scanned candidate** by its port path |
| `device_unbind` | `{device_id}` | the binding projection (`state: "pending"`) | clears the row |

- **The pick is a scan row.** `device_bind` records the host-verified identity from the
  seam's discovery cache (`seam.py:445` `_discovery_cache`, the last scan's rows — the
  #389 no-re-probe clause already treats the cache as the host's identity source), never
  caller-supplied identity fields. A pick naming no cached candidate refuses
  `binding_pick_unscanned:` — the issue's step 1 (discover) is structurally before step 2
  (pick). The connect-time verify (§1.3) is the backstop for a stale cache.
- **Route-only (F-385-1):** the op writes routing data for the host's one connection_key;
  it adds no capability, touches no descriptor, and the row's capability axis has no field.
  The record stores the SW-54 operator (`getpass.getuser()` — the capture-metadata
  precedent) and the SW-34 originating surface (host-supplied dispatch knowledge,
  `web`/`rest`/`mcp`).
- **Both ops join `_STATE_EVENT_OPS`** (`seam.py:108` — the host-state-change set that
  publishes an event, `parameter_stage`'s precedent): a watcher sees binds and unbinds.
- **Refusals:** `conflict` while a session is connected (the §0.6 interlock: a live
  negotiated link is never re-pointed); `conflict` while a `--device` flag names an
  ephemeral endpoint (drop the flag to record a binding — the dual-source rule below);
  `conflict` on the mock transport (binding is a serial-transport concern, the
  `standalone_transport_device_serial_only` precedent); the catalogue/schema refusals ride
  the seam's closed model unchanged.
- **Exposure:** REST (the catalogue adapter's `_add_rest_routes` loop — no hand-written
  route), MCP (`bws_v1_device_bind` / `bws_v1_device_unbind`, schemas pinned from the
  catalogue like every other tool), HTML (`POST /devices/{device_id}/bind` +
  `/unbind`, the `web.py` route style; the discovery page's candidate rows gain a pick
  action, the device page shows the binding state). No UI-private path exists or can (the
  one-contract seam). The write is an explicit operator act — the no-write-on-load
  discipline (`test_nowrite.py`, the parity suite's arm 4: "full load + poll cycle ⇒ verbs
  ⊆ {identify, read}") is untouched: loading a page never binds.

### 1.5 Binding-pending serve (F-385-2, carried forward)

`serve --transport serial` **starts** with no binding and no flag: exit 0, listener bound,
the UI renders. Device operations (`device_connect`, `device_get`, `parameter_*`,
`capture_*`) answer `not_ready` with `standalone_binding_pending:` and
`binding_state: "pending"` in `details`; `device_discover` works (that is how the operator
gets candidates to pick from). This is the PRD-11 **SW-73** posture generalised — *"pages
still render their layout with device operations `not_ready` and the load diagnostic
shown"* — the degraded-load sibling (`_refuse_degraded`, `seam.py`'s `load_diagnostic`
arm): the seam gains a `_refuse_binding_pending` gate alongside it, both pages-render,
ops-`not_ready` states. `host_info` and the device page carry the binding state
(`state: bound|pending`, `source: store|flag`, the resolved endpoint or the pending
reason, the resolved bindings path).

**The `--device` flag becomes an explicit ephemeral override** (the refusal path is
retired; the flag is not):

1. flag only → the session routes to the flag's path; `binding_source: "flag"` disclosed on
   `host_info` and the device page ("ephemeral; not recorded");
2. store only → the binding routes (the normal path);
3. both, same endpoint (byte-equality on the path — alias-blind, D-385-2) → fine;
4. both, **different** endpoints → typed refusal `binding_source_conflict:` at seam
   construction. Two sources of truth for one binding is a bad state; it is made
   unrepresentable rather than policy-checked (the flag can never silently override a
   recorded pick, and a recorded pick can never silently ignore a flag).

The mock transport is unchanged (no endpoints, no binding; `--device` stays refused on
mock — `test_a_device_on_the_mock_transport_refuses` survives as-is).

---

## 2. Minimal first increment — scope and deferrals

### 2.1 In scope (one slice, SDK-repo code + one gateway docs leg)

1. `device_bindings.py` — the store (document, schema dict, typed refusals, atomic write,
   `resolve_binding` with the §1.5 fork rule).
2. The discovery-row gap closure (`_device_row` + `_DEVICE_SUMMARY` + the mock arm's
   `port: null`).
3. `device_bind` / `device_unbind` in the catalogue + seam + REST/MCP/HTML exposure +
   the two `_STATE_EVENT_OPS` entries.
4. The mint-time resolve + the session's minted-endpoint report + the no-re-probe clause
   re-keyed to it + the connect-time fingerprint verify (bound path).
5. The binding-pending serve (the retired `--device` refusal, `_refuse_binding_pending`,
   `host_info`/device-page binding state) and the dual-source rule (§1.5).
6. The minimal UI pick: the discovery page's candidate rows gain a bind action; the device
   page shows bound/pending + source + the pick's identity fields (a real-render companion
   asserts the drawn action and state, §6).
7. Docs: the SDK README's serve/discovery/bind section (the operator surface), a
   device-developer-guide note on the connect-time identity check (device-visible
   behaviour), and the PRD-11 amendment row (the SW-10 catalogue gains `device_bind` /
   `device_unbind`; I3's row notes the binding-pending posture).

### 2.2 Explicitly deferred

| # | Deferred | Home | Reopen trigger |
|---|---|---|---|
| D-385-1 | Gateway-side realization of the binding (interface 0.1.0 operations under the caller's own principal and scopes; the execution-contract's commissioned operator-admission shape, #147 deferral 3) | follow-on issue | the first gateway-side adapter session construction that names a device endpoint — the observable: issue #167's first real capture-class or provider-backed plugin landing (the same event that reopens #147 deferral 3) |
| D-385-2 | Alias-spelling resolution of the bound path (cu vs tty vs `by-id` symlinks; the byte-equality limit the no-re-probe clause already discloses) | follow-on issue #392 | #392's alias-closure landing (the issue's own merge) |
| D-385-3 | The CH343G-class USB-serial measurement (whether common bridges report distinct USB serial numbers) | documentation here (§0.5) | a `list_ports` enumeration run on a bench with two or more same-bridge devices, its output recorded in the tracker — a measured trace, not a judgement |
| D-385-4 | Protocol-level instance identity (a unique board ID in IDENTIFY_RSP; the record's schema v2 `instance_id` field) | follow-on issue #387 | #387's protocol revision landing (the issue's own merge) |
| D-385-5 | Multi-process write locking for the bindings document (the `library.py` `_acquire_lock` carrier) | documentation here (§1.1) | a lost update observed across two host processes sharing one document — a measured trace (a bind whose write lands after a peer's and drops a row) |
| D-385-6 | Multi-transport endpoint shapes (the provider lane's endpoint axes — USB-HID, vendor-SDK; the document's `endpoint` gains a transport discriminator) | follow-on issue (the execution-standard queue — #147 deferral 2's home) | the first provider implementation (the same event as D-385-1) |
| D-385-7 | The binding-management UI beyond the device page (the multi-key list, edit and rebind flows) | follow-on issue | a bindings document containing two rows appearing on any bench — the observable: the second row in an operator's document |

The single-home form: every deferral is a **follow-on issue** except D-385-3 and D-385-5,
which are **documentation here** (this record's §0.5 and §1.1).

---

## 3. Precedent (all in-tree, extended not invented)

1. **The operator-settings document construction** — `control/provider_settings.py`
   (issue #147 increment 3): optional operator-owned JSON in the administrator-configuration
   locus, schema as a dict in source (NOT corpus), exact-byte decode, `additionalProperties:
   false`, typed `settings_*`-prefixed refusals, internal-consistency refusals, "the
   operator's file act plus its internal consistency" as authority. Extended: the same
   construction as a *second* document, because F-secrets and risk-2's falsifier bar
   endpoints in the first one.
2. **`capture_root`'s resolution precedence** (`capture.py:62-110`) — explicit argument
   over environment over working-directory default, blank-env refuse-loud. Extended:
   `--device-bindings` / `BENCHWEAVE_DEVICE_BINDINGS` / `device-bindings.json`.
3. **The degraded-load posture** (PRD-11 SW-73, `session.py:102-112` `LoadedPlugin`'s
   `load_diagnostic` + `_refuse_degraded`) — pages render, device ops `not_ready`, the
   diagnostic shown. Extended: `_refuse_binding_pending` as the second member of that
   family.
4. **The one-contract seam** (`seam.py` header; A13's rule) + the closed catalogue
   (`catalogue.py:490+`) — the pick is a catalogue row; REST/MCP/HTML are adapters.
   Extended: two rows, nothing new architecturally.
5. **The mint-time late-bound factory** (`serial.py:1176-1191`, the `link_event_publisher`
   read at mint) — the resolve rides the same shape; the `LinkReconfigurator` keeps one
   path per mint (#407's law).
6. **The scan cache as identity source** (#389's no-re-probe clause, `cli.py:137-143`
   comment + `seam.py:445`) — the pick records the cache's row; the clause re-keys to the
   session's minted endpoint.
7. **SW-54's operator attribution + SW-34's originating surface** — the pick record's
   `operator` / `surface` fields, copied from the capture-metadata discipline.
8. **The atomic finalise** (`capture.py:358`, temp + rename) — the bindings write.
9. **The serial suite's injectable doubles** (`test_serial_discovery.py:27-75` —
   `LoopbackPort` / `CandidatePort` / `SerialPortHooks`) + the #394 byte-stream mock
   (`session.py` `_DIALECTS`: `stream_exchange` / `send_receive`, `FrameRow`) — the mock
   driver for the whole proof (§6). Extended with `serial_number` on the candidate double
   and a two-candidate same-VID/PID fixture.

**Considered and rejected:** extending `transport-settings.json` (F-secrets closed it —
§1.1); putting the binding in the plugin project (F-385-1 + read-only installs); putting it
in the rebuildable SQLite index (violates "never the only copy of anything"); a UI-private
POST that writes the document (the one-contract seam forbids it and the brief rules it
out); re-probing the picked candidate at bind time (the cache is the probe result; the
connect verify is the backstop; a re-probe is a second transmission the no-re-probe
discipline does not need).

---

## 4. Invariant and drift impacts

### 4.1 `docs/internal/invariants.md` (gateway)

**No gateway invariant changes in this slice** — the gateway reads no binding document, and
the slice's gateway-side bytes are the record, a PRD-11 amendment row, and the submodule
pointer. The governing precedent is **CON-1's amendment (2026-09-23, issue #147 increment
3)**: *"Provider documents and the operator's `transport-settings.json` … decode through the
exact-byte decoder; the settings validator's own prefixes (`settings_schema:`,
`settings_digest_mismatch:`) join the same list."* When the gateway adopts the surface
(D-385-1), CON-1 gains a further amendment naming `device-bindings.json`'s decode and the
`bindings_*`/`binding_*` prefix family beside the settings prefixes — that amendment is
deferred with D-385-1, not pre-written.

### 4.2 SDK-side invariants (`packages/sdk/docs/internal/invariants.md`)

**A new row (or a STD-4 extension)**: the bindings document decodes through the exact-byte
decoder, and its refusal family (`bindings_schema:`, `bindings_io:`, `binding_pick_unscanned:`,
`binding_source_conflict:`, `binding_instance_absent:`, `binding_mismatch:`,
`standalone_binding_pending:`) is part of the machine-matchable surface — the prefixes are
an API (STD-4's own words). The build leg lands this row with the code.

### 4.3 `docs/internal/drift-and-obligations.md` — the walk

| Row | Fires? | Obligation |
|---|---|---|
| 1 — MCP tool change → vendored corpus (`standards/interface/0.1.0/mcp-tools.json`) | **No** | Scope: the gateway pins `stg_v1_*` to the corpus (CON-3). The standalone host's tools are `bws_v1_*` (PRD-11 Q4's own-prefix ruling, `mcp.py:1-8`) and are not corpus rows. Disclosed scope reading: row 1 governs the gateway's tool surface. |
| 2 — API-visible change → `standards/interface/0.1.0/openapi.json` | **No** | The standalone host's REST is its own catalogue adapter; the gateway's openapi is untouched. Same disclosed scope reading. |
| 3 — Plugin/device-visible behaviour → `docs/device-developer-guide.md` | **Yes** | The connect-time identity check refuses a device whose identify answer disagrees with the pick fingerprint (§1.3) — device-visible. The note lands in the SDK's published device-developer guide (the host's own guide; the gateway's guide is a different surface). |
| 4 — Operator-visible behaviour → operator docs + README | **Yes** | The serve/bind/`--device` semantics and the bindings document are operator-visible: the **SDK README** (the standalone host's operator surface) carries them. The gateway's `docs/operator-guide.md` / `README.md` are not this host's docs — the obligation is discharged on the SDK surface (the two-repo shape, §4.4). |
| 5 — The fixture lattice (`fixtures/registry/` ↔ builder ↔ `catalogue.json` ↔ digest tests) | **No** | None of the four move. **Named false-positive trap:** row 5's `catalogue.json` is the registry fixture catalogue, not `benchweave_sdk_server/catalogue.py`, which this slice does change. |
| 6 — Vendored contract bytes / `corpus-manifest.json` | **No** | Zero standards bytes move; the tripwire (`git diff origin/main...HEAD -- standards/`) must stay empty across the whole landing. The bindings schema is SDK source (the `provider_settings` precedent: NOT corpus). |
| 7 — The `packages/sdk` pointer | **Yes** | The two-repo discipline (AGENTS.md): the SDK commit is pushed and its PR merged **before** the pointer lands; the pointer commit advances the gitlink and the `.gitmodules` `pin` in the same commit (#408's rule; the `sdk-drift` lane reds on disagreement). No SDK version bump rides this slice, so no version-pairing set (matrix + lock + mirror) is owed. |
| 8 — The adapter protocol surface | **No** | No `interfaces.py` / `otdp_bridge.py` / descriptor-const movement. |
| 9 — `deploy/systemd/` | **No** | Untouched. |
| 10 — Dependency change | **No** | `pyproject.toml` / `uv.lock` untouched (pyserial already rides the `[server]` extra; fastmcp already present). |

### 4.4 Surfaces checklist (the brief's list)

MCP tools: **move** (SDK `mcp.py` + `catalogue.py`; no corpus). REST + openapi: **REST
moves** (SDK catalogue adapter); **openapi does not** (no standards bytes). CLI: **moves**
(SDK `cli.py` — `--device-bindings`, the `--device` override semantics; the gateway CLI
reference is a different surface). Operator docs: **moves** (SDK README). Device-developer
guide: **moves** (the connect-time identity note). Vendored standards: **does not move**.
Fixture lattice (the registry one): **does not move**; the SDK test fixture lattice
**does** (the mock doubles + the two-candidate cells). The SDK repo: **is** the code
surface. PRD-11 (`docs/implementation-planning/11-standalone-web-ui-prd.md`): **moves**
(the SW-10 catalogue amendment + I3's note — the catalogue is "the closed SW-10 catalogue,
in the PRD's own listing order", so new rows are a PRD amendment; the owner may instead
rule that #385 is the tracker record and the PRD is not amended — **named as fork
F-385-6**).

**On-disk format:** yes — a new persisted operator document (`device-bindings.json`), the
disclosed rubric-scope note of §5. **Schema:** a Python dict in SDK source, not a JSON
Schema file.

### 4.5 CI cost

No new jobs. The SDK `pytest` lane gains one mock-only test file plus extensions to the
serial suite (est. 30-40 tests, no real ports, no sleeps beyond the doubles' existing
timeouts) — seconds, not minutes. The gateway lanes are unchanged (docs + pointer).

---

## 5. Review tier and the Step-1 keyword scan (#254)

**Tier: TIER 3 — deep, mandatory second adversarial reviewer.**

Rules that trigger it (the Tier-3 bullet list; first-match-wins reaches Tier 3 either way):

1. **The keyword rule:** the expected diff text contains `asyncio`, `hashlib` and `sha256`
   (counts below).
2. **"Advances the `packages/sdk` submodule pointer"** — the gateway-side landing's pointer
   commit (§4.3 row 7).
3. **On-disk format (the disclosed scope note):** the slice introduces a new persisted
   operator document. The rubric's persisted-format bullet names the gateway's
   `state/migrations/`, `state/store.py`, `control/documents.py` and does not literally
   cover an SDK-side operator document; the tier is Tier 3 regardless of this bullet, and
   the note records that the brief's "an on-disk format makes it Tier 3" reading is
   satisfied by construction.

**Keyword scan over the expected diff text** (the whole increment: SDK code + tests + SDK
docs + the gateway PRD row + the pointer commit; docs and code alike). Counts are **floors
over the expected diff** — the builder re-derives the exact counts on the real diff:

| Keyword | Count (floor) | Where |
|---|---|---|
| `asyncio` | ≥ 5 | the serial/session/bind test surface is async (`asyncio.run` per test); the seam and serial mint code are already async |
| `hashlib` | ≥ 1 | `device_bindings.py` — the exact-byte decode digest (the `provider_settings` `hashlib.sha256` mirror) |
| `sha256` | ≥ 1 | the same digest call / the schema's digest pattern if any |
| `threading` | ≥ 1 | the serial suite's `LoopbackPort` double (`threading.Event`) rides the extended discovery/binding fixtures |
| `subprocess` | 0 | none expected |
| `migrate` | 0 | none expected |
| `recovery` | 0 | none expected |
| `protection` | 0 | none expected in the slice's own bytes |

Path/other rules: `standards/` — **0 files** (the tripwire); "any JSON Schema file" —
**0** (the bindings schema is a Python dict); dependency change — **0**;
`packages/sdk` pointer — **1 commit**. The record commit's own text carries `asyncio`,
`hashlib`, `sha256` and `protection` — the rubric's keyword-rule interplay self-fire, which
is intended and disclosed here.

Review shape consequent on Tier 3: the full suite (cold), the RED-sanity procedure per
claimed fix (§6's arms each carry a reversion), and **G6's independent second adversarial
reviewer** — plus the standing two-lane adversary on Tier-3 increments (2026-09-24 retro
R3).

---

## 6. Measurable proof and the pre-committed acceptance rule

**Mock driver (no hardware claims).** The `SerialPortHooks` injection (`serial.py:1198` —
`enumerate_ports` / `open_port`, "injectable so tests never open a real port") with the
serial suite's `LoopbackPort` / `CandidatePort` doubles extended with `serial_number`, and
the #394 byte-stream mock (`FrameRow` / the `send_receive` dialect) for the IDENTIFY
exchanges. **Fixture lattice:** four cells — 2 serial-outcome forks (distinct `usb_serial`
/ blank-or-duplicate) × 2 candidate counts (1 and 2 same-VID/PID candidates). Fake fixtures
only; device-behaviour claims (bridge serial reporting, IDENTIFY_RSP contents) are
**speculative** and unmeasured (D-385-3).

**Pre-committed acceptance rule — written before any number is looked at.**

*Metric:* per-arm pass proportion, counts read from `--junitxml` attributes or true exit
codes (never an output-filter summary). *Effect size:* binary exact-match per run
(correct endpoint path / correct not_ready / exact round-trip). *Sample:* N=20 repetitions
per applicable fixture cell for the routing arms (order-independence under `-n auto`);
N=10 for the serve-starts arm; N=1 per candidate for the round-trip arm.

| Arm | Assertion | RED control (the mechanism disabled) | Ship | Kill |
|---|---|---|---|---|
| **A1 bind-then-resolve** | bind K to candidate A's pick; connect; the `open_port` hook receives **exactly** A's port path and the session serves A's identify answer | revert the production resolve (keep the test) → the test goes RED (the mint opens the flag/None instead of the bound path) | 80/80 exact (20 × 4 cells) | any wrong-path open or mismatched identity in any run |
| **A2 binding-pending serves** | with no binding and no flag: `serve --transport serial` starts (exit 0, listener bound) AND `device_connect`/`device_get`/`parameter_read` answer `not_ready` with the `standalone_binding_pending:` reason AND the device page renders its layout with the diagnostic | against current main the arm is RED by construction (`cli.py:123`'s refusal kills serve) — demonstrated as the red-then-green pair | 3/3 assertions per cell (10 × 4) | any refusal (serve not starting) or any device op answering anything other than `not_ready` with the reason |
| **A3 1..N discrimination, both forks** | **Fork A** (distinct `usb_serial`): bind K→instance A, swap the two mock ports' paths under `enumerate_ports`, connect resolves to A's *physical* instance (the hook receives A's new path — the serial-keyed arm). **Fork B** (blank/duplicate): bind K→A's path, connect opens A's path; the swap residual is **disclosed, not claimed** | same reversion as A1 (plus a shuffle control: swap the mapping and assert the resolve follows the serial, not the row order) | 40/40 (20 per fork) | any wrong-instance open in fork A; any wrong-path open in fork B |
| **A4 discovery-endpoint gap closed** | every serial `device_discover` row carries its candidate's `port` (non-null) and `usb_serial` when the candidate reports one; a bind of a picked row writes **exactly** that path (+ serial) into the binding record (round-trip equality) | revert `_device_row` (keep the test) → the rows lose `port` and the arm is RED (the §0.1 spike, as a test) | 1/1 per candidate per cell | a row without a path, or a record whose path/serial differs from the picked row's |

*What ships the slice:* all four arms GREEN with each RED control demonstrated
(red-then-green, collected counts visible). *What kills the slice:* any arm failing after
the fold wave for a design reason (not a test defect) — the design is revised and nothing
ships. *What means the measurement was underpowered rather than conclusive:* the mock
double cannot express `serial_number` (the fixture cannot render the two forks) — then A3's
1..N claim is **unmeasured**, the design's fork support is disclosed as unproven, and the
slice ships A1/A2/A4 only **without** making the 1..N claim; likewise if an arm's RED
reversion cannot be isolated (the mechanism's causal link unproven), that arm is
inconclusive — neither a kill nor a ship — and the slice does not claim it.

**Fluff-killers beyond the arms:** the real-render companion for the UI leg (the G-render
rule — a payload-pinned test cannot falsify a draw claim): the rendered device page must
contain the bind action and the binding state in its HTML (asserted against the real
template render, not a mocked renderer), and the axe suite stays clean. The
no-write-on-load arm (page load + poll ⇒ verbs ⊆ {identify, read}) must stay green with
the bind action present.

---

## 7. Top risks, each with its falsifier

1. **The flip of the `--device` refusal breaks the CLI/serial contract tests by retirement
   rather than by replacement.** `test_serial_without_a_device_refuses` /
   `test_cli_transport_serial_requires_device` must become the A2 arms, not vanish.
   *Falsifier:* the suite passes with no test asserting serve-starts-binding-pending (the
   refusal tests deleted, nothing added) — A2's RED control is the detector.
2. **Serial-keyed resolve is hollow if the recorded serial is not instance-stable** (a
   bridge whose reported serial is port-derived or per-plug random — the CH343G question's
   shadow, §0.5). *Falsifier:* the D-385-3 measurement showing a recorded serial that
   changes across plugs of the same physical board — then fork A's claim dies and only
   path-keying stands; the record's rule (3) already degrades to path-keying when the
   serial is non-unique, and the claim would be withdrawn, not softened.
3. **The connect-time verify produces false refusals** (a legitimate device whose identify
   answer varies). *Falsifier:* a mock cell where `manufacturer`/`model` are stable but the
   session's identity object carries a varying extra field and the verify refuses — the
   verify compares exactly `manufacturer`, `model` and (when recorded) `usb_serial`, so a
   false refusal means the comparison set is wrong and the design is revised (not patched).
4. **The dual-source rule surprises automation** (`--device` + a stale store row →
   `binding_source_conflict` at start). *Falsifier:* a support report of a serve that will
   not start with both set — the mitigation is the refusal's message naming both endpoints
   and the two fixes (drop the flag / unbind); the risk is accepted because the silent
   alternative (§1.5 case 4) is the failure this rule exists to make unrepresentable.
5. **The bindings document default (working directory) collides across benches** (two
   benches sharing a CWD share rows). *Falsifier:* an operator report of a cross-bench bind
   — the banner prints the resolved path and `host_info` reports it; the fix would be a
   stricter default (the capture-root sibling), which the capture-root precedence makes a
   one-line change.
6. **The mint-time resolve races a concurrent bind** (bind during an in-flight connect).
   *Falsifier:* a test interleaving `device_bind` with `device_connect` that opens a path
   neither source named — the bind-refuses-while-connected rule plus the single-loop sync
   write make the interleaving structurally narrow, but the falsifier is a test, not an
   argument.
7. **A stale discovery cache records a wrong identity** (the device behind the picked port
   changed between scan and bind). *Falsifier:* a mock cell where the cache row's identity
   differs from the connect-time identity and the session connects anyway — the §1.3 verify
   is exactly this detector; a green run in that cell is a KILL.

---

## 8. Owner forks (surfaced, with recommendations)

- **F-385-3 — the locus of the binding document.** *Recommendation:* the standalone-host
  operator document (this record's default; the §0.1-0.2 evidence: the issue is `sdk`-labeled,
  every sibling is `packages/sdk` work, `--device` is the standalone CLI's, the standalone
  host has zero `transport-settings` readers, and F-secrets bars endpoints in that file).
  *Alternative:* a gateway-side sibling of `transport-settings.json` in the
  administrator-configuration locus, read by both the gateway and the standalone host —
  only if the owner wants one bench document shared across both processes; it changes
  nothing in the mechanism (the store is the same construction) but moves the file and adds
  a gateway reader, which is D-385-1's work early.
- **F-385-4 — the UI pick in slice 1.** *Recommendation:* **in** (this record's default) —
  the issue is explicitly the question "the standalone web UI must answer"; an operations-only
  slice answers it for MCP callers but not for the operator. *Alternative:* operations-only,
  UI in D-385-7 — smaller, but leaves the issue's own sentence unmet.
- **F-385-5 — `device_bind` while connected.** *Recommendation:* refuse `conflict` (this
  record's default; the §0.6 interlock: a live negotiated link is never silently
  re-pointed). *Alternative:* allow and take effect at next connect with the result
  reporting `takes_effect: "next_connect"` — more permissive, but the page would show a
  binding the live session does not honour.
- **F-385-6 — the PRD-11 amendment.** *Recommendation:* amend PRD-11 (a SW-10 row for
  `device_bind`/`device_unbind` + the binding-pending note on I3) — the catalogue is
  "the closed SW-10 catalogue, in the PRD's own listing order". *Alternative:* treat #385
  as the tracker record and leave the PRD frozen (then the catalogue's docstring
  "closed SW-10" is amended to name the post-PRD rows instead).

Defaults adopted for all four (F-385-1 and F-385-2 are carried forward as given, not
re-opened): standalone-host locus; UI pick in slice 1; bind-refuses-while-connected; PRD
amended.

---

## 9. File-level change list

**SDK repo (`benchweave-sdk`):**

1. `src/benchweave_sdk_server/device_bindings.py` **(new)** — document, schema dict,
   `BindingsRejected` + the §1.1 prefix family, `load_bindings`, the atomic write,
   `resolve_binding` (the §1.5 rule).
2. `src/benchweave_sdk_server/catalogue.py` — `_DEVICE_SUMMARY` += `port` (required,
   nullable) + `usb_serial`/`serial`/`firmware`; new rows `device_bind` / `device_unbind`
   (+ the binding projection schema).
3. `src/benchweave_sdk_server/seam.py` — `_op_device_bind` / `_op_device_unbind`;
   `_refuse_binding_pending` in the device ops; the two `_STATE_EVENT_OPS` entries;
   `host_info`'s binding block; the no-re-probe clause re-keyed to the session's minted
   endpoint; the connect-time fingerprint verify in `_op_device_connect`.
4. `src/benchweave_sdk_server/serial.py` — `_device_row` + `discover_serial_devices` gain
   the endpoint/probe fields; `serial_plugin_session` gains the mint-time resolve and hands
   one resolved path to opener + `LinkReconfigurator`.
5. `src/benchweave_sdk_server/session.py` — `PluginSession.endpoint` (the minted endpoint,
   the no-re-probe and verify source).
6. `src/benchweave_sdk_server/cli.py` — `--device-bindings`; the `--device` override +
   disclosure; the retired `standalone_transport_serial_device_required` refusal.
7. `src/benchweave_sdk_server/web.py` — `POST /devices/{device_id}/bind` + `/unbind`; the
   discovery page's pick action; the device page's binding state.
8. `src/benchweave_sdk_server/mcp.py` — `bws_v1_device_bind` / `bws_v1_device_unbind`.
9. `src/benchweave_sdk_server/templates/` + `ui_assets/` — the pick action + binding state
   (the real-render companion).
10. Tests: `tests/server/test_device_bindings.py` **(new)**; extended
    `test_serial_discovery.py`, `test_serial_session.py`, `test_cli_serial_wiring.py`,
    `test_control.py`, `test_presentation_pages.py` (the flip of the two `--device`
    refusal tests is in this set).
11. `README.md` (the serve/discovery/bind section) + the device-developer guide note (row
    3's obligation).

**Gateway repo (`benchweave`):**

12. `.claude/deep-review/2026-10-06-issue385-device-binding-design.md` — this record
    (the branch's first commit).
13. `docs/implementation-planning/11-standalone-web-ui-prd.md` — the amendment row
    (F-385-6).
14. The `packages/sdk` submodule pointer commit — after the SDK PR merges and pushes (row
    7's order).

---

## 10. What this design does not claim

- No hardware behaviour is claimed. The CH343G-class USB-serial fact is unmeasured
  (D-385-3); both outcomes are supported and neither is asserted.
- The binding is routing and operator trust, not a security boundary (§1.3's stated
  residual: identical-class instances with blank/duplicate serials can swap across paths
  undetected; a spoofing adapter can echo a fingerprint).
- The gateway does not resolve connection keys to endpoints after this slice. The
  execution-contract sentence's endpoint axis remains unrealised gateway-side until
  D-385-1 (and #147 deferral 3) fire.
