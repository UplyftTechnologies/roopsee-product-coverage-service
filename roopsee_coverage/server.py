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
from .profiles import (
    all_profile_combinations,
    skin_concern_special_combinations,
    skin_concern_type_combinations,
    representative_profiles,
)


COVERAGE_MODES = {
    "all_pnc": {
        "label": "All PnC Combinations",
        "description": "4C1 * (2 * (8C1 + 8C2)) * (3C0 + 3C1 + 3C2 + 3C3 + None) * 4",
        "formula": "4 * 72 * 9 * 4 = 10,368",
    },
    "skin_concern_type": {
        "label": "Skin Concern Type",
        "description": "Skin type plus concern group/set; age and special conditions not selected.",
        "formula": "4 * 72 = 288",
    },
    "with_special_conditions": {
        "label": "With Special Conditions",
        "description": "Skin type plus concern group/set plus special-condition state; age not selected.",
        "formula": "4 * 72 * 9 = 2,592",
    },
    "representative": {
        "label": "Quick Representative Sample",
        "description": "Small fast sample for smoke testing only.",
        "formula": "72 sampled profiles",
    },
}


def profiles_for_mode(mode: str, count: int | None = None) -> list[dict[str, Any]]:
    if mode == "skin_concern_type":
        return skin_concern_type_combinations()
    if mode == "with_special_conditions":
        return skin_concern_special_combinations()
    if mode == "representative":
        return representative_profiles(count or 72)
    return all_profile_combinations(include_optional_age=True)


def limit_coverage_rows(payload: dict[str, Any], row_limit: int = 0) -> dict[str, Any]:
    rows = payload.get("rows") or []
    order = {"Coverage gap": 0, "Limited but usable": 1, "Usable": 2, "Strong": 3}
    sorted_rows = sorted(rows, key=lambda row: (order.get(row.get("status"), 9), row.get("profile_id", "")))
    payload["total_rows"] = len(rows)
    if row_limit > 0:
        payload["rows"] = sorted_rows[:row_limit]
        payload["returned_rows"] = len(payload["rows"])
    else:
        payload["rows"] = sorted_rows
        payload["returned_rows"] = len(sorted_rows)
    return payload


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
    content_types = {
        ".html": "text/html; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
        ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
    }
    content_type = content_types.get(path.suffix.lower(), "text/plain; charset=utf-8")
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
                    payload = {"quiz_options": QUIZ_OPTIONS, "coverage_modes": COVERAGE_MODES, "health": engine.health()}
                    send_json(self, payload)
                elif parsed.path == "/api/representative-profiles":
                    count = int(query.get("count", ["72"])[0])
                    send_json(self, {"profiles": representative_profiles(count)})
                elif parsed.path == "/api/coverage":
                    mode = query.get("mode", ["all_pnc"])[0]
                    count = int(query.get("count", ["72"])[0])
                    top_n = int(query.get("top_n", ["5"])[0])
                    row_limit = int(query.get("row_limit", ["0"])[0])
                    profiles = profiles_for_mode(mode, count=count)
                    payload = engine.coverage(profiles, top_n=top_n)
                    payload["mode"] = mode
                    payload["mode_meta"] = COVERAGE_MODES.get(mode, COVERAGE_MODES["all_pnc"])
                    payload = limit_coverage_rows(payload, row_limit=row_limit)
                    send_json(self, payload)
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
                    limit = int(query.get("limit", [str(body.get("limit", 500))])[0])
                    send_json(self, engine.recommend(body, limit=limit))
                elif parsed.path == "/api/routine":
                    limit = int(query.get("limit", [str(body.get("limit", 1000))])[0])
                    send_json(self, engine.routine(body, limit=limit))
                elif parsed.path == "/api/coverage":
                    mode = body.get("mode", "all_pnc")
                    profiles = body.get("profiles") or profiles_for_mode(mode, count=int(body.get("count", 72)))
                    top_n = int(body.get("top_n", 5))
                    row_limit = int(body.get("row_limit", 0))
                    payload = engine.coverage(profiles, top_n=top_n)
                    payload["mode"] = mode
                    payload["mode_meta"] = COVERAGE_MODES.get(mode, COVERAGE_MODES["all_pnc"])
                    payload = limit_coverage_rows(payload, row_limit=row_limit)
                    send_json(self, payload)
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
    host = os.getenv("HOST", "0.0.0.0")

    engine = RecommendationEngine(score_workbook, products_csv)
    server = ThreadingHTTPServer((host, port), make_handler(engine))
    print(f"Roopsee product coverage service running at http://{host}:{port}")
    print(json.dumps(engine.health(), indent=2))
    server.serve_forever()
