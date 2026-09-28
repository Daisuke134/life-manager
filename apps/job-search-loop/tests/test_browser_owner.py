import importlib
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/json/version":
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(
            {
                "Browser": "Chrome/140",
                "webSocketDebuggerUrl": "ws://localhost:9222/devtools/browser/abc",
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


class _EventuallyReadyHandler(_Handler):
    def do_GET(self):
        if self.path == "/json/version" and self.server.request_count == 0:
            self.server.request_count += 1
            body = b"{}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.server.request_count += 1
        super().do_GET()


class BrowserOwnerTests(unittest.TestCase):
    def test_running_cdp_is_declared_ready_for_the_existing_loop_owner(self):
        try:
            module = importlib.import_module("job_search_loop.browser_owner")
        except ModuleNotFoundError:
            self.fail("job_search_loop.browser_owner is missing")
        probe = getattr(module, "probe_cdp", None)
        self.assertIsNotNone(probe)

        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            endpoint = f"http://127.0.0.1:{server.server_port}"
            self.assertEqual(
                probe(endpoint),
                {
                    "status": "ready",
                    "owner": "ai.anicca.job-search-daily",
                    "endpoint": endpoint,
                    "browser": "Chrome/140",
                    "websocket": "ws://localhost:9222/devtools/browser/abc",
                },
            )
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

    def test_cli_waits_for_transient_cdp_startup_before_writing_evidence(self):
        module = importlib.import_module("job_search_loop.browser_owner")

        server = ThreadingHTTPServer(("127.0.0.1", 0), _EventuallyReadyHandler)
        server.request_count = 0
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            endpoint = f"http://127.0.0.1:{server.server_port}"
            with tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "browser-owner.json"
                with mock.patch.object(
                    sys,
                    "argv",
                    [
                        "browser_owner",
                        "--endpoint",
                        endpoint,
                        "--output",
                        str(output),
                    ],
                ):
                    module.main()
                self.assertEqual(json.loads(output.read_text())["status"], "ready")
            self.assertGreaterEqual(server.request_count, 2)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
