# Roopsee Product Coverage Service

This repository contains the Roopsee product scoring playground used for catalog coverage review. It lets a reviewer choose a quiz profile and instantly see scored products, explanations, product details, and routine picks.

The project is intentionally simple for handover:

- Source sheets live in the repo.
- Python scripts regenerate the scored dataset.
- The frontend reads one generated JSON file.
- No database is required for this testing platform.

## Current Dataset

The current generated UI dataset contains **7,172 high-confidence topical skincare products**.

How that number is reached:

- **14,119 source products** were processed from the large source catalog.
- **7,290 products** passed the high-confidence scoring gate.
- **118 high-confidence rows** were then removed by the topical skincare filter.
- **7,172 products** are finally visible in the tool.

The topical filter exists because the source catalog can include oral supplements, capsules, tablets, ingestible powders, gummies, baby powder, and other non-topical rows. The UI should recommend products that are intended to be applied on skin, not every raw catalog item.

## What The Tool Does

For a selected user profile, the browser calculates and displays:

- Products sorted by score and ranking strength.
- Customer-facing product score from 0 to 100.
- Score range bins for quick coverage checking.
- Product detail modal with ingredients, evidence layers, confidence, and doctor-reference anchors.
- AM and PM routine suggestions using the best matching product types.

## Quick Start

Install dependencies if needed:

```bash
pip install -r requirements.txt
```

Run the local static app:

```bash
python3 app.py
```

Open:

```text
http://127.0.0.1:8020
```

For hosted deployments, the Flask entrypoint is:

```text
api/index.py
```

## Regenerate The Dataset

The checked-in source files are already the default inputs, so a normal rebuild is:

```bash
python3 tools/build_automated_scores.py
python3 tools/validate_v2_automated_logic.py
python3 tools/build_final_platform_dataset.py
```

The final browser dataset is written to:

```text
static/data/final_scored_products.json
```

Optional override environment variables:

- `ROOPSEE_USEFUL_PRODUCTS`: override the useful product ingredient sheet.
- `ROOPSEE_RETAILER_PRODUCTS`: override the retailer product export.
- `ROOPSEE_INGREDIENT_SCORES`: override the ingredient scoring master.
- `ROOPSEE_AUTO_OUTPUT_DIR`: override where intermediate automated scoring files are written.
- `ROOPSEE_AUTO_PAYLOAD`: override the intermediate automated scoring payload path.
- `ROOPSEE_FINAL_DATASET`: override the final generated frontend JSON path.

## Scoring Summary

The visible score is a rounded 0-100 product score for the selected profile. The system blends:

- Ingredient-sheet suitability score.
- Automated ingredient and formula score.
- Nearest doctor-reference product anchors.
- Same ingredient-family priors.
- Same product-type priors.
- Safety caps for sensitive conditions.
- Confidence caps when ingredient matching or source evidence is weaker.

The visible score is not the only sorting signal. The product list also uses a hidden rank-fusion score so products with stronger doctor-anchor support, cleaner ingredient matching, and better category fit can rank above products with similar visible scores.

For the full scoring explanation, see:

```text
docs/SCORING_METHODOLOGY.md
```

## Public Product Logic

These are the product-behavior rules that can be discussed externally:

- Skin type options are Oily, Dry, Normal, and Combination.
- Sensitivity is selected separately and maps to sensitive skin score columns.
- Age is shown as Teen or Adult.
- One skin concern is selected at a time.
- Male profiles cannot select Pregnancy or Breastfeeding.
- Serums are mainly scored by concern fit, with safety checks still applied.
- Cleansers are scored by skin type plus concern.
- Cleansers for wrinkles or anti-aging use skin type plus safety conditions rather than concern score.
- Moisturizers and sunscreens are mainly scored by skin type fit.
- Masks use concern plus skin-type fit.
- Pregnancy, breastfeeding, teen, sensitive, and excessive dryness profiles are handled cautiously through caps and modifiers.

## File-By-File Handover Map

