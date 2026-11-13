import http.client
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import archive_store
import auth_store
import seed_signature
import server
import workspace_store

PLATFORM_KEY = "sk-platform-test-key-123"


class FakeAuthority(BaseHTTPRequestHandler):
    """Stands in for the Seed Signature platform: same path, header and answer shape as docs/EMBED_WIDGET.md."""
    seen = []; mode = "ok"; base = ""

    def log_message(self, *args): pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        FakeAuthority.seen.append({"path": self.path, "key": self.headers.get("X-Platform-API-Key"), "auth": self.headers.get("Authorization"), "body": body})
        if self.path != "/api/v1/embed/sessions": return self.reply(404, {})
        if self.headers.get("X-Platform-API-Key") != PLATFORM_KEY: return self.reply(401, {"detail": "bad key"})
        if FakeAuthority.mode == "busy": return self.reply(429, {})
        if FakeAuthority.mode == "foreign_widget": return self.reply(200, {"sessionToken": "t", "widgetUrl": "https://evil.example/steal"})
        self.reply(200, {"sessionToken": "sess-token-1", "widgetUrl": FakeAuthority.base + "/platform?session_token=sess-token-1"})

    def do_GET(self):
        if self.path == "/sdk/seed-signature-widget.js":
            script = b"window.SeedSignature={openSignModal:function(o){window.__opened=o;setTimeout(function(){o.onComplete({signatureId:'sig_abc12345',certificateUrl:'%s/certificate/sig_abc12345'});},50);}};" % FakeAuthority.base.encode()
            self.send_response(200); self.send_header("Content-Type", "application/javascript"); self.send_header("Content-Length", str(len(script))); self.end_headers(); self.wfile.write(script)
        else: self.reply(404, {})

    def reply(self, status, payload):
        data = json.dumps(payload).encode(); self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)


class Base(unittest.TestCase):
    def setUp(self):
        FakeAuthority.seen = []; FakeAuthority.mode = "ok"
        self.authority = HTTPServer(("127.0.0.1", 0), FakeAuthority); FakeAuthority.base = f"http://127.0.0.1:{self.authority.server_address[1]}"
        threading.Thread(target=self.authority.serve_forever, daemon=True).start()
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); self.port = sock.getsockname()[1]
        self.patches = [patch.object(archive_store, "DB_PATH", root / "archive.db"), patch.object(workspace_store, "DB_PATH", root / "archive.db"), patch.object(auth_store, "DB_PATH", root / "archive.db"), patch.object(server, "DATA_FILE", str(root / "seeds.json")), patch.object(server, "CONFIG_FILE", str(root / "config.json")),
                        patch.dict(os.environ, {"SEED_SIGNATURE_API_URL": FakeAuthority.base, "SEED_SIGNATURE_PLATFORM_API_KEY": PLATFORM_KEY})]
        for item in self.patches: item.start()
        archive_store.initialize()

    def tearDown(self):
        self.authority.shutdown(); self.authority.server_close()
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()


class ModuleTests(Base):
    def test_session_uses_the_partner_contract_and_keeps_the_key_server_side(self):
        out = seed_signature.create_session("user-1", "text", "My plan")
        sent = FakeAuthority.seen[-1]
        self.assertEqual((sent["path"], sent["key"], sent["auth"]), ("/api/v1/embed/sessions", PLATFORM_KEY, None))
        self.assertEqual(sent["body"], {"external_user_id": "user-1", "content_type": "text", "title": "My plan"})
        self.assertEqual(out["sessionToken"], "sess-token-1")
        self.assertTrue(out["widgetUrl"].startswith(FakeAuthority.base)); self.assertTrue(out["sdkUrl"].endswith("/sdk/seed-signature-widget.js"))
        self.assertNotIn(PLATFORM_KEY, json.dumps(out))

    def test_bad_key_busy_foreign_widget_unreachable_unconfigured_and_insecure_address(self):
        with patch.dict(os.environ, {"SEED_SIGNATURE_PLATFORM_API_KEY": "wrong"}):
            with self.assertRaises(seed_signature.SignatureError) as caught: seed_signature.create_session("u")
            self.assertIn("did not accept", str(caught.exception)); self.assertNotIn("wrong", str(caught.exception))
        FakeAuthority.mode = "busy"
        with self.assertRaises(seed_signature.SignatureError): seed_signature.create_session("u")
        FakeAuthority.mode = "foreign_widget"
        with self.assertRaises(seed_signature.SignatureError) as caught: seed_signature.create_session("u")
        self.assertIn("unexpected", str(caught.exception))                                   # a widget address on another host is never passed on
        with patch.dict(os.environ, {"SEED_SIGNATURE_API_URL": "http://127.0.0.1:1"}):
            with self.assertRaises(seed_signature.SignatureError) as caught: seed_signature.create_session("u")
            self.assertIn("could not be reached", str(caught.exception))
        with patch.dict(os.environ, {"SEED_SIGNATURE_API_URL": "http://seedsig.example.com"}):
            with self.assertRaises(seed_signature.SignatureError) as caught: seed_signature.create_session("u")
            self.assertIn("https", str(caught.exception))
        with patch.dict(os.environ, {"SEED_SIGNATURE_API_URL": "", "SEED_SIGNATURE_PLATFORM_API_KEY": "", "SEED_SIGNATURE_API_KEY": ""}):
            self.assertFalse(seed_signature.configured())
            with self.assertRaises(seed_signature.SignatureError): seed_signature.create_session("u")
        with self.assertRaises(seed_signature.SignatureError): seed_signature.create_session("u", "BAD TYPE!")

    def test_results_must_name_a_valid_id_and_a_certificate_on_the_authority(self):
        self.assertEqual(seed_signature.validate_result("sig_abc12345", FakeAuthority.base + "/certificate/x")[0], "sig_abc12345")
        for sid, url in (("", ""), ("bad id!", ""), ("sig_abc12345", "https://evil.example/certificate/x")):
            with self.assertRaises(seed_signature.SignatureError): seed_signature.validate_result(sid, url)


