from __future__ import annotations

import csv
import difflib
import importlib.util
import json
import math
import os
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


def env_path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default))).expanduser()


COVERAGE_REPO = env_path("ROOPSEE_COVERAGE_REPO", REPO_ROOT)
AUTO_SCORER_PATH = env_path("ROOPSEE_AUTO_SCORER_PATH", REPO_ROOT / "tools" / "build_automated_scores.py")
PRODUCTS_CSV = COVERAGE_REPO / "data" / "products.csv"
OUTPUT_DIR = env_path("ROOPSEE_AUTO_OUTPUT_DIR", REPO_ROOT / "outputs" / "roopsee_automated_scoring")
OUTPUT_SUMMARY = OUTPUT_DIR / "v2_leave_one_out_validation_summary.json"
OUTPUT_PRODUCTS = OUTPUT_DIR / "v2_leave_one_out_product_summary.csv"
OUTPUT_DETAIL = OUTPUT_DIR / "v2_leave_one_out_score_detail.csv"

sys.path.insert(0, str(COVERAGE_REPO))

from roopsee_coverage.constants import FACE_SHEET, QUIZ_OPTIONS  # noqa: E402
from roopsee_coverage.loaders import parse_catalog, parse_catalog_score_rows  # noqa: E402
from roopsee_coverage.models import ScoreRow  # noqa: E402
from roopsee_coverage.scoring import score_row_for_profile  # noqa: E402
from roopsee_coverage.utils import clean_text, norm_label, norm_key, safe_float  # noqa: E402


SCORE_PAIRS = [
    ("<16", "<16", "<16"),
    ("17-25", "17-25", "17-25"),
    ("Above 25", "+>25", "Above 25"),
    ("Acne", "Acne", "Acne"),
    ("Body Acne", "Body Acne", "Body Acne"),
    ("Dryness", "Dryness", "Dryness"),
    ("Open Pores", "Open Pores", "Open Pores"),
    ("Uneven Skin Tone", "Uneven Skin Tone", "Uneven Skin Tone"),
    ("Dark Spots/Pigmentation", "Dark Spots/Pigmentation", "Dark Spots/Pigmentation"),
    ("Melasma", "Melasma", "Melasma"),
    ("Barrier Repair", "Barrier Repair", "Barrier Repair"),
    ("Comedones", "Comedones", "Comedones"),
    ("Wrinkles/Fine lines", "Wrinkles/Fine lines", "Wrinkles/Fine lines"),
    ("Redness/Irritation", "Redness/Irritation", "Redness/Irritation"),
    ("Dehydration", "Dehydration", "Dehydration"),
    ("Dullness", "Dullness", "Dullness"),
    ("Tanning", "Tanning", "Tanning"),
    ("Oily Score", "Oily Score", "Oily Score"),
    ("Oily+Sensitive Score", "Oily+Sensitive Score", "Oily+Sensitive Score"),
    ("Dry Score", "Dry Score", "Dry Score"),
    ("Dry+Sensitive Score", "Dry+Sensitive Score", "Dry+Sensitive Score"),
    ("Normal Score", "Normal Score", "Normal Score"),
    ("Normal+Sensitive Score", "Normal+Sensitive Score", "Normal+Sensitive Score"),
    ("Combination Score", "Combination Score", "Combination Score"),
    ("Combination+Sensitive Score", "Combination+Sensitive Score", "Combination+Sensitive Score"),
    ("Excessive Dryness score", "Excessive Dryness score", "Excessive Dryness score"),
    ("Pregnancy Score", "Pregnancy Score", "Pregnancy Score"),
    ("Breastfeeling Score", "Breastfeeling Score", "Breastfeeling Score"),
]
DOCTOR_TO_INTERNAL = {doctor: internal for doctor, internal, _ in SCORE_PAIRS}
INTERNAL_TO_LABEL = {internal: label for _, internal, label in SCORE_PAIRS}
INTERNAL_SCORE_COLUMNS = [internal for _, internal, _ in SCORE_PAIRS]

SKIN_COLUMNS = [
    "Oily Score",
    "Oily+Sensitive Score",
    "Dry Score",
    "Dry+Sensitive Score",
    "Normal Score",
    "Normal+Sensitive Score",
    "Combination Score",
    "Combination+Sensitive Score",
]

PHOTO_CONCERNS = {"Tanning", "Dark Spots/Pigmentation", "Melasma", "Uneven Skin Tone"}
HYDRATION_CONCERNS = {"Dryness", "Dehydration", "Barrier Repair", "Redness/Irritation", "Dullness"}
ACNE_CONCERNS = {"Acne", "Body Acne", "Open Pores", "Comedones"}
WRINKLE_CONCERNS = {"Wrinkles/Fine lines"}

