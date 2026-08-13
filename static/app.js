const DATA_URL = "./data/final_scored_products.json";

const CONCERN_FAMILIES = {
  Acne: ["acne", "exfoliant", "clay"],
  "Body Acne": ["acne", "exfoliant", "clay"],
  Dryness: ["hydration", "barrier", "soothing", "emollient"],
  "Open Pores": ["acne", "exfoliant", "clay"],
  "Uneven Skin Tone": ["brightening", "exfoliant", "sunscreen", "retinoid"],
  "Dark Spots/Pigmentation": ["brightening", "exfoliant", "sunscreen", "retinoid"],
  Melasma: ["brightening", "sunscreen"],
  "Barrier Repair": ["barrier", "hydration", "soothing", "emollient"],
  Comedones: ["acne", "exfoliant", "clay"],
  "Wrinkles/Fine lines": ["retinoid", "anti_aging", "exfoliant", "sunscreen"],
  "Redness/Irritation": ["soothing", "barrier", "hydration"],
  Dehydration: ["hydration", "barrier", "soothing"],
  Dullness: ["brightening", "hydration", "exfoliant", "sunscreen"],
  Tanning: ["sunscreen", "brightening"],
};

const HYDRATION_CONCERNS = new Set(["Dryness", "Dehydration", "Barrier Repair", "Redness/Irritation", "Dullness"]);
const ACNE_CONCERNS = new Set(["Acne", "Body Acne", "Open Pores", "Comedones"]);
const PHOTO_CONCERNS = new Set(["Tanning", "Dark Spots/Pigmentation", "Melasma", "Uneven Skin Tone"]);

const SCORE_BINS = [
  { key: "90-100", label: "90-100", tone: "good", test: (score) => score >= 90 },
  { key: "80-89", label: "80-89", tone: "good", test: (score) => score >= 80 && score < 90 },
  { key: "70-79", label: "70-79", tone: "mid", test: (score) => score >= 70 && score < 80 },
  { key: "50-69", label: "50-69", tone: "mid", test: (score) => score >= 50 && score < 70 },
  { key: "1-49", label: "1-49", tone: "low", test: (score) => score > -100 && score < 50 },
  { key: "blocked", label: "Not suggested", tone: "low", test: (score) => score <= -100 },
];

const state = {
  skinType: "Oily",
  sensitive: false,
  age: "Adult",
  gender: "female",
  concern: "Acne",
  specialConditions: ["None"],
  activeTab: "products",
  search: "",
  typeFilter: "All",
  scoreFilter: "All",
  priceFilter: "All",
  confidenceFilter: "All",
};

let dataset = null;
let products = [];
let scoreColumns = [];
let scoreColumnIndex = {};
let lastScoredRows = [];
let currentRowsByUid = new Map();
let renderTimer = null;

const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatMoney(value) {
  if (!Number.isFinite(Number(value)) || Number(value) <= 0) return "Price unavailable";
  return `Rs ${Math.round(Number(value)).toLocaleString("en-IN")}`;
}

function formatNumber(value) {
  if (!Number.isFinite(Number(value))) return "0";
  return Math.round(Number(value)).toLocaleString("en-IN");
}

function prettyType(type) {
  const labels = {
    cleanser: "Cleanser",
    serum: "Serum",
    moisturizer: "Moisturizer",
    sunscreen: "Sunscreen",
    mask: "Mask",
    toner: "Toner",
    other: "Other",
  };
  return labels[type] || String(type || "Product");
}

function roundScore(value) {
  if (!Number.isFinite(value)) return 0;
  return value >= 0 ? Math.floor(value + 0.5) : Math.ceil(value - 0.5);
}

function averageScore(values) {
  const valid = values.filter((value) => Number.isFinite(value));
  if (!valid.length) return 50;
  if (valid.some((value) => value <= -100)) return -100;
  return roundScore(valid.reduce((sum, value) => sum + value, 0) / valid.length);
}

function getLayerScore(product, layerName, columnName) {
  const index = scoreColumnIndex[columnName];
  const layer = product.scoreLayers?.[layerName];
  if (index === undefined || !layer) return columnName === "None" ? 100 : 50;
  const value = Number(layer[index]);
  return Number.isFinite(value) ? value : columnName === "None" ? 100 : 50;
}

function skinColumn() {
  const base = state.skinType;
  return state.sensitive ? `${base}+Sensitive Score` : `${base} Score`;
}

