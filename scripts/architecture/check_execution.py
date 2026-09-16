import copy
import hashlib
import json
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

"Document-contract review checks; not a production interpreter or admission service."
DOCS = globals().get("DOCS", Path(__file__).resolve().parents[2] / "docs")
STANDARDS = globals().get("STANDARDS", Path(__file__).resolve().parents[2] / "standards")
CONTRACT_DIR = STANDARDS / "execution/0.1.0"
E = CONTRACT_DIR / "examples"
results = []


def check(name, value):
    results.append((name, bool(value)))


fc = FormatChecker()


@fc.checks("date-time")
def dt(v):
    try:
        return (
            isinstance(v, str)
            and v.endswith("Z")
            and bool(datetime.fromisoformat(v.replace("Z", "+00:00")))
        )
    except ValueError:
        return False


schemas = {}
ex = {}
validators = {}
for name in ("procedure", "bench", "safety-policy", "commissioning", "run-binding", "run-record"):
    s = json.loads((CONTRACT_DIR / (name + ".schema.json")).read_text(encoding="utf-8"))
    schemas[name] = s
    Draft202012Validator.check_schema(s)
    check(name + " meta-schema", True)
    v = Draft202012Validator(s, format_checker=fc)
    validators[name] = v
    x = json.loads((E / (name + ".json")).read_text(encoding="utf-8"))
    ex[name] = x
    errors = list(v.iter_errors(x))
    check(name + " positive fixture", not errors)
    for k in s["required"]:
        n = copy.deepcopy(x)
        del n[k]
        check(name + " requires " + k, not v.is_valid(n))
    n = copy.deepcopy(x)
    n["unrecognised"] = True
    check(name + " rejects unknown field", not v.is_valid(n))


def refs(value):
    if isinstance(value, list):
        for x in value:
            yield from refs(x)
    elif isinstance(value, dict):
        if "$stg_ref" in value:
            yield value["$stg_ref"]["step"]
        else:
            for x in value.values():
                yield from refs(x)


def proc_errors(p):
    errors = []
    allids = set()
    roles = {r["id"]: r for r in p["roles"]}
    if len(roles) != len(p["roles"]):
        errors.append("duplicate role")

    def block(steps, parents):
        visible = dict(parents)
        bound = 0
        for s in steps:
            if s["id"] in allids:
                errors.append("duplicate step")
            allids.add(s["id"])
            kind = s["kind"]
            if "role" in s and s["role"] not in roles:
                errors.append("unknown role")
            for r in refs(s.get("input", s.get("value", {}))):
                if r not in visible:
                    errors.append("reference scope")
            if kind == "sample" and (
                s["source_step"] not in visible or visible[s["source_step"]] != "invoke"
            ):
                errors.append("sample source")
            if kind in ("if", "assert"):
                pred = s["predicate"]
                if pred["sample"] not in visible or visible[pred["sample"]] != "sample":
                    errors.append("predicate scope")
                if pred["minimum"] > pred["maximum"]:
                    errors.append("bounds order")
            if kind == "repeat":
                bound += s["count"] * block(s["steps"], visible)
            elif kind == "if":
                bound += max(block(s["then"], visible), block(s["else"], visible))
            else:
                bound += s.get("timeout_ms", s.get("duration_ms", 0))
            visible[s["id"]] = kind
        return bound

    bound = block(p["steps"], {})
    if bound > p["max_body_ms"]:
        errors.append("body bound")
    return (errors, bound)


