from __future__ import annotations

from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
BASE_DIR = PACKAGE_DIR.parent
STATIC_DIR = BASE_DIR / "static"

DEFAULT_SCORE_WORKBOOK = str(BASE_DIR / "data" / "Product details and score logic.xlsx")
DEFAULT_PRODUCTS_CSV = str(BASE_DIR / "data" / "products.csv")

FACE_SHEET = "Face and body"
LIPS_SHEET = "Lips"
EYES_SHEET = "Eyes"

QUIZ_OPTIONS = {
    "skinTypes": [
        "Oily",
        "Dry",
        "Normal",
        "Combination",
    ],
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
    ],
    "lipsEyesConcerns": [],
    "specialConditions": ["Excessive Dryness", "Pregnant", "Breastfeeding", "None"],
    "ages": ["Teen", "Adult"],
    "genders": ["male", "female", "other", "prefer not to say"],
}

AGE_COLUMN_MAP = {
    "teen": "<16",
    "under 16": "<16",
    "below 16": "<16",
    "<16": "<16",
    "16": "<16",
    "17-25": "17-25",
    "17 - 25": "17-25",
    "17 25": "17-25",
    "above 25": "+>25",
    "over 25": "+>25",
    "25+": "+>25",
    "+>25": "+>25",
}

AGE_COLUMN_GROUP_MAP = {
    "teen": ["<16"],
    "under 16": ["<16"],
    "below 16": ["<16"],
    "<16": ["<16"],
    "16": ["<16"],
    "adult": ["17-25", "+>25"],
    "17-25": ["17-25"],
    "17 - 25": ["17-25"],
    "17 25": ["17-25"],
    "above 25": ["+>25"],
    "over 25": ["+>25"],
    "25+": ["+>25"],
    "+>25": ["+>25"],
}

FACE_CONCERN_MAP = {
    "acne": ["Acne"],
    "body acne": ["Body Acne"],
    "dryness": ["Dryness"],
    "open pores": ["Open Pores"],
    "large pores": ["Open Pores"],
    "uneven skin tone": ["Uneven Skin Tone"],
    "dark spots pigmentation": ["Dark Spots/Pigmentation"],
    "dark spots": ["Dark Spots/Pigmentation"],
    "pigmentation": ["Dark Spots/Pigmentation"],
    "melasma": ["Melasma"],
    "barrier repair": ["Barrier Repair"],
    "comedones": ["Comedones"],
    "wrinkles fine lines": ["Wrinkles/Fine lines"],
    "aging": ["Wrinkles/Fine lines"],
    "redness irritation": ["Redness/Irritation"],
    "sensitivity": ["Redness/Irritation"],
    "dehydration": ["Dehydration"],
    "dullness": ["Dullness"],
    "tanning": ["Tanning"],
}

LIP_CONCERN_MAP = {
    "chapped lips": ["Dry Lips/Chapped Lips"],
    "dry lips": ["Dry Lips/Chapped Lips"],
    "lip pigment": ["Lip Pigmentation"],
    "lip pigmentation": ["Lip Pigmentation"],
    "dull lips": ["Dull Looking lips"],
    "dehydrated lips": ["Dehydrated Lips"],
}

EYE_CONCERN_MAP = {
    "dark circles": ["Dark circles"],
    "puffiness": ["Puffiness/Eye Bags"],
    "dry under eye": ["Dry/Dehydrated Under Eyes"],
    "dry under eyes": ["Dry/Dehydrated Under Eyes"],
    "sensitive eye": ["Sensitive/Irritated Eye area"],
    "sensitive eyes": ["Sensitive/Irritated Eye area"],
}

SCORE_LABELS = [
    (90, "Excellent Match"),
    (80, "Great Match"),
    (70, "Good Match"),
    (50, "Fits with Caution"),
    (-999, "Not Recommended"),
]

THRESHOLDS = [90, 80, 70, 60, 50]
