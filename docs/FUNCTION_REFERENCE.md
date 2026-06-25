# Roopsee Product Coverage Service Function Reference

This document explains every named Python function/method and every named frontend JavaScript function in this repo. It is meant for fast code review, mentor handoff, and future edits.

The service has four main layers:

1. Data loading: read `products.csv` and the doctor score workbook.
2. Profile rules: clean invalid quiz choices before scoring.
3. Scoring engine: calculate a displayed score by taking the rounded average of applicable doctor-sheet scores, while preserving `-100` hard blockers.
4. Frontend tester: let a tester change the quiz profile and preview the product cards users would see.

Core scoring principle:

```python
final_score = rounded_average_score(components)
```

This means the service reads only sheet-backed component scores, averages the applicable components, and rounds the displayed score to a whole number. If any component is `-100`, the final score remains `-100`.

## `app.py`

### Module entrypoint

`app.py` imports `main` from `roopsee_coverage.server` and calls it only when the file is run directly.

Why it exists:

- Keeps deployment simple with `python app.py`.
- Keeps real server logic inside `roopsee_coverage/server.py`.

Snippet:

```python
from roopsee_coverage.server import main

if __name__ == "__main__":
    main()
```

## `roopsee_coverage/models.py`

### `ScoreRow`

`ScoreRow` is a dataclass, not a custom function, but it is the central data shape for one product row from the doctor score workbook.

Fields:

- `source_sheet`: which score sheet the row came from, such as `Face and body`, `Lips`, or `Eyes`.
- `product_uid`: doctor-sheet product UID.
- `product_name`, `brand`, `category`, `product_type`: product metadata from the score workbook.
- `hero_ingredient`, `secondary_ingredients`: score-sheet ingredient context.
- `scores`: dictionary of score column name to numeric score.
- `source_row`: Excel row number for traceability.

Why it exists:

- Gives the scoring engine a clean, typed row instead of raw Excel cells.

## `roopsee_coverage/utils.py`

### `clean_text(value)`

Normalizes any raw cell/CSV value into a trimmed string.

What it does:

- Converts `None` to an empty string.
- Replaces non-breaking spaces.
- Collapses repeated whitespace.
- Strips leading/trailing spaces.

Why it exists:

- Excel/CSV data often contains invisible spacing differences.
- All later matching depends on stable text.

Example:

```python
clean_text("  Dark\u00a0Spots  ")  # "Dark Spots"
```

### `norm_key(value)`

Creates a compact matching key from product IDs or similar identifiers.

What it does:

- Lowercases the value.
- Removes everything except letters and numbers.

Why it exists:

- Lets `Roopsee/F/SU/13` match `Roopsee-F-SU-13`.

Example:

```python
norm_key("Roopsee/F/SU/13") == norm_key("Roopsee-F-SU-13")
```

### `norm_label(value)`

Creates a normalized label for quiz choices and column matching.

What it does:

- Lowercases the value.
- Replaces non-alphanumeric groups with spaces.
- Trims the result.

Why it exists:

- Makes labels like `Dark Spots`, `dark-spots`, and `dark spots` compare safely.

### `safe_float(value)`

Safely parses an Excel/CSV value into a float.

What it does:

- Returns `None` for empty values.
- Removes `%`.
- Returns `None` if conversion fails.

Why it exists:

- Score columns can have blanks or text.
- The scorer should only use real numeric scores.

### `first_image(raw)`

Extracts a product image URL from the CSV `images` field.

What it does:

- If the field contains a JSON list, returns the first image.
- If the field is already a plain URL, returns it directly.
- Returns empty string when unavailable.

Why it exists:

- Product CSV image data can arrive in different formats.

## `roopsee_coverage/loaders.py`

### `parse_catalog(products_csv)`

Reads `products.csv` and returns a normalized product catalog keyed by normalized product UID.

What it does:

- Opens the CSV with `utf-8-sig` to handle spreadsheet exports.
- Skips rows without `product_uid`.
- Stores product metadata used by cards and modals.
- Extracts the first image through `first_image`.
- Uses `norm_key(uid)` as the dictionary key.

Why it exists:

- Only products present in the live product CSV are shown to testers.
- It creates the catalog side of the product UID join.

Important output shape:

```python
products[norm_key(uid)] = {
    "product_uid": uid,
    "product_name": clean_text(row.get("product_name")),
    "mrp": clean_text(row.get("mrp")),
    "sp": clean_text(row.get("sp")),
    "image": first_image(row.get("images", "")),
}
```

