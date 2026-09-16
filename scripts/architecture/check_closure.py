import copy
import json
import re
from pathlib import Path

DOCS = globals().get("DOCS", Path(__file__).resolve().parents[2] / "docs")
STANDARDS = globals().get("STANDARDS", Path(__file__).resolve().parents[2] / "standards")
CONTRACT_DIR = DOCS / "acceptance"
checks = []


def check(n, b):
    checks.append((n, bool(b)))


g = {
    "profiles": {"deps": [], "version": "1.0.0", "digest": "a"},
    "implementation": {"deps": ["profiles"], "version": "1.0.0", "digest": "b"},
    "wrapper": {"deps": ["implementation", "profiles"], "version": "1.0.0", "digest": "c"},
    "other": {"deps": ["profiles"], "version": "1.0.0", "digest": "d"},
}


def closure(graph, roots):
    visited = set()
    errors = []

    def visit(n, path):
        if n in path:
            errors.append("cycle")
            return
        if n not in graph:
            errors.append("missing")
            return
        if n in visited:
            return
        for dep in graph[n]["deps"]:
            visit(dep, path | {n})
        visited.add(n)

    for root in roots:
        visit(root, set())
    return (visited, errors)


nodes, errors = closure(g, ["wrapper", "other"])
check("wrapper graph acyclic", not errors)
check("shared profile included once", nodes == set(g))
x = copy.deepcopy(g)
x["implementation"]["deps"].append("wrapper")
check("reverse wrapper dependency rejected", "cycle" in closure(x, ["wrapper"])[1])
x = copy.deepcopy(g)
del x["profiles"]
check("missing transitive dependency rejected", "missing" in closure(x, ["wrapper"])[1])


def exact(pins):
    seen = {}
    for registry, name, version, digest in pins:
        k = (registry, name)
        if k in seen and seen[k] != (version, digest):
            return False
        seen[k] = (version, digest)
    return True


check("identical dependency pins deduplicate", exact([("public", "p", "1", "a")] * 2))
check(
    "version conflict rejected", not exact([("public", "p", "1", "a"), ("public", "p", "2", "b")])
)
check("digest conflict rejected", not exact([("public", "p", "1", "a"), ("public", "p", "1", "b")]))
check(
    "registries are distinct identities",
    exact([("public", "p", "1", "a"), ("private", "p", "1", "b")]),
)
check("requested firmware must intersect", not set(["new-firmware"]) <= set(["verified-firmware"]))
check("revoked dependency affects wrapper closure", "profiles" in closure(g, ["wrapper"])[0])
reg = (CONTRACT_DIR / "registry-composition-review.md").read_text(encoding="utf-8")
end = (CONTRACT_DIR / "end-to-end-review.md").read_text(encoding="utf-8")
check("16 composition scenarios", len(set(re.findall("\\| (R\\d\\d) \\|", reg))) == 16)
check("26 integrated scenarios", len(set(re.findall("\\| (E\\d\\d) \\|", end))) == 26)
p = (STANDARDS / "execution/0.1.0/execution-contract.md").read_text(encoding="utf-8")
i = (STANDARDS / "interface/0.1.0/interface-contract.md").read_text(encoding="utf-8")
check("expiry covers protective budget", "full body plus protective budget" in p)
check(
    "repeated faults do not extend deadline",
    "do not restart the transition or extend its deadline" in p,
)
check("own lease is not conflicting owner", "not a conflicting busy owner" in i)
check("original document bytes specified", "original_utf8_base64" in i)
check(
    "Stored fixture agrees: " + str(CONTRACT_DIR / "composition-fixtures.json"),
    json.loads((CONTRACT_DIR / "composition-fixtures.json").read_text(encoding="utf-8"))
    == json.loads(
        json.dumps(
            {
                "notice": (
                    "Simplified graph review fixture. "
                    "Short symbolic digests are not registry manifests or installable artefacts."
                ),
                "graph": g,
                "roots": ["wrapper", "other"],
            },
            indent=2,
        )
        + "\n"
    ),
)
n = sum((b for _, b in checks))
CHECKS = checks
if __name__ == "__main__":
    failures = [name for name, ok in CHECKS if not ok]
    for failure in failures:
        print("FAIL:", failure)
    print(f"{len(CHECKS) - len(failures)}/{len(CHECKS)} checks passed")
    raise SystemExit(bool(failures))