function specialColumn(condition) {
  if (condition === "Pregnant") return "Pregnancy Score";
  if (condition === "Breastfeeding") return "Breastfeeling Score";
  if (condition === "Excessive Dryness") return "Excessive Dryness score";
  return "None";
}

function productFamilies(product) {
  return new Set(product.families || []);
}

function supportsConcern(product, concern) {
  if (!concern || concern === "None") return true;
  const wanted = CONCERN_FAMILIES[concern] || [];
  const families = productFamilies(product);
  return wanted.some((family) => families.has(family));
}

function currentConcern() {
  return state.concern === "None" ? null : state.concern;
}

function productRelevanceCap(product, concern) {
  if (!concern || concern === "None") return 100;
  const type = product.normalizedType;
  const supported = supportsConcern(product, concern);

  if (type === "serum") return supported ? 100 : 72;
  if (type === "cleanser") {
    if (concern === "Wrinkles/Fine lines") return 88;
    return supported || ACNE_CONCERNS.has(concern) ? 100 : 88;
  }
  if (type === "moisturizer") return HYDRATION_CONCERNS.has(concern) || supported ? 100 : 84;
  if (type === "sunscreen") {
    if (PHOTO_CONCERNS.has(concern)) return 100;
    if (concern === "Dullness" || concern === "Barrier Repair") return 84;
    return supported ? 100 : 74;
  }
  if (type === "mask") return supported ? 100 : 88;
  if (type === "toner") return supported ? 93 : 78;
  return supported ? 88 : 72;
}

function confidenceCap(product) {
  if (product.confidence === "High") return 100;
  if (product.confidence === "Medium") return 96;
  return (product.support?.anchor || 0) >= 3 ? 92 : 88;
}

function directProfileFit(product, concern = currentConcern()) {
  if (!concern) return true;
  const type = product.normalizedType;
  const supported = supportsConcern(product, concern);

  if (type === "serum") return supported;
  if (type === "cleanser") {
    if (concern === "Wrinkles/Fine lines") return true;
    return supported || ACNE_CONCERNS.has(concern);
  }
  if (type === "moisturizer") return HYDRATION_CONCERNS.has(concern) || supported;
  if (type === "sunscreen") return PHOTO_CONCERNS.has(concern) || concern === "Dullness" || concern === "Barrier Repair" || supported;
  if (type === "mask") return supported;
  if (type === "toner") return supported || HYDRATION_CONCERNS.has(concern);
  return supported;
}

function displayConfidenceCap(product, directFit) {
  if (!directFit) return product.confidence === "High" ? 88 : 84;
  if (product.confidence === "High") return 99;
  if (product.confidence === "Medium") return 96;
  return (product.support?.anchor || 0) >= 3 || (product.support?.exact || 0) >= 2 ? 90 : 86;
}

function supportIsTrustworthy(product) {
  const support = product.support || {};
  return (support.exact || 0) >= 4 || (support.anchor || 0) >= 2 || (support.family || 0) >= 20 || (support.typeFamily || 0) >= 30;
}

function customerFacingScore(product, featureScores, evidenceScore) {
  const values = Object.values(featureScores).filter((value) => Number.isFinite(value));
  if (evidenceScore <= -100 || values.some((value) => value <= -100)) return -100;

  const directFit = directProfileFit(product);
  const sorted = [...values].sort((left, right) => right - left);
  const best = sorted[0] ?? evidenceScore;
  const topThreeAverage = averageScore(sorted.slice(0, 3));
  const highSignalCount = values.filter((value) => value >= 90).length;
  const goodSignalCount = values.filter((value) => value >= 85).length;
  const weakSignalCount = values.filter((value) => value < 60).length;
  const hasProfileRisk = state.sensitive || state.age === "Teen" || state.specialConditions.some((condition) => condition !== "None");
  const ingredientHero =
    directFit &&
    product.confidence === "High" &&
    (product.support?.exact || 0) >= 25 &&
    (product.support?.anchor || 0) >= 8 &&
    featureScores.baseline >= 90 &&
    featureScores.anchor >= 92 &&
    featureScores.v2 >= 84 &&
    values.every((value) => value >= 60);

  let score = evidenceScore;
  if (directFit && supportIsTrustworthy(product)) {
    if (evidenceScore >= 92 && topThreeAverage >= 92 && highSignalCount >= 3) {
      score = Math.max(score, 97);
    } else if (evidenceScore >= 88 && topThreeAverage >= 90 && highSignalCount >= 2) {
      score = Math.max(score, 95);
    } else if (evidenceScore >= 84 && topThreeAverage >= 88 && goodSignalCount >= 3) {
      score = Math.max(score, 92);
    }
  }

  if (directFit && product.confidence === "High") {
    if (!hasProfileRisk && ingredientHero) {
      score = Math.max(score, 99);
    } else if (!hasProfileRisk && supportIsTrustworthy(product) && evidenceScore >= 92 && topThreeAverage >= 91 && highSignalCount >= 3 && values.every((value) => value >= 88)) {
      score = Math.max(score, 99);
    } else if (best >= 95 && topThreeAverage >= 91 && highSignalCount >= 2) {
      score = Math.max(score, 97);
    }
  }

  let cap = displayConfidenceCap(product, directFit);
  if (weakSignalCount >= 2) cap = Math.min(cap, 79);
  else if (weakSignalCount === 1 && evidenceScore < 86) cap = Math.min(cap, 84);
  if (hasProfileRisk && values.some((value) => value < 70)) cap = Math.min(cap, 84);

  return roundScore(Math.min(score, cap));
}