### `parse_score_sheet(ws, source_sheet, header_row, data_start_row)`

Reads one worksheet from the doctor score workbook and converts each valid product row into a `ScoreRow`.

What it does:

- Reads column headers from `header_row`.
- Iterates product rows starting at `data_start_row`.
- Skips rows missing UID or product name.
- Converts numeric cells into the `scores` dictionary.
- Stores the original source sheet and row number.

Why it exists:

- Each score sheet has slightly different header placement.
- The scorer needs one consistent row model.

### `parse_catalog_score_rows(products_csv)`

Reads score columns directly from `products.csv` when the catalog CSV includes doctor-score columns.

What it does:

- Scans known face/body score columns such as `Acne`, `Dryness`, `Oily Score`, `Pregnancy Score`, and `Breastfeeling Score`.
- Converts numeric score values into the same `ScoreRow` model used by workbook rows.
- Uses the product catalog fields for product name, brand, hero ingredients, category, and product type.
- Adds a `+>25` alias when the CSV uses `Above 25`, so the existing age scoring map still works.

Why it exists:

- The `New products list 19062026.xlsx` rows have score columns but their Product UIDs do not overlap with the older workbook.
- Loading score-bearing catalog rows lets the tester recommend the latest 239 products alongside the older workbook-backed products without inventing scores or relying on mismatched old workbook rows.

### `load_score_rows(score_workbook, products_csv=None)`

Loads all score rows from the score workbook.

What it does:

- Opens the workbook with `openpyxl`.
- Parses the three known doctor score sheets:
  - `Face and body`
  - `Lips`
  - `Eyes`
- Also appends score-bearing product CSV rows when `products_csv` is supplied.
- Returns one combined list of `ScoreRow` objects.

Why it exists:

- The engine should not need to know Excel sheet row/header offsets.
- New catalog uploads can carry their own doctor score columns while still using the same scoring engine.

## `roopsee_coverage/profile_rules.py`

### `is_male_gender(gender)`

Checks if a selected gender value is male after label normalization.

Why it exists:

- Pregnancy and breastfeeding rules depend on gender.

### `sanitize_special_conditions(special_conditions, gender)`

Applies quiz-level safety/validity rules to selected special conditions.

What it does:

- Removes empty values.
- If gender is male, removes `Pregnant` and `Breastfeeding`.
- Records adjustment messages for removed conditions.
- If `None` is selected with another condition, removes `None`.
- Guarantees at least `["None"]` is returned.

Why it exists:

- Prevents impossible profiles like male plus pregnant from influencing scoring.
- Keeps the API transparent by returning adjustment warnings.

Snippet:

```python
if male_profile and key in PREGNANCY_RELATED_CONDITIONS:
    adjustments.append(f"Ignored {label} because selectedGender is male.")
    continue
```

### `sanitize_profile(profile)`

Returns a copy of the full quiz profile with special conditions sanitized.

What it does:

- Copies the incoming profile.
- Reads `selectedSpecialConditions`.
- Calls `sanitize_special_conditions`.
- Replaces the profile's special conditions with the sanitized list.
- Returns both the sanitized profile and adjustment messages.

Why it exists:

- The engine needs a scoring-safe profile while still preserving the original input for response traceability.

### `special_sets_for_gender(gender)`

Returns allowed representative special-condition sets for a given gender.

What it does:

- Male profiles get only `["None"]` or `["Excessive Dryness"]`.
- Other profiles can include pregnancy and breastfeeding states.

Why it exists:

- Representative profile generation should avoid invalid male pregnancy/breastfeeding cases.

## `roopsee_coverage/profiles.py`

### `_choice_sets(items, min_size=1, max_size=None)`

Builds combinations of selected items.

What it does:

- Uses `itertools.combinations`.
- Returns every list combination from `min_size` to `max_size`.

Why it exists:

- The quiz allows one or two concerns from a group.

Example:

```python
_choice_sets(["Acne", "Dryness"], max_size=2)
# [["Acne"], ["Dryness"], ["Acne", "Dryness"]]
```

### `concern_combinations()`

Builds every valid concern selection group.

What it does:

- Builds `8C1 + 8C2 = 36` Face & Body combinations.
- Builds `8C1 + 8C2 = 36` Lips & Eyes combinations.
- Returns `72` total concern states.

Why it exists:

- The final PnC grid depends on all allowed concern states.

### `gender_free_special_states()`

Builds all special-condition states without gender filtering.

What it does:

- Includes a true empty state: `No special selected (3C0)`.
- Includes every non-empty combination of:
  - `Excessive Dryness`
  - `Pregnant`
  - `Breastfeeding`
- Adds explicit `None`.
- Returns `9` states.

Why it exists:

- The final workbook requested gender removed from the PnC calculation.
- It still separates `3C0` from explicit `None` because that was part of the requested formula.

### `gender_free_special_combinations()`

Returns only the special-condition lists from `gender_free_special_states`.

Why it exists:

- Useful when only condition arrays are needed, not display labels.

### `all_profile_combinations(include_optional_age=True)`

Generates the full profile grid.

What it does:

- Iterates skin type.
- Iterates age states.
- Iterates all concern combinations.
- Iterates all special-condition states.
- Returns profile dictionaries ready for scoring.

Formula:

```text
4 skin types * 72 concern states * 9 special states * 4 age states = 10,368 profiles
```

Why it exists:

- This is the exhaustive coverage base for the final workbook.

### `skin_concern_type_combinations()`

Generates a smaller grid using only skin type plus concern group/set.

What it does:

- Uses `Not selected` age.
- Uses no special conditions.
- Returns `4 * 72 = 288` profiles.

Why it exists:

- Helpful for seeing base product coverage without age/special-condition complexity.

### `skin_concern_special_combinations()`

Generates a mid-size grid using skin type, concern group/set, and special-condition state.

What it does:

- Uses `Not selected` age.
- Includes all `9` special-condition states.
- Returns `4 * 72 * 9 = 2,592` profiles.

Why it exists:

- Helps isolate the effect of special conditions.

### `representative_profiles(limit=72)`

Creates a smaller smoke-test list of realistic profiles.

What it does:

- Cycles through skin types and ages.
- Uses curated face/body concern sets.
- Uses curated lips/eyes concern sets.
- Alternates gender safely.
- Stops when `limit` profiles have been created.

Why it exists:

- Fast testing without running the full PnC grid.
- Not used as the final mathematical truth.

## `roopsee_coverage/scoring.py`

### `age_column(age)`

Maps a quiz age label to the corresponding doctor-sheet column.

Example:

```python
age_column("Under 16")  # "<16"
```

Why it exists:

- Quiz labels and workbook column names are not identical.

### `is_sensitive_profile(profile)`

Detects if the selected profile should use sensitive skin score columns.

What it does:

- Normalizes face/body concerns.
- Normalizes lips/eyes concerns.
- Returns `True` when sensitivity or sensitive-eye concerns are present.

Why it exists:

- Face products use different skin-type score columns for sensitive profiles.

### `skin_column(skin_type, sensitive)`

Returns the correct skin-type score column for face/body products.

What it does:

- Defaults unknown skin type to `Normal`.
- Returns either `{Skin Type} Score` or `{Skin Type}+Sensitive Score`.

Examples:

```python
skin_column("Oily", False)  # "Oily Score"
skin_column("Dry", True)    # "Dry+Sensitive Score"
```

### `available_scores(row, headers)`

Returns all score values available on a row for a list of possible headers.

Why it exists:

- Some concerns map to multiple possible doctor-sheet columns.

Note:

- Current core scoring uses `first_available_score` more often because it needs the source column too.

### `first_available_score(row, headers)`

Returns the first `(header, score)` pair found in the row.

Why it exists:

- Concern mappings have fallback columns, and the explanation must say which column was used.

### `sheet_score(value)`

Formats numeric scores from the sheet.

What it does:

- Converts `90.0` to integer `90`.
- Keeps non-integer values if any exist.

Why it exists:

- The UI should show clean integer scores when the sheet has integer values.

### `rounded_average_score(components)`

Calculates the displayed product score from applicable component scores.

What it does:

- Reads every applicable component score.
- Returns `0` when no components are available.
- Averages the component scores.
- Rounds the average to the nearest whole number for display and ranking.

Why it exists:

- The tool should show one score per product/profile while still exposing all source component scores in product details.

### `map_special_columns(row, special_conditions)`

Maps selected special conditions to score columns on a product row.

What it handles:

- No special conditions or `None` uses the `None` score column.
- `Pregnant` maps to pregnancy safety columns.
- `Breastfeeding` maps to breastfeeding safety columns.
- `Excessive Dryness` maps to different columns depending on the sheet.

