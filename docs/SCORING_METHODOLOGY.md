# Roopsee Product Scoring Methodology

This document explains how the Roopsee product coverage tool scores products for a user's skin profile.

It is written for both non-technical and technical readers. The first half explains the logic in plain language. The later sections include formulas, safety rules, and implementation details so the method can be reviewed, improved, and defended.

## 1. What The System Is Trying To Do

The goal is simple:

For a selected skin profile, show the products that are most suitable, safest, and most relevant, ordered by a clear score.

The system does not treat all products equally. A cleanser, serum, moisturizer, sunscreen, mask, and toner should not be scored with the same formula because users expect different benefits from each product type.

For example:

- A serum should be judged mainly by whether it addresses the selected concern.
- A moisturizer should be judged mainly by whether it suits the skin type.
- A sunscreen should be judged mainly by skin compatibility and photo-protection relevance.
- A cleanser for acne or open pores should get credit for cleansing and acne/pore-support ingredients.
- A cleanser for wrinkles should not be over-rewarded just because it contains an anti-aging keyword, because cleansers are wash-off products.

The platform therefore uses a hybrid scoring system:

- Ingredient-level scoring tells us what a product is likely to do.
- Doctor-verified reference products keep the automated score grounded.
- Safety gates prevent unsuitable recommendations.
- Confidence labels tell us how much we should trust an automated result.
- A hidden ranking score sorts products when many products have similar visible scores.

## 2. Current Dataset Snapshot

The current generated platform dataset contains:

- Source products processed: 14,119
- High-confidence products before topical-only filtering: 7,290
- Non-topical high-confidence products excluded: 118
- Final visible platform products: 7,172
- Doctor-reference products: 384
- Current final confidence filter: High only

Product type coverage:

- Serums: 1,713
- Moisturizers: 2,341
- Cleansers: 1,076
- Sunscreens: 255
- Masks: 1,062
- Toners: 510
- Other products: 215

These numbers come from the generated frontend dataset and can change whenever the source sheets are regenerated.

## 3. Source Files Used

The scoring system uses three main source files:

- `data/source/useful_skin_bodycare_products.xlsx`: contains product names, primary ingredients, and secondary ingredients.
- `data/source/retailer_products_rows.csv.gz`: compressed retailer export with brand, MRP, selling price, image, URL, rating, stock, SKU information, and source INCI text when available.
- `data/source/roopsee_ingredient_scores_v3.xlsx`: ingredient-level suitability scores across skin concerns, skin types, age, and special conditions.

The system also uses the existing doctor-scored Roopsee products as a reference set. These are not used as blind copies for new products. They are used as anchors, meaning the system checks whether a new product behaves similarly to known doctor-reviewed products.

## 4. User Profile Inputs

The current quiz profile includes:

- Skin type: Oily, Dry, Normal, or Combination
- Sensitive skin: Yes or No
- Age: Teen or Adult
- Gender: female, male, other, or prefer not to say
- Skin concern: one concern selected at a time
- Special conditions: Excessive Dryness, Pregnant, Breastfeeding, or None

The concern options are:

- Acne
- Body Acne
- Dryness
- Open Pores
- Uneven Skin Tone
- Dark Spots/Pigmentation
- Melasma
- Barrier Repair
- Comedones
- Wrinkles/Fine lines
- Redness/Irritation
- Dehydration
- Dullness
- Tanning
- None

Important profile rules:

- Gender is not used as a beauty score factor.
- Male profiles cannot select Pregnancy or Breastfeeding.
- Sensitive is handled separately from skin type.
- Internally, Oily plus Sensitive becomes `Oily+Sensitive Score`, Dry plus Sensitive becomes `Dry+Sensitive Score`, and so on.
- Teen maps to the `<16` safety column.
- Adult means no teen safety cap is added in the live profile scorer.
- Pregnancy maps to the `Pregnancy Score` column.
- Breastfeeding maps to the sheet column currently named `Breastfeeling Score`.
- Special conditions can be multi-selected, except `None` acts as the no-condition state.
- If the user selects `None` for special conditions, the special-condition score is treated as 100.

## 5. The Score Columns

Each product eventually receives a score vector. A score vector means the product has separate scores for each possible profile dimension.

The columns include:

