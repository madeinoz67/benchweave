import base64
import copy
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

DOCS = globals().get("DOCS", Path(__file__).resolve().parents[2] / "docs")
STANDARDS = globals().get("STANDARDS", Path(__file__).resolve().parents[2] / "standards")
# runpy.run_path does not put the script's directory on sys.path (measured:
# the sibling import fails there), so the shared report writer needs the
# bootstrap. __file__ is set in both execution modes (direct python and
# runpy.run_path with init_globals).
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import _validation_report  # noqa: E402

INTERFACE_VERSION = _validation_report.active_standard_version(STANDARDS, "interface")
# Manifest-derived, resolved once (#102 D2 generalized; the #119 lesson).
CONTRACT_DIR = (STANDARDS / "interface" / INTERFACE_VERSION).resolve()
schema = json.loads((CONTRACT_DIR / "interface.schema.json").read_text(encoding="utf-8"))
catalog = json.loads((CONTRACT_DIR / "operation-catalog.json").read_text(encoding="utf-8"))
api = json.loads((CONTRACT_DIR / "openapi.json").read_text(encoding="utf-8"))
tools = json.loads((CONTRACT_DIR / "mcp-tools.json").read_text(encoding="utf-8"))["tools"]
D = schema["$defs"]
results = []


def check(n, b):
    results.append((n, bool(b)))


f = FormatChecker()


@f.checks("date-time")
def date(v):
    try:
        return (
            isinstance(v, str)
            and v.endswith("Z")
            and bool(datetime.fromisoformat(v.replace("Z", "+00:00")))
        )
    except ValueError:
        return False


Draft202012Validator.check_schema(schema)
check("shared Draft 2020-12 schema", True)


def v(name):
    return Draft202012Validator({"$ref": "#/$defs/" + name, "$defs": D}, format_checker=f)


def specimen(s):
    if "$ref" in s:
        return specimen(D[s["$ref"].split("/")[-1]])
    if "const" in s:
        return s["const"]
    if "enum" in s:
        return s["enum"][0]
    if "oneOf" in s:
        return specimen(s["oneOf"][0])
    if "anyOf" in s:
        return None
    t = s.get("type")
    if t == "object":
        return {k: specimen(val) for k, val in s.get("properties", {}).items()}
    if t == "array":
        return []
    if t == "boolean":
        return False
    if t == "integer":
        return max(1, s.get("minimum", 0))
    if t == "string":
        if s.get("format") == "date-time":
            return "2026-09-09T00:00:00Z"
        if "64" in s.get("pattern", ""):
            return "0" * 64
        if s.get("pattern") == "^(0|[1-9][0-9]*)$":
            return "1"
        return "synthetic"
    if t == "null":
        return None
    raise ValueError(s)


vec = []
maptools = {t["name"]: t for t in tools}
for o in catalog["operations"]:
    name = o["name"]
    req = specimen(o["input_schema"])
    out = specimen(o["output_schema"])
    data = out["data"]
    if name == "artifact_read":
        req.update(offset=0, length=1)
        data.update(offset=0, bytes=1, total_bytes=1, base64="AA==", eof=True)
    if name == "document_get":
        data.update(content={}, original_utf8_base64="e30=")
        data["document"]["sha256"] = hashlib.sha256(b"{}").hexdigest()
        req["sha256"] = data["document"]["sha256"]
    if name == "run_check":
        data["valid"] = True
    if name == "run_start":
        req["lease_id"] = None
    check(name + " positive input", v(name + "_input").is_valid(req))
    check(name + " positive output", v(name + "_output").is_valid(out))
    for field in o["input_schema"]["required"]:
        x = copy.deepcopy(req)
        del x[field]
        check(name + " requires " + field, not v(name + "_input").is_valid(x))
    x = copy.deepcopy(req)
    x["principal_id"] = "spoof"
    check(name + " rejects principal body injection", not v(name + "_input").is_valid(x))
    p = api["paths"][o["path"]][o["method"]]
    check(
        name + " OpenAPI mapping",
        p["operationId"] == name
        and p["x-stg-permission"] == o["permission"]
        and (str(o["success_status"]) in p["responses"]),
    )
    if o["mcp_tool"]:
        t = maptools[o["mcp_tool"]]
        for k in ("inputSchema", "outputSchema"):
            Draft202012Validator.check_schema(t[k])
            check(name + " " + k + " meta-schema", True)
        check(
            name + " MCP/REST input parity",
            {k: val for k, val in t["inputSchema"].items() if k != "$defs"} == o["input_schema"],
        )
        check(
            name + " MCP/REST output parity",
            {k: val for k, val in t["outputSchema"].items() if k != "$defs"} == o["output_schema"],
        )
    vec.append({"operation": name, "input": req, "output": out})
