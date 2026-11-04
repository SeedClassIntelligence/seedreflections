import json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

import seedbridge_client
from tests.test_unified_runtime import UnifiedRuntime


class SeedBridgeClientTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.home=Path(self.temp.name)/"bridge"
        self.environment=patch.dict(os.environ,{"SEEDBRIDGE_HOME":str(self.home)})
        self.environment.start()

    def tearDown(self):
        self.environment.stop(); self.temp.cleanup()

    def test_pair_authorize_and_incrementally_sync_to_workspace(self):
        runtime=UnifiedRuntime("local")
        try:
            status,created=runtime.request("POST","/api/v2/integrations",{"name":"My SeedBridge","provider":"codex"})
            self.assertEqual(status,201)
            with patch.object(seedbridge_client,"_windows_protect",lambda raw:b"protected:"+raw), patch.object(seedbridge_client,"_windows_unprotect",lambda raw:raw.removeprefix(b"protected:")):
                paired=seedbridge_client.pair(f"http://127.0.0.1:{runtime.port}",created["token"])
                self.assertEqual(paired["status"],"paired")
                self.assertNotIn(created["token"],seedbridge_client._config_path().read_text(encoding="utf-8"))

                source=Path(self.temp.name)/"sessions"; source.mkdir()
                (source/"session.jsonl").write_text("\n".join([
                    json.dumps({"session_id":"bridge-session","id":"one","role":"user","content":"Build the hosted SeedBridge."}),
                    json.dumps({"session_id":"bridge-session","id":"two","role":"assistant","content":"Pair and synchronize it."}),
                ]),encoding="utf-8")
                preview=seedbridge_client.connect("codex",source,False)
                self.assertTrue(preview["authorization_required"])
                authorized=seedbridge_client.connect("codex",source,True)
                first=seedbridge_client.sync(authorized["source"]["id"])
                self.assertEqual(first["sources"][0]["files_synced"],1)
                second=seedbridge_client.sync(authorized["source"]["id"])
                self.assertEqual(second["sources"][0]["files_synced"],0)
                self.assertEqual(second["sources"][0]["files_unchanged"],1)
            _,listing=runtime.request("GET","/api/v2/conversations")
            self.assertEqual(listing["total"],1)
        finally: runtime.close()

    def test_remote_pairing_rejects_plain_http(self):
        with self.assertRaisesRegex(ValueError,"HTTPS"):
            seedbridge_client.pair("http://example.com","sr_live_example")

    def test_pair_fails_closed_when_os_token_protection_is_unavailable(self):
        with patch.object(seedbridge_client,"_request",return_value=(200,{"integration":{"id":"bridge"}})), \
                patch.object(seedbridge_client,"protect_token",side_effect=OSError("protection unavailable")):
            paired=seedbridge_client.pair("https://seed.example","sr_live_example")
        config=seedbridge_client.load_config()
        self.assertEqual(paired["token_storage"],"environment_required")
        self.assertTrue(paired["environment_required"])
        self.assertEqual(config["token_env"],"SEEDBRIDGE_TOKEN")
        self.assertNotIn("token",config)
        self.assertNotIn("sr_live_example",seedbridge_client._config_path().read_text(encoding="utf-8"))
        with self.assertRaisesRegex(RuntimeError,"SEEDBRIDGE_TOKEN"):
            seedbridge_client.sync()


if __name__=="__main__": unittest.main()
