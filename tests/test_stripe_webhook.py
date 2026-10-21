import unittest
import json
import os
import sys
import tempfile
import socket
import threading
import urllib.request
import urllib.error
import hmac
import hashlib
import time
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import server

def get_free_port():
    s = socket.socket()
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    return port

class TestStripeWebhook(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_db_path = os.path.join(self.temp_dir.name, "seeds_test.json")
        self.original_data_file = server.DATA_FILE
        server.DATA_FILE = self.temp_db_path

        self.temp_config_path = os.path.join(self.temp_dir.name, "config_test.json")
        self.original_config_file = server.CONFIG_FILE
        server.CONFIG_FILE = self.temp_config_path

        # Fixture with test accounts
        self.initial_fixture = {
            "seeds": [],
            "projects": [],
            "sources": [],
            "decisions": [],
            "conflicts": [],
            "relationships": [],
            "accounts": [
                {
                    "id": "usr_test_consumer",
                    "email": "tester@example.com",
                    "name": "Test User",
                    "role": "consumer",
                    "plan": "free",
                    "status": "active",
                    "tokens_consumed": 0,
                    "created_at": datetime.now().isoformat()
                }
            ],
            "telemetry": []
        }
        with open(self.temp_db_path, "w", encoding="utf-8") as f:
            json.dump(self.initial_fixture, f, indent=2)

        # Config with test webhook secret
        self.test_webhook_secret = "whsec_test_secret_key_12345"
        with open(self.temp_config_path, "w", encoding="utf-8") as f:
            json.dump({
                "stripe_webhook_secret": self.test_webhook_secret,
                "stripe_mode": "test"
            }, f, indent=2)

        # Start isolated server
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

    def make_request(self, endpoint, method="POST", data=None, headers=None):
        url = f"http://127.0.0.1:{self.port}{endpoint}"
        req_headers = {"Content-Type": "application/json"}
        if headers:
            req_headers.update(headers)
        
        req_data = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=req_data, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                status = resp.getcode()
                body = json.loads(resp.read().decode("utf-8"))
                return status, body
        except urllib.error.HTTPError as e:
            status = e.code
            try:
                body = json.loads(e.read().decode("utf-8"))
            except Exception:
                body = {"error": str(e)}
            return status, body

    def test_checkout_completed_upgrades_account(self):
        """Test checkout.session.completed webhook upgrades existing user to Pro plan."""
        event_payload = {
            "id": "evt_test_checkout_1",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_123",
                    "customer": "cus_123",
                    "customer_email": "tester@example.com",
                    "amount_total": 900,
                    "metadata": {"plan": "pro"},
                    "subscription": "sub_pro_123"
                }
            }
        }
        status, body = self.make_request("/api/v1/stripe/webhook", method="POST", data=event_payload)
        self.assertEqual(status, 200)
        self.assertEqual(body.get("status"), "upgraded")
        self.assertEqual(body.get("plan"), "pro")

        # Verify in database
        db = server.load_db()
        account = next(a for a in db["accounts"] if a["email"] == "tester@example.com")
        self.assertEqual(account["plan"], "pro")
        self.assertEqual(account["stripe_customer_id"], "cus_123")
        self.assertEqual(account["stripe_subscription_id"], "sub_pro_123")

    def test_checkout_completed_master_tier(self):
        """Test checkout.session.completed upgrades to master tier."""
        event_payload = {
            "id": "evt_test_checkout_master",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_master",
                    "customer": "cus_master",
                    "customer_email": "tester@example.com",
                    "amount_total": 2000,
                    "metadata": {"plan": "master"}
                }
            }
        }
        status, body = self.make_request("/api/v1/stripe/webhook", method="POST", data=event_payload)
        self.assertEqual(status, 200)
        self.assertEqual(body.get("plan"), "master")

        db = server.load_db()
        account = next(a for a in db["accounts"] if a["email"] == "tester@example.com")
        self.assertEqual(account["plan"], "master")

    def test_subscription_deleted_downgrades_to_free(self):
        """Test customer.subscription.deleted downgrades account to free."""
        # First set user to pro
        db = server.load_db()
        account = next(a for a in db["accounts"] if a["email"] == "tester@example.com")
        account["plan"] = "pro"
        account["stripe_subscription_id"] = "sub_active_to_cancel"
        server.save_db(db)

        event_payload = {
            "id": "evt_test_sub_deleted",
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "id": "sub_active_to_cancel",
                    "customer": "cus_test"
                }
            }
        }
        status, body = self.make_request("/api/v1/stripe/webhook", method="POST", data=event_payload)
        self.assertEqual(status, 200)
        self.assertEqual(body.get("status"), "downgraded_to_free")

        db = server.load_db()
        account = next(a for a in db["accounts"] if a["email"] == "tester@example.com")
        self.assertEqual(account["plan"], "free")
        self.assertIsNone(account["stripe_subscription_id"])

    def test_signature_verification_success_and_failure(self):
        """Test Stripe HMAC SHA-256 signature verification."""
        event_payload = {
            "id": "evt_test_sig",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_sig",
                    "customer_email": "tester@example.com",
                    "amount_total": 900,
                    "metadata": {"plan": "pro"}
                }
            }
        }
        raw_body = json.dumps(event_payload).encode("utf-8")
        timestamp = str(int(time.time()))
        signed_payload = f"{timestamp}.".encode("utf-8") + raw_body
        valid_sig = hmac.new(self.test_webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()

        # Valid signature should succeed
        status, body = self.make_request(
            "/api/v1/stripe/webhook",
            method="POST",
            data=event_payload,
            headers={"Stripe-Signature": f"t={timestamp},v1={valid_sig}"}
        )
        self.assertEqual(status, 200)

        # Invalid signature should be rejected with 400
        invalid_sig = "bad_signature_hash_value"
        status, body = self.make_request(
            "/api/v1/stripe/webhook",
            method="POST",
            data=event_payload,
            headers={"Stripe-Signature": f"t={timestamp},v1={invalid_sig}"}
        )
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    def test_overview_includes_webhook_events(self):
        """Test that /api/v1/admin/overview reports recent webhook activity."""
        # Trigger an event
        self.make_request("/api/v1/stripe/webhook", method="POST", data={
            "id": "evt_overview_check",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "customer_email": "tester@example.com",
                    "amount_total": 900
                }
            }
        })
        status, body = self.make_request("/api/v1/admin/overview", method="GET")
        self.assertEqual(status, 200)
        stripe_billing = body.get("stripe_billing", {})
        self.assertIn("webhook_events", stripe_billing)
        self.assertGreater(len(stripe_billing["webhook_events"]), 0)

if __name__ == "__main__":
    unittest.main()
