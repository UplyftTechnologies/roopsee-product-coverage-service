# Roopsee Final Match Platform

This is a local presentation platform for testing Roopsee product recommendations across the full large product catalog.

## What It Uses

- Large product scores from `useful_skin_bodycare_products.xlsx`
- Retailer metadata from `retailer_products_rows.csv`
- Ingredient score rules from `roopsee_ingredient_scores_v3.xlsx`
- Doctor-reference calibration from the existing doctor-verified Roopsee coverage service

The generated browser dataset is:

```text
data/final_scored_products.json
```

It currently contains 7,172 high-confidence topical skincare products, filtered from 14,119 source products.

## How To Run

From this repo:

```bash
python3 app.py
```

Open:

```text
http://127.0.0.1:8020
```

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
