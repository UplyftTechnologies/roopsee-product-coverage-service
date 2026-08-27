from __future__ import annotations

import importlib.util
import json
import math
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = REPO_ROOT / "data" / "source"


def env_path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default))).expanduser()


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved)


AUTO_OUTPUT_DIR = env_path("ROOPSEE_AUTO_OUTPUT_DIR", REPO_ROOT / "outputs" / "roopsee_automated_scoring")
AUTO_PAYLOAD = env_path("ROOPSEE_AUTO_PAYLOAD", AUTO_OUTPUT_DIR / "automated_scoring_payload.json")
FINAL_DATASET = env_path("ROOPSEE_FINAL_DATASET", REPO_ROOT / "static" / "data" / "final_scored_products.json")
V2_PATH = env_path("ROOPSEE_V2_LOGIC_PATH", REPO_ROOT / "tools" / "validate_v2_automated_logic.py")
FINAL_VALIDATION_SUMMARY = AUTO_OUTPUT_DIR / "final_rank_fusion_algorithm_validation_summary.json"
USEFUL_PRODUCTS = env_path("ROOPSEE_USEFUL_PRODUCTS", SOURCE_DIR / "useful_skin_bodycare_products.xlsx")
RETAILER_PRODUCTS = env_path("ROOPSEE_RETAILER_PRODUCTS", SOURCE_DIR / "retailer_products_rows.csv.gz")
INGREDIENT_SCORES = env_path("ROOPSEE_INGREDIENT_SCORES", SOURCE_DIR / "roopsee_ingredient_scores_v3.xlsx")


