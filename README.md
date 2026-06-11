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
  "selectedSpecialConditions": ["Pregnant", "Excessive Dryness", "Breastfeeding"]
}
```

Returns sorted products with score, label, explanation, price, image, source score sheet, and component scores.

### `GET /api/coverage?count=72&top_n=5`

Generates representative quiz profiles and reports whether each profile has enough high-scoring catalog products.

### `GET /api/health`

Shows workbook/catalog counts and score coverage gaps.

## Frontend

The included frontend is served from `/` and lets you:

- choose skin type, concerns, special conditions, age, and gender,
- submit the same JSON shape the app can send,
- view product cards sorted by score,
- filter returned products by score band, category, product type, and score sheet,
- run a representative profile coverage audit,
- see simple coverage colors: `Good` = green, `Present` = yellow, `Weak` = red.

## Code Structure

```text
app.py                         # Small service entrypoint
roopsee_coverage/
  constants.py                 # Sheet names, quiz options, mappings, thresholds
  engine.py                    # RecommendationEngine orchestration and coverage rows
  loaders.py                   # Workbook and CSV parsers
  models.py                    # ScoreRow dataclass
  profiles.py                  # Representative quiz profile generation
  scoring.py                   # Score calculation, summaries, threshold counts
  server.py                    # HTTP routes and static frontend serving
  utils.py                     # Text/UID normalization helpers
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

The notebook uses the same `RecommendationEngine` as the API, so frontend and notebook numbers stay aligned.

## Scoring Logic

The service combines:

- age fit score,
- concern score,
- skin-type score for face/body products,
- special-condition safety score,
- hard cap for pregnancy/breastfeeding conflicts when the sheet marks a product unsafe.

The final ranking is for product coverage testing, not a replacement for doctor review.

## Notes

The workbook and CSV data files are intentionally not committed because they may contain operational catalog data. Keep them in a local `data/` folder or pass their paths through environment variables.