function safetyAdjustment(product, layerName) {
  let cap = 100;
  const notes = [];
  const type = product.normalizedType;

  if (state.age === "Teen") {
    const teenScore = getLayerScore(product, layerName, "<16");
    if (teenScore <= -100) {
      return { hardBlock: true, cap: -100, notes: ["Not suggested for teen profiles."] };
    }
    if (teenScore < 60) cap = Math.min(cap, 70);
    else if (teenScore < 85) cap = Math.min(cap, 84);
  }

  for (const condition of state.specialConditions) {
    if (condition === "None") continue;
    if (type === "serum" && condition === "Excessive Dryness") {
      continue;
    }
    const column = specialColumn(condition);
    const specialScore = getLayerScore(product, layerName, column);
    if (specialScore <= -100) {
      return { hardBlock: true, cap: -100, notes: [`Not suggested for ${condition.toLowerCase()}.`] };
    }
    if (condition === "Excessive Dryness" && specialScore === 0) {
      cap = Math.min(cap, 69);
      notes.push("Limited fit for excessive dryness.");
    } else if (specialScore < 60) {
      cap = Math.min(cap, 70);
      notes.push(`Limited fit for ${condition.toLowerCase()}.`);
    } else if (specialScore < 85) {
      cap = Math.min(cap, 84);
    }
  }

  return { hardBlock: false, cap, notes };
}

function profileLayerScore(product, layerName) {
  const type = product.normalizedType;
  const concern = currentConcern();
  const skin = getLayerScore(product, layerName, skinColumn());
  const concernScore = concern ? getLayerScore(product, layerName, concern) : null;
  const safety = safetyAdjustment(product, layerName);
  if (safety.hardBlock) return -100;

  let components = [];
  if (type === "serum") {
    components = [concernScore ?? 60];
  } else if (type === "cleanser") {
    components = concern === "Wrinkles/Fine lines" ? [skin] : [skin, concernScore ?? skin];
  } else if (type === "moisturizer" || type === "sunscreen") {
    components = [skin];
  } else if (type === "mask") {
    components = concernScore === null ? [skin] : [concernScore, skin];
  } else {
    components = concernScore === null ? [skin] : [concernScore, skin];
  }

  let score = averageScore(components);
  if (score <= -100) return -100;
  score = Math.min(score, productRelevanceCap(product, concern), confidenceCap(product), safety.cap);
  return roundScore(score);
}

function rankQualities(scoredRows, key) {
  const sorted = [...scoredRows].sort((left, right) => {
    const diff = right.featureScores[key] - left.featureScores[key];
    if (diff) return diff;
    return left.product.name.localeCompare(right.product.name);
  });
  const maxRank = Math.max(1, sorted.length - 1);
  const output = new Map();
  sorted.forEach((row, rank) => {
    output.set(row.product.uid, 100 * (1 - rank / maxRank));
  });
  return output;
}