| File | Why it exists |
| --- | --- |
| `.gitignore` | Keeps local caches, environment files, generated outputs, and temporary files out of Git while allowing required source sheets to stay tracked. |
| `.railwayignore` | Tells Railway which local files should not be uploaded during deployment. |
| `Procfile` | Start command for platforms that use Procfile-style deployment. |
| `README.md` | First-read handover guide for setup, regeneration, dataset meaning, and file purpose. |
| `api/index.py` | Flask deployment entrypoint. It serves the static frontend and health endpoint for hosted environments such as Render or Railway. |
| `app.py` | Small local server for opening the static testing UI without needing a database or full backend stack. |
| `data/Product details and score logic.xlsx` | Doctor-reviewed reference workbook used for calibration, validation, and comparison against known product scoring behavior. |
| `data/products.csv` | Product reference CSV retained for compatibility with the earlier doctor-score engine and validation workflows. |
| `data/source/useful_skin_bodycare_products.xlsx` | Main source sheet containing the products to score and their primary/secondary ingredients. |
| `data/source/retailer_products_rows.csv.gz` | Compressed retailer catalog export containing product metadata such as brand, price, URL, image, stock, and full ingredient text when available. |
| `data/source/roopsee_ingredient_scores_v3.xlsx` | Ingredient scoring master used to convert ingredient evidence into scores across concerns, skin types, ages, and special conditions. |
| `docs/SCORING_METHODOLOGY.md` | Detailed explanation of the scoring theory, formulas, gates, confidence logic, validation, and limitations. |
| `render.yaml` | Render deployment configuration. |
| `requirements.txt` | Python dependencies needed to run the app and rebuild datasets. |
| `roopsee_coverage/__init__.py` | Marks `roopsee_coverage` as a Python package. |
| `roopsee_coverage/constants.py` | Shared constants and default paths for the older doctor-sheet service. |
| `roopsee_coverage/engine.py` | Older deterministic recommendation engine built around doctor sheet scores; kept for reference compatibility and service testing. |
| `roopsee_coverage/loaders.py` | Reads doctor workbook and product CSV inputs for the package engine. |
| `roopsee_coverage/models.py` | Data models used by the package engine for profiles, products, scores, and routines. |
| `roopsee_coverage/profile_rules.py` | Profile-level helper rules such as pregnancy/gender validity and condition handling for the package engine. |
| `roopsee_coverage/profiles.py` | Generates supported profile combinations and quiz option structures for the package engine. |
| `roopsee_coverage/scoring.py` | Doctor-sheet-style profile scoring logic for the package engine. |
| `roopsee_coverage/server.py` | API server wrapper around the package engine for older service-style endpoints. |
| `roopsee_coverage/utils.py` | Shared text cleaning, normalization, and safe parsing helpers. |
| `static/index.html` | Browser UI shell for the testing platform. |
| `static/styles.css` | Visual styling for profile controls, product cards, score circles, bins, routine cards, and product detail modal. |
| `static/app.js` | Main frontend logic. It loads the generated JSON, applies profile scoring, sorts products, renders filters, opens product details, and builds routines. |
| `static/data/final_scored_products.json` | Generated final dataset consumed by the frontend. This is the file that makes the UI fast because it avoids parsing Excel files in the browser. |
| `tools/build_automated_scores.py` | Converts source sheets into an intermediate automated scoring payload by normalizing products, matching ingredients, and creating score vectors. |
| `tools/validate_v2_automated_logic.py` | Validates automated scoring against doctor-reviewed products and produces comparison evidence. |
| `tools/build_final_platform_dataset.py` | Builds the final UI dataset by combining automated scores, doctor anchors, product-type priors, family priors, confidence gates, and topical filtering. |
| `vercel.json` | Vercel deployment configuration if the project is hosted there instead of Render/Railway. |

## Files Usually Edited

Most changes should happen in one of these places:

- Update scoring theory or explanations in `docs/SCORING_METHODOLOGY.md`.
- Update source data by replacing files in `data/source/`.
- Update scoring generation in `tools/build_automated_scores.py` or `tools/build_final_platform_dataset.py`.
- Update frontend behavior in `static/app.js`.
- Update frontend look and feel in `static/styles.css`.

Do not manually edit `static/data/final_scored_products.json` for normal work. Regenerate it from the source sheets so the output remains reproducible.

## Important Caveat

This is an automated scoring and presentation tool for catalog testing and review. It is built to be auditable and conservative, but it is not a substitute for clinical or regulatory review. New low-confidence products and sensitive-condition edge cases should still be manually checked before production launch.
