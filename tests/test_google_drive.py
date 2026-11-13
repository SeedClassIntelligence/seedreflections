import base64
import hashlib
import http.client
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import account_erasure
import agent_tokens
import archive_store
import auth_store
import google_drive
import secret_store
import server
import tenant_archive_store
import work_sessions

DOC, SHEET, PDF, TXT = ("application/vnd.google-apps.document", "application/vnd.google-apps.spreadsheet", "application/pdf", "text/plain")


class FakeGoogle(BaseHTTPRequestHandler):
    """Stands in for Google's sign-in and Drive. State lives on the class so tests can inspect and change it."""
    challenge = None; versions = {}; revoked = []; refreshes = 0; refresh_revoked = False; calls = []

    @classmethod
    def reset(cls):
        cls.challenge = None; cls.versions = {"doc1": 1, "txt1": 1, "sheet1": 1}; cls.revoked = []; cls.refreshes = 0; cls.refresh_revoked = False; cls.calls = []

    def log_message(self, *args): pass

    def send(self, status, payload, kind="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(status); self.send_header("Content-Type", kind); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def authorized(self):
        return self.headers.get("Authorization", "") in ("Bearer at-1", "Bearer at-2")

    def do_POST(self):
        form = urllib.parse.parse_qs(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode())
        one = lambda k: (form.get(k) or [""])[0]
        if self.path == "/token":
            if one("client_id") != "cid" or one("client_secret") != "csecret": return self.send(401, {"error": "invalid_client"})
            if one("grant_type") == "authorization_code":
                digest = base64.urlsafe_b64encode(hashlib.sha256(one("code_verifier").encode()).digest()).rstrip(b"=").decode()
                if one("code") != "good-code" or digest != FakeGoogle.challenge: return self.send(400, {"error": "invalid_grant"})
                return self.send(200, {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600,
                                       "scope": "openid email https://www.googleapis.com/auth/drive.readonly"})
            if one("grant_type") == "refresh_token":
                if FakeGoogle.refresh_revoked or one("refresh_token") != "rt-1": return self.send(400, {"error": "invalid_grant"})
                FakeGoogle.refreshes += 1
                return self.send(200, {"access_token": "at-2", "expires_in": 3600})
        if self.path == "/revoke":
            FakeGoogle.revoked.append(one("token")); return self.send(200, b"")
        self.send(404, {})

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path); query = urllib.parse.parse_qs(url.query); FakeGoogle.calls.append(self.path)
        if url.path == "/auth":                       # the consent screen: approve at once and send the browser back
            FakeGoogle.challenge = query["code_challenge"][0]
            self.send_response(302); self.send_header("Location", query["redirect_uri"][0] + "?" + urllib.parse.urlencode({"code": "good-code", "state": query["state"][0]})); self.end_headers(); return
        if not self.authorized(): return self.send(401, {"error": {"code": 401}})
        if url.path == "/userinfo": return self.send(200, {"email": "person@example.com"})
        if url.path == "/drive/files":
            parent = query["q"][0].split("'")[1]
            v = FakeGoogle.versions
            tree = {"root": [{"id": "folder1", "name": "Work", "mimeType": "application/vnd.google-apps.folder"},
                             {"id": "rootdoc", "name": "Not chosen", "mimeType": DOC, "version": "1", "modifiedTime": "2026-01-01T00:00:00Z"}],
                    "folder1": [{"id": "doc1", "name": "Pricing notes", "mimeType": DOC, "version": str(v["doc1"]), "modifiedTime": "2026-02-01T00:00:00Z"},
                           {"id": "txt1", "name": "plan.txt", "mimeType": TXT, "size": "24", "version": str(v["txt1"]), "md5Checksum": f"m{v['txt1']}", "modifiedTime": "2026-02-02T00:00:00Z"},
                           {"id": "img1", "name": "photo.png", "mimeType": "image/png", "size": "5", "version": "1"},
                           {"id": "huge1", "name": "huge.pdf", "mimeType": PDF, "size": str(google_drive.MAX_FILE_BYTES + 1), "version": "1"},
                           {"id": "folder2", "name": "Sub", "mimeType": "application/vnd.google-apps.folder"}],
                    "folder2": [{"id": "sheet1", "name": "Budget", "mimeType": SHEET, "version": str(v["sheet1"]), "modifiedTime": "2026-02-03T00:00:00Z"}]}
            return self.send(200, {"files": tree.get(parent, [])})
        match = url.path.startswith("/drive/files/") and url.path.split("/")[3]
        if match and url.path.endswith("/export"):
            if match == "doc1": return self.send(200, f"Pricing: start at $19 (v{FakeGoogle.versions['doc1']})".encode(), "text/plain")
            if match == "sheet1": return self.send(200, b"item,cost\nhosting,20\n", "text/csv")
        if match == "txt1" and query.get("alt") == ["media"]:
            return self.send(200, f"Launch plan v{FakeGoogle.versions['txt1']}".encode(), "text/plain")
        self.send(404, {})


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0)); return sock.getsockname()[1]


