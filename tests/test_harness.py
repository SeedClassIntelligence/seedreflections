import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from test_unified_runtime import UnifiedRuntime


class HarnessTests(unittest.TestCase):
    def test_a_long_test_does_not_hang_when_the_server_logs_more_than_a_pipe_holds(self):
        """The server logs a line to stderr for every request. With an unread pipe (about 64 KB) the server blocked after roughly 900
        requests and the test timed out. The harness now writes the log to a file."""
        runtime = UnifiedRuntime("local")
        try:
            started = time.time()
            for _ in range(2500):                                   # about 200 KB of log lines
                self.assertEqual(runtime.request("GET", "/api/v2/health")[0], 200)
            self.assertLess(time.time() - started, 90)
            self.assertIn("GET /api/v2/health", runtime.server_log())   # and the log is still there to read when something fails
        finally:
            runtime.close()

    def test_a_server_that_fails_to_start_reports_why_and_does_so_promptly(self):
        started = time.time()
        with self.assertRaises(RuntimeError) as caught:
            UnifiedRuntime("not-a-real-mode")
        self.assertIn("Invalid SEED_REFLECTIONS_MODE", str(caught.exception)); self.assertIn("exited with code", str(caught.exception))
        self.assertLess(time.time() - started, 15)       # it must notice the exit, not retry a dead server for a minute or more

    def test_waiting_for_a_dead_server_stops_at_once_even_when_connections_are_slow_to_fail(self):
        import subprocess
        from unittest.mock import patch
        from test_unified_runtime import wait_for_server
        dead = subprocess.Popen([sys.executable, "-c", "import sys; print('boom', file=sys.stderr); sys.exit(3)"]); dead.wait()
        def slow_refusal(*args, **kwargs):                                       # what a refused connection can cost on some systems
            time.sleep(5); raise ConnectionRefusedError()
        started = time.time()
        with patch("urllib.request.urlopen", slow_refusal):
            with self.assertRaises(RuntimeError) as caught:
                wait_for_server(dead, 1, lambda: "boom")
        self.assertIn("exited with code 3", str(caught.exception)); self.assertLess(time.time() - started, 2)   # never even tries the slow connection


class PageIntegrityTests(unittest.TestCase):
    def test_every_page_starts_with_a_doctype(self):
        """Anything before <!DOCTYPE html> puts the browser in quirks mode and changes the layout."""
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        for page in sorted(root.glob("*.html")):
            self.assertTrue(page.read_text(encoding="utf-8").lstrip("﻿").lstrip().lower().startswith("<!doctype html"), page.name)