# The prose's count and this pin read the same lens — the set cardinality,
# not the per-operation vector list (equal today because each operation
# appears once; a duplicate catalog entry would diverge them).
unique_operations = len({o["name"] for o in catalog["operations"]})
check("20 unique REST operations", unique_operations == 20)
check("17 unique MCP tools", len(maptools) == 17)
check(
    "administration absent from MCP",
    all(o["mcp_tool"] is None for o in catalog["operations"] if o["permission"] == "admin"),
)
for code, status in catalog["error_http_status"].items():
    error = {
        "ok": False,
        "error": {
            "code": code,
            "message": "Synthetic rejection",
            "correlation_id": "synthetic",
            "retry": "never",
            "details": {
                "findings": [],
                "current_revision": None,
                "stream_id": None,
                "oldest_sequence": None,
                "current_sequence": None,
                "retry_after_ms": None,
            },
        },
    }
    check("error " + code + " structure", v("failure").is_valid(error))
    check(
        "error " + code + " OpenAPI status",
        all(
            str(status) in api["paths"][o["path"]][o["method"]]["responses"]
            for o in catalog["operations"]
        ),
    )
run = next(x["output"] for x in vec if x["operation"] == "run_start")
x = copy.deepcopy(run)
x["data"]["outcome"] = "passed"
check("nonterminal cannot claim pass", not v("run_start_output").is_valid(x))
x = copy.deepcopy(run)
x["data"].update(
    state="terminal", outcome="passed", safe_state="unknown", terminal_record=specimen(D["ref"])
)
check("terminal pass needs verified safety", not v("run_get_output").is_valid(x))
x = copy.deepcopy(run)
x["data"].update(state="terminal")
check("terminal requires outcome and record", not v("run_get_output").is_valid(x))
req = next(x["input"] for x in vec if x["operation"] == "artifact_read")
for field, val in [("offset", -1), ("length", 0), ("length", 65537), ("offset", 9007199254740992)]:
    x = copy.deepcopy(req)
    x[field] = val
    check(
        "reject invalid chunk " + field + " " + str(val), not v("artifact_read_input").is_valid(x)
    )
x = next(copy.deepcopy(x["input"]) for x in vec if x["operation"] == "change_apply")
x["approved"] = True
check("no self-approval Boolean", not v("change_apply_input").is_valid(x))


def walk(x):
    if isinstance(x, dict):
        if "$ref" in x:
            yield x["$ref"]
        for val in x.values():
            yield from walk(val)
    if isinstance(x, list):
        for val in x:
            yield from walk(val)


for ref in sorted(set(walk(api))):
    check(
        "local OpenAPI reference " + ref,
        ref.startswith("interface.schema.json#/$defs/") and ref.split("/")[-1] in D,
    )
