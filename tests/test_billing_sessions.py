import json, os, socket, tempfile, threading, unittest, urllib.error, urllib.request
from datetime import datetime
from unittest.mock import patch

import server


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0)); return sock.getsockname()[1]


class BillingSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_data_file, self.original_config_file = server.DATA_FILE, server.CONFIG_FILE
        server.DATA_FILE = os.path.join(self.temp.name, "workspace.json")
        server.CONFIG_FILE = os.path.join(self.temp.name, "config.json")
        fixture = {key: [] for key in ("seeds", "projects", "sources", "decisions", "conflicts", "relationships", "telemetry", "stripe_events")}
        fixture["accounts"] = [{"id": "usr_billing", "email": "billing@example.com", "name": "Billing User",
            "role": "consumer", "plan": "pro", "status": "active", "stripe_customer_id": "cus_existing",
            "created_at": datetime.now().isoformat()}]
        with open(server.DATA_FILE, "w", encoding="utf-8") as stream: json.dump(fixture, stream)
        with open(server.CONFIG_FILE, "w", encoding="utf-8") as stream:
            json.dump({"stripe_secret_key": "sk_test_server", "stripe_price_pro": "price_pro",
                "stripe_price_master": "price_master"}, stream)
        self.environment = patch.dict(os.environ, {"SEED_REFLECTIONS_BILLING_ENABLED": "1"})
        self.environment.start(); self.port = free_port()
        self.httpd = server.HTTPServer(("127.0.0.1", self.port), server.SeedReflectionAPIHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True); self.thread.start()

    def tearDown(self):
        self.httpd.shutdown(); self.httpd.server_close(); self.environment.stop()
        server.DATA_FILE, server.CONFIG_FILE = self.original_data_file, self.original_config_file
        self.temp.cleanup()

    def request(self, path, payload):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode(), method="POST", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request) as response: return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc: return exc.code, json.loads(exc.read())

    def test_checkout_is_created_server_side_with_account_and_plan_metadata(self):
        with patch.object(server, "stripe_api_request", return_value={"id": "cs_test", "url": "https://checkout.stripe.test/session"}) as stripe:
            status, body = self.request("/api/v2/billing/checkout", {"plan": "pro", "request_id": "request-1"})
        self.assertEqual(status, 200); self.assertEqual(body["session_id"], "cs_test")
        path, parameters, secret, key = stripe.call_args.args
        self.assertEqual(path, "/v1/checkout/sessions"); self.assertEqual(secret, "sk_test_server")
        self.assertEqual(parameters["line_items[0][price]"], "price_pro")
        self.assertEqual(parameters["client_reference_id"], "usr_billing")
        self.assertEqual(parameters["customer"], "cus_existing")
        self.assertEqual(parameters["subscription_data[metadata][plan]"], "pro")
        self.assertEqual(key, "checkout:usr_billing:pro:request-1")

    def test_portal_is_created_for_the_authenticated_customer(self):
        with patch.object(server, "stripe_api_request", return_value={"url": "https://billing.stripe.test/portal"}) as stripe:
            status, body = self.request("/api/v2/billing/portal", {"request_id": "request-2"})
        self.assertEqual(status, 200); self.assertEqual(body["portal_url"], "https://billing.stripe.test/portal")
        self.assertEqual(stripe.call_args.args[0], "/v1/billing_portal/sessions")
        self.assertEqual(stripe.call_args.args[1]["customer"], "cus_existing")

    def test_checkout_rejects_unknown_plan_before_contacting_stripe(self):
        with patch.object(server, "stripe_api_request") as stripe:
            status, body = self.request("/api/v2/billing/checkout", {"plan": "free"})
        self.assertEqual(status, 400); self.assertIn("error", body); stripe.assert_not_called()


if __name__ == "__main__": unittest.main()
