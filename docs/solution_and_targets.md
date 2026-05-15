# 🎯 Solution & Targets — DataStorm 7.0

> **Team**: Code_Stomers  
> **Competition**: DataStorm v7.0 – Storming Round  
> **Objective**: Estimate the latent maximum monthly volume potential (in liters) for 20,000 retail outlets for **January 2026**  
> **Last updated**: May 15, 2026

---

## 1. Problem Restatement

### 1.1 What We're Solving

A beverage manufacturer wants to know the **Maximum Monthly Purchase Potential** (in liters) of each of its 20,000 traditional trade outlets. This is NOT historical sales — it's the **theoretical ceiling** of what each outlet *could* sell if all systemic constraints were removed.

### 1.2 Why Historical Sales Are Insufficient

The observed historical volume is **censored** — it represents the minimum of:

```
Observed_Volume = min(True_Demand, Systemic_Constraint)
```

Where systemic constraints include:
- **Credit limits** — distributor caps the outlet's monthly order value
- **Stockouts** — distributor runs out of product, can't fulfill orders
- **Delivery caps** — logistics limits how much can be delivered
- **Cooler capacity** — outlets with fewer coolers can't stock as much
- **Visit frequency** — salesperson visits determine order opportunities

**Result**: High-potential outlets may appear low-volume because they're constrained, while low-potential outlets may appear to be at capacity. Historical averages are therefore **biased downward**.

### 1.3 The Target Variable Problem

There is **no target variable (y)**. We don't have a column saying "true potential = X liters." This is an **unsupervised / semi-supervised estimation problem** — we must infer the hidden ceiling from observed patterns.

---

## 2. Mathematical Framework

### 2.1 Core Approach: Left-Censored Demand Estimation

We treat the problem as **left-censored data** (the problem statement mentions "left-censored demand curve"). The observed volume is a censored version of the true latent demand:

```
V_observed(i,t) = min(D_true(i,t), C(i,t))
```

Where:
- `V_observed(i,t)` = observed volume for outlet i in month t
- `D_true(i,t)` = true latent demand (what we want to estimate)
- `C(i,t)` = constraint ceiling (credit, stock, delivery, etc.)

### 2.2 Multi-Method Strategy

We will employ a **layered approach** combining multiple methods, then take a defensible aggregation:

#### Method 1: Quantile-Based Uncapping (Primary)

**Intuition**: For each outlet, the historical maximum (or high quantile like P90/P95) represents months when constraints were least binding. This is our best direct observation of near-true demand.

```python
# For each outlet:
potential_quantile(i) = percentile(V_monthly(i), 95)  # or max
```

**Enhancement**: Adjust by peer group. Group outlets by similar characteristics (type, size, distributor, location cluster), then use the group's P90 as a floor for underperformers:

```python
peer_potential(i) = max(outlet_P95(i), peer_group_P75(i))
```

#### Method 2: Tobit Regression (Censored Regression)

**Intuition**: A Tobit model explicitly handles censored data. We model the latent variable as:

```
D_true*(i) = β₀ + β₁·outlet_size + β₂·cooler_count + β₃·poi_density + ... + ε
```

Where `D_true*` is the uncensored latent demand. We observe `V = D_true*` when `D_true* < C` (no constraint), and `V = C` when constrained.

**Censoring detection**: We identify likely constrained observations where:
- Volume is suspiciously consistent month-over-month (hitting a cap)
- Volume is at a round number or cluster point
- Volume drops suddenly then recovers (stockout signature)

#### Method 3: Peer Benchmarking with Regression Adjustment

**Intuition**: Outlets with similar characteristics (size, type, location, POI density) should have similar potential. We:

1. **Cluster** outlets into peer groups using K-Means or hierarchical clustering on features
2. **Within each cluster**, identify the "frontier" outlets (top performers)
3. **Regress** frontier performance against features
4. **Predict** the frontier potential for all outlets in the cluster

```python
# Frontier = outlets performing at P90+ within their peer cluster
# Model: frontier_volume ~ features
# Predict: all outlets get the predicted frontier volume
```

#### Method 4: Constraint Detection & Uplift

**Intuition**: Directly detect which outlets are constrained and by how much.

Constraint signals:
- **Low coefficient of variation (CV)**: Monthly volume barely varies → hitting a cap
- **Truncated distribution**: Volume distribution has a hard right cutoff
- **Credit utilization**: Bill value consistently near a round threshold
- **Cooler saturation**: Volume per cooler is at physical capacity limits

For constrained outlets, apply an uplift multiplier:

```python
if is_constrained(i):
    uplift_factor = peer_unconstrained_ratio(i)
    potential(i) = observed_max(i) * uplift_factor
else:
    potential(i) = observed_P95(i)
```

### 2.3 Final Aggregation

Combine the four methods using a weighted ensemble:

```python
Final_Potential(i) = w1 * Quantile_Potential(i) 
                   + w2 * Tobit_Potential(i) 
                   + w3 * Peer_Benchmark_Potential(i)
                   + w4 * Uplift_Potential(i)
```

