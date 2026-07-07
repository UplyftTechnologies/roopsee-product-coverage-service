from __future__ import annotations

from itertools import combinations
from typing import Any

from .constants import QUIZ_OPTIONS
from .profile_rules import special_sets_for_gender

OPTIONAL_AGE_LABEL = "Not selected"
REAL_SPECIAL_CONDITIONS = ["Excessive Dryness", "Pregnant", "Breastfeeding"]
NO_SPECIAL_SELECTED_LABEL = "No special selected (3C0)"


def _choice_sets(items: list[str], min_size: int = 1, max_size: int | None = None) -> list[list[str]]:
    max_size = max_size or len(items)
    sets: list[list[str]] = []
    for size in range(min_size, max_size + 1):
        sets.extend([list(combo) for combo in combinations(items, size)])
    return sets


def concern_combinations() -> list[dict[str, list[str] | str]]:
    face_sets = _choice_sets(QUIZ_OPTIONS["faceBodyConcerns"], max_size=1)
    return [
        {"concern_group": "Face & Body", "face_body_concerns": concerns, "lips_eyes_concerns": []}
        for concerns in face_sets
    ]


def gender_free_special_states() -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = [
        {"special_state": NO_SPECIAL_SELECTED_LABEL, "special_conditions": []}
    ]
    for conditions in _choice_sets(REAL_SPECIAL_CONDITIONS):
        states.append({
            "special_state": ", ".join(conditions),
            "special_conditions": conditions,
        })
    states.append({"special_state": "None", "special_conditions": ["None"]})
    return states


def gender_free_special_combinations() -> list[list[str]]:
    return [state["special_conditions"] for state in gender_free_special_states()]


def all_profile_combinations(include_optional_age: bool = True) -> list[dict[str, Any]]:
    ages = QUIZ_OPTIONS["ages"] + ([OPTIONAL_AGE_LABEL] if include_optional_age else [])
    profiles: list[dict[str, Any]] = []
    for skin_type in QUIZ_OPTIONS["skinTypes"]:
        for age in ages:
            for concern_set in concern_combinations():
                for special_state in gender_free_special_states():
                    profiles.append({
                        "age": age,
                        "selectedGender": "",
                        "selectedSkinType": skin_type,
                        "selectedFaceBodyConcerns": concern_set["face_body_concerns"],
                        "selectedLipsEyesConcerns": concern_set["lips_eyes_concerns"],
                        "selectedSpecialConditions": special_state["special_conditions"],
                        "specialConditionState": special_state["special_state"],
                        "concernGroup": concern_set["concern_group"],
                    })
    return profiles


def skin_concern_type_combinations() -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for skin_type in QUIZ_OPTIONS["skinTypes"]:
        for concern_set in concern_combinations():
            profiles.append({
                "age": OPTIONAL_AGE_LABEL,
                "selectedGender": "",
                "selectedSkinType": skin_type,
                "selectedFaceBodyConcerns": concern_set["face_body_concerns"],
                "selectedLipsEyesConcerns": concern_set["lips_eyes_concerns"],
                "selectedSpecialConditions": [],
                "specialConditionState": "Not considered",
                "concernGroup": concern_set["concern_group"],
            })
    return profiles


def skin_concern_special_combinations() -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for skin_type in QUIZ_OPTIONS["skinTypes"]:
        for concern_set in concern_combinations():
            for special_state in gender_free_special_states():
                profiles.append({
                    "age": OPTIONAL_AGE_LABEL,
                    "selectedGender": "",
                    "selectedSkinType": skin_type,
                    "selectedFaceBodyConcerns": concern_set["face_body_concerns"],
                    "selectedLipsEyesConcerns": concern_set["lips_eyes_concerns"],
                    "selectedSpecialConditions": special_state["special_conditions"],
                    "specialConditionState": special_state["special_state"],
                    "concernGroup": concern_set["concern_group"],
                })
    return profiles


def representative_profiles(limit: int = 72) -> list[dict[str, Any]]:
    skin_types = QUIZ_OPTIONS["skinTypes"]
    ages = QUIZ_OPTIONS["ages"]
    face_pairs = [[concern] for concern in QUIZ_OPTIONS["faceBodyConcerns"]]
    profiles: list[dict[str, Any]] = []
    for skin_index, skin_type in enumerate(skin_types):
        for concern_index, concerns in enumerate(face_pairs):
            gender = "male" if concern_index % 2 == 0 else "female"
            specials = special_sets_for_gender(gender)
            profiles.append({
                "age": ages[(skin_index + concern_index) % len(ages)],
                "selectedGender": gender,
                "selectedSkinType": skin_type,
                "selectedFaceBodyConcerns": concerns,
                "selectedLipsEyesConcerns": [],
                "selectedSpecialConditions": specials[(skin_index + concern_index) % len(specials)],
            })
            if len(profiles) >= limit:
                return profiles

    return profiles[:limit]