Why it exists:

- Special conditions are not one uniform column across all sheets.

Snippet:

```python
if "excessive dryness" in conditions:
    matched = first_available_score(row, ["Excessive Dryness score"])
    if not matched and row.source_sheet == LIPS_SHEET:
        matched = first_available_score(row, ["Dry Lips/Chapped Lips", "Dehydrated Lips"])
```

### `concern_headers_for_row(row, profile)`

Maps selected concerns to relevant score columns for the row's source sheet.

What it does:

- Face sheet uses `FACE_CONCERN_MAP`.
- Lips sheet uses `LIP_CONCERN_MAP`.
- Eyes sheet uses `EYE_CONCERN_MAP`.
- Ignores concerns that do not belong to the row's sheet.

Why it exists:

- A lip product should not be scored using acne columns.
- A face product should not be scored using dark-circle columns.

### `target_sheets(profile)`

Determines which score sheets are relevant for the selected profile.

What it does:

- Face/body concerns target `Face and body`.
- Lips concerns target `Lips`.
- Eye concerns target `Eyes`.
- If no concerns are selected, defaults to `Face and body`.

Why it exists:

- Keeps recommendation results focused on the selected concern group.

### `label_for_score(score)`

Converts a numeric score into a human-readable match label.

Labels:

- `>= 90`: `Excellent Match`
- `>= 80`: `Great Match`
- `>= 70`: `Good Match`
- `>= 50`: `Fits with Caution`
- Below that: `Not Recommended`

### `score_row_for_profile(row, catalog, profile)`

Scores one doctor-sheet row against one sanitized profile.

What it does:

1. Adds age score if the selected age maps to a sheet column.
2. Adds concern score components.
3. Adds a general `None` score when no concern pairs exist.
4. Adds skin-type score for face/body rows.
5. Adds special-condition scores.
6. Adds warnings for negative safety scores.
7. Uses the rounded average of component scores as the final score unless a component is `-100`, which becomes a hard blocker.
8. Builds a product response object using live catalog data first, then score-sheet fallbacks.

Why it exists:

- This is the core trust logic of the service.

Key snippet:

```python
final_score = rounded_average_score(components)
label = label_for_score(final_score)
```

Important output fields:

- `product_uid`
- `product_name`
- `brand_name`
- `category`
- `product_type`
- `score`
- `match_label`
- `explanation`
- `component_scores`
- `warnings`

### `summarize_results(results)`

Builds summary counts for a recommendation response.

What it does:

- Counts products by category.
- Counts products by product type.
- Counts score thresholds such as `>=90`, `>=80`, `>=70`, and `>=50`.
- Stores top and bottom score from the sorted result list.

Why it exists:

- The API and coverage workbook need quick product coverage summaries.

### `threshold_counts(results, thresholds=None)`

Counts how many products meet each score threshold.

Default thresholds:

```python
[90, 80, 70, 60, 50]
```

Output example:

```python
{
    "above_90": 3,
    "above_80": 9,
    "above_70": 18,
}
```

## `roopsee_coverage/engine.py`

### `RecommendationEngine.__init__(score_workbook, products_csv)`

Initializes the recommendation engine.

What it does:

- Loads the live catalog CSV.
- Loads all doctor score rows.
- Joins score rows to catalog products by normalized product UID.
- Tracks score rows that are not in the catalog.
- Tracks catalog products that have no score rows.

Why it exists:

- The rest of the app should ask the engine for recommendations, not repeatedly parse files.

### `RecommendationEngine.recommend(profile, limit=500)`

Returns scored products for one quiz profile.

What it does:

1. Sanitizes the profile.
2. Chooses relevant target sheets.
3. Scores every matched score row in the catalog.
4. Keeps the best score per product UID when a product appears in multiple sheets.
5. Sorts products by score descending, then category, then product name.
6. Caps return size between `1` and `1000`.
7. Returns profile, adjustments, summary, and product list.

Why it exists:

- This is the main API/business function used by `/api/recommend`, coverage exports, and notebook testing.

Key snippet:

```python
if existing is None or scored["score"] > existing["score"]:
    best_by_uid[catalog["product_uid"]] = scored
```

### `RecommendationEngine.health()`

Returns service health and data coverage metadata.

What it includes:

- Source workbook path.
- Source catalog path.
- Number of catalog products.
- Number of score rows.
- Score row counts by sheet.
- Catalog products missing score rows.
- Score-only UIDs not present in catalog.

