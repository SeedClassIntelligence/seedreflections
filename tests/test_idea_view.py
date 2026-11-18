import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from test_unified_runtime import UnifiedRuntime
from test_work_home import CONVERSATIONS, node_path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(node_path(), "Node and Playwright are not installed")
class IdeaViewTests(unittest.TestCase):
    def test_one_idea_shows_its_work_its_exact_source_its_outputs_and_its_decisions(self):
        runtime = UnifiedRuntime("local")
        try:
            runtime.request("POST", "/api/v2/imports", {"filename": "demo.json", "data": CONVERSATIONS})
            runtime.request("POST", "/api/v2/analysis/run", {})
            pending = []
            for _ in range(40):
                time.sleep(.5)
                pending = runtime.request("GET", "/api/v2/candidates?status=pending")[1].get("candidates", [])
                if len(pending) >= 4: break
            for candidate in pending:
                runtime.request("POST", f"/api/v2/candidates/{candidate['id']}/review", {"action": "accept"})
            workspace = runtime.request("GET", "/api/v2/workspace")[1]
            seeds = workspace["seeds"]; self.assertTrue(seeds)
            every_seed = [s["seed_id"] for s in seeds]
            runtime.request("POST", "/api/v2/artifacts", {"type": "plan", "title": "Pricing page plan", "content": "1. Tiers", "seed_ids": every_seed})
            expected = {}
            for seed in seeds:                                                     # what the page must show for each idea
                convo = runtime.request("GET", f"/api/v2/conversations/{seed['source_conversation_id']}")[1]
                message = next(m for m in convo["messages"] if m["id"] == seed["source_message_id"])
                expected[seed["title"]] = {"source": message["content"], "outputs": ["Pricing page plan"]}
            file = Path(tempfile.mkdtemp()) / "expected.json"; file.write_text(json.dumps(expected))
            done = subprocess.run(["node", str(ROOT / "tests/ideaview/run.js"), f"http://127.0.0.1:{runtime.port}", str(file)],
                                  capture_output=True, text=True, env={**os.environ, "NODE_PATH": node_path()}, timeout=240)
            results = json.loads(done.stdout.strip().splitlines()[-1])
            self.assertEqual([r for r in results if not r["ok"]], [], results)
        finally:
            runtime.close()


if __name__ == "__main__":
    unittest.main()
