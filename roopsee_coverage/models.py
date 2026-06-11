from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScoreRow:
    source_sheet: str
    product_uid: str
    product_name: str
    brand: str
    category: str
    product_type: str
    hero_ingredient: str
    secondary_ingredients: str
    scores: dict[str, float]
    source_row: int