p = ex["procedure"]
check("procedure lexical scope and bound", not proc_errors(p)[0])
check("synthetic static wait/IO bound 1600 ms", proc_errors(p)[1] == 1600)
x = copy.deepcopy(p)
x["steps"][1]["input"]["configuration_id"]["$stg_ref"]["step"] = "later"
check("future reference rejected", "reference scope" in proc_errors(x)[0])
x = copy.deepcopy(p)
x["steps"][1]["id"] = "configure"
check("duplicate step rejected", "duplicate step" in proc_errors(x)[0])
x = copy.deepcopy(p)
x["steps"][-1]["predicate"]["minimum"] = 10
check("inverted assertion rejected", "bounds order" in proc_errors(x)[0])
x = copy.deepcopy(p)
x["max_body_ms"] = 1000
check("body bound rejected", "body bound" in proc_errors(x)[0])
x = copy.deepcopy(p)
x["steps"][0]["role"] = "missing"
check("unknown role rejected", "unknown role" in proc_errors(x)[0])
x = copy.deepcopy(p)
x["steps"] = [{"id": "outer", "kind": "repeat", "count": 2, "steps": copy.deepcopy(p["steps"])}]
check(
    "bounded repeated fixture",
    validators["procedure"].is_valid(x) and (not proc_errors(x)[0]) and (proc_errors(x)[1] == 3200),
)
x["steps"].append(
    {
        "id": "outside",
        "kind": "sample",
        "source_step": "measure",
        "variable_id": "voltage",
        "unit": "V",
        "max_age_ms": 500,
        "require_known_uncertainty": False,
    }
)
check("loop result cannot escape", "sample source" in proc_errors(x)[0])
x = copy.deepcopy(p)
x["steps"].append(
    {
        "id": "decision",
        "kind": "if",
        "predicate": {"sample": "voltage", "minimum": 0, "maximum": 6},
        "then": [{"id": "then-wait", "kind": "delay", "duration_ms": 10}],
        "else": [{"id": "else-wait", "kind": "delay", "duration_ms": 20}],
    }
)
check(
    "both branches admitted with max bound",
    validators["procedure"].is_valid(x) and (not proc_errors(x)[0]) and (proc_errors(x)[1] == 1620),
)
for _key, bad in [("count", 0), ("count", -1)]:
    x = copy.deepcopy(p)
    x["steps"] = [
        {
            "id": "loop",
            "kind": "repeat",
            "count": bad,
            "steps": [{"id": "wait", "kind": "delay", "duration_ms": 1}],
        }
    ]
    check("invalid repeat " + str(bad), not validators["procedure"].is_valid(x))
x = copy.deepcopy(p)
x["steps"][0]["input"]["voltage_v"] = {"$stg_eval": "arbitrary code"}
check("unknown directive rejected", not validators["procedure"].is_valid(x))
x = copy.deepcopy(p)
x["steps"][0]["input"]["configuration_id"]["extra"] = True
check("mixed reserved reference rejected", not validators["procedure"].is_valid(x))
x = copy.deepcopy(p)
x["steps"][1]["input"]["configuration_id"]["$stg_ref"]["pointer"] = "/invalid~3"
check("invalid JSON pointer escape rejected", not validators["procedure"].is_valid(x))


def bench_errors(b, policy):
    e = []
    dev = {d["id"]: d for d in b["devices"]}
    resources = {r["id"]: r for r in b["resources"]}
    terms = {t["id"]: t for t in b["terminals"]}
    signals = {s["id"]: s for s in b["signals"]}
    domains = {d["id"] for d in policy["domains"]}
    for seq in ("devices", "resources", "terminals", "nets", "signals", "protection_mechanisms"):
        if len({v["id"] for v in b[seq]}) != len(b[seq]):
            e.append("duplicate " + seq)

    def visit(r, path):
        if r not in resources:
            e.append("unknown resource")
            return
        if r in path:
            e.append("resource cycle")
            return
        for child in resources[r]["depends_on"]:
            visit(child, path | {r})

    for r in resources:
        visit(r, set())
        if any(d not in dev for d in resources[r]["device_ids"]):
            e.append("unknown resource device")
    if set(dev) - {d for r in resources.values() for d in r["device_ids"]}:
        e.append("unowned device")
    used = set()
    for net in b["nets"]:
        for t in net["terminal_ids"]:
            if t not in terms:
                e.append("unknown terminal")
            if t in used:
                e.append("multiple nets")
            used.add(t)
    for t in terms.values():
        if t["domain_id"] not in domains:
            e.append("unknown domain")
        if t["owner_kind"] == "device" and (
            t["owner_id"] not in dev or t["channel_id"] not in dev[t["owner_id"]]["channels"]
        ):
            e.append("unknown device channel")
        if t["owner_kind"] == "dut" and t["owner_id"] not in b["dut_ids"]:
            e.append("unknown DUT")
    for s in signals.values():
        if s["resource_id"] not in resources:
            e.append("unknown signal resource")
        if s["poll_ms"] > s["max_age_ms"]:
            e.append("poll exceeds freshness")
    for m in b["protection_mechanisms"]:
        if m["resource_id"] not in resources:
            e.append("unknown protection resource")
    if set(policy["independent_protection"]["mechanism_ids"]) - {
        m["id"] for m in b["protection_mechanisms"]
    }:
        e.append("unknown protection mechanism")
    for c in policy["continuous_conditions"] + policy["safe_transition"]["verify"]:
        for name in c.get("signals", [c.get("signal")]):
            if name not in signals:
                e.append("unknown condition signal")
        if c["kind"] == "numeric":
            if c["minimum"] > c["maximum"]:
                e.append("condition bounds")
            if c["signal"] in signals and c["unit"] != signals[c["signal"]]["unit"]:
                e.append("condition unit")
    for a in policy["safe_transition"]["actions"] + policy["allow_rules"]:
        if a["device_id"] not in dev:
            e.append("unknown policy device")
    transition = policy["safe_transition"]
    if (
        sum(a["timeout_ms"] for a in transition["actions"]) + transition["stable_for_ms"]
        > transition["max_duration_ms"]
    ):
        e.append("protection bound")
    return e


