"""Restore a backup made by backup_snapshot.py into the data folder, safely.

Usage: python deploy/restore_snapshot.py BACKUP.tar.gz /data

The backup is checked before anything is touched: every entry must be a plain file or folder inside the archive
(no absolute paths, no "..", no links or devices), it must contain archive.db, and every database in it must pass
SQLite's integrity check. It is unpacked to a staging folder first. Only then is the current data moved aside (never
deleted) into .before-restore-<time>, and the restored files moved in. Run it with the app stopped.
"""
import os
import shutil
import sqlite3
import sys
import tarfile
import time

MAX_BYTES = 200 * 1024 ** 3


class RestoreError(RuntimeError):
    pass


class RollbackIncompleteError(RestoreError):
    """Previous data still needs manual recovery; the app must stay stopped."""


def _safe_members(tar):
    members, total = [], 0
    for member in tar:
        name = member.name
        if name.startswith("/") or ".." in name.split("/") or "\\" in name:
            raise RestoreError(f"Unsafe path in backup: {name!r}")
        if not (member.isfile() or member.isdir()):
            raise RestoreError(f"Backup contains something other than files and folders: {name!r}")
        total += member.size
        if total > MAX_BYTES:
            raise RestoreError("Backup is larger than the safety limit.")
        members.append(member)
    return members


def restore(backup_path, data_dir):
    if not os.path.isfile(backup_path):
        raise RestoreError(f"Backup file not found: {backup_path}")
    os.makedirs(data_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    staging = os.path.join(data_dir, f".restore-staging-{stamp}")
    aside = os.path.join(data_dir, f".before-restore-{stamp}")
    try:
        with tarfile.open(backup_path, "r:gz") as tar:
            members = _safe_members(tar)
            if not any(m.name == "archive.db" for m in members):
                raise RestoreError("This does not look like a SeedReflections backup (no archive.db).")
            os.makedirs(staging)
            tar.extractall(staging, members=members)
        databases = []
        for folder, _dirs, files in os.walk(staging):
            for name in files:
                if name.endswith(".db"):
                    databases.append(os.path.join(folder, name))
        for path in databases:
            db = sqlite3.connect(path)
            try:
                result = db.execute("PRAGMA integrity_check").fetchone()[0]
            except sqlite3.DatabaseError as exc:
                result = str(exc)
            finally:
                db.close()
            if result != "ok":
                raise RestoreError(f"A database in the backup is damaged ({os.path.relpath(path, staging)}): {result}")
        os.makedirs(aside)
        moved_aside, moved_in = [], []
        try:
            for entry in os.listdir(data_dir):
                if entry.startswith(".restore-staging-") or entry.startswith(".before-restore-"):
                    continue
                shutil.move(os.path.join(data_dir, entry), os.path.join(aside, entry)); moved_aside.append(entry)
            for entry in os.listdir(staging):
                shutil.move(os.path.join(staging, entry), os.path.join(data_dir, entry)); moved_in.append(entry)
        except BaseException as exc:
            # Put everything back exactly as it was: take back what was moved in, then restore what was moved aside.
            stuck = []
            for entry in moved_in:
                try: shutil.move(os.path.join(data_dir, entry), os.path.join(staging, entry))
                except OSError: stuck.append(entry)
            for entry in moved_aside:
                try: shutil.move(os.path.join(aside, entry), os.path.join(data_dir, entry))
                except OSError: stuck.append(entry)
            if stuck:
                raise RollbackIncompleteError(f"The restore failed and could not fully undo itself. Your previous data is in {aside}; "
                                   f"these items could not be put back: {', '.join(stuck)}. Copy them back by hand before starting the app.") from exc
            raise RestoreError(f"The restore failed while moving files ({exc}). The previous data was put back unchanged.") from exc
        os.rmdir(staging)
        files = sum(len(f) for _d, _s, f in os.walk(data_dir) if ".before-restore-" not in _d and ".restore-staging-" not in _d)
        return {"restored_files": files, "databases_checked": len(databases), "previous_data_kept_at": aside}
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if os.path.isdir(aside) and not os.listdir(aside):
            os.rmdir(aside)
        raise


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python deploy/restore_snapshot.py BACKUP.tar.gz /data")
    try:
        summary = restore(sys.argv[1], sys.argv[2])
    except RollbackIncompleteError as exc:
        print(f"Restore requires manual recovery: {exc}", file=sys.stderr)
        sys.exit(2)
    except (RestoreError, tarfile.TarError, OSError) as exc:
        sys.exit(f"Restore refused: {exc}")
    print(f"Restored {summary['restored_files']} files; {summary['databases_checked']} databases passed the integrity check.")
    print(f"The data that was there before is kept at {summary['previous_data_kept_at']} (delete it once you are happy).")
