import json, unittest

from tests.test_unified_runtime import UnifiedRuntime

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE=True
except ImportError:
    PLAYWRIGHT_AVAILABLE=False


@unittest.skipUnless(PLAYWRIGHT_AVAILABLE,"Playwright is not installed")
class HostedDashboardBrowserTests(unittest.TestCase):
    def test_local_dashboard_creates_a_provider_neutral_api_connection(self):
        runtime=UnifiedRuntime("local")
        try:
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=True); page=browser.new_page()
                page.goto(f"http://127.0.0.1:{runtime.port}/consumer",wait_until="networkidle")
                page.locator(".library-view-tab[data-library='intake']").click()
                page.locator(".source-method[data-source-method='api']").click()
                page.fill("#api-integration-name","Research automation")
                page.select_option("#api-integration-provider","automation")
                page.get_by_role("button",name="Create connection").click()
                page.wait_for_selector("#api-integration-secret pre")
                self.assertIn("sr_live_",page.locator("#api-integration-secret").inner_text())
                self.assertIn("Research automation",page.locator("#api-integration-list").inner_text())
                browser.close()
        finally: runtime.close()

    def test_local_dashboard_can_connect_and_sync_an_ai_conversation_folder(self):
        runtime=UnifiedRuntime("local")
        try:
            source=__import__("pathlib").Path(runtime.temp.name)/"connected-history"; source.mkdir()
            (source/"claude-session.jsonl").write_text(json.dumps({"sessionId":"browser-sync","type":"user","uuid":"source-message",
                "message":{"role":"user","content":"We should continue this connected conversation inside SeedReflections."}})+"\n",encoding="utf-8")
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=True); page=browser.new_page(); failures=[]
                page.on("response",lambda response: failures.append((response.status,response.url)) if response.status >= 400 else None)
                page.goto(f"http://127.0.0.1:{runtime.port}/consumer",wait_until="networkidle")
                page.locator(".source-method[data-source-method='folder']").click()
                page.select_option("#connector-provider","claude_code"); page.fill("#connector-root-path",str(source)); page.check("#connector-consent")
                page.get_by_role("button",name="Preview source").click()
                page.wait_for_selector("#connector-preview .connector-preview-item")
                page.get_by_role("button",name="Import selected history & connect").click()
                page.wait_for_function("() => document.querySelector('#connector-list').innerText.includes('Claude Code')")
                page.locator(".library-view-tab[data-library='map']").click(); page.wait_for_selector(".archive-map-card")
                self.assertIn("connected conversation",page.locator(".archive-map-card").first.inner_text().lower())
                self.assertEqual([item for item in failures if not item[1].endswith('/favicon.ico')],[])
                browser.close()
        finally: runtime.close()

    def test_import_map_accept_and_continue_use_v2(self):
        runtime=UnifiedRuntime("hosted")
        try:
            status,owner=runtime.request("POST","/api/v2/auth/signup",{
                "name":"Browser Owner","email":"browser@example.com","password":"strong-password-123"})
            self.assertEqual(status,201)
            token=owner["access_token"]
            archive={"conversations":[{"id":"browser-thread","title":"Product continuity", "messages":[
                {"id":"message-1","role":"user","content":"We should build a source-linked workspace that lets people continue ideas from exported conversations."},
                {"id":"message-2","role":"assistant","content":"The archive can preserve that intent and its evidence."}]}]}
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=True)
                page=browser.new_page()
                blocked=[]; failures=[]
                page.on("request",lambda request: blocked.append(request.url) if "/api/v1/" in request.url else None)
                page.on("response",lambda response: failures.append((response.status,response.url)) if response.status >= 400 else None)
                page.add_init_script(f"localStorage.setItem('seedreflections_access_token', {json.dumps(token)})")
                page.goto(f"http://127.0.0.1:{runtime.port}/consumer",wait_until="networkidle")
                page.set_input_files("#ws-file-input",{"name":"history.json","mimeType":"application/json","buffer":json.dumps(archive).encode()})
                page.wait_for_selector(".archive-map-card",timeout=15000)
                page.locator(".archive-map-card").first.click()
                page.get_by_role("button",name="🌱 Map Ideas").click()
                page.wait_for_selector(".candidate-card",timeout=10000)
                page.locator(".candidate-card .btn-primary").first.click()
                page.wait_for_function("() => Array.isArray(ALL_SEEDS) && ALL_SEEDS.length === 1")
                page.locator(".app-primary-tab[data-primary='workspace']").click()
                page.evaluate("() => { activeFocusSeedId=ALL_SEEDS[0].seed_id; }")
                page.fill("#chat-input","What should I do next?")
                page.click("#chat-send")
                page.wait_for_function("() => document.querySelector('#chat-messages').innerText.includes('confirmed intent')")
                self.assertEqual(blocked,[])
                self.assertEqual([item for item in failures if not item[1].endswith('/favicon.ico')],[])
                browser.close()
        finally:
            runtime.close()


if __name__=="__main__": unittest.main()
