import functools
import subprocess
import unittest


@functools.lru_cache(maxsize=1)
def bash_works():
    """True only when `bash` really runs. On Windows `bash` can be a launcher for WSL with no distribution installed."""
    try:
        return subprocess.run(["bash", "-c", "exit 0"], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


needs_bash = unittest.skipUnless(bash_works(), "a working bash is not available here (the deploy scripts target Linux)")


def remove_temp(temp):
    """Delete a TemporaryDirectory after a test. Windows will not delete a file another handle still has open, and a handle
    can outlive the code that opened it until the garbage collector runs, so collect first and allow a short, bounded wait.
    A file that is still locked after that raises with its name: a real leak is reported, never hidden."""
    import gc
    import time
    for attempt in range(10):
        gc.collect()
        try:
            temp.cleanup()
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.3)


class FakeOllama:
    """A stand-in Ollama that answers /api/tags with the given installed models. Use as a context manager; .url is its address."""
    def __init__(self, models):
        import http.server
        import threading
        names = list(models)

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                import json
                body = json.dumps({"models": [{"name": name} for name in names]}).encode()
                self.send_response(200 if self.path == "/api/tags" else 404)
                self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start(); return self

    def __exit__(self, *exc):
        self.httpd.shutdown(); self.httpd.server_close()
