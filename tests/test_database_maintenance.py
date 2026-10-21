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

class TestDatabaseMaintenance(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_db_path = os.path.join(self.temp_dir.name, "seeds_test.json")
        self.original_data_file = server.DATA_FILE
        server.DATA_FILE = self.temp_db_path

        self.temp_transcripts_dir = os.path.join(self.temp_dir.name, "transcripts_test")
        os.makedirs(self.temp_transcripts_dir, exist_ok=True)
        self.original_transcripts_dir = server.TRANSCRIPTS_DIR
        server.TRANSCRIPTS_DIR = self.temp_transcripts_dir

        self.temp_config_path = os.path.join(self.temp_dir.name, "config_test.json")
        self.original_config_file = server.CONFIG_FILE
        server.CONFIG_FILE = self.temp_config_path

        # Create active seed with a referenced transcript ID
        self.initial_fixture = {
            "seeds": [
                {
                    "seed_id": "seed_active_1",
                    "title": "Active Intent",
                    "intent": "Build platform features",
                    "status": "planted",
                    "source_transcript_id": "referenced_tid_123"
                }
            ],
            "projects": [],
            "sources": [],
            "decisions": [],
            "conflicts": [],
            "relationships": [],
            "accounts": [
                {
                    "id": "usr_admin_master",
                    "email": "master@platform.internal",
                    "role": "admin",
                    "plan": "master",
                    "status": "active"
                }
            ]
        }
        with open(self.temp_db_path, "w", encoding="utf-8") as f:
            json.dump(self.initial_fixture, f)

        with open(self.temp_config_path, "w", encoding="utf-8") as f:
            json.dump({"ai_monthly_budget_usd": 50.0}, f)

        # Create 1 referenced transcript file and 2 orphan transcript files
        with open(os.path.join(self.temp_transcripts_dir, "referenced_tid_123.txt"), "w", encoding="utf-8") as f:
            f.write("This transcript is referenced by seed_active_1 and MUST be preserved.")

        with open(os.path.join(self.temp_transcripts_dir, "orphan_tid_abc.txt"), "w", encoding="utf-8") as f:
            f.write("This is an unreferenced orphan transcript cache that should be purged.")

        with open(os.path.join(self.temp_transcripts_dir, "orphan_tid_xyz.txt"), "w", encoding="utf-8") as f:
            f.write("Another abandoned session transcript ready for retention reclamation.")

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
        server.TRANSCRIPTS_DIR = self.original_transcripts_dir
        server.CONFIG_FILE = self.original_config_file
        self.temp_dir.cleanup()

    def _get(self, path):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}")
        with urllib.request.urlopen(req) as resp:
            content = resp.read()
            headers = dict(resp.info())
            return resp.getcode(), content, headers

    def _post(self, path, payload):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            return resp.getcode(), json.loads(resp.read().decode("utf-8"))

    def test_database_backup_download_endpoint(self):
        """Admin can trigger 1-click snapshot download of seeds.json."""
        code, content, headers = self._get("/api/v1/admin/backup")
        self.assertEqual(code, 200)
        self.assertIn("application/json", headers.get("Content-Type", ""))
        self.assertIn("attachment; filename=\"seed_reflections_backup_", headers.get("Content-Disposition", ""))

        # Verify downloaded JSON matches database structure
        snapshot_db = json.loads(content.decode("utf-8"))
        self.assertIn("seeds", snapshot_db)
        self.assertIn("accounts", snapshot_db)
        self.assertEqual(len(snapshot_db["seeds"]), 1)
        self.assertEqual(snapshot_db["seeds"][0]["seed_id"], "seed_active_1")

    def test_orphan_transcripts_cleaner_endpoint(self):
        """Maintenance clean prunes unreferenced transcripts and preserves referenced ones."""
        # Pre-clean check: 3 transcripts exist
        files_before = os.listdir(self.temp_transcripts_dir)
        self.assertEqual(len(files_before), 3)

        code, data = self._post("/api/v1/admin/transcripts/clean", {})
        self.assertEqual(code, 200)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["purged_count"], 2)
        self.assertGreater(data["bytes_reclaimed"], 0)
        self.assertIn("orphan_tid_abc.txt", data["deleted_files"])
        self.assertIn("orphan_tid_xyz.txt", data["deleted_files"])

        # Post-clean check: only referenced transcript remains
        files_after = os.listdir(self.temp_transcripts_dir)
        self.assertEqual(len(files_after), 1)
        self.assertEqual(files_after[0], "referenced_tid_123.txt")

    def test_cleaner_idempotent_when_no_orphans(self):
        """Running the clean routine again when no orphans exist reclaims 0 bytes cleanly."""
        # Run first clean
        self._post("/api/v1/admin/transcripts/clean", {})

        # Run second clean
        code, data = self._post("/api/v1/admin/transcripts/clean", {})
        self.assertEqual(code, 200)
        self.assertEqual(data["purged_count"], 0)
        self.assertEqual(data["bytes_reclaimed"], 0)
        self.assertEqual(len(data["deleted_files"]), 0)

    def test_overview_storage_metrics_reflects_pruned_volume(self):
        """Overview storage metrics reflect reduced transcript counts after maintenance."""
        code, content, _ = self._get("/api/v1/admin/overview")
        self.assertEqual(code, 200)
        data1 = json.loads(content.decode("utf-8"))
        self.assertEqual(data1["storage_metrics"]["transcripts_count"], 3)

        # Run clean
        self._post("/api/v1/admin/transcripts/clean", {})

        # Check overview again
        code, content2, _ = self._get("/api/v1/admin/overview")
        self.assertEqual(code, 200)
        data2 = json.loads(content2.decode("utf-8"))
        self.assertEqual(data2["storage_metrics"]["transcripts_count"], 1)

if __name__ == "__main__":
    unittest.main()
