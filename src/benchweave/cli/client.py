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
        # A scheme-less ``--gateway banana`` used to reach urllib as
        # ``ValueError: unknown url type`` deep inside the request — reject
        # it here, at the boundary, as a handled GatewayError.
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise GatewayError(
                f"gateway URL must start with http:// or https:// — got {base_url!r}"
            )
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
        except ValueError as error:
            # Belt and braces for any future URL shape the constructor's
            # scheme check misses: a malformed target is a handled failure,
            # never a traceback.
            raise GatewayError(f"{method} {url} is not a valid request target: {error}") from error
        except TimeoutError as error:
            # A gateway that accepts and answers headers but hangs on the
            # body (M4): report, never traceback.
            raise GatewayError(f"{method} {url} timed out after {self._timeout}s") from error
        if not raw:
            return {}
        try:
            parsed: object = json.loads(raw)
        except json.JSONDecodeError as error:
            # A wrong-but-alive server on the loopback port (I1): 2xx HTML
            # is the common misconfiguration — surface it, don't traceback.
            snippet = repr(raw[:80])
            raise GatewayError(f"{method} {url} returned a non-JSON body: {snippet}") from error
        if not isinstance(parsed, dict):
            raise GatewayError(
                f"{method} {url} returned a non-JSON-object body: {type(parsed).__name__}"
            )
        return parsed

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

    def bench_get(self, bench_id: str) -> dict[str, Any]:
        """GET ``/v1/benches/{bench_id}`` → the bench object (envelope unwrapped)."""
        path = f"/v1/benches/{bench_id}"
        return self._unwrap(self.get(path), path)

    def run_start(
        self,
        bench_id: str,
        *,
        request_id: str,
        binding_ref: Mapping[str, Any],
        expected_generation: int,
        lease_id: str | None = None,
    ) -> dict[str, Any]:
        """POST ``/v1/benches/{bench_id}/runs`` → the accepted run (202)."""
        path = f"/v1/benches/{bench_id}/runs"
        payload = {
            "request_id": request_id,
            "binding_ref": dict(binding_ref),
            "expected_generation": expected_generation,
            "lease_id": lease_id,
        }
        return self._unwrap(self.post(path, payload), path)

    def run_check(self, bench_id: str, *, binding_ref: Mapping[str, Any]) -> dict[str, Any]:
        """POST ``/v1/benches/{bench_id}/run-checks`` → the advisory preflight."""
        path = f"/v1/benches/{bench_id}/run-checks"
        return self._unwrap(self.post(path, {"binding_ref": dict(binding_ref)}), path)

    def run_get(self, run_id: str) -> dict[str, Any]:
        """GET ``/v1/runs/{run_id}`` → the contract run projection."""
        path = f"/v1/runs/{run_id}"
        return self._unwrap(self.get(path), path)

    def run_find(self, request_id: str) -> dict[str, Any]:
        """GET ``/v1/requests/{request_id}`` → the §9 principal-scoped run lookup."""
        path = f"/v1/requests/{request_id}"
        return self._unwrap(self.get(path), path)

    def document_get(self, sha256: str) -> dict[str, Any]:
        """GET ``/v1/documents/{sha256}`` → the stored document payload."""
        path = f"/v1/documents/{sha256}"
        return self._unwrap(self.get(path), path)

    def events_get(self, bench_id: str, *, limit: int = 100) -> dict[str, Any]:
        """GET ``/v1/benches/{bench_id}/events`` → the bench event stream page."""
        path = f"/v1/benches/{bench_id}/events"
        return self._unwrap(
            self.get(path, params={"after": "", "limit": str(limit)}), path
        )
