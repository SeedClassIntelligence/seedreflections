import json
import os
import shutil
import subprocess
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from test_unified_runtime import UnifiedRuntime

ROOT = Path(__file__).resolve().parents[1]
EXT = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"


def node_path():
    npm = shutil.which("npm")
    if not npm or not shutil.which("node"):
        return None
    root = subprocess.run([npm, "root", "-g"], capture_output=True, text=True).stdout.strip()
    return root if root and (Path(root) / "playwright").exists() else None


def post(runtime, path, body, headers):
    request = urllib.request.Request(f"http://127.0.0.1:{runtime.port}{path}", data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


class ExtensionTests(unittest.TestCase):
    def test_manifest_asks_for_the_least_it_needs(self):
        manifest = json.loads((ROOT / "extension/manifest.json").read_text())
        self.assertEqual(manifest["manifest_version"], 3)
        self.assertEqual(sorted(manifest["permissions"]), ["activeTab", "scripting", "storage"])
        self.assertNotIn("host_permissions", manifest)                 # no standing access to any site
        self.assertNotIn("content_scripts", manifest)                  # nothing runs unless the person clicks
        self.assertNotIn("background", manifest)                       # nothing runs in the background
        for icon in manifest["icons"].values():
            self.assertTrue((ROOT / "extension" / icon).exists())

    def test_local_server_lets_the_extension_deliver_with_a_token_and_nothing_else(self):
        runtime = UnifiedRuntime("local")
        try:
            _, made = runtime.request("POST", "/api/v2/integrations", {"name": "Browser extension", "provider": "browser_extension"})
            bearer = {"Authorization": "Bearer " + made["token"]}
            conversation = {"conversation": {"id": "ext-x", "title": "t", "messages": [{"id": "m1", "role": "user", "content": "hello"}]}}
            self.assertEqual(post(runtime, "/api/v2/integrations/import", conversation, {**bearer, "Origin": EXT}), 202)
            self.assertEqual(post(runtime, "/api/v2/integrations/ping", {}, {**bearer, "Origin": EXT}), 200)
            self.assertEqual(post(runtime, "/api/v2/integrations/ping", {}, {"Origin": EXT}), 403)                      # no token
            self.assertEqual(post(runtime, "/api/v2/integrations/import", conversation, {**bearer, "Origin": "http://evil.example"}), 403)
            self.assertEqual(post(runtime, "/api/v2/agent-tokens", {"name": "x"}, {**bearer, "Origin": EXT}), 403)      # other routes stay closed
            self.assertEqual(post(runtime, "/api/v2/imports", {"data": []}, {**bearer, "Origin": EXT}), 403)
        finally:
            runtime.close()

    @unittest.skipUnless(node_path(), "Node and Playwright are not installed")
    def test_readers_payload_and_delivery_against_a_real_server(self):
        runtime = UnifiedRuntime("local")
        try:
            _, made = runtime.request("POST", "/api/v2/integrations", {"name": "Browser extension", "provider": "browser_extension"})
            done = subprocess.run(["node", str(ROOT / "tests/extension/run.js"), f"http://127.0.0.1:{runtime.port}", made["token"]],
                                  capture_output=True, text=True, env={**os.environ, "NODE_PATH": node_path()}, timeout=120)
            results = json.loads(done.stdout.strip().splitlines()[-1])
            failed = [r for r in results if not r["ok"]]
            self.assertEqual(failed, [], failed)
            _, listing = runtime.request("GET", "/api/v2/conversations")
            titles = sorted(c["title"] for c in listing["conversations"])
            self.assertEqual(titles, ["Launch checklist", "Plan my launch week", "Pricing plan"])      # saved once each
        finally:
            runtime.close()

    @unittest.skipUnless(node_path(), "Node and Playwright are not installed")
    def test_the_real_extension_loads_and_its_popup_works(self):
        done = subprocess.run(["node", str(ROOT / "tests/extension/popup.js")], capture_output=True, text=True,
                              env={**os.environ, "NODE_PATH": node_path()}, timeout=120)
        results = json.loads(done.stdout.strip().splitlines()[-1])
        self.assertEqual([r for r in results if not r["ok"]], [], results)


if __name__ == "__main__":
    unittest.main()
