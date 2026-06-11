from __future__ import annotations

from typing import Any

from .constants import (
    AGE_COLUMN_MAP,
    EYE_CONCERN_MAP,
    EYES_SHEET,
    FACE_CONCERN_MAP,
    FACE_SHEET,
    LIP_CONCERN_MAP,
    LIPS_SHEET,
    SCORE_LABELS,
    THRESHOLDS,
)
from .models import ScoreRow
from .utils import clean_text, norm_label


def age_column(age: str) -> str:
    return AGE_COLUMN_MAP.get(norm_label(age), "+>25")


def is_sensitive_profile(profile: dict[str, Any]) -> bool:
    face_concerns = [norm_label(item) for item in profile.get("selectedFaceBodyConcerns", [])]
    lips_eye = [norm_label(item) for item in profile.get("selectedLipsEyesConcerns", [])]
    return any(item in {"sensitivity", "sensitive eye", "sensitive eyes"} for item in face_concerns + lips_eye)


def skin_column(skin_type: str, sensitive: bool) -> str:
    base = clean_text(skin_type).title()
    if base not in {"Oily", "Dry", "Normal", "Combination"}:
        base = "Normal"
    return f"{base}+Sensitive Score" if sensitive else f"{base} Score"


def available_scores(row: ScoreRow, headers: list[str]) -> list[float]:
    return [row.scores[header] for header in headers if header in row.scores]


def map_special_columns(row: ScoreRow, special_conditions: list[str]) -> list[tuple[str, float]]:
    conditions = [norm_label(item) for item in special_conditions if norm_label(item)]
    if not conditions or conditions == ["none"] or ("none" in conditions and len(conditions) == 1):
        none_value = row.scores.get("None")
        return [("None", none_value)] if none_value is not None else []

    mapped: list[tuple[str, float]] = []
    if "pregnant" in conditions:
        value = row.scores.get("Pregnancy Score", row.scores.get("Pregnancy safe"))
        if value is not None:
            mapped.append(("Pregnancy", value))
    if "breastfeeding" in conditions:
        value = row.scores.get("Breastfeeling Score", row.scores.get("Breastfeeding safe"))
        if value is not None:
            mapped.append(("Breastfeeding", value))
    if "excessive dryness" in conditions:
        value = row.scores.get("Excessive Dryness score")
        if value is None and row.source_sheet == LIPS_SHEET:
            dry_values = available_scores(row, ["Dry Lips/Chapped Lips", "Dehydrated Lips"])
            value = max(dry_values) if dry_values else None
        if value is None and row.source_sheet == EYES_SHEET:
            dry_values = available_scores(row, ["Dry/Dehydrated Under Eyes"])
            value = max(dry_values) if dry_values else None
        if value is not None:
            mapped.append(("Excessive Dryness", value))
    return mapped


def concern_headers_for_row(row: ScoreRow, profile: dict[str, Any]) -> list[tuple[str, list[str]]]:
    mapped: list[tuple[str, list[str]]] = []
    if row.source_sheet == FACE_SHEET:
        for concern in profile.get("selectedFaceBodyConcerns", []):
            headers = FACE_CONCERN_MAP.get(norm_label(concern), [clean_text(concern)])
            mapped.append((clean_text(concern), headers))
    elif row.source_sheet == LIPS_SHEET:
        for concern in profile.get("selectedLipsEyesConcerns", []):
            headers = LIP_CONCERN_MAP.get(norm_label(concern))
            if headers:
                mapped.append((clean_text(concern), headers))
    elif row.source_sheet == EYES_SHEET:
        for concern in profile.get("selectedLipsEyesConcerns", []):
            headers = EYE_CONCERN_MAP.get(norm_label(concern))
            if headers:
                mapped.append((clean_text(concern), headers))
    return mapped


def target_sheets(profile: dict[str, Any]) -> set[str]:
    sheets: set[str] = set()
    if profile.get("selectedFaceBodyConcerns"):
        sheets.add(FACE_SHEET)
    for concern in profile.get("selectedLipsEyesConcerns", []):
        key = norm_label(concern)
        if key in LIP_CONCERN_MAP:
            sheets.add(LIPS_SHEET)
        if key in EYE_CONCERN_MAP:
            sheets.add(EYES_SHEET)
    if not sheets:
        sheets.add(FACE_SHEET)
    return sheets


def label_for_score(score: float) -> str:
    for threshold, label in SCORE_LABELS:
        if score >= threshold:
            return label
    return "Not Recommended"


def weighted_average(components: list[tuple[str, float, float]]) -> float:
    total_weight = sum(weight for _, _, weight in components if weight > 0)
    if total_weight <= 0:
        return 0.0
    return sum(value * weight for _, value, weight in components if weight > 0) / total_weight