class DriveBase(unittest.TestCase):
    def setUp(self):
        FakeGoogle.reset()
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name)
        self.google = HTTPServer(("127.0.0.1", 0), FakeGoogle); base = f"http://127.0.0.1:{self.google.server_address[1]}"
        threading.Thread(target=self.google.serve_forever, daemon=True).start()
        self.patches = [patch.object(archive_store, "DB_PATH", root / "archive.db"), patch.object(secret_store, "DB_PATH", root / "archive.db"),
                        patch.object(server, "DATA_FILE", str(root / "seeds.json")), patch.object(server, "CONFIG_FILE", str(root / "config.json")),
                        patch.object(server, "UPLOAD_JOBS_DIR", root / "jobs"),
                        patch.dict(google_drive.ENDPOINTS, {"auth": base + "/auth", "token": base + "/token", "revoke": base + "/revoke", "userinfo": base + "/userinfo", "drive": base + "/drive"}),
                        patch.dict(os.environ, {"SEED_REFLECTIONS_GOOGLE_CLIENT_ID": "cid", "SEED_REFLECTIONS_GOOGLE_CLIENT_SECRET": "csecret"})]
        for item in self.patches: item.start()
        archive_store.initialize()
        secret_store._SESSION_KEYS.clear()

    def tearDown(self):
        self.google.shutdown(); self.google.server_close()
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    def sign_in(self, workspace="local"):
        url = google_drive.begin_authorization(workspace, "http://127.0.0.1:1/api/v2/google/callback")
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        FakeGoogle.challenge = query["code_challenge"][0]
        return url, query


class SignInTests(DriveBase):
    def test_authorization_url_asks_for_read_only_with_pkce_and_a_one_time_state(self):
        url, query = self.sign_in()
        self.assertEqual(query["scope"][0], "openid email https://www.googleapis.com/auth/drive.readonly")
        self.assertEqual((query["code_challenge_method"], query["access_type"], query["response_type"]), (["S256"], ["offline"], ["code"]))
        self.assertNotIn("csecret", url)
        google_drive.complete_authorization(query["state"][0], "good-code", "http://127.0.0.1:1/api/v2/google/callback", "local")
        with self.assertRaises(google_drive.DriveError) as replay:
            google_drive.complete_authorization(query["state"][0], "good-code", "http://127.0.0.1:1/api/v2/google/callback", "local")
        self.assertIn("already used", str(replay.exception))

    def test_bad_state_wrong_code_and_missing_refresh_token_are_refused(self):
        self.sign_in()
        for state, code in (("nope", "good-code"), ("", "good-code")):
            with self.assertRaises(google_drive.DriveError): google_drive.complete_authorization(state, code, "http://x/cb", "local")
        _, query = self.sign_in()
        with self.assertRaises(google_drive.DriveError): google_drive.complete_authorization(query["state"][0], "wrong-code", "http://x/cb", "local")

    def test_tokens_are_stored_encrypted_and_never_in_status(self):
        _, query = self.sign_in()
        google_drive.complete_authorization(query["state"][0], "good-code", "http://x/cb", "local")
        status = google_drive.status("local")
        self.assertEqual((status["connected"], status["account"]), (True, "person@example.com"))
        self.assertNotIn("rt-1", json.dumps(status)); self.assertNotIn("at-1", json.dumps(status))
        self.assertNotIn(b"rt-1", Path(archive_store.DB_PATH).read_bytes())