function computeScoredRows() {
  const rows = products.map((product) => {
    const featureScores = {
      baseline: profileLayerScore(product, "baseline"),
      v2: profileLayerScore(product, "v2"),
      anchor: profileLayerScore(product, "anchor"),
      typeFamily: profileLayerScore(product, "typeFamily"),
      type: profileLayerScore(product, "type"),
    };
    const evidenceScore = roundScore(
      dataset.metadata.visibleScoreWeights.baseline * featureScores.baseline +
        dataset.metadata.visibleScoreWeights.v2 * featureScores.v2 +
        dataset.metadata.visibleScoreWeights.anchor * featureScores.anchor +
        dataset.metadata.visibleScoreWeights.type_family * featureScores.typeFamily +
        dataset.metadata.visibleScoreWeights.type * featureScores.type
    );
    const finalScore = customerFacingScore(product, featureScores, evidenceScore);
    return { product, score: finalScore, evidenceScore, featureScores, rankingScore: finalScore };
  });

  const baselineRank = rankQualities(rows, "baseline");
  const v2Rank = rankQualities(rows, "v2");
  const anchorRank = rankQualities(rows, "anchor");
  const typeFamilyRank = rankQualities(rows, "typeFamily");
  const weights = dataset.metadata.rankFusionWeights;

  rows.forEach((row) => {
    if (row.score <= -100) {
      row.rankingScore = -999;
      return;
    }
    row.rankingScore =
      weights.score * row.score +
      weights.baseline_rank * (baselineRank.get(row.product.uid) || 0) +
      weights.v2_rank * (v2Rank.get(row.product.uid) || 0) +
      weights.anchor_rank * (anchorRank.get(row.product.uid) || 0) +
      weights.type_family_rank * (typeFamilyRank.get(row.product.uid) || 0);
  });

  return rows.sort((left, right) => {
    const scoreDiff = right.score - left.score;
    if (scoreDiff) return scoreDiff;
    const rankDiff = right.rankingScore - left.rankingScore;
    if (rankDiff) return rankDiff;
    return left.product.name.localeCompare(right.product.name);
  });
}

function scoreColorClass(score) {
  if (score <= -100) return "blocked";
  if (score >= 80) return "green";
  if (score >= 50) return "yellow";
  return "red";
}

function scoreLabel(score) {
  return score <= -100 ? "No" : String(score);
}

function scoreBinKey(score) {
  return SCORE_BINS.find((bin) => bin.test(score))?.key || "1-49";
}

function productPrice(product) {
  return Number(product.sellingPrice || product.mrp || 0);
}

function applyFilters(rows) {
  const search = state.search.trim().toLowerCase();
  return rows.filter((row) => {
    const product = row.product;
    if (state.typeFilter !== "All" && product.normalizedType !== state.typeFilter) return false;
    if (state.confidenceFilter !== "All" && product.confidence !== state.confidenceFilter) return false;
    if (state.scoreFilter !== "All" && scoreBinKey(row.score) !== state.scoreFilter) return false;

    const price = productPrice(product);
    if (state.priceFilter === "under-500" && !(price > 0 && price < 500)) return false;
    if (state.priceFilter === "500-999" && !(price >= 500 && price < 1000)) return false;
    if (state.priceFilter === "1000-1999" && !(price >= 1000 && price < 2000)) return false;
    if (state.priceFilter === "2000-plus" && !(price >= 2000)) return false;

    if (search) {
      const haystack = `${product.name} ${product.brand} ${product.primaryIngredients} ${product.secondaryIngredients} ${(product.families || []).join(" ")}`.toLowerCase();
      if (!haystack.includes(search)) return false;
    }
    return true;
  });
}

function profileLine() {
  const sensitivity = state.sensitive ? "Sensitive" : "Not sensitive";
  const specials = state.specialConditions.join(", ");
  return `${state.skinType} | ${sensitivity} | ${state.age} | ${state.concern} | ${specials}`;
}

function renderScoreBins(rows) {
  const counts = Object.fromEntries(SCORE_BINS.map((bin) => [bin.key, 0]));
  rows.forEach((row) => {
    counts[scoreBinKey(row.score)] += 1;
  });
  $("#score-bins").innerHTML = SCORE_BINS.map(
    (bin) => `
      <button class="bin-card ${bin.tone} ${state.scoreFilter === bin.key ? "active" : ""}" type="button" data-bin="${bin.key}">
        <strong>${formatNumber(counts[bin.key])}</strong>
        <span>${bin.label}</span>
      </button>
    `
  ).join("");
}

function productImage(product, className = "product-image") {
  if (!product.imageUrl) return `<div class="${className}"></div>`;
  return `<img class="${className}" src="${escapeHtml(product.imageUrl)}" alt="${escapeHtml(product.name)}" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('div'), {className: '${className}'}))" />`;
}