- Age: `<16`, `17-25`, `+>25`
- Concerns: Acne, Body Acne, Dryness, Open Pores, Uneven Skin Tone, Dark Spots/Pigmentation, Melasma, Barrier Repair, Comedones, Wrinkles/Fine lines, Redness/Irritation, Dehydration, Dullness, Tanning
- Skin type: Oily, Oily+Sensitive, Dry, Dry+Sensitive, Normal, Normal+Sensitive, Combination, Combination+Sensitive
- Special conditions: Excessive Dryness, Pregnancy, Breastfeeding, None

The displayed score is not just one stored value. It is calculated live from the selected profile using the relevant columns for that product type.

## 6. Score Meaning

The visible product score is shown from 0 to 100, with `-100` used internally as a hard block.

Human meaning:

- 90-100: strongest match
- 80-89: strong/good match
- 70-79: usable but not the strongest option
- 50-69: caution or weaker fit
- 1-49: poor fit
- `-100`: not suggested for that profile

In the UI, the score is shown with a color cue:

- Green: good score
- Yellow: medium score
- Red/blocked: weak, poor, or not suggested

## 7. Ingredient Matching Logic

Before scoring a product, the system must understand its ingredients.

Ingredient names in real catalog data are messy. They may contain spelling variants, percentages, brackets, marketing text, or combined phrases like `AHA + BHA`.

The system therefore tries to match ingredients in this order:

1. Exact match to the ingredient score master.
2. Curated alias match, such as a known alternate name.
3. Strong normalized match, such as singular/plural cleanup or spelling normalization.
4. Ingredient-family match, such as recognizing that salicylic acid belongs to acne/pore support.
5. Conservative fallback ingredient creation if no reliable match exists.

The system does not blindly ignore missing ingredients. If an ingredient cannot be matched, it is either:

- marked as non-ingredient text and skipped from scoring, or
- assigned a conservative fallback family and flagged for review.

Examples of ingredient families:

- Acne and pore actives
- Exfoliants
- Brightening and pigmentation actives
- Retinoids and anti-aging actives
- Hydration and humectants
- Barrier repair
- Soothing ingredients
- Sunscreen filters
- Emollients and occlusives
- Fragrance or irritation-risk ingredients

This helps the system handle new products even when the doctor has not scored them manually yet.

## 8. Primary And Secondary Ingredient Weighting

Products may have primary ingredients and secondary ingredients.

The general formula is:

```text
ingredient_column_score =
  primary_ingredient_group_score * primary_weight
  + secondary_ingredient_group_score * secondary_weight
```

The current weights are:

- Serum: 80% primary ingredients, 20% secondary ingredients
- Cleanser: 50% primary ingredients, 50% secondary ingredients
- Moisturizer: 50% primary ingredients, 50% secondary ingredients
- Sunscreen: 50% primary ingredients, 50% secondary ingredients
- Mask: 50% primary ingredients, 50% secondary ingredients
- Toner: 50% primary ingredients, 50% secondary ingredients
- Other: 50% primary ingredients, 50% secondary ingredients

These weights are used while building the product's underlying score columns. After that, the live app chooses the relevant columns based on the selected user profile.

If only primary ingredients exist, primary gets 100% weight.

If only secondary ingredients exist, secondary gets 100% weight.

If any ingredient group contains a true `-100` hard blocker for a column, that column becomes `-100`.

## 9. Hard Block Rule

The most important safety rule is:

```text
If any included score component is -100, the final score becomes -100.
```

This exists because some products may be unsuitable for specific cases even if they are good products generally.

Examples:

- A retinoid-led product for pregnancy or breastfeeding.
- A strong exfoliating product for a severely dry or compromised profile.
- A product explicitly marked unsafe by the score master.

The system is careful not to create hard blocks from weak fuzzy matches. If the match is uncertain, the system usually applies a cap instead of a hard rejection.

## 10. Excessive Dryness Rule

Excessive Dryness is handled specially.

The doctor-style score is bucketed as:

```text
If score <= 50: final dryness condition score = -100
If score is 51 to 84: final dryness condition score = 0
If score >= 85: final dryness condition score = 100
```

Meaning:

- `-100`: not suggested for excessive dryness
- `0`: very weak fit for excessive dryness
- `100`: suitable for excessive dryness

