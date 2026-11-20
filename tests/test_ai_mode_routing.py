"""The saved AI mode decides which connection a task really uses.

Managed     -> the platform's provider, model and key (server configuration).
Own key     -> the workspace's own provider, model and key; never the platform key.
Hosted own-key accounts cannot point the server at an address of their choosing.
Every case goes through the real /api/v2/chat route; only the network call to the provider is replaced."""
import base64
import http.client
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(__file__))
from support import remove_temp
import agent_tokens
import archive_store
import auth_store
import secret_store
import server
import tenant_archive_store
import work_sessions
import workspace_store

PLATFORM = {"llm_provider": "openai", "llm_model": "platform-model", "llm_api_url": "https://platform.example/v1",
            "llm_api_key": "platform-secret", "ai_killswitch_enabled": False}


class Base(unittest.TestCase):
    MODE = "local"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); self.port = sock.getsockname()[1]
        key = base64.urlsafe_b64encode(os.urandom(32)).decode()
        self.patches = [patch.object(server, "DEPLOYMENT_MODE", self.MODE),
                        patch.object(server, "DATA_FILE", str(root / "seeds.json")), patch.object(server, "CONFIG_FILE", str(root / "config.json")),
                        patch.object(archive_store, "DB_PATH", root / "archive.db"), patch.object(secret_store, "DB_PATH", root / "archive.db"),
                        patch.object(auth_store, "DB_PATH", root / "archive.db"), patch.object(tenant_archive_store, "DB_PATH", root / "archive.db"),
                        patch.object(workspace_store, "DB_PATH", root / "workspaces.db"),
                        patch.object(agent_tokens, "DB_PATH", root / "agent_tokens.db"), patch.object(work_sessions, "DB_PATH", root / "work_sessions.db"),
                        patch.dict(os.environ, {"SEED_REFLECTIONS_CREDENTIAL_MASTER_KEY": key})]
        if self.MODE != "local":
            self.patches.append(patch.object(server, "PUBLIC_ORIGIN", f"http://127.0.0.1:{self.port}"))
        for item in self.patches: item.start()
        archive_store.initialize(); auth_store.initialize(); secret_store._SESSION_KEYS.clear()
        server.save_config({**server.load_config(), **PLATFORM})
        self.httpd = server.HTTPServer(("127.0.0.1", self.port), server.SeedReflectionAPIHandler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.calls = []

    def tearDown(self):
        self.httpd.shutdown(); self.httpd.server_close()
        for item in reversed(self.patches): item.stop()
        secret_store._SESSION_KEYS.clear()
        remove_temp(self.temp)

    def call(self, method, path, body=None, token=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Content-Type": "application/json"}
        if token: headers["Authorization"] = "Bearer " + token
        connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        response = connection.getresponse(); data = response.read(); connection.close()
        return response.status, (json.loads(data) if data else None)

    def fake_model(self, provider, api_url, api_key, model, messages, **kwargs):
        self.calls.append({"provider": provider, "api_url": api_url, "api_key": api_key, "model": model})
        return {"text": '{"answer": "ok"}', "prompt_tokens": 1, "completion_tokens": 1}

    def chat(self, token=None):
        with patch.object(server, "invoke_model", self.fake_model):
            return self.call("POST", "/api/v2/chat", {"prompt": "hello"}, token)[1]


class HostedTests(Base):
    MODE = "hosted"

    def person(self, name):
        made = self.call("POST", "/api/v2/auth/signup", {"name": name, "email": f"{name}@example.com", "password": "strong-password-123"})[1]
        return made["access_token"]

    def settings(self, token, **values):
        status, _ = self.call("POST", "/api/v2/settings", values, token); self.assertEqual(status, 200)

    def test_managed_uses_the_platform_connection(self):
        token = self.person("alice")
        self.settings(token, api_mode="managed")
        result = self.chat(token)
        self.assertEqual(result["mode"], "model")
        self.assertEqual(self.calls[-1], {"provider": "openai", "api_url": "https://platform.example/v1", "api_key": "platform-secret", "model": "platform-model"})

    def test_own_key_uses_the_workspaces_provider_and_key_and_never_the_platform_key(self):
        token = self.person("bob")
        self.settings(token, api_mode="self_hosted", llm_provider="anthropic", llm_model="own-model", llm_api_url="http://10.0.0.5:8080", llm_api_key="bob-secret")
        result = self.chat(token)
        self.assertEqual(result["mode"], "model")
        call = self.calls[-1]
        self.assertEqual((call["provider"], call["model"], call["api_key"]), ("anthropic", "own-model", "bob-secret"))
        self.assertEqual(call["api_url"], "")                                     # the typed address is ignored on the hosted service
        self.assertNotIn("platform-secret", json.dumps(self.calls))

    def test_own_key_mode_without_a_key_does_not_borrow_the_platform_key(self):
        token = self.person("carol")
        self.settings(token, api_mode="self_hosted", llm_provider="openai", llm_model="own-model")
        result = self.chat(token)
        self.assertEqual(result["mode"], "records_only"); self.assertEqual(self.calls, [])
        models = self.call("GET", "/api/v2/models", token=token)[1]
        self.assertEqual(models["connection"]["mode"], "self_hosted"); self.assertFalse(models["connection"]["key_configured"])
        self.assertFalse(any(m["available"] for m in models["models"]))

    def test_hosted_own_key_cannot_use_a_local_or_custom_address(self):
        token = self.person("dave")
        self.settings(token, api_mode="self_hosted", llm_provider="ollama", llm_model="m", llm_api_url="http://169.254.169.254")
        result = self.chat(token)
        self.assertEqual(result["mode"], "records_only"); self.assertEqual(self.calls, [])
        self.assertIn("only be used in the desktop app", result["reason"])
        models = self.call("GET", "/api/v2/models", token=token)[1]
        self.assertIn("desktop app", models["connection"]["refusal"]); self.assertFalse(any(m["available"] for m in models["models"]))

    def test_switching_mode_switches_the_connection(self):
        token = self.person("erin")
        self.settings(token, api_mode="self_hosted", llm_provider="gemini", llm_model="g-model", llm_api_key="erin-secret")
        self.chat(token); self.assertEqual(self.calls[-1]["api_key"], "erin-secret")
        self.settings(token, api_mode="managed")
        self.chat(token); self.assertEqual(self.calls[-1]["api_key"], "platform-secret")
        models = self.call("GET", "/api/v2/models", token=token)[1]
        self.assertEqual(models["connection"], {"mode": "managed", "provider": "openai", "refusal": None, "key_configured": True})
        self.assertNotIn("secret", json.dumps(models))                            # no key is ever returned


class LocalTests(Base):
    MODE = "local"

    def test_desktop_own_settings_route_tasks_and_unsaved_settings_fall_back_to_the_server(self):
        self.assertEqual(self.chat()["mode"], "model")
        self.assertEqual(self.calls[-1]["model"], "platform-model")                # nothing chosen yet: server configuration
        self.call("POST", "/api/v2/settings", {"api_mode": "self_hosted", "llm_provider": "ollama", "llm_model": "qwen2.5:7b", "llm_api_url": "http://127.0.0.1:1"})
        self.chat()
        self.assertEqual({k: self.calls[-1][k] for k in ("provider", "api_url")}, {"provider": "ollama", "api_url": "http://127.0.0.1:1"})
        self.assertEqual(self.calls[-1]["model"], "qwen2.5:7b")


if __name__ == "__main__":
    unittest.main()
