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
from support import FakeOllama, remove_temp
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


class SpendingTests(HostedTests):
    """The platform budget protects the platform's AI account; it does not stop people paying with their own key."""

    def at_cap(self):
        server.save_config({**server.load_config(), "ai_monthly_budget_usd": 0.0, "ai_budget_hard_stop": True})

    def test_own_key_still_runs_when_the_platform_budget_is_spent(self):
        self.at_cap()
        token = self.person("frank")
        self.settings(token, api_mode="self_hosted", llm_provider="anthropic", llm_model="own-model", llm_api_key="frank-secret")
        result = self.chat(token)
        self.assertEqual(result["mode"], "model"); self.assertEqual(self.calls[-1]["api_key"], "frank-secret")

    def test_managed_stops_at_the_platform_budget(self):
        self.at_cap()
        token = self.person("gina")
        self.settings(token, api_mode="managed")
        result = self.chat(token)
        self.assertEqual(result["mode"], "records_only"); self.assertEqual(self.calls, [])
        self.assertIn("budget", result["reason"].lower())

    def test_own_key_calls_are_not_counted_as_platform_spend(self):
        token = self.person("hana")
        self.settings(token, api_mode="self_hosted", llm_provider="openai", llm_model="own-model", llm_api_key="hana-secret")
        before = server.platform_spend()
        with patch.object(server, "invoke_model", lambda *a, **k: {"text": '{"answer": "ok"}', "prompt_tokens": 5_000_000, "completion_tokens": 5_000_000}):
            self.call("POST", "/api/v2/chat", {"prompt": "hello"}, token)
        self.assertEqual(server.platform_spend(), before)
        self.assertEqual(server.TELEMETRY_LOG[-1]["billed"], "own_key")
        self.settings(token, api_mode="managed")
        with patch.object(server, "invoke_model", lambda *a, **k: {"text": '{"answer": "ok"}', "prompt_tokens": 5_000_000, "completion_tokens": 5_000_000}):
            self.call("POST", "/api/v2/chat", {"prompt": "hello"}, token)
        self.assertGreater(server.platform_spend(), before); self.assertEqual(server.TELEMETRY_LOG[-1]["billed"], "platform")

    def test_the_emergency_off_switch_stops_every_outbound_call_including_own_keys(self):
        server.save_config({**server.load_config(), "ai_killswitch_enabled": True})
        token = self.person("ivan")
        self.settings(token, api_mode="self_hosted", llm_provider="anthropic", llm_model="own-model", llm_api_key="ivan-secret")
        self.assertEqual(self.chat(token)["mode"], "records_only")
        self.settings(token, api_mode="managed")
        self.assertEqual(self.chat(token)["mode"], "records_only")
        self.assertEqual(self.calls, [])

    def test_the_legacy_ai_routes_and_their_bare_aliases_are_closed(self):
        for path in ("/api/v1/reflect", "/api/v1/reflect_selected", "/api/v1/seeds/chat", "/reflect", "/reflect_selected", "/seeds/chat"):
            with patch.object(server.urllib.request, "urlopen", side_effect=AssertionError("no outbound call")):
                status, _ = self.call("POST", path, {"conversations": ["x"], "prompt": "hi", "transcript": "t"})
            self.assertEqual(status, 403, path)


class LocalTests(Base):
    MODE = "local"

    def test_desktop_own_settings_route_tasks_and_unsaved_settings_fall_back_to_the_server(self):
        self.assertEqual(self.chat()["mode"], "model")
        self.assertEqual(self.calls[-1]["model"], "platform-model")                # nothing chosen yet: server configuration
        with FakeOllama(["qwen2.5:7b", "my-own-model"]) as ollama:
            self.call("POST", "/api/v2/settings", {"api_mode": "self_hosted", "llm_provider": "ollama", "llm_model": "my-own-model", "llm_api_url": ollama.url,
                                                   "model_selection_mode": "manual", "preferred_model_id": "ollama:my-own-model"})
            self.chat()
            self.assertEqual({k: self.calls[-1][k] for k in ("provider", "api_url", "model")}, {"provider": "ollama", "api_url": ollama.url, "model": "my-own-model"})

    def test_an_unreachable_local_model_is_not_called_and_the_model_list_agrees(self):
        with FakeOllama([]) as ollama:
            dead = ollama.url                                                     # the address of a server that is now gone
        self.call("POST", "/api/v2/settings", {"api_mode": "self_hosted", "llm_provider": "ollama", "llm_model": "qwen2.5:7b", "llm_api_url": dead})
        models = self.call("GET", "/api/v2/models")[1]
        self.assertFalse(any(m["available"] for m in models["models"]))
        result = self.chat()
        self.assertEqual(result["mode"], "records_only"); self.assertEqual(self.calls, [])          # the list and the chat agree
        self.assertIn("No model is available", result["reason"])

    def test_a_listed_but_not_installed_local_model_is_not_called(self):
        with FakeOllama(["llama3.1:8b"]) as ollama:
            self.call("POST", "/api/v2/settings", {"api_mode": "self_hosted", "llm_provider": "ollama", "llm_model": "qwen2.5:7b", "llm_api_url": ollama.url,
                                                   "model_selection_mode": "manual", "preferred_model_id": "ollama:qwen2.5:7b"})
            self.chat()
            self.assertEqual(self.calls[-1]["model"], "llama3.1:8b")                # only an installed model is ever named

    def test_legacy_chat_route_follows_the_saved_mode(self):
        sent = []
        class Reply:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps({"choices": [{"message": {"content": "hi"}}], "usage": {}}).encode()
        def capture(request, timeout=None):
            sent.append(request.get_header("Authorization")); return Reply()
        with patch.object(server.urllib.request, "urlopen", capture):
            self.call("POST", "/api/v2/settings", {"api_mode": "managed"})
            self.call("POST", "/api/v1/seeds/chat", {"prompt": "hello"})
            self.call("POST", "/api/v2/settings", {"api_mode": "self_hosted", "llm_provider": "openai", "llm_model": "own-model", "llm_api_key": "owner-own-secret", "llm_api_key_temporary": True})
            self.call("POST", "/api/v1/seeds/chat", {"prompt": "hello"})
        self.assertEqual(sent, ["Bearer platform-secret", "Bearer owner-own-secret"])


