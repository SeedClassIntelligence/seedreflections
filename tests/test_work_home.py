import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from test_unified_runtime import UnifiedRuntime

ROOT = Path(__file__).resolve().parents[1]


def node_path():
    npm = shutil.which("npm")
    if not npm or not shutil.which("node"):
        return None
    root = subprocess.run([npm, "root", "-g"], capture_output=True, text=True).stdout.strip()
    return root if root and (Path(root) / "playwright").exists() else None


CONVERSATIONS = [
    {"id": "c1", "title": "Pricing for the beta", "messages": [
        {"id": "m1", "role": "user", "content": "We should launch a pricing page for the beta next month."},
        {"id": "m2", "role": "assistant", "content": "Good idea. Which tiers?"},
        {"id": "m3", "role": "user", "content": "I decided to go with three tiers: free, pro and team."}]},
    {"id": "c2", "title": "Onboarding testers", "messages": [
        {"id": "m1", "role": "user", "content": "How will we onboard the first twenty testers?"},
        {"id": "m2", "role": "user", "content": "Let's draft the onboarding email and decide who sends it."}]},
    {"id": "c3", "title": "Hosting plan", "messages": [
        {"id": "m1", "role": "user", "content": "I decided to keep the signing authority separate from everything else."},
        {"id": "m2", "role": "user", "content": "We need to rehearse a restore before launch."}]},
]


@unittest.skipUnless(node_path(), "Node and Playwright are not installed")
class WorkHomeTests(unittest.TestCase):
    def test_the_workspace_opens_on_what_needs_attention_where_you_left_off_and_what_to_start(self):
        full, empty = UnifiedRuntime("local"), UnifiedRuntime("local")
        try:
            full.request("POST", "/api/v2/imports", {"filename": "demo.json", "data": CONVERSATIONS})
            full.request("POST", "/api/v2/analysis/run", {})
            pending = []
            for _ in range(40):
                time.sleep(.5)
                pending = full.request("GET", "/api/v2/candidates?status=pending")[1].get("candidates", [])
                if len(pending) >= 4: break
            for candidate in pending[:2]:
                full.request("POST", f"/api/v2/candidates/{candidate['id']}/review", {"action": "accept"})
            full.request("POST", "/api/v2/artifacts", {"type": "plan", "title": "Beta launch plan", "content": "1. Pricing page"})
            left = full.request("GET", "/api/v2/overview")[1]["pending"]
            self.assertGreaterEqual(left, 1)
            done = subprocess.run(["node", str(ROOT / "tests/workhome/run.js"), f"http://127.0.0.1:{full.port}", f"http://127.0.0.1:{empty.port}", str(left)],
                                  capture_output=True, text=True, env={**os.environ, "NODE_PATH": node_path()}, timeout=180)
            results = json.loads(done.stdout.strip().splitlines()[-1])
            self.assertEqual([r for r in results if not r["ok"]], [], results)
        finally:
            full.close(); empty.close()


if __name__ == "__main__":
    unittest.main()