b = ex["bench"]
policy = ex["safety-policy"]
check("bench/policy reference semantics", not bench_errors(b, policy))
for label, edit, reason in [
    ("net endpoint", lambda x: x["nets"][0]["terminal_ids"].append("missing"), "unknown terminal"),
    (
        "double wiring",
        lambda x: x["nets"][1]["terminal_ids"].append("psu-positive"),
        "multiple nets",
    ),
    (
        "resource cycle",
        lambda x: x["resources"][1]["depends_on"].append("supply-resource"),
        "resource cycle",
    ),
    ("stale polling", lambda x: x["signals"][0].update(poll_ms=100), "poll exceeds freshness"),
    (
        "wrong channel",
        lambda x: x["terminals"][0].update(channel_id="absent"),
        "unknown device channel",
    ),
    ("missing DUT", lambda x: x["terminals"][1].update(owner_id="absent"), "unknown DUT"),
    (
        "unknown signal resource",
        lambda x: x["signals"][0].update(resource_id="absent"),
        "unknown signal resource",
    ),
]:
    x = copy.deepcopy(b)
    edit(x)
    check(label + " rejected", reason in bench_errors(x, policy))
x = copy.deepcopy(policy)
x["safe_transition"]["max_duration_ms"] = 100
check("insufficient protection budget", "protection bound" in bench_errors(b, x))
x = copy.deepcopy(policy)
x["continuous_conditions"][1]["unit"] = "A"
check("monitor unit mismatch", "condition unit" in bench_errors(b, x))
catalog = json.loads(
    (STANDARDS / "otdp/0.1.0/device-profile-catalog.json").read_text(encoding="utf-8")
)


def substitute(v):
    if isinstance(v, list):
        return [substitute(x) for x in v]
    if isinstance(v, dict):
        if "$stg_channel" in v:
            return "ch1"
        if "$stg_issue" in v:
            return "synthetic-issued-id"
        if "$stg_ref" in v:
            return "synthetic-issued-id"
        return {k: substitute(x) for k, x in v.items()}
    return v


for s in p["steps"]:
    if s["kind"] == "invoke":
        check(
            s["id"] + " resolved action input",
            Draft202012Validator(catalog["actions"][s["action_id"]]["input_schema"]).is_valid(
                substitute(s["input"])
            ),
        )
for a in policy["safe_transition"]["actions"]:
    check(
        a["id"] + " protective input",
        Draft202012Validator(catalog["actions"][a["action_id"]]["input_schema"]).is_valid(
            a["input"]
        ),
    )
for a in policy["allow_rules"]:
    Draft202012Validator.check_schema(a["input_constraints"])
    check("allow rule " + a["action_id"] + " meta-schema", True)
check(
    "body plus protection fits domain duration",
    all(
        p["max_body_ms"] + policy["safe_transition"]["max_duration_ms"] <= d["max_energised_ms"]
        for d in policy["domains"]
    ),
)
check(
    "procedure allows required protection budget",
    p["max_protection_ms"] >= policy["safe_transition"]["max_duration_ms"],
)
for doc, fields in [
    ("bench", {"policy": "safety-policy"}),
    ("commissioning", {"bench": "bench", "policy": "safety-policy"}),
    (
        "run-binding",
        {
            "procedure": "procedure",
            "bench": "bench",
            "policy": "safety-policy",
            "commissioning": "commissioning",
        },
    ),
    ("run-record", {"binding": "run-binding"}),
]:
    for field, file in fields.items():
        check(
            doc + " pins " + field,
            ex[doc][field]["sha256"]
            == hashlib.sha256((E / (file + ".json")).read_bytes()).hexdigest(),
        )
