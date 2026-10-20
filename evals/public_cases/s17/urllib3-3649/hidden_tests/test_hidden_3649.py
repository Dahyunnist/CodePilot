from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import urllib3
from urllib3.util import Retry


class RedirectHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/one":
            self.send_response(301)
            self.send_header("Location", "/two")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", "5")
        self.end_headers()
        self.wfile.write(b"final")

    def log_message(self, format: str, *args: object) -> None:
        pass


def test_retry_instance_still_follows_redirects() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    manager = urllib3.PoolManager(retries=Retry(total=2))
    try:
        response = manager.request("GET", f"http://127.0.0.1:{server.server_port}/one")
        assert response.status == 200
        assert response.data == b"final"
    finally:
        manager.clear()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