function shortWhy(row) {
  const product = row.product;
  const anchorSupport = product.support?.anchor || 0;
  const familyText = (product.families || []).slice(0, 3).join(", ") || "general fit";
  if (row.score <= -100) return "Safety rules block this product for the selected profile.";
  if (row.score >= 95 && row.evidenceScore < row.score) return `Strong direct profile fit with customer-facing calibration; active families: ${familyText}.`;
  if (anchorSupport >= 3) return `Anchored by ${anchorSupport} similar doctor-reference products; active families: ${familyText}.`;
  return `Score uses ingredient sheet signals and category priors; active families: ${familyText}.`;
}

function productCard(row) {
  const product = row.product;
  const price = formatMoney(product.sellingPrice || product.mrp);
  return `
    <article class="product-card" data-uid="${escapeHtml(product.uid)}">
      ${productImage(product)}
      <div class="product-info">
        <div class="card-top">
          <div class="product-title">${escapeHtml(product.name)}</div>
          <div class="score-circle ${scoreColorClass(row.score)}">${scoreLabel(row.score)}</div>
        </div>
        <div class="meta-line">
          <span class="pill">${escapeHtml(prettyType(product.normalizedType))}</span>
          <span class="pill">${escapeHtml(product.confidence)} confidence</span>
          <span class="pill">${escapeHtml(product.category || "Catalog")}</span>
        </div>
        <div class="price-line">${price}</div>
        <p class="why-line">${escapeHtml(shortWhy(row))}</p>
      </div>
    </article>
  `;
}

function renderProducts(rows, filteredRows) {
  currentRowsByUid = new Map(filteredRows.map((row) => [row.product.uid, row]));
  $("#results-count").textContent = `Showing ${formatNumber(Math.min(filteredRows.length, 120))} of ${formatNumber(filteredRows.length)} matching products`;
  $("#profile-line").textContent = profileLine();
  $("#product-grid").innerHTML = filteredRows.slice(0, 120).map(productCard).join("");
}

function bestProduct(rows, type, mode, exclude = new Set()) {
  let eligible = rows.filter((row) => row.product.normalizedType === type && row.score > 0 && !exclude.has(row.product.uid));
  if (mode === "premium") {
    const premium = eligible.filter((row) => productPrice(row.product) >= 1000 && row.score >= 90);
    if (premium.length) eligible = premium;
  }
  if (mode === "value") {
    const value = eligible.filter((row) => {
      const price = productPrice(row.product);
      return price > 0 && price < 1000;
    });
    if (value.length) eligible = value;
  }
  return eligible[0] || null;
}

function routineCard(row, slot) {
  if (!row) {
    return `
      <div class="routine-card">
        <div class="product-image"></div>
        <div>
          <strong>${escapeHtml(slot)}</strong>
          <p>No eligible product found for this slot.</p>
        </div>
      </div>
    `;
  }
  const product = row.product;
  return `
    <article class="routine-card" data-uid="${escapeHtml(product.uid)}">
      ${productImage(product, "product-image")}
      <div>
        <strong>${escapeHtml(slot)} | ${scoreLabel(row.score)}</strong>
        <p>${escapeHtml(product.name)}</p>
        <p>${formatMoney(product.sellingPrice || product.mrp)}</p>
      </div>
    </article>
  `;
}

function renderRoutine(rows) {
  const sections = [
    {
      title: "Premium AM Routine",
      mode: "premium",
      slots: [
        ["Cleanser", "cleanser"],
        ["Moisturizer", "moisturizer"],
        ["Sunscreen", "sunscreen"],
      ],
    },
    {
      title: "Premium PM Routine",
      mode: "premium",
      slots: [
        ["Cleanser", "cleanser"],
        ["Serum", "serum"],
        ["Moisturizer", "moisturizer"],
      ],
    },
    {
      title: "Value Fit AM Routine",
      mode: "value",
      slots: [
        ["Cleanser", "cleanser"],
        ["Moisturizer", "moisturizer"],
        ["Sunscreen", "sunscreen"],
      ],
    },
    {
      title: "Value Fit PM Routine",
      mode: "value",
      slots: [
        ["Cleanser", "cleanser"],
        ["Serum", "serum"],
        ["Moisturizer", "moisturizer"],
      ],
    },
  ];

  const html = sections
    .map((section) => {
      const used = new Set();
      const cards = section.slots
        .map(([slot, type]) => {
          const row = bestProduct(rows, type, section.mode, used);
          if (row) used.add(row.product.uid);
          return routineCard(row, slot);
        })
        .join("");
      return `
        <section class="routine-section">
          <h3>${escapeHtml(section.title)}</h3>
          <div class="routine-row">${cards}</div>
        </section>
      `;
    })
    .join("");

  const masks = rows.filter((row) => row.product.normalizedType === "mask" && row.score > 0).slice(0, 2);
  const weekly = `
    <section class="routine-section">
      <h3>Weekly Mask Picks</h3>
      <div class="routine-row">
        ${routineCard(masks[0], "Mask 1")}
        ${routineCard(masks[1], "Mask 2")}
      </div>
    </section>
  `;
  $("#routine-grid").innerHTML = html + weekly;
}