FAMILY_KEYWORDS: dict[str, list[str]] = {
    "acne": ["salicylic", "bha", "benzoyl", "zinc", "tea tree", "sulfur", "sulphur", "azelaic", "blemish", "matmarine"],
    "exfoliant": ["glycolic", "lactic", "mandelic", "gluconic", "lactobionic", "aha", "bha", "pha", "exfoliat", "papain", "enzyme"],
    "brightening": ["vitamin c", "ascorbic", "niacinamide", "arbutin", "kojic", "tranexamic", "licorice", "liquorice", "glutathione", "mulberry", "saffron", "kesar", "orange peel", "orange powder", "orange fruit", "lemon peel"],
    "retinoid": ["retinol", "retinal", "retinoid", "retinyl", "tretinoin", "adapalene"],
    "anti_aging": ["peptide", "collagen", "coenzyme", "q10", "ubiquinone", "bakuchiol"],
    "hydration": ["hyaluronic", "glycerin", "glycerine", "panthenol", "beta glucan", "glyceryl glucoside", "aquaporin", "sodium pca", "trehalose", "urea"],
    "barrier": ["ceramide", "cholesterol", "fatty acid", "squalane", "shea", "kokum", "oat", "omega"],
    "soothing": ["centella", "cica", "madecassoside", "aloe", "allantoin", "green tea", "chamomile", "oat", "heartleaf", "calendula"],
    "sunscreen": ["spf", "uv filter", "zinc oxide", "titanium dioxide", "avobenzone", "octocrylene", "uvinul", "tinosorb", "octinoxate", "sunscreen"],
    "emollient": ["petrolatum", "mineral oil", "dimethicone", "silicone", "oil", "butter", "wax", "lanolin", "emollient"],
    "fragrance_risk": ["fragrance", "parfum", "essential oil", "menthol", "lavender oil", "citrus oil", "orange peel oil", "lemon peel oil", "bergamot oil", "eucalyptus"],
    "clay": ["clay", "kaolin", "bentonite", "charcoal", "multani"],
}

CONCERN_FAMILIES: dict[str, set[str]] = {
    "Acne": {"acne", "exfoliant", "clay"},
    "Body Acne": {"acne", "exfoliant", "clay"},
    "Dryness": {"hydration", "barrier", "soothing", "emollient"},
    "Open Pores": {"acne", "exfoliant", "clay"},
    "Uneven Skin Tone": {"brightening", "exfoliant", "sunscreen", "retinoid"},
    "Dark Spots/Pigmentation": {"brightening", "exfoliant", "sunscreen", "retinoid"},
    "Melasma": {"brightening", "sunscreen"},
    "Barrier Repair": {"barrier", "hydration", "soothing", "emollient"},
    "Comedones": {"acne", "exfoliant", "clay"},
    "Wrinkles/Fine lines": {"retinoid", "anti_aging", "exfoliant", "sunscreen"},
    "Redness/Irritation": {"soothing", "barrier", "hydration"},
    "Dehydration": {"hydration", "barrier", "soothing"},
    "Dullness": {"brightening", "hydration", "exfoliant", "sunscreen"},
    "Tanning": {"sunscreen", "brightening"},
}

RISKY_FALSE_MATCH_CANONICAL = {
    "acid capric triglyceride",
    "cananga odorata oil extract",
    "botanical oils",
}


@dataclass
class ProductRecord:
    uid: str
    row: dict[str, Any]
    catalog: dict[str, Any]
    doctor_scores: dict[str, float]
    baseline_scores: dict[str, float]
    v2_scores: dict[str, float]
    exact_keys: set[str]
    family_keys: set[str]
    primary_family_keys: set[str]
    product_type: str
    category: str
    ingredient_match_status: str
    created_fallback_count: int
    weak_match_count: int
    confidence: str
    review_flags: list[str]


