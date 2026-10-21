import unittest
import json
import os
import sys
import tempfile
import socket
import threading
import urllib.request
import urllib.error
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import server

def get_free_port():
    s = socket.socket()
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    return port

class TestTenantManagement(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_db_path = os.path.join(self.temp_dir.name, "seeds_test.json")
        self.original_data_file = server.DATA_FILE
        server.DATA_FILE = self.temp_db_path

        self.temp_config_path = os.path.join(self.temp_dir.name, "config_test.json")
        self.original_config_file = server.CONFIG_FILE
        server.CONFIG_FILE = self.temp_config_path

        self.initial_fixture = {
            "seeds": [],
            "projects": [],
            "sources": [],
            "decisions": [],
            "conflicts": [],
            "relationships": [],
            "accounts": [
                {
                    "id": "usr_admin_master",
                    "email": "master@platform.internal",
                    "name": "Master Admin",
                    "role": "admin",
                    "plan": "master",
                    "status": "active",
                    "reflections_used_this_month": 0,
                    "billing_cycle_month": datetime.now().strftime("%Y-%m"),
                    "tokens_consumed": 0,
                    "created_at": datetime.now().isoformat()
                },
                {
                    "id": "usr_regular_tenant",
                    "email": "tenant@company.com",
                    "name": "Tenant One",
                    "role": "consumer",
                    "plan": "free",
                    "status": "active",
                    "reflections_used_this_month": 0,
                    "billing_cycle_month": datetime.now().strftime("%Y-%m"),
                    "tokens_consumed": 0,
                    "created_at": datetime.now().isoformat()
                }
            ]
        }
        with open(self.temp_db_path, "w", encoding="utf-8") as f:
            json.dump(self.initial_fixture, f)

        with open(self.temp_config_path, "w", encoding="utf-8") as f:
            json.dump({"ai_monthly_budget_usd": 50.0}, f)

        self.port = get_free_port()
        self.server_address = ("", self.port)
        self.httpd = server.HTTPServer(self.server_address, server.SeedReflectionAPIHandler)
        self.server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.server_thread.start()

    def tearDown(self):
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception:
            pass
        server.DATA_FILE = self.original_data_file
        server.CONFIG_FILE = self.original_config_file
        self.temp_dir.cleanup()

    def _post(self, path, payload):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            return resp.getcode(), json.loads(resp.read().decode("utf-8"))

    def _get(self, path):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}")
        with urllib.request.urlopen(req) as resp:
            return resp.getcode(), json.loads(resp.read().decode("utf-8"))

    def test_create_tenant_account_success(self):
        """Admin can create a new tenant account with credentials and tier."""
        payload = {
            "name": "Bob Builder",
            "email": "bob@builder.org",
            "role": "consumer",
            "plan": "pro",
            "status": "active",
            "password": "SecretPassword123!"
        }
        code, data = self._post("/api/v1/admin/users/create", payload)
        self.assertEqual(code, 201)
        self.assertEqual(data["status"], "created")
        account = data["account"]
        self.assertEqual(account["email"], "bob@builder.org")
        self.assertEqual(account["name"], "Bob Builder")
        self.assertEqual(account["role"], "consumer")
        self.assertEqual(account["plan"], "pro")
        self.assertTrue("password_hash" in account)

        # Verify account persists in DB
        with open(self.temp_db_path, "r", encoding="utf-8") as f:
            db = json.load(f)
        saved = next((a for a in db["accounts"] if a["email"] == "bob@builder.org"), None)
        self.assertIsNotNone(saved)
        self.assertEqual(saved["plan"], "pro")

    def test_create_tenant_duplicate_email_rejected(self):
        """Attempting to create an account with an existing email returns 409 Conflict."""
        payload = {
            "name": "Duplicate User",
            "email": "tenant@company.com",  # Already in fixture
            "role": "consumer",
            "plan": "free"
        }
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._post("/api/v1/admin/users/create", payload)
        self.assertEqual(cm.exception.code, 409)
        err_body = json.loads(cm.exception.read().decode("utf-8"))
        self.assertIn("already exists", err_body["error"])

    def test_create_tenant_missing_email_rejected(self):
        """Attempting to create an account without email returns 400 Bad Request."""
        payload = {
            "name": "No Email User",
            "role": "consumer"
        }
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._post("/api/v1/admin/users/create", payload)
        self.assertEqual(cm.exception.code, 400)

    def test_reset_tenant_password(self):
        """Admin can reset a tenant's password."""
        payload = {
            "user_id": "usr_regular_tenant",
            "password": "BrandNewPassword999!"
        }
        code, data = self._post("/api/v1/admin/users/reset-password", payload)
        self.assertEqual(code, 200)
        self.assertEqual(data["status"], "success")

        # Verify new password hash in DB
        with open(self.temp_db_path, "r", encoding="utf-8") as f:
            db = json.load(f)
        saved = next(a for a in db["accounts"] if a["id"] == "usr_regular_tenant")
        import hashlib
        expected_hash = hashlib.sha256("BrandNewPassword999!".encode("utf-8")).hexdigest()
        self.assertEqual(saved["password_hash"], expected_hash)
        self.assertIn("password_updated_at", saved)

    def test_delete_tenant_account_success(self):
        """Admin can delete a regular tenant account."""
        payload = {"user_id": "usr_regular_tenant"}
        code, data = self._post("/api/v1/admin/users/delete", payload)
        self.assertEqual(code, 200)
        self.assertEqual(data["status"], "deleted")
        self.assertEqual(data["user_id"], "usr_regular_tenant")

        # Verify removed from DB
        with open(self.temp_db_path, "r", encoding="utf-8") as f:
            db = json.load(f)
        remaining_ids = [a["id"] for a in db["accounts"]]
        self.assertNotIn("usr_regular_tenant", remaining_ids)

    def test_delete_root_admin_protected(self):
        """Deleting the primary platform administrator account is strictly prevented (403)."""
        payload = {"user_id": "usr_admin_master"}
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._post("/api/v1/admin/users/delete", payload)
        self.assertEqual(cm.exception.code, 403)
        err_body = json.loads(cm.exception.read().decode("utf-8"))
        self.assertIn("primary platform administrator", err_body["error"])

    def test_admin_overview_reflects_updated_tenant_counts(self):
        """Admin overview reflects updated user totals after creation and deletion."""
        code, data = self._get("/api/v1/admin/overview")
        self.assertEqual(code, 200)
        initial_users = len(data.get("users", []))
        self.assertEqual(initial_users, 2)

        # Create user
        self._post("/api/v1/admin/users/create", {
            "email": "newtenant@platform.com",
            "plan": "pro"
        })

        code, data2 = self._get("/api/v1/admin/overview")
        self.assertEqual(len(data2.get("users", [])), initial_users + 1)
        pro_user = next((u for u in data2.get("users", []) if u["email"] == "newtenant@platform.com"), None)
        self.assertIsNotNone(pro_user)
        self.assertIn("Pro", pro_user["plan"])

if __name__ == "__main__":
    unittest.main()
