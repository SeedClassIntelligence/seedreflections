import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

import archive_store as local
import tenant_archive_store as tenant
import workspace_store


def _export(tag, kinds):
    """One ChatGPT-style conversation whose messages carry the given trigger phrases."""
    mapping, prev = {}, None
    for index, text in enumerate(kinds):
        node = f"n{tag}{index}"
        mapping[node] = {"parent": prev, "message": {"id": f"m{tag}{index}", "create_time": 1700000000 + index,
            "author": {"role": "user" if index % 2 == 0 else "assistant"}, "content": {"parts": [text]}}}
        prev = node
    return {"id": f"c{tag}", "title": f"Conversation {tag}", "create_time": 1700000000, "mapping": mapping}


CORPUS = [
    _export("a", ["Opening remarks here.", "Sure.", "We decided to adopt weekly reviews for the team.", "Noted, thanks.", "Closing remarks."]),
    _export("b", ["Idea: build a source coverage board for imports.", "Good point.", "TODO: write the launch plan with owners."]),
]


class LocalInbox(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        p = patch.object(local, "DB_PATH", Path(self.temp.name) / "archive.db"); p.start(); self.addCleanup(p.stop)
        local.initialize(); local.import_json(json.dumps(CORPUS).encode(), "x.json")
        for item in local.list_conversations(): local.analyze_conversation(item["id"])

    def test_filters_facets_and_sorting_agree_with_each_other(self):
        total = local.count_candidates("pending")
        self.assertGreaterEqual(total, 3)
        facets = local.candidate_facets("pending")
        self.assertEqual(sum(facets["kinds"].values()), total); self.assertEqual(facets["statuses"]["pending"], total)
        for kind, n in facets["kinds"].items():
            self.assertEqual(local.count_candidates("pending", kind=kind), n)
            self.assertEqual(len(local.list_candidates("pending", 100, 0, kind=kind)), n)
        self.assertEqual(local.count_candidates("pending", platform="chatgpt"), total)
        self.assertEqual(local.count_candidates("pending", platform="claude"), 0)
        self.assertEqual(local.count_candidates("pending", query="weekly"), len(local.list_candidates("pending", 100, 0, query="weekly")))
        self.assertGreaterEqual(local.count_candidates("pending", query="weekly"), 1)
        for hostile in ["%", "_", "'; DROP TABLE idea_candidates;--", '"']:
            local.list_candidates("pending", 10, 0, query=hostile); local.count_candidates("pending", query=hostile)
        self.assertEqual(local.count_candidates("pending"), total)  # table intact
        ids = [c["id"] for c in local.list_candidates("pending", 100, 0, sort="confidence")]
        self.assertEqual(len(ids), total)

    def test_detail_gives_exact_passage_and_surrounding_messages(self):
        target = next(c for c in local.list_candidates("pending", 100) if "weekly" in c["interpretation"])
        detail = local.get_candidate_detail(target["id"], window=1)
        sources = [m for m in detail["context"] if m["is_source"]]
        self.assertEqual(len(sources), 1); self.assertIn("weekly reviews", sources[0]["content"])
        self.assertEqual([m["ordinal"] for m in detail["context"]], [1, 2, 3])  # one before, source, one after
        self.assertEqual(detail["message_total"], 5); self.assertEqual(detail["method"], "evidence_rules_v1")
        self.assertIsNone(local.get_candidate_detail("0" * 32))

    def test_defer_then_accept_and_reopen_rules(self):
        item = local.list_candidates("pending", 1)[0]
        self.assertEqual(local.review_candidate(item["id"], "defer")["status"], "deferred")
        self.assertEqual(local.candidate_facets()["statuses"]["deferred"], 1)
        self.assertEqual(local.review_candidate(item["id"], "accept")["status"], "accepted")  # deferred can be decided later
        with self.assertRaises(ValueError): local.review_candidate(item["id"], "reopen")      # accepted is never silently undone
        with self.assertRaises(ValueError): local.review_candidate(item["id"], "reject")
        other = local.list_candidates("pending", 1)[0]
        local.review_candidate(other["id"], "reject")
        self.assertEqual(local.review_candidate(other["id"], "reopen")["status"], "pending")  # a mistaken dismissal is recoverable
        self.assertIsNone(next((c for c in local.list_candidates("rejected", 10) if c["id"] == other["id"]), None))
        with self.assertRaises(ValueError): local.review_candidate(other["id"], "bogus")
        with self.assertRaises(ValueError): local.review_candidate("nope", "accept")

    def test_history_lists_reviewed_items_newest_first(self):
        a, b = local.list_candidates("pending", 2)
        local.review_candidate(a["id"], "reject"); local.review_candidate(b["id"], "reject")
        history = local.list_candidates("rejected", 10, 0, sort="reviewed")
        self.assertEqual({h["id"] for h in history}, {a["id"], b["id"]}); self.assertTrue(all(h["reviewed_at"] for h in history))


class TenantInbox(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        for module in (local, tenant, workspace_store):
            if hasattr(module, "DB_PATH"):
                p = patch.object(module, "DB_PATH", Path(self.temp.name) / "archive.db"); p.start(); self.addCleanup(p.stop)
        tenant.initialize()
        self.ws, self.other = "ws-a", "ws-b"
        tenant.import_json(self.ws, json.dumps(CORPUS)); tenant.import_json(self.other, json.dumps(CORPUS[:1]))
        for ws in (self.ws, self.other):
            with tenant._connect() as db:
                ids = [r[0] for r in db.execute("SELECT id FROM tenant_conversations WHERE workspace_id=?", (ws,))]
            for cid in ids: tenant.analyze(ws, cid)

    def test_parity_and_tenant_isolation(self):
        total = tenant.count_candidates(self.ws)
        self.assertGreaterEqual(total, 3); self.assertLess(tenant.count_candidates(self.other), total)
        facets = tenant.candidate_facets(self.ws); self.assertEqual(sum(facets["kinds"].values()), total)
        for kind, n in facets["kinds"].items(): self.assertEqual(len(tenant.list_candidates(self.ws, "pending", 100, 0, kind=kind)), n)
        mine = tenant.list_candidates(self.ws, "pending", 100)[0]
        self.assertIsNone(tenant.get_candidate_detail(self.other, mine["id"]))         # another tenant cannot read it
        with self.assertRaises(KeyError): tenant.review(self.other, mine["id"], "reject")  # nor review it
        detail = tenant.get_candidate_detail(self.ws, mine["id"], window=1)
        self.assertEqual(sum(1 for m in detail["context"] if m["is_source"]), 1)

    def test_defer_accept_reopen_rules(self):
        item = tenant.list_candidates(self.ws, "pending", 1)[0]
        tenant.review(self.ws, item["id"], "defer")
        self.assertEqual(tenant.candidate_facets(self.ws)["statuses"]["deferred"], 1)
        tenant.review(self.ws, item["id"], "reject")
        self.assertEqual(tenant.review(self.ws, item["id"], "reopen")["status"], "pending")
        with self.assertRaises(KeyError): tenant.review(self.ws, item["id"], "reopen")  # already pending


if __name__ == "__main__":
    unittest.main()


class DetectorParity(unittest.TestCase):
    """Local and hosted must find the same things in the same export."""
    def test_same_export_same_findings_in_both_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            for module in (local, tenant, workspace_store):
                if hasattr(module, "DB_PATH"):
                    p = patch.object(module, "DB_PATH", Path(directory) / "archive.db"); p.start(); self.addCleanup(p.stop)
            local.initialize(); tenant.initialize()
            local.import_json(json.dumps(CORPUS).encode(), "x.json"); tenant.import_json("ws", json.dumps(CORPUS))
            for item in local.list_conversations(): local.analyze_conversation(item["id"])
            with tenant._connect() as db: ids = [r[0] for r in db.execute("SELECT id FROM tenant_conversations")]
            for cid in ids: tenant.analyze("ws", cid)
            shape = lambda rows: sorted((r["kind"], r["interpretation"], r["title"]) for r in rows)
            self.assertEqual(shape(local.list_candidates("pending", 100)), shape(tenant.list_candidates("ws", "pending", 100)))
            kinds = {r["kind"] for r in local.list_candidates("pending", 100)}
            self.assertEqual(kinds, {"decision", "idea", "task"})   # includes "TODO:" with a colon

    def test_reanalysis_never_resurrects_a_dismissed_candidate_in_hosted_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            for module in (local, tenant, workspace_store):
                if hasattr(module, "DB_PATH"):
                    p = patch.object(module, "DB_PATH", Path(directory) / "archive.db"); p.start(); self.addCleanup(p.stop)
            tenant.initialize(); tenant.import_json("ws", json.dumps(CORPUS))
            with tenant._connect() as db: cid = db.execute("SELECT id FROM tenant_conversations LIMIT 1").fetchone()[0]
            tenant.analyze("ws", cid)
            item = tenant.list_candidates("ws", "pending", 1)[0]; tenant.review("ws", item["id"], "reject")
            again = tenant.analyze("ws", cid)
            self.assertEqual(again["candidates_created"], 0)
            self.assertEqual(tenant.count_candidates("ws", "rejected"), 1)
            self.assertNotIn(item["interpretation"], [r["interpretation"] for r in tenant.list_candidates("ws", "pending", 100)])


class RelationshipListing(unittest.TestCase):
    PAIR = [
        _export("p", ["We decided to adopt weekly reviews for the whole product team."]),
        _export("q", ["We decided to adopt weekly reviews across the product team and partners."]),
    ]

    def _patch(self, directory):
        for module in (local, tenant, workspace_store):
            if hasattr(module, "DB_PATH"):
                p = patch.object(module, "DB_PATH", Path(directory) / "archive.db"); p.start(); self.addCleanup(p.stop)

    def test_local_links_report_total_and_page(self):
        with tempfile.TemporaryDirectory() as d:
            self._patch(d); local.initialize(); local.import_json(json.dumps(self.PAIR).encode(), "x.json")
            for item in local.list_conversations(): local.analyze_conversation(item["id"])
            local.generate_candidate_links()
            total = local.count_candidate_links("pending")
            self.assertGreaterEqual(total, 1)
            first = local.list_candidate_links("pending", 1, 0)
            self.assertEqual(len(first), 1); self.assertTrue(first[0]["left_title"] and first[0]["right_title"])
            self.assertEqual(local.list_candidate_links("pending", 1, total), [])

    def test_hosted_links_carry_titles_and_are_tenant_scoped(self):
        with tempfile.TemporaryDirectory() as d:
            self._patch(d); tenant.initialize(); tenant.import_json("ws", json.dumps(self.PAIR)); tenant.import_json("other", json.dumps(CORPUS[:1]))
            for ws in ("ws", "other"):
                with tenant._connect() as db: ids = [r[0] for r in db.execute("SELECT id FROM tenant_conversations WHERE workspace_id=?", (ws,))]
                for cid in ids: tenant.analyze(ws, cid)
            tenant.generate_links("ws")
            links = tenant.list_links("ws")
            self.assertEqual(tenant.count_links("ws"), len(links)); self.assertGreaterEqual(len(links), 1)
            for key in ("left_title", "right_title", "left_conversation", "right_conversation", "relation_type", "rationale", "shared_terms"):
                self.assertTrue(links[0].get(key), key)       # was missing: the UI rendered "undefined ↔ undefined"
            self.assertEqual(tenant.list_links("other"), []); self.assertEqual(tenant.count_links("other"), 0)


class HostedAcceptAndHandlerSafety(unittest.TestCase):
    def test_hosted_deferred_item_can_be_accepted_with_edits(self):
        with tempfile.TemporaryDirectory() as d:
            for module in (local, tenant, workspace_store):
                if hasattr(module, "DB_PATH"):
                    p = patch.object(module, "DB_PATH", Path(d) / "archive.db"); p.start(); self.addCleanup(p.stop)
            tenant.initialize(); workspace_store.create_empty_workspace("ws")
            tenant.import_json("ws", json.dumps(CORPUS))
            with tenant._connect() as db: ids = [r[0] for r in db.execute("SELECT id FROM tenant_conversations WHERE workspace_id='ws'")]
            for cid in ids: tenant.analyze("ws", cid)
            item = next(c for c in tenant.list_candidates("ws", "pending", 100) if c["kind"] == "decision")
            tenant.review("ws", item["id"], "defer")
            result = workspace_store.accept_tenant_candidate("ws", item["id"], title="EDITED decision wording", intent="My own meaning")
            self.assertEqual(result["status"], "accepted")
            document = workspace_store.load_workspace(workspace_id="ws")
            self.assertTrue(any(x["statement"] == "EDITED decision wording" and x["rationale"] == "My own meaning" for x in document["decisions"]))
            self.assertEqual(tenant.count_candidates("ws", "accepted"), 1)
            with self.assertRaises(KeyError): workspace_store.accept_tenant_candidate("ws", item["id"])  # cannot accept twice

    def test_unexpected_errors_return_a_json_500_not_a_dropped_connection(self):
        import http.client, threading
        from http.server import ThreadingHTTPServer
        import server
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.SeedReflectionAPIHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True); thread.start()
        self.addCleanup(lambda: (httpd.shutdown(), httpd.server_close()))
        port = httpd.server_address[1]
        def get(path):
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            connection.request("GET", path, headers={"Host": f"127.0.0.1:{port}"})
            response = connection.getresponse(); body = response.read(); connection.close()
            return response.status, json.loads(body)
        with patch.object(server, "load_workspace", side_effect=RuntimeError("secret internal detail")), \
             patch("traceback.print_exc"):
            status, body = get("/api/v2/workspace")
        self.assertEqual(status, 500); self.assertEqual(body["code"], "internal_error")
        self.assertNotIn("secret internal detail", json.dumps(body))   # internals are not leaked
        self.assertEqual(get("/api/v2/health")[0], 200)                # and the server keeps serving
