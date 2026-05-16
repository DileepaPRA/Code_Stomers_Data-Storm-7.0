# 🏗️ Architecture — DataStorm 7.0 Lakehouse Pipeline

> **Team**: Code_Stomers  
> **Competition**: DataStorm v7.0 – Storming Round (Preliminary)  
> **Deadline**: May 17, 2026 — 06:00 AM IST  

---

## 1. High-Level Architecture

We follow a **Medallion / Lakehouse** pattern with three layers, powered by Python modules and Jupyter Notebooks:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DATA STORM 7.0 PIPELINE                        │
│                                                                        │
│  ┌──────────┐      ┌──────────┐      ┌──────────┐      ┌───────────┐  │
│  │  BRONZE   │ ──► │  SILVER   │ ──► │   GOLD    │ ──► │ PREDICTION │  │
│  │ (Raw)     │     │ (Cleaned) │     │ (Enriched)│     │  (Output)  │  │
│  └──────────┘      └────┬─────┘      └──────────┘      └───────────┘  │
│                         │                                              │
│                    ┌────▼──────┐                                       │
│                    │ REJECTED  │                                       │
│                    │ RECORDS   │                                       │
│                    │ (Quarantine)                                      │
│                    └───────────┘                                       │
│                                                                        │
│  ┌──────────────────────────────────────────────────┐                  │
│  │  EXTERNAL DATA: POI, WEATHER, POPULATION PROXY  │ ──► feeds GOLD   │
│  │  (OpenStreetMap / Open-Meteo API / Clustering)  │                  │
│  └──────────────────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Directory Structure

The project has been professionally structured to separate data, source code, analytical notebooks, and documentation.

```
Code_Stomers_Data-Storm-7.0/          
│
├── src/                              ← Python source code (pipeline modules)
│   ├── config.py                     ← Shared paths, constants, parameters
│   ├── dq_checks.py                  ← Reusable DQ check framework (8 check types)
│   ├── ingest.py                     ← Bronze: raw ingestion (zero transforms)
│   ├── cleaning.py                   ← Silver: DQ checks, cleaning, quarantine
│   ├── external_data.py              ← External: OSM POI, Weather, Population Density
│   ├── features.py                   ← Gold: 57-feature model-ready dataset
│   ├── model.py                      ← Prediction: 4-method hybrid ensemble (LightGBM)
│   ├── validate_output.py            ← CI gate: automated output assertion checks
│   └── __init__.py
│
├── notebooks/                        ← Jupyter Notebooks for EDA and validation
│   └── 01_EDA_and_Modeling.ipynb     ← Interactive analysis of predictions
│
├── docs/                             ← Reference documentation
│   ├── architecture.md               ← System architecture & data flow (This file)
│   ├── guidelines.md                 ← Coding standards & known anomalies
│   └── solution_and_targets.md       ← Methodology, math framework, ML models
│
├── data/                             ← Lakehouse storage (Ignored in Git except output)
│   ├── raw/                          ← Original raw extract
│   ├── bronze/                       ← Byte-for-byte raw copy
│   ├── silver/                       ← Cleaned data
│   │   └── rejected_records/         ← Quarantined records with failure reasons
│   ├── gold/                         ← Enriched features
│   └── output/                       ← Final predictions (`Code_Stomers_predictions.csv`)
│
├── reports/                          ← Output reports (PDF/HTML)
├── requirements.txt                  ← Python dependencies
├── .gitignore                        ← Excludes data/ (except output)
└── README.md                         ← Run instructions
```

---

## 3. Layer Definitions

### 3.1 Bronze Layer (Raw Ingestion)

| Rule | Detail |
|------|--------|
| **Purpose** | Preserve the original data exactly as provided. |
| **Transformations** | NONE — byte-for-byte copy from `data/raw/` to `data/bronze/`. |
| **Module** | `src/ingest.py` |
| **Output** | Exact copies of the 5 CSV files in `data/bronze/`. |