Why it exists:

- Useful before trusting recommendation results.

### `RecommendationEngine.coverage(profiles, top_n=12)`

Runs coverage analysis across many profiles.

What it does:

- Calls `coverage_rows`.
- Counts profile statuses.
- Returns profile count, status counts, catalog count, and rows.

Why it exists:

- Backend support for coverage audits and export tooling.

Note:

- The frontend audit UI has been removed, but this backend function remains useful for notebooks/export scripts.

### `RecommendationEngine.coverage_rows(profiles, top_n=0)`

Builds row-level coverage results for a list of profiles.

What it does:

- Calls `recommend` for each profile.
- Counts products above thresholds.
- Computes a coverage status.
- Optionally includes top products.
- Returns one dictionary per profile.

Why it exists:

- This is the shared row builder for API coverage and workbook exports.

### `coverage_status(profile, summary)`

Classifies product coverage quality for one profile.

What it does:

- Uses lighter thresholds for lips/eyes-only profiles.
- Uses stricter thresholds for face/body profiles.
- Returns one of:
  - `Strong`
  - `Usable`
  - `Limited but usable`
  - `Coverage gap`

Why it exists:

- Converts raw product counts into a tester-readable coverage signal.

## `roopsee_coverage/server.py`

### `profiles_for_mode(mode, count=None)`

Chooses which profile grid to generate for coverage mode.

Supported modes:

- `skin_concern_type`
- `with_special_conditions`
- `representative`
- default full PnC via `all_profile_combinations`

Why it exists:

- Keeps API mode selection separate from profile-generation functions.

### `limit_coverage_rows(payload, row_limit=0)`

Sorts coverage rows by severity and optionally limits returned rows.

What it does:

- Sorts gaps first, strong rows last.
- Adds `total_rows`.
- Adds `returned_rows`.
- Slices rows when `row_limit > 0`.

Why it exists:

- Full coverage can be large, so previews can return weakest rows first.

### `read_request_json(handler)`

Reads a JSON request body from an HTTP handler.

What it does:

- Reads `Content-Length`.
- Returns `{}` for empty bodies.
- Decodes UTF-8 JSON.

Why it exists:

- Shared helper for POST routes.

### `send_json(handler, payload, status=200)`

Sends a JSON response with CORS headers.

What it does:

- Serializes payload using UTF-8.
- Sets JSON content type.
- Allows browser requests from frontend.
- Writes response bytes.

Why it exists:

- All API routes should respond consistently.

### `send_file(handler, path)`

Sends a static file from disk.

What it does:

- Returns 404 when file does not exist.
- Sets content type for HTML, image, CSS, JS, and SVG files.
- Writes the file bytes.

Why it exists:

- The Python service serves both API routes and the tester UI.

### `make_handler(engine)`

Creates an HTTP request handler class bound to a specific `RecommendationEngine`.

Why it exists:

- `BaseHTTPRequestHandler` classes do not naturally accept custom constructor arguments.
- This function closes over `engine` and returns a usable handler class.

### `Handler.do_OPTIONS()`

Responds to CORS preflight requests.

What it does:

- Sends `{"ok": true}` through `send_json`.

### `Handler.do_GET()`

Handles all GET routes.

Routes:

- `/` and `/index.html`: frontend page.
- `/api/health`: engine health.
- `/api/options`: quiz options, coverage modes, health.
- `/api/representative-profiles`: generated representative profiles.
- `/api/coverage`: coverage rows for a generated mode.
- Other paths: static files under `static/`.

Why it exists:

- Gives the browser static assets and simple read-only API endpoints.

### `Handler.do_POST()`

Handles JSON POST routes.

Routes:

- `/api/recommend`: score products for one quiz profile.
- `/api/coverage`: run coverage for provided profiles or selected mode.

Why it exists:

- Product recommendation requires profile JSON in the body.

### `Handler.log_message(format, *args)`

Overrides default HTTP logging.

What it does:

- Prints a concise request log line.

Why it exists:

- Keeps local debugging visible in the terminal.

### `main()`

Starts the HTTP server.

What it does:

- Reads environment variables:
  - `SCORE_WORKBOOK_PATH`
  - `PRODUCTS_CSV_PATH`
  - `PORT`
  - `HOST`
- Creates `RecommendationEngine`.
- Starts `ThreadingHTTPServer`.
- Prints health JSON on startup.

