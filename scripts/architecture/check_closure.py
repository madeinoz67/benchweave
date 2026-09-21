import copy
import json
import re
import sys
from pathlib import Path

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
# Scenario counts stored in variables so the coverage prose derives them
# (D3 digits); the == 16 / == 26 pins themselves stay literal.
composition_scenarios = len(set(re.findall("\\| (R\\d\\d) \\|", reg)))
integrated_scenarios = len(set(re.findall("\\| (E\\d\\d) \\|", end)))
check("16 composition scenarios", composition_scenarios == 16)
check("26 integrated scenarios", integrated_scenarios == 26)
p = (
    STANDARDS
    / "execution"
    / _validation_report.active_standard_version(STANDARDS, "execution")
    / "execution-contract.md"
).read_text(encoding="utf-8")
i = (
    STANDARDS
    / "interface"
    / _validation_report.active_standard_version(STANDARDS, "interface")
    / "interface-contract.md"
).read_text(encoding="utf-8")
check("expiry covers protective budget", "full body plus protective budget" in p)
check(
    "repeated faults do not extend deadline",
    "do not restart the transition or extend its deadline" in p,
)
check("own lease is not conflicting owner", "not a conflicting busy owner" in i)
check("original document bytes specified", "original_utf8_base64" in i)
check(
    # Root-relative, not str(CONTRACT_DIR / ...): an absolute path here would
    # bake the host's checkout location into the pinned report bytes (the
    # portability guard in test_architecture.py pins this). CONTRACT_DIR is
    # built from DOCS by pure path arithmetic, so relative_to stays lexical.
    # as_posix for the same reason: str() of a Windows path would bake the
    # host's separator into those bytes (#138).
    "Stored fixture agrees: "
    + (CONTRACT_DIR / "composition-fixtures.json").relative_to(DOCS).as_posix(),
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
CHECKS = checks

GENERATED_MARKER = _validation_report.marker("scripts/architecture/check_closure.py")
REPORT_TITLE = "# Closure review verification"
REPORT_COVERAGE = (
    "Selected graph/compatibility rejection cases and review coverage were checked. "
    f"{composition_scenarios} composition and {integrated_scenarios} integrated scenarios "
    "were walked through architecturally. Scenario counts and text checks do not "
    "demonstrate runtime behaviour. No physical tests or full package resolver were "
    "executed."
)


def render_report(checks: list[tuple[str, bool]]) -> str:
    """Render the validation report markdown from a closure-suite check list.

    Pure and order-canonical (sorted ``## Checks``, a function of the check
    set only); the shared template lives in ``_validation_report.render``.
    """
    return _validation_report.render(
        [(str(name), bool(ok)) for name, ok in checks],
        marker=GENERATED_MARKER,
        title=REPORT_TITLE,
        coverage=REPORT_COVERAGE,
    )


if __name__ == "__main__":
    _validation_report.main(
        CHECKS,
        CONTRACT_DIR / "validation-report.md",
        script="scripts/architecture/check_closure.py",
        title=REPORT_TITLE,
        coverage=REPORT_COVERAGE,
    )