function profileRuleText(product) {
  const type = product.normalizedType;
  if (type === "serum") return "For serums, the selected concern is the main scoring signal. Pregnancy and breastfeeding safety checks still apply, while excessive dryness is skipped for serum scoring.";
  if (type === "cleanser" && state.concern === "Wrinkles/Fine lines") return "For anti-aging or wrinkles, cleansers are scored from skin type plus selected safety conditions instead of the concern score.";
  if (type === "cleanser") return "For cleansers, the score uses skin type and the selected concern together.";
  if (type === "moisturizer" || type === "sunscreen") return "For moisturizers and sunscreens, the score uses skin type as the main fit signal.";
  if (type === "mask") return "For masks, the score uses concern fit and skin-type fit together.";
  return "For this product type, the score uses concern fit and skin-type fit together.";
}

function detailExplanation(row) {
  const product = row.product;
  const strongestLayer = Object.entries(row.featureScores).sort((a, b) => b[1] - a[1])[0];
  const anchorSupport = product.support?.anchor || 0;
  const confidence = product.confidence.toLowerCase();
  const families = (product.families || []).join(", ") || "no recognized active family";
  const sandwich =
    (product.families || []).includes("retinoid") &&
    (state.age === "Teen" || state.skinType === "Dry" || state.sensitive || state.specialConditions.some((condition) => condition !== "None") || state.concern === "Wrinkles/Fine lines");
  return `
    <p>
      This product scores <strong>${scoreLabel(row.score)}</strong> for ${escapeHtml(profileLine())}.
      ${escapeHtml(profileRuleText(product))}
    </p>
    <p>
      The final score is a customer-facing calibrated score. It starts from an evidence score of <strong>${scoreLabel(row.evidenceScore)}</strong>, then can move upward only when the product is a direct profile fit with strong ingredient, doctor-anchor, and category support.
      The strongest layer here is <strong>${escapeHtml(strongestLayer?.[0] || "anchor")}</strong>, with ${anchorSupport} doctor-anchor match(es) and ${confidence} confidence.
    </p>
    <p>Recognized active families: ${escapeHtml(families)}.</p>
    ${sandwich ? "<p><strong>Use note:</strong> If this is a retinoid-led product, use the sandwich method: moisturizer before and after the retinoid, especially for teen, dry, sensitive, pregnancy, breastfeeding, or special-condition profiles.</p>" : ""}
  `;
}

function layerTile(label, value) {
  return `
    <div class="detail-tile">
      <span>${escapeHtml(label)}</span>
      <strong>${scoreLabel(value)}</strong>
    </div>
  `;
}

function openProductDetail(uid) {
  const row = currentRowsByUid.get(uid) || lastScoredRows.find((item) => item.product.uid === uid);
  if (!row) return;
  const product = row.product;
  const anchors = product.nearestDoctorAnchors?.length
    ? product.nearestDoctorAnchors
        .map(
          (anchor) => `
            <div class="anchor-item">
              <strong>${escapeHtml(anchor.name)}</strong>
              <span>${escapeHtml(anchor.productType)} | similarity ${escapeHtml(anchor.similarity)}</span>
            </div>
          `
        )
        .join("")
    : `<div class="anchor-item"><strong>No strong doctor-reference anchor</strong><span>The product relies more on ingredient scores and category priors.</span></div>`;

  $("#modal-content").innerHTML = `
    <div class="modal-layout">
      <div>
        ${productImage(product, "modal-image")}
        <div class="meta-line">
          <span class="pill">${escapeHtml(prettyType(product.normalizedType))}</span>
          <span class="pill">${escapeHtml(product.confidence)} confidence</span>
          <span class="pill">${formatMoney(product.sellingPrice || product.mrp)}</span>
        </div>
      </div>
      <div>
        <h2 class="modal-title" id="modal-title">${escapeHtml(product.name)}</h2>
        <div class="detail-grid">
          ${layerTile("Final score", row.score)}
          ${layerTile("Evidence score", row.evidenceScore)}
          ${layerTile("Ingredient", row.featureScores.baseline)}
          ${layerTile("Calibrated", row.featureScores.v2)}
          ${layerTile("Anchor", row.featureScores.anchor)}
          ${layerTile("Type prior", row.featureScores.type)}
        </div>
        <div class="explanation">${detailExplanation(row)}</div>
        <div class="explanation">
          <strong>Ingredients used</strong>
          <p>Primary: ${escapeHtml(product.primaryIngredients || "Not available")}</p>
          <p>Secondary: ${escapeHtml(product.secondaryIngredients || "Not available")}</p>
          <p>Review notes: ${escapeHtml((product.reviewFlags || []).join("; ") || "No major review flags")}</p>
        </div>
        <div class="anchor-list">
          <strong>Nearest doctor-reference anchors</strong>
          ${anchors}
        </div>
      </div>
    </div>
  `;
  $("#product-modal").classList.remove("hidden");
}

