import copy
import json
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

DOCS = globals().get("DOCS", Path(__file__).resolve().parents[2] / "docs")
STANDARDS = globals().get("STANDARDS", Path(__file__).resolve().parents[2] / "standards")
CONTRACT_DIR = STANDARDS / "registry/0.1.1"
results = []


def check(n, b):
    results.append((n, bool(b)))


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


vs = {}
es = {}
for name in ("release-manifest", "release-status", "package-lock"):
    s = json.loads((CONTRACT_DIR / (name + ".schema.json")).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(s)
    check(name + " meta-schema", True)
    vs[name] = Draft202012Validator(s, format_checker=fc)
    es[name] = json.loads(
        (CONTRACT_DIR / "examples" / (name + ".json")).read_text(encoding="utf-8")
    )
    check(name + " positive fixture", vs[name].is_valid(es[name]))
    for key in s["required"]:
        x = copy.deepcopy(es[name])
        del x[key]
        check(name + " requires " + key, not vs[name].is_valid(x))
m = es["release-manifest"]
v = vs["release-manifest"]
for role in ("implementation", "sbom", "build_provenance", "dependency_lock"):
    x = copy.deepcopy(m)
    x["payload"]["files"] = [f for f in x["payload"]["files"] if f["role"] != role]
    check("implementation requires " + role, not v.is_valid(x))
for path in ("../escape", "/absolute", "a/../../escape", "a\\escape"):
    x = copy.deepcopy(m)
    x["payload"]["files"][0]["path"] = path
    check("reject path " + path, not v.is_valid(x))
x = copy.deepcopy(m)
# The example carries a skill-role file since 0.1.1; mutating its role to a
# near-miss must fail — the role enum stays closed, one admitted member.
next(f for f in x["payload"]["files"] if f["role"] == "skill")["role"] = "skillx"
check("reject payload role skillx", not v.is_valid(x))
x = copy.deepcopy(m)
x["device_targets"][0]["firmware"]["versions"] = []
check("listed firmware cannot be empty", not v.is_valid(x))
x = copy.deepcopy(m)
x["kind"] = "profile"
check("profile cannot contain device implementation", not v.is_valid(x))
x = copy.deepcopy(m)
x["dependencies"][0]["version"] = "latest"
check("dependency cannot float", not v.is_valid(x))
x = copy.deepcopy(m)
x["compatibility"]["runtimes"] = []
check("implementation requires runtime", not v.is_valid(x))


def semantic(x):
    errors = []
    files = {f["path"]: f for f in x["payload"]["files"]}
    if len({p.casefold() for p in files}) != len(x["payload"]["files"]):
        errors.append("duplicate files")
    for p in [x["licence"]["file"], x["changelog_path"], x["migration_notes_path"]] + [
        e["report_path"] for e in x["evidence"]
    ]:
        if p not in files:
            errors.append("missing file")
    deps = [(d["registry_id"], d["package_id"]) for d in x["dependencies"]]
    if len(set(deps)) != len(deps):
        errors.append("duplicate dependency")
    return errors


check("fixture selected metadata semantics", not semantic(m))
x = copy.deepcopy(m)
x["licence"]["file"] = "missing"
check("licence file resolves", "missing file" in semantic(x))
x = copy.deepcopy(m)
x["payload"]["files"].append(copy.deepcopy(x["payload"]["files"][0]))
check("duplicate payload paths rejected", "duplicate files" in semantic(x))
x = copy.deepcopy(m)
x["dependencies"] *= 2
check("duplicate dependency rejected", "duplicate dependency" in semantic(x))
CHECKS = results
if __name__ == "__main__":
    failures = [name for name, ok in CHECKS if not ok]
    for failure in failures:
        print("FAIL:", failure)
    print(f"{len(CHECKS) - len(failures)}/{len(CHECKS)} checks passed")
    raise SystemExit(bool(failures))
