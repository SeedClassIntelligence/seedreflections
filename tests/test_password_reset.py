import http.client
import json
import os
import re
import socket
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import archive_store
import auth_store
import mailer
import server

PASSWORD = "strong-password-123"


class AuthDb(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(archive_store, "DB_PATH", Path(self.temp.name) / "archive.db"), patch.object(auth_store, "DB_PATH", Path(self.temp.name) / "archive.db")]
        for item in self.patches: item.start()
        auth_store.initialize()

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()


class ResetStoreTests(AuthDb):
    def test_a_link_works_once_changes_the_password_and_signs_everything_out(self):
        user = auth_store.signup("Ann", "ann@example.com", PASSWORD, "hosted"); old_session = user["access_token"]
        made = auth_store.create_password_reset(" Ann@Example.com ")
        self.assertNotIn(made["token"].encode(), (Path(self.temp.name) / "archive.db").read_bytes())          # only a digest is stored
        auth_store.reset_password(made["token"], "a-brand-new-password-9")
        with self.assertRaises(ValueError): auth_store.login("ann@example.com", PASSWORD)
        self.assertTrue(auth_store.login("ann@example.com", "a-brand-new-password-9"))
        self.assertIsNone(auth_store.authenticate(old_session))                                              # the old session is gone
        with self.assertRaises(ValueError): auth_store.reset_password(made["token"], "another-new-password-1")  # single use

    def test_unknown_email_wrong_token_short_password_and_expiry_are_refused(self):
        auth_store.signup("Ann", "ann@example.com", PASSWORD, "hosted")
        self.assertIsNone(auth_store.create_password_reset("nobody@example.com"))
        self.assertIsNone(auth_store.create_password_reset("local@seedreflections.internal"))                 # the built-in local owner has no password
        made = auth_store.create_password_reset("ann@example.com")
        for bad in ("", "nope", made["token"][:-1] + "x"):
            with self.assertRaises(ValueError): auth_store.reset_password(bad, "a-brand-new-password-9")
        with self.assertRaises(ValueError): auth_store.reset_password(made["token"], "short")
        self.assertTrue(auth_store.login("ann@example.com", PASSWORD))                                       # nothing changed yet
        with patch.object(auth_store, "RESET_MINUTES", -1):
            late = auth_store.create_password_reset("ann@example.com")
        with self.assertRaises(ValueError): auth_store.reset_password(late["token"], "a-brand-new-password-9")

    def test_a_newer_link_cancels_the_older_one_and_deleting_the_account_removes_them(self):
        user = auth_store.signup("Ann", "ann@example.com", PASSWORD, "hosted")
        first = auth_store.create_password_reset("ann@example.com"); second = auth_store.create_password_reset("ann@example.com")
        with self.assertRaises(ValueError): auth_store.reset_password(first["token"], "a-brand-new-password-9")
        auth_store.delete_account(user["user"]["id"], PASSWORD)
        with self.assertRaises(ValueError): auth_store.reset_password(second["token"], "a-brand-new-password-9")


class SmtpSink(threading.Thread):
    """A tiny SMTP server that records what it is sent."""
    def __init__(self):
        super().__init__(daemon=True); self.sock = socket.socket(); self.sock.bind(("127.0.0.1", 0)); self.sock.listen(1); self.port = self.sock.getsockname()[1]; self.mail = []

    def run(self):
        while True:
            try: conn, _ = self.sock.accept()
            except OSError: return
            f = conn.makefile("rwb"); send = lambda line: (f.write(line.encode() + b"\r\n"), f.flush())
            send("220 sink ready"); data = None; lines = []
            while True:
                line = f.readline().decode().rstrip("\r\n")
                if not line and data is None: break
                if data is not None:
                    if line == ".": self.mail.append("\n".join(lines)); data = None; send("250 queued")
                    else: lines.append(line)
                    continue
                cmd = line.split(" ")[0].upper()
                if cmd == "EHLO": send("250 sink")
                elif cmd == "DATA": data = []; lines = []; send("354 go")
                elif cmd == "QUIT": send("221 bye"); break
                else: send("250 ok")
            conn.close()


