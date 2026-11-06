import unittest
from model_gateway import select_model, normalize_task, public_catalog

class ModelGatewayTests(unittest.TestCase):
    def test_routes_code_to_coding_model(self):
        self.assertEqual(select_model("code")["model"],"qwen2.5-coder:7b")

    def test_routes_research_to_reasoning_model(self):
        self.assertEqual(select_model("research")["model"],"deepseek-r1:8b")

    def test_manual_selection_overrides_router(self):
        result=select_model("code",preferred_model_id="ollama:llama3.1:8b",selection_mode="manual")
        self.assertEqual(result["model"],"llama3.1:8b"); self.assertEqual(result["selection"],"manual")

    def test_unavailable_manual_model_falls_back(self):
        result=select_model("code",preferred_model_id="missing:model",selection_mode="manual")
        self.assertEqual(result["selection"],"auto")

    def test_alias_and_public_catalog(self):
        self.assertEqual(normalize_task("programming"),"code")
        self.assertTrue(all("api_key" not in item for item in public_catalog()))

if __name__ == "__main__": unittest.main()
