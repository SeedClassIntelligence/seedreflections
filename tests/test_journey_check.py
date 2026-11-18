import base64
import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from test_unified_runtime import UnifiedRuntime

ROOT = Path(__file__).resolve().parents[1]


class JourneyCheckTests(unittest.TestCase):
    def test_the_release_check_passes_against_a_properly_configured_hosted_server_and_cleans_up(self):
        env = {"ADMIN_PASSWORD": "averylongadminpassword1", "SEED_REFLECTIONS_CREDENTIAL_MASTER_KEY": base64.urlsafe_b64encode(os.urandom(32)).decode(),
               "SEED_REFLECTIONS_PUBLIC_ORIGIN": "https://x.example.com", "SEED_REFLECTIONS_SMTP_HOST": "smtp.example.com", "SEED_REFLECTIONS_SMTP_FROM": "noreply@example.com"}
        runtime = UnifiedRuntime("hosted", env)
        try:
            done = subprocess.run([sys.executable, str(ROOT / "scripts/journey_check.py"), f"http://127.0.0.1:{runtime.port}"], capture_output=True, text=True, timeout=180)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("19 of 19 steps passed", done.stdout)
            self.assertEqual(runtime.request("POST", "/api/v2/auth/login", {"email": "x@example.test", "password": "x"})[0], 401)
        finally:
            runtime.close()

    def test_it_fails_loudly_when_the_site_is_not_ready(self):
        runtime = UnifiedRuntime("hosted")
        try:
            done = subprocess.run([sys.executable, str(ROOT / "scripts/journey_check.py"), f"http://127.0.0.1:{runtime.port}"], capture_output=True, text=True, timeout=180)
            self.assertEqual(done.returncode, 1); self.assertIn("every readiness check passes", done.stdout)
        finally:
            runtime.close()


if __name__ == "__main__":
    unittest.main()