class LegacyDesktopRouteTests(Base):
    """The older desktop AI routes use the shared model code: every saved provider works, and the off-switch stops all of them.
    Only the network is replaced, at the lowest level (urlopen inside model_invoke), so provider request shapes are real."""
    MODE = "local"
    REPLIES = {
        "api.openai.com": {"choices": [{"message": {"content": '[{"title": "From OpenAI", "description": "d", "status": "planted"}]'}}], "usage": {}},
        "generativelanguage.googleapis.com": {"candidates": [{"content": {"parts": [{"text": '[{"title": "From Gemini", "description": "d", "status": "planted"}]'}]}}]},
        "api.anthropic.com": {"content": [{"type": "text", "text": '[{"title": "From Anthropic", "description": "d", "status": "planted"}]'}], "usage": {}},
    }

    def setUp(self):
        super().setUp()
        server.save_config({**server.load_config(), "llm_provider": "ollama", "llm_api_url": "http://127.0.0.1:9", "llm_api_key": ""})   # the server's own setup is not one of these

    def own_provider(self, provider):
        self.call("POST", "/api/v2/settings", {"api_mode": "self_hosted", "llm_provider": provider, "llm_model": provider + "-model",
                                               "llm_api_key": provider + "-own-secret", "llm_api_key_temporary": True})

    def network(self):
        sent = []
        replies = self.REPLIES
        class Reply:
            def __init__(self, body): self.body = body
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps(self.body).encode()
        def urlopen(request, timeout=None):
            sent.append({"url": request.full_url, "headers": dict(request.header_items())})
            host = request.full_url.split("/")[2]
            return Reply(replies[host])
        return sent, patch("model_invoke.urllib.request.urlopen", urlopen)

    def test_reflect_calls_each_saved_provider_through_the_shared_code(self):
        for provider, host, title in (("openai", "api.openai.com", "From OpenAI"), ("gemini", "generativelanguage.googleapis.com", "From Gemini"),
                                      ("anthropic", "api.anthropic.com", "From Anthropic")):
            self.own_provider(provider)
            sent, network = self.network()
            with network:
                status, body = self.call("POST", "/api/v1/reflect", {"transcript": "User: we should build a launch checklist for the beta."})
            self.assertEqual(status, 200, provider)
            self.assertEqual([item["url"].split("/")[2] for item in sent], [host], provider)
            self.assertNotIn(provider + "-own-secret", sent[0]["url"], provider)          # keys go in headers, never the address
            self.assertIn(f"{provider}_{provider}-model", body["answer"], provider)          # the model's answer was used, not the fallback

    def test_the_off_switch_stops_reflection_for_every_provider(self):
        server.save_config({**server.load_config(), "ai_killswitch_enabled": True})
        for provider in ("openai", "gemini", "anthropic", "ollama"):
            self.own_provider(provider)
            sent, network = self.network()
            with network:                                                      # urlopen is shared, so this records any outbound call
                for path, body in (("/api/v1/reflect", {"transcript": "User: we should build a launch checklist."}),
                                   ("/api/v1/seeds/chat", {"prompt": "hello"})):
                    status, _ = self.call("POST", path, body)
                    self.assertEqual(status, 200, (provider, path))
            self.assertEqual(sent, [], provider)

    def test_legacy_chat_uses_a_saved_anthropic_key_instead_of_falling_back(self):
        self.own_provider("anthropic")
        sent, network = self.network()
        with network:
            status, body = self.call("POST", "/api/v1/seeds/chat", {"prompt": "hello"})
        self.assertEqual([item["url"].split("/")[2] for item in sent], ["api.anthropic.com"])
        self.assertEqual({k.lower(): v for k, v in sent[0]["headers"].items()}["x-api-key"], "anthropic-own-secret")
        self.assertNotIn("Offline Local Mode", body["answer"])

    def test_legacy_chat_says_why_when_the_provider_fails(self):
        self.own_provider("anthropic")
        with patch("model_invoke.urllib.request.urlopen", side_effect=OSError("down")):
            body = self.call("POST", "/api/v1/seeds/chat", {"prompt": "hello"})[1]
        self.assertIn("could not be reached", body["answer"]); self.assertNotIn("Offline Local Mode", body["answer"])


if __name__ == "__main__":
    unittest.main()
