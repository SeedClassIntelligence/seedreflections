"""Regressions found during the CTO end-to-end review (November 2026)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import archive_store
import document_ingest


def _conv(i, with_message=True):
    mapping = {"a": {"parent": None, "message": {"id": f"m{i}", "create_time": 1700000000 + i,
               "author": {"role": "user"}, "content": {"parts": [f"We decided to ship pricing model {i}."]}}}} if with_message else None
    return {"id": f"c{i}", "title": f"Conversation {i}" if with_message else f"broken {i}",
            "create_time": 1700000000 + i, "mapping": mapping}


class CtoReviewRegressions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(archive_store, "DB_PATH", Path(self.temp.name) / "archive.db")
        self.patch.start(); archive_store.initialize()

    def tearDown(self):
        self.patch.stop(); self.temp.cleanup()

    def _import(self, payload):
        path = Path(self.temp.name) / "export.json"; path.write_text(json.dumps(payload))
        with patch.object(document_ingest, "preserve_source_path"):
            return document_ingest.import_document_path(path, "export.json")

    def test_unreadable_conversations_are_reported_not_counted_as_processed(self):
        result = self._import([_conv(1), _conv(2), _conv(3, with_message=False)])
        coverage = result["coverage"]
        self.assertEqual((coverage["detected"], coverage["processed"]), (3, 2))
        self.assertEqual(coverage["status"], "partial")
        self.assertEqual(coverage["unreadable_count"], 1)
        self.assertIn("broken 3", coverage["unreadable"][0])

    def test_fully_readable_archive_stays_complete(self):
        coverage = self._import([_conv(1), _conv(2)])["coverage"]
        self.assertEqual((coverage["status"], coverage["unreadable"]), ("complete", []))

    def test_search_never_raises_on_punctuation_and_count_matches_list(self):
        self._import([_conv(1), _conv(2), _conv(3, with_message=False)])
        for query in ["C++", "what?", "AND", "pricing-model", '"quoted', "a OR", "*", "NEAR(", "()"]:
            items = archive_store.list_conversations(query, 2000)
            self.assertEqual(len(items), archive_store.count_conversations(query), query)
        # message-less conversations remain findable by title
        self.assertEqual(archive_store.count_conversations("broken"), 1)
        self.assertEqual(len(archive_store.list_conversations("broken")), 1)
        self.assertEqual(archive_store.count_conversations("pricing"), 2)

    def test_candidate_queue_reports_true_total_and_paginates(self):
        self._import([_conv(i) for i in range(5)])
        for item in archive_store.list_conversations():
            archive_store.analyze_conversation(item["id"])
        total = archive_store.count_candidates("pending")
        self.assertGreaterEqual(total, 5)
        first = archive_store.list_candidates("pending", 2, 0)
        second = archive_store.list_candidates("pending", 2, 2)
        self.assertEqual(len(first), 2)
        self.assertFalse({c["id"] for c in first} & {c["id"] for c in second})

    def test_overview_message_total_is_not_capped_by_listing_limit(self):
        self._import([_conv(i) for i in range(600)])
        self.assertEqual(sum(row["messages"] for row in archive_store.source_coverage()), 600)


if __name__ == "__main__":
    unittest.main()


class LocalBackupSnapshot(unittest.TestCase):
    def test_local_backup_is_consistent_verifiable_and_carries_no_credentials(self):
        import hashlib, sqlite3, zipfile
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(archive_store, "DB_PATH", Path(directory) / "archive.db"):
                archive_store.initialize()
                with archive_store._connect() as db:
                    db.execute("CREATE TABLE IF NOT EXISTS model_credentials(id TEXT, ciphertext TEXT)")
                    db.execute("INSERT INTO model_credentials VALUES('1','SECRET-CIPHERTEXT')")
                package = archive_store.export_local_backup_archive()
                try:
                    with zipfile.ZipFile(package) as z:
                        manifest = json.loads(z.read("manifest.json"))
                        blob = z.read("archive.db")
                finally:
                    package.unlink()
                self.assertEqual(hashlib.sha256(blob).hexdigest(), manifest["sha256"])
                self.assertFalse(manifest["credentials_included"])
                self.assertNotIn(b"SECRET-CIPHERTEXT", blob)
                restored = Path(directory) / "restored.db"; restored.write_bytes(blob)
                connection = sqlite3.connect(restored)
                try:
                    self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM model_credentials").fetchone()[0], 0)
                finally:
                    connection.close()


class BoundedRelationshipGeneration(unittest.TestCase):
    def test_link_count_is_linear_and_nonempty_for_low_diversity_archives(self):
        # 2,000 candidates that all share the same common vocabulary used to
        # produce ~2 million stored links; storage must now be bounded per candidate.
        import time
        terms = [{"pricing", "model", "launch", f"unique{i % 40}"} for i in range(2000)]
        conversations = [f"c{i}" for i in range(2000)]
        started = time.monotonic()
        pairs = list(archive_store.bounded_term_pairs(terms, conversations))
        self.assertLess(time.monotonic() - started, 5)
        self.assertGreater(len(pairs), 0)
        self.assertLessEqual(len(pairs), 2000 * archive_store.MAX_LINKS_PER_CANDIDATE)
        degree = {}
        for i, j, shared in pairs:
            self.assertNotEqual(conversations[i], conversations[j])
            self.assertGreaterEqual(len(shared), 2)
            degree[i] = degree.get(i, 0) + 1; degree[j] = degree.get(j, 0) + 1
        self.assertLessEqual(max(degree.values()), archive_store.MAX_LINKS_PER_CANDIDATE)

    def test_same_conversation_candidates_are_never_linked(self):
        terms = [{"alpha", "beta", "gamma"}, {"alpha", "beta", "gamma"}]
        self.assertEqual(list(archive_store.bounded_term_pairs(terms, ["same", "same"])), [])
        self.assertEqual(len(list(archive_store.bounded_term_pairs(terms, ["a", "b"]))), 1)


class StaticFileAllowlist(unittest.TestCase):
    def test_only_public_assets_resolve(self):
        import server
        blocked = ["server.py", "auth_store.py", ".git/config", ".env", "data/archive.db", "admin-dashboard.html",
                   "config.example.json", "tests/test_archive_store.py", "../server.py", "assets/../server.py",
                   "js/../server.py", "Dockerfile", "patch_server.py", "assets", "assets/.hidden.css", "walkthrough.md"]
        for name in blocked:
            self.assertIsNone(server.static_file_path(name), name)
        for name in ["index.html", "auth.html", "consumer-dashboard.html", "assets/style.css", "js/platform.js", "assets/seed-logo.png"]:
            resolved = server.static_file_path(name)
            self.assertIsNotNone(resolved, name)
            self.assertTrue(Path(resolved).is_relative_to(Path.cwd().resolve()))

    def test_admin_page_is_only_reachable_through_the_authenticated_route(self):
        import server
        self.assertIsNone(server.static_file_path("admin-dashboard.html"))
        self.assertIsNotNone(server.static_file_path("admin-dashboard.html", internal=True))

    def test_hosted_readiness_rejects_default_admin_password(self):
        import server
        with patch.object(server, "DEPLOYMENT_MODE", "hosted"), patch.object(server, "PUBLIC_ORIGIN", "https://example.test"), \
             patch.dict(server.CONFIG, {}, clear=False), patch.dict("os.environ", {"ADMIN_PASSWORD": "changeme"}):
            server.CONFIG.pop("ADMIN_PASSWORD", None)
            checks = {c["name"]: c for c in server.production_readiness()["checks"]}
            self.assertFalse(checks["admin_password"]["passed"])
        with patch.object(server, "DEPLOYMENT_MODE", "hosted"), patch.object(server, "PUBLIC_ORIGIN", "https://example.test"), \
             patch.dict("os.environ", {"ADMIN_PASSWORD": "a-long-random-secret-1"}):
            server.CONFIG.pop("ADMIN_PASSWORD", None)
            checks = {c["name"]: c for c in server.production_readiness()["checks"]}
            self.assertTrue(checks["admin_password"]["passed"])
