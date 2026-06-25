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


def age_column(age: str) -> str | None:
    return AGE_COLUMN_MAP.get(norm_label(age))


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


def first_available_score(row: ScoreRow, headers: list[str]) -> tuple[str, float] | None:
    for header in headers:
        if header in row.scores:
            return header, row.scores[header]
    return None


def sheet_score(value: float) -> int | float:
    return int(value) if float(value).is_integer() else value


def rounded_average_score(components: list[dict[str, Any]]) -> int:
    scores = [float(component["score"]) for component in components]
    if not scores:
        return 0
    if any(score <= -100 for score in scores):
        return -100
    average = sum(scores) / len(scores)
    if average >= 0:
        return int(average + 0.5)
    return int(average - 0.5)


def map_special_columns(row: ScoreRow, special_conditions: list[str]) -> list[tuple[str, str, float]]:
    conditions = [norm_label(item) for item in special_conditions if norm_label(item)]
    if not conditions or conditions == ["none"] or ("none" in conditions and len(conditions) == 1):
        none_value = row.scores.get("None")
        return [("None", "None", none_value)] if none_value is not None else []

    mapped: list[tuple[str, str, float]] = []
    if "pregnant" in conditions:
        matched = first_available_score(row, ["Pregnancy Score", "Pregnancy safe"])
        if matched:
            header, value = matched
            mapped.append(("Pregnancy", header, value))
    if "breastfeeding" in conditions:
        matched = first_available_score(row, ["Breastfeeling Score", "Breastfeeding safe"])
        if matched:
            header, value = matched
            mapped.append(("Breastfeeding", header, value))
    if "excessive dryness" in conditions:
        matched = first_available_score(row, ["Excessive Dryness score"])
        if not matched and row.source_sheet == LIPS_SHEET:
            matched = first_available_score(row, ["Dry Lips/Chapped Lips", "Dehydrated Lips"])
        if not matched and row.source_sheet == EYES_SHEET:
            matched = first_available_score(row, ["Dry/Dehydrated Under Eyes"])
        if matched:
            header, value = matched
            mapped.append(("Excessive Dryness", header, value))
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


def score_row_for_profile(row: ScoreRow, catalog: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    components: list[dict[str, Any]] = []
    reasons: list[str] = []
    warnings: list[str] = []

    age_header = age_column(clean_text(profile.get("age", "")))
    age_score = row.scores.get(age_header) if age_header else None
    if age_header and age_score is not None:
        components.append({"name": f"Age {age_header}", "score": sheet_score(age_score), "source_column": age_header})
        reasons.append(f"Age fit {age_header}: {age_score:g}")

    concern_pairs = concern_headers_for_row(row, profile)
    for concern, headers in concern_pairs:
        matched = first_available_score(row, headers)
        if matched:
            header, value = matched
            components.append({"name": concern, "score": sheet_score(value), "source_column": header})
            reasons.append(f"{concern} via {header}: {value:g}")
    if not concern_pairs and row.scores.get("None") is not None:
        components.append({"name": "General fit", "score": sheet_score(row.scores["None"]), "source_column": "None"})

    if row.source_sheet == FACE_SHEET:
        skin_header = skin_column(clean_text(profile.get("selectedSkinType", "Normal")), is_sensitive_profile(profile))
        skin_score = row.scores.get(skin_header)
        if skin_score is not None:
            components.append({"name": skin_header, "score": sheet_score(skin_score), "source_column": skin_header})
            reasons.append(f"{skin_header}: {skin_score:g}")

    special_pairs = map_special_columns(row, profile.get("selectedSpecialConditions", []))
    for label, source_column, value in special_pairs:
        components.append({"name": label, "score": sheet_score(value), "source_column": source_column})
        reasons.append(f"{label}: {value:g}")
        if value < 0:
            warnings.append("Safety conflict with selected pregnancy/breastfeeding condition.")

    final_score = rounded_average_score(components)
    label = label_for_score(final_score)
    hard_blockers = [component for component in components if float(component["score"]) <= -100]
    used_columns = "; ".join(
        f"{component['name']} [{component['source_column']}]: {component['score']}" for component in components[:6]
    )
    if hard_blockers:
        blocked_columns = "; ".join(
            f"{component['name']} [{component['source_column']}]: {component['score']}" for component in hard_blockers[:3]
        )
        explanation = (
            f"{label}: this product has a hard blocker for this profile, so the final score is -100. "
            f"Blocked by {blocked_columns}. "
            f"Used {used_columns or 'no matching score columns'}. "
            "Only products present in the live catalog CSV are returned."
        )
        warnings.append("Hard blocker score found for this profile.")
    else:
        explanation = (
            f"{label}: score is the rounded average of applicable doctor-sheet scores for this profile. "
            f"Used {used_columns or 'no matching score columns'}. "
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
        "component_scores": components,
        "score_basis": "hard_blocker_or_rounded_average_applicable_doctor_sheet_scores",
        "score_reasons": reasons,
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
