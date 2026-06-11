from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import THRESHOLDS
from .loaders import load_score_rows, parse_catalog
from .profile_rules import sanitize_profile
from .scoring import score_row_for_profile, summarize_results, target_sheets, threshold_counts
from .utils import norm_key


class RecommendationEngine:
    def __init__(self, score_workbook: Path, products_csv: Path):
        self.score_workbook = score_workbook
        self.products_csv = products_csv
        self.catalog = parse_catalog(products_csv)
        self.score_rows = load_score_rows(score_workbook)

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

    def recommend(self, profile: dict[str, Any], limit: int = 60) -> dict[str, Any]:
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

        results = sorted(
            best_by_uid.values(),
            key=lambda item: (-item["score"], item["category"], item["product_name"].lower()),
        )
        results = results[: max(1, min(limit, 250))]
        return {
            "profile": scoring_profile,
            "input_profile": profile,
            "profile_adjustments": profile_adjustments,
            "target_sheets": sorted(wanted_sheets),
            "total_matches": len(best_by_uid),
            "returned": len(results),
            "summary": summarize_results(results),
            "products": results,
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
            response = self.recommend(profile, limit=250)
            summary = response["summary"]
            counts = threshold_counts(response["products"], THRESHOLDS)
            status = coverage_status(profile, summary)
            rows.append({
                "profile_id": f"profile_{index:03d}",
                "profile": profile,
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
