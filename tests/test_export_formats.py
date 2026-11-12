import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import archive_store


class ExportFormatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(archive_store, "DB_PATH", Path(self.temp.name) / "archive.db")
        self.patch.start()
        archive_store.initialize()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def messages(self, result):
        found = archive_store.get_conversation(result["conversations"][0]["id"])
        return [(m["role"], m["content"]) for m in found["messages"]]

    def test_gemini_ai_studio_export(self):
        data = {"title": "Studio", "chunkedPrompt": {"chunks": [{"role": "user", "text": "hello"}, {"role": "model", "text": "hi"}]}}
        self.assertEqual(self.messages(archive_store.import_json(json.dumps(data), "studio.json")),
                         [("user", "hello"), ("assistant", "hi")])

    def test_gemini_takeout_activity_export(self):
        data = [{"header": "Gemini Apps", "title": "Prompted Plan my launch", "time": "2026-02-01T10:00:00Z",
                 "safeHtmlItem": [{"html": "<p>Launch in <b>March</b>.</p>"}]}]
        self.assertEqual(self.messages(archive_store.import_json(json.dumps(data), "MyActivity.json")),
                         [("user", "Plan my launch"), ("assistant", "Launch in March .")])

    def test_exports_without_ids_do_not_overwrite_each_other(self):
        for text in ("first", "second"):
            archive_store.import_json(json.dumps([{"title": text, "messages": [{"role": "user", "content": text}]}]), f"{text}.json")
        self.assertEqual(len(archive_store.list_conversations(limit=10)), 2)

    def test_chatgpt_and_claude_exports(self):
        chat = [{"id": "g1", "title": "t", "mapping": {"a": {"id": "a", "parent": None, "message": {"id": "a", "author": {"role": "user"}, "create_time": 1, "content": {"parts": ["q"]}}}}}]
        claude = [{"uuid": "c1", "name": "n", "chat_messages": [{"uuid": "m", "sender": "human", "text": "q"}]}]
        self.assertEqual(self.messages(archive_store.import_json(json.dumps(chat), "conversations.json")), [("user", "q")])
        self.assertEqual(len(self.messages(archive_store.import_json(json.dumps(claude), "claude.json"))), 1)


if __name__ == "__main__":
    unittest.main()
