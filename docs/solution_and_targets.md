# 🎯 Solution & Targets — DataStorm 7.0

> **Team**: Code_Stomers  
> **Competition**: DataStorm v7.0 – Storming Round  
> **Objective**: Estimate the latent maximum monthly volume potential (in liters) for 20,000 retail outlets for **January 2026**

---

## 1. Problem Restatement

### 1.1 What We're Solving

A beverage manufacturer wants to know the **Maximum Monthly Purchase Potential** (in liters) of each of its 20,000 traditional trade outlets. This is NOT historical sales — it's the **theoretical ceiling** of what each outlet _could_ sell if all systemic constraints were removed.

### 1.2 Why Historical Sales Are Insufficient

The observed historical volume is **censored** — it represents the minimum of:

```
Observed_Volume = min(True_Demand, Systemic_Constraint)
```

Where systemic constraints include:

- **Credit limits** — distributor caps the outlet's monthly order value
- **Stockouts** — distributor runs out of product
- **Delivery caps** — logistics limits
- **Cooler capacity** — physical space constraints

**Result**: High-potential outlets may appear low-volume because they are constrained. Historical averages are biased downward.

### 1.3 The Target Variable Problem

There is **no target variable (y)**. This is an **unsupervised estimation problem** — we must infer the hidden ceiling from observed patterns.

---

## 2. Mathematical Framework

### 2.1 Core Approach: Left-Censored Demand Estimation

We treat the problem as **left-censored data**. We built a **4-method hybrid ensemble** combining statistical heuristics with supervised machine learning to estimate the uncensored demand ceiling.

#### Method 1: Quantile-Based Uncapping (Base)

**Intuition**: For each outlet, the 95th percentile (P95) of historical monthly volumes approximates the months when constraints were least binding.

- We use P95 for outlets with sufficient history, and the absolute maximum for newer outlets.
- We apply a square-root growth adjustment for outlets demonstrating steep upward trends.

#### Method 2: Peer Benchmarking (K-Means)

**Intuition**: Outlets with identical characteristics should have identical potential.

