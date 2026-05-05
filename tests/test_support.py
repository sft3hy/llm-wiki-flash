from __future__ import annotations

import json
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit


BACKEND_PATH = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))


@contextmanager
def serve_test_app(router):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            response = router(parsed.path, parse_qs(parsed.query))
            status = response.status
            body = response.body.encode("utf-8")
            self.send_response(status)
            for key, value in response.headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def make_response(status: int, body: str, headers: dict[str, str] | None = None) -> SimpleNamespace:
    merged_headers = {"Content-Type": "text/plain; charset=utf-8"}
    if headers:
        merged_headers.update(headers)
    return SimpleNamespace(status=status, body=body, headers=merged_headers)


def make_json_response(payload: dict) -> SimpleNamespace:
    return make_response(
        200,
        json.dumps(payload),
        {"Content-Type": "application/json; charset=utf-8"},
    )
