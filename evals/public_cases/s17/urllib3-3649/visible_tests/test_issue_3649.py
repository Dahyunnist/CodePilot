from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import urllib3


class RedirectHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/start":
            self.send_response(302)
            self.send_header("Location", "/final")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format: str, *args: object) -> None:
        pass


def test_pool_manager_integer_retries_still_follow_redirects() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    manager = urllib3.PoolManager(retries=3)
    try:
        response = manager.request("GET", f"http://127.0.0.1:{server.server_port}/start")
        assert response.status == 200
        assert response.data == b"ok"
        assert response.geturl().endswith("/final")
    finally:
        manager.clear()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
