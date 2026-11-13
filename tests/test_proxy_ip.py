import http.client
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import archive_store
import auth_store
import server


class ProxyAddressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); self.port = sock.getsockname()[1]
        self.patches = [patch.object(archive_store, "DB_PATH", root / "archive.db"), patch.object(auth_store, "DB_PATH", root / "archive.db"),
                        patch.object(server, "DEPLOYMENT_MODE", "hosted"), patch.object(server, "AUTH_RATE_LIMIT", 3)]
        for item in self.patches: item.start()
        auth_store.initialize()
        self.httpd = server.HTTPServer(("127.0.0.1", self.port), server.SeedReflectionAPIHandler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown(); self.httpd.server_close()
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    def login(self, forwarded=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if forwarded: headers["X-Forwarded-For"] = forwarded
        connection.request("POST", "/api/v2/auth/login", body=json.dumps({"email": "nobody@example.com", "password": "x"}), headers=headers)
        status = connection.getresponse().status; connection.close(); return status

    def test_without_a_trusted_proxy_a_forged_header_cannot_dodge_the_limit(self):
        with patch.object(server, "TRUST_PROXY", False):
            codes = [self.login(f"10.0.0.{i}") for i in range(5)]
        self.assertEqual(codes, [401, 401, 401, 429, 429])

    def test_behind_the_proxy_each_visitor_has_their_own_limit(self):
        with patch.object(server, "TRUST_PROXY", True):
            first = [self.login("203.0.113.7") for _ in range(4)]
            other = self.login("203.0.113.8")                                   # a different real visitor is unaffected
        self.assertEqual(first, [401, 401, 401, 429])
        self.assertEqual(other, 401)

    def test_only_the_proxy_added_address_counts_and_junk_falls_back_to_the_connection(self):
        with patch.object(server, "TRUST_PROXY", True):
            a = [self.login("1.1.1.1, 203.0.113.9") for _ in range(4)]          # the last entry is the one the proxy appended
            b = self.login("9.9.9.9, 203.0.113.9")                               # same real visitor, different forged prefix: still limited
            junk = [self.login("not-an-ip") for _ in range(4)]                   # falls back to the connection address (the proxy), own bucket
        self.assertEqual(a, [401, 401, 401, 429]); self.assertEqual(b, 429)
        self.assertEqual(junk, [401, 401, 401, 429])


if __name__ == "__main__":
    unittest.main()
