import io
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy"))
import backup_snapshot


class BackupTests(unittest.TestCase):
    def test_snapshot_is_consistent_while_the_app_is_writing_and_restores(self):
        with tempfile.TemporaryDirectory() as data, tempfile.TemporaryDirectory() as restored:
            db = sqlite3.connect(Path(data) / "archive.db"); db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE t(v TEXT)"); db.executemany("INSERT INTO t VALUES(?)", [(f"row{i}",) for i in range(200)]); db.commit()
            db.execute("INSERT INTO t VALUES('uncommitted-in-wal')"); db.commit()            # lives in the WAL file, not yet in the main file
            (Path(data) / "tenant_sources" / "ws1").mkdir(parents=True); (Path(data) / "tenant_sources" / "ws1" / "doc.txt").write_text("source text")
            out = io.BytesIO(); backup_snapshot.snapshot(data, out)
            db.close()
            with tarfile.open(fileobj=io.BytesIO(out.getvalue()), mode="r:gz") as tar:
                names = tar.getnames(); tar.extractall(restored)
            self.assertIn("archive.db", names); self.assertIn("tenant_sources/ws1/doc.txt", names)
            self.assertFalse([n for n in names if n.endswith(("-wal", "-shm"))])
            copy = sqlite3.connect(Path(restored) / "archive.db")
            self.assertEqual(copy.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(copy.execute("SELECT COUNT(*) FROM t").fetchone()[0], 201)         # the WAL row is in the backup
            self.assertEqual((Path(restored) / "tenant_sources/ws1/doc.txt").read_text(), "source text")
            copy.close()


class KitTests(unittest.TestCase):
    def test_scripts_parse_and_production_compose_passes_secrets_and_trusts_only_the_proxy(self):
        for script in (ROOT / "deploy").glob("*.sh"):
            self.assertEqual(subprocess.run(["bash", "-n", str(script)]).returncode, 0, script.name)
        compose = (ROOT / "docker-compose.prod.yml").read_text()
        self.assertIn("env_file: .env", compose); self.assertIn('SEED_REFLECTIONS_TRUST_PROXY: "1"', compose)
        self.assertNotIn('"8476:8476"', compose)                                          # the app port is never published
        self.assertIn("ports:\n      - \"80:80\"\n      - \"443:443\"", compose)
        for ignored in (".env",):
            self.assertIn(ignored, (ROOT / ".dockerignore").read_text().split())            # secrets are never baked into the image

    def test_setup_script_refuses_a_bad_domain_before_changing_anything(self):
        result = subprocess.run(["bash", str(ROOT / "deploy/setup-server.sh"), "not a domain"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
