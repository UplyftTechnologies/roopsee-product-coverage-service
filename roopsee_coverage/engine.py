from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import THRESHOLDS
from .loaders import load_score_rows, parse_catalog
from .profile_rules import sanitize_profile
from .scoring import normalized_product_type, score_row_for_profile, summarize_results, target_sheets, threshold_counts
from .utils import norm_key

ROUTINE_SLOTS = {
    "am": [
        {"key": "cleanser", "label": "Cleanser", "aliases": {"cleanser", "wash"}},
        {"key": "moisturiser", "label": "Moisturiser", "aliases": {"moisturiser", "moisturizer"}},
        {"key": "sunscreen", "label": "Sunscreen", "aliases": {"sunscreen"}},
    ],
    "pm": [
        {"key": "serum", "label": "Serum", "aliases": {"serum"}},
        {"key": "moisturiser", "label": "Moisturiser", "aliases": {"moisturiser", "moisturizer"}},
        {"key": "cleanser", "label": "Cleanser", "aliases": {"cleanser", "wash"}},
    ],
}

WEEKLY_MASK_COUNT = 2

ROUTINE_TIERS = {
    "premium": {
        "label": "Premium",
        "description": "Score 90+ and effective price above Rs. 1000.",
        "min_score": 90,
        "min_price": 1000,
        "max_price": None,
    },
    "value_fit": {
        "label": "Value Fit",
        "description": "Best score with effective price below Rs. 1000.",
        "min_score": None,
        "min_price": None,
        "max_price": 1000,
    },
}


def normalize_product_type(product_type: str) -> str:
    return " ".join(str(product_type or "").strip().lower().split())


def product_search_text(product: dict[str, Any]) -> str:
    return " ".join(
        str(product.get(field, ""))
        for field in [
            "product_name",
            "product_type",
            "hero_ingredient",
            "single_hero_ingredient",
            "secondary_hero_ingredients",
            "ingredients",
        ]
    ).lower()