### 3.2 Silver Layer (Cleaned + Quarantined)

| Rule | Detail |
|------|--------|
| **Purpose** | Apply all DQ checks, clean data, quarantine failures. |
| **Key Principle** | **Nothing is silently dropped** — every rejected record goes to `rejected_records/` with a documented `DQ_Failure_Reason`. |
| **Module** | `src/cleaning.py` |
| **DQ Framework** | `src/dq_checks.py` — reusable, parameterizable functions. |
| **Outputs** | Clean CSVs in `data/silver/`, rejected CSVs in `data/silver/rejected_records/`. |

**DQ Checks Applied per Dataset:**

| Dataset | Checks |
|---------|--------|
| `transactions` | Duplicate, Null (mandatory fields), Referential Integrity (Outlet_ID, Distributor_ID), Value Range (Volume >= 0), Consistency (Zero volume ghost entry). |
| `outlet_master` | Duplicate, Format, Standardize typos (`Bakry`→`Bakery`, ` Eatery `→`Eatery`, `small`→`Small`), Null imputation for size based on type. |
| `outlet_coordinates` | Duplicate, Swapped lat/lon detection & fix, Zero coordinate detection, Value bounds (Sri Lanka lat 5.9–9.9, lon 79.4–82.0). |
| `seasonality` | Duplicate, Null, Value bounds. |
| `holidays` | Duplicate, Null. |

### 3.3 Gold Layer (Enriched + Feature Engineering)

| Rule | Detail |
|------|--------|
| **Purpose** | Produce model-ready feature matrix at the **outlet level** (57 features). |
| **Inputs** | All Silver-layer datasets + external features. |
| **Module** | `src/features.py` |
| **Grain** | One row per `Outlet_ID`. |

### 3.4 External Data

| Rule | Detail |
|------|--------|
| **Purpose** | Enrich outlet profiles with localized environmental context. |
| **Module** | `src/external_data.py` |
| **Sources** | OpenStreetMap (Overpass API for POIs), Open-Meteo API (Weather), Haversine spatial clustering (Population proxy). |
| **Method** | Batch queries (bounding box) to bypass API rate limits, grid deduplication for weather, and spatial joins via Haversine distance. |

---

## 4. Script Execution Order

Run these in strict sequence — each depends on the previous:

```bash
# Step 1: Copy raw files to bronze
python src/ingest.py

# Step 2: Clean data, quarantine failures to silver
python src/cleaning.py

# Step 3: Scrape External Data (POI, Weather, Density)
python src/external_data.py

# Step 4: Feature engineering → gold layer (57 features)
python src/features.py

# Step 5: 4-method hybrid ensemble model → predictions
python src/model.py

# Step 6: Automated validation (kill-switch assertions)
python src/validate_output.py
```

**Total pipeline runtime estimate**: ~15–20 minutes (mostly POI scraping).

---

## 5. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **src/ Python Package** | Standardizing scripts into a modular package ensures cleaner code organization and easier imports. |
| **CSV over Parquet** | Simplicity, easy inspection, small enough dataset (20K outlets). |
| **Shared `config.py`** | All paths, constants, and parameters in one place — change once, apply everywhere. |
| **`dq_checks.py`** | Reusable Data Quality check architecture standardizes anomaly detection across datasets. |
| **Quarantine System** | Transparency is critical in data engineering. `DQ_Failure_Reason` tracking prevents silent logic bugs. |
| **Batch API Scraping** | Querying external APIs per-outlet (20,000 times) fails due to rate limits. Pulling a full bounding box and mapping locally is exponentially faster. |

---

## 6. Technology Stack

| Component | Tool |
|-----------|------|
| Language | Python 3.10+ |
| Data Processing | `pandas`, `numpy` |
| Machine Learning | `lightgbm` (gradient boosting), `scikit-learn` (KMeans), `scipy` |
| External API | `requests`, `osmnx`, `geopandas` |
| Notebooks | `jupyter`, `matplotlib`, `seaborn` |
