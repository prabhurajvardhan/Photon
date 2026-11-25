"""Authenticated Streamable HTTP MCP worker for the Photon service.

The worker deliberately contains no browser UI. A reverse proxy can route browser
GET requests to the separately deployed portal while routing MCP POST requests
here. The portal origin is configured with PHOTON_PORTAL_URL.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .slicer import slice_huge_file_surgical

RESOURCE_METADATA = "https://mcp.nanowareai.in/.well-known/oauth-protected-resource"
DEFAULT_PORTAL_URL = "https://nanowareai.in/photon"
PHOTON_SCOPE = "photon:patch"
NANOS_SCOPE = "nanos:spend"


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def verify_hs256_jwt(token: str, secret: str, *, issuer: str | None = None, audience: str | None = None) -> dict[str, Any]:
    """Verify a compact HS256 JWT and return its claims."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("invalid bearer token")
    encoded_header, encoded_payload, encoded_signature = parts
    header = json.loads(_b64decode(encoded_header))
    claims = json.loads(_b64decode(encoded_payload))
    if header.get("alg") != "HS256" or header.get("typ") not in (None, "JWT"):
        raise ValueError("unsupported bearer token")
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, _b64decode(encoded_signature)):
        raise ValueError("invalid bearer token")
    now = int(time.time())
    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise ValueError("bearer token has no subject")
    if not isinstance(claims.get("exp"), (int, float)) or int(claims["exp"]) <= now:
        raise ValueError("bearer token expired")
    if issuer is not None and claims.get("iss") != issuer:
        raise ValueError("bearer token issuer mismatch")
    if audience is not None:
        audiences = claims.get("aud", [])
        if isinstance(audiences, str):
            audiences = [audiences]
        if audience not in audiences:
            raise ValueError("bearer token audience mismatch")
    return claims


