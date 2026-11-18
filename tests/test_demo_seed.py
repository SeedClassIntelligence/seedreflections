import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from test_unified_runtime import UnifiedRuntime

ROOT = Path(__file__).resolve().parents[1]


class DemoSeedTests(unittest.TestCase):
    def test_the_demo_fills_a_local_server_and_refuses_anything_else(self):
        runtime = UnifiedRuntime("local")
        try:
            done = subprocess.run([sys.executable, str(ROOT / "scripts/seed_demo.py"), f"http://127.0.0.1:{runtime.port}"], capture_output=True, text=True, timeout=120)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            overview = runtime.request("GET", "/api/v2/overview")[1]
            self.assertEqual(overview["conversations"], 6); self.assertGreaterEqual(overview["pending"], 2)       # something is left waiting
            workspace = runtime.request("GET", "/api/v2/workspace")[1]
            self.assertGreaterEqual(len(workspace["seeds"]), 3); self.assertEqual(len(workspace["artifacts"]), 2)
        finally:
            runtime.close()
        refused = subprocess.run([sys.executable, str(ROOT / "scripts/seed_demo.py"), "https://seedreflections.com"], capture_output=True, text=True, timeout=30)
        self.assertNotEqual(refused.returncode, 0); self.assertIn("Refusing", refused.stderr + refused.stdout)
        hosted = UnifiedRuntime("hosted")
        try:
            blocked = subprocess.run([sys.executable, str(ROOT / "scripts/seed_demo.py"), f"http://127.0.0.1:{hosted.port}"], capture_output=True, text=True, timeout=30)
            self.assertNotEqual(blocked.returncode, 0)                                                         # a hosted server is refused even on loopback
        finally:
            hosted.close()


if __name__ == "__main__":
    unittest.main()