Apply January 2026 seasonality adjustment:

```python
Jan2026_Potential(i) = Final_Potential(i) * seasonality_factor(distributor(i), Jan_2026)
```

---

## 3. Data Landscape Summary

### 3.1 What We Have (from exploration)

| Dataset | Records | Key Facts |
|---------|---------|-----------|
| `transactions_history_final.csv` | 2,376,389 | 20K outlets × 10 SKUs × ~36 months. Median monthly outlet volume = 102L. Mean = 278L. Max = 10,458L. |
| `outlet_master.csv` | 20,000 | 7 outlet types (with 3 typo variants). 4 sizes + 196 nulls + 600 case errors. Coolers: 0–5. |
| `outlet_coordinates.csv` | 20,000 | 200 swapped lat/lon, 40 zero-zero coordinates. Rest within Sri Lanka bounds. |
| `distributor_seasonality.csv` | 360 | 10 distributors × 36 months. Values: Favorable / Moderate / Un-Favorable. |
| `holiday_list.csv` | 349 | 2023–2025 holidays. Types: Public, Bank, Poya Day, Mercantile. 2023 has 176 entries (likely includes weekends). |

### 3.2 What's Missing (Must Scrape)

| Data | Source | Why It Matters |
|------|--------|---------------|
| **POI density** (schools, hospitals, bus stops, banks, markets) | OpenStreetMap Overpass API | Outlet near a school/bus stop has higher foot traffic = higher potential |
| **Population density** | Proxy from POI density or WorldPop (if time permits) | More people nearby = more potential demand |
| **Road accessibility** | OSM road network (optional) | Outlets on main roads have more drive-by traffic |

### 3.3 What We Don't Have (Accept & Note in Report)

- No **credit limit** data per outlet (would directly show constraints)
- No **order frequency** / visit schedule data
- No **competitor** data (e.g., Pepsi coolers nearby)
- No **Product_Name** column (described in spec but missing from actual data)
- No **population/census** data at outlet level

---

## 4. Feature Engineering Plan

### 4.1 Transaction-Derived Features (per outlet, aggregated across all SKUs)

| Feature | Formula | Rationale |
|---------|---------|-----------|
| `txn_total_volume_36m` | Sum of all monthly volumes | Overall scale indicator |
| `txn_avg_monthly_volume` | Mean monthly volume | Baseline run-rate |
| `txn_median_monthly_volume` | Median monthly volume | Robust central tendency |
| `txn_max_monthly_volume` | Max single-month volume | Best-case observed (closest to true potential) |
| `txn_p90_monthly_volume` | 90th percentile of monthly volumes | Near-max, less noise than absolute max |
| `txn_p95_monthly_volume` | 95th percentile | Even closer to ceiling |
| `txn_std_monthly_volume` | Standard deviation | Variability indicator |
| `txn_cv_monthly_volume` | std / mean (coefficient of variation) | Low CV → possibly constrained |
| `txn_months_active` | Count of months with transactions | Coverage indicator |
| `txn_volume_trend_slope` | OLS slope of monthly volume over time | Growing or declining outlet |
| `txn_recent_6m_avg` | Mean of last 6 months | Recent performance |
| `txn_growth_ratio` | recent_6m_avg / first_6m_avg | Growth trajectory |
| `txn_sku_diversity` | Count of distinct SKUs ordered | Breadth of product engagement |
| `txn_avg_bill_value` | Mean Total_Bill_Value per month | Revenue scale |
| `txn_revenue_per_liter` | avg_bill / avg_volume | Price tier indicator |
| `txn_peak_month` | Month with highest volume | Seasonality pattern |
| `txn_consecutive_zero_months` | Longest streak of zero-order months | Dormancy/constraint signal |

### 4.2 Outlet Attribute Features

| Feature | Source | Encoding |
|---------|--------|----------|
| `outlet_type_encoded` | Outlet_Type (cleaned) | One-hot or ordinal |
| `outlet_size_encoded` | Outlet_Size (cleaned) | Ordinal: Small=1, Medium=2, Large=3, XL=4 |
| `outlet_cooler_count` | Cooler_Count | Numeric |
| `outlet_cooler_capacity_proxy` | Cooler_Count × avg liters per cooler | Physical capacity estimate |

### 4.3 Geographic & POI Features

| Feature | Source | Notes |
|---------|--------|-------|
| `geo_latitude`, `geo_longitude` | Cleaned coordinates | After swap-fix |
| `geo_province` | Inferred from distributor mapping | Western, Central, NW, Southern |
| `geo_poi_total_1km` | POI count within 1km radius | Overall location activity |
| `geo_poi_schools_1km` | Schools within 1km | Youth foot traffic |
| `geo_poi_hospitals_1km` | Hospitals/clinics within 1km | Steady foot traffic |
| `geo_poi_bus_stops_500m` | Bus stops within 500m | Transit-driven demand |
| `geo_poi_shops_1km` | Other shops/retail within 1km | Commercial density |
| `geo_poi_worship_1km` | Places of worship within 1km | Community gathering signal |
| `geo_outlet_density_2km` | Count of other outlets within 2km | Competition / saturation |