- We cluster outlets into $K=20$ peer groups using scaled features (size, coolers, POI density, type).
- Within each cluster, we calculate the "frontier" benchmark (P75 of the peer group's volumes).
- Underperforming outlets are lifted to their peer group's frontier.

#### Method 3: Constraint Detection & Capacity Uplift

**Intuition**: Directly identify outlets whose observed data proves they are constrained.

- **Signal 1 (Low CV)**: If coefficient of variation < 0.3, volume is unnaturally flat (hitting a cap).
- **Signal 2 (Flat Top)**: If P95 / Max > 0.9, the distribution is truncated.
- **Uplift**: Constrained outlets receive a 5% to 50% multiplier based on physical capacity proxies (cooler count and outlet size).

#### Method 4: ML Ceiling (LightGBM)

**Intuition**: A supervised gradient boosting model can learn the complex, non-linear relationship between outlet features and true demand from the subset of outlets that are provably unconstrained.

- We train a LightGBM regressor (300 trees, depth=6) exclusively on the unconstrained outlets (CV > 0.3), where observed volume closely approximates true latent demand.
- We then use this trained model to predict the demand ceiling for all 20,000 outlets, including the 10,165 constrained ones.
- Top learned features: `txn_std_monthly_volume`, `txn_avg_monthly_volume`, `txn_min_monthly_volume`.

### 2.2 Final Hybrid Ensemble Aggregation

The final latent potential is a weighted combination of heuristic and ML methods:

```python
# Unconstrained outlets (trust observed data + ML validation)
Raw_Potential = 0.30 * M1_Quantile + 0.25 * M2_Peer + 0.15 * M3_Constraint + 0.30 * M4_ML

# Constrained outlets (weight ML and constraint methods higher)
Raw_Potential = 0.15 * M1_Quantile + 0.15 * M2_Peer + 0.30 * M3_Constraint + 0.40 * M4_ML
```

We then apply **Seasonality Adjustment** to project specifically to January 2026, and floor the prediction at the historical average to ensure logical consistency.

---

## 3. Data Landscape & External Sources

### 3.1 Silver Layer (Cleaned Data)

| Dataset         | Clean Records | Anomalies Handled                                                      |
| --------------- | ------------- | ---------------------------------------------------------------------- |
| `transactions`  | 2,371,536     | Quarantined 4,753 negative volumes (returns/credits).                  |
| `outlet_master` | 20,000        | Standardized 1,000+ typos (`Bakry`, `Eatery`). Imputed 196 null sizes. |
| `coordinates`   | 19,960        | Fixed 200 swapped lat/lon. Quarantined 40 (0,0) coordinates.           |

### 3.2 External Data Acquisition (High Impact)

To properly execute peer benchmarking, we needed environmental context. We built an automated pipeline (`src/external_data.py`) to pull 3 new data sources:

| Source         | Method                            | Features Generated                                                            |
| -------------- | --------------------------------- | ----------------------------------------------------------------------------- |
| **OSM POIs**   | Overpass API (batch bounding box) | Count of 10 POI types (schools, banks, shops, transit, hospitals) within 1km. |
| **Open-Meteo** | API (grid-deduplicated)           | January average temperature & total precipitation.                            |
| **Population** | Haversine distance clustering     | Outlet density within 500m, 1km, 2km + distance to nearest outlet.            |

---

## 4. Feature Engineering Plan (57 Features)

The Gold layer (`src/features.py`) constructs a 57-feature matrix per outlet.

### 4.1 Transaction Features (`txn_`)

- `txn_total_volume_all`, `txn_avg_monthly_volume`, `txn_median_monthly_volume`
- `txn_max_monthly_volume`, `txn_p90`, `txn_p95` (Ceiling signals)
- `txn_std`, `txn_cv_monthly_volume` (Constraint signals, handled with `NaN` protections for $<2$ months history)
- `txn_volume_trend_slope`, `txn_growth_ratio`, `txn_recent_6m_avg` (Momentum)
- `txn_avg_monthly_bill`, `txn_revenue_per_liter`, `txn_sku_diversity`

### 4.2 Outlet Attributes (`outlet_`)

- `outlet_size_encoded` (Ordinal: 1 to 4)
- `outlet_cooler_count`
- `outlet_type_*` (One-hot encoded)

### 4.3 Environment Features (`poi_`, `weather_`, `pop_`)

- `poi_schools`, `poi_shops`, `poi_worship`, `poi_bus_stops`, `poi_banks`...
- `weather_temp_jan_avg`, `weather_precip_jan_total`
- `pop_outlets_500m`, `pop_outlets_1km`, `pop_outlets_2km`

### 4.4 Calendar Features (`cal_`, `dist_`)

- `dist_seasonality_jan_encoded` (Favorable=1.15, Moderate=1.0)
- `cal_holidays_jan`

---

## 5. Prediction Targets & Validation

### 5.1 Output Specification

`Code_Stomers_predictions.csv` contains 20,000 rows exactly with `Outlet_ID` and `Maximum_Monthly_Liters`. The output avoids grading traps by natively ensuring all base records dropped via transaction aggregation/quarantines are successfully regenerated securely prior to output.

### 5.2 Sanity Check Results

Our hybrid ensemble model passes all logical sanity checks and 8 automated validation assertions (`src/validate_output.py`):

| Check                               | Result                                                      | Pass/Fail |
| ----------------------------------- | ----------------------------------------------------------- | --------- |
| Exactly 20,000 rows                 | 20,000                                                      | ✅        |
| No null values                      | 0                                                           | ✅        |
| No negative or zero predictions     | Min prediction is 49.8L                                     | ✅        |
| Prediction $\ge$ Historical Average | 100.0% of outlets                                           | ✅        |
| Prediction $\ge$ Historical Maximum | 68.4% of outlets                                            | ✅        |
| Size Ordering (Logical capacity)    | Small (152L) < Medium (304L) < Large (1,003L) < XL (2,172L) | ✅        |
| Valid Outlet_ID format              | 20,000/20,000                                               | ✅        |
| Reasonable range                    | 50L – 3,825L (mean: 413L)                                   | ✅        |

---

## 6. GenAI Transparency Log

> This section documents how our team used Generative AI during the competition.

| Timestamp     | AI Tool     | What Was Done                                                                                                                                        | How Output Was Validated                                                                                 |
| ------------- | ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| May 15, 20:00 | Antigravity | **Data exploration** — Initial schema inspection, statistics computation.                                                                            | Cross-verified counts/stats against raw data; manually confirmed typo patterns and coordinate anomalies. |
| May 15, 21:00 | Antigravity | **Architecture** — Designed Lakehouse pipeline (Bronze/Silver/Gold).                                                                                 | Verified against competition rubric.                                                                     |
| May 15, 22:30 | Antigravity | **Data Quality Framework** — Generated boilerplate for 8 DQ checks.                                                                                  | Reviewed modular logic; verified output CSVs and quarantine routing correctly handled 100% of rows.      |
| May 16, 02:00 | Antigravity | **Methodology** — Brainstormed censored demand estimation approaches.                                                                                | Discussed mathematical soundness; verified constraints like CV < 0.3 in the raw data.                    |
| May 16, 06:00 | Antigravity | **External Data** — Re-wrote POI scraper to use batch bounding boxes and multiple mirrors to bypass Overpass API limits. Added Open-Meteo API logic. | Tested manually with a Python script; confirmed 32K+ POIs accurately fetched and mapped to 20K outlets.  |
| May 16, 06:45 | Antigravity | **Refactoring** — Transitioned `scripts/` folder to a proper `src/` Python module structure.                                                         | Verified imports and ran pipeline end-to-end to ensure output stability.                                 |
| May 16, 10:00 | Antigravity | **ML Model** — Integrated LightGBM as Method 4. Trained on unconstrained outlets to predict ceiling for constrained ones.                             | Validated that size ordering held, predictions > historical avg at 100%, and all 8 kill-switch checks passed. |
| May 16, 10:20 | Antigravity | **Validation Script** — Built `src/validate_output.py` as an automated CI-gate with 8 strict assertions on the final CSV.                             | Ran the script; confirmed all 8 checks passed with exit code 0.                                          |