class NanosClient:
    """Small HTTP client for the Nanoware AI Nanos ledger API."""

    def __init__(self, base_url: str, opener: Callable[..., Any] = urlopen):
        self.base_url = base_url.rstrip("/")
        self.opener = opener

    def _request(self, method: str, path: str, token: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"},
        )
        try:
            with self.opener(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(details)
            except json.JSONDecodeError:
                payload = {"error": details or "Nanos service error"}
            payload["status"] = error.code
            return payload
        except (URLError, TimeoutError) as error:
            raise RuntimeError("Nanos service unavailable") from error

    def balance(self, token: str) -> dict[str, Any]:
        return self._request("GET", "/api/nanos/balance", token)

    def deduct(self, token: str, *, input_tokens: int, output_tokens: int) -> dict[str, Any]:
        return self._request("POST", "/api/nanos/deduct", token, {"input_tokens": input_tokens, "output_tokens": output_tokens, "model": "photon-v0-int4"})


class PhotonService:
    def __init__(self, engine: Any, nanos: NanosClient | None = None):
        self.engine = engine
        self.nanos = nanos

    @staticmethod
    def _prompt(lang: str, error_msg: str, full_ctx: str, broken_fn: str) -> str:
        tag = "<|lang_py|>" if lang == "py" else "<|lang_ts|>"
        return f"<|bos|>{tag}<|err|>\n{error_msg}\n<|ctx|>\n{full_ctx}\n<|think|><|end_think|>\n<|search|>\n{broken_fn}\n<|replace|>\n"

    def fix_code_error(self, token: str, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = arguments.get("file_path")
        error_line = arguments.get("error_line")
        error_msg = arguments.get("error_msg")
        if not isinstance(file_path, str) or not isinstance(error_line, int) or not isinstance(error_msg, str):
            raise ValueError("file_path, error_line, and error_msg are required")
        ctx, broken_fn = slice_huge_file_surgical(file_path, error_line)
        lang = "py" if file_path.endswith(".py") else "ts"
        prompt = self._prompt(lang, error_msg, ctx, broken_fn)
        input_tokens = len(self.engine.tok.encode(prompt).ids)
        if self.nanos is not None:
            balance = self.nanos.balance(token)
            if int(balance.get("balance_nanos", 0)) < input_tokens + 30:
                return {"content": [{"type": "text", "text": "Insufficient Nanos balance. Watch a short ad at https://nanowareai.in/nanos/earn?source=photon to claim +100,000 Nanos (~33,000 output tokens) and retry."}], "isError": True}
        patch = self.engine.generate_patch(lang, error_msg, ctx, broken_fn)
        output_tokens = len(self.engine.tok.encode(patch).ids)
        if self.nanos is None:
            remaining = "unmetered"
            spent = input_tokens + output_tokens * 3
        else:
            deduction = self.nanos.deduct(token, input_tokens=input_tokens, output_tokens=output_tokens)
            if int(deduction.get("status", 200)) == 402 or deduction.get("error"):
                return {"content": [{"type": "text", "text": "Insufficient Nanos balance. Watch a short ad at https://nanowareai.in/nanos/earn?source=photon to claim +100,000 Nanos (~33,000 output tokens) and retry."}], "isError": True}
            remaining = deduction.get("balance_nanos", deduction.get("remaining_balance_nanos", "unknown"))
            spent = input_tokens + output_tokens * 3
        footer = f"[Photon • Deducted {spent} Nanos ({input_tokens} in, {output_tokens} out) | Remaining Balance: {remaining} Nanos]"
        return {"content": [{"type": "text", "text": f"{patch}\n\n{footer}"}]}


class PhotonRequestHandler(BaseHTTPRequestHandler):
    server_version = "PhotonMCP/0.1"

    def _json(self, status: int, payload: dict[str, Any], headers: dict[str, str] | None = None) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(encoded)

    def _bearer(self) -> tuple[str | None, dict[str, Any] | None]:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None, None
        token = header[7:].strip()
        try:
            claims = verify_hs256_jwt(token, os.environ["PHOTON_OAUTH_JWT_SECRET"], issuer=os.getenv("PHOTON_OAUTH_ISSUER"), audience=os.getenv("PHOTON_OAUTH_AUDIENCE"))
            return token, claims
        except (KeyError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return None, None

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/photon":
            portal = os.getenv("PHOTON_PORTAL_URL", DEFAULT_PORTAL_URL)
            self.send_response(302)
            self.send_header("Location", portal)
            self.end_headers()
            return
        if self.path == "/.well-known/oauth-protected-resource":
            self._json(200, {"resource": "https://mcp.nanowareai.in/photon", "authorization_servers": ["https://mcp.nanowareai.in"]})
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/photon":
            self._json(404, {"error": "not_found"})
            return
        token, claims = self._bearer()
        if token is None or claims is None:
            self._json(401, {"error": "unauthorized"}, {"WWW-Authenticate": f'Bearer resource_metadata="{RESOURCE_METADATA}"'})
            return
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 1_000_000)
            request = json.loads(self.rfile.read(length))
            result = self._dispatch(token, request)
            self._json(200, result)
        except (ValueError, KeyError, json.JSONDecodeError) as error:
            self._json(400, {"error": str(error)})
        except Exception:
            self._json(500, {"error": "internal_server_error"})

    def _dispatch(self, token: str, request: dict[str, Any]) -> dict[str, Any]:
        request_id = request.get("id")
        method = request.get("method")
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05", "serverInfo": {"name": "photon", "version": "0.1.0-beta"}, "capabilities": {"tools": {}}}
        elif method == "tools/list":
            result = {"tools": [{"name": "fix_code_error", "description": "Patch a Python or TypeScript compiler error with Photon and meter Nanos.", "inputSchema": {"type": "object", "properties": {"file_path": {"type": "string"}, "error_line": {"type": "integer"}, "error_msg": {"type": "string"}}, "required": ["file_path", "error_line", "error_msg"]}}]}
        elif method == "tools/call":
            params = request.get("params", {})
            arguments = params.get("arguments", {})
            name = params.get("name")
            if name not in ("fix_code_error", "fix_compiler_error"):
                raise ValueError("unknown tool")
            result = self.service.fix_code_error(token, arguments)
        else:
            raise ValueError("unsupported method")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @property
    def service(self) -> PhotonService:
        return self.server.service  # type: ignore[attr-defined]


def serve_http(host: str = "0.0.0.0", port: int = 8080, *, engine: Any | None = None, nanos: NanosClient | None = None) -> None:
    if engine is None:
        from .engine import TinyCodeEngine
        engine = TinyCodeEngine()
    handler = PhotonRequestHandler
    server = ThreadingHTTPServer((host, port), handler)
    server.service = PhotonService(engine, nanos or (NanosClient(os.environ["NANOS_API_BASE_URL"]) if os.getenv("NANOS_API_BASE_URL") else None))  # type: ignore[attr-defined]
    try:
        server.serve_forever()
    finally:
        server.server_close()
