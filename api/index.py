from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flask import Flask, Response, abort, send_file


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "static"
DATASET_PATH = STATIC_DIR / "data" / "final_scored_products.json"

app = Flask(__name__, static_folder=None)


def json_response(payload: Any, status: int = 200) -> Response:
    body = json.dumps(payload, ensure_ascii=False)
    return Response(body, status=status, content_type="application/json; charset=utf-8")


@app.after_request
def add_headers(response: Response) -> Response:
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers.setdefault("Cache-Control", "public, max-age=300")
    return response


@app.get("/api/health")
def health() -> Response:
    return json_response(
        {
            "ok": True,
            "service": "roopsee-final-match-platform",
            "dataset": "static/data/final_scored_products.json",
            "dataset_exists": DATASET_PATH.exists(),
        }
    )


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path: str) -> Response:
    if not path:
        return send_file(STATIC_DIR / "index.html")

    requested = (STATIC_DIR / path).resolve()
    if STATIC_DIR in requested.parents and requested.is_file():
        return send_file(requested)

    if "." not in Path(path).name:
        return send_file(STATIC_DIR / "index.html")

    abort(404)
