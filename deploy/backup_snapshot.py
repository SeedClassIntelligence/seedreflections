"""Write a consistent gzip tar of the data folder to stdout.

Databases are copied with SQLite's own backup call, so a copy taken while the app is writing is still
valid; everything else (uploaded source files) is added as it is. WAL side files are skipped because the
backup call already folds them in. Usage: python deploy/backup_snapshot.py /data > backup.tar.gz
"""
import os
import sqlite3
import sys
import tarfile
import tempfile


def snapshot(root, out):
    scratch = tempfile.mkdtemp(prefix="seed-backup-")
    with tarfile.open(fileobj=out, mode="w|gz") as tar:
        for folder, _dirs, files in os.walk(root):
            for name in sorted(files):
                path = os.path.join(folder, name); arc = os.path.relpath(path, root)
                if name.endswith(("-wal", "-shm")):
                    continue
                if name.endswith(".db"):
                    copy = os.path.join(scratch, arc.replace(os.sep, "_"))
                    source = sqlite3.connect(path); target = sqlite3.connect(copy)
                    with target: source.backup(target)
                    target.close(); source.close()
                    tar.add(copy, arcname=arc); os.unlink(copy)
                else:
                    tar.add(path, arcname=arc)
    os.rmdir(scratch)


if __name__ == "__main__":
    snapshot(sys.argv[1] if len(sys.argv) > 1 else "/data", sys.stdout.buffer)