def score_row_for_profile(row: ScoreRow, catalog: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    components: list[tuple[str, float, float]] = []
    reasons: list[str] = []
    warnings: list[str] = []

    age_header = age_column(clean_text(profile.get("age", "")))
    age_score = row.scores.get(age_header)
    if age_score is not None:
        components.append((f"Age {age_header}", age_score, 0.10 if row.source_sheet == FACE_SHEET else 0.15))
        reasons.append(f"Age fit {age_header}: {age_score:g}")

    concern_pairs = concern_headers_for_row(row, profile)
    concern_scores: list[float] = []
    for concern, headers in concern_pairs:
        values = available_scores(row, headers)
        if values:
            best_value = max(values)
            concern_scores.append(best_value)
            reasons.append(f"{concern}: {best_value:g}")
    if concern_scores:
        concern_weight = 0.45 if row.source_sheet == FACE_SHEET else 0.60
        components.append(("Concern fit", sum(concern_scores) / len(concern_scores), concern_weight))
    elif row.scores.get("None") is not None:
        components.append(("General fit", row.scores["None"], 0.25))

    if row.source_sheet == FACE_SHEET:
        skin_header = skin_column(clean_text(profile.get("selectedSkinType", "Normal")), is_sensitive_profile(profile))
        skin_score = row.scores.get(skin_header)
        if skin_score is not None:
            components.append((skin_header, skin_score, 0.30))
            reasons.append(f"{skin_header}: {skin_score:g}")

    special_pairs = map_special_columns(row, profile.get("selectedSpecialConditions", []))
    special_values = [value for _, value in special_pairs]
    if special_values:
        special_score = min(special_values) if any(value < 0 for value in special_values) else sum(special_values) / len(special_values)
        components.append(("Special conditions", special_score, 0.15 if row.source_sheet == FACE_SHEET else 0.25))
        for label, value in special_pairs:
            reasons.append(f"{label}: {value:g}")
        if any(value < 0 for value in special_values):
            warnings.append("Safety conflict with selected pregnancy/breastfeeding condition.")

    raw_score = weighted_average(components)
    if any(value < 0 for value in special_values):
        raw_score = min(raw_score, 30)

    final_score = max(0, min(100, round(raw_score, 1)))
    label = label_for_score(final_score)
    explanation = (
        f"{label}: ranked from doctor-sheet scores for "
        f"{', '.join(reason for reason in reasons[:5])}. "
        "Only products present in the live catalog CSV are returned."
    )
    if warnings:
        explanation = f"{warnings[0]} {explanation}"

    return {
        "product_uid": catalog["product_uid"],
        "score_uid": row.product_uid,
        "product_name": catalog["product_name"] or row.product_name,
        "brand_name": catalog["brand_name"] or row.brand,
        "category": catalog["category"] or row.category,
        "product_type": catalog["product_type"] or row.product_type,
        "score": final_score,
        "match_label": label,
        "explanation": explanation,
        "source_sheet": row.source_sheet,
        "hero_ingredient": catalog["single_hero_ingredient"] or row.hero_ingredient,
        "secondary_hero_ingredients": catalog["secondary_hero_ingredients"] or row.secondary_ingredients,
        "size": catalog["sku_size"],
        "mrp": catalog["mrp"],
        "selling_price": catalog["sp"],
        "when_to_use": catalog["when_to_use"],
        "image": catalog["image"],
        "component_scores": [{"name": name, "score": round(value, 1), "weight": weight} for name, value, weight in components],
        "warnings": warnings,
    }


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    categories: dict[str, int] = {}
    product_types: dict[str, int] = {}
    for item in results:
        categories[item["category"]] = categories.get(item["category"], 0) + 1
        product_types[item["product_type"]] = product_types.get(item["product_type"], 0) + 1
    return {
        "excellent_count": sum(1 for item in results if item["score"] >= 90),
        "great_or_better_count": sum(1 for item in results if item["score"] >= 80),
        "good_or_better_count": sum(1 for item in results if item["score"] >= 70),
        "caution_or_better_count": sum(1 for item in results if item["score"] >= 50),
        "threshold_counts": threshold_counts(results),
        "categories": categories,
        "product_types": product_types,
        "top_score": results[0]["score"] if results else None,
        "bottom_score": results[-1]["score"] if results else None,
    }


def threshold_counts(results: list[dict[str, Any]], thresholds: list[int] | None = None) -> dict[str, int]:
    thresholds = thresholds or THRESHOLDS
    return {f"above_{threshold}": sum(1 for item in results if item["score"] >= threshold) for threshold in thresholds}