class RouteTests(Base):
    def setUp(self):
        super().setUp()
        self.httpd = server.HTTPServer(("127.0.0.1", self.port), server.SeedReflectionAPIHandler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown(); self.httpd.server_close(); super().tearDown()

    def call(self, method, path, body=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        connection.request(method, path, body=json.dumps(body) if body is not None else None, headers={"Content-Type": "application/json"})
        response = connection.getresponse(); data = json.loads(response.read() or b"{}"); connection.close(); return response.status, data

    def test_session_route_and_signing_a_work_artifact_with_staleness(self):
        self.assertEqual(self.call("GET", "/api/v2/seed-signature/status")[1], {"configured": True, "authority": FakeAuthority.base})
        status, session = self.call("POST", "/api/v2/seed-signature/session", {"content_type": "text", "title": "Plan"})
        self.assertEqual((status, session["sessionToken"]), (200, "sess-token-1"))
        self.assertEqual(FakeAuthority.seen[-1]["body"]["external_user_id"], "local-owner")
        self.assertNotIn(PLATFORM_KEY, json.dumps(session))

        _, made = self.call("POST", "/api/v2/artifacts", {"type": "plan", "title": "Plan", "content": "Launch fortnightly."})
        artifact_id = made["artifact"]["artifact_id"]
        self.assertEqual(self.call("POST", f"/api/v2/artifacts/{artifact_id}/signature", {"signature_id": "x", "certificate_url": ""})[0], 400)
        self.assertEqual(self.call("POST", f"/api/v2/artifacts/{artifact_id}/signature", {"signature_id": "sig_abc12345", "certificate_url": "https://evil.example/c"})[0], 400)
        self.assertEqual(self.call("POST", "/api/v2/artifacts/nope/signature", {"signature_id": "sig_abc12345"})[0], 404)
        status, signed = self.call("POST", f"/api/v2/artifacts/{artifact_id}/signature", {"signature_id": "sig_abc12345", "certificate_url": FakeAuthority.base + "/certificate/sig_abc12345"})
        self.assertEqual(status, 200)
        listing = self.call("GET", "/api/v2/artifacts")[1]["artifacts"][0]["signature"]
        self.assertEqual((listing["signature_id"], listing["status"]), ("sig_abc12345", "matches"))
        self.call("POST", f"/api/v2/artifacts/{artifact_id}", {"content": "Launch weekly instead."})
        self.assertEqual(self.call("GET", "/api/v2/artifacts")[1]["artifacts"][0]["signature"]["status"], "edited_since")   # an edit never keeps looking signed

    def test_unreachable_authority_is_a_clear_503(self):
        with patch.dict(os.environ, {"SEED_SIGNATURE_API_URL": "http://127.0.0.1:1"}):
            status, body = self.call("POST", "/api/v2/seed-signature/session", {})
        self.assertEqual(status, 503); self.assertIn("could not be reached", body["error"])


if __name__ == "__main__":
    unittest.main()


class LegacySigningSimulatorTests(unittest.TestCase):
    """The old built-in screens only simulated a signature. They must not be reachable except as an explicit local demo."""
    def request(self, runtime, method, path, body=None):
        import urllib.error, urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:{runtime.port}{path}", data=json.dumps(body).encode() if body is not None else None, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as response: return response.status, response.read().decode()
        except urllib.error.HTTPError as exc: return exc.code, exc.read().decode()

    def test_hosted_and_default_local_refuse_the_simulated_signing_routes(self):
        sys.path.insert(0, os.path.dirname(__file__))
        from test_unified_runtime import UnifiedRuntime
        for mode in ("hosted", "local"):
            runtime = UnifiedRuntime(mode)
            try:
                for method, path in (("POST", "/api/seed/create"), ("POST", "/widget/sign/submit"), ("GET", "/widget/sign?token=x"), ("GET", "/sdk/seed-signature-widget.js")):
                    self.assertEqual(self.request(runtime, method, path, {"seed_id": "a", "content": "x"} if method == "POST" else None)[0], 404, (mode, path))
            finally:
                runtime.close()
        runtime = UnifiedRuntime("hosted")
        try:
            self.assertEqual(self.request(runtime, "GET", "/seeds/verify/SIG_X")[0], 404)
        finally:
            runtime.close()

    def test_the_local_demo_escapes_everything_it_prints(self):
        sys.path.insert(0, os.path.dirname(__file__))
        from test_unified_runtime import UnifiedRuntime
        runtime = UnifiedRuntime("local", {"SEED_REFLECTIONS_LOCAL_SIGNING_DEMO": "1"})
        try:
            status, created = self.request(runtime, "POST", "/api/seed/create", {"seed_id": "a", "content": "<img src=x onerror=alert(1)>"})
            token = json.loads(created)["sessionToken"]
            page = self.request(runtime, "GET", f"/widget/sign?token={token}")[1]
            self.assertNotIn("<img src=x", page); self.assertIn("&lt;img src=x", page)
            self.assertNotIn("<script>alert", self.request(runtime, "GET", "/seeds/verify/%3Cscript%3Ealert(1)%3C/script%3E")[1])
        finally:
            runtime.close()
