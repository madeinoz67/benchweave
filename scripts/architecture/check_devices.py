import copy
import hashlib
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from benchweave.measurement.derivation import (
    DerivationRefused,
    DerivationRejected,
    check_derived_variables,
    derive_dataset_variables,
)

"Document/schema conformance checks, not instrument implementation."
DOCS = globals().get("DOCS", Path(__file__).resolve().parents[2] / "docs")
STANDARDS = globals().get("STANDARDS", Path(__file__).resolve().parents[2] / "standards")
OUT = STANDARDS / "otdp/0.2.0"


def load(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


checks = []


def check(name, truth):
    checks.append((name, bool(truth)))


formats = FormatChecker()


@formats.checks("date-time")
def date(value):
    if not isinstance(value, str):
        return True
    if not re.fullmatch(
        "\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?(?:Z|\\+00:00)", value
    ):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


schemas = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in OUT.glob("*.schema.json")}
registry = Registry()
for name, s in schemas.items():
    Draft202012Validator.check_schema(s)
    check(name + " meta-schema", True)
    registry = registry.with_resource(s["$id"], Resource.from_contents(s))
catalog = load("device-profile-catalog.json")
for aid, a in catalog["actions"].items():
    for direction in ("input_schema", "output_schema"):
        s = a[direction]
        Draft202012Validator.check_schema(s)
        check(aid + " " + direction + " meta-schema", True)
        registry = registry.with_resource(s["$id"], Resource.from_contents(s))


def validator(s):
    return Draft202012Validator(s, registry=registry, format_checker=formats)


dv = validator(schemas["otdp-device-descriptor.schema.json"])
rv = validator(schemas["otdp-runtime.schema.json"])
mv = validator(schemas["otdp-measurement.schema.json"])
check(
    "Catalog structure", validator(schemas["device-profile-catalog.schema.json"]).is_valid(catalog)
)
profile_map = {p["id"]: p for p in catalog["profiles"]}
check("Twelve distinct profiles", len(profile_map) == 12)
known_features = {
    "otdp.core/0.1.0",
    "otdp.adapter/0.1.0",
    "otdp.passive_can/0.1.0",
    "otdp.measurement/0.1.0",
    "otdp.profile_actions/0.1.0",
} | set(profile_map)


def class_errors(d):
    errors = []
    if not set(d["required_features"]) <= known_features:
        errors.append("unknown feature")
    if len({c["id"] for c in d.get("channels", [])}) != len(d.get("channels", [])):
        errors.append("duplicate channel")
    declared = set(d.get("actions", {}))
    allowed = set()
    for pid in d.get("profiles", []):
        if pid not in profile_map:
            errors.append("unknown profile")
            continue
        if pid not in d["required_features"]:
            errors.append("missing profile feature")
        p = profile_map[pid]
        allowed.update(p["required_actions"] + p["optional_actions"])
        if not set(p["required_actions"]) <= declared:
            errors.append("missing required action")
    if declared - allowed:
        errors.append("unclaimed action")
    sweep = {"otdp.smu." + v + "/1.0.0" for v in ("configure_sweep", "arm", "fetch", "abort")}
    if declared & sweep and (not sweep <= declared):
        errors.append("incomplete sweep group")
    for aid, a in d.get("actions", {}).items():
        if aid not in catalog["actions"]:
            continue
        if catalog["actions"][aid]["side_effect"] == "state_change" and a["side_effect"] == "none":
            errors.append("downgraded effect")
    return errors