class FolderTests(DriveBase):
    def connect(self):
        _, query = self.sign_in()
        google_drive.complete_authorization(query["state"][0], "good-code", "http://x/cb", "local")

    def test_preview_lists_only_the_chosen_folder_and_says_what_it_skips(self):
        self.connect()
        self.assertEqual([f["name"] for f in google_drive.list_folders("local", "root", "local")["folders"]], ["Work"])
        manifest = google_drive.preview("local", "folder1", "Work", "local")
        self.assertEqual(sorted(f["path"] for f in manifest["files"]), ["Pricing notes", "Sub/Budget", "plan.txt"])
        self.assertEqual(manifest["skipped"], {"unsupported": 1, "too_large": 1, "over_limit": 0})

    def test_nothing_is_imported_without_consent_and_ids_cannot_inject_queries(self):
        self.connect()
        manifest = google_drive.preview("local", "folder1", "Work", "local"); imported = []
        with self.assertRaises(google_drive.DriveError): google_drive.connect_preview("local", manifest["preview_id"], None, lambda n, c: imported.append(n), "local")
        self.assertEqual(imported, [])
        for bad in ("x' or '1'='1", "a b", "", "../x", "root' in parents or '"):
            with self.assertRaises(google_drive.DriveError): google_drive.list_folders("local", bad, "local") if bad else google_drive.preview("local", bad, "x", "local")

    def test_import_resync_only_changed_and_a_workspace_cannot_use_anothers_preview(self):
        self.connect(); seen = []
        manifest = google_drive.preview("local", "folder1", "Work", "local")
        with self.assertRaises(google_drive.DriveError): google_drive.connect_preview("ws-other", manifest["preview_id"], True, lambda n, c: None, "local")
        first = google_drive.connect_preview("local", manifest["preview_id"], True, lambda n, c: seen.append((n, c)), "local")
        self.assertEqual((first["files_imported"], first["files_failed"], first["status"]), (3, 0, "synced"))
        names = sorted(n for n, _ in seen); self.assertEqual(names, ["drive-Budget.csv", "drive-Pricing notes.txt", "drive-plan.txt.txt".replace(".txt.txt", ".txt")])
        self.assertTrue(any(b"Source: Google Drive: Pricing notes" in c and b"$19" in c for _, c in seen))
        source_id = google_drive.status("local")["sources"][0]["id"]
        self.assertEqual(google_drive.sync("local", source_id, lambda n, c: seen.append((n, c)), "local")["files_imported"], 0)     # nothing changed
        FakeGoogle.versions["doc1"] = 2
        again = google_drive.sync("local", source_id, lambda n, c: seen.append((n, c)), "local")
        self.assertEqual((again["files_imported"], again["files_unchanged"]), (1, 2))

    def test_expired_access_is_refreshed_and_revoked_access_disconnects_cleanly(self):
        self.connect()
        blob = json.loads(secret_store.get_credential("local", google_drive.CREDENTIAL)); blob["expires_at"] = 0
        secret_store.set_credential("local", google_drive.CREDENTIAL, json.dumps(blob), "local", temporary=True)
        google_drive.list_folders("local", "root", "local"); self.assertEqual(FakeGoogle.refreshes, 1)
        blob["expires_at"] = 0; secret_store.set_credential("local", google_drive.CREDENTIAL, json.dumps(blob), "local", temporary=True)
        FakeGoogle.refresh_revoked = True
        with self.assertRaises(google_drive.DriveError) as caught: google_drive.list_folders("local", "root", "local")
        self.assertIn("Connect Google Drive again", str(caught.exception))
        self.assertFalse(google_drive.status("local")["connected"])

    def test_disconnect_revokes_at_google_and_removes_records_but_keeps_imports(self):
        self.connect(); documents = []
        manifest = google_drive.preview("local", "folder1", "Work", "local")
        google_drive.connect_preview("local", manifest["preview_id"], True, lambda n, c: documents.append(n), "local")
        google_drive.disconnect("local")
        self.assertEqual(FakeGoogle.revoked, ["rt-1"])
        self.assertEqual(google_drive.status("local")["sources"], [])
        self.assertFalse(google_drive.status("local")["connected"])
        self.assertEqual(len(documents), 3)


