"""D8: vendored-corpus input validation at the seam (spec Decision 2).

ONE schema per operation, built solely from the vendored interface corpus
(never a hand copy). Per operation the schema is the vendored MCP
``inputSchema`` when the operation has an MCP twin — it is the COMPLETE
payload set (request body plus routing params) and carries its own
``$defs`` — and otherwise the OpenAPI ``requestBody`` schema (the two
REST-only admin operations). Where both sources exist their ``required``
sets must agree once the route's path params are accounted for (the tool
schema carries them, the REST body does not): disagreement is a hard error
at registry construction, never a silent pick. Validation failure is the
contract's ``invalid_request`` on BOTH transports — replacing the
presence-only layer (compatibility.md D8, closing D3's empty-default half
with it).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from benchweave.interfaces import errors
from benchweave.vendoring import contract_family

#: The vendored interface corpus (packaged in the wheel, repo-relative in a
#: dev checkout — :mod:`benchweave.vendoring`). interface-v1.1.1 is the D2
#: errata revision: change_apply's REST body admits the optional
#: ``approver_token`` the adapter forwards. The 1.1.0 corpus stays vendored,
#: frozen, at ``contracts/interface-v1.1.0/``.
VENDORED_CORPUS_ROOT = contract_family("interface-v1.1.1")

_TOOL_PREFIX = "stg_v1_"
_PATH_TEMPLATE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _path_params(route: str) -> frozenset[str]:
    """The routing parameters an OpenAPI path template declares."""
    return frozenset(_PATH_TEMPLATE.findall(route))


class SeamValidator:
    """Per-operation jsonschema admission built from the vendored corpus."""

    def __init__(self, corpus_root: Path) -> None:
        self._corpus = corpus_root
        self._validators: dict[str, Draft202012Validator] = {}
        self._build()

    def _load(self, name: str) -> Any:
        return json.loads((self._corpus / name).read_text(encoding="utf-8"))

    def _build(self) -> None:
        openapi = self._load("openapi.json")
        tools = self._load("mcp-tools.json")
        # Registry construction mirrors presentation/contracts.py: every
        # resource enters under its file name AND its $id, as DRAFT202012.
        # The interface schema itself is registered so urn:stg:interface:*
        # references stay resolvable; the tool schemas additionally carry
        # their own inline $defs (their "#/$defs/..." refs are local).
        registry: Registry = Registry()
        interface_schema = self._load("interface.schema.json")
        resource = Resource.from_contents(interface_schema, default_specification=DRAFT202012)
        registry = registry.with_resource("interface.schema.json", resource)
        if "$id" in interface_schema:
            registry = registry.with_resource(interface_schema["$id"], resource)
        tool_schemas = {
            tool["name"].removeprefix(_TOOL_PREFIX): tool.get("inputSchema")
            for tool in tools["tools"]
        }
        for route, item in openapi["paths"].items():
            op = item.get("post") or item.get("get")
            if op is None:
                continue
            name = op["operationId"].removeprefix(_TOOL_PREFIX)
            body = self._body_schema(op)
            tool_schema = tool_schemas.get(name)
            if tool_schema is not None:
                schema: Mapping[str, Any] = tool_schema
                if body is not None:
                    # Cross-source fence: the tool's required set must be
                    # exactly the REST body's required set plus the route's
                    # path params (the tool carries routing params; the REST
                    # body does not). Anything else is corpus disagreement.
                    tool_required = set(tool_schema.get("required", []))
                    rest_required = set(body.get("required", [])) | _path_params(route)
                    if tool_required != rest_required:
                        raise ValueError(
                            f"corpus disagreement on {name}: "
                            f"{sorted(tool_required)} vs {sorted(rest_required)}"
                        )
            elif body is not None:
                schema = body  # REST-only operation: the body IS the payload
            else:
                continue  # no corpus schema (e.g. change_get): handler owns it
            self._validators[name] = Draft202012Validator(schema, registry=registry)

    @staticmethod
    def _body_schema(op: Mapping[str, Any]) -> Mapping[str, Any] | None:
        content = (op.get("requestBody", {}).get("content", {})
                   .get("application/json", {}))
        schema = content.get("schema")
        return schema if isinstance(schema, dict) else None

    def operation_names(self) -> frozenset[str]:
        return frozenset(self._validators)

    def validate(self, operation: str, payload: Mapping[str, Any]) -> None:
        validator = self._validators.get(operation)
        if validator is None:
            return  # no corpus schema: handler owns presence/404 semantics
        error = next(validator.iter_errors(dict(payload)), None)
        if error is not None:
            raise errors.OperationFailure(errors.failure(
                "invalid_request",
                f"{operation}: {error.message} at {list(error.absolute_path) or '<root>'}",
            )) from None