descriptors = {}
for p in sorted((OUT / "examples").glob("*.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    if "otdp_version" not in d:
        continue
    descriptors[p.name] = d
    errors = list(dv.iter_errors(d))
    check(p.name + " descriptor structure", not errors)
    check(p.name + " known required features", set(d["required_features"]) <= known_features)
    if "profiles" in d:
        check(p.name + " class membership/effects", not class_errors(d))
        for c in d["contracts"]:
            path = (OUT / c["path"]).resolve()
            check(
                p.name + " pinned " + c["id"],
                path.is_relative_to(OUT)
                and path.is_file()
                and (hashlib.sha256(path.read_bytes()).hexdigest() == c["sha256"]),
            )
    for entry in d["provenance"]["test_vectors"]:
        check(p.name + " vector file resolves", (p.parent / entry["path"]).is_file())


def dataset_errors(d):
    e = []
    axes = {a["id"]: a for a in d["axes"]}
    if len(axes) != len(d["axes"]):
        e.append("duplicate axis")
    if len({v["id"] for v in d["variables"]}) != len(d["variables"]):
        e.append("duplicate variable")
    for a in d["axes"]:
        c = a["coordinates"]
        if c["kind"] == "explicit" and len(c["values"]) != a["length"]:
            e.append("coordinate count")
        if c["kind"] == "regular" and a["length"] > 1 and (c["step"] == 0):
            e.append("zero axis step")
    for v in d["variables"]:
        if any(dim not in axes for dim in v["dimensions"]):
            e.append("unknown dimension")
            continue
        count = math.prod(axes[dim]["length"] for dim in v["dimensions"])
        if "values" in v:
            if len(v["values"]) != count:
                e.append("element count")
            if v["status"] == "valid" and any(x is None for x in v["values"]):
                e.append("unmarked null")
            if v["dtype"] in ("int64", "uint64"):
                for x in v["values"]:
                    if x is None:
                        continue
                    n = int(x)
                    low = -(2**63) if v["dtype"] == "int64" else 0
                    high = 2**63 - 1 if v["dtype"] == "int64" else 2**64 - 1
                    if not low <= n <= high or x == "-0":
                        e.append("integer bounds")
        else:
            widths = {
                "f64le": 8,
                "i64le": 8,
                "u64le": 8,
                "u8": 1,
                "bool_u8": 1,
                "logic_u8": 1,
                "complex_f64le": 16,
            }
            a = v["artifact"]
            if a["encoding"] in widths and a["byte_length"] != count * widths[a["encoding"]]:
                e.append("artifact size")
        if v["unit"] in ("dB", "dBm") and "log_reference" not in v:
            e.append("missing log reference")
        if v["uncertainty"]["status"] != "known" and "absolute" in v["uncertainty"]:
            e.append("unknown uncertainty value")
    if d["kind"] == "network_parameters":
        if not any(a["quantity"] == "frequency" for a in d["axes"]):
            e.append("frequency axis")
        for v in d["variables"]:
            if v["dtype"] != "complex128" or "port_pair" not in v:
                e.append("network parameters meaning")
    return e


census = load("examples/derivation-vectors.json")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def census_row_ok(row):
    derived = row.get("derived")
    if derived is None:
        derived = [
            {
                "id": "probe0",
                "quantity": "probe",
                "unit": "1",
                "expression": row["expression"],
            }
        ]
    if row["expect"] == "refused":
        try:
            derive_dataset_variables(copy.deepcopy(row["dataset"]), derived)
        except DerivationRefused as error:
            return str(error).startswith(row["reason_prefix"])
        return False
    if row["expect"] == "reject":
        try:
            check_derived_variables(derived)
        except DerivationRejected as error:
            return str(error).startswith(row["reason_prefix"])
        return False
    if row["expect"] == "accept":
        try:
            check_derived_variables(derived)
            return True
        except DerivationRejected:
            return False
    output = derive_dataset_variables(copy.deepcopy(row["dataset"]), derived)
    appended = output["variables"][len(row["dataset"]["variables"]) :]
    return [canonical(v) for v in appended] == [canonical(v) for v in row["expected"]]


for row in census["grammar"] + census["static"] + census["evaluation"]:
    check(row["id"] + " derivation census", census_row_ok(row))
check(
    "derivation census meets the minimum row counts",
    len(census["grammar"]) >= 30
    and sum(1 for r in census["grammar"] if r["expect"] == "accept") >= 15
    and sum(1 for r in census["grammar"] if r["expect"] == "reject") >= 15
    and len(census["evaluation"]) >= 12,
)
for name, descriptor in sorted(descriptors.items()):
    if "derived_variables" in descriptor:
        try:
            check_derived_variables(descriptor["derived_variables"])
            check(name + " derived declarations", True)
        except DerivationRejected as error:
            check(name + " derived declarations: " + str(error), False)


data = load("examples/measurement-vectors.json")["datasets"]
for name, d in data.items():
    errors = list(mv.iter_errors(d))
    check(name + " measurement structure", not errors)
    check(name + " shape/selected metrology rules", not dataset_errors(d))
for name, d in data.items():
    recorded = [v for v in d["variables"] if "derivation" in v]
    if not recorded:
        continue
    # Replay through the public API: strip the derived variables, re-derive
    # them from the recorded markers, and require the exact recorded
    # variables back — the corpus example IS what the evaluator produces.
    operands_only = copy.deepcopy(d)
    operands_only["variables"] = [
        v for v in operands_only["variables"] if "derivation" not in v
    ]
    declarations = [
        {
            "id": v["id"],
            "quantity": v["quantity"],
            "unit": v["unit"],
            "expression": v["derivation"]["expression"],
        }
        for v in recorded
    ]
    try:
        replayed = derive_dataset_variables(operands_only, declarations)
        appended = replayed["variables"][len(operands_only["variables"]) :]
        check(
            name + " derived example replays exactly",
            [canonical(v) for v in appended] == [canonical(v) for v in recorded],
        )
    except (DerivationRefused, DerivationRejected) as error:
        check(name + " derived example replays: " + str(error), False)


vectors = load("examples/class-action-vectors.json")["vectors"]
covered = set()
for v in vectors:
    req = v["request"]
    res = v["result"]
    aid = req["arguments"]["action_id"]
    covered.add(aid)
    contract = catalog["actions"][aid]
    check(v["id"] + " request envelope", rv.is_valid(req))
    check(v["id"] + " result envelope", rv.is_valid(res))
    ins = validator(contract["input_schema"])
    outs = validator(contract["output_schema"])
    check(v["id"] + " action input", ins.is_valid(req["arguments"]["input"]))
    check(v["id"] + " action output", outs.is_valid(res["data"]["result"]))
    check(
        v["id"] + " correlated identity",
        req["operation_id"] == res["operation_id"] and aid == res["data"]["action_id"],
    )
check(
    "Every standard action has a positive contract vector",
    covered == set(catalog["actions"]) and len(covered) == 50,
)
base = descriptors["class-dc_psu.json"]
d = copy.deepcopy(base)
d["actions"].pop("otdp.dc_psu.output/1.0.0")
check("Reject missing base action semantically", "missing required action" in class_errors(d))
d = copy.deepcopy(base)
d["profiles"] = ["vendor.unknown/1.0.0"]
check("Reject unknown required profile", "unknown profile" in class_errors(d))
d = copy.deepcopy(base)
d["required_features"].append("vendor.unknown/1.0.0")
check("Reject unknown feature despite valid syntax", "unknown feature" in class_errors(d))
d = copy.deepcopy(base)
d["actions"]["otdp.dc_psu.output/1.0.0"]["side_effect"] = "none"
check("Reject downgraded source action", "downgraded effect" in class_errors(d))
d = copy.deepcopy(base)
d["required_features"].remove("otdp.profile_actions/0.1.0")
check("Reject absent action feature structurally", not dv.is_valid(d))
d = copy.deepcopy(base)
d["required_features"].remove("otdp.dc_psu/1.0.0")
check("Reject absent profile feature semantically", "missing profile feature" in class_errors(d))
d = copy.deepcopy(descriptors["class-smu.json"])
d["actions"].pop("otdp.smu.abort/1.0.0")
check("Reject incomplete optional sweep group", "incomplete sweep group" in class_errors(d))
d = copy.deepcopy(base)
d["channels"].append(copy.deepcopy(d["channels"][0]))
check("Reject duplicate channel", "duplicate channel" in class_errors(d))
for cls in ("dc_psu", "electronic_load", "smu", "function_generator"):
    v = validator(catalog["actions"][f"otdp.{cls}.output/1.0.0"]["input_schema"])
    check(cls + " enable requires config", not v.is_valid({"channel": "ch1", "enabled": True}))
    check(cls + " disable permits absent config", v.is_valid({"channel": "ch1", "enabled": False}))
d = copy.deepcopy(data["oscilloscope"])
d["variables"][0]["values"].pop()
check("Reject shape mismatch", "element count" in dataset_errors(d))
d = copy.deepcopy(data["oscilloscope"])
d["variables"][0]["dimensions"] = ["missing"]
check("Reject unknown dimension", "unknown dimension" in dataset_errors(d))
d = copy.deepcopy(data["oscilloscope"])
d["variables"][0]["values"][0] = None
check("Reject null hidden as valid", "unmarked null" in dataset_errors(d))
d = copy.deepcopy(data["spectrum_analyser"])
d["variables"][0].pop("log_reference")
check("Reject missing logarithmic reference", "missing log reference" in dataset_errors(d))
d = copy.deepcopy(data["vna"])
d["variables"][0].pop("port_pair")
check("Reject missing VNA port pair", "network parameters meaning" in dataset_errors(d))
d = copy.deepcopy(data["vna"])
d["variables"][0]["values"][0] = [1, 2, 3]
check("Reject malformed complex element", not mv.is_valid(d))
d = copy.deepcopy(data["logic_analyser"])
d["variables"][0]["values"][0] = "true"
check("Reject unknown logic token", not mv.is_valid(d))
d = copy.deepcopy(data["dmm"])
d["variables"][0]["uncertainty"] = {"status": "known"}
check("Reject known uncertainty without value", not mv.is_valid(d))
source_input = validator(catalog["actions"]["otdp.dc_psu.configure/1.0.0"]["input_schema"])
inp = {
    "configuration_id": "cfg-1",
    "channel": "ch1",
    "voltage_v": 3.3,
    "current_limit_a": 0.5,
    "ovp_v": 3.6,
    "ocp_a": 0.6,
    "raw_command": "OUTP ON",
}
check("Reject arbitrary command field", not source_input.is_valid(inp))
scope = validator(catalog["actions"]["otdp.oscilloscope.configure/1.0.0"]["input_schema"])
inp = copy.deepcopy(
    next(v["request"]["arguments"]["input"] for v in vectors if v["id"] == "oscilloscope-configure")
)
inp["trigger"] = {"kind": "edge"}
check("Reject incomplete edge trigger", not scope.is_valid(inp))
fg = validator(catalog["actions"]["otdp.function_generator.configure/1.0.0"]["input_schema"])
inp = copy.deepcopy(
    next(
        v["request"]["arguments"]["input"]
        for v in vectors
        if v["id"] == "function_generator-configure"
    )
)
inp["function"] = "arbitrary"
check("Reject arbitrary waveform without asset", not fg.is_valid(inp))
fg_constraints = {"properties": {"frequency_hz": {"maximum": 100}}}
inp["function"] = "sine"
check(
    "Device constraints narrow standard contract",
    fg.is_valid(inp) and (not validator(fg_constraints).is_valid(inp)),
)
CHECKS = checks

GENERATED_MARKER = (
    "<!-- Generated by scripts/architecture/check_devices.py --write-report — regenerate "
    "on check changes; do not hand-edit. -->"
)
REPORT_TITLE = "# OTDP 0.2.0 specification verification"
REPORT_COVERAGE = (
    "Twelve class profiles and fifty input/output action contracts were checked against "
    "Draft 2020-12. Each action has a positive vector. Descriptor declarations, pinned "
    "contract hashes, runtime envelopes, typed datasets and selected rejection/semantic "
    "boundaries were checked."
)
REPORT_LIMIT = (
    "**Limit:** These are document/schema checks. No gateway, plugin, device simulator, "
    "hardware interaction or complete C01–C12/M01–M14 behavioural validator is claimed. "
    "Structural reference descriptors intentionally do not contain real manufacturer "
    "evidence or commissioned electrical limits."
)


def render_report(checks: list[tuple[str, bool]]) -> str:
    """Render the validation report markdown from a devices-suite check list.

    Pure and order-canonical: the ``## Checks`` list is emitted sorted by name
    because the suite's accumulation order is partly glob order
    (directory-entry order), which is not portable across platforms. The
    rendered bytes are a function of the check set only.
    """
    passed = sum(1 for _, ok in checks if ok)
    lines = [
        GENERATED_MARKER,
        "",
        REPORT_TITLE,
        "",
        f"**Result: {passed}/{len(checks)} checks passed; {len(checks) - passed} failed.**",
        "",
        REPORT_COVERAGE,
        "",
        REPORT_LIMIT,
        "",
        "## Checks",
        "",
    ]
    lines.extend(f"- {'PASS' if ok else 'FAIL'}: {name}" for name, ok in sorted(checks))
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    failures = [name for name, ok in CHECKS if not ok]
    for failure in failures:
        print("FAIL:", failure)
    print(f"{len(CHECKS) - len(failures)}/{len(CHECKS)} checks passed")
    if "--write-report" in sys.argv[1:]:
        if failures:
            print(f"refusing to write the validation report: {len(failures)} failing check(s)")
            raise SystemExit(1)
        (OUT / "validation-report.md").write_text(
            render_report([(str(name), bool(ok)) for name, ok in CHECKS]),
            encoding="utf-8",
            newline="\n",
        )
        print(f"wrote {OUT / 'validation-report.md'}")
    raise SystemExit(bool(failures))
