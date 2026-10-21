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

class TestAIBudgetAndKillswitch(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_db_path = os.path.join(self.temp_dir.name, "seeds_test.json")
        self.original_data_file = server.DATA_FILE
        server.DATA_FILE = self.temp_db_path

        self.temp_config_path = os.path.join(self.temp_dir.name, "config_test.json")
        self.original_config_file = server.CONFIG_FILE
        server.CONFIG_FILE = self.temp_config_path

        self.original_telemetry = list(server.TELEMETRY_LOG)
        server.TELEMETRY_LOG.clear()

        # Fixture with sample database
        self.initial_fixture = {
            "seeds": [
                {
                    "seed_id": "seed_sample_1",
                    "intent": "Build an intelligent payment webhook",
                    "title": "Payment Webhook",
                    "project_id": "default_project"
                }
            ],
            "projects": [{"project_id": "default_project", "name": "Default", "stage": "Active"}],
            "sources": [],
            "decisions": [],
            "conflicts": [],
            "relationships": [],
            "accounts": [
                {
                    "id": "usr_tester",
                    "email": "tester@seedreflections.app",
                    "name": "Test Developer",
                    "role": "consumer",
                    "plan": "pro",
                    "status": "active"
                }
            ],
            "telemetry": []
        }
        with open(self.temp_db_path, "w", encoding="utf-8") as f:
            json.dump(self.initial_fixture, f, indent=2)

        # Config with initial budget settings
        with open(self.temp_config_path, "w", encoding="utf-8") as f:
            json.dump({
                "llm_provider": "ollama",
                "llm_api_url": "http://127.0.0.1:11434",
                "llm_model": "llama3",
                "llm_api_key": "test_key",
                "ai_killswitch_enabled": False,
                "ai_monthly_budget_usd": 50.0,
                "ai_budget_hard_stop": True
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
        server.TELEMETRY_LOG.clear()
        server.TELEMETRY_LOG.extend(self.original_telemetry)
        self.temp_dir.cleanup()

    def make_request(self, endpoint, method="POST", data=None):
        url = f"http://127.0.0.1:{self.port}{endpoint}"
        headers = {"Content-Type": "application/json"}
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

    def test_killswitch_toggle_endpoint(self):
        """Test POST /api/v1/admin/ai/killswitch toggles state and persists to config."""
        # Toggle ON
        status, body = self.make_request("/api/v1/admin/ai/killswitch", method="POST", data={"killswitch_enabled": True})
        self.assertEqual(status, 200)
        self.assertTrue(body.get("killswitch_enabled"))
        self.assertIn("ACTIVATED", body.get("message", ""))

        # Check config persisted
        cfg = server.load_config()
        self.assertTrue(cfg.get("ai_killswitch_enabled"))

        # Toggle OFF
        status, body = self.make_request("/api/v1/admin/ai/killswitch", method="POST", data={"killswitch_enabled": False})
        self.assertEqual(status, 200)
        self.assertFalse(body.get("killswitch_enabled"))
        self.assertIn("DEACTIVATED", body.get("message", ""))

        cfg = server.load_config()
        self.assertFalse(cfg.get("ai_killswitch_enabled"))

    def test_killswitch_blocks_test_llm(self):
        """When killswitch is engaged, test-llm endpoint blocks outbound call."""
        # Enable killswitch
        self.make_request("/api/v1/admin/ai/killswitch", method="POST", data={"killswitch_enabled": True})

        status, body = self.make_request("/api/v1/admin/test-llm", method="POST", data={
            "llm_provider": "openai_compatible",
            "llm_api_key": "gsk_test_fake_key"
        })
        self.assertEqual(status, 400)
        self.assertFalse(body.get("success", True))
        self.assertIn("Killswitch is currently ENGAGED", body.get("message", ""))

    def test_killswitch_forces_heuristic_fallback_in_reflect(self):
        """When killswitch is engaged, /reflect gracefully uses local heuristics with zero LLM spend."""
        self.make_request("/api/v1/admin/ai/killswitch", method="POST", data={"killswitch_enabled": True})

        status, body = self.make_request("/api/v1/reflect", method="POST", data={
            "transcript": "User: We need to build a distributed caching system for Redis."
        })
        self.assertEqual(status, 200)
        self.assertIn("seeds", body)
        self.assertGreater(len(body["seeds"]), 0)
        self.assertIn("heuristics_fallback (AI_KILLSWITCH_ACTIVE)", body.get("answer", ""))

    def test_killswitch_informs_chat_endpoint(self):
        """When killswitch is engaged, chat endpoint returns notice that AI gateway is paused."""
        self.make_request("/api/v1/admin/ai/killswitch", method="POST", data={"killswitch_enabled": True})

        status, body = self.make_request("/api/v1/seeds/chat", method="POST", data={
            "prompt": "How do I implement this seed?",
            "active_seed_id": "seed_sample_1"
        })
        self.assertEqual(status, 200)
        answer = body.get("answer", "")
        self.assertIn("AI Gateway Paused", answer)
        self.assertIn("Emergency Killswitch", answer)

    def test_budget_cap_exceeded_triggers_hard_stop(self):
        """When spend exceeds budget cap and hard stop is enabled, outbound LLM is paused."""
        # Set budget to $10.00 USD
        cfg = server.load_config()
        cfg["ai_monthly_budget_usd"] = 10.0
        cfg["ai_budget_hard_stop"] = True
        cfg["ai_killswitch_enabled"] = False
        server.save_config(cfg)

        # Simulate spend of $12.00 USD in telemetry
        server.TELEMETRY_LOG.append({
            "timestamp": datetime.now().isoformat(),
            "provider": "openai",
            "model": "gpt-4o",
            "prompt_tokens": 1000000,
            "completion_tokens": 1000000,
            "total_tokens": 2000000,
            "estimated_cost_usd": 12.00,
            "caller": "test"
        })

        is_allowed, code, msg, spend, cap = server.check_ai_gateway_status()
        self.assertFalse(is_allowed)
        self.assertEqual(code, "AI_BUDGET_EXCEEDED")
        self.assertEqual(spend, 12.00)
        self.assertEqual(cap, 10.0)

        # Reflect should fall back to heuristics
        status, body = self.make_request("/api/v1/reflect", method="POST", data={
            "transcript": "User: Add database migration scripts."
        })
        self.assertEqual(status, 200)
        self.assertIn("AI_BUDGET_EXCEEDED", body.get("answer", ""))

    def test_budget_cap_without_hard_stop_permits_traffic(self):
        """When hard-stop is disabled, traffic is allowed even if past budget cap."""
        cfg = server.load_config()
        cfg["ai_monthly_budget_usd"] = 10.0
        cfg["ai_budget_hard_stop"] = False
        cfg["ai_killswitch_enabled"] = False
        server.save_config(cfg)

        server.TELEMETRY_LOG.append({
            "timestamp": datetime.now().isoformat(),
            "provider": "openai",
            "model": "gpt-4o",
            "prompt_tokens": 1000000,
            "completion_tokens": 1000000,
            "total_tokens": 2000000,
            "estimated_cost_usd": 12.00,
            "caller": "test"
        })

        is_allowed, code, msg, spend, cap = server.check_ai_gateway_status()
        self.assertTrue(is_allowed)
        self.assertIsNone(code)

    def test_admin_overview_reflects_budget_and_killswitch(self):
        """Overview endpoint reports killswitch and budget metrics."""
        # Enable killswitch with budget 75.00
        cfg = server.load_config()
        cfg["ai_killswitch_enabled"] = True
        cfg["ai_monthly_budget_usd"] = 75.0
        server.save_config(cfg)

        status, body = self.make_request("/api/v1/admin/overview", method="GET")
        self.assertEqual(status, 200)
        telemetry = body.get("llm_telemetry", {})
        self.assertTrue(telemetry.get("ai_killswitch_enabled"))
        self.assertEqual(telemetry.get("ai_monthly_budget_usd"), 75.0)
        self.assertEqual(telemetry.get("gateway_status"), "killed")

if __name__ == "__main__":
    unittest.main()