For serums, Excessive Dryness is skipped in the final serum special-condition scoring rule, because the current agreed logic says serums should be concern-led, with pregnancy and breastfeeding safety still considered.

## 11. Product-Type Scoring Logic

The product-type rule decides which parts of the profile matter.

### Serum

Serums are scored mainly by concern.

Formula:

```text
serum_profile_score = selected_concern_score
```

Then safety caps are applied for teen, pregnancy, breastfeeding, and other relevant risk signals.

Rules:

- Skin type is not a main scoring component for serums.
- Pregnancy and breastfeeding safety still matter.
- Excessive Dryness is skipped for serum scoring.
- If the serum does not support the selected concern, it is capped lower.
- Retinoid-led serums can trigger usage warnings or restrictions.

### Cleanser

Cleansers are scored by skin type and concern.

Formula:

```text
cleanser_profile_score = average(skin_type_score, selected_concern_score)
```

Special rule for wrinkles or anti-aging:

```text
anti_aging_cleanser_score = skin_type_score
```

Why:

A cleanser is washed off, so it should not get too much credit for anti-aging claims. For wrinkles, the cleanser is judged more by whether it suits the skin and safety profile.

Acne, open-pore, comedone, and body-acne cleanser boost:

- The product must be a cleanser.
- The selected concern must be Acne, Body Acne, Open Pores, or Comedones.
- The product must have active cleanser cues, such as salicylic, BHA, AHA, zinc PCA, tea tree, charcoal, clay, acne, pimple, comedone, blackhead, or exfoliating language.
- It must have trustworthy support from ingredients, doctor anchors, or family evidence.
- It must pass profile safety caps.
- If those conditions are met, eligible cleansers can be lifted into the 90+ range.

### Moisturizer

Moisturizers are scored mainly by skin type.

Formula:

```text
moisturizer_profile_score = skin_type_score
```

Why:

A moisturizer's core job is skin compatibility, hydration, barrier comfort, and texture fit. It should not be treated like a serum for acne or pigmentation unless its ingredients strongly support that concern.

Rules:

- Concern does not directly dominate moisturizer scoring.
- Dryness, Dehydration, Barrier Repair, Redness/Irritation, and Dullness can allow stronger relevance if the product has hydration, soothing, barrier, or emollient support.
- For unrelated concerns, the product may be capped unless it has direct supporting ingredients.

### Sunscreen

Sunscreens are scored mainly by skin type.

Formula:

```text
sunscreen_profile_score = skin_type_score
```

Why:

A sunscreen's primary role is daily protection and skin compatibility. It naturally supports photo-related concerns more than acne or wrinkles.

Rules:

- Tanning, Dark Spots/Pigmentation, Melasma, and Uneven Skin Tone can receive full relevance from sunscreen.
- Dullness and Barrier Repair can receive partial relevance.
- Acne, Comedones, Open Pores, Wrinkles, and Redness need stronger supporting evidence to avoid lower caps.

### Mask

Masks are scored by concern and skin type.

Formula:

```text
mask_profile_score = average(selected_concern_score, skin_type_score)
```

Why:

Masks are usually occasional-use products. They can help specific concerns, but they should not automatically outrank daily routine essentials unless the fit is strong.

### Toner And Other Products

Toners and other products use a combined profile fit.

Formula:

```text
toner_or_other_profile_score = average(selected_concern_score, skin_type_score)
```

They are also capped if the product does not clearly support the selected concern or category.

## 12. Category Relevance Rules

The system checks whether a product belongs to the right body area.

Examples:

- If the concern is Body Acne, Body and Face & Body products can score normally.
- If the concern is Body Acne but the product is face-only, the score is capped.
- If the concern is a face concern and the product is body-only, the score is capped.
- Lip and eye products are capped for unrelated face concerns.

This prevents mistakes such as a body product ranking too high for a face cleanser profile.

## 13. Concern Family Mapping

Each concern is mapped to ingredient families that make sense for that concern.

Examples:

- Acne, Body Acne, Open Pores, Comedones: acne, exfoliant, clay
- Dryness, Dehydration, Barrier Repair: hydration, barrier, soothing, emollient
- Dark Spots/Pigmentation, Uneven Skin Tone, Melasma, Tanning: brightening, sunscreen, exfoliant, retinoid
- Wrinkles/Fine lines: retinoid, anti-aging, exfoliant, sunscreen
- Redness/Irritation: soothing, barrier, hydration
- Dullness: brightening, hydration, exfoliant, sunscreen

