import os, sqlite3, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

import archive_store
import secret_store


class MemoryKeyring:
    """Stand-in OS keychain with a priority > 0, so it counts as a real backend."""
    priority = 5
    def __init__(self): self.items = {}
    def set_password(self, service, name, value): self.items[(service, name)] = value
    def get_password(self, service, name): return self.items.get((service, name))
    def delete_password(self, service, name): self.items.pop((service, name), None)


class FakeKeyringModule:
    def __init__(self, backend): self.backend = backend
    def __getattr__(self, name): return getattr(self.backend, name)


@unittest.skipIf(os.name == "nt", "Windows uses DPAPI; these tests cover the macOS/Linux paths")
class NonWindowsKeyStorage(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        for target in (archive_store, secret_store):
            p = patch.object(target, "DB_PATH", Path(self.temp.name) / "archive.db"); p.start(); self.addCleanup(p.stop)
        secret_store._SESSION_KEYS.clear(); self.addCleanup(secret_store._SESSION_KEYS.clear)

    def _with_keychain(self):
        self.keychain = MemoryKeyring()
        patcher = patch.object(secret_store, "_keyring_module", lambda: FakeKeyringModule(self.keychain)); patcher.start(); self.addCleanup(patcher.stop)

    def _without_keychain(self):
        patcher = patch.object(secret_store, "_keyring_module", lambda: None); patcher.start(); self.addCleanup(patcher.stop)

    def _db_text(self):
        return Path(self.temp.name, "archive.db").read_bytes()

    def test_saved_key_goes_to_keychain_and_database_holds_no_key_material(self):
        self._with_keychain()
        status = secret_store.set_credential("local", "openai", "sk-SECRET-VALUE-1234", "local")
        self.assertEqual((status["credential_configured"], status["scheme"], status["key_hint"]), (True, "os_keyring", "1234"))
        self.assertEqual(secret_store.get_credential("local", "openai"), "sk-SECRET-VALUE-1234")
        self.assertNotIn(b"SECRET-VALUE", self._db_text())
        self.assertTrue(secret_store.local_backend_status()["saved_keys"])

    def test_delete_removes_key_from_keychain_too(self):
        self._with_keychain(); secret_store.set_credential("local", "openai", "sk-abcdef", "local")
        self.assertTrue(secret_store.delete_credential("local", "openai"))
        self.assertEqual(self.keychain.items, {}); self.assertEqual(secret_store.get_credential("local", "openai"), "")

    def test_without_keychain_saving_fails_closed_and_writes_nothing(self):
        self._without_keychain()
        status = secret_store.local_backend_status()
        self.assertFalse(status["saved_keys"]); self.assertTrue(status["session_only_keys"])
        with self.assertRaisesRegex(RuntimeError, "session-only"):
            secret_store.set_credential("local", "openai", "sk-PLAINTEXT-LEAK-9999", "local")
        self.assertEqual(secret_store.get_credential("local", "openai"), "")
        db = Path(self.temp.name, "archive.db")
        self.assertTrue(not db.exists() or b"PLAINTEXT-LEAK" not in db.read_bytes())

    def test_session_only_key_is_usable_but_never_persisted(self):
        self._without_keychain()
        status = secret_store.set_credential("local", "openai", "sk-SESSION-ONLY-5555", "local", temporary=True)
        self.assertEqual((status["scheme"], status["persisted"]), ("session_only", False))
        self.assertEqual(secret_store.get_credential("local", "openai"), "sk-SESSION-ONLY-5555")
        db = Path(self.temp.name, "archive.db")
        self.assertTrue(not db.exists() or b"SESSION-ONLY" not in db.read_bytes())
        secret_store._SESSION_KEYS.clear()  # simulates a restart
        self.assertEqual(secret_store.get_credential("local", "openai"), "")

    def test_session_only_keys_are_refused_in_hosted_mode(self):
        with self.assertRaisesRegex(ValueError, "local mode"):
            secret_store.set_credential("ws", "openai", "sk-x", "hosted", temporary=True)

    def test_saving_a_persistent_key_replaces_a_session_key(self):
        self._with_keychain()
        secret_store.set_credential("local", "openai", "sk-TEMP-1111", "local", temporary=True)
        secret_store.set_credential("local", "openai", "sk-SAVED-2222", "local")
        self.assertEqual(secret_store.get_credential("local", "openai"), "sk-SAVED-2222")

    def test_local_backup_never_contains_the_key(self):
        self._with_keychain(); secret_store.set_credential("local", "openai", "sk-BACKUP-CHECK-7777", "local")
        package = archive_store.export_local_backup_archive()
        try:
            import zipfile
            with zipfile.ZipFile(package) as z: blob = z.read("archive.db")
        finally: package.unlink()
        self.assertNotIn(b"BACKUP-CHECK", blob)


if __name__ == "__main__":
    unittest.main()
