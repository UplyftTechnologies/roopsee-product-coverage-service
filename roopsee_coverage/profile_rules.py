from __future__ import annotations

from typing import Any

from .utils import clean_text, norm_label


PREGNANCY_RELATED_CONDITIONS = {"pregnant", "breastfeeding"}


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


def sanitize_profile(profile: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    sanitized = dict(profile)
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
