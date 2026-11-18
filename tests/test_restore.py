import gzip
import io
import json
import os
import sqlite3
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy")); sys.path.insert(0, str(Path(__file__).parent))
import backup_snapshot
import restore_snapshot
from test_unified_runtime import UnifiedRuntime


def make_data(path, rows=50, note="source text"):
    db = sqlite3.connect(Path(path) / "archive.db"); db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS t(v TEXT)"); db.executemany("INSERT INTO t VALUES(?)", [(f"row{i}",) for i in range(rows)]); db.commit(); db.close()
    (Path(path) / "tenant_sources" / "ws1").mkdir(parents=True, exist_ok=True); (Path(path) / "tenant_sources" / "ws1" / "doc.txt").write_text(note)


def backup_bytes(path):
    out = io.BytesIO(); backup_snapshot.snapshot(str(path), out); return out.getvalue()


def write_tar(path, entries):
    with tarfile.open(path, "w:gz") as tar:
        for name, data, kind in entries:
            info = tarfile.TarInfo(name)
            if kind == "file": info.size = len(data); tar.addfile(info, io.BytesIO(data))
            elif kind == "symlink": info.type = tarfile.SYMTYPE; info.linkname = "/etc/passwd"; tar.addfile(info)


class RestoreDrillTests(unittest.TestCase):
    def test_a_backup_restores_after_the_data_is_lost_and_keeps_what_was_there(self):
        with tempfile.TemporaryDirectory() as work:
            data = Path(work) / "data"; data.mkdir(); make_data(data)
            backup = Path(work) / "b.tar.gz"; backup.write_bytes(backup_bytes(data))
            for victim in data.rglob("*"):                                   # disaster: wipe the data and leave junk
                if victim.is_file(): victim.unlink()
            (data / "junk.txt").write_text("not from the backup")
            summary = restore_snapshot.restore(str(backup), str(data))
            db = sqlite3.connect(data / "archive.db")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM t").fetchone()[0], 50); db.close()
            self.assertEqual((data / "tenant_sources/ws1/doc.txt").read_text(), "source text")
            self.assertFalse((data / "junk.txt").exists())
            kept = Path(summary["previous_data_kept_at"]); self.assertTrue((kept / "junk.txt").exists())          # moved aside, not deleted
            self.assertEqual(summary["databases_checked"], 1)
            again = backup_bytes(data)                                                                           # the safety copy is not swept into later backups
            with tarfile.open(fileobj=io.BytesIO(again), mode="r:gz") as tar:
                self.assertFalse([n for n in tar.getnames() if ".before-restore-" in n])

    def test_unsafe_damaged_or_wrong_backups_are_refused_and_nothing_changes(self):
        with tempfile.TemporaryDirectory() as work:
            data = Path(work) / "data"; data.mkdir(); make_data(data, rows=7)
            bad = {"traversal": [("../evil.txt", b"x", "file"), ("archive.db", b"", "file")],
                   "absolute": [("/etc/evil.txt", b"x", "file")],
                   "symlink": [("archive.db", b"", "file"), ("link", b"", "symlink")],
                   "not_a_backup": [("hello.txt", b"hi", "file")],
                   "damaged_database": [("archive.db", b"this is not a sqlite database at all " * 50, "file")]}
            for label, entries in bad.items():
                path = Path(work) / f"{label}.tar.gz"; write_tar(path, entries)
                with self.assertRaises(restore_snapshot.RestoreError, msg=label):
                    restore_snapshot.restore(str(path), str(data))
            plain = Path(work) / "plain.tar.gz"; plain.write_bytes(b"definitely not gzip")
            with self.assertRaises(Exception): restore_snapshot.restore(str(plain), str(data))
            db = sqlite3.connect(data / "archive.db"); self.assertEqual(db.execute("SELECT COUNT(*) FROM t").fetchone()[0], 7); db.close()   # untouched
            self.assertEqual([p.name for p in data.iterdir() if p.name.startswith((".restore-", ".before-"))], [])                                  # no leftovers
            self.assertFalse((Path(work) / "evil.txt").exists() or Path("/etc/evil.txt").exists())

    def test_the_real_app_comes_back_with_its_accounts_and_archive_after_a_restore(self):
        password = "strong-password-123"
        first = UnifiedRuntime("hosted")
        try:
            _, user = first.request("POST", "/api/v2/auth/signup", {"name": "Ann", "email": "ann@example.com", "password": password})
            first.request("POST", "/api/v2/imports", {"filename": "h.json", "data": [{"id": "c1", "title": "Pricing plan", "messages": [{"id": "m", "role": "user", "content": "Launch fortnightly."}]}]}, token=user["access_token"])
            blob = backup_bytes(first.temp.name)                                  # a backup taken while the app is running
        finally:
            first.close()
        with tempfile.TemporaryDirectory() as fresh:
            backup = Path(fresh) / "b.tar.gz"; backup.write_bytes(blob)
            target = Path(fresh) / "data"; target.mkdir()
            restore_snapshot.restore(str(backup), str(target))
            second = UnifiedRuntime("hosted", {"SEED_REFLECTIONS_DATA_DIR": str(target)})
            try:
                status, login = second.request("POST", "/api/v2/auth/login", {"email": "ann@example.com", "password": password})
                self.assertEqual(status, 200)
                _, listing = second.request("GET", "/api/v2/conversations", token=login["access_token"])
                self.assertEqual([c["title"] for c in listing["conversations"]], ["Pricing plan"])
            finally:
                second.close()


if __name__ == "__main__":
    unittest.main()
