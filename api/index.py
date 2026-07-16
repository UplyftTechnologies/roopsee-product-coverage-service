from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from flask import Flask, Response, abort, jsonify, request, send_file

from roopsee_coverage.constants import DEFAULT_PRODUCTS_CSV, DEFAULT_SCORE_WORKBOOK, QUIZ_OPTIONS, STATIC_DIR
from roopsee_coverage.engine import RecommendationEngine
from roopsee_coverage.profiles import representative_profiles
from roopsee_coverage.server import COVERAGE_MODES, limit_coverage_rows, profiles_for_mode


def make_engine() -> RecommendationEngine:
    score_workbook = Path(os.getenv("SCORE_WORKBOOK_PATH", DEFAULT_SCORE_WORKBOOK)).expanduser()
    products_csv = Path(os.getenv("PRODUCTS_CSV_PATH", DEFAULT_PRODUCTS_CSV)).expanduser()
    return RecommendationEngine(score_workbook, products_csv)


app = Flask(__name__)
engine = make_engine()


def json_response(payload: Any, status: int = 200) -> Response:
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return Response(body, status=status, content_type="application/json; charset=utf-8")


@app.after_request
def add_cors_headers(response: Response) -> Response:
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.route("/", defaults={"path": ""}, methods=["GET", "POST", "OPTIONS"])
@app.route("/<path:path>", methods=["GET", "POST", "OPTIONS"])
def route(path: str) -> Response:
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    route_path = f"/{path}"
    if request.method == "GET":
        if route_path in {"/", "/index.html"}:
            return send_file(STATIC_DIR / "index.html")
        if route_path == "/api/health":
            return json_response(engine.health())
        if route_path == "/api/options":
            return json_response({
                "quiz_options": QUIZ_OPTIONS,
                "coverage_modes": COVERAGE_MODES,
                "health": engine.health(),
            })
        if route_path == "/api/representative-profiles":
            count = int(request.args.get("count", "72"))
            return json_response({"profiles": representative_profiles(count)})
        if route_path == "/api/coverage":
            mode = request.args.get("mode", "all_pnc")
            count = int(request.args.get("count", "72"))
            top_n = int(request.args.get("top_n", "5"))
            row_limit = int(request.args.get("row_limit", "0"))
            profiles = profiles_for_mode(mode, count=count)
            payload = engine.coverage(profiles, top_n=top_n)
            payload["mode"] = mode
            payload["mode_meta"] = COVERAGE_MODES.get(mode, COVERAGE_MODES["all_pnc"])
            return json_response(limit_coverage_rows(payload, row_limit=row_limit))

        requested = (STATIC_DIR / path).resolve()
        if STATIC_DIR in requested.parents and requested.is_file():
            return send_file(requested)
        abort(404)

    body = request.get_json(silent=True) or {}
    if route_path == "/api/recommend":
        limit = int(request.args.get("limit", str(body.get("limit", 500))))
        return json_response(engine.recommend(body, limit=limit))
    if route_path == "/api/routine":
        limit = int(request.args.get("limit", str(body.get("limit", 1000))))
        return json_response(engine.routine(body, limit=limit))
    if route_path == "/api/coverage":
        mode = body.get("mode", "all_pnc")
        profiles = body.get("profiles") or profiles_for_mode(mode, count=int(body.get("count", 72)))
        top_n = int(body.get("top_n", 5))
        row_limit = int(body.get("row_limit", 0))
        payload = engine.coverage(profiles, top_n=top_n)
        payload["mode"] = mode
        payload["mode_meta"] = COVERAGE_MODES.get(mode, COVERAGE_MODES["all_pnc"])
        return json_response(limit_coverage_rows(payload, row_limit=row_limit))

    abort(404)
