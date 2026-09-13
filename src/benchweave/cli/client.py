"""Stdlib-only HTTP client for the BenchWeave gateway REST surface.

``requests``/``httpx`` are deliberately absent: the CLI is a first-class
surface of the main package and must not grow an HTTP dependency — the
gateway's loopback REST API needs nothing beyond ``urllib.request``. POST is
carried here from day one (Task 9) even though ``status`` only GETs, so the
later write-facing commands do not have to reopen this module's transport.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any


class GatewayError(Exception):
    """A gateway call failed (transport error, non-2xx, or ok=false body)."""


class GatewayClient:
    """Bearer-authenticated REST client (GET/POST via stdlib urllib)."""

    def __init__(self, base_url: str, *, token: str, timeout: float = 10.0) -> None:
        self._base = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout

    # --- transport -----------------------------------------------------------

    def get(self, path: str, params: Mapping[str, str] | None = None) -> dict[str, Any]:
        """GET ``path`` (query-encoded ``params``) and return the parsed body."""
        url = self._base + path
        if params:
            url += "?" + urllib.parse.urlencode(dict(params))
        return self._request("GET", url)

    def post(self, path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """POST ``path`` with a JSON ``payload`` and return the parsed body."""
        return self._request("POST", self._base + path, payload=payload)

    def _request(
        self,
        method: str,
        url: str,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
        body: bytes | None = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace").strip()
            raise GatewayError(f"{method} {url} -> HTTP {error.code}: {detail}") from error
        except urllib.error.URLError as error:
            raise GatewayError(f"{method} {url} unreachable: {error.reason}") from error
        return json.loads(raw) if raw else {}

    # --- typed surface --------------------------------------------------------

    @staticmethod
    def _unwrap(body: dict[str, Any], path: str) -> dict[str, Any]:
        """Unwrap the REST envelope; a non-ok body is a failed call."""
        if body.get("ok") is not True or "data" not in body:
            raise GatewayError(f"{path} returned a non-ok envelope: {body!r}")
        data = body["data"]
        if not isinstance(data, dict):
            raise GatewayError(f"{path} returned a non-object data payload: {data!r}")
        return data

    def gateway_info(self) -> dict[str, Any]:
        """GET ``/v1`` → gateway identity payload (envelope unwrapped)."""
        return self._unwrap(self.get("/v1"), "/v1")

    def bench_list(self, *, limit: int = 100) -> dict[str, Any]:
        """GET ``/v1/benches`` → bench inventory payload (envelope unwrapped)."""
        return self._unwrap(self.get("/v1/benches", params={"limit": str(limit)}), "/v1/benches")
