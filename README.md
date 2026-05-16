# DataStorm 7.0 — Storming Round Submission

## Team: Code_Stomers

### Challenge: Latent Maximum Monthly Volume Potential Estimation

Predict the **Maximum Monthly Purchase Potential** (in liters) for 20,000 traditional trade
retail outlets across 4 provinces in Sri Lanka for **January 2026**.

---

## Quick Start

### Prerequisites

```bash
pip install -r requirements.txt
```

Python 3.10+ required.

### Run the Full Pipeline

```bash
# Step 1: Bronze Layer — Copy raw files (no transforms)
python src/ingest.py

# Step 2: Silver Layer — Clean data, quarantine failures
python src/cleaning.py

# Step 3: POI Scraping — External data from OpenStreetMap + Weather + Density
python src/external_data.py

# Step 4: Gold Layer — Feature engineering
python src/features.py

# Step 5: Model — 4-method hybrid ensemble (includes LightGBM)
python src/model.py

# Step 6: Validate — Automated kill-switch assertion checks
python src/validate_output.py
```

**Output**: `data/output/Code_Stomers_predictions.csv` — 20,000 rows with `Outlet_ID` and `Maximum_Monthly_Liters`.

---

## Project Structure (Lakehouse Architecture)

```
Code_Stomers_Data-Storm-7.0/
├── src/                              # All pipeline code
│   ├── config.py                     # Shared paths, constants, parameters
│   ├── dq_checks.py                  # Reusable DQ check framework (8 check types)
│   ├── ingest.py                     # Bronze: raw ingestion (zero transforms)
│   ├── cleaning.py                   # Silver: cleaning + quarantine
│   ├── external_data.py              # External: POI + Weather + Population
│   ├── features.py                   # Gold: feature engineering (57 features)
│   ├── model.py                      # Model: 4-method hybrid ensemble (LightGBM)
│   └── validate_output.py            # CI gate: automated output assertions
│
├── notebooks/                        # Jupyter notebooks for EDA and evaluation
│   └── 01_EDA_and_Modeling.ipynb
│
├── docs/                             # Reference documentation
│   ├── architecture.md               # System architecture & data flow
│   ├── guidelines.md                 # Coding standards & known anomalies
│   └── solution_and_targets.md       # Methodology & math framework
│
├── reports/                          # Optional output reports
│
├── data/                             # Lakehouse data layers (gitignored)
│   ├── raw/                          # Original raw extract
│   ├── bronze/                       # Raw copy
│   ├── silver/                       # Cleaned data + quarantine
│   ├── gold/                         # Enriched features + intermediate ML tables
│   └── output/                       # Final predictions
│
├── requirements.txt
├── .gitignore
└── README.md
```

---

## Methodology

### Data Forensics (Silver Layer)

Our reusable DQ framework (`dq_checks.py`) implements 8 parameterizable check types:
Duplicate, Null, Referential Integrity, Value Range, Format, Outlier (IQR), Consistency, and Whitespace.

**Key anomalies detected and handled:**

- **985 outlet type typos** (`Bakry`→`Bakery`, `Grocry`→`Grocery`, ` Eatery`→`Eatery`)
- **600 case inconsistencies** in outlet size (`small`→`Small`)
- **196 null outlet sizes** — imputed using mode of same outlet type
- **200 swapped coordinates** (lat/lon reversed) — detected via `lat > 50°` and mathematically fixed
- **40 zero coordinates** (0.0, 0.0) — quarantined
- **4,753 negative volumes** (credit notes/returns representing reverse logistics, not demand) — quarantined
- **100 zero volumes** (ghost entries) — quarantined

Total quarantined: **4,893 records** computationally routed to `data/silver/rejected_records/` with a documented `DQ_Failure_Reason`.

### Latent Potential Model (4-Method Hybrid Ensemble)

The observed volume is **censored**: `V_obs = min(True_Demand, Constraint)`. We estimate the uncensored demand ceiling using:

1. **Quantile Uncapping (P95)** — For each outlet, the 95th percentile of monthly volumes approximates months when constraints were least binding. Growth trend adjustments applied for growing outlets.

2. **Peer Benchmarking (K-Means)** — Outlets clustered by size, type, cooler count, POI density (K=20). Underperformers lifted to peer group's P75 frontier. Top performers benchmarked to P90.

3. **Constraint Detection & Uplift** — Outlets with low coefficient of variation (CV < 0.3) or flat-top distributions (P95/max > 0.9) flagged as constrained. Capacity-based uplift (5-50%) applied using size and cooler count as proxy.

4. **ML Ceiling (LightGBM)** — A supervised gradient boosting model trained exclusively on unconstrained outlets (CV > 0.3, where observed ≈ true demand). Predicts the demand ceiling for constrained outlets using the full 57-feature matrix.

**Final**: Weighted hybrid ensemble (heuristic + ML) → Seasonality adjustment for January 2026 → Floor at historical average.  
**Failover Strategy**: Quarantined/dropped `Outlet_ID` entries are automatically re-injected with the dataset median potential to guarantee a 20,000-row perfect submission.

### Feature Engineering (57 Features)

- **Transaction history (`txn_`)**: volume stats (mean, median, max, P90, P95, std, CV), trend slope, growth ratio, recent 6m average, revenue per liter, SKU diversity
- **Outlet attributes (`outlet_`)**: size (ordinal), type (one-hot), cooler count
- **Geographic & POI (`geo_`, `poi_`)**: lat/lon, outlet density, schools, hospitals, bus stops, banks, shops, worship, restaurants, tourism within 1km
- **Climate & Population (`weather_`, `pop_`)**: January avg temperature, precipitation, outlet density at 500m/1km/2km
- **Seasonality & Calendar (`dist_`, `cal_`)**: January distributor seasonality index, province encoding, holiday count, Poya days

---

## Evaluation Results

| Metric                      | Value        |
| --------------------------- | ------------ |
| Total outlets               | 20,000       |
| Prediction range            | 50L — 3,825L |
| Mean potential              | 413L         |
| Median potential            | 183L         |
| Potential >= historical avg | 100.0%       |
| Potential >= historical max | 68.4%        |
| Validation checks passed    | 8/8          |

**Size ordering** (validates causal model logic):

- Small: 152L avg → Medium: 304L → Large: 1,003L → Extra Large: 2,172L ✓

---

## GenAI Transparency

Generative AI (Antigravity/Claude) was strategically used as an engineering accelerator for:

- **Data exploration**: Schema inspection, statistics computation, anomaly detection
- **Boilerplate generation**: Modular DQ framework and Lakehouse pipeline structure
- **Methodology brainstorming**: Left-censored demand estimation approaches
- **Pipeline optimization**: Batch bounding-box POI scraping to bypass API rate-limiting
- **ML integration**: LightGBM hybrid model architecture for constrained outlet ceiling prediction

All AI-generated code was critically reviewed, executed, tested, and iteratively refined.
See `docs/solution_and_targets.md` Section 6 for the full, detailed transparency log.