check(
    # Root-relative, not str(CONTRACT_DIR / ...): an absolute path here would
    # bake the host's checkout location into the pinned report bytes (the
    # portability guard in test_architecture.py pins this).
    f"Stored fixture agrees: interface/{INTERFACE_VERSION}"
    "/examples/operation-vectors.json",
    json.loads((CONTRACT_DIR / "examples/operation-vectors.json").read_text(encoding="utf-8"))
    == json.loads(
        json.dumps(
            {
                "notice": (
                    "Synthetic schema vectors; not authenticated calls or executed operations. "
                    "Digests/IDs are illustrative only."
                ),
                "vectors": vec,
            },
            indent=2,
        )
        + "\n"
    ),
)
start = next(x for x in vec if x["operation"] == "run_start")
wire = {
    "notice": "Synthetic wire shape, not an executed start.",
    "headers": {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2026-07-28",
        "Mcp-Method": "tools/call",
        "Mcp-Name": "stg_v1_run_start",
    },
    "request": {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "stg_v1_run_start",
            "arguments": start["input"],
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                "io.modelcontextprotocol/clientInfo": {
                    "name": "synthetic-client",
                    "version": "0.1.0",
                },
                "io.modelcontextprotocol/clientCapabilities": {},
            },
        },
    },
    "response": {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "resultType": "complete",
            "isError": False,
            "structuredContent": start["output"],
            "content": [{"type": "text", "text": json.dumps(start["output"])}],
        },
    },
}
check(
    "MCP matching protocol metadata",
    wire["headers"]["MCP-Protocol-Version"]
    == wire["request"]["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"],
)
check(
    "MCP structured/text result agreement",
    json.loads(wire["response"]["result"]["content"][0]["text"])
    == wire["response"]["result"]["structuredContent"],
)
check(
    f"Stored fixture agrees: interface/{INTERFACE_VERSION}"
    "/examples/mcp-start-exchange.json",
    json.loads((CONTRACT_DIR / "examples/mcp-start-exchange.json").read_text(encoding="utf-8"))
    == json.loads(json.dumps(wire, indent=2) + "\n"),
)
x = copy.deepcopy(run)
x["data"].update(
    state="terminal", outcome="outcome_unknown", safe_state="verified", terminal_record=None
)
check("storage gap can report terminal uncertainty", v("run_get_output").is_valid(x))
x["data"]["outcome"] = "passed"
check("storage gap cannot report pass", not v("run_get_output").is_valid(x))
x["data"]["outcome"] = "assertion_failed"
check("absent record cannot imply complete evidence", not v("run_get_output").is_valid(x))
doc = next(x["output"]["data"] for x in vec if x["operation"] == "document_get")
raw = base64.b64decode(doc["original_utf8_base64"], validate=True)
check("document exact bytes digest", hashlib.sha256(raw).hexdigest() == doc["document"]["sha256"])
check("document parsed and original bytes agree", json.loads(raw) == doc["content"])
check(
    "altered document bytes fail digest",
    hashlib.sha256(raw + b" ").hexdigest() != doc["document"]["sha256"],
)
CHECKS = results

GENERATED_MARKER = _validation_report.marker("scripts/architecture/check_interface.py")
REPORT_TITLE = "# Interface contract verification"
REPORT_COVERAGE = (
    f"Checked shared/tool JSON Schemas, {unique_operations} synthetic operation vectors, "
    "required "
    "fields, REST/MCP mapping equality, local OpenAPI references, error mappings and "
    "selected lifecycle/chunk rejections. The OpenAPI mapping was checked structurally "
    "against the catalog; no full OpenAPI meta-validator or live protocol suite was run."
)
REPORT_LIMIT = (
    "No HTTP server, OAuth provider, MCP client, physical command, request store or event "
    "replay was executed. The MCP example illustrates pinned 2026-07-28 wire fields; "
    "interoperability and I01–I12 remain implementation acceptance obligations."
)


def render_report(checks: list[tuple[str, bool]]) -> str:
    """Render the validation report markdown from an interface-suite check list.

    Pure and order-canonical (sorted ``## Checks``, a function of the check
    set only); the shared template lives in ``_validation_report.render``.
    """
    return _validation_report.render(
        [(str(name), bool(ok)) for name, ok in checks],
        marker=GENERATED_MARKER,
        title=REPORT_TITLE,
        coverage=REPORT_COVERAGE,
        limit=REPORT_LIMIT,
    )


if __name__ == "__main__":
    _validation_report.main(
        CHECKS,
        CONTRACT_DIR / "validation-report.md",
        script="scripts/architecture/check_interface.py",
        title=REPORT_TITLE,
        coverage=REPORT_COVERAGE,
        limit=REPORT_LIMIT,
    )
