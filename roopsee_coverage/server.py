from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .constants import DEFAULT_PRODUCTS_CSV, DEFAULT_SCORE_WORKBOOK, QUIZ_OPTIONS, STATIC_DIR
from .engine import RecommendationEngine
from .profiles import representative_profiles


def read_request_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    return json.loads(raw or "{}")


def send_json(handler: BaseHTTPRequestHandler, payload: Any, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def send_file(handler: BaseHTTPRequestHandler, path: Path) -> None:
    if not path.exists() or not path.is_file():
        handler.send_error(HTTPStatus.NOT_FOUND)
        return
    content_type = "text/html; charset=utf-8" if path.suffix == ".html" else "text/plain; charset=utf-8"
    body = path.read_bytes()
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def make_handler(engine: RecommendationEngine):
    class Handler(BaseHTTPRequestHandler):
        def do_OPTIONS(self) -> None:
            send_json(self, {"ok": True})

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            try:
                if parsed.path in {"/", "/index.html"}:
                    send_file(self, STATIC_DIR / "index.html")
                elif parsed.path == "/api/health":
                    send_json(self, engine.health())
                elif parsed.path == "/api/options":
                    payload = {"quiz_options": QUIZ_OPTIONS, "health": engine.health()}
                    send_json(self, payload)
                elif parsed.path == "/api/representative-profiles":
                    count = int(query.get("count", ["72"])[0])
                    send_json(self, {"profiles": representative_profiles(count)})
                elif parsed.path == "/api/coverage":
                    count = int(query.get("count", ["72"])[0])
                    top_n = int(query.get("top_n", ["5"])[0])
                    send_json(self, engine.coverage(representative_profiles(count), top_n=top_n))
                else:
                    requested = (STATIC_DIR / parsed.path.lstrip("/")).resolve()
                    if STATIC_DIR in requested.parents:
                        send_file(self, requested)
                    else:
                        self.send_error(HTTPStatus.NOT_FOUND)
            except Exception as exc:  # noqa: BLE001
                send_json(self, {"error": str(exc)}, status=500)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            try:
                body = read_request_json(self)
                if parsed.path == "/api/recommend":
                    limit = int(query.get("limit", [str(body.get("limit", 60))])[0])
                    send_json(self, engine.recommend(body, limit=limit))
                elif parsed.path == "/api/coverage":
                    profiles = body.get("profiles") or representative_profiles(int(body.get("count", 72)))
                    top_n = int(body.get("top_n", 5))
                    send_json(self, engine.coverage(profiles, top_n=top_n))
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
            except Exception as exc:  # noqa: BLE001
                send_json(self, {"error": str(exc)}, status=500)

        def log_message(self, format: str, *args: Any) -> None:
            print(f"{self.address_string()} - {format % args}")

    return Handler


def main() -> None:
    score_workbook = Path(os.getenv("SCORE_WORKBOOK_PATH", DEFAULT_SCORE_WORKBOOK)).expanduser()
    products_csv = Path(os.getenv("PRODUCTS_CSV_PATH", DEFAULT_PRODUCTS_CSV)).expanduser()
    port = int(os.getenv("PORT", "8020"))
    host = os.getenv("HOST", "127.0.0.1")

    engine = RecommendationEngine(score_workbook, products_csv)
    server = ThreadingHTTPServer((host, port), make_handler(engine))
    print(f"Roopsee product coverage service running at http://{host}:{port}")
    print(json.dumps(engine.health(), indent=2))
    server.serve_forever()