check(
    "commissioning pins procedure",
    ex["commissioning"]["procedure_refs"][0]["sha256"]
    == hashlib.sha256((E / "procedure.json").read_bytes()).hexdigest(),
)
check(
    "consistent package lock across admission",
    len({ex[k]["package_lock"]["sha256"] for k in ("bench", "commissioning", "run-binding")}) == 1,
)
x = copy.deepcopy(ex["run-record"])
x["safe_state"] = "unknown"
check("pass cannot hide unknown safety", not validators["run-record"].is_valid(x))
x = copy.deepcopy(ex["run-record"])
x["body_outcome"] = "assertion_failed"
check("pass cannot hide failed assertion", not validators["run-record"].is_valid(x))
x = copy.deepcopy(ex["run-record"])
x.update(body_outcome="outcome_unknown", outcome="outcome_unknown", safe_state="verified")
check("safe transition does not erase test uncertainty", validators["run-record"].is_valid(x))


def commissioning_errors(c, b, policy, p):
    e = []
    if c["dut_class"] != b["dut_class"]:
        e.append("DUT class mismatch")
    if c["id"] != b["commissioning_id"]:
        e.append("commissioning ID mismatch")
    if c["policy"] != b["policy"]:
        e.append("policy mismatch")
    if c["package_lock"] != b["package_lock"]:
        e.append("package lock mismatch")
    if c["expires_at"] <= c["approved_at"]:
        e.append("expiry order")
    if p["mode"] == "gateway_owned" and "unattended" not in c["modes"]:
        e.append("missing unattended grant")
    required = {
        "identity",
        "protocol",
        "envelope",
        "protection",
        "timing",
        "safe_transition",
        "audit_failure",
    }
    if "unattended" in c["modes"]:
        required.add("unattended")
    passing = {r["category"] for r in c["evidence"] if r["result"] == "passed"}
    if not required <= passing:
        e.append("missing passing evidence")
    if proc_errors(p)[1] + c["scheduling_overhead_ms"] > p["max_body_ms"]:
        e.append("overhead budget")
    return e


c = ex["commissioning"]
check("selected commissioning metadata semantics", not commissioning_errors(c, b, policy, p))
for label, edit, reason in [
    ("fixture class change", lambda x: x.update(dut_class="mains_powered"), "DUT class mismatch"),
    ("policy change", lambda x: x["policy"].update(sha256="f" * 64), "policy mismatch"),
    (
        "package lock change",
        lambda x: x["package_lock"].update(sha256="f" * 64),
        "package lock mismatch",
    ),
    ("expired at approval", lambda x: x.update(expires_at=x["approved_at"]), "expiry order"),
    (
        "unattended grant removed",
        lambda x: x.update(modes=["supervised"]),
        "missing unattended grant",
    ),
    (
        "failed protection report",
        lambda x: x["evidence"][3].update(result="failed"),
        "missing passing evidence",
    ),
    (
        "excess scheduling overhead",
        lambda x: x.update(scheduling_overhead_ms=5000),
        "overhead budget",
    ),
]:
    x = copy.deepcopy(c)
    edit(x)
    check(label + " rejected", reason in commissioning_errors(x, b, policy, p))
x = copy.deepcopy(ex["run-record"])
x.update(body_outcome="outcome_unknown", outcome="execution_error")
check("unknown outcome cannot be downgraded", not validators["run-record"].is_valid(x))
x = copy.deepcopy(ex["run-record"])
x.update(body_outcome="assertion_failed", outcome="cancelled")
check("terminal reason cannot mislabel assertion", not validators["run-record"].is_valid(x))
x = copy.deepcopy(b)
x["signals"][1]["absolute_error"] = -1
check("negative signal error bound rejected", not validators["bench"].is_valid(x))


def interval_pass(value, error, lo, hi):
    return error is not None and lo <= value - error and (value + error <= hi)


check("nominal boundary cannot hide uncertainty", not interval_pass(5.1, 0.01, 4.9, 5.1))
check("contained uncertainty interval passes", interval_pass(5.0, 0.01, 4.9, 5.1))
check("unknown required uncertainty is not pass", not interval_pass(5.0, None, 4.9, 5.1))
CHECKS = results
if __name__ == "__main__":
    failures = [name for name, ok in CHECKS if not ok]
    for failure in failures:
        print("FAIL:", failure)
    print(f"{len(CHECKS) - len(failures)}/{len(CHECKS)} checks passed")
    raise SystemExit(bool(failures))
