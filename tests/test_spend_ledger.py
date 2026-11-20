"""The platform budget is enforced from a durable ledger, not from an in-memory list of recent calls."""
import importlib
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(__file__))
from support import remove_temp
import archive_store
import server
import spend_ledger


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name)
        self.patches = [patch.object(archive_store, "DB_PATH", root / "archive.db"),
                        patch.object(server, "CONFIG_FILE", str(root / "config.json")), patch.object(server, "DEPLOYMENT_MODE", "hosted")]
        for item in self.patches: item.start()
        server.save_config({**server.load_config(), "ai_monthly_budget_usd": 1.0, "ai_budget_hard_stop": True, "ai_killswitch_enabled": False})
        self.saved_log = list(server.TELEMETRY_LOG); server.TELEMETRY_LOG.clear()

    def tearDown(self):
        server.TELEMETRY_LOG[:] = self.saved_log
        for item in reversed(self.patches): item.stop()
        remove_temp(self.temp)

    def spend(self, dollars, billed="platform", when=None):
        spend_ledger.record("openai", "gpt-4o-mini", 0, 0, dollars, billed, "test", when=when)

    def test_spend_survives_a_restart(self):
        self.spend(0.6); self.spend(0.6)
        importlib.reload(spend_ledger)                                   # a new process sees only what is on disk
        server.TELEMETRY_LOG.clear()
        self.assertAlmostEqual(server.platform_spend(), 1.2)
        allowed, code, *_ = server.check_ai_gateway_status("managed")
        self.assertFalse(allowed); self.assertEqual(code, "AI_BUDGET_EXCEEDED")

    def test_every_call_in_the_month_counts_not_only_the_last_500(self):
        for _ in range(600): server.record_llm_usage("openai", "gpt-4o-mini", 1000, 1000, "test", "platform")
        self.assertEqual(len(server.TELEMETRY_LOG), 500)                  # the in-memory list is only recent activity
        self.assertEqual(spend_ledger.month_total("platform")["requests"], 600)

    def test_the_budget_is_per_calendar_month(self):
        last_month = datetime(2001, 1, 31, 23, 59, tzinfo=timezone.utc)
        self.spend(50.0, when=last_month)
        self.assertEqual(server.platform_spend(), 0.0)
        self.assertTrue(server.check_ai_gateway_status("managed")[0])
        self.assertEqual(spend_ledger.month_total("platform", "2001-01")["cost_usd"], 50.0)

    def test_own_key_spend_is_recorded_but_never_counts_toward_the_platform_budget(self):
        self.spend(5.0, billed="own_key")
        self.assertEqual(server.platform_spend(), 0.0)
        self.assertTrue(server.check_ai_gateway_status("managed")[0])
        self.assertEqual(spend_ledger.month_total("own_key")["cost_usd"], 5.0)

    def test_an_unreadable_ledger_stops_paid_calls_instead_of_assuming_zero(self):
        with patch.object(spend_ledger, "month_total", side_effect=sqlite3.OperationalError("disk I/O error")):
            allowed, code, *_ = server.check_ai_gateway_status("managed")
            self.assertFalse(allowed); self.assertEqual(code, "AI_BUDGET_UNKNOWN")
            self.assertTrue(server.check_ai_gateway_status("self_hosted")[0])     # own keys are not the platform's cost

    def test_no_text_or_account_is_stored(self):
        server.record_llm_usage("openai", "gpt-4o-mini", 10, 10, "workspace_agent", "platform")
        with sqlite3.connect(archive_store.DB_PATH) as db:
            columns = [row[1] for row in db.execute("PRAGMA table_info(ai_spend)")]
        self.assertEqual(columns, ["id", "created_at", "month", "provider", "model", "caller", "prompt_tokens", "completion_tokens", "cost_usd", "billed"])


if __name__ == "__main__":
    unittest.main()