Why it exists:

- This is the service runtime entrypoint.

## `tools/export_profile_coverage_workbook.py`

### `band_counts(products)`

Counts products into non-overlapping score bins.

Bins:

- `90_100`
- `80_89`
- `70_79`
- `60_69`
- `50_59`
- `below_50`

Why it exists:

- The final Excel audit needs range bins, not only `above X` thresholds.

### `profile_row(profile_id, engine, profile)`

Creates one Excel row for one profile.

What it does:

- Calls `engine.recommend`.
- Counts score bins.
- Computes coverage status.
- Formats top 5 products.
- Stores both original profile JSON and sanitized scoring profile JSON.

Why it exists:

- Centralizes how profile audit rows are represented in the workbook.

### `style_sheet(ws, table_name)`

Applies formatting to a coverage worksheet.

What it does:

- Styles header row.
- Sets column widths.
- Enables wrapped text.
- Freezes header.
- Adds Excel table styling.

Why it exists:

- The generated workbook should be readable and filterable.

### `write_coverage_sheet(wb, sheet_name, table_name, profiles, engine)`

Writes one coverage worksheet.

What it does:

- Creates a sheet.
- Appends headers.
- Appends one row per profile using `profile_row`.
- Counts coverage statuses.
- Applies styling.
- Returns row/status summary.

Why it exists:

- Reused for full PnC, skin-concern type, and special-condition sheets.

### `write_summary(wb, sheet_results, assumptions)`

Writes the workbook `Summary` sheet.

What it does:

- Adds PnC formula and row counts.
- Adds source catalog metrics.
- Adds status counts for each generated sheet.

Why it exists:

- Gives reviewers the high-level result without opening every sheet.

### `write_assumptions(wb, assumptions)`

Writes the workbook `Assumptions` sheet.

What it does:

- Documents scoring basis.
- Documents PnC math.
- Documents age, concern, gender, and special-condition assumptions.
- Applies basic formatting.

Why it exists:

- Makes the generated Excel file self-explanatory.

### `export_workbook(score_workbook, products_csv, output_path)`

Generates the full profile coverage Excel workbook.

What it does:

1. Creates `RecommendationEngine`.
2. Builds full, reduced, and special-condition profile sets.
3. Writes coverage sheets.
4. Calculates PnC assumptions.
5. Writes summary and assumptions.
6. Saves the workbook.
7. Returns export metadata.

Why it exists:

- Produces the release-ready coverage audit workbook from the same scoring logic as the API.

### `main()`

CLI entrypoint for workbook export.

What it does:

- Parses `--score-workbook`, `--products-csv`, and `--output`.
- Calls `export_workbook`.
- Prints export result JSON.

Why it exists:

- Lets anyone regenerate the workbook from the terminal.

## `static/index.html` JavaScript

The frontend JavaScript powers the local Roopsee-style testing studio. It does not score products itself. It sends the selected quiz profile to `/api/recommend` and renders the API response.

### `escapeHtml(value)`

Escapes text before injecting it into HTML strings.

Why it exists:

- Protects the UI from broken HTML and basic injection issues when rendering product names, explanations, images, and labels.

### `payload()`

Builds the API request body from current UI state.

What it does:

- Sanitizes special-condition state.
- Reads age and gender from select fields.
- Reads skin type, concerns, and special conditions from frontend state.

Why it exists:

- Keeps the frontend request shape aligned with `/api/recommend`.

Snippet:

```javascript
return {
  age: document.querySelector("#ageSelect").value,
  selectedGender: document.querySelector("#genderSelect").value,
  selectedSkinType: state.selectedSkinType,
  selectedFaceBodyConcerns: state.selectedFaceBodyConcerns,
  selectedLipsEyesConcerns: state.selectedLipsEyesConcerns,
  selectedSpecialConditions: state.selectedSpecialConditions,
};
```

### `selectedGender()`

Reads the selected gender from the gender dropdown.

Why it exists:

- Shared by profile payload logic and frontend pregnancy/breastfeeding filtering.

### `availableSpecialConditions()`

Returns the special-condition options allowed for the selected gender.

What it does:

- For male, removes `Pregnant` and `Breastfeeding`.
- For other selections, returns all configured special conditions.

Why it exists:

- Prevents invalid profile choices in the UI before they reach the API.

### `sanitizeSpecialState()`

Cleans the frontend's selected special conditions.

What it does:

- Removes conditions no longer allowed after gender change.
- Defaults to `None` when nothing remains.
- Removes `None` when another real condition is selected.

Why it exists:

- Keeps UI state valid even when the tester changes gender mid-flow.

### `renderChips(containerId, items, isActive, onClick)`

Renders a group of selectable chip buttons.

What it does:

- Clears the target container.
- Creates one button per item.
- Applies `active` class based on `isActive`.
- Calls the supplied `onClick` behavior.
- Re-renders the UI and schedules recommendation refresh.

Why it exists:

- Skin type, concerns, and special conditions all use the same chip pattern.

### `toggleMaxTwo(list, item)`

Toggles an item in a selected list while keeping at most two selected items.

What it does:

- Removes item if already selected.
- Adds item if not selected.
- Keeps only the last two selected values.

Why it exists:

- The quiz allows max two concerns.

### `render()`

Renders the full left-side profile panel state.

What it does:

- Sanitizes special conditions.
- Renders skin type chips.
- Renders face/body concern chips.
- Renders lips/eyes concern chips.
- Renders special-condition chips.
- Shows active concern tab.
- Updates testing payload preview.
- Updates profile pill.

Why it exists:

- Central UI refresh function after state changes.

### `scoreRange(score)`

Maps a numeric product score to a score-range key.

Ranges:

- `90_100`
- `80_89`
- `70_79`
- `60_69`
- `50_59`
- `below50`

Why it exists:

- Used by summary bins and score-range filter.

### `scoreBand(score)`

Maps a numeric score to card color language.

Current bands:

- `>= 80`: `Good`, green.
- `>= 60`: `Present`, yellow.
- Below `60`: `Weak`, red.

Why it exists:

- Gives the tester a quick visual quality signal.

### `rangeLabel(key)`

Converts an internal score-range key to display text.

Example:

```javascript
rangeLabel("80_89") // "80-89"
```

### `formatNumber(value)`

Formats numbers using Indian locale grouping.

Why it exists:

- Summary counts are easier to read.

### `formatPrice(product)`

Returns a display price for a product.

What it does:

- Prefers `selling_price`.
- Falls back to `mrp`.
- Returns `Price unavailable` when neither exists.

Why it exists:

- Product cards and modal need consistent price formatting.

### `productImage(product, className = "")`

Returns product image HTML or a fallback block.

What it does:

- Uses product image URL when present.
- Adds lazy loading.
- Uses product name as alt text.
- Replaces broken images with an `R` fallback.

Why it exists:

- Product image data can be missing or broken in catalog exports.

### `metric(label, value)`

Builds one summary metric tile.

Why it exists:

- The top score-bin row uses repeated metric markup.

### `renderProductSummary(products)`

Renders the score-bin summary above the product grid.

What it does:

- Counts filtered products in each score range.
- Renders `Showing`, `90-100`, `80-89`, `70-79`, `60-69`, `50-59`, and `Below 50`.

Why it exists:

- The tester can quickly see product depth for the selected profile and active filters.

### `uniqueValues(products, field)`

Returns sorted unique values for one product field.

Why it exists:

- Builds dynamic category, product type, and sheet filters from returned products.

### `fillFilter(selectId, values, allLabel)`

Populates one select filter.

What it does:

- Preserves previous selected value if still valid.
- Adds an `all` option.
- Adds one option per unique value.

Why it exists:

- Avoids hardcoding filter options.

### `populateFilters(products)`

Populates all product filters from current product results.

Filters:

- Category.
- Product type.
- Source score sheet.

### `filterProducts(products)`

Applies all selected product filters.

What it filters by:

- Score range.
- Category.
- Product type.
- Source sheet.

Why it exists:

- Lets testers inspect product availability by category/type without new API calls.

### `renderFilteredProducts()`

Renders the currently filtered result set.

What it does:

- Calls `filterProducts`.
- Updates summary bins.
- Renders product cards.

Why it exists:

- Shared handler for score/category/type/sheet filter changes.

### `renderProducts(products)`

Renders the product card grid.

What it does:

- Shows an empty state when no products match.
- Creates a 3-column product grid on desktop.
- Renders image, score badge, product name, metadata, price, explanation, tags, and detail button.
- Attaches click handlers that open the product detail modal.

Why it exists:

- This is the storefront-like product preview.

Snippet:

