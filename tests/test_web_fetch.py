import json
import os
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(__file__))
import web_fetch
from web_fetch import FetchError, fetch_page, as_document

PAGE = b"<html><head><title>Beta pricing &amp; plans</title><style>x{}</style></head><body><nav>menu</nav><h1>Plans</h1><p>Start at $19 a month.</p><script>evil()</script></body></html>"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass

    def do_GET(self):
        routes = {
            "/page": (200, "text/html; charset=utf-8", PAGE, {}),
            "/text": (200, "text/plain", b"plain words", {}),
            "/image": (200, "image/png", b"\x89PNG", {}),
            "/missing": (404, "text/html", b"no", {}),
            "/big": (200, "text/html", b"a" * (web_fetch.MAX_BYTES + 10), {}),
            "/redirect": (302, "text/html", b"", {"Location": "/page"}),
            "/loop": (302, "text/html", b"", {"Location": "/loop"}),
            "/to-internal": (302, "text/html", b"", {"Location": "http://169.254.169.254/latest/meta-data"}),
        }
        status, kind, body, headers = routes.get(self.path, (404, "text/html", b"", {}))
        self.send_response(status); self.send_header("Content-Type", kind); self.send_header("Content-Length", str(len(body)))
        for key, value in headers.items(): self.send_header(key, value)
        self.end_headers(); self.wfile.write(body)


class FunctionalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = HTTPServer(("127.0.0.1", 0), Handler); cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close()

    def get(self, path): return fetch_page(self.base + path, allow_private=True)

    def test_reads_a_page_keeps_the_address_and_strips_scripts(self):
        page = self.get("/page")
        self.assertEqual(page["title"], "Beta pricing & plans")
        name, content = as_document(page)
        text = content.decode()
        self.assertTrue(name.startswith("web-127.0.0.1-beta-pricing-plans") and name.endswith(".md"))
        self.assertIn("Source: " + self.base + "/page", text)
        self.assertIn("Retrieved: ", text)
        self.assertIn("Start at $19 a month.", text)
        self.assertNotIn("evil()", text)

    def test_follows_redirects_and_reports_the_final_address(self):
        self.assertTrue(self.get("/redirect")["final_url"].endswith("/page"))

    def test_refuses_loops_wrong_types_errors_and_oversize_pages(self):
        for path, fragment in (("/loop", "too many"), ("/image", "readable document"), ("/missing", "error (404)"), ("/big", "too large")):
            with self.assertRaises(FetchError, msg=path) as caught:
                self.get(path)
            self.assertIn(fragment, str(caught.exception))
        self.assertEqual(self.get("/text")["kind"], "text/plain")


class GuardTests(unittest.TestCase):
    def refused(self, url, fragment=None):
        with self.assertRaises(FetchError, msg=url) as caught:
            fetch_page(url)
        if fragment:
            self.assertIn(fragment, str(caught.exception), url)

    def test_internal_and_special_addresses_are_refused(self):
        for url in ("http://127.0.0.1/", "http://localhost/", "http://[::1]/", "http://169.254.169.254/latest/meta-data/",
                    "http://10.0.0.5/", "http://192.168.1.1/", "http://172.16.0.1/", "http://0.0.0.0/", "http://100.64.0.1/",
                    "http://2130706433/", "http://0x7f000001/", "http://[::ffff:127.0.0.1]/", "http://[fe80::1]/"):
            self.refused(url, "private or internal")

    def test_only_http_and_https_on_standard_ports_without_credentials(self):
        self.refused("file:///etc/passwd", "http://")
        self.refused("ftp://example.com/", "http://")
        self.refused("gopher://example.com/", "http://")
        self.refused("", "http://")
        self.refused("http://user:pass@example.com/", "username or password")
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 8080))]):
            self.refused("http://example.com:8080/", "standard web ports")

    def test_a_name_that_resolves_to_an_internal_address_is_refused(self):
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("10.0.0.5", 80))]):
            self.refused("http://looks-public.example/", "private or internal")
        mixed = [(2, 1, 6, "", ("93.184.216.34", 80)), (2, 1, 6, "", ("127.0.0.1", 80))]
        with patch("socket.getaddrinfo", return_value=mixed):
            self.refused("http://half-public.example/", "private or internal")

    def test_a_redirect_to_an_internal_address_is_stopped_at_that_hop(self):
        public = [(2, 1, 6, "", ("93.184.216.34", 80))]
        hops = iter([(302, "http://169.254.169.254/latest/meta-data", None, None)])
        with patch("socket.getaddrinfo", side_effect=lambda host, *a, **k: public if host == "example.test" else __import__("socket").getaddrinfo.__wrapped__(host) if False else [(2, 1, 6, "", (host, 80))]), \
             patch.object(web_fetch, "_once", side_effect=lambda *a, **k: next(hops)):
            self.refused("http://example.test/start", "private or internal")

    def test_the_connection_goes_to_the_address_that_was_checked(self):
        seen = {}
        def fake_once(parsed, port, ip, timeout):
            seen["ip"] = ip
            return 200, "text/plain", b"ok", "text/plain"
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 80))]), patch.object(web_fetch, "_once", side_effect=fake_once):
            fetch_page("http://example.test/")
        self.assertEqual(seen["ip"], "93.184.216.34")


class RouteTests(unittest.TestCase):
    def test_route_refuses_internal_addresses_requires_sign_in_and_imports_a_page(self):
        from test_unified_runtime import UnifiedRuntime
        httpd = HTTPServer(("127.0.0.1", 0), Handler); threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            runtime = UnifiedRuntime("local")
            try:
                status, refused = runtime.request("POST", "/api/v2/web/import", {"url": base + "/page"})
                self.assertEqual(status, 400); self.assertIn("cannot be added" if "private" in refused["error"] else "ports", refused["error"])   # default: nothing internal
            finally:
                runtime.close()
            runtime = UnifiedRuntime("local", {"SEED_REFLECTIONS_WEB_ALLOW_PRIVATE": "1"})
            try:
                status, accepted = runtime.request("POST", "/api/v2/web/import", {"url": base + "/page"})
                self.assertEqual((status, accepted["title"]), (202, "Beta pricing & plans"))
                for _ in range(60):
                    _, job = runtime.request("GET", f"/api/v2/imports/jobs/{accepted['job_id']}")
                    if job.get("status") in ("complete", "failed"): break
                    time.sleep(.1)
                self.assertEqual(job["status"], "complete", job)
                _, listing = runtime.request("GET", "/api/v2/conversations")
                self.assertEqual([c["title"] for c in listing["conversations"]], ["web-127.0.0.1-beta-pricing-plans"])
                self.assertEqual(runtime.request("POST", "/api/v2/web/import", {"url": "file:///etc/passwd"})[0], 400)
            finally:
                runtime.close()
            runtime = UnifiedRuntime("hosted", {"SEED_REFLECTIONS_WEB_ALLOW_PRIVATE": "1"})                      # hosted ignores the switch
            try:
                self.assertEqual(runtime.request("POST", "/api/v2/web/import", {"url": base + "/page"})[0], 401)  # needs sign-in
                _, user = runtime.request("POST", "/api/v2/auth/signup", {"name": "W", "email": "w@example.com", "password": "strong-password-123"})
                status, refused = runtime.request("POST", "/api/v2/web/import", {"url": base + "/page"}, token=user["access_token"])
                self.assertEqual(status, 400); self.assertIn("ports", refused["error"])                           # the local-only switch is ignored here
            finally:
                runtime.close()
        finally:
            httpd.shutdown(); httpd.server_close()


if __name__ == "__main__":
    unittest.main()
