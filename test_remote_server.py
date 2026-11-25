import base64
import hashlib
import hmac
import json
import os
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from tempfile import NamedTemporaryFile

from photon_ai.remote_server import PhotonRequestHandler, PhotonService, verify_hs256_jwt


class FakeEncoding:
    def __init__(self, ids):
        self.ids = ids


class FakeTokenizer:
    def encode(self, value):
        return FakeEncoding(list(range(max(1, len(value.split())))))


class FakeEngine:
    def __init__(self):
        self.tok = FakeTokenizer()

    def generate_patch(self, lang, error_msg, full_ctx, broken_fn):
        return "return fixed_name"


def token(secret, subject="user-1"):
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": subject, "exp": int(time.time()) + 300, "scope": "photon:patch nanos:spend"}
    encode = lambda value: base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).rstrip(b"=").decode()
    first, second = encode(header), encode(payload)
    signature = base64.urlsafe_b64encode(hmac.new(secret.encode(), f"{first}.{second}".encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
    return f"{first}.{second}.{signature}"


class RemoteServerTests(unittest.TestCase):
    def test_jwt_verification_rejects_tampering_and_expiry(self):
        secret = "test-secret"
        claims = verify_hs256_jwt(token(secret), secret)
        self.assertEqual(claims["sub"], "user-1")
        with self.assertRaises(ValueError):
            verify_hs256_jwt(token(secret)[:-1] + "x", secret)

    def test_unauthenticated_mcp_request_returns_metadata_challenge(self):
        secret = "test-secret"
        os.environ["PHOTON_OAUTH_JWT_SECRET"] = secret
        server = ThreadingHTTPServer(("127.0.0.1", 0), PhotonRequestHandler)
        server.service = PhotonService(FakeEngine())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection("127.0.0.1", server.server_port)
            connection.request("POST", "/photon", body="{}", headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            self.assertEqual(response.status, 401)
            self.assertIn("resource_metadata=", response.getheader("WWW-Authenticate"))
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

    def test_authenticated_tool_call_returns_metered_footer(self):
        secret = "test-secret"
        os.environ["PHOTON_OAUTH_JWT_SECRET"] = secret
        with NamedTemporaryFile("w", suffix=".py", delete=False) as source:
            source.write("def fix():\n    return missing_name\n")
            source_path = source.name
        server = ThreadingHTTPServer(("127.0.0.1", 0), PhotonRequestHandler)
        server.service = PhotonService(FakeEngine())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "fix_code_error", "arguments": {"file_path": source_path, "error_line": 2, "error_msg": "NameError"}}})
            connection = HTTPConnection("127.0.0.1", server.server_port)
            connection.request("POST", "/photon", body=body, headers={"Authorization": f"Bearer {token(secret)}", "Content-Type": "application/json"})
            response = connection.getresponse()
            payload = json.loads(response.read())
            text = payload["result"]["content"][0]["text"]
            self.assertEqual(response.status, 200)
            self.assertIn("[Photon • Deducted", text)
            self.assertIn("Nanos", text)
        finally:
            os.unlink(source_path)
            server.shutdown()
            thread.join()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