This mapping is used to decide whether a product directly supports the selected concern.

## 14. Five Evidence Layers

For every product, the platform stores five score layers.

### Layer 1: Baseline Ingredient Score

This is the direct score calculated from the ingredient score sheet and the product's primary/secondary ingredients.

It answers:

Based only on ingredients, what does this product look like it should score?

### Layer 2: Calibrated Ingredient Score

This adjusts the baseline score using product-type behavior, ingredient families, and confidence caps.

It answers:

Does the raw ingredient score need to be softened or corrected based on broader product behavior?

### Layer 3: Doctor Anchor Score

This compares the product with similar doctor-scored products.

Similarity considers:

- Same product type
- Same or related category
- Exact ingredient overlap
- Ingredient-family overlap
- Primary ingredient-family overlap
- Same brand, as a small tie-breaker

It answers:

How have similar doctor-reviewed products behaved?

### Layer 4: Product Type Plus Family Prior

This uses average behavior for products with the same product type and similar ingredient family.

It answers:

How do similar products of this kind usually perform?

### Layer 5: Product Type Prior

This uses average behavior for the broad product type.

It answers:

If we know only that this is a serum, cleanser, moisturizer, sunscreen, mask, or toner, what is the safest general expectation?

## 15. Visible Score Formula

The visible score is the score shown to the user after profile rules and safety logic are applied.

The evidence score starts with this formula:

```text
evidence_score =
  0.05 * baseline_ingredient_score
  + 0.30 * calibrated_ingredient_score
  + 0.55 * doctor_anchor_score
  + 0.05 * product_type_family_prior
  + 0.05 * product_type_prior
```

Plain meaning:

- 55% comes from similar doctor-reviewed products.
- 30% comes from improved ingredient intelligence.
- 5% comes from raw ingredient score.
- 5% comes from same type plus family behavior.
- 5% comes from broad product type behavior.

This makes the system less random and less purely mathematical. Doctor behavior remains the strongest influence whenever a similar reference exists.

## 16. Final Customer-Facing Calibration

After the evidence score is calculated, the platform applies customer-facing calibration.

This step exists because a purely averaged score can sometimes make very good products look average, especially in a large catalog.

A product can be lifted into higher score ranges only when all of these are true:

- It directly fits the selected concern or product role.
- It has strong ingredient or family support.
- It has useful doctor-anchor support.
- It passes safety rules.
- It is relevant to the selected face/body area.
- It does not contain weak low-scoring signals for the selected profile.

Typical lift logic:

- Strong direct fit with several 90+ evidence signals can move to 97+.
- Good direct fit with multiple 85+ evidence signals can move to 90-95.
- High-confidence hero products with very strong support can reach 99 for low-risk profiles.
- Risk profiles, such as Teen, Sensitive, Pregnancy, Breastfeeding, or special conditions, are capped more carefully.

Important:

The calibration can lift a product only inside safety and confidence limits. It cannot override a true `-100` hard blocker.

## 17. Confidence Caps

The system gives every product a confidence label.

High confidence means:

- Ingredients matched exactly or through trusted aliases.
- Product type is known.
- Ingredient family is recognized.
- There are no major weak/fuzzy match concerns.

Medium confidence means:

- Ingredient family is clear, but some fallback or weak matching was used.
- The result is usable but should be treated more cautiously.

Low confidence means:

- Product type or active family is unclear.
- No exact/curated ingredient anchor exists.
- Too much fallback matching was required.
- Some ingredients need review.

Current caps:

- High confidence can reach 100.
- Medium confidence is capped lower.
- Low confidence is capped lower still, especially when doctor-anchor support is weak.

In the generated calibrated layer:

- Low-confidence predicted scores are capped at 84.
- Medium-confidence predicted scores are capped at 92.

In the frontend profile scoring:

- High confidence can reach the highest visible scores if all other signals support it.
- Medium confidence is capped below the strongest hero range.
- Low confidence is capped unless it has strong supporting anchors.

## 18. Safety Caps

Safety caps are different from hard blockers.

A hard blocker means:

```text
Do not suggest this product for this profile.
```

A cap means:

```text
The product may still be shown, but it cannot receive a high score.
```