def price_amount(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    cleaned = "".join(char for char in text if char.isdigit() or char == ".")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def effective_price(product: dict[str, Any]) -> float | None:
    return price_amount(product.get("selling_price")) or price_amount(product.get("mrp"))


def matches_routine_slot(product: dict[str, Any], slot: dict[str, Any]) -> bool:
    product_type = normalize_product_type(product.get("product_type", ""))
    normalized = normalized_product_type(product_type)
    text = product_search_text(product)
    key = slot["key"]
    if key == "cleanser":
        return normalized == "cleanser"
    if key == "serum":
        return normalized == "serum"
    if key == "moisturiser":
        return normalized == "moisturizer" or product_type in {"body lotion", "body cream"}
    if key == "sunscreen":
        return normalized == "sunscreen" or "sunscreen" in text or "spf" in text
    return product_type in slot["aliases"]


def is_mask_product(product: dict[str, Any]) -> bool:
    product_type = normalize_product_type(product.get("product_type", ""))
    text = product_search_text(product)
    return "mask" in product_type or "masque" in product_type or "mask" in text or "masque" in text


def matches_routine_tier(product: dict[str, Any], tier: dict[str, Any]) -> bool:
    price = effective_price(product)
    if price is None:
        return False
    min_score = tier.get("min_score")
    min_price = tier.get("min_price")
    max_price = tier.get("max_price")
    if min_score is not None and product["score"] < min_score:
        return False
    if min_price is not None and price <= min_price:
        return False
    if max_price is not None and price >= max_price:
        return False
    return True


def select_routine_product(products: list[dict[str, Any]], slot: dict[str, Any], tier: dict[str, Any]) -> dict[str, Any] | None:
    for product in products:
        if matches_routine_slot(product, slot) and matches_routine_tier(product, tier):
            return product
    return None


def select_best_mask_products(products: list[dict[str, Any]], count: int = WEEKLY_MASK_COUNT) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_uids: set[str] = set()
    for product in products:
        uid = norm_key(product.get("product_uid") or product.get("product_name"))
        if uid in seen_uids or not is_mask_product(product):
            continue
        selected.append(product)
        seen_uids.add(uid)
        if len(selected) >= count:
            break
    return selected


def build_routine(products: list[dict[str, Any]]) -> dict[str, Any]:
    routine: dict[str, Any] = {
        "tiers": {},
        "missing_slots": [],
        "selection_basis": "highest_scored_product_per_routine_slot_from_current_profile_results_with_price_tiers_and_top_two_weekly_masks",
    }
    for tier_key, tier in ROUTINE_TIERS.items():
        tier_payload: dict[str, Any] = {
            "label": tier["label"],
            "description": tier["description"],
            "am": [],
            "pm": [],
        }
        for period, slots in ROUTINE_SLOTS.items():
            for slot in slots:
                product = select_routine_product(products, slot, tier)
                item = {
                    "tier": tier_key,
                    "period": period,
                    "slot": slot["key"],
                    "label": slot["label"],
                    "product": product,
                }
                tier_payload[period].append(item)
                if product is None:
                    routine["missing_slots"].append({
                        "tier": tier_key,
                        "period": period,
                        "slot": slot["key"],
                        "label": slot["label"],
                    })
        routine["tiers"][tier_key] = tier_payload

    routine["weekly"] = []
    weekly_products = select_best_mask_products(products)
    for index in range(WEEKLY_MASK_COUNT):
        product = weekly_products[index] if index < len(weekly_products) else None
        slot_key = f"mask_{index + 1}"
        label = f"Best Mask {index + 1}"
        item = {
            "period": "weekly",
            "slot": slot_key,
            "label": label,
            "product": product,
        }
        routine["weekly"].append(item)
        if product is None:
            routine["missing_slots"].append({"period": "weekly", "slot": slot_key, "label": label})

    routine["am"] = routine["tiers"].get("premium", {}).get("am", [])
    routine["pm"] = routine["tiers"].get("premium", {}).get("pm", [])
    return routine


class RecommendationEngine:
    def __init__(self, score_workbook: Path, products_csv: Path):
        self.score_workbook = score_workbook
        self.products_csv = products_csv
        self.catalog = parse_catalog(products_csv)
        self.score_rows = load_score_rows(score_workbook, products_csv)

        self.score_rows_by_catalog_key: dict[str, list[Any]] = {}
        self.score_only_uids: list[str] = []
        for row in self.score_rows:
            key = norm_key(row.product_uid)
            if key in self.catalog:
                self.score_rows_by_catalog_key.setdefault(key, []).append(row)
            else:
                self.score_only_uids.append(row.product_uid)

        self.catalog_missing_score = [
            product["product_uid"]
            for key, product in self.catalog.items()
            if key not in self.score_rows_by_catalog_key
        ]

    def recommend(self, profile: dict[str, Any], limit: int = 500) -> dict[str, Any]:
        scoring_profile, profile_adjustments = sanitize_profile(profile)
        wanted_sheets = target_sheets(scoring_profile)
        best_by_uid: dict[str, dict[str, Any]] = {}
        for key, rows in self.score_rows_by_catalog_key.items():
            catalog = self.catalog[key]
            for row in rows:
                if row.source_sheet not in wanted_sheets:
                    continue
                scored = score_row_for_profile(row, catalog, scoring_profile)
                if profile_adjustments:
                    scored["warnings"] = profile_adjustments + scored["warnings"]
                existing = best_by_uid.get(catalog["product_uid"])
                if existing is None or scored["score"] > existing["score"]:
                    best_by_uid[catalog["product_uid"]] = scored

        sorted_results = sorted(
            best_by_uid.values(),
            key=lambda item: (-item["score"], item["category"], item["product_name"].lower()),
        )
        results = sorted_results[: max(1, min(limit, 1000))]
        return {
            "profile": scoring_profile,
            "input_profile": profile,
            "profile_adjustments": profile_adjustments,
            "target_sheets": sorted(wanted_sheets),
            "total_matches": len(best_by_uid),
            "returned": len(results),
            "summary": summarize_results(results),
            "routine": build_routine(sorted_results),
            "products": results,
        }

    def routine(self, profile: dict[str, Any], limit: int = 1000) -> dict[str, Any]:
        response = self.recommend(profile, limit=limit)
        return {
            "profile": response["profile"],
            "input_profile": response["input_profile"],
            "profile_adjustments": response["profile_adjustments"],
            "target_sheets": response["target_sheets"],
            "total_matches": response["total_matches"],
            "returned": response["returned"],
            "routine": response["routine"],
        }

    def health(self) -> dict[str, Any]:
        by_sheet: dict[str, int] = {}
        for row in self.score_rows:
            by_sheet[row.source_sheet] = by_sheet.get(row.source_sheet, 0) + 1
        return {
            "score_workbook": str(self.score_workbook),
            "products_csv": str(self.products_csv),
            "catalog_products": len(self.catalog),
            "score_rows": len(self.score_rows),
            "score_rows_by_sheet": by_sheet,
            "catalog_missing_score_count": len(self.catalog_missing_score),
            "catalog_missing_score": self.catalog_missing_score,
            "score_only_count": len(self.score_only_uids),
            "score_only_uids": self.score_only_uids,
        }

    def coverage(self, profiles: list[dict[str, Any]], top_n: int = 12) -> dict[str, Any]:
        rows = self.coverage_rows(profiles, top_n=top_n)
        status_counts: dict[str, int] = {}
        for row in rows:
            status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1

        return {
            "profile_count": len(rows),
            "status_counts": status_counts,
            "catalog_products": len(self.catalog),
            "catalog_missing_score_count": len(self.catalog_missing_score),
            "rows": rows,
        }

    def coverage_rows(self, profiles: list[dict[str, Any]], top_n: int = 0) -> list[dict[str, Any]]:
        rows = []
        for index, profile in enumerate(profiles, start=1):
            response = self.recommend(profile, limit=1000)
            summary = response["summary"]
            counts = threshold_counts(response["products"], THRESHOLDS)
            status = coverage_status(response["profile"], summary)
            rows.append({
                "profile_id": f"profile_{index:03d}",
                "profile": profile,
                "scoring_profile": response["profile"],
                "status": status,
                "total_matches": response["total_matches"],
                "excellent_count": summary["excellent_count"],
                "great_or_better_count": summary["great_or_better_count"],
                "good_or_better_count": summary["good_or_better_count"],
                "threshold_counts": counts,
                "above_90": counts["above_90"],
                "above_80": counts["above_80"],
                "above_70": counts["above_70"],
                "above_60": counts["above_60"],
                "above_50": counts["above_50"],
                "top_products": response["products"][:top_n],
                "target_sheets": response["target_sheets"],
            })
        return rows


def coverage_status(profile: dict[str, Any], summary: dict[str, Any]) -> str:
    lips_eye_only = bool(profile.get("selectedLipsEyesConcerns")) and not bool(profile.get("selectedFaceBodyConcerns"))
    if lips_eye_only:
        if summary["good_or_better_count"] >= 4 and summary["great_or_better_count"] >= 2:
            return "Strong"
        if summary["good_or_better_count"] >= 2:
            return "Limited but usable"
        return "Coverage gap"

    if summary["good_or_better_count"] >= 12 and summary["great_or_better_count"] >= 5:
        return "Strong"
    if summary["good_or_better_count"] >= 8 and summary["great_or_better_count"] >= 3:
        return "Usable"
    return "Coverage gap"
