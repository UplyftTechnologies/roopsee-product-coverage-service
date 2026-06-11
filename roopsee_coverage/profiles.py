from __future__ import annotations

from typing import Any

from .constants import QUIZ_OPTIONS


def representative_profiles(limit: int = 72) -> list[dict[str, Any]]:
    skin_types = QUIZ_OPTIONS["skinTypes"]
    ages = QUIZ_OPTIONS["ages"]
    face_pairs = [
        ["Acne"],
        ["Dark Spots"],
        ["Dryness"],
        ["Pigmentation"],
        ["Aging"],
        ["Sensitivity"],
        ["Large Pores"],
        ["Dullness"],
        ["Acne", "Dark Spots"],
        ["Acne", "Large Pores"],
        ["Dryness", "Sensitivity"],
        ["Pigmentation", "Dullness"],
        ["Aging", "Dryness"],
        ["Dark Spots", "Dullness"],
    ]
    lips_eye_pairs = [
        ["Dark circles"],
        ["Puffiness"],
        ["Dry Under Eye"],
        ["Sensitive Eye"],
        ["Chapped Lips"],
        ["Lip Pigment"],
        ["Dull Lips"],
        ["Dehydrated Lips"],
        ["Dark circles", "Puffiness"],
        ["Chapped Lips", "Lip Pigment"],
        ["Dry Under Eye", "Sensitive Eye"],
        ["Dull Lips", "Dehydrated Lips"],
    ]
    specials = [
        ["None"],
        ["Excessive Dryness"],
        ["Pregnant"],
        ["Breastfeeding"],
        ["Pregnant", "Breastfeeding"],
    ]

    profiles: list[dict[str, Any]] = []
    for skin_index, skin_type in enumerate(skin_types):
        for concern_index, concerns in enumerate(face_pairs):
            profiles.append({
                "age": ages[(skin_index + concern_index) % len(ages)],
                "selectedGender": "male" if concern_index % 2 == 0 else "female",
                "selectedSkinType": skin_type,
                "selectedFaceBodyConcerns": concerns,
                "selectedLipsEyesConcerns": [],
                "selectedSpecialConditions": specials[(skin_index + concern_index) % len(specials)],
            })
            if len(profiles) >= limit:
                return profiles

    for skin_index, skin_type in enumerate(skin_types):
        for concern_index, concerns in enumerate(lips_eye_pairs):
            profiles.append({
                "age": ages[(skin_index + concern_index) % len(ages)],
                "selectedGender": "male" if skin_index % 2 == 0 else "female",
                "selectedSkinType": skin_type,
                "selectedFaceBodyConcerns": [],
                "selectedLipsEyesConcerns": concerns,
                "selectedSpecialConditions": specials[(skin_index + concern_index) % len(specials)],
            })
            if len(profiles) >= limit:
                return profiles

    return profiles[:limit]
