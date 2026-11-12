import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import archive_store
import connector_store


class SeedBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "archive.db"
        self.db_patches = [patch.object(connector_store, "DB_PATH", self.db), patch.object(archive_store, "DB_PATH", self.db)]
        for item in self.db_patches: item.start()

    def tearDown(self):
        for item in reversed(self.db_patches): item.stop()
        self.temp.cleanup()

    def test_manifest_declares_truthful_local_read_only_capabilities(self):
        manifest = connector_store.bridge_manifest()
        self.assertEqual(manifest["name"], "SeedBridge")
        self.assertTrue(manifest["read_only"])
        self.assertTrue(manifest["consent_required"])
        self.assertFalse(manifest["capabilities"]["cloud_history_bypass"])
        self.assertIn("codex", {item["provider"] for item in manifest["adapters"]})

    def test_preview_authorize_and_incremental_sync_codex_jsonl(self):
        source = self.root / "codex-sessions"; source.mkdir()
        session = source / "session.jsonl"
        session.write_text("\n".join([
            json.dumps({"session_id":"session-1","id":"m1","role":"user","content":"Build SeedBridge"}),
            json.dumps({"session_id":"session-1","id":"m2","role":"assistant","content":"Connector ready"}),
        ]), encoding="utf-8")
        preview = connector_store.preview_source("codex", source)
        self.assertEqual(len(preview["items"]), 1)
        connected = connector_store.connect_preview(preview["preview_id"], ["session.jsonl"], False)
        self.assertEqual(connected["sync"]["files_changed"], 1)
        self.assertEqual(connected["sync"]["conversations"], 1)
        unchanged = connector_store.sync_connector(connected["connector"]["id"])
        self.assertEqual(unchanged["files_changed"], 0)

    def test_real_codex_rollout_format_is_read(self):
        src = self.root / "src"; src.mkdir()
        lines = [{"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "caching question"}]}},
                 {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "answer"}]}}]
        (src / "rollout.jsonl").write_text("\n".join(json.dumps(x) for x in lines))
        preview = connector_store.preview_source("codex", str(src))
        self.assertEqual(preview["items"][0]["message_count"], 2)

    def test_links_pointing_outside_the_folder_are_never_read(self):
        src = self.root / "src"; src.mkdir()
        outside = self.root / "outside.md"; outside.write_text("OUTSIDE SECRET")
        (src / "ok.md").write_text("fine")
        try: (src / "link.md").symlink_to(outside)
        except OSError: self.skipTest("symlinks unavailable")
        preview = connector_store.preview_source("folder", str(src))
        self.assertEqual([i["path"] for i in preview["items"]], ["ok.md"])


if __name__ == "__main__": unittest.main()
