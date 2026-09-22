"""Composing capture services over the staged writer (issue #43 slice 1).

Slice-1 scaffold (RED collection stub): the module lands before its first
behaviour commit so the capture-services tests collect against a parent
commit that has no implementation yet. The implemented surface, landing in
this slice:

- ``ScopedServicesBundle`` / ``CaptureServicesBundle`` — the SDK §8 shapes
  per session: injected clocks read FRESH per call (never a
  construction-frozen ``now`` — the RetainingServices anti-pattern),
  evidence under the host-minted context key, artifacts through the staged
  writer, transport delegated to an injected provider or refused loudly.
  Constructed without ``artifact_writer`` permission the bundle omits the
  three capture attributes entirely (structural absence, not a runtime
  flag).
- ``CaptureController`` — the bridge-held facade over the writer: open,
  the published record for G4 cross-checks, and the contained abort
  epilogue whose forensic record copies retain_evidence's proven,
  served, contract-legal mold (put_artifact the JSON payload, then
  put_evidence kind ``event_log`` with the doc-ref and ``quota=None``).
- ``build_capture_services`` — the permission gate's construction point.
"""
