import json, os, sqlite3, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch

import archive_store as store


_SEQ = {"n": 0}


def _payload(n):
    _SEQ["n"] += 1; tag = _SEQ["n"]
    return [{"id": f"c{tag}-{i}", "title": f"Conversation {tag}-{i}", "create_time": 1700000000 + i,
             "mapping": {"a": {"parent": None, "message": {"id": f"m{tag}-{i}", "create_time": 1700000001,
             "author": {"role": "user"}, "content": {"parts": [f"We decided to ship plan {i}."]}}}}} for i in range(n)]


class LocalRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(store, "DB_PATH", Path(self.temp.name) / "archive.db")
        self.patch.start(); store.initialize()
        with store._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS model_credentials(id TEXT, ciphertext TEXT)")

    def tearDown(self):
        self.patch.stop(); self.temp.cleanup()

    def _import(self, n):
        store.import_json(json.dumps(_payload(n)).encode(), f"export-{n}.json")

    def _count(self, table="conversations"):
        with store._connect() as db:
            return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def _backup(self):
        path = store.export_local_backup_archive(); target = Path(self.temp.name) / "backup.zip"
        target.write_bytes(path.read_bytes()); path.unlink(); return target

    def test_full_round_trip_replaces_state_preserves_credentials_and_takes_snapshot(self):
        self._import(3); backup = self._backup()
        self._import(5)  # work done after the backup
        with store._connect() as db: db.execute("INSERT INTO model_credentials VALUES('1','LIVE-SECRET')")
        self.assertEqual(self._count(), 8)
        preview = store.preview_local_restore(backup)
        self.assertEqual(preview["backup"]["Conversations"], 3); self.assertEqual(preview["current"]["Conversations"], 8)
        self.assertIn("model_credentials", preview["preserved"])
        result = store.apply_local_restore(preview["token"])
        self.assertEqual(self._count(), 3); self.assertEqual(result["restored"]["Conversations"], 3)
        with store._connect() as db:
            self.assertEqual(db.execute("SELECT ciphertext FROM model_credentials").fetchone()[0], "LIVE-SECRET")
        snapshot = Path(result["safety_snapshot"]); self.assertTrue(snapshot.exists())
        # the safety snapshot is itself a restorable backup of the pre-restore state (8 conversations)
        self.assertEqual(store.preview_local_restore(snapshot)["backup"]["Conversations"], 8)
        # staged copy is removed after a successful restore
        self.assertEqual([p for p in (Path(self.temp.name) / "restore-staging").glob("*.db") if p.stem == preview["token"]], [])

    def test_tampered_backup_is_refused_and_nothing_changes(self):
        self._import(3); backup = self._backup(); self._import(2)
        tampered = Path(self.temp.name) / "tampered.zip"
        with zipfile.ZipFile(backup) as zin, zipfile.ZipFile(tampered, "w") as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "archive.db": data = data[:200] + bytes([data[200] ^ 1]) + data[201:]
                zout.writestr(item, data)
        with self.assertRaisesRegex(store.RestoreError, "checksum"):
            store.preview_local_restore(tampered)
        self.assertEqual(self._count(), 5)
        self.assertEqual(list((Path(self.temp.name) / "restore-staging").glob("*.db")), [])

    def test_wrong_or_corrupt_files_are_refused(self):
        junk = Path(self.temp.name) / "junk.zip"; junk.write_bytes(b"not a zip")
        with self.assertRaises(store.RestoreError): store.preview_local_restore(junk)
        foreign = Path(self.temp.name) / "foreign.zip"
        with zipfile.ZipFile(foreign, "w") as z: z.writestr("manifest.json", "{}"); z.writestr("sources/x.json", "[]")
        with self.assertRaisesRegex(store.RestoreError, "unexpected contents"): store.preview_local_restore(foreign)

    def test_failure_midway_rolls_back_to_pre_restore_state(self):
        self._import(3); backup = self._backup(); self._import(4)
        with store._connect() as db: db.execute("INSERT INTO model_credentials VALUES('1','LIVE-SECRET')")
        preview = store.preview_local_restore(backup)
        calls = {"n": 0}; original = store._write_rows
        def boom(path, saved):
            calls["n"] += 1
            if calls["n"] == 1: raise sqlite3.OperationalError("simulated failure after the swap")
            return original(path, saved)
        with patch.object(store, "_write_rows", boom):
            with self.assertRaisesRegex(store.RestoreError, "previous archive was put back"):
                store.apply_local_restore(preview["token"])
        self.assertEqual(self._count(), 7)  # exactly the pre-restore state
        with store._connect() as db:
            self.assertEqual(db.execute("SELECT ciphertext FROM model_credentials").fetchone()[0], "LIVE-SECRET")

    def test_restore_is_refused_while_a_job_is_running(self):
        self._import(2); backup = self._backup(); preview = store.preview_local_restore(backup)
        job = store.create_analysis_job() if hasattr(store, "create_analysis_job") else None
        with store._connect() as db:
            db.execute("UPDATE analysis_jobs SET status='running'") if job else db.execute(
                "INSERT INTO import_jobs(id,filename,status,stage,progress,created_at,updated_at) VALUES('j','f','running','x',0,'t','t')")
        with self.assertRaisesRegex(store.RestoreError, "still running"):
            store.apply_local_restore(preview["token"])

    def test_invalid_and_expired_tokens_are_refused(self):
        for token in ["", "../../etc/passwd", "g" * 32, "0" * 32]:
            with self.assertRaises(store.RestoreError): store.apply_local_restore(token)
        self._import(2); preview = store.preview_local_restore(self._backup())
        staged = Path(self.temp.name) / "restore-staging" / f"{preview['token']}.db"
        os.utime(staged, (1, 1))
        with self.assertRaisesRegex(store.RestoreError, "expired"): store.apply_local_restore(preview["token"])


if __name__ == "__main__":
    unittest.main()