```javascript
<article class="product-card" data-product-uid="${escapeHtml(product.product_uid)}">
  <div class="product-image-wrap">
    ${productImage(product)}
    <div class="score-badge score-${band.className}">
      <div>${escapeHtml(product.score)}<small>${band.label}</small></div>
    </div>
  </div>
</article>
```

### `shortExplanation(explanation)`

Shortens long product explanations for cards.

What it does:

- Keeps full explanation in the modal.
- Truncates card copy after 118 characters.

Why it exists:

- Cards stay compact while the modal remains detailed.

### `updateProfilePill()`

Updates the small profile summary in the results header.

What it shows:

- Selected skin type.
- Selected concerns.

### `recommend()`

Calls the backend recommendation API and renders results.

What it does:

- Shows filters.
- Displays a loading state.
- POSTs `payload()` to `/api/recommend?limit=500`.
- Stores returned products in `currentProducts`.
- Stores `total_matches`.
- Populates filters.
- Updates subtitle.
- Renders filtered products.

Why it exists:

- Main bridge between frontend UI and sheet-backed backend scoring.

### `scheduleRecommend()`

Debounces automatic recommendation refresh.

What it does:

- Clears pending refresh timer.
- Waits 260ms.
- Calls `recommend()` only if at least one concern is selected.

Why it exists:

- Keeps the UI responsive while avoiding excessive API calls during chip clicking.

### `productByUid(uid)`

Finds the currently loaded product with a matching UID.

Why it exists:

- The modal opens from card click and needs the full product object.

### `openProductModal(uid)`

Renders and opens the product detail modal.

What it does:

- Finds the product by UID.
- Calculates score band.
- Renders warnings.
- Renders component score list.
- Renders image, product name, brand, category, type, price, size, use, hero ingredient, source sheet, explanation, and secondary ingredients.
- Wires the close button.

Why it exists:

- Mirrors the product detail view testers expect from the Roopsee platform, without cart/auth/checkout.

### `closeProductModal()`

Closes the product modal.

What it does:

- Removes the `open` class.
- Sets `aria-hidden` to `true`.

## Frontend inline event callbacks

These are anonymous callbacks rather than named functions, but they are important to understand UI behavior.

### Tab click callback

Attached to `.tab` buttons.

What it does:

- Switches `state.activeTab`.
- Updates active tab styling.
- Calls `render()`.

### Age select callbacks

Attached to `#ageSelect`.

What they do:

- One callback calls `render`.
- One callback calls `scheduleRecommend`.

Why both exist:

- Age updates the payload preview immediately and refreshes product results automatically.

### Gender select callback

Attached to `#genderSelect`.

What it does:

- Sanitizes special conditions.
- Re-renders UI.
- Schedules recommendation refresh.

Why it exists:

- Changing gender can remove pregnancy/breastfeeding from valid choices.

### Refresh button callback

Attached to `#matchButton`.

What it does:

- Calls `recommend()`.

### Filter change callbacks

Attached to score, category, type, and sheet filters.

What they do:

- Call `renderFilteredProducts()`.

Why it exists:

- Filters are client-side over the current API result set.

### Modal backdrop callback

Attached to `#productModal`.

What it does:

- Closes the modal only when the backdrop itself is clicked.

### Escape key callback

Attached to `document`.

What it does:

- Closes the modal when the user presses `Escape`.

### Initial boot calls

At page load:

```javascript
render();
recommend();
```

Why it exists:

- The tester loads with a default profile and immediately shows product recommendations.

## Important code paths

### Recommendation path

```text
Browser state
-> payload()
-> POST /api/recommend
-> Handler.do_POST()
-> RecommendationEngine.recommend()
-> score_row_for_profile()
-> summarize_results()
-> recommend() in frontend receives JSON
-> renderFilteredProducts()
-> renderProducts()
```

### Workbook export path

```text
python tools/export_profile_coverage_workbook.py
-> main()
-> export_workbook()
-> all_profile_combinations()
-> write_coverage_sheet()
-> profile_row()
-> RecommendationEngine.recommend()
-> workbook saved to outputs/
```

### Product detail modal path

```text
Product card click
-> openProductModal(product_uid)
-> productByUid(product_uid)
-> render detail fields from currentProducts
-> closeProductModal() on close/backdrop/Escape
```

## What is intentionally not scored in the frontend

The frontend does not calculate product scores. It only:

- Builds profile input.
- Calls the API.
- Filters returned products client-side.
- Displays score bins, cards, and product details.

All scoring remains backend-driven from the Excel workbook and CSV catalog.
