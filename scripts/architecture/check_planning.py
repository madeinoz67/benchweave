import ast
import json
import re
from pathlib import Path

DOCS = globals().get("DOCS", Path(__file__).resolve().parents[2] / "docs")
CONTRACT_DIR = DOCS.resolve()
P = CONTRACT_DIR / "implementation-planning"
checks = []


def check(n, b):
    checks.append((n, bool(b)))


prd = (P / "00-poc-mvp-prd.md").read_text(encoding="utf-8")
plan = (P / "01-delivery-plan.md").read_text(encoding="utf-8")
hw = (P / "02-hardware-discovery.md").read_text(encoding="utf-8")
first = (P / "03-first-slice-plan.md").read_text(encoding="utf-8")
reqs = set(re.findall("\\| (PRD-\\d\\d) \\|", prd))
check("17 PRD requirements", len(reqs) == 17)
check("12 work packages", len(set(re.findall("\\| (WP\\d\\d) \\|", plan))) == 12)
check("four exit gates", all("**G" + str(i) + " " in prd for i in range(1, 5)))
check("DPS-150 selected in PRD", "FNIRSI DPS-150" in prd)
check("ESP32 explicitly provisional", "ESP32 is the provisional" in prd)
check("hardware protection gate", "PRD-14" in prd and "G3" in plan and ("HW-08" in hw))
check("PSU profile mismatch handled", "limited profile" in hw and "OVP" in hw and ("OCP" in hw))
check(
    "eight step kinds correctly scoped",
    "All eight step kinds" in prd and "Eight step kinds" in plan,
)
check("separate PoC and MVP acceptance", "100 consecutive" in prd and "20 consecutive" in prd)
trace = {
    "PRD-01": ["WP01", "WP08", "WP09"],
    "PRD-02": ["WP06", "WP09"],
    "PRD-03": ["WP06", "WP09"],
    "PRD-04": ["WP04"],
    "PRD-05": ["WP03", "WP05", "WP09"],
    "PRD-06": ["WP05", "WP09"],
    "PRD-07": ["WP03", "WP07", "WP09"],
    "PRD-08": ["WP05", "WP09"],
    "PRD-09": ["WP04", "WP05", "WP07", "WP09"],
    "PRD-10": ["WP02", "WP07", "WP09"],
    "PRD-11": ["WP05", "WP06", "WP09"],
    "PRD-12": ["WP07", "WP09"],
    "PRD-13": ["WP10", "WP11"],
    "PRD-14": ["WP11"],
    "PRD-15": ["WP12"],
    "PRD-16": ["WP12"],
    "PRD-17": ["post_mvp"],
}
check("every PRD requirement mapped", set(trace) == reqs)
check(
    "trace points to planned work",
    all(x == "post_mvp" or "| " + x + " |" in plan for vals in trace.values() for x in vals),
)
check(
    "Stored fixture agrees: " + str(P / "requirements-trace.json"),
    json.loads((P / "requirements-trace.json").read_text(encoding="utf-8"))
    == json.loads(
        json.dumps({"status": "planned, not implemented", "requirements": trace}, indent=2) + "\n"
    ),
)
blocks = re.findall("```python\\n(.*?)```", first, re.S)
check("two complete first-slice code blocks", len(blocks) == 2)
for i, b in enumerate(blocks):
    ast.parse(b)
    check("first-slice code block " + str(i + 1) + " syntax", True)
check("first slice not represented as executed", "they have not been executed" in first)
for p in P.glob("*.md"):
    if p.name == "planning-review.md":
        continue
    check(
        p.name + " no unresolved placeholder tokens",
        not re.search("\\b(?:TODO|TBD|FIXME)\\b", p.read_text(encoding="utf-8")),
    )
    for link in re.findall("\\]\\(([^)]+)\\)", p.read_text(encoding="utf-8")):
        if link.startswith(("https:", "http:", "#")):
            continue
        target = (p.parent / link.split("#")[0]).resolve()
        check(p.name + " link " + link, target.is_file() or target.name == "planning-review.md")
CHECKS = checks
if __name__ == "__main__":
    failures = [name for name, ok in CHECKS if not ok]
    for failure in failures:
        print("FAIL:", failure)
    print(f"{len(CHECKS) - len(failures)}/{len(CHECKS)} checks passed")
    raise SystemExit(bool(failures))