function closeProductDetail() {
  $("#product-modal").classList.add("hidden");
}

function renderAll() {
  if (!dataset) return;
  lastScoredRows = computeScoredRows();
  const filteredRows = applyFilters(lastScoredRows);
  renderScoreBins(lastScoredRows);
  renderProducts(lastScoredRows, filteredRows);
  renderRoutine(lastScoredRows);
}

function scheduleRender() {
  window.clearTimeout(renderTimer);
  renderTimer = window.setTimeout(renderAll, 40);
}

function button(value, active, disabled = false) {
  return `<button class="choice-btn ${active ? "active" : ""} ${disabled ? "disabled" : ""}" type="button" data-value="${escapeHtml(value)}" ${disabled ? "disabled" : ""}>${escapeHtml(value)}</button>`;
}

function renderQuiz() {
  const options = dataset.quizOptions;
  $("#skin-type-options").innerHTML = options.skinTypes.map((item) => button(item, item === state.skinType)).join("");
  $("#sensitive-options").innerHTML = ["No", "Yes"].map((item) => button(item, (item === "Yes") === state.sensitive)).join("");
  $("#concern-options").innerHTML = options.faceBodyConcerns.map((item) => button(item, item === state.concern)).join("");
  $("#special-options").innerHTML = options.specialConditions
    .map((item) => {
      const disabled = state.gender === "male" && (item === "Pregnant" || item === "Breastfeeding");
      return button(item, state.specialConditions.includes(item), disabled);
    })
    .join("");
  $("#age-select").innerHTML = options.ages.map((item) => `<option ${item === state.age ? "selected" : ""}>${escapeHtml(item)}</option>`).join("");
  $("#gender-select").innerHTML = options.genders.map((item) => `<option ${item === state.gender ? "selected" : ""}>${escapeHtml(item)}</option>`).join("");
}

function renderFilters() {
  const types = ["All", ...Array.from(new Set(products.map((product) => product.normalizedType))).sort()];
  $("#type-filter").innerHTML = types.map((type) => `<option value="${escapeHtml(type)}">${escapeHtml(type === "All" ? "All product types" : type)}</option>`).join("");
  $("#score-filter").innerHTML = [`<option value="All">All score ranges</option>`]
    .concat(SCORE_BINS.map((bin) => `<option value="${escapeHtml(bin.key)}">${escapeHtml(bin.label)}</option>`))
    .join("");
  $("#price-filter").innerHTML = `
    <option value="All">All prices</option>
    <option value="under-500">Under Rs 500</option>
    <option value="500-999">Rs 500-999</option>
    <option value="1000-1999">Rs 1000-1999</option>
    <option value="2000-plus">Rs 2000+</option>
  `;
  $("#confidence-filter").innerHTML = `
    <option value="All">All confidence</option>
    <option value="High">High confidence</option>
    <option value="Medium">Medium confidence</option>
    <option value="Low">Low confidence</option>
  `;
}

