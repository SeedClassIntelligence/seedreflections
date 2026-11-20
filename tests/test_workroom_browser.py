"""Browser checks for the Workspace home and the idea view, in Python Playwright so they run wherever the other browser tests run."""
import json
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from test_unified_runtime import UnifiedRuntime

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

DEMO = [
    ("Pricing for the beta", ["We should launch a pricing page for the beta next month.", "Good idea. Which tiers do you want to offer?",
                              "I decided to go with three tiers: free, pro and team.", "How will we handle refunds for annual plans?"]),
    ("Onboarding the first testers", ["How will we onboard the first twenty testers?", "A checklist and one welcome email usually work.",
                                      "Let's draft the onboarding email and decide who sends it."]),
    ("Hosting and backups", ["I want to run everything on one server with nightly backups.", "I decided to rehearse a restore before we invite anyone.",
                             "We need to write down what happens if the server is lost."]),
    ("Signing everything", ["Every platform should sign through Seed Signature.", "Let's build the partner key flow next.",
                            "Should the signing key ever leave the authority?"]),
    ("Browser extension idea", ["A one-click way to save the conversation I have open would help a lot.", "I decided it must never read pages in the background."]),
    ("Launch checklist", ["We need a launch checklist covering terms, hosting, backups and support.", "Let's write the checklist and review it with a lawyer."]),
]
DESKTOP, PHONE = {"width": 1440, "height": 900}, {"width": 390, "height": 844}


def build(runtime):
    """Import the demo history, wait for the analysis to finish, accept every idea and requirement but one, and leave a decision and an idea waiting."""
    data = [{"id": f"d{i}", "title": t, "messages": [{"id": f"m{j}", "role": "user" if j % 2 == 0 else "assistant", "content": c} for j, c in enumerate(ms)]}
            for i, (t, ms) in enumerate(DEMO)]
    runtime.request("POST", "/api/v2/imports", {"filename": "demo.json", "data": data})
    job = runtime.request("POST", "/api/v2/analysis/run", {})[1]
    for _ in range(120):
        time.sleep(.5)
        if runtime.request("GET", f"/api/v2/analysis/jobs/{job['id']}")[1].get("status") in ("complete", "completed", "failed"): break
    pending = runtime.request("GET", "/api/v2/candidates?status=pending")[1].get("candidates", [])
    keep = [next(c for c in pending if c["kind"] == "decision"), next(c for c in pending if c["kind"] != "decision")]
    for candidate in pending:
        if candidate not in keep:
            runtime.request("POST", f"/api/v2/candidates/{candidate['id']}/review", {"action": "accept"})
    return runtime.request("GET", "/api/v2/workspace")[1]["seeds"]


