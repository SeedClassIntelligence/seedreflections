import unittest
from unittest.mock import patch, MagicMock
import json
import os
import sys
import tempfile
import socket
import threading
import urllib.request
import urllib.error
from datetime import datetime

# Add root folder to sys.path so we can import server.py
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import server

def get_free_port():
    s = socket.socket()
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    return port

class TestDatabaseMigrationAndRegression(unittest.TestCase):

    def setUp(self):
        # Create an isolated temporary directory for test database
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_db_path = os.path.join(self.temp_dir.name, "seeds_test.json")
        self.original_data_file = server.DATA_FILE
        server.DATA_FILE = self.temp_db_path

        self.temp_config_path = os.path.join(self.temp_dir.name, "config_test.json")
        self.original_config_file = server.CONFIG_FILE
        server.CONFIG_FILE = self.temp_config_path

        self.temp_transcripts_dir = os.path.join(self.temp_dir.name, "transcripts_test")
        self.original_transcripts_dir = server.TRANSCRIPTS_DIR
        server.TRANSCRIPTS_DIR = self.temp_transcripts_dir

        # Seed initial structured fixture
        self.initial_fixture = {
            "seeds": [
                {
                    "seed_id": "seed_initial_1",
                    "intent": "Initial seed intent description",
                    "title": "Initial Title",
                    "status": "planted",
                    "evidence_status": "Explicitly Stated",
                    "authority_status": "Detected",
                    "continuity_status": "Active",
                    "project_id": "default_project",
                    "versions": [],
                    "created_at": datetime.now().isoformat(),
                    "modified_at": datetime.now().isoformat()
                }
            ],
            "projects": [
                {
                    "project_id": "default_project",
                    "name": "Default Project",
                    "purpose": "Default group",
                    "description": "Default workspace project",
                    "owner": "developer",
                    "stage": "Active",
                    "created_at": datetime.now().isoformat()
                }
            ],
            "sources": [],
            "decisions": [],
            "conflicts": []
        }
        with open(self.temp_db_path, "w", encoding="utf-8") as f:
            json.dump(self.initial_fixture, f, indent=2)

        # Spin up actual HTTPServer on dynamically allocated free port
        self.port = get_free_port()
        self.server_url = f"http://127.0.0.1:{self.port}"
        server.PORT = self.port
        self.httpd = server.HTTPServer(("", self.port), server.SeedReflectionAPIHandler)
        self.server_thread = threading.Thread(target=self.httpd.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()

    def tearDown(self):
        # Safely shutdown the server and join thread
        self.httpd.shutdown()
        self.httpd.server_close()
        self.server_thread.join(timeout=5)
        server.DATA_FILE = self.original_data_file
        server.CONFIG_FILE = self.original_config_file
        server.TRANSCRIPTS_DIR = self.original_transcripts_dir
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def make_post_request(self, path, payload_dict=None, headers=None, raw_data=None):
        url = f"{self.server_url}{path}"
        if payload_dict is not None:
            data = json.dumps(payload_dict).encode("utf-8")
            content_type = "application/json"
        elif raw_data is not None:
            data = raw_data
            content_type = "application/json"
        else:
            data = b""
            content_type = "application/json"

        req_headers = {"Content-Type": content_type}
        if headers:
            req_headers.update(headers)

        req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.getcode(), json.loads(resp.read().decode("utf-8")), resp.info().get_content_type()
        except urllib.error.HTTPError as e:
            try:
                err_body = json.loads(e.read().decode("utf-8"))
            except Exception:
                err_body = None
            return e.code, err_body, e.headers.get_content_type()

    def make_get_request(self, path):
        url = f"{self.server_url}{path}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req) as resp:
                body = resp.read()
                try:
                    data = json.loads(body.decode("utf-8"))
                except Exception:
                    data = body.decode("utf-8")
                return resp.getcode(), data, resp.info().get_content_type()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8"), e.headers.get_content_type()

    def test_legacy_flat_list_migration(self):
        # Write flat list of legacy seeds to test DB path
        legacy_seeds = [
            {
                "seed_id": "seed_legacy_1",
                "intent": "Integrate fallback payment checks",
                "status": "growing",
                "created_at": "2026-07-06T18:19:53"
            }
        ]
        with open(self.temp_db_path, "w", encoding="utf-8") as f:
            json.dump(legacy_seeds, f, indent=2)

        # Trigger load database
        db = server.load_db()
        self.assertTrue(isinstance(db, dict))
        self.assertEqual(len(db["seeds"]), 1)
        self.assertEqual(db["seeds"][0]["seed_id"], "seed_legacy_1")
        self.assertEqual(db["seeds"][0]["project_id"], "default_project")
        self.assertEqual(db["seeds"][0]["status"], "growing")  # raw representation growing
        self.assertEqual(db["seeds"][0]["evidence_status"], "Explicitly Stated")

    def test_empty_title_and_intent_export(self):
        # 1. Inject legacy seed missing title/intent/description/etc.
        with server.DB_LOCK:
            db = server.load_db()
            db["seeds"].append({
                "seed_id": "seed_minimal_legacy",
                # missing title, intent, created_at, versions, decisions
            })
            server.save_db(db)

        # 2. Query seed export endpoint via GET
        code, data, content_type = self.make_get_request("/api/v1/seeds/seed_minimal_legacy/export")
        self.assertEqual(code, 200)
        self.assertIn("application/json", content_type)
        self.assertIn("markdown", data)
        self.assertIn("Untitled Seed", data["markdown"])
        self.assertIn("Not recorded", data["markdown"])
        self.assertNotIn("None", data["markdown"])

    def test_lifecycle_status_persistence(self):
        # Update status to 'wilted' (raw lifecycle value)
        payload = {
            "seed_id": "seed_initial_1",
            "field": "status",
            "value": "wilted"
        }
        code, data, _ = self.make_post_request("/api/v1/seeds/update", payload)
        self.assertEqual(code, 200)
        self.assertEqual(data.get("status"), "success")
        
        # Verify persistence inside test DB
        db = server.load_db()
        target = db["seeds"][0]
        self.assertEqual(target["status"], "wilted")

    def test_seed_version_archiving(self):
        # Modify the seed's intent
        payload = {
            "seed_id": "seed_initial_1",
            "field": "intent",
            "value": "Revised new intent wording"
        }
        code, data, _ = self.make_post_request("/api/v1/seeds/update", payload)
        self.assertEqual(code, 200)
        
        # Verify version archive contains original statement wording
        db = server.load_db()
        target = db["seeds"][0]
        self.assertEqual(len(target["versions"]), 1)
        self.assertEqual(target["versions"][0]["intent"], "Initial seed intent description")
        self.assertEqual(target["intent"], "Revised new intent wording")

    def test_project_creation(self):
        payload = {
            "project_id": "project_new",
            "name": "Integration Tests Workcell",
            "purpose": "Verify backend correctness",
            "description": "Premium isolation verification project",
            "owner": "auditor_claude",
            "stage": "Active"
        }
        code, data, _ = self.make_post_request("/api/v1/projects/create", payload)
        self.assertEqual(code, 200)
        
        # Verify in database
        db = server.load_db()
        project = next((p for p in db["projects"] if p["project_id"] == "project_new"), None)
        self.assertIsNotNone(project)
        self.assertEqual(project["name"], "Integration Tests Workcell")
        self.assertEqual(project["owner"], "auditor_claude")
        self.assertEqual(project["stage"], "Active")

        # Re-creating same Project ID must fail with 400 Bad Request
        code, err_data, _ = self.make_post_request("/api/v1/projects/create", payload)
        self.assertEqual(code, 400)
        self.assertIn("error", err_data)

    def test_decision_creation_and_associations(self):
        # Register a valid architectural decision
        payload = {
            "decision_statement": "Always lock read-modify-write transactions process-wide",
            "decision_type": "Architecture",
            "project_id": "default_project",
            "related_seeds": ["seed_initial_1"],
            "source_excerpt": "Narrow the concurrency window using DB_LOCK",
            "status": "Accepted"
        }
        code, data, _ = self.make_post_request("/api/v1/decisions/create", payload)
        self.assertEqual(code, 200)

        # Check DB association
        db = server.load_db()
        decision = db["decisions"][0]
        self.assertEqual(decision["decision_statement"], "Always lock read-modify-write transactions process-wide")
        self.assertEqual(decision["status"], "Accepted")
        self.assertIn("seed_initial_1", decision["related_seeds"])

        # Rejects if project_id does not exist
        payload["project_id"] = "non_existent_project"
        code, err_data, _ = self.make_post_request("/api/v1/decisions/create", payload)
        self.assertEqual(code, 400)
        self.assertIn("error", err_data)

    def test_conflict_creation_and_associations(self):
        # Create second seed first
        with server.DB_LOCK:
            db = server.load_db()
            db["seeds"].append({
                "seed_id": "seed_initial_2",
                "intent": "Alternative database model",
                "status": "planted",
                "project_id": "default_project"
            })
            server.save_db(db)

        # Log conflict
        payload = {
            "subject": "Contradictory database choice",
            "conflict_type": "Intent Contradiction",
            "project_id": "default_project",
            "seed_a": "seed_initial_1",
            "seed_b": "seed_initial_2",
            "statement_a": "Single thread process locks",
            "statement_b": "Multi-process distributed locks",
            "material_difference": "Process-wide locks do not scale to distributed systems",
            "severity": "High",
            "status": "Unresolved"
        }
        code, data, _ = self.make_post_request("/api/v1/conflicts/create", payload)
        self.assertEqual(code, 200)

        # Verify DB conflict record
        db = server.load_db()
        conflict = db["conflicts"][0]
        self.assertEqual(conflict["subject"], "Contradictory database choice")
        self.assertEqual(conflict["conflict_type"], "Intent Contradiction")
        self.assertEqual(conflict["seed_a"], "seed_initial_1")
        self.assertEqual(conflict["seed_b"], "seed_initial_2")
        self.assertEqual(conflict["status"], "Unresolved")

        # Verify links inside seeds
        seed_1 = next(s for s in db["seeds"] if s["seed_id"] == "seed_initial_1")
        self.assertIn(conflict["conflict_id"], seed_1["conflict_references"])

        # Rejects if seed_b does not exist
        payload["seed_b"] = "non_existent_seed"
        code, err_data, _ = self.make_post_request("/api/v1/conflicts/create", payload)
        self.assertEqual(code, 400)
        self.assertIn("error", err_data)

    def test_existing_seed_data_preservation(self):
        # Perform mutation and check that unrelated keys (like created_at date) remain unchanged
        original_created_at = self.initial_fixture["seeds"][0]["created_at"]
        payload = {
            "seed_id": "seed_initial_1",
            "field": "status",
            "value": "growing"
        }
        code, data, _ = self.make_post_request("/api/v1/seeds/update", payload)
        self.assertEqual(code, 200)
        
        db = server.load_db()
        target = db["seeds"][0]
        self.assertEqual(target["created_at"], original_created_at)

    def test_concurrent_mutation_serialization(self):
        # Spin up 10 concurrent requests updating different values of the seed in parallel threads
        results = []
        def send_update(value):
            payload = {
                "seed_id": "seed_initial_1",
                "field": "status",
                "value": value
            }
            code, data, _ = self.make_post_request("/api/v1/seeds/update", payload)
            results.append((code, data))

        statuses = ["planted", "growing", "bloomed", "wilted", "planted", "growing", "bloomed", "wilted", "planted", "growing"]
        threads = [threading.Thread(target=send_update, args=(s,)) for s in statuses]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Check all mutations succeeded and return 200
        for code, data in results:
            self.assertEqual(code, 200)
            self.assertEqual(data.get("status"), "success")

        # Reload database and confirm it has a valid status from the run
        db = server.load_db()
        self.assertIn(db["seeds"][0]["status"], statuses)

    def test_invalid_enum_rejections(self):
        # Invalid lifecycle status update
        payload_lifecycle = {
            "seed_id": "seed_initial_1",
            "field": "status",
            "value": "invalid_status_value"
        }
        code, data, _ = self.make_post_request("/api/v1/seeds/update", payload_lifecycle)
        self.assertEqual(code, 400)
        self.assertIn("error", data)

        # Invalid Project stage creation
        payload_proj = {
            "project_id": "project_invalid_enum",
            "name": "Invalid Enum Project",
            "stage": "InvalidStageValue"
        }
        code, data, _ = self.make_post_request("/api/v1/projects/create", payload_proj)
        self.assertEqual(code, 400)

        # Invalid Decision status creation
        payload_dec = {
            "decision_statement": "Invalid decision test statement",
            "project_id": "default_project",
            "status": "InvalidStatus"
        }
        code, data, _ = self.make_post_request("/api/v1/decisions/create", payload_dec)
        self.assertEqual(code, 400)

        # Invalid Conflict severity
        payload_conf = {
            "subject": "Invalid Conflict test subject",
            "project_id": "default_project",
            "seed_a": "seed_initial_1",
            "seed_b": "seed_initial_1",
            "severity": "CriticalExtreme"
        }
        code, data, _ = self.make_post_request("/api/v1/conflicts/create", payload_conf)
        self.assertEqual(code, 400)

        # DB must not have written the invalid records
        db = server.load_db()
        self.assertEqual(len(db["projects"]), 1)  # only default project
        self.assertEqual(len(db["decisions"]), 0)
        self.assertEqual(len(db["conflicts"]), 0)

    def test_error_handling_unknown_routes(self):
        code, data, _ = self.make_post_request("/api/v1/unknown/non_existent_route", {})
        self.assertEqual(code, 404)
        self.assertEqual(data, {"error": "Endpoint Not Found"})

    def test_error_handling_malformed_json(self):
        code, data, _ = self.make_post_request("/api/v1/projects/create", raw_data=b"{invalid_json_bytes")
        self.assertEqual(code, 400)
        self.assertEqual(data, {"error": "Invalid JSON payload"})

    def test_signature_verification_regression(self):
        payload = {
            "signatureId": "SIG_TEST_SIGNATURE_1234",
            "certificateUrl": "/seeds/verify/SIG_TEST_SIGNATURE_1234"
        }
        code, data, _ = self.make_post_request("/api/v1/seeds/seed_initial_1/signature", payload)
        self.assertEqual(code, 200)
        self.assertEqual(data["status"], "signed")

        # Verify saved trust state in DB
        db = server.load_db()
        seed = db["seeds"][0]
        self.assertTrue(seed["is_cryptographically_signed"])
        self.assertEqual(seed["trust_state"]["signature"], "SIG_TEST_SIGNATURE_1234")
        self.assertEqual(seed["trust_state"]["verification"], "verified")
        self.assertEqual(seed["trust_state"]["lineage"], "present")
        self.assertIsNotNone(seed["verification_result"]["signed_at"])

    def test_static_and_api_routes_operational(self):
        # Test serving index.html
        url = f"{self.server_url}/index.html"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.getcode(), 200)
            self.assertIn("text/html", resp.info().get_content_type())
            content = resp.read().decode("utf-8")
            self.assertIn("<html", content.lower())

    def test_concurrent_seed_planting(self):
        # Spin up 10 concurrent requests to plant seeds in parallel threads
        results = []
        def plant_seed(idx):
            payload = {
                "intent": f"Concurrent seed intent {idx}",
                "project_id": "default_project"
            }
            code, data, _ = self.make_post_request("/api/v1/seeds", payload)
            results.append((code, data))

        threads = [threading.Thread(target=plant_seed, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Check all creations returned 201
        for code, data in results:
            self.assertEqual(code, 201)
            self.assertEqual(data.get("status"), "planted")

        # Reload database and confirm all 10 concurrent seeds are in the db (plus the initial 1)
        db = server.load_db()
        self.assertEqual(len(db["seeds"]), 11)
        for i in range(10):
            intent_to_find = f"Concurrent seed intent {i}"
            self.assertTrue(any(s.get("intent") == intent_to_find for s in db["seeds"]))

    def test_mock_llm_provider_paths(self):
        original_urlopen = urllib.request.urlopen
        
        with patch("urllib.request.urlopen") as mock_urlopen:
            def side_effect(req, *args, **kwargs):
                if isinstance(req, str):
                    url = req
                else:
                    url = req.full_url
                if f"127.0.0.1:{self.port}" in url or "localhost" in url:
                    return original_urlopen(req, *args, **kwargs)
                
                # Intercept OpenAI
                if "api.openai.com" in url:
                    mock_response = MagicMock()
                    mock_response.getcode.return_value = 200
                    openai_json = {
                        "choices": [
                            {
                                "message": {
                                    "content": '[{"description": "Extracted seed via OpenAI mock", "title": "Mock OpenAI Title", "status": "planted"}]'
                                }
                            }
                        ]
                    }
                    mock_response.read.return_value = json.dumps(openai_json).encode("utf-8")
                    mock_response.info.return_value = MagicMock(get_content_type=lambda: "application/json")
                    mock_response.__enter__.return_value = mock_response
                    return mock_response
                
                # Intercept Gemini
                if "generativelanguage.googleapis.com" in url:
                    mock_response = MagicMock()
                    mock_response.getcode.return_value = 200
                    gemini_json = {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {
                                            "text": '[{"description": "Extracted seed via Gemini mock", "title": "Mock Gemini Title", "status": "planted"}]'
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                    mock_response.read.return_value = json.dumps(gemini_json).encode("utf-8")
                    mock_response.info.return_value = MagicMock(get_content_type=lambda: "application/json")
                    mock_response.__enter__.return_value = mock_response
                    return mock_response
                    
                raise ValueError(f"Unmocked external request in test: {url}")

            mock_urlopen.side_effect = side_effect

            # 1. Test OpenAI provider mapping
            config_openai = {
                "llm_provider": "openai",
                "llm_api_url": "https://api.openai.com/v1",
                "llm_model": "gpt-4o-mini",
                "llm_api_key": "sk-mock-key-12345"
            }
            self.make_post_request("/api/v1/settings", config_openai)

            payload = {"transcript": "Some transcript about OpenAI design decisions."}
            code, data, _ = self.make_post_request("/api/v1/reflect", payload)
            self.assertEqual(code, 200)
            self.assertEqual(data["assimilation_stats"]["new_seed"], 1)

            # Confirm seed is saved in the DB
            db = server.load_db()
            self.assertTrue(any(s.get("intent") == "Extracted seed via OpenAI mock" for s in db["seeds"]))

            # 2. Test Gemini provider mapping
            config_gemini = {
                "llm_provider": "gemini",
                "llm_api_url": "",
                "llm_model": "gemini-2.5-flash",
                "llm_api_key": "AIzaSyMockKey"
            }
            self.make_post_request("/api/v1/settings", config_gemini)

            code, data, _ = self.make_post_request("/api/v1/reflect", payload)
            self.assertEqual(code, 200)
            self.assertEqual(data["assimilation_stats"]["new_seed"], 1)

            db = server.load_db()
            self.assertTrue(any(s.get("intent") == "Extracted seed via Gemini mock" for s in db["seeds"]))

    def test_cascade_delete_cleanup(self):
        # 1. Plant reference seed B
        payload_b = {
            "intent": "Seed B to be referenced",
            "project_id": "default_project"
        }
        code, data, _ = self.make_post_request("/api/v1/seeds", payload_b)
        self.assertEqual(code, 201)
        seed_b_id = data["seed"]["seed_id"]

        # Create a decision referencing seed B and the initial seed
        payload_dec = {
            "decision_statement": "Decision referencing seed B",
            "project_id": "default_project",
            "status": "Proposed",
            "related_seeds": ["seed_initial_1", seed_b_id]
        }
        code, data, _ = self.make_post_request("/api/v1/decisions/create", payload_dec)
        self.assertEqual(code, 200)
        dec_id = data["decision"]["decision_id"]

        # Create a conflict referencing seed B and initial seed
        payload_conf = {
            "subject": "Conflict referencing seed B",
            "project_id": "default_project",
            "seed_a": "seed_initial_1",
            "seed_b": seed_b_id
        }
        code, data, _ = self.make_post_request("/api/v1/conflicts/create", payload_conf)
        self.assertEqual(code, 200)
        conf_id = data["conflict"]["conflict_id"]

        # Delete Seed B
        delete_payload = {"seed_id": seed_b_id}
        code, data, _ = self.make_post_request("/api/v1/seeds/delete", delete_payload)
        self.assertEqual(code, 200)

        # Verify database state
        db = server.load_db()
        # Seed B is deleted
        self.assertFalse(any(s.get("seed_id") == seed_b_id for s in db["seeds"]))
        # Decision still exists but has seed_b_id removed from related_seeds
        dec = next(d for d in db["decisions"] if d.get("decision_id") == dec_id)
        self.assertEqual(dec["related_seeds"], ["seed_initial_1"])
        # Conflict referencing seed_b_id is fully deleted
        self.assertFalse(any(c.get("conflict_id") == conf_id for c in db["conflicts"]))

    def test_signed_update_rejection_with_zero_mutation(self):
        # 1. Plant seed
        payload = {
            "intent": "Original Content To Sign",
            "project_id": "default_project"
        }
        code, data, _ = self.make_post_request("/api/v1/seeds", payload)
        self.assertEqual(code, 201)
        seed_id = data["seed"]["seed_id"]

        # 2. Sign seed (calculates digest)
        payload_sig = {
            "signatureId": "sig_digest_test_123",
            "certificateUrl": "/seeds/verify/sig_digest_test_123"
        }
        code, data, _ = self.make_post_request(f"/api/v1/seeds/{seed_id}/signature", payload_sig)
        self.assertEqual(code, 200)

        # 3. Attempt update of core field (should be blocked)
        payload_update = {
            "seed_id": seed_id,
            "intent": "Unsanctioned mutation attempt"
        }
        code, data, _ = self.make_post_request("/api/v1/seeds/update", payload_update)
        self.assertEqual(code, 403) # Forbidden
        
        # Verify content remained unchanged
        db = server.load_db()
        seed = next(s for s in db["seeds"] if s["seed_id"] == seed_id)
        self.assertEqual(seed["intent"], "Original Content To Sign")

    def test_explicit_evolution_creation(self):
        # 1. Plant seed and sign it
        code, data, _ = self.make_post_request("/api/v1/seeds", {"intent": "Base seed to evolve", "project_id": "default_project"})
        seed_id = data["seed"]["seed_id"]
        self.make_post_request(f"/api/v1/seeds/{seed_id}/signature", {"signatureId": "sig_evolve_base"})

        # 2. Call explicit evolution endpoint
        payload_evolve = {
            "parent_seed_id": seed_id,
            "intent": "Evolved successor seed intent",
            "evidence": "Team discussion on scaling requirements"
        }
        code, data, _ = self.make_post_request("/api/v1/seeds/evolve", payload_evolve)
        self.assertEqual(code, 201)
        
        successor_id = data["seed"]["seed_id"]
        rel = data["relationship"]
        
        # Verify successor seed state
        db = server.load_db()
        successor = next(s for s in db["seeds"] if s["seed_id"] == successor_id)
        self.assertEqual(successor["intent"], "Evolved successor seed intent")
        self.assertEqual(successor["parent_seed_id"], seed_id)
        self.assertEqual(successor["continuity_status"], "Proposed")
        self.assertFalse(successor["is_cryptographically_signed"])

        # Verify relationship proposal
        self.assertEqual(rel["source_seed_id"], seed_id)
        self.assertEqual(rel["target_seed_id"], successor_id)
        self.assertEqual(rel["relationship_type"], "Evolved Into")
        self.assertEqual(rel["approval_status"], "Proposed")

    def test_evolution_without_automatic_supersession(self):
        # Evolve does NOT automatically supersede the parent
        code, data, _ = self.make_post_request("/api/v1/seeds", {"intent": "Base seed no auto-super", "project_id": "default_project"})
        seed_id = data["seed"]["seed_id"]
        self.make_post_request(f"/api/v1/seeds/{seed_id}/signature", {"signatureId": "sig_no_auto_super"})

        self.make_post_request("/api/v1/seeds/evolve", {"parent_seed_id": seed_id, "intent": "Evolved draft"})
        
        db = server.load_db()
        parent = next(s for s in db["seeds"] if s["seed_id"] == seed_id)
        self.assertEqual(parent["continuity_status"], "Active") # remains active!

    def test_explicit_supersession_authorization(self):
        # 1. Evolve signed seed
        code, data, _ = self.make_post_request("/api/v1/seeds", {"intent": "Parent seed to supersede", "project_id": "default_project"})
        parent_id = data["seed"]["seed_id"]
        self.make_post_request(f"/api/v1/seeds/{parent_id}/signature", {"signatureId": "sig_super_parent"})

        code, data, _ = self.make_post_request("/api/v1/seeds/evolve", {"parent_seed_id": parent_id, "intent": "Successor seed"})
        successor_id = data["seed"]["seed_id"]
        rel_id = data["relationship"]["relationship_id"]

        # 2. Attempt supersession before relationship approval (should fail)
        payload_super = {
            "original_seed_id": parent_id,
            "successor_seed_id": successor_id
        }
        code, _, _ = self.make_post_request("/api/v1/seeds/supersede", payload_super)
        self.assertEqual(code, 400) # Bad Request: not approved

        # 3. Approve relationship
        code, _, _ = self.make_post_request("/api/v1/relationships/approve", {"relationship_id": rel_id})
        self.assertEqual(code, 200)

        # 4. Perform supersession
        code, data, _ = self.make_post_request("/api/v1/seeds/supersede", payload_super)
        self.assertEqual(code, 200)

        # Verify states
        db = server.load_db()
        parent = next(s for s in db["seeds"] if s["seed_id"] == parent_id)
        successor = next(s for s in db["seeds"] if s["seed_id"] == successor_id)
        self.assertEqual(parent["continuity_status"], "Superseded")
        self.assertEqual(successor["continuity_status"], "Active")

    def test_signature_digest_enforcement(self):
        # 1. Plant and sign seed
        code, data, _ = self.make_post_request("/api/v1/seeds", {"intent": "Digest safety check", "project_id": "default_project"})
        seed_id = data["seed"]["seed_id"]
        self.make_post_request(f"/api/v1/seeds/{seed_id}/signature", {"signatureId": "sig_digest_safety"})

        db = server.load_db()
        seed = next(s for s in db["seeds"] if s["seed_id"] == seed_id)
        self.assertTrue(server.is_seed_signed_and_valid(seed))

        # 2. Bypass update API to illegally modify file contents directly
        with server.DB_LOCK:
            db = server.load_db()
            for s in db["seeds"]:
                if s["seed_id"] == seed_id:
                    s["intent"] = "Illegally altered content"
            server.save_db(db)

        # 3. Verify validator detects invalid signature digest
        db = server.load_db()
        seed = next(s for s in db["seeds"] if s["seed_id"] == seed_id)
        self.assertFalse(server.is_seed_signed_and_valid(seed))

    def test_relationship_approval_states(self):
        code, data, _ = self.make_post_request("/api/v1/seeds", {"intent": "Seed A", "project_id": "default_project"})
        seed_a_id = data["seed"]["seed_id"]
        code, data, _ = self.make_post_request("/api/v1/seeds", {"intent": "Seed B", "project_id": "default_project"})
        seed_b_id = data["seed"]["seed_id"]

        # AI proposed relationship
        payload_rel = {
            "source_seed_id": seed_a_id,
            "target_seed_id": seed_b_id,
            "relationship_type": "Refined By",
            "created_by": "ai",
            "evidence": "AI heuristic deduction"
        }
        code, data, _ = self.make_post_request("/api/v1/relationships/create", payload_rel)
        self.assertEqual(code, 200)
        rel_id = data["relationship"]["relationship_id"]

        db = server.load_db()
        rel = next(r for r in db["relationships"] if r["relationship_id"] == rel_id)
        self.assertEqual(rel["proposed_by"], "ai")
        self.assertEqual(rel["approval_status"], "Proposed")
        self.assertIsNone(rel["approved_by"])

        # Approve relationship
        code, data, _ = self.make_post_request("/api/v1/relationships/approve", {"relationship_id": rel_id, "approved_by": "lead_dev", "basis": "Validated by team"})
        self.assertEqual(code, 200)

        db = server.load_db()
        rel = next(r for r in db["relationships"] if r["relationship_id"] == rel_id)
        self.assertEqual(rel["approval_status"], "Approved")
        self.assertEqual(rel["approved_by"], "lead_dev")
        self.assertEqual(rel["approval_basis"], "Validated by team")

    def test_relationship_inverse_and_symmetric_behavior(self):
        # Verify relationship registry configuration
        self.assertIn("Evolved Into", server.RELATIONSHIP_REGISTRY)
        self.assertFalse(server.RELATIONSHIP_REGISTRY["Evolved Into"]["symmetric"])
        self.assertEqual(server.RELATIONSHIP_REGISTRY["Evolved Into"]["inverse"], "Evolved From")
        
        self.assertTrue(server.RELATIONSHIP_REGISTRY["Merged With"]["symmetric"])
        self.assertEqual(server.RELATIONSHIP_REGISTRY["Merged With"]["inverse"], "Merged With")

    def test_duplicate_edge_rejection(self):
        code, data, _ = self.make_post_request("/api/v1/seeds", {"intent": "Seed A", "project_id": "default_project"})
        seed_a_id = data["seed"]["seed_id"]
        code, data, _ = self.make_post_request("/api/v1/seeds", {"intent": "Seed B", "project_id": "default_project"})
        seed_b_id = data["seed"]["seed_id"]

        # Create relationship
        payload = {
            "source_seed_id": seed_a_id,
            "target_seed_id": seed_b_id,
            "relationship_type": "Conflicts With",
            "created_by": "user"
        }
        code, _, _ = self.make_post_request("/api/v1/relationships/create", payload)
        self.assertEqual(code, 200)

        # Attempt duplicate creation (Conflicts With is symmetric, so reverse must also be rejected)
        code, _, _ = self.make_post_request("/api/v1/relationships/create", payload)
        self.assertEqual(code, 400) # Duplicate rejected

        payload_rev = {
            "source_seed_id": seed_b_id,
            "target_seed_id": seed_a_id,
            "relationship_type": "Conflicts With",
            "created_by": "user"
        }
        code, _, _ = self.make_post_request("/api/v1/relationships/create", payload_rev)
        self.assertEqual(code, 400) # Symmetric duplicate rejected

    def test_approved_relationship_retraction(self):
        code, data, _ = self.make_post_request("/api/v1/seeds", {"intent": "Seed A", "project_id": "default_project"})
        seed_a_id = data["seed"]["seed_id"]
        code, data, _ = self.make_post_request("/api/v1/seeds", {"intent": "Seed B", "project_id": "default_project"})
        seed_b_id = data["seed"]["seed_id"]

        # Create approved relationship (by user)
        payload = {
            "source_seed_id": seed_a_id,
            "target_seed_id": seed_b_id,
            "relationship_type": "Refined By",
            "created_by": "user"
        }
        code, data, _ = self.make_post_request("/api/v1/relationships/create", payload)
        self.assertEqual(code, 200)
        rel_id = data["relationship"]["relationship_id"]

        # Assert cross-references mapped inside seed structures
        db = server.load_db()
        seed_a = next(s for s in db["seeds"] if s["seed_id"] == seed_a_id)
        self.assertIn(seed_b_id, seed_a["child_seeds"])

        # Retract relationship
        code, data, _ = self.make_post_request("/api/v1/relationships/delete", {"relationship_id": rel_id, "retracted_by": "team_lead", "basis": "Obsolete direction"})
        self.assertEqual(code, 200)

        # Verify it remains in database as Retracted tombstone
        db = server.load_db()
        rel = next(r for r in db["relationships"] if r["relationship_id"] == rel_id)
        self.assertEqual(rel["approval_status"], "Retracted")
        self.assertEqual(rel["retracted_by"], "team_lead")
        self.assertEqual(rel["retraction_basis"], "Obsolete direction")

        # Verify parent/child cross-references are removed
        seed_a = next(s for s in db["seeds"] if s["seed_id"] == seed_a_id)
        self.assertNotIn(seed_b_id, seed_a["child_seeds"])

    def test_lost_score_component_inversion(self):
        payload_proj = {
            "project_id": "lost_inversion_proj",
            "name": "Lost Inversion Project",
            "purpose": "Verify signals inverse calculations",
            "description": "Inversion checks."
        }
        self.make_post_request("/api/v1/projects/create", payload_proj)

        # Plant seed (starts with no descendants, no decisions -> scores high on lost checklist)
        code, data, _ = self.make_post_request("/api/v1/seeds", {"intent": "Bottleneck diagnostic", "project_id": "lost_inversion_proj"})
        seed_id = data["seed"]["seed_id"]

        code, data, _ = self.make_get_request("/api/v1/analysis/lost-seeds?project_id=lost_inversion_proj")
        lost_info = next(item for item in data["lost_seeds"] if item["seed_id"] == seed_id)
        initial_score = lost_info["score"]

        # Link decision (provides protective signal -> lost score should drop)
        payload_dec = {
            "decision_statement": "Address performance bottleneck",
            "project_id": "lost_inversion_proj",
            "related_seeds": [seed_id]
        }
        self.make_post_request("/api/v1/decisions/create", payload_dec)

        code, data, _ = self.make_get_request("/api/v1/analysis/lost-seeds?project_id=lost_inversion_proj")
        lost_info_after = next(item for item in data["lost_seeds"] if item["seed_id"] == seed_id)
        after_score = lost_info_after["score"]

        # Confirm score dropped due to protective signal presence (decision linked)
        self.assertLess(after_score, initial_score)
        self.assertEqual(lost_info_after["metrics"]["no_decisions"], 0.0) # inverted correctly!

    def test_decision_coverage_naming_and_calculation(self):
        payload_proj = {
            "project_id": "coverage_proj",
            "name": "Coverage Project",
            "purpose": "Evaluate Decision Coverage index mapping",
            "description": "Coverage index validation."
        }
        self.make_post_request("/api/v1/projects/create", payload_proj)

        code, data, _ = self.make_post_request("/api/v1/seeds", {"intent": "Uncovered feature idea", "project_id": "coverage_proj"})
        seed_id = data["seed"]["seed_id"]

        # 0% coverage initially (1 seed, 0 decisions)
        code, data, _ = self.make_get_request("/api/v1/analysis/intent-drift?project_id=coverage_proj")
        self.assertEqual(code, 200)
        self.assertEqual(data["decision_coverage_index"], 0.0)
        self.assertEqual(data["analysis_method"], "deterministic lexical analysis")
        self.assertIn("confidence_limitations", data)
        self.assertEqual(data["uncovered_seed_ids"], [seed_id])

        # Link decision (Accepted)
        payload_dec = {
            "decision_statement": "Covered decision link",
            "project_id": "coverage_proj",
            "status": "Accepted",
            "related_seeds": [seed_id]
        }
        self.make_post_request("/api/v1/decisions/create", payload_dec)

        # 100% coverage
        code, data, _ = self.make_get_request("/api/v1/analysis/intent-drift?project_id=coverage_proj")
        self.assertEqual(data["decision_coverage_index"], 100.0)
        self.assertEqual(data["uncovered_seed_ids"], [])

    def test_provenance_preservation_after_seed_deletion(self):
        # 1. Sign seed
        code, data, _ = self.make_post_request("/api/v1/seeds", {"intent": "Seed with signed provenance history", "project_id": "default_project"})
        seed_id = data["seed"]["seed_id"]
        self.make_post_request(f"/api/v1/seeds/{seed_id}/signature", {"signatureId": "sig_provenance_preserve"})

        # 2. Request deletion of signed seed
        code, data, _ = self.make_post_request("/api/v1/seeds/delete", {"seed_id": seed_id})
        self.assertEqual(code, 200)
        self.assertTrue(data.get("tombstoned")) # Indicates it was tombstoned to preserve provenance

        # Verify seed still exists in store with Tombstoned status
        db = server.load_db()
        seed = next((s for s in db["seeds"] if s["seed_id"] == seed_id), None)
        self.assertIsNotNone(seed)
        self.assertEqual(seed["continuity_status"], "Tombstoned")

        # 3. Create normal draft seed
        code, data, _ = self.make_post_request("/api/v1/seeds", {"intent": "Draft seed no history", "project_id": "default_project"})
        draft_id = data["seed"]["seed_id"]

        # Delete draft
        code, data, _ = self.make_post_request("/api/v1/seeds/delete", {"seed_id": draft_id})
        self.assertEqual(code, 200)
        self.assertFalse(data.get("tombstoned"))
        # Verify draft is completely hard-deleted
        db = server.load_db()
        self.assertFalse(any(s["seed_id"] == draft_id for s in db["seeds"]))

    def test_context_package_export(self):
        # 1. Add a seed and decision
        code, data, _ = self.make_post_request("/api/v1/seeds", {"intent": "Export test seed", "project_id": "default_project"})
        seed_id = data["seed"]["seed_id"]
        
        payload_dec = {
            "decision_statement": "Export test decision",
            "project_id": "default_project",
            "related_seeds": [seed_id]
        }
        self.make_post_request("/api/v1/decisions/create", payload_dec)

        # 2. Call Export Package endpoint
        code, data, _ = self.make_get_request("/api/v1/projects/export-package?project_id=default_project")
        self.assertEqual(code, 200)
        self.assertIn("markdown_package", data)
        self.assertIn("json_package", data)
        self.assertEqual(data["json_package"]["package_version"], "2.0.0")
        
        # Check markdown contents
        self.assertIn("Export test seed", data["markdown_package"])
        self.assertIn("Export test decision", data["markdown_package"])

    def test_context_package_import(self):
        # 1. Create a dummy package payload
        dummy_pkg = {
            "json_package": {
                "package_version": "2.0.0",
                "project": {
                    "project_id": "imported_project_xyz",
                    "name": "Imported Test Space",
                    "purpose": "Verify package ingestion",
                    "description": "Integration test check."
                },
                "seeds": [
                    {
                        "seed_id": "imported_seed_1",
                        "project_id": "imported_project_xyz",
                        "title": "Imported Seed One",
                        "intent": "Verify parsing of imported seeds",
                        "status": "planted",
                        "continuity_status": "Active"
                    }
                ],
                "decisions": [
                    {
                        "decision_id": "imported_dec_1",
                        "project_id": "imported_project_xyz",
                        "decision_statement": "Ingestion approved",
                        "status": "Accepted",
                        "related_seeds": ["imported_seed_1"]
                    }
                ],
                "conflicts": [],
                "relationships": [
                    {
                        "relationship_id": "imported_rel_1",
                        "source_seed_id": "seed_initial_1",
                        "target_seed_id": "imported_seed_1",
                        "relationship_type": "Refined By",
                        "approval_status": "Approved",
                        "proposed_by": "user"
                    }
                ]
            }
        }

        # 2. Trigger Ingestion Import
        code, data, _ = self.make_post_request("/api/v1/projects/import-package", dummy_pkg)
        self.assertEqual(code, 200)
        self.assertEqual(data["imported"]["seeds"], 1)
        self.assertEqual(data["imported"]["decisions"], 1)
        self.assertEqual(data["imported"]["relationships"], 1)

        # 3. Verify structures are saved and cross-referenced
        db = server.load_db()
        seed = next(s for s in db["seeds"] if s["seed_id"] == "imported_seed_1")
        self.assertEqual(seed["title"], "Imported Seed One")
        self.assertEqual(seed["parent_seed_id"], "seed_initial_1")

    def test_scia_context_query(self):
        # Trigger SCIA ingestion adapter
        code, data, _ = self.make_get_request("/api/v1/scia/context?project_id=default_project")
        self.assertEqual(code, 200)
        self.assertEqual(data["project_id"], "default_project")
        self.assertIn("charter", data)
        self.assertIn("seeds", data)
        self.assertIn("decisions", data)
        self.assertIn("relationships", data)

if __name__ == "__main__":
    unittest.main()
