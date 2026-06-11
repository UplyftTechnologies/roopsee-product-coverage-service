# Roopsee Product Coverage Service

Small workbook/CSV-backed tester for checking whether the live catalog has enough products for Roopsee quiz profiles. It exposes a basic frontend plus API endpoints that return products sorted by profile score.

## What It Uses

- `Product details and score logic.xlsx`: final doctor-backed score sheets.
- `products.csv`: live products available to show on the site.
- Product UID matching is normalized, so `Roopsee/F/SU/13` and `Roopsee-F-SU-13` join correctly.

Only products present in `products.csv` are returned to the frontend.

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
  "selectedFaceBodyConcerns": ["Acne", "Dark Spots"],
  "selectedLipsEyesConcerns": [],
  "selectedSpecialConditions": ["Excessive Dryness"]
}
```

Returns sorted products with doctor-sheet score, label, explanation, price, image, source score sheet, and component scores.

### `GET /api/coverage?mode=all_pnc&top_n=3`

Runs the coverage audit for one of the supported modes:

- `all_pnc`: `10,368` rows using the final PnC formula.
- `skin_concern_type`: `288` rows for skin type plus concern group/set.
- `with_special_conditions`: `2,592` rows for skin type plus concern group/set plus special-condition state.
- `representative`: `72` rows for quick smoke testing only.

Use `row_limit=50` to calculate full summary counts but return only the weakest rows needed for the app preview.

### `GET /api/health`

Shows workbook/catalog counts and score coverage gaps.

## Frontend

The included frontend is served from `/` and lets you:

- choose skin type, concerns, special conditions, age, and gender,
- submit the same JSON shape the app can send,
- view product cards sorted by score,
- filter returned products by score band, category, product type, and score sheet,
- run the same PnC coverage modes used by the final workbook,
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
```

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
4C1 skin profile
× (2 × (8C1 + 8C2)) concern combinations
× (3C0 + 3C1 + 3C2 + 3C3 + explicit None) special-condition states
× 4 age states
= 4 × 72 × 9 × 4
= 10,368 rows
```

The workbook also includes smaller subsheets for `Skin Concern Type` and `With Special Conditions`.

## Scoring Logic

The service does not invent weighted or decimal scores. For each product, it reads only the applicable score columns from the doctor workbook:

- age fit score,
- concern score,
- skin-type score for face/body products,
- special-condition safety score.

The displayed product score is the lowest applicable doctor-sheet score for the selected profile. This keeps the ranking conservative: if a product is weak or unsafe for any selected criterion, it cannot be hidden by a higher score from another column.

If `selectedGender` is `male`, pregnancy and breastfeeding conditions are ignored before scoring and are not generated in representative coverage profiles.

The final ranking is for product coverage testing, not a replacement for doctor review.

## Notes

The workbook and CSV data files are intentionally not committed because they may contain operational catalog data. Keep them in a local `data/` folder or pass their paths through environment variables.
