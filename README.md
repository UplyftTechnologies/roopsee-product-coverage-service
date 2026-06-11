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
- run a representative profile coverage audit,
- see simple coverage colors: `Good` = green, `Present` = yellow, `Weak` = red.

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
