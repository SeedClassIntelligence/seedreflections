import base64, os, sqlite3, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import secret_store

class SecretStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.original=secret_store.DB_PATH
        secret_store.DB_PATH=Path(self.temp.name)/"secrets.db"
    def tearDown(self):
        secret_store.DB_PATH=self.original; self.temp.cleanup()

    @unittest.skipUnless(os.name=="nt","DPAPI is Windows-specific")
    def test_local_dpapi_round_trip_and_no_plaintext(self):
        value="sk-secret-value-1234"
        def protected(raw,protect=True): return (b"protected:"+raw) if protect else raw.removeprefix(b"protected:")
        with patch.object(secret_store,"_dpapi",side_effect=protected):
            status=secret_store.set_credential("workspace-a","openai",value,"local")
            self.assertTrue(status["credential_configured"]); self.assertEqual(status["key_hint"],"1234")
            self.assertEqual(secret_store.get_credential("workspace-a","openai"),value)
            self.assertNotIn(value,secret_store.DB_PATH.read_bytes().decode("latin1"))

    def test_hosted_envelope_round_trip_and_tenant_isolation(self):
        master=base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")
        with patch.dict(os.environ,{"SEED_REFLECTIONS_CREDENTIAL_MASTER_KEY":master}):
            secret_store.set_credential("workspace-a","anthropic","sk-ant-private-7788","hosted")
            self.assertEqual(secret_store.get_credential("workspace-a","anthropic"),"sk-ant-private-7788")
            self.assertEqual(secret_store.get_credential("workspace-b","anthropic"),"")

    def test_hosted_fails_closed_without_master_key(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(RuntimeError): secret_store.set_credential("workspace-a","openai","secret","hosted")

    def test_delete_and_metadata_never_return_secret(self):
        master=base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")
        with patch.dict(os.environ,{"SEED_REFLECTIONS_CREDENTIAL_MASTER_KEY":master}):
            secret_store.set_credential("workspace-a","gemini","private-key-9999","hosted")
            status=secret_store.credential_status("workspace-a","gemini")
            self.assertNotIn("ciphertext",status); self.assertNotIn("private-key",str(status))
            self.assertTrue(secret_store.delete_credential("workspace-a","gemini"))
            self.assertFalse(secret_store.credential_status("workspace-a","gemini")["credential_configured"])

if __name__=="__main__": unittest.main()
