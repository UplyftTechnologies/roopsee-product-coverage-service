from __future__ import annotations

from typing import Any

from .utils import clean_text, norm_label


PREGNANCY_RELATED_CONDITIONS = {"pregnant", "breastfeeding"}
BASE_SKIN_TYPES = {
    "oily": "Oily",
    "dry": "Dry",
    "normal": "Normal",
    "combination": "Combination",
}
SENSITIVE_TRUE_VALUES = {"yes", "true", "1", "y", "sensitive"}
SENSITIVE_FALSE_VALUES = {"no", "false", "0", "n", "not sensitive", "none"}


def is_male_gender(gender: Any) -> bool:
    return norm_label(gender) == "male"


def sanitize_special_conditions(special_conditions: list[str], gender: Any) -> tuple[list[str], list[str]]:
    """Apply quiz-level safety rules before scoring."""
    sanitized: list[str] = []
    adjustments: list[str] = []
    male_profile = is_male_gender(gender)

    for item in special_conditions:
        label = clean_text(item)
        key = norm_label(label)
        if not key:
            continue
        if male_profile and key in PREGNANCY_RELATED_CONDITIONS:
            adjustments.append(f"Ignored {label} because selectedGender is male.")
            continue
        sanitized.append(label)

    if any(norm_label(item) == "none" for item in sanitized) and len(sanitized) > 1:
        sanitized = [item for item in sanitized if norm_label(item) != "none"]

    return sanitized or ["None"], adjustments


def sensitive_flag(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    label = norm_label(value)
    if not label:
        return None
    if label in SENSITIVE_TRUE_VALUES:
        return True
    if label in SENSITIVE_FALSE_VALUES:
        return False
    return None


def sanitize_skin_type_and_sensitivity(profile: dict[str, Any]) -> tuple[str, bool]:
    raw_skin_type = clean_text(profile.get("selectedSkinType", "Normal"))
    skin_key = norm_label(raw_skin_type)
    inferred_sensitive = "sensitive" in skin_key
    base_skin_key = norm_label(skin_key.replace("sensitive", ""))
    base_skin_type = BASE_SKIN_TYPES.get(base_skin_key, "Normal")

    explicit_sensitive = sensitive_flag(profile.get("selectedSensitive"))
    if explicit_sensitive is None:
        explicit_sensitive = sensitive_flag(profile.get("isSensitive"))

    return base_skin_type, inferred_sensitive if explicit_sensitive is None else explicit_sensitive


def sanitize_profile(profile: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    sanitized = dict(profile)
    skin_type, selected_sensitive = sanitize_skin_type_and_sensitivity(profile)
    sanitized["selectedSkinType"] = skin_type
    sanitized["selectedSensitive"] = selected_sensitive
    special_conditions = profile.get("selectedSpecialConditions") or ["None"]
    sanitized_specials, adjustments = sanitize_special_conditions(
        [clean_text(item) for item in special_conditions],
        profile.get("selectedGender", ""),
    )
    sanitized["selectedSpecialConditions"] = sanitized_specials
    return sanitized, adjustments


def special_sets_for_gender(gender: Any) -> list[list[str]]:
    if is_male_gender(gender):
        return [["None"], ["Excessive Dryness"]]
    return [
        ["None"],
        ["Excessive Dryness"],
        ["Pregnant"],
        ["Breastfeeding"],
        ["Pregnant", "Breastfeeding"],
    ]