### 4.4 Distributor & Calendar Features

| Feature | Source | Notes |
|---------|--------|-------|
| `dist_id` | Transaction → Distributor_ID mapping | Categorical |
| `dist_seasonality_jan2026` | Seasonality index for Jan 2026 | Favorable/Moderate/Un-Favorable encoded |
| `cal_holidays_jan2026` | Count of holidays in Jan 2026 | More holidays = potentially different demand |
| `cal_poya_days_jan2026` | Poya days in Jan 2026 | Sri Lanka-specific: poya days = no alcohol sales |

---

## 5. Prediction Target

### 5.1 Output Specification

| Column | Type | Description |
|--------|------|-------------|
| `Outlet_ID` | String | `OUT_00001` to `OUT_20000` |
| `Maximum_Monthly_Liters` | Float | Predicted latent potential volume for January 2026 |

### 5.2 Sanity Check Bounds

Based on data exploration, reasonable predictions should satisfy:

| Check | Expected Range | Reasoning |
|-------|---------------|-----------|
| Minimum potential | > 0 liters | Every active outlet has some potential |
| Median potential | 100–500 liters | Observed median monthly is ~102L, potential should be higher |
| Mean potential | 200–800 liters | Potential is an uplift over observed mean of 278L |
| Maximum potential | < 15,000 liters | Largest observed single-month was ~10,458L; potential shouldn't be wildly above |
| Potential ≥ Observed max | True for most outlets | Potential is a ceiling — should exceed or equal historical best |

### 5.3 Seasonality Adjustment for January 2026

The prediction must be **specifically for January 2026**, not a generic potential. This requires:

1. Compute the "all-time" latent potential for each outlet
2. Multiply by the January seasonality factor for that outlet's distributor
3. If January 2026 seasonality data isn't available, extrapolate from January 2023/2024/2025 patterns

---

## 6. Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| POI scraping takes too long (20K outlets × Overpass API) | Delays gold layer | Batch by geographic clusters; use generous radius to reduce queries; cache results |
| Tobit model implementation complexity | May not finish in time | Have quantile-based method as reliable fallback — it alone is defensible |
| Overfitting the "potential" to noise | Predictions too extreme | Use peer-group capping; validate that potential follows logical ordering (Large > Medium > Small on average) |
| Zero-coordinate outlets (40) can't get POI data | Missing features for 40 outlets | Impute POI features from peer group averages |
| No January 2026 seasonality data in dataset | Can't adjust for month | Extrapolate from historical January patterns (2023/2024/2025) |

---

## 7. Timeline & Milestones

| Time Block | Milestone | Status |
|------------|-----------|--------|
| **May 15, 20:00–21:00** | ✅ Data exploration complete | Done |
| **May 15, 21:00–22:00** | ✅ Architecture + docs written | Done |
| **May 15, 22:00–23:00** | 🔲 Bronze ingest + DQ framework | Pending |
| **May 15, 23:00–01:00** | 🔲 Silver layer (cleaning + quarantine) | Pending |
| **May 16, 01:00–03:00** | 🔲 POI scraping (can run overnight) | Pending |
| **May 16, 03:00–06:00** | 🔲 Gold layer (feature engineering) | Pending |
| **May 16, 06:00–12:00** | 🔲 Latent potential model + predictions | Pending |
| **May 16, 12:00–18:00** | 🔲 Validation, sanity checks, iteration | Pending |
| **May 16, 18:00–24:00** | 🔲 README, PDF report writing | Pending |
| **May 17, 00:00–05:30** | 🔲 Final review, submission prep | Pending |
| **May 17, 06:00 AM** | 🔲 **SUBMIT** | Deadline |

---

## 8. GenAI Transparency Log

> This section documents how our team used Generative AI during the competition. Required for the 20% evaluation criteria.

| Timestamp | AI Tool | What Was Done | How Output Was Validated |
|-----------|---------|---------------|-------------------------|
| May 15, 20:00 | Antigravity (Claude) | Data exploration — initial schema inspection, statistics computation, anomaly detection | Cross-verified all counts and statistics against raw data; manually confirmed typo patterns and coordinate anomalies |
| May 15, 21:00 | Antigravity (Claude) | Architecture documentation — generated lakehouse pipeline architecture, directory structure, and data flow diagrams | Team reviewed for completeness against competition rubric; adjusted structure to match exact deliverable requirements |
| May 15, 21:30 | Antigravity (Claude) | Solution methodology — brainstormed censored demand estimation approaches (Tobit, quantile, peer benchmarking) | Team discussed mathematical soundness; validated that approaches are cited in literature for demand estimation problems |
| ... | ... | ... | ... |

*This log will be updated continuously throughout the hackathon.*
