"""The platform budget is enforced from a durable ledger, not from an in-memory list of recent calls."""
import importlib
import os
import sqlite3
import sys
import tempfile
import threading
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
        with patch.object(server, "invoke_model", lambda *a, **k: {"text": "ok", "prompt_tokens": 1000, "completion_tokens": 1000}):
            for _ in range(600):
                server.metered_complete("openai", "", "k", "gpt-4o-mini", [{"role": "user", "content": "hi"}], "platform", "test")
                server.record_llm_usage("openai", "gpt-4o-mini", 1000, 1000, "test", "platform")
        self.assertEqual(len(server.TELEMETRY_LOG), 500)                  # the in-memory list is only recent activity
        self.assertEqual(spend_ledger.month_total("platform")["requests"], 600)
        self.assertEqual(spend_ledger.pending_calls(), [])                 # every reservation was settled

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
        with patch.object(server, "invoke_model", lambda *a, **k: {"text": "secret answer", "prompt_tokens": 10, "completion_tokens": 10}):
            server.metered_complete("openai", "", "k", "gpt-4o-mini", [{"role": "user", "content": "secret prompt"}], "platform", "workspace_agent")
        with sqlite3.connect(archive_store.DB_PATH) as db:
            columns = [row[1] for row in db.execute("PRAGMA table_info(ai_spend)")]
        self.assertEqual(columns, ["id", "created_at", "month", "provider", "model", "caller", "prompt_tokens", "completion_tokens", "cost_usd", "billed", "call_id", "status"])


class HeldSpendTests(unittest.TestCase):
    """Spend held after a failed write is recorded exactly once, whatever fails part-way and however many requests hold at once."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(archive_store, "DB_PATH", Path(self.temp.name) / "archive.db"); self.patch.start()
        spend_ledger._MEMORY_HELD.clear()

    def tearDown(self):
        spend_ledger._MEMORY_HELD.clear(); self.patch.stop(); remove_temp(self.temp)

    def ledger_rows(self):
        with sqlite3.connect(archive_store.DB_PATH) as db:
            return db.execute("SELECT call_id, cost_usd FROM ai_spend ORDER BY call_id").fetchall()

    def hold(self, call_id, dollars=0.60):
        spend_ledger.hold("openai", "m", 0, 0, dollars, "platform", "test", call_id=call_id)

    def test_a_failure_half_way_through_recovery_never_counts_a_call_twice(self):
        self.hold("call-a"); self.hold("call-b")
        real = spend_ledger.record
        def first_only(*args, **kwargs):
            if kwargs.get("call_id") == "call-b": raise sqlite3.OperationalError("database is locked")
            return real(*args, **kwargs)
        with patch.object(spend_ledger, "record", side_effect=first_only):
            self.assertFalse(spend_ledger.flush_held())                  # a: written; b: still held
        self.assertTrue(spend_ledger.has_unrecorded())
        self.assertTrue(spend_ledger.flush_held())                       # the retry
        self.assertEqual(self.ledger_rows(), [("call-a", 0.60), ("call-b", 0.60)])
        self.assertAlmostEqual(spend_ledger.month_total("platform")["cost_usd"], 1.20)
        self.assertFalse(spend_ledger.has_unrecorded())

    def test_a_call_written_but_whose_hold_file_could_not_be_removed_is_not_counted_again(self):
        self.hold("call-a")
        with patch.object(Path, "unlink", side_effect=PermissionError("in use")):
            self.assertFalse(spend_ledger.flush_held())                   # recorded, file left behind
        self.assertTrue(spend_ledger.flush_held())
        self.assertEqual(self.ledger_rows(), [("call-a", 0.60)])

    def test_simultaneous_holds_are_all_kept_and_each_recorded_once(self):
        ids = [f"call-{n:02d}" for n in range(20)]
        start = threading.Barrier(len(ids))
        def worker(call_id):
            start.wait(); self.hold(call_id)
        threads = [threading.Thread(target=worker, args=(call_id,)) for call_id in ids]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertTrue(spend_ledger.flush_held())
        self.assertEqual(self.ledger_rows(), [(call_id, 0.60) for call_id in ids])
        self.assertAlmostEqual(spend_ledger.month_total("platform")["cost_usd"], 12.0)

    def test_two_recoveries_running_at_once_record_each_call_once(self):
        for n in range(10): self.hold(f"call-{n}")
        start = threading.Barrier(2)
        def recover():
            start.wait(); spend_ledger.flush_held()
        threads = [threading.Thread(target=recover) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        spend_ledger.flush_held()
        self.assertEqual(len(self.ledger_rows()), 10); self.assertAlmostEqual(spend_ledger.month_total("platform")["cost_usd"], 6.0)
        self.assertFalse(spend_ledger.has_unrecorded())


class ResolveScriptTests(unittest.TestCase):
    def test_the_operator_script_lists_then_resolves_pending_calls_at_their_reserved_cost(self):
        import subprocess
        with tempfile.TemporaryDirectory() as data:
            with patch.object(archive_store, "DB_PATH", Path(data) / "archive.db"):
                spend_ledger.reserve("orphan", "openai", "gpt-4o-mini", "workspace_agent", 0.25)
            env = {**os.environ, "SEED_REFLECTIONS_DATA_DIR": data}
            script = str(Path(__file__).resolve().parents[1] / "scripts" / "resolve_ai_spend.py")
            listed = subprocess.run([sys.executable, script], capture_output=True, text=True, env=env, timeout=60)
            self.assertIn("reserved $0.2500", listed.stdout); self.assertIn("--resolve", listed.stdout)
            done = subprocess.run([sys.executable, script, "--resolve"], capture_output=True, text=True, env=env, timeout=60)
            self.assertIn("Resolved 1", done.stdout)
            with patch.object(archive_store, "DB_PATH", Path(data) / "archive.db"):
                self.assertEqual(spend_ledger.pending_calls(), [])
                self.assertAlmostEqual(spend_ledger.month_total("platform")["cost_usd"], 0.25)


if __name__ == "__main__":
    unittest.main()
