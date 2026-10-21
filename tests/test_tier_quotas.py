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

class TestTierQuotas(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_db_path = os.path.join(self.temp_dir.name, "seeds_test.json")
        self.original_data_file = server.DATA_FILE
        server.DATA_FILE = self.temp_db_path

        self.temp_config_path = os.path.join(self.temp_dir.name, "config_test.json")
        self.original_config_file = server.CONFIG_FILE
        server.CONFIG_FILE = self.temp_config_path

        # Initial fixture with Free user and seeds
        self.initial_fixture = {
            "seeds": [],
            "projects": [
                {
                    "project_id": "default_project",
                    "name": "Default Project",
                    "stage": "Active"
                }
            ],
            "sources": [],
            "decisions": [],
            "conflicts": [],
            "relationships": [],
            "accounts": [
                {
                    "id": "usr_free_tester",
                    "email": "free_user@example.com",
                    "name": "Free Tester",
                    "role": "consumer",
                    "plan": "free",
                    "status": "active",
                    "reflections_used_this_month": 0,
                    "billing_cycle_month": datetime.now().strftime("%Y-%m"),
                    "tokens_consumed": 0,
                    "created_at": datetime.now().isoformat()
                },
                {
                    "id": "usr_pro_tester",
                    "email": "pro_user@example.com",
                    "name": "Pro Tester",
                    "role": "consumer",
                    "plan": "pro",
                    "status": "active",
                    "reflections_used_this_month": 0,
                    "billing_cycle_month": datetime.now().strftime("%Y-%m"),
                    "tokens_consumed": 0,
                    "created_at": datetime.now().isoformat()
                },
                {
                    "id": "usr_master_tester",
                    "email": "master_user@example.com",
                    "name": "Master Tester",
                    "role": "consumer",
                    "plan": "master",
                    "status": "active",
                    "reflections_used_this_month": 0,
                    "billing_cycle_month": datetime.now().strftime("%Y-%m"),
                    "tokens_consumed": 0,
                    "created_at": datetime.now().isoformat()
                }
            ],
            "telemetry": []
        }
        with open(self.temp_db_path, "w", encoding="utf-8") as f:
            json.dump(self.initial_fixture, f, indent=2)

        with open(self.temp_config_path, "w", encoding="utf-8") as f:
            json.dump({
                "llm_provider": "ollama",
                "stripe_checkout_pro": "https://buy.stripe.com/test_seed_reflections_pro",
                "stripe_checkout_master": "https://buy.stripe.com/test_seed_reflections_master"
            }, f, indent=2)

        self.port = get_free_port()
        self.server_address = ("127.0.0.1", self.port)
        self.httpd = server.HTTPServer(self.server_address, server.SeedReflectionAPIHandler)
        self.server_thread = threading.Thread(target=self.httpd.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        server.DATA_FILE = self.original_data_file
        server.CONFIG_FILE = self.original_config_file
        self.temp_dir.cleanup()

    def make_request(self, endpoint, method="POST", data=None, token=None):
        url = f"http://127.0.0.1:{self.port}{endpoint}"
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req_data = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.getcode(), json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode("utf-8"))
            except Exception:
                body = {"error": str(e)}
            return e.code, body

    def test_free_tier_seed_quota_blocked_at_limit(self):
        """Free tier allows up to 20 seeds, then blocks the 21st seed with 403."""
        token = "user_token_usr_free_tester"
        
        # Populate 20 seeds directly into database
        db = server.load_db()
        for i in range(20):
            db["seeds"].append({
                "seed_id": f"seed_pre_{i}",
                "intent": f"Pre-existing seed {i}",
                "title": f"Seed {i}",
                "project_id": "default_project"
            })
        server.save_db(db)

        # Attempt to plant 21st seed
        status, body = self.make_request(
            "/api/v1/seeds",
            method="POST",
            data={"intent": "The 21st seed intention that should exceed free quota"},
            token=token
        )
        self.assertEqual(status, 403)
        self.assertEqual(body.get("code"), "SEED_QUOTA_EXCEEDED")
        self.assertIn("Free tier seed limit reached", body.get("error", ""))
        self.assertIn("upgrade_url", body)

    def test_pro_tier_unlimited_seeds(self):
        """Pro tier allows creating more than 20 seeds without restriction."""
        token = "user_token_usr_pro_tester"

        # Populate 20 seeds directly into database
        db = server.load_db()
        for i in range(20):
            db["seeds"].append({
                "seed_id": f"seed_pro_{i}",
                "intent": f"Pre-existing seed {i}",
                "title": f"Seed {i}",
                "project_id": "default_project"
            })
        server.save_db(db)

        # Pro user creates 21st seed
        status, body = self.make_request(
            "/api/v1/seeds",
            method="POST",
            data={"intent": "Pro user 21st seed intention allowed"},
            token=token
        )
        self.assertEqual(status, 201)
        self.assertEqual(body.get("status"), "planted")

    def test_free_tier_reflection_quota_enforcement(self):
        """Free tier blocks reflection at 50/50 quota with 429."""
        token = "user_token_usr_free_tester"
        db = server.load_db()
        account = next(a for a in db["accounts"] if a["id"] == "usr_free_tester")
        account["reflections_used_this_month"] = 50
        server.save_db(db)

        status, body = self.make_request(
            "/api/v1/reflect",
            method="POST",
            data={"transcript": "User: I need to build a payment gateway integration."},
            token=token
        )
        self.assertEqual(status, 429)
        self.assertEqual(body.get("code"), "REFLECTION_QUOTA_EXCEEDED")
        self.assertIn("50/50", body.get("error", ""))

    def test_pro_tier_allows_above_50_blocks_at_250(self):
        """Pro tier permits > 50 reflections, but blocks at 250 with 429."""
        token = "user_token_usr_pro_tester"
        db = server.load_db()
        account = next(a for a in db["accounts"] if a["id"] == "usr_pro_tester")
        account["reflections_used_this_month"] = 50
        server.save_db(db)

        # Pro user at 50 can still reflect
        status, body = self.make_request(
            "/api/v1/reflect",
            method="POST",
            data={"transcript": "User: Let's create an authentication module."},
            token=token
        )
        self.assertEqual(status, 200)

        # Now set to 250
        db = server.load_db()
        account = next(a for a in db["accounts"] if a["id"] == "usr_pro_tester")
        account["reflections_used_this_month"] = 250
        server.save_db(db)

        status, body = self.make_request(
            "/api/v1/reflect",
            method="POST",
            data={"transcript": "User: Let's create an authentication module."},
            token=token
        )
        self.assertEqual(status, 429)
        self.assertEqual(body.get("code"), "REFLECTION_QUOTA_EXCEEDED")
        self.assertIn("250/250", body.get("error", ""))

    def test_master_tier_unlimited_reflections(self):
        """Master tier allows reflections well beyond 250 without restriction."""
        token = "user_token_usr_master_tester"
        db = server.load_db()
        account = next(a for a in db["accounts"] if a["id"] == "usr_master_tester")
        account["reflections_used_this_month"] = 500
        server.save_db(db)

        status, body = self.make_request(
            "/api/v1/reflect",
            method="POST",
            data={"transcript": "User: Deploying enterprise constellation pipeline."},
            token=token
        )
        self.assertEqual(status, 200)

    def test_billing_cycle_rollover_resets_counter(self):
        """When billing cycle month changes, account usage automatically resets."""
        token = "user_token_usr_free_tester"
        db = server.load_db()
        account = next(a for a in db["accounts"] if a["id"] == "usr_free_tester")
        account["billing_cycle_month"] = "2026-08" # Previous month
        account["reflections_used_this_month"] = 50
        server.save_db(db)

        # Request user info
        status, body = self.make_request("/api/v1/users/me", method="GET", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(body.get("reflections_used"), 0) # Reset to 0

    def test_users_me_and_dashboard_return_real_quotas(self):
        """Test /api/v1/users/me and consumer dashboard return real quota metadata."""
        token = "user_token_usr_free_tester"
        status, body = self.make_request("/api/v1/users/me", method="GET", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(body.get("plan"), "free")
        self.assertEqual(body.get("seeds_limit"), 20)
        self.assertEqual(body.get("reflections_limit"), 50)

        status_dash, body_dash = self.make_request("/api/v1/users/me/consumer-dashboard", method="GET", token=token)
        self.assertEqual(status_dash, 200)
        self.assertEqual(body_dash.get("plan"), "free")
        self.assertEqual(body_dash.get("seeds_limit"), 20)
        self.assertEqual(body_dash.get("reflections_limit"), 50)

if __name__ == "__main__":
    unittest.main()