class MailerTests(unittest.TestCase):
    def test_sends_through_smtp_and_reports_failures_without_secrets(self):
        sink = SmtpSink(); sink.start()
        env = {"SEED_REFLECTIONS_SMTP_HOST": "127.0.0.1", "SEED_REFLECTIONS_SMTP_PORT": str(sink.port), "SEED_REFLECTIONS_SMTP_SECURITY": "none",
               "SEED_REFLECTIONS_SMTP_FROM": "SeedReflections <noreply@example.com>", "SEED_REFLECTIONS_SMTP_PASSWORD": "super-secret-pw"}
        with patch.dict(os.environ, env):
            self.assertTrue(mailer.configured())
            mailer.send("ann@example.com", "Hello", "Body text")
            self.assertTrue(any("Subject: Hello" in m and "Body text" in m and "To: ann@example.com" in m for m in sink.mail))
        with patch.dict(os.environ, {**env, "SEED_REFLECTIONS_SMTP_PORT": "1"}):
            with self.assertRaises(mailer.MailError) as caught: mailer.send("ann@example.com", "Hello", "Body")
            self.assertNotIn("super-secret-pw", str(caught.exception))
        with patch.dict(os.environ, {"SEED_REFLECTIONS_SMTP_HOST": "", "SEED_REFLECTIONS_SMTP_FROM": ""}):
            self.assertFalse(mailer.configured())


class RouteTests(AuthDb):
    def setUp(self):
        super().setUp()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); self.port = sock.getsockname()[1]
        self.sent = []
        self.more = [patch.object(server, "DEPLOYMENT_MODE", "hosted"), patch.object(server, "PUBLIC_ORIGIN", "https://app.example.com"),
                     patch.object(server, "AUTH_RATE_LIMIT", 50), patch.object(server.mailer, "configured", lambda: True),
                     patch.object(server.mailer, "send", lambda to, subject, body: self.sent.append((to, subject, body)))]
        for item in self.more: item.start()
        self.httpd = server.HTTPServer(("127.0.0.1", self.port), server.SeedReflectionAPIHandler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown(); self.httpd.server_close()
        for item in reversed(self.more): item.stop()
        super().tearDown()

    def post(self, path, body):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request("POST", path, body=json.dumps(body), headers={"Content-Type": "application/json"})
        response = connection.getresponse(); data = json.loads(response.read() or b"{}"); connection.close(); return response.status, data

    def wait_for_mail(self, count=1):
        for _ in range(50):
            if len(self.sent) >= count: break
            time.sleep(.05)

    def test_forgot_answers_identically_emails_only_real_accounts_and_the_link_resets(self):
        self.post("/api/v2/auth/signup", {"name": "Ann", "email": "ann@example.com", "password": PASSWORD})
        known = self.post("/api/v2/auth/forgot", {"email": "ann@example.com"}); unknown = self.post("/api/v2/auth/forgot", {"email": "nobody@example.com"})
        self.assertEqual(known, unknown)
        self.wait_for_mail(); time.sleep(.2)
        self.assertEqual([m[0] for m in self.sent], ["ann@example.com"])                                    # exactly one email, to the real account
        link = re.search(r"https://app\.example\.com/auth\.html\?mode=reset#token=([\w-]+)", self.sent[0][2])
        self.assertTrue(link, self.sent[0][2])                                                              # the token rides in the fragment, which browsers never send to servers
        token = link.group(1)
        self.assertEqual(self.post("/api/v2/auth/reset", {"token": token, "password": "short"})[0], 400)
        self.assertEqual(self.post("/api/v2/auth/reset", {"token": token, "password": "a-brand-new-password-9"})[0], 200)
        self.assertEqual(self.post("/api/v2/auth/reset", {"token": token, "password": "yet-another-password-1"})[0], 400)
        self.assertEqual(self.post("/api/v2/auth/login", {"email": "ann@example.com", "password": PASSWORD})[0], 401)
        self.assertEqual(self.post("/api/v2/auth/login", {"email": "ann@example.com", "password": "a-brand-new-password-9"})[0], 200)

    def test_without_email_set_up_the_server_says_so_instead_of_pretending(self):
        with patch.object(server.mailer, "configured", lambda: False):
            self.assertEqual(self.post("/api/v2/auth/forgot", {"email": "ann@example.com"})[0], 503)

    def test_local_mode_has_no_passwords_to_reset(self):
        with patch.object(server, "DEPLOYMENT_MODE", "local"):
            self.assertEqual(self.post("/api/v2/auth/forgot", {"email": "ann@example.com"})[0], 409)
            self.assertEqual(self.post("/api/v2/auth/reset", {"token": "x", "password": "a-brand-new-password-9"})[0], 409)

    def test_requests_are_rate_limited(self):
        with patch.object(server, "AUTH_RATE_LIMIT", 2):
            self.assertEqual([self.post("/api/v2/auth/forgot", {"email": "ann@example.com"})[0] for _ in range(3)], [200, 200, 429])

    def test_readiness_flags_missing_email_only_when_hosted(self):
        with patch.object(server.mailer, "configured", lambda: False):
            check = next(c for c in server.production_readiness()["checks"] if c["name"] == "password_reset_email")
        self.assertFalse(check["passed"])
        with patch.object(server, "DEPLOYMENT_MODE", "local"):
            self.assertTrue(next(c for c in server.production_readiness()["checks"] if c["name"] == "password_reset_email")["passed"])


if __name__ == "__main__":
    unittest.main()
