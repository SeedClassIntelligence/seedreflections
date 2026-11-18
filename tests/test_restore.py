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


import shutil as _shutil
import subprocess as _subprocess
import textwrap as _textwrap
from unittest.mock import patch as _patch


class RestoreRollbackTests(unittest.TestCase):
    """A failure part-way through must leave the previous data exactly as it was."""

    def setup(self, work):
        data = Path(work) / "data"; data.mkdir(); make_data(data, rows=9, note="original source")
        backup = Path(work) / "b.tar.gz"
        other = Path(work) / "other"; other.mkdir(); make_data(other, rows=33, note="backup source")
        backup.write_bytes(backup_bytes(other))
        return data, backup

    def assert_untouched(self, data):
        db = sqlite3.connect(data / "archive.db"); self.assertEqual(db.execute("SELECT COUNT(*) FROM t").fetchone()[0], 9); db.close()
        self.assertEqual((data / "tenant_sources/ws1/doc.txt").read_text(), "original source")
        self.assertEqual([p.name for p in data.iterdir() if p.name.startswith((".restore-staging-", ".before-restore-"))], [])

    def fail_on_call(self, number):
        real, calls = _shutil.move, {"n": 0}
        def flaky(src, dst, *a, **k):
            calls["n"] += 1
            if calls["n"] == number: raise OSError("simulated failure")
            return real(src, dst, *a, **k)
        return _patch.object(restore_snapshot.shutil, "move", flaky)

    def test_a_failure_while_moving_the_old_data_aside_puts_everything_back(self):
        with tempfile.TemporaryDirectory() as work:
            data, backup = self.setup(work)
            with self.fail_on_call(2):                                   # the second item being moved aside
                with self.assertRaises(restore_snapshot.RestoreError) as caught: restore_snapshot.restore(str(backup), str(data))
            self.assertIn("put back unchanged", str(caught.exception)); self.assert_untouched(data)

    def test_a_failure_while_moving_the_restored_files_in_puts_everything_back(self):
        with tempfile.TemporaryDirectory() as work:
            data, backup = self.setup(work)
            entries = len([p for p in data.iterdir()])                   # items moved aside; the next move is the first restored item in
            with self.fail_on_call(entries + 2):                         # fail on the second restored item
                with self.assertRaises(restore_snapshot.RestoreError) as caught: restore_snapshot.restore(str(backup), str(data))
            self.assertIn("put back unchanged", str(caught.exception)); self.assert_untouched(data)
            self.assertTrue((data / "archive.db").exists())              # the exact case reviewed: the database is never left missing

    def test_an_incomplete_rollback_requires_manual_recovery(self):
        with tempfile.TemporaryDirectory() as work:
            data, backup = self.setup(work)
            real_move, calls = _shutil.move, {"n": 0}
            def fail_twice(src, dst, *args, **kwargs):
                calls["n"] += 1
                if calls["n"] in (4, 6): raise OSError("simulated restore and rollback failures")
                return real_move(src, dst, *args, **kwargs)
            with _patch.object(restore_snapshot.shutil, "move", fail_twice):
                with self.assertRaises(restore_snapshot.RollbackIncompleteError) as caught:
                    restore_snapshot.restore(str(backup), str(data))
            self.assertIn("before starting the app", str(caught.exception))
            self.assertTrue(any(data.glob(".before-restore-*/archive.db")))
            self.assertFalse((data / "archive.db").exists())


FAKE_DOCKER = _textwrap.dedent("""\
    #!/usr/bin/env bash
    echo "docker $*" >> "$FAKE_LOG"
    case "$*" in
      *" run "*) exit "${FAKE_RUN_EXIT:-0}";;
      *" exec "*) exit "${FAKE_HEALTH_EXIT:-0}";;
      *) exit 0;;
    esac
""")


class RestoreScriptFlowTests(unittest.TestCase):
    """The shell script's control flow, with a stand-in for docker and the backup script."""

    def run_script(self, run_exit=0, backup_ok=True, extra_env=None):
        work = tempfile.TemporaryDirectory(); root = Path(work.name)
        app = root / "app"; (app / "deploy").mkdir(parents=True)
        _shutil.copy(ROOT / "deploy/restore.sh", app / "deploy/restore.sh")
        (app / "deploy/backup.sh").write_text("#!/usr/bin/env bash\n" + ("exit 0\n" if backup_ok else "echo 'backup failed'; exit 1\n")); (app / "deploy/backup.sh").chmod(0o755)
        bin_dir = root / "bin"; bin_dir.mkdir(); (bin_dir / "docker").write_text(FAKE_DOCKER); (bin_dir / "docker").chmod(0o755)
        backup = root / "b.tar.gz"; backup.write_bytes(backup_bytes(self.make_source(root)))
        log = root / "log.txt"
        env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "SEEDREFLECTIONS_APP": str(app), "FAKE_LOG": str(log), "FAKE_RUN_EXIT": str(run_exit), **(extra_env or {})}
        bash = "bash"
        if os.name == "nt" and _shutil.which("git"):
            git_bash = Path(_shutil.which("git")).resolve().parents[1] / "bin" / "bash.exe"
            if git_bash.exists(): bash = str(git_bash)
        done = _subprocess.run([bash, str(app / "deploy/restore.sh"), str(backup)], capture_output=True, text=True, env=env, timeout=60)
        commands = log.read_text() if log.exists() else ""
        work.cleanup()
        return done, commands

    def make_source(self, root):
        src = root / "src"; src.mkdir(); make_data(src); return src

    def test_a_failed_safety_backup_stops_before_anything_changes(self):
        done, commands = self.run_script(backup_ok=False)
        self.assertNotEqual(done.returncode, 0); self.assertIn("nothing has been changed", done.stdout)
        self.assertNotIn(" stop ", commands)                                          # the app was never stopped
        done, commands = self.run_script(backup_ok=False, extra_env={"RESTORE_WITHOUT_SAFETY_BACKUP": "1"})
        self.assertEqual(done.returncode, 0); self.assertIn(" stop ", commands)       # only with the explicit override

    def test_if_the_restore_fails_after_the_app_was_stopped_the_app_is_started_again(self):
        done, commands = self.run_script(run_exit=3)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("Starting the app again", done.stdout)
        self.assertGreaterEqual(commands.count(" up -d "), 1)

    def test_an_incomplete_rollback_keeps_the_app_stopped_for_manual_recovery(self):
        done, commands = self.run_script(run_exit=2)
        self.assertEqual(done.returncode, 2)
        self.assertIn("Manual recovery is required", done.stdout)
        self.assertIn(" stop ", commands)
        self.assertNotIn(" up -d ", commands)

    def test_the_success_path_restores_and_starts_once(self):
        done, commands = self.run_script()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr); self.assertIn("Restore complete", done.stdout)
        self.assertEqual(commands.count(" up -d "), 1)