@unittest.skipUnless(PLAYWRIGHT_AVAILABLE, "Playwright is not installed")
class WorkroomBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = UnifiedRuntime("local", {"SEED_SIGNATURE_API_URL": "http://127.0.0.1:9", "SEED_SIGNATURE_PLATFORM_API_KEY": "test-key"})
        cls.seeds = build(cls.runtime)
        assert len(cls.seeds) >= 3, cls.seeds
        cls.A, cls.B, cls.C = cls.seeds[0], cls.seeds[1], cls.seeds[2]
        every = [s["seed_id"] for s in cls.seeds]
        cls.runtime.request("POST", "/api/v2/artifacts", {"type": "plan", "title": "Pricing page plan", "content": "1. Tiers", "seed_ids": every})
        cls.waiting = cls.runtime.request("GET", "/api/v2/overview")[1]["pending"]
        # a confirmed relationship A-B, a merely proposed one A-C, and a decision tied to A through related_seeds
        post = cls.runtime.request
        post("POST", "/api/v2/workspace/relationships/create", {"source_seed_id": cls.A["seed_id"], "target_seed_id": cls.B["seed_id"], "relationship_type": "Related Work", "created_by": "user"})
        post("POST", "/api/v2/workspace/relationships/create", {"source_seed_id": cls.A["seed_id"], "target_seed_id": cls.C["seed_id"], "relationship_type": "Related Work"})
        post("POST", "/api/v2/workspace/decisions", {"decision_statement": "Publish pricing before refund rules", "rationale": "Testers need prices first", "related_seeds": [cls.A["seed_id"]]})
        post("POST", "/api/v2/workspace/decisions", {"decision_statement": "Noted in the same chat only", "source_conversation_id": cls.A["source_conversation_id"]})
        cls.D = next(x for x in cls.seeds if x["source_conversation_id"] != cls.A["source_conversation_id"])

    @classmethod
    def tearDownClass(cls):
        cls.runtime.close()

    def page(self, playwright, size, runtime=None, tab="workspace"):
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport=size); errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{(runtime or self.runtime).port}/consumer-dashboard.html", wait_until="domcontentloaded")
        page.wait_for_function("() => typeof ALL_SEEDS !== 'undefined' && typeof switchDashTab === 'function'")
        page.wait_for_timeout(1500); page.evaluate(f"() => switchDashTab('{tab}')"); page.wait_for_timeout(1200)
        return browser, page, errors

    def focus(self, page, seed):
        page.evaluate("(id) => selectSeedForCockpit(id)", seed["seed_id"]); page.wait_for_selector("#idea-header", state="visible")

    # ---- Overview ----
    def test_overview_is_three_rows_whose_buttons_go_where_the_work_is_done(self):
        with sync_playwright() as pw:
            for label, size in (("desktop", DESKTOP), ("phone", PHONE)):
                browser, page, errors = self.page(pw, size, tab="overview")
                rows = page.locator("#overview-brief .brief-row"); self.assertEqual(rows.count(), 3, label)
                needs = " ".join(page.inner_text("#brief-needs-you").split())
                self.assertIn(f"{self.waiting} finding", needs, label); self.assertIn("for your decision", needs, label); self.assertIn("Review now", needs, label)
                self.assertIn("in every state", page.inner_text("#overview-brief"), label)                 # totals are described as totals, not as work in progress
                self.assertEqual(page.locator("#overview-brief .btn-primary").count(), 1, label)           # one main action, the one that needs the person
                self.assertEqual(page.locator(".overview-stat").count(), 0, label)                         # the six counters are gone
                self.assertFalse(page.evaluate("() => document.documentElement.scrollWidth > innerWidth"), label)
                page.click("#brief-needs-you button"); page.wait_for_timeout(500)
                self.assertEqual(page.evaluate("() => localStorage.getItem('active_dash_tab')"), "review", label)
                self.assertEqual(errors, [], label); browser.close()

    def test_overview_with_nothing_waiting_says_so_and_offers_the_next_step_not_review(self):
        with sync_playwright() as pw:
            browser, page, errors = self.page(pw, DESKTOP, tab="overview")
            page.evaluate("() => { ARCHIVE_TOTALS = Object.assign({}, ARCHIVE_TOTALS || {}, {pending: 0}); PENDING_CANDIDATE_COUNT = 0; renderGarden(); }")
            text = " ".join(page.inner_text("#brief-needs-you").split())
            self.assertIn("Nothing is waiting for your decision.", text); self.assertNotIn("Review now", text)
            self.assertEqual(page.inner_text("#brief-needs-action"), "Add history")
            self.assertEqual(page.locator("#overview-brief .btn-primary").count(), 0)                   # the archive has history, so nothing is shouted
            page.click("#brief-needs-action"); page.wait_for_timeout(300)
            self.assertEqual(page.evaluate("() => localStorage.getItem('active_dash_tab')"), "intake")
            self.assertEqual(errors, []); browser.close()
        empty = UnifiedRuntime("local")
        try:
            with sync_playwright() as pw:
                browser, page, errors = self.page(pw, PHONE, runtime=empty, tab="overview")
                text = " ".join(page.inner_text("#brief-needs-you").split())
                self.assertIn("Bring in your AI history", text); self.assertNotIn("Review now", text)
                self.assertEqual(page.locator("#overview-brief .btn-primary").count(), 1)                # with an empty archive, adding history is the main action
                self.assertEqual(page.inner_text("#overview-brief .btn-primary"), "Add history")
                self.assertIn("0 ideas, 0 decisions and 0 projects", " ".join(page.inner_text("#overview-brief").split()))
                self.assertEqual(errors, []); browser.close()
        finally:
            empty.close()

    # ---- Work home ----
    def test_work_home_says_what_is_waiting_where_you_left_off_and_what_to_start(self):
        with sync_playwright() as pw:
            for label, size in (("desktop", DESKTOP), ("phone", PHONE)):
                browser, page, errors = self.page(pw, size)
                text = " ".join(page.inner_text(".wh").split())
                phrase = "1 finding is waiting for your decision" if self.waiting == 1 else f"{self.waiting} findings are waiting for your decision"
                self.assertIn(phrase, text, label)
                self.assertGreaterEqual(page.locator(".wh-card .btn-primary").count(), 1)
                self.assertIn("recent work", text.lower()); self.assertGreaterEqual(page.locator(".wh-work").count(), 1)       # saved work is listed (which items depends on what other tests saved)
                self.assertIn("From a finding", text); self.assertIn("From a blank page", text)
                self.assertNotIn("Review the source context", text)
                self.assertFalse(page.evaluate("() => document.documentElement.scrollWidth > innerWidth"), label)
                self.assertEqual(page.evaluate("() => [...document.querySelectorAll('.wh *')].filter(e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()) && parseFloat(getComputedStyle(e).fontSize) < 12).length"), 0)
                self.assertEqual(errors, [], label); browser.close()

    def test_first_run_invites_the_person_to_bring_in_history(self):
        empty = UnifiedRuntime("local")
        try:
            with sync_playwright() as pw:
                browser, page, errors = self.page(pw, DESKTOP, runtime=empty)
                self.assertIn("Start by bringing in your history", " ".join(page.inner_text(".wh").split()))
                self.assertEqual(page.locator(".wh-first .btn-primary").count(), 1); self.assertEqual(errors, []); browser.close()
        finally:
            empty.close()

    # ---- Idea view ----
    def test_idea_view_header_tabs_source_outputs_and_the_way_back(self):
        with sync_playwright() as pw:
            browser, page, errors = self.page(pw, DESKTOP)
            page.locator(".wh-card .btn-primary").first.click(); page.wait_for_selector("#idea-header", state="visible")
            self.assertEqual(page.locator("#idea-header [role=tab]").count(), 4)
            self.assertEqual(page.get_attribute("#idea-tab-work", "aria-selected"), "true"); self.assertTrue(page.is_visible("#chat-input"))
            title = page.inner_text("#idea-title").strip(); seed = next(s for s in self.seeds if s["title"].startswith(title[:40]))
            convo = self.runtime.request("GET", f"/api/v2/conversations/{seed['source_conversation_id']}")[1]
            expected = next(m for m in convo["messages"] if m["id"] == seed["source_message_id"])["content"]
            page.click("#idea-tab-sources"); page.wait_for_selector("#idea-panel .src-msg.hit")
            self.assertIn(expected, " ".join(page.inner_text("#idea-panel .src-msg.hit").split())); self.assertFalse(page.is_visible("#chat-input"))
            page.click("#idea-tab-outputs"); self.assertIn("Pricing page plan", page.inner_text("#idea-panel")); self.assertEqual(page.inner_text("#idea-n-outputs").strip(), "1")
            page.click("#idea-tab-decisions"); page.click('#idea-panel button:has-text("Record a decision")')
            self.assertEqual(page.get_attribute("#idea-tab-work", "aria-selected"), "true"); self.assertTrue(page.input_value("#chat-input").startswith("Record a decision"))
            self.assertFalse(page.evaluate("() => document.documentElement.scrollWidth > innerWidth"))
            page.click('#idea-header button:has-text("Workspace home")'); page.wait_for_timeout(1200)
            self.assertTrue(page.is_visible(".wh")); self.assertFalse(page.is_visible("#idea-header")); self.assertEqual(errors, []); browser.close()

    def test_open_the_full_conversation_opens_that_exact_conversation_at_the_source_message(self):
        with sync_playwright() as pw:
            browser, page, errors = self.page(pw, DESKTOP); self.focus(page, self.A)
            convo = self.runtime.request("GET", f"/api/v2/conversations/{self.A['source_conversation_id']}")[1]
            title = convo["conversation"]["title"]; expected = next(m for m in convo["messages"] if m["id"] == self.A["source_message_id"])["content"]
            page.click("#idea-tab-sources"); page.wait_for_selector("#idea-panel .src-msg.hit")
            page.click('#idea-panel button:has-text("Open the full conversation")'); page.wait_for_selector("#archive-map-detail .archive-message-source")
            self.assertTrue(page.is_visible("#section-map")); self.assertIn(title, page.inner_text("#archive-map-detail h2"))
            self.assertIn(expected, " ".join(page.inner_text("#archive-map-detail .archive-message-source").split()))
            top = page.evaluate("() => document.querySelector('.archive-message-source').getBoundingClientRect().top")
            self.assertTrue(0 <= top < 900, top)                                                          # the marked message is on screen
            self.assertEqual(errors, []); browser.close()

    def test_an_unmatched_source_message_is_never_labelled_as_where_the_idea_came_from(self):
        with sync_playwright() as pw:
            browser, page, errors = self.page(pw, DESKTOP); self.focus(page, self.A)
            page.evaluate("() => { var s = ideaSeed(); s.source_message_id = 'no-such-message'; }")
            page.click("#idea-tab-sources"); page.wait_for_selector("#idea-panel .src-msg")
            text = " ".join(page.inner_text("#idea-panel").split())
            label = " ".join(page.inner_text("#idea-panel .src-msg.hit .who").split()).lower()
            self.assertIn("closest match", label); self.assertNotIn("where this idea came from", label)       # a match is offered as a match, never as the origin
            self.assertIn("could not be found", text)                                                         # and the person is told
            # nothing matches at all: no message is marked and the start of the conversation is shown with a notice
            page.evaluate("() => { var s = ideaSeed(); s.source_message_id = null; s.content = 'zzz nothing like this appears anywhere'; }")
            page.click("#idea-tab-outputs"); page.click("#idea-tab-sources"); page.wait_for_selector("#idea-panel .idea-empty[role=note]")
            self.assertEqual(page.locator("#idea-panel .src-msg.hit").count(), 0); self.assertIn("none is marked", page.inner_text("#idea-panel"))
            self.assertEqual(errors, []); browser.close()

    def test_only_approved_relationships_are_listed_as_related_ideas(self):
        with sync_playwright() as pw:
            browser, page, errors = self.page(pw, DESKTOP); self.focus(page, self.A)
            page.click("#idea-tab-sources"); page.wait_for_selector("#idea-panel .src-msg"); page.wait_for_timeout(400)
            panel = " ".join(page.inner_text("#idea-panel").split())
            lower = panel.lower(); self.assertIn("related ideas you confirmed", lower); self.assertIn(self.B["title"][:30].lower(), lower)     # the approved one (approval_status: Approved)
            self.assertNotIn(self.C["title"][:30].lower(), lower.split("related ideas you confirmed")[1])                                  # the merely proposed one
            self.assertEqual(errors, []); browser.close()

    def test_direct_decisions_are_kept_apart_from_decisions_that_only_share_the_conversation(self):
        with sync_playwright() as pw:
            browser, page, errors = self.page(pw, DESKTOP)
            self.focus(page, self.A); page.click("#idea-tab-decisions")
            panel = page.inner_text("#idea-panel"); lower = " ".join(panel.split()).lower()
            direct, context = lower.split("also decided in the same conversation")[0], lower.split("also decided in the same conversation")[1]
            self.assertIn("publish pricing before refund rules", direct)                                  # linked through related_seeds
            self.assertNotIn("noted in the same chat only", direct)                                       # context is never presented as linked
            self.assertIn("noted in the same chat only", context); self.assertIn("not linked to this idea", context)
            self.assertEqual(page.inner_text("#idea-n-decisions").strip(), "1")                           # the count is direct decisions only
            self.focus(page, self.D); page.click("#idea-tab-decisions")                                   # an idea from another conversation sees neither
            other = page.inner_text("#idea-panel").lower()
            self.assertNotIn("publish pricing before refund rules", other); self.assertNotIn("noted in the same chat only", other)
            linked = page.evaluate("""() => { var sd = {seed_id: 'x1', decision_references: ['d1'], source_conversation_id: null};
                ALL_DECISIONS = ALL_DECISIONS.concat([{decision_id: 'd1', statement: 'Linked from the idea side'}]); return ideaDecisions(sd).map(function(d){ return d.statement; }); }""")
            self.assertEqual(linked, ["Linked from the idea side"])                                       # and a link recorded on the idea itself counts
            self.assertEqual(errors, []); browser.close()

    # ---- saved work keeps its relationships ----
    def make_artifact(self, title, **fields):
        body = {"type": "plan", "title": title, "content": "first version", "seed_ids": [self.A["seed_id"]], "conversation_ids": [self.A["source_conversation_id"]]}
        body.update(fields)
        made = self.runtime.request("POST", "/api/v2/artifacts", body)[1]["artifact"]; return made["artifact_id"]

    def stored(self, artifact_id):
        return next(a for a in self.runtime.request("GET", "/api/v2/artifacts")[1]["artifacts"] if a["artifact_id"] == artifact_id)

    def edit_in_the_studio(self, page, artifact_id, text):
        page.evaluate("(id) => openArtifactById(id)", artifact_id); page.wait_for_function("(id) => document.getElementById('artifact-id').value === id", arg=artifact_id)
        page.fill("#artifact-content", text); page.click('#section-artifacts button:has-text("Save artifact")')
        for _ in range(40):
            if self.stored(artifact_id)["content"] == text: return
            page.wait_for_timeout(150)
        self.fail("the edit was never saved")

    def test_editing_saved_work_with_nothing_in_focus_keeps_every_link(self):
        artifact_id = self.make_artifact("Plan edited without focus")
        with sync_playwright() as pw:
            browser, page, errors = self.page(pw, DESKTOP)
            self.assertEqual(page.evaluate("() => activeFocusSeedId"), None)                              # nothing is focused, as when opened from Recent work
            self.edit_in_the_studio(page, artifact_id, "second version")
            saved = self.stored(artifact_id)
            self.assertEqual(saved["seed_ids"], [self.A["seed_id"]]); self.assertEqual(saved["conversation_ids"], [self.A["source_conversation_id"]])
            self.assertEqual(len(saved["versions"]), 1)                                                   # history kept
            self.assertIn("Saving keeps these links", page.inner_text("#artifact-links")); self.assertEqual(errors, []); browser.close()

    def test_editing_saved_work_while_another_idea_is_in_focus_neither_loses_nor_adds_links(self):
        artifact_id = self.make_artifact("Plan edited under another idea")
        with sync_playwright() as pw:
            browser, page, errors = self.page(pw, DESKTOP); self.focus(page, self.D)
            page.evaluate("(id) => { activeWorkingThreadId = id; }", self.D["source_conversation_id"])
            self.edit_in_the_studio(page, artifact_id, "second version")
            saved = self.stored(artifact_id)
            self.assertEqual(saved["seed_ids"], [self.A["seed_id"]])                                      # still A, and D was not added
            self.assertEqual(saved["conversation_ids"], [self.A["source_conversation_id"]]); self.assertEqual(errors, []); browser.close()

    def test_work_started_from_an_idea_is_linked_to_it_and_stays_linked_after_an_unfocused_edit(self):
        with sync_playwright() as pw:
            browser, page, errors = self.page(pw, DESKTOP); self.focus(page, self.D)
            page.click("#idea-tab-outputs"); page.click('#idea-panel button:has-text("Brief")'); page.wait_for_selector("#artifact-title", state="visible")
            page.fill("#artifact-title", "Brief started from an idea"); page.fill("#artifact-content", "draft one"); page.click('#section-artifacts button:has-text("Save artifact")')
            artifact = None
            for _ in range(40):
                artifact = next((a for a in self.runtime.request("GET", "/api/v2/artifacts")[1]["artifacts"] if a["title"] == "Brief started from an idea"), None)
                if artifact: break
                page.wait_for_timeout(150)
            self.assertIsNotNone(artifact); self.assertEqual(artifact["seed_ids"], [self.D["seed_id"]])
            page.evaluate("() => clearActiveSeedFocus()"); page.wait_for_timeout(300)                     # leave the idea, then edit the saved work
            self.edit_in_the_studio(page, artifact["artifact_id"], "draft two")
            self.assertEqual(self.stored(artifact["artifact_id"])["seed_ids"], [self.D["seed_id"]]); self.assertEqual(errors, []); browser.close()

    def test_a_signed_artifact_keeps_its_signature_when_edited_and_says_it_is_out_of_date(self):
        artifact_id = self.make_artifact("Signed plan")
        self.assertEqual(self.runtime.request("POST", f"/api/v2/artifacts/{artifact_id}/signature", {"signature_id": "sig_abc12345"})[0], 200)
        with sync_playwright() as pw:
            browser, page, errors = self.page(pw, DESKTOP)
            self.edit_in_the_studio(page, artifact_id, "changed after signing")
            saved = self.stored(artifact_id)
            self.assertEqual(saved["signature"]["signature_id"], "sig_abc12345"); self.assertEqual(saved["signature"]["status"], "edited_since")
            self.assertEqual(saved["seed_ids"], [self.A["seed_id"]]); self.assertEqual(errors, []); browser.close()

    def test_the_api_keeps_links_unless_a_list_is_sent_and_rejects_a_malformed_one(self):
        artifact_id = self.make_artifact("API link rules")
        post = lambda body: self.runtime.request("POST", f"/api/v2/artifacts/{artifact_id}", body)
        self.assertEqual(post({"content": "no link fields"})[0], 200)
        self.assertEqual((self.stored(artifact_id)["seed_ids"], self.stored(artifact_id)["conversation_ids"]), ([self.A["seed_id"]], [self.A["source_conversation_id"]]))
        self.assertEqual(post({"seed_ids": None})[0], 400); self.assertEqual(post({"seed_ids": "abc"})[0], 400); self.assertEqual(post({"conversation_ids": [1]})[0], 400)
        self.assertEqual(self.stored(artifact_id)["seed_ids"], [self.A["seed_id"]])                       # a bad request changed nothing
        self.assertEqual(post({"seed_ids": [self.B["seed_id"]]})[0], 200); self.assertEqual(self.stored(artifact_id)["seed_ids"], [self.B["seed_id"]])   # an explicit list replaces on purpose

    def test_on_a_phone_the_work_area_comes_first_and_the_idea_is_in_view_after_continue_and_inspect(self):
        with sync_playwright() as pw:
            browser, page, errors = self.page(pw, PHONE)
            order = page.evaluate("() => [document.getElementById('cockpit-chat-panel').getBoundingClientRect().top, document.getElementById('cockpit-shelf-panel').getBoundingClientRect().top]")
            self.assertLess(order[0], order[1])                                                          # Active work before Project memory
            page.locator(".wh-card .btn-primary").first.click(); page.wait_for_selector("#idea-header", state="visible"); page.wait_for_timeout(500)
            top = page.evaluate("() => document.getElementById('idea-header').getBoundingClientRect().top")
            self.assertTrue(0 <= top < 844, top)                                                          # not above the screen
            self.assertIn(page.evaluate("() => document.activeElement.id"), ("idea-title", "chat-input"))          # focus lands in the idea, never back above it
            # Inspect from the idea list lower on the page must also bring the idea into view
            page.evaluate("() => document.getElementById('shelf-seed-list').scrollIntoView()"); page.wait_for_timeout(200)
            page.locator("#shelf-seed-list .shelf-seed-card .btn-ghost").nth(1).click(); page.wait_for_timeout(600)
            top = page.evaluate("() => document.getElementById('idea-header').getBoundingClientRect().top")
            self.assertTrue(0 <= top < 844, top)
            self.assertFalse(page.evaluate("() => document.documentElement.scrollWidth > innerWidth")); self.assertEqual(errors, []); browser.close()


if __name__ == "__main__":
    unittest.main()
