from __future__ import annotations

import json
import re
from typing import Any


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\u00a0", " ").split()).strip()


def norm_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", clean_text(value).lower())


def norm_label(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean_text(value).lower()).strip()


def safe_float(value: Any) -> float | None:
    if value is None or clean_text(value) == "":
        return None
    try:
        return float(str(value).replace("%", "").strip())
    except ValueError:
        return None


def first_image(raw: str) -> str:
    raw = clean_text(raw)
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list) and parsed:
            return clean_text(parsed[0])
    except json.JSONDecodeError:
        pass
    first_url_start = raw.find("http")
    if first_url_start >= 0:
        next_url_start = raw.find("http", first_url_start + 4)
        if next_url_start >= 0:
            return clean_text(raw[first_url_start:next_url_start]).rstrip(",")
    urls = re.findall(r"https?://\S+", raw)
    if urls:
        return clean_text(urls[0]).rstrip(",")
    if "," in raw:
        return clean_text(raw.split(",", 1)[0]).rstrip(",")
    return raw.rstrip(",")
