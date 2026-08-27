# Roopsee Product Coverage Service

This repo contains the handover-ready Roopsee scoring playground: a lightweight frontend, a generated scored product dataset, and the scripts/docs that explain how product scores are produced.

## What Is Included

- `static/`: the browser UI used to test profiles, product scores, details, and routines.
- `static/data/final_scored_products.json`: generated high-confidence scored product dataset.
- `tools/build_automated_scores.py`: creates ingredient-level automated scores from source sheets.
- `tools/validate_v2_automated_logic.py`: validates automated scoring against doctor-reviewed products.
- `tools/build_final_platform_dataset.py`: builds the final frontend dataset.
- `docs/SCORING_METHODOLOGY.md`: non-technical and technical explanation of the scoring system.
- `data/Product details and score logic.xlsx` and `data/products.csv`: doctor-reference data used for validation/calibration.

## Current Dataset

The generated browser dataset currently contains 7,172 high-confidence topical skincare products, filtered from 14,119 source products.

## How To Run

From this repo:

```bash
python3 app.py
```

Open:

```text
http://127.0.0.1:8020
```

For Render/Railway-style hosting, the Flask entrypoint is `api/index.py`.

## How To Regenerate Scores

Place the latest source files locally, then run:

```bash
python3 tools/build_automated_scores.py
python3 tools/validate_v2_automated_logic.py
python3 tools/build_final_platform_dataset.py
```

The scripts default to these filenames in `~/Downloads`, and each path can be overridden with environment variables:

- `ROOPSEE_USEFUL_PRODUCTS`
- `ROOPSEE_RETAILER_PRODUCTS`
- `ROOPSEE_INGREDIENT_SCORES`
- `ROOPSEE_AUTO_OUTPUT_DIR`
- `ROOPSEE_FINAL_DATASET`

## Scoring Summary

The visible score is a rounded 0-100 product score for the selected profile. The platform blends:

- Ingredient-sheet score
- Calibrated automated ingredient score
- Nearest doctor-reference product anchors
- Same ingredient-family priors
- Same product-type priors

The product list is sorted using a hidden rank-fusion score so the most relevant products appear first, even when visible scores are close.

For the full non-technical and technical scoring explanation, see:

```text
docs/SCORING_METHODOLOGY.md
```

## Current Public Rules

- Skin type supports Oily, Dry, Normal, and Combination.
- Sensitive is selected separately and maps to the sensitive skin score columns.
- Age is Teen or Adult.
- One concern is selected at a time from the expanded concern list.
- Male profiles cannot select Pregnancy or Breastfeeding.
- Serums use concern fit as the main score signal.
- Cleansers use skin type plus concern, except wrinkles/anti-aging cleansers use skin type plus safety conditions.
- Moisturizers and sunscreens use skin type as the main fit signal.
- Masks use concern plus skin-type fit.
- Special conditions are treated as safety modifiers.

## Important Caveat

This is an automated scoring and presentation tool. It is useful for catalog coverage, testing, and review, but low-confidence products should still be manually checked before production launch.
