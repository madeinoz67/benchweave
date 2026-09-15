import json
import re
from pathlib import Path
from urllib.parse import unquote, urldefrag, urljoin, urlparse

from referencing import Registry, Resource
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

"Offline JSON, schema-reference and local Markdown-link integrity checks."
DOCS = globals().get("DOCS", Path(__file__).resolve().parents[2] / "docs")
STANDARDS = globals().get("STANDARDS", Path(__file__).resolve().parents[2] / "standards")
CHECKS = []


def strip_code_fences(text: str) -> str:
    """Markdown minus its fenced code blocks.

    A fenced block can contain ``](...)`` expressions that are CODE, not
    links (``legs[leg](arg)``); the link scan must run on prose only. An
    opening fence may carry an info string (`````python`````); a closing
    fence is only the fence characters. An unclosed fence swallows the rest
    of the file — conservative in the safe direction (fewer false links).
    """
    kept: list[str] = []
    fence_char = ""
    fence_len = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if fence_char:
            if (
                len(stripped) >= fence_len
                and stripped.startswith(fence_char * fence_len)
                and not stripped.strip(fence_char)
            ):
                fence_char = ""
            continue
        run = len(stripped) - len(stripped.lstrip(stripped[0])) if stripped else 0
        if run >= 3 and stripped[0] in "`~":
            fence_char = stripped[0]
            fence_len = run
            continue
        kept.append(line)
    return "".join(kept)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"Non-finite JSON number: {value}")


def walk(value, base):
    if isinstance(value, dict):
        if "$id" in value:
            base = urljoin(base, value["$id"])
        yield (value, base)
        for child in value.values():
            yield from walk(child, base)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child, base)


documents = {}
registry = Registry()
for path in sorted(STANDARDS.rglob("*.json")):
    try:
        data = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (ValueError, UnicodeError) as error:
        CHECKS.append((f"{path.relative_to(STANDARDS)} valid JSON: {error}", False))
        continue
    CHECKS.append((f"{path.relative_to(STANDARDS)} valid JSON", True))
    documents[path] = data
    resource = Resource.from_contents(data, default_specification=DRAFT202012)
    registry = registry.with_resource(path.as_uri(), resource)
    for node, base in walk(data, path.as_uri()):
        if "$id" in node:
            registry = registry.with_resource(
                base, Resource.from_contents(node, default_specification=DRAFT202012)
            )
for path, data in documents.items():
    roots = [(path.as_uri(), data)]
    if path.name == "mcp-tools.json":
        # Each MCP tool schema is an independent JSON Schema document.
        roots = [
            (path.as_uri() + f"?tool={index}&direction={direction}", tool[direction])
            for index, tool in enumerate(data["tools"])
            for direction in ("inputSchema", "outputSchema")
        ]
    elif path.name == "operation-catalog.json":
        # Catalog schemas explicitly use the shared interface definitions.
        shared = documents[path.parent / "interface.schema.json"]
        roots = [(path.as_uri(), {**data, "$defs": shared["$defs"]})]
    for base_uri, root in roots:
        scoped = registry.with_resource(
            base_uri, Resource.from_contents(root, default_specification=DRAFT202012)
        )
        for node, base in walk(root, base_uri):
            if "$ref" not in node:
                continue
            ref = node["$ref"]
            try:
                scoped.resolver(base).lookup(ref)
                resolved = True
            except Unresolvable:
                resolved = False
            CHECKS.append((f"{path.relative_to(STANDARDS)} resolves {ref}", resolved))
for path in sorted(DOCS.rglob("*.json")):
    try:
        json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (ValueError, UnicodeError) as error:
        CHECKS.append((f"{path.relative_to(DOCS)} valid JSON: {error}", False))
        continue
    CHECKS.append((f"{path.relative_to(DOCS)} valid JSON", True))
for path, text in sorted(
    (path, strip_code_fences(path.read_text(encoding="utf-8")))
    for root in (DOCS, STANDARDS)
    for path in root.rglob("*.md")
):
    for link in re.findall("\\]\\(([^)]+)\\)", text):
        link = link.strip("<>")
        if urlparse(link).scheme:
            CHECKS.append(
                (
                    f"{path.name} portable link {link}",
                    link.startswith(("https:", "http:", "mailto:")),
                )
            )
            continue
        target, _fragment = urldefrag(link)
        if not target:
            continue
        destination = (path.parent / unquote(target)).resolve()
        CHECKS.append(
            (
                f"{path.name} local link {link}",
                not Path(target).is_absolute()
                and (
                    destination.is_relative_to(DOCS.resolve())
                    or destination.is_relative_to(STANDARDS.resolve())
                )
                and destination.exists(),
            )
        )
if __name__ == "__main__":
    failures = [name for name, ok in CHECKS if not ok]
    for failure in failures:
        print("FAIL:", failure)
    print(f"{len(CHECKS) - len(failures)}/{len(CHECKS)} checks passed")
    raise SystemExit(bool(failures))
