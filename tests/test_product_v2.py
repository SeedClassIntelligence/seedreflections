import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Runtime:
    def __init__(self, mode="local"):
        self.temp = tempfile.TemporaryDirectory()
        self.port = free_port()
        env = os.environ.copy()
        env.update({"SEED_REFLECTIONS_DATA_DIR": self.temp.name, "SEED_REFLECTIONS_PORT": str(self.port),
                    "SEED_REFLECTIONS_HOST": "127.0.0.1", "SEED_REFLECTIONS_MODE": mode,
                    "SEED_REFLECTIONS_PUBLIC_ORIGIN": "http://127.0.0.1:3000",
                    "SEED_REFLECTIONS_QUIET": "1", "SEED_REFLECTIONS_MIGRATE_LEGACY": "0",
                    "PYTHONDONTWRITEBYTECODE": "1"})
        self.process = subprocess.Popen([sys.executable, str(ROOT / "server.py")], cwd=ROOT,
                                        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        for _ in range(80):
            try:
                self.request("GET", "/api/v2/health")
                break
            except Exception:
                time.sleep(.05)
        else:
            raise RuntimeError("server failed to start")

    def request(self, method, path, data=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(data).encode() if data is not None else None, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def close(self):
        self.process.terminate()
        self.process.wait(timeout=5)
        self.temp.cleanup()


class ProductLocalFlowTests(unittest.TestCase):
    def setUp(self): self.runtime = Runtime("local")
    def tearDown(self): self.runtime.close()

    def test_archive_to_review_to_recovery_to_context(self):
        archive = [{"id": "conv-1", "title": "Product plan", "messages": [
            {"id": "m1", "role": "user", "content": "We should build a local conversation library so people can find their work."},
            {"id": "m2", "role": "assistant", "content": "That can be indexed."},
            {"id": "m3", "role": "user", "content": "Decision: we will use SQLite for the archive."}
        ]}]
        status, imported = self.runtime.request("POST", "/api/v2/imports", {"filename": "history.json", "platform": "generic", "data": archive})
        self.assertEqual(status, 201); self.assertEqual(imported["conversations"], 1); self.assertEqual(imported["messages"], 3)
        status, library = self.runtime.request("GET", "/api/v2/conversations?q=SQLite")
        self.assertEqual(status, 200); self.assertEqual(len(library["conversations"]), 1)
        conversation_id = library["conversations"][0]["id"]
        status, analyzed = self.runtime.request("POST", f"/api/v2/conversations/{conversation_id}/analyze", {})
        self.assertEqual(status, 200); self.assertGreaterEqual(analyzed["candidates_created"], 2)
        status, candidates = self.runtime.request("GET", "/api/v2/candidates?status=pending")
        self.assertEqual(status, 200); self.assertTrue(all(c["excerpt"] for c in candidates["candidates"]))
        candidate_id = next(c["id"] for c in candidates["candidates"] if c["kind"] != "decision")
        status, accepted = self.runtime.request("POST", f"/api/v2/candidates/{candidate_id}/review", {"action": "accept"})
        self.assertEqual(status, 200); self.assertIn("seed_id", accepted)
        status, recovery = self.runtime.request("GET", "/api/v2/recovery")
        self.assertEqual(len(recovery["recovery_candidates"]), 1)
        seed_id = recovery["recovery_candidates"][0]["id"]
        status, resumed = self.runtime.request("POST", f"/api/v2/seeds/{seed_id}/resume", {})
        self.assertEqual(resumed["status"], "recovered")
        status, overview = self.runtime.request("GET", "/api/v2/overview")
        self.assertEqual(overview["recovered"], 1)
        status, lost = self.runtime.request("GET", "/api/v2/analysis/lost-seeds?project_id=default_project")
        self.assertEqual(status, 200); self.assertEqual(lost["project_id"], "default_project")
        self.assertTrue(any(item["seed_id"] == seed_id for item in lost["lost_seeds"]))
        status, drift = self.runtime.request("GET", "/api/v2/analysis/intent-drift?project_id=default_project")
        self.assertEqual(status, 200); self.assertIn("mission_drift_index", drift); self.assertIn("decision_coverage_index", drift)

    def test_analyzer_abstains_without_evidence(self):
        archive = [{"title": "Greeting", "messages": [{"role": "user", "content": "Hello, how are you?"}]}]
        _, imported = self.runtime.request("POST", "/api/v2/imports", {"filename": "small.json", "platform": "generic", "data": archive})
        _, library = self.runtime.request("GET", "/api/v2/conversations")
        _, result = self.runtime.request("POST", f"/api/v2/conversations/{library['conversations'][0]['id']}/analyze", {})
        self.assertTrue(result["abstained"]); self.assertEqual(result["candidates_created"], 0)

    def test_no_secret_fields_in_capabilities(self):
        _, data = self.runtime.request("GET", "/api/v2/capabilities")
        self.assertFalse(any("key" in key or "secret" in key for key in data))


class ProductHostedAuthTests(unittest.TestCase):
    def setUp(self): self.runtime = Runtime("hosted")
    def tearDown(self): self.runtime.close()

    def test_hosted_data_requires_auth_and_passwords_are_verified(self):
        status, _ = self.runtime.request("GET", "/api/v2/overview")
        self.assertEqual(status, 401)
        status, signup = self.runtime.request("POST", "/api/v2/auth/signup", {"name": "Audit User", "email": "audit@example.com", "password": "strong-password-123"})
        self.assertEqual(status, 201)
        status, _ = self.runtime.request("POST", "/api/v2/auth/login", {"email": "audit@example.com", "password": "wrong-password-123"})
        self.assertEqual(status, 401)
        status, login = self.runtime.request("POST", "/api/v2/auth/login", {"email": "audit@example.com", "password": "strong-password-123"})
        self.assertEqual(status, 200)
        status, overview = self.runtime.request("GET", "/api/v2/overview", token=login["access_token"])
        self.assertEqual(status, 200); self.assertEqual(overview["conversations"], 0)


if __name__ == "__main__": unittest.main()
