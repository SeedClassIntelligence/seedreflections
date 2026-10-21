import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import workspace_store


class WorkspaceStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_patch = patch.object(workspace_store, "DB_PATH", self.root / "archive.db")
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.temp.cleanup()

    def test_json_is_migrated_once_and_becomes_read_only_source_evidence(self):
        legacy = self.root / "seeds.json"
        original = {"seeds":[{"seed_id":"one","title":"Original"}],"projects":[],"sources":[],
                    "decisions":[],"conflicts":[],"relationships":[],"accounts":[],"telemetry":[]}
        legacy.write_text(json.dumps(original, indent=2), encoding="utf-8")
        before = legacy.read_bytes()
        first = workspace_store.load_workspace(legacy)
        self.assertEqual(first["seeds"][0]["title"], "Original")
        first["seeds"][0]["title"] = "Stored in SQLite"
        revision = workspace_store.save_workspace(first, reason="test_update")
        self.assertEqual(revision, 2)
        self.assertEqual(workspace_store.load_workspace(legacy)["seeds"][0]["title"], "Stored in SQLite")
        self.assertEqual(legacy.read_bytes(), before)
        status = workspace_store.storage_status()
        self.assertEqual(status["backend"], "sqlite_normalized")
        self.assertEqual(status["schema_version"], 2)
        self.assertEqual(status["entity_counts"]["seeds"], 1)
        self.assertEqual(status["revision"], 2)
        self.assertEqual(status["revision_count"], 2)
        self.assertTrue(status["source_sha256"])

    def test_existing_sqlite_state_is_not_overwritten_by_changed_legacy_file(self):
        legacy = self.root / "seeds.json"
        legacy.write_text(json.dumps({"seeds":[{"title":"First"}]}), encoding="utf-8")
        workspace_store.load_workspace(legacy)
        legacy.write_text(json.dumps({"seeds":[{"title":"Changed outside store"}]}), encoding="utf-8")
        self.assertEqual(workspace_store.load_workspace(legacy)["seeds"][0]["title"], "First")

    def test_normalized_entities_are_authoritative_over_compatibility_snapshot(self):
        legacy = self.root / "seeds.json"
        legacy.write_text(json.dumps({"seeds":[{"seed_id":"one","title":"Normalized authority"}],
            "projects":[],"decisions":[],"relationships":[],"conflicts":[],"sources":[],"accounts":[],"telemetry":[]}), encoding="utf-8")
        workspace_store.load_workspace(legacy)
        db = sqlite3.connect(self.root / "archive.db")
        try:
            db.execute("UPDATE workspace_state SET document_json=? WHERE workspace_id='local'",
                       (json.dumps({"seeds":[{"seed_id":"one","title":"Stale snapshot"}]}),))
            db.commit()
        finally:
            db.close()
        loaded = workspace_store.load_workspace(legacy)
        self.assertEqual(loaded["seeds"][0]["title"], "Normalized authority")


if __name__ == "__main__":
    unittest.main()