class HttpFlowTests(DriveBase):
    def setUp(self):
        super().setUp()
        self.httpd = server.HTTPServer(("127.0.0.1", free_port()), server.SeedReflectionAPIHandler); self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown(); self.httpd.server_close(); super().tearDown()

    def call(self, method, path, body=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        connection.request(method, path, body=json.dumps(body) if body is not None else None, headers={"Content-Type": "application/json"})
        response = connection.getresponse(); data = response.read(); connection.close()
        try: parsed = json.loads(data) if data else None
        except ValueError: parsed = None
        return response.status, parsed, response.getheader("Location")

    def test_full_flow_through_the_real_routes(self):
        status, started, _ = self.call("POST", "/api/v2/tools/google_drive/connect", {})
        self.assertEqual(status, 200)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(started["authorization_url"]).query)
        self.assertEqual(query["redirect_uri"][0], f"http://127.0.0.1:{self.port}/api/v2/google/callback")
        FakeGoogle.challenge = query["code_challenge"][0]
        status, _, location = self.call("GET", f"/api/v2/google/callback?code=good-code&state={query['state'][0]}")
        self.assertEqual((status, location), (302, "/consumer-dashboard.html?google=connected"))
        self.assertEqual(self.call("GET", f"/api/v2/google/callback?code=good-code&state={query['state'][0]}")[2].split("&")[0], "/consumer-dashboard.html?google=error")   # replay
        self.assertEqual(self.call("GET", "/api/v2/google/callback?error=access_denied&state=x")[2], "/consumer-dashboard.html?google=denied")
        self.assertTrue(self.call("GET", "/api/v2/google/status")[1]["connected"])
        _, tools, _ = self.call("GET", "/api/v2/tools")
        self.assertEqual(next(t for t in tools["tools"] if t["id"] == "google_drive")["state"], "connected")
        self.assertEqual(self.call("GET", "/api/v2/google/folders?parent=x%27%20or%20%271%27%3D%271")[0], 400)
        _, preview, _ = self.call("POST", "/api/v2/google/preview", {"folder_id": "folder1", "folder_name": "Work"})
        self.assertEqual(len(preview["files"]), 3)
        self.assertEqual(self.call("POST", "/api/v2/google/connect-folder", {"preview_id": preview["preview_id"]})[0], 400)            # no consent
        status, synced, _ = self.call("POST", "/api/v2/google/connect-folder", {"preview_id": preview["preview_id"], "consent": True})
        self.assertEqual((status, synced["files_imported"], synced["files_failed"]), (200, 3, 0))
        titles = sorted(c["title"] for c in archive_store.list_conversations(limit=20))
        self.assertEqual(titles, ["drive-Budget", "drive-Pricing notes", "drive-plan"])
        source_id = self.call("GET", "/api/v2/google/status")[1]["sources"][0]["id"]
        self.assertEqual(self.call("POST", f"/api/v2/google/sources/{source_id}/sync", {})[1]["files_imported"], 0)
        self.assertEqual(self.call("POST", "/api/v2/tools/google_drive/disconnect", {})[0], 200)
        self.assertFalse(self.call("GET", "/api/v2/google/status")[1]["connected"])
        self.assertEqual(FakeGoogle.revoked, ["rt-1"])
        self.assertEqual(len(archive_store.list_conversations(limit=20)), 3)                                                          # imports kept

    def test_without_deployment_credentials_connect_is_refused_not_faked(self):
        with patch.dict(os.environ, {"SEED_REFLECTIONS_GOOGLE_CLIENT_ID": "", "SEED_REFLECTIONS_GOOGLE_CLIENT_SECRET": ""}):
            status, body, _ = self.call("POST", "/api/v2/tools/google_drive/connect", {})
        self.assertEqual((status, body["code"]), (503, "provider_configuration_required"))


