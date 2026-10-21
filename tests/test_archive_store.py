import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import archive_store
import server


class ArchiveStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(archive_store, "DB_PATH", Path(self.temp.name) / "archive.db")
        self.db_patch.start()
        archive_store.initialize()

    def tearDown(self):
        self.db_patch.stop()
        self.temp.cleanup()

    def test_chatgpt_archive_persists_messages_and_source(self):
        payload = [{
            "id": "source-1",
            "title": "A serious product idea",
            "create_time": 1700000000,
            "mapping": {
                "a": {"parent": None, "message": {"id": "m1", "create_time": 1700000001,
                    "author": {"role": "user"}, "content": {"parts": ["I want to build a durable idea archive."]}}},
                "b": {"parent": "a", "message": {"id": "m2", "create_time": 1700000002,
                    "author": {"role": "assistant"}, "content": {"parts": ["Let's map the archive."]}}},
            },
        }]
        result = archive_store.import_json(json.dumps(payload).encode(), "conversations.json")
        self.assertEqual(result["platform"], "chatgpt")
        self.assertEqual(result["message_count"], 2)
        stored = archive_store.list_conversations()
        self.assertEqual(len(stored), 1)
        detail = archive_store.get_conversation(stored[0]["id"])
        self.assertEqual([m["role"] for m in detail["messages"]], ["user", "assistant"])
        self.assertIn("durable idea archive", detail["messages"][0]["content"])
        raw = archive_store.raw_conversations([stored[0]["id"]])
        self.assertEqual(raw[0]["id"], "source-1")

    def test_search_finds_message_content(self):
        payload = [{"id": "one", "title": "Notes", "messages": [
            {"role": "user", "content": "Develop the copper lighthouse concept"}
        ]}]
        archive_store.import_json(json.dumps(payload), "generic.json")
        self.assertEqual(len(archive_store.list_conversations("lighthouse")), 1)
        self.assertEqual(len(archive_store.list_conversations("unrelated")), 0)

    def test_invalid_archive_is_rejected_without_records(self):
        with self.assertRaises(ValueError):
            archive_store.import_json(json.dumps("not an archive"), "bad.json")
        self.assertEqual(archive_store.list_conversations(), [])

    def test_pasted_conversation_preserves_roles(self):
        result = archive_store.import_text(
            "User: I want to recover my unfinished project.\nAssistant: We can map the decisions first.\nUser: Then make a plan.",
            "Recovery planning",
        )
        detail = archive_store.get_conversation(result["conversations"][0]["id"])
        self.assertEqual(detail["conversation"]["title"], "Recovery planning")
        self.assertEqual([message["role"] for message in detail["messages"]], ["user", "assistant", "user"])

    def test_newer_full_export_adds_updates_and_keeps_unchanged_without_duplicates(self):
        first_export = [
            {"id": "same", "title": "Stable", "messages": [{"id":"s1", "role":"user", "content":"Keep me unchanged"}]},
            {"id": "extended", "title": "Growing", "messages": [{"id":"g1", "role":"user", "content":"Initial thought"}]},
        ]
        first = archive_store.import_json(json.dumps(first_export), "export-one.json")
        original_ids = {item["source_id"]: item["id"] for item in first["conversations"]}
        second_export = [
            first_export[0],
            {"id": "extended", "title": "Growing", "messages": [
                {"id":"g1", "role":"user", "content":"Initial thought"},
                {"id":"g2", "role":"assistant", "content":"New continuation"},
            ]},
            {"id": "new", "title": "New thread", "messages": [{"id":"n1", "role":"user", "content":"Brand new idea"}]},
        ]
        second = archive_store.import_json(json.dumps(second_export), "export-two.json")
        self.assertEqual(second["reconciliation"], {"added": 1, "updated": 1, "unchanged": 1})
        conversations = archive_store.list_conversations()
        self.assertEqual(len(conversations), 3)
        extended = next(item for item in conversations if item["source_id"] == "extended")
        self.assertEqual(extended["id"], original_ids["extended"])
        self.assertEqual(extended["depth"], 2)
        detail = archive_store.get_conversation(extended["id"])
        self.assertEqual([message["content"] for message in detail["messages"]], ["Initial thought", "New continuation"])

    def test_import_job_state_is_persistent_and_inspectable(self):
        job_id = archive_store.create_import_job("large-export.json")
        queued = archive_store.get_import_job(job_id)
        self.assertEqual((queued["status"], queued["stage"], queued["progress"]), ("queued", "received", 5))
        archive_store.update_import_job(job_id, status="running", stage="indexing", progress=80)
        running = archive_store.get_import_job(job_id)
        self.assertEqual((running["status"], running["stage"], running["progress"]), ("running", "indexing", 80))
        archive_store.update_import_job(job_id, status="complete", stage="complete", progress=100,
                                        result={"reconciliation": {"added": 3, "updated": 1, "unchanged": 9}})
        complete = archive_store.get_import_job(job_id)
        self.assertEqual(complete["result"]["reconciliation"]["unchanged"], 9)
        self.assertEqual(archive_store.list_import_jobs()[0]["id"], job_id)

    def test_json_array_streams_items_across_small_chunk_boundaries(self):
        path = Path(self.temp.name) / "stream.json"
        payload = [
            {"id": "one", "title": "One", "messages": [{"role":"user", "content":"A" * 5000}]},
            {"id": "two", "title": "Two", "messages": [{"role":"user", "content":"second"}]},
        ]
        path.write_text(json.dumps(payload), encoding="utf-8")
        items = list(archive_store.iter_json_array(path, chunk_size=37))
        self.assertEqual([item["id"] for item in items], ["one", "two"])
        result = archive_store.import_json_path(path, "provider-export.json")
        self.assertEqual(result["reconciliation"], {"added": 2, "updated": 0, "unchanged": 0})
        self.assertEqual(len(archive_store.list_conversations()), 2)

    def test_wrapped_provider_export_streams_conversations_array(self):
        path = Path(self.temp.name) / "wrapped.json"
        wrapped = {"export_version":"1", "account":{"name":"owner"}, "conversations":[
            {"id":"wrapped-1", "title":"Wrapped", "messages":[{"role":"user","content":"inside wrapper"}]}
        ], "metadata":{"complete":True}}
        path.write_text(json.dumps(wrapped), encoding="utf-8")
        items = list(archive_store.iter_json_array(path, chunk_size=19))
        self.assertEqual(items[0]["id"], "wrapped-1")
        result = archive_store.import_json_path(path, "chatgpt-export.json")
        self.assertEqual(result["platform"], "chatgpt")
        self.assertEqual(result["message_count"], 1)

    def test_gemini_and_codex_shapes_are_detected_and_normalized(self):
        gemini_path = Path(self.temp.name) / "gemini.json"
        gemini_path.write_text(json.dumps([{"id":"g", "title":"Gemini thread", "chunkedPrompt":{"parts":["Question"]},
                                            "modelResponse":{"parts":["Answer"]}}]), encoding="utf-8")
        gemini = archive_store.import_json_path(gemini_path, "provider.json")
        self.assertEqual(gemini["platform"], "gemini")
        self.assertEqual(gemini["message_count"], 2)
        codex_path = Path(self.temp.name) / "codex.json"
        codex_path.write_text(json.dumps([{"id":"c", "title":"Codex task", "rollout":{}, "turns":[
            {"role":"user", "content":"Build it"}, {"role":"assistant", "content":"Implemented"}
        ]}]), encoding="utf-8")
        codex = archive_store.import_json_path(codex_path, "provider.json")
        self.assertEqual(codex["platform"], "codex")
        self.assertEqual(codex["message_count"], 2)

    def test_analysis_creates_reviewable_evidence_only_from_user_messages(self):
        payload = [{"id":"ideas", "title":"Product direction", "messages":[
            {"id":"u1", "role":"user", "content":"I want to build a durable archive that keeps the source evidence attached."},
            {"id":"a1", "role":"assistant", "content":"We should invent an assistant-only feature that the user never requested."},
        ]}]
        imported = archive_store.import_json(json.dumps(payload), "ideas.json")
        conversation_id = imported["conversations"][0]["id"]
        result = archive_store.analyze_conversation(conversation_id)
        self.assertEqual(result["created"], 1)
        candidates = archive_store.list_candidates("pending")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["kind"], "idea")
        self.assertIn("durable archive", candidates[0]["excerpt"])
        self.assertEqual(candidates[0]["message_ordinal"], 0)
        repeated = archive_store.analyze_conversation(conversation_id)
        self.assertEqual((repeated["created"], repeated["existing"]), (0, 1))
        reviewed = archive_store.review_candidate(candidates[0]["id"], "accept")
        self.assertEqual(reviewed["status"], "accepted")
        self.assertEqual(archive_store.list_candidates("pending"), [])

    def test_analysis_abstains_when_source_has_no_explicit_signal(self):
        imported = archive_store.import_json(json.dumps([{
            "id":"neutral", "title":"Neutral", "messages":[{"role":"user", "content":"Thanks for the explanation."}]
        }]), "neutral.json")
        result = archive_store.analyze_conversation(imported["conversations"][0]["id"])
        self.assertTrue(result["abstained"])
        self.assertEqual(result["created"], 0)
        self.assertEqual(archive_store.list_candidates("pending"), [])

    def test_archive_wide_analysis_tracks_complete_coverage(self):
        archive_store.import_json(json.dumps([
            {"id":"one", "title":"Explicit", "messages":[{"role":"user", "content":"We should build a source-linked idea map for the archive."}]},
            {"id":"two", "title":"Neutral", "messages":[{"role":"user", "content":"Thank you for the useful explanation."}]},
        ]), "complete-export.json")
        before = archive_store.archive_analysis_overview()
        self.assertEqual((before["total"], before["unmapped"]), (2, 2))
        job = archive_store.create_analysis_job()
        complete = archive_store.run_archive_analysis(job["id"])
        self.assertEqual(complete["status"], "complete")
        self.assertEqual(complete["processed"], 2)
        self.assertEqual(complete["candidates_created"], 1)
        self.assertEqual(complete["abstained"], 1)
        after = archive_store.archive_analysis_overview()
        self.assertEqual((after["mapped"], after["unmapped"], after["no_explicit_evidence"]), (2, 0, 1))

    def test_cross_conversation_links_are_proposals_with_explained_shared_terms(self):
        imported = archive_store.import_json(json.dumps([
            {"id":"a", "title":"Archive concept", "messages":[{"role":"user", "content":"We should create a source-linked archive map for conversation history."}]},
            {"id":"b", "title":"History continuation", "messages":[{"role":"user", "content":"I want to extend the source-linked archive map across conversation history."}]},
        ]), "related.json")
        for conversation in imported["conversations"]:
            archive_store.analyze_conversation(conversation["id"])
        result = archive_store.generate_candidate_links()
        self.assertEqual(result["created"], 1)
        links = archive_store.list_candidate_links("pending")
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["relation_type"], "possible_overlap")
        self.assertIn("archive", links[0]["shared_terms"])
        self.assertIn("does not prove", links[0]["rationale"])
        reviewed = archive_store.review_candidate_link(links[0]["id"], "accept")
        self.assertEqual(reviewed["status"], "accepted")
        self.assertEqual(archive_store.list_candidate_links("pending"), [])
        candidates = archive_store.list_candidates("pending")
        workspace = {"seeds":[
            {"seed_id":"seed-a", "candidate_id":candidates[0]["id"]},
            {"seed_id":"seed-b", "candidate_id":candidates[1]["id"]},
        ], "relationships":[]}
        materialized = server.materialize_confirmed_candidate_links(workspace)
        self.assertEqual(len(materialized), 1)
        self.assertEqual(materialized[0]["approval_status"], "Approved")
        self.assertEqual(materialized[0]["source_candidate_link_id"], links[0]["id"])
        self.assertEqual(server.materialize_confirmed_candidate_links(workspace), [])

    def test_confirmed_decision_link_materializes_as_governance_not_seed_lineage(self):
        imported = archive_store.import_json(json.dumps([
            {"id":"idea", "title":"Storage idea", "messages":[{"role":"user", "content":"We should use durable SQLite archive storage for conversation history."}]},
            {"id":"decision", "title":"Storage decision", "messages":[{"role":"user", "content":"Decision: we will use durable SQLite archive storage for conversation history."}]},
        ]), "decision-link.json")
        for conversation in imported["conversations"]:
            archive_store.analyze_conversation(conversation["id"])
        archive_store.generate_candidate_links()
        link = archive_store.list_candidate_links("pending")[0]
        self.assertEqual(link["relation_type"], "possible_decision_link")
        archive_store.review_candidate_link(link["id"], "accept")
        candidates = archive_store.list_candidates("pending")
        idea = next(item for item in candidates if item["kind"] == "idea")
        decision_candidate = next(item for item in candidates if item["kind"] == "decision")
        workspace = {"seeds":[{"seed_id":"seed-storage", "candidate_id":idea["id"]}],
                     "decisions":[{"decision_id":"decision-storage", "candidate_id":decision_candidate["id"], "related_seeds":[]}],
                     "relationships":[]}
        bindings = server.materialize_confirmed_candidate_links(workspace)
        self.assertEqual(bindings[0]["binding_type"], "Decision Governance")
        self.assertEqual(workspace["decisions"][0]["related_seeds"], ["seed-storage"])
        self.assertEqual(workspace["seeds"][0]["decision_references"], ["decision-storage"])
        self.assertEqual(workspace["relationships"], [])


if __name__ == "__main__":
    unittest.main()
