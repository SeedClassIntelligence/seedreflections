import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import archive_store
import document_ingest


class DocumentIngestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(archive_store, "DB_PATH", Path(self.temp.name) / "archive.db")
        self.db_patch.start()
        archive_store.initialize()

    def tearDown(self):
        self.db_patch.stop()
        self.temp.cleanup()

    def test_text_document_uses_same_archive_contract_and_preserves_source(self):
        payload = b"User: I want to continue the housing project.\nAssistant: Let us recover the decisions."
        result = document_ingest.import_document(payload, "housing-notes.txt")
        self.assertEqual(result["coverage"]["status"], "complete")
        detail = archive_store.get_conversation(result["conversations"][0]["id"])
        self.assertIn("housing project", detail["messages"][0]["content"])
        with archive_store._connect() as db:
            source = db.execute("SELECT * FROM source_files WHERE import_id=?", (result["import_id"],)).fetchone()
        self.assertEqual(source["content"], payload)

    def test_docx_reads_body_headers_footnotes_and_comments(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as package:
            package.writestr("word/document.xml", '<w:document xmlns:w="x"><w:p><w:r><w:t>Body idea</w:t></w:r></w:p></w:document>')
            package.writestr("word/header1.xml", '<w:hdr xmlns:w="x"><w:p><w:r><w:t>Header context</w:t></w:r></w:p></w:hdr>')
            package.writestr("word/footnotes.xml", '<w:footnotes xmlns:w="x"><w:footnote><w:p><w:r><w:t>Footnote evidence</w:t></w:r></w:p></w:footnote></w:footnotes>')
            package.writestr("word/comments.xml", '<w:comments xmlns:w="x"><w:comment><w:p><w:r><w:t>Reviewer decision</w:t></w:r></w:p></w:comment></w:comments>')
        extracted = document_ingest.extract_document(buffer.getvalue(), "complete.docx")
        self.assertEqual(extracted["coverage"]["status"], "complete")
        for expected in ("Body idea", "Header context", "Footnote evidence", "Reviewer decision"):
            self.assertIn(expected, extracted["text"])

    def test_zip_reports_every_file_and_partial_coverage(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as package:
            package.writestr("notes.txt", "Complete notes")
            package.writestr("unsupported.bin", b"binary")
        extracted = document_ingest.extract_document(buffer.getvalue(), "archive.zip")
        self.assertEqual(extracted["coverage"]["detected"], 2)
        self.assertEqual(extracted["coverage"]["processed"], 1)
        self.assertEqual(extracted["coverage"]["status"], "partial")
        self.assertEqual(extracted["coverage"]["unreadable"], ["unsupported.bin"])

    def test_exact_source_reimport_is_idempotent_and_visible_in_ledger(self):
        payload = b"User: Keep this source once.\nAssistant: Understood."
        first = document_ingest.import_document(payload, "one-copy.txt")
        second = document_ingest.import_document(payload, "renamed-copy.txt")
        self.assertFalse(first.get("duplicate", False))
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["import_id"], second["import_id"])
        self.assertEqual(len(archive_store.list_conversations()), 1)
        ledger = archive_store.list_imports()
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0]["coverage"]["status"], "complete")


if __name__ == "__main__":
    unittest.main()