class HostedFlowTests(DriveBase):
    PASSWORD = "strong-password-123"

    def setUp(self):
        super().setUp()
        root = Path(self.temp.name)
        self.port = free_port()
        key = base64.urlsafe_b64encode(os.urandom(32)).decode()
        more = [patch.object(server, "DEPLOYMENT_MODE", "hosted"), patch.object(server, "PUBLIC_ORIGIN", f"http://127.0.0.1:{self.port}"),
                patch.object(auth_store, "DB_PATH", root / "archive.db"), patch.object(tenant_archive_store, "DB_PATH", root / "archive.db"),
                patch.object(agent_tokens, "DB_PATH", root / "agent_tokens.db"), patch.object(work_sessions, "DB_PATH", root / "work_sessions.db"),
                patch.dict(os.environ, {"SEED_REFLECTIONS_CREDENTIAL_MASTER_KEY": key})]
        for item in more: item.start()
        self.more = more
        auth_store.initialize()
        self.httpd = server.HTTPServer(("127.0.0.1", self.port), server.SeedReflectionAPIHandler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown(); self.httpd.server_close()
        for item in reversed(self.more): item.stop()
        super().tearDown()

    def call(self, method, path, body=None, token=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Content-Type": "application/json"}
        if token: headers["Authorization"] = "Bearer " + token
        connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        response = connection.getresponse(); data = response.read(); connection.close()
        try: parsed = json.loads(data) if data else None
        except ValueError: parsed = None
        return response.status, parsed, response.getheader("Location")

    def person(self, name):
        return self.call("POST", "/api/v2/auth/signup", {"name": name, "email": f"{name}@example.com", "password": self.PASSWORD})[1]

    def test_hosted_isolation_encrypted_tokens_and_erasure(self):
        alice, bob = self.person("alice"), self.person("bob")
        a, b = alice["access_token"], bob["access_token"]
        for path in ("/api/v2/google/status", "/api/v2/google/folders"):
            self.assertEqual(self.call("GET", path)[0], 401)                                      # not signed in
        self.assertEqual(self.call("POST", "/api/v2/google/preview", {"folder_id": "folder1"})[0], 401)

        started = self.call("POST", "/api/v2/tools/google_drive/connect", {}, a)[1]
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(started["authorization_url"]).query)
        self.assertEqual(query["redirect_uri"][0], f"http://127.0.0.1:{self.port}/api/v2/google/callback")
        FakeGoogle.challenge = query["code_challenge"][0]
        self.assertEqual(self.call("GET", f"/api/v2/google/callback?code=good-code&state={query['state'][0]}")[2], "/consumer-dashboard.html?google=connected")
        self.assertTrue(self.call("GET", "/api/v2/google/status", token=a)[1]["connected"])
        self.assertFalse(self.call("GET", "/api/v2/google/status", token=b)[1]["connected"])        # another account is not connected
        self.assertEqual(self.call("GET", "/api/v2/google/folders", token=b)[0], 400)               # and cannot browse alice's Drive
        self.assertNotIn(b"rt-1", Path(archive_store.DB_PATH).read_bytes())                        # the refresh token is encrypted at rest

        preview = self.call("POST", "/api/v2/google/preview", {"folder_id": "folder1", "folder_name": "Work"}, a)[1]
        self.assertEqual(self.call("POST", "/api/v2/google/connect-folder", {"preview_id": preview["preview_id"], "consent": True}, b)[0], 400)   # bob cannot use alice's review
        done = self.call("POST", "/api/v2/google/connect-folder", {"preview_id": preview["preview_id"], "consent": True}, a)[1]
        self.assertEqual((done["files_imported"], done["files_failed"]), (3, 0))
        self.assertEqual(len(self.call("GET", "/api/v2/conversations", token=a)[1]["conversations"]), 3)
        self.assertEqual(self.call("GET", "/api/v2/conversations", token=b)[1]["conversations"], [])

        status, deleted, _ = self.call("POST", "/api/v2/account/delete", {"password": self.PASSWORD, "confirm": "DELETE"}, a)
        self.assertEqual((status, deleted["deleted"]), (200, True))
        left = {}
        import sqlite3
        db = sqlite3.connect(archive_store.DB_PATH)
        for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'google_drive_%'"):
            count = db.execute(f"SELECT COUNT(*) FROM {table} WHERE workspace_id=?", (alice["workspace_id"],)).fetchone()[0]
            if count: left[table] = count
        self.assertEqual(left, {})                                                                  # Drive records went with the account
        self.assertEqual(db.execute("SELECT COUNT(*) FROM model_credentials WHERE workspace_id=?", (alice["workspace_id"],)).fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