function bindEvents() {
  $("#skin-type-options").addEventListener("click", (event) => {
    const target = event.target.closest("button[data-value]");
    if (!target) return;
    state.skinType = target.dataset.value;
    renderQuiz();
    scheduleRender();
  });

  $("#sensitive-options").addEventListener("click", (event) => {
    const target = event.target.closest("button[data-value]");
    if (!target) return;
    state.sensitive = target.dataset.value === "Yes";
    renderQuiz();
    scheduleRender();
  });

  $("#concern-options").addEventListener("click", (event) => {
    const target = event.target.closest("button[data-value]");
    if (!target) return;
    state.concern = target.dataset.value;
    renderQuiz();
    scheduleRender();
  });

  $("#special-options").addEventListener("click", (event) => {
    const target = event.target.closest("button[data-value]");
    if (!target || target.disabled) return;
    const value = target.dataset.value;
    if (value === "None") {
      state.specialConditions = ["None"];
    } else {
      const withoutNone = state.specialConditions.filter((item) => item !== "None");
      state.specialConditions = withoutNone.includes(value) ? withoutNone.filter((item) => item !== value) : [...withoutNone, value];
      if (!state.specialConditions.length) state.specialConditions = ["None"];
    }
    renderQuiz();
    scheduleRender();
  });

  $("#age-select").addEventListener("change", (event) => {
    state.age = event.target.value;
    scheduleRender();
  });

  $("#gender-select").addEventListener("change", (event) => {
    state.gender = event.target.value;
    if (state.gender === "male") {
      state.specialConditions = state.specialConditions.filter((item) => item !== "Pregnant" && item !== "Breastfeeding");
      if (!state.specialConditions.length) state.specialConditions = ["None"];
    }
    renderQuiz();
    scheduleRender();
  });

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      state.activeTab = tab.dataset.tab;
      document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("active", item === tab));
      $("#products-view").classList.toggle("hidden", state.activeTab !== "products");
      $("#routine-view").classList.toggle("hidden", state.activeTab !== "routine");
    });
  });

  $("#search-input").addEventListener("input", (event) => {
    state.search = event.target.value;
    scheduleRender();
  });
  $("#type-filter").addEventListener("change", (event) => {
    state.typeFilter = event.target.value;
    scheduleRender();
  });
  $("#score-filter").addEventListener("change", (event) => {
    state.scoreFilter = event.target.value;
    scheduleRender();
  });
  $("#price-filter").addEventListener("change", (event) => {
    state.priceFilter = event.target.value;
    scheduleRender();
  });
  $("#confidence-filter").addEventListener("change", (event) => {
    state.confidenceFilter = event.target.value;
    scheduleRender();
  });

  $("#score-bins").addEventListener("click", (event) => {
    const target = event.target.closest("[data-bin]");
    if (!target) return;
    state.scoreFilter = state.scoreFilter === target.dataset.bin ? "All" : target.dataset.bin;
    $("#score-filter").value = state.scoreFilter;
    scheduleRender();
  });

  $("#product-grid").addEventListener("click", (event) => {
    const card = event.target.closest("[data-uid]");
    if (card) openProductDetail(card.dataset.uid);
  });

  $("#routine-grid").addEventListener("click", (event) => {
    const card = event.target.closest("[data-uid]");
    if (card) openProductDetail(card.dataset.uid);
  });

  $("#modal-close").addEventListener("click", closeProductDetail);
  $("#product-modal").addEventListener("click", (event) => {
    if (event.target.id === "product-modal") closeProductDetail();
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeProductDetail();
  });
}

function renderHeader() {
  const meta = dataset.metadata;
  $("#product-count").textContent = `${formatNumber(meta.productCount)} products`;
  $("#confidence-summary").textContent = `${formatNumber(meta.confidenceCounts.High)} high confidence`;
  const validation = meta.validation?.visibleScoreValidation;
  if (validation) {
    $("#validation-card").innerHTML = `
      <span>Validation</span>
      <strong>${escapeHtml(validation.within_10_pct)}%</strong>
      <p>Within 10 score points on doctor-reference final-score checks. Hard-block agreement: ${escapeHtml(validation.hard_block_agreement_pct)}%.</p>
    `;
  }
}

async function init() {
  const response = await fetch(DATA_URL);
  if (!response.ok) throw new Error(`Failed to load ${DATA_URL}`);
  dataset = await response.json();
  products = dataset.products || [];
  scoreColumns = dataset.scoreColumns || [];
  scoreColumnIndex = Object.fromEntries(scoreColumns.map((column, index) => [column, index]));
  renderHeader();
  renderQuiz();
  renderFilters();
  bindEvents();
  renderAll();
}

init().catch((error) => {
  console.error(error);
  document.body.innerHTML = `
    <main class="page-shell">
      <section class="quiz-card">
        <h1>Could not load product data.</h1>
        <p class="hero-copy">${escapeHtml(error.message)}</p>
      </section>
    </main>
  `;
});