Examples:

- A teen profile with a low teen-safety score may be capped.
- A pregnancy profile with a low pregnancy score may be capped or blocked.
- Excessive Dryness with a score of 0 is capped strongly.
- Sensitive profiles are capped when irritation-risk ingredients appear.
- Products with one weak signal may be capped around the good/medium range.
- Products with multiple weak signals are capped lower.

This allows the system to be cautious without unnecessarily removing every product.

## 19. Hidden Ranking Score

The visible score is what the user sees.

The hidden ranking score is used only to sort products.

Why this is needed:

Two products may both show a visible score of 92, but one may have stronger doctor-anchor support, better ingredient confidence, and better ranking behavior. That product should appear first.

Formula:

```text
ranking_score =
  0.20 * visible_score
  + 0.10 * baseline_rank_quality
  + 0.10 * calibrated_rank_quality
  + 0.55 * doctor_anchor_rank_quality
  + 0.05 * product_type_family_rank_quality
```

Plain meaning:

- The displayed score matters.
- But the order is mostly driven by doctor-anchor ranking quality.
- Blocked products receive a very low hidden ranking score and go to the bottom.

## 20. Routine Logic

The routine tab uses the same scored product list for the selected profile.

It does not create a separate score. It chooses the highest eligible products from the already-scored results.

Routine sections:

- Premium AM Routine
- Premium PM Routine
- Value Fit AM Routine
- Value Fit PM Routine
- Weekly Mask Picks

AM routine slots:

- Cleanser
- Moisturizer
- Sunscreen

PM routine slots:

- Cleanser
- Serum
- Moisturizer

Weekly mask slots:

- Best Mask 1
- Best Mask 2

Premium logic:

- Prefer products priced at or above Rs 1000.
- Prefer products scoring 90 or above.
- If no premium product exists for that slot, fall back to the best available eligible product.

Value logic:

- Prefer products priced below Rs 1000.
- If no value product exists for that slot, fall back to the best available eligible product.

Tie behavior:

- If multiple products are eligible, the system uses the already-sorted scored list, so the top-ranked product is selected first.
- The same product is not repeated inside the same routine section if another eligible product exists.

## 21. Filters And Product Display Logic

The frontend lets testers filter by:

- Product type
- Score range
- Price range
- Confidence level
- Search keyword

Score bins:

- 90-100
- 80-89
- 70-79
- 50-69
- 1-49
- Not suggested

Each product card shows:

- Product image or blank placeholder
- Score circle
- Product name
- Brand
- Product type
- Price
- Confidence
- Short explanation

Clicking a product opens details such as:

- Final visible score
- Evidence score
- Ingredient layer score
- Calibrated layer score
- Doctor-anchor layer score
- Type-prior score
- Ingredient families
- Primary and secondary ingredients
- Nearest doctor-reference anchors
- Review flags
- Usage notes when relevant

## 22. Example Calculation

Example profile:

- Skin type: Oily
- Sensitive: No
- Age: Adult
- Concern: Acne
- Special condition: None

Example product:

- Product type: Cleanser
- Category: Face
- Ingredients: salicylic acid plus supporting cleansing agents
- Confidence: High
- Similar doctor anchors exist

Step 1: Choose profile columns.

- Skin column: `Oily Score`
- Concern column: `Acne`
- Special condition: `None = 100`

Step 2: Calculate each layer for the profile.

For a cleanser:

```text
profile_layer_score = average(Oily Score, Acne Score)
```

This is done separately for:

- Baseline ingredient layer
- Calibrated ingredient layer
- Doctor-anchor layer
- Type plus family prior layer
- Product type prior layer

Step 3: Blend the layers.

```text
evidence_score =
  5% baseline
  + 30% calibrated
  + 55% doctor anchor
  + 5% type plus family
  + 5% type
```

Step 4: Apply relevance and safety.

The product must:

- be relevant to acne,
- have cleanser acne/pore support,
- pass face/body category checks,
- pass safety checks,
- stay within confidence limits.

Step 5: Apply final calibration.

If the product has strong direct acne-cleanser fit, high confidence, and good doctor-anchor support, it can be lifted into the 90+ range.

## 23. Validation Against Doctor Scores

The automated algorithm was validated using doctor-scored products.

Validation setup:

- 384 doctor-scored products
- 224 representative user profiles
- 86,016 profile-product comparisons
- Leave-one-product-out testing

Leave-one-product-out means:

When predicting a product, the system temporarily excludes that product's own doctor score and uses other doctor-scored products as references. This is stricter than simply checking whether the model remembers the same product.

Visible score validation:

- Mean absolute difference: 15.198
- Median absolute difference: 6
- Within 10 score points: 75.91%
- Within 20 score points: 86.06%
- Same score bucket: 56.53%
- Hard-block agreement: 93.9%
- Pearson correlation: 0.7224

Interpretation:

- The system is directionally strong.
- It is especially useful for pre-scoring, coverage testing, and large catalog filtering.
- It is not a full replacement for doctor review in high-risk cases.

## 24. What We Can Safely Say Publicly

Safe public explanation:

Roopsee recommends products by matching the user's skin type, concern, sensitivity, age group, and selected conditions with product ingredients and product type. The system uses dermatologist-reviewed product behavior as a reference, ingredient-level compatibility signals, and safety checks to produce a clear product match score.

Safe claims:

- The system is ingredient-aware.
- The system is profile-aware.
- The system considers product type.
- The system applies safety rules for sensitive profiles and special conditions.
- The system uses doctor-reviewed products as reference anchors.
- Scores are explainable and auditable.

Claims to avoid:

- Do not say the system diagnoses skin conditions.
- Do not say it replaces a dermatologist.
- Do not say every automated score is doctor-approved.
- Do not say low-confidence products are ready for production without review.
- Do not promise medical treatment outcomes.

## 25. Why This Logic Is Trustworthy

The logic is trustworthy because it does not depend on one weak signal.

It combines:

- Ingredient science from the ingredient score master
- Product type behavior
- Skin profile rules
- Safety blockers and caps
- Doctor-reference similarity
- Confidence labels
- Review flags
- Face/body relevance checks
- Validation against known doctor-scored products

This makes the system scalable while still remaining cautious.

The most important design choice is that new products can be scored automatically, but the system still respects doctor-verified product behavior as the strongest anchor.

## 26. Known Limitations

The current system is strong for coverage testing and recommendation prototyping, but it has limits:

- Automated scoring can still be wrong if product ingredients are incomplete.
- A product's concentration, formulation quality, pH, and delivery system may not be fully known.
- Some products may have marketing names that imply benefits not supported by ingredients.
- Low-confidence products require manual review.
- Ranking overlap with doctor top picks is useful but not perfect.
- Sensitive, teen, pregnancy, breastfeeding, and excessive dryness profiles need extra caution.

## 27. Implementation Map

Main deployed repo:

```text
roopsee-product-coverage-service
```

Important files:

```text
static/data/final_scored_products.json
```

Contains the generated product dataset, score layers, metadata, product details, confidence labels, and nearest doctor anchors.

```text
static/app.js
```

Applies the live selected profile logic, calculates visible scores, sorts products, renders filters, product cards, details, and routines.

```text
docs/SCORING_METHODOLOGY.md
```

This document.

Generator files:

```text
tools/build_automated_scores.py
```

Creates ingredient-based automated score columns from product ingredients.

```text
tools/build_final_platform_dataset.py
```

Builds the final frontend dataset, including baseline, calibrated, doctor-anchor, type-family, and type-prior layers.

```text
tools/validate_v2_automated_logic.py
```

Validates automated scoring against doctor-scored products.

## 28. Short Presentation Version

Roopsee's scoring engine works in three stages.

First, it understands the product by reading its type, category, primary ingredients, and secondary ingredients. Ingredients are matched to Roopsee's ingredient score master, normalized where needed, and grouped into families such as acne support, hydration, brightening, sunscreen, soothing, barrier repair, or retinoid.

Second, it calculates profile fit differently for each product type. Serums are concern-led, cleansers use skin type plus concern, moisturizers and sunscreens are skin-type-led, and masks use concern plus skin-type fit. Safety rules handle teen users, sensitivity, pregnancy, breastfeeding, and excessive dryness.

Third, it calibrates the automated ingredient score using similar doctor-reviewed products. The final visible score is mostly influenced by doctor-anchor behavior, then ingredient intelligence, then product-type priors. This gives us a scalable system that can score thousands of new products while staying explainable, cautious, and reviewable.
