import unittest
import socket
import threading
import sys
import os
import json
import time

# Adjust path to import server
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('localhost', 0))
    port = s.getsockname()[1]
    s.close()
    return port

class TestBrowserAutomation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PLAYWRIGHT_AVAILABLE:
            print("\n[WARNING] Playwright is not installed. Skipping browser automation tests.")
            print("To run, please execute:")
            print("  pip install playwright")
            print("  playwright install chromium")
            return

        # Setup sandbox databases
        cls.sandbox_dir = os.path.join(os.path.dirname(__file__), "sandbox_browser_test")
        os.makedirs(cls.sandbox_dir, exist_ok=True)
        
        cls.db_file = os.path.join(cls.sandbox_dir, "seeds.json")
        cls.config_file = os.path.join(cls.sandbox_dir, "config.json")
        cls.transcripts_dir = os.path.join(cls.sandbox_dir, "transcripts")
        os.makedirs(cls.transcripts_dir, exist_ok=True)

        # Initialize mock database
        initial_db = {
            "projects": [
                {
                    "project_id": "default_project",
                    "name": "Default Automation Project",
                    "purpose": "Test browser automated workflows",
                    "description": "Validation test space."
                }
            ],
            "seeds": [
                {
                    "seed_id": "seed_initial_1",
                    "project_id": "default_project",
                    "title": "Initial Seed One",
                    "intent": "Verify landing dashboard renders seeds list",
                    "status": "planted",
                    "continuity_status": "Active"
                }
            ],
            "decisions": [],
            "conflicts": [],
            "relationships": []
        }
        with open(cls.db_file, "w", encoding="utf-8") as f:
            json.dump(initial_db, f)

        with open(cls.config_file, "w", encoding="utf-8") as f:
            json.dump({"provider": "ollama", "model": "llama3", "url": "http://localhost:11434"}, f)

        # Override server paths
        server.DATA_FILE = cls.db_file
        server.CONFIG_FILE = cls.config_file
        server.TRANSCRIPTS_DIR = cls.transcripts_dir

        # Start server in thread
        cls.port = get_free_port()
        cls.server_address = ('localhost', cls.port)
        cls.httpd = server.ThreadingHTTPServer(cls.server_address, server.SeedReflectionAPIHandler)
        
        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever)
        cls.server_thread.daemon = True
        cls.server_thread.start()
        time.sleep(1) # Let server start up

    @classmethod
    def tearDownClass(cls):
        if not PLAYWRIGHT_AVAILABLE:
            return
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.server_thread.join(timeout=2)
        
        # Clean up files
        try:
            for f in os.listdir(cls.sandbox_dir):
                os.remove(os.path.join(cls.sandbox_dir, f))
            os.rmdir(cls.sandbox_dir)
        except Exception:
            pass

    def test_dashboard_ui_workflow(self):
        if not PLAYWRIGHT_AVAILABLE:
            self.skipTest("Playwright library is not installed.")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            url = f"http://localhost:{self.port}/consumer"
            page.goto(url)

            # Verify the consolidated product shell and library views.
            page.wait_for_selector("text=Bring your history home.")
            self.assertTrue(page.locator("#section-intake").is_visible())

            page.click(".library-view-tab[data-library='map']")
            page.wait_for_selector("#section-map", state="visible")
            self.assertTrue(page.locator("#archive-map-grid").is_visible())

            page.click(".library-view-tab[data-library='browser']")
            page.wait_for_selector("#section-browser", state="visible")
            self.assertTrue(page.locator("#seed-list").is_visible())

            page.click(".app-primary-tab[data-primary='workspace']")
            page.wait_for_selector("#section-workspace", state="visible")
            self.assertTrue(page.locator("#chat-input").is_visible())

            # Open Settings and verify core configuration controls are reachable.
            page.click("button[title='Settings']")
            page.wait_for_selector("#section-account", state="visible")
            page.click("button:has-text('Data, AI & portability')")
            page.wait_for_selector("#settings-modal", state="visible")
            self.assertTrue(page.locator("button:has-text('Export Package v2')").is_visible())
            self.assertTrue(page.locator("button:has-text('Import Package v2')").is_visible())
            self.assertTrue(page.locator("button:has-text('Download Complete Archive')").is_visible())
            self.assertTrue(page.locator("button:has-text('Restore Complete Archive')").is_visible())

            browser.close()

if __name__ == "__main__":
    unittest.main()
