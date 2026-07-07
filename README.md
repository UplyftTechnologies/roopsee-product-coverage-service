# Roopsee Product Coverage Service

Small workbook/CSV-backed tester for checking whether the live catalog has enough products for Roopsee quiz profiles. It exposes a basic frontend plus API endpoints that return products sorted by profile score.

## What It Uses

- `Product details and score logic.xlsx`: final doctor-backed score sheets.
- `products.csv`: normalized live catalog available to show on the site.
- `New products list 07072026.xlsx`: uploaded source workbook used to generate the current 384-product catalog from the `All products` sheet.
- Product UID matching is normalized, so `Roopsee/F/SU/13` and `Roopsee-F-SU-13` join correctly.

Only products present in `products.csv` are returned to the frontend.
If `products.csv` contains score columns, those rows are loaded as the authoritative face/body score rows for matching product UIDs.

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Set the two source-file paths before running:

```bash
export SCORE_WORKBOOK_PATH="/path/to/Product details and score logic.xlsx"
export PRODUCTS_CSV_PATH="/path/to/products.csv"
python app.py
```

Open:

```text
http://127.0.0.1:8020
```

Optional environment variables:

- `HOST`: defaults to `127.0.0.1`
- `PORT`: defaults to `8020`
- `SCORE_WORKBOOK_PATH`: final score workbook path
- `PRODUCTS_CSV_PATH`: live product catalog CSV path

## API

### `POST /api/recommend`

Input shape:

```json
{
  "age": "Under 16",
  "selectedGender": "male",
  "selectedSkinType": "Oily",
  "selectedFaceBodyConcerns": ["Acne"],
  "selectedLipsEyesConcerns": [],
  "selectedSpecialConditions": ["Excessive Dryness"]
}
```

Returns sorted products with doctor-sheet score, label, explanation, price, image, source score sheet, component scores, and a routine object.

The routine object chooses the highest scored product for each slot in the current profile:

- Premium AM/PM: score `90+` and effective price above `1000`.
- Value Fit AM/PM: best score with effective price below `1000`.
- AM slots: cleanser, moisturiser, sunscreen.
- PM slots: serum, moisturiser, cleanser.
- Weekly: best sheet mask and best clay mask by score, independent of price tier.
- If multiple products have the same score for a slot, any one tied product can be used.
- Serums become night-only for under-16, dry/sensitive, pregnancy, or breastfeeding profiles.

### `POST /api/routine`

Accepts the same profile input as `/api/recommend` and returns only the tiered AM/PM/weekly routine without the full product list.

### `GET /api/coverage?mode=all_pnc&top_n=3`

Runs the coverage audit for one of the supported modes:

- `all_pnc`: `4,032` rows using the final one-concern PnC formula.
- `skin_concern_type`: `112` rows for skin profile plus one concern.
- `with_special_conditions`: `1,008` rows for skin profile plus one concern plus special-condition state.
- `representative`: `72` rows for quick smoke testing only.

Use `row_limit=50` to calculate full summary counts but return only the weakest rows needed for the app preview.

### `GET /api/health`

Shows workbook/catalog counts and score coverage gaps.

## Frontend

The included frontend is served from `/` and lets you:

- choose one of the 8 sheet-backed skin profiles, one of the 14 July-workbook concerns, special conditions, age, and gender,
- submit the same JSON shape the app can send,
- view product cards sorted by score,
- filter returned products by score band, category, product type, and score sheet,
- preview the Roopsee storefront-style product cards without auth, cart, or checkout,
- see simple coverage colors: `Good` = green, `Present` = yellow, `Weak` = red.

## Code Structure

```text
app.py                         # Small service entrypoint
roopsee_coverage/
  constants.py                 # Sheet names, quiz options, mappings, thresholds
  engine.py                    # RecommendationEngine orchestration and coverage rows
  loaders.py                   # Workbook and CSV parsers
  models.py                    # ScoreRow dataclass
  profile_rules.py             # Gender-aware profile sanitization rules
  profiles.py                  # PnC grid and representative profile generation
  scoring.py                   # Score calculation, summaries, threshold counts
  server.py                    # HTTP routes and static frontend serving
  utils.py                     # Text/UID normalization helpers
tools/export_profile_coverage_workbook.py
static/index.html              # Basic frontend tester
notebooks/profile_score_coverage.ipynb
docs/FUNCTION_REFERENCE.md     # Every function explained for handoff/review
```

For a function-by-function walkthrough, see `docs/FUNCTION_REFERENCE.md`.

## Notebook

Open `notebooks/profile_score_coverage.ipynb` to generate a profile-by-profile audit table. It shows the number of matching products above:

- `90`
- `80`
- `70`
- `60`
- `50`

The notebook uses the same `RecommendationEngine` as the API, so frontend and notebook numbers stay aligned. It uses the full gender-free PnC grid, not the 72-profile quick sample.

## Final Coverage Workbook

Generate the final workbook with every valid gender-free profile combination:

```bash
python tools/export_profile_coverage_workbook.py \
  --score-workbook "/path/to/Product details and score logic.xlsx" \
  --products-csv "/path/to/products.csv" \
  --output "outputs/Roopsee_Full_Profile_Coverage_Final.xlsx"
```

The export follows this PnC formula:

```text
8C1 skin profile
× 14C1 concern combinations
× (3C0 + 3C1 + 3C2 + 3C3 + explicit None) special-condition states
× 4 age states
= 8 × 14 × 9 × 4
= 4,032 rows
```

The workbook also includes smaller subsheets for `Skin Concern Type` and `With Special Conditions`.

## Scoring Logic

The service does not invent new source scores. For each product, it reads only the applicable score columns from the doctor workbook or from score-bearing catalog rows:

- age fit score,
- concern score,
- skin-type score for face/body products,
- special-condition safety score.

The displayed product score is product-type aware:

- Serums average selected concerns, age, and special condition, but do not use skin-type scores. For serums, `Excessive Dryness` is skipped as a special-condition score; `Pregnancy`, `Breastfeeding`, and `None = 100` still apply.
- Cleansers average skin type, selected concerns, age, and special condition. If special condition is `None`, the special-condition component is `100`.
- Moisturisers and sunscreens ignore concern scores and average skin type, age, and special condition.
- Excessive Dryness preserves existing `-100/0/100` bucketed scores. If a raw Monika rating appears instead, it is converted as `<=50 => -100`, `51-84 => 0`, and `>=85 => 100`.
- Any applicable `-100` component is a hard blocker and the final product score stays `-100` instead of being averaged away.

Serums are night-only for under-16, dry/sensitive, pregnancy, or breastfeeding profiles. Retinoid products are night-only. If a retinoid product is suggested for Aging, under-16, dry/sensitive, or special-condition profiles, the response includes sandwich-method instructions: moisturiser before retinol and moisturiser again after retinol.

If `selectedGender` is `male`, pregnancy and breastfeeding conditions are ignored before scoring and are not generated in representative coverage profiles.

The final ranking is for product coverage testing, not a replacement for doctor review.

## Notes

The current repository includes the source workbook and normalized CSV used by the deployed tester. You can still override them locally with `SCORE_WORKBOOK_PATH` and `PRODUCTS_CSV_PATH`.