def load_auto_scorer() -> Any:
    spec = importlib.util.spec_from_file_location("roopsee_build_automated_scores", AUTO_SCORER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load automated scorer from {AUTO_SCORER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def score_value(value: float) -> int:
    if value >= 0:
        return int(value + 0.5)
    return int(value - 0.5)


def average(values: list[float]) -> float | None:
    valid = [float(value) for value in values if value is not None and not math.isnan(float(value))]
    if not valid:
        return None
    return sum(valid) / len(valid)


def rounded_average(values: list[float]) -> int | None:
    value = average(values)
    return None if value is None else score_value(value)


def safe_pct(count: int, total: int) -> float:
    return round((count / total * 100), 2) if total else 0.0


def score_bucket(score: float) -> str:
    if score <= -100:
        return "hard_block"
    if score < 50:
        return "weak"
    if score < 70:
        return "limited"
    if score < 80:
        return "good"
    if score < 90:
        return "great"
    return "excellent"


def normalized_product_type(value: str) -> str:
    product_type = norm_label(value)
    if product_type in {"moisturizer", "moisturiser", "cream", "lotion", "body lotion", "balm"}:
        return "moisturizer"
    if product_type in {"cleanser", "wash", "body wash", "face wash"}:
        return "cleanser"
    if product_type in {"sunscreen", "sun screen", "spf"}:
        return "sunscreen"
    if product_type in {"mask", "sheet mask", "face mask", "clay mask"}:
        return "mask"
    if product_type in {"serum", "treatment", "body treatment", "ampoule"}:
        return "serum"
    if product_type == "toner":
        return "toner"
    return product_type or "other"


def classify_families(text: str) -> set[str]:
    normalized = norm_label(text)
    families: set[str] = set()
    for family, keywords in FAMILY_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            families.add(family)
    return families


def risky_match(match: dict[str, Any]) -> bool:
    method = clean_text(match.get("match_method"))
    canonical_key = norm_label(match.get("canonical_ingredient"))
    if method == "Created fallback":
        return True
    if method == "Token subset relation" and canonical_key in RISKY_FALSE_MATCH_CANONICAL:
        return True
    if method == "Token subset relation" and float(match.get("confidence") or 0) < 0.9:
        return True
    return False


def explicit_hardblock_allowed(record: ProductRecord, column: str) -> bool:
    families = record.family_keys
    if column in {"Pregnancy Score", "Breastfeeling Score"}:
        return "retinoid" in families
    if column == "<16":
        return bool({"retinoid", "exfoliant"} & families)
    if column == "Excessive Dryness score":
        return bool({"retinoid", "exfoliant", "acne", "fragrance_risk"} & families)
    sensitive_columns = {
        "Oily+Sensitive Score",
        "Dry+Sensitive Score",
        "Normal+Sensitive Score",
        "Combination+Sensitive Score",
        "Redness/Irritation",
        "Barrier Repair",
    }
    if column in sensitive_columns:
        return "fragrance_risk" in families
    return False


def soften_weak_hardblock(record: ProductRecord, column: str, base_score: float, fallback_score: float) -> float:
    if base_score > -100:
        return base_score
    if explicit_hardblock_allowed(record, column):
        return base_score
    if record.weak_match_count or record.created_fallback_count:
        return max(min(fallback_score, 70), 40)
    return base_score


def shrink(value: float | None, support: int, fallback: float, strength: int = 5) -> float | None:
    if value is None or support <= 0:
        return None
    return ((value * support) + (fallback * strength)) / (support + strength)


def row_score(row: dict[str, Any], doctor_column: str) -> float | None:
    value = safe_float(row.get(doctor_column))
    return value


def overlap_score(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def nearest_neighbors(records: list[ProductRecord], target_index: int, limit: int = 5) -> list[tuple[int, float]]:
    target = records[target_index]
    scored: list[tuple[int, float]] = []
    for index, other in enumerate(records):
        if index == target_index:
            continue
        score = 0.0
        if other.product_type == target.product_type:
            score += 3.0
        if norm_label(other.category) == norm_label(target.category):
            score += 0.5
        score += 5.0 * overlap_score(target.exact_keys, other.exact_keys)
        score += 2.5 * overlap_score(target.family_keys, other.family_keys)
        if norm_label(other.row.get("brand_name")) == norm_label(target.row.get("brand_name")):
            score += 0.25
        name_ratio = difflib.SequenceMatcher(
            None,
            norm_label(target.row.get("product_name")),
            norm_label(other.row.get("product_name")),
        ).ratio()
        if name_ratio >= 0.55:
            score += 0.5 * name_ratio
        if score >= 3.25:
            scored.append((index, score))
    return sorted(scored, key=lambda item: item[1], reverse=True)[:limit]


def weighted_neighbor_average(records: list[ProductRecord], neighbors: list[tuple[int, float]], doctor_column: str) -> tuple[float | None, int]:
    weighted_sum = 0.0
    total_weight = 0.0
    support = 0
    for index, weight in neighbors:
        value = row_score(records[index].row, doctor_column)
        if value is None:
            continue
        weighted_sum += value * weight
        total_weight += weight
        support += 1
    if total_weight <= 0:
        return None, support
    return weighted_sum / total_weight, support


def prior_for(
    records: list[ProductRecord],
    target_index: int,
    doctor_column: str,
    mode: str,
    fallback: float,
) -> tuple[float | None, int]:
    target = records[target_index]
    values: list[float] = []
    for index, other in enumerate(records):
        if index == target_index:
            continue
        if other.product_type != target.product_type:
            continue
        if mode == "exact" and not (target.exact_keys & other.exact_keys):
            continue
        if mode == "family" and not (target.family_keys & other.family_keys):
            continue
        value = row_score(other.row, doctor_column)
        if value is not None:
            values.append(value)
    if not values:
        return None, 0
    return shrink(sum(values) / len(values), len(values), fallback), len(values)


def type_prior(records: list[ProductRecord], target_index: int, doctor_column: str, fallback: float) -> tuple[float, int]:
    target = records[target_index]
    values: list[float] = []
    for index, other in enumerate(records):
        if index == target_index:
            continue
        if other.product_type != target.product_type:
            continue
        value = row_score(other.row, doctor_column)
        if value is not None:
            values.append(value)
    if not values:
        return fallback, 0
    return shrink(sum(values) / len(values), len(values), fallback, strength=10) or fallback, len(values)


def global_prior(records: list[ProductRecord], target_index: int, doctor_column: str) -> float:
    values = [row_score(record.row, doctor_column) for index, record in enumerate(records) if index != target_index]
    return average([value for value in values if value is not None]) or 50.0


def confidence_for(created_count: int, weak_count: int, exact_keys: set[str], families: set[str]) -> tuple[str, list[str]]:
    flags: list[str] = []
    if created_count:
        flags.append(f"{created_count} fallback ingredient match(es)")
    if weak_count:
        flags.append(f"{weak_count} weak/fuzzy ingredient match(es)")
    if not exact_keys:
        flags.append("no exact/curated ingredient match")
    if not families:
        flags.append("no recognized ingredient family")
    if created_count or weak_count >= 2 or not families:
        return "Low", flags
    if weak_count or not exact_keys:
        return "Medium", flags
    return "High", flags


def build_records() -> list[ProductRecord]:
    auto = load_auto_scorer()
    canonical_rows, alias_map, alias_labels, _ = auto.read_ingredient_scores()
    match, _, _ = auto.make_matcher(canonical_rows, alias_map, alias_labels)
    catalog = parse_catalog(PRODUCTS_CSV)

    rows: list[dict[str, Any]]
    with PRODUCTS_CSV.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    records: list[ProductRecord] = []
    for row in rows:
        uid = clean_text(row.get("product_uid"))
        primary_labels = auto.split_ingredients(row.get("single_hero_ingredient", ""))
        secondary_labels = auto.split_ingredients(row.get("secondary_hero_ingredients", ""))
        primary_matches = [match(label) for label in primary_labels]
        secondary_matches = [match(label) for label in secondary_labels]
        all_matches = primary_matches + secondary_matches
        baseline_scores = {column: float(value) for column, value in auto.product_scores(primary_matches, secondary_matches, row.get("product_type", "")).items()}

        doctor_scores: dict[str, float] = {}
        for doctor_column, internal_column, _ in SCORE_PAIRS:
            value = safe_float(row.get(doctor_column))
            if value is not None:
                doctor_scores[internal_column] = float(value)
                if doctor_column == "Above 25":
                    doctor_scores["Above 25"] = float(value)

        exact_keys: set[str] = set()
        weak_count = 0
        created_count = 0
        for item in all_matches:
            if not item.get("used_for_scoring"):
                continue
            if item.get("match_method") == "Created fallback":
                created_count += 1
            if risky_match(item):
                weak_count += 1
                continue
            method = clean_text(item.get("match_method"))
            if method in {"Exact or alias", "Singular/plural normalized", "Curated related match"} or float(item.get("confidence") or 0) >= 0.93:
                key = norm_key(item.get("canonical_ingredient"))
                if key:
                    exact_keys.add(key)

        primary_text = " ".join(primary_labels)
        full_text = " ".join(
            [
                row.get("product_name", ""),
                row.get("single_hero_ingredient", ""),
                row.get("secondary_hero_ingredients", ""),
                row.get("ingredients", ""),
                " ".join(clean_text(item.get("canonical_ingredient")) for item in all_matches),
            ]
        )
        family_keys = classify_families(full_text)
        primary_family_keys = classify_families(primary_text)
        confidence, flags = confidence_for(created_count, weak_count, exact_keys, family_keys)

        records.append(
            ProductRecord(
                uid=uid,
                row=row,
                catalog=catalog[norm_key(uid)],
                doctor_scores=doctor_scores,
                baseline_scores=baseline_scores,
                v2_scores={},
                exact_keys=exact_keys,
                family_keys=family_keys,
                primary_family_keys=primary_family_keys,
                product_type=normalized_product_type(row.get("product_type", "")),
                category=clean_text(row.get("category")),
                ingredient_match_status=auto.summarize_match_status(all_matches),
                created_fallback_count=created_count,
                weak_match_count=weak_count,
                confidence=confidence,
                review_flags=flags,
            )
        )
    return records


def predict_v2_scores(records: list[ProductRecord]) -> None:
    neighbors_by_index = [nearest_neighbors(records, index) for index in range(len(records))]
    for index, record in enumerate(records):
        for doctor_column, internal_column, _ in SCORE_PAIRS:
            base = float(record.baseline_scores.get(internal_column, 50.0))
            global_avg = global_prior(records, index, doctor_column)
            type_avg, type_support = type_prior(records, index, doctor_column, global_avg)
            exact_avg, exact_support = prior_for(records, index, doctor_column, "exact", type_avg)
            family_avg, family_support = prior_for(records, index, doctor_column, "family", type_avg)
            anchor_avg, anchor_support = weighted_neighbor_average(records, neighbors_by_index[index], doctor_column)

            base = soften_weak_hardblock(record, internal_column, base, type_avg)

            weighted_parts: list[tuple[float, float]] = []
            if exact_avg is not None and exact_support >= 2:
                weighted_parts.extend([(base, 0.45), (exact_avg, 0.25), (type_avg, 0.10)])
                if anchor_avg is not None:
                    weighted_parts.append((anchor_avg, 0.20))
                else:
                    weighted_parts.append((family_avg or type_avg, 0.20))
            elif family_avg is not None and family_support >= 3:
                weighted_parts.extend([(base, 0.45), (family_avg, 0.25), (type_avg, 0.15)])
                if anchor_avg is not None:
                    weighted_parts.append((anchor_avg, 0.15))
            elif anchor_avg is not None:
                weighted_parts.extend([(base, 0.55), (anchor_avg, 0.30), (type_avg, 0.15)])
            else:
                weighted_parts.extend([(base, 0.70), (type_avg, 0.30)])

            if record.confidence == "Low":
                weighted_parts = [(base, 0.35), (anchor_avg if anchor_avg is not None else type_avg, 0.35), (type_avg, 0.30)]

            total_weight = sum(weight for _, weight in weighted_parts)
            predicted = sum(value * weight for value, weight in weighted_parts) / total_weight if total_weight else base

            if record.confidence == "Low" and predicted > 84:
                predicted = 84
            elif record.confidence == "Medium" and predicted > 92:
                predicted = 92

            if internal_column == "Excessive Dryness score":
                if predicted <= 50:
                    predicted = -100
                elif predicted <= 84:
                    predicted = 0
                else:
                    predicted = 100

            record.v2_scores[internal_column] = float(score_value(predicted))
        record.v2_scores["Above 25"] = record.v2_scores["+>25"]
        record.v2_scores["None"] = 100.0


def selected_concern(profile: dict[str, Any]) -> str | None:
    concerns = profile.get("selectedFaceBodyConcerns") or []
    if not concerns:
        return None
    concern = clean_text(concerns[0])
    aliases = {
        "Aging": "Wrinkles/Fine lines",
        "Dark Spots": "Dark Spots/Pigmentation",
        "Pigmentation": "Dark Spots/Pigmentation",
        "Open pores": "Open Pores",
        "redness": "Redness/Irritation",
    }
    return aliases.get(concern, concern)


def age_component(scores: dict[str, float], profile: dict[str, Any]) -> float | None:
    age = norm_label(profile.get("age"))
    if age in {"teen", "under 16", "below 16", "16", "<16"}:
        return scores.get("<16")
    if age == "adult":
        return rounded_average([scores.get("17-25", 50), scores.get("+>25", 50)])
    if age in {"17 25", "17-25", "17 - 25"}:
        return scores.get("17-25")
    if age in {"above 25", "over 25", "25", "25+", "+>25"}:
        return scores.get("+>25")
    return None


def skin_component(scores: dict[str, float], profile: dict[str, Any]) -> float | None:
    skin = clean_text(profile.get("selectedSkinType")) or "Normal"
    sensitive = bool(profile.get("selectedSensitive"))
    base = skin.title()
    if base not in {"Oily", "Dry", "Normal", "Combination"}:
        base = "Normal"
    return scores.get(f"{base}+Sensitive Score" if sensitive else f"{base} Score")


def special_components(scores: dict[str, float], profile: dict[str, Any], product_type: str) -> list[float]:
    values: list[float] = []
    conditions = [norm_label(item) for item in profile.get("selectedSpecialConditions", []) if norm_label(item)]
    if not conditions or conditions == ["none"]:
        return [100.0]
    for condition in conditions:
        if product_type == "serum" and condition == "excessive dryness":
            continue
        if condition == "pregnant" and "Pregnancy Score" in scores:
            values.append(scores["Pregnancy Score"])
        elif condition == "breastfeeding" and "Breastfeeling Score" in scores:
            values.append(scores["Breastfeeling Score"])
        elif condition == "excessive dryness" and "Excessive Dryness score" in scores:
            values.append(scores["Excessive Dryness score"])
    return values or [100.0]


def concern_supported(record: ProductRecord, concern: str | None) -> bool:
    if not concern:
        return False
    wanted = CONCERN_FAMILIES.get(concern, set())
    return bool(wanted & record.family_keys)


def product_relevance_cap(record: ProductRecord, concern: str | None, profile: dict[str, Any]) -> int:
    product_type = record.product_type
    if not concern:
        return 100
    supported = concern_supported(record, concern)

    if product_type == "serum":
        return 100 if supported else 74
    if product_type == "cleanser":
        if concern in WRINKLE_CONCERNS:
            return 84
        return 100 if supported or concern in ACNE_CONCERNS else 89
    if product_type == "moisturizer":
        if concern in HYDRATION_CONCERNS:
            return 100
        return 100 if supported else 84
    if product_type == "sunscreen":
        if concern in PHOTO_CONCERNS:
            return 100
        if concern in {"Dullness", "Barrier Repair"}:
            return 84
        return 100 if supported else 74
    if product_type == "mask":
        return 100 if supported else 89
    return 89 if supported else 79


def confidence_cap(record: ProductRecord) -> int:
    if record.confidence == "Low":
        return 79
    if record.created_fallback_count:
        return 84
    if record.confidence == "Medium":
        return 92
    return 100


def has_hard_block(values: list[float]) -> bool:
    return any(float(value) <= -100 for value in values if value is not None)


def v2_profile_score(record: ProductRecord, profile: dict[str, Any]) -> int:
    scores = record.v2_scores
    product_type = record.product_type
    concern = selected_concern(profile)
    components: list[float] = []

    age = age_component(scores, profile)
    skin = skin_component(scores, profile)
    concern_value = scores.get(concern) if concern else None
    specials = special_components(scores, profile, product_type)

    if product_type == "serum":
        if concern_value is not None:
            components.append(concern_value)
        if age is not None:
            components.append(age)
        components.extend(specials)
        if profile.get("selectedSensitive") and skin is not None:
            components.append(skin)
    elif product_type == "cleanser":
        if concern in WRINKLE_CONCERNS:
            if skin is not None:
                components.append(skin)
            components.extend(specials)
        else:
            for value in [skin, concern_value, age]:
                if value is not None:
                    components.append(value)
            components.extend(specials)
    elif product_type in {"moisturizer", "sunscreen"}:
        if skin is not None:
            components.append(skin)
        components.extend(specials)
    elif product_type == "mask":
        for value in [concern_value, skin]:
            if value is not None:
                components.append(value)
        components.extend(specials)
    else:
        for value in [concern_value, skin, age]:
            if value is not None:
                components.append(value)
        components.extend(specials)

    if not components:
        components = [50.0]
    if has_hard_block(components):
        return -100

    score = rounded_average(components) or 0
    score = min(score, product_relevance_cap(record, concern, profile), confidence_cap(record))
    return int(score)


def make_profile_grid() -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for skin_type in QUIZ_OPTIONS["skinTypes"]:
        for sensitive in [False, True]:
            for age in ["Teen", "Adult"]:
                for concern in QUIZ_OPTIONS["faceBodyConcerns"]:
                    profiles.append(
                        {
                            "age": age,
                            "selectedGender": "female",
                            "selectedSkinType": skin_type,
                            "selectedSensitive": sensitive,
                            "selectedFaceBodyConcerns": [concern],
                            "selectedLipsEyesConcerns": [],
                            "selectedSpecialConditions": ["None"],
                        }
                    )
    return profiles


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denom_x = sum((x - mean_x) ** 2 for x in xs)
    denom_y = sum((y - mean_y) ** 2 for y in ys)
    if denom_x <= 0 or denom_y <= 0:
        return None
    return numerator / math.sqrt(denom_x * denom_y)


def aggregate_score_metrics(pairs: list[tuple[float, float]]) -> dict[str, Any]:
    diffs = [abs(auto_score - doctor_score) for doctor_score, auto_score in pairs]
    same_bucket = sum(1 for doctor_score, auto_score in pairs if score_bucket(doctor_score) == score_bucket(auto_score))
    hard_agree = sum(1 for doctor_score, auto_score in pairs if (doctor_score <= -100) == (auto_score <= -100))
    return {
        "pairs": len(pairs),
        "mean_abs_diff": round(average(diffs) or 0, 3),
        "median_abs_diff": round(statistics.median(diffs), 3) if diffs else 0,
        "within_5_pct": safe_pct(sum(1 for diff in diffs if diff <= 5), len(diffs)),
        "within_10_pct": safe_pct(sum(1 for diff in diffs if diff <= 10), len(diffs)),
        "within_20_pct": safe_pct(sum(1 for diff in diffs if diff <= 20), len(diffs)),
        "same_bucket_pct": safe_pct(same_bucket, len(pairs)),
        "hard_block_agreement_pct": safe_pct(hard_agree, len(pairs)),
        "pearson": round(pearson([p[0] for p in pairs], [p[1] for p in pairs]) or 0, 4),
    }


def validate_base_scores(records: list[ProductRecord]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    baseline_pairs: list[tuple[float, float]] = []
    v2_pairs: list[tuple[float, float]] = []
    product_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []

    by_column_baseline: dict[str, list[tuple[float, float]]] = defaultdict(list)
    by_column_v2: dict[str, list[tuple[float, float]]] = defaultdict(list)

    for record in records:
        product_baseline_diffs: list[float] = []
        product_v2_diffs: list[float] = []
        product_hard_disagreements = 0
        for doctor_column, internal_column, label in SCORE_PAIRS:
            doctor_score = row_score(record.row, doctor_column)
            if doctor_score is None:
                continue
            baseline_score = float(record.baseline_scores.get(internal_column, 50))
            v2_score = float(record.v2_scores.get(internal_column, 50))
            baseline_pairs.append((doctor_score, baseline_score))
            v2_pairs.append((doctor_score, v2_score))
            by_column_baseline[label].append((doctor_score, baseline_score))
            by_column_v2[label].append((doctor_score, v2_score))

            product_baseline_diffs.append(abs(baseline_score - doctor_score))
            product_v2_diffs.append(abs(v2_score - doctor_score))
            product_hard_disagreements += int((doctor_score <= -100) != (v2_score <= -100))
            detail_rows.append(
                {
                    "product_uid": record.uid,
                    "product_name": record.row.get("product_name", ""),
                    "product_type": record.row.get("product_type", ""),
                    "score_column": label,
                    "doctor_score": doctor_score,
                    "baseline_score": baseline_score,
                    "v2_score": v2_score,
                    "baseline_abs_diff": abs(baseline_score - doctor_score),
                    "v2_abs_diff": abs(v2_score - doctor_score),
                    "v2_minus_baseline_abs_diff": abs(v2_score - doctor_score) - abs(baseline_score - doctor_score),
                    "confidence": record.confidence,
                    "review_flags": "; ".join(record.review_flags),
                    "families": "; ".join(sorted(record.family_keys)),
                }
            )

        product_rows.append(
            {
                "product_uid": record.uid,
                "product_name": record.row.get("product_name", ""),
                "product_type": record.row.get("product_type", ""),
                "confidence": record.confidence,
                "ingredient_match_status": record.ingredient_match_status,
                "created_fallback_count": record.created_fallback_count,
                "weak_match_count": record.weak_match_count,
                "families": "; ".join(sorted(record.family_keys)),
                "baseline_mean_abs_diff": round(average(product_baseline_diffs) or 0, 3),
                "v2_mean_abs_diff": round(average(product_v2_diffs) or 0, 3),
                "improvement": round((average(product_baseline_diffs) or 0) - (average(product_v2_diffs) or 0), 3),
                "v2_hard_block_disagreements": product_hard_disagreements,
            }
        )

    column_rows = []
    for _, _, label in SCORE_PAIRS:
        baseline = aggregate_score_metrics(by_column_baseline[label])
        v2 = aggregate_score_metrics(by_column_v2[label])
        column_rows.append(
            {
                "score_column": label,
                "baseline_mean_abs_diff": baseline["mean_abs_diff"],
                "v2_mean_abs_diff": v2["mean_abs_diff"],
                "improvement": round(baseline["mean_abs_diff"] - v2["mean_abs_diff"], 3),
                "baseline_within_20_pct": baseline["within_20_pct"],
                "v2_within_20_pct": v2["within_20_pct"],
                "baseline_hard_block_agreement_pct": baseline["hard_block_agreement_pct"],
                "v2_hard_block_agreement_pct": v2["hard_block_agreement_pct"],
            }
        )

    metrics = {
        "baseline": aggregate_score_metrics(baseline_pairs),
        "v2": aggregate_score_metrics(v2_pairs),
        "column_rows": sorted(column_rows, key=lambda row: row["improvement"], reverse=True),
        "products_improved": sum(1 for row in product_rows if row["improvement"] > 0),
        "products_worsened": sum(1 for row in product_rows if row["improvement"] < 0),
        "products_unchanged": sum(1 for row in product_rows if row["improvement"] == 0),
    }
    return metrics, product_rows, detail_rows


def score_row_from_record(record: ProductRecord, scores: dict[str, float]) -> ScoreRow:
    row_scores = dict(scores)
    if "+>25" in row_scores:
        row_scores["Above 25"] = row_scores["+>25"]
    row_scores["None"] = 100.0
    return ScoreRow(
        source_sheet=FACE_SHEET,
        product_uid=record.uid,
        product_name=record.row.get("product_name", ""),
        brand=record.row.get("brand_name", ""),
        category=record.row.get("category", ""),
        product_type=record.row.get("product_type", ""),
        hero_ingredient=record.row.get("single_hero_ingredient", ""),
        secondary_ingredients=record.row.get("secondary_hero_ingredients", ""),
        scores=row_scores,
        source_row=int(safe_float(record.row.get("source_excel_row")) or 0),
    )


def validate_profiles(records: list[ProductRecord]) -> dict[str, Any]:
    profiles = make_profile_grid()
    doctor_rows_by_uid = {row.product_uid: row for row in parse_catalog_score_rows(PRODUCTS_CSV)}
    record_by_uid = {record.uid: record for record in records}
    variant_pairs: dict[str, list[tuple[float, float]]] = {
        "baseline_current_profile_logic": [],
        "v2_calibrated_current_profile_logic": [],
        "v2_full_profile_caps": [],
    }
    overlaps: dict[str, dict[str, list[float]]] = {
        key: {"top_10": [], "top_20": [], "top_50": []} for key in variant_pairs
    }
    worst_profiles: dict[str, list[dict[str, Any]]] = {key: [] for key in variant_pairs}

    for profile_index, profile in enumerate(profiles, start=1):
        doctor_scored: list[tuple[str, int]] = []
        variant_scored: dict[str, list[tuple[str, int]]] = {key: [] for key in variant_pairs}
        for record in records:
            doctor_row = doctor_rows_by_uid[record.uid]
            doctor_score = score_row_for_profile(doctor_row, record.catalog, profile)["score"]
            doctor_scored.append((record.uid, int(doctor_score)))
            baseline_row = score_row_from_record(record, record.baseline_scores)
            v2_current_logic_row = score_row_from_record(record, record.v2_scores)
            variant_scores = {
                "baseline_current_profile_logic": int(score_row_for_profile(baseline_row, record.catalog, profile)["score"]),
                "v2_calibrated_current_profile_logic": int(score_row_for_profile(v2_current_logic_row, record.catalog, profile)["score"]),
                "v2_full_profile_caps": v2_profile_score(record, profile),
            }
            for key, variant_score in variant_scores.items():
                variant_scored[key].append((record.uid, variant_score))
                variant_pairs[key].append((float(doctor_score), float(variant_score)))

        def ranking_key(item: tuple[str, int]) -> tuple[int, str, str]:
            uid, score = item
            record = record_by_uid[uid]
            return (-score, clean_text(record.catalog.get("category")), clean_text(record.catalog.get("product_name")).lower())

        doctor_sorted = sorted(doctor_scored, key=ranking_key)
        for key, scored_rows in variant_scored.items():
            variant_sorted = sorted(scored_rows, key=ranking_key)

            def overlap(n: int) -> float:
                doctor_top = {uid for uid, _ in doctor_sorted[:n]}
                variant_top = {uid for uid, _ in variant_sorted[:n]}
                return len(doctor_top & variant_top) / n * 100

            top10 = overlap(10)
            top20 = overlap(20)
            top50 = overlap(50)
            overlaps[key]["top_10"].append(top10)
            overlaps[key]["top_20"].append(top20)
            overlaps[key]["top_50"].append(top50)
            worst_profiles[key].append(
                {
                    "profile_id": f"profile_{profile_index:03d}",
                    "age": profile["age"],
                    "skin_type": profile["selectedSkinType"],
                    "sensitive": profile["selectedSensitive"],
                    "concern": profile["selectedFaceBodyConcerns"][0],
                    "top_10_overlap_pct": round(top10, 2),
                    "top_20_overlap_pct": round(top20, 2),
                    "top_50_overlap_pct": round(top50, 2),
                    "doctor_top_5": [f"{uid}:{score}" for uid, score in doctor_sorted[:5]],
                    "variant_top_5": [f"{uid}:{score}" for uid, score in variant_sorted[:5]],
                }
            )

    variant_results: dict[str, Any] = {}
    for key, pairs in variant_pairs.items():
        final_metrics = aggregate_score_metrics(pairs)
        variant_results[key] = {
            "overall_final_score": final_metrics,
            "top_overlap": {
                "top_10_avg_overlap_pct": round(average(overlaps[key]["top_10"]) or 0, 2),
                "top_20_avg_overlap_pct": round(average(overlaps[key]["top_20"]) or 0, 2),
                "top_50_avg_overlap_pct": round(average(overlaps[key]["top_50"]) or 0, 2),
                "top_10_min_overlap_pct": round(min(overlaps[key]["top_10"]), 2),
                "top_20_min_overlap_pct": round(min(overlaps[key]["top_20"]), 2),
            },
            "worst_profiles_by_top20_overlap": sorted(
                worst_profiles[key],
                key=lambda item: (item["top_20_overlap_pct"], item["top_50_overlap_pct"]),
            )[:20],
        }
    return {
        "profiles_checked": len(profiles),
        "products_per_profile": len(records),
        "final_score_pairs_per_variant": len(next(iter(variant_pairs.values()))),
        "variants": variant_results,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    records = build_records()
    predict_v2_scores(records)
    base_metrics, product_rows, detail_rows = validate_base_scores(records)
    profile_metrics = validate_profiles(records)

    confidence_counts = Counter(record.confidence for record in records)
    summary = {
        "method": "V2 leave-one-out validation: each product is predicted using automated ingredient scores plus doctor calibration from the other 383 products only.",
        "doctor_products_checked": len(records),
        "confidence_counts": dict(confidence_counts),
        "base_score_validation": base_metrics,
        "profile_recommendation_validation": profile_metrics,
        "output_files": {
            "summary": str(OUTPUT_SUMMARY),
            "product_summary": str(OUTPUT_PRODUCTS),
            "score_detail": str(OUTPUT_DETAIL),
        },
    }
    OUTPUT_SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_csv(OUTPUT_PRODUCTS, sorted(product_rows, key=lambda row: row["improvement"], reverse=True))
    write_csv(OUTPUT_DETAIL, detail_rows)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