def load_module(path: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


v2 = load_module(V2_PATH, "roopsee_v2_for_final_platform")


SCORE_COLUMNS = v2.INTERNAL_SCORE_COLUMNS + ["None"]
VISIBLE_SCORE_WEIGHTS = {
    "baseline": 0.05,
    "v2": 0.30,
    "anchor": 0.55,
    "type_family": 0.05,
    "type": 0.05,
}
RANK_FUSION_WEIGHTS = {
    "score": 0.20,
    "baseline_rank": 0.10,
    "v2_rank": 0.10,
    "anchor_rank": 0.55,
    "type_family_rank": 0.05,
}
KEEP_CONFIDENCE_LEVELS = {"High"}

SOURCE_QUALITY_TERMS = [
    "removed",
    "not found in retailer full inci",
    "late or unknown-strength active",
    "no clear primary surfactant",
]

SALICYLATE_TERMS = ["salicylic acid", " bha", "bha ", "willow bark", "salix alba", "salicylate"]
SALICYLATE_HIGH_STRENGTH_TERMS = ["chemical peel", "peel solution", "peeling solution", "aha bha peel", "body peel"]
TREATMENT_CONCERN_COLUMNS = {
    "Acne",
    "Body Acne",
    "Open Pores",
    "Comedones",
    "Dark Spots/Pigmentation",
    "Uneven Skin Tone",
    "Melasma",
    "Dullness",
    "Tanning",
    "Wrinkles/Fine lines",
}


@dataclass
class LargeProductRecord:
    uid: str
    row: dict[str, Any]
    product_type: str
    category: str
    exact_keys: set[str]
    family_keys: set[str]
    primary_family_keys: set[str]
    base_scores: dict[str, float]
    confidence: str
    review_flags: list[str]
    created_fallback_count: int
    weak_match_count: int


def clean(value: Any) -> str:
    return v2.clean_text(value)


def to_float(value: Any) -> float | None:
    return v2.safe_float(value)


def score_value(value: float) -> int:
    return v2.score_value(value)


def shrink(value: float | None, support: int, fallback: float, strength: int = 5) -> float | None:
    if value is None or support <= 0:
        return None
    return ((value * support) + (fallback * strength)) / (support + strength)


def overlap_ratio(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def parse_int(value: Any) -> int:
    parsed = to_float(value)
    return int(parsed or 0)


def joined_row_text(row: dict[str, Any]) -> str:
    return v2.norm_label(
        " ".join(
            clean(row.get(key))
            for key in [
                "product_name",
                "brand",
                "product_type",
                "category",
                "primary_ingredients",
                "secondary_ingredients",
                "matched_primary_ingredients",
                "matched_secondary_ingredients",
                "retailer_full_ingredients",
            ]
        )
    )


def has_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def split_flags(value: Any) -> list[str]:
    return [clean(part) for part in clean(value).split(";") if clean(part)]


def source_quality_flags(row: dict[str, Any]) -> list[str]:
    return split_flags(row.get("source_validation_flags")) + split_flags(row.get("formula_quality_flags"))


def has_source_quality_issue(row: dict[str, Any]) -> bool:
    text = v2.norm_label("; ".join(source_quality_flags(row)))
    return any(term in text for term in SOURCE_QUALITY_TERMS)


def base_auto_uid(value: Any) -> str:
    match = re.match(r"^(AUTO-\d+)", clean(value))
    return match.group(1) if match else clean(value)


def is_orange_peel_powder_product(row: dict[str, Any]) -> bool:
    text = v2.norm_label(
        " ".join(
            clean(row.get(key))
            for key in [
                "product_name",
                "brand",
                "product_type",
                "category",
                "primary_ingredients",
                "secondary_ingredients",
            ]
        )
    )
    return has_any(text, ["orange peel powder", "orange powder", "dry orange peel", "citrus sinensis"]) and not has_any(
        text,
        ["orange peel oil", "essential oil", "bergamot oil"],
    )


def apply_reviewed_source_overrides(row: dict[str, Any]) -> dict[str, Any]:
    """Fix known catalog/source extraction errors before confidence and scoring are derived."""
    output = dict(row)
    name = v2.norm_label(output.get("product_name"))

    if "be neude instant detanning and brightening face mask" in name:
        output["product_type"] = "Mask"
        output["primary_ingredients"] = "Kaolin, Milk Cream, Isopropyl Myristate, Fruit Extract Complex"
        output["secondary_ingredients"] = (
            "Lactic Acid, Kojic Acid, Lactobacillus Ferment, Aloe Vera, "
            "Willow Bark Extract, Lemon Peel Extract, Fragrance"
        )
        output["matched_primary_ingredients"] = (
            "Kaolin -> Clay (Exact or alias); "
            "Milk Cream -> Emollient Cream Base (Exact or alias); "
            "Isopropyl Myristate -> Emollient Cream Base (Exact or alias)"
        )
        output["matched_secondary_ingredients"] = (
            "Lactic Acid -> Lactic Acid (Exact or alias); "
            "Kojic Acid -> Kojic Dipalmitate (Curated related match); "
            "Lactobacillus Ferment -> Probiotics (Exact or alias); "
            "Aloe Vera -> Aloe Vera (Exact or alias); "
            "Willow Bark Extract -> Willow Bark Extract (Exact or alias); "
            "Lemon Peel Extract -> Lemon Peel Extract (Exact or alias); "
            "Fragrance -> Fragrance (Exact or alias)"
        )
        output["ingredient_match_status"] = "Reviewed formula correction"
        output["needs_review_ingredient_count"] = 0
        output["created_fallback_ingredient_count"] = 0
        output["source_validation_flags"] = ""
        output["formula_quality_flags"] = ""

    if is_orange_peel_powder_product(output):
        output["product_type"] = "Mask"
        output["primary_ingredients"] = "Orange Peel Powder"
        output["secondary_ingredients"] = clean(output.get("secondary_ingredients"))
        output["matched_primary_ingredients"] = "Orange Peel Powder -> Orange Peel Powder (Exact or alias)"
        output["ingredient_match_status"] = "Reviewed botanical powder correction"
        output["needs_review_ingredient_count"] = 0
        output["created_fallback_ingredient_count"] = 0

    return output


MATCH_RE = re.compile(r"^\s*(.*?)\s*->\s*(.*?)\s*\((.*?)\)\s*$")


def parse_matched_ingredients(text: str) -> tuple[set[str], list[str], int]:
    exact_keys: set[str] = set()
    canonical_labels: list[str] = []
    weak_count = 0
    for part in clean(text).split(";"):
        part = part.strip()
        if not part:
            continue
        match = MATCH_RE.match(part)
        if not match:
            weak_count += 1
            continue
        _source, canonical, method = match.groups()
        method_key = clean(method).lower()
        canonical = clean(canonical)
        if not canonical:
            weak_count += 1
            continue
        canonical_labels.append(canonical)
        if "created fallback" in method_key:
            continue
        if "exact" in method_key or "alias" in method_key or "singular" in method_key or "curated" in method_key:
            exact_key = v2.norm_key(canonical)
            if exact_key:
                exact_keys.add(exact_key)
            continue
        if "token subset" in method_key or "fuzzy" in method_key:
            weak_count += 1
    return exact_keys, canonical_labels, weak_count


def product_confidence(
    row: dict[str, Any],
    exact_keys: set[str],
    family_keys: set[str],
    created_count: int,
    weak_count: int,
) -> tuple[str, list[str]]:
    flags: list[str] = []
    status = clean(row.get("ingredient_match_status"))
    needs_review_count = parse_int(row.get("needs_review_ingredient_count"))
    validation_flags = split_flags(row.get("source_validation_flags"))
    formula_flags = split_flags(row.get("formula_quality_flags"))
    if created_count:
        flags.append(f"{created_count} ingredient(s) created as fallback from product text")
    if weak_count or needs_review_count:
        flags.append(f"{weak_count + needs_review_count} ingredient match(es) need review")
    flags.extend(validation_flags)
    flags.extend(formula_flags)
    if not exact_keys:
        flags.append("no exact/curated ingredient anchor")
    if not family_keys:
        flags.append("no recognized active-ingredient family")
    if validation_flags:
        return "Medium", flags
    if any("no clear primary surfactant" in flag.lower() for flag in formula_flags):
        return "Medium", flags
    if any("late or unknown-strength active" in flag.lower() for flag in formula_flags) and v2.norm_label(row.get("product_type")) == "cleanser":
        return "Medium", flags
    if status.lower().startswith("needs review") or needs_review_count or not family_keys:
        return "Low", flags
    if created_count >= 2 or weak_count or not exact_keys:
        return "Medium", flags
    if created_count == 1:
        return "Medium", flags
    return "High", flags


def infer_product_type(row: dict[str, Any]) -> str:
    """Correct obvious catalog type noise without changing the raw sheet value."""
    name = v2.norm_label(row.get("product_name"))
    raw_type = v2.normalized_product_type(row.get("product_type"))

    if any(token in name for token in ["sunscreen", "sun screen", "spf", "pa++++", "pa+++", "uv shield", "sunblock", "sun gel"]):
        return "sunscreen"
    if any(
        token in name
        for token in [
            "face wash",
            "facewash",
            "body wash",
            "bodywash",
            "cleanser",
            "cleansing foam",
            "cleansing gel",
            "cleansing oil",
            "cleansing balm",
            "cleansing mousse",
            "foaming wash",
            "foam wash",
            "gel wash",
            "scrub",
        ]
    ):
        return "cleanser"
    if any(token in name for token in ["body acne spray", "acne spray", "salyzap", "treatment spray"]):
        return "toner"
    if any(
        token in name
        for token in [
            "mask",
            "sheet mask",
            "sleeping mask",
            "face pack",
            "face powder",
            "clay pack",
            "ubtan",
            "multani",
            "mitti",
            "chandan powder",
            "orange peel powder",
            "orange powder",
            "powder for face",
            "powder for skin",
            "skin powder",
            "clay powder",
            "kaolin clay powder",
            "charcoal powder",
            "neem leaf",
            "turmeric powder",
            "licorice powder",
            "dried orange peel",
            "detan powder",
        ]
    ):
        return "mask"
    if any(
        token in name
        for token in [
            "serum",
            "ampoule",
            "concentrate",
            "corrector gel",
            "spot corrector",
            "treatment gel",
            "acne gel",
            "anti acne gel",
            "anti-acne gel",
            "pimple gel",
        ]
    ):
        return "serum"
    if "gel" in name and any(
        active in name
        for active in [
            "salicylic acid",
            "niacinamide",
            "benzoyl peroxide",
            "azelaic",
            "kojic",
            "glycolic acid",
            "retinol",
            "vitamin c",
        ]
    ):
        return "serum"
    if any(token in name for token in ["toner", "toning", "peeling pad", "toner pad"]):
        return "toner"
    if any(token in name for token in ["under eye patches", "eye patches", "patches"]):
        return "mask"
    if any(
        token in name
        for token in [
            "moisturizer",
            "moisturiser",
            "moisturising",
            "moisturizing",
            "water cream",
            "night cream",
            "day cream",
            "barrier cream",
            "body lotion",
            "lotion",
            "body butter",
            "cream",
        ]
    ):
        return "moisturizer"
    return raw_type


def infer_product_category(row: dict[str, Any], product_type: str) -> str:
    """Infer the customer-facing application area instead of trusting noisy catalog tags."""
    name = v2.norm_label(row.get("product_name"))
    raw_category = v2.norm_label(row.get("category"))
    text = " ".join(
        [
            name,
            v2.norm_label(row.get("product_type")),
            raw_category,
            v2.norm_label(row.get("primary_ingredients")),
            v2.norm_label(row.get("secondary_ingredients")),
        ]
    )

    lip_terms = ["lip ", " lips", "lip balm", "lip scrub", "lip mask", "chapped lips"]
    eye_terms = ["under eye", "eye cream", "eye mask", "eye patch", "eye serum", "dark circle", "puffiness"]
    explicit_body_terms = [
        "body wash",
        "bodywash",
        "body lotion",
        "body cream",
        "body butter",
        "body sunscreen",
        "body spray",
        "body acne",
        "back acne",
        "hand cream",
        "foot cream",
        "hand & foot",
        "hand and foot",
        "elbow",
        "knee",
        "bum",
        "buttock",
        "inner thigh",
    ]
    explicit_face_terms = [
        "face wash",
        "facewash",
        "face cleanser",
        "face serum",
        "face cream",
        "face moisturizer",
        "face moisturiser",
        "face mask",
        "face pack",
        "face powder",
        "skin powder",
        "facial",
        "toner",
        "sunscreen",
        "sun cream",
        "spf",
    ]

    if any(term in text for term in lip_terms):
        return "Lips"
    if any(term in text for term in eye_terms):
        return "Eye"

    has_body = any(term in text for term in explicit_body_terms) or product_type == "body wash"
    has_face = any(term in text for term in explicit_face_terms) or product_type in {"serum", "toner", "sunscreen", "mask"}

    if has_body and has_face:
        return "Face & Body"
    if has_body:
        return "Body"
    if has_face:
        return "Face"
    if raw_category in {"lips", "lip"}:
        return "Lips"
    if raw_category in {"eye", "eyes"}:
        return "Eye"
    if raw_category == "body":
        return "Body"
    return "Face"


def score_map_from_payload_row(row: dict[str, Any]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for column in SCORE_COLUMNS:
        if column == "None":
            scores[column] = 100.0
            continue
        value = to_float(row.get(column))
        scores[column] = float(value if value is not None else 50.0)
    if "Above 25" not in scores and "+>25" in scores:
        scores["Above 25"] = scores["+>25"]
    return scores


def set_score_values(scores: dict[str, float], values: dict[str, float]) -> None:
    for column, value in values.items():
        if column in scores:
            scores[column] = float(value)


def apply_reviewed_score_overrides(row: dict[str, Any], scores: dict[str, float], product_type: str) -> dict[str, float]:
    """Apply audited ingredient corrections that the source payload cannot infer safely."""
    output = dict(scores)
    name = v2.norm_label(row.get("product_name"))

    if is_orange_peel_powder_product(row):
        set_score_values(
            output,
            {
                "<16": 70,
                "17-25": 88,
                "+>25": 88,
                "Acne": 74,
                "Body Acne": 68,
                "Dryness": 55,
                "Open Pores": 78,
                "Uneven Skin Tone": 76,
                "Dark Spots/Pigmentation": 76,
                "Melasma": 65,
                "Barrier Repair": 55,
                "Comedones": 70,
                "Wrinkles/Fine lines": 45,
                "Redness/Irritation": 55,
                "Dehydration": 55,
                "Dullness": 78,
                "Tanning": 76,
                "Oily Score": 82,
                "Oily+Sensitive Score": 70,
                "Dry Score": 55,
                "Dry+Sensitive Score": 45,
                "Normal Score": 72,
                "Normal+Sensitive Score": 64,
                "Combination Score": 78,
                "Combination+Sensitive Score": 68,
                "Excessive Dryness score": 0,
                "Pregnancy Score": 90,
                "Breastfeeling Score": 90,
            },
        )

    if "be neude instant detanning and brightening face mask" in name:
        set_score_values(
            output,
            {
                "<16": 45,
                "17-25": 76,
                "+>25": 80,
                "Acne": 56,
                "Body Acne": 50,
                "Dryness": 68,
                "Open Pores": 62,
                "Uneven Skin Tone": 76,
                "Dark Spots/Pigmentation": 80,
                "Melasma": 64,
                "Barrier Repair": 62,
                "Comedones": 50,
                "Wrinkles/Fine lines": 52,
                "Redness/Irritation": 58,
                "Dehydration": 68,
                "Dullness": 70,
                "Tanning": 72,
                "Oily Score": 62,
                "Oily+Sensitive Score": 55,
                "Dry Score": 74,
                "Dry+Sensitive Score": 68,
                "Normal Score": 72,
                "Normal+Sensitive Score": 65,
                "Combination Score": 66,
                "Combination+Sensitive Score": 60,
                "Excessive Dryness score": 0,
                "Pregnancy Score": 45,
                "Breastfeeling Score": 50,
            },
        )

    output["None"] = 100.0
    if "+>25" in output:
        output["Above 25"] = output["+>25"]
    return output


def is_leave_on_treatment(record: LargeProductRecord) -> bool:
    text = joined_row_text(record.row)
    if record.product_type in {"serum", "toner"}:
        return True
    if record.product_type in {"cleanser", "mask"}:
        return False
    return has_any(text, ["serum", "ampoule", "leave on", "leave-on", "spot corrector", "treatment gel", "acne gel"])


def salicylate_percent(text: str) -> float | None:
    matches = []
    for pattern in [
        r"(\d+(?:\.\d+)?)\s*%\s*(?:salicylic|bha)",
        r"(?:salicylic|bha)[a-z\s]*?(\d+(?:\.\d+)?)\s*%",
    ]:
        matches.extend(float(value) for value in re.findall(pattern, text))
    return max(matches) if matches else None


def high_strength_salicylate(text: str) -> bool:
    percent = salicylate_percent(text)
    if percent is not None and percent > 2:
        return True
    return has_any(text, SALICYLATE_HIGH_STRENGTH_TERMS)


def pregnancy_lactation_score_cap(record: LargeProductRecord, column: str) -> float | None:
    if column not in {"Pregnancy Score", "Breastfeeling Score"}:
        return None

    text = joined_row_text(record.row)
    if has_any(text, ["retinol", "retinal", "retinoid", "retinyl", "tretinoin", "adapalene", "hydroquinone"]):
        return -100

    cap: float | None = None

    has_salicylate = has_any(text, SALICYLATE_TERMS)
    if has_salicylate:
        if high_strength_salicylate(text):
            cap = 60 if column == "Pregnancy Score" else 65
        elif is_leave_on_treatment(record):
            cap = 82 if column == "Pregnancy Score" else 84
        else:
            cap = 82 if column == "Pregnancy Score" else 85

    has_kojic = has_any(text, ["kojic acid", "kojic dipalmitate"])
    has_exfoliant_or_irritant = has_any(
        text,
        ["lactic acid", "glycolic acid", "mandelic acid", "aha", "lemon peel", "fragrance", "parfum"],
    )
    if column == "Pregnancy Score" and has_kojic and has_exfoliant_or_irritant:
        cap = min(cap if cap is not None else 100, 60)
    elif column == "Pregnancy Score" and has_kojic:
        cap = min(cap if cap is not None else 100, 70)

    return cap


def is_non_topical_catalog_product(product: dict[str, Any]) -> bool:
    name_text = v2.norm_label(" ".join([clean(product.get("name")), clean(product.get("brand"))]))
    ingredient_text = v2.norm_label(" ".join([clean(product.get("primaryIngredients")), clean(product.get("secondaryIngredients"))]))
    full_text = f"{name_text} {ingredient_text}"

    if has_any(name_text, ["capsule cream", "face serum", "face mask", "face wash", "cleanser", "cream", "lotion", "lip balm"]):
        return False
    if "baby powder" in name_text:
        return True

    hard_oral_terms = [
        "effervescent tablet",
        "effervescent tablets",
        "effervescent tab",
        "effervescent tabs",
        "tabs",
        "veg capsule",
        "veg capsules",
        "capsules supplement",
        "capsule supplement",
        "tablet",
        "capsule",
        "tablets capsules",
        "tablets supplements",
        "glutathione tablets",
        "collagen supplement",
        "supplement powder",
        "sipper",
        "sip n go",
    ]
    if has_any(name_text, hard_oral_terms):
        return True

    oral_supplement_terms = [
        "supplement powder",
        "collagen powder",
        "marine collagen powder",
        "collagen supplement",
        "biotin",
        "hair and nails",
        "hairs and nails",
        "sip n go",
        "capsule",
        "capsules",
        "tablet",
        "tablets",
        "gummies",
        "drink mix",
    ]
    if has_any(full_text, oral_supplement_terms) and has_any(name_text, ["powder", "supplement", "tablet", "capsule", "gummies"]):
        return True
    return False


def build_large_records(payload_rows: list[dict[str, Any]]) -> list[LargeProductRecord]:
    records: list[LargeProductRecord] = []
    for raw_row in payload_rows:
        row = apply_reviewed_source_overrides(raw_row)
        primary_exact, primary_canonical, primary_weak = parse_matched_ingredients(row.get("matched_primary_ingredients", ""))
        secondary_exact, secondary_canonical, secondary_weak = parse_matched_ingredients(row.get("matched_secondary_ingredients", ""))
        exact_keys = primary_exact | secondary_exact
        created_count = parse_int(row.get("created_fallback_ingredient_count"))
        weak_count = primary_weak + secondary_weak
        primary_text = " ".join([clean(row.get("primary_ingredients")), " ".join(primary_canonical)])
        full_text = " ".join(
            [
                clean(row.get("product_name")),
                clean(row.get("product_type")),
                clean(row.get("category")),
                clean(row.get("primary_ingredients")),
                clean(row.get("secondary_ingredients")),
                " ".join(primary_canonical),
                " ".join(secondary_canonical),
            ]
        )
        family_keys = v2.classify_families(full_text)
        if is_orange_peel_powder_product(row):
            family_keys.discard("fragrance_risk")
            family_keys.update({"brightening", "acne"})
        primary_family_keys = v2.classify_families(primary_text)
        if is_orange_peel_powder_product(row):
            primary_family_keys.discard("fragrance_risk")
            primary_family_keys.update({"brightening", "acne"})
        confidence, flags = product_confidence(row, exact_keys, family_keys, created_count, weak_count)
        product_type = infer_product_type(row)
        category = infer_product_category(row, product_type)
        base_scores = apply_reviewed_score_overrides(row, score_map_from_payload_row(row), product_type)
        records.append(
            LargeProductRecord(
                uid=clean(row.get("auto_product_uid")),
                row=row,
                product_type=product_type,
                category=category,
                exact_keys=exact_keys,
                family_keys=family_keys,
                primary_family_keys=primary_family_keys,
                base_scores=base_scores,
                confidence=confidence,
                review_flags=flags,
                created_fallback_count=created_count,
                weak_match_count=weak_count,
            )
        )
    return records


def load_auto_payload() -> list[dict[str, Any]]:
    data = json.loads(AUTO_PAYLOAD.read_text(encoding="utf-8"))
    rows = data["uniqueRows"]
    headers = data["uniqueHeaders"]
    if rows and isinstance(rows[0], list):
        unique_rows = [dict(zip(headers, row)) for row in rows]
    else:
        unique_rows = rows

    sku_rows_raw = data.get("skuRows") or []
    sku_headers = data.get("skuHeaders") or []
    sku_rows = [dict(zip(sku_headers, row)) for row in sku_rows_raw] if sku_rows_raw and isinstance(sku_rows_raw[0], list) else sku_rows_raw
    sku_by_base_uid: dict[str, dict[str, Any]] = {}
    for sku_row in sku_rows:
        base_uid = base_auto_uid(sku_row.get("auto_product_uid"))
        if not base_uid or base_uid in sku_by_base_uid:
            continue
        sku_by_base_uid[base_uid] = sku_row

    source_fields = [
        "retailer_full_ingredients",
        "retailer_how_to_use",
        "retailer_product_attributes",
        "source_validation_flags",
        "formula_quality_flags",
    ]
    for row in unique_rows:
        sku_row = sku_by_base_uid.get(base_auto_uid(row.get("auto_product_uid")))
        if not sku_row:
            continue
        for field in source_fields:
            if not clean(row.get(field)):
                row[field] = clean(sku_row.get(field))
    return unique_rows


def vector_from_scores(scores: dict[str, float]) -> list[float]:
    return [float(scores.get(column, 100.0 if column == "None" else 50.0)) for column in SCORE_COLUMNS]


def doctor_vector(record: Any) -> list[float]:
    values: list[float] = []
    for doctor_column, _internal_column, _label in v2.SCORE_PAIRS:
        value = v2.row_score(record.row, doctor_column)
        values.append(float(value if value is not None else 50.0))
    values.append(100.0)
    return values


def weighted_vector_average(items: list[tuple[list[float], float]], fallback: list[float]) -> tuple[list[float], int]:
    valid = [(values, weight) for values, weight in items if weight > 0]
    if not valid:
        return list(fallback), 0
    total_weight = sum(weight for _values, weight in valid)
    output: list[float] = []
    for index in range(len(SCORE_COLUMNS)):
        output.append(sum(values[index] * weight for values, weight in valid) / total_weight)
    return output, len(valid)


def average_vector(vectors: list[list[float]], fallback: list[float]) -> tuple[list[float], int]:
    if not vectors:
        return list(fallback), 0
    output = []
    for index in range(len(SCORE_COLUMNS)):
        output.append(sum(vector[index] for vector in vectors) / len(vectors))
    return output, len(vectors)


def softened_base_value(record: LargeProductRecord, column: str, base_score: float, fallback_score: float) -> float:
    pregnancy_cap = pregnancy_lactation_score_cap(record, column)
    if pregnancy_cap is not None and pregnancy_cap <= -100:
        return -100
    if pregnancy_cap is not None:
        if base_score <= -100:
            return pregnancy_cap
        base_score = min(base_score, pregnancy_cap)

    if base_score > -100:
        return base_score
    family_keys = record.family_keys
    if column in {"Pregnancy Score", "Breastfeeling Score"} and "retinoid" in family_keys:
        return base_score
    if column == "<16" and family_keys & {"retinoid", "exfoliant"}:
        return base_score
    if column == "Excessive Dryness score" and family_keys & {"retinoid", "exfoliant", "acne", "fragrance_risk"}:
        return base_score
    if column in {
        "Oily+Sensitive Score",
        "Dry+Sensitive Score",
        "Normal+Sensitive Score",
        "Combination+Sensitive Score",
        "Redness/Irritation",
        "Barrier Repair",
    } and "fragrance_risk" in family_keys:
        return base_score
    if record.weak_match_count or record.created_fallback_count:
        return max(min(fallback_score, 70), 40)
    return base_score


def has_formula_uncertainty(record: LargeProductRecord) -> bool:
    text = v2.norm_label("; ".join(record.review_flags))
    return any(term in text for term in SOURCE_QUALITY_TERMS)


def source_quality_lift_cap(record: LargeProductRecord, column: str, base: float, predicted: float) -> float:
    if not has_formula_uncertainty(record) or base <= -100:
        return predicted

    cap = base + 8
    if record.product_type == "cleanser" and column in {"Acne", "Body Acne", "Open Pores", "Comedones"}:
        cap = min(cap, 70)
    elif record.product_type == "cleanser" and column in TREATMENT_CONCERN_COLUMNS:
        cap = min(cap, 68)
    if column in {"Oily+Sensitive Score", "Dry+Sensitive Score", "Normal+Sensitive Score", "Combination+Sensitive Score"}:
        cap = min(cap, 78)
    return min(predicted, cap)


def build_v2_vector(
    record: LargeProductRecord,
    base_vector: list[float],
    type_vector: list[float],
    exact_vector: list[float],
    exact_support: int,
    family_vector: list[float],
    family_support: int,
    anchor_vector: list[float],
    anchor_support: int,
) -> list[float]:
    output: list[float] = []
    for index, column in enumerate(SCORE_COLUMNS):
        if column == "None":
            output.append(100.0)
            continue
        base = softened_base_value(record, column, base_vector[index], type_vector[index])
        formula_uncertain = has_formula_uncertainty(record)
        if formula_uncertain and exact_support >= 2:
            parts = [(base, 0.60), (exact_vector[index], 0.20), (type_vector[index], 0.10)]
            parts.append((anchor_vector[index] if anchor_support else family_vector[index], 0.10))
        elif formula_uncertain and family_support >= 3:
            parts = [(base, 0.65), (family_vector[index], 0.15), (type_vector[index], 0.12)]
            if anchor_support:
                parts.append((anchor_vector[index], 0.08))
        elif formula_uncertain and anchor_support:
            parts = [(base, 0.75), (anchor_vector[index], 0.10), (type_vector[index], 0.15)]
        elif exact_support >= 2:
            parts = [(base, 0.45), (exact_vector[index], 0.25), (type_vector[index], 0.10)]
            parts.append((anchor_vector[index] if anchor_support else family_vector[index], 0.20))
        elif family_support >= 3:
            parts = [(base, 0.45), (family_vector[index], 0.25), (type_vector[index], 0.15)]
            if anchor_support:
                parts.append((anchor_vector[index], 0.15))
        elif anchor_support:
            parts = [(base, 0.55), (anchor_vector[index], 0.30), (type_vector[index], 0.15)]
        else:
            parts = [(base, 0.70), (type_vector[index], 0.30)]

        if record.confidence == "Low":
            parts = [(base, 0.35), (anchor_vector[index] if anchor_support else type_vector[index], 0.35), (type_vector[index], 0.30)]

        total_weight = sum(weight for _value, weight in parts)
        predicted = sum(value * weight for value, weight in parts) / total_weight if total_weight else base
        predicted = source_quality_lift_cap(record, column, base, predicted)
        if record.confidence == "Low" and predicted > 84:
            predicted = 84
        elif record.confidence == "Medium" and predicted > 92:
            predicted = 92
        if column == "Excessive Dryness score":
            if predicted <= 50:
                predicted = -100
            elif predicted <= 84:
                predicted = 0
            else:
                predicted = 100
        pregnancy_cap = pregnancy_lactation_score_cap(record, column)
        if pregnancy_cap is not None:
            predicted = -100 if pregnancy_cap <= -100 else min(predicted, pregnancy_cap)
        output.append(float(score_value(predicted)))
    return output


def similarity(left: LargeProductRecord, right: Any) -> float:
    score = 0.0
    if left.product_type == right.product_type:
        score += 4.0
    elif v2.norm_label(left.category) == v2.norm_label(right.category):
        score += 0.75
    score += 6.0 * overlap_ratio(left.exact_keys, right.exact_keys)
    score += 3.0 * overlap_ratio(left.family_keys, right.family_keys)
    score += 2.0 * overlap_ratio(left.primary_family_keys, right.primary_family_keys)
    left_brand = v2.norm_label(left.row.get("brand"))
    right_brand = v2.norm_label(right.row.get("brand_name"))
    if left_brand and left_brand == right_brand:
        score += 0.35
    return score


def row_number(value: Any) -> float | None:
    parsed = to_float(value)
    return parsed


def build_dataset() -> dict[str, Any]:
    payload_rows = load_auto_payload()
    large_records = build_large_records(payload_rows)

    doctor_records = v2.build_records()
    v2.predict_v2_scores(doctor_records)
    doctor_vectors = [doctor_vector(record) for record in doctor_records]
    global_vector, _global_support = average_vector(doctor_vectors, [50.0] * len(SCORE_COLUMNS))

    type_vectors: dict[str, list[list[float]]] = {}
    for record, vector in zip(doctor_records, doctor_vectors):
        type_vectors.setdefault(record.product_type, []).append(vector)

    type_avg_cache = {
        product_type: average_vector(vectors, global_vector)
        for product_type, vectors in type_vectors.items()
    }

    products: list[dict[str, Any]] = []
    confidence_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    match_counts: Counter[str] = Counter()

    for index, record in enumerate(large_records, start=1):
        base_vector = vector_from_scores(record.base_scores)
        type_vector, type_support = type_avg_cache.get(record.product_type, (global_vector, 0))

        exact_items: list[tuple[list[float], float]] = []
        family_items: list[tuple[list[float], float]] = []
        type_family_items: list[tuple[list[float], float]] = []
        anchor_items: list[tuple[list[float], float]] = []
        anchors: list[tuple[int, Any, float]] = []

        for doctor_index, (doctor_record, vector) in enumerate(zip(doctor_records, doctor_vectors)):
            exact_overlap = overlap_ratio(record.exact_keys, doctor_record.exact_keys)
            family_overlap = overlap_ratio(record.family_keys, doctor_record.family_keys)
            if record.product_type == doctor_record.product_type and record.exact_keys & doctor_record.exact_keys:
                exact_items.append((vector, 1.0 + 4.0 * exact_overlap))
            if record.product_type == doctor_record.product_type and record.family_keys & doctor_record.family_keys:
                family_items.append((vector, 1.0 + 3.0 * family_overlap))
            if record.product_type == doctor_record.product_type and (exact_overlap or family_overlap):
                type_family_items.append((vector, 1.0 + 4.0 * exact_overlap + 4.0 * family_overlap))

            sim = similarity(record, doctor_record)
            if sim >= 4.5:
                anchors.append((doctor_index, doctor_record, sim))

        anchors.sort(key=lambda item: item[2], reverse=True)
        for doctor_index, _doctor_record, sim in anchors[:12]:
            anchor_items.append((doctor_vectors[doctor_index], sim))

        exact_raw, exact_support = weighted_vector_average(exact_items, type_vector)
        family_raw, family_support = weighted_vector_average(family_items, type_vector)
        type_family_raw, type_family_support = weighted_vector_average(type_family_items, type_vector)
        anchor_vector, anchor_support = weighted_vector_average(anchor_items, base_vector)

        exact_vector = [
            shrink(exact_raw[i], exact_support, type_vector[i]) if exact_support else type_vector[i]
            for i in range(len(SCORE_COLUMNS))
        ]
        family_vector = [
            shrink(family_raw[i], family_support, type_vector[i]) if family_support else type_vector[i]
            for i in range(len(SCORE_COLUMNS))
        ]
        type_family_vector = type_family_raw if type_family_support else type_vector
        if not anchor_support:
            anchor_vector = base_vector

        v2_vector = build_v2_vector(
            record,
            base_vector,
            list(type_vector),
            [float(value if value is not None else type_vector[i]) for i, value in enumerate(exact_vector)],
            exact_support,
            [float(value if value is not None else type_vector[i]) for i, value in enumerate(family_vector)],
            family_support,
            anchor_vector,
            anchor_support,
        )

        if not anchor_support:
            anchor_vector = v2_vector
        if not type_family_support:
            type_family_vector = v2_vector

        review_flags = list(record.review_flags)
        if anchor_support < 3:
            review_flags.append("limited doctor-anchor support")
        validation_flags = split_flags(record.row.get("source_validation_flags"))
        quality_flags = split_flags(record.row.get("formula_quality_flags"))

        confidence_counts[record.confidence] += 1
        type_counts[record.product_type] += 1
        match_counts[clean(record.row.get("ingredient_match_status"))] += 1

        products.append(
            {
                "uid": record.uid,
                "sourceRow": int(row_number(record.row.get("source_row")) or 0),
                "name": clean(record.row.get("product_name")),
                "brand": clean(record.row.get("brand")),
                "variant": clean(record.row.get("variant")),
                "category": record.category,
                "productType": clean(record.row.get("product_type")),
                "normalizedType": record.product_type,
                "mrp": row_number(record.row.get("mrp")),
                "sellingPrice": row_number(record.row.get("selling_price")),
                "rating": row_number(record.row.get("rating")),
                "ratingCount": row_number(record.row.get("rating_count")),
                "reviewCount": row_number(record.row.get("review_count")),
                "inStock": clean(record.row.get("in_stock")),
                "productUrl": clean(record.row.get("product_url")),
                "imageUrl": clean(record.row.get("image_url")),
                "primaryIngredients": clean(record.row.get("primary_ingredients")),
                "secondaryIngredients": clean(record.row.get("secondary_ingredients")),
                "matchedPrimaryIngredients": clean(record.row.get("matched_primary_ingredients")),
                "matchedSecondaryIngredients": clean(record.row.get("matched_secondary_ingredients")),
                "ingredientMatchStatus": clean(record.row.get("ingredient_match_status")),
                "createdFallbackIngredientCount": record.created_fallback_count,
                "needsReviewIngredientCount": parse_int(record.row.get("needs_review_ingredient_count")),
                "sourceValidationFlags": validation_flags,
                "formulaQualityFlags": quality_flags,
                "families": sorted(record.family_keys),
                "confidence": record.confidence,
                "reviewFlags": review_flags,
                "support": {
                    "anchor": anchor_support,
                    "typeFamily": type_family_support,
                    "type": type_support,
                    "exact": exact_support,
                    "family": family_support,
                },
                "nearestDoctorAnchors": [
                    {
                        "uid": clean(anchor.uid),
                        "name": clean(anchor.row.get("product_name")),
                        "productType": clean(anchor.row.get("product_type")),
                        "similarity": round(sim, 3),
                    }
                    for _anchor_index, anchor, sim in anchors[:5]
                ],
                "scoreLayers": {
                    "baseline": [score_value(value) for value in base_vector],
                    "v2": [score_value(value) for value in v2_vector],
                    "anchor": [score_value(value) for value in anchor_vector],
                    "typeFamily": [score_value(value) for value in type_family_vector],
                    "type": [score_value(value) for value in type_vector],
                },
            }
        )

        if index % 1000 == 0:
            print(f"prepared {index}/{len(large_records)} products")

    all_product_count = len(products)
    all_confidence_counts = dict(confidence_counts)
    all_type_counts = dict(type_counts)
    all_match_counts = dict(match_counts)
    high_confidence_before_topical_filter = 0
    excluded_non_topical_count = 0

    if KEEP_CONFIDENCE_LEVELS:
        products = [product for product in products if product["confidence"] in KEEP_CONFIDENCE_LEVELS]
        high_confidence_before_topical_filter = len(products)
        topical_products = [product for product in products if not is_non_topical_catalog_product(product)]
        excluded_non_topical_count = len(products) - len(topical_products)
        products = topical_products
        confidence_counts = Counter(product["confidence"] for product in products)
        type_counts = Counter(product["normalizedType"] for product in products)
        match_counts = Counter(product["ingredientMatchStatus"] for product in products)

    validation_summary = {}
    if FINAL_VALIDATION_SUMMARY.exists():
        validation_summary = json.loads(FINAL_VALIDATION_SUMMARY.read_text(encoding="utf-8"))

    return {
        "metadata": {
            "generatedAt": "2026-08-25",
            "productCount": len(products),
            "sourceProductCount": all_product_count,
            "highConfidenceBeforeTopicalFilter": high_confidence_before_topical_filter,
            "excludedNonTopicalCount": excluded_non_topical_count,
            "selectionRule": "High confidence topical skincare products only",
            "doctorReferenceProductCount": len(doctor_records),
            "sourceFiles": {
                "usefulProducts": display_path(USEFUL_PRODUCTS),
                "retailerProducts": display_path(RETAILER_PRODUCTS),
                "ingredientScores": display_path(INGREDIENT_SCORES),
                "automatedPayload": display_path(AUTO_PAYLOAD),
            },
            "visibleScoreWeights": VISIBLE_SCORE_WEIGHTS,
            "rankFusionWeights": RANK_FUSION_WEIGHTS,
            "validation": {
                "visibleScoreValidation": validation_summary.get("visible_score_validation"),
                "bestTopOverlap": (validation_summary.get("best_ranking_layer") or {}).get("top_overlap"),
            },
            "confidenceCounts": dict(confidence_counts),
            "allConfidenceCounts": all_confidence_counts,
            "productTypeCounts": dict(type_counts),
            "allProductTypeCounts": all_type_counts,
            "ingredientMatchStatusCounts": dict(match_counts),
            "allIngredientMatchStatusCounts": all_match_counts,
        },
        "quizOptions": {
            "skinTypes": ["Oily", "Dry", "Normal", "Combination"],
            "sensitivityOptions": ["No", "Yes"],
            "faceBodyConcerns": [
                "Acne",
                "Body Acne",
                "Dryness",
                "Open Pores",
                "Uneven Skin Tone",
                "Dark Spots/Pigmentation",
                "Melasma",
                "Barrier Repair",
                "Comedones",
                "Wrinkles/Fine lines",
                "Redness/Irritation",
                "Dehydration",
                "Dullness",
                "Tanning",
                "None",
            ],
            "specialConditions": ["Excessive Dryness", "Pregnant", "Breastfeeding", "None"],
            "ages": ["Teen", "Adult"],
            "genders": ["female", "male", "other", "prefer not to say"],
        },
        "scoreColumns": SCORE_COLUMNS,
        "products": products,
    }


def main() -> None:
    FINAL_DATASET.parent.mkdir(parents=True, exist_ok=True)
    dataset = build_dataset()
    FINAL_DATASET.write_text(json.dumps(dataset, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(FINAL_DATASET),
                "productCount": dataset["metadata"]["productCount"],
                "confidenceCounts": dataset["metadata"]["confidenceCounts"],
                "productTypeCounts": dataset["metadata"]["productTypeCounts"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
